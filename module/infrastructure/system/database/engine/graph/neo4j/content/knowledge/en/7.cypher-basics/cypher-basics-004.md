# Intermediate Table Flow, Result Row Counts, and Variable Scope in Cypher

> **Chapter:** Cypher Basics  
> **Module context:** Neo4j stores data as a *property graph* consisting of nodes, relationships, and properties. When writing Cypher to query relationships or paths, what matters is not only whether a graph pattern matches, but also **how many data rows each clause changes and which variables remain usable**. These principles are foundational for reading results, tuning queries, and handling records from the Java Driver or Spring Data Neo4j.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Visualize a Cypher query as a stream of **intermediate tables consisting of rows and columns**.
2. Predict row counts after `MATCH`, `WHERE`, `OPTIONAL MATCH`, `UNWIND`, `WITH`, `DISTINCT`, and `LIMIT`.
3. Explain why a single input node can produce multiple rows when matching multiple relationships.
4. Distinguish `count(*)`, `count(x)`, `count(DISTINCT x)`, and the impact of `null`.
5. Know which variables are forwarded through `WITH`, when variables fall out of scope, and the role of the `AS` alias.
6. Control result **granularity** using grouping keys, aggregations, and the placement of `ORDER BY`/`LIMIT`.
7. Recognize queries that cause row explosions via Cartesian products or multi-branch relationship expansion.

## 2. Mental Model: Each Stage Receives and Emits Rows

Cypher is a **declarative** language: we write the pattern to find and the desired output, and Neo4j chooses the execution plan. To **reason about semantics**, you can imagine clauses operating sequentially on an intermediate result table:

```text
MATCH ...       -> create / expand rows using graph patterns
WHERE ...       -> keep rows satisfying the condition
OPTIONAL MATCH  -> expand if matched; otherwise keep the row with null
WITH ...        -> select columns, compute expressions, aggregate, filter, sort
MATCH ...       -> reuse variables still in scope and expand further
RETURN ...      -> produce final result columns returned to the caller
```

This is a **logical model** for understanding queries. Neo4j does not necessarily materialize separate physical tables after every clause: the optimizer can use pipelines, operators, indexes, and other execution strategies. Operations may be replanned as long as query semantics are preserved.

### 2.1. A Row Is a Tuple of Values Bound to Variables

Example:

```cypher
MATCH (p:Person)-[w:WORKS_ON]->(pr:Project)
RETURN p.name AS nhanSu, w.role AS vaiTro, pr.name AS duAn;
```

Immediately after `MATCH`, a row set might contain:

| Variable `p` | Variable `w` | Variable `pr` |
|---|---|---|
| Node An | Relationship WORKS_ON (role = lead) | Node Graph API |
| Node An | Relationship WORKS_ON (role = advisor) | Node Recommendation |
| Node Bình | Relationship WORKS_ON (role = developer) | Node Graph API |

Each intermediate column can hold **a node, relationship, path, string, number, list, map, or `null`**. A variable like `p` does not "hold only one single person for the whole query": it can take different values across rows; the same node can also appear in multiple rows.

**Concept of granularity:** Is the query returning "one row per node", "one row per relationship", or "one row per group"? Stating the granularity clearly before writing a query helps avoid miscounting and duplicate outputs.

## 3. Sample Data Used Throughout This Lesson

To verify row counts precisely, use a **practice database** with the following data. IDs carry the `c004-` prefix for easy identification. The counts in this lesson assume there are no duplicate-ID nodes/relationships and no extra edges connected to the sample nodes.

```cypher
MERGE (an:Person {id: 'c004-an'})
SET an.name = 'An', an.age = 30

MERGE (binh:Person {id: 'c004-binh'})
SET binh.name = 'Bình', binh.age = 27

MERGE (chi:Person {id: 'c004-chi'})
SET chi.name = 'Chi', chi.age = 35

MERGE (dung:Person {id: 'c004-dung'})
SET dung.name = 'Dũng', dung.age = 24

MERGE (api:Project {id: 'c004-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (reco:Project {id: 'c004-reco'})
SET reco.name = 'Recommendation', reco.status = 'planned'

MERGE (pipeline:Project {id: 'c004-pipeline'})
SET pipeline.name = 'Data Pipeline', pipeline.status = 'active'

MERGE (an)-[wa:WORKS_ON]->(api)
SET wa.role = 'lead'
MERGE (an)-[wb:WORKS_ON]->(reco)
SET wb.role = 'advisor'
MERGE (binh)-[wc:WORKS_ON]->(api)
SET wc.role = 'developer'
MERGE (chi)-[wd:WORKS_ON]->(reco)
SET wd.role = 'lead'

MERGE (an)-[:KNOWS]->(binh)
MERGE (binh)-[:KNOWS]->(chi);
```

Condensed diagram:

```text
An   ──WORKS_ON──> Graph API       (active)
  └──WORKS_ON──> Recommendation   (planned)
Bình ─WORKS_ON──> Graph API       (active)
Chi  ─WORKS_ON──> Recommendation  (planned)
Dũng   (not yet on a project)

Data Pipeline (active)             (no participants yet)
An ──KNOWS──> Bình ──KNOWS──> Chi
```

**Baseline reference table for self-checking:**

| Entity | Count |
|---|---:|
| Sample `Person` nodes | 4 |
| Sample `Project` nodes | 3 |
| Sample `WORKS_ON` relationships | 4 |
| Sample `KNOWS` relationships | 2 |
| People with at least one project | 3 |
| People with no project | 1 (Dũng) |
| Projects with no staff | 1 (Data Pipeline) |

In practice queries, we commonly use:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS ten;
```

The `WHERE` condition ensures only the four people in this lesson are evaluated, even if the database contains other `Person` records. If practicing on a database that already has extra edges attached to the sample nodes, row counts after relationship expansion will reflect the actual data.

## 4. `MATCH`: From One Row to Many Rows

### 4.1. Starting with a Set of Nodes

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS ten
ORDER BY ten;
```

After `MATCH` and `WHERE`, there are **4 rows**:

| Row | `p` |
|---:|---|
| 1 | Node An |
| 2 | Node Bình |
| 3 | Node Chi |
| 4 | Node Dũng |

`RETURN p.name` projects the node in each row into a string column; projecting properties does not merge rows by default.

### 4.2. Expanding One Relationship

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
MATCH (p)-[w:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, w.role AS vaiTro, pr.name AS duAn
ORDER BY nguoi, duAn;
```

The second `MATCH` clause is applied against the already-bound values of `p`:

| Input `p` | Matching Relationships | Output Rows |
|---|---:|---|
| An | 2 | An – Graph API; An – Recommendation |
| Bình | 1 | Bình – Graph API |
| Chi | 1 | Chi – Recommendation |
| Dũng | 0 | Dũng's row is dropped |
| **Total** | **4** | **4 rows** |

The input node count is 4; the post-expansion row count also equaling 4 is **purely coincidental**. An expansion can increase or decrease the row count because each input row can match 0, 1, or many relationships.

General model when each input row `i` matches `m_i` patterns:

\[
\text{Rows after MATCH} = \sum_{i=1}^{n} m_i
\]

In the example above: `2 + 1 + 1 + 0 = 4`.

### 4.3. Filtering Before Expanding Changes the Row Count

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND p.age >= 30
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

After `WHERE`, only **An and Chi** remain (2 rows); after the expanding `MATCH`, this becomes **3 rows**: An has two projects, Chi has one. Do not treat the number of people matching a filter as the final row count if another relationship expansion follows.

## 5. `WHERE`: Filtering Rows or Constraining Patterns

In a basic read query, a `WHERE` condition attached to `MATCH` restricts the patterns to be matched:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi;
```

Out of four `WORKS_ON` edges, only two lead to an `active` project. Result:

| nguoi | duAn |
|---|---|
| An | Graph API |
| Bình | Graph API |

If the condition were `WHERE p.age > 30`, only Chi meets the age threshold, yet Chi's project has status `planned`; when combined with `pr.status = 'active'`, zero rows remain.

Logically, you can think of `WHERE` as keeping rows where the condition expression evaluates to `true`. In Cypher, an expression involving `null` can evaluate to `null` (not `true`), so that row is also filtered out.

## 6. `OPTIONAL MATCH`: Keeping Rows with `null`

Unlike `MATCH`, which requires a match, `OPTIONAL MATCH` preserves every input row even when **no connection is found**, by assigning `null` to new unmatched variables.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

| nguoi | duAn |
|---|---|
| An | Graph API |
| An | Recommendation |
| Bình | Graph API |
| Chi | Recommendation |
| Dũng | `null` |

The result has **5 rows**. `OPTIONAL MATCH` does not mean "always output only one row per person": An still produces two rows, while Dũng retains one row containing `null` instead of being dropped.

With `m_i` pattern matches per input row:

\[
\text{Rows after OPTIONAL MATCH} = \sum_{i=1}^{n}\max(1,m_i)
\]

In the example: `max(1,2) + max(1,1) + max(1,1) + max(1,0) = 5`.

### 6.1. `WHERE` Accompanying `OPTIONAL MATCH`

Requirement: keep **all people**, but only traverse edges leading to active projects.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAnDangChay
ORDER BY nguoi;
```

`WHERE pr.status = 'active'` here **belongs to the optional pattern**. An and Bình match `Graph API`; Chi and Dũng have no `active` project, yet still retain one row with `null`:

| nguoi | duAnDangChay |
|---|---|
| An | Graph API |
| Bình | Graph API |
| Chi | `null` |
| Dũng | `null` |

### 6.2. Placing the Condition After `WITH` Has a Different Meaning

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, pr
WHERE pr.status = 'active'
RETURN p.name AS nguoi, pr.name AS duAnDangChay
ORDER BY nguoi;
```

Now `WHERE` **filters rows after `WITH`**. It drops Chi because `Recommendation` is `planned`, drops Dũng because `pr = null`, and drops the An – Recommendation row. Only **2 rows** (An, Bình) remain.

| Where Is the Condition Placed? | Meaning | Are Chi and Dũng Kept? |
|---|---|---|
| Immediately after `OPTIONAL MATCH` | Constrains the optional pattern being searched | Yes, with `pr = null` |
| After `WITH p, pr` | Filters the entire existing intermediate table | No |

This is a critical distinction when writing reports that must include people without matching relationships.

## 7. `WITH`: Variable Scope Boundaries and Processing Stages

`WITH` acts like a **column projection** combined with expression evaluation, aggregation, and row limiting. It divides a query into stages with explicit **variable scope**.

### 7.1. Only Forwarded Variables Remain Usable

```cypher
MATCH (p:Person)
WHERE p.id = 'c004-an'
WITH p.name AS ten, p.age AS tuoi
RETURN ten, tuoi;
```

`WITH p.name AS ten, p.age AS tuoi` produces two columns holding string and numeric values. After `WITH`, only `ten` and `tuoi` remain in scope; the node variable `p` **is not forwarded**.

**Intentionally invalid** example:

```cypher
// Invalid: p is out of scope
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten
RETURN p.age AS tuoi;
```

Fix by keeping `p`:

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p, p.name AS ten
RETURN ten, p.age AS tuoi;
```

Or extract the needed properties up front and pass them forward, as in the first valid query.

### 7.2. `AS` Aliases Rename Columns/Variables

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p AS nhanSu
RETURN nhanSu.name AS ten;
```

`p AS nhanSu` preserves the node value while **renaming the variable** to `nhanSu`; in the subsequent part, `p` is no longer in scope. Conversely, `WITH p.name AS nhanSu` produces a **string**, not a node; `nhanSu.age` no longer makes sense for accessing a person's property.

### 7.3. Keeping Multiple Variables When Expanding Further

```cypher
MATCH (p:Person {id: 'c004-an'})-[r:KNOWS]->(friend:Person)
WITH p, friend
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN friend.name AS ban, pr.name AS duAn
ORDER BY duAn;
```

After `WITH p, friend`, `p` and `friend` remain, while `r` does not. Because An has one outgoing acquaintance and two projects, the query returns **2 rows**:

| ban | duAn |
|---|---|
| Bình | Graph API |
| Bình | Recommendation |

If you need to return `r.since` at the end, you must pass `r` through `WITH`. Conversely, there is no need to keep `r` when you only want to chain nodes `p` and `friend`.

### 7.4. `WITH *` vs. Explicit Scope Selection

`WITH *` forwards all existing variables. It is convenient while experimenting:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH *
RETURN p.name AS nguoi, pr.name AS duAn;
```

In large queries, explicitly list `WITH p, pr` or only the columns needed. This makes scope clear, avoids accidentally retaining unnecessary variables, and prevents corrupting the **grouping granularity** in aggregation steps.

### 7.5. Variable Names and Parameters Are Not the Same

```cypher
MATCH (p:Person)
WHERE p.id = $personId
RETURN p.name AS ten;
```

`p` is a variable bound to nodes in rows; `$personId` is a parameter passed in by Neo4j Browser or a Java application, such as `'c004-an'`. Parameters supply **data values** and do not keep variable `p` alive across a `WITH` boundary.

## 8. Aggregations Change Row Counts and Granularity

`count`, `sum`, `avg`, `collect`, `min`, and `max` are common aggregate functions. Inside `WITH` or `RETURN`, they produce **one row per group** defined by the non-aggregated expressions in the same clause.

### 8.1. Before Aggregation: One Person Can Span Multiple Rows

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

The result has **5 rows** as in Section 6, with An appearing twice.

### 8.2. Grouping to Produce One Row per Person

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn, collect(pr.name) AS tenDuAn
RETURN p.name AS nguoi, soDuAn, tenDuAn
ORDER BY nguoi;
```

| nguoi | soDuAn | tenDuAn |
|---|---:|---|
| An | 2 | `['Graph API', 'Recommendation']` |
| Bình | 1 | `['Graph API']` |
| Chi | 1 | `['Recommendation']` |
| Dũng | 0 | `[]` |

The order of elements in An's list can vary if the input order is not specified. What is guaranteed is that `collect(pr.name)` contains both project names, and `collect` ignores `null` values so Dũng gets an empty list.

**Explanation:** In `WITH p, count(pr), collect(pr.name)`, `p` is the grouping key. From 5 intermediate rows, the query produces **4 groups**, one row per group.

### 8.3. Why Also Keeping `pr` Can Cause Miscounting

Compare:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
RETURN p.name AS nguoi, soDuAn;
```

Result: **An – 2**.

If you accidentally include `pr` in the grouping key list:

```cypher
MATCH (p:Person {id: 'c004-an'})-[:WORKS_ON]->(pr:Project)
WITH p, pr, count(pr) AS soDuAnTrongNhom
RETURN p.name AS nguoi, pr.name AS duAn, soDuAnTrongNhom;
```

The result becomes **2 rows**, each with `soDuAnTrongNhom = 1` because the grouping key is now **the pair `(p, pr)`**, instead of just `p`. This is a frequent mistake: which variables are kept in `WITH` can determine the granularity of the result.

### 8.4. `count(*)` vs. `count(pr)` When `null` Is Present

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi,
       count(*) AS soDong,
       count(pr) AS soDuAn
ORDER BY nguoi;
```

| nguoi | soDong | soDuAn |
|---|---:|---:|
| An | 2 | 2 |
| Bình | 1 | 1 |
| Chi | 1 | 1 |
| Dũng | 1 | 0 |

- `count(*)` counts **every row in the group**, including rows where some columns are `null`.
- `count(pr)` counts only rows where `pr` is **non-`null`**.
- `count(DISTINCT pr)` counts **unique projects** in each group, especially needed when joining additional patterns could repeat a project across multiple rows.

A query with no grouping keys that only returns `count(*)` across the entire dataset yields a single total value. When the input set has zero rows, an ungrouped aggregation such as `count(*)` still yields `0`; conversely, when grouping keys are present, there are no groups to emit.

### 8.5. Filtering **After** Computing Aggregations

Requirement: retrieve only people participating in two or more projects.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WITH p, count(pr) AS soDuAn
WHERE soDuAn >= 2
RETURN p.name AS nguoi, soDuAn;
```

The `WITH` stage reduces 5 rows to 4 groups. The `WHERE` following `WITH` keeps only An's group, so `RETURN` produces **1 row**. If the total-project condition were placed before `WITH` when `soDuAn` does not yet exist, the query could not use that alias.

## 9. `DISTINCT`: Deduplicating Rows Across Selected Columns

A node can appear multiple times across rows because it matches multiple edges:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi
ORDER BY nguoi;
```

The result has **4 rows**: An, An, Bình, Chi. If you only need a unique list of people:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN DISTINCT p.name AS nguoi
ORDER BY nguoi;
```

The result has **3 rows**: An, Bình, Chi. `DISTINCT` removes duplicate records across the **entire set of projected expressions**, rather than automatically deduplicating individual variables in other columns.

Example:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN DISTINCT p.name AS nguoi, pr.name AS duAn;
```

There are still **2 rows**, because the combinations `(An, Graph API)` and `(An, Recommendation)` are distinct.

`DISTINCT` is useful for expressing unique-data semantics; it should not be used to mask an erroneous join that unexpectedly inflates row counts.

## 10. `UNWIND`: Expanding a List into Multiple Rows

`UNWIND` performs the inverse transformation of `collect`: it **expands** each element of a list into its own row.

```cypher
UNWIND ['c004-an', 'c004-binh', 'c004-chi'] AS personId
MATCH (p:Person {id: personId})
RETURN personId, p.name AS ten;
```

In the sample graph, the input list has three elements, creating **3 rows**; each row then matches a node. If a `personId` does not match any node, `MATCH` drops that row; when you want to retain unmatched IDs, use `OPTIONAL MATCH`.

### 10.1. Duplicate Data Produces Duplicate Rows

```cypher
UNWIND [1, 1, 2] AS giaTri
RETURN giaTri;
```

Returns **3 rows**, even though there are only two distinct values. Adding `RETURN DISTINCT giaTri` leaves **2 rows**.

### 10.2. An Empty List Drops All Rows in the Stream

```cypher
WITH 'An' AS ten
UNWIND [] AS item
RETURN ten, item;
```

Returns **0 rows**: `UNWIND []` emits zero elements, so the initial `ten = 'An'` row is not forwarded either. This is an important characteristic when expanding a list column into rows.

### 10.3. `collect` and `UNWIND` Transform Table Shapes in Opposite Directions

```cypher
UNWIND ['Graph API', 'Recommendation'] AS duAn
WITH collect(duAn) AS danhSach
UNWIND danhSach AS tungDuAn
RETURN tungDuAn;
```

| Stage | Rows | Contents |
|---|---:|---|
| First `UNWIND` | 2 | One project name per row |
| `WITH collect(duAn)` | 1 | One list containing two project names |
| `UNWIND danhSach` | 2 | Two rows containing each project name |

Therefore, always check column data types: **a list inside a single cell** and **multiple rows** are two distinct structures.

## 11. Where Should `ORDER BY`, `SKIP`, and `LIMIT` Be Placed?

`ORDER BY` sorts rows; `SKIP` and `LIMIT` reduce the row count by position. Their scope of effect depends on the `WITH` or `RETURN` stage they are attached to.

### 11.1. Limiting Before Expanding Relationships

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
WITH p
ORDER BY p.age DESC, p.id
LIMIT 2
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

By age, the top two people are **Chi (35)** and **An (30)**. `WITH ... LIMIT 2` selects **2 nodes before** expanding; after `OPTIONAL MATCH`, these two people produce **3 rows** (Chi 1, An 2).

### 11.2. Limiting After Expanding Relationships

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn
LIMIT 2;
```

`LIMIT 2` at the end takes only **2 result rows**, both of which can belong to the same person (in the sample data, An's two rows), **not two different people**.

If the goal is "two people and the list of all projects for each", you must first group by person or select the people before expanding, and apply the limit at the appropriate stage.

### 11.3. Pagination Requires a Deterministic Sort Order

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.id AS id, p.name AS ten
ORDER BY ten, id
SKIP 0
LIMIT 2;
```

`SKIP 0` skips zero rows; `LIMIT 2` takes at most the next two rows after sorting. Add `id` as a tie-breaker in case names collide. Without `ORDER BY`, row order is not guaranteed. When data changes between queries, offset-based pagination can still encounter duplicate or skipped rows; large systems often consider keyset-based pagination.

## 12. Multiple Independent Patterns: Cartesian Products Cause Row Explosions

If you combine patterns that share no variables and have no joining condition, row counts can **multiply** together.

```cypher
MATCH (p:Person), (pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.id IN ['c004-api', 'c004-reco', 'c004-pipeline']
RETURN p.name AS nguoi, pr.name AS duAn
ORDER BY nguoi, duAn;
```

There are 4 people and 3 projects, so the query returns **4 × 3 = 12 rows**: every person–project combination, including people not working on that project. This is a **Cartesian product**.

If you want only people actually working on projects, the pattern must include the relationship:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi, pr.name AS duAn;
```

The result has only **4 rows**, corresponding to the four `WORKS_ON` relationships.

### 12.1. Expanding Two Branches Can Also Multiply Row Counts

For example, needing "An's acquaintances" and "the projects An participates in":

```cypher
MATCH (an:Person {id: 'c004-an'})-[:KNOWS]->(ban:Person)
MATCH (an)-[:WORKS_ON]->(pr:Project)
RETURN an.name AS nguoi, ban.name AS ban, pr.name AS duAn;
```

An has **1 outgoing KNOWS relationship** and **2 outgoing WORKS_ON relationships**, so the result has **1 × 2 = 2 rows**. If An had 5 acquaintances and 4 projects, there could be up to **20 combinatorial rows**. This is not always a bug; what matters is whether you need one row per combination or one row per person.

If the goal is one row for An with two independent lists, you can separate the stages:

```cypher
MATCH (an:Person {id: 'c004-an'})
OPTIONAL MATCH (an)-[:KNOWS]->(ban:Person)
WITH an, collect(DISTINCT ban.name) AS dsBan
OPTIONAL MATCH (an)-[:WORKS_ON]->(pr:Project)
RETURN an.name AS nguoi,
       dsBan,
       collect(DISTINCT pr.name) AS dsDuAn;
```

`WITH` aggregates the first branch down to **one row for An** before expanding the second branch. This approach works well when you need two independent lists and clarifies the intended granularity.

## 13. Comprehensive Example: Tracing Row Counts Across Clauses

**Problem:** List people aged 25 or older who have at least one active project; return their name, active project count, and list of project names. Order by most active projects first, then by name.

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND p.age >= 25
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
WITH p,
     count(pr) AS soDuAnActive,
     collect(DISTINCT pr.name) AS dsDuAnActive
WHERE soDuAnActive > 0
RETURN p.name AS nguoi, soDuAnActive, dsDuAnActive
ORDER BY soDuAnActive DESC, nguoi ASC;
```

Intermediate table analysis:

| Clause / Stage | Granularity and Variables in Scope | Row Count |
|---|---|---:|
| `MATCH (p:Person)` + ID filter | Per person: An, Bình, Chi, Dũng; variable `p` | 4 |
| `WHERE p.age >= 25` | Drops Dũng (age 24); leaves An, Bình, Chi | 3 |
| `OPTIONAL MATCH` + `pr.status = 'active'` filter | An – Graph API; Bình – Graph API; Chi – `null` | 3 |
| `WITH p, count(pr), collect(...)` | Grouped by `p`: An 1, Bình 1, Chi 0 | 3 |
| `WHERE soDuAnActive > 0` | Drops Chi's group | 2 |
| `RETURN ... ORDER BY ...` | Returns two rows, one row per person | 2 |

Result:

| nguoi | soDuAnActive | dsDuAnActive |
|---|---:|---|
| An | 1 | `['Graph API']` |
| Bình | 1 | `['Graph API']` |

**Variable scope** also changes clearly:

```text
MATCH p
  └─ p
OPTIONAL MATCH pr
  └─ p, pr
WITH p, count(pr) AS soDuAnActive, collect(...) AS dsDuAnActive
  └─ p, soDuAnActive, dsDuAnActive
RETURN ...
  └─ nguoi, soDuAnActive, dsDuAnActive (result columns)
```

After `WITH`, the variable `pr` is no longer directly available in `RETURN`, because it was not forwarded as an independent variable. The needed information from `pr` has been **aggregated into a count and a list**.

### 13.1. If You Also Want to Keep People Without Active Projects

Simply remove the filter condition after `WITH`:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
WITH p, count(pr) AS soDuAnActive, collect(pr.name) AS dsDuAnActive
RETURN p.name AS nguoi, soDuAnActive, dsDuAnActive
ORDER BY nguoi;
```

Now there are **4 rows**, including Chi and Dũng with project count `0` and an empty list `[]`. The age filter was also removed to illustrate keeping all four people.

## 14. Observing Actual Row Counts with `EXPLAIN` and `PROFILE`

The numbers in the examples above represent **logical cardinality** deduced from the sample graph. On real data, Neo4j provides execution plans to understand the operators and the number of rows processed.

```cypher
EXPLAIN
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN pr.name AS duAn;
```

`EXPLAIN` produces the estimated plan **without executing** the query. To observe actual row counts across operators:

```cypher
PROFILE
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = 'c004-an'
RETURN pr.name AS duAn;
```

`PROFILE` executes the query and provides runtime statistics, typically including row counts and database hits (depending on operator and version). `PROFILE` can modify data if used with write queries, so run it only on appropriate data.

When analyzing a plan, distinguish between:

- **Expected logical row count**: the output record count required by the problem.
- **Intermediate row count**: can grow very large due to expanding many edges or joining multiple branches.
- **Physical plan**: operators, indexes, and processing order selected by the optimizer to reduce cost while preserving correct results.

Indexes or constraints often speed up finding starting points and protect identifying data; they **do not automatically turn four `WORKS_ON` edges into four unique people**. To change granularity, you must express it explicitly with aggregations or `DISTINCT`.

## 15. Considerations When Reading Results via the Java Driver and Spring Data Neo4j

A Cypher result consists of **records**. If `RETURN` emits multiple rows for the same node, the application receives **multiple records**, even though those records may refer to the same node.

Example:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id = $personId
RETURN p.name AS personName, pr.name AS projectName
ORDER BY projectName;
```

When `$personId = 'c004-an'`, the query returns **2 records**:

| personName | projectName |
|---|---|
| An | Graph API |
| An | Recommendation |

If the application wants **one person with a list of projects**, choose the appropriate output structure directly in Cypher:

```cypher
MATCH (p:Person {id: $personId})
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.id AS personId,
       p.name AS personName,
       collect(pr.name) AS projects;
```

This query produces a single row containing a `projects` column of list type. With the two outputs above, mapping to a DTO or projection in Java differs: the first example maps to a list of per-project records, whereas the second maps to a single object holding a list. When using Spring Data Neo4j to map entities and relationships, design queries to return the exact shape expected by the mapping mechanism.

## 16. Common Pitfalls and How to Self-Check

| Symptom | Common Cause | Resolution |
|---|---|---|
| One person appears on multiple rows | That person matches multiple relationships. | Clarify granularity; use `WITH p, collect(...)` or `RETURN DISTINCT p` if appropriate. |
| Rows for people without projects disappear | Using mandatory `MATCH`. | Use `OPTIONAL MATCH` when rows must be preserved. |
| `null` rows still disappear even with `OPTIONAL MATCH` | `WHERE` filters the table after `WITH`. | Put the condition inside `OPTIONAL MATCH` or handle `null` intentionally. |
| `count(*) = 1` for a person with no projects | Counting the row kept by `OPTIONAL MATCH`. | Use `count(pr)` or `count(r)` to count matched values. |
| `count(pr)` is too large | Projects repeat after joining multiple branches. | Check the join pattern; consider `count(DISTINCT pr)`. |
| Undefined variable error | `WITH` did not forward the needed variable. | Add the variable to `WITH` or project the needed value under an alias. |
| Each project gets counted as its own group | Keeping `pr` alongside `p` in an aggregating `WITH`. | Keep only the grouping keys matching your target granularity. |
| `LIMIT 2` returns only one person | Limiting to two **rows**, which can both belong to the same node. | Select people first or group by person before limiting. |
| Results jump from a few rows to thousands | Independent patterns create a Cartesian product, or branches multiply combinatorially. | Connect patterns with relationships/join conditions, or aggregate each branch before expanding the next. |
| `UNWIND []` drops the original row | An empty list produces zero elements. | Handle empty lists before `UNWIND` if the row must be preserved. |
| Two pagination runs return different orders | Missing `ORDER BY` or insufficient tie-breaker keys. | Sort by a deterministic key, and consider keyset pagination. |

**Three questions to walk through a long query:**

1. **What does one row represent at this stage?** One node, one relationship, one path, one combination, or one group?
2. **How many output rows can each input row produce?** Zero matches, one match, many matches, or preserved via `OPTIONAL MATCH`?
3. **Which variables remain alive after `WITH`?** Are any renamed, converted to scalars/lists, or folded into aggregate functions?

## 17. Self-Practice Exercises

The exercises below use the dataset from Section 3. Try predicting the row count **before** running Cypher, then compare.

### Exercise 1. Counting Rows After Expansion

How many rows does the following query return, and which person's name repeats?

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

<details>
<summary>Answer</summary>

There are **4 rows**: An – Graph API, An – Recommendation, Bình – Graph API, Chi – Recommendation. **An** repeats twice because An has two `WORKS_ON` relationships; Dũng has no row.

</details>

### Exercise 2. Keeping People Who Have Not Joined a Project

Write a query returning **one row** per person, along with their project count, including Dũng with `0`.

<details>
<summary>Suggested Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, count(pr) AS soDuAn
ORDER BY nguoi;
```

Result: An 2, Bình 1, Chi 1, Dũng 0.

</details>

### Exercise 3. Variable Scope

Why does the following query fail? Fix it to return An's name and age.

```cypher
// Intentionally erroneous query
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten
RETURN ten, p.age AS tuoi;
```

<details>
<summary>Suggested Answer</summary>

`p` is not forwarded through `WITH`, so it is out of scope.

```cypher
MATCH (p:Person {id: 'c004-an'})
WITH p.name AS ten, p.age AS tuoi
RETURN ten, tuoi;
```

Or use `WITH p, p.name AS ten` and then `RETURN ten, p.age AS tuoi`.

</details>

### Exercise 4. `WHERE` on `OPTIONAL MATCH`

Write a query keeping all four people and returning the number of **active projects** for each. The sample data should produce An 1, Bình 1, Chi 0, Dũng 0.

<details>
<summary>Suggested Answer</summary>

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
WHERE pr.status = 'active'
RETURN p.name AS nguoi, count(pr) AS soDuAnActive
ORDER BY nguoi;
```

The `WHERE` condition is attached to the optional part, so Chi and Dũng still have rows with `count(pr) = 0`.

</details>

### Exercise 5. `LIMIT` at Different Stages

Predict the row count and which people appear in this query:

```cypher
MATCH (p:Person)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
WITH p
ORDER BY p.age DESC
LIMIT 2
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

<details>
<summary>Answer</summary>

`WITH` selects **Chi and An** first; `OPTIONAL MATCH` produces **3 rows**: Chi – Recommendation; An – Graph API; An – Recommendation. Without a final `ORDER BY`, the order of those three rows may vary.

</details>

### Exercise 6. Why Did Combinatorial Multiplication Happen?

Given two independent patterns with four people and three projects:

```cypher
MATCH (p:Person), (pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
  AND pr.id IN ['c004-api', 'c004-reco', 'c004-pipeline']
RETURN p.name AS nguoi, pr.name AS duAn;
```

What is the row count, and how do you fix it if you only want person–project pairs that actually have a `WORKS_ON` relationship?

<details>
<summary>Suggested Answer</summary>

There are **12 rows** because `4 × 3`. Fix it with a pattern containing the relationship:

```cypher
MATCH (p:Person)-[:WORKS_ON]->(pr:Project)
WHERE p.id IN ['c004-an', 'c004-binh', 'c004-chi', 'c004-dung']
RETURN p.name AS nguoi, pr.name AS duAn;
```

The result drops to **4 rows**.

</details>

## 18. Key Takeaways

The **intermediate table** is a helpful model for understanding Cypher semantics: each row is a tuple of variable values at a given stage. `MATCH` can increase or decrease row counts when matching patterns; `OPTIONAL MATCH` keeps unmatched rows with `null`; `WHERE` filters rows or constrains patterns depending on placement; `WITH` determines which variables remain in scope and whether rows are aggregated; `DISTINCT`, `UNWIND`, and `LIMIT` further reshape the table.

To read and tune Neo4j queries reliably, always identify the **desired granularity, intermediate row counts, and variable scope**. These govern the correctness of counts, relationship lists, path queries, and the record structures received by Java applications.
