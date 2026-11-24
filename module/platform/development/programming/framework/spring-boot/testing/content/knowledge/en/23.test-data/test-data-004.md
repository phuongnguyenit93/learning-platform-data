# Spring Boot Testing: @SqlConfig, Transaction Modes, and Cleanup Scripts

## 1. The Problem: Having Data for Tests Without Leaving Data Behind

An integration test suite requires repeatable data. Usually, you want to:

1. Create schemas and **seed** fixed records before a test.
2. Execute production code via a repository, `JdbcTemplate`, or real HTTP calls.
3. Assert data, errors, and side effects.
4. **Clean up** the created data, even when the test fails.
5. Avoid corrupting the database or another test's data.

Spring TestContext provides `@Sql` and `@SqlConfig` to perform these steps. However, merely adding `@Sql(scripts = "...cleanup.sql", executionPhase = AFTER_TEST_METHOD)` **does not guarantee the cleanup script will commit**. If the test runs with `@Transactional`, the cleanup script may by default run **inside the test's own transaction** and then roll back along with everything else.

The most important takeaway of this lesson:

**Choose `transactionMode` based on transaction ownership, not just the script's filename.**

- Seeds serving only a single JDBC/JPA test with default rollback → typically use `INFERRED`, letting the seed join the test-managed transaction.
- Seeds that must be visible to code running in a **different transaction/connection** (e.g., real HTTP server, `REQUIRES_NEW`, another process) → use `ISOLATED` or a separately committed setup.
- Cleanups that must delete records **committed independently** → typically require `AFTER_TEST_METHOD` **and `ISOLATED`**.
- Code that only relies on test-transaction rollback without producing committed side effects → no cleanup script is needed to delete rows that already roll back.

This lesson covers mechanism explanations, decision matrices, subtle pitfalls, and a Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2 / JUnit Jupiter / H2 example suite proving each case with real tests.

### Learning Outcomes

- Know how `@Sql` differs from `@SqlConfig` and when `SqlScriptsTestExecutionListener` runs.
- Choose properly among `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS`, and `AFTER_TEST_CLASS`.
- Understand `TransactionMode.DEFAULT`, `INFERRED`, and `ISOLATED` accurately.
- Write SQL fixtures with clear paths, UTF-8 charset, valid separators, and comment rules.
- Use `@SqlMergeMode(MERGE)` so class-level cleanup is not disabled by method-level seeds.
- Distinguish cleanup scripts from test rollback so cleanup scripts do not get rolled back.
- Pick safe `ErrorMode` settings without hiding SQL failures that cause false-positive passes.
- Test a real HTTP server with committed data and assert state after `@AfterTransaction`.
- Use isolated test schemas/databases, avoiding production databases and flaky parallel tests.

## 2. What Is @Sql and What Executes It?

`@Sql` is an annotation in the **Spring TestContext Framework** under package:

~~~java
import org.springframework.test.context.jdbc.Sql;
~~~

Example:

~~~java
@Test
@Sql("/sql/seed-users.sql")
void loadsUsers() {
    // Test code sees data loaded from the SQL script.
}
~~~

This is an **illustrative snippet**, not a standalone test file.

`@Sql` declares:

- `scripts` or `value`: one or more SQL files/resource paths.
- `statements`: SQL statements declared inline in the annotation.
- `executionPhase`: whether the script runs before/after a method or before/after a class.
- `config`: a local `@SqlConfig` for parsing, datasource, and transaction settings.
- Multiple/repeatable `@Sql`: a test can declare multiple script groups with different phases and configs.

`SqlScriptsTestExecutionListener` executes the scripts. This listener is registered by default in Spring TestContext, so you do not need to call `Files.readString()`, `Connection.createStatement()`, or open a Hibernate `Session` just to run fixtures.

**Do not confuse with Boot SQL initialization:** Spring Boot reads `schema.sql`/`data.sql` when the **ApplicationContext/DataSource initializes**, whereas `@Sql` runs within **each test class/method's lifecycle**. Both can coexist, but schema creation and data seeding responsibilities must be clearly separated.

### 2.1 Example of Seeding Before and Cleaning Up After

~~~java
@Test
@Sql(
    scripts = "/sql/seed-example.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-example.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
void shouldWorkWithCommittedFixture() {
    // Code under test may execute on another connection or thread.
}
~~~

This is an **annotated example**, without the actual scripts, DB, or test class. Both seed and cleanup use `ISOLATED` to **commit independently**, without relying on test-managed rollback.

If all seed and test operations run within a single test-opened transaction with no independent commits, an `ISOLATED` seed is unnecessary and even creates committed data that must be cleaned up explicitly.

## 3. Lifecycle Ordering: BEFORE, AFTER, and the Test Transaction

In JUnit Jupiter + Spring TestContext, a `@Transactional` test usually follows this sequence:

~~~text
ApplicationContext initializes; Boot schema.sql runs if configured
           |
           v
@Sql BEFORE_TEST_CLASS       (if declared; once per class)
           |
           v
@BeforeTransaction            (if a test-managed transaction exists)
           |
           v
TransactionalTestExecutionListener BEGINS test transaction
           |
           v
@Sql BEFORE_TEST_METHOD       (according to transactionMode)
           |
           v
JUnit @BeforeEach             (inside test transaction)
           |
           v
JUnit @Test                   (inside test transaction)
           |
           v
JUnit @AfterEach              (inside test transaction)
           |
           v
@Sql AFTER_TEST_METHOD        (according to transactionMode)
           |
           v
TransactionalTestExecutionListener ROLLBACK or COMMIT
           |
           v
@AfterTransaction             (outside test transaction)
           |
           v
@Sql AFTER_TEST_CLASS        (if declared; once per class)
~~~

**Pay close attention to the order:** `SqlScriptsTestExecutionListener` has order **5000**, running after `TransactionalTestExecutionListener` (order **4000**) in the “before” direction; in the “after” direction, the order reverses. Therefore, `@Sql AFTER_TEST_METHOD` executes while the test-managed transaction **may still be active**, before the transaction listener rolls back. That is the exact trap of `INFERRED` cleanup.

JUnit's `@BeforeEach` and `@AfterEach` run inside the test-managed transaction, not as an automatic way to clean up rows committed by another transaction.

### 3.1 Class-Level Scripts

Spring Framework 6.1+ supports:

~~~java
@Sql(
    scripts = "/sql/create-shared-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
@Sql(
    scripts = "/sql/drop-shared-schema.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
class SharedSchemaTests {
    // ...
}
~~~

This is an **illustrative snippet**, not part of the runnable project below. Class-level phases run once per class, outside any test method's test-managed transaction. `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` declarations are **not overridden by method-level `@Sql`**. In shared schemas, strictly avoid dropping tables or schemas used by other test classes.

### 3.2 When a Test Has No @Transactional

If a test has no test-managed transaction, `INFERRED` can open a short-lived Spring-managed transaction to run the script and commit it when a transaction manager exists; if only a `DataSource` exists with no manager, the script runs directly on the `DataSource`. Never oversimplify `INFERRED` to mean “always roll back” or “always commit”: it **depends** on whether the context already has an active transaction.

## 4. What Does @SqlConfig Configure?

Annotation:

~~~java
import org.springframework.test.context.jdbc.SqlConfig;
~~~

It can be placed **globally on the test class**:

~~~java
@SqlConfig(encoding = "UTF-8", errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
@JdbcTest
class RepositorySqlTests {
    // ...
}
~~~

Or **locally inside `@Sql`**:

~~~java
@Sql(
    scripts = "/sql/custom-format.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = "@@"))
~~~

Key attributes:

| Attribute | Purpose |
| --- | --- |
| `dataSource` | `DataSource` bean name when multiple datasources exist or discovery is ambiguous |
| `transactionManager` | `PlatformTransactionManager` bean name used to run scripts |
| `transactionMode` | `DEFAULT`, `INFERRED`, `ISOLATED` |
| `encoding` | Character encoding of SQL resources, e.g. `UTF-8` |
| `separator` | SQL statement delimiter, implicitly defaulting to `;` |
| `commentPrefix` | Single-line comment prefix; defaults to `--` |
| `commentPrefixes` | Multiple single-line comment prefixes, alternative to `commentPrefix` |
| `blockCommentStartDelimiter` | Opening block comment delimiter; defaults to `/*` |
| `blockCommentEndDelimiter` | Closing block comment delimiter; defaults to `*/` |
| `errorMode` | Policy to fail, continue, or ignore failed drops |

### 4.1 How Are Global and Local @SqlConfig Merged?

Every `@SqlConfig` attribute has an **explicit default**:

- String: `""`.
- String array: `{}`.
- Enum: `DEFAULT`.

When global config exists on the class and local config inside `@Sql`, any local attribute with an explicit value **other than the default** overrides global; local attributes left at default **inherit from global**.

Example:

~~~java
@SqlConfig(
    encoding = "UTF-8",
    errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class Example {
    @Test
    @Sql(
        scripts = "/sql/custom.sql",
        config = @SqlConfig(separator = "@@"))
    void customSql() {
        // separator = "@@" (local)
        // encoding = "UTF-8" (global)
        // errorMode = FAIL_ON_ERROR (global)
    }
}
~~~

This snippet is illustrative and lacks Spring test annotations and real files. If you want a local attribute to revert to a non-global default, you cannot use `DEFAULT` to “erase global”; structure the annotation scopes appropriately instead.

### 4.2 Do Not Mix commentPrefix and commentPrefixes

`commentPrefix` and `commentPrefixes` are **mutually exclusive alternatives**; never specify both at once. If a script uses `--` and `#`, write:

~~~java
@SqlConfig(commentPrefixes = {"--", "#"})
~~~

This snippet illustrates configuration only. For real SQL, align comment syntax with what both the parser and DB dialect support, and avoid splitting SQL prematurely on characters inside string literals.

### 4.3 When Multiple DataSources or TransactionManagers Exist

Suppose an app has a primary datasource and a reporting datasource. If `@Sql` implicitly picks primary by mistake, seeds land in DB A while the repository under test queries DB B.

~~~java
@Sql(
    scripts = "/sql/report-fixture.sql",
    config = @SqlConfig(
        dataSource = "reportingDataSource",
        transactionManager = "reportingTransactionManager",
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

This pattern only works if **both beans genuinely have those names** and the transaction manager manages that exact datasource. Never guess bean names; check the application configuration and verify with read-back queries on the same datasource. `ISOLATED` requires a matching transaction manager to commit the new transaction.

## 5. transactionMode = DEFAULT, INFERRED, and ISOLATED

This is the core of the lesson.

`@SqlConfig.TransactionMode` has three enum values:

### DEFAULT

`DEFAULT` is the annotation default value and inherits the global config if present. Without any override, the effective behavior is **INFERRED**. It **does not** mean “skip transactions” or “definitely commit.”

### INFERRED

Spring infers execution behavior from the context:

1. Neither a datasource nor a transaction manager → error.
2. Datasource present, no transaction manager → executes directly on the datasource with no Spring-managed transaction.
3. Transaction manager and suitable datasource present, and **a transaction is already active** → runs the script **inside that transaction**.
4. Transaction manager present, **no transaction active** → opens a new transaction and **commits after the script**.

Thus, in default-transactional `@JdbcTest`/`@DataJpaTest`, `@Sql INFERRED BEFORE_TEST_METHOD` joins the test transaction and the seed rolls back after the test. Meanwhile, the exact same script in a test without `@Transactional` can commit.

### ISOLATED

`ISOLATED` runs the script in a **brand-new, independent transaction**, committing immediately upon successful completion. If a test transaction is active, it is suspended while the isolated script executes. If no transaction is active, the script still opens its own transaction.

Key caveats:

- `ISOLATED` **does not** create a brand-new DB; it targets the same datasource and schema using a separate transaction.
- `ISOLATED` requires a resolvable transaction manager, not a bare `DataSource`.
- It does not roll back if the test subsequently fails, because it already committed when the script ran.
- If the script touches rows locked by another active test transaction, the isolated script can block or time out. Use distinct fixture IDs and avoid conflicting updates.

### 5.1 Decision Matrix

| Test Context | Phase | Mode | Where Does SQL Usually Run? | What Happens When Test Rolls Back? |
| --- | --- | --- | --- | --- |
| `@JdbcTest` default TX | BEFORE | INFERRED | Test transaction | Seed rolls back |
| `@JdbcTest` default TX | AFTER | INFERRED | Test transaction still open | Cleanup rolls back too; does not delete committed rows outside TX |
| Test with TX | BEFORE | ISOLATED | New transaction, commits | Seed persists unless cleaned up separately |
| Test with TX | AFTER | ISOLATED | New transaction, commits | Cleanup commits independently, unaffected by test rollback |
| Test without TX, manager present | BEFORE | INFERRED | New transaction, commits | No test rollback to clean up |
| Test without TX, manager present | AFTER | INFERRED | New transaction, commits | Cleanup usually commits, though dependent on context |
| Test without TX, manager present | BEFORE/AFTER | ISOLATED | New transaction, commits | Explicit commit |
| `DataSource` only, no manager | BEFORE/AFTER | INFERRED | Runs directly on datasource | Depends on auto-commit / DB behavior |
| `DataSource` only, no manager | BEFORE/AFTER | ISOLATED | Cannot start a valid isolated Spring TX | Requires manager; throws error |

**Never design cleanup around the assumption “`@Sql` runs after the test so it must commit.”** Phase controls **timing**; `transactionMode` controls **transaction**. They are two orthogonal axes.

## 6. Three Common Scenarios

### 6.1 Repository Test Where Everything Shares the Test-Managed Transaction

~~~java
@JdbcTest
class RepositoryTest {
    @Test
    @Sql("/sql/seed-rows.sql")
    void query() {
        // INFERRED + transactional @JdbcTest
        // seed and test writes roll back together.
    }
}
~~~

An explicit `@Sql` cleanup is unnecessary when every operation joins the test transaction with no external side effects. Unnecessary cleanup can even fail if it targets committed fixtures or needlessly complicates tests.

### 6.2 Test with an External/Server/Inner Transaction Reading Committed Fixtures

~~~java
@Test
@Sql(
    scripts = "/sql/seed-committed.sql",
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-committed.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void externalCallerNeedsFixture() {
    // HTTP server or REQUIRES_NEW sees the committed seed.
}
~~~

If the seed stayed `INFERRED` inside the test TX, a server thread or `REQUIRES_NEW` under `READ_COMMITTED` could **fail to see the data** or block on locks. Never raise isolation levels casually just to work around uncommitted fixture data.

### 6.3 Test Without a Test-Managed Transaction

~~~java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJdbcTests {
    // Executes SQL via JDBC with no outer test-managed TX.
    // Committed writes must be cleaned up explicitly.
}
~~~

When disabling the test transaction, the test database no longer rolls back writes automatically. Use `@Sql AFTER_TEST_METHOD` with `ISOLATED`, cleanup in `@AfterEach` outside a transaction, schema truncation/reset, or an isolated database depending on scope.

## 7. Which errorMode Should You Use?

`SqlConfig.ErrorMode` offers these modes:

| Mode | Meaning | Recommendation |
| --- | --- | --- |
| `DEFAULT` | Uses default/inherited config, implicitly `FAIL_ON_ERROR` | Suitable for most tests |
| `FAIL_ON_ERROR` | Any SQL error fails the script | **Recommended** for critical seed/cleanup |
| `CONTINUE_ON_ERROR` | Logs error and keeps running subsequent statements | Dangerous: can leave partial/incomplete data |
| `IGNORE_FAILED_DROPS` | Ignores errors on failed `DROP` statements; other errors fail | Consider only for cleanup/schema resets where objects may not exist |

Avoid `CONTINUE_ON_ERROR` just to make a test pass when cleanup lacks delete permissions or seeding hits a unique constraint violation. Tests must know when fixtures fail so they do not produce false positives.

If cleanup uses safe SQL:

~~~sql
DELETE FROM demo_item WHERE item_id LIKE 'CASE-%';
~~~

then matching zero rows **is not an error**; a `DELETE` affecting 0 rows normally succeeds. Neither `IGNORE_FAILED_DROPS` nor `CONTINUE_ON_ERROR` is needed.

Depending on DDL dialect, prefer `DROP TABLE IF EXISTS` where supported. `ErrorMode` is no substitute for proper DB permissions or schema isolation.

### 7.1 FAIL_ON_ERROR with AFTER Scripts

If a test fails and the cleanup SQL also fails, the test report may surface both the assertion failure and the cleanup failure. That is valuable signal. Never mask cleanup failures with `CONTINUE_ON_ERROR`, because leftover committed rows will break subsequent tests.

When cleanup is critical, log the script name, datasource, ID/prefix, and transaction mode; never log secrets or production credentials.

## 8. Script Resource Paths, Encoding, Separators, and Comment Syntax

### 8.1 Paths

Given test class `example.sqldemo.SampleSqlTest`:

| @Sql path | How Spring Resolves It |
| --- | --- |
| `"setup.sql"` | Relative to class package: `example/sqldemo/setup.sql` |
| `"/sql/setup.sql"` | Absolute classpath: `src/test/resources/sql/setup.sql` |
| `"classpath:/sql/setup.sql"` | Spring classpath resource at the same location |
| `"file:/..."` | Filesystem resource; avoid depending on local developer paths |

Prefer `"/sql/seed-xyz.sql"` so tests do not break if Java packages are refactored. When both `scripts` and `statements` are omitted, Spring attempts to resolve a default script from the class or method name and fails if absent. In knowledge lessons and CI, always specify explicit resource paths.

Spring Framework 6.2 supports property placeholders in script paths resolved via the `Environment`. Never pass untrusted input into SQL script paths or arbitrary filenames.

### 8.2 UTF-8 Encoding

SQL scripts containing Vietnamese characters:

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('VI-282', 'Cà phê sữa', TRUE);
~~~

Ensure the file is saved as UTF-8 and configure:

~~~java
@SqlConfig(encoding = "UTF-8")
~~~

The attribute name is `encoding` (not `charset`). If the platform default encoding differs and you omit this setting, tests may misread characters or fail title assertions.

### 8.3 Custom Separators

A script may use `@@` as a delimiter:

~~~sql
-- Script using separator @@ instead of ;
INSERT INTO demo_item(item_id, title, active)
VALUES ('X-282', 'Dữ liệu đặc biệt', TRUE)@@
~~~

Annotation:

~~~java
@Sql(
    scripts = "/sql/seed-custom.sql",
    config = @SqlConfig(separator = "@@", encoding = "UTF-8"))
~~~

Spring TestContext's parser splits statements by `separator`. This is the **script reader's separator**, not a change to the DB's SQL dialect. If a script contains stored procedures with embedded semicolons, use an appropriate migration runner/parser (Flyway/Liquibase) or a carefully designed separator; never assume an arbitrary delimiter parses PostgreSQL dollar-quoted PL/pgSQL correctly.

### 8.4 Comment Rules

Defaults are `--` for single-line comments and `/* ... */` for block comments. When multiple prefixes are needed, use `commentPrefixes={"--","#"}` instead of `commentPrefix`.

Never split SQL manually with `String.split(";")`, because semicolons can appear inside quoted strings or stored routine bodies.

## 9. @SqlMergeMode: Avoiding Accidental Cleanup Disabling

By default, method-level `@Sql` **overrides** class-level `@Sql` declarations for regular execution phases. This can cause subtle bugs:

~~~java
@Sql(
    scripts = "/sql/cleanup-every-test.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
class Example {

    @Test
    @Sql(
        scripts = "/sql/seed-one-case.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
    void caseOne() {
        // Watch out: method @Sql can override class cleanup!
    }
}
~~~

Without merge mode configured, the class cleanup will be skipped for any method declaring its own `@Sql`. To run both sets together, add:

~~~java
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
~~~

at the class or method level. `MERGE` combines class-level and method-level declarations; you can still apply `@SqlMergeMode(OVERRIDE)` to a specific method that genuinely wants full replacement (making sure it provides its own cleanup).

**Exception:** class-level `@Sql` with `BEFORE_TEST_CLASS` or `AFTER_TEST_CLASS` runs once and is not overridden by method-level `@Sql` like per-method phases are.

### 9.1 Global @SqlConfig Differs from @SqlMergeMode

These are **two distinct mechanisms**:

- Global/local `@SqlConfig`: merges **parsing and transaction attributes**.
- `@SqlMergeMode`: merges or overrides **the sets of `@Sql` declarations** between class and method.

You can inherit global UTF-8 encoding **while** class-level cleanup is still overridden by a method-level seed if `@SqlMergeMode(MERGE)` is missing. Tests should verify both.

## 10. Cleanup Strategy: Choose Based on Where Data Commits

| Data Source | Who Holds the Transaction? | Appropriate Cleanup |
| --- | --- | --- |
| `@Sql INFERRED` seed + default rollback repository test | TestContext | Rollback suffices; SQL `DELETE` usually unnecessary |
| `@Sql ISOLATED` seed read by `REQUIRES_NEW` | SQL listener's separate TX | `@Sql AFTER_TEST_METHOD ISOLATED` |
| `RANDOM_PORT` HTTP server auto-committing | Server service | Separate committed cleanup; `AFTER_TEST_METHOD ISOLATED` or DB reset |
| `@Transactional(REQUIRES_NEW)` writing audit rows | Spring service independent TX | Separate committed cleanup |
| `@Commit` or `@Rollback(false)` test | TestContext commit | Post-commit cleanup in a separate TX |
| Non-`@Transactional` test | Application/JDBC autocommit | Independent committed cleanup |
| Data seeded by `schema.sql`/`data.sql` at context startup | Boot initializer | Dedicated DB / fixture reset; never wipe shared schemas casually |
| Test class creating its own schema | Depends on DB DDL transactions | DROP/reset after class when isolated, or fresh container |
| Data in object storage / Redis / Kafka | Outside JDBC TX | Cleanup via dedicated client/service or scoped container/namespace |
| Parallel tests sharing a DB | Multiple concurrent connections | Isolated fixture keys/tenants/schemas; avoid shared `TRUNCATE` |

### 10.1 DELETE by Stable ID Instead of Indiscriminate TRUNCATE

Example:

~~~sql
DELETE FROM order_line WHERE order_id LIKE 'TEST282-%';
DELETE FROM customer_order WHERE order_id LIKE 'TEST282-%';
~~~

This illustrative SQL assumes a foreign key `order_line → customer_order`. Deleting children before parents avoids FK violations. Never run `TRUNCATE customer_order` on a shared test database while another suite is running, and never run cleanup scripts against production.

### 10.2 Idempotency of Cleanup

An ideal cleanup script can run multiple times safely and only deletes the test's own data:

~~~sql
DELETE FROM demo_item WHERE item_id IN ('S-282', 'HTTP-282');
~~~

If no matching rows exist, deleting 0 rows still succeeds. When a test fails mid-execution, cleanup still handles the case where only the seed exists without the HTTP write. Avoid hardcoded table-wide `DELETE` statements.

### 10.3 Does Cleanup Run When a Test Fails?

`@Sql AFTER_TEST_METHOD` is a lifecycle callback and normally executes even when a `@Test` assertion fails, unless a catastrophic error occurs before the listener/lifecycle starts or the process is killed. It is **not a 100% guarantee** against JVM crashes or dropped DB connections. Testcontainers or ephemeral DBs prevent permanent leaks when processes crash.

## 11. Runnable Example: Java 17+ / Spring Boot 3.5.x

This section provides a complete mini-project with **all Java classes and SQL scripts**. It uses:

- Spring Boot 3.5.x and Spring Framework 6.2.
- `spring-boot-starter-jdbc` + `spring-boot-starter-web`.
- In-memory H2 for tests only; no production DB.
- JUnit Jupiter + Spring Boot `starter-test`.
- `@JdbcTest` for query, fixture, and transaction tests.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` for HTTP requests executed on a server thread.
- **Eight `@Test` methods** across five classes.

Each class uses distinct IDs/prefixes so tests do not depend on execution order. `@JdbcTest` uses test-level `@Transactional` by default; the HTTP test class also adds `@Transactional` to highlight the thread difference and uses `ISOLATED` cleanup.

### 11.1 Directory Tree

~~~text
src/
  main/java/example/sqldemo/
    SqlDemoApplication.java
    ItemGateway.java
    ItemService.java
    ItemController.java
  test/java/example/sqldemo/
    InferredSqlTest.java
    IsolatedSqlTest.java
    MergedSqlTest.java
    NoTestTransactionSqlTest.java
    HttpSqlCleanupTest.java
  test/resources/
    application.properties
    schema.sql
    sql/
      seed-rollback.sql
      seed-custom.sql
      seed-isolated.sql
      cleanup-isolated.sql
      seed-merge.sql
      cleanup-merge.sql
      seed-nontx.sql
      cleanup-nontx.sql
      seed-http.sql
      cleanup-http.sql
~~~

Flyway/Liquibase are omitted from the demo to keep focus on `@SqlConfig`. When production uses migrations, use the real migrations to build schemas on an isolated test DB rather than accidentally maintaining divergent test DDL.

### 11.2 Gradle Dependency Snippet

In a project already declaring the Spring Boot plugin/version, dependency management, and Java 17 toolchain:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **`build.gradle` snippet**, not a standalone file with plugins and toolchain. H2 is test-runtime only; a standalone app outside tests requires its own configured datasource and driver.

### 11.3 src/test/resources/application.properties

~~~properties
spring.datasource.generate-unique-name=true
spring.datasource.hikari.maximum-pool-size=8
spring.sql.init.mode=always

logging.level.org.springframework.test.context.jdbc=DEBUG
logging.level.org.springframework.jdbc.datasource.init=DEBUG
~~~

Explanation:

- `generate-unique-name=true` prevents different `ApplicationContext` instances from colliding on the same embedded database name.
- Pool size 8 gives transactional tests, the HTTP server, and `ISOLATED` scripts enough connections when multiple connections are active simultaneously (Hikari settings apply when the datasource uses Hikari).
- `spring.sql.init.mode=always` loads `schema.sql` from test resources when the context initializes.
- `DEBUG` logging aids diagnosing script and SQL execution, though it is not required by assertions; in large CI pipelines you can turn it down to reduce noise.

Never put production credentials here, and never log bind parameters containing secrets in public CI.

### 11.4 src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS demo_item (
    item_id VARCHAR(40) PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL
);
~~~

The schema is created by Boot's SQL initializer when the test context starts. `@Sql` only seeds and cleans up data in the existing table. Avoid using `data.sql` to seed shared records globally, since its lifecycle differs from `@Sql` and easily leaves uncleaned fixtures.

### 11.5 src/main/java/example/sqldemo/SqlDemoApplication.java

~~~java
package example.sqldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SqlDemoApplication.class, args);
    }
}
~~~

### 11.6 ItemGateway.java — Real SQL Adapter

~~~java
package example.sqldemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ItemGateway {

    private final JdbcTemplate jdbc;

    public ItemGateway(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void create(String id, String title) {
        jdbc.update("""
                INSERT INTO demo_item(item_id, title, active)
                VALUES (?, ?, TRUE)
                """, id, title);
    }

    public int count(String id) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_item
                WHERE item_id = ?
                """, Integer.class, id);
        return result.intValue();
    }

    public int countPrefix(String prefix) {
        Integer result = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_item
                WHERE item_id LIKE ?
                """, Integer.class, prefix + "%");
        return result.intValue();
    }

    public String title(String id) {
        return jdbc.queryForObject("""
                SELECT title FROM demo_item WHERE item_id = ?
                """, String.class, id);
    }

    public boolean exists(String id) {
        return count(id) == 1;
    }
}
~~~

`@JdbcTest` does not scan all application `@Repository` beans like a full `@SpringBootTest`, so the slice tests use `@Import(ItemGateway.class)`. `count` uses parameterized SQL and queries real DB state rather than mocking a repository.

### 11.7 ItemService.java — Creating Data in an Application Transaction

~~~java
package example.sqldemo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ItemService {

    private final ItemGateway gateway;

    public ItemService(ItemGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void create(String id, String title) {
        gateway.create(id, title);
    }
}
~~~

When `ItemService.create` is called from the controller on an HTTP server thread, it opens and commits its own transaction because no JUnit test-thread transaction propagates across HTTP. This is key to demonstrating committed cleanup.

### 11.8 ItemController.java — Endpoint for Live HTTP Testing

~~~java
package example.sqldemo;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    private final ItemService service;
    private final ItemGateway gateway;

    public ItemController(
            ItemService service,
            ItemGateway gateway) {
        this.service = service;
        this.gateway = gateway;
    }

    @GetMapping("/api/items/{id}/exists")
    public ResponseEntity<Void> exists(
            @PathVariable("id") String id) {
        return gateway.exists(id)
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    @PostMapping("/api/items/{id}")
    public ResponseEntity<Void> create(
            @PathVariable("id") String id) {
        service.create(id, "created by HTTP");
        return ResponseEntity
                .created(URI.create("/api/items/" + id))
                .build();
    }
}
~~~

Spring Security is not configured in this mini-project. Production code must validate IDs, enforce auth, rate limits, ownership, and map duplicate primary key errors cleanly.

## 12. Complete SQL Scripts

All files live under `src/test/resources/sql/` and are saved in UTF-8.

### 12.1 seed-rollback.sql

~~~sql
-- Data will be rolled back with the test transaction.
INSERT INTO demo_item(item_id, title, active)
VALUES ('R-282-A', 'Học Spring', TRUE);

INSERT INTO demo_item(item_id, title, active)
VALUES ('R-282-B', 'Tài liệu Tiếng Việt', TRUE);
~~~

### 12.2 seed-custom.sql

Script **using `@@` separator**, without `;`:

~~~sql
-- SQL parser configured with @SqlConfig(separator = "@@")
INSERT INTO demo_item(item_id, title, active)
VALUES ('X-282', 'Cà phê dữ liệu', TRUE)@@
~~~

### 12.3 seed-isolated.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('C-282', 'Committed fixture', TRUE);
~~~

### 12.4 cleanup-isolated.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'C-282';
~~~

### 12.5 seed-merge.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('M-282', 'Merged SQL fixture', TRUE);
~~~

### 12.6 cleanup-merge.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'M-282';
~~~

### 12.7 seed-nontx.sql

~~~sql
INSERT INTO demo_item(item_id, title, active)
VALUES ('N-282', 'No test transaction', TRUE);
~~~

### 12.8 cleanup-nontx.sql

~~~sql
DELETE FROM demo_item WHERE item_id = 'N-282';
~~~

### 12.9 seed-http.sql

~~~sql
-- Committed seed so the HTTP server thread can observe it.
INSERT INTO demo_item(item_id, title, active)
VALUES ('S-282', 'Seed visible to server', TRUE);
~~~

### 12.10 cleanup-http.sql

~~~sql
-- Cleans up both the seed and the row committed by the HTTP server service.
DELETE FROM demo_item
WHERE item_id IN ('S-282', 'HTTP-282');
~~~

Design note: each cleanup script touches only the specific IDs owned by that test rather than wiping the entire table. If the test fails before inserting `HTTP-282`, cleanup still succeeds and deletes `S-282`. These IDs are for learning only; production suites should use per-test prefixes/namespaces for parallel execution.

## 13. InferredSqlTest: Seed Joins Test TX and Rolls Back

File `src/test/java/example/sqldemo/InferredSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(ItemGateway.class)
@SqlConfig(encoding = "UTF-8")
@DisplayName("@Sql INFERRED joins test-managed transaction")
class InferredSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    @Sql("/sql/seed-rollback.sql")
    void seededRowsAreVisibleInsideTest() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1, gateway.count("R-282-A"));
        assertEquals(1, gateway.count("R-282-B"));
        assertEquals("Tài liệu Tiếng Việt",
                gateway.title("R-282-B"));
    }

    @Test
    @Sql(
        scripts = "/sql/seed-custom.sql",
        config = @SqlConfig(separator = "@@"))
    void localSeparatorInheritsGlobalUtf8() {
        assertTrue(TestTransaction.isActive());
        assertEquals("Cà phê dữ liệu",
                gateway.title("X-282"));
    }

    @Test
    @Sql(statements = """
            INSERT INTO demo_item(item_id, title, active)
            VALUES ('I-282', 'Inline SQL', TRUE)
            """)
    void inlineSqlStatementAlsoRollsBack() {
        assertEquals(1, gateway.count("I-282"));
    }

    @AfterTransaction
    void allInferredSeedsAreRolledBack() {
        assertEquals(0, gateway.countPrefix("R-282-"));
        assertEquals(0, gateway.count("X-282"));
        assertEquals(0, gateway.count("I-282"));
    }
}
~~~

**Three `@Test` methods.**

Analysis:

- `@JdbcTest` creates a test-managed transaction by default and rolls back after each method.
- Omitting `transactionMode` means `DEFAULT`, which resolves to `INFERRED`; SQL seeds run inside the test transaction.
- Class-level `@SqlConfig(encoding="UTF-8")` is inherited by the method overriding `separator="@@"`.
- `@AfterTransaction` runs **after** rollback, confirming rows from all SQL scripts have disappeared.
- No separate cleanup scripts are needed for `R-282-`/`X-282`/`I-282` because there are no independent commits in this class.

**Do not conclude:** “`@Sql` always rolls back”; in contexts without a test transaction or when using `ISOLATED`, behavior differs.

## 14. IsolatedSqlTest: Both Seed and Cleanup Commit Independently

File `src/test/java/example/sqldemo/IsolatedSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Import(ItemGateway.class)
@Sql(
    scripts = "/sql/seed-isolated.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-isolated.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@DisplayName("@Sql ISOLATED: seed and cleanup data committed")
class IsolatedSqlTest {

    @Autowired ItemGateway gateway;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager txManager;

    @Test
    void committedSeedIsVisibleToTest() {
        assertEquals(1, gateway.count("C-282"));

        // LOCAL-282 created by test; rolled back by default.
        gateway.create("LOCAL-282", "uncommitted local");
        assertEquals(1, gateway.count("LOCAL-282"));
    }

    @Test
    void committedSeedIsVisibleToRequiresNewTransaction() {
        TransactionTemplate inner =
                new TransactionTemplate(txManager);
        inner.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Integer visible = inner.execute(status ->
                jdbc.queryForObject("""
                        SELECT COUNT(*) FROM demo_item
                        WHERE item_id = ?
                        """, Integer.class, "C-282"));

        assertEquals(1, visible.intValue());
    }

    @AfterTransaction
    void isolatedCleanupCommittedAndTestWritesRolledBack() {
        // @Sql AFTER_TEST_METHOD ISOLATED committed DELETE C-282.
        assertEquals(0, gateway.count("C-282"));

        // LOCAL-282 lived in test-managed TX and rolled back.
        assertEquals(0, gateway.count("LOCAL-282"));
    }
}
~~~

**Two `@Test` methods.**

For **each method**, the class-level scripts run:

1. `seed-isolated.sql` inserts `C-282` in a new TX and commits.
2. The main test transaction runs the JUnit test body.
3. `cleanup-isolated.sql` runs before TestContext rollback, in a **new TX**, and commits the DELETE.
4. The test-managed transaction rolls back; `LOCAL-282` (if created) disappears.
5. `@AfterTransaction` verifies both kinds of data are gone.

The second test opens `REQUIRES_NEW` to demonstrate that **another connection/transaction can read the committed seed**. If the seed had been `INFERRED` inside the test TX, the inner TX under `READ_COMMITTED` would not see it. The pool must have enough connections.

**Important:** `ISOLATED` is not a new `DataSource` or schema. It is a new transaction on the same database; concurrent tests can still interfere if they share keys.

## 15. MergedSqlTest: Method-Level Seed Does Not Drop Class Cleanup

File `src/test/java/example/sqldemo/MergedSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.transaction.AfterTransaction;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Import(ItemGateway.class)
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
@Sql(
    scripts = "/sql/cleanup-merge.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class MergedSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    @Sql(
        scripts = "/sql/seed-merge.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED))
    void methodSeedMergesWithClassCleanup() {
        assertEquals(1, gateway.count("M-282"));
    }

    @AfterTransaction
    void classCleanupWasNotOverridden() {
        assertEquals(0, gateway.count("M-282"));
    }
}
~~~

**One `@Test` method.** `@SqlMergeMode(MERGE)` ensures both the class-level cleanup (`AFTER_TEST_METHOD`) and method-level seed (`BEFORE_TEST_METHOD`) are selected. `@AfterTransaction` confirms the cleanup committed.

Without `@SqlMergeMode`, the method-level `@Sql` overrides class-level scripts and **cleanup will not run**, leaving `M-282` behind after test rollback. This shows why `@Sql` declaration merging must be distinguished from global/local `@SqlConfig` attribute merging.

## 16. NoTestTransactionSqlTest: No Rollback to Clean Up Automatically

File `src/test/java/example/sqldemo/NoTestTransactionSqlTest.java`:

~~~java
package example.sqldemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@JdbcTest
@Import(ItemGateway.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@Sql(
    scripts = "/sql/seed-nontx.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-nontx.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class NoTestTransactionSqlTest {

    @Autowired ItemGateway gateway;

    @Test
    void explicitIsolatedScriptsWorkWithoutTestTransaction() {
        assertFalse(TestTransaction.isActive());
        assertEquals(1, gateway.count("N-282"));
    }
}
~~~

**One `@Test` method.** `@JdbcTest` is normally transactional, but `@Transactional(propagation=NOT_SUPPORTED)` on the class **disables the test-managed transaction**. Therefore, no TestContext rollback cleans up data automatically. `seed-nontx.sql` and `cleanup-nontx.sql` run and commit explicitly via `ISOLATED`.

When a transaction manager exists, `INFERRED` without an active transaction also opens and commits a new transaction; using `ISOLATED` here makes the **intent of committed fixture/cleanup** explicit without relying on context assumptions.

## 17. HttpSqlCleanupTest: Real HTTP and Committed Cleanup

This is the most important test when using `@Sql` in integration tests with a real server. `@SpringBootTest(RANDOM_PORT)` starts an embedded HTTP server; the JUnit client sends requests over TCP; controller and service run on a server thread **separate from the test-managed transaction's thread**.

~~~text
JUnit thread                           Server thread
-----------                           -------------
TestContext begins TX A
@Sql BEFORE ISOLATED:
  TX B INSERT S-282; COMMIT
       |
       +-- HTTP GET /api/items/S-282/exists -->
                                      TX server sees S-282
       |
       +-- HTTP POST /api/items/HTTP-282 ----->
                                      ItemService @Transactional
                                      TX C INSERT HTTP-282; COMMIT
       |
Test assertions pass
@Sql AFTER ISOLATED:
  TX D DELETE S-282 and HTTP-282; COMMIT
TestContext ROLLBACK TX A
@AfterTransaction:
  assert both rows absent
~~~

If the cleanup script used `INFERRED` and joined TX A, the `DELETE` would roll back when TX A rolls back, **leaving `HTTP-282` and `S-282` behind**. That is a classic test-isolation bug.

File `src/test/java/example/sqldemo/HttpSqlCleanupTest.java`:

~~~java
package example.sqldemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
@Sql(
    scripts = "/sql/seed-http.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@Sql(
    scripts = "/sql/cleanup-http.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class HttpSqlCleanupTest {

    @LocalServerPort int port;
    @Autowired ItemGateway gateway;

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    void isolatedSeedVisibleToServerAndCleanupAfterRequest()
            throws Exception {

        URI committedSeed = url("/api/items/S-282/exists");

        HttpResponse<Void> lookup = http.send(
                HttpRequest.newBuilder(committedSeed)
                        .timeout(Duration.ofSeconds(20))
                        .GET().build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(204, lookup.statusCode());

        HttpResponse<Void> created = http.send(
                HttpRequest.newBuilder(
                                url("/api/items/HTTP-282"))
                        .timeout(Duration.ofSeconds(20))
                        .POST(HttpRequest.BodyPublishers.noBody())
                        .build(),
                HttpResponse.BodyHandlers.discarding());

        assertEquals(201, created.statusCode());
        assertEquals(1, gateway.count("HTTP-282"));
        assertEquals(1, gateway.count("S-282"));
    }

    @AfterTransaction
    void cleanupCommittedEvenThoughTestTransactionRolledBack() {
        // @Sql AFTER_TEST_METHOD ISOLATED committed DELETE.
        assertEquals(0, gateway.count("S-282"));
        assertEquals(0, gateway.count("HTTP-282"));
    }

    private URI url(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }
}
~~~

**One `@Test` method.** Expected outcomes:

- HTTP GET sees the committed seed → `204`.
- HTTP POST hits the production service → `201`.
- Inside the test method, the JDBC query sees both rows.
- `@Sql AFTER_TEST_METHOD ISOLATED` commits the `DELETE`.
- Subsequent test-transaction rollback **does not undo the cleanup**.
- `@AfterTransaction` verifies both rows are gone.

This example directly catches the bug where **cleanup runs in the right phase but the wrong transaction mode**.

**Note:** do not use MockMvc to demonstrate separate threads or physical transactions. MockMvc normally executes the MVC flow in a mock servlet environment on the same test thread. To test transactions across TCP, use `RANDOM_PORT` and a real HTTP client.

## 18. Summary of the Eight Test Methods

| Class | `@Test` Count | Evidence |
| --- | ---: | --- |
| `InferredSqlTest` | 3 | `INFERRED` seed rollback; inline SQL; local separator inherits global encoding |
| `IsolatedSqlTest` | 2 | `ISOLATED` seed/cleanup commit; `REQUIRES_NEW` observes committed seed |
| `MergedSqlTest` | 1 | `@SqlMergeMode(MERGE)` preserves class-level cleanup |
| `NoTestTransactionSqlTest` | 1 | Test TX disabled, using `ISOLATED` seed/cleanup |
| `HttpSqlCleanupTest` | 1 | HTTP server commit and `AFTER_TEST_METHOD ISOLATED` cleanup |
| **Total** | **8** | Independent of test order; each case has its own data scope |

### Running Gradle

On Linux/macOS:

~~~bash
./gradlew test --tests example.sqldemo.InferredSqlTest --tests example.sqldemo.IsolatedSqlTest --tests example.sqldemo.MergedSqlTest --tests example.sqldemo.NoTestTransactionSqlTest --tests example.sqldemo.HttpSqlCleanupTest
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.sqldemo.InferredSqlTest --tests example.sqldemo.IsolatedSqlTest --tests example.sqldemo.MergedSqlTest --tests example.sqldemo.NoTestTransactionSqlTest --tests example.sqldemo.HttpSqlCleanupTest
~~~

**Expected outcome:** eight JUnit Jupiter methods discovered and **PASS** in a project configured with the Boot 3.5.x plugin, Java 17+, the exact files/classes/SQL in this lesson, and an isolated test database. This is a design expectation, **not captured logs or stdout from an executed Gradle run**. Tests contain no `System.out.println(...)`; aside from the test report, Boot/SQL logs may vary.

If the HTTP test returns 401/403 because a real app has Spring Security enabled, configure test security credentials/CSRF per contract rather than disabling security filters just to pass tests. When production migrations are present, adjust test schema initialization so SQL init does not recreate tables.

## 19. Why Can AFTER_TEST_METHOD + INFERRED Nullify Cleanup?

Suppose a test has `@Transactional`, an `ISOLATED` seed script committed `S-282`, and the HTTP server committed `HTTP-282`. Then the test declares:

~~~java
@Sql(
    scripts = "/sql/cleanup-http.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
~~~

This annotation has `transactionMode=DEFAULT` → effective `INFERRED`. When the `afterTestMethod` listener runs, the **test-managed transaction may still be open**. Consequently, the cleanup `DELETE` executes inside the test transaction.

Timeline:

~~~text
Seed independent:   INSERT S-282     -> COMMIT
Server independent: INSERT HTTP-282  -> COMMIT
Test transaction:   DELETE S-282 and HTTP-282  (UNCOMMITTED)
Test ends:          ROLLBACK test transaction
DB final:           S-282 and HTTP-282 remain!
~~~

**Fix:** declare `config = @SqlConfig(transactionMode = ISOLATED)` on the cleanup. The `DELETE` then commits in its own transaction and is not rolled back with the test.

When a SQL test runs entirely inside the test transaction, an `INFERRED` cleanup before rollback is usually **unnecessary**: rollback automatically removes both the seed and transaction writes. Use isolated cleanup only when **external committed state** must be removed.

## 20. @Sql BEFORE_TEST_CLASS / AFTER_TEST_CLASS: When to Use Them?

Starting in Spring Framework 6.1, you can create data or schemas once for an entire test class:

~~~java
@Sql(
    scripts = "/sql/class-setup.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
@Sql(
    scripts = "/sql/class-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
class BatchDatabaseTests {
    // ...
}
~~~

This is an illustrative snippet. Use it when:

- Setup is expensive (schemas/routines/lookup data) and independent of test methods.
- The test database or schema is isolated exclusively for that class.
- No concurrent tests mutate the same shared state.

Avoid it when:

- Each method needs its own fixture; sharing causes test-order dependencies.
- Cleanup `DROP` statements risk deleting tables used by other test classes.
- The test context/shared datasource is cached and migrations already manage schemas.
- You expect seeds to be visible cleanly per method without checking the commit semantics of class-level scripts.

Class-level phases are not overridden by method-level `@Sql`; per-method scripts still obey `@SqlMergeMode` as usual. When checking commit timing, remember class-level phases do not run inside per-method test-managed transactions; `INFERRED` typically runs and commits if a transaction manager is available.

## 21. @Sql and @Transactional: Traps with REQUIRES_NEW, MANDATORY, and NOT_SUPPORTED

### 21.1 Inner REQUIRES_NEW Does Not See Uncommitted Fixtures

~~~text
Test-managed TX A:
    @Sql BEFORE INFERRED -> INSERT user A (uncommitted)
    service.inner() @Transactional(REQUIRES_NEW):
        TX B SELECT user A -> not visible under READ_COMMITTED
~~~

The fix is `@Sql BEFORE ISOLATED` to commit the fixture or seeding in an independent transaction before the test TX starts. Never “fix” this by letting queries read dirty uncommitted data just to make a test pass.

### 21.2 MANDATORY Can Be Masked by the Test Transaction

A `@Transactional(MANDATORY)` service called from a default-transactional `@JdbcTest` can succeed even if the production caller lacks a transaction. Seeding with `@Sql` does not prove production callers provide a transaction. Add a non-transactional test when verifying `MANDATORY` enforcement.

### 21.3 NOT_SUPPORTED and JDBC Auto-Commit

If a method or test runs without a Spring transaction, JDBC operations may auto-commit. Rollback in another test transaction cannot undo them. Data written under `NOT_SUPPORTED` requires explicit committed cleanup.

### 21.4 NESTED Is Not Equivalent to ISOLATED

`@Transactional(NESTED)` typically uses a savepoint **within the same physical transaction**; an outer rollback cancels nested writes too. `@SqlConfig(transactionMode=ISOLATED)` opens a genuinely **independent** transaction for the script. The two concepts serve different purposes and are not interchangeable.

## 22. Cleaning the Database Does Not Clean “Outside the Database”

`@Sql` only executes SQL against a datasource. It does not remove:

- Files written to the filesystem.
- Objects uploaded to S3/MinIO.
- Redis cache keys.
- Published Kafka messages or sent emails.
- Search index documents (Elasticsearch/OpenSearch).
- External API side effects.

If business logic triggers these side effects, cleanup must extend to appropriate fixtures, test containers, namespaces, and resource-cleanup APIs. Never assume database rollback clears every side effect.

A good practice is using a **test correlation ID** and cleaning up in the exact system that owns the resource; remove only the test's own keys without wiping shared services.

## 23. Common Mistakes

**1. `@Sql AFTER_TEST_METHOD` without `transactionMode`, assuming DELETE definitely commits.**  
When the test TX is still active, `INFERRED` joins it and rolls back. Use `ISOLATED` for committed cleanup.

**2. Seeding with `INFERRED` and wondering why the HTTP server cannot see the fixture.**  
The server uses another connection and cannot see uncommitted rows. Use `ISOLATED` or a committed seed.

**3. Using an `ISOLATED` seed and forgetting cleanup.**  
Test rollback does not remove committed seeds, causing unique constraint violations in the next test.

**4. Putting cleanup at class level and having method-level `@Sql` override it.**  
Use `@SqlMergeMode(MERGE)` or declare both seed and cleanup on the method.

**5. Confusing global/local `@SqlConfig` merging with `@SqlMergeMode`.**  
One merges config options; the other merges `@Sql` declarations.

**6. Using `CONTINUE_ON_ERROR` to ignore failing fixture or cleanup SQL.**  
Tests can false-pass on incomplete datasets. Stick to default `FAIL_ON_ERROR`.

**7. Using `IGNORE_FAILED_DROPS` for every SQL error.**  
This mode is not meant to silence general failures. Prefer idempotent `DELETE` or `DROP IF EXISTS`.

**8. Omitting encoding for scripts with Vietnamese text.**  
Can produce mojibake in CI. Save as UTF-8 and specify `encoding="UTF-8"` when needed.

**9. Assuming `;` always splits stored procedure bodies correctly.**  
The simple script parser may not handle vendor-specific DDL. Use an appropriate migration runner.

**10. Using relative `"data.sql"`, refactoring the test package, and losing the script.**  
Use absolute classpath paths like `/sql/seed-data.sql`.

**11. Using `@Sql` with default script detection without creating the expected filename.**  
Spring fails to locate the script. Declare explicit paths.

**12. Using `@JdbcTest` with a custom `@Repository` without `@Import`.**  
Slices do not scan every production bean; import the gateway under test.

**13. Assuming `@Sql` hits the same `DataSource` as the repository when multiple DBs exist.**  
Specify `dataSource` and `transactionManager` explicitly and verify with read-backs.

**14. Truncating entire tables on a shared test DB.**  
Breaks concurrent tests or foreign keys. Use dedicated IDs, tenants, or schemas.

**15. Using `@DirtiesContext` and expecting external databases to be wiped.**  
Resetting the context cache does not delete committed rows from an external DB.

**16. Checking data on the test thread and assuming cleanup committed.**  
Verify after TestContext rollback using `@AfterTransaction` or a separate connection/probe.

**17. Writing `@AfterEach` to verify post-rollback state.**  
`@AfterEach` runs before test rollback; use `@AfterTransaction`.

**18. Running tests in parallel against the same IDs or schema.**  
Risks races, duplicates, and locks. Use unique fixture keys or isolated DBs.

**19. Letting `schema.sql`, `data.sql`, and Flyway run together without coordination.**  
Can collide on schemas, break migration order, or insert duplicate rows.

**20. Seeing H2 pass and assuming PostgreSQL DDL/locks/SQLSTATE behave identically.**  
Use Testcontainers with the matching engine for dialect-dependent behavior.

**21. Leaving leaked datasets when the JVM is killed before cleanup runs.**  
AFTER hooks are not guaranteed if the process crashes. Use ephemeral test DBs/containers.

**22. Having no logging when an `@Sql` script fails.**  
Enable `DEBUG` for `org.springframework.test.context.jdbc` and `org.springframework.jdbc.datasource.init` in test environments to inspect resources and statements.

**23. Cleanup timing out on locks held by the active test transaction.**  
`ISOLATED` opens a new transaction and cannot easily delete rows locked by the outer TX. Design fixture IDs and transaction boundaries carefully.

**24. Sending scripts containing secrets or production data to public test runners.**  
Use synthetic data, isolated datasource configurations, and never log passwords.

## 24. Process for Designing Reliable Seed and Cleanup

1. **Identify the target under test:** repository query, business transaction, HTTP endpoint, DB migration, or async job.
2. **Choose the database engine:** H2 for simple examples, Testcontainers PostgreSQL/MySQL when real semantics matter.
3. **Decide what creates the schema:** Boot SQL init, Hibernate DDL, or Flyway/Liquibase—avoid overlap.
4. **Pick fixture scope:** per method, per class, per container, or per suite; avoid shared mutable data.
5. **Choose seed transaction mode:** `INFERRED` when only the test thread inside a rollback TX needs it; `ISOLATED` when external callers need committed data.
6. **Choose cleanup:** automatic rollback when sufficient; `AFTER_TEST_METHOD` + `ISOLATED` for committed state.
7. **Write idempotent, targeted scripts:** `DELETE` test-owned IDs in FK order, never table-wide truncation.
8. **If class-level and method-level `@Sql` coexist,** decide explicitly between `@SqlMergeMode` `MERGE` and `OVERRIDE`.
9. **Configure parser options:** `encoding="UTF-8"`, accurate `separator`, accurate comment syntax, avoiding unsupported SQL dialects.
10. **Pick `ErrorMode`:** `FAIL_ON_ERROR` unless there is a specific reason and tests handle partial state.
11. **Enable TestContext transaction awareness:** track `@Transactional` across test, service, HTTP server threads, and `REQUIRES_NEW`.
12. **Verify data inside tests:** assert rows, values, counts, and real queries—not just that the script ran without error.
13. **Verify post-cleanup state:** `@AfterTransaction` or an appropriate probe, not just `@AfterEach`.
14. **Guarantee cleanup even on test failure:** lifecycle hooks, `finally`/isolated scripts, or ephemeral databases.
15. **Keep CI independent:** distinct IDs/schemas, order-independent tests, and no access to production credentials.

### Final Checklist

- [ ] Script paths are explicit, reside in test resources, and are readable in CI.
- [ ] Boot `schema.sql`/`data.sql` initializer is clearly distinguished from TestContext `@Sql`.
- [ ] Where `BEFORE`/`AFTER_TEST_METHOD` occur relative to test-transaction rollback is understood.
- [ ] `DEFAULT` resolves to `INFERRED` unless overridden globally.
- [ ] Transactional test seeds use `INFERRED` when no external committed reads are needed.
- [ ] Seeds for HTTP servers or `REQUIRES_NEW` are committed via `ISOLATED` or separate setup.
- [ ] Committed rows are removed by a cleanup that genuinely commits.
- [ ] `AFTER_TEST_METHOD` cleanup never accidentally joins the test TX and rolls back.
- [ ] Class-level cleanup is not unintentionally overridden by method-level `@Sql`.
- [ ] `@SqlConfig` global/local inheritance matches intended encoding/separator/transactionMode.
- [ ] `ErrorMode` does not hide missing data or SQL/permission failures.
- [ ] Cleanup `DELETE` targets only test IDs and succeeds even when rows do not exist.
- [ ] Table-wide `TRUNCATE` is never used on shared DBs.
- [ ] Tests verify post-rollback/cleanup state at the appropriate lifecycle point.
- [ ] Parallel runs never share fixture IDs or schemas without isolation.
- [ ] Production-like DB tests exist when migrations, triggers, transactions, or vendor SQL matter.
- [ ] SQL scripts never point at a production database.

**Remember:** `@Sql` defines **what runs and when**, while `@SqlConfig(transactionMode=...)` decides **which transaction it joins and whether it commits independently**. For simple transactional tests, `INFERRED` with default rollback is convenient. For data committed by an HTTP server, `REQUIRES_NEW`, or an isolated seed, **`AFTER_TEST_METHOD` + `ISOLATED`** cleanup is far more transparent. Combining proper script scoping, `MERGE` when needed, strict error handling, and post-cleanup verification produces repeatable tests that never leak data.

### Official References

- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): `@Sql`, script paths, execution phases, transactions, `MERGE`/`OVERRIDE`, `TestExecutionListener`.
- [Spring Framework 6.2 — @SqlConfig API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html): `encoding`, `separator`, `errorMode`, `dataSource`, `transactionManager`.
- [Spring Framework 6.2 — TransactionMode API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.TransactionMode.html): `INFERRED` inference rules and `ISOLATED`.
- [Spring Framework 6.2 — SqlScriptsTestExecutionListener](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/test/context/jdbc/SqlScriptsTestExecutionListener.html): listener order 5000 and before/after test phases.
- [Spring Framework 6.2 — @SqlMergeMode](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-sqlmergemode.html): method-level `OVERRIDE` vs. `MERGE`.
- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): rollback, `@AfterTransaction`, test vs. server threads.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest`/`@DataJpaTest`, `RANDOM_PORT`.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`/`data.sql`, initialization mode, Flyway/Liquibase cautions.
