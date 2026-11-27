# Nodes, Labels, and Properties in the Property Graph Model

## 1. Learning Objectives and Context

Neo4j is a graph database that uses the **property graph model**. In the `DATABASE_ENGINE_GRAPH_NEO4J` module, this model serves as the foundation for representing highly connected data, querying relationships and paths with **Cypher**, and then advancing to designing indexes, constraints, data ingestion, Java Driver/Spring Data Neo4j integration, and system operations.

After this lesson, you will be able to:

- Explain **node**, **label**, and **property**; distinguish their roles from **relationship**.
- Model an entity as a node with one or more labels and an appropriate set of properties.
- Use Cypher to create, search, read, and update nodes, labels, and properties.
- Understand how Neo4j handles missing properties, `null`, data types, and node identity.
- Know when to use uniqueness constraints and indexes, and when to split data into nodes with relationships.

Imagine an HR system: people, companies, and skills can all become nodes; a person working for a company or knowing a skill is represented by a relationship. This lesson focuses on the **anatomy of each node**; relationships are mentioned only to place the components in the right context.

## 2. Basic Structure of a Property Graph

A property graph consists of **nodes** and **relationships**. Both can carry properties; a node can have one or more labels. For example:

```text
(:Person:Employee {
    personId: "p001",
    fullName: "Nguyễn An",
    active: true
})
          |
          | [:WORKS_AT {since: 2023}]
          v
(:Company {
    companyId: "c001",
    name: "GreenTech"
})
```

| Component | Meaning | Example |
| --- | --- | --- |
| **Node** | An entity in the graph with its own identity | Node representing Nguyễn An |
| **Label** | Classification/role attached to a node; a node can carry multiple labels | `:Person`, `:Employee` |
| **Property** | `key: value` pair storing information on a node or relationship | `fullName: "Nguyễn An"` |
| **Relationship** | Directed, typed connection between two nodes | `[:WORKS_AT]` |

In Cypher syntax:

- `(p)`: variable `p` represents a node, without restricting its labels.
- `(p:Person)`: node with the `Person` label.
- `(p:Person:Employee)`: the same node has **both** the `Person` and `Employee` labels.
- `(p:Person {personId: 'p001'})`: node with the `Person` label and property `personId` holding the value `'p001'`.
- `(p)-[:WORKS_AT]->(c)`: relationship from node `p` to node `c`; the arrow direction is part of the model.

**Note:** A `Person` node is not a row in a `Person` table in the mandatory sense of relational databases. Neo4j allows nodes with the same label to carry different sets of properties; modeling conventions and constraints help keep data consistent.

## 3. Node: An Entity with Identity

A **Node** is the unit representing a thing, person, event, or concept to be stored and connected. Examples: customer, account, order, product, location. Each node exists independently of its property values: two nodes with the same name and date of birth are still **two different nodes** if created separately.

In Neo4j, the `CREATE` clause creates a new node:

```cypher
CREATE (p:Person:Employee {
  personId: 'p001',
  fullName: 'Nguyễn An',
  age: 29,
  active: true,
  skills: ['Java', 'Cypher'],
  joinedOn: date('2024-07-01')
})
RETURN p;
```

Here, `p` is a local variable within the query, **not a property stored in the database**. The node has two labels and six properties, and is persisted after the write query succeeds. If you run `CREATE` again, Neo4j will create **another node**; `CREATE` itself does not automatically check for duplicate `personId` values.

### 3.1. Technical Identity and Business Identifier

Neo4j provides `elementId(p)` to reference an element in certain operations. However, you should not treat `elementId` as a stable business key when exporting/importing, recreating, or migrating data. Applications typically need a dedicated property such as `personId`, `customerId`, or `orderId`:

```cypher
MATCH (p:Person {personId: 'p001'})
RETURN p.personId AS personId, elementId(p) AS elementId;
```

**Principle:** Use an immutable business identifier for lookups, cross-system exchange, and linking via APIs; apply a **uniqueness constraint** to prevent two nodes with the same label from carrying the same identifier (see Section 8).

## 4. Label: Classifying and Expressing Node Roles

A label is a classification name placed after `:` in Cypher. You do not need to declare a table or pre-create a label: when you write a node with a label, Neo4j uses that label name in the data. Labels have **set** semantics: a node can carry multiple labels; multiple nodes can carry the same label.

For example, an employee is also a person:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p:Mentor
RETURN labels(p) AS labels;
```

The result is a list of labels that may include `Person`, `Employee`, `Mentor` (you should not rely on the element order of this list). If the `Mentor` role is no longer applicable:

```cypher
MATCH (p:Person {personId: 'p001'})
REMOVE p:Mentor
RETURN labels(p) AS labels;
```

### 4.1. When to Use a Label vs. a Property?

| Design Question | Usually use a **label** | Usually use a **property** |
| --- | --- | --- |
| Representing a meaningful entity group/role in the graph? | `:Person`, `:Employee`, `:Company` | Not the primary choice |
| Filtering by status or a value that changes frequently? | No need to create a new label for every value | `status: 'ACTIVE'`, `age: 29` |
| Need to query all nodes of a type, or define constraints/indexes by type? | Yes: `MATCH (p:Person)` | Can add property filters |
| Is it a nearly unique value per node? | Do not use labels like `:Person_p001` | `personId: 'p001'` |

Naming conventions should be clear and consistent: labels such as `Person`, `Order`, `Customer`, and properties such as `personId`, `createdAt`. Neo4j is case-sensitive: `:Person` differs from `:person`, and `fullName` differs from `fullname`.

A label does not automatically guarantee that every `:Person` node has `personId` or `fullName`. Enforcing required properties, uniqueness checks, or type checks may require constraints and application rules.

## 5. Property: Data Describing a Node

A property is a **key–value** pair. In the example `{fullName: 'Nguyễn An', age: 29}`, `fullName` and `age` are keys; `'Nguyễn An'` and `29` are values. Even with the same label, nodes can have different properties:

```cypher
CREATE (:Person {personId: 'p002', fullName: 'Bình'});
CREATE (:Person {personId: 'p003', fullName: 'Chi', email: 'chi@example.com'});
```

Therefore, you cannot infer that every `Person` node has an `email`. Lacking an `email` property is still a valid data state if the model does not require it.

### 5.1. Common Value Types

| Group | Property Example | Cypher Syntax |
| --- | --- | --- |
| String (`STRING`) | Name, email, business ID | `fullName: 'Nguyễn An'` |
| Integer (`INTEGER`) | Age, login count | `age: 29` |
| Float (`FLOAT`) | Average score, measured coordinates | `rating: 4.5` |
| Boolean (`BOOLEAN`) | Activation status | `active: true` |
| Date, time, and duration | Join date, creation timestamp | `joinedOn: date('2024-07-01')`, `createdAt: datetime()` |
| Spatial coordinates | Geographic location | `location: point({latitude: 10.82, longitude: 106.63})` |
| List of simple values | Skills, application-managed keyword tags | `skills: ['Java', 'Cypher']` |

When **storing as a property**, Neo4j supports valid property value types, including primitives, spatial types, temporal types, and homogeneous lists of simple values. **Nested maps**, lists containing nodes/relationships, or arbitrary object structures can exist in Cypher expressions but **cannot be assigned directly as a stored property**. Split them into flat properties or linked nodes depending on the nature of the data.

The following example illustrates a map used temporarily for processing inside a query, not a stored property:

```cypher
WITH {city: 'Hà Nội', postalCode: '100000'} AS address
RETURN address.city AS city;
```

If an address is just simple information for one person, you can use `city` and `postalCode` as two properties. If an address needs to be shared among multiple people, requires change history, or needs pathfinding across locations, consider `:Address`/`:Location` nodes and relationships.

### 5.2. `null` and Missing Properties

In Neo4j, **a property with a `null` value is not stored as a regular key–value pair**. Assigning `null` to a property has the effect of **removing** that property:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p.nickname = 'An'
RETURN p.nickname AS nickname;

MATCH (p:Person {personId: 'p001'})
SET p.nickname = null
RETURN p.nickname AS nickname;
```

In the second query, `nickname` is removed; reading `p.nickname` will return `null`. Check queries:

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.personId AS personId;

MATCH (p:Person)
WHERE p.email IS NOT NULL
RETURN p.personId AS personId, p.email AS email;
```

`IS NULL` also matches cases where the property key does not exist; to provide a fallback value when reading, use `coalesce(p.email, 'Not provided')`. Do not confuse `null` with an empty string `''`, `false`, or `0`: those values can be stored and carry their own meaning.

### 5.3. Reading Multiple Properties

```cypher
MATCH (p:Person {personId: 'p001'})
RETURN
  p.fullName AS fullName,
  keys(p) AS propertyKeys,
  properties(p) AS allProperties,
  labels(p) AS nodeLabels;
```

- `p.fullName` accesses a single property by name.
- `keys(p)` returns the property keys that currently exist.
- `properties(p)` returns a map containing the existing properties.
- `labels(p)` returns the list of labels, not properties.

## 6. Working with Nodes, Labels, and Properties in Cypher

The following examples demonstrate individual operations. When practicing on the same database, note that `CREATE` can create duplicate data if executed multiple times.

### 6.1. Finding Nodes by Label and Conditions

```cypher
MATCH (p:Person)
WHERE p.active = true AND p.age >= 18
RETURN p.personId AS id, p.fullName AS name, p.age AS age
ORDER BY name;
```

`MATCH (p:Person)` narrows the candidate set by label; `WHERE` filters by property values. In large graphs, an appropriate index can help reduce the amount of data scanned (see Section 8).

### 6.2. Updating Properties While Preserving Others

```cypher
MATCH (p:Person {personId: 'p001'})
SET p.age = 30,
    p.department = 'Engineering'
RETURN p;
```

You can merge a set of properties from a map:

```cypher
MATCH (p:Person {personId: 'p001'})
SET p += {age: 31, active: true}
RETURN p;
```

`SET p += {...}` only updates/adds the specified keys (keys with a `null` value are removed). Conversely, `SET p = {...}` **replaces the entire property set** of the node, which can drop properties not listed in the map; only use it when that is intentional.

Remove a property with `REMOVE`:

```cypher
MATCH (p:Person {personId: 'p001'})
REMOVE p.department
RETURN keys(p) AS remainingKeys;
```

### 6.3. Using Parameters Instead of String Concatenation in Queries

Java/Spring Data Neo4j applications typically pass data via **Cypher parameters**, such as `$personId` and `$fullName`. This separates query structure from data, enables query plan reuse, and mitigates Cypher injection risks:

```cypher
MATCH (p:Person {personId: $personId})
SET p.fullName = $fullName
RETURN p.personId AS id, p.fullName AS name;
```

When executing the query, the client supplies the corresponding parameter map, such as `{personId: 'p001', fullName: 'Nguyễn An'}`. The `$` prefix is part of the parameter syntax, not part of the property name in the database.

### 6.4. `MERGE` to Find or Create a Node by a Defined Key

`MERGE` attempts to match a node pattern; if no matching pattern exists, it creates one. With a dedicated identifier key, it is typically written as:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET
  p.fullName = $fullName,
  p.createdAt = datetime()
RETURN p;
```

`MERGE` **does not replace a uniqueness constraint** when there are concurrent transactions. Create a constraint on `personId` first to safeguard uniqueness. Avoid putting mutable properties like `fullName` or `email` into the `MERGE` pattern map, because changed values can cause the pattern not to match and lead to unintended node creation.

## 7. Modeling Example: Customers and Orders

Suppose an ordering platform needs to store customer information and orders. A simple model:

```text
(:Person:Customer {customerId, fullName, email})
                  |
                  | [:PLACED]
                  v
          (:Order {orderId, totalAmount, placedAt})
```

**Why separate the `Order` node?** A customer can place multiple orders; each order has its own identifier, order date, total amount, and separate relationships to products, shipping, or payments. Storing all orders in a string or list on the customer node would make querying individual orders, updating them, and traversing their connections much harder.

Create sample data:

```cypher
CREATE (c:Person:Customer {
  customerId: 'C001',
  fullName: 'Lan',
  email: 'lan@example.com'
})
CREATE (o:Order {
  orderId: 'O101',
  totalAmount: 850000,
  placedAt: datetime('2025-03-15T10:30:00+07:00')
})
CREATE (c)-[:PLACED]->(o)
RETURN c, o;
```

Query customer names and the orders they placed:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       c.fullName AS customerName,
       o.orderId AS orderId,
       o.totalAmount AS totalAmount;
```

This example illustrates three layers of meaning:

1. **Node** `c` represents a customer; `o` represents a distinct order.
2. **Label** `Person` and `Customer` both classify node `c`; `Order` classifies node `o`.
3. **Property** stores the attributes of each entity; **relationship** `PLACED` expresses that the customer placed the order.

In real-world datasets, you should configure constraints on `customerId` and `orderId` and choose a deduplication strategy before bulk importing.

## 8. Indexes and Constraints Associated with Labels/Properties

A property graph is structurally flexible, but production systems usually need to control data quality and query speed. Two foundational mechanisms:

| Tool | Purpose | Example |
| --- | --- | --- |
| **Constraint** | Enforces integrity rules, such as preventing duplicate ID values among nodes with the same label | Unique `Person.personId` |
| **Index** | Speeds up lookups by label and property in appropriate query patterns | Looking up `Person.fullName` |

Create a uniqueness constraint for person IDs:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Create an index on names:

```cypher
CREATE INDEX person_full_name_idx IF NOT EXISTS
FOR (p:Person)
ON (p.fullName);
```

Check existing definitions:

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

A uniqueness constraint prevents **two equal `personId` values**, but **does not automatically require every `Person` node to have this property**. To require both existence and uniqueness, look into existence constraints/node keys and the support conditions for your Neo4j version and edition.

To inspect the execution plan of a query:

```cypher
EXPLAIN
MATCH (p:Person {personId: 'p001'})
RETURN p;
```

`EXPLAIN` only plans the query without executing it. When an appropriate index/constraint exists, the optimizer **may** use an index lookup operation; the exact decision depends on the data, statistics, query conditions, and Neo4j version. Do not assume that having an index automatically makes every query faster.

## 9. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a separate label for each person, e.g., `:Person_C001` | Hard to query across the entity type; generates many labels with no modeling meaning | Use `:Person` and `personId: 'C001'` |
| Assuming `CREATE` guarantees `personId` uniqueness | May create two nodes representing the same entity | Use a business key, uniqueness constraint, and appropriate ingestion strategy |
| Using a mutable person name or email as a long-term unique identifier | Name/email changes destabilize business links | Prefer a durable ID; validate email separately if required by business rules |
| Storing a list of nested objects in a single property | Incompatible with stored property types and hard to query relationships | Split into primitive properties or nodes/relationships |
| Treating `null` the same as an empty string | Incorrect filtering and update results | Use `IS NULL`/`IS NOT NULL` and clearly define the meaning of missing data |
| Using `SET n = {...}` when only intending to modify one field | Loses fields omitted from the map | Use `SET n.key = value` or `SET n += {...}` |
| Confusing `:Person` with `:person`, or `fullName` with `fullname` | Queries fail to find expected data | Apply consistent naming conventions; inspect `labels(n)`/`keys(n)` |
| Treating `elementId(n)` as an immutable business ID | Can lose stability when data is recreated or moved across environments | Store a dedicated business identifier |

A useful rule of thumb when choosing between a **property** and a **node**: if the data simply describes a single entity, a property is usually enough; if the object has its own identity, multiple attributes, multiple links, or needs to be queried independently, consider a node.

## 10. Guided Practice

To avoid affecting real data, run the practice exercises in a test database. The statements below assume there is no `Skill` node with code `S001` yet.

**Exercise 1 – Create a multi-label node and read properties**

```cypher
CREATE (s:Skill:TechnicalSkill {
  skillId: 'S001',
  name: 'Cypher',
  level: 'BEGINNER'
})
RETURN labels(s) AS labels,
       properties(s) AS properties;
```

Observe that `Skill` and `TechnicalSkill` are **two labels on the same node**, while `skillId`, `name`, and `level` are properties.

**Exercise 2 – Modify properties and labels**

```cypher
MATCH (s:Skill {skillId: 'S001'})
SET s.level = 'INTERMEDIATE'
SET s:QueryLanguageSkill
REMOVE s:TechnicalSkill
RETURN labels(s) AS labels, s.level AS level;
```

Expected: the node keeps the `Skill` label, gains the `QueryLanguageSkill` label, and no longer has `TechnicalSkill`; `level` holds the value `INTERMEDIATE`. Changing labels does not create a new node.

**Exercise 3 – Check a missing property**

```cypher
MATCH (s:Skill {skillId: 'S001'})
REMOVE s.level
RETURN s.level AS level,
       'level' IN keys(s) AS hasLevel;
```

Expected: `level` returns `null`, `hasLevel` is `false`. The reason is that the `level` property is no longer stored on the node.

If you want to test uniqueness, first create a `skillId` constraint on the `Skill` label in the test database, then try creating two nodes with the same `skillId`; the second operation must be rejected if both carry the `Skill` label and the constraint is active.

## 11. Summary

- **Node** represents an entity with identity; **label** classifies/assigns roles; **property** stores key–value pairs; **relationship** connects nodes.
- A node can have multiple labels and a flexible set of properties. A label does not automatically enforce that all nodes have the same properties.
- `CREATE` creates new elements; `MATCH` queries; `SET` updates properties/labels; `REMOVE` deletes properties/labels; `MERGE` finds or creates by pattern.
- Properties do not directly store `null` values; missing keys read back as `null`. Avoid storing nested maps as a single property and choose appropriate data types.
- Use business identifiers alongside appropriate constraints to manage entities; use indexes for actual query needs. Model objects with their own connections as nodes and relationships when needed.

Mastering the three core elements — **node – label – property** — helps you write accurate Cypher patterns, avoid duplicate data, and build the foundation for upcoming lessons on relationships, paths, indexing, query tuning, and integrating Neo4j with Java applications.
