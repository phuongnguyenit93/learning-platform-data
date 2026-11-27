# Comparing Plans Before and After Changes Using the Same Dataset

A Neo4j query can return the **exact same result** while differing dramatically in intermediate rows, data accesses, memory, and execution time. When adding an **index**, rewriting `WHERE`, changing relationship traversal direction, or adjusting aggregations in Cypher, the reliable way to verify improvement is **placing the before and after execution plans side by side, with the same data and identical execution conditions**.

This is a hands-on lesson in the **Execution Plans** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. In a property graph system, nodes and relationships are queried with Cypher; the plan-comparison techniques below also apply when tuning path queries, pagination, the Java Driver, and Spring Data Neo4j. The content uses Neo4j 5 syntax as reference. Operator names or plan reporting details may vary across versions and runtimes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the **logical query**, **physical plan**, and execution metrics.
2. Design a **before–after A/B test** with the same graph, parameters, and expected results.
3. Use `EXPLAIN` to compare projected plans and `PROFILE` to inspect actual row counts and costs.
4. Recognize common operators such as `NodeByLabelScan`, `NodeIndexSeek`, `Filter`, `Sort`, `Top`, `Expand(All)`, and `EagerAggregation` when they appear in a plan.
5. Build an evidence table to conclude which change truly helps while stating the limits of the measurement.

## 2. What Questions Does Reading a Plan Answer?

Cypher describes **the result to retrieve**. Neo4j's planner picks how to access nodes, traverse relationships, filter, join, aggregate, and sort. The same statement can produce different physical plans when statistics, schema, or versions change.

| Component | What Does It Show? | What Can It Conclude? |
|---|---|---|
| `EXPLAIN` | **Projected** plan, row/cost estimates; **does not execute** the query | Projected scan vs. index usage, presence of `Sort`, step ordering |
| `PROFILE` | **Executes** the query and attaches metrics such as `Rows` and `DB Hits` to the plan | How many rows flow through operators; sources of heavy access |
| Query results | Business rows, columns, and values | Whether two alternatives actually return equivalent results |
| Repeated timing measurements | Latency distribution under specific test conditions | Whether a change improves observed latency or merely one plan metric |

**Never substitute “a pretty plan” for verifying results.** For example, adding `LIMIT 20` or dropping a `MATCH` branch can make a query very fast while returning incomplete data. Conversely, fewer `DB Hits` is usually a positive sign, yet **does not guarantee** lower execution time under every condition.

## 3. Principles of Fair Comparison

To isolate the benefit of **one change**, hold all other factors constant:

| Factor | Before and After Condition |
|---|---|
| Graph | Same database, same node/relationship sets, same properties and values |
| Parameters | Same values, **same types** (number, string, `DATE`, `DATETIME`, …) |
| Query under test | Keep identical when measuring only index impact; alter only the piece being tested when testing a Cypher rewrite |
| Version/runtime | Keep the same Neo4j version and execution environment within a comparison run |
| Results | Verify the exact same row set, values, and ordering if ordering is promised |
| Schema | When testing an index's impact, only the target index is the intentionally varied variable |
| System load | Minimize concurrent writes and heavy queries during measurement |
| Cache | Warm up comparably; never compare one cold run against one warm cached run |

When testing **adding an index**, graph data must stay identical while schema, index structures, and related statistics change intentionally. When testing **rewriting a query**, keep both data and schema identical, and prove both Cypher queries return the exact same result.

One `PROFILE` run suffices to inspect the plan, **not** to draw stable conclusions about latency. Separate plan analysis from repeated latency measurement.

## 4. Setting Up a Fixed Neo4j Dataset

This example tests the impact of a **range index** on the `orderNo` property of `:PlanSampleOrder`. We want enough nodes to clearly observe the difference between a label scan and an index lookup, while remaining small enough for practice on a test machine.

**Run the data creation script only once in a dedicated practice database.** Re-running `CREATE` creates duplicate nodes and breaks the “same dataset” rule. Never run examples on a production database or anywhere existing nodes share these labels.

~~~cypher
UNWIND range(1, 10000) AS n
CREATE (:PlanSampleOrder {
  orderNo: n,
  amount: 100000 + (n % 20) * 10000,
  createdAt: date('2026-01-01') + duration({days: n % 365}),
  status: CASE WHEN n % 3 = 0 THEN 'PAID' ELSE 'NEW' END
});
~~~

The dataset contains 10,000 simulated orders; `orderNo` holds integers from `1` to `10000`, while `amount`, `createdAt`, and `status` are computed **deterministically** from `n`. Do not use `rand()` or current timestamps, which would cause regenerated datasets to differ.

Record a **data fingerprint** before starting:

~~~cypher
MATCH (o:PlanSampleOrder)
RETURN count(o) AS nodeCount,
       count(DISTINCT o.orderNo) AS distinctOrderNos,
       min(o.orderNo) AS minOrderNo,
       max(o.orderNo) AS maxOrderNo,
       sum(o.orderNo) AS sumOrderNo,
       sum(o.amount) AS sumAmount;
~~~

Expected result if data was created cleanly once:

| Metric | Value |
|---|---:|
| `nodeCount` | 10,000 |
| `distinctOrderNos` | 10,000 |
| `minOrderNo` | 1 |
| `maxOrderNo` | 10,000 |
| `sumOrderNo` | 50,005,000 |
| `sumAmount` | 1,950,000,000 |

These metrics catch common mistakes (such as running creation twice), though they are not cryptographic proof that every property and relationship is immutable. In real systems, also verify primary key sets, relationship counts by type, and ensure no write transactions occur during measurement.

### Define a Target Query

Find up to 20 orders whose numbers lie in `[8500, 8600)`, sorted ascending by order number:

~~~cypher
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

The correct result has **20 rows** with `orderNo` from `8500` to `8519`. `orderNo` is unique in the sample data so ordering is deterministic, making before/after result comparison straightforward. If an experiment uses data with duplicate sort keys, add a tie-breaker key to verify stable ordering.

## 5. Step A: Capture the Plan **Before** Creating the Index

First, ensure the practice database **does not yet have an equivalent property index** on `:PlanSampleOrder(orderNo)`. Run:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

If a suitable index on this label and property already exists, a “before index” measurement is no longer clean. Either use a fresh test database or proceed as a **query rewrite comparison under a fixed schema**. Never drop an index serving a real application just to reproduce a lesson.

Run `EXPLAIN`:

~~~cypher
EXPLAIN
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

Without a suitable index, a plausible plan scans nodes labeled `PlanSampleOrder`, checks `orderNo`, and then handles sorting/limiting. **Do not try to guess exact operator names or order** because the optimizer can fuse, transform, or substitute operators depending on the runtime.

Next, run `PROFILE` with **the exact same query**:

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500 AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

Save a screenshot or record of the following fields from the plan in Neo4j Browser or your query tool:

1. **Data-access starting operator**, such as label node scan or index lookup.
2. **`Rows` at each operator**: rows produced, filtered, and passed upstream.
3. **`DB Hits`**, along with actual access stats if shown by the tool.
4. **`Sort`/`Top`, `Filter`**: processing steps still required after fetching nodes.
5. **Returned result**: 20 rows, `orderNo` 8500–8519, accurate `amount` values.

If `PROFILE` reports execution time, record it strictly as **that run's timing**. Do not treat it as representative of every run.

## 6. Step B: Add the Index While Keeping **Data Identical**

Create a single index to support the range condition:

~~~cypher
CREATE RANGE INDEX plan_sample_order_no_idx IF NOT EXISTS
FOR (o:PlanSampleOrder) ON (o.orderNo);
~~~

Monitor the index until `state = 'ONLINE'`:

~~~cypher
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, state
WHERE name = 'plan_sample_order_no_idx'
RETURN name, type, labelsOrTypes, properties, state;
~~~

A new index may show `POPULATING` while building. If the index does not appear as expected, check the actual name and schema; if `FAILED`, resolve the error before measuring. `IF NOT EXISTS` avoids some duplicate-creation errors but does not replace checking the actual index.

**Re-run the fingerprint query from section 4.** `nodeCount`, `distinctOrderNos`, `minOrderNo`, `maxOrderNo`, `sumOrderNo`, and `sumAmount` must remain identical because creating an index does not add, modify, or delete nodes in the dataset.

Once the index is `ONLINE`, re-run **verbatim** the same `EXPLAIN` and `PROFILE` statements from Step A. Do not add hints, change the `8500–8600` range, or alter `LIMIT` or `ORDER BY`. This is essential to attribute plan changes solely to the index.

The subsequent plan may show an operator such as `NodeIndexSeekByRange` or `NodeIndexSeek` to look up nodes over the `orderNo` range; the optimizer may also leverage index key order for `ORDER BY orderNo ASC` and `LIMIT 20`. However, it is **not guaranteed** to always drop `Sort` or pick the index: cost rules, statistics, and data size govern the actual plan.

### Illustrating the Data Path

~~~mermaid
flowchart LR
    subgraph Before["Before: no suitable index"]
        A["Scan :PlanSampleOrder nodes"] --> B["Filter orderNo in range"]
        B --> C["Sort / take 20 rows"]
    end
    subgraph After["After: index is ONLINE"]
        D["Range index on orderNo"] --> E["Seek values 8500..8599"]
        E --> F["Return 20 rows in order"]
    end
~~~

The diagram illustrates **a candidate strategy that may be chosen**, not a transcript of an actual `PROFILE` plan measured on a live database.

## 7. Comparing Before–After Plans with an Evidence Table

Because this lesson has no live execution data, the table below is a **template for the learner to fill in**, not verified measurement output:

| Criterion | Before: No Range Index | After: With Range Index |
|---|---|---|
| Node count in graph | 10,000 (verified by query) | 10,000 (re-verified) |
| `orderNo` results | 8500–8519 | 8500–8519 |
| Data-reading operator | *Record from `PROFILE`* | *Record from `PROFILE`* |
| `Rows` at reading operator | *Fill in observed count* | *Fill in observed count* |
| Total `DB Hits` | *Fill in observed count* | *Fill in observed count* |
| `Sort` or `Top` present? | *Fill in from plan* | *Fill in from plan* |
| Execution time after warm-up | *Measure across runs* | *Measure across runs* |
| Conclusion | *Based on collected data* | *State benefits and limits* |

A **hypothetical** example of reading the table: if before adding the index the plan had to inspect 10,000 nodes, whereas afterward it accessed only a 100-key range and returned 20 rows, that signals reduced data scanning. Exact `Rows` or `DB Hits` figures must come from `PROFILE`, because operators may stop early, read from cache, or emit rows differently than expected.

### Operators Worth Watching

| Operator (names may vary by version) | Common Role | Question When Comparing |
|---|---|---|
| `NodeByLabelScan` | Scan nodes by label | Is it scanning a large set only to filter down to a few results? |
| `NodeIndexSeek` / `NodeIndexSeekByRange` | Lookup via a property index | Does the index match the predicate and is it selective enough? |
| `NodeIndexScan` | Scan index entries | Is it leveraging ordering or scanning a large portion of the index? |
| `Filter` | Discard rows after an earlier step | How many rows are dropped; can the filter be pushed earlier? |
| `Sort` / `Top` | Full sort or maintain ordered top results | Can sorting be avoided via an index or rows reduced before sorting? |
| `Expand(All)` / `Expand(Into)` | Traverse relationships between nodes | Which relationship branch is sharply inflating row counts? |
| `EagerAggregation` | Grouping/aggregation with an execution boundary | How many rows are processed before grouping? |

**`Rows` does not equal distinct node count.** One node can appear in multiple rows when expanding multiple relationships. Likewise, **`DB Hits` does not equal disk reads**: it measures data-layer accesses in the plan, influenced by operator mechanics and runtime. Evaluate it alongside row counts, CPU, memory, and timing rather than comparing a single metric in isolation.

## 8. Second Experiment: Rewrite the Query, **Keep the Index Identical**

After Step B, keep the database and `plan_sample_order_no_idx` index unchanged. Test two equivalent filter forms **on the sample data where `orderNo` is confirmed to be INTEGER**.

**Variant C — transforming the property inside the predicate:**

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE toInteger(o.orderNo) >= 8500
  AND toInteger(o.orderNo) < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

**Variant D — comparing the property directly:**

~~~cypher
PROFILE
MATCH (o:PlanSampleOrder)
WHERE o.orderNo >= 8500
  AND o.orderNo < 8600
RETURN o.orderNo AS orderNo, o.amount AS amount
ORDER BY orderNo ASC
LIMIT 20;
~~~

`toInteger(o.orderNo)` does not change the integer values on sample nodes, yet wrapping the property in a function can prevent the optimizer from turning the predicate into a direct lookup on the `orderNo` index. Variant D is typically a better candidate to leverage the range index. **This is a hypothesis to test with `PROFILE`**, not a guarantee every version will produce a different plan.

Two queries are equivalent only when data types and values match. If string data, non-numeric strings, or `null` values exist, type conversion can alter semantics. Before applying a rewrite technique in a real application, inspect the schema and real data.

In this experiment, **do not alter indexes, data, `RETURN`, `ORDER BY`, or `LIMIT`**. Compare result row counts along with `orderNo` and `amount` values; then compare operators, `Rows`, `DB Hits`, and multi-run timings. If both produce the exact same plan, record honestly that this rewrite **made no measurable difference in the test environment**.

## 9. When Comparing Graph Queries with Relationships

Path queries introduce **row multiplication during relationship expansion**. For instance, a customer has many orders and many reviews:

~~~cypher
MATCH (c:Customer)
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN c.customerId AS customerId,
       count(o) AS orderCount,
       count(r) AS reviewCount;
~~~

With `m` orders and `n` reviews, the query can generate `m × n` rows per customer before aggregating. The plan can show `Rows` climbing across expansion steps. If the business requirement is actually counting **orders** and **reviews** independently, the query above can even return **wrong counts**, not merely run slowly.

In Neo4j 5.23+, you can test a branch-separated aggregation version:

~~~cypher
MATCH (c:Customer)
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    RETURN count(o) AS orderCount
}
CALL (c) {
    MATCH (c)-[:WROTE]->(r:Review)
    RETURN count(r) AS reviewCount
}
RETURN c.customerId AS customerId, orderCount, reviewCount;
~~~

**Fairness warning:** the two examples above are not an equivalent A/B pair if customers have multiple records on both branches. Before using them to compare latency, you must **fix the original query so both return identical results** (for example, using `count(DISTINCT ...)` for both node counts as business rules dictate), or explicitly document it as **a change fixing both a logic bug and the execution plan**. Never report a speedup from a query with wrong numbers as a pure optimization win.

For complex connected queries, watch:

- `Rows` **before and after** relationship expansion operators: does row count grow multiplicatively?
- `DB Hits` during edge traversals: is the starting variable selective enough to anchor on the right nodes?
- Placement of aggregation and filtering: can a condition be applied earlier **without changing results**?
- Node identity conditions: does a node variable repeated across multiple paths need `DISTINCT`?

## 10. Measuring Latency Without Fooling Yourself

`PROFILE` reveals internal execution, yet latency from a single call can be skewed by caches, JIT, host resources, network, and concurrent queries. For before–after evaluation:

1. **Lock variables:** same database, data, version, parameters, and output row count; document every schema or Cypher change.
2. **Verify indexes are `ONLINE`** before measuring an indexed option.
3. **Warm up comparably:** run several iterations before taking official measurements; if you run A then B in the same session, B may benefit from a pre-warmed page cache.
4. **Repeat across many runs** on the same workload, alternating A/B when comparing two queries on the same schema; report the median and spread rather than only the fastest single run.
5. **Measure plan and latency separately:** use `PROFILE` to inspect `Rows`/`DB Hits` differences, and run separate timing measurements so profiling overhead does not distort latency.
6. **Verify row counts, values, and ordering** after every change; for aggregations, test 0, 1, and many-relationship edge cases.

In a Java Driver application, pass identical strongly typed parameters and measure the same read method (same transaction mode, fetch size, routing, and network conditions). If using Spring Data Neo4j, check the exact Cypher the framework sends and its result-mapping/conversion steps. Client-observed duration also includes connection handling, data transfer, and mapping, so it can differ from timings in Neo4j Browser.

### Why Look at Distributions Rather Than a Single Number?

Suppose one measurement after a change is faster, while subsequent runs are slower; you cannot claim a stable improvement. For small samples, record the **median**, slow outliers, and load conditions. In real systems, also track percentiles such as `p95` and monitor write-query impact if the change involved adding an index.

## 11. Common Methodological Mistakes

| Mistake | Why It Distorts Conclusions | How to Fix |
|---|---|---|
| Re-running data creation between measurements | Alters data size or distribution | Create once; compare fingerprints before/after |
| Changing parameters or data types | Selectivity and plans can differ | Lock identical parameters and types |
| Comparing a cold `PROFILE` against a warmed cache run | Speed is biased by cache warmth | Warm up comparably and repeat multiple times |
| Comparing a query returning 100 rows against one returning 20 rows | Two different requirements | Prove identical expected result sets |
| `ORDER BY` missing a tie-breaker when sort keys collide | Tied rows can swap order | Add a deterministic tie-breaker when required |
| Creating an index and measuring while `POPULATING` | Index is not ready yet | Confirm `ONLINE` |
| Adding multiple indexes, changing Cypher, and switching runtime at once | Cannot tell which change caused the effect | Isolate one controlled experiment at a time |
| Treating `DB Hits` as disk reads or absolute speed | Metrics measure different layers | Read multiple metrics and time latency separately |
| Assuming `NodeIndexSeek` must appear | Optimizer may pick another plan | Read the actual `EXPLAIN`/`PROFILE` output |
| Drawing broad conclusions from a tiny dataset | Scans can be cheaper than indexes | Test on representative data |

Never drop application indexes or modify production schemas just to reproduce a lesson. Experiments should run in a dedicated, load-controlled environment free of production transactions.

## 12. Reusable Comparison Report Template

Copy the template below into your notes when tuning a Cypher query:

~~~text
Business goal:
Database / Neo4j version / runtime:
Measurement date / system load:
Dataset: nodes, relationships, fingerprint:
Parameters (values and types):
Before condition: schema, query, index state:
After condition: what single change was made?:

CORRECTNESS:
  Row count before/after:
  Keys and aggregated values before/after:
  ORDER BY and ordering before/after:

EXPLAIN/PROFILE PLAN:
  Data-reading operators before/after:
  Rows across key steps:
  DB Hits before/after:
  Sort/Top, relationship expansion, aggregation:
  Estimated vs. actual Rows:

LATENCY:
  Warm-up runs / measured runs:
  Median before/after:
  Spread, p95 if enough runs:

CONCLUSION:
  Observed benefit:
  Trade-offs (writes, index storage, memory):
  Test limitations / next verification steps:
~~~

Reports should include both **evidence and explanation**: “After adding the range index, the plan switched from a label scan to a range seek and `DB Hits` decreased in this test” is a sound conclusion when backed by matching metrics. Saying “indexes are always faster” overreaches beyond the measured data.

## 13. Self-Practice Exercises

### Exercise 1 — Fill In the Results Table Yourself

Perform Steps A and B in an isolated practice database. Fill in the data-reading operator name, `Rows`, `DB Hits`, and presence/absence of `Sort` for each option. Answer: did Neo4j use the range index after creation? If not, which factors in the data or plan might explain why?

**Hint:** check `ONLINE` state, `orderNo` type, node count, predicates, statistics, and the actual plan. Do not force results to match initial expectations.

### Exercise 2 — Separating Two Causes

A colleague simultaneously added an index on `createdAt` and changed a filter from `date(o.createdAt)` to `o.createdAt`, then reported “the index made the query 60% faster.” Why is this inconclusive? Propose an experiment to isolate the impact of each change.

**Reference answer:** two changes were applied at once. Hold the dataset and parameters constant; measure the old query vs. the new query **under the same schema** to evaluate the rewrite. Then hold a single query constant and measure before/after adding the index in a controlled environment. You must also verify `createdAt` is truly the same temporal type and both expressions have identical semantics on the measured data.

### Exercise 3 — Same Plan, Different Timings

Two `PROFILE` runs show the exact same operators and nearly equal `DB Hits`, yet the second run finishes noticeably faster. Does that necessarily mean the optimizer improved the plan?

**Answer:** no. The plan stayed the same, while data may have entered the page cache, system resources may have been less contended, or measurement variance occurred. Use consistent warm-up and multiple runs before concluding on execution time.

### Exercise 4 — Evaluating Correctness

The before query uses `MATCH` expanding two relationship branches and then computes `sum(amount)`; the after query uses subqueries aggregating each branch. Both return one row per customer, yet total amounts differ. Should you report the latencies of the two queries as a “performance optimization”?

**Answer:** not yet. Verify which aggregation matches business rules and bring both queries to identical results before comparing them as equivalent alternatives. If the change also fixed a correctness bug, explicitly label it a **logic fix** accompanied by a plan change, not a pure speedup.

## 14. Takeaways

- **Same dataset, same parameters, same result goal** are the baseline conditions for fair plan comparison.
- **`EXPLAIN` shows the projected strategy; `PROFILE` shows execution metrics.** Both must be read in the context of your running Neo4j version.
- **Change only one intentional variable per experiment.** When testing an index, keep Cypher unchanged; when testing a Cypher rewrite, keep schema and data unchanged.
- **Track `Rows`, `DB Hits`, `Sort`/`Top`, and output row counts**, combined with multi-run latency measurements under comparable warm-up.
- **Prove correctness before claiming optimization.** A faster plan that returns wrong or missing data is not a valid improvement.
