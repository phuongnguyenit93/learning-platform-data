# FOREACH and Conditional Update Options in Neo4j Cypher

## Objectives

When working with **Neo4j**, data is represented as a **property graph**: nodes carry labels and properties, and relationships have a direction, type, and properties. An update statement sometimes needs to run only when a node or relationship satisfies a business condition: flagging an overdue task, creating a link for a high-priority task, or writing a field only when valid input data is present.

After this lesson, you can:

- Understand the syntax, variable scope, and limitations of `FOREACH` in Cypher.
- Perform conditional updates using `FOREACH` combined with `CASE`.
- Choose appropriately among `WHERE` + `SET`, `CASE` inside expressions, `UNWIND`, `MERGE ... ON CREATE/ON MATCH`, `CALL` subqueries, and `WHEN` in Cypher 25.
- Avoid bugs related to `null` values, filtered records, repeated updates, and performance when working with graphs.

> **Version scope:** `FOREACH`, `CASE`, `WHERE`, `MERGE`, and `UNWIND` in the main examples work with Cypher 5 and Cypher 25. The conditional query syntax `WHEN ... THEN ... ELSE` is available only in **Cypher 25**, introduced in **Neo4j 2025.06**. When trying examples, use Neo4j Browser or a Cypher environment matching your chosen version.

## 1. Context: Does the Condition Apply to Rows or to Properties?

Consider a project management graph:

```text
(:Project {code: "P-01"})
     │
     ├──[:HAS_TASK]──> (:Task {id: "T-101", status: "OPEN", priority: 9})
     ├──[:HAS_TASK]──> (:Task {id: "T-102", status: "OPEN", priority: 3})
     └──[:HAS_TASK]──> (:Task {id: "T-103", status: "DONE", priority: 8})
```

Three different requirements lead to three different styles:

1. **Modify only qualifying nodes:** filter with `WHERE`, then `SET`.
2. **Compute new values across multiple branches:** use `CASE` on the right-hand side of `SET`.
3. **Run a group of write clauses or create relationships when a condition holds:** use `FOREACH` with a conditional list, or a conditional subquery on supported versions.

`FOREACH` is primarily meant for iterating over a **list** to **write data**. The `FOREACH + CASE` pattern leverages a single-element list to execute once and an empty list to skip; therefore it is sometimes referred to as a way to simulate `IF` in Cypher 5.

## 2. Preparing Practice Data

Run the two constraint creation statements on a **test database**:

```cypher
CREATE CONSTRAINT project_code_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.code IS UNIQUE;
```

```cypher
CREATE CONSTRAINT task_id_unique IF NOT EXISTS
FOR (t:Task) REQUIRE t.id IS UNIQUE;
```

Then create one project and three tasks:

```cypher
MERGE (p:Project {code: 'P-01'})
WITH p
UNWIND [
  {id: 'T-101', status: 'OPEN', priority: 9, dueDate: date('2025-10-01')},
  {id: 'T-102', status: 'OPEN', priority: 3, dueDate: date('2030-01-01')},
  {id: 'T-103', status: 'DONE', priority: 8, dueDate: date('2025-09-01')}
] AS data
MERGE (t:Task {id: data.id})
SET t.status = data.status,
    t.priority = data.priority,
    t.dueDate = data.dueDate
MERGE (p)-[:HAS_TASK]->(t);
```

In this example, `T-101` is open, high priority, and overdue; `T-102` is open but not yet due; `T-103` is completed. Re-running the initialization statement resets `status`, `priority`, and `dueDate` on the three tasks; properties or relationships added during the exercises will not be removed automatically. If you want to compare each example's output independently, use a clean test database.

Inspect the data:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
RETURN p.code AS projectCode, t.id AS taskId,
       t.status AS status, t.priority AS priority, t.dueDate AS dueDate
ORDER BY taskId;
```

## 3. Syntax and Semantics of FOREACH

General form:

```cypher
FOREACH (item IN listExpression |
  SET item.someProperty = 'value'
)
```

- `listExpression` must evaluate to a list; the body executes **once per element** in the list.
- The body only accepts update clauses such as `SET`, `REMOVE`, `CREATE`, `MERGE`, `DELETE`, or nested `FOREACH`. Do not place `MATCH`, `OPTIONAL MATCH`, `WITH`, or `RETURN` inside the parentheses of `FOREACH`.
- The loop variable and any new variables created **inside** `FOREACH` have local scope. Variables declared **before** `FOREACH` can still be referenced inside the body, while internal variables are not exposed outside.
- `FOREACH` does not produce a result stream of rows like `UNWIND`. When you need to keep reading, filtering, or matching patterns for each element, use `UNWIND`.

Example: mark all tasks belonging to a project after collecting them into a list.

```cypher
MATCH (:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
WITH collect(DISTINCT t) AS tasks
FOREACH (task IN tasks |
  SET task.checkedByBatch = true
);
```

`collect(DISTINCT t)` prevents adding the same node to the list multiple times when a match pattern returns duplicate rows. On large graphs, avoid collecting all nodes into a massive list just to update them; process row-by-row with `MATCH ... WHERE ... SET`.

`FOREACH` is also useful with nodes or relationships along a path:

```cypher
MATCH p = (project:Project {code: 'P-01'})-[:HAS_TASK]->(:Task)
FOREACH (r IN relationships(p) |
  SET r.inspected = true
);
```

Here `relationships(p)` returns the list of relationships on each matched path.

## 4. FOREACH + CASE: Write Only When a Condition Holds

`CASE` is a **value-selecting expression**, not a control-flow statement block. To control execution of the `FOREACH` body, make `CASE` return a list:

```cypher
MATCH (t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN' AND t.dueDate < date() THEN [1]
  ELSE []
END |
  SET t.isOverdue = true,
      t.needsReview = true
)
RETURN t.id AS taskId, t.isOverdue AS isOverdue
ORDER BY taskId;
```

| Condition Value | List from `CASE` | Body Execution Count |
| --- | --- | --- |
| `true` | `[1]` | 1 |
| `false` | `[]` | 0 |
| `null` | `[]`, via the `ELSE` branch | 0 |

The variable `_` merely serves as a dummy placeholder element and is not used in `SET`. On the sample data, `T-101` is flagged; `T-102` is not yet overdue and `T-103` is completed, so both are skipped.

**Important distinction:** the `ELSE []` branch means **do not update**, not "set the property to `false` or delete the previous property." If a task's condition changes later, the old flag may remain. To synchronize true/false flags on every run, use `SET + CASE` in Section 5.2.

### Multiple Write Operations in the Same Branch

One advantage of `FOREACH + CASE` is grouping write operations that are allowed to run only when the condition is met. For example, creating an escalation link for high-priority tasks:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN [1]
  ELSE []
END |
  SET t.escalationLevel = 2
  MERGE (p)-[:ESCALATES]->(t)
);
```

On the sample data, only `T-101` receives the escalation level and the `ESCALATES` relationship. `MERGE` can reuse an existing relationship pattern, reducing duplicate risk on re-runs; `CREATE` creates a new relationship on every execution.

If you need an extra `MATCH` to find another node, perform it **before** `FOREACH`, or choose `UNWIND`/subquery. Example with an assignee node that might not exist:

```cypher
MATCH (t:Task {id: 'T-101'})
OPTIONAL MATCH (u:User {id: 'U-01'})
FOREACH (_ IN CASE
  WHEN u IS NOT NULL AND t.status = 'OPEN' THEN [1]
  ELSE []
END |
  MERGE (u)-[:ASSIGNED_TO]->(t)
);
```

If `U-01` does not exist, `OPTIONAL MATCH` binds `u` to `null` and the empty list prevents `MERGE` from running. Checking node existence is essential before using it in a write pattern.

## 5. Conditional Update Alternatives

### 5.1. WHERE + SET: Filter Nodes Before Writing

When you only need to update nodes satisfying a condition, this is usually the most direct approach:

```cypher
MATCH (t:Task)
WHERE t.status = 'OPEN' AND t.priority >= 8
SET t.reviewRequired = true
RETURN count(t) AS updatedTasks;
```

`WHERE` filters out rows that fail the condition **before the write step**. Unlike `CASE` on the right-hand side of `SET`, filtered-out nodes do not pass through the rest of the query. In this example, `updatedTasks` is the number of rows remaining after filtering; if `MATCH` produces multiple rows for the same node, watch out for duplicates or use `WITH DISTINCT t`.

### 5.2. SET + CASE: Compute the Value to Store

When you want **every node to have its state recomputed**, a `CASE` expression suffices:

```cypher
MATCH (t:Task)
SET t.isOverdue =
  CASE
    WHEN t.status = 'OPEN' AND t.dueDate < date() THEN true
    ELSE false
  END
RETURN t.id AS taskId, t.isOverdue AS isOverdue
ORDER BY taskId;
```

Here `T-101` receives `true`, while `T-102` and `T-103` receive `false`. Thanks to the `ELSE` branch, stale flags are refreshed according to current state.

`CASE` also supports multiple ordered branches:

```cypher
MATCH (t:Task)
SET t.queue = CASE
  WHEN t.status = 'DONE' THEN 'ARCHIVE'
  WHEN t.priority IS NULL THEN 'UNCLASSIFIED'
  WHEN t.priority >= 8 THEN 'URGENT'
  ELSE 'NORMAL'
END;
```

The first branch evaluating to `true` is selected. `CASE` only **computes a value** for `t.queue`; it cannot directly run `CREATE`, `MERGE`, or a sequence of write clauses.

### 5.3. SET += CASE: Conditionally Update a Group of Properties

When a condition holds, you can merge a map into a node; otherwise, merge an empty map:

```cypher
MATCH (t:Task)
SET t += CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8
    THEN {reviewRequired: true, route: 'URGENT'}
  ELSE {}
END;
```

`SET t += map` only adds/overwrites properties named in the map, preserving all other properties. `SET t = map` means **replace the entire property set** of the node, so never substitute it unintentionally. This is a concise option for multiple properties, though it still cannot create or delete relationships.

In Neo4j, setting a property to `null` **deletes that property**. For example:

```cypher
MATCH (t:Task)
SET t.reviewReason = CASE
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN 'HIGH_PRIORITY'
  ELSE null
END;
```

Choose `ELSE false` if business logic requires storing a boolean flag, or `ELSE null` if the property should not exist when the condition is false.

### 5.4. MERGE with ON CREATE / ON MATCH: Distinguishing Newly Created vs. Existing

`MERGE` finds or creates a pattern. Its two accompanying branches depend solely on whether **that pattern was just created or was found**:

```cypher
MERGE (t:Task {id: 'T-104'})
ON CREATE SET t.status = 'OPEN',
              t.createdAt = datetime()
ON MATCH SET t.lastSeenAt = datetime()
RETURN t.id AS taskId, t.status AS status,
       t.createdAt AS createdAt, t.lastSeenAt AS lastSeenAt;
```

On the first run, `T-104` is created and `ON CREATE` executes; on subsequent runs, the pattern is found and `ON MATCH` executes. This is **not** an `IF t.priority >= 8` mechanism: to filter by business conditions, you still need `WHERE`, `CASE`, `FOREACH`, or conditional queries. A unique constraint on `Task.id` protects the business key under concurrent writes.

### 5.5. UNWIND + WHERE: Working with Lists While Still Needing MATCH

`UNWIND` turns each list element into a query row. Afterward, you can use `WITH`, `WHERE`, `MATCH`, and `SET` as usual:

```cypher
UNWIND [
  {id: 'T-101', rating: 3},
  {id: 'T-102', rating: null},
  {id: 'T-999', rating: 2}
] AS data
WITH data
WHERE data.rating IS NOT NULL
MATCH (t:Task {id: data.id})
SET t.importRating = data.rating
RETURN count(t) AS updatedTasks;
```

As a result, only `T-101` receives `importRating`: `T-102` is filtered out because of `null`, and `T-999` finds no matching node. In real ingestion from the Java Driver, the list can be passed as a parameter instead of being hardcoded in Cypher.

When using `WHERE` after `UNWIND`, place `WHERE` after an appropriate `WITH` (as shown); do not write `UNWIND ... AS data WHERE ...` as if `UNWIND` directly supports `WHERE`.

### 5.6. CALL and WHEN: Conditional Query Branches in Cypher 25

Starting with **Neo4j 2025.06**, **Cypher 25** adds `WHEN ... THEN ... ELSE` to execute **conditional query branches**, including branches with write operations. Example:

```cypher
CYPHER 25
MATCH (t:Task)
CALL (t) {
  WHEN t.status = 'OPEN' AND t.priority >= 8 THEN {
    SET t.reviewRequired = true
    RETURN 'updated' AS action
  }
  ELSE {
    RETURN 'skipped' AS action
  }
}
RETURN t.id AS taskId, action
ORDER BY taskId;
```

`CALL (t)` imports variable `t` from the outer query into the subquery. Both branches return a column named `action` so the result structure is uniform. With the three initially created tasks, `T-101` reports `updated`, `T-102` and `T-103` report `skipped`; `T-104` also reports `skipped` if you ran Section 5.4's example.

Note three points when using `WHEN`:

- You must select **Cypher 25** on a supported Neo4j version. Do not use this syntax on older Neo4j 5 releases or queries running in Cypher 5 mode.
- In a query with an outer `MATCH`, `WHEN` must sit inside an appropriate subquery such as `CALL (t) { ... }`; you cannot write `MATCH ... WHEN ...` directly like an ordinary clause.
- If a subquery has branches returning rows without an `ELSE`, rows matching no branch may drop out of the outer result. Explicitly include `ELSE` when you want to retain an output row for every input row.

For problems that need to `MATCH` additional patterns inside a condition, `CALL` subqueries are more flexible than `FOREACH` because `FOREACH` only allows write commands in its body. When separate execution branches are needed on Cypher 25 systems, `WHEN` is generally more readable than the `[1]`/`[]` list trick.

## 6. Choosing the Right Approach for Your Needs

| Scenario | Suitable Choice | Reason |
| --- | --- | --- |
| Modify only nodes meeting a condition | `MATCH ... WHERE ... SET` | Concise, clear, and filters rows before writing |
| Each node needs a different computed value | `SET property = CASE ... END` | Recomputes values for both true and false branches |
| Update multiple properties, keep other fields | `SET n += CASE ... END` | Conditional map merge |
| Loop updates over existing nodes/relationships in a list or path | `FOREACH` | Executes write operations per element |
| Run multiple write operations only when a condition holds in Cypher 5 | `FOREACH + CASE` | Single-element or empty list controls write execution count |
| Need to look up additional nodes per list element | `UNWIND` with `MATCH`/`WHERE` | Supports both read and write clauses |
| Distinguish whether a pattern was newly created or already existed | `MERGE ... ON CREATE/ON MATCH` | Condition depends on `MERGE` outcome |
| Multiple query branches with different reads and writes in Cypher 25 | `CALL (...) { WHEN ... THEN ... ELSE ... }` | Expresses conditional branches cleanly |

## 7. Common Errors and How to Avoid Them

**Error 1 — Placing MATCH inside FOREACH.**

```cypher
// WRONG: MATCH cannot be used inside FOREACH.
WITH ['T-101', 'T-102'] AS ids
FOREACH (id IN ids |
  MATCH (t:Task {id: id})
  SET t.checked = true
);
```

Fix using `UNWIND`:

```cypher
UNWIND ['T-101', 'T-102'] AS id
MATCH (t:Task {id: id})
SET t.checked = true;
```

**Error 2 — Assuming ELSE [] undoes previous updates.** It merely skips the current run. To keep `true`/`false` synchronized, use `SET ... = CASE ... ELSE false END`; to remove a property when the condition fails, use `ELSE null` on the relevant property.

**Error 3 — Ignoring null.** In Cypher, an expression like `t.priority >= 8` evaluates to `null` when `priority` is missing. `CASE WHEN` selects a branch only when the condition evaluates to `true`. Use `IS NULL`/`IS NOT NULL`, `coalesce(...)`, or an `ELSE` branch to specify behavior explicitly.

**Error 4 — Using CREATE in repeatable jobs.** `CREATE (p)-[:ESCALATES]->(t)` can generate another relationship of the same type between the same pair of nodes on every run. `MERGE` is usually more appropriate when only one instance of that relationship pattern should exist; consider business-key constraints on nodes created via `MERGE`.

**Error 5 — Forgetting input row multiplicity.** If a `MATCH` produces three rows for the same node, a `FOREACH` body can also run three times on that node. Check row counts, use `WITH DISTINCT`, or refine the match pattern before updating.

**Error 6 — Variables inside FOREACH lose scope.** For example, `FOREACH (id IN ids | CREATE (newTask:Task {id: id}))` does not allow `RETURN newTask` after `FOREACH`. If you need to return newly created nodes, use `UNWIND ids AS id CREATE (newTask:Task {id: id}) RETURN newTask`.

## 8. Correctness, Performance, and Operations

- **Lookup keys:** use stable identifying properties (`Task.id`, `Project.code`), unique constraints, and suitable indexes. With `MATCH (t:Task {id: $taskId})`, the query can leverage the index backed by the unique constraint.
- **Safe re-runs:** prefer `MERGE` when duplicates must be avoided; for `SET`, clearly separate operations that reset state from those that only mark once. Properties like `lastModifiedAt = datetime()` can change on each run.
- **Input data:** pass parameters from the Java Driver/Spring Data Neo4j (e.g., `$taskId`, `$minPriority`), never concatenating user input directly into Cypher strings. Example:

  ```cypher
  MATCH (t:Task {id: $taskId})
  WHERE t.status = 'OPEN' AND t.priority >= $minPriority
  SET t.reviewRequired = true
  RETURN t.id AS taskId;
  ```

- **Large datasets:** avoid `collect(...)` on huge numbers of nodes just to pass into `FOREACH`. Process row-by-row with `MATCH/WHERE/SET` or `UNWIND`; when importing very large volumes, consider `CALL { ... } IN TRANSACTIONS` with an appropriate batch size and note its autonomous transaction behavior.
- **Inspecting plans:** use `EXPLAIN` to inspect the plan without executing updates, or `PROFILE` when executing writes on test data is acceptable. Check index usage and actual row counts.
- **Concurrent writes:** `MERGE` with unique constraints prevents duplicate nodes with the same key, but concurrent updates to the same node still require transaction design and application-level retry handling if conflicts occur.

## 9. Integrated Practice Exercise

**Requirement:** For `Task` nodes belonging to `P-01`, if the task is open, has priority 8 or higher, and is overdue, set `requiresEscalation = true` and create a `(:Project)-[:ESCALATES]->(:Task)` relationship. Re-running must not create duplicate relationships.

A solution using `FOREACH + CASE`, compatible with Cypher 5 or Cypher 25:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
FOREACH (_ IN CASE
  WHEN t.status = 'OPEN'
   AND t.priority >= 8
   AND t.dueDate IS NOT NULL
   AND t.dueDate < date()
  THEN [1]
  ELSE []
END |
  SET t.requiresEscalation = true
  MERGE (p)-[:ESCALATES]->(t)
);
```

Verify status and relationships:

```cypher
MATCH (p:Project {code: 'P-01'})-[:HAS_TASK]->(t:Task)
OPTIONAL MATCH (p)-[e:ESCALATES]->(t)
RETURN t.id AS taskId,
       t.status AS status,
       t.requiresEscalation AS requiresEscalation,
       count(e) AS escalationRelationships
ORDER BY taskId;
```

Starting from clean sample data, only `T-101` has `requiresEscalation = true` and one `ESCALATES` relationship. Try running the update query a second time: `count(e)` for `T-101` remains 1. If you already ran Section 4 earlier, the verification result still holds because `MERGE` reuses the existing relationship. If you want to **remove** the relationship when the condition no longer holds, design an additional conditional delete statement; the current `ELSE []` branch does not automatically remove relationships.

## 10. Takeaways

`FOREACH` is an iteration clause intended for **writing data over a list**. Combining `CASE WHEN ... THEN [1] ELSE [] END` lets you choose whether or not to run a group of write operations, though it cannot replace `MATCH` inside the body and does not automatically undo prior updates. In most cases of updating a property or filtering nodes, `WHERE + SET` or `SET + CASE` is simpler. For complex conditional queries on modern Neo4j, you can use `WHEN` in **Cypher 25**.

### References

- [Neo4j Cypher Manual — FOREACH](https://neo4j.com/docs/cypher-manual/current/clauses/foreach/)
- [Neo4j Cypher Manual — SET](https://neo4j.com/docs/cypher-manual/current/clauses/set/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — Conditional queries (WHEN)](https://neo4j.com/docs/cypher-manual/current/queries/composed-queries/conditional-queries/)
- [Neo4j Cypher Manual — Select Cypher version](https://neo4j.com/docs/cypher-manual/current/queries/select-version/)
