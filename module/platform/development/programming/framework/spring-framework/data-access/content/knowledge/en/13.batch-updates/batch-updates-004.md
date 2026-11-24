# Splitting Data into Small Chunks to Bound Memory During Batch Updates

> **Context:** Spring Framework – Data Access, topic **Batch Updates**. The goal is to update many records using JDBC batching while keeping only a bounded amount of input data in application memory.

## 1. Why Is Chunking Needed?

Suppose you must update the names of 2 million customers. If you load all 2 million objects into a `List` before calling `JdbcTemplate.batchUpdate(...)`, heap memory can grow proportionally to the total record count. Each object also brings strings, arrays, and object overhead; the JDBC driver may also buffer parameters. With large datasets, this risks prolonged GC pauses or `OutOfMemoryError`.

**Chunking** processes at most `batchSize` elements at a time: fetch a small group from the source → send the same parameterized SQL to JDBC batch → release references to that group → fetch the next group. For example, `N = 2,001` records with `batchSize = 500` becomes 5 chunks: `500 + 500 + 500 + 500 + 1`.

Important distinctions:

- **JDBC batching** groups multiple executions of the *same* `PreparedStatement` to reduce network round trips and SQL invocation overhead. It is primarily a performance technique.
- **Input chunking** limits how many objects are held simultaneously in the application. This is what directly caps heap usage when the data source is read sequentially.
- **Transactions** determine commit/rollback scope; finishing a JDBC batch **does not mean** committing a transaction.
- **`fetchSize`** is a hint for how many rows to fetch per query round trip (driver-dependent), whereas **`batchSize`** here is the number of write operations grouped into one batch. Do not confuse the two parameters.

With a truly streamed data source, the application buffer needs roughly `O(B × S)` memory, where `B` is the number of elements per chunk and `S` is the average size of one element. If you load the entire source into a `List` first, memory remains `O(N × S)` even if you invoke JDBC batch with a small `B`. This formula only describes the application-level data buffer, excluding other JVM memory, driver buffers, return results, or database resources.

## 2. Choosing the Right Spring JDBC API

Spring Framework provides several options:

| API | How It Works | Memory Considerations |
| --- | --- | --- |
| `JdbcTemplate.batchUpdate(sql, BatchPreparedStatementSetter)` | `getBatchSize()` reports the number of parameter bindings in the current call; `setValues(...)` populates each parameter set. | If passed a huge list, that list is still retained; call it per small chunk. |
| `JdbcTemplate.batchUpdate(sql, Collection<T>, batchSize, ParameterizedPreparedStatementSetter<T>)` | Spring splits the **passed collection** into JDBC batches and returns `int[][]`. | `batchSize` does not turn a preloaded collection into a streaming source. To cap heap, only pass a small collection fetched incrementally from the source. |
| `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` | Uses named parameters, one array element per parameter set. | Create `SqlParameterSource[]` **per chunk**; avoid creating an array for the entire dataset. |

The section below uses `JdbcTemplate` with `Collection<T>` and `ParameterizedPreparedStatementSetter<T>`. The SQL is parameterized with `?` placeholders rather than concatenating data into SQL strings. Drivers with good batch support generally reduce round trips, though speedup depends on the driver, configuration, and database; some drivers may execute sequentially instead of optimizing into true batching.

## 3. Runnable Example: Reading Incrementally, Holding at Most 3 Elements

The example uses **Java 17, Spring JDBC 6.2, and H2** so it runs standalone easily. The data source is an `Iterator` generating records on demand; the application does not build a list of all records before updating.

Create the structure:

```text
spring-jdbc-chunks/
├── pom.xml
└── src/main/java/ChunkedBatchDemo.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-jdbc-chunks</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <version>2.5.252</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ChunkedBatchDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/ChunkedBatchDemo.java`**

```java
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class ChunkedBatchDemo {
    private static final String SQL =
            "UPDATE customer SET full_name = ? WHERE id = ?";

    record NameChange(long id, String newName) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:chunks;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE customer (" +
                "id BIGINT PRIMARY KEY, full_name VARCHAR(100) NOT NULL)");

        for (long id = 1; id <= 7; id++) {
            jdbc.update(
                    "INSERT INTO customer (id, full_name) VALUES (?, ?)",
                    id, "old-" + id);
        }

        // Source creates one element on demand; does not hold a 7-element List.
        Iterator<NameChange> source = new Iterator<>() {
            private long nextId = 1;

            @Override
            public boolean hasNext() {
                return nextId <= 7;
            }

            @Override
            public NameChange next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                long id = nextId++;
                return new NameChange(id, "new-" + id);
            }
        };

        int successfulStatements = updateInChunks(jdbc, source, 3);
        Integer renamedRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customer " +
                "WHERE full_name LIKE 'new-%'",
                Integer.class);

        System.out.println("Successful statements: " + successfulStatements);
        System.out.println("Rows now renamed: " + renamedRows);
    }

    static int updateInChunks(JdbcTemplate jdbc,
                              Iterator<NameChange> source,
                              int batchSize) {
        if (batchSize <= 0) {
            throw new IllegalArgumentException("batchSize must be > 0");
        }

        List<NameChange> buffer = new ArrayList<>(batchSize);
        int successfulStatements = 0;

        while (source.hasNext()) {
            buffer.add(source.next());

            if (buffer.size() == batchSize) {
                successfulStatements += executeChunk(jdbc, buffer);
                buffer.clear();
            }
        }

        // Do not forget the final batch when record count is not divisible.
        if (!buffer.isEmpty()) {
            successfulStatements += executeChunk(jdbc, buffer);
            buffer.clear();
        }

        return successfulStatements;
    }

    static int executeChunk(JdbcTemplate jdbc, List<NameChange> chunk) {
        int[][] counts = jdbc.batchUpdate(
                SQL,
                chunk,
                chunk.size(),
                (ps, change) -> {
                    ps.setString(1, change.newName());
                    ps.setLong(2, change.id());
                });

        int accepted = 0;
        for (int[] oneBatch : counts) {
            for (int count : oneBatch) {
                if (count == Statement.EXECUTE_FAILED) {
                    throw new IllegalStateException("Batch entry failed");
                }
                if (count >= 0 || count == Statement.SUCCESS_NO_INFO) {
                    accepted++;
                } else {
                    throw new IllegalStateException(
                            "Unexpected JDBC update count: " + count);
                }
            }
        }

        System.out.println("Chunk size: " + chunk.size());
        return accepted;
    }
}
```

Run in the directory containing `pom.xml` (requires JDK 17+ and Maven):

```bash
mvn -q compile exec:java
```

Expected output with H2:

```text
Chunk size: 3
Chunk size: 3
Chunk size: 1
Successful statements: 7
Rows now renamed: 7
```

**Flow explanation:**

1. `source.next()` produces one `NameChange` per call; in the example, no giant input `List` exists.
2. `buffer` grows from 0 up to 3 elements. Once it reaches 3, `executeChunk` runs the row-update SQL as a JDBC batch.
3. After the command succeeds, `buffer.clear()` drops references to the processed chunk's objects. The JVM can reclaim memory during GC; there is no need and no reason to force `System.gc()`.
4. The first two chunks have 3 elements, and the last has 1 element. Checking `!buffer.isEmpty()` ensures the final chunk is not missed.
5. `int[][]` stores batch results for the **current call**, rather than accumulating results for millions of statements. In the example, each call holds only one small chunk.

JDBC update count values must be understood correctly: a non-negative number is the affected row count reported by the driver; `Statement.SUCCESS_NO_INFO` (`-2`) means the statement succeeded with an **unknown row count**, and `Statement.EXECUTE_FAILED` (`-3`) indicates failure. Hence the example counts **accepted statements** rather than inferring that each statement necessarily updated one row. `Rows now renamed: 7` is a direct verification query on the H2 table.

> **Example limitation:** `DriverManagerDataSource` and in-memory H2 are suited for demonstration. Real applications typically use a connection-pooled `DataSource` and an `Iterator` backed by a file, queue, or properly lifecycle-managed data reader. The `Iterator` here is a simulated source; simply turning `hugeList.iterator()` into an `Iterator` will **not** remove `hugeList` from memory.

## 4. Only Reading the Source Properly Truly Bounds the Heap

**Pattern that fails the goal:**

```java
// Anti-pattern illustration, not a standalone program.
List<NameChange> all = loadMillionsOfRowsIntoList();
jdbc.batchUpdate(SQL, all, 500, (ps, row) -> {
    ps.setString(1, row.newName());
    ps.setLong(2, row.id());
});
```

Spring may split the JDBC work into batches of 500 statements, but `all` still holds the entire dataset. Switching to a loop using `all.subList(from, to)` does not free the original list either: `subList` is only a view backed by the original list.

**Proper pattern:** the source must supply data incrementally, such as reading file lines or querying small pages; place at most `B` elements into `buffer`; process and clear references before reading further. Real-world sources:

- **Large files:** read sequentially with `BufferedReader`/`Files.lines(...)` and close resources with `try-with-resources`; parse only enough data for one chunk.
- **Database source:** keyset pagination on a stable key (such as `WHERE id > :lastId ORDER BY id LIMIT :pageSize` if the database supports this syntax) or a cursor/streaming `ResultSet` once you understand how the driver handles `fetchSize`, transactions, and connections. Do not call `queryForList` to fetch millions of rows at once.
- **Message/queue:** pull only a reasonable number of messages, send the batch, record processing status, and then fetch more. You must decide how to handle received messages when a batch fails.

If the same operation both streams a `ResultSet` from a database and updates that database, evaluate connections, isolation, cursors, and consistency; do not assume you can keep a long-lived cursor open and execute all UPDATEs on that exact connection without affecting the read source. For large datasets needing restartability, keyset pagination with checkpoints is usually easier to control.

## 5. Chunks Do Not Automatically Create Transaction Boundaries

There are two distinct business requirements:

| Transaction Style | Meaning | Trade-off |
| --- | --- | --- |
| **One transaction covering all chunks** | If an error and rollback occur, the entire update run rolls back together (subject to transaction/database). | Transaction can run long, hold locks/connections, and increase undo/redo log pressure. A small buffer heap does not solve those resources. |
| **One transaction per chunk** | A successful chunk can commit before moving to the next. Locks and rollback scope are usually smaller. | If the 5th chunk fails, the previous four may already have committed. Requires checkpoints, retries, and duplicate-write prevention. |

For example in Spring, `TransactionTemplate` can wrap **each `executeChunk` call** in a transaction when there is no outer transaction:

```java
// Illustrative snippet placed in an app that already has dataSource, jdbc, and chunk.
TransactionTemplate tx = new TransactionTemplate(
        new DataSourceTransactionManager(dataSource));

tx.executeWithoutResult(status -> {
    executeChunk(jdbc, chunk);
});
```

Corresponding imports: `org.springframework.transaction.support.TransactionTemplate` and `org.springframework.jdbc.datasource.DataSourceTransactionManager`. The snippet above **is not a standalone program**; it shows that transaction boundaries must be configured deliberately. By default `TransactionTemplate` uses `REQUIRED` propagation: if an outer transaction already exists, it joins that transaction and does **not** commit per chunk. Similarly, putting `@Transactional` on the entire method running the loop typically creates *one* transaction for all chunks when invoked via a Spring proxy. Do not confuse one `batchUpdate` call with one commit.

Which approach to pick depends on **atomicity** requirements. For restartable tasks, key-based updates and idempotent operations (re-running does not corrupt state) generally support per-chunk recovery. For instance, `SET status = 'DONE' WHERE id = ?` is easier to re-run than `SET balance = balance + ?` if there is no protection against double application.

## 6. Error Handling, Counting, and Retries

- **Do not swallow exceptions:** `JdbcTemplate` translates JDBC errors into `DataAccessException`; when a batch fails, the driver/database may already have executed part of the statements. Do not automatically assume the whole chunk had no effect.
- **Control commits:** with per-chunk transactions, record checkpoints only after a successful commit. Store the last processed key or job/batch ID durably. If the system stops abruptly, resume from the checkpoint and ensure operations are safe to re-run.
- **Understand returned counts:** `0` may mean no matching rows; `SUCCESS_NO_INFO` cannot be summed as updated row count. If business logic must know the exact row count, verify via SQL conditions, target data, or an appropriate audit mechanism.
- **Handling transient errors:** retry at chunk or transaction boundaries with backoff for appropriate errors; control unique keys, processing order, and idempotency. Do not blindly retry every error (such as invalid SQL syntax or data constraint violations).
- **Stop on error:** the runnable example above throws an exception and stops at the failing chunk; it does not `clear()` and continue unconditionally. In production, design job reporting, failed-chunk tracking, and a clear recovery strategy.

## 7. Choosing `batchSize` Based on Measurement

There is no universal optimal value. You can **start testing** around `100–500` records/chunk for small UPDATE statements, then measure and adjust; this is only an empirical starting point, not a Spring limit. A row containing large BLOBs may need a much smaller chunk.

Monitor concurrently:

1. **Heap and GC:** peak heap, allocation rate, GC duration; are `List`, parameter arrays, or results retained longer than one chunk?
2. **Throughput:** rows/second or statements/second, time per chunk, round trips, and JDBC batch effectiveness in the driver.
3. **Database:** lock hold duration, transaction/undo log, transaction length, deadlocks, packet/bind-parameter limits, or DBMS statement timeouts.
4. **Operational resilience:** overly large chunks make rollbacks/retries more expensive; overly small chunks create many calls and can increase commit overhead.
5. **Object size:** row count does not directly reflect byte size; 500 lightweight objects are very different from 500 objects carrying large binary payloads.

A useful experiment is to fix the dataset and SQL, run sequentially with `B = 100`, `B = 500`, `B = 1000`, and record throughput, peak heap, and latency; pick the level that stays stable with the real database. If reading from a file or cursor, measure read speed separately to avoid confusing data-source bottlenecks with update bottlenecks.

## 8. Common Implementation Mistakes and Checks

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Loading all records before splitting into batches | Heap grows with `N` | Fetch data incrementally and keep buffer ≤ `B`. |
| Calling one massive batch | Driver/DB may buffer many parameters, long transaction | Call batch in finite chunks. |
| Forgetting the final chunk | Data loss when `N % B != 0` | After the loop, process if buffer is not empty. |
| Not validating `batchSize <= 0` | Broken loop or confusing API errors | Validate inputs at the start of the method. |
| Assuming each chunk auto-commits | Misunderstood atomicity, hard rollback design | Define transaction boundaries explicitly. |
| Adding `-2` into updated row counts | Negative or wrong statistics | Distinguish succeeded statements from affected row counts. |
| Retrying after partial commit without keys/checkpoints | Duplicate writes or double-crediting balances | Design idempotency and durable checkpoints. |
| Using `subList` on a giant `List` and dropping the view | Original list is still retained | Read incrementally from the source; avoid building the large original list. |

**Minimum test suite:** empty source (`N=0`); exactly one element; `N=B`; `N=B+1` to catch remainder-chunk bugs; data with non-existent `id` (`update count=0`); `batchSize=0` and negative values; SQL or constraint error in a middle chunk; re-running an already committed chunk. In real environments, monitor heap and target table state, not just `batchUpdate` call counts.

## 9. Spring Framework Adoption Checklist

- [ ] Data source supplies records sequentially or in small pages; the entire dataset is never held in heap.
- [ ] `batchSize > 0` is chosen and at most `batchSize` objects are kept in the buffer.
- [ ] Parameterized `PreparedStatement` is used; all batch elements share the same SQL template.
- [ ] The final chunk is fully executed and references are cleared after each successful chunk.
- [ ] It is clearly decided whether one transaction wraps the whole run or commits per chunk.
- [ ] `DataAccessException`, special update count values, and controlled retries are handled.
- [ ] Heap, GC, throughput, and database load are measured at realistic data scale.

**Takeaway:** a small `batchSize` only bounds memory **when the entire data pipeline is chunked**: read → hold in buffer → batch update → drop references. If the source already loaded everything into a `List`, splitting batches at the JDBC layer organizes SQL statements but does not reclaim the memory used to load the data.

### References

- Spring Framework 6.2 – JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html
- Spring Framework – Programmatic Transaction Management (`TransactionTemplate`): https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Java SE – `java.sql.Statement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
