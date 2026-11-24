# Reading Per-Element Row Counts and `SUCCESS_NO_INFO` in Batch Updates

In Spring Framework Data Access, `JdbcTemplate.batchUpdate(...)` lets you send multiple SQL executions in a batch and returns information about the **affected row count for each element**. Developers must correctly read both non-negative counts and the special code `Statement.SUCCESS_NO_INFO`: an operation succeeding **does not mean** JDBC always knows the exact number of affected rows.

## 1. Batch Results Are Per-Element Results

Suppose the application needs to update the status of three orders in sequence:

| Position in batch (index) | Input | Executed SQL with parameters |
| --- | --- | --- |
| 0 | `id = 101`, `status = DONE` | `UPDATE orders SET status = ? WHERE id = ?` |
| 1 | `id = 102`, `status = DONE` | Same SQL, next parameter set |
| 2 | `id = 103`, `status = DONE` | Same SQL, next parameter set |

If `batchUpdate` returns `int[] counts = {1, 0, -2}`, then `counts[0]` corresponds to the first element, `counts[1]` to the second element, and `counts[2]` to the third element. The elements **do not** represent separate tables, different SQL statement types, or an overall total. With standard APIs, result order matches the order commands were added to the batch.

General workflow:

1. The application builds a list of parameter sets in a defined order.
2. `JdbcTemplate` uses a JDBC `PreparedStatement` to execute the batch; whether the driver actually supports batching or Spring executes them individually depends on driver capabilities.
3. JDBC reports the affected row count or a special code for each statement.
4. The application pairs `counts[i]` with the input element at index `i` for logging, business-rule checks, or aggregating statistics.

**Note:** A statement result showing successful execution does not say that the transaction has `COMMIT`ted. If the transaction later rolls back, the changes may not be persisted permanently.

## 2. Exact Meaning of the Values

`java.sql.Statement` defines the following important constants:

| Value | Interpretation | What Can Be Concluded? |
| --- | --- | --- |
| `0` | Statement processed successfully, reported row count is 0 | No rows affected per how the driver/DBMS reports results; `WHERE` may not have matched or a conditional statement made no change. |
| Positive number, e.g. `1` or `5` | Statement succeeded, affected row count reported accordingly | Can be used to sum **known** row counts. |
| `Statement.SUCCESS_NO_INFO` = `-2` | Statement **succeeded** but the driver **does not provide** the affected row count | Cannot infer 0, 1, or any specific number. |
| `Statement.EXECUTE_FAILED` = `-3` | Statement execution **failed** | Commonly seen in `getUpdateCounts()` when `BatchUpdateException` occurs and the driver continues processing remaining statements. |

Rules to remember:

- `count >= 0`: succeeded, with a reported row count.
- `count == Statement.SUCCESS_NO_INFO`: succeeded, but **row count unknown**; never add `-2` to a total.
- `count == Statement.EXECUTE_FAILED`: failed; never treat this as "success with negative rows."
- Do not rely on `count > 0` to classify success, because both `0` and `-2` can represent a successful statement.
- Do not assume "every successful update element must have `count == 1`." A statement can affect 0, 1, or more rows depending on the SQL; `-2` also makes the actual count unobservable.

**Distinguish two layers of information:** "whether the statement executed successfully or failed" and "how many rows the statement affected" are two separate questions. `SUCCESS_NO_INFO` answers the first question as **success** while leaving the second open.

## 3. Reading `int[]` via `JdbcTemplate.batchUpdate`

The following example belongs to a Spring application with the `spring-jdbc` dependency, configured `DataSource`/`JdbcTemplate`, and an existing `orders(id, status)` table in the database. Place the code in `OrderBatchRepository.java` inside a package scanned by Spring; this is a class for a Spring project, not a standalone JDK-only runnable program.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

record StatusChange(long id, String status) {}

@Repository
public class OrderBatchRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderBatchRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int[] updateStatuses(List<StatusChange> changes) {
        String sql = "UPDATE orders SET status = ? WHERE id = ?";

        return jdbcTemplate.batchUpdate(sql, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int i) throws SQLException {
                StatusChange item = changes.get(i);
                ps.setString(1, item.status());
                ps.setLong(2, item.id());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        });
    }
}
```

Meaning of key lines:

- `getBatchSize()` gives the number of elements to process; `setValues(ps, i)` binds parameters for the `i`-th element.
- The two `?` placeholders receive `status` and `id` respectively; using parameters avoids concatenating values directly into SQL.
- With one SQL statement and a list of parameter sets, the method returns `int[]`. When processing succeeds, `counts[i]` corresponds to `changes.get(i)`.
- Values in the array come from the JDBC driver; Spring **does not convert** `-2` into `1` or run `SELECT COUNT(*)` to guess row counts.
- If the update fails, the method may throw `DataAccessException`; do not build logic assuming every call returns a success array.

For example, suppose `changes` has three elements and the driver returns `{1, 0, Statement.SUCCESS_NO_INFO}`:

| Element | `counts[i]` | Proper Interpretation |
| --- | --- | --- |
| `changes.get(0)` | `1` | Executed, 1 row reported as affected. |
| `changes.get(1)` | `0` | Executed, 0 rows reported as affected; check whether business rules allow this. |
| `changes.get(2)` | `-2` | Executed successfully, row count unknown; neither 0 rows nor an error. |

## 4. Standalone Java 17+ Program to Read Each Result and Aggregate Properly

This example **runs standalone with the JDK**, intentionally simulating a count array received from JDBC to test result-reading logic without configuring a database or Spring. Save the code as `BatchCountReader.java`.

```java
import java.sql.Statement;

public final class BatchCountReader {
    public static void main(String[] args) {
        // Simulated data returned by executeBatch()/batchUpdate().
        int[] counts = {1, 0, Statement.SUCCESS_NO_INFO, 3};

        long knownRows = 0;
        int unknownSuccesses = 0;

        for (int i = 0; i < counts.length; i++) {
            int count = counts[i];

            if (count >= 0) {
                knownRows += count;
                System.out.printf("[%d] OK: %d hàng%n", i, count);
            } else if (count == Statement.SUCCESS_NO_INFO) {
                unknownSuccesses++;
                System.out.printf("[%d] OK: chưa biết số hàng%n", i);
            } else if (count == Statement.EXECUTE_FAILED) {
                System.out.printf("[%d] LỖI: phần tử batch thất bại%n", i);
            } else {
                throw new IllegalStateException("Mã count không xác định: " + count);
            }
        }

        System.out.printf(
                "Known rows: %d; unknown successes: %d%n",
                knownRows, unknownSuccesses);
    }
}
```

Compile and run in the directory containing the file (set UTF-8 encoding to preserve Vietnamese text in the source):

```bash
javac -encoding UTF-8 BatchCountReader.java
java BatchCountReader
```

Output:

```text
[0] OK: 1 hàng
[1] OK: 0 hàng
[2] OK: chưa biết số hàng
[3] OK: 3 hàng
Known rows: 4; unknown successes: 1
```

The total `knownRows = 1 + 0 + 3 = 4` is only the **sum of known counts**. In the example, one statement succeeded with an unknown row count, so **you cannot claim the actual total for the whole batch is 4**. Using `long` to sum non-negative numbers reduces overflow risk when summing many `int` results, though `long` cannot recover information missing due to `-2`.

Minimum checking pattern when processing results:

```java
if (count == Statement.SUCCESS_NO_INFO) {
    // Succeeded; row count is UNKNOWN.
} else if (count == Statement.EXECUTE_FAILED) {
    // Failed; usually read from batch exception results.
} else if (count >= 0) {
    // Succeeded; count is the row count reported by the driver.
} else {
    // Unexpected value: inspect the driver/API.
}
```

This `if` block is an **illustrative snippet** inside a loop that already has a `count` variable; by itself it is not a standalone program.

## 5. When Spring Returns `int[][]` Instead of `int[]`

Spring also provides the overload:

`JdbcTemplate.batchUpdate(String sql, Collection<T> batchArgs, int batchSize, ParameterizedPreparedStatementSetter<T> pss)`

This overload splits the input into groups of at most `batchSize` and returns **`int[][]`**: the outer array represents the groups, and the inner array holds the results for the elements in each group.

For example, the snippet below can be placed **inside a method of `OrderBatchRepository`** above, where `jdbcTemplate` and `List<StatusChange> changes` already exist:

```java
int[][] groups = jdbcTemplate.batchUpdate(
        "UPDATE orders SET status = ? WHERE id = ?",
        changes,
        200,
        (ps, change) -> {
            ps.setString(1, change.status());
            ps.setLong(2, change.id());
        });

int originalIndex = 0;
for (int group = 0; group < groups.length; group++) {
    for (int offset = 0; offset < groups[group].length; offset++) {
        int count = groups[group][offset];
        StatusChange item = changes.get(originalIndex++);
        // Match item with count, checking for -2 before summing.
    }
}
```

Suppose there are 5 elements, group size 2, and all groups complete: one possible return shape is `{{1, -2}, {0, 1}, {1}}`. Reading in original order gives `1, -2, 0, 1, 1`; never mistake `groups.length == 3` for three affected rows, or treat `groups[0][1]` as "element #1 across the entire request" in other groups.

When mapping results back to input objects, use a list with a stable order. Do not infer the number of successful elements across the whole request if the batch throws an exception mid-way.

## 6. How Does `SUCCESS_NO_INFO` Affect Business Checks?

Consider a requirement: update **exactly one** record by `id` and `version` to detect optimistic locking conflicts.

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
```

The application might define rules as follows:

- `count == 1`: driver reported exactly one row; the count condition is satisfied.
- `count == 0`: driver reported zero affected rows; the record may not exist or the version may have changed. Determine based on context.
- `count > 1`: abnormal if the key/condition design only allows one record.
- `count == SUCCESS_NO_INFO`: **insufficient evidence** to confirm "exactly one row," even though the statement was reported successful.

If business logic **strictly requires proving** each operation affected exactly one row, do not coerce `SUCCESS_NO_INFO` to `1` to pass validation. Consider updating individually to obtain proper counts, using a data-layer version-control mechanism, or performing DB verification compatible with your transaction/isolation and DBMS rules. Re-querying after an update does not automatically eliminate all concurrency issues.

Conversely, if business logic only needs to know the batch executed successfully, then `-2` is not a reason to automatically fail. Validation rules must match your goals, JDBC driver capabilities, and data consistency requirements.

## 7. Batch Exceptions and `EXECUTE_FAILED`

In raw JDBC, when a statement in `executeBatch()` fails, the driver throws `java.sql.BatchUpdateException`. There are two driver behavior styles:

1. **Stop on error:** `getUpdateCounts()` only contains results for statements that succeeded **before** the error. If 4 statements were added and the array has length 2, do **not** assume the remaining 2 statements ran and failed; they may not have been executed.
2. **Continue after error:** `getUpdateCounts()` may contain results for **all** added statements; failing positions have `Statement.EXECUTE_FAILED` (`-3`), while successful positions with unknown row counts may still be `Statement.SUCCESS_NO_INFO` (`-2`).

For example, with 3 statements, `{1, -3, -2}` in `BatchUpdateException.getUpdateCounts()` from a continue-on-error driver means: statement 0 reported 1 row, statement 1 failed, statement 2 succeeded with an unknown row count. This array does **not** mean the whole batch succeeded. Final data state still depends on transactions and rollback.

Illustrative JDBC snippet for handling exceptions (assuming `PreparedStatement ps` has been created and statements have been added via `addBatch()`):

```java
try {
    int[] counts = ps.executeBatch();
    // Only reached when executeBatch() returns normally.
} catch (java.sql.BatchUpdateException ex) {
    int[] partialCounts = ex.getUpdateCounts();
    // Check length and each code; do not assume
    // statements without results were executed.
    throw ex;
}
```

With `JdbcTemplate`, SQL errors are usually translated by Spring into an exception under `DataAccessException`; the original JDBC exception may reside in the cause chain for diagnostics. Do not rely on a single root exception subclass across all drivers, and do not swallow the exception and use a partial count array as a complete result.

In Spring, `@Transactional` on an appropriate service manages transactions; by default, runtime exceptions escaping a transactional method trigger rollback per Spring rules, though this also depends on the transaction manager, database, and operation type. A batch returning `0` or `-2` **does not trigger rollback automatically**. If the application catches an error and continues, explicitly decide whether to roll back; never assume a batch is atomic just because it was sent as a single batch.

For row counts that may exceed `Integer.MAX_VALUE`, JDBC also provides `executeLargeBatch()` returning `long[]` and `BatchUpdateException.getLargeUpdateCounts()`. The `SUCCESS_NO_INFO` and `EXECUTE_FAILED` constants retain the same meaning.

## 8. Proper Logging, Monitoring, and Testing

When recording batch metrics, separate at least four numbers:

- **Submitted statements:** size of the input list.
- **Known affected rows:** sum of `count >= 0`, excluding negative codes.
- **Statements succeeded with unknown row count:** number of elements with `count == -2`.
- **Error status:** whether a batch exception or `-3` appeared in diagnostic results, along with position and SQL state/cause when available.

Appropriate log example: `submitted=4, knownAffectedRows=4, successCountUnknown=1, failure=none`. Avoid logging `totalAffectedRows=4` when `-2` is present, because that field name asserts something the system does not know. Likewise, do not equate the number of successful **statements** with total affected **rows**.

Test cases you should include:

| Result | Expectation |
| --- | --- |
| `{1, 1, 1}` | 3 elements with definite counts, known total = 3. |
| `{1, 0, 2}` | Do not mark `0` as a JDBC error; known total = 3. |
| `{1, -2, 2}` | 1 success with unknown row count; known total = 3, actual total unknown. |
| `BatchUpdateException` with `{1, -3, -2}` | Error at element 1; do not report entire batch succeeded. |
| `BatchUpdateException` with prefix array `{1}` | Know the first statement was reported successful before the error; do not guess status of remaining statements. |

To test real behavior, use a DB/driver matching your deployment environment whenever possible: different RDBMSs and JDBC drivers can report affected rows differently in cases like updating to the same value, `UPSERT`, `ON CONFLICT DO NOTHING`, batch rewrite settings, or whether the driver returns concrete counts vs. `-2`. Testing on mock arrays verifies **decoding logic**; integration tests verify **how the driver reports results**.

## 9. Common Misconceptions

**"Is `-2` an error?"** No. `Statement.SUCCESS_NO_INFO` means success without a row count; batch errors are signaled by exceptions and in some cases by `EXECUTE_FAILED`.

**"Does `{1, -2, 1}` prove two rows were updated?"** Only two counts are known to be 1, while the middle count is unknown. The known sum is 2; the total for the whole batch is unknown.

**"Does `count == 0` always mean the operation did not execute?"** No. A statement can execute and report 0 affected rows; understand the SQL condition and how the driver/DBMS determines affected rows.

**"Can all elements be summed with `IntStream.sum()`?"** Not when `-2` or `-3` may appear. Only sum non-negative counts and track unknown and failed counts separately.

**"After catching `BatchUpdateException`, can you immediately retry everything?"** Not by default. Some statements may already have executed; transaction state and idempotency of statements dictate recovery. Handle transactions, rollbacks, and retries deliberately.

## 10. Takeaways and Reference Docs

When receiving batch results, **pair elements in order**, **check JDBC constants before aggregating**, and **keep "row count unknown" as a distinct state**. `SUCCESS_NO_INFO` means *success*, but row count *no info*. If a problem requires confirming "exact one row," treat this result as **insufficient evidence** rather than forcing it to `1`.

Official documentation for reference:

- JDBC `Statement.executeBatch()` and constants: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- JDBC `BatchUpdateException.getUpdateCounts()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html
- Spring Framework, *JDBC Batch Operations*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `JdbcTemplate.batchUpdate(...)` JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html