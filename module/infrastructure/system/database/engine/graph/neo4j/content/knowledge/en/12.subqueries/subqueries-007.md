# Decomposing Complex Queries into Verifiable Blocks

## 1. Why Break Down a Cypher Query?

In Neo4j, data is represented as a **property graph**: nodes carry labels and properties, while relationships represent directed links between nodes. Cypher lets you traverse multiple relationship types, filter, aggregate, and return results in a single query. When business requirements involve multiple independent calculations, one long query easily causes three problems:

- **Hard to verify correctness:** you cannot tell whether bad numbers come from the node lookup step, relationship expansion step, or aggregation step.
- **Unintended row multiplication:** joining multiple one-to-many relationship branches can produce a row product, corrupting `count()`, `sum()`, and `avg()`.
- **Hard to control variable scope and cost:** a misplaced filter or aggregation can alter both the result set and the number of rows processed.

**Subqueries**, especially `CALL { ... }` and its scope-declaring variant `CALL (p) { ... }`, split a query into blocks with clear contracts: what input it takes, what output it produces, and how many rows it generates. The goal of this lesson is to build a workflow: *write one block → run it in isolation → compare against expected results → compose the blocks → verify the whole*.

After this lesson, you will be able to:

1. Point out why statistics go wrong when two independent relationship branches are `MATCH`ed in the same row stream.
2. Design a subquery that returns exactly one row per input node and verify the zero-relationship case.
3. Compose query blocks, keep variable scope clear, and use `EXPLAIN`/`PROFILE` to inspect performance.

## 2. Illustrative Problem and Test Data

Suppose a movie system needs statistics, for **each person**, on how many movies they acted in and how many movies they directed from 2020 onward. The system also needs the list of movie titles they acted in and should select only people who acted in at least two movies during this period.

Simple model:

```text
(:SQ007Person {id, name})
       | \
       |  \--[:SQ007_DIRECTED]--> (:SQ007Film {id, title, year})
       |
       +-----[:SQ007_ACTED_IN]--> (:SQ007Film {id, title, year})
```

Labels and relationship types prefixed with `SQ007` are for this example only, helping avoid collisions with existing data. Run the Cypher snippet below in a practice database to create the small dataset; `MERGE` allows re-running without automatically creating identical duplicate relationships.

```cypher
MERGE (an:SQ007Person {id: 'an'})
SET an.name = 'An'
MERGE (binh:SQ007Person {id: 'binh'})
SET binh.name = 'Bình'
MERGE (chi:SQ007Person {id: 'chi'})
SET chi.name = 'Chi'
MERGE (dung:SQ007Person {id: 'dung'})
SET dung.name = 'Dũng'

MERGE (alpha:SQ007Film {id: 'alpha'})
SET alpha.title = 'Alpha', alpha.year = 2021
MERGE (beta:SQ007Film {id: 'beta'})
SET beta.title = 'Beta', beta.year = 2023
MERGE (legacy:SQ007Film {id: 'legacy'})
SET legacy.title = 'Legacy', legacy.year = 2018
MERGE (delta:SQ007Film {id: 'delta'})
SET delta.title = 'Delta', delta.year = 2024

MERGE (an)-[:SQ007_ACTED_IN]->(alpha)
MERGE (an)-[:SQ007_ACTED_IN]->(beta)
MERGE (an)-[:SQ007_ACTED_IN]->(legacy)
MERGE (binh)-[:SQ007_ACTED_IN]->(beta)
MERGE (binh)-[:SQ007_ACTED_IN]->(delta)
MERGE (chi)-[:SQ007_ACTED_IN]->(legacy)

MERGE (an)-[:SQ007_DIRECTED]->(alpha)
MERGE (binh)-[:SQ007_DIRECTED]->(beta)
MERGE (binh)-[:SQ007_DIRECTED]->(delta)
MERGE (chi)-[:SQ007_DIRECTED]->(delta);
```

Expected results for the year threshold `2020`:

| Person | Acted from 2020 | Directed from 2020 | Notes |
|---|---:|---:|---|
| An | 2 | 1 | `Legacy` (2018) is excluded |
| Bình | 2 | 2 | Has two relationship branches with two films each |
| Chi | 0 | 1 | Only acted in a 2018 film |
| Dũng | 0 | 0 | Has no relationships |

**Important:** both Chi and Dũng must still appear when generating statistics for *all people*. When applying the filter "at least two acted films", only An and Bình remain.

## 3. Identifying the Bug: Two `OPTIONAL MATCH` Branches Multiply Rows

A seemingly reasonable query:

```cypher
MATCH (p:SQ007Person)
OPTIONAL MATCH (p)-[:SQ007_ACTED_IN]->(acted:SQ007Film)
WHERE acted.year >= 2020
OPTIONAL MATCH (p)-[:SQ007_DIRECTED]->(directed:SQ007Film)
WHERE directed.year >= 2020
RETURN p.id AS personId,
       count(acted) AS actedCount,
       count(directed) AS directedCount
ORDER BY personId;
```

For Bình, two acted films combine with two directed films to produce **4 rows** before aggregation: `(Beta, Beta)`, `(Beta, Delta)`, `(Delta, Beta)`, `(Delta, Delta)`. Consequently, the query returns `actedCount = 4` and `directedCount = 4` for Bình, whereas the true counts are `2` and `2`. Likewise, An gets `directedCount = 2` instead of `1`.

You could use `count(DISTINCT acted)` and `count(DISTINCT directed)` to fix **these two specific node counts**, but that is not a general solution. For example, `sum(acted.revenue)` would still double-count when the same acted film pairs with multiple directed films. A more verifiable approach is to **aggregate each branch before combining**.

## 4. Defining Input and Output Contracts for Each Block

Describe each block before writing code:

| Block | Input | Output | Expected row count |
|---|---|---|---|
| Root | `SQ007Person` label | `p` | One row per person |
| A: acting | One `p` | `actedCount`, `actedTitles` | **Exactly one row per `p`** |
| B: directing | One `p` | `directedCount` | **Exactly one row per `p`** |
| Combined | `p` and three statistical values | Person result row | One row per `p` |
| Final filter | `actedCount` | Only people with at least two films | Can reduce rows, as required |

The crux is that blocks A and B must return **one row even when there are no matching films**. To achieve this, each block uses `count()` and `collect()` aggregations **without grouping by film properties**. On an empty `MATCH`, `count()` returns `0` and `collect()` returns `[]`.

### 4.1. Testing Block A in Isolation — Acting

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount,
         collect(DISTINCT m.title) AS actedTitles
}
RETURN p.id AS personId, actedCount, actedTitles
ORDER BY personId;
```

Expected result: `an = 2` with titles `Alpha`, `Beta`; `binh = 2` with `Beta`, `Delta`; `chi = 0`, `dung = 0`, and both have empty lists `[]`. **Element order in `collect()` is not guaranteed** without explicit sorting; verify list contents rather than assuming order.

What to verify right here: the query returns **four rows**, with each `personId` appearing exactly once. If a person appears in multiple rows, block A fails its contract and should not be composed further yet.

### 4.2. Testing Block B in Isolation — Directing

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS directedCount
}
RETURN p.id AS personId, directedCount
ORDER BY personId;
```

Expected: `an = 1`, `binh = 2`, `chi = 1`, `dung = 0`; still **four rows**. Thus block B is verified independently before combining with A.

### 4.3. Composing the Two Verified Blocks

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount,
         collect(DISTINCT m.title) AS actedTitles
}
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS directedCount
}
RETURN p.id AS personId,
       p.name AS personName,
       actedCount,
       directedCount,
       actedTitles
ORDER BY personId;
```

Each `CALL` receives person `p` supplied by the outer stream. Because each block returns exactly one row, composing the two blocks **does not multiply rows**. The final query returns four people with the exact numbers in the expected table.

To apply the requirement *select only people with at least two acted films*, replace the final `RETURN` with:

```cypher
WITH p, actedCount, directedCount, actedTitles
WHERE actedCount >= 2
RETURN p.id AS personId,
       p.name AS personName,
       actedCount,
       directedCount,
       actedTitles
ORDER BY personId;
```

The snippet above is a **continuation** of the composed query, not a standalone statement: place it immediately after the second `CALL`. The result now contains only `an` and `binh`, each with exactly one row.

## 5. Automating Contract Verification with a Cypher Query

In addition to visual inspection, you can run a statement returning a Boolean value to verify the sample data and both blocks' contracts:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(a:SQ007Film)
  WHERE a.year >= 2020
  RETURN count(DISTINCT a) AS actedCount
}
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(d:SQ007Film)
  WHERE d.year >= 2020
  RETURN count(DISTINCT d) AS directedCount
}
WITH collect({
  id: p.id,
  acted: actedCount,
  directed: directedCount
}) AS actual
RETURN
  size(actual) = 4
  AND any(x IN actual WHERE x.id = 'an'   AND x.acted = 2 AND x.directed = 1)
  AND any(x IN actual WHERE x.id = 'binh' AND x.acted = 2 AND x.directed = 2)
  AND any(x IN actual WHERE x.id = 'chi'  AND x.acted = 0 AND x.directed = 1)
  AND any(x IN actual WHERE x.id = 'dung' AND x.acted = 0 AND x.directed = 0)
  AS passed;
```

`passed = true` means the sample data check passes. This query intentionally tests both multi-relationship cases and zero-film cases, because checking only people with data easily misses bugs that drop rows.

On real data, add invariants: row counts before and after aggregation blocks must match; each input identifier must appear once; counts must be non-negative; results must not depend on `collect()` order unless sorted.

## 6. Common Mistakes When Writing Subqueries

### 6.1. A Subquery Can Drop Outer Query Rows

The example below **does not preserve people with no acted films from 2020 onward**:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN m.title AS title
}
RETURN p.id AS personId, title;
```

This block returns **one row per matched film**, or **zero rows** if no films match. Consequently An and Bình appear multiple times, while Chi and Dũng disappear. The difference lies not in `CALL` itself, but in **how many rows the inner `RETURN` produces**. When you need one row per person, aggregate like blocks A/B or design the subquery with an appropriate row-preserving mechanism.

### 6.2. Variable Scope Must Be Transparent

In broadly compatible syntax:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  RETURN count(m) AS n
}
RETURN p.id, n;
```

`WITH p` at the top of the block imports variable `p` from the outer query into the subquery. Only values exported via the subquery's `RETURN` can be used after `CALL` (in addition to variables already present in the outer scope). Avoid naming output columns the same as variables already existing in the outer scope. Use `WITH` to carry or filter variables between steps when needed.

From **Neo4j 5.23**, you can use a clearer variable scope declaration syntax:

```cypher
MATCH (p:SQ007Person)
CALL (p) {
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS n
}
RETURN p.id, n;
```

The `CALL (p) { ... }` syntax directly declares the variable imported into the block. If you are practicing on a Neo4j version older than 5.23, use the `CALL { WITH p ... }` pattern from the main examples. Check which Neo4j and Cypher versions your system supports before copying modern syntax.

### 6.3. Distinguish Match Count, Distinct Node Count, and Sum

- `count(*)` counts pattern-matching rows; `count(m)` counts non-null `m` values; `count(DISTINCT m)` counts distinct movie nodes.
- When multiple relationships point to the same film, `count(m)` can exceed the actual number of films. Clearly define whether you are counting *relationships*, *occurrences*, or *distinct films*.
- `collect()` gathers values into a list; `collect(DISTINCT ...)` removes duplicate elements. `avg()` can return `null` when there is no data, so handle it explicitly if business rules require a default value.
- If you aggregate by a film property inside a block (e.g., `WITH m.year AS year, count(*) AS n`), the block may return **multiple rows per person**, breaking the single-row contract. Only do this when multi-row output is intentional.

### 6.4. Choose the Subquery Type Matching Your Output

Beyond `CALL` for blocks with multiple output columns, Cypher offers direct intent-expressing forms (availability depends on version):

```cypher
MATCH (p:SQ007Person)
RETURN p.id AS personId,
       EXISTS {
         MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
         WHERE m.year >= 2020
       } AS hasRecentDirectedFilm,
       COUNT {
         MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
         WHERE m.year >= 2020
       } AS recentActingMatches,
       COLLECT {
         MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
         WHERE m.year >= 2020
         RETURN m.title
       } AS recentActingTitles
ORDER BY personId;
```

`EXISTS { ... }` returns a Boolean, `COUNT { ... }` counts subquery-matching rows, and `COLLECT { ... }` returns a list. `COUNT` and `COLLECT` subquery expressions exist from Neo4j 5.6; do not assume every version supports them. In the sample dataset, acting relationships are not duplicated, so matching rows equal the number of films; when duplicate relationships or multi-branch paths exist, re-verify the counting unit. Use `CALL` when you need an independently testable block with multiple aggregations; use expression subqueries when the output fits a single scalar, Boolean, or list.

## 7. Checking Execution Plans and Performance

A readable query still needs to run efficiently on a large graph. Use:

```cypher
EXPLAIN
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount
}
RETURN p.id, actedCount;
```

`EXPLAIN` shows the plan **without executing the query**. When you have an appropriate benchmarking environment, replace it with `PROFILE` to see runtime data such as rows passing through each operator and database accesses (`DB Hits`). Watch closely where row counts spike after relationship expansion steps or before aggregation.

To improve performance:

1. Narrow the root node set with appropriate filter conditions before invoking multiple blocks. If filtering frequently by `id` or properties, consider indexes/constraints matching the actual schema.
2. Return only needed variables from each block; aggregate as early as possible when individual relationship rows are not needed.
3. Measure each block individually, then measure the composed query. A subquery runs once per **input row**, so a cheap block receiving too many rows can still consume significant resources.
4. Read the actual plan before concluding an index will be used; traversal direction, selectivity, and data statistics all affect the optimizer's choice.

## 8. Process for Applying This to Other Business Queries

For a complex Neo4j query, you can follow this cycle:

1. **Turn business questions into verifiable outputs.** Example: how many orders does each customer have, what is the total amount, and is there at least one order in progress?
2. **Identify the key and row count of the root stream.** Example: one row per `Customer`; record the count and a few customers with no orders.
3. **Separate independent relationship branches.** Each branch—such as orders, addresses, payment sessions—has clear inputs and outputs.
4. **Verify each branch on small data.** Compare row counts, boundary values, duplicate relationships, missing properties, and zero-match cases.
5. **Compose the blocks, then filter on aggregated results.** Re-check row counts to avoid errors from row multiplication or dropped rows.
6. **Use `EXPLAIN`/`PROFILE` and measure on representative data.** Choose a formulation that is both accurate and cost-effective.

### Practice Exercises

1. Replace the fixed year threshold with parameter `$fromYear` and pass `2023`. Predict each person's result before running it.
2. Add another `SQ007_ACTED_IN` relationship from An to an existing film via a separate test dataset; compare `count(m)` with `count(DISTINCT m)`. Explain why the contract must explicitly specify the counting unit.
3. Add the requirement "select only people who have directed at least one film from 2020 onward and acted in at least two films". Where should this condition be placed so it does not alter the aggregations?

**Completion criteria:** you can state the input/output row counts of each block; both subqueries A/B return correct results for all four people, including Dũng; the automated check returns `true`; the final filtered query returns exactly two people; and you can explain why the initial `OPTIONAL MATCH` query miscounted.
