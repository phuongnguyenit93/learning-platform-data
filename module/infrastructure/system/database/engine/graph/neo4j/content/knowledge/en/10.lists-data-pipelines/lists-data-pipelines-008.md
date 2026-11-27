# Tracking Row Counts When Expanding Lists and Matching Multiple Patterns in Cypher

In Neo4j, a Cypher query processes a **row stream**. Each row holds currently bound variables, such as `p`, `skill`, `project`, and `tag`. When using `UNWIND` to expand a list or `MATCH` to join additional graph patterns, **one input row can produce multiple output rows, one row, or zero rows**. Understanding these changes helps write semantically accurate queries, avoid overcounting, and control execution cost.

This lesson belongs to the **Lists and Data Pipelines** chapter, focusing on tracking *cardinality* (intermediate row counts) when querying nodes, relationships, and paths in a Neo4j property graph. The examples use Cypher and apply equally when later consuming results with the Neo4j Java Driver or Spring Data Neo4j.

## 1. Distinguishing Row Counts from Entity Counts

A Cypher row is **a combination of values for the variables currently in scope**, and does not necessarily correspond to a distinct node. The same `Person` node can appear in multiple rows when that person has multiple skills, works on multiple projects, or when a project carries multiple classification tags.

For example, if one person has 2 skills and 3 projects, a query expanding both dimensions can produce `2 × 3 = 6` rows for that person alone. Those six rows do not mean there are six people or six projects.

| Component | Typical Effect on Row Count |
| --- | --- |
| `MATCH` | Retains pattern-matching combinations; can drop non-matching rows or multiply rows when multiple matches exist. |
| `OPTIONAL MATCH` | If unmatched, keeps one row with new variables set to `null`; if multiple matches exist, still multiplies rows. |
| `UNWIND list AS x` | Turns each list element into a row; an empty list produces **0 rows**. |
| `WHERE` | Drops rows that do not satisfy the predicate. |
| `WITH` / `RETURN` projecting columns only | Typically preserves row count, unless combined with filtering, `DISTINCT`, aggregation, `LIMIT`, etc. |
| `DISTINCT` | Collapses duplicate rows over the **selected set of expressions**. |
| `count()`, `collect()`, and aggregations | Groups rows by grouping keys; output row count equals the number of groups (or one summary row if there are no grouping keys). |

> **Observation rule:** after each operation, ask "How many results can one input row match?" and compute row counts *per* input row. Do not assume every `MATCH` or `UNWIND` multiplies by a uniform factor.

## 2. Creating a Small Dataset for Verification

Run the following statement **once on a test database**. The `DemoPerson`, `DemoProject`, and `DemoTag` labels separate sample data from application data. Running `CREATE` again will create duplicate nodes/relationships and invalidate the counts below.

```cypher
CREATE
  (an:DemoPerson {name: 'An', skills: ['Cypher', 'Java']}),
  (binh:DemoPerson {name: 'Bình', skills: ['Cypher']}),
  (chi:DemoPerson {name: 'Chi', skills: []}),
  (atlas:DemoProject {name: 'Atlas'}),
  (boreal:DemoProject {name: 'Boreal'}),
  (graph:DemoTag {name: 'Graph'}),
  (backend:DemoTag {name: 'Backend'}),
  (an)-[:WORKS_ON]->(atlas),
  (an)-[:WORKS_ON]->(boreal),
  (binh)-[:WORKS_ON]->(boreal),
  (atlas)-[:HAS_TAG]->(graph),
  (atlas)-[:HAS_TAG]->(backend),
  (boreal)-[:HAS_TAG]->(backend);
```

Sample structure:

```text
An ──WORKS_ON──► Atlas ──HAS_TAG──► Graph
 │                   └──HAS_TAG──► Backend
 └──WORKS_ON──► Boreal ─HAS_TAG──► Backend
 Bình ─WORKS_ON──► Boreal
 Chi  (not on any project; skills = [])

skills: An = [Cypher, Java], Bình = [Cypher], Chi = []
```

We have 3 people: An has 2 skills and 2 projects; Bình has 1 skill and 1 project; Chi has an empty skills list and no projects. Atlas has 2 tags, and Boreal has 1 tag.

## 3. Counting Rows Through Each Step of the Pipeline

Consider a query that unwinds skills, then joins people to projects and projects to tags:

```cypher
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, skill,
       project.name AS project, tag.name AS tag
ORDER BY person, skill, project, tag;
```

Tracing each stage:

| After Operation | An | Bình | Chi | Total Rows |
| --- | ---: | ---: | ---: | ---: |
| `MATCH (p:DemoPerson)` | 1 | 1 | 1 | **3** |
| `UNWIND p.skills AS skill` | 2 | 1 | 0 | **3** |
| `MATCH (p)-[:WORKS_ON]->(project)` | 2 × 2 = 4 | 1 × 1 = 1 | 0 | **5** |
| `MATCH (project)-[:HAS_TAG]->(tag)` | 2 × (2 + 1) = 6 | 1 × 1 = 1 | 0 | **7** |

The final result has 7 rows:

| person | skill | project | tag |
| --- | --- | --- | --- |
| An | Cypher | Atlas | Backend |
| An | Cypher | Atlas | Graph |
| An | Cypher | Boreal | Backend |
| An | Java | Atlas | Backend |
| An | Java | Atlas | Graph |
| An | Java | Boreal | Backend |
| Bình | Cypher | Boreal | Backend |

You can verify each checkpoint by **stopping the query at the point you want to measure** and using `count(*)`:

```cypher
// Checkpoint 1: 3 rows
MATCH (p:DemoPerson)
RETURN count(*) AS rows;

// Checkpoint 2: 3 rows (An: 2, Bình: 1, Chi: 0)
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
RETURN count(*) AS rows;

// Checkpoint 3: 5 rows
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
RETURN count(*) AS rows;

// Checkpoint 4: 7 rows
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN count(*) AS rows;
```

The expansion factor depends on **each data branch**. For the `UNWIND` → project → tag chain above, the row count is given by:

\[
N = \sum_{p \in P} |\operatorname{skills}(p)|
    \times \sum_{q \in \operatorname{projects}(p)} |\operatorname{tags}(q)|
\]

On the sample data: `N = 2 × (2 + 1) + 1 × 1 + 0 = 7`. This formula assumes each relationship in the example produces a single match; when data has parallel relationships, count **pattern matches**, not just distinct target nodes.

## 4. Understanding `UNWIND`, Empty Lists, and `null`

`UNWIND` expands **each element** of the list in every input row:

```cypher
UNWIND ['Cypher', 'Java'] AS skill
RETURN skill;
// 2 rows: Cypher, Java

UNWIND [] AS skill
RETURN skill;
// 0 rows

UNWIND [null] AS skill
RETURN skill;
// 1 row: skill = null
```

Because `Chi.skills = []`, Chi **disappears from the stream** immediately after `UNWIND p.skills`. An `OPTIONAL MATCH` placed *after* that step cannot recover the dropped row.

If business logic requires keeping people with no skills, replace empty or `null` lists with a single-`null` list **before unwinding**:

```cypher
MATCH (p:DemoPerson)
UNWIND CASE
  WHEN p.skills IS NULL OR size(p.skills) = 0 THEN [null]
  ELSE p.skills
END AS skill
RETURN p.name AS person, skill
ORDER BY person, skill;
```

The result has **4 rows**: 2 for An, 1 for Bình, and 1 for Chi (with `skill = null`). This approach works when you need to display a row for entities with no elements; if the goal is accurately counting skills, use `count(skill)` so the synthetic `null` row is not counted.

`coalesce(p.skills, [])` only replaces `null`; it does **not** preserve the row when the list is empty. Conversely, writing `coalesce(p.skills, [null])` does not handle `[]` either. Distinguish these two cases clearly.

Two consecutive `UNWIND` clauses can create a **Cartesian product** across lists in the same row:

```cypher
WITH ['An', 'Bình'] AS people, ['Graph', 'Backend', 'Java'] AS topics
UNWIND people AS person
UNWIND topics AS topic
RETURN person, topic;
// 2 × 3 = 6 rows, not 2 or 3 rows
```

If two lists represent positionally paired elements, do not `UNWIND` both independently; instead, unwind a list of indexes and access the corresponding elements.

## 5. Matching Multiple `MATCH` Patterns: Filtering, Row Multiplication, and Cartesian Products

A `MATCH` clause performs pattern matching based on existing variables. For each input row:

- Zero matches: the row is dropped.
- One match: emits one row.
- Multiple matches: emits multiple rows, even when rows share the same node in certain columns.

For example, omitting the skill step and joining just two relationship types:

```cypher
MATCH (p:DemoPerson)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, project.name AS project,
       tag.name AS tag
ORDER BY person, project, tag;
// 4 rows: An–Atlas–Graph, An–Atlas–Backend,
//         An–Boreal–Backend, Bình–Boreal–Backend
```

The two patterns **share the variable** `project`, so only tags belonging to the matched project are joined. Conversely, if two patterns are independent, Neo4j must evaluate every combination:

```cypher
MATCH (p:DemoPerson)
MATCH (tag:DemoTag)
RETURN count(*) AS rows;
// 3 people × 2 tags = 6 rows
```

This is a **Cartesian product** because there is no joining condition between `p` and `tag`. In large queries, combining independent patterns can cause row counts to explode. When an actual link is intended, write the connecting relationship pattern or join condition; when all combinations are genuinely desired, make the intent explicit and estimate cardinality.

### `OPTIONAL MATCH` Preserves Unmatched Rows, Yet Still Expands Matches

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
RETURN p.name AS person, project.name AS project
ORDER BY person, project;
```

This produces **4 rows**: An–Atlas, An–Boreal, Bình–Boreal, and Chi–`null`. For An, `OPTIONAL MATCH` still multiplies into 2 rows; for Chi, it keeps 1 row with `null`. If you chain another `OPTIONAL MATCH` for tags, Atlas's rows expand to 2 each, while Chi's row is kept with a `null` tag.

Watch predicate scope: `WHERE` attached directly to `OPTIONAL MATCH` is part of the optional match itself. A `WHERE` filter placed on a subsequent `WITH` can drop rows containing `null`, defeating the row-preserving effect of `OPTIONAL MATCH`:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
WITH p, project
WHERE project.name = 'Atlas'
RETURN p.name AS person;
// Only An remains; Chi and Bình are filtered out of the stream
```

## 6. Accurate Counting, Deduplication, and Grouping

First determine **what unit you are counting**: result rows, people, projects, tags, or relationships.

```cypher
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN
  count(*) AS resultRows,
  count(DISTINCT p) AS uniquePeople,
  count(DISTINCT project) AS uniqueProjects,
  count(DISTINCT tag) AS uniqueTags;
// resultRows = 7, uniquePeople = 2,
// uniqueProjects = 2, uniqueTags = 2
```

- `count(*)` counts all rows, including rows where some columns are `null`.
- `count(x)` counts only rows where `x` is non-`null`.
- `count(DISTINCT x)` counts distinct non-`null` values of `x`.
- `WITH DISTINCT p` collapses the stream to one row per person `p`, **but also discards the skill/project/tag combinations** unless they were retained or aggregated earlier.

If the goal is **one row per person** with lists of projects and tags, group before returning results:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
OPTIONAL MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
WITH p,
     collect(DISTINCT project.name) AS projects,
     collect(DISTINCT tag.name) AS tags
RETURN p.name AS person, p.skills AS skills, projects, tags
ORDER BY person;
```

The result has **3 rows**, one per person. An has projects `Atlas`, `Boreal` and tags `Graph`, `Backend`; Bình has `Boreal` and `Backend`; Chi has `projects = []` and `tags = []`. Element order inside lists from `collect()` is not guaranteed unless appropriate ordering is established before aggregating; compare as sets when testing this example. `null` values are excluded from lists by `collect()`.

When you only need each person's **project count**, do not multiply rows by tags:

```cypher
MATCH (p:DemoPerson)
OPTIONAL MATCH (p)-[:WORKS_ON]->(project:DemoProject)
WITH p, count(DISTINCT project) AS projectCount
RETURN p.name AS person, projectCount
ORDER BY person;
// An: 2, Bình: 1, Chi: 0
```

Here `count(DISTINCT project)` counts distinct project nodes. If you need to count **`WORKS_ON` relationships** (including multiple relationships pointing to the same project), bind a relationship variable and count that variable instead.

## 7. Reducing Row Multiplication When Only Checking Existence

Not every query needs to return every combination of nodes and relationships. If the requirement is simply "which people work on at least one project tagged Graph", use `EXISTS` to test the condition:

```cypher
MATCH (p:DemoPerson)
WHERE EXISTS {
  MATCH (p)-[:WORKS_ON]->(:DemoProject)-[:HAS_TAG]->(:DemoTag {name: 'Graph'})
}
RETURN p.name AS person;
// One row: An
```

This directly expresses the existence check and keeps one row per qualifying `p`, rather than expanding all projects and tags only to deduplicate with `DISTINCT`.

When multiple distinct result sets (such as lists of skills, projects, and tags) are needed for **a single root entity**, consider aggregating each branch before joining, or using subqueries with clear scoping. Expanding independent branches simultaneously before calling `collect()` can cause intermediate row counts to spike even when the final table has only a few rows.

## 8. Reading Cardinality in Execution Plans

`EXPLAIN` shows the plan and **estimated** row counts without running the query; `PROFILE` executes the query and shows **actual row counts** at each operator (along with cost metrics, depending on Neo4j version and UI). For a read-only example:

```cypher
PROFILE
MATCH (p:DemoPerson)
UNWIND p.skills AS skill
MATCH (p)-[:WORKS_ON]->(project:DemoProject)
MATCH (project)-[:HAS_TAG]->(tag:DemoTag)
RETURN p.name AS person, skill, project.name AS project, tag.name AS tag;
```

When reading the plan, pay attention to common operators such as `Unwind`, `Expand(All)`, `Filter`, `Aggregation`, `Distinct`, and their output **Rows**. A warning sign to investigate is Rows spiking after a relationship expansion or `UNWIND`, only to drop sharply at `Distinct`/`Aggregation`: the query may be generating many intermediate combinations unused in the final output.

**Do not infer from Cypher clause order that physical execution order is always identical.** The planner may reorder pattern traversals or push filters earlier. The 3 → 3 → 5 → 7 table above describes the logical semantics of query stages; to observe actual operators, inspect the execution plan in your running environment. Only run `PROFILE` directly on write queries when you genuinely intend to **execute the write operations**.

## 9. Real-World Scenario and Control Checklist

Suppose a learning recommendation system stores learners, interest topics, courses, and skill tags. The question "how many learners are interested in Graph?" is completely different from "how many learner–course–Graph-tag combinations exist?". The second query can return multiple rows for the same learner if they enrolled in multiple matching courses. If a Java Driver application maps one row to one learner DTO, the UI may display duplicate learners; if the system uses `count(*)` for learner pagination, page totals will also be semantically wrong.

Before finalizing a query containing `UNWIND` or multiple `MATCH` clauses, check:

1. **What is the output unit?** One row per person, one row per project, or one row per pattern combination?
2. **Can lists be empty/`null`?** Is it acceptable to drop rows during `UNWIND`?
3. **How many matches occur per branch?** Estimate per entity instead of multiplying a single average factor across the entire table.
4. **Do patterns share variables or join conditions?** Could an unintended Cartesian product occur?
5. **Must unmatched entities be retained?** Place `OPTIONAL MATCH` at the right spot and watch subsequent filters.
6. **Are you counting rows, non-`null` values, or distinct nodes/relationships?** Choose `count(*)`, `count(x)`, or `count(DISTINCT x)` accordingly.
7. **Do you only need an existence check or early aggregation?** Trim intermediate rows using `EXISTS`, aggregation, or separate query branches.
8. **Do observed row counts match expectations?** Count at each checkpoint with `RETURN count(*)`, then inspect `EXPLAIN`/`PROFILE` when optimizing.

**Key takeaway:** cardinality is a property of the **result stream**, not the node count in Neo4j. Understanding how `UNWIND`, `MATCH`, `OPTIONAL MATCH`, `DISTINCT`, and aggregation reshape the stream helps you write more accurate Cypher, especially when a graph model has interlocking one-to-many relationships.
