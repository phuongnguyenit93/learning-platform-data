# CALL with Subqueries and Variable Passing by Cypher Version

> **Chapter:** Subqueries  
> **Scope:** Neo4j property graph, Cypher queries using `CALL` to process groups of nodes/relationships, perform per-row computations, and update the graph. The focus is on **how to pass variables from the outer query into a subquery**, especially when migrating from legacy Cypher to Cypher 5 and Cypher 25.

## 1. Why Do We Need `CALL` Subqueries?

In a Neo4j property graph, a query typically starts with `MATCH` to find nodes and relationships, followed by `WITH` or `RETURN` to aggregate results. When you need to process **each input node individually** — such as fetching at most two acquaintances per person, counting relationships per group, or updating data in batches — `CALL { ... }` helps organize the processing into a **subquery** with a clear variable scope.

You must distinguish between two uses of the `CALL` keyword:

- `CALL (p) { ... }`: invokes a **Cypher subquery**, defined inline by the query author inside curly braces.
- `CALL db.labels() YIELD label`: invokes a **procedure** provided by Neo4j or an application; parameter passing and `YIELD` belong to the procedure mechanism.

This lesson focuses on the first form. A `CALL` subquery does not produce an independent table of data and join it arbitrarily: **it is evaluated for each input row from the outer query**. The columns returned via `RETURN` by the subquery are appended to the corresponding row in the outer query.

A simple example that runs on **Neo4j 5.23+** or newer versions supporting the scope syntax:

```cypher
UNWIND [1, 2, 3] AS n
CALL (n) {
  RETURN n * n AS square
}
RETURN n, square
ORDER BY n;
```

| n | square |
|---:|---:|
| 1 | 1 |
| 2 | 4 |
| 3 | 9 |

Here, `UNWIND` produces three rows; each row has a value for `n`. `CALL (n)` brings that specific row's `n` into the subquery; `RETURN ... AS square` creates the `square` column for the outer query.

```text
Outer query                   Subquery                 Combined result
n = 1  -------------------->  square = 1    ------->  (1, 1)
n = 2  -------------------->  square = 4    ------->  (2, 4)
n = 3  -------------------->  square = 9    ------->  (3, 9)
```

## 2. Compatibility Matrix: How Variable-Passing Syntax Evolved

A common point of confusion is that the **Neo4j server version** and the **Cypher language version** no longer always share the same version number.

| Environment | How to pass variables from outer query to `CALL` | Notes |
|---|---|---|
| Neo4j 4.4 | `CALL { WITH x ... }` | Uses an initial `WITH` inside the subquery to import variables. |
| Neo4j 5.0–5.22 | `CALL { WITH x ... }` | Legacy syntax continues to be used. |
| Neo4j 5.23 and later | **Prefer** `CALL (x) { ... }` | Neo4j 5.23 introduced the *variable scope clause*. `CALL { WITH x ... }` and `CALL { ... }` without a scope declaration became *deprecated*. |
| Neo4j 5.24 and later | `CALL (x) { ... }`; adds `OPTIONAL CALL (x) { ... }` | `OPTIONAL CALL` can preserve the outer row when the subquery returns no rows. |
| Neo4j 2025.06 and later | `CYPHER 5` or `CYPHER 25` | A single server can run both language versions. The `CALL (x)` syntax works in both; new features after 2025.06 may only be available in Cypher 25. |

**Syntax selection rule:** when your application is guaranteed to run on Neo4j **5.23+**, use `CALL (x)` for new code. If you must maintain compatibility with 4.4 or 5.0–5.22, use importing `WITH` and accept that it is deprecated on newer versions. You cannot use `CALL (x)` on Neo4j 5.22 simply by prepending `CYPHER 25`: older server releases do not provide Cypher 25.

Starting from Neo4j **2025.06**, you can select the language version per query:

```cypher
CYPHER 25
WITH 7 AS x
CALL (x) {
  RETURN x * 10 AS result
}
RETURN result;
```

```cypher
CYPHER 5
WITH 7 AS x
CALL (x) {
  RETURN x * 10 AS result
}
RETURN result;
```

Both yield `result = 70` when executed on a server that supports language version selection. From Neo4j **2026.02**, new databases are more explicitly configured to use Cypher 25; upgraded databases may retain their older configuration. Therefore, when migrating systems, check **both the server version and the database's default language**.

## 3. Passing Variables with the Variable Scope Clause — The Modern Approach

General syntax:

```cypher
... // Outer query produces variables a, b, c
CALL (a, b) {
  // Subquery sees a, b
  // c is not imported so it is unavailable here
  RETURN ... AS output
}
RETURN a, b, c, output;
```

There are three important cases:

| Syntax | Variables usable inside the subquery | When to use |
|---|---|---|
| `CALL (a, b) { ... }` | Only `a` and `b` from the outer scope | Recommended default: explicit dependencies, easy to read and maintain. |
| `CALL (*) { ... }` | All variables currently in scope in the outer query | Small queries or when full context is needed; be careful when the outer query grows. |
| `CALL () { ... }` | Imports no variables from the outer scope | Subquery is independent of outer row data; it **still executes once per input row**. |

**Importing one or more variables:**

```cypher
WITH 4 AS price, 3 AS quantity, 'HN' AS region
CALL (price, quantity) {
  RETURN price * quantity AS total
}
RETURN region, price, quantity, total;
```

Result: `region = 'HN'`, `price = 4`, `quantity = 3`, `total = 12`. `region` exists only in the outer query; it does not need to be imported to be used in the outer `RETURN`.

**Importing all variables:**

```cypher
WITH 4 AS price, 3 AS quantity
CALL (*) {
  RETURN price * quantity AS total
}
RETURN total;
```

**Importing no variables:**

```cypher
UNWIND ['A', 'B'] AS code
CALL () {
  RETURN 100 AS fixedValue
}
RETURN code, fixedValue
ORDER BY code;
```

The subquery does not use `code` yet is still invoked twice: the result is `('A', 100)` and `('B', 100)`. `CALL ()` **does not mean executing only once for the entire query**.

### Imported Variables Persist Throughout the Subquery

With the scope clause, imported variables behave as *subquery-wide*: a regular `WITH` in the middle does not remove access to those variables.

```cypher
WITH 11 AS x
CALL (x) {
  UNWIND [2, 3] AS factor
  WITH factor
  RETURN x * factor AS product
}
RETURN x, product
ORDER BY product;
```

The result is `(11, 22)` and `(11, 33)`, even though `WITH factor` does not mention `x`.

However, **you cannot define aliases inside the import parentheses**, nor can you redeclare an imported variable:

```cypher
// INVALID: scope clause only accepts variable names, not aliases
WITH 1 AS x
CALL (x AS renamed) {
  RETURN renamed AS value
}
RETURN value;
```

```cypher
// VALID: define the alias in the outer query before importing
WITH 1 AS x
WITH x AS renamed
CALL (renamed) {
  RETURN renamed + 1 AS value
}
RETURN value;
```

A variable already existing in the outer query also **cannot become a new column name** returned by the subquery. For example, with `WITH 1 AS x`, writing `CALL (x) { RETURN x AS x }` causes a name conflict. Keep `x` outside and only return a new column such as `RETURN x + 1 AS nextX`.

## 4. Passing Variables with Importing `WITH` — Syntax for Legacy Versions

On Neo4j 4.4 and Neo4j 5.0–5.22, the start of the subquery must import variables using `WITH`. The example in section 1 is equivalently written as:

```cypher
UNWIND [1, 2, 3] AS n
CALL {
  WITH n
  RETURN n * n AS square
}
RETURN n, square
ORDER BY n;
```

Note: `WITH n` in this example is an **importing WITH**, recognized as such because it is the first clause inside `CALL { ... }` (or after `USE` where supported). It has stricter rules than a regular `WITH`:

1. Only **simple variable references** are allowed, such as `WITH n` or `WITH n, multiplier`.
2. Do not write expressions or aliases directly in the importing `WITH`: `WITH n AS number` and `WITH n + 1 AS nextN` are invalid in this role.
3. Do not attach `WHERE`, `ORDER BY`, `LIMIT`, `SKIP`, or `DISTINCT` directly to the importing `WITH`.
4. If there are multiple `UNION` branches inside the subquery, **each branch needs its own importing `WITH`** if it uses outer variables.

**Invalid** example on legacy versions:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL {
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value;
```

The fix is to use **two consecutive `WITH` clauses**; the first imports, and the second filters the data:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL {
  WITH n
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value
ORDER BY n;
```

The result contains only `n = 3` and `n = 4`. The rows `n = 1` and `n = 2` are not kept because the subquery returns no rows for them.

Once on Neo4j 5.23+, replace the legacy double `WITH` with:

```cypher
UNWIND [1, 2, 3, 4] AS n
CALL (n) {
  WITH n
  WHERE n > 2
  RETURN n * 10 AS value
}
RETURN n, value
ORDER BY n;
```

Here `WITH n` is a **regular** `WITH`, no longer an importing `WITH`; therefore, `WHERE` can be used.

One important difference to remember: with the legacy syntax, subsequent `WITH` clauses **can drop imported variables from scope** according to normal `WITH` rules. With the new `CALL (n)`, `n` remains referenceable anywhere inside the subquery.

## 5. Property Graph Example: Fetching Relationships per Node

To see why variable scope matters for **nodes**, **relationships**, and relationship traversal, let's use a small graph:

```text
(An) ──KNOWS──> (Bình) ──KNOWS──> (Chi)

  └────────────KNOWS────────────> (Chi)

(Dũng)     [no KNOWS relationships]
```

Create the data in a **test database**; `MERGE` lets you rerun the example without unintentionally adding duplicate nodes/relationships of the same pattern:

```cypher
MERGE (an:SubqueryDemoPerson {id: 'an'})
  SET an.name = 'An'
MERGE (binh:SubqueryDemoPerson {id: 'binh'})
  SET binh.name = 'Bình'
MERGE (chi:SubqueryDemoPerson {id: 'chi'})
  SET chi.name = 'Chi'
MERGE (dung:SubqueryDemoPerson {id: 'dung'})
  SET dung.name = 'Dũng'
WITH an, binh, chi
MERGE (an)-[:KNOWS]->(binh)
MERGE (an)-[:KNOWS]->(chi)
MERGE (binh)-[:KNOWS]->(chi);
```

### 5.1. Counting Relationships per Person, Including People with 0 Relationships

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN count(friend) AS knownCount
}
RETURN p.name AS person, knownCount
ORDER BY knownCount DESC, person;
```

| person | knownCount |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 0 |
| Dũng | 0 |

`CALL (p)` brings **node p** into the inner scope. `OPTIONAL MATCH` handles the case where there are no relationships, and `count(friend)` counts non-`null` values, so `Chi` and `Dũng` get a count of 0.

For Neo4j 4.4–5.22, replace the subquery header with:

```cypher
MATCH (p:SubqueryDemoPerson)
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN count(friend) AS knownCount
}
RETURN p.name AS person, knownCount
ORDER BY knownCount DESC, person;
```

### 5.2. Fetching at Most One Acquaintance for **Each** Person

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN friend.name AS firstFriend
  ORDER BY firstFriend
  LIMIT 1
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

| person | firstFriend |
|---|---|
| An | Bình |
| Bình | Chi |

`LIMIT 1` **inside** the subquery applies to **each row `p`**. Placing `LIMIT 1` at the end of the outer query would return only one row for the **entire** result, not one row per person. `Chi` and `Dũng` disappear here because `MATCH` inside the subquery finds no rows for them.

From **Neo4j 5.24+**, you can keep these two people using `OPTIONAL CALL`:

```cypher
MATCH (p:SubqueryDemoPerson)
OPTIONAL CALL (p) {
  MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  RETURN friend.name AS firstFriend
  ORDER BY firstFriend
  LIMIT 1
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

`Chi` and `Dũng` will appear with `firstFriend = null`. This mirrors `OPTIONAL MATCH`: when the subquery produces no rows, `OPTIONAL CALL` keeps the input row and assigns `null` to the subquery's returned columns.

If you need compatibility with older Neo4j versions without `OPTIONAL CALL`, one option is to return **a single aggregated result** per person:

```cypher
MATCH (p:SubqueryDemoPerson)
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:KNOWS]->(friend:SubqueryDemoPerson)
  WITH friend
  ORDER BY friend.name
  RETURN collect(friend.name)[0] AS firstFriend
}
RETURN p.name AS person, firstFriend
ORDER BY person;
```

Because `collect()` ignores `null` values, people with no relationships receive `firstFriend = null`, and every person still gets one result row. With a very large number of friends, collecting everything into a list requires memory consideration; `OPTIONAL CALL` combined with `LIMIT` is usually clearer on supported versions.

### 5.3. `UNION` Inside a Subquery and Import Scope

Suppose we want to retrieve both outgoing and incoming `KNOWS` relationships for the person named `Chi`.

In Neo4j 5.23+, import `targetName` **once** for the entire subquery; every `UNION ALL` branch can use that variable:

```cypher
WITH 'Chi' AS targetName
CALL (targetName) {
  MATCH (a:SubqueryDemoPerson {name: targetName})-[:KNOWS]->(b)
  RETURN b.name AS otherPerson, 'outgoing' AS direction
  UNION ALL
  MATCH (a:SubqueryDemoPerson {name: targetName})<-[:KNOWS]-(b)
  RETURN b.name AS otherPerson, 'incoming' AS direction
}
RETURN targetName, otherPerson, direction
ORDER BY direction, otherPerson;
```

Result: two rows `('Chi', 'An', 'incoming')` and `('Chi', 'Bình', 'incoming')`. With legacy Neo4j using importing `WITH`, **each branch must re-import**:

```cypher
WITH 'Chi' AS targetName
CALL {
  WITH targetName
  MATCH (a:SubqueryDemoPerson {name: targetName})-[:KNOWS]->(b)
  RETURN b.name AS otherPerson, 'outgoing' AS direction
  UNION ALL
  WITH targetName
  MATCH (a:SubqueryDemoPerson {name: targetName})<-[:KNOWS]-(b)
  RETURN b.name AS otherPerson, 'incoming' AS direction
}
RETURN targetName, otherPerson, direction
ORDER BY direction, otherPerson;
```

`UNION` branches must match in **column names and count in `RETURN`**. `UNION` removes duplicate results by default; `UNION ALL` retains duplicates, which is useful when you need to reflect all relationships fully.

## 6. Returning Subqueries vs. Write-Only (Unit) Subqueries

There are two types of `CALL` subqueries that differ in their effect on the **row count** of the outer query:

| Type | Inside the subquery | Effect on outer rows |
|---|---|---|
| *Returning subquery* | Has `RETURN` | Can emit 0, 1, or more rows per input row. If 0 rows, the input row is dropped (unless using `OPTIONAL CALL` on supported versions). |
| *Unit subquery* | Has no `RETURN` | Typically used for `CREATE`, `MERGE`, `SET`, `DELETE`; preserves the outer query's row count. |

Unit subquery example: mark all test nodes as checked.

```cypher
MATCH (p:SubqueryDemoPerson)
CALL (p) {
  SET p.checked = true
}
RETURN p.id AS processedId
ORDER BY processedId;
```

The `CALL` block returns no new columns; the outer query still has four rows: `an`, `binh`, `chi`, and `dung`.

Do not confuse `CALL () { RETURN count(*) AS c }` with a unit subquery. Even though it appears to return only a single value, it is **still a returning subquery**. The distinction lies in **the presence or absence of `RETURN`**, regardless of the number of columns.

A subquery returning too many rows will multiply the outer row count. If the outer query feeds 100 nodes, and each node has an average of 20 relationships matching the inner `MATCH`, the result can expand to around 2,000 rows. Use per-group `LIMIT`, `count()` / `collect()` aggregation, or early filtering when appropriate.

## 7. Using `CALL ... IN TRANSACTIONS` for Batch Processing

When importing data, creating nodes, or updating the graph with a large number of rows, you can append `IN TRANSACTIONS` after the subquery so Neo4j processes them in batched **inner transactions**.

Example for **Neo4j 5.23+**; run on a test database:

```cypher
UNWIND range(1, 2500) AS num
CALL (num) {
  MERGE (:SubqueryBatchDemo {id: num})
} IN TRANSACTIONS OF 500 ROWS
RETURN count(*) AS submittedRows;
```

There are 2,500 input rows and a batch size of 500 rows; changes are committed incrementally across inner transactions. For Neo4j 4.4–5.22, use the legacy variable-importing syntax inside the block:

```cypher
UNWIND range(1, 2500) AS num
CALL {
  WITH num
  MERGE (:SubqueryBatchDemo {id: num})
} IN TRANSACTIONS OF 500 ROWS
RETURN count(*) AS submittedRows;
```

Important notes:

- `CALL { ... } IN TRANSACTIONS` only runs inside an **implicit/auto-commit transaction**, not inside an explicit transaction. In Neo4j Browser, prepend `:auto` before the query if Browser requires it.
- With the Java Driver, do not wrap this statement in a managed transaction such as `session.executeWrite(...)`; use an **implicit transaction** execution method such as `session.run(query, params)`, and consume all results according to the Driver API.
- Previously committed batches may remain persisted if a later batch fails. Design your logic to be safely re-runnable, such as `MERGE` on an appropriate identifier key, and monitor errors.
- `IN TRANSACTIONS` addresses **commit boundaries and batch size**; it does not by itself guarantee a fast query if each row must perform a full graph scan. For `id` lookups, check appropriate indexes/constraints and the `PROFILE` plan.

## 8. Common Upgrade Errors and How to Fix Them

| Symptom | Cause | Fix |
|---|---|---|
| `Variable x not defined` inside `CALL` | `x` was not imported or fell out of scope in legacy `WITH` syntax. | Neo4j 5.23+: `CALL (x)`; older versions: `CALL { WITH x ... }` and carry `x` through required `WITH` clauses. |
| Syntax error on `CALL (x)` | Server is older than Neo4j 5.23. | Use importing `WITH` or upgrade the environment. |
| `Importing WITH ... WHERE is not allowed` | Attached `WHERE` directly after importing `WITH`. | Use `WITH x WITH x WHERE ...` on older versions; on newer versions use `CALL (x) { WITH x WHERE ... }`. |
| Error on `CALL (x AS alias)` | Scope clause does not support aliases or expressions. | Define the alias in the outer query, then import the new variable name. |
| Returned variable name conflict | `RETURN` in the subquery defines a name already present in the outer scope. | Choose a different output name, e.g., `AS score`; the outer variable remains available outside. |
| Missing people with no relationships | Returning subquery with `MATCH` yields 0 rows. | Use `OPTIONAL CALL` (5.24+) or an aggregating subquery with `OPTIONAL MATCH`. |
| Result contains only one person | Placed `LIMIT 1` in the outer query instead of inside the subquery. | Move `ORDER BY ... LIMIT 1` inside `CALL (p) { ... }` to limit **per p**. |
| `Variable x not defined` in the second `UNION` branch | Legacy syntax only imported `x` in the first branch. | Repeat `WITH x` in each branch; on 5.23+ use `CALL (x)`. |
| Error when using `IN TRANSACTIONS` | Query was invoked inside an explicit/managed transaction. | Execute using an implicit transaction. |

When you see a *deprecated* notice regarding importing `WITH`, distinguish between a **future-change warning** and a **current query error**. First verify the Neo4j version in use; then switch to the scope clause if your environment supports it.

## 9. Designing Maintainable and Efficient Queries

1. **Import only the variables you actually need.** `CALL (person, maxResults)` is usually easier to read than `CALL (*)` when the outer query holds many variables. This clarifies dependencies and reduces risk when adding variables in the future.
2. **Filter in the right place.** To get the top N relationships **per node**, place `ORDER BY` and `LIMIT` inside the subquery; to limit to N nodes **across the entire result**, place `LIMIT` outside.
3. **Watch row counts before and after `CALL`.** For subqueries returning many rows, cost can grow sharply with the number of nodes/relationships. Use `EXPLAIN` or `PROFILE` to inspect `Apply`/related operators and actual row counts.
4. **Use indexes for query anchor points.** If each invocation must look up nodes by `id` or business key, having the right index/constraint can matter more than switching between `CALL (x)` and `CALL (*)`.
5. **Know when `CALL` is unnecessary.** `EXISTS { ... }` checks existence, `COUNT { ... }` counts, and `COLLECT { ... }` returns a list in an expression; they have their own semantics and scoping rules. Use `CALL` when you need to return multiple columns/rows, process per-row logic, use `UNION`, or perform updates.
6. **Be careful with processing order.** The order of rows fed into `CALL` is not automatically guaranteed. If write logic depends on order, explicitly add `ORDER BY` right before `CALL`. Later subquery executions can observe changes made by earlier ones.

### Quick Decision Guide: Which Syntax to Choose?

```text
Server < Neo4j 5.23?
    Yes -> CALL { WITH x ... }
    No
      |
      +-- Need outer variables?    -> CALL (x, y) { ... }
      +-- None needed?             -> CALL () { ... }
      +-- Need all variables?      -> CALL (*) { ... }  [use intentionally]
      |
      +-- Need to keep rows on no match?
              Yes and >= 5.24     -> OPTIONAL CALL (x) { ... }
              Older version       -> OPTIONAL MATCH / aggregate to return 1 row
```

## 10. Key Takeaways

- A `CALL` subquery executes **once per input row**, and can only use outer variables when **explicitly imported**.
- Legacy syntax: `CALL { WITH x ... }`. Recommended syntax from Neo4j 5.23: `CALL (x) { ... }`, `CALL () { ... }`, or `CALL (*) { ... }`.
- Importing `WITH` has specific restrictions; inside a legacy `UNION` you must import in **each branch**. The new scope clause applies to the **entire** subquery and keeps imported variables visible throughout.
- Returning subqueries can change the row count; unit subqueries do not change the outer row count. `OPTIONAL CALL` (5.24+) preserves rows when there are no results.
- Starting from Neo4j 2025.06, you should also account for the **Cypher 5 / Cypher 25** selection alongside the server version.

## References

- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/) — per-row mechanics, scope clause, importing `WITH`, unit/returning subqueries, and `OPTIONAL CALL`.
- [Neo4j Cypher Manual 4.4 — CALL subqueries](https://neo4j.com/docs/cypher-manual/4.4/clauses/call-subquery/) — historical syntax suitable for legacy environments.
- [Neo4j Cypher Manual 5 — Additions/deprecations](https://neo4j.com/docs/cypher-manual/5/deprecations-additions-removals-compatibility/) — 5.23 (scope clause) and 5.24 (`OPTIONAL CALL`) milestones.
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/) — distinguishing Cypher 5/Cypher 25 since Neo4j 2025.06.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/) — batch processing and implicit transaction constraints.
