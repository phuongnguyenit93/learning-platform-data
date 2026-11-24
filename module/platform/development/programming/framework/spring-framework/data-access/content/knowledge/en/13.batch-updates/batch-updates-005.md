# ParameterizedPreparedStatementSetter and Handling the Final Batch in Spring JDBC

When an application needs to execute many `INSERT`, `UPDATE`, or `DELETE` statements with the **same SQL structure** but different parameters, `JdbcTemplate` supports grouping operations into multiple batches. `ParameterizedPreparedStatementSetter<T>` maps each Java object to the `?` placeholders of a `PreparedStatement`; Spring handles splitting into batches and executing them, including a **final batch with fewer elements than `batchSize`**.

This lesson focuses on the overload:

```java
<T> int[][] batchUpdate(
    String sql,
    Collection<T> batchArgs,
    int batchSize,
    ParameterizedPreparedStatementSetter<T> pss
)
```

This is an API of `org.springframework.jdbc.core.JdbcTemplate` (declared via `JdbcOperations`).

## 1. When to Use This Overload?

Suppose there are 1,005 records to write to the `inventory` table, all using the SQL:

```sql
INSERT INTO inventory (id, sku, quantity) VALUES (?, ?, ?)
```

Calling `jdbcTemplate.update(...)` 1,005 times can incur many database round trips. With batching, the JDBC driver has an opportunity to group statements to reduce communication cost. If you choose `batchSize = 200`, Spring splits the data into six batches: five full batches of 200 records and a final batch of 5 records.

This overload is appropriate when:

- You already have a `Collection<T>` containing the objects to process, such as `List<Product>` or `List<OrderLine>`.
- All elements share one SQL statement with fixed `?` placeholder positions.
- You want to limit the number of elements per batch without writing `addBatch()`/`executeBatch()` loops yourself.
- You want clear parameter mapping code, able to use `setLong`, `setString`, `setNull`, `setTimestamp`, and appropriate JDBC setters.

**Distinction:** `batchSize` is the **maximum number of operations in one JDBC batch**, not a guaranteed number of updated rows, not the number of transactions, and not the number of parallel threads.

## 2. Role of Each Parameter and Callback

| Component | Meaning | What to Remember |
| --- | --- | --- |
| `sql` | SQL statement reused for every element | Number/positions of `?` must match `ps.setXxx(...)` calls. |
| `batchArgs` | Input dataset of type `Collection<T>` | Each object corresponds to one callback invocation. |
| `batchSize` | Limit on elements grouped in one batch | Must be a positive integer; validate `batchSize > 0` at application input. |
| `pss` | Callback `ParameterizedPreparedStatementSetter<T>` | Receives `PreparedStatement` and **the current object `T` itself** to bind parameters. |
| Result `int[][]` | Update counts per batch | Outer array corresponds to batches; inner array holds results for each operation in the batch. |

Functional interface:

```java
@FunctionalInterface
public interface ParameterizedPreparedStatementSetter<T> {
    void setValues(PreparedStatement ps, T argument) throws SQLException;
}
```

Example mapping three fields:

```java
(ps, item) -> {
    ps.setLong(1, item.id());
    ps.setString(2, item.sku());
    ps.setInt(3, item.quantity());
}
```

JDBC parameter positions start at **1**. The callback is invoked for each `item`, unlike `BatchPreparedStatementSetter.setValues(PreparedStatement ps, int i)` which receives the **element index**. Do not call `ps.addBatch()`, `ps.executeBatch()`, `ps.clearBatch()`, `ps.close()`, or `commit()` inside this callback: `JdbcTemplate` manages those operations. The callback is only responsible for **binding all parameters for one element**; do not rely on bound values left over from the previous element.

## 3. Batch-Splitting Mechanism and the Final Batch

Suppose `batchArgs` has `n = 5` elements and `batchSize = 2`:

```text
Input:         A  B  C  D  E
Batch 1:      [A  B]          -> executeBatch()
Batch 2:            [C  D]    -> executeBatch()
Final batch:              [E] -> executeBatch()
Size:          2      2    1
```

According to the batch-splitting logic when the driver supports JDBC batching:

1. Spring iterates over each object in `batchArgs` in the collection's iteration order.
2. For each object, Spring invokes `pss.setValues(ps, object)` and adds the operation to the batch.
3. When `batchSize` is reached, Spring executes the batch and stores a group of update counts.
4. When **input data ends**, if leftover elements remain that do not fill a batch, Spring **still executes the final batch** and appends its result group to `int[][]`.
5. The method returns after processing the entire collection, or throws an exception if an error occurs.

There is no need to pad dummy elements to fill the final batch, nor to call `flush` manually.

With a driver supporting JDBC batching and no errors, the number of batches is `ceil(n / batchSize)` when `n > 0`. The final batch has size `n % batchSize` if there is a remainder; if evenly divisible, the final batch also has `batchSize` elements, with **no extra empty batch**.

| Elements `n` | `batchSize` | Batches | Batch Sizes |
| ---: | ---: | ---: | --- |
| 0 | 2 | 0 | `[]` |
| 1 | 2 | 1 | `[1]` |
| 5 | 2 | 3 | `[2, 2, 1]` |
| 6 | 3 | 2 | `[3, 3]` |
| 7 | 3 | 3 | `[3, 3, 1]` |

**Important condition:** This shape describes the normal batch execution path. If the JDBC driver reports that it does not support batching, `JdbcTemplate` may execute individual updates; do not assume the exact result-group shape across every driver. Always test with your real driver and database.

## 4. Runnable Example with Java 17+, Spring JDBC, and H2

The following example inserts 5 products with `batchSize = 2`, reads the results, and verifies all 5 rows. `TransactionTemplate` is used so the inserts run in **one transaction**.

Create the structure:

```text
batch-demo/
├── build.gradle
└── src/main/java/BatchUpdateDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.19'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'BatchUpdateDemo'
}
```

Contents of `src/main/java/BatchUpdateDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class BatchUpdateDemo {

    record Stock(long id, String sku, int quantity) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:batch_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
            CREATE TABLE stock (
                id BIGINT PRIMARY KEY,
                sku VARCHAR(30) NOT NULL,
                quantity INT NOT NULL
            )
            """);

        List<Stock> items = List.of(
            new Stock(1L, "A", 10),
            new Stock(2L, "B", 20),
            new Stock(3L, "C", 30),
            new Stock(4L, "D", 40),
            new Stock(5L, "E", 50)
        );

        int batchSize = 2;
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be positive");
        }

        TransactionTemplate transaction = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        int[][] counts = transaction.execute(status ->
            jdbc.batchUpdate(
                "INSERT INTO stock (id, sku, quantity) VALUES (?, ?, ?)",
                items,
                batchSize,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.sku());
                    ps.setInt(3, item.quantity());
                }
            )
        );

        int[] sizes = Arrays.stream(counts).mapToInt(batch -> batch.length).toArray();
        System.out.println("Batch sizes: " + Arrays.toString(sizes));
        System.out.println("Update counts: " + Arrays.deepToString(counts));

        Integer total = jdbc.queryForObject(
            "SELECT COUNT(*) FROM stock", Integer.class
        );
        System.out.println("Rows in table: " + total);
    }
}
```

In the `batch-demo` directory, run with Gradle (you can use `./gradlew run` if the project already has a wrapper):

```bash
gradle run
```

With H2 and the sample data, **the lines printed by the program** are:

```text
Batch sizes: [2, 2, 1]
Update counts: [[1, 1], [1, 1], [1]]
Rows in table: 5
```

Gradle may print its own build logs as well. The fifth record is in the **one-element** final batch and is still inserted; `SELECT COUNT(*)` returns 5. H2 reports one affected row per successful `INSERT`, so all update counts in the example are `1`.

### Reading Key Lines

- `List<Stock> items` is the input `Collection<Stock>`; no need to convert to `List<Object[]>`.
- `jdbc.batchUpdate(..., items, 2, (ps, item) -> ...)` iterates over each `Stock` and binds three `?` placeholders.
- `Arrays.stream(counts).mapToInt(batch -> batch.length)` shows the **number of elements per batch**.
- `Arrays.deepToString(counts)` displays both dimensions of `int[][]`; `Arrays.toString(counts)` does not print nested array values as desired.
- `TransactionTemplate` shares the same `DataSource` as `JdbcTemplate`; Spring manages the connection in the transaction. The batch boundaries `[2, 2, 1]` **do not automatically create three transactions**.

This is a minimal console app to observe the mechanism. In Spring Boot, you normally inject `JdbcTemplate` and use `@Transactional` on a service method invoked through a Spring proxy, instead of manually creating `DriverManagerDataSource`/`TransactionTemplate` in `main`.

## 5. Understanding `int[][]` and Update Counts Properly

Suppose a batch consists of `UPDATE inventory SET quantity = ? WHERE id = ?` statements:

- `1`: the statement affected one row.
- `0`: no row matched the condition, or a situation reported by the driver as zero affected rows; do not automatically treat it as a technical error.
- Positive value greater than 1: the statement affected multiple rows.
- `Statement.SUCCESS_NO_INFO` (`-2`): the statement succeeded, but the driver did not supply a specific row count.
- `Statement.EXECUTE_FAILED` (`-3`): failure indicator per JDBC convention; when a batch fails, the driver usually throws `BatchUpdateException` and Spring translates it to `DataAccessException`. Do not assume the method always returns a full array containing `-3`.

For example, `[[1, 1], [1, 0], [1]]` shows three batches totaling five operations; the fourth operation updated no rows. **Do not use `counts.length` as the number of affected rows**, because that is the number of batch groups along the batch execution path.

When aggregating, sum only **non-negative** update counts. If `SUCCESS_NO_INFO` appears, you cannot compute an exact row total by summing update counts; reconcile the written data afterwards if business logic requires an exact count. Do not silently add `-2` to the total or treat every `-2` result as a failure.

## 6. Transactions, Mid-Way Errors, and the Final Batch

**Splitting into batches does not mean splitting transactions.** Three cases must be distinguished:

1. **A transaction wraps the entire call:** if an element or the final batch causes an error and the exception propagates out of `TransactionTemplate` or an appropriate `@Transactional` method, the transaction is rolled back per Spring rules. With transaction-capable databases/engines, earlier changes in the same transaction are also undone.
2. **No enclosing transaction:** the connection may be in auto-commit mode; an earlier successful batch may already have committed before a later batch fails. Never assume the entire operation is always "all-or-nothing."
3. **Driver throws during `executeBatch()`:** how much executed before the error, update counts, and whether the batch continued depend on the driver. Inspect the cause, `BatchUpdateException`, contextual logs, and DB state rather than guessing which elements committed from array length alone.

For example, modify the input data so two elements have a duplicate primary key (`id = 3`). The second insert for the same key violates the `PRIMARY KEY` constraint; if the error occurs inside the example's transaction and is not swallowed, Spring rolls back the earlier inserts. When the application catches the exception to report it, catch it **outside** `TransactionTemplate`. Catching and ignoring the error **inside** the transaction callback and returning normally can inadvertently commit the transaction without handling rollback state.

When retry after failure is needed, design **idempotent** operations (e.g., unique business keys and an upsert policy suited to the DB), define transaction boundaries, and verify actual state. Blindly retrying all data can cause duplicates, wrong counts, or unintended side effects.

## 7. Edge Cases and Common Mistakes

### Empty Input or Smaller Than `batchSize`

If `items.isEmpty()`, no SQL operations need to run; the typical result is an empty outer array. If there is 1 element with `batchSize=100`, that single element is the final batch and is still processed. If `n` is divisible by `batchSize`, no trailing empty batch is created.

### Invalid `batchSize`

Use `batchSize > 0`. With `0` or a negative number, batch splitting makes no sense; reject invalid inputs before calling the API instead of relying on implementation exceptions. Overly large values are not automatically faster either: they can increase driver memory used to buffer parameters or exceed DB/driver limits.

### Binding `null` and SQL Types

Do not carelessly call `ps.setString(2, null)` if the driver or schema needs an explicit SQL type. For example, if `sku` is nullable (`NULL` allowed):

```java
if (item.sku() == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, item.sku());
}
```

Adjust according to the actual column. Do not leave parameters bound from the previous object when encountering `null` on the current object; always bind every position. Use `?` placeholders for **data values**, and never concatenate input strings into SQL to build values. Table/column names cannot be replaced with `?`; validate them separately if dynamic.

### Driver Capabilities

Actual batching and detailed update counts are determined by the driver; both efficiency and the returned group shape can differ when JDBC batching is unsupported. Run integration tests against the **production driver/DB**, especially if relying on `SUCCESS_NO_INFO`, timeouts, mid-batch errors, or update ordering.

### Do Not Let a Large `Collection` Overflow Memory

`batchSize=500` only chunks **operations sent to JDBC**; it does not automatically paginate data from a source. If `batchArgs` contains millions of objects already loaded in a `List`, the data still occupies application memory. For very large datasets, read in pages/chunks at the business layer, call `batchUpdate` per chunk, and deliberately decide transaction scope. Splitting across multiple chunks can change atomicity, so design commit/retry/checkpoint behavior clearly.

### Do Not Confuse Batch APIs

| API | Input/Callback | Result | Key Difference |
| --- | --- | --- | --- |
| `batchUpdate(sql, BatchPreparedStatementSetter)` | `setValues(ps, i)` + `getBatchSize()` | `int[]` | Usually for one batch; callback retrieves elements by index. |
| `batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` | `setValues(ps, item)` | `int[][]` | Spring splits the collection into multiple batches and **automatically executes a partial final batch**. |
| `InterruptibleBatchPreparedStatementSetter` | Index-based callback that can signal end of data | `int[]` with the matching setter overload | Used when signaling early completion in the `BatchPreparedStatementSetter` mechanism. |
| `NamedParameterJdbcTemplate.batchUpdate(...)` | Named parameters, e.g. `:sku`, source `SqlParameterSource[]` | `int[]` | Different binding style; does not use this lesson's `ParameterizedPreparedStatementSetter<T>` callback. |

Do not manually add `executeBatch()` for the final batch as in raw JDBC; with this overload, Spring already handles it.

## 8. How to Test Final-Batch Behavior Properly

To verify your code and avoid dropping data, test at least these cases:

1. `n = 0` and `batchSize = 2`: no data written.
2. `n = 1` and `batchSize = 2`: 1 row written, final batch has 1 element.
3. `n = 5` and `batchSize = 2`: 3 batches of sizes `[2, 2, 1]`, DB stores all 5 rows.
4. `n = 6` and `batchSize = 3`: 2 full batches `[3, 3]`, no extra empty batch.
5. One element has a wrong type/key violation: observe exception and rollback when inside a transaction, and re-check the DB.
6. With an `UPDATE` statement where one ID does not exist: observe update count `0` without mistaking it for an SQL error.

In standalone H2 tests, you can assert the exact `int[][]` shape as in the example. When testing across drivers or on a production DB, **database state and transaction guarantees** are the primary business criteria; update counts may include `SUCCESS_NO_INFO` and are insufficient to prove exact row counts.

**Self-check question:** With 1,001 elements, `batchSize=250`, a batch-capable driver, and all statements succeeding: how many batches will there be and how many elements in the final batch?

**Answer:** There are `ceil(1001/250)=5` batches; the first four batches have 250 elements each, and the final batch has **1 element**. If you previously wrote a manual loop that only called `executeBatch()` every 250 items, you would drop the final element; Spring's overload handles the remainder automatically.

## 9. Takeaways

- `ParameterizedPreparedStatementSetter<T>` binds **each object `T`** into a `PreparedStatement` sharing one SQL template.
- `JdbcTemplate.batchUpdate(sql, collection, batchSize, pss)` splits data into multiple batches and returns `int[][]`; **a final batch smaller than `batchSize` is still executed**.
- `batchSize` is a batch boundary, **not** a transaction boundary; use `TransactionTemplate` or `@Transactional` appropriately to control atomicity.
- Understand `0`, `SUCCESS_NO_INFO`, and batch errors before aggregating results; verify actual DB data after writes when accuracy matters.
- Bind all parameters properly, handle `null`/SQL types, validate `batchSize > 0`, and test partial final batches.

### References

- Spring Framework Reference — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework `JdbcOperations` Javadoc, `batchUpdate` overload taking `Collection<T>`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- Java 17 API — `java.sql.Statement` (update count constants): https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
