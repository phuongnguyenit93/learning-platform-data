# ON CREATE SET and ON MATCH SET When Syncing Data in Neo4j

> **Chapter:** Create and Update  
> **Module:** `DATABASE_ENGINE_GRAPH_NEO4J` — using Neo4j to model connected data as a property graph and query relationships and paths with Cypher.

In a system managing employees, users, or projects, data often arrives across multiple syncs: the first pass needs to **create entities**, and subsequent passes need to **update existing entities**. Cypher provides `MERGE` to find or create by pattern; paired with it, `ON CREATE SET` and `ON MATCH SET` allow executing **two distinct update branches** depending on the outcome of `MERGE`.

This enables applications to record a creation date once, update the latest sync timestamp, keep business identifiers stable, and handle **node** or **relationship** properties separately. Understanding these two branches accurately also helps design bulk data imports, constraints, Java Driver queries, and Spring Data Neo4j code without creating graph duplicates.

## 1. Learning Objectives

After this lesson, you can:

1. Explain when `ON CREATE SET` and `ON MATCH SET` execute within a `MERGE` clause.
2. Write queries to create or update nodes using a business key while preserving properties set only at creation time.
3. Use unconditional `SET` when a property needs to be updated in **both branches**.
4. Sync two nodes and the relationship between them using separate `MERGE` clauses, placing creation/match logic in the right places.
5. Identify common pitfalls: missing constraints, unstable keys, `null` values, overly broad relationship patterns, and overwritten data during syncs.
6. Apply parameters, `UNWIND`, and transactions from the Java Driver or custom queries in Spring Data Neo4j.

## 2. Core Syntax and Semantics of the Two Branches

General syntax:

~~~cypher
MERGE (n:Label {businessKey: $businessKey})
ON CREATE SET
  n.createdAt = datetime(),
  n.name = $name
ON MATCH SET
  n.lastSyncedAt = datetime(),
  n.name = $name
RETURN n;
~~~

Reading sequentially:

1. `MERGE` checks whether a node with label `Label` and matching `businessKey` property exists.
2. If **no matching pattern exists**, `MERGE` creates a new pattern; the assignments after `ON CREATE SET` execute.
3. If **a matching pattern exists**, `MERGE` reuses the matched component; the assignments after `ON MATCH SET` execute.
4. `RETURN` returns the data after the operation so the application can confirm the result.

`ON CREATE SET` and `ON MATCH SET` are **branches of `MERGE`**, not standalone clauses following `CREATE` or `MATCH`. Nor are they general-purpose conditional statements for arbitrary clauses in a query.

| Statement | Effect | When Does It Run? |
|---|---|---|
| `MERGE (n:Label {id: $id})` | Finds or creates the pattern | Every time an input row is processed |
| `ON CREATE SET n.createdAt = datetime()` | Assigns properties specific to new data | The **immediately preceding `MERGE`** just created its pattern |
| `ON MATCH SET n.lastSyncedAt = datetime()` | Assigns properties specific to matched data | The **immediately preceding `MERGE`** pattern already existed |
| `SET n.name = $name` | Unconditionally assigns properties | Whenever the query row reaches `SET`, in both branches |

You can use only `ON CREATE SET`, only `ON MATCH SET`, or both. If a property needs to be assigned in both cases, you can write it in both branches, though an unconditional `SET` is usually more concise.

### 2.1. Visualizing the Execution Flow

~~~mermaid
flowchart TD
    A["Receive business key and new data"] --> B["MERGE by business key"]
    B --> C{"Matching pattern exists?"}
    C -->|No| D["Create new pattern"]
    D --> E["ON CREATE SET"]
    C -->|Yes| F["Reuse existing pattern"]
    F --> G["ON MATCH SET"]
    E --> H["Unconditional SET, if present"]
    G --> H
    H --> I["RETURN or continue query"]
~~~

**Important:** "matching pattern exists" means matching **the entire pattern in that `MERGE` clause**. If `MERGE` includes a relationship path with unbound nodes, the mere existence of two nodes with matching IDs is not enough to trigger the `ON MATCH SET` branch. A later section demonstrates how to separate `MERGE` per entity and relationship.

## 3. Basic Example: Syncing an Employee Profile

Suppose an external system provides:

~~~json
{
  "employeeId": "E001",
  "fullName": "Nguyễn An",
  "department": "Engineering",
  "active": true
}
~~~

In Neo4j, `employeeId` is the **stable business key** of the `Employee` node. `fullName`, `department`, and `active` are fields that may change later.

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.createdAt = datetime(),
  e.source = 'hr-system'
ON MATCH SET
  e.lastSyncedAt = datetime()
SET e.fullName = $fullName,
    e.department = $department,
    e.active = $active
RETURN e.employeeId AS employeeId,
       e.fullName AS fullName,
       e.createdAt AS createdAt,
       e.lastSyncedAt AS lastSyncedAt;
~~~

Results across runs:

| Execution | State Before Run | `MERGE` Branch | Effect |
|---|---|---|---|
| Run 1 | No `Employee(employeeId='E001')` exists | `ON CREATE SET` | Creates node; writes `createdAt`, `source`, and the three business fields |
| Run 2 | Node E001 already exists | `ON MATCH SET` | Keeps `createdAt`; writes `lastSyncedAt`; updates business fields |
| Run 3 | Node E001 still exists, department changed | `ON MATCH SET` | Reuses existing node; updates `department`, `lastSyncedAt` |

Thus, `createdAt` records when the node was created in the graph, while `lastSyncedAt` records when it **matched and was processed**. In this example, `lastSyncedAt` will **not exist** right after the initial creation because it is only assigned in the `ON MATCH SET` branch.

If the business requirement is to record **every sync**, including the first one, place `lastSyncedAt` in the shared `SET`:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName,
    e.department = $department,
    e.lastSyncedAt = datetime()
RETURN e;
~~~

Both approaches are valid, but the meaning of `lastSyncedAt` differs; choose according to business requirements.

### 3.1. Why Not MERGE on the Entire Profile?

Error-prone query:

~~~cypher
MERGE (e:Employee {
  employeeId: $employeeId,
  fullName: $fullName,
  department: $department
})
ON CREATE SET e.createdAt = datetime();
~~~

If `department` changes, the old pattern fails to match the new pattern. Neo4j will try to create a new node with the same `employeeId`, causing **duplicate entities** without constraints or **constraint violation errors** if a unique key is configured.

Clearly separate:

- **Identifying key:** durable property, e.g., `employeeId`.
- **Properties to sync:** `fullName`, `department`, `active`.
- **Lifecycle metadata:** `createdAt`, `lastSyncedAt`, `source`, `updatedAt`.

A query that `MERGE`s on the key and then `SET`s mutable fields preserves the same entity when attributes change.

## 4. Common Update Patterns

### 4.1. Write Properties Only on Initial Creation

Some data should not be modified arbitrarily after creation, such as `registeredAt` or `createdBy`:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET
  u.registeredAt = datetime(),
  u.createdBy = $actor
SET u.displayName = $displayName
RETURN u;
~~~

When the account already exists, `registeredAt` and `createdBy` remain unchanged; `displayName` can change.

### 4.2. Modify Only When the Node Already Exists

~~~cypher
MERGE (d:Device {deviceId: $deviceId})
ON CREATE SET
  d.firstSeenAt = datetime(),
  d.state = 'new'
ON MATCH SET
  d.lastSeenAt = datetime(),
  d.state = 'known'
RETURN d;
~~~

Initially `state` is `new`, and on subsequent matches `state` transitions to `known`. However, when modeling business statuses with multiple states, **avoid** hardcoding `state = 'known'` if syncing might accidentally overwrite a state managed by another application.

### 4.3. Update in Both Branches Using SET

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET
  p.createdAt = datetime()
ON MATCH SET
  p.lastSeenAsExistingAt = datetime()
SET p.name = $name,
    p.price = $price,
    p.updatedAt = datetime()
RETURN p;
~~~

On both creation and match, `SET` is executed. The `ON MATCH SET` branch writes `lastSeenAsExistingAt` only when the pattern already existed.

### 4.4. Merging Parameter Maps with `+=`

If the application has a set of properties to update, you can use:

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET p.createdAt = datetime()
SET p += $properties
RETURN p;
~~~

For example, `$properties` is:

~~~json
{
  "name": "Graph Book",
  "price": 150000,
  "inStock": true
}
~~~

`SET p += $properties` updates keys present in the map while keeping properties **not mentioned** intact; if the map passes a key with value `null`, the corresponding property may be removed. In contrast, `SET p = $properties` replaces the entire property set with the new map, which can wipe out `createdAt` or business keys. Therefore, never pass an arbitrary user map into an update statement without controlling the allowed field list.

Additionally, there is no need to include `sku` in the update map: the `sku` key is already in the identifying pattern and should remain stable.

## 5. When to Use ON CREATE SET, ON MATCH SET, and SET

These branches are not mere stylistic choices; they represent **business policies**:

| Property | Desired Behavior | Recommended Implementation |
|---|---|---|
| `employeeId` | Stable identification | Place in the `MERGE` pattern |
| `createdAt` | Set only on first creation | `ON CREATE SET` |
| `importSource` | Record source at creation, preserve original source history | `ON CREATE SET` |
| `firstJoinedOn` | Time the relationship was created in the graph | `ON CREATE SET` on relationship `MERGE` |
| `fullName` | Sync whenever a valid value is received | Shared `SET` |
| `active` | Sync current state | Shared `SET` |
| `lastSyncedAt` | Mark every sync, including the first | Shared `SET` |
| `lastMatchedAt` | Mark only when the pattern already existed | `ON MATCH SET` |
| `retryCount` | Increment only on re-encounter | `ON MATCH SET n.retryCount = coalesce(n.retryCount, 0) + 1` |

**Important distinction:** Timestamp field names carry business meaning. `createdAt` assigned in `ON CREATE SET` is **when the Neo4j record was created**, not necessarily when the entity originated in the source system. If the source already provides a reliable `createdAt`, give it a distinct name such as `sourceCreatedAt` and consider a separate sync policy.

## 6. Syncing Nodes and Relationships: Each MERGE Has Its Own Branch

In a property graph, data consists not only of nodes but also of relationships. Suppose an employee works on a project:

~~~text
(:Employee {employeeId: 'E001'})
           -[:WORKS_ON {role: 'Backend'}]->
(:Project {projectId: 'PR001'})
~~~

Requirements:

- Find or create the employee by `employeeId`.
- Find or create the project by `projectId`.
- Find or create **one `WORKS_ON` relationship** between those two nodes.
- Record when the relationship was created only once; update the role on subsequent syncs.

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET
  e.fullName = $employeeName,
  e.createdAt = datetime()

MERGE (pr:Project {projectId: $projectId})
ON CREATE SET
  pr.title = $projectTitle,
  pr.createdAt = datetime()

MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET
  r.joinedAt = date(),
  r.createdAt = datetime()
ON MATCH SET
  r.lastMatchedAt = datetime()
SET r.role = $role

RETURN e.employeeId AS employeeId,
       pr.projectId AS projectId,
       r.role AS role,
       r.joinedAt AS joinedAt;
~~~

Clause-by-clause breakdown:

1. `MERGE (e:Employee ...)` decides solely whether the employee node needs to be created. `ON CREATE SET e...` belongs to this clause.
2. `MERGE (pr:Project ...)` decides separately for the project node. `ON CREATE SET pr...` runs only if the **project node** is newly created.
3. `MERGE (e)-[r:WORKS_ON]->(pr)` decides separately for the relationship. Because `e` and `pr` were bound earlier, the relationship uses those exact found/created nodes.
4. `ON CREATE SET r.joinedAt...` runs only when the **relationship** is newly created. `ON MATCH SET r.lastMatchedAt...` runs when the **relationship** matched, regardless of whether the employee and project nodes were just created or already existed.
5. `SET r.role = $role` runs in both branches of the relationship `MERGE`.

### 6.1. Branches Can Differ Within the Same Query

For example, if employee E001 already exists in the graph, but project PR01 does not yet exist:

| Component | MERGE Clause | Branch Triggered |
|---|---|---|
| Employee E001 | `MERGE (e:Employee ...)` | `ON MATCH` if declared |
| Project PR01 | `MERGE (pr:Project ...)` | `ON CREATE` |
| Relationship `WORKS_ON` | `MERGE (e)-[r:WORKS_ON]->(pr)` | `ON CREATE` |

**There is no single `ON CREATE` or `ON MATCH` branch for the whole query.** Each `MERGE` clause evaluates its own pattern and branches against the data at the moment it executes.

### 6.2. Avoid Full-Pattern MERGE with Unbound Endpoints

The following style can create duplicate nodes when **both endpoints already exist without the relationship**:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
      -[r:WORKS_ON]->
      (pr:Project {projectId: $projectId})
ON CREATE SET r.createdAt = datetime();
~~~

Because neither `e` nor `pr` was bound beforehand, the clause asks to find **the entire path**. If no matching path exists, `MERGE` can try to create both nodes and the relationship instead of merely connecting the two existing nodes. With unique constraints on node keys, the query can raise an error.

When business logic has independent entities reused across many relationships, **`MERGE` each node first**, then `MERGE` the relationship. If the nodes **must already exist**, use `MATCH` for the endpoints:

~~~cypher
MATCH (e:Employee {employeeId: $employeeId})
MATCH (pr:Project {projectId: $projectId})
MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
ON MATCH SET r.lastMatchedAt = datetime()
SET r.role = $role
RETURN r;
~~~

If either endpoint does not exist, `MATCH` returns no corresponding row, so no relationship is created.

## 7. Business Keys, Constraints, and Concurrent Writes

`MERGE` is convenient, but **it does not replace data constraints**. For systems with multiple transactions or multiple sync processes, define clear business keys and apply appropriate constraints.

Examples:

~~~cypher
CREATE CONSTRAINT employee_id_unique IF NOT EXISTS
FOR (e:Employee)
REQUIRE e.employeeId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (pr:Project)
REQUIRE pr.projectId IS UNIQUE;
~~~

These constraints ensure each `employeeId` or `projectId` value belongs to at most one corresponding node with that label. Node unique constraints also provide an index to serve key lookups.

**Deployment note:** If existing data already has duplicate keys, creating the constraint can fail. Clean up duplicate data first and handle constraint errors in the application.

### 7.1. Node Uniqueness Does Not Enforce Relationship Uniqueness

Even when both `Employee(employeeId)` and `Project(projectId)` are unique, two nodes can still have multiple parallel `WORKS_ON` relationships. `MERGE (e)-[r:WORKS_ON]->(pr)` finds a matching relationship by type and direction in normal cases, but it does not automatically remove pre-existing duplicate relationships, and node constraints do not guarantee relationship uniqueness under concurrent writes.

If business rules require **each project assignment to be an independent historical record**, you can identify the relationship with an `assignmentId` or use an `Assignment` node. In that case, `MERGE` on the relationship's key; do not let changing `role` accidentally spawn a new historical relationship.

### 7.2. MERGE Keys Must Not Be Null

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime();
~~~

If `$employeeId = null`, `MERGE` with this key property will raise an error. Validate business keys **before** running the query. A unique constraint also does not mean every node is required to have the key: if you want to ensure a property always exists, design an existence constraint appropriate for your Neo4j version and data policy.

### 7.3. Wrong Keys or Mutable Keys

Avoid using person names, project titles, or mutable emails as identifiers unless business rules guarantee they are immutable. If a composite key is needed (for example, each employee ID is unique only within a company), the identifying pattern can be:

~~~cypher
MERGE (e:Employee {
  companyId: $companyId,
  employeeId: $employeeId
})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName
RETURN e;
~~~

In this case, the constraint must also be defined on the **pair of properties** rather than `employeeId` alone.

## 8. Repeated Syncs and Idempotency

An ingestion process may re-run the same record due to network errors, transaction retries, or scheduled syncs. Typically, we want:

- **No increase in node/relationship counts** when re-running with the same key.
- **No loss of creation timestamps** when a record already exists.
- To update only fields that the data source is authorized to manage.
- Not to accidentally overwrite newer data if an older event arrives later.

`MERGE` on a stable key, combined with constraints and update branches, supports **structural idempotency**: re-running with the same identifier does not intend to create new entities. However, writing `lastSyncedAt = datetime()` on every run causes **property state to change**; thus the query can be *idempotent in entity count* while **not idempotent across all properties**.

### 8.1. Do Not Confuse lastSyncedAt with Source Event Time

Suppose a source sends an `eventId` and a `sourceUpdatedAt` timestamp. If two syncs have the same payload at different run times, `datetime()` reflects when it was written **to Neo4j**, not when the actual change happened at the source. To preserve source provenance:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
ON CREATE SET e.createdAt = datetime()
SET e.fullName = $fullName,
    e.sourceUpdatedAt = datetime($sourceUpdatedAt),
    e.lastSyncedAt = datetime()
RETURN e;
~~~

The example above still overwrites `fullName` if an old message arrives late. If the source can deliver out of order, add a **version or timestamp validity rule** before updating data. `ON MATCH SET` itself does not compare old vs. new messages.

### 8.2. Null Values in Sync Data

In Cypher, setting a property to `null` means **removing that property**. For example:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
SET e.department = $department
RETURN e;
~~~

If `$department` is `null`, the `department` property is removed. That is right if the source intentionally requests deletion, but dangerous when `null` merely means "this field was omitted."

If the policy is to **ignore null values**, one simple option is:

~~~cypher
MERGE (e:Employee {employeeId: $employeeId})
SET e.department = coalesce($department, e.department)
RETURN e;
~~~

`coalesce` picks the first non-`null` value. If both are `null`, no `department` property exists, matching the unpopulated state. Clearly distinguish **missing fields**, **intentional null values**, and **empty strings** per your integration contract; using `coalesce` means you do not support deleting properties via `null`.

### 8.3. Do Not Increment Counters Just Because a Query Retried

Example:

~~~cypher
MERGE (j:Job {jobId: $jobId})
ON CREATE SET j.createdAt = datetime(), j.seenCount = 1
ON MATCH SET j.seenCount = coalesce(j.seenCount, 0) + 1;
~~~

`seenCount` increments on every re-match, even when processing the same repeated message. If you only want to count **unique events**, identify each event with its own key or deduplication mechanism before incrementing the counter. `ON MATCH SET` alone does not provide "exactly-once processing."

## 9. Creating and Updating Multiple Records with UNWIND

`UNWIND` turns a list into rows, allowing the same `MERGE` and `ON CREATE/ON MATCH SET` rules to apply to each record.

Example parameters:

~~~json
{
  "employees": [
    {
      "employeeId": "E001",
      "fullName": "Nguyễn An",
      "department": "Engineering",
      "active": true
    },
    {
      "employeeId": "E002",
      "fullName": "Trần Bình",
      "department": "Data",
      "active": true
    }
  ]
}
~~~

Query:

~~~cypher
UNWIND $employees AS row
MERGE (e:Employee {employeeId: row.employeeId})
ON CREATE SET
  e.createdAt = datetime(),
  e.importSource = 'hr-batch'
ON MATCH SET
  e.lastMatchedAt = datetime()
SET e.fullName = row.fullName,
    e.department = row.department,
    e.active = row.active,
    e.lastSyncedAt = datetime()
RETURN count(*) AS processedRows;
~~~

With two valid, unique employee IDs in the input and an appropriate constraint, the query finds/creates two nodes. If E001 already exists while E002 does not, `ON MATCH SET` applies to row E001 and `ON CREATE SET` applies to row E002.

`processedRows` is the **number of processed rows reaching `RETURN`**, not the number of newly created employees. If the initial data contains multiple nodes sharing the same key so `MERGE` matches multiple nodes, the row count can exceed expectations.

### 9.1. Rules for Batch Input Data

- Validate that `employeeId` is non-empty and non-`null` for every row.
- Deduplicate keys within the same batch, especially when rows with the same ID carry conflicting values. `UNWIND` does not guarantee ordering, so do not rely on "last row wins" without proper ordering/versioning rules.
- Handle `null` values and conditionally updated fields explicitly.
- Batch appropriately for large datasets, monitoring query latency and transaction pressure.
- Create constraints before importing, after confirming existing data satisfies the constraints.

### 9.2. Batch Syncing Relationships

Example where each row has an employee, a project, and a role, aiming to find/create both endpoints and the relationship:

~~~cypher
UNWIND $assignments AS row
MERGE (e:Employee {employeeId: row.employeeId})
ON CREATE SET e.createdAt = datetime(), e.fullName = row.employeeName

MERGE (pr:Project {projectId: row.projectId})
ON CREATE SET pr.createdAt = datetime(), pr.title = row.projectTitle

MERGE (e)-[r:WORKS_ON]->(pr)
ON CREATE SET r.createdAt = datetime()
ON MATCH SET r.lastMatchedAt = datetime()
SET r.role = row.role

RETURN count(*) AS processedAssignments;
~~~

Two employees joining the same project share the same project node **if they have the same `projectId` and data is protected by a constraint**. Each `MERGE` evaluates its own create/match branch per row and per component.

## 10. Using from the Neo4j Java Driver

In Java, pass parameters instead of concatenating names, IDs, or other values directly into Cypher strings. The example below receives a sync record, finds or creates an `Employee`, and returns its ID:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public final class EmployeeSyncService {
    private final Driver driver;

    public EmployeeSyncService(Driver driver) {
        this.driver = driver;
    }

    public String syncEmployee(
            String employeeId,
            String fullName,
            String department
    ) {
        String cypher = """
                MERGE (e:Employee {employeeId: $employeeId})
                ON CREATE SET e.createdAt = datetime()
                ON MATCH SET e.lastMatchedAt = datetime()
                SET e.fullName = $fullName,
                    e.department = $department,
                    e.lastSyncedAt = datetime()
                RETURN e.employeeId AS id
                """;

        try (Session session = driver.session()) {
            return session.executeWrite(tx ->
                    tx.run(cypher, Map.of(
                            "employeeId", employeeId,
                            "fullName", fullName,
                            "department", department
                    )).single().get("id").asString()
            );
        }
    }
}
~~~

**Technical notes:**

- `executeWrite` runs the query inside a Driver-managed write transaction and includes a retry mechanism for certain transient errors. Because the callback may be re-executed, avoid placing **external side effects outside the database** (such as sending emails or calling payment APIs) inside the callback without idempotency protection.
- `Map.of` is used for **non-null** parameters in this example. If data permits nulls, construct a compatible parameter map and define the property update policy.
- `single()` is appropriate when `employeeId` genuinely identifies a single node. A unique constraint supports that assumption.
- The `Driver` object should be lifecycle-managed and reused across the application; each operation can open/close an appropriate `Session`.
- When targeting a specific database, configure the database on the `Session` according to your environment.

In **Spring Data Neo4j**, repositories and entity mappings perform persistence at a higher level of abstraction. When a custom `@Query` is needed to sync by key, the same rules for `MERGE`, `ON CREATE SET`, `ON MATCH SET`, and constraints apply. Beyond the update branches, the application must manage transactions, data versioning, and relationships updated from the source.

## 11. Verifying Results and Troubleshooting

Suppose you synced employee E001; you can inspect it:

~~~cypher
MATCH (e:Employee {employeeId: 'E001'})
RETURN e.employeeId AS id,
       e.fullName AS name,
       e.createdAt AS createdAt,
       e.lastMatchedAt AS lastMatchedAt,
       e.lastSyncedAt AS lastSyncedAt;
~~~

Check whether multiple nodes share the same key:

~~~cypher
MATCH (e:Employee)
WITH e.employeeId AS employeeId, count(*) AS total
WHERE employeeId IS NOT NULL AND total > 1
RETURN employeeId, total
ORDER BY total DESC;
~~~

`EXPLAIN` can be used to inspect a query's execution plan without executing the write portion. `PROFILE` **executes the query**, so when inspecting sync queries, use it only on test data or when you fully understand the impact.

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `createdAt` changes on every sync | Used shared `SET` instead of `ON CREATE SET` | Move `createdAt` to the creation branch |
| `lastSyncedAt` missing after initial creation | Placed in `ON MATCH SET` | If you want to record every sync, move it to shared `SET` |
| Updating department creates another node | Included `department` in the `MERGE` pattern | `MERGE` on a stable key, update non-key properties outside the pattern |
| Cannot create data due to constraint violation | Attempted to create an entity with an existing key via a different pattern, or conflicting data | Check key, pattern, duplicate data, and constraint status |
| Duplicate relationships or duplicate endpoint nodes appear | Full-path `MERGE` with unbound endpoints | Separate `MERGE` for each node and relationship; use constraints |
| Properties disappear after sync | Passed `null` or `SET n = $map` replaced all properties | Define a null policy, update only allowed fields |
| Newer data overwritten by older event | No source ordering/version control | Check source modification timestamp or version before updating |
| "New count" metric does not match `count(*)` | `count(*)` counts rows, without distinguishing newly created branches | Design explicit create/match counters when needed |
| Java callback triggers side effects multiple times | Transaction was retried | Do not put non-idempotent side effects inside the callback |
| `MERGE` fails on null | Input business key is `null` | Validate keys before executing the query |

## 12. Practice Exercises

### Exercise 1: Creating and Updating a Course

Requirements:

- `Course` nodes are identified by `courseId`.
- `createdAt` is recorded only on initial creation.
- `title` and `published` are updated after every sync.
- `lastMatchedAt` is recorded only when the course already existed.

<details>
<summary>Reference answer</summary>

~~~cypher
MERGE (c:Course {courseId: $courseId})
ON CREATE SET c.createdAt = datetime()
ON MATCH SET c.lastMatchedAt = datetime()
SET c.title = $title,
    c.published = $published
RETURN c;
~~~

If no `Course` node exists on the first run, the `ON CREATE SET` branch runs and `ON MATCH SET` does not. When re-running with the same `courseId`, the roles swap.

</details>

### Exercise 2: Avoiding Overwriting the Registration Date

Consider the statement:

~~~cypher
MERGE (u:User {userId: $userId})
SET u.registeredAt = datetime(),
    u.displayName = $displayName;
~~~

**Question:** Why does `registeredAt` become wrong after multiple syncs? Fix it to preserve the initial registration time.

<details>
<summary>Reference answer</summary>

Here `SET` runs **every time** the query reaches the clause, so the registration date gets overwritten. Move it to `ON CREATE SET`:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.registeredAt = datetime()
SET u.displayName = $displayName;
~~~

</details>

### Exercise 3: Two Existing Nodes, Relationship May Not Exist Yet

Requirements: `User U01` and `Group G01` **must already exist**; do not create nodes if missing. Find or create the `MEMBER_OF` relationship, setting `joinedOn` only when the relationship is new; update `membershipRole` on every run.

<details>
<summary>Reference answer</summary>

~~~cypher
MATCH (u:User {userId: 'U01'})
MATCH (g:Group {groupId: 'G01'})
MERGE (u)-[r:MEMBER_OF]->(g)
ON CREATE SET r.joinedOn = date()
SET r.membershipRole = $role
RETURN u.userId AS userId,
       g.groupId AS groupId,
       r.joinedOn AS joinedOn,
       r.membershipRole AS membershipRole;
~~~

`MATCH` guarantees endpoints are not auto-created, and `MERGE` only finds/creates the relationship between the two bound nodes. If either node is missing, the query creates no relationship.

</details>

### Exercise 4: Understanding Create vs. Match Branches

Suppose employee E01 **already exists**, project PR01 **does not exist yet**, and no `WORKS_ON` relationship exists:

~~~cypher
MERGE (e:Employee {employeeId: 'E01'})
ON CREATE SET e.createdFlag = true
ON MATCH SET e.matchedFlag = true
MERGE (p:Project {projectId: 'PR01'})
ON CREATE SET p.createdFlag = true
ON MATCH SET p.matchedFlag = true
MERGE (e)-[r:WORKS_ON]->(p)
ON CREATE SET r.createdFlag = true
ON MATCH SET r.matchedFlag = true
RETURN e, p, r;
~~~

**Question:** Which flags will the three objects receive?

<details>
<summary>Answer</summary>

- `Employee E01` matched: sets `matchedFlag = true`; `createdFlag` exists only if written earlier.
- `Project PR01` was created: sets `createdFlag = true`; `matchedFlag` is not set in this clause.
- `WORKS_ON` was newly created: sets `createdFlag = true`; `matchedFlag` is not set in this clause.

Each branch belongs to its immediately preceding `MERGE`; there is no shared branch for the entire query.

</details>

## 13. Key Takeaways and Application

- **`MERGE`** finds or creates a *pattern*; **`ON CREATE SET`** runs when that `MERGE` pattern is created; **`ON MATCH SET`** runs when it already matched.
- **Unconditional `SET`** is suitable for properties that need updating on both creation and match.
- **Identify by stable key**: put the key in `MERGE`; put names, statuses, business values, and changing metadata in the appropriate `SET` branches.
- **Each `MERGE` has its own branches**: when syncing a graph, find/create each node first, then find/create relationships between the bound nodes.
- **Constraints and valid data** preserve identity; `MERGE` alone does not replace integrity policies or protect against every concurrent write race.
- **Repeated syncs** do not mean every value is immutable: timestamps, counters, and out-of-order messages must be designed explicitly.
- **Java Driver, Spring Data Neo4j, and bulk imports** all share the same Cypher semantics; use parameters, transactions, null validation, and source data tracking.

Mastering `ON CREATE SET` and `ON MATCH SET` is an essential step toward writing controlled Neo4j update queries before moving on to query plan optimization, indexes/constraints, large-source syncing, and operating graph systems.
