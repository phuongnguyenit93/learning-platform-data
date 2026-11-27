# Measuring Import Speed and Pinpointing Bottlenecks at the Source, Network, or Server

## 1. Why measure each stage of data import separately?

Importing data into Neo4j can start from a CSV, API, message broker, relational database, or Java program. The final destination is **nodes**, **relationships**, and **properties** in a property graph. A slow import pipeline may be caused by:

- Slow source generation or reading, with expensive decompression or transformations.
- Network paths transferring data between the application, file source, and Neo4j constrained by latency, bandwidth, or connection errors.
- The Neo4j server needing more CPU, heap, page cache, disk I/O, transaction log capacity, or contending with locks, constraints, and indexes.

Within the `DATABASE_ENGINE_GRAPH_NEO4J` module, this **Data Import** topic shows how to **measure import speed and isolate bottlenecks at the source, network, or server**, covering `LOAD CSV`, Cypher `UNWIND` over the Neo4j Java Driver, and high-volume imports.

Practice examples use a dedicated test database, labels prefixed with `QA010`, and a small dataset with known answers. This is a controlled performance-measurement guide: timing numbers appear only when you run tests yourself; numbers labeled **hypothetical** illustrate how to interpret measurements and must never be taken as real Neo4j benchmark results.

After this lesson, you will know how to:

1. Properly define throughput, latency, error rate, and committed record counts.
2. Measure the source, network, Cypher execution, and commit stages independently.
3. Design controlled experiments to distinguish root causes of slowdowns.
4. Choose batch size, concurrency, and import method based on evidence.
5. Verify entity counts and idempotency to avoid "importing fast but importing wrong."

## 2. Diagrams of import paths: where do the source and network sit?

The data ingestion path differs between `LOAD CSV` and the Java Driver.

### 2.1. Java application sending records over Bolt

~~~mermaid
flowchart LR
    A["Source CSV/API/Database"] --> B["Java app: read, parse, normalize"]
    B --> C["Serialize and batch"]
    C --> D["App ↔ Neo4j network (Bolt/TLS)"]
    D --> E["Neo4j: Cypher, indexes/constraints, locks"]
    E --> F["Page cache, transaction log, disk"]
~~~

In this model, **the application** reads the source and sends each batch of records as a Cypher parameter, typically using `UNWIND $rows`. Slowness at the source starves the application of records to send; slowness on Bolt lengthens request/response transfer times; slowness inside Neo4j backs up requests even when batches are ready.

### 2.2. Neo4j running LOAD CSV

~~~mermaid
flowchart LR
    A["Local CSV in import dir or HTTP(S)"] --> B["Neo4j server: LOAD CSV"]
    B --> C["Parse and convert data types"]
    C --> D["Cypher: CREATE/MERGE"]
    D --> E["Indexes/constraints, transaction log, page cache/disk"]
    F["Browser/Java client"] -. "Send statement and receive summary" .-> B
~~~

With `LOAD CSV`, **the Neo4j server reads the CSV file**. When the URL is `file:///...`, the path is resolved on the **Neo4j server**, typically under the configured import directory—not on the user's laptop. When the URL is HTTP(S), **the Neo4j server itself fetches the CSV over the network**. The client only sends the statement and receives results, so Bolt bandwidth between the client and Neo4j is usually not where the full CSV payload travels.

> **First question when an import is slow:** which network path is the data actually traveling? Concluding "Java ↔ Neo4j network is slow" is wrong if the payload is mainly flowing along "HTTP CSV → Neo4j server."

## 3. Choosing the right speed metrics and start/end boundaries

Measure **work volume**, **elapsed time**, and **correctness** together:

| Metric | Definition | Note |
|---|---|---|
| Input rows/s | Source rows read/decoded per second | May include duplicate or rejected rows |
| Committed rows/s | Source rows processed and committed per second | Does not always equal newly created nodes |
| Created nodes/s | New nodes actually created per second | Can be 0 when re-running `MERGE` |
| Created relationships/s | New relationships created per second | Measure separately when loading edges |
| MiB/s | Actual data bytes transferred/read per second | Differs from rows/s because record sizes vary |
| Batch latency | Processing and commit time of one batch | Track median and p95, not just averages |
| Error/reject rate | Fraction of rows or batches failing | Never count failed records as successful imports |
| Backlog / queue depth | Records waiting between stages | Continuously growing queues pinpoint slower consumers |

Basic formulas:

\[
\text{rows/s}=\frac{\text{successfully processed rows}}{\text{measured seconds}}
\]

\[
\text{MiB/s}=\frac{\text{bytes transferred or read}}{1024^2\times \text{measured seconds}}
\]

\[
\text{Error rate}=\frac{\text{rejected or failed rows}}{\text{source rows}}\times100\%
\]

**Hypothetical example:** a run has 120,000 source rows, and 118,800 rows succeed in 60 seconds. Throughput is **1,980 committed rows/s**, and the failed-row rate is **1%**. If every 100 rows create 30 nodes and update 70 existing nodes, **created nodes/s** differs sharply from **rows/s**; never treat the two as interchangeable.

### 3.1. Distinguish "finished sending" from "finished committing"

Sending all request bytes does not mean transactions have committed. In a Java app, stop the batch timer only after receiving successful transaction confirmation—for instance, after `session.executeWrite(...)` returns. With `CALL { ... } IN TRANSACTIONS`, batches commit individually; if the final batch fails, earlier batches may have already committed.

For end-to-end reporting, measure from the start of reading input data (or a clearly defined job start) until **all required transactions are confirmed and results are reconciled**. When reporting only "Neo4j write time," exclude source discovery/download time and state that boundary explicitly.

### 3.2. Total pipeline time includes overlap

A pipeline can simultaneously read batch N+1, transmit batch N, and have Neo4j process batch N−1. Therefore:

\[
T_{\text{end-to-end}}\neq
T_{\text{source}}+T_{\text{network}}+T_{\text{server}}
\]

in general. Simple addition applies only when steps execute strictly sequentially with zero overlap. In a pipelined system, examine **each stage's throughput**, queue lengths, and boundary wait times. Under steady state, the stage with the lowest consumption rate usually bounds overall throughput.

## 4. Designing reliable measurements

Before optimizing, lock down conditions and define what "import succeeded" means.

1. **Define the workload:** node/relationship types, property counts, record size, row count, duplicate-ID rate, `MERGE` vs. `CREATE` ratio, and constraint/index levels.
2. **Separate initial inserts from updates:** first-time node creation behaves very differently from a second pass matching existing nodes. Never compare the two as the same test.
3. **Stabilize the schema:** create constraints/indexes before measuring and confirm they are `ONLINE`. Never add or drop indexes between two runs and attribute the difference to the network.
4. **Stabilize the environment:** record Neo4j version, edition, runtime, Java Driver, heap, page cache, CPU, RAM, IOPS, container limits, and concurrent load.
5. **Fix the inputs:** keep the exact same file/records/bytes, UTF-8 encoding, date formats, casting rules, and null handling.
6. **Measure the full lifecycle:** source open, parse/transform, batch assembly, send, server accept/commit, and confirmation; record errors and retries.
7. **Repeat and capture distributions:** include warmup runs, run multiple independent trials, report median/p95 for latency, and record total duration and overall job throughput.
8. **Isolate tests:** avoid production jobs competing for CPU, disk, heap, or locks. Never delete production data or restart production just to "cool down" caches.

Even with identical code, a **warm run** typically differs from a **cold run** due to page cache, query plan cache, JVM JIT, connection pools, and OS filesystem cache. If cache state cannot be fully controlled, label runs explicitly as "first observed" vs. "post-warmup" rather than claiming pure disk-cold numbers.

## 5. Small fixture with known answers to validate measurement

Create a UTF-8 file **`qa010_people.csv`** inside the import directory accessible to Neo4j. Sample data:

~~~csv
personId,name,city
P001,An,Ha Noi
P002,Binh,Da Nang
P003,Chi,Ha Noi
P004,Dung,Ho Chi Minh
P005,Ha,Da Nang
P006,Giang,Ha Noi
P003,Chi,Ha Noi
~~~

The file has **7 data rows**, yet only **6 unique IDs** because `P003` appears twice. Having one duplicate row checks whether your pipeline measures "source rows" or "created nodes."

Expected data after importing with `MERGE` on `personId`:

| Metric | Answer |
|---|---:|
| Input CSV rows (excluding header) | 7 |
| Distinct IDs | 6 |
| `QA010Person` nodes after first import | 6 |
| New nodes after re-importing the same file | 0 |
| Nodes with `city = 'Ha Noi'` | 3 |
| Nodes with `city = 'Da Nang'` | 2 |
| Nodes with `city = 'Ho Chi Minh'` | 1 |

Run in a **dedicated practice database**. Before creating data, clean up only this lesson's label/constraint if no other data shares those names:

~~~cypher
DROP CONSTRAINT qa010_person_id IF EXISTS;
~~~

~~~cypher
MATCH (p:QA010Person)
DETACH DELETE p;
~~~

Create the constraint so `MERGE` by ID has an appropriate lookup path and prevents duplicates:

~~~cypher
CREATE CONSTRAINT qa010_person_id IF NOT EXISTS
FOR (p:QA010Person)
REQUIRE p.personId IS UNIQUE;
~~~

Confirm the state of the backing index:

~~~cypher
SHOW INDEXES
YIELD name, type, state, owningConstraint
WHERE owningConstraint = 'qa010_person_id'
RETURN name, type, state, owningConstraint;
~~~

Start tests only after the index is `ONLINE`. Skipping the constraint changes both concurrent `MERGE` performance and integrity; never use an unconstrained setup to represent a production system requiring uniqueness.

> **Fixture size:** seven rows suffice to verify **correctness and measurement logic**, not representative performance numbers. For serious benchmarking, use larger datasets with realistic ID distributions, property counts, string lengths, and update ratios.

## 6. Measuring the source stage in isolation: read and parse without writing

### 6.1. With LOAD CSV

Start with a read-only check:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
RETURN count(row) AS inputRows;
~~~

Answer: `inputRows = 7`. This measurement includes Neo4j's CSV reading and parsing work, **without** creating nodes, relationships, or writing transaction logs as a real import does.

To force accessing column values, you can measure:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
RETURN
  count(row) AS inputRows,
  sum(size(row.personId)) AS totalIdChars;
~~~

For this fixture, `totalIdChars = 28` since all seven IDs are four characters long. This still does not simulate full transformation/normalization/writing, yet yields a verifiable **source-reading baseline**.

**Interpreting results:**

- If `LOAD CSV ... RETURN count(row)` is already slow, inspect the source file, readability, file delivery, and the **server → source** network path (for HTTP(S)).
- If reading/parsing is fast while actual importing is slow, suspect type conversion, `MERGE`, indexes, transaction log writes, locking, or batch settings.
- With `file:///`, read speed depends on the **Neo4j server's** filesystem. Do not blame that time on the Bolt network between Browser/Java client and the database.

An HTTPS URL can replace `file:///` when permitted by configuration. In that case, the "CSV read-only" test measures **network download + server-side parsing** combined. To separate those two components, measure on the source host or compare against a copy of the same file placed locally near Neo4j in a controlled experiment.

### 6.2. When a Java application reads the source

In the Java application, measure separately:

- Time to read bytes from the source (disk, API, JDBC, Kafka, object storage).
- Time to decompress, parse, validate schema, cast types, and normalize strings.
- Rows/s and MiB/s the application can produce **with Neo4j calls temporarily disabled**.
- Error row rate and total bytes processed.

If the source delivers only 800 rows/s in a no-DB test while Neo4j sustains 5,000 rows/s on a comparable workload, **the source** is a strong bottleneck candidate. That conclusion holds only if both tests share identical transformation costs and do not alter source caches, thread counts, or record sizes.

## 7. Measuring the network between app and Neo4j without writing data

With the Java Driver/Bolt, send a **parameterized batch** that only counts elements instead of writing:

~~~cypher
UNWIND $rows AS row
RETURN count(row) AS receivedRows;
~~~

Example `$rows`:

~~~json
[
  {"personId": "P001", "name": "An", "city": "Ha Noi"},
  {"personId": "P002", "name": "Binh", "city": "Da Nang"}
]
~~~

The result must be `receivedRows = 2`. This measures **parameter transport/serialization/deserialization plus minimal Cypher execution**, not raw TCP bandwidth. It also excludes lock and write-commit costs.

How to isolate cleanly:

1. Pre-build batches in application memory **before starting the timer** to exclude source-reading cost.
2. Execute queries across multiple batches using a **warmed-up connection pool** and consume all results.
3. Record serialized payload size if tooling/libraries expose it, p50/p95 latency, client CPU, and network traffic.
4. Keeping the same Neo4j server and parameters, compare runs with the app **colocated near the server** vs. over a remote connection.
5. Increase batch size stepwise to observe whether throughput saturates on bandwidth, round-trip time (RTT), or client/server serialization CPU.

Typical signs of a network bottleneck include **latency scaling with network distance or payload size**, bytes/s hitting link limits, elevated retransmissions/timeouts, or the server having spare CPU/disk while starved for requests. On setups using `neo4j://`, Bolt traffic may route across servers; record the actual endpoint addresses and path rather than assuming every request hits the same host.

**Safety note:** repeatedly sending one batch in a read-only test warms up the connection pool and JVM. Never infer that dropping latency is due to Neo4j's page cache; `count(row)` does not read graph nodes.

## 8. Measuring the Neo4j server baseline without CSV overhead

To test server write execution capability on its own, generate synthetic test nodes directly in Cypher. The example below targets versions supporting the **variable scope clause `CALL (i) { ... }` (Neo4j 5.23+ / current Cypher)**; run in an **implicit/auto-commit transaction**, not wrapped inside a managed/explicit transaction:

~~~cypher
UNWIND range(1, 10000) AS i
CALL (i) {
  CREATE (:QA010Synthetic {
    runId: 'R01',
    seq: i,
    payload: 'fixed-payload'
  })
} IN TRANSACTIONS OF 1000 ROWS;
~~~

The first run should create **10,000 new nodes**, split into sub-transactions of roughly 1,000 rows. Verify:

~~~cypher
MATCH (n:QA010Synthetic {runId: 'R01'})
RETURN count(n) AS created;
~~~

Answer: `created = 10000` if the entire statement succeeded and no `runId='R01'` nodes existed beforehand.

Comparing this test against CSV import reveals when source/network costs dominate, yet **it is not a pure zero-overhead write benchmark**: the server still generates `range`, creates properties, writes transaction logs, and updates existing indexes. Moreover, if your CSV test uses `MERGE` while the synthetic test uses `CREATE`, write costs are **different**. Use the comparison to form hypotheses; for a direct comparison, keep property counts, constraints/indexes, and CREATE/MERGE operations equivalent.

**Version note:** versions prior to 5.23 support `CALL { WITH i ... } IN TRANSACTIONS`; the newer scope-clause syntax may not parse there. `CALL ... IN TRANSACTIONS` cannot run inside an application-opened explicit transaction or `session.executeWrite`. Neo4j Browser may require the corresponding auto-commit mode when running this statement.

If one batch fails, earlier batches may have already committed. Before re-testing, clean up the test nodes or use a distinct `runId` and document it clearly. Never treat the total database node count as a single-run counter when prior data exists.

## 9. Importing the fixture with LOAD CSV and batched transactions

With the file from Section 5, import using `MERGE`:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
CALL (row) {
  MERGE (p:QA010Person {personId: trim(row.personId)})
  SET p.name = trim(row.name),
      p.city = trim(row.city)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

On Neo4j 5.23+ (and matching Cypher), `CALL (row)` passes `row` into the subquery. `IN TRANSACTIONS OF 1000 ROWS` splits work into sub-transactions and avoids a single giant transaction holding too much state. With seven fixture rows, the command executes in one sub-transaction; **a batch size of 1000 does not magically speed up a tiny example**.

To run on older Neo4j 5.x releases, use the legacy variable-import subquery form and check against your version:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///qa010_people.csv' AS row
CALL {
  WITH row
  MERGE (p:QA010Person {personId: trim(row.personId)})
  SET p.name = trim(row.name),
      p.city = trim(row.city)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Before applying to large datasets, test syntax on your specific Neo4j version. On file URL errors, check the **server's import directory and file permissions**, not just paths on the laptop running Browser.

### 9.1. Verifying data after import

~~~cypher
MATCH (p:QA010Person)
RETURN
  count(p) AS persistedNodes,
  count(DISTINCT p.personId) AS uniqueIds,
  count(CASE WHEN p.city = 'Ha Noi' THEN 1 END) AS haNoi
;
~~~

| persistedNodes | uniqueIds | haNoi |
|---:|---:|---:|
| 6 | 6 | 3 |

Run the `LOAD CSV` statement a second time and re-check: node count stays **6** because `MERGE` keys on ID. Yet **processed rows equal 7**, while **new nodes created on the second pass equal 0**. That is why reports must separate `inputRows`, `processedRows`, and `nodesCreated`.

### 9.2. CREATE or MERGE?

| Case | Behavior | Measurement impact |
|---|---|---|
| `CREATE` | Creates new nodes/relationships on every run | Fast in some cases, but duplicates on rerun |
| `MERGE` by ID with constraint/index | Matches or creates by identity | Adds lookup, constraint, and occasional lock cost; simplifies safe reruns |
| `MERGE` on long multi-relationship pattern | May match/create complex structures | Easily inflates DB hits and lock contention; consider separating node and relationship imports |

Never boost throughput by dropping uniqueness constraints if the domain requires deduplication. Preserve correctness first, then optimize batching, indexes, and Cypher structure.

## 10. Measuring batching and commits from the Neo4j Java Driver

For applications sending CSV/JSON over Bolt, the common pattern is `UNWIND $rows` paired with `MERGE`. The Java Driver 5+ example below assumes `driver` is initialized and `rows` is a **pre-loaded** list of records. Each call handles one batch; timing from `System.nanoTime()` until `executeWrite` returns **captures transaction execution and commit**, plus client/transport overhead.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import java.util.List;
import java.util.Map;

public final class ImportMeasure {
    public static double writeBatch(
            Driver driver, List<Map<String, Object>> rows) {
        String query = """
            UNWIND $rows AS row
            MERGE (p:QA010Person {personId: row.personId})
            SET p.name = row.name, p.city = row.city
            """;

        long start = System.nanoTime();
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run(query, Map.of("rows", rows)).consume();
                return null;
            });
        }
        double seconds = (System.nanoTime() - start) / 1e9;
        System.out.printf(
            "batchRows=%d, elapsedSeconds=%.4f, rowsPerSecond=%.1f%n",
            rows.size(), seconds, rows.size() / seconds
        );
        return seconds;
    }
}
~~~

**How to read the measurement:**

- If `rows` was prepared beforehand, this measures **driver + Bolt network + Neo4j execution/commit**. Source reading/parsing is excluded.
- To measure end-to-end, start the timer **before fetching the batch from the source**, stop after commit, and sum successful rows across the entire job.
- `executeWrite` can **retry the transaction** on transient errors. Thus a batch's elapsed time may include multiple attempts; log retry counts or classify errors when diagnosing.
- Keep each batch small enough for memory/transaction limits yet large enough to amortize per-request/commit overhead.
- To run Section 7's read-only test, use `session.run("UNWIND $rows AS row RETURN count(row)", ...)` and consume results, then compare against the write measurement. Both measurements share part of client/network cost and do not differ solely by disk I/O.

In Spring Data Neo4j, you can instrument the service before and after repository calls. When measuring across layers, clarify whether timing includes entity mapping, transaction interceptors, and retries at which layer. A bulk Cypher `UNWIND` typically generates fewer round trips than calling repository `save()` entity by entity, though real results depend on schema, cascading mappings, and workload.

## 11. Analyzing bottlenecks on the Neo4j server

If source parsing and network transfer are fast, yet commit latency rises or write queues grow, inspect server resources.

| Resource | Metrics to watch | Signs and how to verify |
|---|---|---|
| **CPU** | CPU utilization, runnable threads, query time | CPU saturates as threads grow; check parsing, `MERGE`, casting, Cypher logic |
| **Heap / GC** | Heap used, GC pauses, transaction memory, OOM/throttling | Large batches, big lists/maps, or long transactions increase allocation pressure |
| **Page cache** | Hit/miss ratio, page faults, working set, read I/O | Frequent `MERGE`/index misses; check indexes and RAM allocated to page cache |
| **Disk & transaction log** | Write latency, IOPS, throughput, fsync/commit latency, log/checkpoint pressure | Disk saturated, batch commits slow despite moderate CPU |
| **Locks & transactions** | Wait time, active/blocked transactions, retries/deadlocks | Multiple workers `MERGE`-ing or updating the same IDs cause contention |
| **Indexes & constraints** | `SHOW INDEXES`, state, index count, schema | Missing/non-`ONLINE` indexes or excessive index updates per record |
| **Server-side network** | Bytes/s, TCP retransmits, Bolt connections/timeouts | Server starved of payloads or delayed responses while other resources are idle |
| **Container / platform** | CPU quota, memory limit, storage throttling, noisy neighbors | Host has spare capacity while container/VM hits caps |

No single metric proves a root cause. For example, **low CPU utilization** does not mean the server is idle: threads may be waiting on locks or disk. A **high page cache hit ratio** does not guarantee fast imports if transaction log writes are slow. **High disk write bytes** alone does not prove the disk hit its IOPS or latency ceiling.

### 11.1. Using EXPLAIN and PROFILE properly

~~~cypher
EXPLAIN
UNWIND $rows AS row
MERGE (p:QA010Person {personId: row.personId})
SET p.name = row.name, p.city = row.city;
~~~

`EXPLAIN` executes no writes and reveals whether the planner intends to use an index to match IDs. In a **test** environment, use `PROFILE` to inspect `Rows`, `DB Hits`, operators, and the actual plan—remembering that `PROFILE` **does execute the write** and adds instrumentation overhead. Therefore, never report `PROFILE` latency as application throughput, and never run `PROFILE` in production without controlling its impact.

`DB Hits` measures logical work in the query engine, **not SSD read/write operations**. Page cache misses and transaction log costs must be observed separately through your version's execution-plan metrics or server telemetry.

### 11.2. Inspecting slow active transactions

An account with sufficient privileges can inspect running transactions:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, elapsedTime, status
RETURN transactionId, currentQuery, elapsedTime, status
ORDER BY elapsedTime DESC;
~~~

This is only a point-in-time snapshot. To diagnose lock contention, also inspect monitoring metrics, transaction logs, retries, and lock/wait fields exposed by your Neo4j version. Never treat a long-running query by itself as proof of a deadlock.

## 12. Controlled bottleneck-isolation experiments

Holding other factors constant, **change one variable at a time** and compare against baseline:

| Controlled test | If noticeably faster | What still needs checking |
|---|---|---|
| Read source → count rows, skip Neo4j writes | Writing/committing likely accounts for major cost | For HTTP sources, network and parsing are still combined |
| Pre-build batches in RAM, then send `UNWIND` | If much faster than end-to-end, source/parse is a strong candidate | Keep `MERGE` workload and duplicate rate identical |
| Read CSV from server local disk vs. remote HTTP (same bytes) | HTTP source server or server→source network may cap throughput | Local disk and caching differ too; run multiple trials |
| Move Java app close to Neo4j, same batch/query | Bolt RTT/bandwidth or routing may be the bottleneck | Do not conclude if client CPU/runtime also changed |
| Increase batch 100 → 500 → 1000 → 5000 | If throughput rises and requests/s drop, batch/commit overhead was significant | Watch heap, p95, locks, and transaction memory |
| Increase workers 1 → 2 → 4 → 8 | If throughput scales nearly linearly, headroom remains | Stop when p95/retries/CPU/I/O rise while throughput plateaus |
| Swap `CREATE` for `MERGE` or vice versa | Lookup/uniqueness cost may dominate | Keep business semantics intact; these are different workloads |
| Add appropriate index before `MERGE` by ID | Eliminates scans on large datasets | Index maintenance cost on writes rises too; measure overall |

A practical way to find **peak sustainable throughput** is testing the same dataset across concurrency levels and recording:
- `X`: committed rows/s;
- `L50` and `L95`: batch latency;
- `E`: errors/retries;
- CPU, RAM/GC, cache misses, write latency, and queue depth.

Pick a configuration near the high-throughput region **where latency and retries remain acceptable**, not maximum possible workers. Once adding workers leaves `X` flat while `L95` and lock waits climb, extra concurrency only amplifies congestion.

## 13. Quick diagnostic table by symptom

| Observation | Likely bottleneck | Next verification step |
|---|---|---|
| Without Neo4j writes, source still reads few rows/s | Source / parser | Profile I/O, decompression, casting, schema errors separately |
| Java takes long to build batches while Bolt/commit is fast | Source app CPU or I/O | Measure serialization, parsing, client GC; test pre-built RAM batches |
| Switching local/remote network sharply alters throughput while Neo4j has spare CPU/disk | Network / RTT / routing | Compare bytes/s, RTT, retransmissions, payload size, and TLS |
| `LOAD CSV` from HTTP is slow while local server file copy is fast | HTTP source or server → source link | Measure HTTP response/chunk times, download duration, source host CPU |
| Rows/s plateaus with more workers while Neo4j CPU is saturated | Server CPU | Run `PROFILE` on fixture; check operators/DB Hits, casting, and MERGE |
| Commit p95 climbs while CPU is low and disk write latency is high | Transaction log / disk | Check write IOPS, fsync, log/checkpoint activity, storage throttling |
| Large batches spike GC/OOM or transaction memory | Transaction memory | Shrink batch size; inspect `collect`/list/transaction overhead |
| Multiple workers update the same IDs; retries/deadlocks climb | Lock contention | Partition keys by ID; reduce concurrent writes to overlapping groups |
| `MERGE` is slow on large data, missing ID index | Lookup query | Create proper unique constraint/index and wait for `ONLINE` |
| Input rows/s is high yet node count barely grows | Duplicates, updates, skipped errors, or wrong metric | Check distinct IDs, created/matched counters, errors, and MERGE rules |
| First run is slow, later runs are fast with identical counts and plans | Warmup/caching effects | Inspect page cache misses, plan cache, JIT, and connection pool |

Follow **observation → hypothesis → controlled test → scoped conclusion**, rather than picking a hypothesis upfront and hunting for metrics to confirm it.

## 14. Batching, transactions, and concurrency: core trade-offs

### 14.1. Batches too small

Every batch incurs a round trip and transaction/commit overhead; with one node per batch, network RTT and commit overhead dominate write time. Increasing batch size can improve rows/s.

### 14.2. Batches too large

Huge batches increase heap and transaction memory demand, hold locks longer, inflate p95 latency, and force retries to redo excessive work. In Cypher, building huge lists via `collect()` can also raise memory consumption dramatically.

Starting points to **benchmark**—not "Neo4j optimal values"—are `100`, `500`, `1,000`, and `5,000` rows/batch. Depending on property/relationship volume, 100 rows may already be heavy, or 5,000 rows may still be light. Track both bytes/batch and commit duration.

### 14.3. Concurrency too high

Multithreading utilizes multiple cores and disk queues, yet can trigger resource contention, lock waits, and transaction retries. Especially with `MERGE` on identical keys, two workers can block each other. Partition IDs deterministically across workers and enforce uniqueness constraints where required.

### 14.4. Nodes-before-relationships strategy

For large graphs, consider importing **nodes by unique ID first**, then creating relationships once endpoints exist. Relationship creation typically looks up both endpoints via keys/indexes; missing indexes trigger repeated scans. When using two passes, measure and reconcile both **nodes/s** and **relationships/s**—never sum them into a generic "rows/s" if their units differ.

### 14.5. Loading via offline tooling

`neo4j-admin database import` fits scenarios involving **massive CSV bulk loads into a brand-new or offline database**. It does not share the online transactional properties of `LOAD CSV`/Java Driver; it imposes specific requirements on file placement, permissions, database state/downtime, and version-dependent syntax.

When evaluating offline import, compare total wall-clock time across **file prep, stopping/initializing the database per procedure, running import, verifying data, building indexes/constraints, and bringing the system online**, not just the tool's raw write rate. Never run an import flag that overwrites an existing database in practice exercises.

## 15. Benchmark log: minimum fields to record

Every run should record enough context for others to reproduce it:

~~~text
run_id:
timestamp / neo4j_version / driver_version:
import_mode: LOAD_CSV | JAVA_DRIVER | OFFLINE
source_location: file_local | HTTP(S) | API | JDBC ...
source_rows / source_bytes:
success_rows / created_nodes / created_relationships:
failed_rows / retries:
batch_size / workers:
query_or_import_command:
constraint_and_index_state:
elapsed_source_ms / elapsed_transform_ms:
elapsed_send_and_commit_ms / elapsed_total_ms:
rows_per_second / MiB_per_second:
batch_latency_p50_ms / batch_latency_p95_ms:
client_CPU / server_CPU / heap_GC / pagecache:
disk_write_latency / IOPS / network_bytes / RTT:
notes: warmup, cache, concurrency, dataset fingerprint
~~~

Not every system collects every field; record **N/A** for unavailable metrics rather than inventing numbers. At minimum, record **data volume, elapsed time, succeeded records, error count, and workload settings**. A screenshot saying "query completed in 1.2 s" proves nothing about import speed unless it states what that 1.2 s included and how much data committed.

A **hypothetical** example to practice drawing conclusions:

| Stage / experiment | Throughput | Observed metric |
|---|---:|---|
| Source read + parse, no DB | 8,000 rows/s | Source CPU 35% |
| Java sends batch and only `RETURN count(row)` | 12,000 rows/s | Network has headroom |
| Server synthetic `CREATE` | 6,000 rows/s | High disk write latency |
| End-to-end real `MERGE` | 3,500 rows/s | High CPU + lock waits |

Do not naively conclude end-to-end must reach `min(8,000, 12,000, 6,000) = 6,000`: `CREATE` differs from `MERGE` in constraints/indexes and contention. The sound conclusion is **the source and no-write transport do not yet appear to be the slowest stages**; profile `MERGE`/locks/logs/disk on a matching workload before deciding optimizations.

## 16. Verifying correctness and retry safety

Import measurement requires two parallel outputs: **performance** and **correctness**.

- Compare total input rows against processed rows, rejected rows, failed batches, and retry counts. Retain error lists for replay if needed.
- Check distinct IDs, newly created nodes, and updated existing nodes. On the fixture, `7 source rows → 6 nodes` is **correct**, not a lost row.
- Place uniqueness constraints on critical business keys; `MERGE` by key for predictable replay behavior.
- Never treat every error as "ignorable." If only part of a batch set committed before stopping, know your checkpoint and resume position.
- Never write personal data, secrets, tokens, or sensitive payloads into benchmark logs. Aggregate metrics and error codes suffice.
- Keep queries, schema, datasets, and edition fixed across comparative runs; document any change explicitly.

To verify the fixture after two import passes:

~~~cypher
MATCH (p:QA010Person)
RETURN
  count(p) AS persisted,
  count(DISTINCT p.personId) AS distinctIds,
  sum(CASE WHEN p.city = 'Ha Noi' THEN 1 ELSE 0 END) AS haNoi,
  sum(CASE WHEN p.city = 'Da Nang' THEN 1 ELSE 0 END) AS daNang;
~~~

Answer: `persisted = 6`, `distinctIds = 6`, `haNoi = 3`, `daNang = 2`. Data for the six fixture IDs remains unchanged even after re-running `MERGE` with identical content.

## 17. Exercises with answers

**Exercise 1 — Computing throughput.** An import has 25 batches of 800 rows each, all committing in 50 seconds with zero errors. What is the throughput?

**Answer:** `25 × 800 = 20,000` committed rows; `20,000 / 50 = 400 rows/s`. If a batch retried, count each successful row only once.

**Exercise 2 — Distinguishing source and network.** Java reads a source API at 500 rows/s, while sending pre-loaded RAM batches and `MERGE`-ing into Neo4j achieves 3,000 rows/s. What should be optimized first?

**Answer:** the API source/parser is the bottleneck candidate. Measure API latency, rate limits, parsing, and transformations carefully rather than prematurely increasing Neo4j heap. Verify both tests use comparable data and queries.

**Exercise 3 — Reading server symptoms.** Increasing workers from 2 to 8 leaves rows/s nearly flat while commit p95 quadruples and lock waits and retries rise. What is the sensible fix?

**Answer:** reduce concurrency or partition IDs/keys to curb contention, and review `MERGE` and constraints/indexes. Adding even more workers will likely worsen congestion.

**Exercise 4 — Counting data accurately.** The fixture file has 7 rows, and two passes of `MERGE` by `personId` are executed. What is the node count after each pass and new-node count on pass two?

**Answer:** **6 nodes** after the first pass, still **6 nodes** after the second pass, and **0 new nodes** on pass two. Report `processed rows` separately to reflect the 7 rows processed in each pass.

**Exercise 5 — Tracing the network path.** A `LOAD CSV FROM 'https://...'` statement runs in Neo4j Browser on a laptop. Who downloads the full CSV over the network?

**Answer:** the **Neo4j server** sends the HTTP(S) request to the CSV source and receives the content; Browser only sends Cypher and receives results. To diagnose, measure the **server → HTTP source** path instead of automatically blaming **laptop → Neo4j**.

**Exercise 6 — Concluding from controlled tests.** `LOAD CSV RETURN count(row)` takes only 2 seconds, whereas importing 100,000 rows with `MERGE` takes 180 seconds. Can we conclude disk is the bottleneck?

**Answer:** not yet. Those runs suggest **writing/lookup/commit** takes most of the time; inspect CPU, `PROFILE`, indexes, transaction log I/O, locking, GC, and errors/retries to pinpoint the specific cause.

## 18. Cleaning up practice data

In this lesson's dedicated test database, once metrics are recorded:

~~~cypher
DROP CONSTRAINT qa010_person_id IF EXISTS;
~~~

~~~cypher
MATCH (p:QA010Person)
DETACH DELETE p;
~~~

~~~cypher
MATCH (n:QA010Synthetic)
DETACH DELETE n;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA010Person OR n:QA010Synthetic
RETURN count(n) AS remaining;
~~~

Expect `remaining = 0`. `DETACH DELETE` removes relationships attached to nodes carrying the test labels; do not run if your environment uses those labels for other data.

## 19. References and closing checklist

- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/): path configuration, file/URL reading, and CSV import requirements.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): batched processing and independent commit behavior.
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/): batching, transactions, parameterized queries, and client tuning.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`, `PROFILE`, `Rows`, and `DB Hits`.
- [Neo4j Operations Manual — Monitoring metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/): monitoring page cache, JVM, transactions, and I/O.
- [Neo4j Operations Manual — Import](https://neo4j.com/docs/operations-manual/current/import/): offline import mechanics via `neo4j-admin database import`.

Before declaring you have found the bottleneck, be able to answer four questions: **(1)** how many records actually committed and are the answers correct; **(2)** which stage is the slowest consumer or causing queues to grow; **(3)** which controlled test shows that improving that stage raises overall pipeline speed; **(4)** does the improvement hold as batch size, concurrency, and dataset size vary under realistic conditions?

Measuring the boundary between **source, network, and Neo4j server** accurately enables evidence-based optimization: tuning the parser/source, colocating the app near the database, adjusting batch size, fixing `MERGE`/indexes, or scaling server resources only when genuinely needed.
