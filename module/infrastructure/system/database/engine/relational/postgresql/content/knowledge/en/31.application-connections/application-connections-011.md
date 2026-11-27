# JDBC Batching, Fetch Size, Cursors, and Reading Large Results in PostgreSQL

Java applications connecting to PostgreSQL frequently face two very different performance scenarios:

- **Writing many records**: importing tens of thousands of orders, syncing statuses from another service, or executing many `UPDATE` statements. Sending each statement individually can incur huge network round-trip and execution overhead.
- **Reading very large results**: exporting 500,000 report rows or scanning large event tables. If the driver buffers all rows into the Java heap, the application may suffer GC pressure, run out of memory, or hold connections too long.

JDBC provides distinct mechanisms for these two needs:

| Problem | Tool | Purpose |
| --- | --- | --- |
| Multiple parameter sets for the same SQL | `PreparedStatement.addBatch()`, `executeBatch()` | Reduce bulk write overhead |
| Transaction spanning multiple operations | `setAutoCommit(false)`, `commit()`, `rollback()` | Control atomicity |
| Iterating through a large `ResultSet` | `setFetchSize(n)` | Tune how many rows the driver fetches per batch |
| Retaining traversal state on the server | Cursor/portal | Fetch subsequent chunks incrementally |
| Fetching independent pages | Keyset pagination | Avoid deep `OFFSET` and long-held transactions |
| Dedicated bulk loading | `COPY` and pgJDBC Copy API | Stream large datasets efficiently |

**Write batching differs from fetch batching.** `executeBatch()` processes multiple commands or parameter sets. `setFetchSize()` applies to retrieving rows from **a single `SELECT` result**.

~~~mermaid
flowchart TD
    A["Java Application"] --> Q{"Workload Type?"}
    Q -->|"Bulk writes"| W["PreparedStatement.addBatch"]
    W --> WX["executeBatch"]
    WX --> T["COMMIT / ROLLBACK"]
    Q -->|"Reading a large SELECT"| F["setFetchSize(n)"]
    F --> C["Forward-only ResultSet, transaction"]
    C --> S["pgJDBC cursor/portal"]
    S --> R["Process row-by-row without holding full result"]
    Q -->|"Independent pages"| K["Keyset + LIMIT"]
    K --> P["Checkpoint and resume"]
~~~

This lesson belongs to the **Application Connections** chapter of the **Relational Database Engine — PostgreSQL** module. All examples use a dedicated lab database and Java/JDBC with a pgJDBC version compatible with your environment.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish between batch `INSERT`/`UPDATE`, fetch size, and SQL cursors.
2. Write a `PreparedStatement` using `addBatch`, `executeBatch`, and transactions.
3. Understand `BatchUpdateException`, update counts, SQLSTATE errors, and rollbacks.
4. Choose batch sizes separately from transaction chunks based on the business contract.
5. Know the benefits and limitations of `reWriteBatchedInserts` in pgJDBC.
6. Use `ON CONFLICT` and idempotency keys to handle retries safely.
7. Compare JDBC batching with PostgreSQL `COPY`.
8. Explain why `ResultSet.next()` alone does not guarantee streaming memory usage.
9. Use `setFetchSize` under pgJDBC's requirements: `autoCommit=false`, forward-only, positive fetchSize, and compatible query/protocol.
10. Manage the lifecycles of `ResultSet`, `Statement`, `Connection`, and transactions.
11. Distinguish driver-managed cursors from SQL `DECLARE`/`FETCH`/`CLOSE`.
12. Avoid holding snapshots, locks, and connections open too long, impacting `VACUUM` and pools.
13. Write keyset pagination with stable sort keys.
14. Build exports with backpressure, timeouts, and proper cleanup.
15. Measure end-to-end throughput, heap/GC, server I/O, WAL, latency, and transaction duration.

## 2. Data Path from PostgreSQL to Java

~~~text
Java code
  |
  | PreparedStatement.executeQuery()
  v
pgJDBC
  |
  | PostgreSQL wire protocol
  v
PostgreSQL backend
  |
  | Scan / Join / Aggregate / Sort
  v
Row production
  |
  | Fetch all or cursor fetch
  v
ResultSet.next()
  |
  | Row mapping
  v
CSV writer / domain consumer / streaming sink
~~~

For good application performance, examine the entire pipeline:

- Is the SQL reading too many rows?
- Does the query plan contain memory-heavy `Sort` or `HashAggregate` nodes?
- How many rows does the driver buffer?
- How many bytes is each row?
- Does Java accumulate an unbounded `List`?
- Can the file/network sink write as fast as rows arrive?
- How long are the transaction and DB connection held open?

**Fetch size does not replace proper SQL indexes and `WHERE` filters.** It mainly controls how the driver receives rows, not how many rows PostgreSQL must compute.

## 3. Lab Environment

The Java snippets use:

- A JDK supporting Java text blocks, such as Java 17.
- Standard JDBC (`java.sql`).
- PostgreSQL JDBC driver (**pgJDBC**) compatible with your JDK and PostgreSQL versions.
- A lab database where creating tables is permitted.
- A `DataSource` (from a connection pool) or valid connection.

Example Maven dependency:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version><!-- Version pinned and verified by your project --></version>
</dependency>
~~~

Never hard-code real usernames or passwords in code, logs, or documentation. Sample connection URL:

~~~text
jdbc:postgresql://localhost:5432/training_db
~~~

The name `training_db` is only an example. Configure credentials via a secret manager or secure deployment mechanism.

## 4. Lab: Schema for Bulk Writes and Large Reads

**Warning:** `DROP SCHEMA ... CASCADE` deletes every object in the specified schema. Run this only in a **dedicated lab database**, never in production.

~~~sql
-- RUN ONLY IN A PRACTICE DATABASE.
DROP SCHEMA IF EXISTS jdbc_batch_lab CASCADE;
CREATE SCHEMA jdbc_batch_lab;

CREATE TABLE jdbc_batch_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    customer_ref text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'confirmed', 'cancelled')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE TABLE jdbc_batch_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    event_time timestamptz NOT NULL,
    payload text NOT NULL
);

CREATE INDEX idx_events_time_id
ON jdbc_batch_lab.events (event_time, event_id);
~~~

Seed a few initial orders:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES
    ('seed-001', 'customer-A', 100.00),
    ('seed-002', 'customer-B',  75.50),
    ('seed-003', 'customer-C',  24.00);
~~~

Generate data for large reads:

~~~sql
-- 50,000 illustrative rows; use 5,000 on smaller lab setups.
INSERT INTO jdbc_batch_lab.events (
    event_type, event_time, payload
)
SELECT
    CASE WHEN g % 5 = 0 THEN 'payment' ELSE 'view' END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 second',
    repeat('x', 200)
FROM generate_series(1, 50000) AS s(g);

ANALYZE jdbc_batch_lab.orders;
ANALYZE jdbc_batch_lab.events;
~~~

The lab populates 50,000 events with 200-character payloads; those writes generate real index updates, WAL, and disk I/O. Do not run this on a database serving production traffic.

## 5. `PreparedStatement` Instead of SQL String Concatenation

Wrong:

~~~java
// ANTI-PATTERN: raw input concatenated into SQL.
String sql = "INSERT INTO jdbc_batch_lab.orders (customer_ref,amount)"
    + " VALUES ('" + customerRef + "'," + amount + ")";
~~~

Right:

~~~java
String sql = """
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    ) VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, idempotencyKey);
    ps.setString(2, customerRef);
    ps.setBigDecimal(3, amount);
    ps.executeUpdate();
}
~~~

Bind parameters prevent SQL injection, eliminate quoting bugs, and provide a reusable SQL template. This is also the foundation of JDBC batching.

## 6. What Overhead Does Row-by-Row Writing Incur?

Example:

~~~java
for (OrderInput order : orders) {
    try (PreparedStatement ps =
            connection.prepareStatement(INSERT_SQL)) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.executeUpdate();
    }
}
~~~

With 10,000 items, this creates 10,000 statements and performs 10,000 network round trips to the server. When `autoCommit=true`, each statement may also run in its own separate transaction.

Optimization progression:

1. Reuse a single `PreparedStatement`.
2. Group parameter sets with `addBatch()`.
3. Define appropriate transaction boundaries.
4. Benchmark `reWriteBatchedInserts` if using pgJDBC.
5. For massive bulk loads, consider `COPY`.

**Do not use batching to disguise work that a set-based SQL query can handle far better.**

## 7. `addBatch` and `executeBatch`

~~~java
try (PreparedStatement ps = connection.prepareStatement(INSERT_SQL)) {
    for (OrderInput order : orders) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

### Exact Meaning

- `setString`/`setBigDecimal`: bind parameter values for the statement.
- `addBatch`: append a parameter set to the logical batch.
- `executeBatch`: instruct the JDBC driver to execute the batch.
- `updateCounts`: report per-command results per the JDBC contract.
- `commit`: complete the transaction when autocommit is off.

**Calling `addBatch` does not persist rows. Calling `executeBatch` does not `COMMIT` either** if the connection is inside a caller-managed transaction.

## 8. Complete Java Example: Atomic Batch `INSERT`

Input record:

~~~java
import java.math.BigDecimal;

public record OrderInput(
    String key,
    String customerRef,
    BigDecimal amount
) {}
~~~

Method opening its own connection and managing its transaction:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public final class OrderImporter {

    private static final String INSERT_SQL = """
        INSERT INTO jdbc_batch_lab.orders (
            idempotency_key, customer_ref, amount
        )
        VALUES (?, ?, ?)
        ON CONFLICT (idempotency_key) DO NOTHING
        """;

    public static void insertOrders(
            DataSource dataSource,
            List<OrderInput> orders
    ) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement ps =
                        connection.prepareStatement(INSERT_SQL)) {

                    for (OrderInput order : orders) {
                        ps.setString(1, order.key());
                        ps.setString(2, order.customerRef());
                        ps.setBigDecimal(3, order.amount());
                        ps.addBatch();
                    }

                    ps.executeBatch();
                }

                connection.commit();

            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

Explanation:

- `DataSource` supplies a pooled connection.
- The method owns its connection and transaction.
- `setAutoCommit(false)` allows committing the entire batch together.
- `ON CONFLICT DO NOTHING` handles expected duplicate keys.
- Exceptions trigger rollback before rethrowing; any rollback error is attached as a suppressed exception.
- `try-with-resources` closes statement and connection cleanly.

**Do not copy `commit()` into methods participating in a Spring/JTA or caller-managed transaction.** When a framework manages transactions, it must control boundaries.

## 9. Use `BigDecimal` for Monetary Amounts

~~~java
new OrderInput(
    "ext-001",
    "customer-A",
    new BigDecimal("19.99")
);
~~~

Avoid:

~~~java
new BigDecimal(0.1);
~~~

when expecting exact decimal `0.1`, because constructing from `double` captures binary floating-point representation error. Construct from a `String` or an exact conversion per your contract.

PostgreSQL `numeric(12,2)` fits fixed two-decimal-place amounts in this example; multi-currency systems may require dedicated precision and currency modeling.

## 10. Batch Size: Chunking Statements

Do not pile one million rows into a single batch, retaining every parameter set in JVM memory.

~~~java
int batchSize = 500;
int pending = 0;

try (PreparedStatement ps = connection.prepareStatement(INSERT_SQL)) {
    for (OrderInput order : orders) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.addBatch();

        pending++;

        if (pending >= batchSize) {
            ps.executeBatch();
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
        ps.clearBatch();
    }
}
~~~

**Chunking batches is not chunking transactions.** If `connection.commit()` is called once at the end, all `executeBatch()` calls still belong to the same transaction.

### How Many Rows per Batch?

Benchmark 100, 500, 1,000, or suitable sizes. It depends on:

- Row size.
- Parameters per command.
- Network round-trip latency.
- Driver/JVM RAM.
- WAL, index, and trigger costs.
- Lock duration.
- Replication lag.
- Protocol/driver parameter limits.
- Rollback granularity on error.

Never assume 10,000 is always faster than 500.

## 11. Batch Size vs. Transaction Chunk Size Are Two Distinct Concepts

**Single transaction:**

~~~text
BEGIN
  executeBatch(500)
  executeBatch(500)
  ...
COMMIT
~~~

If a later batch fails unrecoverably, the whole job can roll back cleanly. Ideal when **all-or-nothing** atomicity is required, though transactions can run long.

**Multiple smaller transactions:**

~~~text
BEGIN -> executeBatch(500) -> COMMIT
BEGIN -> executeBatch(500) -> COMMIT
...
~~~

Reduces lock and snapshot duration and simplifies resuming, though the job can partially succeed if a later chunk fails.

### Questions Business Design Must Answer

- Is partial import acceptable?
- Which batch was processed so far?
- How do retries run safely?
- Do inputs carry idempotency keys?
- Are checkpoints committed atomically alongside data?
- What happens if the network drops right after `COMMIT`?

**Never trade away atomicity merely to boost rows/sec.**

## 12. Reading Update Counts

`PreparedStatement.executeBatch()` returns `int[]`. `executeLargeBatch()` returns `long[]` when row counts may exceed `int` range under the JDBC contract.

Each element can be:

| Value | Meaning |
| --- | --- |
| Non-negative integer | Reported number of affected rows |
| `Statement.SUCCESS_NO_INFO` (-2) | Succeeded, exact count unknown |
| `Statement.EXECUTE_FAILED` (-3) | Command failed while the driver continued processing the batch |

~~~java
int[] counts = ps.executeBatch();

for (int count : counts) {
    if (count >= 0) {
        System.out.println("Affected rows = " + count);
    } else if (count == java.sql.Statement.SUCCESS_NO_INFO) {
        System.out.println("Succeeded, count not available");
    } else if (count == java.sql.Statement.EXECUTE_FAILED) {
        System.out.println("Batch command failed");
    }
}
~~~

With `ON CONFLICT DO NOTHING`, a command may affect **0 rows**. When the driver rewrites batches, per-item counts can also differ depending on driver version and optimization path.

**Never treat `counts.length` as the number of committed rows.** Verify post-commit via batch IDs or idempotency keys.

## 13. `BatchUpdateException`

~~~java
try {
    ps.executeBatch();
} catch (java.sql.BatchUpdateException ex) {
    int[] counts = ex.getUpdateCounts();
    String sqlState = ex.getSQLState();

    // Log only permitted metadata; avoid logging PII.
    System.err.println(
        "Batch failed: SQLSTATE=" + sqlState
        + ", counts reported=" + counts.length
    );

    throw ex;
}
~~~

Per JDBC, a driver may halt on the first error or continue remaining commands, reflecting that in `getUpdateCounts()`.

In PostgreSQL, any SQL statement error inside an explicit transaction puts the transaction into the **aborted** state until `ROLLBACK` or rolling back to a valid savepoint. Never blindly issue another `executeBatch()` on that connection assuming earlier commands were ignored or recovered.

### Safe Handling Flow

1. Classify SQLSTATE.
2. Roll back the failed transaction.
3. Log structured metadata without sensitive payloads.
4. Determine whether the error is retryable.
5. Retry the full transaction with bounded attempts and idempotency.
6. Reconcile commit status if the client lost visibility into the outcome.

## 14. Important SQLSTATEs

| Code | Meaning | Approach |
| --- | --- | --- |
| `23505` | Unique violation | Check key/payload and duplicate policy |
| `23503` | Foreign key violation | Check referenced data or import ordering |
| `23514` | Check violation | Input violates invariant |
| `23502` | Not-null violation | Missing required value |
| `40001` | Serialization failure | Retry full transaction when safe |
| `40P01` | Deadlock detected | Roll back, back off, retry appropriately |
| `55P03` | Lock not available | Adjust locking strategy/timeouts |
| `57014` | Query cancelled | Handle timeout/cancellation |
| `08006` | Connection failure | Unknown whether transaction committed |

Never blindly retry every constraint error. If an input amount is negative, retrying one million times will never fix the data.

## 15. Idempotency to Prevent Duplicate Writes

Suppose the server committed a batch, yet the client lost the connection before receiving the acknowledgment. The client retries.

Schema uses:

~~~sql
idempotency_key text NOT NULL UNIQUE
~~~

Example:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES (
    'external-123',
    'customer-A',
    100.00
)
ON CONFLICT (idempotency_key) DO NOTHING;
~~~

The same key will not insert a duplicate row. However, you must still catch **same key with different payload**; `DO NOTHING` alone can silently mask business errors if the caller changed payload fields.

Production designs typically compute canonical payload hashes or compare stored fields and enforce explicit conflict contracts. Never mint a **new** random key on each retry of the same request.

## 16. `reWriteBatchedInserts` in pgJDBC

pgJDBC provides a connection property:

~~~text
reWriteBatchedInserts=true
~~~

Example URL:

~~~text
jdbc:postgresql://localhost:5432/training_db?reWriteBatchedInserts=true
~~~

When eligible, the driver can rewrite multiple batched `INSERT`s into multi-row `VALUES` form:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES
    (?, ?, ?),
    (?, ?, ?),
    (?, ?, ?);
~~~

### Benefits

- Cuts protocol overhead and round trips for repeated identical `INSERT` templates.
- Can substantially boost rows/sec on suitable workloads.

### Limitations

- This is a **pgJDBC property**, not standard JDBC.
- Not every SQL statement or batch qualifies for rewriting.
- `RETURNING`, generated keys, and complex `INSERT` forms can affect rewrite eligibility.
- The driver may split batches internally to stay within parameter/protocol limits.
- Returned batch update counts may differ from unrewritten individual `INSERT`s depending on version.
- PostgreSQL still checks all `UNIQUE`, `FK`, `CHECK`, and trigger constraints.
- Always test against your exact driver version.

**Do not assume enabling this property yields a fixed speedup percentage or creates one arbitrarily huge statement.**

## 17. Be Careful with Generated Keys in Batches

Single `INSERT`:

~~~java
String sql = """
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    )
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        java.sql.Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "generated-key-demo");
    ps.setString(2, "customer-A");
    ps.setBigDecimal(3, new java.math.BigDecimal("25.00"));

    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long orderId = keys.getLong(1);
            System.out.println(orderId);
        }
    }
}
~~~

With batches:

- `getGeneratedKeys()` and `RETURNING` carry driver-specific mapping and performance behavior.
- `ON CONFLICT DO NOTHING` may emit no key for skipped conflicts.
- Do not assume every input command returns exactly one generated key in order.
- When exact correlation is required, carry an application correlation key and query or return it explicitly.

Never trade key-mapping correctness for raw throughput.

## 18. Batch `UPDATE` or Set-Based SQL?

A batch `UPDATE`:

~~~java
String sql = """
    UPDATE jdbc_batch_lab.orders
    SET status = ?
    WHERE idempotency_key = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (String key : keys) {
        ps.setString(1, "confirmed");
        ps.setString(2, key);
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

Yet if all target keys are already known:

~~~sql
UPDATE jdbc_batch_lab.orders
SET status = 'confirmed'
WHERE idempotency_key IN ('seed-001', 'seed-002');
~~~

A single set-based SQL command can be cleaner and faster than hundreds of individual `UPDATE`s. For larger datasets, consider staging tables, `UPDATE ... FROM`, `INSERT ... ON CONFLICT DO UPDATE`, or `COPY` followed by a set-based merge.

**JDBC batching cuts per-command dispatch cost; it does not replace set-based SQL thinking.**

## 19. `COPY` for Bulk Loading

PostgreSQL `COPY` supports bulk import/export, and pgJDBC offers an extended Copy API distinct from `PreparedStatement.executeBatch`.

| Requirement | JDBC Batch | `COPY` |
| --- | --- | --- |
| Many parameterized `INSERT`s | Well suited | Possible via stream/file formatting |
| Very large bulk loads | Good depending on workload | Often highly efficient |
| Direct `ON CONFLICT` | Supported via `INSERT` | `COPY` directly has no `ON CONFLICT` |
| Per-row generated keys | Supported via driver/SQL mapping | Not like `INSERT ... RETURNING` |
| Row-by-row validation | Easy in Java/JDBC | Best handled via staging + SQL validation |
| Atomicity | Transaction | Transaction |
| Standard portable JDBC | Yes | PostgreSQL-specific Copy API |

Example pipeline:

~~~text
BEGIN
  COPY staging_orders FROM input stream
  Validate and transform in SQL
  INSERT INTO orders SELECT ... FROM staging_orders
    ON CONFLICT (...) DO NOTHING
COMMIT
~~~

When incoming data is large and messy, staging lets you check duplicates, mappings, constraints, and error reporting cleanly. Never disable production constraints just to make an import faster.

## 20. When to Use Savepoints?

JDBC provides `Savepoint` for partial rollback:

~~~java
java.sql.Savepoint sp = connection.setSavepoint();

try {
    // Execute a group of SQL commands.
} catch (SQLException ex) {
    connection.rollback(sp);
    // Decide whether to skip or fail per import policy.
}
~~~

After a statement error inside a transaction, you must roll back to a valid savepoint before continuing further work per PostgreSQL semantics.

However:

- Savepoints add overhead.
- Never swallow errors you do not know how to handle.
- They cannot roll back external side effects.
- If input data is clearly invalid, retrying does not fix it.
- All-or-nothing imports usually do not need savepoints; rolling back the full transaction is simpler.

## 21. What Is Fetch Size?

Example:

~~~sql
SELECT event_id, event_type, event_time, payload
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

This returns 50,000 rows. A Java loop:

~~~java
while (rs.next()) {
    // Process one row.
}
~~~

**does not guarantee the driver keeps only one row in memory**. Under default settings, pgJDBC may buffer the entire result set on the client before or during iteration.

~~~java
ps.setFetchSize(500);
~~~

hints the batch size of rows to retrieve when the driver uses an appropriate cursor mode.

**`setFetchSize(500)` does not make `SELECT` return only 500 rows.** Nor is it equivalent to `LIMIT 500`.

## 22. Conditions for pgJDBC Cursor Fetching

Under typical pgJDBC server-side cursor/portal fetching, you need:

1. The connection is **not in autocommit mode** when executing the `SELECT`.
2. The `ResultSet`/`Statement` is **forward-only**.
3. The fetch size is **positive**.
4. A suitable query, typically a single statement.
5. Query protocol and driver settings supporting cursor fetch.
6. The transaction, statement, and connection stay open while iterating.

### Why `autoCommit = false`?

Non-holdable server cursors close when the transaction ends. If the `SELECT` runs in a transaction that autocommits right away, the driver cannot keep fetching subsequent chunks from the portal as desired.

A tutorial claiming “just set `setFetchSize(100)` and you are streaming” without mentioning `autoCommit = false` **is misleading for PostgreSQL**.

## 23. Example Missing Cursor Conditions

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement("""
         SELECT event_id, event_type
         FROM jdbc_batch_lab.events
         ORDER BY event_id
         """)) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Getting right results does not prove cursor fetch was active.
        }
    }
}
~~~

If the connection remains `autoCommit = true`, pgJDBC will not necessarily use server-side cursor fetching as expected. Always verify your driver, version, and query mode.

## 24. Correct Example: Reading a Large `ResultSet`

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class EventScanner {

    public static long scan(DataSource source)
            throws SQLException {

        String sql = """
            SELECT event_id, event_type, event_time
            FROM jdbc_batch_lab.events
            ORDER BY event_id
            """;

        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);
            connection.setReadOnly(true);

            try {
                long rows = 0L;

                try (PreparedStatement ps =
                        connection.prepareStatement(
                            sql,
                            ResultSet.TYPE_FORWARD_ONLY,
                            ResultSet.CONCUR_READ_ONLY)) {

                    ps.setFetchSize(500);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long id = rs.getLong("event_id");
                            String type = rs.getString("event_type");

                            consume(id, type);
                            rows++;
                        }
                    }
                }

                connection.commit();
                return rows;

            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    private static void consume(long id, String type) {
        // Fast demo consumer; do not collect the entire ResultSet into a List.
        if (id < 0) {
            throw new IllegalArgumentException(type);
        }
    }
}
~~~

Key points:

- The connection belongs exclusively to this method.
- `setAutoCommit(false)` satisfies the key requirement for pgJDBC cursor fetching.
- `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` fit sequential scanning.
- `setFetchSize(500)` specifies chunk size.
- `ResultSet` is consumed within the scope of `PreparedStatement` and `Connection`.
- Commits only after finishing traversal, rolling back on errors.
- Avoids accumulating rows in an in-memory `List`.

### Note on Read-Only Mode

`Connection.setReadOnly(true)` is an API hint/setting whose exact enforcement depends on the driver and `readOnlyMode`. It does not replace PostgreSQL object privileges or guarantee every command is read-only; check your pgJDBC version and configuration.

### Framework-Managed Transactions

If code runs inside a Spring-managed transaction or a caller already owns the connection, do not flip `autoCommit` or call `commit()` without an explicit transaction contract. The pattern above applies to methods **owning their own transaction**.

## 25. `fetchSize` 0 vs. Positive Values

| Setting | Typical Meaning in pgJDBC |
| --- | --- |
| `setFetchSize(0)` | Default; typically fetches the whole result instead of incremental cursor chunks |
| `setFetchSize(100)` | Fetches roughly 100 rows per trip when cursor mode applies |
| `setFetchSize(500)` | Fetches roughly 500 rows per trip when cursor mode applies |
| `setFetchSize(10000)` | Larger chunks, fewer round trips, larger client buffer |
| Negative number | Invalid per the JDBC fetch size contract |

### Which Number Should You Pick?

100, 500, or 1,000 are starting points for benchmarking, not universal defaults.

- Smaller batches → more fetch round trips.
- Larger batches → higher peak buffer memory.
- A 100-byte row differs vastly from a 5 MB JSON row.
- Drivers and queries impose their own constraints.

**Measure heap, time-to-first-row, total duration, round trips, network traffic, and pool occupancy** on realistic data.

## 26. `fetchSize` Differs from `LIMIT` and `setMaxRows`

~~~java
ps.setFetchSize(100);
~~~

does not restrict the SQL query to returning 100 rows.

If a user should only see 100 rows, express that limit in SQL:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id
LIMIT 100;
~~~

`Statement.setMaxRows` has its own JDBC semantics, whereas SQL `LIMIT` states the business bound directly.

**Fetch size = how results are transported in chunks. `LIMIT` = total size of the result set.**

## 27. Forward-Only vs. Scrollable `ResultSet`

~~~java
connection.prepareStatement(
    sql,
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
~~~

is designed for single-pass forward traversal via `next()`.

Using `TYPE_SCROLL_INSENSITIVE` or `TYPE_SCROLL_SENSITIVE` to call `previous()` or `absolute()` may force the driver to buffer/materialize the whole result and forego forward-only cursor fetching.

For a single-pass export, never request a scrollable `ResultSet` just out of habit.

## 28. Queries and Protocols Affect Cursor Mode

A single query:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

is normally eligible.

Do not combine multiple statements in one SQL string and expect the driver to stream a `SELECT` cursor:

~~~java
// Do not expect single-SELECT cursor fetching here.
String sql = "SET search_path TO jdbc_batch_lab; "
    + "SELECT * FROM events";
~~~

pgJDBC query protocol modes and properties like `preferQueryMode` affect portal/cursor support. Also, never copy MySQL properties like `useCursorFetch` into pgJDBC configs.

## 29. `defaultRowFetchSize`

pgJDBC offers the `defaultRowFetchSize` connection property:

~~~text
jdbc:postgresql://localhost:5432/training_db?defaultRowFetchSize=500
~~~

It sets a default fetch size across statements depending on driver/version rules. However:

- It does not automatically disable `autoCommit`.
- It affects many small queries that do not need cursor streaming.
- Frameworks may override fetch size explicitly.
- Compatible queries and protocols are still required.

If only one export needs streaming, setting `ps.setFetchSize(500)` right on that statement is easier to maintain unless a connection-wide default is explicitly desired.

## 30. SQL Cursors: `DECLARE`, `FETCH`, `CLOSE`

An explicit SQL cursor in PostgreSQL:

~~~sql
BEGIN;

DECLARE event_cursor NO SCROLL CURSOR FOR
SELECT event_id, event_type, event_time
FROM jdbc_batch_lab.events
ORDER BY event_id;

FETCH FORWARD 5 FROM event_cursor;
FETCH FORWARD 5 FROM event_cursor;

CLOSE event_cursor;

COMMIT;
~~~

Explanation:

- `DECLARE` opens a cursor inside the transaction.
- `FETCH FORWARD 5` retrieves the next 5 rows.
- `CLOSE` closes the cursor once finished.
- `COMMIT` ends the transaction.

Non-holdable cursors close automatically at transaction end; closing them explicitly as soon as finished remains good practice.

### Does a pgJDBC `ResultSet` Need Manual `DECLARE`?

**No.** When `setFetchSize` is configured under the proper conditions, pgJDBC manages the server-side cursor/portal transparently via the protocol. SQL `DECLARE`/`FETCH` is for controlling cursors directly in SQL, not a prerequisite before `ResultSet.next()`.

## 31. `WITH HOLD` Across `COMMIT`

PostgreSQL supports `WITH HOLD` SQL cursors:

~~~sql
BEGIN;

DECLARE held_events CURSOR WITH HOLD FOR
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;

COMMIT;

FETCH FORWARD 10 FROM held_events;

CLOSE held_events;
~~~

### Trade-offs

To keep a cursor alive across `COMMIT`, the server may **materialize the entire result set into memory or temporary disk files**, incurring server-side cost. Never treat `WITH HOLD` as free streaming.

JDBC `ResultSet` holdability and SQL `WITH HOLD` cursors also have API/driver nuances; verify carefully before combining them.

## 32. SQL Cursor vs. JDBC `ResultSet`

| Criterion | SQL Cursor | JDBC `ResultSet` with `fetchSize` |
| --- | --- | --- |
| Opening cursor | Application sends `DECLARE` | Driver manages internally |
| Fetching rows | `FETCH n` | `rs.next()` |
| Closing | `CLOSE` or transaction end | `ResultSet.close` / `Statement` / `Connection` |
| Transaction | Follows PostgreSQL cursor semantics | Follows driver and transaction mode |
| Fetch size | Rows per `FETCH` | `Statement.setFetchSize` |
| Fit for Java row mapping | Must orchestrate SQL flow manually | More natural |

For sequential reading in Java, `ResultSet` is usually cleaner. When database-side procedural logic specifically requires cursor control, `DECLARE`/`FETCH` has its place.

## 33. Cursors Do Not Eliminate Server-Side Sorting

Example:

~~~sql
SELECT event_type, COUNT(*) AS count_events
FROM jdbc_batch_lab.events
GROUP BY event_type
ORDER BY count_events DESC;
~~~

PostgreSQL still must scan and aggregate all rows before emitting the first output row. `setFetchSize(500)` does not make aggregation inherently cheaper.

Likewise, large sorts, hash joins, window functions, or aggregates still run on the server regardless of driver fetch size.

**Before tuning fetch size, optimize the SQL query with `WHERE`, column projection, indexes, and `EXPLAIN`.**

## 34. Snapshots, Isolation, and Fetching

Under `READ COMMITTED`, each normal SQL statement receives a snapshot per isolation rules. However, a single `SELECT` being iterated through a portal must not be mistaken for **each `FETCH` running a brand-new `SELECT` that sees subsequent commits**.

Under `REPEATABLE READ`, the transaction snapshot stays pinned per isolation rules, and long-running readers retain needed row versions.

### Consequences

- Chunked fetching **does not dynamically refresh** the result set with newer committed rows.
- A cursor offers a more consistent single-query snapshot than independent page queries.
- If “latest data per page” is needed, define those semantics explicitly.
- On heavily updated/deleted tables, long-lived snapshots can delay `VACUUM` cleanup.

## 35. Long Transactions Affect `VACUUM` and Pools

A 2-million-row export taking 30 minutes due to a slow client download holds its connection and transaction open the whole time.

Consequences:

- Ties up a pool slot.
- Keeps backend and portal resources busy.
- Holds back the snapshot/`xmin` horizon, blocking dead tuple reclamation.
- Increases table bloat and autovacuum lag in high-churn workloads.
- Risks mid-export timeouts or cancellations.
- With `FOR UPDATE`, holds row locks for the entire duration.
- Starves other requests when the pool runs dry.

Never stream an unbounded cursor straight out to unthrottled internet clients without deadlines, concurrency caps, and cancellation.

## 36. Streaming Does Not Automatically Mean Low Java RAM

Wrong:

~~~java
List<Event> allEvents = new ArrayList<>();

while (rs.next()) {
    allEvents.add(mapEvent(rs));
}
~~~

Even if the driver fetches 500 rows at a time, Java retains all mapped objects in memory.

Better for single-pass processing:

~~~java
while (rs.next()) {
    Event event = mapEvent(rs);
    sink.write(event);
}
~~~

Still, `sink` needs bounded buffering. If `sink` pushes into an unbounded queue, memory still grows. If `sink` blocks slowly, the transaction stretches out.

**Control driver buffering, Java object mapping, and downstream sink backpressure together.**

## 37. Never Return a `ResultSet` After Closing the `Connection`

Wrong:

~~~java
public ResultSet loadEvents(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection();
         PreparedStatement ps = connection.prepareStatement(
             "SELECT * FROM jdbc_batch_lab.events")) {
        return ps.executeQuery();
    }
}
~~~

Once the method returns, `PreparedStatement` and `Connection` are closed. The caller has no valid resource lifecycle to read the `ResultSet`.

Correct approaches:

- Consume the `ResultSet` inside the scope that owns the connection.
- Or expose a lazy iterator/API with explicit connection ownership and `close()` semantics.
- Never return a Java `Stream` from a repository if the transaction closes before the stream is consumed.

**Resource ownership is a correctness requirement, not just an optimization.**

## 38. `SELECT` Only Needed Columns, Never `SELECT *`

If an export only needs event ID and type:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

is far better than:

~~~sql
SELECT *
FROM jdbc_batch_lab.events;
~~~

when unused `payload` columns are 200 bytes or several megabytes wide.

Benefits:

- Fewer bytes over the network.
- Lower driver and JVM heap usage.
- Less GC pressure.
- Enables index-only scans in some queries.
- Reduces accidental exposure of sensitive columns.
- Less brittle when columns are added to the table.

Fetch size cannot compensate for shipping unneeded columns.

## 39. Large Objects, `bytea`, and Stream APIs

JDBC offers `getBinaryStream` and `getCharacterStream`:

~~~java
try (java.io.Reader reader = rs.getCharacterStream("payload")) {
    char[] buf = new char[8192];
    while (reader.read(buf) != -1) {
        // Process buffer per business contract.
    }
}
~~~

**Do not assume** every column type or driver streams directly off the socket without partial client/server materialization.

- `bytea` differs from PostgreSQL Large Objects (OIDs).
- The Large Object API carries its own transaction and lifecycle rules.
- A single huge column value can spike RAM even with `fetchSize = 1`.
- If the payload is unused, do not `SELECT` it.
- For multi-megabyte files, consider object storage or dedicated streaming storage APIs.

## 40. Keyset Pagination vs. `OFFSET`

`OFFSET`:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id
LIMIT 500 OFFSET 100000;
~~~

PostgreSQL must walk past and discard 100,000 rows before returning the page. Concurrent `INSERT`/`DELETE` operations can also shift page boundaries.

Keyset:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
WHERE event_id > 1000
ORDER BY event_id
LIMIT 500;
~~~

The application tracks `last_seen_id` and queries rows strictly greater than the last key. With a matching B-tree index, this avoids deep offset scans.

### Advantages

- No scanning and discarding ever-growing offsets.
- Each page can run in a short transaction.
- Easy to checkpoint and resume.
- Well suited to background export jobs.

### Limitations

- Independent page transactions **do not share a single snapshot**.
- Concurrent `UPDATE`/`DELETE` operations can shift results between pages.
- Increasing IDs do not necessarily match commit order.
- Exporting “exactly every event committed up to a point” requires a cutoff/watermark or explicit consistency design.

## 41. Multi-Column Keyset Pagination

When sorting by timestamp then ID:

~~~sql
SELECT event_id, event_time, event_type
FROM jdbc_batch_lab.events
WHERE (event_time, event_id) > (
    timestamptz '2026-01-01 12:00:00+00',
    1000
)
ORDER BY event_time, event_id
LIMIT 500;
~~~

Lab index:

~~~sql
CREATE INDEX idx_events_time_id
ON jdbc_batch_lab.events (event_time, event_id);
~~~

Created during lab setup. When multiple rows share the exact same `event_time`, `event_id` acts as a unique tie-breaker.

**Omitting a tie-breaker can skip rows sharing identical timestamps.** Keep column order identical between the `WHERE` tuple and `ORDER BY`.

## 42. Cursor or Keyset?

| Criterion | `ResultSet` Cursor | Keyset Pagination |
| --- | --- | --- |
| Scanning one large `SELECT` sequentially | Well suited | Possible |
| Bounded client memory | Yes if used properly and sink bounded | Yes via `LIMIT` |
| Long-held transaction | Usually yes | Usually not needed |
| Resuming after failure | Harder | Supported via checkpoint |
| Single-query snapshot | Built into cursor/transaction semantics | Requires extra design |
| Slow network client downloads | Risks exhausting DB pool | Can write file first, then serve download |
| Parallel export workers | Harder | Easy to partition ranges |
| Concurrent data modifications | Follows query snapshot | Cross-page consistency must be handled |
| Query requires large server `Sort` | Does not eliminate `Sort` | Does not automatically eliminate `Sort` |

No single choice wins everywhere. A quick few-second export works cleanly with a cursor; multi-hour resumable exports favor keyset pagination, CDC, or async file jobs.

## 43. Connection Pools, Backpressure, and HTTP

Suppose a pool has 20 connections. If 20 requests stream CSVs through cursors to slow clients concurrently, the pool can starve normal API traffic.

Actual data flow:

~~~text
PostgreSQL -> pgJDBC -> Java mapping -> CSV encoder
           -> HTTP buffer -> network -> browser/client
~~~

When downstream slows down:

- Buffers grow or connections remain pinned.
- Transactions stretch out.
- Idle-in-wait transactions keep snapshots open.
- Other users wait on pool slots.
- Exports time out mid-stream.

### Better Architecture for Very Large Exports

1. API schedules an export job and returns a job ID.
2. Concurrency-capped worker reads via cursor or keyset pagination.
3. Worker writes output file to storage under appropriate data protection policies.
4. Worker closes the DB connection as soon as file generation finishes.
5. Client downloads the file independently of any DB transaction.
6. Files follow expiration/retention cleanup policies.

This adds workflow machinery but avoids pinning DB connections and transactions on slow HTTP clients.

## 44. Timeouts and Cancellation

JDBC:

~~~java
ps.setQueryTimeout(60); // Seconds per JDBC.
~~~

PostgreSQL inside a transaction:

~~~sql
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
~~~

Different timeouts govern different layers:

| Timeout | Scope |
| --- | --- |
| JDBC `setQueryTimeout` | Driver-requested statement cancellation limit |
| `statement_timeout` | Server-side statement execution duration |
| `lock_timeout` | Waiting to acquire locks |
| `idle_in_transaction_session_timeout` | Session idle time inside an open transaction |
| Pool connection timeout | Waiting to borrow a connection from the pool |
| Socket/network timeout | Driver socket read/write timeout behavior |

Never assume `setQueryTimeout(60)` guarantees an **entire export including every cursor fetch and `sink.write()`** finishes in 60 seconds. Implement application-level job deadlines and cancellation.

After a timeout or cancellation, roll back the transaction if needed and always close `ResultSet`, `Statement`, and `Connection` along error paths.

## 45. A Callback API That Owns Resources Safely

~~~java
@FunctionalInterface
public interface EventConsumer {
    void accept(long id, String type) throws Exception;
}
~~~

Example:

~~~java
public static long scanEvents(
        javax.sql.DataSource ds,
        EventConsumer consumer
) throws Exception {

    String sql = """
        SELECT event_id, event_type
        FROM jdbc_batch_lab.events
        ORDER BY event_id
        """;

    try (java.sql.Connection c = ds.getConnection()) {
        c.setAutoCommit(false);

        try {
            long total = 0L;

            try (java.sql.PreparedStatement ps =
                    c.prepareStatement(
                        sql,
                        java.sql.ResultSet.TYPE_FORWARD_ONLY,
                        java.sql.ResultSet.CONCUR_READ_ONLY)) {

                ps.setFetchSize(500);

                try (java.sql.ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        consumer.accept(
                            rs.getLong("event_id"),
                            rs.getString("event_type")
                        );
                        total++;
                    }
                }
            }

            c.commit();
            return total;

        } catch (Exception ex) {
            try {
                c.rollback();
            } catch (java.sql.SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    }
}
~~~

Notice the callback executes **while the DB transaction is open**. Never call slow external APIs, send emails, or trigger irreversible side effects inside the callback assuming a DB rollback can undo them.

If resumability is required, a job controller with keyset checkpoints is usually a better fit.

## 46. `SELECT FOR UPDATE` and Long Cursors

Example:

~~~sql
SELECT order_id, status
FROM jdbc_batch_lab.orders
WHERE status = 'new'
ORDER BY order_id
FOR UPDATE;
~~~

Inside a transaction, this locks matching rows. Iterating slowly over 100,000 rows keeps those locks held and blocks other sessions.

For queue-like workloads, use short batches instead:

~~~sql
SELECT order_id
FROM jdbc_batch_lab.orders
WHERE status = 'new'
ORDER BY order_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

`SKIP LOCKED` fits certain job queues while offering a partial view of uncommitted contenders; do not treat it as a universal fix for every concurrency challenge.

Keeping locks brief and completing updates in tight transactions is usually far better than streaming a long-lived locking cursor.

## 47. Monitoring Long-Running Transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Watch for:

- Sessions long in `idle in transaction`.
- Very old `xact_start` timestamps.
- Wait events and locks.
- Pool active/pending metrics.
- Replication slots or snapshots if `VACUUM` stalls cleanup.

Never blame every `VACUUM` lag solely on cursors; replication slots, prepared transactions, and other long transactions can also hold back the `xmin` horizon.

`pg_stat_activity.query` may contain sensitive SQL literals; govern monitoring access under your security policy.

## 48. `EXPLAIN` Does Not Measure Transfer Time to Java

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_type, event_time
FROM jdbc_batch_lab.events
WHERE event_time >= timestamptz '2026-01-01 01:00:00+00'
ORDER BY event_time, event_id;
~~~

Inspect:

- `Seq Scan`, `Index Scan`, `Bitmap Scan`.
- Rows removed by filter.
- Sorts and temporary disk spills.
- Buffers hit/read.
- Actual rows and execution time.

**`EXPLAIN ANALYZE` runs on the server**; it does not measure shipping `ResultSet` rows across the network, allocating objects in the JVM, or writing CSV output.

End-to-end cost:

~~~text
Server SQL execution
+ Network transfer / fetch round trips
+ pgJDBC buffering
+ Java row mapping / GC
+ Sink / file / network latency
+ Pool wait
~~~

A 200 ms SQL query can easily become a 30-second export endpoint if network or sink performance bottlenecks it.

## 49. How to Benchmark Write Batches

Hold constant:

- Input dataset, row size, constraints, indexes, and triggers.
- Network path and connection pool.
- Server resource limits.
- Transaction isolation level.
- Cases with and without duplicates.

Compare:

1. Row-by-row `executeUpdate`.
2. `PreparedStatement` batch size 100.
3. Batch sizes 500 and 1,000.
4. `reWriteBatchedInserts=false/true`.
5. `COPY` into staging + merge where appropriate.

Measure:

| Metric | Meaning |
| --- | --- |
| Committed rows/sec | True business throughput |
| Batch latency p50/p95 | Per-transaction latency |
| Driver/client heap/GC | Application overhead |
| DB CPU/I/O/WAL | Server overhead |
| Replication lag | Downstream impact |
| Locks/deadlocks | Write contention |
| Errors/retries/duplicates | Stability |
| Total job completion | End-to-end efficiency |

**Never benchmark large `INSERT`s in production without an approved plan and operational authorization.**

## 50. How to Benchmark Streaming Reads

Test representative datasets:

- 1,000 rows × 100 bytes.
- 100,000 rows × 100 bytes.
- 100,000 rows × 10 KB.
- 1,000 rows with very large payloads.

For each dataset:

- Compare `fetchSize = 0, 100, 500, 1000`.
- Keep SQL, driver version, and transaction mode identical.
- Verify cursor mode prerequisites actually hold.
- Measure peak heap, time-to-first-row, total duration, and network bytes.
- Measure transaction lifetime, pool occupancy, and GC pauses.
- Measure sink throughput and cancellation behavior.
- Verify exact row counts and ordering.

**The largest fetch size is not automatically best; time-to-first-row and total throughput can pull in opposite directions.**

## 51. Common JDBC Batching Mistakes

1. **Calling `addBatch` and forgetting `executeBatch`**, so no SQL runs.
2. **Assuming `executeBatch` commits automatically** when `autoCommit=false`.
3. **Using `autoCommit=true` for an all-or-nothing import**, leaving partial state on error.
4. **Batching one million rows in one giant chunk**, causing heap/memory pressure.
5. **Committing every row**, magnifying transaction overhead.
6. **Confusing batch size with transaction chunk size.**
7. **Treating `counts.length` as inserted row count**, ignoring `ON CONFLICT` skips.
8. **Ignoring `SUCCESS_NO_INFO` / `0` / `EXECUTE_FAILED`.**
9. **Failing to roll back after `BatchUpdateException`.**
10. **Continuing SQL on an aborted transaction.**
11. **Retrying without idempotency**, creating duplicates.
12. **Generating a new idempotency key on every retry.**
13. **Using `double` for money.**
14. **Concatenating untrusted input into SQL.**
15. **Enabling rewrite and assuming every `INSERT` collapses into one statement.**
16. **Skipping tests for generated key mapping with batches/`RETURNING`.**
17. **Assuming `COPY` natively supports `ON CONFLICT`.**
18. **Measuring only driver call time**, ignoring commit/WAL/locks.
19. **Disabling constraints/triggers in benchmarks that production still enforces.**
20. **Failing to classify SQLSTATE before retrying.**

## 52. Common Mistakes When Reading Large Results

1. **Setting `setFetchSize > 0` while `autoCommit=true`**, bypassing cursor mode.
2. **Using a scrollable `ResultSet`**, forcing excessive buffering.
3. **Combining multiple SQL statements in one query** while expecting cursor fetch.
4. **Applying other drivers' properties** to pgJDBC.
5. **Confusing `fetchSize` with `LIMIT`.**
6. **Returning a `ResultSet` after closing the `Connection`.**
7. **Returning a lazy `Stream` outside transaction scope.**
8. **Collecting every row into a `List`**, defeating streaming.
9. **Running `SELECT *`** and dragging along huge or sensitive columns.
10. **Using `fetchSize=1000` with multi-MB row payloads.**
11. **Holding a cursor open while a slow HTTP client downloads**, exhausting the pool.
12. **Leaking resources when exceptions occur.**
13. **Failing to roll back on timeout/cancel.**
14. **Using `WITH HOLD` while overlooking server materialization cost.**
15. **Using deep `OFFSET` to export millions of rows.**
16. **Omitting a tie-breaker in keyset pagination**, silently dropping rows with identical timestamps.
17. **Assuming sequence IDs match commit order.**
18. **Leaving export snapshot consistency undefined.**
19. **Holding `SELECT FOR UPDATE` across a long cursor.**
20. **Measuring only server SQL time while ignoring network, mapping, and sink.**
21. **Not capping concurrent export jobs.**
22. **Failing to stop DB scans when clients disconnect.**
23. **Assuming every fetch chunk sees newly committed rows**, ignoring isolation.
24. **Lacking checkpoints/retries** on multi-hour export jobs.
25. **Missing access controls when exporting sensitive data.**

## 53. Practice Exercises with Answers

Use the `jdbc_batch_lab` schema created above; run DML exercises inside a lab database and roll back when testing only.

### Exercise 1. How do batching and fetch size differ?

**Answer:** Batching sends multiple commands or parameter sets to execute; fetch size controls how many rows the driver fetches per chunk when iterating a `ResultSet`.

### Exercise 2. Does `addBatch` write the row?

**Answer:** Not yet. It queues the command/parameter set into the batch; `executeBatch` is required.

### Exercise 3. Does `executeBatch` commit automatically?

**Answer:** No when `autoCommit=false`; the transaction owner must `commit()` or `rollback()`.

### Exercise 4. Why use `PreparedStatement`?

**Answer:** Parameter binding prevents SQL injection and lets the same SQL template be reused efficiently.

### Exercise 5. Write a batch `INSERT`

~~~java
try (PreparedStatement ps = connection.prepareStatement("""
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    ) VALUES (?, ?, ?)
    """)) {

    ps.setString(1, "exercise-1");
    ps.setString(2, "customer-A");
    ps.setBigDecimal(3, new BigDecimal("9.99"));

    ps.addBatch();
    ps.executeBatch();
}
~~~

**Answer:** One parameter set was executed; manage the transaction explicitly if autocommit is off.

### Exercise 6. What does `SUCCESS_NO_INFO` mean?

**Answer:** The command succeeded, but the driver did not report an exact affected row count.

### Exercise 7. What can an update count of `0` mean?

**Answer:** The command affected zero rows—for example, `ON CONFLICT DO NOTHING` hitting an existing key.

### Exercise 8. What should you do on `BatchUpdateException`?

**Answer:** Inspect SQLSTATE and update counts, roll back the transaction per contract, and never assume earlier commands in an uncommitted transaction succeeded durably.

### Exercise 9. If you call `executeBatch` every 500 rows and `commit` once at the end, is the whole job atomic?

**Answer:** Yes, if every batch runs in that same transaction ending in one final `commit`.

### Exercise 10. If you `commit` every 500 rows, is the whole job atomic?

**Answer:** No; earlier committed chunks persist if a later chunk fails.

### Exercise 11. Is `reWriteBatchedInserts` standard JDBC?

**Answer:** No. It is a pgJDBC-specific property for eligible batch `INSERT`s.

### Exercise 12. Can generated keys from a batch always be mapped 1-to-1 to input rows?

**Answer:** Do not assume so; verify exact driver and SQL behavior and use an application correlation key when needed.

### Exercise 13. When should you use `COPY`?

**Answer:** For large bulk loads, typically from streams or files, often loading into a staging table to validate and merge.

### Exercise 14. Does `COPY` support `ON CONFLICT` directly like `INSERT`?

**Answer:** No; typically `COPY` into a staging table and then run `INSERT ... SELECT ... ON CONFLICT`.

### Exercise 15. Does `setFetchSize(100)` return only 100 rows?

**Answer:** No, it does not limit the total `ResultSet` size.

### Exercise 16. What are the core conditions for pgJDBC cursor fetching?

**Answer:** `autoCommit=false`, forward-only `ResultSet`, positive `fetchSize`, and a compatible query and protocol mode.

### Exercise 17. Why can `autoCommit=true` make pgJDBC fetch all rows at once?

**Answer:** Normal cursors/portals close at transaction end, so the driver cannot keep fetching incrementally across chunks.

### Exercise 18. What does `setFetchSize(0)` typically mean in pgJDBC?

**Answer:** Default fetch-all behavior rather than positive-size cursor chunking.

### Exercise 19. When is `TYPE_FORWARD_ONLY` appropriate?

**Answer:** When scanning sequentially in one direction with `next()`, suited for large streaming reads and cursor mode.

### Exercise 20. Write an SQL cursor fetching 10 rows

~~~sql
BEGIN;

DECLARE c NO SCROLL CURSOR FOR
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;

FETCH FORWARD 10 FROM c;

CLOSE c;
COMMIT;
~~~

**Answer:** Cursor declared inside a transaction, fetches 10 rows, closes, and commits.

### Exercise 21. Does `WITH HOLD` keep a cursor across commit at zero cost?

**Answer:** It survives commit where supported, but the server may materialize the result in memory or temp disk.

### Exercise 22. Why must you not return a `ResultSet` after closing its `Connection`?

**Answer:** `ResultSet` requires an active `Statement` and `Connection` to read rows.

### Exercise 23. Can heap still grow if the driver fetches chunks while code appends into a `List`?

**Answer:** Yes. The `List` retains every row in application memory.

### Exercise 24. Why is `SELECT *` risky for exports?

**Answer:** It ships unneeded columns/payloads, wastes memory and bandwidth, and risks leaking PII.

### Exercise 25. Why is deep `OFFSET` slow?

**Answer:** The server must scan through and discard many preceding rows before returning the requested page.

### Exercise 26. Keyset pagination after `event_id` 1000

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
WHERE event_id > 1000
ORDER BY event_id
LIMIT 500;
~~~

**Answer:** Retrieves up to 500 rows with IDs above 1000, able to leverage the primary key index.

### Exercise 27. If sorting by `event_time`, how do you avoid skipping tied timestamps?

**Answer:** Include unique `event_id` as a tie-breaker with tuple comparison `WHERE (event_time, event_id) > ...` matching `ORDER BY event_time, event_id`.

### Exercise 28. Do sequence IDs always match commit order?

**Answer:** No; a transaction allocated an earlier sequence value can commit after a transaction with a later ID.

### Exercise 29. Why do long-running cursors affect `VACUUM`?

**Answer:** Open transactions/snapshots pin old row versions needed for visibility, preventing dead-tuple reclamation.

### Exercise 30. Is `fetchSize=1` guaranteed to be fastest?

**Answer:** No; it causes excessive fetch round trips.

### Exercise 31. What risk arises with 5 MB rows and `fetchSize=1000`?

**Answer:** A single fetched chunk can be huge, creating severe heap and network pressure.

### Exercise 32. Should you try fixing a very slow query solely by increasing `fetchSize`?

**Answer:** No; fix query plan, indexes, and `WHERE` filters first—`fetchSize` mainly tunes client buffering.

### Exercise 33. Does `setQueryTimeout(60)` guarantee an entire file export finishes in 60 seconds?

**Answer:** Not necessarily; repeated fetches and sink writes follow different timing bounds. Add explicit job deadlines and cancellation.

### Exercise 34. Why can HTTP streaming exhaust a connection pool easily?

**Answer:** Slow clients hold cursors, transactions, and connections open for long periods, letting concurrent downloads consume every pool slot.

### Exercise 35. What issue arises with `SELECT FOR UPDATE` on a long cursor?

**Answer:** It holds row locks throughout traversal, blocking concurrent writers.

### Exercise 36. What should you measure beyond server SQL execution time?

**Answer:** Network transfer, driver fetch round trips, heap/GC, Java mapping, sink latency, pool wait, transaction duration, WAL, and retries.

### Exercise 37. How should `SQLSTATE 40001` be retried?

**Answer:** Roll back and retry the **entire transaction** with bounded backoff, recomputing business decisions from scratch.

### Exercise 38. What if connection drops right after `COMMIT`?

**Answer:** The commit outcome is uncertain. Query durable state via the idempotency key before retrying.

## 54. Implementation Checklist

- [ ] Separate bulk-write workloads from large single-`SELECT` read workloads.
- [ ] Use `PreparedStatement` and bind parameters.
- [ ] Use `addBatch`/`executeBatch` when sending many parameter sets for the same SQL.
- [ ] Define explicit transaction boundaries and rollback rules.
- [ ] Choose batch sizes by benchmarking rather than buffering infinitely.
- [ ] Distinguish batch size from transaction chunk size.
- [ ] Handle `BatchUpdateException` and update counts accurately.
- [ ] Use idempotency keys for retries and unknown commit outcomes.
- [ ] Never retry validation errors indefinitely.
- [ ] Benchmark `reWriteBatchedInserts` on your exact driver version and statements.
- [ ] Test generated key mapping in batches.
- [ ] Consider `COPY` + staging for large bulk loads.
- [ ] Never drop constraints or triggers just for benchmark speed.
- [ ] Set `autoCommit=false` for pgJDBC cursor fetching.
- [ ] Use `TYPE_FORWARD_ONLY` and `CONCUR_READ_ONLY`.
- [ ] Set a positive `fetchSize` on a compatible single-statement query.
- [ ] Do not confuse `fetchSize` with `LIMIT`.
- [ ] Consume `ResultSet` inside the connection/transaction scope.
- [ ] Close `ResultSet`/`Statement`/`Connection` and roll back on errors.
- [ ] Never return a lazy `ResultSet` past its resource owner.
- [ ] Avoid collecting every row into a `List` when bounded memory is needed.
- [ ] `SELECT` only required columns.
- [ ] Account for row byte size when tuning `fetchSize`.
- [ ] Enforce row, duration, and concurrency caps on exports.
- [ ] Implement cancellation/timeouts and cleanup on client disconnect.
- [ ] Monitor pool active/wait metrics and long-running `xact_start`.
- [ ] Avoid holding `SELECT FOR UPDATE` locks across long streams.
- [ ] Use keyset pagination when jobs need resume capability and short transactions.
- [ ] Include a unique tie-breaker and clear cutoff/consistency policy.
- [ ] Do not equate sequence IDs with commit order.
- [ ] Measure `EXPLAIN` and end-to-end Java throughput separately.
- [ ] Monitor WAL, replication lag, and lock contention during bulk writes.
- [ ] Test on your exact PostgreSQL, pgJDBC, and JDK versions.
- [ ] Never log secrets or PII from parameters or `ResultSet` rows.
- [ ] Never run large ad-hoc batch DML or `EXPLAIN ANALYZE UPDATE` casually in production.

## 55. Official Documentation

Match references to your deployed PostgreSQL, pgJDBC, and JDK versions:

- [pgJDBC: Cursor-based results](https://jdbc.postgresql.org/documentation/query/#getting-results-based-on-a-cursor) — `autoCommit=false`, fetch size, forward-only, and cursor conditions.
- [pgJDBC: Connection parameters](https://jdbc.postgresql.org/documentation/use/#connection-parameters) — `reWriteBatchedInserts`, `defaultRowFetchSize`, and driver properties.
- [pgJDBC documentation](https://jdbc.postgresql.org/documentation/) — official driver guide.
- [Java PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — parameters, `addBatch`, and `executeBatch`.
- [Java Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html) — fetch size, counts, result set types.
- [Java Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html) — `autoCommit`, `commit`, `rollback`, savepoints, isolation.
- [Java ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — cursor lifecycle, getters, navigation.
- [Java BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html) — batch errors and update counts.
- [PostgreSQL DECLARE](https://www.postgresql.org/docs/current/sql-declare.html) — SQL cursors.
- [PostgreSQL FETCH](https://www.postgresql.org/docs/current/sql-fetch.html) — retrieving rows from a cursor.
- [PostgreSQL CLOSE](https://www.postgresql.org/docs/current/sql-close.html) — closing a cursor.
- [PostgreSQL COPY](https://www.postgresql.org/docs/current/sql-copy.html) — bulk loading and exporting.
- [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshots and concurrency.
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, `SKIP LOCKED`.
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — query plans and `ANALYZE`.
- [PostgreSQL Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity` and transaction states.
- [PostgreSQL Runtime Client Settings](https://www.postgresql.org/docs/current/runtime-config-client.html) — timeouts and session settings.

The `/current/` links point to the latest PostgreSQL documentation; driver properties can change across versions. Always verify in your target environment.

## 56. Summary

**JDBC batching and JDBC cursor fetching solve opposite sides of large-scale data processing: dispatching many commands to PostgreSQL and receiving many rows back from PostgreSQL.**

1. **`addBatch()`/`executeBatch()`** cut parameter transmission overhead; they do not by themselves define atomicity.
2. **Batch chunks differ from transaction chunks.** Committing every chunk allows partial job completion, requiring checkpoints and idempotency.
3. **`BatchUpdateException`/update counts alone do not prove which rows committed.** Roll back and verify business state.
4. **`reWriteBatchedInserts` is a pgJDBC-specific optimization**; test rewrite conditions and generated-key mapping carefully.
5. **`COPY` excels at massive bulk loads**, typically paired with staging and merge steps for validation and conflict handling.
6. **`setFetchSize(n)` is not `LIMIT`.** In pgJDBC, cursor fetching usually requires **`autoCommit=false`**, a forward-only `ResultSet`, a positive `fetchSize`, and a compatible query/protocol.
7. **SQL `DECLARE`/`FETCH` differs from pgJDBC-managed cursors/portals**; Java usually needs only a properly configured `ResultSet`.
8. **Streaming does not save RAM** if the application accumulates every row or individual rows are huge.
9. **Cursors carry transaction, snapshot, and pool costs**; enforce deadlines and concurrency limits to protect `VACUUM` and other traffic.
10. **Keyset pagination** fits checkpointed/resumable exports, while cross-page consistency under concurrent writes demands explicit design.
11. **Real tuning measures SQL, server, driver, Java, and sink end-to-end** instead of merely picking the largest batch or fetch number.

With clear **batch units, transaction boundaries, cursor lifecycles, and `ResultSet` consumption**, Java applications can write and read PostgreSQL at scale while keeping memory, consistency, and operational resources under control.
