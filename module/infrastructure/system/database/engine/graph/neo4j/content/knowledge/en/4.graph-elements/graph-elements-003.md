# Multiple Labels on a Single Node and Entity Classification Semantics

## 1. Learning Objectives

Neo4j stores connected data as a **property graph**: a **node** represents an entity, a **relationship** expresses a link between nodes, and a **property** describes facts. Alongside these, **labels** classify nodes so we can search, enforce data rules, and organize the model.

In the **Graph Elements** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson dives into an important feature: **a single node can carry multiple labels at the same time**. This is how Neo4j represents an entity belonging to multiple groups or fulfilling multiple roles while keeping a single node to connect with Cypher.

After this lesson, you will be able to:

- Explain why a node can have multiple labels and **does not need duplicate copies** for each role.
- Distinguish **node**, **label**, **property**, and **relationship** when classifying entities.
- Write Cypher to create, read, add, remove, and combine labels on the same node.
- Understand that a multi-label pattern such as `(p:Person:Employee)` requires the node to **simultaneously have all** specified labels.
- Design classifications aligned with business roles, queries, indexes, constraints, and data mapping in Java/Spring Data Neo4j.
- Recognize common mistakes: treating labels as automatic inheritance, creating one node per label, abusing labels to store property values, or creating duplicate nodes during `MERGE`.

## 2. What Is a Label and Why Does a Node Have Multiple Labels?

A **label** is a classification name attached directly to a node. A node can have **zero, one, or multiple labels**; the labels on the same node form a set, not an ordered list with business meaning.

For example, in an internal training system, Nguyễn An is a person, an employee, and also mentors newcomers:

```text
               THE SAME NODE
   ┌─────────────────────────────────┐
   │ :Person :Employee :Mentor       │
   │ personId: "P001"                │
   │ fullName: "Nguyễn An"           │
   │ department: "Engineering"       │
   └─────────────────────────────────┘
```

Cypher pattern:

```cypher
(an:Person:Employee:Mentor {
  personId: 'P001',
  fullName: 'Nguyễn An',
  department: 'Engineering'
})
```

Here:

| Component | Role | Example |
| --- | --- | --- |
| **Node** | Represents an entity with its own identity | A single node representing Nguyễn An |
| **Labels** | Groups/roles that the entity belongs to | `Person`, `Employee`, `Mentor` |
| **Properties** | Values describing the node | `personId`, `fullName`, `department` |
| **Relationships** | Links from the node to other nodes | `(an)-[:WORKS_AT]->(company)`, `(an)-[:MENTORS]->(junior)` |

If a model created a separate `:Person` node, `:Employee` node, and `:Mentor` node for **the same Nguyễn An** just to represent three roles, the application would have to synchronize names, IDs, statuses, and relationships across those copies. Attaching multiple labels to **one node** is usually the simpler choice when all three labels truly describe the same entity.

**Key point:** Having multiple labels **does not** mean having multiple nodes. Each node remains a single entity with its own set of properties and relationships.

## 3. Cypher Syntax for Multiple Labels

### 3.1. Creating a Node with Multiple Labels

In a practice database, run the following command once:

```cypher
CREATE (p:Person:Employee:Mentor {
  personId: 'ML-P001',
  fullName: 'Nguyễn An',
  department: 'Engineering',
  active: true
})
RETURN p;
```

The `:` separates labels attached to the **same variable `p`**. The syntax `:Person:Employee:Mentor` **does not** create three nodes.

Read the information back:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
RETURN p.personId AS personId,
       p.fullName AS fullName,
       labels(p) AS labels,
       properties(p) AS properties;
```

The `labels(p)` function returns a list of current labels. The list may contain `Person`, `Employee`, `Mentor`; **do not rely on label order** when checking results.

### 3.2. Specifying Multiple Labels in MATCH

```cypher
MATCH (p:Person:Employee)
RETURN p.personId AS id, p.fullName AS name;
```

This query finds nodes that have **both the `Person` label and the `Employee` label**. It does not mean "Person **or** Employee".

In other words:

```text
MATCH (p:Person)             → All nodes with the Person label
MATCH (p:Employee)           → All nodes with the Employee label
MATCH (p:Person:Employee)    → Intersection of both groups: having both labels
```

A `:Person:Employee:Mentor` node satisfies all three patterns above. A node carrying only `:Person` does not satisfy `(p:Person:Employee)`.

### 3.3. Adding Labels to an Existing Node

Suppose this person is also assigned a manager role:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Manager
RETURN labels(p) AS labels;
```

`SET p:Manager` attaches the `Manager` label to the existing node `p`; the `Person`, `Employee`, `Mentor` labels and all properties remain intact.

Multiple labels can be added in a single statement:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Trainer:Reviewer
RETURN labels(p) AS labels;
```

If a label already exists on the node, setting the same label again does not create a "duplicate" of that label.

### 3.4. Removing One or More Labels

When Nguyễn An is no longer a manager:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Manager
RETURN labels(p) AS labels,
       p.fullName AS fullName;
```

The `REMOVE p:Manager` command only removes the `Manager` label; **it does not delete the node, properties, or other labels**. Multiple labels can be removed together:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Trainer:Reviewer
RETURN labels(p) AS labels;
```

Distinguish these three operations:

| Syntax | Effect |
| --- | --- |
| `SET p:Mentor` | Adds the `Mentor` label to the node |
| `REMOVE p:Mentor` | Removes the `Mentor` label from the node |
| `DELETE p` | Deletes the **node**; if relationships still exist, handle connected relationships first or use a deletion operation that accounts for them |

Do not use `DELETE` when you only want to change classification.

## 4. Semantics of Multiple Labels: One Entity, Multiple Perspectives

Let us examine three common label usage patterns in modeling.

### 4.1. Base Type and Specialized Roles

```text
(:Person:Employee)
(:Person:Customer)
(:Person:Employee:Customer)
```

All three patterns can be valid. Someone who is both an employee and a customer can be represented by **one node** carrying all three labels. `MATCH (p:Customer)` will find that person; `MATCH (p:Employee)` will also find that same node.

However, **there is no automatic inheritance** between labels. Neo4j does not infer that "being an `Employee` guarantees being a `Person`". Only labels **explicitly attached** appear in `labels(p)` and match query patterns.

For example:

```cypher
CREATE (e:Employee {
  personId: 'ML-E001',
  employeeId: 'ML-E001',
  fullName: 'Bình'
})
RETURN labels(e) AS labels;
```

The node above only has the `Employee` label. It will **not** be returned by `MATCH (p:Person:Employee)` unless we explicitly add the `Person` label:

```cypher
MATCH (e:Employee {employeeId: 'ML-E001'})
SET e:Person
RETURN labels(e) AS labels;
```

Labels can express the idea of "specialized role belonging to a base type", but maintaining this rule is the responsibility of data design, write queries, and ingestion pipelines.

### 4.2. One Entity Participating in Multiple Business Contexts

In an educational platform, one person can simultaneously be `:User`, `:Learner`, and `:Instructor`:

```cypher
CREATE (u:User:Learner:Instructor {
  userId: 'ML-U001',
  displayName: 'Chi'
})
RETURN u;
```

When querying the learning dashboard, we use `MATCH (u:Learner)`. When displaying the instructor roster, we use `MATCH (u:Instructor)`. Both queries can point to **the same `userId`**.

This works well if the data truly shares one identity and lifecycle. If "instructor" represents an independent contract with multiple statuses, start dates, end dates, or separate links to multiple organizations, you may need an `:InstructorAssignment` node and relationships; a label alone may not suffice.

### 4.3. Classification for Querying and Data Rules

Labels commonly scope queries:

```cypher
MATCH (p:Person:Mentor)
RETURN p.fullName AS mentorName
ORDER BY mentorName;
```

Labels are also used in **index** and **constraint** definitions, such as requiring every `personId` to appear at most once within the `Person` group. This allows a flexible dataset to enforce integrity rules where needed.

## 5. Multiple Labels Are Set Intersection, Not Union

This is the most important point when reading a multi-label pattern.

Suppose the database has four nodes:

| Node | Labels |
| --- | --- |
| An | `Person`, `Employee`, `Mentor` |
| Bình | `Person`, `Employee` |
| Chi | `Person`, `Customer` |
| Dũng | `Organization` |

Expected results:

| Query | Returned Nodes |
| --- | --- |
| `MATCH (n:Person)` | An, Bình, Chi |
| `MATCH (n:Employee)` | An, Bình |
| `MATCH (n:Person:Employee)` | An, Bình |
| `MATCH (n:Person:Employee:Mentor)` | An |
| `MATCH (n:Organization)` | Dũng |

To find **Person or Organization**, avoid misinterpreting multi-label syntax as OR. A compatible and readable way to write it is:

```cypher
MATCH (n)
WHERE 'Person' IN labels(n)
   OR 'Organization' IN labels(n)
RETURN n;
```

This example illustrates OR semantics and is **not by default optimal for large graphs**, because `MATCH (n)` does not constrain nodes to an initial label. On large datasets, you can use separate query branches per label and combine results, or label expression syntax depending on your Cypher version.

### 5.1. Using WHERE to Express Label Conditions

```cypher
MATCH (p:Person)
WHERE p:Employee
RETURN p.personId, p.fullName;
```

In terms of label filtering, this is equivalent to:

```cypher
MATCH (p:Person:Employee)
RETURN p.personId, p.fullName;
```

If you need to inspect the label list using a function:

```cypher
MATCH (p:Person)
WHERE 'Employee' IN labels(p)
RETURN p.personId AS id;
```

`labels(p)` is suitable when you need to **inspect or display actual labels**; when the required labels are already known, prefer explicit label patterns so the query is readable and the optimizer sees the classification predicates directly.

### 5.2. Counting Nodes by Label and Label Intersection

```cypher
MATCH (p:Person)
RETURN count(p) AS totalPeople;

MATCH (p:Person:Employee)
RETURN count(p) AS peopleWhoAreEmployees;

MATCH (p:Person:Employee:Mentor)
RETURN count(p) AS employeesWhoAreMentors;
```

Because groups can **overlap**, the count of `Person` nodes and the count of `Employee` nodes do not represent disjoint sets. Do not sum them to compute "total people" when many nodes carry both labels.

## 6. When Should You Use a Label, a Property, or a Relationship?

An entity can be described by all three mechanisms; choose based on the **nature of the information** and query requirements.

| Need | Usually Suitable Representation | Example |
| --- | --- | --- |
| Classify an entity into meaningful groups/roles | **Label** | `:Person:Employee`, `:User:Instructor` |
| Store a descriptive, mutable value | **Property** | `department: 'Engineering'`, `status: 'ACTIVE'` |
| Connect this entity to another entity | **Relationship** | `(p)-[:WORKS_AT]->(c)` |
| Model a record with its own identity and lifecycle | **Separate node + relationship** | `(:Person)-[:HAS]->(:EmploymentContract)` |

### 6.1. Labels vs. Status Properties

For example, consider two representations:

```cypher
(:Employee:Active {employeeId: 'E001'})
(:Employee {employeeId: 'E001', status: 'ACTIVE'})
```

Both can have valid use cases, but you should not create a label for **every value** such as `:Status_ACTIVE`, `:Status_PENDING`, `:Status_SUSPENDED` just because a field has an enumerated set of values. When status changes frequently or needs value filtering/comparison, a **`status` property** is usually simpler.

Conversely, if a group has a stable meaning, is used across many queries, and has dedicated constraints/indexes or modeling policies, a **label** can be appropriate.

**Practical question:** "Employee" is a **type/role** of a person in the graph, whereas "Engineering" may simply be a **department value**. You do not necessarily need `:Engineering` or `:Finance` labels for each department—especially if you need rich information about departments, model a `:Department` node instead.

### 6.2. Labels vs. Relationships Between Entities

Attaching a `:Mentor` label to a person **does not indicate whom that person mentors**. If the domain needs to query "who mentors whom", you must store a relationship:

```cypher
MATCH (mentor:Person:Mentor {personId: 'ML-P001'})
MATCH (learner:Person {personId: 'ML-E001'})
CREATE (mentor)-[:MENTORS {startedOn: date()}]->(learner)
RETURN mentor.fullName AS mentorName,
       learner.fullName AS learnerName;
```

In the query above, the `Mentor` label classifies **a mentor**, while the `MENTORS` relationship type represents **a specific mentoring link**. Never use a label alone to replace information that has two endpoints.

### 6.3. When Should You Split into Multiple Nodes?

Having multiple roles **does not require** multiple nodes. However, when each role has a separate identifier, sensitive data requiring separate access control, independent change history, or complex relationships, a multi-node model may be more suitable.

For example, a `:Person` can have multiple `:Employment` records over time:

```text
(:Person)
    |
    +--[:HAS_EMPLOYMENT]--> (:Employment {startedOn, endedOn})
    |                                 |
    |                                 +--[:AT_COMPANY]--> (:Company)
    |
    +--[:HAS_EMPLOYMENT]--> (:Employment {startedOn, endedOn})
                                      |
                                      +--[:AT_COMPANY]--> (:Company)
```

The `Employment` node represents **a single job/contract** with its own lifecycle; the `Employee` label on `Person` (if used) only denotes a current classification or business convention and does not store contract history by itself.

## 7. Design Conventions and Consistency Across Labels

### 7.1. Choosing a Base Label for Entities with Identity

An easy-to-follow organization is:

```text
:Person + :Employee
:Person + :Customer
:Person + :Employee + :Mentor
```

In this model, `Person` is the base label, while `Employee`, `Customer`, and `Mentor` describe roles. The rule "every `Employee` also has `Person`" is an **application convention**, not an inheritance rule automatically enforced by Neo4j.

When writing data, clarify:

- Which roles may coexist, and which are mutually exclusive?
- Which roles are temporary, and which are long-lived?
- When removing a role, should data associated with that role be kept or removed?
- Which part of the application is authorized to modify labels?
- Which identifier guarantees the same person is not created as two separate nodes?

### 7.2. Avoiding Label Explosion

**Avoid** creating separate labels for each ID, date, user, or arbitrary value:

```text
(:Person_P001)
(:Person_P002)
(:Employee_2025)
(:Customer_HaNoi)
```

Such labels make the model hard to manage and continually change with data. Typically, represent them as:

```cypher
(:Person:Employee {
  personId: 'P001',
  joinedYear: 2025,
  city: 'Hà Nội'
})
```

Only create labels for **groups with modeling significance** that are explicitly used in queries or governance rules.

### 7.3. Consistent Naming and Casing

Neo4j label names are case-sensitive:

```text
:Person     differs from :person
:Employee   differs from :EMPLOYEE
```

The common convention for labels is singular nouns or role names in PascalCase: `Person`, `Employee`, `Instructor`, `Order`. Maintain consistency across Cypher queries, data ingestion, Java code, and mapping configurations.

## 8. Indexes, Constraints, and Label Scope

Labels participate in defining **the set of nodes to which an index or constraint applies**.

### 8.1. Consistent Business Identifier on the Base Label

In an example where `Person` is the base label, you can create a uniqueness constraint on `personId`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

This constraint means: **no two nodes carrying the `Person` label may have the same `personId` value**. It applies to `:Person`, `:Person:Employee`, and `:Person:Customer` nodes because all of them carry the `Person` label.

However:

- A unique constraint **does not automatically require** every `Person` node to have `personId`. Property existence constraints or node keys have specific support conditions depending on Neo4j version/edition.
- A node with only the `Employee` label and **without** `Person` falls outside the scope of `FOR (p:Person)`.
- Uniqueness on `Employee.employeeId` is a different scope from uniqueness on `Person.personId`; design keys according to how the application identifies entities.

### 8.2. Indexes for Role and Property Lookups

For example, frequently looking up employees by `employeeCode`:

```cypher
CREATE INDEX employee_code_idx IF NOT EXISTS
FOR (e:Employee)
ON (e.employeeCode);
```

And querying:

```cypher
MATCH (e:Employee {employeeCode: $employeeCode})
RETURN e;
```

Because labels do not alter node identity, a `:Person:Employee` node can be found via the `Person` label by `personId` or via the `Employee` label by `employeeCode`, provided values and configurations match.

A query with multiple labels like `MATCH (e:Person:Employee)` may receive different execution plans from the optimizer depending on statistics, indexes, property predicates, and Neo4j version. Do not assume that adding labels automatically makes every query faster.

Check with:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;

EXPLAIN
MATCH (e:Person:Employee {personId: $personId})
RETURN e;
```

`EXPLAIN` plans the query without executing it. `PROFILE` shows both the plan and actual execution metrics when running the query; use it in a test database or on safe queries to avoid unintended side effects.

## 9. MERGE and the Risk of Duplicate Nodes When Changing Roles

This is an important pitfall when working with multiple labels.

Suppose the database already has:

```cypher
CREATE (:Person {
  personId: 'ML-P003',
  fullName: 'Dũng'
});
```

When Dũng becomes an employee, **do not assume** that a `MERGE` pattern containing both labels will find the existing node:

```cypher
// NOT suitable when you only want to add a role to an existing Person
MERGE (p:Person:Employee {personId: 'ML-P003'})
RETURN p;
```

Because the existing node does not yet have `Employee`, **the full pattern does not match**. Without an appropriate constraint, the system could create **a second node** carrying both labels and the same `personId`. If a `Person.personId` uniqueness constraint exists, the duplicate creation will be rejected. Either way, this is not the intended way to update a role.

**A better approach:** identify the node by its base label and business key, then add the role label.

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName
SET p:Employee
RETURN p, labels(p) AS labels;
```

When run with `$personId = 'ML-P003'`, the query locates the existing `Person` node and attaches the `Employee` label to **that exact node**. A uniqueness constraint on `Person.personId` should be in place to protect identity under concurrent transactions.

If the record is already guaranteed to exist, you can write simply:

```cypher
MATCH (p:Person {personId: $personId})
SET p:Employee
RETURN p;
```

During bulk ingestion, perform identifier normalization and duplicate record merging according to business rules before attaching role labels; do not infer duplicate entities merely because two nodes share the same display name.

## 10. Behavior When Changing Labels: What to Watch Out For

Adding or removing a label only changes the **classification** of a node; it does not automatically:

- Create a new node or copy properties.
- Move data from one node to another.
- Create or delete relationships such as `WORKS_AT` or `MENTORS`.
- Set identifier keys or guarantee required fields expected by the application.
- Infer parent labels according to a classification convention.

However, **changing labels can change which indexes/constraints apply to the node**. For instance, adding the `Person` label to a node whose `personId` collides with another `Person` node will be blocked by a uniqueness constraint on `Person.personId`. Removing a label means queries filtering exclusively for that label will no longer return the node.

Illustrative example:

```cypher
MATCH (p:Person {personId: 'ML-P001'})
REMOVE p:Mentor
RETURN p.personId AS id, labels(p) AS labels;
```

After this command, the `MENTORS` relationship (if one exists) **remains stored**; the system needs explicit business logic if ending a role also means closing mentoring relationships or updating history.

## 11. Applications in Java Driver and Spring Data Neo4j

### 11.1. Passing Identifiers as Parameters

Applications should never concatenate user-provided `personId` values directly into Cypher strings. With the Neo4j Java Driver, execute parameterized queries:

```cypher
MATCH (p:Person {personId: $personId})
SET p:Mentor
RETURN p.personId AS id, labels(p) AS currentLabels;
```

The driver passes a corresponding parameter map, for example:

```json
{
  "personId": "ML-P001"
}
```

This separates **query structure** from **business values**. For requests that change role types based on input, never interpolate arbitrary label names from a request: use an allowlist of permitted labels and control queries according to the application model.

### 11.2. Entity Mapping and Multiple Labels

In Spring Data Neo4j, entity mapping configuration must align with the **node labels** being stored. With a model using `Person` as the base label and `Employee`/`Mentor` as roles, clearly decide:

1. Which label identifies the primary entity when loading/saving?
2. Who manages additional role labels and at which step in the workflow?
3. When updating an entity, must the application preserve role labels attached by other services?
4. When a user loses a role, how are related data and relationships handled?

Depending on the Spring Data Neo4j version and mapping configuration, saving an entity may manage the labels that the mapping considers owned by that entity. Therefore, verify actual mapping behavior before mixing manual Cypher label updates with entity saves on the same node.

## 12. Comprehensive Example: Classifying Users in a Learning Platform

Suppose a system has three users:

- An: user, learner, and instructor.
- Bình: user and learner.
- Chi: user and instructor.

Create a standalone dataset in a test database:

```cypher
CREATE (:User:Learner:Instructor {
  userId: 'ML-U101',
  displayName: 'An'
});
CREATE (:User:Learner {
  userId: 'ML-U102',
  displayName: 'Bình'
});
CREATE (:User:Instructor {
  userId: 'ML-U103',
  displayName: 'Chi'
});
```

### 12.1. Finding All Instructors

```cypher
MATCH (u:User:Instructor)
RETURN u.userId AS id, u.displayName AS name
ORDER BY id;
```

Expected result: **An** and **Chi**.

### 12.2. Finding Users Who Are Both Learners and Instructors

```cypher
MATCH (u:User:Learner:Instructor)
RETURN u.userId AS id, u.displayName AS name;
```

Expected result: **An**. The pattern matches the **intersection** of all three label groups.

### 12.3. Finding Learners Without the Instructor Role

```cypher
MATCH (u:User:Learner)
WHERE NOT u:Instructor
RETURN u.userId AS id, u.displayName AS name;
```

Expected result: **Bình**.

### 12.4. Granting the Instructor Role to Bình

```cypher
MATCH (u:User {userId: 'ML-U102'})
SET u:Instructor
RETURN u.displayName AS name, labels(u) AS labels;
```

Bình becomes a `:User:Learner:Instructor` node. No new user node is created; the query in Section 12.2 now returns **An and Bình**.

### 12.5. Statistics by Label

```cypher
MATCH (u:User)
RETURN count(u) AS totalUsers,
       sum(CASE WHEN u:Learner THEN 1 ELSE 0 END) AS learners,
       sum(CASE WHEN u:Instructor THEN 1 ELSE 0 END) AS instructors;
```

In the state **after Step 12.4**, there are 3 users, 2 learners, and 3 instructors. The sum of learners plus instructors is **greater than total users** because a single person can carry both labels; this is normal in a multi-label model.

## 13. Common Modeling Mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Creating separate nodes for `Person`, `Employee`, and `Mentor` of the same person | Data duplication, hard to synchronize and connect relationships | Attach the appropriate labels to a single node with a business identifier |
| Assuming `:Employee` automatically implies `:Person` | Queries by `Person` miss nodes | Explicitly attach the base label and validate ingested data |
| Reading `(n:Person:Employee)` as Person **or** Employee | Missing or incorrect query results | Understand this requires **having both labels simultaneously** |
| Using labels like `:User_123`, `:City_HaNoi` for every value | Label count grows with data, hard to maintain | Use properties or appropriate node + relationship modeling |
| Using `MERGE (p:Person:Employee {id: ...})` when the `Person` node already exists | Pattern fails to match and may attempt to create a duplicate node | `MERGE` or `MATCH` by base label + ID, then `SET p:Employee` |
| Assuming removing the `Mentor` label deletes `MENTORS` links | Old relationships persist, potentially violating business logic | Design workflows to update relationships/statuses per business rules |
| Turning all status values into dynamic labels | Hard to standardize and filter by value | Use a `status` property when representing a status value |
| Relying on element order in `labels(n)` | Results depend on unspecified implementation details | Check with list membership (`IN`) or set comparison |
| Assuming a constraint on `Person` applies to every `Employee` | May miss nodes without the `Person` label | Define constraints according to actual label scope and maintain label conventions |

## 14. Practice Exercises

Perform these in a test database so production data is unaffected.

**Exercise 1 — Querying label intersections.** Given:

```text
N1: (:Person:Employee:Mentor)
N2: (:Person:Employee)
N3: (:Person:Customer)
N4: (:Company)
```

Questions:

1. Which nodes does `MATCH (n:Person:Employee)` match?
2. Which nodes does `MATCH (n:Person:Mentor)` match?
3. How many nodes does `MATCH (n:Person)` match?

**Answer:** (1) N1, N2; (2) N1; (3) 3 nodes — N1, N2, N3.

**Exercise 2 — Updating roles without creating a new node.** Write Cypher to find the person with `personId = 'ML-P001'`, add `:Reviewer`, remove `:Mentor`, and return the remaining labels.

**Reference Answer:**

```cypher
MATCH (p:Person {personId: 'ML-P001'})
SET p:Reviewer
REMOVE p:Mentor
RETURN p.personId AS id, labels(p) AS labels;
```

**Exercise 3 — Identifying a MERGE bug.** The database already contains `(:User {userId: 'U100'})`. Why might `MERGE (:User:Instructor {userId: 'U100'})` fail to add the role to the existing node?

**Answer:** `MERGE` searches for the **entire pattern** with both labels and the property. Because the existing node lacks `Instructor`, it does not match. The proper way to add a role is to match the node by `:User` and `userId`, then `SET u:Instructor`; an appropriate constraint on the ID should exist to protect identity.

**Exercise 4 — Model design.** An employee worked at three companies, each time with a distinct position and start/end dates. Should you use three labels `:Employee_CompanyA`, `:Employee_CompanyB`, `:Employee_CompanyC`?

**Answer:** Usually no. Keep the `:Person` node (possibly with `:Employee` per current convention) and use `WORKED_AT` relationships with relevant properties, or an `Employment` node if each stint must be managed as its own entity. Each company should be a `:Company` node with a clear identifier.

## 15. Summary

- A Neo4j node can carry **multiple labels** while remaining **a single unique entity**.
- Labels classify entities by group/role; properties store values; relationships describe connections between entities.
- `MATCH (n:Person:Employee)` requires **both labels**. Neo4j does not infer that `Employee` is automatically a `Person`.
- Use `SET n:Role` to add and `REMOVE n:Role` to remove labels without creating or deleting nodes.
- Choose a stable base label and business identifier; consider constraint/index scope per label; be careful with `MERGE` on multi-label patterns when a node already exists.
- When data involves mutable values, separate identity, or two endpoints, evaluate **properties** and **relationships** before adding more labels.

Understanding the multi-label model helps you design consistent property graphs, write accurate role-based Cypher queries, and prepare for upcoming topics on relationships, paths, indexes/constraints, data ingestion, and integrating Neo4j with Java applications.
