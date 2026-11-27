# Distinguishing Full-Pattern MERGE from Per-Entity and Relationship MERGE

> **Chapter:** Create and Update  
> **Module:** `DATABASE_ENGINE_GRAPH_NEO4J` — Neo4j, property graphs, and Cypher queries.

When storing connected data in Neo4j, applications often need to **find or create** a node and **connect nodes** with relationships. Cypher provides the `MERGE` clause for this purpose. However, writing a single `MERGE` containing **an entire path pattern** versus writing multiple `MERGE` clauses to handle **each node and then the relationship** can produce very different results.

For example, suppose the system already has employee An and project Atlas, but has not yet recorded that An works on Atlas. If you use `MERGE` on the entire pattern `(An)-[:WORKS_ON]->(Atlas)` when neither node variable is bound beforehand, Neo4j does not automatically reuse the two nodes just because their properties match. This is one of the most common causes of **duplicate nodes** or **unique constraint violations**.

This lesson focuses on the atomicity of `MERGE` pattern matching, the role of bound variables, how to design business keys, and safe workflows for adding relationships.

## 1. Learning Objectives

After this lesson, you can:

1. Correctly interpret `MERGE`'s "match the whole pattern or create the whole pattern" semantics.
2. Predict the outcome of `MERGE` when the graph is empty, when only nodes exist, and when the relationship already exists.
3. Distinguish full-pattern `MERGE` with unbound nodes, per-node then relationship `MERGE`, and `MATCH`ing existing nodes followed by `MERGE`ing the relationship.
4. Use `ON CREATE SET` and `ON MATCH SET` accurately with each `MERGE`, avoiding placing frequently changing properties in match keys.
5. Apply constraints, parameters, `UNWIND`, and result checks to prevent duplicate data in Java applications, Spring Data Neo4j, or data import pipelines.

## 2. Recap: Graph Patterns and MERGE

In the *property graph* model:

- **Node** represents an entity, e.g., `:Person`, `:Project`.
- **Relationship** connects two nodes with a direction and a type, e.g., `[:WORKS_ON]`.
- **Property** describes a node or relationship, e.g., `personId`, `projectId`, `role`.
- **Cypher variables** such as `p`, `pr`, `r` reference components within **query scope**; variables are not persistent identifiers of the data.

Illustrative business data:

~~~text
(:Person {personId: 'P01', name: 'An'})
                 |
                 | [:WORKS_ON {role: 'Backend'}]
                 v
(:Project {projectId: 'PR01', title: 'Atlas'})
~~~

Basic syntax:

~~~cypher
MERGE (p:Person {personId: 'P01'})
RETURN p;
~~~

`MERGE` first tries to match the specified pattern. If a matching pattern exists, those components are reused. If no matching pattern exists, Neo4j creates what is needed according to the semantics **of the entire pattern in that `MERGE` clause**.

**Difference from `CREATE`:** `CREATE` requests creating new elements matching the pattern. `MERGE` performs find-or-create by pattern. However, `MERGE` **does not guarantee global uniqueness** if the data lacks proper business keys and constraints; nor does it automatically stitch disjoint partial matches of a nonexistent pattern into a complete connected path.

## 3. Full-Pattern MERGE: Match the Whole Path or Create the Whole Path

Consider the following query:

~~~cypher
MERGE (p:Person {personId: 'P01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR01'})
RETURN p, r, pr;
~~~

This is **a single `MERGE` clause containing the entire three-part pattern**:

~~~text
(p:Person {personId: 'P01'})
       -[:WORKS_ON]->
(pr:Project {projectId: 'PR01'})
~~~

When `p` and `pr` are not already bound from a `MATCH` or a prior clause, Neo4j tries to find **a path matching the entire pattern**. The mere separate existence of a `Person` node and a `Project` node with the right IDs **is not enough** for the pattern above to be considered matched if no `WORKS_ON` relationship exists between them.

### 3.1. Three Input States and Outcomes

Assume `personId` and `projectId` are business identifiers, and all examples below represent **independent hypothetical data states**, not three consecutive runs in the same database.

| State Before Query | What Will Full-Pattern `MERGE` Do? |
|---|---|
| Neither person P01, project PR01, nor `WORKS_ON` exists | Creates two nodes and one relationship |
| Both nodes P01 and PR01 exist, but **no relationship** exists between them | Full pattern does not match; attempts to create a new pattern consisting of two nodes and one relationship |
| P01 `-[:WORKS_ON]->` PR01 already exists | Matches the existing pattern and reuses the matched components |

For the second row, the outcome depends on constraints:

- **Without unique constraints:** duplicate nodes for P01 and PR01 can appear along with a new relationship connecting those duplicates.
- **With unique constraints** on `:Person(personId)` and `:Project(projectId)`: the query can fail because creating two new nodes conflicts with the existing nodes. It **does not automatically switch strategies** to reuse the two nodes and create only the relationship.

### 3.2. Diagram Illustrating the Pre-Existing Two-Node Scenario

**Before running** full-pattern `MERGE`:

~~~text
[P01: An]                              [PR01: Atlas]
  (Person)                              (Project)

     Two existing nodes, no WORKS_ON between them yet.
~~~

**After running on a graph without unique constraints:**

~~~text
[P01: An]                              [PR01: Atlas]
  (Person)                              (Project)

[P01: An] --[:WORKS_ON]--------------> [PR01: Atlas]
  (New Person)                           (New Project)
~~~

The new relationship connects the two newly created duplicates, **not** the two original nodes. Identical properties do not make two nodes the same entity in the graph.

### 3.3. Why Does "Full Pattern" Matter?

A relationship pattern consists of structure, labels, relationship type, direction, and the property values used for matching. Missing even one component causes the pattern to **fail to match fully**:

~~~cypher
MERGE (p:Person {personId: 'P01'})
      -[:WORKS_ON {role: 'Backend'}]->
      (pr:Project {projectId: 'PR01'});
~~~

Suppose P01 `-[:WORKS_ON {role: 'Data'}]->` PR01 already exists. The pattern requiring `role: 'Backend'` does not match the old relationship; if the two endpoints are unbound, full-pattern `MERGE` again attempts to create an entire new pattern. Therefore, fields like `role`, `status`, or `updatedAt` require careful consideration: if they change over time, they should not routinely be placed in the identifying part of the pattern.

## 4. MERGE Each Entity, Then MERGE the Relationship

For the problem "P01 works on PR01", a usually more appropriate statement structure is:

~~~cypher
MERGE (p:Person {personId: 'P01'})
MERGE (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       type(r) AS relationshipType;
~~~

Here there are **three independent `MERGE` clauses**:

1. `MERGE (p:Person {personId: 'P01'})` finds or creates the **Person node**; after this clause, `p` references a concrete node.
2. `MERGE (pr:Project {projectId: 'PR01'})` finds or creates the **Project node**; after this clause, `pr` references a concrete node.
3. `MERGE (p)-[r:WORKS_ON]->(pr)` finds the relationship between **those exact two bound nodes**, or creates the relationship if absent.

In the state where P01 and PR01 already exist but are not yet connected, the first two `MERGE` clauses reuse the matching nodes and the last `MERGE` creates the new relationship:

~~~text
[P01: An] --[:WORKS_ON]--> [PR01: Atlas]
  old node      new          old node
~~~

The key is that **variables `p` and `pr` are already bound before creating the relationship**. The relationship pattern is not permitted to unilaterally recreate the two already-bound endpoint nodes.

### 4.1. Direct Comparison

| Criterion | Full-pattern `MERGE` with unbound nodes | `MERGE` each node, then the relationship |
|---|---|---|
| Number of clauses | One `MERGE` for the full path | Multiple `MERGE` clauses, each with its own responsibility |
| What must match | The entire declared path | Each node first, then the relationship connecting the found/created nodes |
| When both nodes exist but relationship is missing | Attempts to create an entire new pattern | Reuses both nodes, creates the missing relationship |
| When nodes have unique constraints | Can fail due to conflict when creating the full pattern | Better suited when identifying each node by a unique key |
| When run repeatedly | Re-finds the full pattern if it exists | Re-finds each node and existing relationship |
| Suitable use cases | Wanting to check/create a whole pattern as a unit, or small patterns with brand-new components | Syncing connected data, reusing entities, application data ingestion |

**Note:** Per-node `MERGE` can still produce incorrect results if the property used as the key is not unique or is poorly chosen. Good clause structure only works effectively alongside business keys and constraints.

### 4.2. When Both Nodes Must Already Exist: MATCH + MERGE

Sometimes the application must **refuse to create a relationship if the person or project does not exist**, meaning it must not auto-create missing nodes. Use `MATCH`:

~~~cypher
MATCH (p:Person {personId: 'P01'})
MATCH (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       type(r) AS relationshipType;
~~~

The two `MATCH` clauses bind `p` and `pr` to existing nodes, then `MERGE` handles only the relationship. If either `MATCH` returns no results, the query has no rows to proceed with and **does not create any relationship**. This differs from per-node `MERGE`, which can create missing nodes.

### 4.3. When Endpoints Are Bound While Still Using One MERGE

The term "full-pattern `MERGE`" only makes sense when considering **variable scope**. For example:

~~~cypher
MATCH (p:Person {personId: 'P01'})
MATCH (pr:Project {projectId: 'PR01'})
MERGE (p)-[r:WORKS_ON]->(pr)
RETURN r;
~~~

Even though the pattern inside `MERGE` has the shape of a path with two endpoints and a relationship, `p` and `pr` **were already bound** earlier, so duplicating the two nodes does not occur as in the unbound full-pattern `MERGE` example. You cannot judge solely by the number of parentheses in a clause whether nodes will be recreated.

## 5. ON CREATE SET and ON MATCH SET Apply Per MERGE

`ON CREATE SET` runs when the immediately preceding `MERGE` clause **newly creates** its pattern. `ON MATCH SET` runs when that `MERGE` clause **matches an existing pattern**.

Example of creating or finding a person by a stable key and updating their name:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.name = $name,
  p.createdAt = datetime()
ON MATCH SET
  p.name = $name,
  p.updatedAt = datetime()
RETURN p;
~~~

`personId` is the match key. When the node is new, `createdAt` is assigned; when the node is found, `name` and `updatedAt` are updated.

### 5.1. Combining Three MERGEs, Placing Properties in the Right Spot

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.name = $personName,
  p.createdAt = datetime()
ON MATCH SET
  p.name = $personName

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET
  pr.title = $projectTitle,
  pr.createdAt = datetime()
ON MATCH SET
  pr.title = $projectTitle

MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET
  r.role = $role,
  r.joinedOn = date(),
  r.createdAt = datetime()
ON MATCH SET
  r.role = $role,
  r.updatedAt = datetime()

RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

Here:

- The first `ON CREATE/ON MATCH` group belongs to **the Person node MERGE clause**.
- The next group belongs to **the Project node MERGE clause**.
- The final group belongs to **the WORKS_ON relationship MERGE clause**.

This lets you separate write policies for each entity and relationship. For a link type that only needs to store one `WORKS_ON` relationship per person–project pair, `role` is typically an **updated property** on the relationship, not part of the match key.

### 5.2. Do Not Put Frequently Changing Data in the MERGE Key

Error-prone approach:

~~~cypher
MERGE (p:Person {
  personId: $personId,
  name: $personName,
  department: $department
});
~~~

If an employee transfers departments or changes their name, the new pattern differs from the old one. Neo4j may try to create another node with the same `personId`; with a unique constraint, an error will occur.

Better approach:

~~~cypher
MERGE (p:Person {personId: $personId})
SET p.name = $personName,
    p.department = $department
RETURN p;
~~~

**Rule:** properties inside the `MERGE` pattern should describe **stable identifying conditions** of the entity; frequently changing properties are updated via `SET` or `ON CREATE/ON MATCH` branches. If a business key itself can change, consider using a different stable identifier.

## 6. Constraints and Indexes: Preserving Identity

To limit duplicates when multiple users or threads write concurrently, create **unique constraints** on business keys.

Example on a learning Neo4j database supporting this constraint syntax:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT project_projectId_unique IF NOT EXISTS
FOR (pr:Project)
REQUIRE pr.projectId IS UNIQUE;
~~~

When creating a constraint, Neo4j requires existing data to satisfy the uniqueness condition. If multiple nodes share the same key, creating the constraint will fail and duplicate records must be resolved first.

### 6.1. What Constraints Do and Do Not Do

Unique constraints help:

- Prevent two nodes with the same label from having the same constrained key value.
- Preserve business keys when multiple transactions compete.
- Provide the basis for exact lookups by `personId` or `projectId`; node uniqueness constraints are backed by an index that speeds up queries.

However, constraints **do not**:

- Turn a full-pattern `MERGE` into "match existing nodes and create only the relationship."
- Automatically determine what the right business key is.
- Guarantee at most one relationship between two nodes without relationship-level policies/constraints and concurrency control.

A node with a unique constraint on `personId` can still lack `personId` unless an appropriate existence constraint is also present. Therefore, always validate inputs.

### 6.2. MERGE and NULL

Do not use a `null` value for an identifying property in a `MERGE` pattern:

~~~cypher
// If $personId = null, the MERGE statement may raise an error
MERGE (p:Person {personId: $personId});
~~~

Validate `personId` and `projectId` at the application layer before sending the query. Avoid creating placeholder nodes with keys such as empty strings just to bypass `null` checks; they can corrupt data.

### 6.3. Parallel Relationships and Concurrent Writes

`MERGE (p)-[:WORKS_ON]->(pr)` looks for a matching relationship between two nodes **with the specified type and direction**. When a matching relationship already exists, `MERGE` normally reuses it, but if **multiple relationships matching the pattern** already exist beforehand, matching can return **multiple rows**. `MERGE` does not automatically delete pre-existing duplicate relationships.

Under concurrent writes, you must still design proper transactions and integrity mechanisms. A **node** unique constraint does not automatically prevent duplicate **relationships**. If business rules require identifying each relationship individually, consider a business key on the relationship with an appropriate constraint when supported by your Neo4j version/edition, while also enforcing consistency in the application. Do not treat `MERGE` alone as an absolute guarantee for every concurrent write race.

## 7. Should Relationship Properties Participate in Identification?

The same two nodes can have multiple `WORKS_ON` relationships if the model allows multiple assignments.

**Scenario A — Each person has only one current assignment per project:** the relationship type and two endpoints suffice for identification, while `role` is updated.

~~~cypher
MATCH (p:Person {personId: $personId})
MATCH (pr:Project {projectId: $projectId})
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.startedOn = date()
SET r.role = $role
RETURN r;
~~~

If the role changes from `Backend` to `Tech Lead`, the same relationship is updated (assuming input data has no duplicate relationships and each endpoint is uniquely identified).

**Scenario B — Need to store multiple independent assignment periods:** the relationship must have an identifier like `assignmentId`, or be modeled as an `Assignment` node, depending on the model.

~~~cypher
MATCH (p:Person {personId: $personId})
MATCH (pr:Project {projectId: $projectId})
MERGE (p)-[r:WORKS_ON {assignmentId: $assignmentId}]->(pr)
ON CREATE SET r.startedOn = date($startDate)
SET r.role = $role
RETURN r;
~~~

Query B distinguishes relationships by `assignmentId` on **the two existing endpoints**. If the integrity rule requires `assignmentId` to be globally unique across that relationship type, design an appropriate constraint and handle conflicts. If an `assignmentId` in a record could point to two different endpoints, define a data remediation policy because `MERGE` anchored on both endpoints does not move an existing relationship.

### 7.1. Relationship Direction Is Part of the Pattern

~~~cypher
MERGE (a)-[:REPORTS_TO]->(b);
~~~

is not the same pattern as:

~~~cypher
MERGE (b)-[:REPORTS_TO]->(a);
~~~

For directional relationships such as `REPORTS_TO`, `WORKS_ON`, and `OWNS`, you must write the right direction. Cypher permits undirected `MERGE` patterns in certain cases, but when a relationship must be created, Neo4j picks an arbitrary direction, so this should be avoided when business logic depends on direction.

## 8. Runnable Comparison Example: Two Existing Nodes

**Assumption:** the following examples run in a test environment with two nodes:

~~~cypher
CREATE
  (:Person {personId: 'P-MERGE-01', name: 'An'}),
  (:Project {projectId: 'PR-MERGE-01', title: 'Atlas'});
~~~

Run this setup step **only once** on test data that does not yet contain those two keys. The step below verifies them:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
RETURN p.personId AS personId, pr.projectId AS projectId;
~~~

### 8.1. Full-Pattern Style That Easily Causes Duplicates

~~~cypher
MERGE (p:Person {personId: 'P-MERGE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-MERGE-01'})
RETURN p, r, pr;
~~~

If `WORKS_ON` does not yet exist between the two nodes and there are no unique constraints, this operation can create **two additional nodes with the same business IDs**. If unique constraints exist, the operation can fail due to duplicate keys.

**Do not run this query on real data just to test.** Practice on a separate test graph, or use `EXPLAIN` to view the plan without executing the write.

### 8.2. Style That Reuses Existing Nodes

Starting from the initial state with two unique nodes and no relationship:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.role = 'Backend', r.createdAt = datetime()
ON MATCH SET r.role = 'Backend'
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

The first run creates the relationship, **without creating additional nodes**. Re-running when only one matching relationship exists will reuse that relationship. The critical condition is that each `MATCH` finds exactly one endpoint.

Verify the nodes and relationship:

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
RETURN count(p) AS personCount;
~~~

~~~cypher
MATCH (pr:Project {projectId: 'PR-MERGE-01'})
RETURN count(pr) AS projectCount;
~~~

~~~cypher
MATCH (p:Person {personId: 'P-MERGE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-MERGE-01'})
RETURN count(r) AS relationshipCount;
~~~

If starting from exactly two unique nodes and running the `MATCH` + `MERGE` query above once, the three expected results are `1`, `1`, `1` respectively.

### 8.3. When Data Might Be Missing Nodes

If the goal is to create the person or project when missing, use per-entity `MERGE`:

~~~cypher
MERGE (p:Person {personId: 'P-MERGE-02'})
ON CREATE SET p.name = 'Bình'
MERGE (pr:Project {projectId: 'PR-MERGE-02'})
ON CREATE SET pr.title = 'Knowledge Search'
MERGE (p)-[:WORKS_ON]->(pr)
RETURN p.personId AS personId, pr.projectId AS projectId;
~~~

Whether the two nodes already exist or not, this approach can find/create each node and then find/create the relationship. When data may be written concurrently, add constraints and control transactions.

## 9. Bulk Creation or Linking with UNWIND

Applications frequently receive a list of assignments, each containing person ID, project ID, and role.

Example parameter structure:

~~~json
{
  "assignments": [
    {
      "personId": "P01",
      "personName": "An",
      "projectId": "PR01",
      "projectTitle": "Atlas",
      "role": "Backend"
    },
    {
      "personId": "P02",
      "personName": "Bình",
      "projectId": "PR01",
      "projectTitle": "Atlas",
      "role": "Data Engineer"
    }
  ]
}
~~~

Query:

~~~cypher
UNWIND $assignments AS row
MERGE (p:Person {personId: row.personId})
ON CREATE SET p.name = row.personName
MERGE (pr:Project {projectId: row.projectId})
ON CREATE SET pr.title = row.projectTitle
MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
SET r.role = row.role
RETURN count(r) AS processedAssignments;
~~~

With two valid input rows and no duplicate keys in the data:

- Two Person nodes are found/created by `personId`.
- One Project node is found/created by `projectId` even though `PR01` appears in multiple rows.
- `WORKS_ON` relationships are found/created between each person and the corresponding project.
- `count(r)` counts the number of processed rows with a matched relationship; **not** the number of relationships newly created in this run.

If the same list is reloaded, `MERGE` per entity and relationship avoids recreating the same pattern under normal conditions; however, key constraints, transactions, and input validation are still required to ensure consistency when multiple processes execute concurrently. For large datasets, batch appropriately and monitor query plans.

## 10. Connecting with the Java Driver and Spring Data Neo4j

When sending queries through the Neo4j Java Driver, use parameters instead of concatenating user data into Cypher strings. Example:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class AssignmentService {
    private final Driver driver;

    public AssignmentService(Driver driver) {
        this.driver = driver;
    }

    public void assign(String personId, String projectId, String role) {
        String cypher = """
            MERGE (p:Person {personId: $personId})
            MERGE (pr:Project {projectId: $projectId})
            MERGE (p)-[r:WORKS_ON]->(pr)
            SET r.role = $role
            """;

        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run(cypher, Map.of(
                    "personId", personId,
                    "projectId", projectId,
                    "role", role
                )).consume();
                return null;
            });
        }
    }
}
~~~

This snippet illustrates sending a query with multiple `MERGE` clauses inside a write transaction; the `Driver` object's lifecycle is managed by the application. In real systems, validate parameters, use unique keys, specify the database, and handle transaction errors appropriately.

With **Spring Data Neo4j**, entity classes and repositories help map nodes and relationships. However, saving a Java object does not replace understanding individual Cypher pattern semantics. For custom queries, the same principle holds: identify each node with a stable key before finding/creating relationships. Clearly distinguish sync writes, history creation, and property updates to avoid creating unintended graph structures.

## 11. Performance and Operations

Using per-node `MERGE` requires lookup operations on each label and key, so performance depends on the data and indexes/constraints:

- Create **unique constraints** on business keys before bulk importing data, once existing data is valid.
- Specify clear labels and key properties such as `:Person(personId)`, `:Project(projectId)`.
- Avoid using continuously changing properties as keys for `MERGE`, which causes the system to lose its ability to re-find entities.
- Check whether `MATCH` returns exactly one record per key. If it returns multiple records, the number of paired rows and processed relationships can grow unexpectedly.
- Use `EXPLAIN` to inspect the plan **without executing the write statement**. `PROFILE` executes the query to measure actual statistics, so only use it with write statements on controlled test data.
- Choose a reasonable batch size when using `UNWIND`; monitor constraint errors, processed row counts, and newly created node/relationship counts.

Common issues:

| Symptom | Cause | Fix |
|---|---|---|
| Two nodes share the same `personId` after linking | Full-pattern `MERGE` attempted to create an entire new path | `MERGE` each node or `MATCH` endpoints, then `MERGE` the relationship |
| Full-pattern `MERGE` throws duplicate key error | Constraint blocked creating a new node with the same key when the relationship was missing | Separate node identification from relationship creation |
| Updating a person's name causes a constraint error | Included `name` inside the node's `MERGE` pattern | `MERGE` on a stable key, use `SET` to update the name |
| Each role creates a different relationship | `role` was placed in the match pattern despite being a mutable property | `MERGE` the relationship by endpoints and type, then `SET r.role` |
| One statement returns multiple rows and updates multiple relationships | Data already contained duplicate relationships or `MATCH` matched multiple nodes | Verify endpoint uniqueness and clean up old data |
| Relationship direction is reversed | Wrong arrow direction used in `MERGE` | Standardize direction conventions for each relationship type |
| `MERGE` fails on missing key value | Value used in pattern is `null` | Validate identifiers before the transaction |

## 12. Self-Check Exercises

### Exercise 1 — Predict the Outcome

Suppose the graph **only contains**:

~~~cypher
CREATE (:User {userId: 'U01'});
CREATE (:Group {groupId: 'G01'});
~~~

No `MEMBER_OF` relationship exists yet. No unique constraints are applied.

Statement A:

~~~cypher
MERGE (:User {userId: 'U01'})
      -[:MEMBER_OF]->
      (:Group {groupId: 'G01'});
~~~

Statement B (run against another copy of the initial data state):

~~~cypher
MERGE (u:User {userId: 'U01'})
MERGE (g:Group {groupId: 'G01'})
MERGE (u)-[:MEMBER_OF]->(g);
~~~

**Question:** Which statement can create additional nodes with the same business keys?

<details>
<summary>Answer</summary>

- **A:** Does not find the full pattern. It can create an additional `User`, an additional `Group`, and a relationship connecting the two new nodes; if unique constraints exist on both keys, it can raise an error instead of creating duplicates.
- **B:** Each node is found and reused, and the final `MERGE` creates the relationship between the two existing nodes. Given one node per key and no existing relationship, no additional nodes are created.

</details>

### Exercise 2 — Write an Appropriate Query

Requirement: user `U02` and group `G02` **must already exist**; create the `MEMBER_OF` relationship if missing, preserve `joinedOn` from initial creation, and allow updating `role` on every call.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (u:User {userId: 'U02'})
MATCH (g:Group {groupId: 'G02'})
MERGE (u)-[m:MEMBER_OF]->(g)
ON CREATE SET m.joinedOn = date()
SET m.role = $role
RETURN u.userId AS userId, g.groupId AS groupId, m.role AS role;
~~~

If an endpoint is not found, the query creates neither new nodes nor a relationship.

</details>

### Exercise 3 — Choosing the Key in MERGE

For user data, compare these two patterns:

~~~cypher
MERGE (u:User {userId: $userId, displayName: $displayName})
~~~

~~~cypher
MERGE (u:User {userId: $userId})
SET u.displayName = $displayName
~~~

If a user changes their display name, which statement is more stable? **Answer:** the second statement, because it uses `userId` for identification and updates `displayName` separately.

## 13. Summary

| Need | Appropriate Query Pattern |
|---|---|
| Need an entire path pattern and definitely want to find/create **the whole pattern** | `MERGE (a:Label {...})-[:TYPE]->(b:Label {...})`, understanding full-pattern matching rules |
| Need to find/create each entity then connect them | `MERGE (a:Label {id: ...}) MERGE (b:Label {id: ...}) MERGE (a)-[:TYPE]->(b)` |
| Both endpoints **must already exist** | `MATCH (a:Label {id: ...}) MATCH (b:Label {id: ...}) MERGE (a)-[:TYPE]->(b)` |
| Need to update mutable properties | `MERGE` by stable key, then `SET` or `ON CREATE/ON MATCH SET` |
| Need to avoid duplicate data by business key | Appropriate constraints, stable keys, and transaction management; validate input data |

**Core takeaway:** `MERGE` is a find-or-create operation **on the exact pattern within each clause**, not an automatic "stitch together" of disjoint nodes with matching properties. When nodes are independently identified, **bind each endpoint first** before `MERGE`ing the relationship between them.

**Connection to next lessons:** understanding `MERGE` helps you learn `SET`, `REMOVE`, `DELETE`, batch data imports, constraint/index design, reading query plans, and running Cypher queries in the Java Driver or Spring Data Neo4j.
