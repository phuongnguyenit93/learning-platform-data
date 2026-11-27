# Detecting CartesianProduct, Eager, Sort, and Large Intermediate Sets in Neo4j Execution Plans

## 1. Goal: Find What Actually Consumes Resources

In Neo4j, a Cypher query describes **the graph pattern to find**, not each physical step to locate it. The query planner picks an **execution plan** made up of *operators* such as `NodeIndexSeek`, `Expand(All)`, `Filter`, `CartesianProduct`, `Eager`, and `Sort`. Performance depends heavily on how much data flows **through intermediate operators**, not just on the number of rows in the final result.

For example, an application wants to return the 10 most viewed products. The query has `LIMIT 10`, yet it might have to expand millions of relationships, aggregate, and sort a huge set before returning 10 rows. Looking only at execution time or the 10 output rows misses the root cause.

This lesson focuses on four signals in execution plans:

| Signal | Common Impact | Diagnostic Question |
| --- | --- | --- |
| `CartesianProduct` | Multiplies every row from the left set with every row from the right set | Do the two branches genuinely need every pair combined? |
| `Eager` | Forces upstream work to finish and buffers intermediate rows before continuing | Is there a read/write conflict requiring a semantic barrier? |
| `Sort` | Sorts a row stream, typically buffering all input rows to be ordered | Can we shrink the input, use `Top`, or leverage index ordering? |
| Large intermediate sets | Increases `Rows`, `DB Hits`, memory, or downstream work | At which exact operator does the data stream blow up? |

**Seeing one of these operators does not automatically mean the query is wrong.** The goal is determining whether it is necessary, how large the data flowing through it is, and whether cost can be reduced **while preserving result semantics**.

## 2. Using `EXPLAIN` and `PROFILE` Properly

### 2.1. Difference Between Projected Plan and Measured Execution

```cypher
EXPLAIN
MATCH (p:Product)
WHERE p.active = true
RETURN p.name;
```

`EXPLAIN` shows the **projected plan**, without executing the Cypher query or writing data. It is the first choice when inspecting unfamiliar queries or statements containing `SET`, `CREATE`, `MERGE`, or `DELETE`.

```cypher
PROFILE
MATCH (p:Product)
WHERE p.active = true
RETURN p.name;
```

`PROFILE` **actually executes** the Cypher statement, recording row counts, data accesses, and performance metrics. For write queries, `PROFILE` **can mutate the graph**. Run it only in an intentional environment or transaction; prefer `EXPLAIN` before deciding to profile a write query.

`PROFILE` also introduces overhead, so measure under suitable conditions using representative data and parameters rather than drawing conclusions from a single run.

### 2.2. Reading the Key Columns

| Column / Component | Meaning | How to Read When Hunting Bottlenecks |
| --- | --- | --- |
| `Operator` | Execution step, such as `Expand(All)` or `Sort` | Identify the type of work taking place |
| `Details` | Nodes/relationships, predicates, expressions, or indexes used | Verify whether the right label, type, property, and direction are scanned |
| `Estimated Rows` | Number of rows the planner **estimated** at the operator | Compare with `Rows` to find misprediction zones; do not treat as actual count |
| `Rows` | Number of rows the operator **actually produced** during `PROFILE` | Find where row counts surge before getting filtered or aggregated |
| `DB Hits` | Storage-layer access statistics | Unusually large counts can indicate scans, repeated seeks, or costly expansions |
| `Memory (Bytes)` | Tracked peak memory for the operator | Pay special attention to `Sort`, `Eager`, and aggregate/join operators |
| `Ordered by` | Ordering an operator guarantees on its output rows | Helps spot whether an extra `Sort` can be avoided |
| `Page Cache Hits/Misses` | Page hits/misses in cache, when reported by runtime/edition | Compare under equivalent cache conditions |
| `Time (ms)`, `Pipeline` | Execution time and pipeline when reported | May apply to an entire fused pipeline; do not assume it is one operator's exclusive time |

Two caveats:

- `Memory (Bytes)` on a row is the **per-operator peak**, not total query memory. Do not sum those peaks arbitrarily; check total memory in the plan footer if reported.
- Plans can differ by Neo4j version, runtime, indexes, graph statistics, and parameters. Never expect operator names to appear **identically** across two environments.

### 2.3. Reading the Diagram by Data Flow

Plans are displayed as a tree, with records flowing from **leaf operators** (scans/seeks at the bottom) up to `ProduceResults` at the top. Illustrative example, not a fixed plan output:

```text
+ProduceResults              10 rows
 |
 +Top                        10 rows
  |
  +Projection               5,000 rows
   |
   +Filter                  5,000 rows
    |
    +Expand(All)            80,000 rows
     |
     +NodeIndexSeek            1 row
```

The bottleneck may lie at the `Expand(All)` step generating 80,000 rows, even though the output has only 10 rows. Numbers here only illustrate how to read; obtain actual measurements from `PROFILE` on your specific query.

An effective analysis sequence:

1. Start at `ProduceResults` to see how many rows the final output contains.
2. Trace down the branches to locate where `Rows` suddenly jumps, or where `DB Hits`/memory is high.
3. Identify the cause: joining two independent sets, broad scan, overly deep relationship traversal, late grouping, or late sorting.
4. Propose a way to shrink data **before the bottleneck**, then re-run `PROFILE` under the same data, parameters, and load conditions.

## 3. Detecting `CartesianProduct`

### 3.1. Why Does This Operator Easily Explode Row Counts?

`CartesianProduct` pairs **every row from the left branch with every row from the right branch**. If the two branches have \(N\) and \(M\) rows respectively, output combinations can reach \(N \times M\).

| Left Branch Rows | Right Branch Rows | Pairs Generated |
| ---: | ---: | ---: |
| 10 | 20 | 200 |
| 1,000 | 5,000 | 5,000,000 |
| 50,000 | 100,000 | 5,000,000,000 |

Example of two independent graph patterns:

```cypher
EXPLAIN
MATCH (u:AppUser), (p:Product)
RETURN u.id AS userId, p.id AS productId;
```

There is no relationship or join condition linking `u` and `p`. Semantically, the query **asks for every user–product pair**, so the planner may choose `CartesianProduct`. Simply adding `LIMIT 10` at the end does not turn the overall requirement into a conditional relationship query; blocking operators such as `Sort` or aggregations may still have to process the large set.

**Signal in the plan:** look for `CartesianProduct` with high `Rows`; trace both child branches to see their input row counts and why they are unlinked. Other join/nested-loop variants can also multiply row counts even without bearing the exact name `CartesianProduct`.

### 3.2. Fixing from the Query Model

If business logic needs **products viewed by a specific person**, write the relationship explicitly:

```cypher
PROFILE
MATCH (u:AppUser {id: $userId})-[:VIEWED]->(p:Product)
WHERE p.active = true
RETURN p.id, p.name;
```

This query only retrieves products with a `VIEWED` edge from the target user. A unique constraint or range index on `AppUser.id` lets the planner start from a selective node. A lookup index on the `AppUser` label **does not replace** a value index on `id` when filtering by property.

If the goal is joining two sets by a **business key**, write an actual join predicate:

```cypher
MATCH (u:AppUser)
MATCH (a:UserAudit)
WHERE u.id = a.userId
RETURN u.id, a.createdAt;
```

Here, joining by property means something different from a graph relationship; the planner may choose a hash join, index seek, or another strategy. Inspect indexes and actual plans to choose an efficient approach. Do not invent a relationship if the graph does not store one.

### 3.3. When a Cartesian Product Is Intentional

Some problems require generating every combination (test matrices, scheduling combinations, candidate pairs). In those cases:

- Keep input scopes small enough and filter before forming the Cartesian product.
- Evaluate \(N \times M\) before running across full data.
- Choose pagination/batching strategies and resource limits aligned with business needs.
- Do not make removing `CartesianProduct` at all costs the goal: **correct results** come first, then optimization.

## 4. Detecting and Properly Understanding `Eager`

### 4.1. `Eager` Is a Data Barrier, Usually Protecting Semantics

Many Neo4j operators can **stream rows lazily** to the next step. Conversely, `Eager` requires upstream steps to complete and collects relevant rows before allowing downstream processing to begin. This can raise memory consumption and time-to-first-row latency.

Why does the planner insert `Eager`? A query might both **read the graph** and **modify the very structure or properties affecting the read**. If mutations happened mid-scan, the query could risk re-observing newly created elements or missing elements, diverging from Cypher's intended semantics. `Eager` separates the two phases to preserve semantics.

Example strictly to **inspect the plan**, without mutating data:

```cypher
EXPLAIN
MATCH (p:DemoProduct)
CREATE (:DemoProduct {id: p.id + 1000});
```

The query reads nodes with label `DemoProduct` and creates new nodes with the same label. This is a situation prone to read/write conflicts, prompting the planner to use a barrier such as `Eager`. Exact operators **depend on plan/version**, so verify directly rather than asserting it must always appear.

**Do not run `PROFILE` on the example above casually**: `PROFILE` will actually create nodes, which can cause duplicate `id` conflicts on repeated runs. For update statements, use `EXPLAIN` first; try `PROFILE` in a controlled practice database only if measurements are truly needed.

### 4.2. How to Evaluate Whether It Is Concerning

In `PROFILE` of a safely prepared write query, check:

- How many `Rows` enter `Eager`? 50 rows or millions of rows?
- What are the operator's `Memory (Bytes)` and the **query-wide peak memory**?
- Has data already been filtered by key, label, type, timestamp, etc. before `Eager`?
- Must all rows remain inside a single transaction to preserve atomicity?

Do not confuse `Eager` with `EagerAggregation`. `EagerAggregation` is a **grouping/aggregation** operator that must maintain computation state and can use memory proportional to group count; `Eager` typically separates plan phases to preserve read/write semantics. Although both can create memory pressure, **their causes and remedies differ**.

### 4.3. How to Reduce Pressure from `Eager`

1. **Shrink inputs**: identify nodes/relationships by keys and selective conditions before writing. Check whether the planner pushes predicates down early.
2. **Separate operations that do not need mixing**: e.g., create nodes first and relationships afterward when business consistency allows. Manage transactions properly for each step.
3. **Controlled batch processing** when data is too large: design small, idempotent batches with progress tracking and safe re-runnability. `CALL { ... } IN TRANSACTIONS` commits per batch and must run in implicit transaction mode; it **does not provide cross-batch atomicity**.
4. **Accept `Eager` when required for correctness**. Do not try to force the planner to drop a barrier merely to make the plan look shorter.

Notably, a `WITH` clause **does not automatically mean** materializing all data. The planner chooses the actual operators; only `EXPLAIN`/`PROFILE` reveals whether a barrier is present.

## 5. Detecting `Sort` and Other Blocking Steps

### 5.1. `Sort` Often Must Buffer the Entire Input to Be Ordered

```cypher
PROFILE
MATCH (p:Product)
RETURN p.id, p.price
ORDER BY p.price DESC;
```

If no access path naturally provides the desired ordering, the plan may contain `Sort`. With many rows, buffering rows to sort raises memory usage and wait time before results arrive.

When reading the plan:

- Find `Sort` and inspect `Details` to see **which expressions are sorted**.
- Inspect `Rows`/`Memory (Bytes)` on `Sort` and on the branch feeding into it.
- Determine why so many rows arrived upstream: scan, join, or relationship expansion.
- Distinguish sorting the entire result set from only taking **top N**.

### 5.2. `ORDER BY` with `LIMIT` Can Produce `Top`

```cypher
PROFILE
MATCH (p:Product)
RETURN p.id, p.price
ORDER BY p.price DESC
LIMIT 10;
```

The planner may use `Top` or `PartialTop` to retain only the best candidates instead of sorting and buffering the entire dataset. This usually reduces sorting memory, **yet does not guarantee reducing the number of input rows scanned**: to know the 10 highest-priced products without an ordered access path, the engine may still have to read many products.

`LIMIT` is not a “cure-all” for every `Sort`. If `ORDER BY` follows a large aggregation, groups must still be built before picking the top rows. If deep pagination uses a large `SKIP`, processing cost can also climb; consider cursor/keyset pagination with a stable sort key when appropriate.

### 5.3. Leveraging an Index to Return Ordered Data

For queries that frequently filter and sort by one property:

```cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product)
ON (p.price);
```

Once the index is `ONLINE`, test:

```cypher
EXPLAIN
MATCH (p:Product)
WHERE p.price >= $minPrice
RETURN p.id, p.price
ORDER BY p.price ASC
LIMIT 10;
```

An appropriate range index **can** allow the planner to retrieve data already ordered by `price`, reducing the need for a separate `Sort`. The outcome depends on predicates, sort direction, index, runtime, and cost estimation; never assume “index present means `Sort` disappears”.

Watch in the plan: the index lookup operator, the `Ordered by` column, and whether `Sort`/`Top` is present. For multi-column sorting, consider composite indexes and key order appropriately. Do not create indexes indiscriminately without measuring real queries and index maintenance cost.

## 6. Large Intermediate Sets Even Without the Three Operators Above

### 6.1. Source of Row Multiplication: Multi-Hop Expansion

Example finding “friends of friends” in a social graph:

```cypher
PROFILE
MATCH (u:AppUser {id: $userId})-[:FOLLOWS]->(f:AppUser)
      -[:FOLLOWS]->(suggested:AppUser)
RETURN suggested.id AS candidateId;
```

If the starting user follows 1,000 users and each of those follows 500 users on average, **two-hop paths** can reach hundreds of thousands, including many paths leading to the same `suggested` user. In the plan, `Expand(All)`, `Apply`, or traversal operators can show `Rows` climbing rapidly.

If business logic only needs **unique candidates**:

```cypher
MATCH (u:AppUser {id: $userId})-[:FOLLOWS]->(:AppUser)
      -[:FOLLOWS]->(suggested:AppUser)
WHERE suggested <> u
RETURN DISTINCT suggested.id AS candidateId;
```

`DISTINCT` removes duplicate results, yet when placed **after** a huge expansion, it does not eliminate the cost of generating those paths beforehand. It can also require `Distinct`, `OrderedDistinct`, or stateful aggregation operators. Optimize starting points, relationship scope, and early filtering accordingly.

### 6.2. `collect()` and Aggregation Over Large Sets

Consider the query:

```cypher
MATCH (u:AppUser)-[:VIEWED]->(p:Product)
WITH u, collect(p) AS viewedProducts
RETURN u.id, size(viewedProducts) AS viewedCount;
```

`collect(p)` can accumulate many nodes per user when the goal is only a **count**. A lighter formulation in terms of intermediate data:

```cypher
MATCH (u:AppUser)-[:VIEWED]->(p:Product)
RETURN u.id AS userId, count(p) AS viewedCount;
```

Both return the same view count per user when each `VIEWED` relationship represents one view to count. If data allows multiple `VIEWED` edges to the same product and business logic wants **distinct products**, use `count(DISTINCT p)`. Switching `collect` to `count` avoids buffering node lists, though aggregation still maintains per-group state.

### 6.3. Signs of Cardinality Misestimation

If `Estimated Rows` is tiny while actual `Rows` is huge at an `Expand` or join, the planner may have chosen a suboptimal strategy because statistics or estimation models did not reflect the data:

- Inputs include “hub” nodes with abnormally high degree.
- Predicates are hard to estimate or property value distributions are skewed.
- Labels and relationship types are omitted, giving the planner less information.
- An index exists, yet the predicate cannot use it or the index does not fit the query pattern.

Do not treat every gap between `Estimated Rows` and `Rows` as a Neo4j bug. They are two different kinds of information, and the planner must estimate before running. Trace to **the first operator where divergence spikes**, then inspect data, model, indexes, and parameters there.

### 6.4. Checklist of Operations That Can Inflate Intermediate Sets

| Query Pattern / Operator | Why It Can Be Expensive | Optimization Question |
| --- | --- | --- |
| `CartesianProduct` / joining two broad sets | Combinatorial row multiplication | Is there an actual join condition or relationship? |
| Multi-hop `Expand(All)` | Fan-out compounds per hop and degree | Can we start from a more selective node or cap hops/types? |
| Unbounded variable-length pattern | Path space can grow enormously | Is there a business upper bound? Is the full path needed? |
| `EagerAggregation`, `Distinct` | Must maintain group/deduplication state | Can input shrink earlier, or use `count` instead of `collect`? |
| `Sort`, `Top` | Ranking candidate sets | Can `LIMIT`, index order, or early filtering help? |
| Large `UNWIND` + repeated `MATCH` | Each item can trigger a scan or seek | Can we batch, reduce items, or change lookup strategy? |
| Multiple `OPTIONAL MATCH` branches | Can multiply combinations when each branch emits multiple rows | Are we multiplying relationships across independent branches? |

**Note:** placing `LIMIT` at the end reduces results sent to the client, but **does not necessarily** reduce upstream work. Prioritize shrinking data right where it starts expanding.

## 7. Hands-On Practice Executable in a Test Database

To observe these effects clearly, create a small demo dataset. Run only on a **test database**; do not use these demo labels on a production environment holding real data.

### 7.1. Creating Idempotent Sample Data

```cypher
CREATE CONSTRAINT demo_user_id_unique IF NOT EXISTS
FOR (u:DemoUser)
REQUIRE u.id IS UNIQUE;
```

```cypher
CREATE CONSTRAINT demo_product_id_unique IF NOT EXISTS
FOR (p:DemoProduct)
REQUIRE p.id IS UNIQUE;
```

```cypher
UNWIND range(1, 120) AS id
MERGE (u:DemoUser {id: id})
ON CREATE SET u.active = (id % 2 = 0);
```

```cypher
UNWIND range(1, 60) AS id
MERGE (p:DemoProduct {id: id})
ON CREATE SET p.price = id * 10000;
```

```cypher
MATCH (u:DemoUser {id: 1})
MATCH (p:DemoProduct)
WHERE p.id <= 5
MERGE (u)-[:VIEWED]->(p);
```

If the demo database did not initially contain these labels, the sample set has 120 `DemoUser` nodes, 60 `DemoProduct` nodes, and 5 `VIEWED` relationships. Using `MERGE` and uniqueness constraints keeps re-runs from creating duplicate copies.

### 7.2. Observing Cartesian Products

```cypher
PROFILE
MATCH (u:DemoUser), (p:DemoProduct)
RETURN sum(u.id + p.id) AS checksum;
```

The `RETURN` clause emits only **one aggregated row**, yet combining the two sets as requested can pass through **120 × 60 = 7,200 pairs** on the demo data alone. Find `CartesianProduct` and its `Rows`; the final count hides all intermediate work.

Contrast with a query specifying a relationship:

```cypher
PROFILE
MATCH (u:DemoUser {id: 1})-[:VIEWED]->(p:DemoProduct)
RETURN u.id AS userId, p.id AS productId;
```

The second query finds only five relationships in the demo data. The two queries **have different business requirements**, so compare them to understand how expressing relationship predicates affects cardinality, not to blindly replace every cross join.

### 7.3. Observing `Sort` and `Top`

```cypher
PROFILE
MATCH (p:DemoProduct)
RETURN p.id AS productId, p.price AS price
ORDER BY p.price DESC;
```

Then:

```cypher
PROFILE
MATCH (p:DemoProduct)
RETURN p.id AS productId, p.price AS price
ORDER BY p.price DESC
LIMIT 5;
```

Record the `Sort`/`Top` operator (or whatever strategy the planner chooses), `Rows`, `DB Hits`, and `Memory (Bytes)`. Numbers on a small set are strictly illustrative; scale up in a controlled manner if studying large-data behavior.

### 7.4. Observing a Scenario That May Require `Eager`

```cypher
EXPLAIN
MATCH (p:DemoProduct)
CREATE (:DemoProduct {id: p.id + 1000});
```

Look for `Eager` in the plan if the planner inserts a barrier. **Do not run `PROFILE` here unless you intentionally allow data modifications**; `EXPLAIN` suffices to see the projected plan. If your version/runtime does not show `Eager`, note the difference rather than insisting it must appear.

### 7.5. Measuring Intermediate Sets Caused by Aggregation

```cypher
PROFILE
MATCH (u:DemoUser)
OPTIONAL MATCH (u)-[:VIEWED]->(p:DemoProduct)
RETURN u.id AS userId, count(p) AS viewedCount;
```

Compare with:

```cypher
PROFILE
MATCH (u:DemoUser)
OPTIONAL MATCH (u)-[:VIEWED]->(p:DemoProduct)
WITH u, collect(p) AS products
RETURN u.id AS userId, size(products) AS viewedCount;
```

Both can produce the same counts on the demo data, yet how intermediate values are held differs. Locate the aggregation operator, `Rows`, and reported memory. Note that `collect(null)` does not add nulls to the list in Cypher semantics; when `OPTIONAL MATCH` matches no product, the expected count is 0.

## 8. Evidence-Based Optimization Workflow

A safe improvement cycle can follow these steps:

1. **Define query and target**: inputs, business result, database, Neo4j version, data/scale, and typical parameters; save the query and baseline results.
2. **Run `EXPLAIN`**: inspect the plan first and spot potentially expensive operators; never run `PROFILE` on write queries without preparation.
3. **Run `PROFILE` safely**: use read queries or a controlled test environment; record `Rows`, `Estimated Rows`, `DB Hits`, memory, time, and notable operators.
4. **Isolate the root cause**: focus on one issue at a time (e.g., cross join or large `Sort`). Determine why so much data enters that operator.
5. **Make an evidence-backed change**: add real relationship constraints, filter early, apply suitable indexes, retain only needed fields, trim aggregations/lists, or batch when business rules allow.
6. **Verify correctness**: compare results and consistency before/after, including empty sets, duplicates, NULLs, and pagination.
7. **Re-measure fairly**: use the same data, parameters, cache conditions, and comparable load; compare both total DB Hits and intermediate inflation points rather than a single timing run.

Example before/after tracking:

| Metric | Before | After | Assessment |
| --- | ---: | ---: | --- |
| Rows at largest multiplication point | 1,000,000 | 4,000 | Reduced intermediate combinations |
| Total DB Hits | 2,500,000 | 15,000 | Less storage-layer work |
| Peak memory (if reported) | 180 MB | 12 MB | Lower memory pressure |
| Business-accurate result rows | 10 | 10 | **Exact content must stay identical**, not just row count |

The figures in this table are **purely hypothetical to illustrate reporting**, not a Neo4j benchmark or an expectation for any specific system.

## 9. Analyzing Plans from the Java Driver and Spring Data Neo4j

In Java applications, plans are accessible through `ResultSummary`. In **Neo4j Java Driver 6.2 and later**, the current API provides `queryPlan()` and `queryProfile()`; in some older versions, the corresponding methods are `plan()` and `profile()`. Use the API matching your **actual dependency version**.

Java Driver 6.2+ example using a read query with `PROFILE`:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.QueryConfig;

public class InspectCypherPlan {
    public static void main(String[] args) {
        try (Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me"))) {

            var outcome = driver.executableQuery("""
                PROFILE
                MATCH (u:DemoUser {id: $id})-[:VIEWED]->(p:DemoProduct)
                WHERE p.price >= $minPrice
                RETURN p.id AS productId, p.price AS price
                ORDER BY p.price DESC
                LIMIT 5
                """)
                .withParameters(Map.of("id", 1, "minPrice", 10000))
                .withConfig(
                    QueryConfig.builder().withDatabase("neo4j").build()
                )
                .execute();

            System.out.println("Result row count: " + outcome.records().size());
            outcome.summary().queryProfile().ifPresentOrElse(
                profile -> System.out.println(
                    profile.arguments().get("string-representation")
                ),
                () -> System.out.println("No PROFILE information available")
            );
        }
    }
}
```

The snippet uses a placeholder password; in real applications, load credentials via configuration/secrets. `PROFILE` executes the query for real, which here is read-only. For `EXPLAIN`, use the `EXPLAIN` prefix and `summary().queryPlan()` instead of `queryProfile()`. For older Driver versions, adapt method calls to the matching API.

In **Spring Data Neo4j**, repositories and `Neo4jClient` are convenient for business logic, yet normal repository calls do not directly display the operator tree. When investigating performance:

- Capture the exact Cypher generated by the application (and representative parameters), avoiding measuring a “guessed” query that differs from runtime Cypher.
- Run `EXPLAIN`/`PROFILE` against the appropriate environment and database, or use the Driver to obtain `ResultSummary`.
- Inspect relationship mappings, hop counts, property selectivity, indexes/constraints, and any occurrence of `CartesianProduct`, `Eager`, or `Sort`.
- Never run `PROFILE` on a write query directly against critical data unless you explicitly accept that write operation.

## 10. Frequent Misconceptions

| Hasty Conclusion | What to Check Instead |
| --- | --- |
| “Any `CartesianProduct` is always wrong.” | Does business logic require all combinations; what are the actual sizes of both branches? |
| “Adding `LIMIT 10` guarantees only 10 rows are processed.” | How many rows did `Sort`/aggregation/expansion process before `LIMIT`? |
| “`Eager` is a bug and must be removed.” | Is there a read/write conflict requiring a barrier to preserve semantics? |
| “`WITH` always materializes the intermediate set.” | Which actual blocking operators are in the plan, and how much data do they hold? |
| “A 1-row result means the query is lightweight.” | Inspect `Rows` upstream of aggregation/`ProduceResults`. |
| “Having an index makes `Sort` vanish automatically.” | Does the index match the predicate and `ORDER BY` direction; what did the planner choose? |
| “`DB Hits` equals row count.” | It measures storage-access work, not cardinality. |
| “`Estimated Rows` is the count of records processed.” | Only `PROFILE` gives actual `Rows`. |
| “Query memory equals the sum of the `Memory (Bytes)` column.” | Check query-wide peak memory; per-operator peaks do not simply sum. |
| “`PROFILE` only simulates the statement.” | `PROFILE` executes for real, including updates in write queries. |
| “`DISTINCT` at the end eliminates prior expansion cost.” | The cost of generating the large set has already occurred; `DISTINCT` may add stateful work. |

## 11. Self-Check

1. A query `MATCH (a:A), (b:B) RETURN count(*)` returns a single number. If `A` has 5,000 nodes and `B` has 2,000 nodes, how many combinations might the plan process? Must each pair be returned to incur that cost?
2. Why can `Eager` appear in a Cypher statement that reads and updates the same group of nodes? When is splitting a transaction into multiple batches **inappropriate**?
3. What is the difference between `Sort` and `Top`? Why does `LIMIT` not necessarily reduce data reads?
4. If `Estimated Rows` is 10 while `Rows` is 800,000 at `Expand(All)`, where in the graph and query should you investigate?
5. Which metrics and conditions must be compared to conclude that a Cypher change improved performance **and** did not alter correctness?

**Passing criteria:** you can open and read a plan with `EXPLAIN`/`PROFILE`; pinpoint where row counts surge; accurately explain the roles of `CartesianProduct`, `Eager`, and `Sort`; propose evidence-based fixes; and verify both correctness and resource consumption after optimizing.

## Official References

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): plan structure, `Estimated Rows`, `Rows`, `DB Hits`, memory, and reading operators.
- [Neo4j Cypher Manual — Operators in detail](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/operators-detail/): `CartesianProduct`, `Eager`, `Sort`, `Top`, aggregation, and traversal.
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/): planner, runtime, tuning, and planner options.
- [Neo4j Cypher Manual — Basic query tuning example](https://neo4j.com/docs/cypher-manual/current/appendix/tutorials/basic-query-tuning/): worked example of changing a query and reading plans.
- [Neo4j Java Driver Manual — Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/): `ResultSummary`, `queryPlan()`/`queryProfile()`, and profiling results in Java.
