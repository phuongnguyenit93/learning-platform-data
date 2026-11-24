# Batching Reduces Round Trips for Many Similar Operations

## 1. What Problem Does Batching Solve?

When a Spring application needs to execute hundreds or thousands of INSERT, UPDATE, or DELETE statements that share the **same SQL structure but differ in parameters**, looping over each statement individually typically creates many round trips between the application and the database. **JDBC batching** groups multiple parameter sets into a single batch execution call on the driver to reduce communication and statement-management overhead.

Example of updating the status for 1,000 orders:

~~~text
No batching:
Application -> DB: UPDATE ... WHERE id = 1
Application -> DB: UPDATE ... WHERE id = 2
...
Application -> DB: UPDATE ... WHERE id = 1000

With batching, batchSize = 200:
Application -> JDBC driver: 200 parameter sets -> executeBatch()
                           200 parameter sets -> executeBatch()
                           ... (5 batches)
~~~

With batching, the driver has the opportunity to group/pipeline commands and reduce network round trips. **Five calls to `executeBatch()` do not guarantee that there are only five packets or five physical round trips**: the details depend on the driver, protocol, configuration, and database.

### Distinguishing Three Concepts

| Approach | Meaning | When Appropriate |
| --- | --- | --- |
| Calling `jdbcTemplate.update(...)` in a loop | Each element is a separate update call | A few records, or different logic per operation |
| `jdbcTemplate.batchUpdate(...)` | Multiple parameter sets for one SQL template; JDBC driver executes in batches | Many similar INSERT/UPDATE/DELETE operations |
| A single bulk SQL statement, such as `UPDATE ... WHERE ...` or `INSERT ... VALUES (...), (...)` | The database itself processes multiple rows in one SQL statement | When the entire requirement can be expressed as a single set-based statement |

JDBC batching **does not turn 1,000 UPDATE statements into a single UPDATE**. The database still has to execute the corresponding logic for each parameter set. If a set-based SQL statement can solve the business requirement properly, consider it first.

## 2. JDBC Mechanism and Impact on Round Trips

JDBC provides `PreparedStatement` to fix the SQL and vary data via parameters. When using batching, the equivalent idea is:

~~~java
// Plain JDBC illustration; dataSource is provided by the application.
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "UPDATE task SET status = ? WHERE id = ?")) {
    for (StatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.id());
        ps.addBatch();
    }
    int[] updateCounts = ps.executeBatch();
}
~~~

This is an **illustrative snippet**, not a standalone runnable Java file: `dataSource`, `StatusChange`, and `changes` belong to the calling context. With Spring, `JdbcTemplate` manages acquiring/releasing connections, creating/closing statements, and translating `SQLException` into `DataAccessException`.

- `addBatch()` queues a parameter set into the batch; `executeBatch()` asks the driver to process the queued items.
- The SQL must have a suitable structure to reuse the `PreparedStatement`; only parameter values change.
- The driver may optimize, send grouped commands, or fall back to individual execution if it does not support batching. **There is no guarantee of speedup by a fixed factor.**
- Batching reduces communication/statement overhead. It does not bypass parsing/execution, UNIQUE/FOREIGN KEY constraints, triggers, index updates, locks, or database log-writing costs.

Estimation model to understand trends (not an exact measurement formula):

- `N`: number of operations; `k`: items per batch; `L`: communication overhead; `E`: average execution time per item.
- Without batching: `T ≈ N × (L + E)`.
- With batching: `T ≈ ceil(N/k) × L + N × E + batch packaging/sending overhead`.

The largest reduction is usually `L`, especially when the database is remote and each statement is small. For a database busy with CPU/I/O, locks, or heavy triggers, the benefit may be limited.

## 3. Spring JDBC: Runnable Example with Java 17+

The following example uses Spring Boot 3.3.x, Spring JDBC, and in-memory H2. Two records start in the `NEW` status; the service updates them with the same SQL template to `DONE` in one batch. `@Transactional` is separated onto a Spring-managed service so the call goes through the transaction proxy.

File structure:

~~~text
batch-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/BatchDemoApplication.java
    └── resources/application.properties
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'batch-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**src/main/resources/application.properties**

~~~properties
spring.datasource.url=jdbc:h2:mem:batchdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
~~~

**src/main/java/demo/BatchDemoApplication.java**

~~~java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class BatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TaskBatchWriter writer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE task (
                        id BIGINT PRIMARY KEY,
                        status VARCHAR(20) NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO task (id, status) VALUES (?, ?)",
                    1L, "NEW");
            jdbc.update(
                    "INSERT INTO task (id, status) VALUES (?, ?)",
                    2L, "NEW");

            List<StatusChange> changes = List.of(
                    new StatusChange(1L, "DONE"),
                    new StatusChange(2L, "DONE")
            );

            int[][] counts = writer.updateStatuses(changes);
            int[] sizes = Arrays.stream(counts)
                    .mapToInt(batch -> batch.length)
                    .toArray();
            System.out.println("Batch sizes: " + Arrays.toString(sizes));

            Integer done = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM task WHERE status = ?",
                    Integer.class, "DONE");
            System.out.println("DONE rows: " + done);
        };
    }
}

record StatusChange(long id, String status) {}

@Service
class TaskBatchWriter {
    private static final int BATCH_SIZE = 100;
    private final JdbcTemplate jdbc;

    TaskBatchWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int[][] updateStatuses(List<StatusChange> changes) {
        if (changes.isEmpty()) {
            return new int[0][];
        }

        return jdbc.batchUpdate(
                "UPDATE task SET status = ? WHERE id = ?",
                changes,
                BATCH_SIZE,
                (ps, change) -> {
                    ps.setString(1, change.status());
                    ps.setLong(2, change.id());
                });
    }
}
~~~

In the project directory, use Gradle 8.x and JDK 17+ (or the wrapper if already present):

~~~bash
gradle bootRun
~~~

Two lines printed by the program (aside from Spring Boot startup logs):

~~~text
Batch sizes: [2]
DONE rows: 2
~~~

**Exact explanation:**

1. `JdbcTemplate.batchUpdate(sql, collection, batchSize, setter)` takes the same SQL template, iterates over elements, and binds parameters via `ParameterizedPreparedStatementSetter`.
2. `BATCH_SIZE = 100` is the limit on the number of items in a group; because the example only has 2 items, the result has one sub-array containing 2 update counts. This does not prove the database used exactly one round trip.
3. The return value is `int[][]`: each sub-array corresponds to a group, and each number inside corresponds to an item. **The number of array elements** is not the total number of modified rows.
4. `@Transactional` applies when `CommandLineRunner` calls the public method on `TaskBatchWriter` through the Spring bean. If a data error causes a `DataAccessException` to escape the method, Spring marks that transaction for rollback by default.
5. In the example, the two `jdbc.update` statements creating sample data are **outside** the `updateStatuses` transaction; real applications need to set transaction boundaries according to business logic.

If not using Spring Boot, you can still instantiate `JdbcTemplate` with a `DataSource` and call the same batch APIs; the example above uses Boot for minimal runnable configuration.

## 4. Spring JDBC Batch APIs

### 4.1. `BatchPreparedStatementSetter`: Full Control of Index-Based Binding

With a list already in memory:

~~~java
// Method snippet placed inside a class that already has the JdbcTemplate jdbc field.
int[] updateStatuses(List<StatusChange> changes) {
    return jdbc.batchUpdate(
            "UPDATE task SET status = ? WHERE id = ?",
            new org.springframework.jdbc.core.BatchPreparedStatementSetter() {
                @Override
                public void setValues(
                        java.sql.PreparedStatement ps, int i)
                        throws java.sql.SQLException {
                    StatusChange change = changes.get(i);
                    ps.setString(1, change.status());
                    ps.setLong(2, change.id());
                }

                @Override
                public int getBatchSize() {
                    return changes.size();
                }
            });
}
~~~

This API returns `int[]` for a single call, but a very large list can make the batch too big. You can split the list yourself or use the overload with the `batchSize` parameter as in the runnable example above.

### 4.2. Overload with `batchSize`: Convenient for Large Data

~~~java
int[][] counts = jdbc.batchUpdate(
        "UPDATE task SET status = ? WHERE id = ?",
        changes,
        200,
        (ps, item) -> {
            ps.setString(1, item.status());
            ps.setLong(2, item.id());
        });
~~~

If there are 450 items and `batchSize = 200`, the expected group sizes are **200, 200, 50**. The update count values inside still depend on the driver; do not assume one item always affects exactly one row.

### 4.3. `NamedParameterJdbcTemplate`: Readable When There Are Many Columns

~~~java
// Method snippet placed inside a class that already has the NamedParameterJdbcTemplate named field.
org.springframework.jdbc.core.namedparam.SqlParameterSource[] params =
        changes.stream()
                .map(item -> new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
                        .addValue("status", item.status())
                        .addValue("id", item.id()))
                .toArray(
                    org.springframework.jdbc.core.namedparam.SqlParameterSource[]::new);

int[] counts = named.batchUpdate(
        "UPDATE task SET status = :status WHERE id = :id",
        params);
~~~

Named parameters help reduce ordering mistakes in SQL with many fields. You can use `SqlParameterSourceUtils.createBatch(...)` when beans/maps have matching field names. When binding `null` whose type is hard to infer, consider `MapSqlParameterSource.addValue(name, value, sqlType)` or `PreparedStatement.setNull(index, sqlType)` to avoid data type errors or unnecessary metadata queries.

### 4.4. INSERT and DELETE Also Support Batching

As long as the SQL structure is identical across elements:

~~~sql
INSERT INTO task (id, status) VALUES (?, ?)
DELETE FROM task WHERE id = ?
~~~

Statements with different SQL structures (different tables, column counts, expressions) cannot be grouped into **the same `PreparedStatement` batch** using the pattern above. You can classify them by SQL template and batch each group separately.

## 5. Transactions: Batching Does Not Mean Atomic

**Batching is how statements are sent/executed; a transaction is the commit/rollback boundary.** The two mechanisms solve two different problems.

- **With `@Transactional` at the right boundary:** batches inside the method participate in the same transaction on a transaction-capable DataSource; when an uncaught `DataAccessException` escapes, Spring's default configuration rolls back uncommitted changes in the transaction.
- **Without an enclosing transaction:** depending on connection/autocommit configuration and the driver, some items or groups may already be committed before another group fails.
- **Catching errors without rethrowing:** the transaction may continue and commit the successful portion if not marked for rollback; actively decide your handling policy.
- **Checked exceptions:** by default `@Transactional` rolls back on `RuntimeException` or `Error`, not automatically on checked exceptions; configure `rollbackFor` when business logic requires it.
- **Internal calls within the same bean:** `this.updateStatuses(...)` typically does not go through the Spring proxy, so `@Transactional` may not be applied. Call through another bean/service or redesign the boundary.

Suppose 2,500 rows are split into 25 batches and executed together inside **one** `@Transactional` method: that can still be **one transaction**, not 25 transactions. Conversely, creating 25 separate transactions helps limit lock hold time, but no longer guarantees all-or-nothing across all 2,500 items.

If retry after failure is needed, determine whether a batch may have already committed, use appropriate transactions, and design idempotent operations (unique key/upsert/status condition) so side effects are not duplicated unintentionally.

## 6. Understanding Update Counts and Execution Errors

JDBC returns an update count for each item. In common Spring JDBC methods, the result is `int[]` or `int[][]` depending on the overload.

| Count Value | Meaning |
| --- | --- |
| `0` | No rows updated according to the driver result; for UPDATE by id, the id may not exist |
| Positive number | Number of affected rows reported by the driver for that item |
| `Statement.SUCCESS_NO_INFO` = `-2` | Driver indicates the item succeeded, but the row count is unknown |
| `Statement.EXECUTE_FAILED` = `-3` | Indicates the item failed in batch result info, if provided by the driver |

`BatchUpdateException` from JDBC may contain a count array for processed items; the driver may stop immediately or continue processing after a failing item. Spring JDBC typically translates SQL errors into a `DataAccessException`. Therefore, **do not rely on the result array always having complete counts when a batch fails**.

When you need to ensure every id exists, check results according to business requirements: `0` may be a logic error; `-2` cannot be used to conclude an exact row count. For UPDATEs with optimistic locking (such as `WHERE id = ? AND version = ?`), a count of `0` may indicate a version conflict.

Catch and handle exceptions at the proper layer, logging **group identifier, element count, related ids, and cause**, while avoiding logging full sensitive data. A failed batch does not automatically identify which item failed if the driver does not return enough information; when identification is needed, you can re-run on subsets in a controlled environment following transaction policy.

## 7. Choosing Batch Size Based on Data and System Limits

A batch should not hold an entire million records by default.

- You can start measuring with `batchSize` values of 100, 200, 500, or 1,000; **these are trial values**, not a universal optimal setting.
- Small batches: more `executeBatch()` calls, higher overhead, but lower memory, request size, and resource hold time.
- Large batches: fewer calls, but may increase memory, lock/transaction duration, message size, failure latency, and risk of hitting driver/database limits.
- For large/streaming data, read/transform in chunks and batch group by group; do not load the entire dataset into RAM just to build batches.
- Consider limits on parameter count, packet/request size, timeouts, logging/replication, and DB concurrency capacity. Limits for a multi-VALUES `INSERT` statement are not necessarily the same as limits for a `PreparedStatement` batch.
- In an environment with many concurrent requests, account for connection count, lock contention, and overall DB load; increasing batch size in isolation does not necessarily improve system throughput.

A sound sizing workflow: keep the dataset and transaction semantics constant, test multiple sizes, and measure p50/p95/p99 latency, rows/second, statement dispatch count, DB CPU/I/O, lock waits, and errors. Choose a balance of **throughput, response time, memory, and stability** instead of only looking at the runtime of a single import.

## 8. Does Spring Data JPA/Hibernate Automatically Batch on `saveAll()`?

**Do not assume `repository.saveAll(items)` is a single SQL statement or has JDBC batching enabled.** In Spring Data JPA, `saveAll` implementations typically iterate through elements and call `save` per entity; Hibernate decides when to flush and whether it can group JDBC DML depending on configuration, entity setup, and ID generation strategy.

Example Hibernate configuration via Spring Boot:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Effects and limitations:

- `hibernate.jdbc.batch_size` allows Hibernate to group similar DML statements into JDBC batches when appropriate.
- Ordering inserts/updates can help group more statements with the same structure, though it also has overhead and should be measured.
- When using the `IDENTITY` id strategy for INSERT, Hibernate typically cannot JDBC-batch inserts in the normal way because it must retrieve the generated id after each insert.
- The persistence context retains managed entities; processing very large row counts requires considering `flush()`/`clear()` per group, though `clear()` detaches entities and can alter cascade/dirty-checking behavior.
- `saveAllAndFlush()` requests a flush after saving, **not a single SQL statement**; bulk JPQL `UPDATE`/`DELETE` and native SQL have different semantics from entity lifecycle/cascading.

For large volumes of simple key-based updates without needing ORM lifecycle features, Spring JDBC `batchUpdate` generally provides more direct control over SQL, batch size, and counts. If business logic depends on the entity graph, callbacks, or optimistic locking, evaluate JPA/Hibernate before replacing it with plain SQL.

## 9. Common Design Mistakes and Fixes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Calling `jdbc.update` inside a `for` loop and thinking `@Transactional` batched it | A single transaction still makes many database calls | Use `batchUpdate` properly |
| Putting all data into one giant batch | High RAM usage, long lock hold times, hard-to-isolate errors | Split into groups and benchmark an appropriate size |
| Building SQL by string concatenation of data | SQL injection risk, hard to reuse statements | Use `PreparedStatement` with bind parameters |
| Assuming every update count equals `1` | Missing non-existent ids or driver returning `-2` | Check `0` and `-2` per business requirements |
| Swallowing exceptions inside `@Transactional` | May commit partial/incomplete data | Let errors propagate or explicitly mark for rollback |
| Overusing many small transactions in an import requiring atomicity | Data may be partially committed | Define transaction boundaries clearly |
| Concluding batching speeds things up without measuring | False optimization if bottleneck is index, lock, or I/O | Benchmark with real data, driver, and DB |
| Thinking `saveAll` is a JDBC batch | Lower performance than expected | Configure and observe actual Hibernate/JDBC behavior |

## 10. Workflow for Applying in a Real Application

1. **Identify repetitive work:** same INSERT/UPDATE/DELETE template, varying parameters; check whether simpler set-based SQL exists.
2. **Design inputs:** validate ids/data, avoid unintended duplicate operations, choose a suitable update order; if there is a version condition, check optimistic locking.
3. **Choose the API:** `JdbcTemplate.batchUpdate` when clear SQL and batch size are needed; `NamedParameterJdbcTemplate` when there are many named parameters; Hibernate batching when using entity lifecycle.
4. **Set transaction boundaries:** one transaction for the entire operation if atomicity is required; split transactions per group if partial commits are acceptable and resume/retry is in place.
5. **Execute and verify:** handle `DataAccessException`, inspect update counts, verify post-operation row counts, monitor logs/metrics; distinguish success, no-info, and failure.
6. **Measure before and after:** same data volume, indexes, and transaction semantics; observe actual round trips via driver/proxy/DB metrics when needed, rather than inferring from API group count.

### Self-Check Exercises

1. There are 10,500 operations and `batchSize = 300`. There are **35 groups** under this split; this conclusion does **not** guarantee 35 physical round trips. If `batchSize = 400`, the number of groups is **27** (26 full groups of 400 and a final group of 100).
2. There are 200 UPDATEs, but 3 ids do not exist. If business logic requires all ids to be updated, execution succeeding is not enough: check update counts (`0` if the driver can report it), or verify postconditions; do not treat `-2` as one row.
3. A service calls `saveAll(entities)` but logs still show individual INSERTs. Check `hibernate.jdbc.batch_size`, id generation strategy, statement ordering, flushing, and transaction usage rather than blindly increasing batch size indefinitely.
4. A third batch fails after two batches have already succeeded. The final outcome depends on **transaction boundary and rollback**, not simply on `batchSize`.

## 11. Key Takeaways

Batching reduces communication overhead when many operations share the same SQL and vary parameters. To use it properly in Spring Data Access, distinguish **JDBC batching**, **set-based SQL**, **transactions**, and **ORM flushing**. Design batch sizes around real load, handle update counts and exceptions with the right semantics, and verify through measurement on your actual driver and database.

**Official Documentation:**

- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html)
- [Spring Framework — Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Hibernate ORM — Batching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch)
- [Spring Data JPA — SimpleJpaRepository.saveAll](https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java)
