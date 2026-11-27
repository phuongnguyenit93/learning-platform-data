# UNION and UNION ALL for Combining Result Sets

> **Chapter:** Subqueries  
> **Scope:** Neo4j property graph and Cypher, combining multiple query branches with `UNION` and `UNION ALL`; specifically processing combined results inside a `CALL` subquery.  
> **Objective:** Choose the right duplicate-keeping/removal rule, design consistent return columns, combine results from multiple relationship types, aggregate or paginate after combining, and write syntax matching the running Neo4j version.

## 1. Why Combine Multiple Result Sets?

In Neo4j, the same service can connect to another service through multiple **relationship types**. For example:

- `(API)-[:DEPENDS_ON]->(Auth)`: API depends on Auth.
- `(API)-[:CALLS]->(Auth)`: API calls Auth at runtime.
- `(API)-[:CALLS]->(Billing)`: API also calls Billing.

If we want to ask **"which services is the API service linked to across both relationship types?"**, we can run two different `MATCH` branches and combine the returned rows:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

The `UNION` keyword merges the results of **query branches** into a single result set. Common uses:

- Combining results from two different relationship patterns.
- Merging nodes from different groups/labels into a unified return shape.
- Gathering event lists from multiple sources.
- Returning special cases using multiple branches with different read logic.
- Using `CALL { ... UNION ... }` to **count, group, sort, or paginate after combining**.

Each branch can have its own `MATCH`, `WHERE`, `WITH`, and `RETURN`. However, the **result schema** must be compatible: `UNION` branches must have **the same number of columns and the same column names**.

## 2. Foundational Rule: `UNION` Deduplicates, `UNION ALL` Keeps Duplicates

Let's start with an example independent of graph data.

### 2.1. `UNION ALL` Preserves All Rows

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION ALL

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

Result rows (display order is not guaranteed without `ORDER BY`):

| destination |
|---|
| Auth |
| Catalog |
| Auth |
| Billing |

There are **4 rows**: two from the first branch and two from the second. `Auth` appears **twice** because `UNION ALL` keeps duplicate rows.

This can be understood via *multiset* (bag of potentially repeating rows) semantics:

```text
Branch A: [Auth, Catalog]
Branch B: [Auth, Billing]
                 │
                 ▼
             UNION ALL
                 │
                 ▼
[Auth, Catalog, Auth, Billing]    (4 rows)
```

### 2.2. `UNION` Removes Duplicate Rows

Same data, replacing `UNION ALL` with `UNION`:

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

The result has **3 rows**:

| destination |
|---|
| Auth |
| Catalog |
| Billing |

`UNION` applies **DISTINCT** semantics to the combined result by default. It does not require a separate `DISTINCT` keyword to deduplicate.

### 2.3. Quick Selection Table

| Scenario | Use | Reason |
|---|---|---|
| Only want a **unique** list of target services | `UNION` | Identical result rows appearing across multiple branches are kept only once. |
| Need to keep **every occurrence** to count events, relationships, or sources | `UNION ALL` | Repetition carries business meaning. |
| Want to know **which relationship types** led to the same target | `UNION ALL` plus a source column | Preserves per-branch information for analysis. |
| Branches definitely cannot produce duplicate rows | Usually `UNION ALL` | Avoids unnecessary deduplication work; still benchmark performance. |
| Need unique results after merging multiple branches | `UNION` or `RETURN DISTINCT` outside `CALL` when appropriate | Keeps only unique rows across the exact projected columns. |

**Remember:** `UNION` deduplicates based on **the entire returned result row**, not implicitly by node name, `id`, or a key assumed by the application.

## 3. Sample Graph: Dependencies and Calls Between Services

This lesson uses five nodes with label `UnionDemoService`, and two relationship types `DEPENDS_ON` and `CALLS`.

```text
                   DEPENDS_ON
          ┌──────────────────────> (Auth)
          │                         ^  ^
          │                         │  │
        (API) ──DEPENDS_ON──> (Catalog)  │
          │                       │      │
          │                       └──────┤ DEPENDS_ON
          │                              │
          └──CALLS──────> (Billing) ──────┘
          │
          └──CALLS────────────────> (Auth)

        (Catalog) ──CALLS─────────> (Auth)
        (Metrics) has no outgoing edges in sample data
```

Exact edge table:

| Source | Relationship | Target |
|---|---|---|
| API | `DEPENDS_ON` | Auth |
| API | `DEPENDS_ON` | Catalog |
| Billing | `DEPENDS_ON` | Auth |
| Catalog | `DEPENDS_ON` | Auth |
| API | `CALLS` | Auth |
| API | `CALLS` | Billing |
| Catalog | `CALLS` | Auth |

Create the data in a **dedicated practice database**:

```cypher
MERGE (api:UnionDemoService {id: 'api'})
  SET api.name = 'API'
MERGE (auth:UnionDemoService {id: 'auth'})
  SET auth.name = 'Auth'
MERGE (catalog:UnionDemoService {id: 'catalog'})
  SET catalog.name = 'Catalog'
MERGE (billing:UnionDemoService {id: 'billing'})
  SET billing.name = 'Billing'
MERGE (metrics:UnionDemoService {id: 'metrics'})
  SET metrics.name = 'Metrics'
WITH api, auth, catalog, billing
MERGE (api)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:DEPENDS_ON]->(catalog)
MERGE (billing)-[:DEPENDS_ON]->(auth)
MERGE (catalog)-[:DEPENDS_ON]->(auth)
MERGE (api)-[:CALLS]->(auth)
MERGE (api)-[:CALLS]->(billing)
MERGE (catalog)-[:CALLS]->(auth);
```

`MERGE` lets you rerun the example on a clean sample graph without unintentionally creating duplicate edge types between the same node pairs. The results below assume only **these five nodes and seven edges** with the example's labels/types. If the database contains additional edges of the same type, actual results may differ.

## 4. Combining Two Relationship Patterns on the Same Graph

### 4.1. Using `UNION ALL` to Keep All Four Occurrences

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

Returned values:

| Branch | destination |
|---|---|
| `DEPENDS_ON` | Auth |
| `DEPENDS_ON` | Catalog |
| `CALLS` | Auth |
| `CALLS` | Billing |

There are **4 rows**, with `Auth` appearing twice. The table adds a "Branch" column to explain the origin, whereas the actual query returns only **one column `destination`**.

### 4.2. Using `UNION` to Get Unique Destinations

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination;
```

The result has **3 rows**: `Auth`, `Billing`, and `Catalog`. Because both branches return the string `"Auth"` in the same `destination` column, `UNION` keeps a single row.

### 4.3. Adding a Source Column Changes the Deduplication Criteria

If you need to know which relationship type matched a destination, add a `relationType` column in **both branches**:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
RETURN d.name AS destination, 'DEPENDS_ON' AS relationType

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
RETURN d.name AS destination, 'CALLS' AS relationType;
```

The result has **4 rows**, even when using `UNION`:

| destination | relationType |
|---|---|
| Auth | DEPENDS_ON |
| Catalog | DEPENDS_ON |
| Auth | CALLS |
| Billing | CALLS |

The two rows `(Auth, DEPENDS_ON)` and `(Auth, CALLS)` **differ** in the `relationType` column, so they are not deduplicated.

This is especially important when using `UNION` to merge events from multiple sources: if you include `source`, `eventId`, or `createdAt` in `RETURN`, two rows sharing the same business key become **two distinct rows**. When you need uniqueness by **a specific set of keys**, project only those keys before deduplicating or aggregating after `CALL`.

## 5. Column Rules and Common Syntax Errors

### 5.1. Branches Must Return the Same **Column Count and Names**

This is an **invalid** query:

```cypher
// INVALID: column names do not match.
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS dependency

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS callee;
```

The first branch returns column `dependency`, while the second returns column `callee`. To fix it, unify the alias:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Another **invalid** query returns different numbers of columns:

```cypher
// INVALID: first branch has two columns, second branch has only one column.
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'dependency' AS origin

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

Fix: both return two columns, `destination` and `origin`.

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'dependency' AS origin

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination, 'runtime-call' AS origin;
```

**Practical rule:** treat each branch's `RETURN` clause as a "data contract": identical column list and aliases, and preferably **compatible data types** for each column so the application can handle them cleanly.

### 5.2. Variable Names Inside Branches Are Scoped Independently

Two branches can use different variable names as long as the final aliases match:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(dependency)
RETURN dependency.name AS destination

UNION ALL

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(callee)
RETURN callee.name AS destination;
```

`dependency` and `callee` are internal variables of their respective branches. The union interface only cares about the output `destination` column.

### 5.3. `UNION` Removes Identical Rows, It Does Not Clean Dirty Data

Two different nodes can still share the same `name` property. If you only return `name`, `UNION` treats identical name values as duplicates in the result set. If you want to distinguish **entities**, return the node or an appropriate identifier key:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.id AS serviceId, d.name AS destination

UNION

MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.id AS serviceId, d.name AS destination;
```

Here deduplication is based on **the column pair `(serviceId, destination)`**. When an application needs durable identity, maintain a business key `id` with an appropriate constraint rather than relying solely on display names.

### 5.4. A Row Containing `null` Is Still a Row

Do not confuse "no data" with "no row".

```cypher
UNWIND [null] AS destination
RETURN destination

UNION

UNWIND [null] AS destination
RETURN destination;
```

Both branches return one row with `destination = null`; `UNION` keeps **one row**. With `UNION ALL`, there will be **two `null` rows**.

However, if a branch's `MATCH` matches nothing and **has no `OPTIONAL MATCH`**, that branch returns **0 rows**. `UNION` does not synthesize `null` for an empty branch.

## 6. `UNION` at Outer Query Scope vs. Inside `CALL`

Since this lesson belongs to the **Subqueries** chapter, you should understand both forms.

### 6.1. `UNION` Directly at Query Level

```cypher
MATCH (s:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination

UNION ALL

MATCH (s:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

This is a **combined query**: results from multiple branches are merged directly. Useful for APIs that only return raw rows.

### 6.2. Wrapping `UNION` Inside `CALL` to Process **After Merging**

From **Neo4j 5.23**, use `CALL ()` when the subquery imports no outer variables:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination;
```

The result is explicitly sorted:

| destination |
|---|
| Auth |
| Auth |
| Billing |
| Catalog |

This technique matters because `UNION` **does not guarantee result row ordering**. If you need to sort or paginate **the entire merged set**, place `ORDER BY`, `SKIP`, and `LIMIT` **outside the `CALL` block**.

### 6.3. Aggregating After `UNION ALL` to Preserve Occurrence Counts

Example: "How many times is each destination service referenced across **both edge types** over the whole graph?"

```cypher
CALL () {
  MATCH (s:UnionDemoService)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  MATCH (s:UnionDemoService)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS occurrences
ORDER BY occurrences DESC, destination;
```

| destination | occurrences |
|---|---:|
| Auth | 5 |
| Billing | 1 |
| Catalog | 1 |

Origin of `Auth = 5`:

- `DEPENDS_ON` from API, Billing, Catalog to Auth: **3 rows**.
- `CALLS` from API, Catalog to Auth: **2 rows**.
- `UNION ALL` keeps all five rows; `count(*)` outside `CALL` aggregates by `destination`.

If `UNION ALL` were replaced with `UNION`, only **one Auth row** would remain after merging; then the outer `count(*)` would be 1, **no longer representing occurrence counts**.

### 6.4. Paginating the Full Merged Result

Example returning the first two rows of the merged list after sorting:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination
SKIP 0
LIMIT 2;
```

The result is two rows `Auth`, `Auth` because `UNION ALL` was used. If the application wants **two distinct services**, switch to `UNION` or deduplicate before paginating.

When using cursor/pagination on production data, include a deterministic tie-breaker sort key rather than relying solely on non-unique names.

## 7. `ORDER BY` and `LIMIT` per Branch vs. Global Limits

Suppose we want to find **the first destination alphabetically** from each of API's relationship types:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination
  ORDER BY destination
  LIMIT 1

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
  ORDER BY destination
  LIMIT 1
}
RETURN destination
ORDER BY destination;
```

The result has **2 Auth rows**:

- The `DEPENDS_ON` branch evaluates `Auth, Catalog` and picks `Auth`.
- The `CALLS` branch evaluates `Auth, Billing` and picks `Auth`.

The two `LIMIT 1` clauses apply **separately to each branch**, and then `UNION ALL` combines the two results. This is **top one per source**, not top one across all sources.

Conversely:

```cypher
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination
LIMIT 1;
```

This example returns exactly **1 Auth row** for the entire union.

| `LIMIT` placement | Meaning |
|---|---|
| Inside each branch before `UNION ALL` | Limits **each source/branch**. |
| Outside `CALL` after merging | Limits **the entire result set**. |
| After `WITH` before `CALL` when multiple input rows exist | Limits **how many outer rows enter the subquery**. |

With `LIMIT`, pair `ORDER BY` in the same scope so the selected items are well-defined.

## 8. `UNION` Inside a **Correlated** Subquery

When you need to combine relationships **for each service**, use `CALL` receiving node `s` from the outer query. From **Neo4j 5.23**, the recommended syntax is `CALL (s) { ... }`:

```cypher
MATCH (s:UnionDemoService)
CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

The result has **7 rows**:

| sourceService | destination |
|---|---|
| API | Auth |
| API | Auth |
| API | Billing |
| API | Catalog |
| Billing | Auth |
| Catalog | Auth |
| Catalog | Auth |

Explanation:

- API has 2 `DEPENDS_ON` edges and 2 `CALLS` edges: **4 rows**.
- Billing has 1 `DEPENDS_ON` edge: **1 row**.
- Catalog has 1 `DEPENDS_ON` edge and 1 `CALLS` edge: **2 rows**.
- Auth and Metrics have no outgoing edges: **0 rows**, so they drop out of the returning `CALL` output.

`CALL (s)` evaluates **for each row `s`**. Both `UNION ALL` branches inside share the current row's node `s`, with no need for `WITH s` when using the scope clause.

### 8.1. With `UNION`, Each Service Is Deduplicated Individually

Replace `UNION ALL` with `UNION` in the block above:

- API: `Auth, Billing, Catalog` → **3 rows**.
- Billing: `Auth` → **1 row**.
- Catalog: `Auth` → **1 row**.
- Auth, Metrics: **0 rows**.

Total **5 rows**. Deduplication occurs **within each subquery evaluation for each `s`**. Results from two different source nodes remain two distinct rows in the outer query (for example, Billing → Auth and Catalog → Auth).

### 8.2. Retaining Source Nodes with No Relationships

From **Neo4j 5.24**, `OPTIONAL CALL` preserves row `s` when the inner block returns no results:

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

The result has **7 rows**: 5 unique relationship rows from API/Billing/Catalog, plus Auth and Metrics with `destination = null`.

If you want **one row per service** with its unique destination count, aggregate after `OPTIONAL CALL`:

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.id AS destinationId

  UNION

  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.id AS destinationId
}
RETURN s.name AS service,
       count(destinationId) AS uniqueDestinationCount
ORDER BY service;
```

| service | uniqueDestinationCount |
|---|---:|
| API | 3 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

Make sure to use `count(destinationId)`, because `count(*)` would also count the `null`-padded row added by `OPTIONAL CALL`. Using `count(*)` would miscount Auth and Metrics as 1.

## 9. Neo4j and Cypher Version Support

Do not assume every syntax in this lesson runs on every version. Key milestones:

| Environment | Recommended syntax or new feature |
|---|---|
| Neo4j 4.4 | `UNION`, `UNION ALL`, and `CALL { ... }` are supported; import outer variables into each branch with *importing* `WITH`. |
| Neo4j 5.0–5.18 | `UNION` and `UNION ALL` continue to work; `UNION DISTINCT` keyword is not yet available. |
| Neo4j 5.19 and later | Adds `UNION DISTINCT`, semantically equivalent to `UNION`. |
| Neo4j 5.23 and later | Adds `CALL (s) { ... }`, `CALL () { ... }` replacing legacy importing `WITH`; legacy form is *deprecated*. |
| Neo4j 5.24 and later | Adds `OPTIONAL CALL` to retain outer rows without inner results. |
| Neo4j 2025.06 and later, **Cypher 25** | Supports **query grouping with curly braces** when combining `UNION` and `UNION ALL` at different nesting levels. |

From Neo4j **2025.06**, a server can support choosing between language versions **`CYPHER 5`** and **`CYPHER 25`**. This is a *language* selection, distinct from the Neo4j server release. You cannot run syntax specific to 5.23/5.24/Cypher 25 on an overly old server merely by prepending `CYPHER 25`.

### 9.1. `UNION DISTINCT` Is Equivalent to `UNION`

From **Neo4j 5.19**:

```cypher
UNWIND ['Auth', 'Catalog'] AS destination
RETURN destination

UNION DISTINCT

UNWIND ['Auth', 'Billing'] AS destination
RETURN destination;
```

The result is still three rows: `Auth, Billing, Catalog`. `UNION DISTINCT` explicitly states deduplication, aligning with the GQL standard direction.

### 9.2. Importing Variables in **Each Branch** on Legacy Neo4j

If running Neo4j **4.4–5.22**, the correlated subquery example in section 8 can be rewritten as:

```cypher
MATCH (s:UnionDemoService)
CALL {
  WITH s
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION ALL

  WITH s
  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN s.name AS sourceService, destination
ORDER BY sourceService, destination;
```

**Crucial point:** with legacy importing `WITH`, every branch that uses outer variable `s` **needs its own `WITH s`**. Importing only in the first branch and referencing `s` in the second branch causes a variable scope error.

With the scope clause from 5.23, a single `CALL (s)` declaration applies to the **entire** subquery block across all `UNION` branches.

### 9.3. Grouping `UNION` and `UNION ALL` in Cypher 25

On **Neo4j 2025.06+ using Cypher 25**, you can use curly braces to group results according to the desired precedence rules.

Example: merge two relationship types and **deduplicate within the group**, then append a test `Auth` row via `UNION ALL`:

```cypher
CYPHER 25
{
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination

  UNION

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}

UNION ALL

UNWIND ['Auth'] AS destination
RETURN destination;
```

The block inside `{ ... }` returns **Auth, Billing, Catalog** (each destination once). The final branch appends an `Auth` row; the result has **4 rows**, with Auth appearing twice.

The curly braces here **group combined queries in Cypher 25**, not a `CALL` subquery. This is a version-gated feature: **do not use this exact snippet in Cypher 5 or older Neo4j 5.x releases**. For applications needing broad compatibility, using a `CALL` subquery and separating processing steps clearly is often easier to read.

## 10. When Should You Use `UNION` Instead of a Single `MATCH` Pattern?

Sometimes branches differ only in relationship type, such as fetching targets of `DEPENDS_ON` or `CALLS`. In that case, Cypher also supports **multi-type relationship patterns**; depending on version and requirements, you can write a single `MATCH` instead:

```cypher
MATCH (:UnionDemoService {id: 'api'})-[r:DEPENDS_ON|CALLS]->(d:UnionDemoService)
RETURN DISTINCT d.name AS destination
ORDER BY destination;
```

Result: `Auth, Billing, Catalog`. This is concise when **both relationship types share the same direction, node pattern, and filter conditions**.

Conversely, `UNION` is useful when:

- One branch traverses outgoing relationships, while another traverses incoming relationships.
- Each branch has very different `WHERE` conditions or path lengths.
- Each source needs its own `ORDER BY`/`LIMIT`.
- Branches query different node labels yet normalize into the same output columns.
- You need to distinguish sources for group aggregation.

Example combining **two opposite directions** of `DEPENDS_ON` at Auth:

```cypher
MATCH (src:UnionDemoService)-[:DEPENDS_ON]->
      (:UnionDemoService {id: 'auth'})
RETURN src.name AS neighbor, 'incoming' AS direction

UNION ALL

MATCH (:UnionDemoService {id: 'auth'})-[:DEPENDS_ON]->
      (dst:UnionDemoService)
RETURN dst.name AS neighbor, 'outgoing' AS direction;
```

The result has **3 incoming rows** from API, Billing, and Catalog. Auth has no outgoing `DEPENDS_ON`, so the `outgoing` branch returns 0 rows. The two branches can be designed independently while normalizing to the column pair `neighbor` and `direction`.

### Is a Single `MATCH` with `OR` Always Equivalent to `UNION`?

Not necessarily. `WHERE conditionA OR conditionB` filters **rows already produced by `MATCH`**, whereas `UNION` merges results from **two query streams**, each able to generate its own row count. If the branches match different path patterns or return multiple rows for the same node, the row counts will differ. Check both **schema and cardinality** before substituting.

## 11. Performance: Deduplication Cost and Generated Row Count

Compared to `UNION ALL`, `UNION` performs extra work to **detect and eliminate identical rows**. When branches return large volumes of data, this step can consume CPU and memory.

However, do not jump to the conclusion that `UNION ALL` **is always faster end-to-end**: keeping more rows can make downstream `ORDER BY`, `collect()`, `count()`, Java object mapping, and network transfer more expensive. The right choice must be guided first by **business semantics**.

### 11.1. Inspecting with `EXPLAIN`

```cypher
EXPLAIN
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination
ORDER BY destination;
```

`EXPLAIN` shows the planned operators **without executing the query**. Depending on version/runtime, you may see operators for combining branches, deduplication, relationship expansion, and sorting. Avoid tying your understanding to a fixed operator name, as plan structure can evolve.

### 11.2. Measuring with `PROFILE`

```cypher
PROFILE
CALL () {
  MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
  RETURN d.name AS destination

  UNION ALL

  MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS occurrences
ORDER BY occurrences DESC, destination;
```

Inspect metrics such as **Rows**, **DB Hits**, **Estimated Rows**, and time/memory if displayed. You can compare `UNION` against `UNION ALL` on **representative data** to identify which stage consumes resources.

### 11.3. Filter Early per Branch and Keep Projections Lean

1. Use `WHERE` inside each appropriate branch to avoid generating unnecessary rows.
2. Return only the columns needed for business logic; extra columns complicate duplicate comparison and can make two rows that share the same primary key appear distinct.
3. If you need top N per source, apply `ORDER BY ... LIMIT` inside the branch. If you need top N overall, apply it outside `CALL`.
4. If looking up nodes repeatedly by `id`, consider an index/constraint. The `UNION` keyword cannot offset a full label scan inside every branch.
5. When a list is already guaranteed unique by key, `UNION ALL` avoids redundant deduplication; do not blindly add `DISTINCT` without a requirement.

In a dedicated demo database, you can create a uniqueness constraint on `id`:

```cypher
CREATE CONSTRAINT union_demo_service_id IF NOT EXISTS
FOR (s:UnionDemoService)
REQUIRE s.id IS UNIQUE;
```

A uniqueness constraint prevents duplicate non-`null` `id` values across nodes and provides an index for `id` lookups.

## 12. Using `UNION ALL` Results with Java Driver and Spring Data Neo4j

`UNION` branches are processed **on the Neo4j server**. The Java application sends **a single Cypher statement** and receives results with a normalized schema.

Example using Java Driver 5.x, with a configured `Driver driver`, reading rows with two columns `destination` and `relationType`:

```java
import org.neo4j.driver.Session;
import java.util.List;
import java.util.Map;

String cypher = """
    CALL () {
      MATCH (:UnionDemoService {id: $sourceId})-[:DEPENDS_ON]->(d:UnionDemoService)
      RETURN d.name AS destination, 'DEPENDS_ON' AS relationType

      UNION ALL

      MATCH (:UnionDemoService {id: $sourceId})-[:CALLS]->(d:UnionDemoService)
      RETURN d.name AS destination, 'CALLS' AS relationType
    }
    RETURN destination, relationType
    ORDER BY relationType, destination
    """;

try (Session session = driver.session()) {
    List<String> rows = session.executeRead(tx ->
        tx.run(cypher, Map.of("sourceId", "api"))
          .list(record ->
              record.get("relationType").asString()
              + " -> "
              + record.get("destination").asString())
    );
    rows.forEach(System.out::println);
}
```

Output in the declared order:

```text
CALLS -> Auth
CALLS -> Billing
DEPENDS_ON -> Auth
DEPENDS_ON -> Catalog
```

Key points:

- Parameter `$sourceId` is shared across both branches. Avoid concatenating user data directly into Cypher strings.
- Because both branches' `RETURN` clauses expose the **same columns**, Java can map them to a single return type.
- In Spring Data Neo4j, a custom `@Query` can also return a projection/DTO with the same two columns `destination` and `relationType`; exact mapping behavior depends on library version and repository structure.
- `CALL ()` was introduced in Neo4j 5.23. On older servers, **change it to `CALL { ... }`** when importing no variables, keeping the `UNION ALL` branches unchanged.
- Upgrading the Java Driver or Spring Data Neo4j does not automatically add new syntax to the **Neo4j server**.

## 13. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `UNION` reports mismatched return columns | Branches use different aliases or different column counts. | Standardize the `RETURN ... AS ...` column list across all branches. |
| Expected `UNION` to keep one Auth, yet two Auth rows remain | An extra column like `relationType`/`source` differs, making the **full rows** non-identical. | Project only the keys to deduplicate on, or use `RETURN DISTINCT` on the desired columns after merging. |
| Lost occurrence counts with `count(*)` | Used `UNION` before counting, eliminating duplicate rows. | Use `UNION ALL` when the goal is to count every occurrence. |
| Too many duplicate rows in API output | Used `UNION ALL` when only unique targets were desired. | Switch to `UNION` or deduplicate by an appropriate key. |
| Result order flips between runs | `UNION` does not guarantee ordering. | Sort **after merging** via `CALL` with an outer `ORDER BY`. |
| `LIMIT 1` returns two rows instead of one | `LIMIT 1` was placed separately in **both branches**. | For one global row, place the limit outside `CALL`. |
| `Variable s not defined` in the second branch of legacy `CALL { ... UNION ... }` | Second branch is missing `WITH s` to import. | Use importing `WITH s` in **each branch**; on 5.23+ use `CALL (s)`. |
| Query returns 0 rows for a service with no edges | Returning `CALL` had no inner rows to join. | Use `OPTIONAL CALL` (5.24+) or an aggregating/alternative query when rows must be preserved. |
| `count(*)` counts 1 for unlinked nodes after `OPTIONAL CALL` | `OPTIONAL CALL` preserves the row with a `null` inner column. | Use `count(destinationId)` instead of `count(*)`. |
| `UNION DISTINCT` throws an error | Neo4j is older than 5.19. | Use traditional `UNION`. |
| `{ ... } UNION ALL ...` grouping is rejected | Combined query grouping syntax requires **Cypher 25** on a supporting server. | Use compatible syntax or switch to the right version; do not use on legacy versions. |
| Query is slow despite `UNION ALL` | `MATCH` branches scan broadly or post-processing sorts too many rows. | Filter/index appropriately, narrow projections, and measure with `PROFILE`. |

## 14. Practice Exercises

Use the graph in section 3. Try predicting the **row count** before running each query.

### Exercise 1. Merge API's Destinations and Keep Occurrence Counts

Write a query returning a single `destination` column from both `DEPENDS_ON` and `CALLS`, **preserving duplicates**.

**Answer:**

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination
UNION ALL
MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination;
```

There are **4 rows**: Auth twice, Billing once, Catalog once.

### Exercise 2. Return a Unique List of Destinations

Modify Exercise 1 so there is only one row per destination service name.

**Answer:** replace `UNION ALL` with `UNION`. There are **3 rows**: Auth, Billing, Catalog.

### Exercise 3. Explain Why `UNION` Still Produces Four Rows

```cypher
MATCH (:UnionDemoService {id: 'api'})-[:DEPENDS_ON]->(d)
RETURN d.name AS destination, 'DEPENDS_ON' AS kind
UNION
MATCH (:UnionDemoService {id: 'api'})-[:CALLS]->(d)
RETURN d.name AS destination, 'CALLS' AS kind;
```

**Answer:** `UNION` compares the **pair `(destination, kind)`**, not just the `destination` column. The two Auth rows have different `kind` values, so both are retained.

### Exercise 4. Count Occurrences of Each Destination Across the Whole Graph

Combine all `DEPENDS_ON` and `CALLS` edges and count by `d.name`.

**Answer:**

```cypher
CALL () {
  MATCH (:UnionDemoService)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.name AS destination
  UNION ALL
  MATCH (:UnionDemoService)-[:CALLS]->(d:UnionDemoService)
  RETURN d.name AS destination
}
RETURN destination, count(*) AS appearances
ORDER BY appearances DESC, destination;
```

Result: **Auth = 5, Billing = 1, Catalog = 1**. This query requires Neo4j 5.23+ because it uses `CALL ()`.

### Exercise 5. Keep All Five Services, Even Those Without Edges

Find the number of **unique destinations** for each service across both relationship types, including Auth and Metrics.

**Reference answer for Neo4j 5.24+:**

```cypher
MATCH (s:UnionDemoService)
OPTIONAL CALL (s) {
  MATCH (s)-[:DEPENDS_ON]->(d:UnionDemoService)
  RETURN d.id AS destinationId
  UNION
  MATCH (s)-[:CALLS]->(d:UnionDemoService)
  RETURN d.id AS destinationId
}
RETURN s.name AS sourceService,
       count(destinationId) AS destinationCount
ORDER BY sourceService;
```

Result: **API = 3, Auth = 0, Billing = 1, Catalog = 1, Metrics = 0**.

### Exercise 6. Fix the Alias Error

What is wrong with the following snippet?

```cypher
MATCH (a:UnionDemoService)-[:DEPENDS_ON]->(b:UnionDemoService)
RETURN b.name AS dependency
UNION ALL
MATCH (a:UnionDemoService)-[:CALLS]->(b:UnionDemoService)
RETURN b.name AS callee;
```

**Answer:** both branches must return the same column name; change both to `RETURN b.name AS destination`.

## 15. Conclusions and Takeaways

1. `UNION ALL` **keeps all rows**, including duplicates; `UNION` **removes duplicate rows** across **all `RETURN`ed columns**.
2. Every branch must return **the same number and names of columns**, with a consistently designed schema and data types.
3. Do not rely on `UNION` row ordering. To sort, paginate, or aggregate **after merging**, wrap the branches in `CALL { ... }` and process in the outer query.
4. Inside a correlated `CALL`, `UNION` branches execute per outer row. On Neo4j 5.23+, use `CALL (s)`; on older versions use `WITH s` in **each branch**.
5. `OPTIONAL CALL` (5.24+) preserves rows with no inner results; watch out for `null` when counting.
6. `UNION DISTINCT` appeared in Neo4j 5.19 and is equivalent to `UNION`. Grouping multiple `UNION` types is a **Cypher 25** feature on Neo4j 2025.06+.
7. Choose `UNION` or `UNION ALL` based on **data semantics** first, then measure performance impact with `EXPLAIN`/`PROFILE`.

## References

- [Neo4j Cypher Manual — Combined queries (UNION)](https://neo4j.com/docs/cypher-manual/current/queries/composed-queries/combined-queries/) — column requirements, `UNION`/`UNION ALL`, `UNION DISTINCT`, post-processing, and `UNION` grouping in Cypher 25.
- [Neo4j Cypher Manual 5 — Combined queries](https://neo4j.com/docs/cypher-manual/5/queries/combined-queries/) — examples compatible with Cypher/Neo4j 5.
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — post-`CALL` `UNION` processing, variable importing, and correlated subqueries.
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/) — distinguishing Cypher 5 and Cypher 25 since Neo4j 2025.06.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/) — result sorting rules and deterministic ordering.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — `EXPLAIN` and `PROFILE` for inspecting query cost.
