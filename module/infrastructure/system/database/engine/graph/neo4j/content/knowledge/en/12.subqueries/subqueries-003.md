# COUNT and COLLECT Subqueries When Supported by the Version

> **Chapter:** Subqueries  
> **Scope:** Neo4j property graph and Cypher; counting subquery results with `COUNT { ... }`, collecting results into a list with `COLLECT { ... }`, and choosing compatible alternatives when running older Neo4j versions.  
> **Objective:** Understand precisely what unit is counted, how to control the returned list, variable scoping, and how they differ from the `count()` and `collect()` aggregation functions.

## 1. Why Do We Need `COUNT { ... }` and `COLLECT { ... }`?

In Neo4j, a single node can connect to many other nodes via relationships. When displaying information about a service, we often want to keep **one row per service** while computing:

- **How many** other services does this service depend on?
- What is the list of names of **the services it depends on**?
- How many **two-hop dependency paths** exist?
- Retrieve **at most the first two dependencies by name** for each service.
- How many dependencies have the property `critical = true`?

If you write `MATCH` directly for all relationships and then `RETURN`, a service with three relationships can produce three rows; getting one row requires grouping. Subquery expressions solve this right in the position of an **expression**:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT { (s)-[:DEPENDS_ON]->(:CountCollectDemoService) } AS directCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

Meaning:

- `COUNT { ... }` counts **the number of rows produced by the subquery** and returns an integer.
- `COLLECT { ... }` takes **the value of the single `RETURN` column** in each inner row to build a list.
- Variable `s` from the outer query is used **directly inside** the subqueries; you do not need to declare `WITH s` to import it.
- The expression result is computed per row `s`; using these two expressions does not multiply the outer rows.

> **Important distinction:** `COUNT { ... }` and `COLLECT { ... }` are **subquery expressions**; `count(...)` and `collect(...)` are **aggregation functions**. Curly braces `{ ... }` differ from parentheses `(...)` in both syntax and processing scope.

## 2. Version Requirements: Do Not Apply One Syntax to Every Neo4j Version

| Environment version | `COUNT { ... }` | `COLLECT { ... }` | Application choice |
|---|---|---|---|
| Neo4j 4.4 | Does not support the new `COUNT { ... }` form | Not supported | Use `OPTIONAL MATCH` + `count()/collect()` or `CALL { WITH s ... }`. |
| Neo4j 5.0–5.2 | Has `COUNT { ... }` expression for supported patterns/cases | Not yet supported | Use `COUNT` for simple pattern counts; use aggregation or `CALL` to return lists. |
| Neo4j 5.3–5.5 | `COUNT` extended to support read queries such as `UNION` and `WITH` inside | Not yet supported | Use complex `COUNT` when needed; lists still rely on `collect()` or `CALL`. |
| Neo4j 5.6 and later | Supported | **Supports `COLLECT { ... }`** | Both can be used in `RETURN`/`WHERE`/`SET` at valid expression positions. |
| Neo4j 2025.06 and later, running Cypher 5 or Cypher 25 | Supports the general examples in this lesson | Supports the general examples in this lesson | Cypher 25 also has conditional subquery forms such as `WHEN ... THEN ... ELSE` that Cypher 5 does not have. |

**Version note:** Neo4j 5.6 means release **5.6**, not an arbitrary user-selected "Cypher 5.6". Starting from Neo4j **2025.06**, the server can support choosing **Cypher 5** or **Cypher 25**. The main examples here use syntax common to Neo4j **5.6+** and do not require Cypher 25-specific syntax.

If your system has multiple environments (development, CI, staging, production), check the version **actually running where queries execute**, rather than relying solely on the Java Driver or Spring Data Neo4j library version. A newer driver does not automatically add missing Cypher syntax on an older server.

## 3. Sample Dataset: Service Dependency Graph

We use a property graph from a microservices system containing five service nodes. A `:DEPENDS_ON` relationship means the service at the source must use the service at the target. The `critical` property marks critical dependencies.

```text
                      DEPENDS_ON
            +------------------------> (Auth)
            |                            ^  ^
            |                            |  |
          (API) ---------> (Catalog) ----+  |
            |                              |
            +--------------> (Billing) ----+
                           DEPENDS_ON

         (Metrics) -- no outgoing DEPENDS_ON
```

Specific edges:

| From | To | `critical` |
|---|---|---|
| API | Auth | `true` |
| API | Catalog | `false` |
| API | Billing | `true` |
| Catalog | Auth | `false` |
| Billing | Auth | `true` |

The test data can be created in a **test database**:

```cypher
MERGE (api:CountCollectDemoService {id: 'api'})
SET api.name = 'API'
MERGE (auth:CountCollectDemoService {id: 'auth'})
SET auth.name = 'Auth'
MERGE (catalog:CountCollectDemoService {id: 'catalog'})
SET catalog.name = 'Catalog'
MERGE (billing:CountCollectDemoService {id: 'billing'})
SET billing.name = 'Billing'
MERGE (metrics:CountCollectDemoService {id: 'metrics'})
SET metrics.name = 'Metrics'
WITH api, auth, catalog, billing
MERGE (api)-[r1:DEPENDS_ON]->(auth)
SET r1.critical = true
MERGE (api)-[r2:DEPENDS_ON]->(catalog)
SET r2.critical = false
MERGE (api)-[r3:DEPENDS_ON]->(billing)
SET r3.critical = true
MERGE (catalog)-[r4:DEPENDS_ON]->(auth)
SET r4.critical = false
MERGE (billing)-[r5:DEPENDS_ON]->(auth)
SET r5.critical = true;
```

`MERGE` prevents repeated runs on a clean sample graph from unintentionally creating duplicate identical relationship patterns. In a production system, there should be a uniqueness constraint on the identifier key. The results shown in this lesson assume the `:CountCollectDemoService` label contains only the five nodes and edges above.

## 4. `COUNT { ... }` — Counting Rows Produced by a Pattern or Subquery

### 4.1. Counting Direct Dependencies

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
       } AS dependencyCount
ORDER BY service;
```

| service | dependencyCount |
|---|---:|
| API | 3 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 1 |
| Metrics | 0 |

In the simple form containing only a relationship pattern, you can **omit the `MATCH` keyword** inside `COUNT`:

```cypher
COUNT { (s)-[:DEPENDS_ON]->(d:CountCollectDemoService) }
```

If you need multiple clauses or explicit conditional expressions, write the full form:

```cypher
COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
}
```

Even though API has three dependencies, the outer query still has only one row with `service = 'API'`. For Auth and Metrics, which have no dependencies, the result is **0**, without needing `OPTIONAL MATCH` in the outer query.

### 4.2. Counting with Relationship Property Filtering

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
         WHERE r.critical = true
       } AS criticalCount
ORDER BY service;
```

| service | criticalCount |
|---|---:|
| API | 2 |
| Auth | 0 |
| Billing | 1 |
| Catalog | 0 |
| Metrics | 0 |

Only **rows corresponding to patterns with `r.critical = true`** are counted. You can combine conditions on node `d`, relationship `r`, or parameters `$name`/`$minRisk`.

### 4.3. Filtering the Outer Query by Relationship Count

Find services with **two or more direct dependencies**:

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
} >= 2
RETURN s.name AS service;
```

Result: **API**.

`COUNT { ... }` can appear in `WHERE` as an integer expression; it is not restricted to `RETURN`. Compare with `EXISTS { ... }`:

- `EXISTS { ... }`: returns `true/false`, suitable for "is there at least one?".
- `COUNT { ... }`: returns `0, 1, 2, ...`, suitable for "how many?" or "at least N?".

For a simple `> 0` check, `EXISTS` conveys intent more clearly; for a threshold like `>= 2`, `COUNT` is the natural choice.

### 4.4. Counting Paths vs. Counting Destination Nodes Are Different Requirements

Consider **exact two-hop** dependency paths:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(downstream:CountCollectDemoService)
} AS twoHopPathCount;
```

The result is **2**, because there are two ways to traverse:

```text
API -> Catalog -> Auth
API -> Billing -> Auth
```

However, both paths lead to **a single destination node, Auth**. If you want to count **distinct destination nodes**, use `RETURN DISTINCT` directly inside `COUNT` (Neo4j 5.3+):

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(downstream:CountCollectDemoService)
  RETURN DISTINCT downstream
} AS uniqueDownstreamCount;
```

The result is **1**. The difference lies in **which inner rows are counted**:

| Expression | What each inner row represents | Value for API |
|---|---|---:|
| `COUNT { MATCH (s)-[:DEPENDS_ON]->()-[:DEPENDS_ON]->(d) }` | One two-hop path match | 2 |
| `COUNT { MATCH (s)-[:DEPENDS_ON]->()-[:DEPENDS_ON]->(d) RETURN DISTINCT d }` | One unique destination node | 1 |

In models where multiple routes lead to the same service, counting paths versus counting affected services can differ greatly. Before writing a query, clarify whether you want to count **relationships, path patterns, or distinct nodes**.

### 4.5. `COUNT` with `UNION`: Watch Out for Duplicates

From Neo4j **5.3+**, `COUNT` supports complex read queries, including `UNION`. For example, suppose you want to count **service names** that appear as a direct dependency **or** a two-hop dependency:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS depName
  UNION
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS depName
} AS distinctAffectedServiceCount;
```

The result is **3** (Auth, Billing, Catalog). `UNION` removes duplicate rows after combining the two branches.

If replaced with `UNION ALL`, the result is **5**: three direct matches plus two two-hop paths reaching Auth. With `UNION` (deduplicating), each branch must `RETURN` the same number and names of columns; write `AS depName` explicitly to keep it easy to verify.

## 5. `COLLECT { ... }` — Building Lists Directly Inside an Expression

### 5.1. Basic Syntax and Empty List Results

Starting from **Neo4j 5.6**, you can write:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
       } AS dependencies
ORDER BY service;
```

| service | dependencies |
|---|---|
| API | `["Auth", "Billing", "Catalog"]` |
| Auth | `[]` |
| Billing | `["Auth"]` |
| Catalog | `["Auth"]` |
| Metrics | `[]` |

Unlike `COUNT`, `COLLECT` **must end with a `RETURN` that has exactly one column**. That column can be a string, number, node, relationship, map, or another value Cypher supports in lists.

When the subquery produces no result rows, the returned value is an **empty list `[]`**. This is a major convenience when building APIs: you can return `dependencies: []` instead of dropping services that have no relationships.

**Two invalid forms:**

```cypher
// INVALID: missing final RETURN
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
} AS dependencies;
```

```cypher
// INVALID: RETURN has two columns, whereas COLLECT only allows one column
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name, r.critical
} AS dependencies;
```

### 5.2. Returning a Map When Multiple Fields Are Needed

To retrieve both the dependency name and criticality level, wrap them in **a single map value**:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN {name: d.name, critical: r.critical} AS item
  ORDER BY item.name
} AS dependencies;
```

Result:

```json
[
  {"name": "Auth", "critical": true},
  {"name": "Billing", "critical": true},
  {"name": "Catalog", "critical": false}
]
```

`RETURN { ... } AS item` produces **a single map-typed column**, satisfying the `COLLECT` rule. When using the Java Driver, this column becomes a list of map values; the application can map it to an appropriate DTO.

### 5.3. Getting Top N per Node with `ORDER BY` and `LIMIT`

Goal: retrieve **the first two dependencies alphabetically** for **each service**:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS dependency
         ORDER BY dependency
         LIMIT 2
       } AS firstTwoDependencies
ORDER BY service;
```

The result for API is `["Auth", "Billing"]`, excluding Catalog. Services with only one dependency keep a one-element list; Auth and Metrics return `[]`.

`LIMIT 2` **inside** `COLLECT` limits results **for each node `s`**. Conversely, `LIMIT 2` at the end of the outer query only limits how many **services** are returned.

If you need to paginate the related list, you can place `SKIP` and `LIMIT` after `ORDER BY` inside, provided the application defines a deterministic order. Without `ORDER BY`, **the order of elements is not guaranteed**.

### 5.4. Removing Duplicates from the List

If multiple distinct paths lead to the same target node, `COLLECT` takes the value from **each row** by default, so duplicate elements may occur.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS downstream
  ORDER BY downstream
} AS allTwoHopDestinations;
```

Result: `["Auth", "Auth"]` (two distinct paths).

To get a **deduplicated** list of target nodes, add `DISTINCT`:

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN DISTINCT d.name AS downstream
  ORDER BY downstream
} AS uniqueTwoHopDestinations;
```

Result: `["Auth"]`.

**Rule:** `COLLECT { ... }` does not deduplicate by default. The name "collect" describes gathering **result rows**, not constructing a *set*.

### 5.5. Using `COLLECT` as an Expression in `WHERE` or `CASE`

Using `COLLECT { ... }` in a membership expression:

```cypher
MATCH (s:CountCollectDemoService)
WHERE 'Auth' IN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS dependency
}
RETURN s.name AS service
ORDER BY service;
```

Result: **API, Billing, Catalog**. For the simple question "is there a dependency named Auth?", `EXISTS { MATCH ... WHERE ... }` usually expresses the intent better and avoids materializing a list. However, `COLLECT` is useful when you need the **actual list** for subsequent processing.

## 6. Differences Between Subquery Expressions and Aggregation Functions

Two pairs of names are easy to confuse:

| Syntax | Category | Unit processed | Result |
|---|---|---|---|
| `COUNT { MATCH ... }` | Subquery expression | Rows produced by the query **inside curly braces** per outer row | Integer |
| `count(d)` | Aggregation function | Non-`null` values of `d` in the **current row group** | Integer |
| `COLLECT { MATCH ... RETURN d.name }` | Subquery expression | Value of a single column across inner rows | List |
| `collect(d.name)` | Aggregation function | Non-`null` values of `d.name` in the current row group | List |

Example aggregating with `OPTIONAL MATCH`:

```cypher
MATCH (s:CountCollectDemoService)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
RETURN s.name AS service,
       count(d) AS dependencyCount,
       collect(d.name) AS dependencies
ORDER BY service;
```

This query still returns all five services; `count(d)` yields `0` when `d = null`, and `collect(d.name)` skips `null` values so it returns `[]` for Auth and Metrics.

This approach is useful for older versions, but watch out for **row multiplication before aggregation**. If after the first `MATCH` there are two independent relationship branches—for instance, a service with 3 dependencies and 4 deployments—two consecutive `MATCH` clauses can produce **3 × 4 = 12 rows**. In that case, `count(d)` and `collect(d.name)` may duplicate or miscount unless you handle grouping/`DISTINCT`.

With `COUNT { ... }` and `COLLECT { ... }`, each expression processes **its own pattern bound to `s`**, avoiding row multiplication from combining multiple independent patterns in the same result stream:

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
       } AS dependencyCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.name AS name
         ORDER BY name
       } AS dependencyNames
ORDER BY service;
```

Changing syntax does not automatically guarantee faster speed; it primarily clarifies that the count and list are computed per outer node.

## 7. Outer Variables, Inner Variables, and Scoping Pitfalls

### 7.1. Outer Variables Are Used Directly

```cypher
MATCH (s:CountCollectDemoService)
RETURN s.name AS service,
       COUNT {
         MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
         WHERE r.critical = true
       } AS criticalCount,
       COLLECT {
         MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
         RETURN d.id AS dependencyId
       } AS dependencyIds;
```

Variable `s` is defined in the outer query and is available in **both** expressions. Variables `r` and `d` declared inside each expression have local scope; they do not "leak" outside.

**Invalid** example:

```cypher
// INVALID: d is only declared inside COLLECT.
MATCH (s:CountCollectDemoService)
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS dependency
} AS dependencies,
d.name AS outsideName;
```

If you want `d`'s name at the outer row level, you need an appropriate `MATCH` or `CALL { ... RETURN ... }` to export the variable.

### 7.2. Do Not Redeclare Outer Variables with the Same Name Inside the Expression

Variables from the outer scope remain accessible throughout the subquery; avoid **shadowing** by creating a new variable with the same name. For example:

```cypher
// INVALID: variable 'target' already exists outside, yet is redeclared in an inner WITH.
WITH 'Auth' AS target
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  WITH 'Billing' AS target
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE d.name = target
} AS n;
```

Fix: use a different name such as `desiredName`:

```cypher
WITH 'Auth' AS target
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  WITH 'Billing' AS desiredName
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE d.name = desiredName
} AS n;
```

The result is **1** because API depends on Billing. The outer `target` variable is unchanged. Complex inner `WITH` usage is supported from Neo4j 5.3+ for `COUNT`, and from 5.6+ for `COLLECT`.

### 7.3. Be Careful with `OPTIONAL MATCH` and Aggregation Inside `COUNT`

`COUNT { ... }` **counts subquery rows**, not non-`null` values.

The following example can be misleading:

```cypher
MATCH (s:CountCollectDemoService {id: 'metrics'})
RETURN COUNT {
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d
} AS rowsFromOptionalMatch;
```

The result is **1**, even though Metrics has no dependencies. Reason: `OPTIONAL MATCH` produces **one row with `d = null`** when no relationship is found; `COUNT { ... }` counts that row.

Similarly:

```cypher
MATCH (s:CountCollectDemoService {id: 'metrics'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN count(d) AS innerCount
} AS rowsFromAggregation;
```

The result is also **1**: `RETURN count(d)` produces **one aggregated row** with value `0`, so the outer `COUNT { ... }` counts one row. To count dependencies, use `COUNT { MATCH ... }` directly; do not nest an aggregation like this.

For `COLLECT`, if you use `OPTIONAL MATCH` followed by `RETURN d.name` when nothing matches, you may get a `null` element instead of an empty list because the subquery produced a `null` row. To get `[]` when there are no links, use regular `MATCH` inside `COLLECT` and let the expression handle the 0-row case naturally.

## 8. Real-World Application: Dependency Overview Dashboard and Alerts

Example query returning complete information to render one row on a service management dashboard:

```cypher
MATCH (s:CountCollectDemoService)
RETURN
  s.id AS id,
  s.name AS name,
  COUNT {
    MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
  } AS dependencyCount,
  COUNT {
    MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
    WHERE r.critical = true
  } AS criticalDependencyCount,
  COLLECT {
    MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
    RETURN d.name AS dependencyName
    ORDER BY dependencyName
  } AS dependencyNames
ORDER BY name;
```

| name | dependencyCount | criticalDependencyCount | dependencyNames |
|---|---:|---:|---|
| API | 3 | 2 | `["Auth", "Billing", "Catalog"]` |
| Auth | 0 | 0 | `[]` |
| Billing | 1 | 1 | `["Auth"]` |
| Catalog | 1 | 0 | `["Auth"]` |
| Metrics | 0 | 0 | `[]` |

From this output, the application can classify services with many dependencies needing monitoring, services independent of other systems, or construct DTOs for an API response. Data is modeled via nodes/relationships; `COUNT` and `COLLECT` are **read and expression-evaluation constructs** that do not mutate the graph.

A simple alert condition:

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
  WHERE r.critical = true
} >= 2
RETURN s.name AS serviceRequiringReview;
```

Result: **API**.

## 9. Alternatives When the Server Does Not Support `COLLECT { ... }`

### 9.1. Neo4j 4.4 or 5.0–5.5: `collect()` Aggregation

If the `COLLECT { ... }` expression is unavailable, you can still use:

```cypher
MATCH (s:CountCollectDemoService)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
RETURN s.name AS service,
       count(d) AS dependencyCount,
       collect(d.name) AS dependencyNames
ORDER BY service;
```

This approach is more broadly compatible, though it is prone to **row multiplication** if you subsequently join multiple independent patterns in the same `MATCH` pipeline.

### 9.2. Neo4j 4.4–5.22: `CALL { WITH s ... }` When Top N per Node Is Needed

For lists with per-node filtering/sorting/limiting, a `CALL` subquery can build a list column:

```cypher
MATCH (s:CountCollectDemoService)
CALL {
  WITH s
  OPTIONAL MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  WITH d
  ORDER BY d.name
  RETURN collect(d.name)[0..2] AS firstTwoDependencies
}
RETURN s.name AS service, firstTwoDependencies
ORDER BY service;
```

Explanation:

- The initial `WITH s` imports the outer variable using the legacy `CALL` syntax.
- `OPTIONAL MATCH` retains Auth/Metrics that have no dependencies.
- `WITH d ORDER BY d.name` sorts before `collect()` aggregates, and then the slice `[0..2]` takes only elements at indices 0 and 1.
- `collect(d.name)` skips `null` values, so the list for Auth/Metrics remains `[]`.

From Neo4j 5.23+, with the modern `CALL` subquery, you can import explicitly using `CALL (s) { ... }`. However, **`COUNT { ... }` and `COLLECT { ... }` still do not require that import syntax**.

### 9.3. Choosing Syntax Based on Requirements

| Requirement | Modern Neo4j with full features | Older versions |
|---|---|---|
| Count dependencies per node | `COUNT { ... }` | `OPTIONAL MATCH` + `count(d)`, or `CALL` with aggregation |
| List dependencies per node | `COLLECT { ... RETURN ... }` (5.6+) | `collect(d.name)` or `CALL` + `collect()` |
| Top 2 dependencies per node | `COLLECT { ... ORDER BY ... LIMIT 2 }` | `CALL`, sort then `collect()[0..2]` |
| Return multiple columns per dependency | `COLLECT` returning **one map** per row | `collect({ ... })` or `CALL` returning subquery |
| Only check whether a dependency exists | `EXISTS { ... }` | `EXISTS { ... }` per supported version syntax |

## 10. Interacting with the Java Driver and Spring Data Neo4j

`COUNT`/`COLLECT` expressions execute on the **server**. The Java Driver merely sends Cypher and receives return values, while Spring Data Neo4j builds the mapping between graph data and Java objects.

Java Driver 5.x example, given a configured and connected `Driver driver`:

```java
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.Value;

import java.util.List;
import java.util.Map;

String query = """
    MATCH (s:CountCollectDemoService {id: $serviceId})
    RETURN COUNT {
             (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
           } AS dependencyCount,
           COLLECT {
             MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
             RETURN d.name AS dependency
             ORDER BY dependency
           } AS dependencies
    """;

try (Session session = driver.session()) {
    Record record = session.run(
        query, Map.of("serviceId", "api")
    ).single();

    int dependencyCount = record.get("dependencyCount").asInt();
    List<String> dependencies =
        record.get("dependencies").asList(Value::asString);

    System.out.println(dependencyCount); // 3
    System.out.println(dependencies);    // [Auth, Billing, Catalog]
}
```

In this example, `COUNT` returns an integer; `COLLECT` returns an ordered `List<String>` thanks to `ORDER BY`. If returning maps, nodes, or relationships, choose the corresponding `Value` conversion API instead of calling `asString()` on every element.

With Spring Data Neo4j, a custom repository query can also use any Cypher syntax supported by the **server**. Verify projection/DTO mapping for your library version and column data types. In particular, `COLLECT` returns **a list of values**, which does not mean Spring Data Neo4j automatically hydrates the entire entity graph or relationships into entity fields.

**You cannot resolve an "Invalid input COLLECT" error by upgrading only the Java Driver** while the Neo4j server is still prior to 5.6. Choose the `collect()`/`CALL` fallback or upgrade the database.

## 11. Performance and Query Plans

### 11.1. Outer Node Scope Determines How Many Times Expressions Are Evaluated

`COUNT` and `COLLECT` are expressions that can be correlated with outer `s`. If `MATCH (s:CountCollectDemoService)` returns 10,000 nodes, the inner patterns must be evaluated for many rows. Wrapping them as an expression **does not eliminate relationship traversal cost**.

Filter targets early:

```cypher
EXPLAIN
MATCH (s:CountCollectDemoService {id: $serviceId})
RETURN COUNT {
  (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
} AS dependencyCount;
```

When you need actual row counts and execution cost:

```cypher
PROFILE
MATCH (s:CountCollectDemoService {id: $serviceId})
RETURN COLLECT {
  MATCH (s)-[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN d.name AS name
  ORDER BY name
  LIMIT 5
} AS topDependencies;
```

Use `EXPLAIN` to view the plan without executing; use `PROFILE` to collect runtime statistics. Do not rely on a fixed operator name because the planner can change across versions and statistics states.

### 11.2. Indexes and Constraints

The `id` key is the natural way to look up input nodes. In a dedicated demo database, you can create a uniqueness constraint:

```cypher
CREATE CONSTRAINT count_collect_demo_service_id IF NOT EXISTS
FOR (s:CountCollectDemoService)
REQUIRE s.id IS UNIQUE;
```

This constraint prevents nodes with the demo label from sharing the same non-`null` `id`, while providing an index to accelerate lookups by `id`. Note: a uniqueness constraint does not mean every node must have an `id`; property existence enforcement is a different constraint type with its own version/edition requirements.

### 11.3. Limiting Lists to Avoid Excessive Memory Usage

Even though `COLLECT { ... }` returns a single column, a node with hundreds of thousands of relationships can still create a massive list. For APIs displaying top N items, place `ORDER BY` and `LIMIT` inside the expression before building the list.

Do not assume `COLLECT` is always faster than `collect()`. Actual cost depends on outer row count, relationship density, filter conditions, sorting, and Neo4j version. Compare using `PROFILE` on a representative dataset.

## 12. Common Errors and How to Handle Them

| Symptom | Cause | Fix |
|---|---|---|
| `COLLECT { ... }` syntax is not recognized | Neo4j prior to **5.6**, or a language mode not supporting the syntax used in the query. | Check the actual server version; use `collect()`/`CALL` or upgrade the server. |
| `COUNT { ... }` with `UNION` fails on 5.0–5.2 | Complex read queries inside `COUNT` were only extended from **5.3**. | Use simple `COUNT` forms suited to the running version or switch to aggregation/`CALL`. |
| `COLLECT` errors due to missing `RETURN` | `COLLECT` requires a final `RETURN`. | Return exactly one expression with a clear alias. |
| `COLLECT` errors due to `RETURN a, b` | Subquery returns more than one column. | Wrap as `RETURN {a: a, b: b} AS item`. |
| `COUNT` returns 1 even though the node has no relationships | `OPTIONAL MATCH` or inner aggregation generates one row, even when no data matches. | Count using `COUNT { MATCH ... }` directly. |
| List contains duplicate names | Multiple paths/relationships produce multiple rows yielding the same value. | Use `RETURN DISTINCT ...` when unique values are required. |
| `COUNT` returns 2 when there is only 1 destination node | Two different paths lead to the same node. | Clarify "number of paths" vs. "number of nodes"; use `RETURN DISTINCT d` for unique nodes. |
| Fetching two elements produces unstable results | `LIMIT` without `ORDER BY`. | Add `ORDER BY` inside the subquery before `LIMIT`. |
| Cannot access `d` outside | `d` was created inside the subquery expression. | Return a number/list; if you need to output nodes row by row, use `MATCH` or `CALL`. |
| Adding `WITH` inside triggers a name conflict | Redeclaring an outer-scope variable. | Rename the new variable to avoid shadowing. |
| Multiple `MATCH` clauses inflate counts | Combining independent patterns causes row multiplication. | Split patterns into subquery expressions or aggregate carefully with `DISTINCT`. |

## 13. Practice Exercises with the Sample Graph

**Exercise 1.** Write a query to find services with **at least one critical dependency**. Expected result: **API** and **Billing**.

```cypher
MATCH (s:CountCollectDemoService)
WHERE COUNT {
  MATCH (s)-[r:DEPENDS_ON]->(:CountCollectDemoService)
  WHERE r.critical = true
} >= 1
RETURN s.name AS service
ORDER BY service;
```

**Exercise 2.** Write a query to get the names of API's critical dependencies in ascending order. Expected result: `["Auth", "Billing"]`.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COLLECT {
  MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE r.critical = true
  RETURN d.name AS dependency
  ORDER BY dependency
} AS criticalDependencies;
```

**Exercise 3.** Find the number of **distinct services** that API can affect in exactly two hops. Why does this differ from the number of two-hop paths?

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
RETURN COUNT {
  MATCH (s)-[:DEPENDS_ON]->(:CountCollectDemoService)
        -[:DEPENDS_ON]->(d:CountCollectDemoService)
  RETURN DISTINCT d
} AS uniqueDestinations;
```

Answer: **1**, because both paths end at Auth.

**Exercise 4.** Rewrite the dependency list query from Exercise 2 for Neo4j 4.4, where `COLLECT { ... }` does not exist yet.

```cypher
MATCH (s:CountCollectDemoService {id: 'api'})
CALL {
  WITH s
  OPTIONAL MATCH (s)-[r:DEPENDS_ON]->(d:CountCollectDemoService)
  WHERE r.critical = true
  WITH d ORDER BY d.name
  RETURN collect(d.name) AS criticalDependencies
}
RETURN criticalDependencies;
```

The result is still `["Auth", "Billing"]`. The legacy `CALL` form needs `WITH s` to import the variable; the modern `COLLECT` does not.

## 14. Summary

- `COUNT { ... }` counts **the number of rows in the subquery**, not necessarily unique nodes; `RETURN DISTINCT` changes the number of rows counted.
- `COLLECT { ... }` creates **a list from a single `RETURN` column**; use a map when combining multiple fields, and it returns `[]` when `MATCH` yields no rows.
- Use `ORDER BY`, `LIMIT`, and `DISTINCT` **inside** `COLLECT` to control the list for each outer node.
- Outer variables are directly available inside both expressions; new inner variables cannot be exported outside. They differ from `CALL` subqueries in variable-importing mechanics and result nature.
- Compatibility milestones to remember: `COUNT` exists in the Neo4j 5 line; richer read subquery capabilities start from **5.3**; `COLLECT` appears from **5.6**. Neo4j 4.4 and versions before those milestones require `count()/collect()` or `CALL`.
- When upgrading Java or Spring Data Neo4j applications, always verify the **server version**, inspect query row counts, and measure performance on realistic data.

## References

- [Neo4j Cypher Manual — COUNT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/count/) — row counting, filtering, `UNION`, outer variables, and limitations.
- [Neo4j Cypher Manual — COLLECT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/) — list creation, single-column `RETURN` requirement, filtering, and `UNION`.
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/) — `count()`, `collect()`, and `null` handling.
- [Neo4j Cypher Manual — Additions and compatibility (Neo4j 5)](https://neo4j.com/docs/cypher-manual/5/deprecations-additions-removals-compatibility/) — syntax addition milestones.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/) — result ordering and interaction with aggregation.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — `EXPLAIN` and `PROFILE`.
