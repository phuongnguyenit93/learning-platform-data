# Batching Imports with Transactions and Tracking Progress

In Neo4j, data is modeled as a **property graph** consisting of nodes, relationships, labels, relationship types, and properties. When importing hundreds of thousands or millions of records from CSV files, APIs, or external systems, a single transaction containing the entire dataset can consume excessive memory, hold locks for too long, and be difficult to recover when errors occur. **Splitting data into batches**, processing each batch in its own transaction, and recording progress makes imports controllable, measurable, and safer to rerun.

This lesson belongs to the **Data Import** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, focusing on using **`LOAD CSV` with `CALL { ... } IN TRANSACTIONS`** and actively batching from the **Java Driver**. It also covers identifying key design, constraints, handling bad records, **committed** progress, resuming after interruptions, and choosing batch sizes. Cypher examples target Neo4j 5; the `CALL (row)` subquery variable-import syntax requires Neo4j **5.23 or later**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why batched imports reduce rollback scope and help control transaction resources.
2. Use `LOAD CSV` and `CALL { ... } IN TRANSACTIONS OF n ROWS` to import nodes or relationships.
3. Choose an initial batch size, tune it from real measurements, and understand the trade-offs between too-small and too-large batches.
4. Distinguish between **source rows read**, **accepted rows**, **committed transactions/batches**, and **newly created nodes/relationships**.
5. Design a checkpoint mechanism to resume an import safely after errors using the Java Driver.
6. Monitor import activity and verify correctness with Cypher.

## 2. Why batch by transaction?

A transaction in Neo4j is an atomic unit: **either all changes in that transaction commit, or all roll back**. For large imports, batching changes the scope of that atomic unit:

~~~text
Source data (10,000 rows)
         |
         v
  [Batch 1: 1..1000] ------> TX 1: COMMIT
  [Batch 2: 1001..2000] ---> TX 2: COMMIT
  [Batch 3: 2001..3000] ---> TX 3: ROLLBACK (if error)
  [Batches 4..10] ---------> Not run yet (if job stops)
~~~

If an error occurs in the third batch, the two already-committed batches **remain persisted**; Neo4j does not roll back the entire import job. Consequently, **the overall import job is no longer a single atomic transaction**. That is an intentional trade-off to limit resource hold times and make retrying unfinished portions practical.

| Approach | Benefits | Risks / limitations |
|---|---|---|
| One transaction for all data | All-or-nothing | May consume excessive memory/locks; a late error loses all progress |
| Many small transactions | Limits failure blast radius, enables commit tracking | Overhead of creating/committing many transactions; requires resume strategy |
| Larger batched transactions | Lower commit overhead | Each failure rolls back more rows; higher memory and lock duration |

There is no single optimal batch size for every dataset. It depends on row size, number of relationships created, `MERGE` complexity, indexes, storage speed, memory, and concurrent write load.

## 3. Preparing the data source and identifying keys

Suppose we need to import customers and orders. Two sample CSV files:

**`customers.csv`**

~~~csv
customerId,name,region
C001,An,Ha Noi
C002,Binh,Ho Chi Minh
C003,Chi,Da Nang
~~~

**`orders.csv`**

~~~csv
orderId,customerId,totalAmount
O001,C001,150000
O002,C001,90000
O003,C003,350000
~~~

Expected graph:

~~~text
(C001:Customer {name:'An'})  --[:PLACED]--> (O001:Order {totalAmount:150000})
                             \-[:PLACED]--> (O002:Order {totalAmount:90000})
(C002:Customer {name:'Binh'})
(C003:Customer {name:'Chi'}) --[:PLACED]--> (O003:Order {totalAmount:350000})
~~~

So that `MERGE` finds the right node on reruns and avoids creating multiple nodes with the same key, create constraints **before** importing on the practice database:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

**Why are constraints needed?** `MERGE (c:Customer {customerId: ...})` matches an existing pattern or creates a new node. A uniqueness constraint enforces uniqueness on `customerId` and provides a backing index for lookups. Without a constraint, duplicate records or two competing write streams can produce unwanted data; `MERGE` does not replace full uniqueness enforcement, especially when duplicate data already exists.

### Where does Neo4j read CSV files from?

The examples use `file:///customers.csv` or `file:///orders.csv`. These paths are evaluated from the **Neo4j server's perspective**, typically inside the configured import directory—**not by default a folder on the machine running Neo4j Browser or a Java client**. In Docker, files must be mounted into the container environment properly. Cloud services may require HTTPS sources or other ingestion mechanisms rather than local file access.

`LOAD CSV WITH HEADERS` uses the first line as property keys on `row`; CSV fields are initially read as **strings or null**. Explicitly convert numbers and datetimes rather than expecting Neo4j to guess types.

## 4. Batch-importing nodes with `LOAD CSV` and `CALL ... IN TRANSACTIONS`

On Neo4j **5.23+**, the statement below reads each CSV row, keeps only customers with valid keys, and processes rows across multiple transactions:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
CALL (row, customerId) {
    MERGE (c:Customer {customerId: customerId})
    SET c.name = row.name,
        c.region = row.region
} IN TRANSACTIONS OF 1000 ROWS;
~~~

`CALL (row, customerId)` imports variables from the outer query into the subquery. `IN TRANSACTIONS OF 1000 ROWS` groups rows **entering the subquery call** into batches of up to 1,000 rows and processes each batch in a separate transaction. With only the 3 sample rows, the job completes in one transaction; with 10,000 valid rows, there are typically 10 batches of 1,000 rows.

**Important:** `CALL { ... } IN TRANSACTIONS` must run in an **implicit (auto-commit) transaction**. Do not place this statement inside `BEGIN ... COMMIT`, an explicit transaction, or a Java Driver `session.executeWrite(...)` callback. In Neo4j Browser, you may need to prefix the query with `:auto` (e.g., `:auto LOAD CSV ...`); in the Java Driver, run it as an auto-commit query with `session.run(...)`. If your tooling wraps every query in an explicit transaction, adjust the execution mode.

On Neo4j 5 versions prior to 5.23 (where `CALL { ... } IN TRANSACTIONS` is supported without the `CALL (row)` scope clause), use the older importing syntax:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
CALL {
    WITH row, customerId
    MERGE (c:Customer {customerId: customerId})
    SET c.name = row.name,
        c.region = row.region
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Keep two concerns distinct:** `1000 ROWS` defines commit boundaries; `MERGE` defines how each node is matched or created to support reruns. Replacing `MERGE` with `CREATE` can be faster in some cases, yet reruns may create duplicate nodes and hit constraint conflicts. Only use `CREATE` when the data and ingestion strategy guarantee it is safe.

### Result after importing the sample file

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IN ['C001', 'C002', 'C003']
RETURN c.customerId AS customerId,
       c.name AS name,
       c.region AS region
ORDER BY customerId;
~~~

On a test database that was empty before import, the result is three customers: `C001`, `C002`, and `C003`. If the source CSV contains rows with duplicate keys, the number of processed rows can be **greater** than the number of resulting nodes, because `MERGE` updates existing nodes.

## 5. Importing relationships: splitting the workflow into clear stages

When data represents relationships, establish endpoint nodes first. For example, import orders only when the referenced customer already exists. First check for missing customer keys in the CSV:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row,
     trim(coalesce(row.customerId, '')) AS customerId
WHERE customerId <> ''
OPTIONAL MATCH (c:Customer {customerId: customerId})
WITH row, c
WHERE c IS NULL
RETURN row.orderId AS orderId,
       row.customerId AS missingCustomerId
LIMIT 20;
~~~

This query detects only **part** of reference errors (rows with a non-empty `customerId` that lacks a matching node). Separately check for empty keys, duplicate IDs, and invalid monetary amounts.

Once the data is validated, import orders and relationships:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row,
     trim(coalesce(row.orderId, '')) AS orderId,
     trim(coalesce(row.customerId, '')) AS customerId,
     toIntegerOrNull(row.totalAmount) AS totalAmount
WHERE orderId <> ''
  AND customerId <> ''
  AND totalAmount IS NOT NULL
  AND totalAmount >= 0
CALL (orderId, customerId, totalAmount) {
    MATCH (c:Customer {customerId: customerId})
    MERGE (o:Order {orderId: orderId})
    SET o.totalAmount = totalAmount
    MERGE (c)-[:PLACED]->(o)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Import order:** import customers first, then import orders and links. `MATCH (c:Customer ...)` inside the subquery matches nothing if a row references a missing customer: that row will **not create an Order or relationship**, and does not raise an error by default. Therefore, **count and report invalid source rows before and after import**, rather than treating statement completion as proof that every row was written.

With valid sample data, verification query:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE o.orderId IN ['O001', 'O002', 'O003']
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       o.totalAmount AS totalAmount
ORDER BY orderId;
~~~

There must be three accurate link pairs, with total amount `150000 + 90000 + 350000 = 590000`. If the same order ID appears with different customers in the file, define business conflict rules before importing; `MERGE (c)-[:PLACED]->(o)` does not by itself enforce that each Order has only one owner.

## 6. Tracking progress: distinguishing four metrics

A message like "imported 10,000 records" is easily misleading. A pipeline using `WHERE`, `MERGE`, and multiple transactions must distinguish:

| Metric | Meaning | Equals newly created nodes? |
|---|---|---|
| **Source rows** | Rows present in source after headers, including bad rows | No |
| **Accepted rows** | Rows passing validation and sent into the import step | No |
| **Committed input rows** | Source rows belonging to batches that committed successfully | No |
| **Created/updated entities** | Nodes/relationships actually created or updated | Not necessarily equal to the three above |

For example, a file has 10,000 rows, 100 invalid rows, and 200 duplicate-key rows. You may have 9,900 accepted rows yet **fewer than 9,900 new nodes** if `MERGE` matches existing nodes. If a transaction rolls back, its rows must not be added to the **committed** count.

### 6.1. Inspecting running jobs with `SHOW TRANSACTIONS`

On Neo4j 5, with appropriate transaction-viewing privileges, you can inspect active transactions:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, status, elapsedTime
WHERE currentQuery CONTAINS 'LOAD CSV'
RETURN transactionId, status, elapsedTime, currentQuery;
~~~

This command shows whether a query is still running, transaction elapsed time, and the status reported by Neo4j. **It is not an exact completion percentage meter**: already-committed transactions may no longer appear in the list, and total committed CSV rows across batches cannot be inferred from elapsed time alone. Nor should `elapsedTime` be assumed to predict total job completion time.

### 6.2. Counting target data for reconciliation

After importing, inspect persisted data:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS totalCustomerNodes;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS totalOrderNodes,
       coalesce(sum(o.totalAmount), 0) AS totalOrderAmount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

Target counts are meaningful when a practice database holds only the dataset being imported, or when data carries a dedicated `runId`/label/key set separating it from older data. In a production database, counting an entire label does not necessarily reflect the progress of a **specific import run**.

### 6.3. Estimating `LOAD CSV` progress

If you know the **total valid rows** in a CSV snapshot and track the **actually committed rows**, you can compute:

~~~text
progress_percent = committed_valid_rows / total_valid_rows * 100
~~~

Row counts in a source file can be counted before import or computed in the data-prep pipeline. However, `CALL { ... } IN TRANSACTIONS` **does not automatically create durable business checkpoints per batch**. If you need accurate progress reporting, resumability by `batchNo`, and error logs, manage batches at the application layer as shown next.

## 7. Application-managed batching and checkpointing with the Java Driver

When a Java application needs exact progress updates, it can split the file into batches, attach `runId` and `batchNo`, and use **one managed write transaction per batch**. Within **the same transaction**, write both the business data and an `:ImportBatch` checkpoint marker. If the transaction rolls back, **both the data and the checkpoint for that batch roll back**.

Checkpoint node design:

~~~text
(:ImportBatch {
  batchKey: 'customers-20261125:0',
  runId: 'customers-20261125',
  batchNo: 0,
  state: 'DONE',
  rowsSubmitted: 1000,
  finishedAt: datetime(...)
})
~~~

`batchKey` is a stable unique key, commonly combining `runId` and `batchNo`. The `DONE` record is created **only after the batch's statements succeed and within the same transaction**. Prepare a constraint to prevent duplicate-key checkpoint nodes:

~~~cypher
CREATE CONSTRAINT import_batch_key_unique IF NOT EXISTS
FOR (b:ImportBatch)
REQUIRE b.batchKey IS UNIQUE;
~~~

Java Driver 5.x example for a customer batch. The input `rows` is a list of maps whose **keys have been validated and data types normalized** by the application; outer caller code streams the CSV, groups up to 1,000 valid rows per batch, and invokes this method for each group:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

public final class CustomerBatchImporter {
    private CustomerBatchImporter() {}

    public static void writeBatch(
            Session session,
            String runId,
            long batchNo,
            List<Map<String, Object>> rows) {

        final String batchKey = runId + ":" + batchNo;

        // Single transaction for both data and checkpoint of the same batch.
        session.executeWrite(tx -> {
            boolean done = tx.run("""
                    MATCH (b:ImportBatch {batchKey: $batchKey})
                    WHERE b.state = 'DONE'
                    RETURN b.batchKey AS batchKey
                    """, Values.parameters("batchKey", batchKey))
                    .hasNext();

            if (done) {
                return null; // This batch already committed in a previous run.
            }

            tx.run("""
                    UNWIND $rows AS row
                    MERGE (c:Customer {customerId: row.customerId})
                    SET c.name = row.name,
                        c.region = row.region
                    """, Values.parameters("rows", rows)).consume();

            tx.run("""
                    MERGE (b:ImportBatch {batchKey: $batchKey})
                    SET b.runId = $runId,
                        b.batchNo = $batchNo,
                        b.state = 'DONE',
                        b.rowsSubmitted = $rowsSubmitted,
                        b.finishedAt = datetime()
                    """, Values.parameters(
                        "batchKey", batchKey,
                        "runId", runId,
                        "batchNo", batchNo,
                        "rowsSubmitted", rows.size())).consume();

            return null;
        });
    }
}
~~~

**Important code semantics:**

1. `session.executeWrite(...)` creates a managed transaction that retries on certain transient errors according to driver configuration. Everything inside the callback must be safe to **re-execute**—do not send emails, write external files, or increment external counters inside the callback.
2. `UNWIND $rows` expands a parameter list into multiple rows within **one** transaction. This is batching managed by the **Java Driver**, unlike `CALL ... IN TRANSACTIONS` where the **Cypher engine** splits transactions.
3. `MERGE` on `customerId` plus a uniqueness constraint prevents duplicate nodes on rerun when data and keys match. If source rows share a key with differing values, update rules still need to be defined.
4. The `ImportBatch` marker is written in the **same transaction**. If the batch fails before commit, no new `DONE` marker appears; if the application loses connectivity right after commit and does not know the outcome, a rerun detects the existing marker.
5. `rowsSubmitted` counts only **rows passed into the batch by the application**, not newly created nodes. This example assumes the application validated rows before calling; to count Cypher-accepted rows or actual created nodes, add dedicated metrics.

The example is designed for a **sequential runner**. Do not run two concurrent workers on the same `runId`/`batchNo` without proper coordination and locking; reading a marker and then writing within a transaction does not create a "distributed lock" guaranteeing single-worker ownership. Furthermore, a `DONE` marker is trustworthy only when **the source snapshot, cleaning rules, and mapping for that `runId` have not changed**.

### Invoking from a source-reading pipeline

CSV reading can use a Java CSV library (to handle commas, quotes, and encoding properly). Conceptual flow:

~~~text
Fixed runId + fixed source snapshot
              |
    read CSV and normalize each row
              |
         group up to 1,000 rows
              |
    writeBatch(session, runId, batchNo, rows)
              |
    transaction committed successfully?
       /                         \
     yes                          no
      |                            |
write/read DONE checkpoint    log error outside transaction /
advance to next batchNo       stop or retry per policy
~~~

There is no need to load the entire CSV into memory. Keeping only the current batch and immutable source metadata is the advantage of streaming. On rerun, reuse the same `runId` and batching boundaries so completed `batchKey` markers are recognized.

## 8. Querying progress from committed checkpoints

For Java-managed batches, the following query returns the number of committed batches and total input rows accepted by those batches:

~~~cypher
MATCH (b:ImportBatch {runId: $runId})
WHERE b.state = 'DONE'
RETURN count(b) AS committedBatches,
       coalesce(sum(b.rowsSubmitted), 0) AS committedInputRows,
       max(b.finishedAt) AS latestCommittedAt;
~~~

Suppose the source snapshot has **10,000 valid rows** split into 10 batches of 1,000 rows each. If the query returns `committedBatches = 7` and `committedInputRows = 7000`, **commit progress by input rows** is `7000 / 10000 = 70%`. These are illustrative figures after 7 batches, not real system measurements.

On a monitoring dashboard, you can display:

| Field | Example | What to interpret accurately |
|---|---:|---|
| Total accepted rows | 10,000 | Taken from the validated snapshot |
| Committed input rows | 7,000 | Sum of `rowsSubmitted` across `DONE` markers |
| Committed batches | 7/10 | Committed batches out of total defined batches |
| Progress | 70% | Commit progress by source rows |
| Created customers | *Measured separately* | Do not infer from 7,000 if `MERGE` updates existing nodes |
| Failed batch | *From application report* | A rolled-back transaction will not create a `DONE` marker |

If the final batch has fewer than 1,000 rows, do not use `committedBatches / totalBatches` to infer exact completed rows; sum `rowsSubmitted` from actual batches instead.

### Distinguishing progress from source state

A `DONE` checkpoint does not prove the source file has remained unchanged since import. A robust strategy ties each run to a **snapshot name/version**, **file checksum**, **total valid row count**, and **transformation rule version**. If the source changes, generate a new `runId` or follow an explicit update plan instead of reusing markers from older data.

## 9. Error handling, rollback, and resuming imports

| Scenario | What can happen | How to handle |
|---|---|---|
| CSV missing `customerId` key | `MERGE` cannot identify the node properly | Validate and quarantine bad rows before adding to a batch |
| Non-numeric monetary amount | `toIntegerOrNull` returns `null`; row may be filtered | Count and persist rejected-row reports; do not treat as imported |
| A batch hits a constraint error | That batch's transaction rolls back | Fix data/logic and rerun the batch; committed batches remain |
| Network drop after server commits | Application may not know the batch succeeded | Query the DB checkpoint, then decide whether to skip or rerun |
| Job stops at batch k | Prior batches already committed | Read `DONE` markers and resume missing batches on the same snapshot |
| Row duplicates key of existing data | `MERGE` may match and update the old node | Define update policies and protect keys with constraints |
| Multiple threads run the same batch | Lock contention or duplicate writes | Enforce single batch owner or coordinated locking |

**With `CALL { ... } IN TRANSACTIONS`**, if a job fails mid-way, previously committed batches may still exist. Depending on the Neo4j version, error-handling syntax and transaction status reporting vary. Never assume the entire source rolled back, nor that batches after the failure were processed. Verify target data and rerun with idempotent writes, or use application-level checkpoints as in Section 7 when exact per-batch recovery is required.

**Idempotent** here means rerunning the same batch with the same data does not create unintended extra nodes or relationships. Using `MERGE` on stable keys and appropriate relationship `MERGE`s is part of the solution, but is not enough if updates use `SET x = x + 1`, unguarded `CREATE`, changing source data, or one business key mapping to multiple nodes.

## 10. Choosing batch size and optimizing performance

Values such as **100**, **500**, **1,000**, and **5,000** rows/batch are starting configurations **to benchmark**, not Neo4j-guaranteed optimal thresholds. Start moderate (e.g., 1,000 rows/batch), then measure:

- **Batch count and committed transaction count:** too many tiny batches add commit overhead.
- **Time per batch and rows/second:** measure on representative data rather than drawing conclusions from the first batch alone.
- **Memory per transaction and lock hold time:** large batches or rows creating many relationships consume significant resources.
- **Rollback/retry cost:** large batches force more rows to be redone upon error.
- **Impact on other workloads:** run in parallel only after checking lock contention, resources, and write load.

| Symptom | Possible cause | Tuning direction |
|---|---|---|
| Many batches, high commit overhead | Batch too small | Test increasing batch size in controlled steps |
| Memory or transaction duration spikes | Batch too large, or each row creates many nodes/edges | Reduce batch size, simplify per-row operations |
| Slow `MERGE` on large datasets | Missing index/constraint on lookup key | Create appropriate constraints/indexes before import |
| Single error forces re-running lots of data | Large batch or unvalidated source | Reduce batch size, validate early |
| Batches contend on the same node | Multiple writers updating a shared key | Reduce concurrency, partition source by key |

A batch of 1,000 simple customer rows and 1,000 rows creating many relationships via complex pattern matches have very different costs. Do not tune solely on `ROWS` while ignoring the work inside each row.

### Indexes/constraints before or after import?

For `MERGE` on identifying keys, a **uniqueness constraint** or suitable index speeds up matching existing nodes and enforces identity consistency. If you use only `CREATE` for an initial load of brand-new data, some strategies defer secondary indexes until after import to reduce write overhead. That is a decision about **correctness guarantees and total cost**, not a rule to "always drop indexes for speed."

For very large initial loads into a new database, also evaluate **`neo4j-admin database import`** under the offline workflow supported by your version. That tool serves a different scenario than online imports into a live database and does not share the Cypher checkpointing mechanism shown here.

## 11. Verifying correctness after import

In a practice database containing only the three sample customers and three orders, check counts:

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customers;  // 3 if only sample data is present
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orders,
       coalesce(sum(o.totalAmount), 0) AS totalAmount;
// orders = 3, totalAmount = 590000 if only sample data is present
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
// 3 if only sample data is present
~~~

Check for missing links:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
    MATCH (:Customer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderWithoutCustomer
LIMIT 20;
~~~

With valid sample data, the result must be empty. On real data, also cross-check quarantined bad records, source totals/identifiers, duplicate-key counts, and updated nodes. If an import is designed to append only a subset of data, do not use total database node counts as the sole verification criterion.

### Re-running to test idempotency

On the practice database:

1. Record current counts of customers, orders, and relationships.
2. Rerun the exact same data using the `MERGE` commands from Sections 4–5.
3. Recount: node and relationship counts **must not increase** when keys and relationships have not changed.
4. Try changing one `name` in a copy of the source to observe how the `SET` policy updates it; no longer treat that as the same snapshot.

## 12. Common mistakes and fixes

| Mistake | Consequence | Right approach |
|---|---|---|
| Running `CALL ... IN TRANSACTIONS` inside an explicit transaction | May be rejected because an implicit transaction is required | Use auto-commit; for explicit transaction control, use `UNWIND $rows` and the Java Driver |
| Reading `file:///...` from client machine | File not found on the Neo4j server | Place/mount the file in an allowed server source, or use a supported URL |
| Using `MERGE` on large data without a unique key | Slow and hard to prevent duplicate entities | Design keys and create appropriate constraints/indexes |
| Using `CREATE` and rerunning the job after failure | Spawns duplicate nodes/relationships | Use idempotent operations or resume only uncommitted batches |
| Treating CSV row count as new node count | Wrong because filtering and `MERGE` may update existing nodes | Track source, accepted, committed, and created counts separately |
| Counting the entire label as progress of one run | Mixes old data with newly imported data | Tag runs/snapshots/batches or reconcile key sets |
| Writing checkpoints outside the data transaction | `DONE` marker may appear without data, or vice versa | Write checkpoints and data in the same transaction |
| Reusing checkpoints after the CSV was edited | Wrongly skips batches or produces inconsistent imports | Bind runs to snapshot/checksum/version |
| Picking a huge batch size upfront | Raises OOM risk and rollback duration | Start moderate, benchmark, then tune |
| Not checking for missing referenced relationships | Silently drops Orders or corrupts the model | Validate source keys and reconcile counts after import |

## 13. Practice exercises

### Exercise 1 — Computing transaction count

A CSV has **12,350 rows**; after validation, **350 rows are invalid**. The query feeds only valid rows into `CALL ... IN TRANSACTIONS OF 1000 ROWS`. How many transactions will be needed for the data batches?

<details>
<summary>Suggested answer</summary>

There are `12,350 - 350 = 12,000` valid rows. At 1,000 rows per batch, there are **12 transactions** (assuming no other factors alter input rows). This is the count of executed batch transactions, not newly created nodes.

</details>

### Exercise 2 — Analyzing a mid-import failure

A source has 4,500 valid rows and batch size 1,000. The first two batches succeed; the third batch fails and the job halts. Without an automatic resume mechanism, can you say "the whole job rolled back"? What must be done before rerunning?

<details>
<summary>Suggested answer</summary>

No. The two committed batches remain persisted; only the third batch rolled back and the remaining batches were not processed. Inspect persisted data/checkpoints, fix the root cause, verify the source data has not changed, and then rerun safely with `MERGE` or resume only uncommitted batches.

</details>

### Exercise 3 — Designing a checkpoint

You implement a Java Driver import with 500-row batches and want a progress dashboard showing **committed source rows**. Identify the minimum fields needed on `:ImportBatch` and explain why the checkpoint must be written in the same transaction as the batch's nodes and relationships.

<details>
<summary>Suggested answer</summary>

Each batch should have a unique `batchKey`, `runId`, `batchNo`, `state`, and `rowsSubmitted`; also record an observed commit timestamp and source version/snapshot at the run level. If data rolls back while a `DONE` marker was written separately, the pipeline might skip an unimported batch; if data commits without the marker, the app might rerun it. Writing both in the same transaction yields one atomic commit unit and makes recovery verifiable.

</details>

### Exercise 4 — Choosing a strategy

A system receives nightly customer updates into a live database, each record having a unique key. Would you pick `neo4j-admin database import` or batching via Cypher/Java Driver? Why? If you instead had to load 50 million initial nodes into a brand-new database not yet serving queries, would your choice change?

<details>
<summary>Suggested answer</summary>

Nightly updates into a running database fit online batched imports using `MERGE` and constraints. For a massive initial load into a new database, evaluate the offline `neo4j-admin database import` tool according to your version and operational requirements. There is no single universally best choice; evaluate downtime windows, data sources, update rules, and data verification.

</details>

## 14. Key takeaways

- **Batches are transaction boundaries:** a failure in one batch does not automatically roll back previously committed batches.
- **`CALL { ... } IN TRANSACTIONS OF n ROWS`** is convenient for server-side batched `LOAD CSV`, but requires an implicit transaction.
- **Java Driver `executeWrite` + `UNWIND $rows`** fits when the application wants to coordinate each batch itself and write checkpoints in the same transaction.
- **Progress is meaningful only when tied to actual commits** and when source rows, valid rows, committed rows, and newly created nodes/relationships are kept distinct.
- **`MERGE`, stable keys, and uniqueness constraints** support safe reruns; you must still manage duplicates, missing references, and snapshot versions.
- **Tune batch size by measuring** duration, memory, locks, retries, and system impact—never pick a fixed number for all workloads.
