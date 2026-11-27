# Estimated Rows, Rows, DB Hits, and Metric Interpretation Limits in Neo4j Execution Plans

## 1. Why Read Execution Plan Metrics?

Neo4j uses a **property graph** consisting of nodes, relationships, and properties; Cypher describes *what data to find*, while the **query planner** decides *how to traverse the graph*. The same query can be executed by scanning labels, looking up an index, traversing relationships in a chosen direction, or combining multiple operators.

For example, a retail application wants to find the products purchased by a customer:

```cypher
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

A query returning the right results can still be slow if the planner starts from too many nodes, expands relationships too broadly, or sorts a large number of rows. The execution plan provides signals to answer:

- **`Estimated Rows`**: How many rows did Neo4j *estimate* each operator would emit during planning?
- **`Rows`**: How many rows did the operator *actually* emit in the measured run?
- **`DB Hits`**: How many units of database access work did the operator perform?

These three numbers are related, yet **they are not interchangeable**. In particular, they are not direct measurements of user response time, total node count in the database, or physical disk reads.

The goal of this lesson in the **Execution Plans** chapter is to learn how to read these three metrics in `EXPLAIN`/`PROFILE`, locate where row counts inflate or heavy access occurs, and avoid false conclusions when tuning Cypher, indexes, constraints, relationship queries, the Java Driver, or Spring Data Neo4j.

## 2. `EXPLAIN` and `PROFILE`: Preview the Plan or Measure Execution?

Neo4j builds an execution plan from the Cypher query and available metadata, such as labels/types, indexes, constraints, and data distribution statistics.

| Command | Executes query? | What is visible? | When to use? |
| --- | --- | --- | --- |
| `EXPLAIN` | **Does not** execute the query | Operator structure, `Estimated Rows`, data access paths | Quickly inspect planner strategy before running heavy queries |
| `PROFILE` | **Executes** the query | Plan structure and measurements such as `Rows`, `DB Hits`, and sometimes time, memory, page cache | Measure safe read queries on a representative dataset |

```cypher
EXPLAIN
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

```cypher
PROFILE
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku, p.price;
```

**Warning about `PROFILE`:** this is an **actual query execution**, not a simulation. If you place `PROFILE` before `CREATE`, `MERGE`, `DELETE`, or `SET`, Neo4j still executes those write operations. To preview a write statement without modifying the graph, use `EXPLAIN`. Profiling itself also introduces overhead, so measure only with a clear objective.

## 3. How Is an Execution Plan Structured?

An execution plan typically consists of:

1. **Header:** Cypher version, planner, runtime, and sometimes batch size.
2. **Operator tree:** each step for locating nodes/relationships, filtering, joining, aggregating, sorting, and returning results.
3. **Footer:** total database accesses and other summary metrics if provided by the runtime.

Some common operators:

| Operator | Common Role | What to Watch |
| --- | --- | --- |
| `NodeByLabelScan` | Scan nodes by label | Reasonable on small labels; expensive when scanning millions of unnecessary nodes |
| `NodeIndexSeek` | Find nodes via an index | Check predicates, selectivity, actual `Rows`, and `DB Hits` |
| `Expand(All)` | Follow relationships from input nodes | A high-degree node can emit a vast number of rows |
| `Expand(Into)` | Check/connect already-bound nodes | Can generate many relationship-checking operations |
| `Filter` | Discard rows not matching a condition | If very many rows are dropped, check whether filtering can happen earlier |
| `CartesianProduct` | Pair every row from two independent input sets | Easily multiplies row count to the product of both sets |
| `EagerAggregation` | Group or count | Output may be just a few rows despite reading millions of rows |
| `Sort` or `Top` | Sort or pick leading elements | Watch memory, row count, and whether index order can be leveraged |
| `ProduceResults` | Return result rows to the client | Row count here can differ vastly from rows processed by operators below |

**A plan is a tree**, not a log of sequential single-threaded statements. Usually you read data flow from access operators at the bottom up to result-producing operators at the top, while watching `Apply`, `Join`, or `CartesianProduct` branches. Neo4j can use pipelined/parallel runtimes and fuse multiple operators into a single pipeline.

### Illustrative Table Sample

The table below is **completely hypothetical for practicing reading metrics**, not measured output from a specific Neo4j version:

| Operator | Estimated Rows | Rows | DB Hits |
| --- | ---: | ---: | ---: |
| `ProduceResults` | 10 | 6 | 0 |
| `Filter` | 10 | 6 | 0 |
| `Expand(All)` | 15 | 400 | 1,200 |
| `NodeIndexSeek` | 1 | 1 | 3 |

From this illustrative table, you can observe: the planner expected `Expand(All)` to emit 15 rows, yet it actually emitted 400, and then `Filter` kept only 6 rows; relationship expansion cost occurred before discarding most of the results. **Do not** treat numbers in this table as standard benchmarks for an operator type; an actual plan depends on data, version, and runtime.

## 4. `Estimated Rows`: The Planner's Row Prediction

### 4.1. Concept and Origin

`Estimated Rows` is **the estimated number of rows an operator will output**. The planner uses it to evaluate competing strategies and choose a plan with a reasonable estimated cost.

Estimates are usually based on:

- Node counts per label, relationship counts per type, and connection distribution models.
- Index statistics, such as the selectivity of a property.
- Probability/selectivity models for `WHERE` conditions.
- Assumptions when combining multiple pattern branches, especially when properties or graph structures are strongly correlated.

**Estimated Rows is not a runtime measurement.** It is not automatically overwritten with `Rows` merely because Neo4j observed actual rows during a `PROFILE` run.

### 4.2. Why Can Estimates Be Wrong?

Suppose a social network graph has 99% of users following only a few accounts, while 1% of popular accounts have millions of followers. If the planner relies on average distribution, it can mispredict row counts when a query hits a particularly famous account.

Common causes:

- **Data skew:** nodes with much higher relationship degree than most other nodes.
- **Data correlation:** `city = 'HCM'` and `country = 'VN'` are not independent; estimation models may not represent this correlation accurately.
- **Stale statistics after recent changes:** following a large import, deletion, or label change.
- **Different parameter values:** the same query where `customerId` points to a customer with few orders versus one with millions of orders.
- **Complex patterns:** multi-hop expansions, `OPTIONAL MATCH`, variable-length paths, joins, aggregations.
- **Cached plans:** a query may reuse a previously cached plan rather than immediately replanning with updated statistics.

An underestimate can lead the planner to pick an unsuitable traversal or join order. However, **an estimate mismatch alone does not prove a query is slow**; cross-check `DB Hits`, time, and resource usage.

### 4.3. Measuring the Gap Between `Estimated Rows` and `Rows`

For a given operator, you can define:

\[
\text{Deviation Ratio} =
\frac{\max(\text{Estimated Rows},\ \text{Rows})}
{\max(1,\min(\text{Estimated Rows},\ \text{Rows}))}
\]

This is **only a diagnostic aid** computed by the analyst, not an official metric reported by Neo4j. If the estimate is 20 while actual rows are 2,000, the deviation corresponds to **100x**. Focus first on **the earliest operator where a large divergence appears**, rather than comparing only at `ProduceResults`.

If `Estimated Rows = 0` or `Rows = 0`, the ratio can lose meaning, especially for operators with tiny estimates. Inspect absolute numbers and the meaning of the data branch directly; do not treat a division ratio as proof of performance.

## 5. `Rows`: Rows Flowing Through an Operator, Not Node Count

`Rows` appears only with `PROFILE` and records **the number of rows emitted by the operator during that execution**. A row can contain:

- A node variable: `{c}`.
- A pair of nodes: `{c, p}`.
- A relationship or path: `{c, r, p}`.
- An aggregated value: `{customerId, purchaseCount}`.

For example, Cypher **without touching the graph at all** can still produce many rows:

```cypher
PROFILE
UNWIND [1, 2, 3] AS number
UNWIND ['A', 'B'] AS letter
RETURN number, letter;
```

The first `UNWIND` produces 3 rows; each row is expanded by the second `UNWIND` into 2 rows, so the final output has **6 rows**. `Rows` increases at the row-generating step even though there are neither 6 nodes nor 6 disk reads.

Conversely:

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN count(*) AS purchaseCount;
```

The final result has only **one row containing the total count of matched patterns**; underlying read and traversal operators can still process very many rows. Therefore, **`Rows = 1` at `ProduceResults` does not mean the query only processed one record**.

### Patterns That Cause `Rows` to Increase or Decrease

| Query Pattern / Operator | Observable Effect | Notes |
| --- | --- | --- |
| `Expand(All)` on a high-degree node | One input row can fan out into hundreds or millions of rows | Measure relationship fan-out, type, and direction |
| `MATCH (a), (b)` without linking the two sets | Row count can become the product `\|A\| × \|B\|` | Very easy to create an unintended Cartesian product |
| `WHERE` / `Filter` | Reduces rows continuing upstream | Late filtering still pays the cost of earlier steps |
| `DISTINCT` | Can eliminate duplicate rows | Incurs deduplication cost and may require memory |
| `RETURN count(*)` | One aggregated row when ungrouped | Does not reflect how many rows were scanned |
| `WITH key, count(*)` | One row per `key` group | Measure group count separately from input row count |
| `LIMIT n` | Caps output and can stop lazy upstream work early | Does not guarantee proportional savings if upstream must sort or aggregate |
| `OPTIONAL MATCH` | Can retain a row with `null` values when unmatched | Does not mean all branches had 0 rows |

## 6. `DB Hits`: Storage-Layer Operations, Not Disk Reads

### 6.1. What Is a Database Hit?

`DB Hits` is an **abstract unit** counting work requested from the storage engine, such as:

- Finding a node or relationship by ID, index, or scan.
- Checking a label, relationship type, or node degree.
- Reading a node or relationship property.
- Traversing relationships or finding paths.
- Creating, deleting, or updating graph elements, or checking certain schema metadata.

`DB Hits` is recorded in `PROFILE` and commonly helps locate where a query performs heavy work against the storage engine.

### 6.2. Distinguishing Three Commonly Confused Metrics

| Metric | What Does It Measure? | What It Does Not Mean |
| --- | --- | --- |
| `Rows` | Actual rows emitted by each operator | Distinct node count or storage operations |
| `DB Hits` | Storage-engine access operations under Neo4j's accounting model | Physical reads from SSD/HDD |
| `Page Cache Hits/Misses` | Successful/failed page lookups in cache, when reported by runtime/edition | Identical to `DB Hits` or end-to-end response time |

For example, reading a property already in the page cache can still incur **DB Hits** without reading a block from disk. An `IndexSeek` returning one row can still produce multiple DB Hits. Conversely, an `UNWIND` generating thousands of in-memory rows can have very few storage operations.

### 6.3. Should You Always Minimize DB Hits?

**No.** Fewer DB Hits is usually a positive sign when comparing *the same requirement* on *the same dataset* with a comparable runtime. However:

- A query can spend heavy CPU on sorting, hash joins, regexes, or expression evaluation even with low DB Hits.
- An `EagerAggregation` can consume significant memory without adding many storage accesses.
- A cold page cache makes accesses much slower than a warm cache even when DB Hits stay nearly constant.
- The pipelined runtime or different Neo4j versions can account for DB Hits slightly differently.
- A query that lowers DB Hits while increasing execution time due to sorting or materializing many rows can still be a poor optimization.

The total `DB Hits` in the footer is the sum across operators **when all operators can be fully measured**. If an operator does not support accounting, you may see **`n + ?`**, meaning `n` is a lower bound rather than an exact total. Do not sum the entire operator column and claim it equals physical I/O count.

## 7. Hands-On Practice on a Customer–Product Graph

### 7.1. Creating Small, Repeatable Data

The following examples use a dedicated test database or dedicated labels if the environment contains real data. Start with constraints for keyed `MERGE`:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.id IS UNIQUE;
```

```cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
```

Create three customers:

```cypher
UNWIND [
  {id: 'C001', name: 'An'},
  {id: 'C002', name: 'Bình'},
  {id: 'C003', name: 'Chi'}
] AS row
MERGE (c:Customer {id: row.id})
SET c.name = row.name;
```

Create three products:

```cypher
UNWIND [
  {sku: 'P001', name: 'Cypher Book', price: 120},
  {sku: 'P002', name: 'Pen', price: 30},
  {sku: 'P003', name: 'Keyboard', price: 250}
] AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.price = row.price;
```

Create purchase links:

```cypher
UNWIND [
  {customerId: 'C001', sku: 'P001'},
  {customerId: 'C001', sku: 'P002'},
  {customerId: 'C002', sku: 'P002'},
  {customerId: 'C003', sku: 'P001'},
  {customerId: 'C003', sku: 'P003'}
] AS row
MATCH (c:Customer {id: row.customerId})
MATCH (p:Product {sku: row.sku})
MERGE (c)-[:PURCHASED]->(p);
```

If the test database started completely clean, the graph has 3 `Customer` nodes, 3 `Product` nodes, and 5 `PURCHASED` relationships. Do not interpret these numbers as database-wide totals if prior data with the same labels already existed.

### 7.2. Using `EXPLAIN` to Inspect the Strategy

```cypher
EXPLAIN
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku AS sku, p.price AS price
ORDER BY price DESC;
```

Questions when reading the plan:

1. Does Neo4j start from `Customer` or `Product`? This shows up in the leaf operators.
2. Does it use `NodeIndexSeek` on `Customer.id` or `Product.sku`, or a label scan?
3. Where does the `PURCHASED` expansion sit?
4. How does `Estimated Rows` change between node lookup, expansion, and filtering?
5. Is there a `Sort`, `Top`, or other operator before returning results?

Because the dataset has only a few nodes, the planner may consider a label scan cheaper than an index lookup; that **does not by itself prove the index was misconfigured**.

### 7.3. Using `PROFILE` to Cross-Check

```cypher
PROFILE
MATCH (c:Customer {id: 'C001'})-[:PURCHASED]->(p:Product)
WHERE p.price >= 100
RETURN p.sku AS sku, p.price AS price
ORDER BY price DESC;
```

With unmodified sample records, the query returns product `P001` with `price = 120`: customer `C001` bought two products `P001` and `P002`, but `P002` does not meet the 100 threshold.

Locate the operator traversing `PURCHASED` relationships. It may emit two rows and then the filter branch leaves one row. **Actual operator names and ordering can differ** by Cypher version, runtime, statistics, and chosen plan; never force an illustrative plan screenshot onto every environment.

### 7.4. Cartesian Product Example Inflating Rows

```cypher
PROFILE
MATCH (c:Customer), (p:Product)
RETURN c.id AS customerId, p.sku AS sku;
```

If the test set contains exactly 3 customers and 3 products, the query returns **9 pairs**. This is a Cartesian product, not “customers who bought products”. To find purchase transactions, link them via the relationship:

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.id AS customerId, p.sku AS sku;
```

The second query returns 5 results corresponding to the 5 sample relationships. When fixing a query, **preserving semantics** matters more than shrinking metrics: the two statements above return different result sets, so they must never be used as direct benchmark substitutes for one another.

### 7.5. Aggregation Hiding Intermediate Row Counts

```cypher
PROFILE
MATCH (c:Customer)-[:PURCHASED]->(p:Product)
RETURN c.id AS customerId, count(p) AS purchasedCount
ORDER BY customerId;
```

If the graph matches the sample data, the result has three rows: `C001 → 2`, `C002 → 1`, `C003 → 2`. These numbers reflect matched relationships; an operator near the output having three rows **does not negate** the fact that earlier traversal generated five rows.

## 8. How to Read Divergences Between `Estimated Rows` and `Rows`

A practical workflow should focus on **where the divergence first appears** and then trace its effect upward:

### Case A: Index Seek Estimate Is Accurate, Traversal Blows Up

Hypothetical example:

| Step | Estimated Rows | Rows | Interpretation |
| --- | ---: | ---: | --- |
| Look up `Customer.id` | 1 | 1 | Starting node selection is accurate |
| Follow `PURCHASED` | 10 | 50,000 | This customer has far more relationships than estimated |
| Filter by `price` | 2 | 300 | Most rows were produced first and discarded afterward |

This may indicate fan-out, data skew, or an underexploited selective condition. Do not conclude “adding another index will fix it” before checking whether starting from the opposite endpoint, changing traversal direction, or improving selectivity is feasible.

### Case B: `Rows` Is Already High Before `Filter`

If many rows are produced only to be discarded by `Filter`, check whether `WHERE` uses the right property and has an appropriate index. **Do not assume that moving a `WHERE` clause earlier in Cypher text changes the plan**: Cypher is declarative, and the planner is free to push predicates and reorder access paths.

### Case C: Large Estimate Divergence, Yet Low `DB Hits`

An inaccurate estimate may **have negligible practical impact** if absolute row counts are small, everything stays in memory, or the planner still chose a good strategy. Judge by execution time and stability; do not tune merely to make the estimated and actual columns match.

### Case D: `Estimated Rows` Is Close, Yet `DB Hits` Is High

The planner predicting row counts accurately does not guarantee a cheap access path. A pattern matching few rows that still has to inspect many relationships or read many properties can generate high DB Hits. Inspect access operators, predicates, and index status.

## 9. Limits When Interpreting Plan Metrics

### 9.1. Do Not Compare Numbers Across Runtimes as If They Were One Standardized Metric

Neo4j has multiple runtimes, among which **pipelined** and **parallel** differ in execution mechanics. Some operators are **fused** into a pipeline; when that happens, certain statistics (especially time) are attached to the pipeline rather than individual operators.

- `Rows` and `DB Hits` remain useful, though exact counting details and display granularity can vary by runtime/version.
- `Time (ms)` on fused operators can represent **the entire pipeline**; do not sum identical-looking timing cells repeatedly.
- In the parallel runtime, reported work time may accumulate across workers rather than representing total request wall-clock time.
- Blank cells or `?` indicate **no measurement available**, not a value of 0.

When benchmarking, document the Neo4j version, Cypher version, runtime, query parameters, dataset, and system load.

### 9.2. Page Cache and Disk Access Latency

Neo4j maintains a **page cache** to avoid re-reading pages from disk. Two runs of the same query can have similar DB Hits yet very different latencies if:

- On the first run, the page cache is **cold**, requiring many page loads from storage.
- On the subsequent run, the cache is **warm**, with much of the data already in RAM.
- The system is concurrently processing writes or other queries competing for resources.

`Page Cache Hits/Misses` (when available, e.g., in Enterprise Edition) provide helpful extra context. **High DB Hits does not equal the same count of physical disk I/O**; likewise, page-cache misses alone do not explain total network, driver, and application latency.

### 9.3. Memory and Eager Processing

`Sort`, `EagerAggregation`, joins, or `Eager` can buffer many rows in memory. A query with low DB Hits can still be slow or put pressure on heap memory when sorting millions of results.

Per-operator `Memory (Bytes)` (when reported) reflects **that operator's individual peak**, not the sum across all operators. Total memory in the footer reflects the query-wide peak, **not simply the sum of operator peaks**: peaks can occur at different times.

`Eager` may be inserted to preserve correctness when reads and writes overlap; do not try to eliminate it by rewriting a query if doing so alters semantics or breaks correctness.

### 9.4. `LIMIT` and Avoiding Reading All Data

```cypher
PROFILE
MATCH (p:Product)
RETURN p.sku
LIMIT 5;
```

With **lazy** operators, `LIMIT` can stop upstream work early. However, with:

```cypher
PROFILE
MATCH (p:Product)
RETURN p.sku, p.price
ORDER BY p.price DESC
LIMIT 5;
```

Neo4j may need to examine many products before knowing the top 5, unless an index order or appropriate optimization can be leveraged. Therefore, do not take `Rows = 5` at the output to mean only 5 nodes were read.

### 9.5. Query Results and Data Transferred to the Client

The plan reflects processing work inside the database engine. The duration of an HTTP request or Java service call also includes network transit, driver connection handling, DTO mapping, serialization, pagination, system load, and the time it takes the consumer to receive all results.

If a query returns 100,000 results, data transfer and serialization can take substantial time even if the plan shows no unusual DB Hits. Measure application-side latency as well, not just a `PROFILE` screenshot in Neo4j Browser.

## 10. Optimizing Based on Evidence, Not a Single Number

### 10.1. Hold Inputs Constant for Fair Comparison

To evaluate a Cypher or index change:

1. Preserve **semantics and the result set**. Compare row counts, entity keys, and duplicates before and after.
2. Run with representative data and parameters, covering both **high-degree nodes** and typical cases.
3. Capture `EXPLAIN` and `PROFILE`: check index/scan choices, `Estimated Rows`, `Rows`, `DB Hits`, and memory/time when available.
4. Measure multiple times after warm-up while tracking page cache state and system load; never compare a cold-cache run against a warm-cache run.
5. Deploy the change only when latency, resource consumption, and correctness meet your target.

**Do not profile write queries directly in production to experiment.** Create a data copy or a controlled test scenario; if measuring a real write flow is necessary, understand commit impact and retry behavior.

### 10.2. Check Indexes/Constraints and Use Suitable Predicates

Example constraint for the customer key:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.id IS UNIQUE;
```

The constraint keeps data consistent and provides an appropriate index for lookups by `id`. For a query filtering products by price as in the example, consider a range index:

```cypher
CREATE RANGE INDEX idx_product_price IF NOT EXISTS
FOR (p:Product) ON (p.price);
```

After creating the schema, inspect `SHOW INDEXES` and confirm `ONLINE` status before evaluating the plan. An index is not guaranteed to be used when a label is tiny or a predicate has low selectivity. **An index does not replace graph traversal conditions.**

### 10.3. Design Queries to Avoid Unnecessary Expansion

If the goal is counting purchases for **one customer**, rather than scanning the whole graph and filtering in the application layer:

```cypher
MATCH (c:Customer {id: $customerId})-[:PURCHASED]->(p:Product)
RETURN count(*) AS purchases;
```

The query places a predicate on the customer key before following relationships. The planner gets an opportunity to use an index and narrow the graph region explored. Even so, the Cypher planner is allowed to choose the execution order; inspect the actual operators to see the access path.

To avoid multiplying rows across two independent one-to-many branches, aggregate each branch separately inside a subquery. For example, counting purchased products and visited stores for a customer:

```cypher
MATCH (c:Customer {id: $customerId})
CALL (c) {
  MATCH (c)-[:PURCHASED]->(p:Product)
  RETURN count(p) AS productCount
}
CALL (c) {
  MATCH (c)-[:VISITED]->(s:Store)
  RETURN count(s) AS storeCount
}
RETURN c.id, productCount, storeCount;
```

The example above uses the **variable scope clause** `CALL (c)` (Cypher 5.23+). Writing `MATCH` for both branches and aggregating in the same stream without accounting for multiplicity can multiply rows, skewing `count` and inflating `DB Hits`. Verify the semantics of `count(*)`, `count(DISTINCT ...)`, and handling customers with no relationships before rewriting.

### 10.4. Limit Manual Planner Overrides

Hints like `USING INDEX` or `USING JOIN` should only be considered after measurements clearly show the planner picked an unsuitable access path and you have verified the fix on representative data. A hint that helps on today's data can hurt when graph distribution and size evolve.

If you suspect statistics are stale, review the **index sampling** and **query replanning** mechanisms of your Neo4j version. `db.resampleIndex('indexName')` updates planner statistics; **it does not repair corrupt data or resync index entries**. Clearing the query cache or forcing a replan is an operational action requiring clear justification, not the first reaction to seeing `Estimated Rows` diverge.

## 11. Reading Metrics from the Java Driver and Spring Applications

### 11.1. Java Driver: Reading the Profile After Consuming Results

The Neo4j Java Driver exposes the execution plan via `ResultSummary`. On **Java Driver 6.2+**, the `queryProfile()` API returns `Optional<QueryProfile>`; `QueryProfile` exposes fields such as `rows()` and `dbHits()` as `OptionalLong`. Example:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.QueryProfile;
import org.neo4j.driver.summary.ResultSummary;

String query = """
    PROFILE
    MATCH (c:Customer {id: $customerId})-[:PURCHASED]->(p:Product)
    RETURN p.sku AS sku
    """;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    ResultSummary summary = session.run(
        query, java.util.Map.of("customerId", "C001")
    ).consume();

    summary.queryProfile().ifPresent(root -> {
        System.out.println("Root operator: " + root.operatorType());
        System.out.println("Rows: " + root.rows().orElse(-1));
        System.out.println("DB Hits: " + root.dbHits().orElse(-1));
    });
}
```

In this example, `driver` is already created and lifecycle-managed at the application layer. `consume()` ensures the entire result/summary is received before reading the plan. The root operator represents only **one node of the plan tree**; for a complete analysis, traverse `children()`, checking `operatorType()` and per-operator metrics. `-1` is an illustrative fallback when a metric is absent, **not a Neo4j measurement**.

Older Java Driver versions have `ResultSummary.profile()` and `ProfiledPlan.records()`/`dbHits()`; those APIs are marked deprecated in newer driver releases. Do not copy a 6.2+ snippet into a 5.x driver without verifying the API in use.

### 11.2. Spring Data Neo4j

Spring Data Neo4j applications can use `@Query` or `Neo4jClient` for Cypher. Plan verification is commonly done with **the exact same Cypher and parameters** in Neo4j Browser/`cypher-shell` or through the Neo4j Java Driver in a controlled manner. Keep in mind:

- Enabling `PROFILE` on a write query can **actually mutate the graph**, even inside a `@Transactional` service.
- The Cypher string, parameter types, and conditions generated or passed by Spring must match the measured query; plans can differ when parameters or data differ.
- The driver/API may add entity mapping overhead, lazy loading, or separate queries. When measuring at the service layer, do not assume a single plan represents the entire application operation.
- Inspect `Rows` and `DB Hits` to pinpoint Neo4j-side costs while monitoring application-side latency and throughput.

## 12. Misconceptions That Cause Misguided Tuning

| Misconception | Correct Understanding |
| --- | --- |
| “`Estimated Rows = 100` means the DB read 100 nodes.” | It is the **estimated output rows of the operator**, not node count or read count. |
| “`Rows = 1` so the query has no issues.” | Aggregation or `LIMIT` can return one row after processing huge volumes of data. |
| “`DB Hits = 1,000` means 1,000 disk reads.” | DB Hits counts storage-engine operations; distinguish it from page-cache misses and physical I/O. |
| “Query A has fewer DB Hits so it is definitely faster than B.” | Compare with identical semantics, data, cache, and runtime, and measure latency/CPU/memory. |
| “`EXPLAIN` shows how many DB Hits the executed query cost.” | `EXPLAIN` **does not run**; use `PROFILE` to obtain actual measurements. |
| “`PROFILE DELETE` is just a preview.” | `PROFILE` executes the real write operation; use `EXPLAIN` to check beforehand. |
| “Moving `WHERE` before `MATCH` definitely reduces DB Hits.” | The Cypher planner picks its own strategy; inspect the plan and preserve semantics. |
| “An operator with `DB Hits = 0` costs no time.” | Sorting, aggregation, CPU, memory, and network can still consume substantial resources. |
| “`Memory (Bytes)` can be summed across all operators.” | Each operator typically reports its own peak; query-wide peak is not a simple sum. |
| “Multiple `Time (ms)` cells with the same value mean each operator spent that much time.” | Operators fused into the same pipeline can share a single pipeline timing measurement. |
| “The planner estimated wrong so the index is broken.” | Bad estimates can stem from skew, selectivity, statistics, or plan cache; check index status and real data. |
| “The planner always uses an index if one exists.” | The planner chooses by estimated cost; a scan can be cheaper on small data or low-selectivity conditions. |

## 13. Checklist for Analyzing a Slow Query

1. **Verify correctness:** what result set does the query return, and are there duplicates from multiple paths/relationships?
2. **Run `EXPLAIN`:** identify leaf operators, indexes/scans, `Estimated Rows`, traversal direction, and potential Cartesian products.
3. **Run `PROFILE` safely:** only on read queries or test data permitted to be modified. Record `Rows` and `DB Hits` per branch.
4. **Locate the first row-inflation point:** compare `Estimated Rows` with `Rows` across `Expand`, joins, `OPTIONAL MATCH`, filters, and aggregations.
5. **Locate storage-heavy regions:** compare operator `DB Hits`; cross-check page cache, memory, and time when available.
6. **Inspect context:** runtime, Neo4j version, plan cache, parameters, skewed data, transaction/cluster topology, and concurrent load.
7. **Choose a small, evidence-backed change:** index/constraint, selective predicate, traversal pattern, subquery separating branches, or fixing an unintended Cartesian product.
8. **Re-measure and compare results:** same semantics, same inputs; evaluate latency, resources, and stability before deploying.

## 14. Practice Exercises

1. On the sample graph, run `PROFILE MATCH (c:Customer)-[:PURCHASED]->(p:Product) RETURN count(*)`. Explain why `Rows` at `ProduceResults` can be 1 while operators below process 5 relationships.
2. Compare `PROFILE MATCH (c:Customer), (p:Product) RETURN c, p` with the query containing `[:PURCHASED]`. Explain why row counts 9 and 5 reflect two **different semantics**.
3. Test `EXPLAIN` before and after creating a constraint on `Customer.id`. On a small graph, might the planner still scan? Explain in terms of cost.
4. Suppose an `Expand(All)` operator has `Estimated Rows = 50`, `Rows = 5,000`, and `DB Hits = 12,000`. Which operators and details would you inspect before proposing an index or rewriting the query?
5. Two `PROFILE` runs of the same query have nearly equal DB Hits yet very different execution times; list at least three reasons unrelated to a bad query plan.
6. Write a query finding each customer along with two counts: `PURCHASED` relationships and `VISITED` relationships. Use subqueries to separate branches so the two sets do not multiply each other, then compare the plan against a combined approach.

## 15. Takeaways

- **`Estimated Rows`** is each operator's predicted output during **planning**; it can diverge due to data skew, statistics, and selectivity assumptions.
- **`Rows`** is the actual number of rows emitted by each operator in **`PROFILE`**; it is not distinct node count and does not necessarily equal the final row count.
- **`DB Hits`** indicates storage-engine work, **differs from disk reads**, and does not solely determine latency.
- **`EXPLAIN` does not run the query**; **`PROFILE` executes it for real**, including any write side effects.
- Read **the entire operator tree**, watching fan-out at `Expand`, `CartesianProduct` branches, late filters, aggregations/sorts, page cache, memory, and runtime.
- Optimize only after confirming **the correct result set**, making fair comparisons, and re-measuring on representative data.

### Official References

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual — Operators](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/)
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — Query caches](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/)
- [Neo4j Operations Manual — Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/)
- [Neo4j Java Driver API — `ResultSummary`](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/ResultSummary.html)
- [Neo4j Java Driver API — `QueryProfile`](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/summary/QueryProfile.html)
