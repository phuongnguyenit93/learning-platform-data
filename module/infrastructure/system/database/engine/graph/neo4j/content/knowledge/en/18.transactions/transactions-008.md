# Batching Data Writes by Size and Transaction Duration in Neo4j

## Objectives

Neo4j stores data as a **property graph** of nodes, relationships, and properties. When importing hundreds of thousands of products, syncing millions of relationships, or updating a large graph network, putting every operation into **a single long transaction** increases memory pressure, lock hold times, and rollback rework costs. Conversely, opening **one transaction per row** typically incurs high server round-trip overhead.

In the **Transactions** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, this lesson focuses on splitting write workloads into bounded **batches**, covering Cypher, the Neo4j Java Driver, and Spring Data Neo4j applications. After this lesson, you will be able to:

- Distinguish batch limits by **row count**, **estimated byte size**, and **time budget**.
- Understand commit/rollback boundaries and the impact of **earlier batches already committing** when a later batch fails.
- Write `CALL { ... } IN TRANSACTIONS` statements for server-side Cypher batching and choose Java-side batching when fine-grained control is needed.
- Tune batch sizes empirically, design **rerunnable** writes, and control timeouts and contention errors.

> **Scope:** Examples use Neo4j Cypher 5 and Neo4j Java Driver 5.x. The `CALL (row) { ... }` syntax uses the *variable scope clause* introduced in Neo4j 5.23; an alternative for older versions appears in Section 4. If your application runs Cypher 25 or another release, consult version-matched documentation.

## 1. Why Batch Writes?

Imagine an e-commerce graph storing:

```text
(:Customer {id})
    └──[:PLACED]──> (:Order {id, placedAt})
                           └──[:CONTAINS]──> (:Product {sku, name, price})
```

An import might load 500,000 products followed by millions of `CONTAINS` relationships. Each `MERGE` or `SET` can require index lookups, record reads/writes, and transaction log entries. Operations within **one transaction** must all succeed or all roll back together; if that transaction is huge, all of its work must be redone upon failure.

There are three common strategies:

| Strategy | Characteristics | Consequences |
| --- | --- | --- |
| One transaction for all 500,000 rows | Preserves whole-import atomicity | Resource/lock/rollback risks and prolonged duration |
| One transaction per row | Each failure affects one row | Huge setup/commit and network round-trip overhead |
| Multiple transactions, each with hundreds to thousands of rows | Balances fixed overhead against per-transaction resources | Must accept and manage partial commits |

Application flow diagram:

```text
Data source
    ↓ validate + normalize
Record queue/buffer
    ↓ reached row count, byte size, or buffer age
One batch sent to one transaction
    ↓ commit succeeds
Record progress → take next batch
    └── on error: safe retry / log failure / resume from checkpoint
```

**Decision point:** if a batch holds 500 rows, **the commit unit is those 500 rows**. Completing the first batch does not put subsequent batches into the same transaction. An error in batch 8 does not automatically roll back the 7 earlier committed batches.

## 2. Three Limits to Consider Together

### 2.1. Rows per Batch

The simplest limit is `maxRows`. With `N` input rows and `B` rows per batch:

```text
Batch count = ceil(N / B)
```

For example, `N = 4,800` and `B = 500` produce **10 batches**: 9 batches of 500 rows and 1 batch of 300 rows. Row count helps predict commit frequency, yet **does not reflect the actual size of each record**. A node with only `sku` differs drastically from a node carrying dozens of properties and long strings.

### 2.2. Bytes per Batch

Add a `maxEstimatedBytes` threshold to prevent one batch from packing too much large data. Illustrative example:

| Case | Row count | Estimated input size per row | Total input size |
| --- | ---: | ---: | ---: |
| A: code + price | 500 | 1 KiB | ~500 KiB |
| B: many text fields | 500 | 100 KiB | ~49 MiB |
| C: many text fields | 2,000 | 100 KiB | ~195 MiB |

This is only an **estimate of input payload**, not Neo4j's actual transaction memory footprint. Server cost also includes touched entities, indexes, transaction state, log records, and query operator memory. There is no exact conversion factor from JSON/CSV size to transaction memory.

You can enforce a rule before appending a row:

```text
If batch is non-empty and (batchBytes + rowBytes > maxEstimatedBytes):
    send and commit current batch
    start new batch
append row to batch
```

If an individual row exceeds the limit, **split valid data at the business level** or reject it with a dedicated error; never silently exceed the cap while assuming the system remains safe.

### 2.3. Buffer Age and Transaction Execution Time

There are **two distinct clocks**:

1. **Buffer age:** the application has received a few rows without reaching `maxRows`/`maxEstimatedBytes`. After a threshold, it flushes the batch to cap latency.
2. **Transaction duration:** from starting processing/writes until commit or rollback finishes. This is a performance metric tied to transaction timeouts.

For example, an application sets `maxRows = 500`, `maxEstimatedBytes = 1 MiB`, and `maxBufferAge = 2 seconds`. When rows arrive slowly, it may flush 20 rows after 2 seconds; when rows are large, it may flush 30 rows near 1 MiB; when data is small and fast, it flushes 500 rows.

**Do not confuse buffer age with transaction timeout.** A timeout can abort an overly long transaction; it **does not automatically commit partial progress**. To adapt batch size dynamically by execution time, measure completed transactions and adjust **the next batch**.

## 3. Practice Setup

Run examples only in a practice database. We use the `:Product` label to stay focused on batching without creating too many node/relationship types at once.

Create a business key constraint (run separately **before** ingestion):

```cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
```

This constraint enables index-backed lookups by `sku` and prevents two `Product` nodes from sharing the same `sku`. Input must provide a non-null `sku`; `MERGE` with a `null` key value will fail.

Before importing, inspect real data for duplicate keys, missing values, numeric types, and field sizes. To make the example rerunnable without creating duplicate nodes, use `MERGE` on the `sku` key.

## 4. Batching Directly in Cypher: `CALL ... IN TRANSACTIONS`

Neo4j supports subqueries executed across separate transactions via the `IN TRANSACTIONS` clause. Example creating or updating 2,500 products, 500 rows per transaction:

```cypher
UNWIND range(1, 2500) AS n
CALL (n) {
  MERGE (p:Product {sku: 'SKU-' + toString(n)})
  SET p.name = 'Product ' + toString(n),
      p.price = toFloat(n % 1000)
} IN TRANSACTIONS OF 500 ROWS;
```

Execution steps:

1. `range(1, 2500)` generates a list of 2,500 numbers; `UNWIND` produces 2,500 rows.
2. `CALL (n)` passes each row's `n` into the subquery.
3. `IN TRANSACTIONS OF 500 ROWS` creates **5 sub-transactions**, each processing up to 500 rows.
4. `MERGE` finds or creates the node by `sku`; `SET` updates properties.

Verify the count in a database containing only nodes created by this example:

```cypher
MATCH (p:Product)
WHERE p.sku STARTS WITH 'SKU-'
RETURN count(p) AS productsImported;
```

With clean sample data, the result is `2500`. If `Product` nodes with that prefix already existed, the count reflects all matching nodes currently in the database, not just the rows written by that statement.

### 4.1. Syntax Differences Across Versions

`CALL (n) { ... }` is the explicit input-variable syntax available from **Neo4j 5.23 onward**. In older Cypher 5 versions, you can write:

```cypher
UNWIND range(1, 2500) AS n
CALL {
  WITH n
  MERGE (p:Product {sku: 'SKU-' + toString(n)})
  SET p.name = 'Product ' + toString(n),
      p.price = toFloat(n % 1000)
} IN TRANSACTIONS OF 500 ROWS;
```

Importing variables via `WITH` inside a subquery is the older style and may trigger deprecation warnings in newer Neo4j releases; prefer the syntax matching your active version.

### 4.2. Crucial Constraint: Implicit Transactions

`CALL { ... } IN TRANSACTIONS` must run inside an **implicit transaction**. If you submit the entire statement inside an **explicit/managed transaction** (for example, inside a Java Driver `session.executeWrite(...)` callback), Neo4j rejects it because this mechanism manages its own sub-transactions.

- In **Neo4j Browser**, some versions require prefixing `:auto` before the query to run in auto-commit mode.
- In the **Java Driver**, use `session.run(cypher, parameters)` to execute an implicit-transaction query; consume the result to ensure completion.
- If your application already opens one transaction per batch, run `UNWIND $rows ... MERGE/SET` inside that transaction, and do **not** add `IN TRANSACTIONS`.

Each batch commits independently. If a batch fails after earlier batches committed, only uncommitted or failing transactions roll back. Never design logic assuming the entire import is a single atomic transaction.

### 4.3. Batching CSV Imports

Suppose a CSV file has header `sku,name,price` and sits where Neo4j config allows access via `file:///products.csv`:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS csv
WITH csv, toFloat(csv.price) AS parsedPrice
WHERE csv.sku IS NOT NULL
  AND trim(csv.sku) <> ''
  AND parsedPrice IS NOT NULL
CALL (csv, parsedPrice) {
  MERGE (p:Product {sku: csv.sku})
  SET p.name = csv.name,
      p.price = parsedPrice
} IN TRANSACTIONS OF 500 ROWS;
```

This query passes only filtered rows into the subquery, so **500 ROWS means 500 post-filter rows**, not necessarily 500 contiguous physical file lines. Invalid rows are skipped here; in production systems, route them to a separate error report instead of silently dropping data.

`LOAD CSV` is convenient for CSV sources accessible to Neo4j. Where the import directory lives, which URLs are permitted, permissions, and security settings depend on server configuration. A `file:///` path does not mean Neo4j reads files from a remote Java application machine.

### 4.4. Choosing Cypher Batch Sizes

`IN TRANSACTIONS OF 500 ROWS` controls by **row count**. It does not measure byte size and does not mean "commit every 2 seconds." When payloads vary widely in size or require fine-grained timing policies, **application-built batches** are usually easier to control.

## 5. Batching in the Java Driver: Rows + Bytes + Time

In Java or Spring Data Neo4j applications, a clear pattern is building input lists per batch and running **one managed transaction per batch**. The Java Driver provides `Session.executeWrite(...)`, whose callback may re-run on eligible retryable errors. Therefore, write statements must be safe to re-execute.

Example using Java 17+ and Neo4j Java Driver 5.x, assuming `Driver` is initialized and lifecycle-managed at the application layer:

```java
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.TransactionConfig;

public final class ProductBatchWriter {
    public record ProductInput(String sku, String name, double price) {}

    private static final int MAX_ROWS = 500;
    private static final long MAX_BYTES = 1L * 1024 * 1024;
    private static final long MAX_BUFFER_AGE_NANOS =
        Duration.ofSeconds(2).toNanos();

    private static final String UPSERT = """
        UNWIND $rows AS row
        MERGE (p:Product {sku: row.sku})
        SET p.name = row.name,
            p.price = row.price
        """;

    public static void importAll(
        Driver driver, Iterable<ProductInput> source
    ) {
        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            List<Map<String, Object>> batch = new ArrayList<>();
            long bufferedBytes = 0;
            long firstRowAt = 0;

            for (ProductInput item : source) {
                if (item.sku() == null || item.sku().isBlank()
                    || item.name() == null
                    || !Double.isFinite(item.price())) {
                    throw new IllegalArgumentException("Invalid product");
                }

                // Estimated size, not actual Bolt byte count.
                long rowBytes =
                    item.sku().getBytes(StandardCharsets.UTF_8).length
                    + item.name().getBytes(StandardCharsets.UTF_8).length
                    + Double.BYTES + 64L;
                if (rowBytes > MAX_BYTES) {
                    throw new IllegalArgumentException("Oversized row");
                }

                long now = System.nanoTime();
                if (!batch.isEmpty() &&
                    (bufferedBytes + rowBytes > MAX_BYTES
                     || now - firstRowAt >= MAX_BUFFER_AGE_NANOS)) {
                    writeBatch(session, batch);
                    batch.clear();
                    bufferedBytes = 0;
                }

                if (batch.isEmpty()) {
                    firstRowAt = System.nanoTime();
                }
                batch.add(Map.of(
                    "sku", item.sku(),
                    "name", item.name(),
                    "price", item.price()
                ));
                bufferedBytes += rowBytes;

                if (batch.size() >= MAX_ROWS
                    || bufferedBytes >= MAX_BYTES) {
                    writeBatch(session, batch);
                    batch.clear();
                    bufferedBytes = 0;
                }
            }

            if (!batch.isEmpty()) {
                writeBatch(session, batch); // Final partial batch.
            }
        }
    }

    private static void writeBatch(
        Session session, List<Map<String, Object>> buffered
    ) {
        // Copy before callback: data across retries must remain immutable.
        List<Map<String, Object>> rows = List.copyOf(buffered);
        TransactionConfig config = TransactionConfig.builder()
            .withTimeout(Duration.ofSeconds(15))
            .build();

        session.executeWrite(tx -> {
            tx.run(UPSERT, Map.of("rows", rows)).consume();
            return null;
        }, config);
    }
}
```

Characteristics of this example:

- `MAX_ROWS` caps record count; `MAX_BYTES` caps **estimated input payload**; `MAX_BUFFER_AGE_NANOS` caps buffer wait time **when the next record arrives**.
- `executeWrite` opens a driver-managed transaction for **each batch**; `consume()` forces query execution before the callback finishes.
- `withTimeout(15 seconds)` sets a timeout on **transaction duration**, not an instruction for Neo4j to commit after 15 seconds. If a timeout occurs, that batch must be treated as unconfirmed.
- `List.copyOf(buffered)` keeps the parameter list immutable across driver callback retries. `Map.of(...)` likewise creates unmodifiable maps.
- If the source pauses emitting rows, the loop receives no new events to evaluate `MAX_BUFFER_AGE_NANOS`. To **flush on schedule even when no new rows arrive**, use a queue and a timer-awakened scheduler/consumer.
- The byte estimate in code sums UTF-8 strings, numbers, and an assumed overhead; it **does not replace** real memory/latency measurements in Neo4j.

This example uses synchronous processing. Production systems should add batch logging, checkpointing, monitoring, and ingestion error reporting. Place `writeBatch` in the appropriate service layer when integrating with Spring Data Neo4j; do not wrap a multi-batch loop inside **one** shared `@Transactional` method if the goal is to commit each batch independently.

## 6. Transaction Duration: Measuring and Tuning Batches

If a 500-row batch normally finishes in 200 ms yet occasionally takes 20 seconds, a fixed batch size may not fit. Rather than guessing one "best" number for every system, benchmark on representative data.

### 6.1. Metrics to Collect

| Metric | How to use it |
| --- | --- |
| `rows/batch` and `estimatedBytes/batch` | Understand configuration and variance across records |
| `transactionDurationMs`, p50/p95/p99 | Spot uneven or target-exceeding slow batches |
| `rowsCommitted/s` | Measure business-meaningful throughput |
| Failed, retried, and timed-out batch counts | Identify oversized batches, conflicts, or failures |
| Memory, GC, CPU, disk I/O, transaction log | Pinpoint resource bottlenecks |
| Lock waits, deadlocks, concurrent transactions | Identify contention during parallel writes |

During a benchmark, change **one variable at a time**. For example, hold data, indexes, and concurrency constant while testing `B = 100, 500, 1,000, 2,000` rows. Compare throughput and p95 batch duration. If larger batches stop improving throughput while increasing timeouts or memory usage, lower the threshold.

### 6.2. Time Budget for a Batch

Suppose the operational target wants each transaction to finish in **about 1 second**, with a 15-second timeout configured. You can tune batches **after observing committed transactions**:

```text
If transaction duration p95 > target:
    reduce maxRows or maxEstimatedBytes for upcoming batches
If p95 is low, zero retries/timeouts, and headroom exists:
    gradually try raising batch size, always with a ceiling
If errors/timeouts appear:
    do not treat batch as committed; verify or retry safely
```

This is an **application-level tuning policy**, not an automatic feature of `IN TRANSACTIONS`. In practice, transaction duration also depends on indexes, expanded relationships, write volume, and lock contention. A timeout is a **safety guardrail against runaway transactions**, not a tool guaranteeing millisecond-exact commit times.

## 7. Consistency, Retries, and Recoverability

### 7.1. Independent Batches Do Not Form One "Super-Transaction"

Suppose there are four batches of 500 rows each:

| Batch | Outcome | State |
| --- | --- | --- |
| 1 | Committed successfully | 500 rows written |
| 2 | Committed successfully | 500 more rows written |
| 3 | Data type error, rolled back | Batch 3 is not recorded as written |
| 4 | Not yet run | Not written |

At this point, **the first 1,000 rows are committed**. If business rules require all 2,000 rows to succeed or fail together, reconsider the design: you cannot simply add `IN TRANSACTIONS` and retain whole-import atomicity.

### 7.2. Idempotency: Rerunning a Batch Without Duplicating Data

Use durable business keys:

```cypher
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price;
```

When the same `sku` is resent, `MERGE` locates the existing node and `SET` updates its values. A uniqueness constraint on `:Product(sku)` prevents duplicate nodes for the same key under concurrent writes.

Conversely:

```cypher
UNWIND $rows AS row
CREATE (p:Product {sku: row.sku, name: row.name});
```

`CREATE` always attempts to create a new node; with a unique constraint it fails on duplicate `sku`, and without a constraint it easily creates duplicate records on retry. Similarly, `CREATE (a)-[:BOUGHT]->(b)` can create duplicate relationships; design appropriate keys/relationships and use `MERGE` when you truly want to reuse a pattern.

**Do not assume every update is idempotent.** For example, `SET p.stock = p.stock + row.delta` can add inventory **twice** if the same event is retried. For additive/subtractive business operations, use a unique transaction/event ID and proper deduplication.

### 7.3. Checkpoints and Failed Batches

An ingestion pipeline can persist:

```text
jobId
sourceVersion
lastCommittedCursor (or last confirmed event ID)
totalRowsCommitted
lastError
```

Update the checkpoint only after **the batch is confirmed committed**. On replay, rely on business keys and idempotent operations to remain safe even if a commit succeeded on the server while the application lost connection before receiving the response. If the checkpoint lives outside Neo4j, updating the checkpoint and committing Neo4j do not automatically form a distributed transaction; the replay design must tolerate that gap.

If the source mutates over time, bind the cursor to a data version or stable ordering. Never treat "read 500 rows" as proof that those 500 rows committed.

### 7.4. Retries and Contention Errors

`executeWrite` can automatically retry **transient errors** per driver policy. Because callbacks may execute multiple times, never send emails, charge external services, or increment external counters inside the callback. Keep only suitable, rerunnable database writes inside the callback; external side effects require dedicated coordination.

With multiple writers, start testing at **low concurrency**. Updating the same nodes/relationships can cause lock waits, deadlocks, or longer transactions. Packing many rows per batch reduces commit count yet can lengthen lock hold times. Adding more threads does not always improve throughput.

## 8. Impact on Java Driver, Spring Data Neo4j, and Operations

### 8.1. Java Driver

- Using **one query with `UNWIND $rows` per batch** typically cuts network round-trips compared to running one query per row.
- Scope `Session` lifetime cleanly and close when done; never share sessions across threads not designed for sharing.
- Use `executeWrite` for application-managed transactions; use `session.run` if you genuinely need server-side `IN TRANSACTIONS`.
- Pass parameters instead of concatenating Cypher strings; validate `sku`, numeric values, and potentially `null` properties before writing.

### 8.2. Spring Data Neo4j

A `@Transactional` method normally wraps all writes inside it into **one transaction**, even if Java loops over 500 rows. To commit per batch, the transaction boundary must sit **around each batch**, for instance via a separate service call or `TransactionTemplate` where each batch runs its own independent transaction per the transaction manager configuration.

Watch out for Spring proxy **self-invocation**: calling another `@Transactional` method **on the same instance** can bypass the proxy, breaking expected transaction boundaries. Also plan for mid-batch write errors and resume logic. Never assume repository pagination or `saveAll(...)` automatically creates batches sized by your target bytes or duration.

### 8.3. Neo4j Operations

- Create indexes/constraints on keys used in `MERGE` **before** bulk ingestion; inspect `EXPLAIN` and `PROFILE` on test data to verify query plans and intermediate row counts.
- Monitor transaction memory, GC pressure, I/O, transaction logs, and lock wait times. Never predict server memory from CSV file size alone.
- For very large imports, evaluate `LOAD CSV` and `CALL { ... } IN TRANSACTIONS`; some deployments also have APOC if installed and permitted, though this exercise does not require APOC.
- When a batch fails, log complete error codes and batch identifiers for investigation; never blindly raise `maxRows` indefinitely or retry invalid input errors.
- Benchmark with realistic node/relationship structures, indexes, concurrency, and hardware; a batch size that works well for 10,000 simple products may not work for 10,000 heavily connected nodes.

## 9. Common Pitfalls

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Transaction too slow or times out | Batch too large, lock waits, missing index | Shrink batch, inspect query plan and contention |
| Data written even though job reported failure | Earlier batches already committed | Implement checkpoints, idempotency, and partial-success alerts |
| Rerun creates duplicate relationships | Using `CREATE` or missing business key | Use appropriate `MERGE` and unique constraints |
| 500-row batch still runs out of memory | Huge individual rows or broad entity traversals | Add byte limits and monitor transaction memory |
| 2-second buffer age configured, yet some data waits longer | Clock checked only when new rows arrive | Use a queue scheduler/timer if real-time flushing is required |
| Error using `IN TRANSACTIONS` inside `executeWrite` | Nested explicit/implicit transactions are unsupported | Pick either server-side or client-side batching properly |
| Retry double-counts inventory | `x = x + delta` update is not idempotent | Key by event ID, deduplicate, and redesign write |
| Larger batches stop increasing throughput | CPU/I/O/index/lock bottleneck reached | Measure p95, GC, locks, and tune concurrency limits |

## 10. Synthesis Exercise

**Scenario:** A service receives 12,300 products, each roughly 2 KiB of input, to ingest into Neo4j with a target batch cap of at most 1 MiB. Data occasionally arrives slowly, users want continuous progress visibility, and the job must be rerunnable after failures.

1. If you only apply `maxRows = 500`, how many batches result?
2. If each row is 2 KiB, how many KiB do 500 rows estimate to? Does that prove the transaction will use less than 1 MiB of Neo4j memory?
3. If batches 1–7 commit and batch 8 fails, can an outer statement roll back batches 1–7?
4. Choose the write approach when the source is a server-side CSV file; then choose the approach when data flows through a Java service needing byte and buffer-age limits.
5. Why are `MERGE` with unique `sku` and per-batch checkpoints needed?

**Suggested Answers:**

1. `ceil(12300 / 500) = 25` batches (24 batches of 500 rows, one batch of 300 rows).
2. `500 × 2 KiB = 1,000 KiB`, below 1 MiB in **estimated input size**; Neo4j transactions incur many other overheads, so you cannot conclude anything about actual server memory.
3. **No**. Batches 1–7 committed independently; business compensation is required if committed state must be reversed.
4. Server-side CSV: consider `LOAD CSV ... CALL { ... } IN TRANSACTIONS OF 500 ROWS`. Java service: build batches using `rows/bytes/bufferAge` thresholds and run one `executeWrite` transaction per batch.
5. `MERGE` on a stable key avoids duplicating nodes on replay; checkpoints record confirmed progress, combined with idempotency to handle ambiguous commit outcomes after dropped connections.

## 11. Pre-Production Checklist

- [ ] Business keys and unique constraints are defined; inputs contain no `null` keys.
- [ ] Every batch is bounded by row count and, where needed, estimated input bytes.
- [ ] **Buffer age**, **transaction duration**, and **transaction timeout** are clearly distinguished.
- [ ] One batching mechanism is chosen intentionally: server-side `IN TRANSACTIONS` or application-managed batch transactions.
- [ ] Succeeded batches, failed batches, retries, p95 duration, and throughput are instrumented.
- [ ] Job can safely rerun after partial commit without duplicating nodes/relationships or re-applying deltas.
- [ ] Tested with malformed data, missing values, oversized rows, final partial batch, dropped connections, and concurrent writes.
- [ ] Batch size benchmarked with production-representative indexes, data shapes, and concurrency.

## Conclusion

Batching data writes in Neo4j is fundamentally a decision about **transaction boundaries**. `CALL { ... } IN TRANSACTIONS` fits row-count batching in Cypher; batching in the Java Driver or Spring Data Neo4j lets you add byte caps, buffer age, timeouts, checkpoints, and retry policies. Bounding by **row count, size, and time** keeps resources and latency under control, yet does not automatically make the whole import one atomic transaction. Recovering cleanly from failures requires stable business keys, rerunnable writes, and monitoring against real workloads.

### References

- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
