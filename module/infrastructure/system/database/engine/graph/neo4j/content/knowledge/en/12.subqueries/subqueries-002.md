# EXISTS for Checking Existence of Patterns or Subquery Results

> **Chapter:** Subqueries  
> **DBMS:** Neo4j — property graph, queried using Cypher.  
> **Objective:** Learn how to use `EXISTS { ... }` to check whether at least one relationship pattern or result row satisfies a condition, use `NOT EXISTS { ... }` to find non-matching cases, and avoid multiplying data rows when only a true/false answer is needed.

## 1. The Problem: Asking "Does It Exist?" on a Graph

In a property graph, each **node** represents an entity, and each **relationship** represents a link and can carry properties. Very common questions include:

- Does a user **follow anyone**?
- Does a person **follow an active user**?
- Does a **two-hop path** exist from person A to person B?
- Is there someone A follows whom A has **not blocked**?
- Does a node have **any relationship** satisfying a time or property condition?

If you only need to know whether **at least one match exists**, without retrieving all nodes/relationships matching the pattern, use an **existential subquery**:

```cypher
MATCH (u:User)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:User)
}
RETURN u;
```

`EXISTS { ... }` is a **Boolean expression** in Cypher:

- Returns `true` if the subquery produces **at least one row** satisfying the condition.
- Returns `false` if the subquery produces **0 rows**.
- Can be placed in `WHERE`, `RETURN` expressions, `CASE`, and combined with `AND`, `OR`, and `NOT`.
- **Does not return nodes/relationships** from the subquery to the outer query, and **does not multiply outer rows** by the number of matching patterns.

The core condition is **whether any result row exists**; not whether the column values in that row are `true`, `false`, or `null`.

## 2. Sample Dataset to Follow Along

The examples below model a small social network. Each `:ExistsDemoUser` node has `id`, `name`, and `active`. The `:FOLLOWS` relationship has a `since` property representing the year following began; `:BLOCKS` represents blocking.

```text
                    FOLLOWS (2022)
          An --------------------------> Bình
          |                                |
          | FOLLOWS (2020)                 | FOLLOWS (2024)
          v                                v
         Chi <-----------------------------+
          |
          | FOLLOWS (2023)
          +-----------------------------> An

          An --BLOCKS-------------------> Chi

         Dũng  (no FOLLOWS)
```

`active` status: **An = true**, **Bình = true**, **Chi = false**, **Dũng = true**.

Run the following snippet **once** on a test database. Each node uses a distinct `id`; `MERGE` ensures that re-running the example snippet will not unintentionally create an identical duplicate relationship between the same two nodes if the initial graph is clean.

```cypher
MERGE (an:ExistsDemoUser {id: 'an'})
SET an.name = 'An', an.active = true
MERGE (binh:ExistsDemoUser {id: 'binh'})
SET binh.name = 'Bình', binh.active = true
MERGE (chi:ExistsDemoUser {id: 'chi'})
SET chi.name = 'Chi', chi.active = false
MERGE (dung:ExistsDemoUser {id: 'dung'})
SET dung.name = 'Dũng', dung.active = true
WITH an, binh, chi
MERGE (an)-[ab:FOLLOWS]->(binh)
SET ab.since = 2022
MERGE (an)-[ac:FOLLOWS]->(chi)
SET ac.since = 2020
MERGE (binh)-[bc:FOLLOWS]->(chi)
SET bc.since = 2024
MERGE (chi)-[ca:FOLLOWS]->(an)
SET ca.since = 2023
MERGE (an)-[:BLOCKS]->(chi);
```

Throughout this lesson, the illustrated results assume the test database contains only **the four nodes and relationships above** with the specified labels/types. If your dataset has additional nodes or links of the same kind, the result set may differ.

## 3. Using `EXISTS { MATCH ... }` to Check Relationship Patterns

### 3.1. Finding People with at Least One Outgoing Relationship

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Bình |
| Chi |

For `An`, the subquery finds **two** following relationships, yet `EXISTS` returns only a single Boolean value so the outer query still has **one row for An**. `Dũng` has no outgoing `FOLLOWS` relationship and is therefore filtered out.

You can write the **short pattern form** without declaring `MATCH` for simple cases:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

The two examples express the same question. When you want to add conditions on nodes, relationships, or multi-hop pattern matching, the form with `MATCH` and `WHERE` is usually easier to extend.

### 3.2. How Does `EXISTS` Work Row by Row?

`MATCH (u:ExistsDemoUser)` produces four input rows corresponding to the four people. For **each row**, `EXISTS` attempts to find a pattern bound to that row's `u`.

| Outer value of `u` | Matching `FOLLOWS` patterns inside | Value of `EXISTS` | Outer row kept when using `WHERE`? |
|---|---:|---|---|
| An | 2 | `true` | Yes |
| Bình | 1 | `true` | Yes |
| Chi | 1 | `true` | Yes |
| Dũng | 0 | `false` | No |

This is a **correlated subquery**: the subquery depends on the variable `u` defined in the outer query. Although the condition is evaluated logically per row, physical execution is decided by Neo4j's query planner; you should not interpret the table above as a guarantee that Neo4j must always scan every pattern sequentially.

## 4. Filtering by Node and Relationship Properties

### 4.1. Following Someone Who Is Active?

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Chi |

Explanation:

- `An` follows `Bình`, and `Bình.active = true`.
- `Chi` follows `An`, and `An.active = true`.
- `Bình` only follows `Chi`, who is inactive.
- `Dũng` follows no one.

The condition `WHERE v.active = true` is placed **inside** `EXISTS` because it checks a property of the newly matched node `v`. Variable `v` exists only within the subquery.

### 4.2. Combining Conditions on Relationships and Nodes

Find people who have a following relationship starting **from 2023 onward**, where the followed person is active:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= 2023
    AND v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

The result contains only **Chi**, because the relationship `Chi -[:FOLLOWS {since: 2023}]-> An` matches both conditions. The relationship `Bình -> Chi` has year 2024, but `Chi.active = false`.

In a Java Driver or Spring Data Neo4j application, pass the year threshold as a parameter instead of concatenating query strings:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= $minYear
    AND v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

With `minYear = 2023`, the result matches the previous example. Parameters enable query reuse and avoid concatenating user data directly into Cypher syntax.

## 5. `NOT EXISTS`: Checking Pattern Non-Existence

To find **people who do not follow anyone**, negate the `EXISTS` expression:

```cypher
MATCH (u:ExistsDemoUser)
WHERE NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
RETURN u.name AS person
ORDER BY person;
```

The result contains only **Dũng**.

Distinguish between two easily confused questions:

| Condition | Meaning | Result in sample data |
|---|---|---|
| `NOT EXISTS { MATCH (u)-[:FOLLOWS]->(v) }` | This person follows no one. | Dũng |
| `NOT EXISTS { MATCH (u)-[:FOLLOWS]->(v) WHERE v.active = true }` | This person follows no **active** user. They may still follow inactive users. | Bình, Dũng |

Query for the second condition:

```cypher
MATCH (u:ExistsDemoUser)
WHERE NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

**Bình** has a `FOLLOWS` relationship, but has **no** `FOLLOWS` relationship leading to an active user. Therefore, Bình satisfies the second question but not the first.

This is the exact negation phrasing for problems such as "customers with no successful orders", "servers missing a patch", "accounts without an authentication link", or "nodes not connected to a banned group".

## 6. Checking Complex Subquery Results: Multi-Hop and Nested `EXISTS`

### 6.1. Is There a Two-Hop Path to a Specific Node?

Find people who can reach node `Chi` via **exactly two** `FOLLOWS` relationships:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(middle:ExistsDemoUser)
        -[:FOLLOWS]->(destination:ExistsDemoUser {id: 'chi'})
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Chi |

- `An -> Bình -> Chi`: two-hop path exists.
- `Chi -> An -> Chi`: two-hop path exists.
- `Bình -> Chi -> An`: does not reach `Chi` after two hops.
- `Dũng`: no path exists.

Here, `EXISTS` checks for **the existence of a two-hop MATCH result**, without returning that path outside. If you need to return the list of paths or intermediate nodes, use a regular `MATCH` or an appropriate `CALL` subquery.

### 6.2. Checking "Follows Someone Whom They Have Not Blocked"

This is a case where **nested** `EXISTS` expresses two conditions related to **the same node `v`**:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE NOT EXISTS {
    MATCH (u)-[:BLOCKS]->(v)
  }
}
RETURN u.name AS person
ORDER BY person;
```

| person |
|---|
| An |
| Bình |
| Chi |

`An` follows both `Bình` and `Chi` while blocking `Chi`; the relationship `An -> Bình` still makes the condition true. `Bình` follows `Chi` without blocking; `Chi` follows `An` without blocking. `Dũng` follows no one.

**Crucial point:** in the innermost subquery, variable `v` is already bound by the `MATCH` directly above it, so the block check applies to **the exact person being evaluated**. Two separate existence checks would answer a different question:

```cypher
// DIFFERENT MEANING: follows someone AND blocks nobody at all.
// Does not guarantee the followed person is the one checked for blocking.
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
AND NOT EXISTS {
  MATCH (u)-[:BLOCKS]->(:ExistsDemoUser)
}
RETURN u.name AS person;
```

The second example **excludes An completely**, because An blocks Chi, even though An still follows Bình without blocking Bình. Whenever a problem statement includes phrases like "the same person", "the same order", or "the same target node", you must share the variable within the proper scope.

### 6.3. `AND` / `OR` with Multiple Existence Conditions

Find people who **both** follow someone **and** block someone:

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
}
AND EXISTS {
  MATCH (u)-[:BLOCKS]->(:ExistsDemoUser)
}
RETURN u.name AS person;
```

The result is **An**. The two `EXISTS` clauses check two independent conditions that are both correlated with the outer row's `u`. If you need "or", you can replace `AND` with `OR`, adding parentheses to clarify evaluation order.

## 7. Variable Scope: How Does It Differ from a `CALL` Subquery?

For **`EXISTS { ... }`**, variables currently in the outer scope are **automatically available** inside the subquery. Typically **no importing `WITH`** or `CALL (u)` variable scope clause is needed.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person;
```

Here:

- `u` is bound by the outer `MATCH` and used inside.
- `v` is bound by the inner `MATCH` and usable only inside.
- `EXISTS` provides **true/false** to the outer expression; **it does not export variable `v`**.

**Invalid** example due to variable scope:

```cypher
// INVALID: v is created inside EXISTS, so it is not in scope for the outer RETURN.
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
}
RETURN u.name, v.name;
```

If you need both `u.name` and `v.name`, use `MATCH` directly:

```cypher
MATCH (u:ExistsDemoUser)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS source, v.name AS target
ORDER BY source, target;
```

Or use a `CALL` subquery to return the desired columns. On Neo4j 5.23+, `CALL (u) { ... RETURN ... }` declares imported variables explicitly; **do not apply `CALL`'s variable-importing rules to `EXISTS`**.

| Characteristic | `EXISTS { ... }` | `CALL (u) { ... }` (Neo4j 5.23+) |
|---|---|---|
| Purpose | Check if at least one matching row exists. | Run a subquery to return results or perform writes. |
| Result | Boolean `true`/`false`. | Returns columns/rows from `RETURN` or performs writes. |
| Outer variables | Automatically sees variables in scope. | Only receives variables specified in `(...)`, or `*`. |
| New inner variables | Not exported outside. | Can be exported via `RETURN`. |
| Outer row count | The expression itself does not multiply rows. | A returning subquery can produce 0, 1, or many rows per outer row. |
| Data writes | Not used for `CREATE`/`MERGE`/`SET`/`DELETE`. | Unit subqueries can write data. |

## 8. Using `EXISTS` in `RETURN` and `CASE`

It is not mandatory to place `EXISTS` inside `WHERE`. You can **return the Boolean value as a column** for the application to process further:

```cypher
MATCH (u:ExistsDemoUser)
RETURN
  u.name AS person,
  EXISTS {
    MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
  } AS hasFollowing
ORDER BY person;
```

| person | hasFollowing |
|---|---|
| An | `true` |
| Bình | `true` |
| Chi | `true` |
| Dũng | `false` |

Compared to the `WHERE EXISTS` example above, `RETURN EXISTS` **keeps all four people** and adds a status column. This approach fits display flags in APIs, such as `hasFollowing`, `hasPermission`, or `hasUnresolvedIssue`.

It can be combined with `CASE`:

```cypher
MATCH (u:ExistsDemoUser)
RETURN u.name AS person,
       CASE
         WHEN EXISTS {
           MATCH (u)-[:FOLLOWS]->(:ExistsDemoUser)
         }
         THEN 'Following'
         ELSE 'Not following'
       END AS followingStatus
ORDER BY person;
```

In Java or Spring Data Neo4j applications, prefer having Cypher return a Boolean value when mapping to `boolean`/`Boolean`; use a status string when that is an explicit display requirement.

## 9. Comparing `EXISTS`, `MATCH`, `OPTIONAL MATCH`, `COUNT`, and `IS NOT NULL`

### 9.1. Only Need to Know If a Pattern Exists? `EXISTS` Avoids Row Multiplication

```cypher
MATCH (u:ExistsDemoUser)
MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS person
ORDER BY person;
```

The result is **An, An, Bình, Chi**. `An` appears twice because there are two `FOLLOWS` relationships. If you only want people **who** follow someone, replacing the second `MATCH` with `WHERE EXISTS` produces **An, Bình, Chi**, one row per person.

You can use `DISTINCT` after `MATCH` to remove duplicates, but when you do not need any data from node `v`, `EXISTS` usually expresses the intent more accurately. Neo4j can leverage specialized query plans that check existence without materializing all matching results; actual speed should still be measured with `PROFILE`.

### 9.2. When Do You Need `COUNT`?

`COUNT` is appropriate for answering **how many**, whereas `EXISTS` answers **yes or no**.

```cypher
MATCH (u:ExistsDemoUser)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
RETURN u.name AS person, count(v) AS followingCount
ORDER BY person;
```

| person | followingCount |
|---|---:|
| An | 2 |
| Bình | 1 |
| Chi | 1 |
| Dũng | 0 |

If you need **both the relationship count** and a **has-relationship flag**, you can compute the count once and derive `followingCount > 0`. If you only need the yes/no flag, `EXISTS` is clearer.

Modern Cypher also offers the **`COUNT { MATCH ... }`** subquery expression to count correlated results; however, **you should not replace `EXISTS` with `COUNT { ... } > 0` just because both express existence**, unless you actually need the count or have a specific benchmark reason.

### 9.3. Is `EXISTS { ... }` the Same as Checking If a Property Exists?

Not quite. There are two distinct questions:

1. **Does a relationship pattern / query result exist?** → `EXISTS { MATCH ... }`.
2. **Does a node/relationship property have a non-`null` value?** → `IS NOT NULL`.

Example checking a relationship property:

```cypher
MATCH (u:ExistsDemoUser)-[r:FOLLOWS]->(:ExistsDemoUser)
WHERE r.since IS NOT NULL
RETURN u.name AS person, r.since AS since
ORDER BY person, since;
```

The `exists(n.property)` function syntax appeared in older Neo4j documentation; in modern Cypher, the recommended way to check properties is `n.property IS NOT NULL`. Meanwhile, `EXISTS { ... }` is a subquery expression used to verify **whether result rows exist**.

### 9.4. `OPTIONAL MATCH` vs. `NOT EXISTS`

`OPTIONAL MATCH` preserves the outer row even when there is no match and fills unmatched pattern variables with `null`. It is suitable for fetching **optional data**, though it can generate multiple rows when multiple relationships match. `NOT EXISTS` checks negation and **introduces no new variables**.

If you need a list of people who follow no one, `WHERE NOT EXISTS` is concise and exact. If you need the name of the followed person or `null` when none exists, `OPTIONAL MATCH` is more appropriate.

## 10. Performance and Reading Query Plans

On large graph datasets, the cost of an existence check depends on the number of candidate nodes, pattern selectivity, and filter properties.

**Example:**

```cypher
EXPLAIN
MATCH (u:ExistsDemoUser {id: 'an'})
WHERE EXISTS {
  MATCH (u)-[r:FOLLOWS]->(v:ExistsDemoUser)
  WHERE r.since >= 2023
    AND v.active = true
}
RETURN u.name AS person;
```

`EXPLAIN` shows the plan **without executing** the query. Once you understand the command's impact, you can switch to `PROFILE` to collect actual row counts and database hits.

Practical guidelines:

1. **Narrow down input nodes first.** For example, filter `u.id = $id` before checking relationships. For frequent lookups by `id`, consider an appropriate constraint/index.
2. **Attach conditions to the inner pattern.** For example, `r.since >= $minYear` and `v.active = true` precisely specify the target pattern.
3. **Do not use `MATCH` + `DISTINCT` or `COUNT` just to derive a Boolean flag if `EXISTS` already matches the semantics.** Generating/aggregating many rows can be unnecessary.
4. **Inspect row counts at each step.** For high-fanout patterns or long paths, the number of possibilities to evaluate can grow rapidly. `EXISTS` only returns a Boolean, but that **does not mean every existential query runs fast**.
5. **Do not assume fixed operator names.** Depending on the version and plan, you may see variants such as `SemiApply`, `AntiSemiApply`, or other operators implementing existence checks. Evaluate using `EXPLAIN` and `PROFILE` on your target version.

Optional constraint creation example, **for a practice database only**:

```cypher
CREATE CONSTRAINT exists_demo_user_id IF NOT EXISTS
FOR (u:ExistsDemoUser)
REQUIRE u.id IS UNIQUE;
```

A uniqueness constraint prevents multiple `:ExistsDemoUser` nodes from sharing the same non-`null` `id` value and provides index-backed lookup for queries filtering by `id`.

## 11. Common Pitfalls

| Issue | Why does it happen? | How to fix |
|---|---|---|
| A person appears multiple times when you only need to know if a link exists | Using `MATCH` which returns every relationship. | Use `WHERE EXISTS { MATCH ... }` to check yes/no; only use `MATCH` when you need the linked data. |
| `Variable v not defined` in the outer `RETURN` | `v` was declared inside `EXISTS` and is not in the outer scope. | Return only a Boolean, or switch to `MATCH`/`CALL` when you need to output `v`. |
| `NOT EXISTS` yields "unexpected" results | It negates **the entire pattern along with conditions inside the subquery**, not just the presence of a relationship. | Write the subquery pattern clearly and test with a case that has a relationship failing the property filter. |
| A person following someone is excluded despite having a valid match | Using two independent `EXISTS` checks when the requirement applies to **the same target node**. | Nest the `NOT EXISTS` check inside `EXISTS` after binding variable `v`. |
| Comparing against `null` returns no results | In Cypher, `= null` does not work as a missing-value check. | Use `IS NULL` / `IS NOT NULL` for properties. |
| Confusing `EXISTS` with `CALL` | Trying to import with `CALL (u)` or expecting `EXISTS` to return detailed rows. | `EXISTS` uses outer variables automatically and returns a Boolean; `CALL` is a different construct. |
| Using `exists(n.property)` in new code | Legacy syntax for property checks, potentially incompatible with current Cypher versions. | Replace with `n.property IS NOT NULL`. |
| Assuming `EXISTS` is always fast | Long paths or missing filters can still be expensive. | Narrow down candidates, use indexes when appropriate, and measure the actual plan. |

## 12. Self-Check Exercises

Use the sample dataset from section 2. Try writing the queries yourself before checking the answers.

**Exercise 1.** Find people who follow at least one **inactive** person.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = false
}
RETURN u.name AS person
ORDER BY person;
```

Expected: **An, Bình**.

**Exercise 2.** Find people who follow an inactive person, but **do not follow any active person**.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = false
}
AND NOT EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  WHERE v.active = true
}
RETURN u.name AS person
ORDER BY person;
```

Expected: **Bình**. `Dũng` follows no one, so he does not satisfy the first `EXISTS` clause.

**Exercise 3.** Find people **who have blocked someone they are currently following**.

```cypher
MATCH (u:ExistsDemoUser)
WHERE EXISTS {
  MATCH (u)-[:FOLLOWS]->(v:ExistsDemoUser)
  MATCH (u)-[:BLOCKS]->(v)
}
RETURN u.name AS person;
```

Expected: **An** — who follows and blocks Chi.

## 13. Summary

- `EXISTS { ... }` checks whether a subquery has **at least one result** and returns `true`/`false`; it neither exports inner variables nor multiplies rows in the outer query.
- `NOT EXISTS { ... }` checks that **no result satisfies the entire pattern and conditions** — especially useful for negative relationship queries.
- Outer variables are used **directly** inside an existential subquery; only variables defined in the outer scope can continue to be used in the outer `RETURN`.
- Use `EXISTS` when the goal is **yes/no**; use `MATCH` when retrieving nodes/relationships, `COUNT` when you need a count, and `IS NOT NULL` when checking property presence.
- For multi-hop networks, place the full pattern and correlated conditions inside one `EXISTS`; nest `NOT EXISTS` when a negation check applies to **the same target variable**.

## References

- [Neo4j Cypher Manual — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/) — existential syntax, variable correlation, and use cases.
- [Neo4j Cypher Manual — WHERE](https://neo4j.com/docs/cypher-manual/current/clauses/where/) — using Boolean expressions to filter patterns.
- [Neo4j Cypher Manual — Predicates](https://neo4j.com/docs/cypher-manual/current/expressions/predicates/) — comparison operators, `IS NULL`, and `IS NOT NULL`.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/) — reading `EXPLAIN` and `PROFILE` for performance analysis.
