# BatchPreparedStatementSetter and Batch Size in Spring JDBC

## 1. Goal and Context

When you need to insert or update hundreds or thousands of records using the **same SQL statement with different parameters**, calling `JdbcTemplate.update(...)` row by row can create many round trips to the database. JDBC batching groups parameter sets together so the driver has the opportunity to optimize execution and reduce back-and-forth overhead between the application and the database.

`BatchPreparedStatementSetter` is a Spring JDBC callback used with:

```java
int[] counts = jdbcTemplate.batchUpdate(sql, batchPreparedStatementSetter);
```

It determines the **parameter values for each element** and the **number of elements in a single batch call**. This lesson focuses on implementing those two methods, controlling batch size, reading results, and choosing appropriate configurations. This is JDBC batching, distinct from the Spring Batch project dedicated to job orchestration.

After this lesson, you will be able to:
- Write `BatchPreparedStatementSetter` with the right indices and data types.
- Distinguish total record count from the size of an execution batch.
- Split large datasets into multiple batches, including a smaller final batch.
- Understand the meaning of the `int[]` returned by `batchUpdate` and handle errors/transactions properly.
- Measure and tune batch size based on real metrics.

## 2. Contract of BatchPreparedStatementSetter

The interface lives in `org.springframework.jdbc.core.BatchPreparedStatementSetter` and has exactly two methods:

```java
public interface BatchPreparedStatementSetter {
    void setValues(PreparedStatement ps, int i) throws SQLException;
    int getBatchSize();
}
```

- `getBatchSize()` returns the **number of parameter sets bound in the current batch**. For a list of 75 items passed in one call, it usually returns 75. This value is **not a setting that automatically splits a large list into chunks**.
- `setValues(ps, i)` is called to bind parameters for the `i`-th element; `i` starts at **0**. Conversely, `?` positions in a JDBC `PreparedStatement` start at **1**: `ps.setLong(1, ...)` is the first parameter.
- A single `batchUpdate(sql, pss)` call reuses the **same SQL with `?` placeholders**. Each `setValues` call must populate all parameters corresponding to that SQL; do not concatenate user data directly into the SQL string.
- `SQLException` inside the callback is handled by `JdbcTemplate` and translated into the appropriate `DataAccessException` hierarchy. There is no need to swallow exceptions inside `setValues`.

Conceptual flow:

```text
Data list → getBatchSize()
          → setValues(ps, 0), setValues(ps, 1), ...
          → JDBC addBatch / executeBatch
          → int[] updateCounts
```

The JDBC driver decides the actual level of optimization. Per the API contract, if the driver does not support batching, `JdbcTemplate` may execute individual updates on the same `PreparedStatement`; therefore, batching is not guaranteed to always be faster.

## 3. Runnable Java 17+ Example: Splitting 5 Records into Batches of 2

A standalone example using Spring JDBC and in-memory H2, requiring neither Spring Boot nor a database server. Structure:

```text
spring-jdbc-batch-demo/
├── pom.xml
└── src/main/java/demo/BatchDemo.java
```

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jdbc-batch-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.21</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BatchDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/BatchDemo.java`**:

```java
package demo;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

public class BatchDemo {

    record Item(long id, String sku, int stock) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
            CREATE TABLE inventory (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(32) NOT NULL,
                stock INT NOT NULL
            )
            """);

        List<Item> items = List.of(
            new Item(1L, "A-01", 10),
            new Item(2L, "A-02", 20),
            new Item(3L, "B-01", 30),
            new Item(4L, "B-02", 40),
            new Item(5L, "C-01", 50)
        );

        int batchSize = 2;
        int batchNumber = 0;
        String sql = "INSERT INTO inventory (id, sku, stock) VALUES (?, ?, ?)";

        for (int from = 0; from < items.size(); from += batchSize) {
            List<Item> chunk = items.subList(
                from, Math.min(from + batchSize, items.size())
            );

            int[] counts = jdbc.batchUpdate(sql, new BatchPreparedStatementSetter() {
                @Override
                public void setValues(PreparedStatement ps, int i)
                        throws SQLException {
                    Item item = chunk.get(i);
                    ps.setLong(1, item.id());
                    ps.setString(2, item.sku());
                    ps.setInt(3, item.stock());
                }

                @Override
                public int getBatchSize() {
                    return chunk.size();
                }
            });

            System.out.println("Batch " + (++batchNumber)
                + ": " + Arrays.toString(counts));
        }

        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM inventory", Integer.class
        );
        System.out.println("Total rows: " + total);
    }
}
```

Run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Output with the declared H2 database:

```text
Batch 1: [1, 1]
Batch 2: [1, 1]
Batch 3: [1]
Total rows: 5
```

Step-by-step explanation:

1. The SQL has three `?` placeholders, so `setValues` puts `id` at position 1, `sku` at position 2, and `stock` at position 3.
2. The outer loop creates three groups of sizes 2, 2, and 1. `getBatchSize()` returns the **actual length of `chunk`**, so the final batch does not access past the end of the list.
3. In each batch, `i` starts from 0 again; `chunk.get(i)` maps accurately to the record in that batch.
4. Each `INSERT` in the H2 example affects one row, so the count arrays are `[1, 1]` or `[1]`. Other drivers/databases may return special codes instead of specific row counts.

This pattern illustrates limiting the **number of elements sent in each JDBC batch call**. Because `items` is already loaded completely into memory, it does not yet solve reading millions of input rows; that case requires paged reading, a cursor, or a bounded-buffer stream.

## 4. Distinguishing Batch Size from Total Record Count

Calling `jdbc.batchUpdate(sql, pss)` once with `getBatchSize() = 50_000` means one batch with 50,000 parameter sets; **it does not automatically split into 100 batches of 500 records**. To limit each batch to 500, you must split the input dataset or use a batch API that takes a batch size parameter.

With `N` elements and target size `B > 0`:

- Number of batches = `ceil(N / B)`.
- Earlier batches usually have `B` elements.
- The last batch has `N % B` elements if the remainder is non-zero.
- For example, `N = 1,205`, `B = 500` → three batches: `500 + 500 + 205`.
- `N = 0` → no elements to write; can return an empty result immediately.

In code, avoid writing `getBatchSize() { return 500; }` when the actual list only has 205 elements. The returned value must match the index range that `setValues` can access.

If you have a `List<Item>`, Spring JDBC also provides an overload that manages batch splitting:

```java
int batchSize = 500;
int[][] countsByBatch = jdbc.batchUpdate(
    "INSERT INTO inventory (id, sku, stock) VALUES (?, ?, ?)",
    items,
    batchSize,
    (PreparedStatement ps, Item item) -> {
        ps.setLong(1, item.id());
        ps.setString(2, item.sku());
        ps.setInt(3, item.stock());
    }
);
```

This is `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)`, distinct from the overload taking `BatchPreparedStatementSetter` in the main example. With this overload, the framework splits the list by `batchSize` and returns `int[][]`: the outer array is per batch, and the inner array is per element. Only use the snippet above **inside a method that already has `jdbc` and `items`**; it is a supplementary API example, not a standalone Java program.

## 5. Reading Update Counts Accurately

With `batchUpdate(String, BatchPreparedStatementSetter)`, the return type is `int[]`. Each element corresponds to one operation in the batch, but **it is not always a positive number**.

| Value | Meaning |
|---|---|
| `n >= 0` | Number of affected rows reported by the driver; `0` can happen with an `UPDATE` that finds no matching record. |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Operation succeeded, but the driver does not provide a specific row count. |
| `Statement.EXECUTE_FAILED` (`-3`) | Driver reports the operation failed in the batch result; in many cases it throws `BatchUpdateException` instead of returning normally. |

Do not blindly sum all elements of `counts` to conclude the "total rows written": `-2` is not minus two rows and `-3` is not minus three rows. If business logic needs to know which records succeeded, combine counts with JDBC errors, business keys, and reconciliation queries; do not infer that the whole batch is atomic solely from `int[]`.

Example of inspecting results when no exception occurs:

```java
for (int count : counts) {
    if (count == java.sql.Statement.SUCCESS_NO_INFO) {
        // Succeeded, but row count is unknown.
    } else if (count == java.sql.Statement.EXECUTE_FAILED) {
        // Error needs investigation according to driver and transaction state.
    } else if (count == 0) {
        // Possibly an UPDATE that matched no rows.
    } else {
        // count > 0: number of affected rows provided by the driver.
    }
}
```

Normally `JdbcTemplate` translates SQL errors into `DataAccessException`. When part of a batch fails, the database/driver may already have executed earlier elements; whether those changes are rolled back depends on the **transaction enclosing the work**.

## 6. What Batch Size Is Reasonable?

There is no fixed number that fits every system. Numbers like 100, 500, or 1,000 are only **starting points for measurement**, not mandatory defaults for `BatchPreparedStatementSetter`.

| Batch size | Potential benefits | Potential trade-offs |
|---|---|---|
| Too small, e.g. 1–10 | Less data waiting per batch, easier error isolation | Many driver calls and round trips; throughput may be low |
| Moderate, e.g. 100–1,000 | Often balances call overhead and per-batch data volume | Must be measured against actual SQL, driver, and database |
| Very large, e.g. 10,000+ | Fewer `executeBatch` calls | High memory/buffer usage, long resource holds, hard error handling, may hit driver/database limits |

Factors that determine the best choice in practice:

1. **Size of each record:** 500 rows with a few numeric columns are completely different from 500 rows containing long strings or binary data.
2. **Driver and database:** JDBC batch support, SQL rewriting behavior, parameter/packet limits, network latency, and driver version make a significant difference.
3. **SQL statement:** a simple `INSERT` differs from an `UPDATE` with conditions, triggers, foreign key checks, indexes, and unique constraints.
4. **Transactions and contention:** large batches can increase lock hold times or transaction duration, impacting other requests.
5. **Resources:** heap, connection pool, timeouts, transaction logs, I/O, CPU, and packet size can all become bottlenecks.
6. **Business requirements:** tolerance for partial writes, retryability, reconciliation needs, and idempotency.

How to measure properly:

- Create a dataset resembling production data, with the same indexes and insert/update ratio; you can try levels like `100 → 500 → 1,000` after measuring a baseline.
- Measure **throughput** (records/second), total duration, per-batch latency and p95, database call count, CPU/heap, lock waits, timeouts, and error rate.
- Repeat runs after proper warm-up; verify the written data, not just the Java loop execution time.
- Choose the smallest size that achieves target throughput while meeting memory, latency, lock-duration, and error-recovery requirements. Do not assume "bigger batch is always faster."

Sometimes a driver has options to accelerate batching (such as rewriting multiple inserts into multi-row syntax). Check the documentation for the **exact driver version** and re-benchmark because both performance and counts can change.

## 7. Transactions, Mid-Batch Errors, and Retries

**Batching does not mean transactions.** Batching describes how SQL operations are grouped; transactions determine commit/rollback scope.

- If batches run inside **one** Spring transaction (for example, a service method invoked through a `@Transactional` proxy with an appropriate transaction manager), unchecked errors like `DataAccessException` normally trigger a rollback of the whole transaction by default.
- If there is **no enclosing transaction** or each chunk is committed explicitly, previously executed/committed batches may persist when a later batch fails. The extent of commits also depends on auto-commit settings and the driver.
- Splitting 10,000 records into 20 `batchUpdate` calls **does not automatically create 20 transactions**. To have per-chunk transactions, define separate boundaries, such as using `TransactionTemplate` per chunk.
- Very long transactions enable all-or-nothing rollback but can increase lock duration, log growth, and timeout risk; per-chunk transactions reduce failure blast radius but require handling partial completion state.

A safe retry policy must answer: "If the previous batch committed but the application did not receive the response, will writing the same data again create duplicate records?" Consider business unique keys, idempotent operations, `UPSERT`/`ON CONFLICT` for the target DBMS, checkpoints, and reconciliation before retrying. Do not automatically retry all data without knowing commit state.

If row-level error diagnosis is needed, you can inspect the underlying JDBC `BatchUpdateException` and `getUpdateCounts()`, but error codes and ability to identify failing rows depend on the driver; do not use them as proof of whether a transaction committed.

## 8. Common Mistakes

**Index off-by-one:** list index `i` starts at 0, whereas `PreparedStatement` starts at 1. `ps.setString(0, ...)` is invalid.

**Wrong fixed size:** returning `100` in `getBatchSize()` even when the last batch only has 17 elements causes out-of-bounds access or wrong parameter binding. Always use `chunk.size()` when processing chunks.

**Missing/extra parameters:** if SQL has `?, ?, ?`, each `setValues` must bind all three positions with the right types. When values are nullable, use `ps.setNull(index, java.sql.Types.VARCHAR)` or an appropriate setter; do not concatenate strings manually to represent `NULL`.

**Misunderstanding batching efficiency:** a huge list with `getBatchSize() = items.size()` has no memory bound. To process massive data, read input in chunks and call `batchUpdate` multiple times.

**Ignoring negative results:** `SUCCESS_NO_INFO` means success with unknown row count, not failure. Do not sum the count array without handling special codes.

**Assuming automatic rollback:** Spring JDBC only executes statements and translates exceptions; rollback depends on the configured transaction. Verify actual transaction setup before designing retries.

**Optimizing with "magic" numbers:** picking 1,000 because it sounds faster than 100 without measuring record size, driver, SQL, locks, and completion time often degrades throughput or stability.

## 9. Project Application Checklist

1. Confirm records share a single SQL template with `?` placeholders and parameter binding covers all data types.
2. Define a positive batch size limit; handle empty lists and the final batch with the exact element count.
3. Choose `BatchPreparedStatementSetter` when you need control over index-based binding; choose the overload with `ParameterizedPreparedStatementSetter` when you want Spring to split a `Collection` by `batchSize`.
4. Review constraints, indexes, duplicate-key behavior, and update rules.
5. Design transaction scope, rollback, and retry strategy before running on critical data.
6. Verify `counts`, exceptions, database row counts, and metrics using test data.
7. Benchmark multiple batch sizes on the real driver/database, then lock in the proven configuration.

## 10. Self-Check Questions

1. With 1,205 records and batch size 500, how many batches are there and how many elements are in the last batch? **Answer:** three batches, of sizes 500, 500, and 205.
2. Does `getBatchSize() = 500` make `JdbcTemplate` automatically split a 20,000-record list into 40 calls? **No.** The `BatchPreparedStatementSetter` overload only processes the number of elements provided by the callback in one call. You must split manually or choose the overload with a batch size parameter.
3. Why must `setValues(ps, 0)` still call `ps.setLong(1, id)`? Because element index `i` and `PreparedStatement` parameter index use two different conventions: 0-based and 1-based.
4. What does `counts = [1, -2, 0]` mean? One operation affected one row, one succeeded with unknown row count, and one had a count of 0; you cannot sum them into a reliable written-row count.
5. Does splitting into 20 batches guarantee each batch commits independently? **No.** Commit scope is determined by transactions/auto-commit.

## References

- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Javadoc — `BatchPreparedStatementSetter`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/BatchPreparedStatementSetter.html
- Javadoc — `JdbcOperations.batchUpdate`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
