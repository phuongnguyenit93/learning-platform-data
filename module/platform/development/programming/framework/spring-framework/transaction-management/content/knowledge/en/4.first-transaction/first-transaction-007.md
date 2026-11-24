# Verifying Data with an Independent Connection After Completion

## 1. Lesson Objectives

In Spring Framework, a method annotated with `@Transactional` can read data it just wrote, even while the transaction **has not committed yet**. Therefore, calling `repository.findById(...)` or `JdbcTemplate.queryForObject(...)` immediately inside that same method does not prove the data was committed and is visible from another connection.

This lesson guides you on how to **verify database state using an independent JDBC connection after the transaction boundary has actually completed**. After this lesson, you can:

- Distinguish data sitting inside an active transaction from committed data.
- Pinpoint the exact moment Spring finishes commit/rollback when calling `@Transactional` through a proxy.
- Re-read data using a fresh JDBC connection not participating in the writer's transaction.
- Verify two outcomes: on successful commit, the new data is visible; on rollback, the new data is absent.
- Write integration tests that avoid confusing application transactions with transactions managed by the test framework.
- Identify causes of misleading verification: querying in the same transaction, self-invocation, unfinished outer transaction, isolation levels, replica lag, wrong schema, or caching.

**Scope:** Examples focus on synchronous JDBC transactions, a single database, Spring Boot/Spring JDBC, and H2. The commit-boundary principles are also useful with JPA, though with JPA you must additionally pay attention to `flush` and the persistence context.

## 2. Why Is Re-Reading Immediately Inside the Method Not Enough?

Suppose a method has its transaction managed by Spring:

```java
@Transactional
public void save(long id) {
    jdbcTemplate.update(
        "INSERT INTO ledger_entry(id, description) VALUES (?, ?)",
        id, "new-value");

    // This reads inside the same transaction.
    String value = jdbcTemplate.queryForObject(
        "SELECT description FROM ledger_entry WHERE id = ?",
        String.class, id);
}
```

This is an **illustrative snippet**, not a standalone program. `JdbcTemplate` normally uses the JDBC connection bound to the current thread's transaction. That connection can **read your own writes**: it sees its own changes before `COMMIT`. Thus, the `"new-value"` result here only indicates the INSERT statement took effect inside the current transaction; it does not prove another connection sees that value.

Under standard `READ_COMMITTED` isolation:

| Moment | Writing Connection A | Independent Connection B |
| --- | --- | --- |
| A begins transaction | No new data | No new data |
| A INSERTs yet has not committed | A sees the new row | B does not see the new row yet |
| A commits successfully | Row is confirmed | B opens a new query and sees the row |
| If A rolls back instead of committing | A's changes are undone | B does not see the row written by A |

An independent read transaction opened **before** commit time may continue seeing an older snapshot under isolation levels such as `REPEATABLE_READ` or `SERIALIZABLE`. To verify cleanly, open a **new reading connection/transaction after commit/rollback has finished**. Query the primary data source—same database, schema, and tenant—rather than a read replica that may lag.

## 3. When Is "After Completion" in Spring?

In standard declarative transaction management, calls must pass through the Spring AOP proxy:

```text
Caller
  |
  | calls proxy bean
  v
TransactionInterceptor
  |  opens/joins transaction
  v
@Transactional service method
  |  INSERT / UPDATE / DELETE
  |  return or throw
  v
TransactionInterceptor
  |  COMMIT or ROLLBACK when owning physical transaction
  v
Caller receives result or exception
  |
  v
Open an independent connection -> SELECT to verify
```

When there is **no outer transaction** and the call goes properly through the Spring proxy, the transaction manager performs commit/rollback inside the interceptor before returning control to the caller. In that case, you can check right after the call finishes:

```java
service.save(42L);        // Call through Spring proxy; commit is complete if it returns successfully.
verifyUsingNewConnection(); // Independent query outside the completed transaction.
```

This only illustrates how to structure the call flow, not standalone code.

Important exceptions:

1. If the service joins an outer transaction via `Propagation.REQUIRED`, **the inner method returning does not mean the outer transaction committed**. Only verify after the outermost boundary finishes.
2. Calling `this.save(...)` inside the same bean can bypass the AOP proxy in proxy mode; `@Transactional` on the target method is then not applied as desired.
3. A business method may finish running yet **commit fails** (for instance, constraint errors at flush/commit, timeout, or transaction marked rollback-only). Treat it as committed only when the proxied call returns normally and the physical transaction actually ended; if an exception occurs, investigate the outcome before concluding.
4. For reactive transactions, `Publisher` completion follows different mechanics; do not apply synchronous JDBC method timing rules to reactive pipelines.

## 4. Designing a Trustworthy Verification

Workflow for a simple JDBC transaction:

1. **Prepare a known initial state**, e.g., an ID that does not yet exist.
2. **Call the `@Transactional` service via the Spring bean**; inside the service, write a row using `JdbcTemplate`.
3. If you want to observe the difference **before commit**, while still inside the service, query using the transaction-bound connection and using a completely separate JDBC connection; under `READ_COMMITTED`, the current connection sees the change while the other does not.
4. Let the service finish; the proxy commits on success or rolls back if an exception matches rollback rules.
5. **Open a fresh independent connection after step 4 completes**, execute `SELECT` by specific key/ID; compare *both row existence and column values* against expected results.
6. Close `ResultSet`, `PreparedStatement`, and `Connection` via `try-with-resources`.
7. For failure cases, catch the exception **in the caller after passing through the proxy**, then read via an independent connection to confirm data was not committed.

In production environments, you typically use the application's connection pool and query after the transaction has ended. The example below uses `DriverManager.getConnection(...)` directly to **prove unambiguously** that the verifying connection is completely independent of the Spring-managed transaction-bound connection. Creating a connection directly like this makes sense for practice; in real systems, consider pooling, SSL configuration, credentials, multi-tenancy, and routing.

## 5. Runnable Spring Boot Example: Observing Commit Visibility and Rollback Absence

The sample application uses Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC, and in-memory H2. It runs two scenarios:

- `save(1)` writes id=1 and returns normally: the service sees uncommitted data; the independent connection does not see it before commit, and sees the exact value after commit.
- `saveAndFail(2)` writes id=2 then throws `IllegalStateException`: the service sees its own change, the independent connection does not see it; after rollback it still does not see it.

Structure:

```text
transaction-check/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TransactionCheckApplication.java
    │   │   ├── WriteService.java
    │   │   └── IndependentReader.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── TransactionVisibilityTest.java
```

### 5.1. Maven dependencies

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>transaction-check</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

### 5.2. Configuring the Same Database for Both Connections

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:transaction_check;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

Use a **named in-memory H2** `transaction_check` so connections within the same JVM point to the same database. `DB_CLOSE_DELAY=-1` keeps H2 from destroying the database when the last connection closes during the demo. Do not use an unnamed in-memory URL (`jdbc:h2:mem:`), because new connections may hit different databases.

### 5.3. Independent Reading Connection

**`src/main/java/demo/IndependentReader.java`**

```java
package demo;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class IndependentReader {
    private final String jdbcUrl;
    private final String username;
    private final String password;

    public IndependentReader(
            @Value("${spring.datasource.url}") String jdbcUrl,
            @Value("${spring.datasource.username}") String username,
            @Value("${spring.datasource.password:}") String password) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.password = password;
    }

    public Optional<String> findDescription(long id) {
        String sql = "SELECT description FROM ledger_entry WHERE id = ?";

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, username, password);
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, id);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(rows.getString(1));
            }

        } catch (SQLException ex) {
            throw new IllegalStateException(
                    "Unable to verify data", ex);
        }
    }
}
```

Key points:

- `DriverManager.getConnection(...)` creates a fresh JDBC connection that Spring does not bind to `WriteService`'s transaction. It does not use `DataSourceUtils.getConnection(...)` or `JdbcTemplate`, which would reuse the thread-bound connection.
- URL/username/password come from the same configuration so the reading connection points to **the same database**, yet has its **own transaction scope**. H2 here uses `READ_COMMITTED` by default, and a new connection typically has `autoCommit=true`; each `SELECT` sees the committed state at query time.
- `PreparedStatement` uses the `?` parameter, avoiding string concatenation of IDs into SQL. `Optional.empty()` means no row exists; `Optional[value-1]` means value `value-1` was read.
- After each read, `try-with-resources` closes resources. This reading connection neither commits nor rolls back on behalf of the writing transaction.

### 5.4. Writing Service via Spring-Managed Transaction

**`src/main/java/demo/WriteService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;
    private final IndependentReader independentReader;

    public WriteService(
            JdbcTemplate jdbc,
            IndependentReader independentReader) {
        this.jdbc = jdbc;
        this.independentReader = independentReader;
    }

    @Transactional
    public void save(long id) {
        insert(id);

        System.out.println(
                "Same transaction, id=" + id + ": " + readInCurrentTransaction(id));
        System.out.println(
                "Independent connection before commit, id=" + id + ": "
                        + independentReader.findDescription(id));
    }

    @Transactional
    public void saveAndFail(long id) {
        insert(id);

        System.out.println(
                "Same transaction, id=" + id + ": " + readInCurrentTransaction(id));
        System.out.println(
                "Independent connection before rollback, id=" + id + ": "
                        + independentReader.findDescription(id));

        throw new IllegalStateException("intentional rollback");
    }

    private void insert(long id) {
        jdbc.update(
                "INSERT INTO ledger_entry(id, description) VALUES (?, ?)",
                id, "value-" + id);
    }

    private String readInCurrentTransaction(long id) {
        return jdbc.queryForObject(
                "SELECT description FROM ledger_entry WHERE id = ?",
                String.class, id);
    }
}
```

`@Transactional` defaults to `Propagation.REQUIRED`. If the caller has no outer transaction, Spring opens a transaction upon entering `save(...)` and commits when the method returns through the interceptor. `JdbcTemplate` inside the service participates in the active transaction's connection.

In `saveAndFail(...)`, `IllegalStateException` is a `RuntimeException`; default rollback rules handle it when the exception escapes through the proxy. Note that **the `throw` statement occurs after both SELECT statements**, so the two lines printed before rollback still describe the *unfinished* state.

### 5.5. Application Creating the Table and Verifying After Calls Finish

**`src/main/java/demo/TransactionCheckApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TransactionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionCheckApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcTemplate jdbc,
            WriteService writeService,
            IndependentReader independentReader) {

        return args -> {
            jdbc.execute("""
                    CREATE TABLE ledger_entry (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            // No outer transaction; call service via Spring bean proxy.
            writeService.save(1L);
            System.out.println(
                    "Independent connection after commit, id=1: "
                            + independentReader.findDescription(1L));

            try {
                writeService.saveAndFail(2L);
            } catch (IllegalStateException ex) {
                System.out.println("Caught error: " + ex.getMessage());
            }

            System.out.println(
                    "Independent connection after rollback, id=2: "
                            + independentReader.findDescription(2L));
        };
    }
}
```

Here `CommandLineRunner` does not carry `@Transactional`, so it does not create an outer transaction wrapping both calls. `writeService` injected by Spring is a bean going through the transaction proxy. When `writeService.save(1L)` returns control to the runner without throwing an error, the interceptor has already processed the commit. Similarly, when the exception from `saveAndFail(2L)` reaches the `catch` block, the interceptor has already processed the rollback.

### 5.6. Running and Checking the Output

Requirements: JDK 17+ and Maven 3.6.3+. In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Lines **printed by the program**, excluding Spring startup logs:

```text
Same transaction, id=1: value-1
Independent connection before commit, id=1: Optional.empty
Independent connection after commit, id=1: Optional[value-1]
Same transaction, id=2: value-2
Independent connection before rollback, id=2: Optional.empty
Caught error: intentional rollback
Independent connection after rollback, id=2: Optional.empty
```

**Explanation of each milestone:**

| Milestone | Writing transaction | Independent connection | Meaning |
| --- | --- | --- | --- |
| `save(1)` after INSERT | Reads `value-1` | Does not see id=1 yet | Same connection sees uncommitted data |
| `save(1)` returns via proxy | Commit succeeds | Reads `value-1` | Data can now be read by new connections |
| `saveAndFail(2)` after INSERT | Reads `value-2` | Does not see id=2 yet | Data still exists only inside writing transaction |
| Exception escapes proxy | Transaction rolls back | Does not see id=2 | Uncommitted change was undone |

This is a **transaction-independent verification** because each query of `IndependentReader` opens a new JDBC connection and sends SQL directly to the database, without relying on service return values or an ORM cache.

## 6. Automating Verification with an Integration Test

Add the following file to verify commit/rollback without visually comparing console output.

**`src/test/java/demo/TransactionVisibilityTest.java`**

```java
package demo;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionVisibilityTest {
    @Autowired
    private WriteService writeService;

    @Autowired
    private IndependentReader independentReader;

    @Test
    void committedDataIsVisibleThroughFreshConnection() {
        writeService.save(101L);

        assertEquals(
                Optional.of("value-101"),
                independentReader.findDescription(101L));
    }

    @Test
    void rolledBackDataIsNotVisibleThroughFreshConnection() {
        assertThrows(
                IllegalStateException.class,
                () -> writeService.saveAndFail(102L));

        assertEquals(
                Optional.empty(),
                independentReader.findDescription(102L));
    }
}
```

Run:

```bash
mvn test
```

The two tests above use dedicated IDs (101 and 102), avoiding IDs 1 and 2 created by the demo runner when the application context starts. Neither test has **`@Transactional` on the method/class**, so the service owns its own transaction boundary; each read checks state after the service call has finished. Expectation: both tests pass.

If you also want to verify saving **the exact content** rather than merely row existence, compare `Optional.of("value-101")` directly as shown; when checking other columns, return a DTO/record containing multiple values and assert all important fields.

### Why Can `@Transactional` on a Test Falsify Verification?

The following snippet is an **illustrative anti-pattern**:

```java
@SpringBootTest
@Transactional
class TransactionalTestExample {
    @Autowired WriteService writeService;
    @Autowired IndependentReader independentReader;

    @Test
    void misleadingCheck() {
        writeService.save(201L);

        // A new connection may not yet see id=201 because the test transaction
        // is still active and has not committed.
        assertEquals(
                Optional.of("value-201"),
                independentReader.findDescription(201L));
    }
}
```

The code above omits imports and is not a recommended test example. By default, Spring TestContext opens a **test-managed transaction** when a test is marked `@Transactional`, and rolls back that transaction after the test. The `Propagation.REQUIRED` service call joins the active test transaction. Therefore, returning from the service **does not commit**; the independent connection will not see id=201 while the test transaction remains open under `READ_COMMITTED`.

There are three right ways to verify:

1. **Prefer** tests without `@Transactional` when observing post-commit state of a service; this is the approach used in `TransactionVisibilityTest`.
2. If a test must run inside a test-managed transaction, you can use `TestTransaction.flagForCommit()` followed by `TestTransaction.end()` to finish and commit the test's transaction, **and only afterward** open an independent connection to verify. This writes real data to the test database and requires appropriate cleanup/isolation.
3. With Spring TestContext, `@AfterTransaction` can inspect state after the test transaction ends; if the test is configured for default rollback, the right result must reflect **rollback**, not commit. `@Commit`/`@Rollback(false)` is an intentional choice when committing the test transaction is desired.

Example **additional method snippet inside a test class supported by Spring TestContext**, run only against a test database:

```java
@Test
@Transactional
void verifyAfterTestManagedCommit() {
    writeService.save(301L);

    TestTransaction.flagForCommit();
    TestTransaction.end();

    assertEquals(
            Optional.of("value-301"),
            independentReader.findDescription(301L));
}
```

Requires importing `org.springframework.transaction.annotation.Transactional` and `org.springframework.test.context.transaction.TestTransaction` alongside the test components above. `TestTransaction.end()` ends the test-managed transaction; do not use this casually in tests that rely on automatic cleanup after every run.

## 7. When Is a Verification Considered Valid?

A valid verification must simultaneously satisfy these conditions:

| Factor | Check to Perform |
| --- | --- |
| Write boundary | Caller has exited the **outermost physical transaction**, with no outer/test transaction still awaiting commit |
| Read boundary | Fresh reading connection, not sharing the writer's transaction/persistence context |
| Data source | Same primary database, right schema/catalog/tenant; not accidentally reading an H2 memory DB or lagging replica |
| Timing | SELECT starts **after** commit or rollback is confirmed; not querying inside an old snapshot |
| Isolation | Understand `READ_COMMITTED`/`REPEATABLE_READ`; avoid false conclusions from dirty reads or stale snapshots |
| Comparison data | Use unique ID/correlation key, check fields and expected values rather than merely checking that the method did not throw |
| Failures | When transaction fails, expect the new record not to exist; check exception and data together |
| Resources | Close connections/statements/result sets to avoid connection leaks or holding long-lived read transactions |

**You do not need to open a different database.** An "independent" connection means an independent transaction and JDBC connection reading **the same target data**. Using a different database does not prove the original transaction committed.

In the H2 example, each time `findDescription` runs, `DriverManager` opens a new connection and closes it immediately. In production, you can obtain a connection from the `DataSource`/pool **after the writing transaction has actually ended**; what matters is that the reading connection is not bound to the active writing transaction. `DataSourceUtils.getConnection` on the same thread while a transaction is running can return that very bound connection, so do not use it as proof of an independent connection before commit.

## 8. Situations That Easily Produce Misleading Results

### 8.1. Inner Service Returned, Outer Still Has a Transaction

```text
@Transactional outer()
  ├── writeService.save(42)   // REQUIRED joins outer
  ├── save() returns            // NO physical commit yet
  ├── independent SELECT        // usually does not see changes yet
  └── outer() returns           // outermost proxy finally commits
```

Fix: perform verification after the **outermost proxy invocation** finishes; or use the right phase callback API when a hook is needed. Do not confuse the moment a Java method returns with the moment the physical transaction ends.

### 8.2. Checking with the Same `JdbcTemplate` Inside the Service

That query can reuse the transaction-bound connection, seeing uncommitted writes. It tests **logic running inside the transaction**, not proof that data committed. Move the verification read to the caller after the boundary, using an independent connection.

### 8.3. Independent Connection Opened Early and Holding an Old Snapshot

Under `REPEATABLE_READ`, a long-running read transaction can keep seeing a pre-commit snapshot even after the writer commits. End the old read transaction and start a fresh reading transaction/connection; understand the isolation and MVCC behavior of the database in use.

### 8.4. Reading from a Read Replica

A replica may apply changes later than the primary. A "not found yet" result after commit on a replica does not mean the primary rolled back. If the goal is immediate commit verification, verify against the primary or use the system's read-after-write consistency mechanism.

### 8.5. Reading from JPA Persistence Context/Cache

`EntityManager.find()` can return an entity already in the first-level cache without issuing new SQL; `flush()` only synchronizes SQL to the database within the transaction, which **is not equivalent to commit**. To verify committed state, read through an independent transaction and persistence context after completion; when needed, verify actual SQL sent to the database.

### 8.6. Database Has Triggers, Defaults, or Generated Values

Persisted values may differ from the Java object prior to commit (for example, DB defaults, triggers, or generated columns). Verification must SELECT **actual values** and inspect critical columns rather than assuming the object returned by save reflects the entire final state.

### 8.7. Commit Reports an Error or Uncertain State

Never conclude "rolled back" in every case merely because the caller received an exception; a network error at commit time can leave the application **unsure** whether the database committed or not. For critical systems, you need a business ID/idempotency key, verification queries against the primary source, and a workflow for handling uncertain outcomes. In the demo, the exception is intentionally thrown *before commit* and Spring rolls back by rule, so the outcome is deterministic.

### 8.8. Verifying Too Early in a Callback

`TransactionSynchronization.afterCompletion(...)` or `@TransactionalEventListener(phase = AFTER_COMMIT)` can be used for post-transaction work, yet some resources may remain bound until Spring finishes cleanup. Do not reuse an old connection/persistence context inside a callback to claim independent verification. When needing to write a new transaction from a callback, you typically must open a `REQUIRES_NEW` boundary; never assume DB operations in a callback will commit separately by default.

### 8.9. Verifying by Total Row Count

`SELECT COUNT(*) FROM ledger_entry` can rise or fall due to other transactions. Use an ID/correlation key specific to the operation under test, add tenant/schema filters, and compare every critical field. If testing under concurrent load, design to avoid races with other transactions modifying the same rows.

## 9. Debugging Workflow When Results Do Not Match Expectations

If the independent connection **already sees the row before commit**, check:

- Is `@Transactional` actually applied through a Spring proxy? Is there self-invocation or a missing transaction manager in configuration?
- Does the INSERT's JDBC connection have `autoCommit` unintentionally enabled?
- Is the "independent" connection actually distinct from the bound connection, or did `JdbcTemplate`/`DataSourceUtils` join the same transaction?
- Is isolation set to `READ_UNCOMMITTED`/dirty read? Does the driver/database have special behavior?
- Did the record exist from a previous run? Did you use a unique ID and reset data properly?

If **after commit the row is still not visible**, check:

- Did only an inner service finish while an outer transaction/test-managed transaction has not committed yet?
- Did the INSERT actually execute, or was there a commit/constraint/rollback-only error after the method ended?
- Do the reader's URL, schema, username, tenant, or datasource routing point to the exact primary DB?
- Is the reader holding a pre-commit snapshot, or reading from a replica/cache?
- Did a concurrent transaction delete or overwrite the row?

If **after rollback the row is still visible**, check:

- Did that ID already exist before the transaction, or did another transaction commit it?
- Did the exception escape through the interceptor, or was it caught/swallowed inside the method?
- Was a checked exception used without configuring `rollbackFor`? By default `@Transactional` rolls back on `RuntimeException` and `Error`.
- Did part of the work run inside `REQUIRES_NEW` or an independently auto-committing connection? Independently committed changes are not undone by an outer rollback.

You can enable logging in a practice environment:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Transaction logs help observe start, participation, commit, and rollback. However, logs do not replace SQL evidence executed **through an independent connection after completion**.

## 10. Practice Exercises

**Exercise 1 — Commit:** Change `writeService.save(1L)` to `save(10L)` and update the post-commit check to id=10. Predict the three outputs for same transaction, independent before commit, and independent after commit.

**Answer:** `value-10`, `Optional.empty`, and `Optional[value-10]` respectively, under the same H2 `READ_COMMITTED` conditions.

**Exercise 2 — Rollback:** Remove `throw new IllegalStateException(...)` in `saveAndFail` and keep the caller unchanged. Predict the query output after the call returns.

**Answer:** the method finishes normally and the transaction commits; thus, the independent connection after the call reads `Optional[value-2]`. The `catch` block does not run.

**Exercise 3 — Test transaction:** Add `@Transactional` to the `committedDataIsVisibleThroughFreshConnection` test. Why might the assertion no longer pass?

**Answer:** the `REQUIRED` service joins the test-held transaction; after the service returns, the test transaction has not committed yet. The independent connection does not see the change yet. TestContext rolls back the test transaction by default at the end of the test.

**Exercise 4 — Snapshot:** Reading connection B opens a `REPEATABLE_READ` transaction and runs SELECT before A commits. After A commits, is B guaranteed to see the data immediately in that same reading transaction?

**Answer:** no. B may continue reading the old snapshot; you must end the reading transaction and start a fresh read per actual database/isolation behavior.

**Exercise 5 — Real-world scenario:** After the service commits, you verify against a read replica and do not see the data yet. Can you conclude Spring rolled back?

**Answer:** no. A replica can lag in replication; check the primary with the same ID, schema, and tenant before concluding on commit results.

## 11. Points to Remember

- **Being readable inside the transaction does not prove commit.** The writing connection can see its own uncommitted changes.
- **Verification timing must be after the outermost physical transaction finishes.** An inner `REQUIRED` returning is not enough if an outer transaction is still active.
- **Use an independent reading connection/transaction started after commit or rollback**, targeting the same primary database and right data scope.
- **Commit:** the record is verified with expected values. **Rollback:** none of the new changes created by the failed transaction exist.
- **`@Transactional` tests roll back by default** and can distort post-service state verification; tests should define clear completion boundaries.
- **Verification should rely on IDs and actual values, not just a successful method call or a `SELECT` on the same connection.**

## 12. References

- Spring Framework — How declarative transactions work via proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `@Transactional` settings, propagation, and rollback defaults: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC connections and transaction-aware resource access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — TestContext transactions, default rollback, and `TestTransaction`: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- H2 Database — Reference documentation (JDBC connections, isolation, in-memory DB): https://h2database.com/html/features.html