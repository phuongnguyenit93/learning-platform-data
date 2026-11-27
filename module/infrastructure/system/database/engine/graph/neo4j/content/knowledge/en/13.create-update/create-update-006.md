# REMOVE to Remove Properties or Labels in Neo4j

> **Chapter:** Create and Update  
> **Module:** `DATABASE_ENGINE_GRAPH_NEO4J` — using Neo4j to model connected data as a *property graph* and query relationships and paths with Cypher.

In a graph system, data is not only created and updated; sometimes we need to **remove a property that is no longer relevant** or **strip a classification label** from a node. For example, an employee no longer has a nickname, a project participation relationship no longer carries a temporary note, or a person stops belonging to `:Contractor` while remaining a `:Person`. Cypher's **`REMOVE`** clause handles these changes.

The key point of this lesson: `REMOVE` **does not delete nodes, relationships, or the entire graph**. It removes **properties** from nodes/relationships, or **labels** from nodes. When you want to delete graph elements themselves, you must use other operations such as `DELETE` or `DETACH DELETE`, which carry their own effects and risks.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish node properties, relationship properties, node labels, and relationship types in the property graph model.
2. Use `MATCH ... REMOVE` to drop one or more properties from an existing node or relationship.
3. Use `REMOVE n:Label` to strip a label and understand its impact on label-based queries.
4. Distinguish `REMOVE n.property`, `SET n.property = null`, `SET n += {property: null}`, and `SET n = map`.
5. Understand the differences between `REMOVE` and `DELETE`, `DETACH DELETE`, and `SET` when modifying data.
6. Assess the impact of constraints, indexes, bulk queries, transactions, and Java Driver/Spring Data Neo4j layers.
7. Build a safe property/label removal workflow that can be verified before and after writing.

## 2. Recap of the Property Graph Model

Consider the following graph:

~~~text
(:Person:Employee {
    personId: 'P001',
    name: 'An',
    nickname: 'An Neo',
    department: 'Engineering'
})
         |
         | [:WORKS_ON {
         |    role: 'Backend',
         |    temporaryNote: 'Data handover'
         | }]
         v
(:Project {projectId: 'PR001', title: 'Atlas'})
~~~

| Component | Example | Meaning |
|---|---|---|
| Node | `(p)` | An entity such as a person, project, course, etc. |
| Node label | `:Person`, `:Employee` | Node classification; multiple labels can exist on one node |
| Node property | `p.nickname` | Key-value data attached to the node |
| Relationship | `(p)-[r]->(pr)` | Directed connection between two nodes |
| Relationship type | `:WORKS_ON` | Meaning of the relationship; each relationship has one type |
| Relationship property | `r.temporaryNote` | Key-value data belonging to the connection itself |

The following two commands change **different things**:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname
RETURN p;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Employee
RETURN p;
~~~

The first command removes the `nickname` property; the second removes the `Employee` label. The `Person` node and its relationships remain intact unless another delete operation is run.

### 2.1. Quick Behavior Table

| Syntax | Effect | Preserved Components |
|---|---|---|
| `REMOVE p.nickname` | Drops the `nickname` property from node `p` | Node, labels, other properties, relationships |
| `REMOVE r.temporaryNote` | Drops a property from relationship `r` | Relationship, both endpoints, other properties |
| `REMOVE p:Employee` | Strips the `Employee` label from node `p` | Node, other labels, properties, and relationships |
| `DELETE p` | Deletes the node if no relationships remain attached | Outside the scope of `REMOVE` |
| `DETACH DELETE p` | Deletes the node along with all attached relationships | Outside the scope of `REMOVE` |

There is no way to use `REMOVE` to directly "strip" the type of a `WORKS_ON` relationship. If you need to change a relationship's type, you must remodel the link, typically by creating a relationship of the new type and handling the old relationship within an appropriate transaction.

## 3. REMOVing a Node Property

Basic syntax:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN p.personId AS personId,
       p.name AS name,
       p.nickname AS nickname;
~~~

Meaning:

1. `MATCH` locates the node identified by `personId`.
2. `REMOVE p.nickname` drops the **`nickname` property key** from the matched node.
3. `RETURN` reads back the fields. After removal, `p.nickname` reads as `null` because that key no longer exists.

For example, suppose before the query:

~~~text
(:Person {
  personId: 'P001',
  name: 'Nguyễn An',
  nickname: 'An Neo',
  department: 'Engineering'
})
~~~

After `REMOVE p.nickname`:

~~~text
(:Person {
  personId: 'P001',
  name: 'Nguyễn An',
  department: 'Engineering'
})
~~~

Only `nickname` disappears. The business key `personId`, `name`, and `department` remain preserved.

### 3.1. What If the Property Does Not Exist?

Running `REMOVE p.nickname` on a node that already lacks `nickname` does not need to create any property. In other words, repeating the removal of an already-absent property does not delete the node or generate new data.

Therefore, considering **property state** alone, removing a key can be repeated and still yield "key absent." However, this does not replace transaction checks, write authorization, or data constraints.

### 3.2. What If MATCH Finds No Node?

~~~cypher
MATCH (p:Person {personId: 'P-DOES-NOT-EXIST'})
REMOVE p.nickname
RETURN p;
~~~

If no node is found, zero rows reach `REMOVE` and the query creates no node. This differs from `MERGE`, which can create a new pattern when none matches.

To see how many nodes were selected for the operation, you can use:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN count(p) AS matchedNodes;
~~~

`matchedNodes` is the number of matched and processed nodes, **not necessarily the number of properties actually removed**: some nodes may already have lacked `nickname`.

## 4. REMOVing Multiple Properties in One Query

`REMOVE` accepts multiple comma-separated items:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname, p.temporaryPhone, p.legacyCode
RETURN p.personId AS personId, properties(p) AS remainingProperties;
~~~

The query drops the three keys if they exist, keeping all unspecified properties intact. The `properties(p)` function returns a map of the node's remaining properties.

Example with product data:

~~~cypher
MATCH (pr:Product {sku: 'SKU001'})
REMOVE pr.oldPrice, pr.importBatchId
SET pr.updatedAt = datetime()
RETURN pr.sku AS sku, properties(pr) AS properties;
~~~

Here:

- `REMOVE` drops two obsolete fields.
- `SET` records the update timestamp.
- Both operations happen within the same query and its transaction.

**Note:** updating `updatedAt` as above changes the timestamp on every run even if the properties to remove are already gone. If business rules require avoiding side effects when nothing changed, check beforehand or add an appropriate conditional mechanism.

### 4.1. Mixing Properties and Labels in REMOVE

A single clause can specify removing both properties and labels:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname, p:Contractor
RETURN labels(p) AS labels,
       properties(p) AS properties;
~~~

The node still keeps other labels like `Person` and `Employee` if they already exist. Make sure you understand both changes before combining them in one query.

## 5. REMOVing Relationship Properties

Properties do not live only on nodes. A relationship can also hold `role`, `since`, `notes`, or other data.

Suppose:

~~~text
(:Person {personId: 'P001'})
   -[:WORKS_ON {
       role: 'Backend',
       temporaryNote: 'Handling pilot phase',
       startedOn: 2026-01-15
   }]->
(:Project {projectId: 'PR001'})
~~~

To remove the temporary note from **the relationship itself**, first find the relationship and bind it to variable `r`:

~~~cypher
MATCH (p:Person {personId: 'P001'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR001'})
REMOVE r.temporaryNote
RETURN p.personId AS personId,
       pr.projectId AS projectId,
       properties(r) AS relationProperties;
~~~

After the query, `r.role` and `r.startedOn` still exist. The `WORKS_ON` relationship and both endpoint nodes are not deleted.

### 5.1. Multiple Relationships May Match

If the database has multiple `WORKS_ON` relationships with the same type, direction, and endpoint pair, `MATCH` can return multiple results; `REMOVE r.temporaryNote` applies to **each matched relationship**.

For systems that distinguish assignments by an ID, add a relationship identifying key:

~~~cypher
MATCH (:Person {personId: $personId})
      -[r:WORKS_ON {assignmentId: $assignmentId}]->
      (:Project {projectId: $projectId})
REMOVE r.temporaryNote
RETURN r.assignmentId AS assignmentId,
       properties(r) AS properties;
~~~

This selects only the relationship with the requested `assignmentId`, though you still must ensure business-key uniqueness and design appropriate constraints if the system performs concurrent writes.

### 5.2. Why Can't You REMOVE a Relationship Type?

In a property graph, `:WORKS_ON` is the relationship's **type**, unlike a node label. `REMOVE r:WORKS_ON` is not a way to change a relationship's type. To retire a connection, decide based on business semantics:

- Drop only extra info: `REMOVE r.temporaryNote`.
- Mark the link inactive: `SET r.active = false` or `SET r.endedOn = date()`.
- Actually delete the link: `DELETE r`.
- Switch to another link type: create a relationship of the new type with the properties to preserve and handle the old relationship in the same transaction.

Do not delete a relationship when the requirement is only to remove a data field.

## 6. REMOVing Labels from a Node

A Neo4j node can carry multiple labels. For example:

~~~text
(:Person:Employee:Contractor {
  personId: 'P001',
  name: 'An'
})
~~~

When An transitions from contract staff to a full-time employee, the business may want to remove the `Contractor` label:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Contractor
RETURN labels(p) AS labels;
~~~

After the query, the node still carries `Person` and `Employee` (if present before), and all of the node's relationships remain intact. No new node is created.

### 6.1. Removing Multiple Labels

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Contractor:TemporaryStaff
RETURN labels(p) AS labels;
~~~

You can list labels as above to strip multiple labels from the same node. If a label does not exist on the node, removing it does not create any new node or label.

### 6.2. Labels Differ from Properties

The two statements below are not equivalent:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Manager
RETURN labels(p) AS labels;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.role
RETURN properties(p) AS properties;
~~~

- `REMOVE p:Manager` strips the `Manager` **classification**. Properties such as `role` do not automatically vanish.
- `REMOVE p.role` drops the `role` **property**. Any existing `Manager` label remains.

If the application uses both to represent permissions or titles, establish a synchronized update policy to avoid contradictory data.

### 6.3. Switching Labels with SET and REMOVE

Suppose a person previously had the `:Candidate` label and is now hired. You can run:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p:Candidate
SET p:Employee
RETURN p.personId AS personId, labels(p) AS labels;
~~~

`REMOVE` strips the old classification; `SET` adds the new classification. Using a single query clearly expresses the state transition.

This query **does not create** a new node if the person is not found. If business logic needs to create a new person, that is a separate `CREATE`/`MERGE` task.

### 6.4. Querying by Label After REMOVE

Before removing the `Employee` label:

~~~cypher
MATCH (p:Employee {personId: 'P001'})
RETURN p.name AS name;
~~~

After removing that label, `MATCH (p:Employee ...)` no longer finds node P001 (unless the label is re-added). However:

~~~cypher
MATCH (p:Person {personId: 'P001'})
RETURN p.name AS name, labels(p) AS labels;
~~~

still finds the node as long as it retains the `Person` label. If all labels are removed, the node becomes an **unlabeled node**, which can still exist along with its properties and relationships.

## 7. REMOVE vs. SET null and Replacing the Property Map

In Cypher, `null` **is not stored** as a normal property value. Assigning `null` to a property has the effect of removing that property.

### 7.1. Two Ways to Drop a Property

The two statements below produce the same final state for the `nickname` property:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname
RETURN p.nickname AS nickname;
~~~

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p.nickname = null
RETURN p.nickname AS nickname;
~~~

Both leave the `nickname` key absent from the node. `REMOVE` directly expresses the intent to **drop a property**, while `SET ... = null` is especially useful when the value to clear is computed via an expression.

### 7.2. Removing a Key Through a Map Patch

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p += {nickname: null}
RETURN properties(p) AS properties;
~~~

When using `SET p += map`, properties **absent from the map** are preserved; keys whose value is `null` are removed. The effect on `nickname` matches `REMOVE p.nickname`.

With parameters:

~~~json
{
  "personId": "P001",
  "patch": {
    "nickname": null,
    "department": "Platform"
  }
}
~~~

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch
RETURN properties(p) AS properties;
~~~

The query can simultaneously **remove `nickname`** and **update `department`**, provided you are certain that `null` in your protocol means "delete field" rather than "source did not send a value."

### 7.3. Do Not Confuse SET = map with Selective REMOVE

~~~cypher
MATCH (p:Person {personId: 'P001'})
SET p = {personId: 'P001', name: 'Nguyễn An'}
RETURN properties(p) AS properties;
~~~

`SET p = map` **replaces the entire property map**: every old key missing from the new map vanishes. This has a far broader impact than `REMOVE p.nickname`.

| Style | Unmentioned Old Keys |
|---|---|
| `REMOVE p.nickname` | Preserved, except `nickname` |
| `SET p.nickname = null` | Preserved, except `nickname` |
| `SET p += {nickname: null}` | Preserved, except `nickname` |
| `SET p = {name: 'An'}` | **Deleted entirely**, except the `name` key in the new map |

If you only need to drop a property, `REMOVE` usually expresses the intent most clearly. Use `SET = map` only when you genuinely want to replace the entire property state and have ensured all keys to keep are present in the map.

## 8. REMOVE Differs from DELETE and DETACH DELETE

Three groups of operations are easily confused:

~~~cypher
// Drop the nickname field; keep the node and relationships
MATCH (p:Person {personId: 'P001'})
REMOVE p.nickname;
~~~

~~~cypher
// Delete a specific relationship; both endpoint nodes are kept
MATCH (p:Person {personId: 'P001'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR001'})
DELETE r;
~~~

~~~cypher
// Delete the node along with all relationships directly attached to it
MATCH (p:Person {personId: 'P001'})
DETACH DELETE p;
~~~

`DELETE p` cannot delete a node that still has relationships attached unless those relationships are handled first; `DETACH DELETE p` deletes the node and its attached relationships together.

| Statement | Removes Property | Strips Node Label | Deletes Node | Deletes Relationship |
|---|---:|---:|---:|---:|
| `REMOVE p.nickname` | Yes, one key | No | No | No |
| `REMOVE p:Employee` | No | Yes | No | No |
| `DELETE r` | Along with relationship | No | No | Yes |
| `DELETE p` | Along with node | Along with node | Yes if no relationships remain | Does not auto-delete relationships |
| `DETACH DELETE p` | Along with node | Along with node | Yes | Yes, relationships attached to node |

**Principle:** when the requirement is merely "user removed phone number" or "employee no longer belongs to a category," do not use `DELETE`, because it removes the entity or connection itself.

## 9. Constraints, Indexes, and Required Data

Neo4j can use **constraints** and **indexes** to protect and look up data. When removing properties or labels, know which constraints apply.

### 9.1. Removing a Business Key Property

Suppose there is a constraint:

~~~cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

A unique constraint guarantees each `personId` value is unique across nodes with label `Person`, but **a uniqueness constraint alone does not guarantee every node has `personId`**. Therefore:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p.personId;
~~~

can destroy the ability to identify the node by its business key if no property existence constraint is also present. This is a **data risk**, even though the operation may be syntactically valid.

When the model requires a key to always exist, use constraints appropriate to your Neo4j version/edition and application-level policies. Existence or property-type constraints can cause `REMOVE` to fail rather than allowing a missing field.

### 9.2. Removing a Label Changes Constraint/Index Scope

If a constraint or index is defined for `:Employee(employeeId)`, stripping the `Employee` label from a node removes that node from the scope of queries/indexes targeting that label. This **does not delete the node's `employeeId` property**.

Example:

~~~cypher
MATCH (p:Person {personId: 'P001'})
REMOVE p:Employee
RETURN labels(p) AS labels, p.employeeId AS employeeId;
~~~

`employeeId` can remain even without the `Employee` label. When re-adding the label via `SET p:Employee`, constraints for that label apply again; invalid data can trigger an error when re-labeling.

### 9.3. Do Not Use REMOVE to Bypass Constraints

Technically, removing a label or property can change the set of data governed by a given constraint. However, **you should never use this as a shortcut to work around data conflicts**. Clarify entities, business rules, and normalization policies before modifying integrity-related properties/labels.

### 9.4. Designing Stable Keys

An update query typically begins with:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.legacyCode
RETURN p.personId AS personId;
~~~

`personId` should be a stable key. Avoid looking up targets by `name` when names are not unique. If a `MATCH` matches multiple nodes, `REMOVE` affects every matched node rather than picking "the right node."

## 10. REMOVE During Data Synchronization

In integrated systems, information may need to be removed because:

- An authoritative source confirms a field is no longer valid.
- A classification label changes with business state.
- Temporary data is cleaned up after completing a task.
- Retention policies require not keeping a certain kind of information.

However, "source value is `null`" and "source **requests deleting** the property" are not always synonymous.

### 10.1. Distinguishing Missing Fields, Null, and Explicit Delete Requests

Consider three messages from a source:

~~~json
{"personId": "P001", "department": "Data"}
~~~

~~~json
{"personId": "P001", "nickname": null}
~~~

~~~json
{"personId": "P001", "removeFields": ["nickname"]}
~~~

Depending on the protocol:

1. Omitting `nickname` may mean "do not change nickname."
2. `nickname: null` may mean "delete nickname" **or** "nickname unknown."
3. `removeFields` expresses an intentional delete request.

The application must define the protocol explicitly before translating inputs into Cypher. If clients can send arbitrary maps directly into `SET p += $patch`, `null` values can accidentally wipe out critical properties.

### 10.2. Controlling the Allowlist of Removable Fields

Suppose a service only permits removing `nickname` and `temporaryPhone`, and forbids removing `personId`, `createdAt`, `verified`, or fields managed by an authorization service.

You can use fixed queries per action:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.nickname
RETURN p.personId AS personId;
~~~

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p.temporaryPhone
RETURN p.personId AS personId;
~~~

For multiple optional fields, the application can validate the field list on the server side and construct the appropriate query from **allowlist-validated field names**. Never concatenate user-entered property names directly into raw Cypher strings; `$personId` parameterizes **values**, and does not magically make untrusted key names safe syntax elements.

### 10.3. Syncing Classification State

If a person transitions from `Contractor` to `Employee`:

~~~cypher
MATCH (p:Person {personId: $personId})
REMOVE p:Contractor
SET p:Employee,
    p.employmentStatus = 'active',
    p.updatedAt = datetime()
RETURN p.personId AS personId,
       labels(p) AS labels,
       p.employmentStatus AS employmentStatus;
~~~

This example uses `REMOVE` and `SET` to update **classification** and **status properties** in a single query. Decide consistently when labels represent roles, departments, or access permissions, especially if application permissions depend on labels.

## 11. Bulk REMOVE with UNWIND

During data cleanup, you often need to strip a legacy field across many nodes. `UNWIND` expands a list of IDs into rows:

~~~json
{
  "personIds": ["P001", "P002", "P003"]
}
~~~

~~~cypher
UNWIND $personIds AS id
MATCH (p:Person {personId: id})
REMOVE p.legacyCode
RETURN count(DISTINCT p) AS matchedPersons;
~~~

If the three IDs are unique and all three nodes exist, `matchedPersons` is typically `3`. If one ID does not exist, only the found nodes are processed.

**Metric note:** `matchedPersons` is the number of distinct nodes found, **not the number of properties actually removed**. A person might already have no `legacyCode`.

### 11.1. Bulk Label Removal

~~~cypher
UNWIND $personIds AS id
MATCH (p:Person {personId: id})
REMOVE p:TemporaryStaff
RETURN count(DISTINCT p) AS matchedPersons;
~~~

The query does not delete nodes or other labels. If duplicate records share an ID due to missing constraints, a single ID can match multiple nodes and all of them will be modified.

### 11.2. Scoping with WHERE

Sometimes an obsolete field needs to be removed only for a subset:

~~~cypher
MATCH (p:Person)
WHERE p.legacyCode IS NOT NULL
  AND p.department = 'Engineering'
REMOVE p.legacyCode
RETURN count(p) AS matchedPersons;
~~~

Pre-filtering with `WHERE` narrows down the target group. `IS NOT NULL` selects nodes that currently have a property value; since Neo4j does not store null properties as ordinary values, this condition also restricts to nodes that actually have the field to drop.

**Note:** `MATCH (p:Person)` can scan a large node set if no suitable condition/index exists. For large systems, inspect the query plan, batch the work, and execute during an appropriate maintenance window.

### 11.3. Transactions, Write Scope, and Repeatability

`REMOVE` is a write operation. For millions of records, a single transaction can cause heavy load. Split into reasonably sized batches, configure retry policies, and monitor impact.

Repeating `REMOVE p.legacyCode` on the same node after the field is already removed makes no further change to that field's state. However, if the same query also updates timestamps, counters, or other state, the overall transaction may no longer be side-effect-free on repeat runs.

## 12. Using REMOVE from the Neo4j Java Driver

Java applications should pass identifiers via **parameters** and execute writes in managed transactions. Example method to remove a person's nickname:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonCleanupService {
    private final Driver driver;

    public PersonCleanupService(Driver driver) {
        this.driver = driver;
    }

    public long removeNickname(String personId) {
        String cypher = """
                MATCH (p:Person {personId: $personId})
                REMOVE p.nickname
                RETURN count(p) AS matched
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of("personId", personId))
                      .single()
                      .get("matched")
                      .asLong()
            );
        }
    }
}
~~~

**Explanation:**

- `MATCH` identifies the node by `personId`. If no node exists, `count(p)` returns `0`.
- `REMOVE p.nickname` drops only the property, without deleting the node or relationships.
- `Map.of` requires a **non-null** `personId` parameter; validate identifiers before calling.
- `executeWrite` runs the callback inside a Driver-managed write transaction; on transient errors, the callback may be retried. Do not place non-idempotent external actions inside the callback.
- The returned value is the number of nodes found, not the number of properties actually changed. In a system with unique keys, this count is usually `0` or `1`.

`Driver` should be lifecycle-managed at the application level. Depending on the system, specify the target database, timeout policy, write permissions, monitoring, and transaction error handling.

### 12.1. With Spring Data Neo4j

Spring Data Neo4j provides entity mapping and repository layers. When business logic needs to drop a property or label using custom Cypher, standard `REMOVE` syntax still applies in configured queries, such as via `@Query`.

Keep in mind:

- A Cypher command modifies stored data directly, whereas a previously loaded Java entity may still hold stale state in memory.
- Uncontrolled saving of a stale entity can overwrite or diverge from the `REMOVE` operation just executed, depending on mapping strategy and transaction boundaries.
- Labels can participate in how repositories find/map entities; stripping a label can cause repository queries targeting the old label to stop finding the record.

Design transactions and entity lifecycles carefully when mixing direct `REMOVE` queries with other repository operations.

## 13. Controlled Practice Workflow

The following example is written for a **test graph**. The steps use one person, one project, and one relationship, then remove properties or labels without deleting elements.

### Step 1 — Prepare Sample Data

Run once on a test dataset that does not yet contain the keys below:

~~~cypher
CREATE
  (p:Person:Employee:TemporaryStaff {
    personId: 'P-REMOVE-01',
    name: 'Lan',
    nickname: 'Lan Graph',
    legacyCode: 'OLD-01',
    department: 'Engineering'
  }),
  (pr:Project {
    projectId: 'PR-REMOVE-01',
    title: 'Graph Knowledge'
  }),
  (p)-[:WORKS_ON {
    role: 'Backend',
    temporaryNote: 'Handing over'
  }]->(pr);
~~~

Do not re-run `CREATE` on real data with the same business keys because it can create duplicates or be rejected by constraints.

### Step 2 — Inspect State Before Changes

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-REMOVE-01'})
RETURN labels(p) AS personLabels,
       properties(p) AS personProperties,
       type(r) AS relationType,
       properties(r) AS relationProperties,
       pr.title AS project;
~~~

Expected result shows labels `Person`, `Employee`, `TemporaryStaff`; person has `nickname` and `legacyCode`; relationship has `temporaryNote`.

### Step 3 — Remove Old Fields and Temporary Label

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
REMOVE p.nickname, p.legacyCode, p:TemporaryStaff
RETURN labels(p) AS labels, properties(p) AS properties;
~~~

After the operation, `p.name`, `p.department`, and `p.personId` remain preserved. The node can still be queried by `Person` and `Employee`.

### Step 4 — Remove Temporary Note on the Relationship

~~~cypher
MATCH (:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (:Project {projectId: 'PR-REMOVE-01'})
REMOVE r.temporaryNote
RETURN type(r) AS relationType, properties(r) AS properties;
~~~

The relationship still has `role = 'Backend'` and still connects the two nodes.

### Step 5 — Verify After Operations

~~~cypher
MATCH (p:Person {personId: 'P-REMOVE-01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR-REMOVE-01'})
RETURN p.personId AS personId,
       labels(p) AS labels,
       keys(p) AS personPropertyKeys,
       type(r) AS relationType,
       keys(r) AS relationPropertyKeys,
       pr.projectId AS projectId;
~~~

Expected:

- Still **one Person node**, **one Project node**, and the example `WORKS_ON` relationship.
- Node no longer has label `TemporaryStaff`.
- Node no longer has `nickname` or `legacyCode`.
- Relationship no longer has `temporaryNote`, but still has `role`.

These expectations assume initial data was unique by key and no concurrent operation interfered with the test dataset.

## 14. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `REMOVE` ran but no changes appeared | `MATCH` did not match; or field/label did not exist | Check keys, labels, matched row count, and prior state |
| One request removed properties from many nodes | `MATCH` used a non-unique name or overly broad condition | Use business keys; check `RETURN count(*)` before writing |
| Node no longer found by old query after label removal | Old `MATCH` filtered by the exact label that was removed | Query by a stable label; update entity selection criteria |
| Label removed but role property still exists | Labels and properties are independent components | Use `REMOVE n.role` if business logic requires deleting it too |
| Relationship property removed but relationship still exists | `REMOVE r.prop` only drops the property key | Use `DELETE r` only when the link itself must be deleted |
| Error when removing a required property | Constraint requires the property to exist or meet a rule | Check schema/constraints and data policies |
| Node can no longer be found by ID after field cleanup | Accidentally removed business key or replacement map omitted it | Protect identifiers; review `SET = map`/`+=` |
| `SET n = $map` wiped out other fields | `=` operator replaces all properties | Use `REMOVE` for specific fields or `+=` for patches |
| Null payload accidentally deleted a property | Blindly used `SET n.field = $value` when value was `null` | Define explicit API null semantics |
| Label removal caused repository to miss entity | Application query depends on the old label | Review mappings and queries after changing classifications |
| Large-scale cleanup increased system load | Single transaction wrote too many nodes/relationships | Batch operations, use keys/indexes, inspect query plans |

## 15. Self-Practice Exercises

### Exercise 1 — Removing Two Properties from a Node

**Requirement:** for the `User` node identified by `userId = 'U001'`, delete `middleName` and `temporaryEmail` while keeping `userId` and `fullName`.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (u:User {userId: 'U001'})
REMOVE u.middleName, u.temporaryEmail
RETURN u.userId AS userId, properties(u) AS properties;
~~~

Other properties remain unchanged.

</details>

### Exercise 2 — Removing an Outdated Label

**Requirement:** node `(:Person:Candidate {personId: 'P002'})` has become an employee. Remove `Candidate`, add `Employee`, and keep `Person` plus all properties.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (p:Person {personId: 'P002'})
REMOVE p:Candidate
SET p:Employee
RETURN p.personId AS personId, labels(p) AS labels;
~~~

`REMOVE` strips one label; `SET` adds the new label. The node remains intact.

</details>

### Exercise 3 — Distinguishing REMOVE and DELETE

Given the relationship:

~~~text
(:Student {studentId: 'S001'})
  -[:ENROLLED_IN {status: 'completed', note: 'Manual import'}]->
(:Course {courseId: 'C001'})
~~~

**Question:** write a query that deletes only `note`, preserving the relationship and `completed` status.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (:Student {studentId: 'S001'})
      -[r:ENROLLED_IN]->
      (:Course {courseId: 'C001'})
REMOVE r.note
RETURN properties(r) AS properties;
~~~

`DELETE r` would delete the entire relationship, which does not match the requirement.

</details>

### Exercise 4 — Error from Replacing the Entire Map

Suppose node `Employee` has:

~~~text
{employeeId: 'E001', name: 'Bình', department: 'Data', createdAt: ...}
~~~

You need to remove `department` while keeping the other fields. Compare:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
SET e = {employeeId: 'E001', name: 'Bình'};
~~~

and:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
REMOVE e.department;
~~~

**Question:** which query preserves `createdAt`?

<details>
<summary>Answer</summary>

The query `REMOVE e.department` drops only the `department` field and preserves `createdAt`. The query `SET e = {...}` replaces the entire property set; since the new map omits `createdAt`, that property is removed as well.

</details>

### Exercise 5 — Counting Processed Nodes

Suppose you need to remove `legacyFlag` from `Product` nodes whose `sku` is in `$skus`. Write a query returning **the number of distinct matched products**, avoiding confusion with the number of properties actually deleted.

<details>
<summary>Reference answer</summary>

~~~cypher
UNWIND $skus AS sku
MATCH (p:Product {sku: sku})
REMOVE p.legacyFlag
RETURN count(DISTINCT p) AS matchedProducts;
~~~

`matchedProducts` counts only matched nodes, including nodes that already lacked `legacyFlag`. To measure how many fields were actually removed, check the property's value/presence before modifying and compute dedicated statistics.

</details>

## 16. Summary

| Purpose | Suggested Cypher Syntax |
|---|---|
| Remove a node property | `MATCH (n:Label {id: $id}) REMOVE n.oldField` |
| Remove multiple properties | `REMOVE n.fieldA, n.fieldB` |
| Remove a relationship property | `MATCH (a)-[r:TYPE]->(b) REMOVE r.note` |
| Remove a node label | `REMOVE n:OldLabel` |
| Remove multiple labels | `REMOVE n:LabelA:LabelB` |
| Swap classification labels | `REMOVE n:OldLabel SET n:NewLabel` |
| Remove a property via null assignment | `SET n.field = null` |
| Remove a key via map patch | `SET n += {field: null}` |
| Replace all properties | `SET n = $fullSnapshot` — consider carefully |
| Permanently delete a relationship | `DELETE r` |
| Delete a node and its attached relationships | `DETACH DELETE n` — completely different from `REMOVE` |

**Takeaway:** `REMOVE` is the tool for **removing properties or labels** while preserving node and relationship structure. Because labels govern query scope and interact with indexes/constraints, and properties may hold identifying keys, choose the right target, right field, and right business rules before writing. When using Neo4j in ingestion, the Java Driver, or Spring Data Neo4j, identify nodes/relationships by stable keys, use parameters, manage transactions, and verify data after the operation.

Building on this knowledge, you can further distinguish `REMOVE` from `DELETE`, learn complex write patterns with `MERGE`/`SET`, and optimize update queries with indexes, constraints, `EXPLAIN`, and transaction management.
