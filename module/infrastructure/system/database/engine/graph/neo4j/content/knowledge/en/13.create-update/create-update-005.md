# SET to Update Properties, Merge Maps, and Manage Labels in Neo4j

> **Chapter:** Create and Update  
> **Module:** `DATABASE_ENGINE_GRAPH_NEO4J` — modeling connected data as a *property graph*, manipulating nodes and relationships with Cypher.

In Neo4j, information on nodes and relationships changes over time: an employee transfers departments, a product changes price, a project participation relationship changes role, or a node receives an additional classification label. Cypher's **`SET`** clause is used to make these changes. `SET` can update individual properties, set multiple properties at once, **merge into or replace an entire property map**, and **add labels to nodes**.

The difference between `SET n.property = value`, `SET n += map`, and `SET n = map` is especially critical when syncing data from external systems: using the wrong operator can wipe out properties, overwrite business keys, or produce unintended states.

## 1. Learning Objectives

After completing this lesson, you can:

1. Write `MATCH ... SET` queries to update properties on existing nodes or relationships.
2. Use `SET` with multiple assignments, expressions, data types, and `null` values.
3. Distinguish **replacing all properties** (`=`) from **adding/updating individual keys** (`+=`).
4. Add labels to nodes with `SET n:Label` and understand its relationship to `REMOVE`.
5. Combine `SET` with `CREATE`, `MERGE`, `ON CREATE SET`, and `ON MATCH SET`.
6. Avoid sync errors related to constraints, identifying keys, missing data, lists, and bulk write operations.
7. Apply `SET` queries in Java Driver applications and Spring Data Neo4j custom queries.

## 2. Which Property Graph Components Does SET Affect?

Example graph:

~~~text
(:Person {personId: 'P01', name: 'An', department: 'Data'})
        |
        | [:WORKS_ON {role: 'Developer', active: true}]
        v
(:Project {projectId: 'PR01', title: 'Atlas'})
~~~

| Component | Syntax | Effect |
|---|---|---|
| Node property | `SET p.name = 'An Nguyễn'` | Adds or updates a key-value pair on node `p` |
| Multiple node properties | `SET p.name = 'An', p.active = true` | Assigns multiple properties in one `SET` |
| Relationship property | `SET r.role = 'Tech Lead'` | Updates a property on relationship `r` |
| Add/update via map | `SET p += {city: 'Hà Nội'}` | Updates keys present in the map, keeps other keys |
| Replace properties via map | `SET p = {personId: 'P01'}` | Replaces the entire property set with the new map |
| Add node label | `SET p:Employee` | Adds the `Employee` label to node `p` |

**Scope:** `SET` modifies properties of nodes or relationships; adding labels applies only to **nodes**. `SET` does not create new relationships, does not delete nodes, and does not directly change an existing relationship's type.

Another key point: `SET` requires a **variable referencing a concrete element**. That variable is usually bound by `MATCH`, `MERGE`, `CREATE`, or an earlier clause in the same query.

## 3. Updating One or More Properties

### 3.1. Updating a Single Property on a Node

Suppose a `Person` node with `personId = 'P01'` already exists:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.department = 'Engineering'
RETURN p.personId AS personId,
       p.name AS name,
       p.department AS department;
~~~

Reading the query top to bottom:

1. `MATCH` finds and binds variable `p` to the node matching label `Person` and key `personId`.
2. `SET` writes the value `'Engineering'` to the `department` property of the matched node.
3. `RETURN` reads back the properties for verification.

If `department` already existed, the old value is replaced. If it did not exist, the property is added. If `MATCH` finds no node, `SET` executes on nothing for that node and the query does not create a new node.

### 3.2. Updating Multiple Properties at Once

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.name = 'Nguyễn An',
    p.department = 'Engineering',
    p.active = true,
    p.updatedAt = datetime()
RETURN p;
~~~

Assignments within the same `SET` are separated by commas. Besides strings and booleans, properties can use numbers, dates, datetimes, spatial points, and lists of valid property values.

Use consistent property names like `personId` and `updatedAt`. Cypher is case-sensitive: `p.userId` and `p.userid` are two different keys.

### 3.3. Updating Properties on a Relationship

Suppose the `WORKS_ON` relationship already exists:

~~~cypher
MATCH (p:Person {personId: 'P01'})
      -[r:WORKS_ON]->
      (pr:Project {projectId: 'PR01'})
SET r.role = 'Tech Lead',
    r.active = true,
    r.updatedAt = datetime()
RETURN p.name AS employee,
       pr.title AS project,
       r.role AS role,
       r.updatedAt AS updatedAt;
~~~

`r` references the **relationship**, so `r.role` is information about the project assignment, not a property of the person or project alone. You cannot write `SET r:Manager` to "change a label" on a relationship; relationships have a **type**, not labels like nodes.

### 3.4. Updating with Expressions

The right-hand side can be a Cypher expression:

~~~cypher
MATCH (p:Product {sku: 'SKU-001'})
SET p.price = 125000,
    p.stock = coalesce(p.stock, 0) + 10,
    p.lastRestockedOn = date()
RETURN p.sku AS sku, p.price AS price, p.stock AS stock;
~~~

`coalesce(p.stock, 0)` returns `p.stock` if non-`null`, otherwise `0`. Thus the addition does not evaluate to `null` when `stock` does not yet exist.

**Be careful with counter increments:** if the same request is resent due to a retry, `stock = stock + 10` will add 10 again. When business logic requires processing each event once, you need an event key and deduplication rules, not just a `SET` statement.

## 4. A Null Value Means Deleting the Property

In Neo4j, properties do not store a `null` value in the conventional sense. Assigning `null` to a property **removes** that property from the node or relationship.

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.nickname = null
RETURN p.nickname AS nickname;
~~~

If `nickname` existed previously, after this operation it no longer exists; reading `p.nickname` returns `null`. `REMOVE p.nickname` is the alternative syntax for intentionally removing a property.

This is especially important when data arrives from an API: an omitted field, a field with value `null`, and an explicit request to delete a field can carry **three different meanings**.

For example, if `$department` is `null`:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p.department = $department;
~~~

the statement will delete `department`. If the sync rule is *ignore null and keep the existing value*, you can use:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p.department = coalesce($department, p.department)
RETURN p.department AS department;
~~~

If both arguments are `null`, the result is `null` and the property remains absent. Using `coalesce` fits a "null means do not update" policy, but is **not appropriate** when null must be interpreted as a request to clear data.

## 5. Property Maps and Three Important Assignment Styles

A *map* in Cypher is a collection of key–value pairs:

~~~cypher
{
  name: 'Nguyễn An',
  department: 'Engineering',
  active: true
}
~~~

For the properties of a node `p`, compare three update styles:

~~~cypher
// Update only a single property
SET p.name = 'Nguyễn An'
~~~

~~~cypher
// Add or update only the listed keys
SET p += {name: 'Nguyễn An', active: true}
~~~

~~~cypher
// Replace the ENTIRE property set with the new map
SET p = {name: 'Nguyễn An', active: true}
~~~

The two map assignments below have **very different** effects.

### 5.1. SET n += map: Partial Add or Update

Suppose the initial node is:

~~~text
(:Person {
  personId: 'P01',
  name: 'An',
  department: 'Data',
  active: false,
  createdAt: 2026-01-01T00:00:00Z
})
~~~

Query:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p += {
  name: 'Nguyễn An',
  active: true,
  city: 'Đà Nẵng'
}
RETURN properties(p) AS props;
~~~

Semantic result:

~~~text
{
  personId: 'P01',         // preserved
  name: 'Nguyễn An',       // updated
  department: 'Data',      // preserved
  active: true,            // updated
  createdAt: ...,          // preserved
  city: 'Đà Nẵng'          // newly added
}
~~~

`+=` assigns **each key present in the map**:

- Key in map and on node: updated with the map's value.
- Key in map but not yet on node: property is added.
- Key on node not present in map: preserved.
- Key in map with value `null`: that property is deleted.

This is usually the right choice for partial update (*PATCH*) APIs, provided the application restricts which keys are allowed to change.

### 5.2. SET n = map: Replace All Properties

Starting from the same initial node above:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p = {
  personId: 'P01',
  name: 'Nguyễn An',
  active: true
}
RETURN properties(p) AS props;
~~~

After the operation, the node has only `personId`, `name`, and `active`. `department`, `city` (if present), and `createdAt` **are deleted** because they are absent from the replacement map.

| Criterion | `SET n += map` | `SET n = map` |
|---|---|---|
| Properties in the map | Added or updated | Added or updated |
| Old properties absent from the map | **Preserved** | **Removed** |
| Properties given `null` in the map | Removed | Not stored |
| Risk of losing `createdAt`/business keys | Possible if map contains overwriting values or null | Very high if map omits those keys |
| Suitable use case | Partial update, adding fields | Replacing full property state from an authoritative source |
| Node labels | Unchanged | Unchanged |
| Connected relationships | Unchanged | Unchanged |

**Rule:** only use `SET n = map` when the input map genuinely represents the **entire desired set of properties**, and you know old properties absent from the map should be removed.

### 5.3. Map Parameters from Applications

Instead of hardcoding property names and values in Cypher, pass them via parameters:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch
RETURN p.personId AS personId, properties(p) AS properties;
~~~

Example:

~~~json
{
  "personId": "P01",
  "patch": {
    "name": "Nguyễn An",
    "active": true,
    "city": "Đà Nẵng"
  }
}
~~~

The application must verify `$patch` is a valid map and **contains only allowed fields**. Never let clients pass an unfiltered map directly, because a patch like `{"personId": null}` could delete the identifying key or trigger a constraint error. Exclude fields like `personId`, `createdAt`, and `role`, especially if the source is not authorized to update them.

### 5.4. When to Use SET n = $map?

If an external source is the system of record for **all properties** of an entity type, you can replace the state snapshot:

~~~cypher
MATCH (p:Product {sku: $sku})
SET p = $fullSnapshot
RETURN properties(p) AS properties;
~~~

This example is safe only when `$fullSnapshot` includes `sku` and every property that must be retained. If `sku` is missing or wrong, the key property may be deleted/replaced or trigger a constraint error. A better design for most systems is to explicitly define the fields managed by the source and update them individually or via a filtered map.

### 5.5. Additional Map Details

You can construct a map from properties of another node or relationship:

~~~cypher
MATCH (source:Product {sku: 'SKU-001'})
MATCH (target:Product {sku: 'SKU-002'})
SET target += {
  name: source.name,
  price: source.price
}
RETURN target;
~~~

When you only want to copy selected fields, list the property names explicitly as above. If you use `SET target += properties(source)`, every property key on `source` can overwrite the corresponding property on `target`, **including business keys** if both share the same key name.

Values inside a map must be **Neo4j-supported property values** when written to a node or relationship. You cannot store a nested map or a list of maps as a regular node property. For example, `address: {city: 'Hanoi'}` cannot be stored directly as a property. Use `city`, `addressCity`, or model the address as a separate node depending on query needs.

## 6. SET and Managing Node Labels

**Labels** describe a node's classification in a property graph; for example, the same person can carry `Person`, `Employee`, or `Manager`. Labels differ from **properties** such as `role` or `department`.

### 6.1. Adding a New Label

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p:Employee
RETURN labels(p) AS labels;
~~~

If the node originally had only `:Person`, after the statement it has both `:Person` and `:Employee`. `SET p:Employee` **does not remove** existing labels.

You can add multiple labels in one clause:

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p:Employee:Manager
RETURN labels(p) AS labels;
~~~

In this example, `:Employee` and `:Manager` are added to the same node. Adding a label that is already present does not create a duplicate label on the node.

### 6.2. Labels and Properties Are Not Interchangeable

~~~cypher
SET p:Manager
~~~

differs from:

~~~cypher
SET p.role = 'Manager'
~~~

- `:Manager` is a **label** for classification, query pattern matching, and label-scoped indexes/constraints.
- `role = 'Manager'` is a **property** holding a value, useful when roles are multi-valued data or change frequently.

Depending on needs, the same node can have both an `Employee` label and a `role` property. However, if each role is represented by its own label, enforce consistent rules so labels and properties do not contradict each other.

### 6.3. Changing Classification: Adding a New Label and REMOVing the Old Label

`SET` only **adds** labels. To transition a person from `Candidate` to `Employee`, remove the old label with `REMOVE`:

~~~cypher
MATCH (p:Person {personId: 'P01'})
REMOVE p:Candidate
SET p:Employee
RETURN labels(p) AS labels;
~~~

If you only run `SET p:Employee`, the `Candidate` label remains. `REMOVE p:Candidate` does not delete node `p` or its relationships; it only removes one label. `REMOVE p.department` can also remove a property, though that is a different operation from removing a label.

### 6.4. Labels Affect Constraints and Indexes

Suppose the database has a unique constraint on `:Employee(employeeId)`. When adding the `Employee` label to a node whose `employeeId` matches another node already carrying that label, the labeling operation can violate the constraint and fail.

Labels also determine which queries find the node:

~~~cypher
MATCH (p:Employee)
RETURN p.employeeId AS employeeId, p.name AS name;
~~~

A node carrying only the `Person` label will not be selected by `MATCH (p:Employee)` until the `Employee` label is added.

### 6.5. Dynamic Labels and Untrusted Input

For problems with a small fixed set of categories, write queries using statically designed labels:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p:Employee
RETURN p;
~~~

Some newer Cypher/Neo4j versions support dynamic label syntax, but availability depends on the version. Regardless of syntax, **never concatenate user-supplied label names directly into Cypher strings** without validation. When dynamic classification is genuinely required, validate against an allowlist of permitted label names and verify support in your running Neo4j version.

## 7. Updating Lists and Conditional Expressions

### 7.1. Replacing an Entire List

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.skills = ['Java', 'Cypher', 'Spring']
RETURN p.skills AS skills;
~~~

`skills` is a string-list property. This assignment **replaces the entire old list**.

### 7.2. Appending an Element to a List

~~~cypher
MATCH (p:Person {personId: 'P01'})
SET p.skills = coalesce(p.skills, []) + ['Neo4j']
RETURN p.skills AS skills;
~~~

If the list already exists, the new element is appended to the end. If not, the result is a list containing `Neo4j`. This command **can create duplicate elements** when re-run.

To add only when the element is not already present:

~~~cypher
MATCH (p:Person {personId: 'P01'})
WITH p, coalesce(p.skills, []) AS currentSkills
SET p.skills = CASE
  WHEN 'Neo4j' IN currentSkills THEN currentSkills
  ELSE currentSkills + ['Neo4j']
END
RETURN p.skills AS skills;
~~~

Here `CASE` creates a conditional branch inside the assignment expression. Avoid using long list properties as substitutes for relationships that require complex querying; if skills are entities shared across many people, consider modeling `(:Person)-[:HAS_SKILL]->(:Skill)`.

### 7.3. Conditional Updates

~~~cypher
MATCH (p:Product {sku: 'SKU-001'})
SET p.status = CASE
  WHEN coalesce(p.stock, 0) > 0 THEN 'available'
  ELSE 'out_of_stock'
END
RETURN p.status AS status;
~~~

For multi-source data reconciliation or complex state-transition policies, build conditions according to explicit business rules.

## 8. Combining SET with CREATE and MERGE

### 8.1. SET Immediately After CREATE

~~~cypher
CREATE (pr:Project {projectId: 'PR-SET-001'})
SET pr.title = 'Graph Platform',
    pr.active = true,
    pr.createdAt = datetime()
RETURN pr;
~~~

`CREATE` creates the new node, and `SET` adds its properties. If all properties are known upfront, you can also declare them directly inside the `CREATE` pattern.

### 8.2. MERGE on Key, SET Mutable Properties

`MERGE` finds or creates an entity by a stable key:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
SET p.name = $name,
    p.department = $department,
    p.lastSyncedAt = datetime()
RETURN p;
~~~

If the node does not yet exist, `MERGE` creates it and `ON CREATE SET` assigns `createdAt`. If it already exists, the existing node is used. The trailing `SET` updates the business fields **in both cases**.

When you need a dedicated branch for existing records:

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
ON MATCH SET p.lastMatchedAt = datetime()
SET p.name = $name
RETURN p;
~~~

`ON MATCH SET` runs only when the `MERGE` pattern **already matched**. It does not automatically check whether source data is newer or older; if versioned sync is needed, add timestamp or version comparison rules.

### 8.3. MERGE Each Node, SET on the Relationship

~~~cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.name = $personName

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET pr.title = $projectTitle

MERGE (p)-[r:WORKS_ON]->(pr)
ON CREATE SET r.joinedOn = date()
SET r.role = $role,
    r.lastSyncedAt = datetime()

RETURN p.personId AS personId,
       pr.projectId AS projectId,
       r.role AS role;
~~~

Each `MERGE` binds one component according to its own pattern. Because `p` and `pr` are found/created first, the final relationship `MERGE` finds/creates the relationship **between those two identified endpoints**. `SET r.role` can update the relationship's role without creating a new relationship simply because `role` changed.

**Note:** appropriate constraints are needed to protect node keys under concurrent writes; `MERGE` alone is not a guarantee of uniqueness in every scenario.

## 9. Constraints, Business Keys, and Overwrite Risks

### 9.1. Constraining Identifying Keys

A business key should be protected by a constraint when the model requires uniqueness:

~~~cypher
CREATE CONSTRAINT person_personId_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
~~~

If two `:Person` nodes already share the same non-`null` `personId`, creating the constraint will fail. Once the constraint exists, attempting to change a node's `personId` to a value already belonging to another node will also fail.

Constraints help catch integrity violations, but do not replace input map validation or field ownership rules.

### 9.2. Do Not Let Patches Overwrite Keys and Metadata

The query:

~~~cypher
MATCH (p:Person {personId: $personId})
SET p += $patch;
~~~

is convenient, but dangerous if `$patch` contains `personId`, `createdAt`, `verified`, or a field owned by another department. The application should **filter the list of updatable fields** before passing the parameter.

Example simple policy:

| Field | Sync Rule |
|---|---|
| `personId` | Identification only; do not allow patches to modify it |
| `name` | Allowed to update |
| `department` | Allowed to update when HR source is authoritative |
| `active` | Allowed to update from official source |
| `createdAt` | Preserved after creation |
| `lastSyncedAt` | Managed by the writing application |
| `securityRole` | Modifiable only by the authorization service |

Field-level authorization belongs in application design and operational rules, and does not arise automatically from `SET` or `MERGE`.

### 9.3. Multiple Nodes Matching MATCH

~~~cypher
MATCH (p:Person {name: 'An'})
SET p.active = true
RETURN count(p) AS updatedNodes;
~~~

If three people are named An, the query updates all three. Neo4j does not infer which person was meant to be modified. Use stable business keys, appropriate indexes/constraints, and verify matched row counts.

### 9.4. Concurrent Writes and Transactions

`SET` executes inside a Neo4j write transaction. If multiple operations concurrently modify the same node or relationship, the system needs transaction management and an appropriate conflict policy. For instance, two applications concurrently writing different `department` values can leave whichever write lands last; unique keys do not decide which source has priority.

When integrating multiple sources, establish versioning rules, source update timestamps, retry handling, or conflict checks. Additive assignments like `stock = stock + 1` require protection against unintended event replays.

## 10. Bulk Updates with UNWIND

Suppose an application receives a list of patches:

~~~json
{
  "people": [
    {
      "personId": "P01",
      "patch": {
        "name": "Nguyễn An",
        "active": true
      }
    },
    {
      "personId": "P02",
      "patch": {
        "department": "Data",
        "city": "Hà Nội"
      }
    }
  ]
}
~~~

Query to update **existing** nodes:

~~~cypher
UNWIND $people AS row
MATCH (p:Person {personId: row.personId})
SET p += row.patch,
    p.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

`UNWIND` produces one row per element, `MATCH` locates the node by key, and `SET +=` updates the provided fields. If a `personId` does not exist, that row **updates nothing** and is not counted in the final `count(*)`.

If the requirement is to **auto-create nodes when missing**, replace `MATCH` with `MERGE`:

~~~cypher
UNWIND $people AS row
MERGE (p:Person {personId: row.personId})
ON CREATE SET p.createdAt = datetime()
SET p += row.patch,
    p.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

**Safety conditions:** the `row.patch` map must not alter `personId` or `createdAt`. Input data must be validated, field-filtered, and key-deduplicated before running. If a key appears multiple times in the same batch with conflicting patches, the result can depend on processing order; `UNWIND` does not guarantee row ordering without explicit sorting rules.

### 10.1. Reading Results and Record Counts

`count(*)` in the two queries above is the **number of rows reaching `RETURN`**, not necessarily the number of newly created nodes or modified property keys. A `MATCH` can return multiple nodes if constraints are missing; thus the count can even exceed the number of elements in the input list.

### 10.2. Performance When Updating Large Datasets

- Create indexes/constraints on lookup keys like `:Person(personId)` to avoid unnecessary full node scans.
- Split lists into reasonable batches to avoid oversized transactions.
- Send and update only the fields that need to change, especially when nodes have many properties.
- Validate property types before writing; do not use nested maps as node properties.
- Use `EXPLAIN` to view the plan without executing writes. `PROFILE` actually executes the query, so use it on write queries only against controlled test data.

## 11. Using SET in the Neo4j Java Driver

In Java, passing maps via parameters avoids concatenating user data into Cypher strings. The following example performs a targeted update on an existing person profile:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class PersonService {
    private final Driver driver;

    public PersonService(Driver driver) {
        this.driver = driver;
    }

    public boolean updateDepartment(String personId, String department) {
        String cypher = """
            MATCH (p:Person {personId: $personId})
            SET p.department = $department,
                p.updatedAt = datetime()
            RETURN p.personId AS id
            """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                tx.run(cypher, Map.of(
                    "personId", personId,
                    "department", department
                )).hasNext()
            );
        }
    }
}
~~~

In this example:

- `MATCH` updates only an existing node. If `personId` is not found, the query updates nothing and the method returns `false`.
- `Map.of(...)` requires non-`null` values. If your contract allows deleting properties via `null`, build a compatible parameter map and explicitly control the data semantics.
- `executeWrite` runs the callback inside a Driver-managed write transaction; the callback may be retried on certain transient errors. Therefore, do not place external side effects inside the callback without idempotency protection.
- `Driver` should be managed over the application lifecycle; each operation uses an appropriate `Session`.
- To protect identity when data is updated by multiple processes, use constraints and business-level conflict handling.

If you want to apply a map patch, replace `SET` with `SET p += $patch` and pass an additional `patch` parameter filtered against an allowed field list.

In **Spring Data Neo4j**, repositories and entity mappings map domain entities. When using custom Cypher queries, e.g., via `@Query`, the semantics of `SET`, `+=`, `=`, and adding labels remain identical to standard Cypher. When using entity-save mechanisms, understand how the library manages property and relationship state to avoid losing data when Java objects hold only a subset of fields.

## 12. Practice with a Product Scenario

Suppose a graph database manages courses:

~~~text
(:Course {
  courseId: 'C001',
  title: 'Cypher Fundamentals',
  durationHours: 12,
  published: false,
  createdAt: <creation timestamp>
})
~~~

To prepare test data on a graph that does not yet have `C001`:

~~~cypher
CREATE (c:Course {
  courseId: 'C001',
  title: 'Cypher Fundamentals',
  durationHours: 12,
  published: false,
  createdAt: datetime()
})
RETURN c;
~~~

If the system already has this ID, do not re-run `CREATE` because it will create a duplicate or fail a constraint.

### Exercise 1 — Updating Individual Properties

**Requirement:** publish course `C001` by setting `published = true` and `publishedAt` to the current date. Do not touch `createdAt`.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c.published = true,
    c.publishedAt = date()
RETURN c.courseId AS courseId,
       c.published AS published,
       c.publishedAt AS publishedAt;
~~~

The statement writes only the specified properties. `createdAt` remains untouched.

</details>

### Exercise 2 — Distinguishing the Two Map Operators

**Initially**, node C001 has: `courseId='C001'`, `title='Cypher Fundamentals'`, `durationHours=12`, and `createdAt`.

Compare two queries run on **two independent copies of the initial state**:

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c += {title: 'Practical Cypher', published: true};
~~~

~~~cypher
MATCH (c:Course {courseId: 'C001'})
SET c = {courseId: 'C001', title: 'Practical Cypher', published: true};
~~~

**Question:** which operation preserves `durationHours` and `createdAt`?

<details>
<summary>Answer</summary>

`SET c += {...}` preserves properties not appearing in the map, including `durationHours` and `createdAt`. `SET c = {...}` replaces the entire property set; since the new map lacks those two keys, they are removed from the node. The node's `:Course` label remains unchanged in both cases.

</details>

### Exercise 3 — Adding a New Label, Removing an Old Label

**Requirement:** add the `PublishedCourse` label to C001 and remove `DraftCourse` if present, without deleting the node or its properties.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (c:Course {courseId: 'C001'})
REMOVE c:DraftCourse
SET c:PublishedCourse
RETURN labels(c) AS labels;
~~~

Here `REMOVE` strips the `DraftCourse` label, while `SET` adds `PublishedCourse`. The `Course` label stays intact.

</details>

### Exercise 4 — Updating a Student Course Enrollment Relationship

Suppose `Student {studentId: 'S001'}`, `Course {courseId: 'C001'}`, and an `ENROLLED_IN` relationship between them already exist. Update `status = 'completed'` and `completedOn` to the current date.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (s:Student {studentId: 'S001'})
      -[r:ENROLLED_IN]->
      (c:Course {courseId: 'C001'})
SET r.status = 'completed',
    r.completedOn = date()
RETURN s.studentId AS studentId,
       c.courseId AS courseId,
       r.status AS status,
       r.completedOn AS completedOn;
~~~

`SET` updates the existing relationship; if no matching relationship is found, the query does not create a new one.

</details>

### Exercise 5 — Finding the Bug When Receiving an API Patch

Given the query:

~~~cypher
MERGE (c:Course {courseId: $courseId})
SET c = $patch;
~~~

where `$patch` contains only `title` and `published`. Why might `courseId` disappear after syncing or the query violate a constraint?

<details>
<summary>Reference answer</summary>

`SET c = $patch` replaces the entire property set with the new map; if the map lacks `courseId`, the key property is deleted (or the transaction fails if an existence constraint forbids it). To perform a partial update, use `SET c += $patch` after filtering allowed fields, or `SET c.title = $title, c.published = $published`.

</details>

## 13. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `SET` changes nothing | `MATCH` found no node/relationship | Check labels, relationship types, and key values; use `MERGE` if auto-creation is needed |
| Updating one person changes multiple people | `MATCH`ed by name or a non-unique property | Use business keys and appropriate constraints |
| Old properties vanish unexpectedly | Used `SET n = map` with a map missing fields | Use `+=` for partial patches or pass a full snapshot |
| Business key is modified or lost | Patch map contained the identifying key or null | Filter fields, forbid overwriting keys, and check constraints |
| A property is deleted when sent from an API | Parameter received `null` | Clarify null semantics and apply ignore/delete policy accordingly |
| Old label remains after adding a new label | `SET n:Label` only adds labels | Use `REMOVE n:OldLabel` when needed |
| Cannot "SET label" on a relationship | Relationships do not use labels like nodes | Use relationship types and properties; redesign when changing connection types |
| Updating a list repeatedly creates duplicate items | Concatenated element with `+` on every run | Check membership before appending or model as relationships |
| Adding a label throws a constraint error | New label enforces a constraint on a colliding key | Verify data and identifiers before adding the label |
| Older message overwrites newer value | No version or source timestamp comparison | Add precedence rules and transaction control |

## 14. Summary

Key operations to distinguish:

| Purpose | Cypher Pattern |
|---|---|
| Update one property | `MATCH (n:Label {id: $id}) SET n.name = $name` |
| Update multiple properties | `SET n.name = $name, n.active = $active` |
| Add/update via map | `SET n += $patch` |
| Replace all properties | `SET n = $fullSnapshot` |
| Delete a property | `SET n.property = null` or `REMOVE n.property` |
| Add one or more node labels | `SET n:Employee` or `SET n:Employee:Manager` |
| Remove an old node label | `REMOVE n:OldLabel` |
| Set fields on both create and match | `MERGE ... SET n.field = $value` |
| Set fields only on creation | `MERGE ... ON CREATE SET n.createdAt = datetime()` |
| Update relationship properties | `MATCH (a)-[r:TYPE]->(b) SET r.role = $role` |

**Core point:** `SET` is the tool for updating properties and adding labels; choosing `=` versus `+=` determines whether you **replace everything** or **partially update**. Combining `SET` with `MATCH`/`MERGE` by business keys, constraints, parameters, transactions, and field-ownership rules enables a Neo4j system to sync accurately, remain inspectable, and operate reliably.

After this topic, continue exploring `REMOVE` to drop properties/labels, `DELETE`/`DETACH DELETE` to delete graph elements, and indexes plus `EXPLAIN` to optimize conditional write queries.
