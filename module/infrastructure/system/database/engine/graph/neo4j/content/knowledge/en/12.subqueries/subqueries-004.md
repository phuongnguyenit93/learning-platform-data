# Correlated Subqueries and Their Impact on Execution Count

> **Chapter:** Subqueries  
> **DBMS:** Neo4j, property graph, and Cypher language.  
> **Objective:** Understand *correlated subqueries*, the number of rows passed into `CALL`, how subqueries alter the output row count, and how to reduce repeated work when querying relationships, paths, or updating the graph.

## 1. What Is a Correlated Subquery?

In a Neo4j graph database, nodes are connected by relationships. For instance, an `API` service might depend on `Auth` and `Catalog`. We often want to process **each service individually**: list dependencies, count dependencies, or record statuses.

A **correlated subquery** is a subquery that uses one or more **variables from the outer query**. The subquery can yield different results as the outer variable values change.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

Here:

- `s` is produced by the outer `MATCH` and **passed into** the subquery via `CALL (s)`.
- `d` is an **inner** variable of the subquery, representing a dependency of the current `s`.
- The subquery searches for dependencies attached to **that specific input row's node `s`**, not a global dependency set for the entire result table.
- Each row returned via `RETURN` by the subquery is combined with its corresponding outer query row.

This is *per-input-row* semantics; it does not mean a Java application sends an extra Cypher command over the network for each row. The entire query remains **a single statement sent to Neo4j**; the server organizes the work inside its execution plan.

## 2. Sample Data: Service Dependency Graph

Consider five `:CorrDemoService` nodes and four `:DEPENDS_ON` relationships:

```text
     (API) ───────────────> (Auth)
       │                      ^
       │                      │
       └──> (Catalog) ────────┤
                              │
            (Billing) ────────┘

     (Metrics)   [no outgoing DEPENDS_ON]
```

| Service | `id` | Outgoing dependency count |
|---|---|---:|
| API | `api` | 2 (Auth, Catalog) |
| Auth | `auth` | 0 |
| Billing | `billing` | 1 (Auth) |
| Catalog | `catalog` | 1 (Auth) |
| Metrics | `metrics` | 0 |

Create the data in a **dedicated practice database**. Use `MERGE` so repeated runs on a clean sample graph do not unintentionally create duplicate identical nodes/relationships:

```cypher
MERGE (api:CorrDemoService {id: 'api'})
  SET api.name = 'API'
MERGE (auth:CorrDemoService {id: 'auth'})
  SET auth.name = 'Auth'
MERGE (billing:CorrDemoService {id: 'billing'})
  SET billing.name = 'Billing'
MERGE (catalog:CorrDemoService {id: 'catalog'})
  SET catalog.name = 'Catalog'
MERGE (metrics:CorrDemoService {id: 'metrics'})
  SET metrics.name = 'Metrics'
WITH api, auth, billing, catalog
MERGE (api)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:DEPENDS_ON]->(catalog)
MERGE (billing)-[:DEPENDS_ON]->(auth)
MERGE (catalog)-[:DEPENDS_ON]->(auth);
```

The examples below assume the practice graph contains only **these five nodes labeled `CorrDemoService`** and the relationships above. Real datasets with additional relationships will produce different results.

## 3. Foundational Rule: `CALL` Is Evaluated Once per Input Row

Under Neo4j Cypher semantics, a `CALL` subquery runs **once for each incoming row**. If the outer query feeds three rows, there will be three subquery evaluations bound to those three row contexts.

Graph-free example:

```cypher
UNWIND [10, 20, 30] AS number
CALL (number) {
  RETURN number * 2 AS doubled
}
RETURN number, doubled
ORDER BY number;
```

| number | doubled |
|---:|---:|
| 10 | 20 |
| 20 | 40 |
| 30 | 60 |

Data flow diagram:

```text
Outer query                     CALL (number)              Row after CALL

number = 10  ────────────────>  RETURN 20  ────────────>  (10, 20)
number = 20  ────────────────>  RETURN 40  ────────────>  (20, 40)
number = 30  ────────────────>  RETURN 60  ────────────>  (30, 60)
```

What determines **how many contexts are processed** is the number of rows **present immediately before `CALL`**. You cannot deduce it merely from the total nodes in the graph or the row count in the final `RETURN`.

### 3.1. What If There Are No Input Rows?

```cypher
UNWIND [] AS number
CALL (number) {
  RETURN number * 2 AS doubled
}
RETURN number, doubled;
```

No rows enter `CALL`, so the query produces zero result rows. A `CALL` cannot resurrect missing outer rows on its own.

Conversely, if a query **starts with `CALL ()`** without a preceding `MATCH`/`UNWIND` filtering out all rows, Cypher provides an initial context so the query can return a result:

```cypher
CALL () {
  RETURN 42 AS answer
}
RETURN answer;
```

The result is one row: `answer = 42`.

### 3.2. Correlated Variables Come from the Exact Current Row

```cypher
UNWIND [1, 2, 3] AS n
WITH n, 10 AS factor
CALL (n, factor) {
  RETURN n * factor AS scaled
}
RETURN n, scaled
ORDER BY n;
```

The subquery is allowed to use `n` and `factor` because both are explicitly imported via `CALL (n, factor)`. Their values correspond to the current row.

If `factor` is not imported, the subquery cannot see `factor` under the modern scope clause mechanism.

## 4. Uncorrelated Subqueries Can Still Be Invoked Row by Row

A common misconception: **`CALL ()` does not mean "run exactly once for the whole query"**. It only states that the subquery **imports no outer variables**.

```cypher
UNWIND ['A', 'B', 'C'] AS code
CALL () {
  RETURN 'ready' AS state
}
RETURN code, state
ORDER BY code;
```

| code | state |
|---|---|
| A | ready |
| B | ready |
| C | ready |

Even though the body of `CALL ()` does not depend on `code`, the `state` value is still joined to **each row**. Under `CALL` semantics, there are three evaluation contexts.

Likewise, if a subquery reads a graph-wide total:

```cypher
MATCH (s:CorrDemoService)
CALL () {
  MATCH (other:CorrDemoService)
  RETURN count(other) AS totalServices
}
RETURN s.name AS service, totalServices
ORDER BY service;
```

On the sample graph, there are **five rows**, each with `totalServices = 5`. The body of `CALL ()` has nothing to do with `s`, yet it still executes in a per-outer-row position.

**Distinguish two concepts:**

| Concept | Question to answer |
|---|---|
| Is it *correlated*? | Does the subquery use variable values from the outer query? |
| How many input rows? | By the time execution reaches `CALL`, how many rows remain in the outer stream? |

A **correlated** subquery typically needs to use different values per row. An uncorrelated `CALL ()` still carries per-row invocation semantics. The optimizer may reorganize some read steps when valid; do not infer physical scan counts solely from `()`.

## 5. Output Row Count: Returning Subqueries, Unit Subqueries, and `OPTIONAL CALL`

To distinguish "evaluation count" from "result row count", consider **five input rows** corresponding to our five sample services.

Let `kᵢ` be the number of rows a **returning subquery** produces for the `i`-th input row.

- Standard returning `CALL`: rows after `CALL` equal the sum `k₁ + k₂ + ... + kₙ`.
- Returning `OPTIONAL CALL`: if an input row yields no inner results, it still contributes **one row with `null` return values**; total rows equal the sum of `max(1, kᵢ)`.
- **Unit** `CALL` without `RETURN`: keeps the outer row count equal to the input row count, even if it updates many nodes/relationships inside.
- A returning subquery with an ungrouped aggregation such as `RETURN count(d)` usually returns **one row containing 0** when no `d` matches, thereby preserving the outer row count.

### 5.1. A Returning Subquery Can Drop or Multiply Rows

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency
ORDER BY service, dependency;
```

Result:

| service | dependency |
|---|---|
| API | Auth |
| API | Catalog |
| Billing | Auth |
| Catalog | Auth |

Before `CALL` there are **5 rows**; after `CALL` there are **4 rows**. This does not contradict "once per row" semantics at all: API produces **2 rows**, Auth produces **0**, Billing **1**, Catalog **1**, Metrics **0**.

Full breakdown:

| Outer row | Rows returned by `MATCH` inside subquery | Rows after standard `CALL` |
|---|---:|---:|
| API | 2 | 2 |
| Auth | 0 | 0 |
| Billing | 1 | 1 |
| Catalog | 1 | 1 |
| Metrics | 0 | 0 |
| **Total** | **4** | **4** |

Seeing 4 rows in the final `RETURN` and concluding the subquery was evaluated 4 times is wrong: the logical input to `CALL` still had 5 rows.

### 5.2. `OPTIONAL CALL` Retains Unmatched Rows

Available from **Neo4j 5.24**, `OPTIONAL CALL`:

```cypher
MATCH (s:CorrDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency
ORDER BY service, dependency;
```

The result has **6 rows**:

| service | dependency |
|---|---|
| API | Auth |
| API | Catalog |
| Auth | `null` |
| Billing | Auth |
| Catalog | Auth |
| Metrics | `null` |

`OPTIONAL CALL` preserves the outer rows for Auth and Metrics when the subquery returns 0 rows. It **does not force each service down to a single row**: API still has two dependencies and thus produces two rows.

### 5.3. Inner Aggregation Can Preserve One Row per Service

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

| service | dependencyCount |
|---|---:|
| API | 2 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

`RETURN count(d)` is an aggregation **without grouping keys**, so it returns **one row** containing `0` even when `MATCH` finds no dependencies. The result has 5 rows.

Be mindful of the difference if you add a grouping key:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency, count(*) AS matches
}
RETURN s.name AS service, dependency, matches
ORDER BY service, dependency;
```

Because we grouped by `d.name`, cases with no `d` have **no group to return**. Auth and Metrics disappear again; API continues to have two rows.

### 5.4. Unit Subqueries Preserve Row Count Even When Writing to the Graph

Illustrative example — **run only on a practice database**:

```cypher
UNWIND [101, 102, 103] AS eventId
CALL (eventId) {
  MERGE (:CorrDemoEvent {id: eventId})
}
RETURN eventId
ORDER BY eventId;
```

This is a **unit subquery** because there is no `RETURN` inside `CALL`. Three rows enter and three rows exit; `MERGE` runs for each `eventId`.

If the input contains duplicate values, such as `[101, 101, 102]`, the subquery still **receives three rows**. With an appropriate `MERGE`, only two nodes may be created; with `CREATE`, three nodes will be created. **Row count**, **logical processing count**, and **created node count** are three separate quantities.

## 6. Four Ways to Change the Number of Rows Entering `CALL`

Suppose we need to compute `dependencyCount` for services in an input list. Since the goal is to reduce repeated work, arranging clauses **before** the subquery is crucial.

### 6.1. `WHERE` Before `CALL`: Early Filtering

```cypher
MATCH (s:CorrDemoService)
WHERE s.id IN ['api', 'billing']
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Instead of five input nodes, only **API** and **Billing** enter `CALL`.

When filtering frequently by an identifier key, an appropriate index or constraint on `s.id` lets Neo4j locate those two nodes without scanning the entire label.

### 6.2. `WITH DISTINCT` Before `CALL`: Avoiding Duplicates When Permitted

```cypher
UNWIND ['api', 'api', 'billing'] AS serviceId
MATCH (s:CorrDemoService {id: serviceId})
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount;
```

There are **three input rows** even though there are only two distinct service nodes. API appears **twice**, so the result also has two API rows.

If the requirement is **each service strictly once**, change it to:

```cypher
UNWIND ['api', 'api', 'billing'] AS serviceId
MATCH (s:CorrDemoService {id: serviceId})
WITH DISTINCT s
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Now only **two rows** remain before `CALL`. `DISTINCT` should only be used when dropping duplicate rows **does not violate business logic**. For instance, a task that logs one event for **every occurrence in the input data** cannot arbitrarily collapse duplicate rows.

### 6.3. `ORDER BY ... LIMIT` Before `CALL`: Selecting an Input Subset

```cypher
MATCH (s:CorrDemoService)
WITH s
ORDER BY s.name
LIMIT 2
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

Only the first two services alphabetically — **API** and **Auth** — are passed into `CALL`.

If you place `LIMIT 2` **after** `CALL`, the meaning shifts to limiting the **final result rows**, no longer stating that "only two services are selected for processing". Moreover, a pipelined execution engine might stop early once enough final rows are produced; therefore, **you must not deduce an exact physical operation count** merely by counting final rows. When you need to explicitly bound the input, place `LIMIT` **before `CALL`**.

### 6.4. Aggregating Before `CALL`: Turning Multiple Rows into Groups

Suppose you want to perform one check per **dependency count**:

```cypher
MATCH (s:CorrDemoService)
WITH s, COUNT {
  (s)-[:DEPENDS_ON]->(:CorrDemoService)
} AS degree
WITH degree, count(*) AS servicesInGroup
CALL (degree) {
  RETURN CASE
    WHEN degree = 0 THEN 'none'
    WHEN degree = 1 THEN 'single'
    ELSE 'multiple'
  END AS category
}
RETURN degree, servicesInGroup, category
ORDER BY degree;
```

Rows are grouped by `degree` before `CALL`. On the sample graph there are **3 groups**:

| degree | servicesInGroup | category |
|---:|---:|---|
| 0 | 2 | none |
| 1 | 2 | single |
| 2 | 1 | multiple |

In this example, `CASE` could be written directly in the outer query without `CALL`; the subquery simply illustrates shifting the **unit of processing from nodes to groups**.

## 7. `LIMIT` Inside a Subquery Restricts Results per Row

A common graph task: retrieve the **first connected person** or the **first two dependencies of each service**, rather than the first two results across the entire system.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
  ORDER BY dependency
  LIMIT 1
}
RETURN s.name AS service, dependency
ORDER BY service;
```

Result:

| service | dependency |
|---|---|
| API | Auth |
| Billing | Auth |
| Catalog | Auth |

`LIMIT 1` is **inside** `CALL`, so each service returns at most one dependency. Auth and Metrics are still dropped because they have no dependencies; `LIMIT` does not synthesize `null` rows.

If you need to retain all five services, an option compatible with 5.x releases supporting the scope clause is:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
  ORDER BY dependency
  LIMIT 1
}
RETURN s.name AS service, dependency
ORDER BY service;
```

`OPTIONAL MATCH` creates one row with `d = null` when there is no relationship; `CALL` then returns one row per service. From **Neo4j 5.24**, you can use `OPTIONAL CALL` with regular `MATCH` to keep missing rows.

### Comparing `LIMIT` Placement

| Position | What does it limit? |
|---|---|
| Before `CALL`: `WITH s ORDER BY ... LIMIT 2` | Number of input rows entering the subquery. |
| Inside `CALL`: `RETURN d ... LIMIT 2` | Maximum number of inner rows **per outer row**. |
| After `CALL`: `RETURN ... LIMIT 2` | Number of rows returned **for the entire query**. |

With `LIMIT`, pair it with `ORDER BY` in the corresponding scope so the result is deterministic according to clear criteria.

## 8. `EXISTS`, `COUNT`, and `COLLECT` Are Also Correlated, Returning Expressions

The `CALL` keyword is not the only place with correlated semantics in Cypher.

The following *subquery expressions* can reference outer variables **directly**, without needing `CALL (s)`:

```cypher
MATCH (s:CorrDemoService)
RETURN s.name AS service,
       EXISTS {
         MATCH (s)-[:DEPENDS_ON]->(:CorrDemoService)
       } AS hasDependencies,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CorrDemoService)
       } AS dependencyCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

This query requires **Neo4j 5.6+** because of `COLLECT { ... }`.

| service | hasDependencies | dependencyCount | dependencies |
|---|---|---:|---|
| API | `true` | 2 | `["Auth", "Catalog"]` |
| Auth | `false` | 0 | `[]` |
| Billing | `true` | 1 | `["Auth"]` |
| Catalog | `true` | 1 | `["Auth"]` |
| Metrics | `false` | 0 | `[]` |

Note the differences:

| Form | Return value | Outer variables | Effect on outer row count |
|---|---|---|---|
| `CALL (s) { ... RETURN ... }` | 0, 1, or many inner rows | Explicitly imported | Can multiply/drop rows |
| `CALL (s) { ... }` without `RETURN` | Returns no inner columns | Explicitly imported | Preserves outer rows |
| `EXISTS { ... }` | Boolean | Automatically visible in scope | The expression itself does not multiply rows |
| `COUNT { ... }` | Integer | Automatically visible in scope | The expression itself does not multiply rows |
| `COLLECT { ... RETURN ... }` | List | Automatically visible in scope | The expression itself does not multiply rows |

These expressions **are defined per row context `s`**, though that does not mean every evaluation corresponds to a standalone physical subquery execution on the server. Neo4j can optimize read steps or stop early, especially for `EXISTS`. Use `PROFILE` to see the total work on your actual version and data.

### Why Does `COUNT { ... }` Sometimes Return 1 When There Are No Relationships?

`COUNT { ... }` counts **rows of the inner query**, not non-`null` values. Example:

```cypher
MATCH (s:CorrDemoService {id: 'metrics'})
RETURN COUNT {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d
} AS numberOfRows;
```

The result is **1** because `OPTIONAL MATCH` produces one row with `d = null`. To count actual dependencies, use `COUNT { MATCH ... }`, which yields **0**.

Similarly, `COUNT { MATCH ... RETURN count(d) }` can return **1** when the aggregating subquery produces a single row containing `0`. This is the clearest illustration that **row count** differs from **data values inside a row**.

## 9. Neo4j Version Determines How Variables Are Passed

### 9.1. Modern Scope Clause from Neo4j 5.23

From **Neo4j 5.23**, you can declare imported variables right after `CALL`:

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name, degree;
```

Import forms:

| Form | Outer variables accessible inside the subquery |
|---|---|
| `CALL (s) { ... }` | Only `s` |
| `CALL (s, threshold) { ... }` | `s` and `threshold` |
| `CALL (*) { ... }` | All variables currently in the outer scope |
| `CALL () { ... }` | Imports no outer variables |

Using `CALL (s)` instead of `CALL (*)` generally clarifies subquery dependencies. With the scope clause, imported variables remain usable inside the subquery even after a `WITH` that does not re-list them.

### 9.2. Legacy Syntax for Neo4j 4.4–5.22

Servers prior to 5.23 do not understand `CALL (s)`. Use *importing WITH*:

```cypher
MATCH (s:CorrDemoService)
CALL {
  WITH s
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

In legacy syntax, `WITH s` opens the subquery to import variables. Do not attach `WHERE`, `ORDER BY`, `LIMIT`, or aliases directly to the importing `WITH`. If you need to filter immediately after importing, use two `WITH` clauses:

```cypher
MATCH (s:CorrDemoService)
CALL {
  WITH s
  WITH s
  WHERE s.id <> 'metrics'
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

The query above is not a good example for **filtering outer rows**: because `RETURN count(d)` aggregates without grouping keys, non-matching cases can still return a row with count 0. To exclude Metrics cleanly and reduce rows entering the subquery, place `WHERE s.id <> 'metrics'` **before `CALL`** in the outer query.

If you use a regular `WITH` inside a legacy subquery and drop `s` from scope, subsequent clauses can no longer reference `s`. With the new scope clause, imported variables remain in scope throughout the subquery.

### 9.3. Server, Language Version, and Java Driver

| Environment | Practical rule |
|---|---|
| Neo4j 4.4 and 5.0–5.22 | Use `CALL { WITH s ... }`. |
| Neo4j 5.23 and later | Prefer `CALL (s) { ... }`; importing `WITH` is deprecated. |
| Neo4j 5.24 and later | Adds `OPTIONAL CALL` to retain unmatched rows. |
| Neo4j 2025.06 and later | May offer **Cypher 5** or **Cypher 25** selection; distinguish **language** version from **server** version. |

Upgrading the Java Driver or Spring Data Neo4j **does not automatically add subquery syntax to an older Neo4j server**. Always verify the database version your application actually connects to before choosing syntax.

## 10. Correlation, Execution Order, and Data Updates

Neo4j allows `CALL` subqueries to write data via `CREATE`, `MERGE`, `SET`, and `DELETE`. When there are multiple input rows, later executions within the same query can **observe changes made by earlier executions**.

Example in a practice database:

```cypher
UNWIND [1, 2, 3] AS seq
WITH seq
ORDER BY seq
CALL (seq) {
  CREATE (:CorrDemoLog {sequence: seq})
}
RETURN count(*) AS submittedRows;
```

Three rows are fed into `CALL`; the query creates three log nodes and `submittedRows = 3`. `ORDER BY` before `CALL` makes the order of incoming rows explicit if write logic depends on ordering.

**Note:** if multiple inputs update **the same node**, do not rely on the "incidental order" of `MATCH`. Neo4j does not guarantee the order in which outer rows enter a subquery without an explicit `ORDER BY` **before `CALL`**. With parallel processing or concurrent transactions, additional analysis of change visibility and batch independence is needed.

Also distinguish **one statement** from **individual write operations**. From a Java application, a single `session.run(query, params)` call may cause Neo4j to perform multiple writes across `UNWIND` rows, without incurring a separate network round-trip per row.

## 11. `IN TRANSACTIONS`: Invocation Count Differs from Commit Count

For large volumes, `CALL ... IN TRANSACTIONS` processes outer rows in **batches**, committing each inner transaction.

```cypher
UNWIND range(1, 5) AS id
CALL (id) {
  MERGE (:CorrDemoBatchItem {id: id})
} IN TRANSACTIONS OF 2 ROWS
RETURN count(*) AS submittedRows;
```

When executed on Neo4j supporting `CALL (id)` (5.23+), there are:

- **5 input rows** with `id = 1, 2, 3, 4, 5`.
- **5 logical evaluations** of the unit subquery across the rows.
- **3 inner transaction batches**: first batch 2 rows, second batch 2 rows, final batch 1 row.
- `submittedRows = 5` in the aggregated output.

**Do not interpret `OF 2 ROWS` as "run the subquery only twice".** This parameter specifies the number of **input rows per commit batch**.

Only use `CALL { ... } IN TRANSACTIONS` in an **implicit transaction**. In Neo4j Browser, prepend `:auto` if needed; with the Java Driver, use an implicit transaction form (such as `session.run(...)` and consume the results), rather than wrapping in `session.executeWrite(...)`.

Previously committed batches may remain persisted if a later batch fails; design write operations to be safely re-runnable and create appropriate indexes/constraints for `MERGE`. Newer Neo4j versions also support concurrent transaction options; these change assumptions about ordering and cross-batch visibility, so only use them when data and operations are independent.

### Why Must Rows Be Generated **Before** the Subquery?

If you want to update 5,000 nodes in batches of 1,000 rows, first `MATCH`/`UNWIND` or `LOAD CSV` must produce 5,000 **input rows** before passing into `CALL ... IN TRANSACTIONS OF 1000 ROWS`.

If the entire search for 5,000 nodes is placed **inside** a `CALL () { ... }` while the outer query has only one row, `IN TRANSACTIONS` only sees **one input row**, and therefore cannot split those 5,000 nodes into five batches as intended.

## 12. Cost Estimation and Verification with `EXPLAIN` and `PROFILE`

### 12.1. Mental Model for Identifying Repeated Work

Suppose:

- `N`: number of rows entering `CALL`.
- `kᵢ`: number of rows the returning subquery produces for the `i`-th row.
- `cᵢ`: cost of pattern matching, path traversal, or writing data for the `i`-th row.

Semantically, returning `CALL` produces **sum of `kᵢ` rows**; total work generally depends on **sum of `cᵢ`**. The output row count `kᵢ` is only an indicator, **not a direct measure of execution time**.

For example, 100 services each having 20 dependencies can generate around 2,000 rows with `MATCH` inside `CALL`. If you only need a "has dependencies" flag, using `EXISTS` can avoid materializing the full result list. If you only need the count, use `COUNT { ... }` or an appropriate aggregation.

A correlated subquery keyed repeatedly on the same key across many rows can duplicate work. However, do not conclude that each correlation creates a separate *network query*: the server still executes the single Cypher statement sent by the client.

### 12.2. Using `EXPLAIN` to Inspect the Plan

```cypher
EXPLAIN
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

`EXPLAIN` shows which operators Neo4j plans to run, **without executing the query**.

You may see operators related to applying the subquery per row (*Apply* or another variant), node scans/lookups, relationship expansion, and column projection. Exact operator names depend on version, runtime, and query structure.

### 12.3. Using `PROFILE` to Measure on Real Data

```cypher
PROFILE
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS degree
}
RETURN s.name AS service, degree
ORDER BY service;
```

`PROFILE` **executes** the query and displays metrics at each operator, such as:

- **Rows:** the actual number of rows produced by each operator (typically cumulative across the execution).
- **DB Hits:** storage access operations performed by the operator.
- **Estimated Rows:** cardinality estimates to compare against actual counts.
- Timing/memory or other metrics if supported by the runtime and tooling.

Inspect the number of rows **entering** the subquery-apply operator, the number of rows **exiting**, and costly relationship expansions. Rely on the actual plan to detect excessive duplicate inputs, wide inner pattern traversals, or large list sorts.

Do not assert that "operator X executed exactly N times" purely from one `Rows` figure: the planner can merge operators, push down predicates, pipeline execution, or short-circuit early where permitted. The goal is to verify whether **cardinality and cost** match expectations.

### 12.4. How Do Indexes Help in Correlated Subqueries?

If each row inside the subquery must look up a service by another key, an index/constraint on that property can reduce the cost of each lookup.

Example creating a uniqueness constraint **in a practice database**:

```cypher
CREATE CONSTRAINT corr_demo_service_id IF NOT EXISTS
FOR (s:CorrDemoService)
REQUIRE s.id IS UNIQUE;
```

With this, queries looking up services by `id` can leverage the constraint-backed index. When you already hold **node `s`** from the outer query and only expand `(s)-[:DEPENDS_ON]->(...)`, there is no need to look up `s` again by name/ID inside every subquery.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `CALL` returns 4 rows despite 5 services | Returning subquery returns 0 rows for Auth and Metrics, and 2 rows for API. | Distinguish input rows from output rows; use aggregation, `OPTIONAL MATCH`, or `OPTIONAL CALL` to retain unmatched services. |
| `CALL ()` still repeats results for each service | Importing no variables only means **uncorrelated**, not running once globally. | If you need a global total, compute it once first and join as needed, or rewrite the query appropriately. |
| Subquery reads/writes the same service multiple times | Duplicate outer rows from `UNWIND` or multiple `MATCH`es. | Check row count before `CALL`; use `WITH DISTINCT` when business logic permits. |
| Outermost `LIMIT 1` returns only one row total | `LIMIT` is scoped to the outer query. | Move `LIMIT` inside the subquery for one result **per row**; place it before `CALL` to process only one input row. |
| Outer `count(*)` "hides" distinct row counts | Outer aggregation collapses multiple rows into one summary row. | Check grouping keys and what is being counted; measure intermediate cardinality. |
| `COUNT { OPTIONAL MATCH ... }` returns 1 for a service with no relationships | `OPTIONAL MATCH` emits one row containing `null`. | Use `COUNT { MATCH ... }` when counting actual matches. |
| Error saying variable is undefined inside `CALL` | Outer variable was not imported. | Neo4j 5.23+: `CALL (s)`; older versions: `CALL { WITH s ... }`. |
| Using `CALL (s)` causes a server syntax error | Neo4j server is older than 5.23. | Use importing `WITH` or upgrade the server. |
| Data updates rely on arbitrary order | No `ORDER BY` before `CALL`. | Define an explicit order when ordered processing is truly needed; account for conflicts in concurrent execution. |
| `IN TRANSACTIONS OF 1000 ROWS` still creates one batch | Subquery receives only one outer row; the large `MATCH` or `UNWIND` is inside. | Generate input rows via `MATCH`/`UNWIND`/`LOAD CSV` **before `CALL`**. |
| Seeing 5 result rows and concluding 5 DB hits | Row count does not reflect full traversals or physical optimizations. | Use `PROFILE`; inspect `Rows`, `DB Hits`, and the actual plan. |

## 14. Self-Check Exercises

The questions below use the graph from section 2. Before running them, try predicting **how many rows enter `CALL`** and the **final row count**.

**Exercise 1.** How many input rows and result rows are there?

```cypher
UNWIND ['api', 'api', 'billing', 'metrics'] AS id
MATCH (s:CorrDemoService {id: id})
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service, dependency;
```

**Answer:** 4 outer rows enter `CALL`; the final row count is **5**:

- API appears twice, each yielding 2 dependencies: `2 × 2 = 4` rows.
- Billing yields 1 row.
- Metrics yields 0 rows.

**Exercise 2.** Replacing `CALL` with `OPTIONAL CALL` on 5.24+, what is the final row count?

**Answer:** **6** rows: 4 from the two occurrences of API, 1 from Billing, and 1 from Metrics with `dependency = null`.

**Exercise 3.** If you place `WITH DISTINCT s` before `CALL` in Exercise 1, how many rows enter and exit?

**Answer:** **3 rows** enter (API, Billing, Metrics) and **3 rows** exit (2 from API, 1 from Billing).

**Exercise 4.** Get one final result per service, including services with 0 dependencies, without using `OPTIONAL CALL`.

```cypher
MATCH (s:CorrDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:CorrDemoService)
  RETURN count(d) AS dependencyCount
}
RETURN s.name AS service, dependencyCount
ORDER BY service;
```

**Answer:** 5 rows, with counts `API = 2`, `Auth = 0`, `Billing = 1`, `Catalog = 1`, `Metrics = 0`.

**Exercise 5.** Given 2,501 outer rows processed with `IN TRANSACTIONS OF 1000 ROWS` in default sequential mode, what is the maximum number of batches when no errors occur?

**Answer:** **3 batches** (1,000, 1,000, 501). The number of rows requiring logical processing remains **2,501**.

## 15. Takeaways for Writing Production Queries

1. **Determine the input rows right before `CALL`.** Correlated variables come from the current row; total nodes in the graph do not always equal the number of logical evaluations.
2. **Uncorrelated does not mean run-once.** `CALL ()` imports no variables yet still follows per-outer-row application semantics.
3. **Distinguish row count from values inside a row.** Returning subqueries can yield 0 or many rows; `OPTIONAL CALL` preserves empty rows; ungrouped aggregation can return one row containing `0`.
4. **Reduce rows before the subquery when business rules allow.** `WHERE`, `DISTINCT`, `LIMIT`, and aggregation placed appropriately reduce the contexts to process.
5. **Place `ORDER BY`/`LIMIT` in the right scope.** Inside limits per row; before `CALL` limits input; after `CALL` limits total output.
6. **Use `EXISTS`/`COUNT`/`COLLECT` when you only need an expression.** They have their own scoping rules and do not multiply rows like a returning `CALL`.
7. **Measure with actual plans.** `PROFILE` shows row counts and server cost, whereas "execution count" inferred from syntax only describes semantics.

## References

- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — per-row semantics, variable importing, returning/unit subquery output, and memory management.
- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/) — correlated Boolean subqueries.
- [Neo4j Cypher Manual — COUNT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/count/) — counting subquery rows per outer variable.
- [Neo4j Cypher Manual — COLLECT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/) — collecting values per outer row into a list.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/) — batching input rows and implicit transaction rules.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — reading `EXPLAIN` and `PROFILE` to verify cardinality and execution cost.
