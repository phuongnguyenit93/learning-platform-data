# MERGE to Find or Create Data by Pattern in Neo4j

> **Chapter:** Create and Update  
> **Topic:** `MERGE` in Cypher — finding an existing graph pattern or creating a new one.

In the `DATABASE_ENGINE_GRAPH_NEO4J` module, data is represented as a **property graph**: nodes contain entity information, relationships connect entities, and properties store attributes of both nodes and relationships. Cypher provides `MATCH` to query, `CREATE` to create new elements, and `MERGE` to perform **match-or-create by pattern**. This technique is very useful when synchronizing users, importing data repeatedly, managing membership relationships, or recording relationships between already identified entities.

This lesson explains `MERGE` at the graph-pattern level, `ON CREATE`/`ON MATCH` branches, business keys, constraints and indexes, batch data imports, and calling Cypher from the Java Driver. The focus is on using `MERGE` with the right semantics to avoid creating unintended nodes or relationships.

## 1. Learning Objectives

After completing this lesson, you can:

1. Distinguish `MATCH`, `CREATE`, and `MERGE` based on existing data.
2. Explain why `MERGE` evaluates the **entire pattern**, rather than automatically matching each part of the pattern individually.
3. Use `MERGE` for nodes with business keys and distinguish identifying properties from mutable properties.
4. Write `ON CREATE SET` and `ON MATCH SET` to properly handle initial creation and subsequent matches.
5. Create relationships between existing nodes by binding the endpoints before `MERGE`ing the relationship.
6. Design constraints, bulk queries, and transactions aligned with deduplication requirements.

## 2. Core Concept: `MERGE` Matches or Creates the Entire Pattern

Simple syntax:

~~~cypher
MERGE (p:Person {personId: 'P-001'})
RETURN p;
~~~

Neo4j processes a pattern `(p:Person {personId: 'P-001'})` as follows:

- **A node matches the pattern:** binds variable `p` to the existing node; no additional node is created for that pattern.
- **No node matches the pattern:** creates a `Person` node with `personId = 'P-001'`; binds variable `p` to the newly created node.

Flow visualization:

~~~mermaid
flowchart TD
    A["MERGE Cypher pattern"] --> B{"Full pattern match exists?"}
    B -->|Yes| C["Use existing data"]
    B -->|No| D["Create new pattern"]
    C --> E["ON MATCH SET (if declared)"]
    D --> F["ON CREATE SET (if declared)"]
    E --> G["Pass result row to next clause"]
    F --> G
~~~

`MERGE` is commonly used to write idempotent queries that can be run repeatedly while still identifying the same entity or connection. However, **`MERGE` alone does not guarantee duplicate-free data in every scenario**. Uniqueness also depends on the match pattern, business keys, existing data, constraints, and concurrent writes.

### Comparing the Three Basic Clauses

| Clause | When matching data exists | When data does not exist | Purpose |
|---|---|---|---|
| `MATCH (p:Person {personId: $id})` | Returns the matching node | Returns no rows | Read/find |
| `CREATE (p:Person {personId: $id})` | Still requests creating a new node | Creates a new node | Create new |
| `MERGE (p:Person {personId: $id})` | Uses the matching node | Creates a new node | Find or create |

If multiple nodes match the pattern, `MERGE` can produce **multiple matching result rows**; it does not merge duplicate nodes into one.

## 3. Finding or Creating Nodes Using Business Keys

### 3.1. Identifying an Entity's Identity

Suppose every user has a unique `userId` in the system. Query:

~~~cypher
MERGE (u:User {userId: 'U-101'})
RETURN u;
~~~

The first time (when no corresponding `User` node exists), the query creates the node:

~~~text
(:User {userId: 'U-101'})
~~~

On subsequent runs, the query finds and uses the existing node. `userId` is an application-controlled **business key**. It is distinct from Neo4j's internal ID and is suitable for identifying data across syncs or imports.

To inspect the state:

~~~cypher
MATCH (u:User {userId: 'U-101'})
RETURN u.userId AS userId, labels(u) AS labels;
~~~

### 3.2. Do Not Put Mutable Properties in the Identifying Pattern

**An approach that easily causes duplicate data:**

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  displayName: 'An'
});
~~~

Later, the user changes their name to "An Nguyễn":

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  displayName: 'An Nguyễn'
});
~~~

The two patterns do not match because `displayName` differs. Without a constraint, Neo4j can create a second `User` node with the same `userId`. With a unique constraint on `userId`, the second query can **be rejected due to a constraint violation**. That query does not automatically turn into a name update.

**Recommended approach: use only the stable key in `MERGE`, and update all other fields with `SET`.**

~~~cypher
MERGE (u:User {userId: 'U-101'})
SET u.displayName = 'An Nguyễn'
RETURN u;
~~~

In a real system, pass values via parameters:

~~~cypher
MERGE (u:User {userId: $userId})
SET u.displayName = $displayName
RETURN u.userId AS userId, u.displayName AS displayName;
~~~

Example parameters:

~~~json
{
  "userId": "U-101",
  "displayName": "An Nguyễn"
}
~~~

**Design rule:** Properties in the `MERGE` pattern should describe **identity or immutable matching criteria**. Display names, visit counts, statuses, or update timestamps typically belong in `SET`.

## 4. `ON CREATE SET` and `ON MATCH SET`

`MERGE` allows separating two execution branches:

- `ON CREATE SET`: runs only when `MERGE` **creates a new pattern**.
- `ON MATCH SET`: runs only when `MERGE` **matches an existing pattern**.
- Standalone `SET`: runs in both cases when the row reaches this clause.

Example of an employee record:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.fullName = $fullName,
  e.department = $department,
  e.createdAt = datetime()
ON MATCH SET
  e.fullName = $fullName,
  e.department = $department,
  e.updatedAt = datetime()
RETURN e.employeeId AS employeeId,
       e.fullName AS fullName,
       e.createdAt AS createdAt,
       e.updatedAt AS updatedAt;
~~~

Example parameters:

~~~json
{
  "employeeId": "EMP-101",
  "fullName": "Lê Bình",
  "department": "Platform"
}
~~~

| Scenario | Branch Executed | Expected Outcome |
|---|---|---|
| No `Employee` with `EMP-101` exists | `ON CREATE SET` | Creates node, sets name/department and `createdAt` |
| That node already exists | `ON MATCH SET` | Uses existing node, updates name/department and `updatedAt` |

`createdAt` is set on initial creation and is not overwritten by `ON MATCH`. `updatedAt` only appears when updated in the match branch; if the business requirement wants an update timestamp upon creation as well, it can be set in both branches.

### Distinguishing Data Updates from Repeatability

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p.price = $price;
~~~

Re-running with the same `sku` does not create an extra `Product` node if only one node matches and no concurrent write race creates duplicates. However, `price` can change on each run. If `updatedAt = datetime()` is assigned on every run, the timestamp property also changes even with identical input. Therefore, "re-running without creating structural duplicates" differs from "every property always remains unchanged."

### `MERGE` Can Accept Multiple Labels

~~~cypher
MERGE (e:Person:Employee {employeeId: 'EMP-102'})
RETURN labels(e) AS labels;
~~~

This pattern requires a node with **both labels** and the specified `employeeId` value. A node with only the `Person` label and the same `employeeId` is not a full pattern match. When designing ingestion from multiple sources, choose consistent labels and keys to avoid identity fragmentation.

## 5. Important: `MERGE` Evaluates the Entire Relationship Pattern

### 5.1. Pitfall When `MERGE`ing Two Nodes and a Relationship Together

Suppose the graph already has:

~~~text
(:Person {personId: 'P-101'})      (:Team {teamId: 'T-01'})
~~~

There is currently **no** `MEMBER_OF` relationship between the two nodes. The following query looks at first glance like it creates a missing relationship:

~~~cypher
MERGE (p:Person {personId: 'P-101'})
      -[:MEMBER_OF]->
      (t:Team {teamId: 'T-01'});
~~~

However, `MERGE` checks the **entire pattern** consisting of the person node, the relationship, and the team node. Because the full connection does not yet exist, the pattern fails to match; Cypher will attempt to **create the entire pattern**, including **two new nodes and one relationship**. Without constraints, that can lead to duplicate nodes carrying `personId`/`teamId`. With constraints, the statement can fail instead of connecting the two existing nodes.

This is the critical difference between "find or create a pattern" and "find or create each individual part of a pattern."

### 5.2. The Right Way: Bind Nodes First, Then `MERGE` the Relationship

When **both endpoints already exist**:

~~~cypher
MATCH (p:Person {personId: 'P-101'})
MATCH (t:Team {teamId: 'T-01'})
MERGE (p)-[r:MEMBER_OF]->(t)
RETURN p.personId AS personId,
       type(r) AS relation,
       t.teamId AS teamId;
~~~

- The first `MATCH` binds `p` to the existing person node.
- The second `MATCH` binds `t` to the existing team node.
- `MERGE (p)-[r:MEMBER_OF]->(t)` looks for a relationship of that exact type and direction between those two nodes; if none exists, it creates a new relationship.
- Because `p` and `t` are already bound, the `MERGE` step does not request recreating the two endpoint nodes.

If `MATCH` fails to find either node, no rows reach `MERGE`, so **no relationship is created**. If `MATCH` returns multiple nodes for a key, the result can produce multiple pairs and multiple relationships; duplicate data cleanup and uniqueness constraints are required.

### 5.3. The Right Way When Nodes Might Not Exist Yet

If you want to automatically create the person, the team, and the connection as needed, use **three separate `MERGE` clauses**:

~~~cypher
MERGE (p:Person {personId: $personId})
  ON CREATE SET p.name = $personName
MERGE (t:Team {teamId: $teamId})
  ON CREATE SET t.name = $teamName
MERGE (p)-[r:MEMBER_OF]->(t)
  ON CREATE SET r.joinedAt = date(),
                r.role = $role
RETURN p.personId AS personId,
       t.teamId AS teamId,
       r.role AS role;
~~~

First, each node is identified by its business key; finally, the relationship is found or created between the **two bound variables**. The `joinedAt` and `role` properties live on the relationship because they describe **a person belonging to a team**, rather than an independent attribute of the person or the team.

### 5.4. Direction and Relationship Type Are Part of the Pattern

~~~cypher
MERGE (a)-[:FOLLOWS]->(b)
~~~

does not have the same directional pattern as:

~~~cypher
MERGE (b)-[:FOLLOWS]->(a)
~~~

For directed relationships, the positions of the source node and target node matter. A `FOLLOWS` relationship is also distinct from `KNOWS` or `MEMBER_OF`. Choose the type and direction that reflect the business rules.

Cypher allows querying undirected patterns in some contexts, but when creating or finding relationships with `MERGE`, you should **write an explicit direction** so readers clearly understand the meaning of the data.

## 6. `MERGE`ing Relationships with Properties

Properties can be part of the relationship match condition:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (c:Course {courseId: $courseId})
MERGE (u)-[r:ENROLLED_IN {enrollmentCode: $enrollmentCode}]->(c)
ON CREATE SET
  r.enrolledAt = datetime(),
  r.status = 'ACTIVE'
ON MATCH SET
  r.lastCheckedAt = datetime()
RETURN u.userId AS userId,
       c.courseId AS courseId,
       r.enrollmentCode AS enrollmentCode,
       r.status AS status;
~~~

Here, `enrollmentCode` is part of what identifies the enrollment relationship. If `enrollmentCode` changes, the relationship pattern changes as well, and the statement can create an additional relationship. Do not put mutable fields like `status` in the identifying pattern if the business requirement wants to **update the same relationship**.

If the rule is "each person has at most one enrollment per course," you can use the pattern:

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (c:Course {courseId: $courseId})
MERGE (u)-[r:ENROLLED_IN]->(c)
ON CREATE SET r.enrolledAt = datetime()
SET r.status = $status
RETURN r;
~~~

This statement fits when the **node pair + relationship type** uniquely identifies the connection per business rules. If a person can enroll multiple times in the same course (multiple terms, multiple events), you need to include an enrollment identifier in the model or create a separate `Enrollment` node. When you need to record **every new event** rather than folding events by pattern, `CREATE` is usually more appropriate.

## 7. `MERGE`, Constraints, and Indexes

### 7.1. Why Are Unique Constraints Needed?

`MERGE` alone does not replace data integrity rules. If two concurrent transactions both see that no `User` node exists for the same `userId`, the lack of a constraint can lead to duplicate records. Define business keys and unique constraints:

~~~cypher
CREATE CONSTRAINT user_userId_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT team_teamId_unique IF NOT EXISTS
FOR (t:Team)
REQUIRE t.teamId IS UNIQUE;
~~~

With clean data, constraints prevent **two nodes of the same label from having the same key value**. A constraint can cause a violating query to fail; the application must handle the error and apply a transaction retry policy where appropriate.

Before creating a constraint on an existing database, check for duplicate data. If multiple `User` nodes already share the same `userId`, creating a unique constraint will not succeed until the data is cleaned up.

### 7.2. Partial Matches Can Trigger Constraint Errors

Suppose the graph already has:

~~~text
(:User {userId: 'U-101', email: 'an@example.com'})
~~~

and `userId` has a unique constraint. The query:

~~~cypher
MERGE (u:User {
  userId: 'U-101',
  email: 'an.new@example.com'
});
~~~

will not match the existing node because `email` differs. Creating a new node then violates uniqueness on `userId`, so the statement may throw an error. The fix is to identify by `userId` first, then update `email`:

~~~cypher
MERGE (u:User {userId: 'U-101'})
SET u.email = 'an.new@example.com'
RETURN u;
~~~

Constraints do not alter `MERGE`'s "match the entire pattern" rule.

### 7.3. Role of Indexes When Using `MERGE`

Indexes help Neo4j locate nodes by label and property more efficiently, especially as the graph grows. A unique constraint on a node property also supports data lookups by that key. When `MERGE` runs frequently, consider:

- Defining constraints for business keys that truly must be unique.
- Choosing match patterns with explicit labels and keys; avoid using free-form names or unstable values as keys.
- Inspecting execution plans with `EXPLAIN` to see how nodes are looked up; measuring with `PROFILE` in an appropriate environment because `PROFILE` **executes the query**, including write queries.
- Avoiding pairing `MERGE` with a `MATCH` that returns an unexpectedly large number of rows; each row can trigger a pattern evaluation.

## 8. Common Errors and How to Handle Them

| Symptom | Cause | Fix |
|---|---|---|
| Re-running still produces duplicate nodes | No stable key or existing data already has duplicates | Define a business key, clean data, add a constraint |
| Every name change creates a new node | Including `name` in the `MERGE` pattern | `MERGE` by ID; `SET` the name |
| Creates duplicates of both nodes | `MERGE`ing the entire path when nodes are unbound | `MATCH` or `MERGE` each node separately, then `MERGE` the relationship |
| No new relationship appears | Endpoint `MATCH` returned zero rows | Check labels, keys, and existing data before connecting |
| Multiple copies of a relationship appear | Endpoint or relationship data was already duplicated; concurrent writes | Clean data, define a uniqueness model, design proper transactions/constraints |
| Constraint error during `MERGE` | Pattern has non-matching properties while the unique key already exists | `MERGE` only on the key, use `SET` for mutable properties |
| Query fails with `null` value | Property used in the `MERGE` pattern has a `null` value | Validate or filter out rows missing keys before `MERGE` |
| Update did not run on creation | Used `ON MATCH SET` when the node was just created | Use `ON CREATE SET` or a general `SET` |

### `null` Values in Match Keys

The following example cannot use `userId = null` as a condition to create or match a node:

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u;
~~~

When the `$userId` parameter is `null`, `MERGE` fails because it cannot look up or create a node with a `null` key property in the pattern. Validate at the application layer. For list imports, you can skip rows missing a key:

~~~cypher
UNWIND $users AS item
WITH item
WHERE item.userId IS NOT NULL
MERGE (u:User {userId: item.userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = item.displayName
RETURN count(DISTINCT u) AS distinctUsers;
~~~

This query skips records without a `userId`; if business rules require every record to be valid, **raise a validation error** rather than silently skipping them.

## 9. Batch Data Import with `UNWIND` + `MERGE`

Suppose you need to repeatedly sync a list of students from an external source. Parameter data:

~~~json
{
  "students": [
    {"studentId": "ST-101", "name": "Hà", "city": "Hà Nội"},
    {"studentId": "ST-102", "name": "Linh", "city": "Đà Nẵng"},
    {"studentId": "ST-103", "name": "Khánh", "city": "TP.HCM"}
  ]
}
~~~

Query:

~~~cypher
UNWIND $students AS row
MERGE (s:Student {studentId: row.studentId})
ON CREATE SET s.createdAt = datetime()
SET s.name = row.name,
    s.city = row.city
RETURN count(DISTINCT s) AS studentsProcessed;
~~~

`UNWIND` turns each list element into a row, and `MERGE` identifies the student by `studentId`. When re-run with the same data, the query does not recreate nodes that already matched. `count(DISTINCT s)` reports the number of **distinct nodes processed** in the result, not the number of newly created nodes.

Notes for bulk imports:

1. Normalize and validate keys before passing them into `MERGE` (`studentId` non-empty, consistent data types).
2. Handle duplicate keys within the same batch if rows carry conflicting properties; do not rely on `UNWIND` order to pick the winning record.
3. Set up a unique constraint on `Student.studentId` when the data requires one node per student.
4. For large datasets, split into batches or use a batched transaction mechanism appropriate for your version and environment, avoiding a single oversized transaction.
5. Monitor input row counts, processed entity counts, and constraint errors; do not infer from `count(*)` that the same number of nodes were created.

## 10. Complete Example: Syncing Learners and Course Enrollments

Problem: a learning platform needs to manage **one node per learner**, **one node per course**, and **one enrollment relationship per learner–course pair**. Data may be resent after network errors, so repeating the operation must not create duplicate connections.

### Step 1 — Declare Unique Keys

Run once during model setup, after ensuring existing data has no violations:

~~~cypher
CREATE CONSTRAINT learner_learnerId_unique IF NOT EXISTS
FOR (l:Learner)
REQUIRE l.learnerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT course_courseId_unique IF NOT EXISTS
FOR (c:Course)
REQUIRE c.courseId IS UNIQUE;
~~~

### Step 2 — Find or Create Nodes, Then Find or Create the Relationship

~~~cypher
MERGE (l:Learner {learnerId: 'L-901'})
ON CREATE SET
  l.fullName = 'Trần An',
  l.createdAt = datetime()
MERGE (c:Course {courseId: 'C-901'})
ON CREATE SET
  c.title = 'Neo4j Fundamentals',
  c.createdAt = datetime()
MERGE (l)-[r:ENROLLED_IN]->(c)
ON CREATE SET
  r.enrolledAt = datetime(),
  r.status = 'ACTIVE'
RETURN l.learnerId AS learnerId,
       c.courseId AS courseId,
       r.enrolledAt AS enrolledAt,
       r.status AS status;
~~~

Resulting graph:

~~~text
(:Learner {learnerId: 'L-901', fullName: 'Trần An'})
          |
          | [:ENROLLED_IN {status: 'ACTIVE', enrolledAt: ...}]
          v
(:Course {courseId: 'C-901', title: 'Neo4j Fundamentals'})
~~~

If run a second time without duplicate data and without competing write transactions causing parallel relationships, the query finds the existing nodes and relationship. `ON CREATE SET r.enrolledAt` does not run again, so the original enrollment timestamp is preserved.

### Step 3 — Verify the Result with `MATCH`

~~~cypher
MATCH (l:Learner {learnerId: 'L-901'})
      -[r:ENROLLED_IN]->
      (c:Course {courseId: 'C-901'})
RETURN l.fullName AS learner,
       c.title AS course,
       r.status AS status,
       r.enrolledAt AS enrolledAt;
~~~

In a valid model with at most one enrollment relationship per pair, the query returns **one row**. If it returns multiple rows, the data may already contain duplicate relationships and needs inspection.

### Step 4 — Update Enrollment Status

Because `status` is a mutable property, do not include it in the `MERGE` pattern:

~~~cypher
MATCH (l:Learner {learnerId: 'L-901'})
MATCH (c:Course {courseId: 'C-901'})
MERGE (l)-[r:ENROLLED_IN]->(c)
ON CREATE SET r.enrolledAt = datetime()
SET r.status = 'COMPLETED',
    r.updatedAt = datetime()
RETURN r.status AS status, r.updatedAt AS updatedAt;
~~~

This approach can create the relationship if absent and update `status` on either the matched or newly created relationship. If business rules **only allow updating an existing enrollment**, replace the relationship `MERGE` with `MATCH (l)-[r:ENROLLED_IN]->(c)` so it does not auto-create the relationship.

### Step 5 — When Multiple Enrollments Are Needed

If a learner can take the same course multiple times across different cohorts, do not force every enrollment into a single relationship. You can model each enrollment as a node with its own `enrollmentId`:

~~~cypher
MATCH (l:Learner {learnerId: $learnerId})
MATCH (c:Course {courseId: $courseId})
MERGE (e:Enrollment {enrollmentId: $enrollmentId})
ON CREATE SET e.enrolledAt = datetime()
MERGE (l)-[:HAS_ENROLLMENT]->(e)
MERGE (e)-[:FOR_COURSE]->(c)
RETURN e.enrollmentId AS enrollmentId;
~~~

Here, each enrollment has its own key, allowing the same learner to enroll multiple times; set a constraint on `Enrollment.enrollmentId` if the identifier must be unique. Ensure `enrollmentId` is tied to the right learner and course according to business rules; the statement above does not automatically validate existing relationships if the input conflicts.

## 11. Using `MERGE` from the Neo4j Java Driver

Java applications should pass parameters, manage transactions, and handle constraint errors. Example method to sync a learner:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class LearnerRepository {
    private final Driver driver;

    public LearnerRepository(Driver driver) {
        this.driver = driver;
    }

    public String upsertLearner(String learnerId, String fullName) {
        String cypher = """
                MERGE (l:Learner {learnerId: $learnerId})
                ON CREATE SET l.createdAt = datetime()
                SET l.fullName = $fullName
                RETURN l.learnerId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "learnerId", learnerId,
                            "fullName", fullName
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

Explanation:

- `Driver` lifecycle is managed by the application; `Session` is closed after each operation.
- `executeWrite(...)` performs the write work inside a Driver transaction function.
- `$learnerId` and `$fullName` are parameters, avoiding direct string concatenation of inputs into Cypher.
- `single()` is appropriate when constraints and the model guarantee the query returns exactly one row. If the data contains multiple duplicate nodes for `learnerId`, the result may no longer be a single row.
- Transaction functions can be re-invoked by the Driver on transient errors according to its retry mechanism. Therefore, do not place non-idempotent external side effects (such as sending payment emails) directly inside the callback.
- `Map.of(...)` does not accept Java `null` values; validate keys and data before calling.

If using Spring Data Neo4j, entities and repositories map the graph into Java. When exact `MERGE`/`ON CREATE`/`ON MATCH` semantics are required, you can write custom Cypher queries via `@Query` with appropriate parameters; do not assume every `save(...)` call is strictly equivalent to a single `MERGE` statement.

## 12. Practice and Self-Check Questions

### Exercise 1 — Find or Create a Product

Write a statement according to the requirements:

- `sku` identifies the product.
- Set `createdAt` only on initial creation.
- Selling price `price` is updated on every execution.
- Return `sku`, `price`.

<details>
<summary>Solution hint</summary>

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p.price = $price
RETURN p.sku AS sku, p.price AS price;
~~~

</details>

### Exercise 2 — Connect Existing Nodes

Suppose `(:Author {authorId: 'A-01'})` and `(:Book {bookId: 'B-01'})` already exist. Write a query that ensures a `WROTE` relationship in the direction Author → Book exists without recreating the nodes.

<details>
<summary>Solution hint</summary>

~~~cypher
MATCH (a:Author {authorId: 'A-01'})
MATCH (b:Book {bookId: 'B-01'})
MERGE (a)-[:WROTE]->(b)
RETURN a.authorId AS authorId, b.bookId AS bookId;
~~~

</details>

### Exercise 3 — Predict the Outcome

The graph already contains two nodes but no relationship:

~~~text
(:Person {personId: 'P-777'})
(:Team {teamId: 'T-777'})
~~~

There are no constraints. You run:

~~~cypher
MERGE (:Person {personId: 'P-777'})
      -[:MEMBER_OF]->
      (:Team {teamId: 'T-777'});
~~~

**Question:** Is the query forced to reuse the two existing nodes?

**Answer:** No. The entire pattern does not yet exist, so `MERGE` can create the entire new pattern, including both endpoint nodes. The right way is to `MATCH` both nodes first, then `MERGE` the relationship; or `MERGE` each node separately and use variables to connect them.

### Exercise 4 — Identifying by a Mutable Property

Why should you avoid:

~~~cypher
MERGE (u:User {userId: $userId, displayName: $displayName});
~~~

**Answer:** When the name changes, the pattern no longer matches. The query can create a duplicate node or violate a constraint. Replace it with `MERGE (u:User {userId: $userId}) SET u.displayName = $displayName`.

### Exercise 5 — Checking Relationship Semantics

An application logs history every time a user clicks on a product. Should you use `CREATE` or `MERGE` for each click?

**Answer:** If each click is **a separate event that must be recorded in full**, use `CREATE` to add a new event (typically an Event node with its own ID), or `MERGE` on a genuinely unique `eventId` when deduplicating resent events. `MERGE` only on the user–product pair will collapse clicks into a single connection pattern and lose individual event counts/occurrences unless supported by a different model.

## 13. Takeaways

- `MERGE` is **find-or-create by pattern**: if the pattern matches, reuse the data; otherwise, create the pattern.
- `MERGE` evaluates the **entire written pattern**, without automatically resolving individual nodes of a path.
- For **nodes**, use labels and a stable business key inside `MERGE`; put mutable properties in `SET`.
- `ON CREATE SET` runs when the pattern is created; `ON MATCH SET` runs when the pattern already matched.
- For **relationships**, bind nodes via `MATCH` or separate `MERGE` clauses before `MERGE`ing the connection.
- Unique constraints protect node identity, especially during syncs and concurrent writes; indexes support lookup performance.
- Existing duplicate data, `null` keys, multiple `MATCH` results, and concurrent writes still require proper handling at the data and application layers.
- `UNWIND` + `MERGE` is the foundation for repeatable imports; the Java Driver enables parameterized execution and transactions.

**Next steps:** Combine `MERGE` with `MATCH`, `SET`, `REMOVE`, indexes/constraints, query plans, and transactions when building Neo4j systems with the Java Driver or Spring Data Neo4j.
