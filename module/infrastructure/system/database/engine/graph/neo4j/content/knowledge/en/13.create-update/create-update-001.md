# CREATE to Create Nodes, Relationships, and Properties in Neo4j

> **Chapter:** Create and Update  
> **Topic:** Using Cypher's `CREATE` clause to create data according to the *property graph* model.

In the `DATABASE_ENGINE_GRAPH_NEO4J` module, Neo4j is used to represent connected data using **nodes**, **relationships**, and **properties**. Cypher is the language for describing graph patterns, querying relationships, and traversing paths. `CREATE` is the fundamental operation for adding new nodes or relationships and attaching labels, relationship types, and properties upon creation. It also serves as the foundation before learning `MATCH`, `MERGE`, `SET`, indexes, constraints, the Java Driver, or Spring Data Neo4j.

## 1. Learning Objectives

After this lesson, you can:

1. Explain which components `CREATE` creates in the property graph model and how to read Cypher patterns.
2. Create one or more nodes with labels and properties; create directed relationships and relationship properties.
3. Distinguish between **creating two new nodes** and **creating a relationship between two existing nodes**.
4. Use parameters to pass data, and `UNWIND` to create multiple records.
5. Identify the risk of creating duplicate data, use unique constraints when needed, and quickly distinguish `CREATE` from `MERGE`.

## 2. `CREATE` and the Property Graph Model

Consider the data "An works on the Knowledge Base project in a backend role":

~~~text
(:Person {personId: "P01", name: "An"})
       |
       | [:WORKS_ON {role: "backend"}]
       v
(:Project {projectId: "PR01", title: "Knowledge Base"})
~~~

| Component | Meaning | Representation in Cypher |
|---|---|---|
| Node | An entity, such as a person or a project | `(p)` |
| Label | Group/classification of a node | `(p:Person)` |
| Node property | Key-value data attached to a node | `{personId: 'P01', name: 'An'}` |
| Relationship | Connection between two nodes, directed | `(p)-[r]->(pr)` |
| Relationship type | Meaning of the connection | `[r:WORKS_ON]` |
| Relationship property | Information belonging to the connection itself | `[r:WORKS_ON {role: 'backend'}]` |
| Variable | Name used within query scope to reference a component | `p`, `pr`, `r` |

General syntax:

~~~cypher
CREATE (n:Label {key1: value1, key2: value2})
RETURN n;
~~~

- `CREATE` adds data matching the pattern written after the clause.
- Parentheses `(...)` represent a node; square brackets `[...]` represent a relationship.
- `:Person` is the node label; `:WORKS_ON` is the relationship type.
- `n` is a **query-scoped variable**, not a persistent ID of the node.
- `RETURN` lets you inspect the newly created data; it is optional if you only need to write data.

**Key takeaway:** `CREATE` always requests creating new components according to the pattern. It does not automatically look up an existing node or relationship with the same properties to reuse.

## 3. Creating Nodes and Properties

### 3.1. Creating a Simple Node

~~~cypher
CREATE (p:Person {
  personId: 'P-101',
  name: 'Nguyễn An',
  age: 27,
  active: true
})
RETURN p;
~~~

The query creates **one node** with the `Person` label and four properties. The `personId` value here is an **application-defined business key**, not Neo4j's internal ID.

You can create a node without properties or with multiple labels:

~~~cypher
CREATE (draft:Document)
RETURN draft;
~~~

~~~cypher
CREATE (engineer:Person:Employee {
  personId: 'P-102',
  name: 'Trần Bình',
  team: 'Platform'
})
RETURN engineer;
~~~

A node can carry multiple labels (for example, `Person` and `Employee`), helping classify it from multiple perspectives. You should name labels, relationship types, and properties with a consistent convention because Cypher is case-sensitive.

### 3.2. Property Value Types

Common examples:

~~~cypher
CREATE (p:Product {
  productId: 'SP-001',          // string
  price: 125000.50,            // float
  quantity: 12,                // integer
  available: true,             // boolean
  tags: ['database', 'graph'],  // list of primitive values
  releasedOn: date('2025-07-01'),
  createdAt: datetime()
})
RETURN p;
~~~

Neo4j supports property values such as strings, numbers, booleans, temporal types, spatial points, and homogeneous lists of supported primitive values. **You cannot store a nested map directly as a node or relationship property**. For example, `address: {city: 'Hanoi'}` is not a valid property to store as a raw map. Instead, use `city: 'Hanoi'` or model the address as a separate node when there are relationships to query.

`null` does not represent an "empty" value stored on a node: a property with value `null` is treated as nonexistent. For required fields, validate inputs and consider appropriate constraints.

### 3.3. Creating Nodes from Parameters

In applications, do not concatenate user input directly into Cypher strings. Pass values via parameters prefixed with `$`:

~~~cypher
CREATE (p:Person {
  personId: $personId,
  name: $name,
  age: $age
})
RETURN p.personId AS personId, p.name AS name;
~~~

Example parameter payload sent by the application:

~~~json
{
  "personId": "P-103",
  "name": "Lê Chi",
  "age": 25
}
~~~

Parameters make queries easier to reuse, handle strings containing quotes properly, and reduce the risk of Cypher injection through input values. Parameters in the example are used for **property values**; dynamic labels and relationship types follow specific rules depending on the Cypher version, so prefer static names when starting out.

### 3.4. Combining `CREATE` and `SET`

You can declare most properties directly inside the `CREATE` pattern; `SET` is useful when you need to add or compute properties after the node has been bound to a variable:

~~~cypher
CREATE (p:Person {personId: 'P-104'})
SET p.name = 'Phạm Dung',
    p.createdAt = datetime(),
    p.active = true
RETURN p;
~~~

`CREATE` creates the node; `SET` assigns or modifies properties on a referenced node or relationship. For updating **existing** data, you typically use `MATCH ... SET` rather than creating a new node.

## 4. Creating Relationships Between Nodes

### 4.1. Creating Two New Nodes and a Relationship Together

~~~cypher
CREATE
  (an:Person {personId: 'P-201', name: 'An'}),
  (binh:Person {personId: 'P-202', name: 'Bình'}),
  (an)-[r:KNOWS {since: 2024, context: 'same project'}]->(binh)
RETURN an.name AS fromPerson, type(r) AS relationshipType,
       r.since AS since, binh.name AS toPerson;
~~~

Structural result:

~~~text
(:Person {personId: 'P-201', name: 'An'})
         -[:KNOWS {since: 2024, context: 'same project'}]->
(:Person {personId: 'P-202', name: 'Bình'})
~~~

Within the same query, the variables `an` and `binh` are reused to refer to the exact nodes just created; `r` references the new relationship. `since` is a **relationship property** because it describes when the two people met, not an inherent attribute of a single person.

Relationships in Neo4j are **directed**. `(an)-[:KNOWS]->(binh)` has `an` as the source node and `binh` as the target node. When reading data, Cypher can match undirected patterns, but when creating data you should represent the proper business direction. Each relationship has exactly one type, such as `KNOWS` or `WORKS_ON`.

### 4.2. Creating a Relationship Between **Two Existing Nodes**

This is a common operation in applications. Suppose a person with `personId = 'P-201'` and a person with `personId = 'P-202'` already exist:

~~~cypher
MATCH (a:Person {personId: 'P-201'})
MATCH (b:Person {personId: 'P-202'})
CREATE (a)-[r:COLLABORATES_WITH {
  project: 'Graph project',
  startedOn: date('2025-04-01')
}]->(b)
RETURN a.name AS fromPerson, type(r) AS relation, b.name AS toPerson;
~~~

**Execution order:** `MATCH` finds and binds variables `a` and `b` to the existing nodes; `CREATE` creates only the new relationship between them. The query does not create two additional `Person` nodes.

If either `MATCH` finds no node, there are no rows passed to `CREATE`, so **no relationship is created**. If each `MATCH` matches multiple nodes, the query can create multiple relationships corresponding to the Cartesian product of matched pairs; a unique business key helps prevent this error.

**Common pitfall:** Writing `CREATE (a:Person {personId: 'P-201'})` on its own will create a new node even if a `Person` node with that `personId` already exists (unless a constraint causes the statement to fail). To use an existing node, find it with `MATCH` first.

### 4.3. Relationships Cannot Exist Independently

You cannot create a "dangling" relationship without both endpoints. A valid pattern must contain both a source node and a target node:

~~~cypher
CREATE (a:Author {authorId: 'A-301', name: 'Mai'})
       -[r:WROTE {year: 2026}]->
       (b:Book {bookId: 'B-301', title: 'Introduction to Graphs'})
RETURN a.name AS author, r.year AS year, b.title AS book;
~~~

Here, both nodes and the relationship are created in a single pattern. The variable names `a`, `r`, and `b` are valid only within the scope of the query.

## 5. Creating Multiple Nodes and Multiple Relationships in One Statement

`CREATE` accepts multiple comma-separated patterns. For example, a team working together on a project:

~~~cypher
CREATE
  (lan:Person {personId: 'P-401', name: 'Lan'}),
  (minh:Person {personId: 'P-402', name: 'Minh'}),
  (project:Project {
    projectId: 'PR-401',
    title: 'Neo4j Knowledge Base'
  }),
  (lan)-[:KNOWS {since: 2023}]->(minh),
  (lan)-[:WORKS_ON {role: 'Backend'}]->(project),
  (minh)-[:WORKS_ON {role: 'Data Engineer'}]->(project)
RETURN lan.name AS personA, minh.name AS personB,
       project.title AS projectName;
~~~

All components declared in this query reference the same `project` variable, so both `WORKS_ON` relationships point to the same project node. This approach is appropriate when **all entities need to be created from scratch**.

If the project already exists, you must `MATCH (project:Project {projectId: ...})` before `CREATE`ing the relationships; re-creating `project` each time will generate duplicate projects.

## 6. Bulk Creation with `UNWIND`

`UNWIND` expands each element of a list into a row for subsequent clauses to process. Given a parameter `$people` as a list of maps:

~~~json
{
  "people": [
    {"personId": "P-501", "name": "Hà"},
    {"personId": "P-502", "name": "Khoa"},
    {"personId": "P-503", "name": "Linh"}
  ]
}
~~~

Query to create three nodes:

~~~cypher
UNWIND $people AS item
CREATE (p:Person {
  personId: item.personId,
  name: item.name
})
RETURN count(p) AS createdCount;
~~~

If the input contains three valid elements and violates no constraints, `createdCount` is `3`. `UNWIND` is useful for importing application data or pre-processed datasets. For very large datasets, batch the data and control transaction sizes according to system capacity; re-running the same batch with `CREATE` still risks creating duplicate records.

## 7. Avoiding Duplicate Data and Ensuring Integrity

### 7.1. How Does `CREATE` Differ from `MERGE`?

| Clause | Core Behavior | When to Use |
|---|---|---|
| `CREATE` | Creates new components matching the pattern | When you are certain a new record/relationship is needed |
| `MATCH` | Finds existing components without creating anything | Connecting existing nodes or preparing updates |
| `MERGE` | Finds a matching pattern; if absent, creates it | When you want "exactly this pattern to exist" via find-or-create logic |
| `SET` | Assigns/changes labels or properties on referenced components | Adding or updating information |

For example, running the following statement **twice** on a database without constraints creates **two distinct nodes** with the same `personId`:

~~~cypher
CREATE (:Person {personId: 'P-601', name: 'Nga'});
~~~

To prevent two `Person` nodes from sharing the same business key `personId`, you can create a unique constraint before importing data:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

At this point, creating a node with the same `personId` as an existing node will be rejected due to a constraint violation. **A constraint does not turn `CREATE` into an update or "find-or-create"**: the query remains a creation request and may raise an error. On data that already contains duplicates, creating the constraint can also fail; you must clean up the data first.

When you genuinely need find-or-create semantics, consider `MERGE`:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.name = $name, p.createdAt = datetime()
RETURN p;
~~~

In this example, `personId` is the key used to identify the person; `ON CREATE SET` runs only when the node is newly created. You still need proper business keys and constraints because `MERGE` alone does not replace all uniqueness guarantees under concurrent writes.

### 7.2. Notes When Creating Relationships

Two unique nodes **do not imply the relationship between them is unique**:

~~~cypher
MATCH (a:Person {personId: 'P-201'})
MATCH (b:Person {personId: 'P-202'})
CREATE (a)-[:FOLLOWS]->(b);
~~~

Re-running the query can create an additional parallel `FOLLOWS` relationship between the same two nodes. If business rules allow only one relationship of this type, consider `MERGE (a)-[:FOLLOWS]->(b)` after identifying the two nodes accurately and designing appropriate integrity mechanisms.

### 7.3. Common Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Re-running the command increases node count | `CREATE` always creates new nodes | Use business keys and constraints; consider `MERGE` |
| Two person nodes have the same name | A person's name does not guarantee uniqueness | Identify by `personId`, not by `name` |
| Relationship points to a "duplicate" node | Recreating endpoint nodes with `CREATE` | `MATCH` existing endpoints first, then `CREATE` the relationship |
| No relationship is created | Preceding `MATCH` returned zero rows | Check labels, key values, and query order |
| More relationships created than expected | `MATCH` returned multiple results | Check unique keys and the number of matched nodes |
| Error saving properties | Attempting to store nested maps or invalid types | Flatten properties or extract the entity into a separate node |
| Constraint violation error | Identifier already exists | Review creation logic and business requirements |

## 8. Integrated Example: Employees Joining a Project

The example below illustrates the workflow for adding data in a property graph: identifying nodes with business keys, creating employees and a project, creating relationships with role properties, and querying back. The statements execute sequentially; run them in a learning environment with separate sample data.

**Step 1 — Create constraints for business keys.**

~~~cypher
CREATE CONSTRAINT demo_employee_id_unique IF NOT EXISTS
FOR (e:Employee) REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.projectId IS UNIQUE;
~~~

**Step 2 — Create two employees, one project, and relationships.**

~~~cypher
CREATE
  (ha:Employee {
    employeeId: 'E-DEMO-01',
    name: 'Hà',
    department: 'Engineering'
  }),
  (khoa:Employee {
    employeeId: 'E-DEMO-02',
    name: 'Khoa',
    department: 'Data'
  }),
  (project:Project {
    projectId: 'PR-DEMO-01',
    title: 'Customer Relationship Analysis'
  }),
  (ha)-[:WORKS_ON {
    role: 'Backend Developer',
    startedOn: date('2026-01-10')
  }]->(project),
  (khoa)-[:WORKS_ON {
    role: 'Data Engineer',
    startedOn: date('2026-02-01')
  }]->(project)
RETURN ha.employeeId AS employeeA, khoa.employeeId AS employeeB,
       project.projectId AS projectId;
~~~

**Step 3 — Verify the newly created relationships.**

~~~cypher
MATCH (e:Employee)-[r:WORKS_ON]->(p:Project)
WHERE p.projectId = 'PR-DEMO-01'
RETURN e.name AS employee,
       r.role AS role,
       r.startedOn AS startDate,
       p.title AS project
ORDER BY employee;
~~~

The expected result has **two rows**, one for Hà and one for Khoa, both pointing to project `PR-DEMO-01`. The verification query does not modify the graph.

**Step 4 — Add an existing person to an existing project.**

~~~cypher
MATCH (e:Employee {employeeId: 'E-DEMO-01'})
MATCH (p:Project {projectId: 'PR-DEMO-01'})
CREATE (e)-[:REVIEWS {frequency: 'weekly'}]->(p)
RETURN e.name AS reviewer, p.title AS project;
~~~

Step 4 creates only **one new relationship**; it does not create additional employees or projects. If you re-run Step 2, the constraints will prevent recreating nodes with the same keys and the statement may fail. If you re-run Step 4, the `REVIEWS` relationship may be duplicated.

## 9. Using `CREATE` via the Neo4j Java Driver

In a Java application, pass parameters and manage transactions using the Driver. The example method below for adding a person assumes the application has configured and manages the lifecycle of the `Driver` object:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonRepository {
    private final Driver driver;

    public PersonRepository(Driver driver) {
        this.driver = driver;
    }

    public String createPerson(String personId, String name) {
        String cypher = """
                CREATE (p:Person {personId: $personId, name: $name})
                RETURN p.personId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "personId", personId,
                            "name", name
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

- `executeWrite` executes the write operation within a Driver-managed transaction.
- `Map.of(...)` passes parameters; Java code does not concatenate input strings into the Cypher statement.
- `single()` is appropriate when the statement is expected to return exactly one row.
- In production applications, you need to specify the database, error handling policy, unique constraints, and retry requirements. With Spring Data Neo4j, entity mapping and repository persistence provide a higher-level abstraction; understanding `CREATE` patterns still helps when reading custom Cypher queries.

## 10. Practice and Self-Check

**Exercise 1 — Node and properties.** Write a statement to create a `Course` node with `courseId`, `title`, `durationHours`, and `published`; return `courseId` and `title`.

<details>
<summary>Reference solution</summary>

~~~cypher
CREATE (c:Course {
  courseId: 'C-001',
  title: 'Cypher Fundamentals',
  durationHours: 12,
  published: true
})
RETURN c.courseId AS courseId, c.title AS title;
~~~

</details>

**Exercise 2 — Relationship with properties.** Assume a person with `personId = 'P-101'` and a course with `courseId = 'C-001'` already exist. Create an `ENROLLED_IN` relationship carrying `enrolledOn` as the current date, without recreating either node.

<details>
<summary>Reference solution</summary>

~~~cypher
MATCH (p:Person {personId: 'P-101'})
MATCH (c:Course {courseId: 'C-001'})
CREATE (p)-[:ENROLLED_IN {enrolledOn: date()}]->(c)
RETURN p.personId AS personId, c.courseId AS courseId;
~~~

</details>

**Exercise 3 — Behavior analysis.** After running the following query twice, how many `:Category {name: 'Graph'}` nodes will exist, assuming no matching data existed initially and no constraints are defined?

~~~cypher
CREATE (:Category {name: 'Graph'});
~~~

Answer: **Two nodes**. `CREATE` does not check for duplicate values. If `Category` is identified by name, consider a unique key and `MERGE`; if names can change or collide, use a separate `categoryId`.

## 11. Takeaways

- `CREATE` creates new nodes, new relationships, and the properties declared in the Cypher pattern.
- Nodes have labels and properties; relationships must connect two nodes, are directed, have a type, and may carry properties.
- **Creating an entire small subgraph:** `CREATE (a:...)-[:REL]->(b:...)`.
- **Connecting existing data:** `MATCH` the endpoint nodes, then `CREATE` the relationship.
- Use `$...` parameters and `UNWIND` for application-supplied data or bulk creation.
- `CREATE` can create duplicates when re-run; constraints protect business keys, while `MERGE` serves find-or-create pattern needs.
- When tuning and operating Neo4j, review the model, queries, and constraints before writing large volumes. `EXPLAIN` helps inspect query plans; `PROFILE` executes the query, so use caution with write statements.

**Next steps:** After `CREATE`, learn `MATCH` to find nodes/relationships, `SET` and `REMOVE` to modify properties/labels, `MERGE` for find-or-create cases, and `DELETE`/`DETACH DELETE` for deleting data along with relationships.
