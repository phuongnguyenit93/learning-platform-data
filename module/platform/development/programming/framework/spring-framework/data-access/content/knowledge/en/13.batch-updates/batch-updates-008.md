# Batching Does Not Automatically Guarantee Atomicity Without a Proper Transaction

In Spring Framework Data Access, `batch` is a technique for grouping multiple SQL operations to reduce statement dispatch and processing overhead. **Batching is not the same as a transaction.** When an operation fails mid-way, whether previously executed operations are kept or rolled back together depends on **transaction boundaries, commit/rollback mechanisms, and database transactional capabilities**.

After this lesson, you will be able to explain the difference between batching and atomicity, recognize partial-update risks, place transaction boundaries properly when using `JdbcTemplate.batchUpdate(...)`, and verify rollback with a deliberately triggered failure case.

## 1. Distinguishing Batching, Transactions, and Atomicity

| Concept | Role | What Must Not Be Inferred |
| --- | --- | --- |
| JDBC batch | Groups multiple executions of the same `PreparedStatement` or command batch to reduce round trips; `JdbcTemplate.batchUpdate` supports this mechanism. | Grouping commands **does not automatically create** a transaction wrapping all commands. |
| Transaction | A unit of work managed via `BEGIN`/transaction start, `COMMIT`, or `ROLLBACK`. | Only operations that actually participate in the **same transaction** are handled together at that boundary. |
| Atomicity | For operations guaranteed at the transaction level by the DB: either all changes in the transaction commit, or all roll back. | Atomicity does not automatically extend to other connections, external non-DB resources, or already committed transactions. |
| Isolation | Defines how concurrent transactions observe and affect each other. | Isolation does not replace atomicity and does not fix a missing transaction. |

A single API call is not always equivalent to a single SQL command. For example, a `batchUpdate` containing 500 `INSERT`s may be sent by the driver in various ways, split into smaller groups, or executed sequentially if the driver does not support batching. Never treat a method name or API call count as proof that all changes will succeed or fail together.

### `autoCommit` Is a Critical Link

On a standard JDBC `Connection`, `autoCommit=true` is the initial default. Without a Spring-managed transaction and with the connection operating in auto-commit mode, a successful statement may already be committed before another statement in the batch fails. How the driver/database handles the rest after an error varies; **do not assume the batch will stop right at the failing element or undo earlier elements**.

When `autoCommit=false`, operations on the **same connection** can belong to the same transaction. However, merely disabling auto-commit is not enough: the program must `commit()` when the entire unit of work is valid, and `rollback()` when an error occurs. In Spring, the transaction manager coordinates this if configured and invoked within the right scope.

## 2. Scenario: Two Rows Written, Third Row Fails

Suppose the table starts empty:

~~~sql
CREATE TABLE batch_item (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL
);
~~~

The application wants to insert three items sequentially:

~~~text
(1, 'One')  -> valid
(2, 'Two')  -> valid
(1, 'Dup')  -> PRIMARY KEY duplicate error
~~~

Observable progression on a database supporting this scenario, such as H2 in the runnable example in Section 3:

| Checkpoint | No transaction wrapping the batch, auto-commit on | Entire batch in one transaction, error triggers rollback |
| --- | --- | --- |
| Write `id=1` first time | Succeeds and may already be committed | Provisionally succeeds, not yet committed |
| Write `id=2` | Succeeds and may already be committed | Provisionally succeeds, not yet committed |
| Write `id=1` second time | Primary key error | Primary key error |
| State after error handling | First two rows **may** remain in the DB | No rows from that transaction remain if rollback completes |
| Atomicity of *the whole group* | Not guaranteed | Guaranteed within the transaction scope and suitable DB resources |

The decisive point is that **`ROLLBACK` only undoes uncommitted changes of that exact transaction**. It cannot "rewind" commits already completed in other transactions. Do not rely on the assumption that "a batch is one method call" to protect business operations such as updating balances, creating orders with line items, or importing data that must be consistent as a group.

## 3. Runnable Java 17 Example: Same Batch, Two Outcomes

The example uses Spring JDBC, `TransactionTemplate`, and in-memory H2 to avoid depending on a Spring Boot application. The program intentionally triggers a primary key error twice: first **without an enclosing transaction**, and second **wrapping the entire batch in one transaction**. It catches the exception **outside** the transaction so it can count the remaining rows.

Create the file structure:

~~~text
batch-atomicity-demo/
├── pom.xml
└── src/main/java/example/BatchAtomicityDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>batch-atomicity-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.BatchAtomicityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/example/BatchAtomicityDemo.java`:

~~~java
package example;

import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class BatchAtomicityDemo {

    record Item(long id, String name) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_atomicity;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE batch_item (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL
                )
                """);

        List<Item> rows = List.of(
                new Item(1, "One"),
                new Item(2, "Two"),
                new Item(1, "Dup")
        );

        // Attempt 1: No transaction wrapping the entire batch.
        try {
            insertBatch(jdbc, rows);
        } catch (DataAccessException expected) {
            System.out.println("No tx: batch failed");
        }
        System.out.println("No tx: rows=" + countRows(jdbc));

        // Clear attempt 1 data so both cases start from the same initial state.
        jdbc.update("DELETE FROM batch_item");

        // Attempt 2: Same operation, but the transaction manager manages the connection,
        // rolling back when DataAccessException escapes the callback.
        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource)
        );
        try {
            tx.executeWithoutResult(status -> insertBatch(jdbc, rows));
        } catch (DataAccessException expected) {
            System.out.println("With tx: batch failed");
        }
        System.out.println("With tx: rows=" + countRows(jdbc));
    }

    static void insertBatch(JdbcTemplate jdbc, List<Item> rows) {
        jdbc.batchUpdate(
                "INSERT INTO batch_item(id, name) VALUES (?, ?)",
                rows,
                3,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.name());
                }
        );
    }

    static int countRows(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM batch_item", Integer.class
        );
    }
}
~~~

In the root directory, with JDK 17+ and Maven installed:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the program with H2 and the dependency versions above:

~~~text
No tx: batch failed
No tx: rows=2
With tx: batch failed
With tx: rows=0
~~~

**Result explanation:** In the first run, H2 accepted the first two `INSERT`s before detecting the duplicate key; without an enclosing transaction, two rows were committed. In the second run, `TransactionTemplate` started a transaction, `JdbcTemplate` used the connection bound to that transaction, and the exception escaping the callback caused the manager to roll back both executed `INSERT`s; 0 rows remained. The `DELETE` statement between the two runs only resets test data and is **not** part of Attempt 2's transaction.

This example confirms the **possibility of partial updates**, not a promise that every driver or database leaves exactly 2 rows after a failed batch when auto-commit is enabled. DBMSs have different rules for handling batches and statements; results must be verified on your real DB/driver. In production applications, do not swallow `DataAccessException` if business logic requires rollback; the `catch` block here sits outside the transaction call solely to report the experiment's outcome.

## 4. Applying in a Spring Application: Placing Transactions at the Service Layer

In a Spring JDBC application, `JdbcTemplate.batchUpdate(...)` **does not add a transaction on its own**. Boundaries should encompass the *unit of business work* at the service layer: one call may include one batch, multiple batches, or several related update statements. The following example is a **code snippet placed in a Spring application with JDBC already configured**, not a second standalone program.

~~~java
package example;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchItemService {
    private final JdbcTemplate jdbc;

    public BatchItemService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveAll(List<Item> items) {
        jdbc.batchUpdate(
                "INSERT INTO batch_item(id, name) VALUES (?, ?)",
                items,
                100,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.name());
                }
        );
        // If there are more DB operations that must succeed together, place them here
        // so they participate in the same transaction.
    }

    public record Item(long id, String name) {}
}
~~~

For `@Transactional` to take real effect, these conditions must hold:

1. `BatchItemService` is a Spring-managed bean and the method is called **through the Spring proxy from outside the bean**. Internal self-invocation `this.saveAll(...)` within the same object is not intercepted by the proxy under the default mechanism.
2. Configuration enables transaction management and provides a suitable `PlatformTransactionManager`. For JDBC on a single `DataSource`, use `JdbcTransactionManager` or `DataSourceTransactionManager` as appropriate; in plain Spring configuration, declare `@EnableTransactionManagement`.
3. `JdbcTemplate` and the transaction manager reference the **same managed `DataSource`**; statements obtain connections through Spring's mechanism to join the active transaction. Calling `DriverManager.getConnection(...)` manually inside may create a connection outside the transaction.
4. Errors must trigger rollback. Spring's `DataAccessException` is unchecked, so it rolls back by default when escaping a proxy-managed method. By default `@Transactional` does not roll back on checked exceptions unless configured otherwise.
5. The database/tables genuinely support transactions for the executed operations; do not expect rollback on statements with implicit commit or resources outside DB boundaries.

In Spring Boot with JDBC auto-configuration enabled, an appropriate transaction manager is usually already registered; inspect existing beans instead of blindly declaring extra managers. In plain Spring configuration, an illustrative setup is (used when no equivalent manager exists):

~~~java
@Configuration
@EnableTransactionManagement
public class JdbcTxConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

This configuration snippet needs corresponding imports from `org.springframework.context.annotation`, `org.springframework.transaction`, `org.springframework.jdbc.datasource`, and `javax.sql`; it is used inside a Spring context with a `DataSource` bean. Putting `@Transactional` on a method while calling `new BatchItemService(...)` or invoking internally via `this` will not trigger the expected proxy behavior.

### One Transaction Across Multiple Chunks

Suppose you import 10,000 records in chunks of 100. `batchSize=100` only tells Spring to divide JDBC work into smaller batches; **it does not limit or extend transaction scope**. If all 10,000 records must succeed together, place the loop or `batchUpdate` call inside **one** `@Transactional` method (and ensure consistent transaction manager/connection usage). If each chunk runs in its own transaction and commits, a failure in a later chunk does not undo earlier chunks.

Conversely, a very long transaction holds locks, logs, and resources longer. Transaction scope must reflect true consistency requirements: some workflows accept per-chunk success with retry/idempotency mechanisms; others strictly require a single shared commit. Do not compromise correctness by silently switching from a group-wide transaction to per-chunk commits.

## 5. Why `@Transactional` Might Still Fail to Protect a Batch

| Symptom | Possible Cause | How to Check or Fix |
| --- | --- | --- |
| Partial data persisted after an error | No active transaction, or exception caught and ignored before leaving the transactional method | Verify active transaction; let the appropriate exception escape the method, or mark `rollbackOnly` when handling errors inside |
| Annotation present but no rollback | Self-invocation in the same class, object instantiated with `new`, or transaction configuration not enabled | Call the service via a proxy-managed Spring bean; check transaction manager bean and proxy |
| Some statements still commit | Different connection/`DataSource`; `REQUIRES_NEW` propagation may have committed an inner transaction; one step ran outside transaction | Trace each connection and transaction boundary; check `propagation` |
| Checked exception occurs yet data commits | Default rollback follows unchecked rules; method returns normally or checked exception is outside rollback rules | Use `@Transactional(rollbackFor = Exception.class)` if business rules require, or throw an appropriate exception |
| Rollback fails to undo all effects | DDL with implicit commit, non-transactional table/engine, sending email/HTTP/Kafka or writing files outside the DB transaction | Separate non-DB operations; use transactional outbox, saga, or appropriate compensation when needed |
| Error appears after method returns | Async call, transaction already ended, work moved to another thread losing thread-bound context | Place transaction on the actual unit of execution; clarify threads and commit timing |

**Two easily overlooked cases:**

- Catching an error inside the method and only logging it: `catch (DataAccessException ex) { log.warn(...); }` can cause the transaction to end with a commit because no exception escapes, unless the resource/manager already marked it rollback-only. If the whole operation should fail, rethrow the exception or explicitly mark rollback-only.
- `@Transactional(propagation = REQUIRES_NEW)` starts an independent transaction. Changes in that transaction can commit earlier; a subsequent rollback of the outer transaction cannot undo that independent commit.

## 6. Reading Batch Results and Exceptions Accurately

`JdbcTemplate.batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` returns `int[][]`: each sub-array holds statement results for one chunk. Other `batchUpdate` overloads may return `int[]`. Affected row counts come from the JDBC driver; `Statement.SUCCESS_NO_INFO` (value `-2`) means the driver reported success without knowing the exact row count; `Statement.EXECUTE_FAILED` (value `-3`) indicates a failed statement in cases where the driver continues reporting per-element status.

In raw JDBC, `BatchUpdateException.getUpdateCounts()` can indicate execution progress up to the failure point, but **it is neither proof of commit nor a sign that all rows will remain after rollback**. Spring may translate `SQLException` into `DataAccessException`; inspect the root exception when diagnosing, and also query DB state after the transaction finishes to verify actual impact.

Things to check while debugging:

- Is a transaction actually active at the batch call site? You can use `TransactionSynchronizationManager.isActualTransactionActive()` to aid logging in Spring.
- Which SQL error occurred: unique/check/foreign key, `NOT NULL` constraint, or connection error?
- Do the statements actually use the same connection bound by the transaction manager?
- After the exception and once the transactional method has exited, how much data remains? Read from a new transaction/connection when verifying **committed** state.
- If the driver supports multiple batching/rewrite strategies, verify behavior on the exact DB, driver version, and production settings.

## 7. Testing Atomicity by Behavior, Not by Annotation

A meaningful test must intentionally trigger an error on a later element and verify DB state **after the transactional method completes**:

1. Create a table with clear constraints and seed deterministic data; use a list containing two valid rows and one duplicate-key row.
2. Call the `@Transactional` service method from another bean or from the test via the Spring bean so the call genuinely goes through the proxy.
3. Assert that a `DataAccessException` or configured rollback business exception is thrown; do not merely check update count arrays.
4. Re-query and assert **none of the rows from the attempted group were committed**. If the group touches multiple tables, check all relevant tables.
5. You can run a control call without a transaction in a separate test setup to observe partial updates; do not treat the remaining row count as a constant across all DBs.

Note: tests themselves annotated with `@Transactional` sometimes roll back after each test, masking whether the service actually has a transaction. When testing service commit boundaries, structure the test to inspect state outside the test's transaction, or disable test-level transactions and clean up data explicitly.

## 8. Practical Rules and Limits to Remember

- **Batching optimizes command dispatch; transactions decide which changes commit or roll back together.** They are two orthogonal axes.
- Place transactions around the smallest business unit that must succeed together; manage connections/`DataSource` consistently and select the transaction manager matching the resource type.
- Let failure exceptions propagate across the transaction boundary with appropriate rollback rules. Do not accidentally swallow errors or start an independent transaction mid-flow.
- Check transactional properties of tables/engines and DDL statements; some DBs perform implicit commits. A single DB's transaction does not automatically govern network services, files, message brokers, or multiple DBs.
- For large batches, balance chunk size, lock hold time, resources, retries, and idempotency. If committing per chunk is required, explicitly document "partial success" semantics and design recovery.
- Use deliberate failure tests and post-transaction queries to prove atomicity; annotations, `updateCounts`, and "batch complete" logs are only secondary signals.

**Self-check:** If 100 records are processed via `JdbcTemplate.batchUpdate` with `batchSize=20` and the 73rd record violates a primary key, what happens to the first 72 records? **You cannot conclude from `batchSize` alone.** You must know whether all 100 records ran inside one proper transaction, whether the exception triggered rollback, and how the driver/DB and any non-transactional steps behaved. If one transaction wrapped the whole run and rollback succeeded, none of the group's records were committed; if chunks or individual statements were committed earlier, partial data may remain.

### References

- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
