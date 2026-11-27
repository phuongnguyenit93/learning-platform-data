# Distinguishing Node Properties from Relationship Properties

## 1. Learning Objectives

In Neo4j, a **property graph** consists of **nodes** and **relationships**. Both can store **properties** as key–value pairs, but choosing where to place a property determines the **meaning**, **queryability**, and **accuracy** of the data.

This lesson belongs to the **Graph Elements** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module covers using Neo4j to model connected data and query relationships and paths with Cypher; from there, it proceeds to indexes, constraints, query tuning, data ingestion, Neo4j Java Driver, Spring Data Neo4j, and graph database operations.

After this lesson, you will be able to:

1. Distinguish properties describing an **entity** from properties describing a **specific connection**.
2. Properly model facts that vary by node pair, such as **job role**, **collaboration start date**, or **product quantity in an order**.
3. Read, add, update, and remove properties on nodes and relationships using **Cypher**.
4. Recognize situations where a pair of nodes has **multiple relationships**, avoiding erroneous updates or miscounted data.
5. Know when a connection with its **own identity and lifecycle** should be promoted into an intermediate node.
6. Understand how property placement impacts indexes, constraints, and how Java applications interact with Neo4j.

## 2. Both Are Properties, Yet Belong to Different Objects

Consider a person named **An** working at company **Alpha**:

```text
(:Person {
  personId: 'P001',
  fullName: 'An',
  email: 'an@example.com'
})
          |
          | [:WORKS_AT {
          |   role: 'Developer',
          |   startedOn: 2024-01-10
          | }]
          v
(:Company {
  companyId: 'C001',
  name: 'Alpha',
  country: 'VN'
})
```

In this model:

- `Person.personId`, `Person.fullName`, and `Person.email` describe **the person An**.
- `Company.companyId`, `Company.name`, and `Company.country` describe **the company Alpha**.
- `WORKS_AT.role` and `WORKS_AT.startedOn` describe **An's work at Alpha**, not an intrinsic fixed trait of An or Alpha.

Reading with Cypher:

```cypher
MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
RETURN p.fullName AS personName,
       c.name AS companyName,
       r.role AS roleAtCompany,
       r.startedOn AS employmentStart;
```

**Intuitive rule:** If a value only makes sense when knowing **both endpoints** and the **relationship type**, it usually belongs on the relationship. If a value describes an entity even without considering any particular connection, it usually belongs on the node.

## 3. Comparing Node and Relationship Properties

| Criterion | **Node** Property | **Relationship** Property |
| --- | --- | --- |
| Subject described | An entity, object, or concept | A link/action between two entities |
| Storage syntax location | Inside parentheses `(n:Label {key: value})` | Inside square brackets `-[r:TYPE {key: value}]->` |
| Good examples | `Person.fullName`, `Company.name`, `Product.sku` | `WORKS_AT.startedOn`, `FOLLOWS.since`, `CONTAINS.quantity` |
| Need endpoints to understand? | Usually no | Usually yes |
| Value count when an entity has many links | One property on the node represents an entity-level value | Each relationship has its **own** property set |
| Cypher access | `p.fullName`, `properties(p)` | `r.startedOn`, `properties(r)` |
| Index/constraint scope | By node **label** and property | By relationship **type** and property |
| Link direction | Has no direction | Relationship has a **start node** and an **end node** |

A node can carry multiple labels while properties still belong to that **single node**. Each relationship has **exactly one type**, two endpoints, and its own property set. Neo4j allows two nodes to be connected by **multiple relationships**, even with the same type and direction.

### 3.1. Quick Syntax Glance

```cypher
// Node property: email belongs to p
(p:Person {personId: 'P001', email: 'an@example.com'})

// Relationship property: since belongs to r
(p)-[r:FOLLOWS {since: date('2025-06-01')}]->(q)

// Property of the other node: name belongs to q
(q:Person {personId: 'P002', name: 'Bình'})
```

The three lines above illustrate **syntax patterns**, not three standalone statements to execute directly. When creating real data, use `CREATE` or `MERGE` inside a complete statement.

## 4. Questions to Decide Where to Place a Property

When building a model, ask in order:

1. **Who/what is this fact about?** A person, product, or company? Place it on the corresponding node.
2. **Does the value vary depending on the other entity in the link?** Does a person hold different roles at two companies? Place it on the employment relationship or employment entity.
3. **Can multiple links exist between the same two nodes?** Two purchases of the same product with different dates and prices? Store each occurrence as a separate relationship or an event node.
4. **Does the link itself have an identifier, status, history, and multiple other relationships?** Then a separate node like `Employment`, `OrderLine`, or `Booking` may be a better fit.
5. **At what point in time does the fact change?** Is it the entity's current value or a snapshot at the moment a transaction occurred? Avoid overwriting history.

For example, `Product.currentPrice` can belong on the product if it represents the current catalog price; `CONTAINS.unitPriceAtOrder` represents the **price applied in a specific order**. Changing the product's price today must not alter the prices of completed orders.

## 5. End-to-End Example: One Person Working at Multiple Companies

Suppose An was previously a Developer at Alpha and is currently a Tech Lead at Beta.

```text
                              [:WORKS_AT {
 (:Person {                    assignmentId: 'A001',
   personId: 'P001',            role: 'Developer',
   fullName: 'An'              startedOn: 2021-03-01,
 }) ─────────────────────────→ endedOn: 2023-12-31
  │                          }] (:Company {name: 'Alpha'})
  │
  │ [:WORKS_AT {
  │   assignmentId: 'A002',
  │   role: 'Tech Lead',
  │   startedOn: 2024-01-01
  │ }]
  └──────────────────────────→ (:Company {name: 'Beta'})
```

**Why not place `role: 'Tech Lead'` directly on the `Person` node?**

If An works at two companies simultaneously, `Person.role` cannot specify which company that role belongs to. If only the latest title is kept on `Person`, historical information about the position at Alpha gets overwritten.

Placing `role`, `startedOn`, and `endedOn` on **each `WORKS_AT` relationship** preserves exact context. Meanwhile, `fullName` and `personId` remain on `Person`; `name` and `companyId` remain on `Company`.

### 5.1. Initializing the Test Dataset

Run once in a **learning database**, since `CREATE` always creates new data:

```cypher
CREATE (an:Person {
  personId: 'GE005-P001',
  fullName: 'An',
  email: 'an@example.com'
})
CREATE (alpha:Company {
  companyId: 'GE005-C001',
  name: 'Alpha',
  country: 'VN'
})
CREATE (beta:Company {
  companyId: 'GE005-C002',
  name: 'Beta',
  country: 'VN'
})
CREATE (an)-[:WORKS_AT {
  assignmentId: 'GE005-A001',
  role: 'Developer',
  startedOn: date('2021-03-01'),
  endedOn: date('2023-12-31')
}]->(alpha)
CREATE (an)-[:WORKS_AT {
  assignmentId: 'GE005-A002',
  role: 'Tech Lead',
  startedOn: date('2024-01-01')
}]->(beta)
RETURN an, alpha, beta;
```

Upon each successful `CREATE`, Neo4j creates two independent relationships between An and the two companies. The `role` property shares the same key name but holds **two distinct values on the two links**.

### 5.2. Reading Properties at the Right Level

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       p.fullName AS personName,
       c.companyId AS companyId,
       c.name AS companyName,
       r.assignmentId AS assignmentId,
       r.role AS roleAtCompany,
       r.startedOn AS startedOn,
       r.endedOn AS endedOn
ORDER BY startedOn;
```

Expected output:

| personName | companyName | roleAtCompany | startedOn | endedOn |
| --- | --- | --- | --- | --- |
| An | Alpha | Developer | 2021-03-01 | 2023-12-31 |
| An | Beta | Tech Lead | 2024-01-01 | `null` |

`null` in Beta's row appears because `endedOn` **does not exist on that relationship**. Do not automatically assume `null` always means "currently active": in real systems, it could also mean unknown. Establish a clear business convention; you can use a `status` property if you need to distinguish "active", "resigned", and "unknown".

### 5.3. Updating a Role at One Company

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company {companyId: 'GE005-C002'})
SET r.role = 'Engineering Manager'
RETURN p.fullName AS personName,
       c.name AS companyName,
       r.role AS newRole;
```

This statement updates `role` on **employment relationship A002** without altering properties on node An or affecting the Developer role at Alpha.

If instead you ran:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.role = 'Engineering Manager'
RETURN p.fullName AS name, p.role AS role;
```

Then `p.role` becomes a **property on the `Person` node**, not on `WORKS_AT`. The data is syntactically valid but **semantically different**; if an application has both `p.role` and `r.role`, it must define which source of truth is authoritative to prevent contradictions.

## 6. Relationship Properties Express Connection Context

Several common patterns:

| Graph Pattern | Node Properties | Relationship Properties | Reason |
| --- | --- | --- | --- |
| `(Person)-[:WORKS_AT]->(Company)` | `Person.fullName`, `Company.name` | `role`, `startedOn`, `endedOn` | Role and tenure belong to the employment at that company |
| `(User)-[:FOLLOWS]->(User)` | `User.userId`, `User.displayName` | `since`, `notificationsEnabled` | Each user has different follow settings per target user |
| `(Order)-[:CONTAINS]->(Product)` | `Order.orderId`, `Product.sku` | `quantity`, `unitPriceAtOrder` | Quantity and purchase price belong to each line item in the order |
| `(Service)-[:DEPENDS_ON]->(Service)` | `Service.name`, `Service.version` | `dependencyType`, `criticality` | Dependency level pertains to the specific service pair |
| `(Person)-[:ATTENDED]->(Event)` | `Person.personId`, `Event.eventId` | `checkedInAt`, `ticketClass` | Check-in time and ticket tier belong to that attendance |

### 6.1. Same Property Key Does Not Mean Same Semantics

Neo4j does not forbid a node and a relationship from sharing a property named `status`. For example:

```cypher
(u:User {status: 'ACTIVE'})
  -[:SUBSCRIBED_TO {status: 'PAUSED'}]->
(channel:Channel {status: 'PUBLIC'})
```

Here:

- `u.status` is the account status.
- `r.status` is the user's subscription status for that channel.
- `channel.status` is the channel's visibility status.

The key name is identical, yet they belong to **three different subjects**. In queries, qualify with explicit variables (`u.status`, `r.status`, `channel.status`) to avoid confusion.

### 6.2. Properties Describing Events and History

Two people can meet multiple times, or one account can transfer money multiple times to another account:

```text
(:Account A)-[:TRANSFERRED {eventId: 'T001', amount: 100000}]->(:Account B)
(:Account A)-[:TRANSFERRED {eventId: 'T002', amount: 250000}]->(:Account B)
```

The two `amount` values belong to **two separate transfers**. Storing `amount` on node A or B makes it impossible to tell which amount belongs to which transaction. Neo4j allows multiple relationships with the same direction, type, and endpoints; the `eventId` property is what distinguishes events in business terms.

In financial scenarios, you can store monetary amounts as **integers in the smallest currency unit** (such as VND or cents) alongside `currency` when appropriate, to avoid unwanted floating-point precision errors.

## 7. Shared Property Mechanics: Data Types and `null`

Technically, nodes and relationships use the same property storage mechanism. Common value types:

| Type | Node Example | Relationship Example |
| --- | --- | --- |
| String | `fullName: 'An'` | `role: 'Developer'` |
| Integer | `age: 28` | `quantity: 3` |
| Float | `rating: 4.5` | `weight: 0.85` |
| Boolean | `active: true` | `approved: false` |
| Date/time | `birthDate: date('1998-04-01')` | `startedOn: date('2024-01-01')` |
| List of valid values | `skills: ['Java', 'Cypher']` | `permissions: ['READ', 'WRITE']` |
| Spatial point | `location: point({latitude: 10.82, longitude: 106.63})` | `meetingPoint: point({latitude: 10.82, longitude: 106.63})` |

**Note:** In Cypher, maps and complex lists can exist temporarily inside expressions, but you cannot store an **arbitrary nested map** or a node/relationship as the value of a regular property. When you need structured data with its own connections, consider creating nodes/relationships instead of stuffing everything into properties.

### 7.1. Non-Existent Properties and `null`

Reading a non-existent property returns `null`:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company)
RETURN p.nickname AS nickname,
       r.endedOn AS endedOn,
       c.name AS companyName;
```

In the sample data, neither `p.nickname` nor `r.endedOn` exists, so both return `null`.

Assigning `null` to a node or relationship property **deletes the property**:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.nickname = 'A'
SET p.nickname = null
RETURN p.nickname AS nickname;
```

```cypher
MATCH (:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
SET r.note = 'Needs update'
SET r.note = null
RETURN r.note AS note;
```

Check for missing properties using `IS NULL`:

```cypher
MATCH (p:Person)-[r:WORKS_AT]->(c:Company)
WHERE r.endedOn IS NULL
RETURN p.fullName AS personName, c.name AS companyName;
```

**Distinction:** `null` differs from an empty string `''`, the number `0`, and Boolean `false`; those values can be stored and carry distinct meanings.

## 8. Reading Properties and Metadata with Cypher

Core functions:

| Function/Expression | Effect |
| --- | --- |
| `p.fullName` | Reads the `fullName` property from node `p` |
| `r.role` | Reads the `role` property from relationship `r` |
| `properties(p)` | Returns a map of existing properties on the node |
| `properties(r)` | Returns a map of existing properties on the relationship |
| `keys(p)` | Returns existing property key names on the node |
| `keys(r)` | Returns existing property key names on the relationship |
| `labels(p)` | Returns the node's labels, not properties |
| `type(r)` | Returns the relationship's type, not properties |
| `startNode(r)` | Returns the start node according to the stored relationship direction |
| `endNode(r)` | Returns the end node according to the stored relationship direction |

Example reading an edge along with both endpoints:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
RETURN labels(p) AS personLabels,
       properties(p) AS personProperties,
       type(r) AS relationshipType,
       properties(r) AS employmentProperties,
       labels(c) AS companyLabels,
       properties(c) AS companyProperties
ORDER BY r.startedOn;
```

You can display each key–value pair for data inspection:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
UNWIND keys(r) AS propertyName
RETURN c.name AS companyName,
       propertyName,
       r[propertyName] AS propertyValue
ORDER BY companyName, propertyName;
```

`r[propertyName]` reads a property by **dynamic key name**. This is useful when all relationship properties are not known ahead of time. For application queries where the desired fields are fixed, prefer `r.role` or `r.startedOn` for readability.

## 9. Updating and Deleting Properties: Same Syntax, Different Targets

### 9.1. Adding/Updating Properties on a Node

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p.email = 'an.new@example.com',
    p.updatedAt = datetime()
RETURN properties(p) AS personProperties;
```

### 9.2. Adding/Updating Properties on a Relationship

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT {assignmentId: 'GE005-A002'}]->
      (c:Company {companyId: 'GE005-C002'})
SET r.role = 'Engineering Manager',
    r.updatedAt = datetime()
RETURN properties(r) AS employmentProperties;
```

### 9.3. Updating Properties with a Map

`SET n += {...}` or `SET r += {...}` adds/updates the listed keys while preserving all other keys:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
SET p += {active: true, department: 'Engineering'}
RETURN properties(p);
```

```cypher
MATCH (:Person)-[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
SET r += {role: 'Tech Lead', employmentType: 'FULL_TIME'}
RETURN properties(r);
```

Conversely, `SET p = {...}` or `SET r = {...}` **replaces the entire property set**, deleting any keys omitted from the map. When updating only a few fields, use `+=` or `SET ... .key`.

### 9.4. Removing a Property Does Not Delete the Node/Relationship

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
REMOVE p.department
RETURN keys(p) AS personPropertyKeys;
```

```cypher
MATCH (:Person)-[r:WORKS_AT {assignmentId: 'GE005-A002'}]->(:Company)
REMOVE r.employmentType
RETURN keys(r) AS relationshipPropertyKeys;
```

Both statements above remove only a property. **`DELETE r` deletes the entire relationship**, while **`DELETE p` deletes the node** (and requires handling any edges still attached to it). Never use element deletion when you only want to remove a property.

## 10. Parallel Relationships: Placing Properties Right Still Requires Identity

A person can work at **the same company across multiple employment stints**:

```text
(:Person An) ──[:WORKS_AT {
    assignmentId: 'A101',
    role: 'Developer',
    startedOn: 2020-01-01,
    endedOn: 2021-12-31
}]──→ (:Company Alpha)

(:Person An) ──[:WORKS_AT {
    assignmentId: 'A205',
    role: 'Consultant',
    startedOn: 2025-03-01
}]──→ (:Company Alpha)
```

Both relationships share the same type, direction, and endpoints, yet represent **two independent employment stints**. Do not rely solely on the person–company pair as the key to distinguish stints.

### 10.1. Be Careful When MATCHing an Endpoint Pair

Example:

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->
      (c:Company {companyId: $companyId})
SET r.role = $role;
```

If **multiple `WORKS_AT` relationships exist between the two nodes**, this statement updates **all** matching relationships. When you need to update **one specific stint**, add an identifier filter:

```cypher
MATCH (p:Person {personId: $personId})
      -[r:WORKS_AT {assignmentId: $assignmentId}]->
      (c:Company {companyId: $companyId})
SET r.role = $role
RETURN r.assignmentId AS assignmentId, r.role AS role;
```

In this model, `assignmentId` should be issued uniquely per stint, and the system should enforce uniqueness of that business ID.

### 10.2. Counting Links vs. Related Entities

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->(c:Company)
RETURN count(r) AS employmentPeriods,
       count(DISTINCT c) AS distinctCompanies;
```

`count(r)` counts **employment records**; `count(DISTINCT c)` counts **distinct companies**. If a person worked twice at the same company, these two numbers differ.

## 11. When Should You Promote a Relationship into a Dedicated Node?

A relationship works well when the data primarily describes **a connection between two nodes**. However, sometimes the "connection occurrence" itself must be managed as an **independent entity**.

### 11.1. Orders and Line Items Example

A simple model:

```text
(:Order {orderId: 'O001'})
  -[:CONTAINS {quantity: 2, unitPriceAtOrder: 120000}]->
(:Product {sku: 'SKU001', name: 'Cypher Book'})
```

`Product.name` and `Product.sku` describe the product. `CONTAINS.quantity` and `CONTAINS.unitPriceAtOrder` describe **the product line in order O001**. Putting `quantity: 2` on `Product` would break when order O002 buys 5 copies.

If one order can contain multiple lines of the same SKU with different promotions, each line having its own ID, return status, and link to a voucher, you can use:

```text
(:Order {orderId: 'O001'})
     |
     | [:HAS_LINE]
     v
(:OrderLine {lineId: 'L001', quantity: 2, unitPrice: 120000})
     |
     | [:FOR_PRODUCT]
     v
(:Product {sku: 'SKU001'})
```

Then `OrderLine` is a **node with its own identity**, easy to connect to related objects (promotions, returns, inventory). Base the modeling choice on **business rules and supported query patterns**, not merely on property count.

### 11.2. Employment Contract with Complex Lifecycle Example

If an employment stint involves contracts, addenda, approvals, departments, tax records, and independent audits, you can model:

```text
(:Person)-[:HAS_EMPLOYMENT]->(:Employment {
  employmentId: 'E001',
  startedOn: date(...),
  status: 'ACTIVE'
})-[:AT_COMPANY]->(:Company)
```

The `Employment` node carries data for **one stint** and can connect to other entities. If you only need `role` and `startedOn` per person–company pair, a `WORKS_AT` relationship with properties is usually sufficient.

**Signals to consider an intermediate node:** the event/link has its own ID, multiple states, a long lifecycle, multiple other entities referencing it, or needs relationships from **the event itself** to other nodes. Neo4j does not allow attaching a relationship as **an endpoint of another relationship**.

## 12. MERGE, Idempotency, and Accurate Data Updates

### 12.1. MERGE on Nodes

To find or create a person by business ID:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName
RETURN p;
```

`MERGE` matches by pattern and creates if no match exists. Use a uniqueness constraint on `Person.personId` to prevent duplicate IDs during ingestion or concurrent writes.

### 12.2. MERGE on Relationships: Choosing the Right Key

When business rules allow **at most one existing relationship** between a person and a company with the same type/direction, you can write:

```cypher
MATCH (p:Person {personId: $personId})
MATCH (c:Company {companyId: $companyId})
MERGE (p)-[r:WORKS_AT]->(c)
ON CREATE SET r.startedOn = date()
RETURN r;
```

However, when **one person has multiple employment stints at the same company**, this approach is **unsuitable**, because all stints match the same `(p)-[:WORKS_AT]->(c)` pattern. You must distinguish each stint, for instance with `assignmentId`:

```cypher
MATCH (p:Person {personId: $personId})
MATCH (c:Company {companyId: $companyId})
MERGE (p)-[r:WORKS_AT {assignmentId: $assignmentId}]->(c)
ON CREATE SET
  r.role = $role,
  r.startedOn = date($startedOn)
RETURN r.assignmentId AS assignmentId;
```

**Two notes:**

- `MERGE` matches the **entire pattern**, including type, direction, both endpoints, and the properties in the map. If `assignmentId` was already used for another link, handle the identifier conflict rather than silently creating or modifying the wrong record.
- `MERGE` does not automatically clean up pre-existing duplicate relationships and does not replace concurrency coordination mechanisms. Design transactions, constraints, and conflict handling according to business requirements.

### 12.3. Avoid Putting Mutable Properties in MERGE Keys

The following pattern is error-prone:

```cypher
MERGE (p:Person {personId: $personId, fullName: $fullName})
```

If `fullName` changes, **the full pattern fails to match** and Neo4j may attempt to create a second person or hit a uniqueness constraint error. It is better to `MERGE` by `personId` and then update `fullName` with `SET`.

Similarly, for relationships, `MERGE` by the **link's identifier**—do not include `role` or update timestamps in the pattern map if those values can change over time.

## 13. Where Do Indexes and Constraints Apply?

In Neo4j, indexes and constraints help look up and validate data by **node label**, **relationship type**, and properties.

### 13.1. Uniqueness Constraints on Node Properties

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT company_id_unique IF NOT EXISTS
FOR (c:Company)
REQUIRE c.companyId IS UNIQUE;
```

These constraints prevent two nodes with the `Person` label from sharing the same `personId` or two `Company` nodes from sharing the same `companyId`.

### 13.2. Uniqueness Constraints on Relationship Properties

On Neo4j versions supporting relationship property uniqueness constraints (such as Neo4j 5 and compatible releases):

```cypher
CREATE CONSTRAINT works_at_assignment_unique IF NOT EXISTS
FOR ()-[r:WORKS_AT]-()
REQUIRE r.assignmentId IS UNIQUE;
```

A constraint on **`WORKS_AT.assignmentId`** protects the assignment ID, yet **does not forbid multiple `WORKS_AT` edges between the same node pair** as long as each stint has a distinct ID.

**Distinction:** A uniqueness constraint typically **does not require** every node/relationship in scope to possess that property. Property existence constraints or key constraints have version/edition-specific support conditions.

### 13.3. Indexes for Lookups

```cypher
CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person)
ON (p.email);

CREATE INDEX works_at_start_idx IF NOT EXISTS
FOR ()-[r:WORKS_AT]-()
ON (r.startedOn);
```

Node indexes assist certain lookups by person email; relationship indexes can assist certain queries filtering by link start date. Whether an index is actually used depends on query predicates, data statistics, version, and optimizer choices; do not mechanically index every property.

Inspect the plan:

```cypher
SHOW INDEXES;
SHOW CONSTRAINTS;

EXPLAIN
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->(c:Company)
WHERE r.startedOn >= date($fromDate)
RETURN p.fullName, c.name, r.startedOn;
```

`EXPLAIN` only produces the plan. `PROFILE` executes the real query and reports execution metrics; test on representative data to evaluate index effectiveness.

## 14. Querying Multiple Relationships: Do Not Confuse Properties and Row Counts

### 14.1. Counting at the Right Level

Suppose An has two `WORKS_AT` relationships:

```cypher
MATCH (p:Person {personId: 'GE005-P001'})-[r:WORKS_AT]->(c:Company)
RETURN
  count(r) AS employmentRecords,
  count(DISTINCT c) AS companyCount;
```

`count(r)` counts **relationship records**, while `count(DISTINCT c)` counts **distinct companies**. If a person worked twice at the same company, these two numbers differ.

### 14.2. Row Multiplication When Combining Multiple Patterns

Suppose a person has 2 `WORKS_AT` relationships and 3 `FOLLOWS` relationships:

```cypher
MATCH (p:Person {personId: $personId})-[employment:WORKS_AT]->(c)
MATCH (p)-[following:FOLLOWS]->(friend)
RETURN count(employment) AS employmentRows,
       count(following) AS followingRows;
```

This query produces **2 × 3 = 6 paired rows**; `count(employment)` and `count(following)` both evaluate to 6, misrepresenting the actual relationship counts. When the goal is to count **distinct relationships**:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[employment:WORKS_AT]->()
WITH p, count(DISTINCT employment) AS employmentCount
OPTIONAL MATCH (p)-[following:FOLLOWS]->()
RETURN employmentCount,
       count(DISTINCT following) AS followingCount;
```

`OPTIONAL MATCH` ensures the person remains in the result even when one of the relationship types is absent. For complex reports, you can also compute each group via subqueries and combine by entity ID.

### 14.3. Distinguishing "No Link" from "Link Missing a Property"

Two different cases:

1. **No `WORKS_AT`**: a required `MATCH (p)-[r:WORKS_AT]->(c)` returns no row for that person.
2. **`WORKS_AT` exists without `role`**: the pattern matches, and `r.role` returns `null`.

Example preserving people without a company yet:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[r:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       c.name AS companyName,
       r.role AS roleAtCompany
ORDER BY personId, companyName;
```

Remember that for a person with multiple relationships, `OPTIONAL MATCH` still returns **multiple rows**, each describing one matching link.

## 15. Java Driver and Spring Data Neo4j Integration

### 15.1. Neo4j Java Driver: Passing Contextual Parameters

Java applications should separate **Cypher query structure** from user-supplied data. For example, updating the end date of **one employment relationship**:

```cypher
MATCH (p:Person {personId: $personId})
      -[r:WORKS_AT {assignmentId: $assignmentId}]->
      (c:Company {companyId: $companyId})
SET r.endedOn = date($endedOn)
RETURN p.personId AS personId,
       c.companyId AS companyId,
       r.assignmentId AS assignmentId,
       r.endedOn AS endedOn;
```

The client supplies a parameter map, for instance:

```json
{
  "personId": "GE005-P001",
  "companyId": "GE005-C002",
  "assignmentId": "GE005-A002",
  "endedOn": "2027-06-30"
}
```

Never concatenate arbitrary strings to inject person IDs, relationship IDs, or date values into Cypher. Specifically, keep `r.endedOn` accurate instead of accidentally writing `p.endedOn` or `c.endedOn`.

### 15.2. Spring Data Neo4j: Distinguishing Entity vs. Relationship Properties

In Spring Data Neo4j, nodes are typically represented by `@Node` entities; entity fields map to properties on the node. For relationships carrying their own data such as `WORKS_AT.role` and `WORKS_AT.startedOn`, you can model them using classes annotated with `@RelationshipProperties` combined with `@TargetNode` according to supported versions.

Conceptually:

```text
Person entity
  personId, fullName               → properties on (:Person)
  employment relationships         → WORKS_AT edges

Employment relationship properties
  assignmentId, role, startedOn    → properties on [:WORKS_AT]
  targetNode                       → (:Company) node

Company entity
  companyId, name                  → properties on (:Company)
```

Keep in mind:

- Relationships have **direction** and **type**; mapping configuration must match the stored direction.
- A person can have **multiple relationships of the same type**, including multiple stints at the same company if business rules allow.
- Updating one entity must not accidentally overwrite another relationship's data.
- When mixing mapped entities and custom Cypher on the same data, test the save/load behavior of your specific Spring Data Neo4j version.

Getting property placement right from the start enables Java applications to separate **entity data** from **link data** without guessing from field names.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `WORKS_AT.role` on `Person.role` when a person holds multiple jobs | Unclear which company the role belongs to; risks overwriting history | Place on the relationship or an `Employment` node |
| Putting `OrderLine.quantity` on `Product.quantity` | Confuses purchased quantity with global stock/inventory | Store quantity per order line |
| Using current `Product.price` for historical orders | Past orders change totals when product prices change | Store `unitPriceAtOrder` on the line-item edge or `OrderLine` node |
| Updating `r.role` without identifying the specific relationship | May overwrite all links between the same endpoint pair | Use a dedicated business ID such as `assignmentId` |
| Assuming at most one relationship exists between two nodes | Misses multiple employment stints or transactions | Define cardinality by business rules and write explicit queries |
| Using `SET r = {...}` when only updating one property | Drops other existing properties | Use `SET r.key = ...` or `SET r += {...}` |
| Equating `null` with an empty string or an ended status | Misinterprets missing data | Define statuses explicitly and use `IS NULL` where appropriate |
| Counting rows across multiple `MATCH` clauses as relationship counts | Overcounts due to Cartesian products between patterns | Use `DISTINCT` or explicit grouping/subqueries |
| Assuming an index on `Person.email` accelerates queries filtering `WORKS_AT.startedOn` | Misplaced performance expectations | Create indexes matching the label/type and filtered property |
| Turning every complex event into properties on a single edge | Difficult to attach statuses, receipts, and additional links | Consider an intermediate node with its own identity |

## 17. Self-Check Exercises

### Exercise 1. Classifying Where Properties Belong

Given the model `(:Student)-[:ENROLLED_IN]->(:Course)`, assign the following fields to nodes or relationships: `studentId`, `studentName`, `courseId`, `courseTitle`, `enrolledAt`, `finalGrade`.

**Suggested Answer:** `studentId` and `studentName` belong on `Student`; `courseId` and `courseTitle` belong on `Course`; `enrolledAt` and `finalGrade` belong on `ENROLLED_IN` because each student can enroll in multiple courses and grades vary per course.

### Exercise 2. Writing Queries to Read Properties at the Right Level

Using the `GE005-P001` dataset, return the person's name, company name, assignment ID, and role for each employment stint.

**Answer:**

```cypher
MATCH (p:Person {personId: 'GE005-P001'})
      -[r:WORKS_AT]->(c:Company)
RETURN p.fullName AS person,
       c.name AS company,
       r.assignmentId AS assignment,
       r.role AS role
ORDER BY assignment;
```

### Exercise 3. Reading Two SET Syntaxes

Given `r` with `{assignmentId: 'A001', role: 'Developer', startedOn: date('2021-03-01')}`, what happens if you execute:

```cypher
SET r += {role: 'Senior Developer'}
```

Versus:

```cypher
SET r = {role: 'Senior Developer'}
```

**Answer:** With `+=`, only `role` is updated and the other properties are preserved. With `=`, all properties are replaced by the new map; `assignmentId` and `startedOn` disappear, which may violate constraints or corrupt data.

### Exercise 4. Identifying Link Records

Account A transfers money to B three times, each with its own `eventId`. Where should `amount` be placed, and why?

**Answer:** On each `TRANSFERRED` relationship, or on a separate `Transfer` node per transaction if there is a complex workflow. `amount` belongs to **each transfer**, not as a global attribute of account A or B.

### Exercise 5. Adding Conditions to Prevent Wrong Updates

What risk does the following query have if a person was hired multiple times at the same company?

```cypher
MATCH (p:Person {personId: $personId})-[r:WORKS_AT]->
      (c:Company {companyId: $companyId})
SET r.role = $role;
```

**Answer:** The query modifies **every matching `WORKS_AT`**. Add `r.assignmentId = $assignmentId` or another business identifier predicate to update **the exact stint**; configure an appropriate constraint so link IDs do not collide.

### Exercise 6. Modeling Mindset

A conference attendance involves a ticket, payment, invoice, check-in/check-out history, and refund requests. Should everything live on `[:ATTENDED]` or should an `Attendance` node be created?

**Suggested Answer:** An `Attendance` node with its own identifier is usually better because the attendance itself has a lifecycle and multiple distinct relationships. You can use `(person)-[:HAS_ATTENDANCE]->(attendance)-[:FOR_EVENT]->(event)` and connect `attendance` to `Payment`, `Invoice`, and `Refund` as needed.

## 18. Summary

- **Node properties** describe **entities**: people, companies, products, orders. **Relationship properties** describe **connections or events** between two entities.
- Whenever a value varies by **node pair, timestamp, or interaction occurrence**, consider placing it on the relationship rather than attaching it globally to a node.
- Both nodes and relationships support reading and updating properties with syntax such as `properties(x)`, `keys(x)`, `SET x.key`, `SET x += {...}`, and `REMOVE x.key`.
- Multiple relationships can share the same type and endpoints. To update accurately, **identify each link** when the domain allows multiple records.
- Apply uniqueness constraints, indexes, and transactions to the proper **label/type and property**; never use `MERGE` with mutable properties to identify an entity.
- When a link requires its own **ID, lifecycle, and separate connections**, an intermediate node model such as `Employment` or `OrderLine` is often clearer and more extensible.

Properly distinguishing node and relationship properties lays the groundwork for designing meaningful property graphs, writing accurate Cypher, controlling ingestion, tuning queries, and mapping data with Neo4j Java Driver or Spring Data Neo4j.
