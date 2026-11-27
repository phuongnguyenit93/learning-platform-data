# List Predicate Functions: all, any, none, and single in Neo4j Cypher

When querying a **property graph** in Neo4j, we often need to evaluate **multiple elements at once**: whether all scores meet a passing threshold, whether any course is unfinished, whether a role list contains a forbidden value, or whether exactly one step in a path has a desired property. Cypher provides four list predicate functions for this: `all()`, `any()`, `none()`, and `single()`.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. These concepts apply to list properties on nodes/relationships, lists collected across relationships, as well as node and relationship lists along a path. They support modeling connected data and querying relationships/paths with Cypher; when combined with indexes, constraints, the Java Driver, or Spring Data Neo4j, you need a solid grasp of both predicate correctness and the effects of `null`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Read and write the syntax of all four functions accurately, understanding the element variable and `WHERE` predicate.
2. Distinguish “all”, “at least one”, “none”, and “exactly one” matching a condition.
3. Predict results when a list is **empty**, **`null`**, or contains an element whose predicate evaluates to `null`.
4. Combine these functions with `MATCH`, `OPTIONAL MATCH`, `collect()`, `nodes(path)`, and `relationships(path)`.
5. Avoid common logic bugs when checking missing data, lists with duplicate elements, and predicates spanning multiple rows.

## 2. Syntax and Semantics

All four functions take **an input list**, a **variable representing each element**, and a **predicate expression**:

~~~cypher
all(x IN listExpression WHERE predicate)
any(x IN listExpression WHERE predicate)
none(x IN listExpression WHERE predicate)
single(x IN listExpression WHERE predicate)
~~~

Where:

- `listExpression` evaluates to a list, such as `[1, 2, 3]`, a list property `p.scores`, `collect(c)`, `nodes(path)`, or `relationships(path)`.
- `x` is a local variable bound to each element being evaluated; it can be named contextually, such as `score`, `course`, `node`, or `rel`.
- `predicate` is a Boolean expression, such as `score >= 7`, `course.published = true`, or `rel.active = true`.
- The output of each function is a **single logical value**: `true`, `false`, or `null`—not a filtered list of elements.

| Function | Intuitive Meaning | Condition to Return `true` (Without `null`) |
| --- | --- | --- |
| `all(x IN xs WHERE P(x))` | Every element satisfies `P` | All elements satisfy `P` |
| `any(x IN xs WHERE P(x))` | At least one element satisfies `P` | Exists at least one element satisfying `P` |
| `none(x IN xs WHERE P(x))` | No element satisfies `P` | Zero elements satisfy `P` |
| `single(x IN xs WHERE P(x))` | Exactly one element satisfies `P` | Count of elements satisfying `P` is exactly one |

Example you can run directly in Neo4j Browser:

~~~cypher
WITH [2, 4, 7, 9] AS numbers
RETURN
  all(n IN numbers WHERE n > 0) AS allPositive,
  any(n IN numbers WHERE n % 2 <> 0) AS hasOdd,
  none(n IN numbers WHERE n < 0) AS noNegative,
  single(n IN numbers WHERE n = 7) AS exactlyOneSeven;
~~~

**Result:** all four columns are `true`. Every number is positive; there is an odd number; none are negative; and there is exactly one element equal to 7.

Two easily confused cases:

~~~cypher
WITH [4, 4, 9] AS numbers
RETURN
  any(n IN numbers WHERE n = 4) AS atLeastOneFour,
  single(n IN numbers WHERE n = 4) AS exactlyOneFour;
~~~

`atLeastOneFour = true`, while `exactlyOneFour = false` because **two positions** in the list satisfy `n = 4`. `single()` counts matching elements by position, not the number of **distinct values**.

> `all()`, `any()`, `none()`, and `single()` are **list predicate functions**, not aggregation functions like `count()`. They evaluate elements of a *list within a single row*; to gather elements across multiple rows first, `collect()` is typically needed.

## 3. Practice on a List of Scores

Consider a list of learner records. The Cypher snippet below is a **standalone example** requiring no node creation or database modifications:

~~~cypher
WITH [
  {id: 'L01', scores: [8, 9, 10]},
  {id: 'L02', scores: [6, 8]},
  {id: 'L03', scores: []},
  {id: 'L04', scores: [7, null]}
] AS learners
UNWIND learners AS learner
RETURN
  learner.id AS learnerId,
  all(s IN learner.scores WHERE s >= 7) AS allPassing,
  any(s IN learner.scores WHERE s >= 9) AS hasExcellentScore,
  none(s IN learner.scores WHERE s < 5) AS noFailingScore,
  single(s IN learner.scores WHERE s >= 8) AS exactlyOneHighScore
ORDER BY learnerId;
~~~

Expected output:

| Learner | `allPassing` | `hasExcellentScore` | `noFailingScore` | `exactlyOneHighScore` |
| --- | --- | --- | --- | --- |
| L01: `[8, 9, 10]` | `true` | `true` | `true` | `false` |
| L02: `[6, 8]` | `false` | `false` | `true` | `true` |
| L03: `[]` | `true` | `false` | `true` | `false` |
| L04: `[7, null]` | `null` | `null` | `null` | `null` |

Analysis:

- **L01:** all three scores are at least 7; there is a score of 9 or 10; none are below 5; there are **three** scores of 8 or higher, so `single()` returns `false`.
- **L02:** a score of 6 makes `allPassing` false; no score is 9 or higher; none are below 5; there is exactly one score of 8 or higher.
- **L03:** on an empty list, “every element satisfies” is vacuously true and “no element satisfies” is also true; however, no element makes `any()` or `single()` true.
- **L04:** the second score is unknown, so it cannot be determined whether all scores are at least 7, whether any score is 9+, whether any is below 5, or whether exactly one is 8+. All results are `null`.

This is why you must define the **business meaning of empty lists and unknown scores** before using these functions in filter conditions.

## 4. Truth Table with Empty Lists and `null`

Cypher uses three-valued logic: `true`, `false`, and `null` (unknown/missing). If an element causes `P(x)` to evaluate to `null`, the overall result depends on whether the remaining elements suffice to determine the outcome.

The table below interprets inputs by the **evaluation of `P(x)` on each element**, rather than raw element values:

| `P(x)` Results in Order | `all` | `any` | `none` | `single` |
| --- | --- | --- | --- | --- |
| Empty list `[]` | `true` | `false` | `true` | `false` |
| `[true, true]` | `true` | `true` | `false` | `false` |
| `[true, false]` | `false` | `true` | `false` | `true` |
| `[false, false]` | `false` | `false` | `true` | `false` |
| `[true, null]` | `null` | `true` | `false` | `null` |
| `[false, null]` | `false` | `null` | `null` | `null` |
| `[true, true, null]` | `null` | `true` | `false` | `false` |
| `[null]` | `null` | `null` | `null` | `null` |

Reasoning rules:

- `all()`: a **single false** makes it `false`; if there is no false but at least one null, it returns `null`; if every result is true (including an empty list), it returns `true`.
- `any()`: a **single true** makes it `true`; if there is no true but at least one null, it returns `null`; if all are false or the list is empty, it returns `false`.
- `none()`: any true makes it `false`; no true with at least one null returns `null`; all false or empty returns `true`.
- `single()`: **at least two trues** guarantees `false`; exactly one true with all other elements false returns `true`; uncertain whether exactly one is true due to null returns `null`; no true and no null returns `false`.

You can verify this table with the following Cypher snippet:

~~~cypher
WITH [true, null] AS values
RETURN
  all(x IN values WHERE x = true) AS resultAll,
  any(x IN values WHERE x = true) AS resultAny,
  none(x IN values WHERE x = true) AS resultNone,
  single(x IN values WHERE x = true) AS resultSingle;
~~~

Note: `null = true` evaluates to `null`, not `false`.

### 4.1. An Empty List Differs from a Missing List

An empty list `[]` has **0 elements**; `null` means **there is no list to evaluate**:

~~~cypher
WITH [] AS emptyList, null AS missingList
RETURN
  all(x IN emptyList WHERE x > 0) AS allEmpty,
  all(x IN missingList WHERE x > 0) AS allMissing,
  none(x IN emptyList WHERE x < 0) AS noneEmpty,
  any(x IN missingList WHERE x < 0) AS anyMissing;
~~~

The results are `true`, `null`, `true`, and `null`, respectively.

Because `all()` and `none()` return `true` on empty lists, the question “do all scores pass?” can evaluate to true even when no scores exist. When business logic requires at least one score, check the element count:

~~~cypher
WITH [] AS scores
RETURN
  size(scores) > 0
  AND all(s IN scores WHERE s >= 7) AS hasScoresAndAllPass;
~~~

Result: `false`. This pattern applies equally to score lists, permission lists, and collected relationships.

### 4.2. Explicitly Detecting `null`

If missing scores should count as **failing**, convert unknown logical values to false inside the predicate:

~~~cypher
WITH [7, null] AS scores
RETURN
  all(s IN scores WHERE coalesce(s >= 7, false)) AS allPassStrict,
  all(s IN scores WHERE s IS NOT NULL AND s >= 7) AS allPassExplicit;
~~~

Both expressions return `false`, whereas `all(s IN scores WHERE s >= 7)` naturally returns `null`.

Conversely, if you must **distinguish missing data from failing scores**, do not convert all `null` values to `false`. Use `CASE` instead:

~~~cypher
WITH [7, null] AS scores
RETURN CASE
  WHEN scores IS NULL THEN 'missing-list'
  WHEN size(scores) = 0 THEN 'empty-list'
  WHEN any(s IN scores WHERE s IS NULL) THEN 'contains-unknown'
  WHEN all(s IN scores WHERE s >= 7) THEN 'passed'
  ELSE 'failed'
END AS assessment;
~~~

Result: `contains-unknown`. Here `s IS NULL` produces a definite Boolean (`true` or `false`) even when `s` is `null`.

> `coalesce(listProperty, [])` is a deliberate choice: it **turns a missing list into an empty list**. That can cause `all()` and `none()` to return `true`, so it is not always appropriate.

## 5. Applying List Predicates on a Property Graph

Beyond literal lists, these functions are useful on **node list properties** and lists produced from **relationships** or **paths**.

### 5.1. Evaluating a Node List Property

Suppose each learner is stored as a `:Learner` node with a `scores` list property:

~~~cypher
MATCH (l:Learner)
WHERE l.scores IS NOT NULL
  AND size(l.scores) > 0
  AND all(score IN l.scores WHERE score >= 7)
RETURN l.id AS learnerId, l.scores AS scores
ORDER BY learnerId;
~~~

The query selects only learners whose score list **exists, is non-empty, and has all scores >= 7**. If a `null` score exists and no other score makes the predicate false, `all()` returns `null`; `WHERE` keeps only rows where the condition evaluates to `true`.

Replace `all()` with `any()` when only **one** score of 7+ is needed:

~~~cypher
MATCH (l:Learner)
WHERE any(score IN l.scores WHERE score >= 7)
RETURN l.id, l.scores;
~~~

Use `none()` to filter lists containing no forbidden codes:

~~~cypher
MATCH (u:User)
WHERE u.roles IS NOT NULL
  AND none(role IN u.roles WHERE role IN ['BANNED', 'SUSPENDED'])
RETURN u.id, u.roles;
~~~

This condition selects nodes that have no banned roles **and** possess the `roles` property. If the system treats a missing `roles` property as “no roles”, handle the missing list according to your business rules.

### 5.2. Collecting Connected Nodes with `collect()`

Relationship model:

~~~mermaid
flowchart LR
    L["Learner"] -->|ENROLLED_IN| C["Course"]
    C -->|COVERS| T["Topic"]
~~~

If a learner can enroll in multiple courses and you want learners where **all enrolled courses are published**, first collect the related `Course` nodes into a list:

~~~cypher
MATCH (l:Learner)
OPTIONAL MATCH (l)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE size(courses) > 0
  AND all(course IN courses WHERE course.published = true)
RETURN l.id AS learnerId,
       [course IN courses | course.code] AS courseCodes
ORDER BY learnerId;
~~~

Note the following:

1. `OPTIONAL MATCH` preserves learners with no courses; for unmatched rows, `c` can be `null`.
2. `collect(c)` **ignores `null` values**, so a learner with no linked courses gets an empty course list.
3. `size(courses) > 0` prevents learners with zero enrollments from slipping into the results simply because `all()` on `[]` returns `true`.
4. If `course.published` is missing, `course.published = true` evaluates to `null`. Provided no other element makes `all()` false, that row will not pass `WHERE`.

To find learners with **at least one unpublished course**:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE any(course IN courses WHERE course.published = false)
RETURN l.id AS learnerId;
~~~

This query does not treat `published = null` as `false`. If “unknown status” must also be flagged, write the condition explicitly:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(c:Course)
WITH l, collect(c) AS courses
WHERE any(course IN courses
          WHERE course.published IS NULL OR course.published = false)
RETURN l.id AS learnerId;
~~~

### 5.3. Inspecting Paths with `nodes(path)` and `relationships(path)`

For path queries, `nodes(p)` returns the list of nodes along the path and `relationships(p)` returns the list of relationships in path order. We can evaluate each step without manually breaking the path into separate queries.

Example finding dependency paths of length 1 to 4 traversing only active relationships:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE all(rel IN relationships(p) WHERE rel.active = true)
RETURN p;
~~~

The snippet above uses Neo4j Cypher's traditional variable-length path syntax; syntax, planning, and path optimization capabilities can vary by version. The key point here is that **`relationships(p)` returns a list** usable with `all()`.

If a path needs **at least one** critical service:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE any(n IN nodes(p) WHERE n.critical = true)
RETURN p;
~~~

If **no step** may exceed a latency threshold:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE none(rel IN relationships(p) WHERE rel.latencyMs > 200)
RETURN p;
~~~

If **exactly one** node along the path must be a checkpoint:

~~~cypher
MATCH p = (source:Service {id: $sourceId})
          -[:DEPENDS_ON*1..4]->
          (target:Service)
WHERE single(n IN nodes(p) WHERE n.checkpoint = true)
RETURN p;
~~~

Note that `nodes(p)` includes **both the start and end nodes**. If `active`, `latencyMs`, or `checkpoint` can be missing, explicitly decide whether missing values should exclude the path, keep it, or trigger a data-quality check.

## 6. Common Mistakes

| Misconception | Consequence | Proper Syntax / Interpretation |
| --- | --- | --- |
| Using `all()` to mean “has at least one element” | Empty lists still return `true` | Add `size(xs) > 0` |
| Assuming `single()` equals `any()` | Lists with two matching elements are rejected by `single()` | Choose `any()` for “at least one”, `single()` for “exactly one” |
| Assuming `null` always equals `false` | Misinterprets three-valued logic results | Check for missing data; use `IS NULL` or `coalesce()` if business rules allow |
| Using `coalesce(xs, [])` without checking semantics | Unrecorded data may be treated as a valid empty list | Distinguish “no data” from “confirmed empty list” |
| Using `collect()` and assuming it is always non-empty | `collect(null)` adds no element | Check `size(xs)`; distinguish `count(*)` vs `count(variable)` when needed |
| Assuming `single()` counts distinct values | `[4, 4]` has two matching positions | Deduplicate the list if business logic is based on distinct values |
| Calling functions per row thinking all relationships were checked | Each call evaluates only the list in the current row | `WITH key, collect(value) AS xs` before calling the predicate |
| Calling `none()` with the wrong inverted predicate | “No score below 5” differs from “all scores above 5” when a score equals 5 | Write the exact inequality; handle `null` separately |

### 6.1. Difference Between Negation and Switching Quantifiers

For predicates with only `true` and `false`, you can think of them as:

- `none(x IN xs WHERE P(x))` corresponds to “there exists no `x` satisfying `P(x)`”.
- `all(x IN xs WHERE P(x))` corresponds to “there is no `x` making `P(x)` false”.
- `single(x IN xs WHERE P(x))` requires the number of elements making `P(x)` true to equal one.

In Cypher, however, **`null`** must also be considered, and negating `null` with `NOT` still returns `null`. You cannot arbitrarily swap `P(x)` with its “opposite” predicate when missing values exist.

For example, `none(n IN xs WHERE n < 5)` when `xs = [null]` returns `null`, rather than proving “all scores are >= 5”.

### 6.2. Variable Scope and Multiple Rows

The element variable declared inside the function serves only the inner predicate expression. Choose clear names to avoid confusion with variables from `MATCH` or `WITH`:

~~~cypher
MATCH (l:Learner)-[:ENROLLED_IN]->(course:Course)
WITH l, collect(course) AS enrolledCourses
WHERE single(c IN enrolledCourses WHERE c.level = 'ADVANCED')
RETURN l.id AS learnerId;
~~~

This query checks for **exactly one ADVANCED-level course per learner**. If you want “exactly one distinct course” in a graph where multiple enrollment relationships could point to the same node, consider `collect(DISTINCT course)` to deduplicate while aggregating.

## 7. Performance and Verification

These four functions do not create or use indexes on their own. They evaluate a predicate across elements of a list already materialized in the query row. On large datasets:

- Use `MATCH` and `WHERE` predicates on identifier keys to narrow down nodes/relationships before building large lists; leverage appropriate indexes or constraints when locating starting nodes.
- Avoid `collect()` over all relationships in the entire graph when you only care about one learner or one path. Large lists consume memory and force many elements to be evaluated.
- Pass parameters (such as `$sourceId`) via the Java Driver, Spring Data Neo4j, or Cypher runner; never concatenate input values directly into query strings.
- Use `EXPLAIN` to view the estimated plan and `PROFILE` to inspect actual execution. Check the row count before aggregation, data volume, and graph traversal hits.

Example inspecting the plan for a list-property filter query:

~~~cypher
EXPLAIN
MATCH (l:Learner {id: $learnerId})
WHERE any(score IN l.scores WHERE score >= 9)
RETURN l.id;
~~~

An index on `:Learner(id)` can locate the node, but that **does not mean** Neo4j uses an index to inspect individual elements of `l.scores`. To draw conclusions about performance, benchmark on realistic data and your target Neo4j version.

## 8. Practice Exercises with Suggested Solutions

Try predicting the results before checking the answers below. All queries are standalone and do not modify the database.

**Exercise 1 — Counting matching elements accurately.** Given `xs = [3, 6, 9]` and `P(x) := x % 3 = 0`, predict all four functions.

~~~cypher
WITH [3, 6, 9] AS xs
RETURN
  all(x IN xs WHERE x % 3 = 0) AS a,
  any(x IN xs WHERE x % 3 = 0) AS b,
  none(x IN xs WHERE x % 3 = 0) AS c,
  single(x IN xs WHERE x % 3 = 0) AS d;
~~~

**Solution:** `a = true`, `b = true`, `c = false`, `d = false` because three elements satisfy the condition.

**Exercise 2 — Empty lists.** Fix the query so it accepts only when at least one course exists and all courses are completed:

~~~cypher
WITH [] AS completionFlags
RETURN size(completionFlags) > 0
   AND all(done IN completionFlags WHERE done = true) AS validCompletion;
~~~

**Solution:** `validCompletion = false`. Without `size(completionFlags) > 0`, the result would be `true`.

**Exercise 3 — Distinguishing `false` and `null`.** Predict:

~~~cypher
WITH [false, null] AS flags
RETURN
  any(f IN flags WHERE f = true) AS hasTrue,
  none(f IN flags WHERE f = true) AS hasNoTrue,
  single(f IN flags WHERE f = true) AS exactlyOneTrue;
~~~

**Solution:** all three return `null`: an unknown element can change whether a matching element exists or how many match.

**Exercise 4 — Paths.** Write a predicate to keep paths with **exactly one** relationship having `rel.priority = 'HIGH'`. Hint:

~~~cypher
MATCH p = (a:Service)-[:DEPENDS_ON*1..3]->(b:Service)
WHERE single(rel IN relationships(p) WHERE rel.priority = 'HIGH')
RETURN p;
~~~

Try replacing `single()` with `any()` and explain the difference when a path has two relationships with `HIGH` priority.

**Exercise 5 — Missing data rules.** Given `scores = [8, null]`, write two expressions: one preserving the “insufficient data” meaning, and one treating missing scores as failing.

~~~cypher
WITH [8, null] AS scores
RETURN
  all(s IN scores WHERE s >= 7) AS unknownAllowed,
  all(s IN scores WHERE coalesce(s >= 7, false)) AS missingIsFailure;
~~~

**Solution:** `unknownAllowed = null`, `missingIsFailure = false`.

## 9. Checklist for Real-World Queries

- [ ] Choose the right quantifier: **all**, **at least one**, **none**, or **exactly one**.
- [ ] Determine whether the list can be empty or `null`; define how to handle it before writing the predicate.
- [ ] Check whether duplicate elements or elements with `null` properties can occur.
- [ ] When using `collect()`, verify grouping in `WITH`, skipped `null` values, and whether `DISTINCT` is needed.
- [ ] For paths, decide whether to evaluate nodes, relationships, or both, and whether start/end nodes should be included.
- [ ] Test against small datasets covering true, false, empty, and unknown cases.
- [ ] On large datasets, use `EXPLAIN`/`PROFILE` to inspect the query plan instead of guessing speed from syntax alone.

The four functions `all()`, `any()`, `none()`, and `single()` turn business rules about **how many elements satisfy a condition** into concise Cypher. For accurate results, always account for **empty lists, missing data, and duplicate elements** alongside the graph's node–relationship structure.
