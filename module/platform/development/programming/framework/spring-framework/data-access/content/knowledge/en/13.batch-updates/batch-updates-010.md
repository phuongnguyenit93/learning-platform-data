# Verifying Batch Benefits with a Real JDBC Driver

> **Context:** Spring Framework Data Access → Batch Updates. The focus is on **measuring and verifying** the benefit of batching against a real database and JDBC driver, rather than assuming calling `batchUpdate()` is faster under all conditions.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish command grouping at the Spring/JDBC layer from actual optimizations in the driver and database server.
2. Design a fair benchmark comparing row-by-row `executeUpdate()`, grouped `executeBatch()`, and batching with driver optimization options enabled.
3. Run a repeatable experiment on **real PostgreSQL + pgJDBC**, verify data after each run, measure total duration including `COMMIT`, and calculate throughput/speedup.
4. Map the findings back to a `JdbcTemplate.batchUpdate(...)` flow in Spring and explain when batching helps and when it does not.
5. Identify measurement skews, batch size limits, transaction impact, data constraints, and row-count reporting returned by JDBC.

## 2. What Does Batching Actually Optimize?

With the same parameterized SQL statement, two ways of sending data differ:

- **Row-by-row:** prepare one `PreparedStatement`, bind parameters, and call `executeUpdate()` N times.
- **JDBC batch:** bind parameters, call `addBatch()` N times, and send in groups via `executeBatch()`. Spring's `JdbcTemplate.batchUpdate()` builds on this capability.
- **Driver rewrite:** some drivers recognize batched `INSERT ... VALUES (?, ?)` and rewrite them into fewer larger `INSERT ... VALUES (...), (...), ...` statements. This is an optimization **dependent on the driver, configuration, and SQL shape**; batching does not automatically mean a single SQL statement.

Flow to observe:

```text
Application / Spring JDBC
       │
       ├─ 10,000 update() / executeUpdate() calls
       │         or
       └─ multiple addBatch() → grouped executeBatch()
                         ↓
                   JDBC driver
                   (with/without rewrite)
                         ↓
                   Network protocol
                         ↓
                 Real PostgreSQL
                 (parse/plan/execute/WAL/index/commit)
```

Batching generally reduces statement invocation and DB communication overhead; the driver may group or pipeline commands, so **never infer exact round-trip counts solely from API call counts**. If time is dominated by constraint checks, indexes, triggers, I/O, locks, or WAL, the gain may be small. Overly large batches can also increase memory, transaction hold duration, and error-handling cost. The goal of this lesson is to **measure on your exact driver/workload** before deciding.

## 3. Designing a Controlled Benchmark

Use a **10,000-row INSERT** workload with identical structure, one table, and the same primary key; all records are generated **before starting the timer**. Measure three main configurations:

| Scenario | Application Call Style | pgJDBC `reWriteBatchedInserts` | Meaning |
| --- | --- | --- | --- |
| A | Row-by-row `PreparedStatement.executeUpdate()` | `false` | Baseline reusing a prepared statement |
| B | `addBatch()/executeBatch()`, 500 rows/group | `false` | JDBC batch effectiveness without rewrite |
| C | Same as B, 500 rows/group | `true` | Additional benefit when pgJDBC can rewrite INSERTs |

Compare A and B **in the same run with the flag set to `false`**; compare B and C across two runs identical except for the driver flag. You can also measure A in the `true` run to confirm the baseline remains stable. The comparison must satisfy these conditions:

- **Same PostgreSQL version, pgJDBC, JVM, table schema, indexes, data, row count, SQL, host, network, and thread count.** Record versions; a localhost result does not represent a DB over a high-latency network.
- **Same transaction scope:** both write paths use `autoCommit=false`, with one `COMMIT` per workload. Never compare 10,000 auto-commit calls against one batch with one commit and claim the difference is solely due to batching.
- Both paths use **one connection** and reuse **one `PreparedStatement`** for the workload; measured time includes statement creation/closing and `COMMIT`, but excludes data setup, `TRUNCATE`, or verification queries.
- Include **warm-up** rounds, multiple measured rounds, alternate A/B order, and use the **median** rather than picking the fastest run. Ensure no other tasks are loading the DB.
- After **each** round, verify row count, key sum, and payload values; data errors or exceptions must fail the benchmark run instead of being recorded as fast.
- Record `batchSize`, driver flags, and payload size separately. Do not equate this single-threaded benchmark with full-application throughput when many concurrent requests write to the DB.

Formulas:

```text
elapsed_ms   = (endNano - startNano) / 1_000_000
throughput   = verified rows / (elapsed_ms / 1_000)
speedup      = median_ms(baseline) / median_ms(candidate)
```

`speedup > 1` indicates the candidate is faster than the baseline under the experiment conditions; `speedup < 1` indicates slower. This is an **environment-specific measurement**, not a guaranteed property of `batchUpdate()`.

## 4. Runnable Experiment: PostgreSQL + pgJDBC + Java 17+

### 4.1. Starting a Real Database

Requirements: JDK 17+, Docker, a file download tool, and a PostgreSQL JDBC driver. The example uses PostgreSQL 16 in a local container; port `54329` avoids colliding with a developer machine's port 5432.

```bash
docker run --rm -d --name pg-batch-lab \
  -e POSTGRES_DB=batch_lab \
  -e POSTGRES_USER=lab \
  -e POSTGRES_PASSWORD=labpass \
  -p 54329:5432 postgres:16

docker exec pg-batch-lab pg_isready -U lab -d batch_lab
```

Only run the benchmark when `pg_isready` reports accepting connections. If not using Docker, point the JDBC URL to an isolated test PostgreSQL instance with permissions to create tables and `TRUNCATE`; **never run this against production data**.

In a dedicated practice directory, download a verified pgJDBC release from Maven Central:

```bash
curl -L -o postgresql-42.7.7.jar https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar
```

The Java code below only requires `java.sql` at compile time. The pgJDBC JAR must be on the **runtime classpath** so `DriverManager` can locate the driver.

### 4.2. Complete Benchmark Program

Save as `BatchProbe.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class BatchProbe {
    private static final int ROWS = 10_000;
    private static final int CHUNK = 500;
    private static final int WARMUPS = 2;
    private static final int ROUNDS = 8;

    private static final String INSERT =
            "INSERT INTO batch_probe(id, payload) VALUES (?, ?)";

    record Item(int id, String payload) {}

    private static List<Item> createItems() {
        List<Item> items = new ArrayList<>(ROWS);
        for (int id = 1; id <= ROWS; id++) {
            items.add(new Item(id, "item-" + id));
        }
        return items;
    }

    private static void createTable(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE IF NOT EXISTS batch_probe (
                    id INTEGER PRIMARY KEY,
                    payload VARCHAR(100) NOT NULL
                )
                """);
        }
        connection.commit();
    }

    private static void resetTable(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("TRUNCATE TABLE batch_probe");
        }
        connection.commit();
    }

    private static void checkCounts(int[] counts, int expected)
            throws SQLException {
        if (counts.length != expected) {
            throw new SQLException("Wrong batch count length: " + counts.length);
        }
        for (int count : counts) {
            // Rewritten INSERT may report SUCCESS_NO_INFO (-2).
            if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                throw new SQLException("Unexpected batch update count: " + count);
            }
        }
    }

    private static void verifyRows(Connection connection, int size)
            throws SQLException {
        String sql = """
            SELECT COUNT(*),
                   COALESCE(SUM(id), 0),
                   COUNT(*) FILTER (WHERE payload <> 'item-' || id)
            FROM batch_probe
            """;
        try (Statement statement = connection.createStatement();
             ResultSet resultSet = statement.executeQuery(sql)) {
            if (!resultSet.next()) {
                throw new SQLException("No aggregate result");
            }
            long count = resultSet.getLong(1);
            long sumIds = resultSet.getLong(2);
            long mismatchedPayload = resultSet.getLong(3);
            long expectedSum = (long) size * (size + 1) / 2;
            if (count != size || sumIds != expectedSum
                    || mismatchedPayload != 0) {
                throw new SQLException("Data verification failed: count="
                        + count + ", sumIds=" + sumIds
                        + ", badPayload=" + mismatchedPayload);
            }
        }
        connection.commit();
    }

    private static long run(Connection connection, List<Item> items,
                            boolean batched) throws SQLException {
        // Reset has its own commit; excluded from insert timing.
        resetTable(connection);
        long started = System.nanoTime();
        try (PreparedStatement statement =
                     connection.prepareStatement(INSERT)) {
            int pending = 0;
            for (Item item : items) {
                statement.setInt(1, item.id());
                statement.setString(2, item.payload());

                if (batched) {
                    statement.addBatch();
                    pending++;
                    if (pending == CHUNK) {
                        checkCounts(statement.executeBatch(), pending);
                        pending = 0;
                    }
                } else {
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Single insert affected != 1");
                    }
                }
            }
            if (batched && pending > 0) {
                checkCounts(statement.executeBatch(), pending);
            }
            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        }
        long elapsed = System.nanoTime() - started;
        verifyRows(connection, items.size()); // Excluded from timing.
        return elapsed;
    }

    private static double median(List<Long> nanos) {
        List<Long> sorted = new ArrayList<>(nanos);
        Collections.sort(sorted);
        int middle = sorted.size() / 2;
        return sorted.size() % 2 == 0
                ? (sorted.get(middle - 1) + sorted.get(middle)) / 2.0
                : sorted.get(middle);
    }

    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "DB_URL", "jdbc:postgresql://localhost:54329/batch_lab");
        String user = System.getenv().getOrDefault("DB_USER", "lab");
        String password = System.getenv().getOrDefault(
                "DB_PASSWORD", "labpass");

        List<Item> items = createItems(); // Before timing.
        List<Long> singles = new ArrayList<>();
        List<Long> batches = new ArrayList<>();

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            connection.setAutoCommit(false);
            System.out.println("Driver: "
                    + connection.getMetaData().getDriverName() + " "
                    + connection.getMetaData().getDriverVersion());
            if (!connection.getMetaData().supportsBatchUpdates()) {
                throw new IllegalStateException("Driver has no JDBC batch support");
            }

            createTable(connection);

            for (int round = 0; round < WARMUPS + ROUNDS; round++) {
                boolean batchFirst = round % 2 == 0;
                long first = run(connection, items, batchFirst);
                long second = run(connection, items, !batchFirst);

                if (round >= WARMUPS) {
                    if (batchFirst) {
                        batches.add(first);
                        singles.add(second);
                    } else {
                        singles.add(first);
                        batches.add(second);
                    }
                }
            }
        }

        double singleMs = median(singles) / 1_000_000.0;
        double batchMs = median(batches) / 1_000_000.0;
        System.out.printf(Locale.ROOT,
                "single median: %.2f ms%n", singleMs);
        System.out.printf(Locale.ROOT,
                "batch  median: %.2f ms%n", batchMs);
        System.out.printf(Locale.ROOT,
                "single throughput: %.0f rows/s%n", ROWS * 1_000.0 / singleMs);
        System.out.printf(Locale.ROOT,
                "batch  throughput: %.0f rows/s%n", ROWS * 1_000.0 / batchMs);
        System.out.printf(Locale.ROOT,
                "batch speedup: %.2fx%n", singleMs / batchMs);
    }
}
```

**Why is this code fairer than a naive comparison?** Both branches reuse `PreparedStatement`, run one transaction for 10,000 inserts, use the same data, and perform the same `COMMIT`. Each round clears the table before measuring to avoid primary-key collisions. The program verifies committed data, including payload values, **before accepting the timing**. Each A/B pair alternates execution order; the median is taken from eight measured rounds after two warm-up rounds. Constants `ROWS`, `CHUNK`, `WARMUPS`, and `ROUNDS` can be adjusted to explore other cases.

Compile and run commands in **PowerShell/Windows** (use `;` in the Java classpath):

```powershell
javac --release 17 BatchProbe.java

$env:DB_USER = 'lab'
$env:DB_PASSWORD = 'labpass'

# A vs B: JDBC batch, rewrite disabled
$env:DB_URL = 'jdbc:postgresql://localhost:54329/batch_lab?reWriteBatchedInserts=false'
java -cp '.;postgresql-42.7.7.jar' BatchProbe

# Re-measure with same data, same program: C
$env:DB_URL = 'jdbc:postgresql://localhost:54329/batch_lab?reWriteBatchedInserts=true'
java -cp '.;postgresql-42.7.7.jar' BatchProbe
```

On Linux/macOS, the classpath separator is `:` instead of `;`, and environment variables can be exported with `export`. The file name and class name `BatchProbe` must match. The `Driver: ...` line proves the program actually uses pgJDBC rather than an embedded driver like H2. The `single median`, `batch median`, `throughput`, and `speedup` lines are **actual measurements of your run**, with no fixed timing stdout to copy. This example is a benchmark illustrating the technique and measurement methodology; for production-scale evaluation, you must also measure on representative infrastructure and data.

Clean up the test environment when finished:

```bash
docker stop pg-batch-lab
```

### 4.3. Interpreting Results Across Three Tiers

1. If **B is faster than A**, JDBC/driver batching helps this workload even without rewrite.
2. If **C is faster than B**, `reWriteBatchedInserts=true` adds further benefit for compatible `INSERT` shapes. Do not attribute C's entire gain to Spring: the benchmark above uses plain JDBC.
3. If **there is no clear difference**, examine network latency, I/O/WAL limits, indexes/triggers, DB CPU, buffer/cache state, concurrent load, per-record size, and whether the driver can actually optimize that SQL shape. Repeat runs and check variance rather than declaring batching useless from one run.

In pgJDBC, `reWriteBatchedInserts` defaults to `false`; this option can rewrite **compatible INSERT VALUES** into multi-values INSERTs. It is **not a general rewrite mechanism for UPDATE/DELETE** and has exceptions such as `RETURNING`/generated-key retrieval. When rewrite is enabled, `executeBatch()` may return `Statement.SUCCESS_NO_INFO` (`-2`) instead of an exact row count per element. **Never add negative numbers into the total written row count**; verify results separately in the DB.

## 5. Bringing Measurements Back to Spring `JdbcTemplate`

The JDBC-layer exercise verifies driver behavior; Spring applications typically call `JdbcTemplate`. Measure a Spring pass as well to understand **end-to-end effectiveness in real code**. In an application that already has `spring-jdbc` and a PostgreSQL `DataSource`, the class below offers two write paths for the same data and transaction. This class compiles inside a Spring project; table setup and benchmarking harness follow Section 4 and are kept out of this class.

```java
import java.sql.Statement;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringBatchWriter {
    public record Item(int id, String payload) {}

    private static final String INSERT =
            "INSERT INTO batch_probe(id, payload) VALUES (?, ?)";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public SpringBatchWriter(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.transaction = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
    }

    public void writeSeparately(List<Item> items) {
        transaction.executeWithoutResult(status -> {
            for (Item item : items) {
                jdbc.update(INSERT, item.id(), item.payload());
            }
        });
    }

    public void writeInBatches(List<Item> items) {
        transaction.executeWithoutResult(status -> {
            int[][] counts = jdbc.batchUpdate(
                    INSERT,
                    items,
                    500,
                    (ps, item) -> {
                        ps.setInt(1, item.id());
                        ps.setString(2, item.payload());
                    });
            for (int[] oneBatch : counts) {
                for (int count : oneBatch) {
                    if (count == Statement.EXECUTE_FAILED) {
                        throw new IllegalStateException(
                                "A JDBC batch entry failed");
                    }
                }
            }
        });
    }
}
```

**Mechanism:** the overload `JdbcTemplate.batchUpdate(sql, Collection<T>, int batchSize, ParameterizedPreparedStatementSetter<T>)` automatically splits the list into batches of at most 500 elements and returns `int[][]` (one update-count array per group). The variant `batchUpdate(sql, BatchPreparedStatementSetter)` returns `int[]` and is typically used when controlling element counts manually. Spring may **fall back to individual updates** if the driver reports no JDBC batch support; merely seeing the Spring API invoked is **not enough** to conclude the network/DB receives an optimized batch.

`TransactionTemplate` in both branches ensures one transaction commits when the callback succeeds and rolls back when a runtime exception is thrown. If using `@Transactional` instead, invoke through a Spring proxy; self-invocation within the same bean can bypass the transaction interceptor. Never benchmark one branch inside a Spring transaction against another branch using per-row auto-commit.

When benchmarking these two methods, initialize/start the `ApplicationContext`, `DataSource`, pool, and data **before** the timed window; invoke from an external caller; reset the table and verify data after each round. Comparing `writeSeparately` with `writeInBatches` **measures effectiveness at the Spring layer**, distinct from the raw JDBC comparison in Section 4 (Spring adds statement-creation, parameter-mapping, and abstraction overhead).

If using `NamedParameterJdbcTemplate.batchUpdate()`, each row takes a `SqlParameterSource`, such as `SqlParameterSourceUtils.createBatch(items.toArray())`; you still need to verify driver and transaction behavior. For `null` parameters, pass explicit JDBC types when the driver needs them, because `ParameterMetaData` lookups can add round trips; Spring 6.1.2+ includes specific optimizations for PostgreSQL and MS SQL Server on this path.

## 6. Gathering Evidence at the Driver and DB Layers

`supportsBatchUpdates() == true` only proves the driver advertises **JDBC batch support**, not that INSERTs are merged into one SQL statement. Combine multiple observation layers:

| Layer | Appropriate Observation | What Can Be Concluded |
| --- | --- | --- |
| Application | Median wall-clock, throughput, verification results, errors/rollbacks | Benefit seen from the caller's perspective |
| JDBC | Driver version, URL/flags, `supportsBatchUpdates()`, `updateCounts` | Which driver is running, its support, and batch outcomes |
| PostgreSQL | Query statistics, server-side call counts/latency, locks/WAL/I/O, slow query log in test environment | Whether server load dropped / SQL shape changed, or cost shifted elsewhere |
| Network (when permitted) | Protocol trace or proxy observing message counts, bytes, and timing | Protocol-level evidence; avoid inferring solely from Java logs |

If the `pg_stat_statements` extension is enabled in your test environment, compare normalized SQL, `calls`, and `total_exec_time` before and after. With rewrite enabled, the same logical INSERT can appear under **multiple VALUES-tuple counts**, so **do not inspect only a single statistics row**. Measuring `pg_stat_statements` requires appropriate DB permissions and configuration; it is not mandatory for the self-contained benchmark in Section 4.

With MySQL Connector/J, the corresponding option is `rewriteBatchedStatements=true`, though its activation conditions and behavior **differ from pgJDBC**. Do not apply PostgreSQL flag names to MySQL/MariaDB/Oracle/SQL Server, and do not assume the same SQL is rewritten across all drivers. Verify version, driver documentation, metrics, and actual SQL received on each DBMS.

## 7. Experimenting with Batch Size Changes

Hold N and transaction behavior constant while varying `CHUNK` sequentially, for example **1, 50, 100, 500, 1,000, 5,000**. Batch size 1 is a useful boundary test; larger sizes are not necessarily faster. After changing `CHUNK`, re-run full warm-up/measurement rounds, verify data, and record median and throughput for **each** level.

Effects to interpret:

- Small groups: more `executeBatch()` calls, higher iteration overhead, but less queued parameter/memory footprint.
- Moderate groups: usually balance overhead and memory cost; look for the plateau of diminishing returns.
- Overly large groups: increase client memory, packet/command size, lock duration, timeout risk, and error-handling complexity. pgJDBC also has protocol parameter limits when constructing multi-values INSERTs; the driver decides valid rewrite groups internally.
- Batches mixing heterogeneous SQL shapes or requiring per-row result retrieval can disable driver optimizations.
- For large workloads, design **chunk + transaction boundaries** according to atomicity requirements; committing per chunk changes failure semantics, so it must be measured and documented separately rather than mixed into a single-transaction comparison table.

Never choose batch size solely from benchmarks on a developer laptop. Payload size, indexes, network, concurrent connections, and application SLOs can all shift the optimal point.

## 8. Correctness and Error Handling

Batching does not relax data-integrity requirements:

1. **Update counts:** JDBC uses `Statement.SUCCESS_NO_INFO = -2` on success with unknown row count; `Statement.EXECUTE_FAILED = -3` indicates failure at that position if the driver continues processing. Counts do not replace data-verification queries.
2. **BatchUpdateException:** when one item fails (e.g., duplicate key), the driver may stop or continue remaining items depending on DB/driver. `getUpdateCounts()` is only a clue about what was attempted; decide full-transaction rollback or retry/idempotency strategy before deployment.
3. **Transactions:** in the example, one failing item rolls back the entire round. If code catches the exception and still commits, partial state may persist; never use benchmarks to justify compromising atomicity.
4. **Constraints and triggers:** verify row counts, column contents, duplicate handling, and ordering effects if the workload is order-sensitive; do not assume `INSERT ... ON CONFLICT` or generated keys return identical results under rewrite.
5. **Resources:** for very large inputs, do not hold unbounded elements in RAM. Process in finite chunks; monitor heap, connection pool, timeouts, open transactions, and DB response.
6. **Repeatability:** table data must be reset before each round; changing indexes/constraints, hardware, network, driver, pool size, or isolation level creates a **new** experiment.

A measurement succeeds only when it satisfies **correct data + repeatable timing + configuration description** simultaneously. A program that finishes fast while missing records, or measures only `addBatch()` without `executeBatch()/COMMIT`, is an invalid result.

## 9. Diagnosing When "Batching Is Not Faster"

| Symptom | Hypothesis to Test | Check |
| --- | --- | --- |
| A and B are nearly identical | DB is on the same machine; execution/index cost dominates; driver gives minimal gain | Measure against a test DB over a network with representative latency; inspect DB CPU/WAL and throughput |
| B improves, C adds little | SQL structure ineligible for rewrite; batch is bottlenecked by I/O/constraints | Confirm exact URL and pgJDBC; test simple INSERT VALUES like the demo; check SQL stats |
| C is faster but update counts contain `-2` | Rewrite drops exact per-entry row counts | Use `COUNT`/data verification; handle `SUCCESS_NO_INFO` properly |
| Larger batch size gets slower | Statement/heap size, locks, DB cost, too many parameters | Sweep multiple batch sizes and monitor resources |
| First round slow, later rounds fast | JIT, connection warm-up, buffers/cache, statement/DB initialization | Use warm-ups, repeat runs, alternate order, report median |
| Spring loop very slow while JDBC loop is not | Spring loop has statement-creation, binding, or connection-acquisition overhead; inconsistent transaction/pool | Benchmark raw JDBC and Spring loop separately, ensuring identical connection/transaction setup |
| Duplicate key or missing rows | Table not reset properly, duplicate input data, wrong transaction/retry | Roll back and verify `COUNT`, checksum/content, and log root causes |

## 10. Completion Criteria and Self-Practice

A verifiable benchmark report must specify: actual DB and driver with versions; SQL/schema/indexes; row count and payload; `autoCommit` and commit count; measurement type and timing boundaries; `batchSize`, rewrite flags; warm-up and measured round counts; median, throughput, speedup; data verification outcome; and environment-conditioned conclusions.

Practice in order: (1) run A/B with rewrite `false`, (2) run B/C with rewrite `true`, (3) vary `CHUNK` to 50, 100, 1,000, (4) add a secondary index or change payload size and **re-measure**, (5) deliberately insert a duplicate key to observe rollback/exception, then (6) reproduce both write approaches using `SpringBatchWriter`. Adjust only one variable per change so you understand why results changed.

**Engineering conclusion from data:** batching is a conditional overhead-reduction strategy; final gains depend on **calling code, transactions, driver, SQL shape, DB configuration, and workload**. Optimize only when measurements on the real driver prove improvement while data remains correct.

## References

- Spring Framework, *JDBC Batch Operations*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- pgJDBC, *Initializing the Driver* (`reWriteBatchedInserts` parameter): https://jdbc.postgresql.org/documentation/use/
- pgJDBC, *Batch INSERT rewriting* (rewrite conditions and `updateCounts`): https://vlsi.github.io/pgjdbc/documentation/query/batch-inserts/
- Java SE, `Statement.executeBatch()`, `SUCCESS_NO_INFO`, `EXECUTE_FAILED`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html
- MySQL Connector/J, *Configuration Properties*: https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html
