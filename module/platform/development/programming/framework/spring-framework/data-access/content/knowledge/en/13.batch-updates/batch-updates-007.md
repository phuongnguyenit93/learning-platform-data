# BatchUpdateException, Partial Failures, and Driver Information

## 1. Context and Goal

In the **Spring Framework – Data Access** module, batch updates let you send many `INSERT`, `UPDATE`, or `DELETE` operations over JDBC with fewer round trips to the database. However, when one statement fails, the question is not just "did the batch fail or not" but also:

- How far did the driver execute, and did it continue after the error?
- Do returned values mean **executed**, **how many rows affected**, or **committed**?
- Which exception does Spring wrap the JDBC error into, and is the original information still accessible?
- How do you roll back, log, isolate bad records, and retry without corrupting data?

This lesson focuses on `java.sql.BatchUpdateException`, per-statement execution results, and handling in `JdbcTemplate`. The scope is JDBC/Spring JDBC; do not equate this behavior with JPA `saveAll` or R2DBC.

## 2. The Path of a Batch

In raw JDBC, an application usually sets parameters, calls `PreparedStatement.addBatch()` multiple times, and finally calls `executeBatch()`. With Spring JDBC, `JdbcTemplate.batchUpdate(...)` handles statement creation, parameter binding, invoking JDBC, and cleaning up resources.

```text
Ordered input list
    -> JdbcTemplate.batchUpdate(...)
    -> PreparedStatement / JDBC driver
    -> Database processes each operation or optimizes the whole batch
    -> Success: int[] update counts
       JDBC Error: SQLException / BatchUpdateException
    -> Spring translates SQLException to DataAccessException
```

Note: batching is a mechanism for sending/executing multiple statements; **batching does not automatically create an atomic transaction boundary**. Atomicity depends on the transaction, driver, and database.

## 3. What Is BatchUpdateException?

`BatchUpdateException` lives in `java.sql` and extends `SQLException`. It can be thrown when `executeBatch()` encounters an error and carries extra information about the processed statements:

| API / Information | Meaning | How to Use |
| --- | --- | --- |
| `getUpdateCounts()` | `int[]` array of results reported by the driver in the order statements were added to the batch | Match positions that have reported results |
| `getLargeUpdateCounts()` | Corresponding `long[]` array | Prefer with `executeLargeBatch()` when row counts may be very large |
| `getSQLState()` | SQLState code supplied by the driver; may be `null` | Preliminary error categorization, cross-referenced with DB/driver docs |
| `getErrorCode()` | Vendor-specific error code; may be `0` | Look up specific cause by database |
| `getMessage()` | Driver message | Aid investigation; do not use string matching to drive logic |
| `getNextException()` | Chained additional `SQLException`s | Read detailed errors of one or more statements |
| `getCause()` | Cause in the Java exception chain | Trace back through wrapper layers |

`BatchUpdateException` is a **report from the driver**, not a guaranteed post-commit status table of records. Nor is it always present: if the driver does not support JDBC batching, `JdbcTemplate` may execute updates sequentially and throw a `DataAccessException` with a different JDBC cause.

### Special Result Codes

| Element value `counts[i]` | Interpretation |
| --- | --- |
| `0` | Statement reported a result, but affected zero rows; not automatically an error |
| Positive number such as `1`, `2` | Number of affected rows reported by the driver |
| `Statement.SUCCESS_NO_INFO` = `-2` | Statement succeeded, but the driver does not know or report the exact row count |
| `Statement.EXECUTE_FAILED` = `-3` | Statement at that position failed; commonly appears when the driver continues processing after an error |

Do not add negative codes to a "successful rows" total, do not treat `-2` as an error, and do not turn `0` into "business success" if your requirement is to update exactly one row.

## 4. Two Partial-Failure Modes: Driver Stops or Continues

Suppose four parameter sets are submitted in order `[A, B, C, D]`.

**When the driver stops on error:**

```text
Input:              A   B   C   D
getUpdateCounts() = [1, 0]
```

The first two results are reported (A affected 1 row, B affected 0 rows). The driver provides no result elements for C and D; under the JDBC "stop on failure" contract, the statement immediately following the two successful ones is the candidate culprit. There is no proof that D was executed. Whether A/B **were committed or not** depends on the transaction.

**When the driver continues after error:**

```text
Input:              A    B    C    D
getUpdateCounts() = [1, -3, -2, 0]
```

The driver reports A affected 1 row, B failed, C succeeded with unknown row count, and D affected 0 rows. The array has one element per statement; the `-3` position identifies the statement reported as failed by the driver. Even so, the transaction may ultimately roll everything back.

Interpreting results requires considering **whether the driver stops or continues**, whether it rewrites/merges batches, and the actual SQL statement. Some driver optimizations can limit precision when locating the failing record. Do not infer from `counts.length == input size` that "everything committed."

## 5. How Does Spring JDBC Return Values and Translate Exceptions?

Commonly used APIs:

| API | Result on Completion | Characteristics |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(String, BatchPreparedStatementSetter)` | `int[]` | One SQL, binds parameters by index `i` from `0` |
| `JdbcTemplate.batchUpdate(String, List<Object[]>)` | `int[]` | Each array holds parameters for one run of the same SQL |
| `NamedParameterJdbcTemplate.batchUpdate(String, SqlParameterSource[])` | `int[]` | Binds parameters by name |
| `JdbcTemplate.batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` | `int[][]` | Splits into groups of the specified size |

The grouped `int[][]` array is only meaningful **when the call completes**; if a group hits an error and an exception escapes, there is no guarantee you receive all result arrays as on success.

`JdbcTemplate` uses `SQLExceptionTranslator` to translate `SQLException` into an unchecked `DataAccessException` (for example, a constraint- or resource-related subtype). **Do not write `catch (BatchUpdateException e)` directly around `jdbcTemplate.batchUpdate(...)`**: Spring's signature throws `DataAccessException`, while the underlying JDBC exception usually sits in the cause chain. Do not assume every duplicate-key error always becomes `DuplicateKeyException`; the subtype depends on the translator, error code, and driver.

If the driver does not support batch updates, Spring may fall back to individual updates on one `PreparedStatement`. Therefore, monitoring logic must tolerate cases where no `BatchUpdateException` is found.

## 6. Spring Example: Ordered Input Data and Rollback

Assume an existing table `employee(id BIGINT PRIMARY KEY, full_name VARCHAR(200) NOT NULL)`, configured `DataSource`, `JdbcTemplate`, and an appropriate transaction manager. This is **a Spring service class**, not a standalone plain-Java program if dependencies/configuration are missing:

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeImportService {
    private final JdbcTemplate jdbcTemplate;

    public EmployeeImportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public int[] importEmployees(List<Employee> employees) {
        return jdbcTemplate.batchUpdate(
            "INSERT INTO employee (id, full_name) VALUES (?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int i)
                        throws SQLException {
                    Employee e = employees.get(i);
                    ps.setLong(1, e.id());
                    ps.setString(2, e.fullName());
                }

                @Override
                public int getBatchSize() {
                    return employees.size();
                }
            }
        );
    }

    public record Employee(long id, String fullName) {}
}
```

`setValues(..., i)` binds the `i`-th element in the list, so preserve the order/IDs of `employees` to aid diagnostics. Use `?` placeholders rather than concatenating data directly into SQL.

With `@Transactional` activated through a Spring proxy and a transaction manager using the same `DataSource`, a `DataAccessException` escaping the method (being a `RuntimeException`) triggers rollback under default rules. Note that `@Transactional` may not apply on internal self-invocation via `this` instead of going through the proxy. Also, the database must properly support transactions for that table/operation.

If logging is needed, catch the error in the **caller outside the transaction boundary**, or catch and rethrow. Swallowing exceptions inside a `@Transactional` method prevents Spring from knowing it must roll back; in some databases, the transaction is already marked aborted and commit will still fail.

## 7. Finding Root Information in Spring's Exception Chain

A service-layer exception can be wrapped multiple times. Calling only `getMessage()` on `DataAccessException` often misses SQL codes and update counts.

The Java 17 snippet below is a **standalone helper**, searching for `BatchUpdateException` across both `getCause()` and `SQLException.getNextException()` while guarding against exception-chain cycles:

```java
import java.sql.BatchUpdateException;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

public final class BatchErrorInspector {
    private BatchErrorInspector() {}

    public static BatchUpdateException findBatchFailure(Throwable error) {
        if (error == null) {
            return null;
        }

        Deque<Throwable> queue = new ArrayDeque<>();
        Set<Throwable> seen =
            Collections.newSetFromMap(new IdentityHashMap<>());
        queue.add(error);

        while (!queue.isEmpty()) {
            Throwable current = queue.removeFirst();
            if (!seen.add(current)) {
                continue;
            }
            if (current instanceof BatchUpdateException batch) {
                return batch;
            }
            if (current.getCause() != null) {
                queue.addLast(current.getCause());
            }
            if (current instanceof SQLException sql
                    && sql.getNextException() != null) {
                queue.addLast(sql.getNextException());
            }
        }
        return null;
    }
}
```

After catching `DataAccessException e` in the caller, you can obtain `BatchUpdateException b = BatchErrorInspector.findBatchFailure(e)`. If `b != null`, log `b.getSQLState()`, `b.getErrorCode()`, the length and elements of `b.getUpdateCounts()`; if `b == null`, still log the `DataAccessException` classification and any `SQLException` cause, because errors can originate outside `executeBatch()`.

Read the `getNextException()` chain to find detailed errors. For example, an SQLState in class `23` generally indicates a constraint violation under standard SQLState; specific SQLState codes, vendor codes, messages, and behavior must be checked against the **actual database + JDBC driver version**. Avoid building logic on English driver messages.

**Diagnostic data to log:** operation name, number of statements in the batch, group index, non-sensitive business identifier of each record (when permitted), SQLState, vendor code, exception type, counts array, and driver/database info. **Never log passwords, tokens, full interpolated statements, or personal data from parameters.**

## 8. Standalone Runnable Java 17 Example: Understanding Update Counts

This example **constructs two simulated exceptions** to illustrate response formats. It does not connect to a database and does not prove how any specific driver will behave.

Save as `BatchFailureDemo.java`:

```java
import java.sql.BatchUpdateException;
import java.sql.Statement;
import java.util.Arrays;

public class BatchFailureDemo {
    private static void explain(String label,
                                BatchUpdateException error,
                                int submitted) {
        int[] counts = error.getUpdateCounts();
        System.out.println(label + ": " + Arrays.toString(counts));

        for (int i = 0; i < counts.length; i++) {
            int value = counts[i];
            String meaning = value == Statement.SUCCESS_NO_INFO
                ? "SUCCESS_NO_INFO"
                : value == Statement.EXECUTE_FAILED
                    ? "EXECUTE_FAILED"
                    : "affected=" + value;
            System.out.println("  #" + i + ": " + meaning);
        }

        if (counts.length < submitted) {
            System.out.println("  no result from index " + counts.length);
        }
    }

    public static void main(String[] args) {
        BatchUpdateException stop = new BatchUpdateException(
            "Simulated failure", "23505", 0, new int[] {1, 0});
        BatchUpdateException continueAfterFailure =
            new BatchUpdateException(
                "Simulated failure", "23505", 0,
                new int[] {
                    1,
                    Statement.EXECUTE_FAILED,
                    Statement.SUCCESS_NO_INFO,
                    0
                });

        explain("stop", stop, 4);
        explain("continue", continueAfterFailure, 4);
    }
}
```

Run with JDK 17 or higher:

```bash
javac BatchFailureDemo.java
java BatchFailureDemo
```

Exact stdout output:

```text
stop: [1, 0]
  #0: affected=1
  #1: affected=0
  no result from index 2
continue: [1, -3, -2, 0]
  #0: affected=1
  #1: EXECUTE_FAILED
  #2: SUCCESS_NO_INFO
  #3: affected=0
```

In real applications, if using `Statement.executeLargeBatch()` with huge row counts, prefer `BatchUpdateException.getLargeUpdateCounts()` to avoid `int` overflow. Do not replace `int[]` in Spring APIs with `long[]` when the method signature only returns `int[]`.

## 9. Partial Failure Differs from Committed State

Separate three concepts:

1. **Submitted**: the application added the statement to the batch.
2. **Driver reported executed**: a counts element is a non-negative number or `SUCCESS_NO_INFO`.
3. **Committed**: the change took durable effect according to the transaction.

`getUpdateCounts()` reflects level (2), **not level (3)**. For instance, the driver reports `[1, 1]` and then the third statement fails; if the entire batch is inside one transaction and rollback succeeds, the first two changes are not committed either. Conversely, without an enclosing transaction and when auto-commit/driver/DB allows partial commits, partial data may persist. Do not infer behavior from the counts array; verify the transaction, `autoCommit`, DB traits, errors at commit time, and post-transaction data.

| Transaction Organization | On Mid-Batch Error | How to Decide |
| --- | --- | --- |
| One `@Transactional` wrapping the entire import | Unchecked errors propagating through the proxy typically trigger rollback of the entire transaction | Choose when all-or-nothing is required |
| Each chunk has its own transaction | Earlier chunks may have committed; failing chunk rolls back | Choose when business rules allow saving progress per chunk |
| No explicit transaction | Risk of partial persistence depending on connection/driver/DB | Do not use if atomicity is required |
| Catch exception and continue inside transaction | State may become unusable; commit may fail or partial data may be saved | Do not "continue as normal" without a recovery policy |

Confirm behavior via integration tests on the exact production DB and driver version. On some DBs, a single failed SQL statement puts the active transaction into an abort-only state requiring rollback; savepoints or recovery must be designed and tested separately.

## 10. Investigation, Isolation, and Safe Retries

Practical handling workflow:

1. **Preserve input order:** record batch ID, chunk ID, and an index-to-business-key mapping so counts are meaningful; avoid storing sensitive data in logs.
2. **Inspect Spring exceptions:** check the `DataAccessException` subtype and search for `SQLException` / `BatchUpdateException` across both cause and next-exception chains.
3. **Interpret counts on the right branch:** distinguish stop-on-error drivers, continue-on-error drivers, `-2`, `-3`, and statements with no result. Explicitly record "unknown" when the driver provides insufficient evidence.
4. **Verify transaction outcome:** did it roll back or commit? If the error happened at commit time, do not assume data was definitely not saved; verify state via business/idempotency keys.
5. **Classify root cause:** unique/foreign-key/not-null violations and invalid data require fixing data or rules; deadlocks/transient connection errors may be considered for retry after rollback, depending on error type and safe repeatability.
6. **Controlled retries:** only retry in a new transaction when the cause is appropriate; use unique keys, idempotency keys, or explicitly designed upserts to avoid duplicating data. Never blindly re-run an entire batch when commit state is uncertain.
7. **Isolate bad data if needed:** after rollback, you can split into smaller batches to locate the failing record, or process record by record in independent transactions, but only when business rules accept partial success and full reporting is in place.

In Spring, the simplest approach for an **all-or-nothing** task is letting `DataAccessException` escape the `@Transactional` method. If partial success is desired, explicitly design per-chunk transactions, per-record state, retry rules, and post-commit reporting.

## 11. Common Misconceptions

- **"Having `-2` means failure."** False: `SUCCESS_NO_INFO` means success with an unknown row count.
- **"`counts.length` is smaller than input, so the rest definitely never touched the DB."** You cannot conclude this absolutely beyond verified driver contracts/behavior, especially with batch optimizations and multi-layer errors.
- **"`1` in counts means the record is permanently saved."** False: the transaction can still roll back.
- **"Spring always throws `BatchUpdateException`."** False: the Spring layer usually throws `DataAccessException`, sometimes without a `BatchUpdateException` underneath.
- **"If I catch and log the error in `@Transactional` and return, Spring still rolls back automatically."** Not guaranteed; let the exception escape or explicitly mark rollback by design.
- **"Any batch error can be retried."** False: constraint/data errors do not vanish on their own, and non-idempotent retries can cause duplicates.
- **"SQLState and error codes are identical across all DBs."** False: check documentation for the specific DBMS and driver.

## 12. Verification Exercise on a Real System

Create a table with a primary key, submit a four-row batch where the third row has a duplicate key; run two modes **with** and **without** an enclosing transaction (in a test environment). Record:

- The exception type thrown by Spring and all nested `SQLException`s inside.
- `getSQLState()`, `getErrorCode()`, `getUpdateCounts()`, and `getNextException()` when a `BatchUpdateException` is found.
- Input order ↔ error index; whether the driver stops or continues.
- Rows actually remaining in the DB **after** rollback/commit.
- Behavior when split into two chunks and when retrying one chunk with an idempotent operation.

Next, try an `UPDATE` with a non-existent key to observe that a count of `0` can be a valid JDBC result while still failing a business requirement. Try `BatchPreparedStatementSetter` and the `batchSize` overload to observe the difference between `int[]` and `int[][]` on success.

## Primary Sources

- [Java 17: BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html) — counts contract, stop/continue behavior, `getLargeUpdateCounts()`.
- [Spring Framework: JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html) — `batchUpdate` overloads, result types, and chunked batching.
- [Spring Framework: JDBC exception translation](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/core.html) — translating `SQLException` to `DataAccessException`.
- [Spring Framework: Transaction rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html) — default rollback for unchecked exceptions.
