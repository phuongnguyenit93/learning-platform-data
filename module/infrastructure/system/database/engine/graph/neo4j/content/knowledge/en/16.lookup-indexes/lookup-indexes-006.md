# Token Lookup Indexes for Labels and Relationship Types in Neo4j

## Lesson Objectives

After completing this lesson, you will be able to:

- Explain how **token lookup indexes** help Neo4j find nodes by **label** and relationships by **type**.
- Distinguish lookup indexes from property indexes, uniqueness constraints, and other property-query index types.
- Inspect, recreate when needed, and observe lookup index usage via Cypher and execution plans.
- Recognize scenarios where a lookup index helps, where it falls short, and operational considerations for large graphs.

This lesson belongs to the **Lookup Indexes** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j stores data as a *property graph*: nodes carry *labels*, relationships carry *types*, and both can hold properties. When learning Cypher, many queries start by finding nodes with a given label or edges of a given type. **Token lookup indexes** are designed for this structural lookup step.

## 1. Why Are Lookups by Label and Relationship Type Needed?

Suppose an e-commerce system holds millions of nodes with labels `Customer`, `Order`, `Product` and multiple relationship types such as `PLACED`, `CONTAINS`, and `VIEWED`:

~~~cypher
MATCH (c:Customer)
RETURN c.customerId
LIMIT 20;
~~~

This query needs to find nodes carrying the **`Customer` label**. It does not search by a specific `customerId` or require any other property value. Another example:

~~~cypher
MATCH (c)-[r:PLACED]->(o)
RETURN r
LIMIT 20;
~~~

The second query asks for relationships of **type `PLACED`**. When neither endpoint is narrowed down beforehand, the database needs a way to locate relationships of that type.

Token lookup indexes help Neo4j find groups of graph elements by structural token:

| Element | Indexed Token | Example Query |
| --- | --- | --- |
| Node | Label | `MATCH (n:Customer) RETURN n` |
| Relationship | Relationship type | `MATCH ()-[r:PLACED]->() RETURN r` |

A node can carry **multiple labels**, such as `(n:Customer:Premium)`; it can appear when looking up each applicable label. Every relationship has **one type**, such as `PLACED`.

Conceptually, a lookup index acts like a lookup table mapping **token → elements carrying that token**. Neo4j manages internal storage and querying; applications do not need to maintain manual lists of node IDs per label or edge IDs per type.

~~~mermaid
flowchart LR
    Q["Cypher: MATCH (n:Customer)"] --> L["Look up Customer label token"]
    L --> N["Nodes carrying label Customer"]
    R["Cypher: MATCH ()-[r:PLACED]->()"] --> T["Look up PLACED type token"]
    T --> E["Relationships of type PLACED"]
~~~

Crucial point: a lookup index answers **"which elements belong to this label/type?"**. It does not directly answer **"which customer has a specific email?"**.

## 2. Two Categories of Token Lookup Indexes

### 2.1. Node Label Lookup Index

A node lookup index serves node access by label, for example:

~~~cypher
MATCH (p:Person)
RETURN p.name
LIMIT 10;

MATCH (p:Person:Employee)
RETURN p.employeeId;
~~~

In the two-label query, the database engine may use lookup information for one label and filter on the remaining label, or choose another plan based on statistics. A lookup index does not mean a separate composite index exists for every label combination.

### 2.2. Relationship Type Lookup Index

A relationship lookup index helps find relationships by type:

~~~cypher
MATCH ()-[r:WORKS_AT]->()
RETURN r
LIMIT 10;

MATCH (a)-[r:PURCHASED]->(b)
RETURN a, r, b
LIMIT 10;
~~~

In the example above, the second query can leverage a lookup on `PURCHASED` when it needs to locate relationships starting from the type. However, if a highly selective endpoint node has already been found, Neo4j can instead **expand relationships from that node** (*expand*) and check the type. The execution strategy depends on the plan selected by the query planner.

**Do not confuse:** Looking up type `PURCHASED` looks up the *relationship type*, not a substring inside a relationship property.

## 3. Creating and Inspecting Lookup Indexes with Cypher

### 3.1. Checking Existing Indexes

In modern Neo4j 5.x versions, a newly created database typically already has a system-created **node label lookup index** and **relationship type lookup index**. Therefore, inspect first rather than creating duplicates out of habit.

~~~cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state
RETURN name, entityType, state
ORDER BY entityType;
~~~

Typical output contains one `NODE` row and one `RELATIONSHIP` row, with `state` equal to `ONLINE` once ready to serve queries. **System-assigned index names may differ across databases**; do not hardcode fixed names in operational scripts.

You can also view them alongside other index types:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, state
WHERE type = 'LOOKUP'
RETURN name, type, entityType, state;
~~~

If an index is still being created, its state may reflect active population; treat it as ready only when the state is appropriate, typically `ONLINE`.

### 3.2. Creating a Node Label Lookup Index

When recreating a dropped index or initializing a database lacking one:

~~~cypher
CREATE LOOKUP INDEX node_label_lookup_index IF NOT EXISTS
FOR (n)
ON EACH labels(n);
~~~

Syntax breakdown:

- `CREATE LOOKUP INDEX` explicitly specifies the **lookup** index type.
- `node_label_lookup_index` is the operator-chosen index name.
- `IF NOT EXISTS` avoids an error if a matching index already exists or the name is already taken under Neo4j's rules; inspect the actual schema afterward.
- `FOR (n) ON EACH labels(n)` defines the index over the **label tokens** of nodes. This does not target one specific label.

### 3.3. Creating a Relationship Type Lookup Index

~~~cypher
CREATE LOOKUP INDEX relationship_type_lookup_index IF NOT EXISTS
FOR ()-[r]-()
ON EACH type(r);
~~~

`FOR ()-[r]-()` targets relationships; `ON EACH type(r)` extracts the **relationship type token**. This index serves all relationship types in the same database—not a separate index for `PLACED` or `WORKS_AT`.

**Scope and limits:** Neo4j supports one node lookup index and one relationship lookup index per database. Do not create a second lookup index dedicated to `Customer` or `PLACED`. If the corresponding index already exists, `IF NOT EXISTS` will not create a second one. Use `SHOW LOOKUP INDEXES` to confirm after DDL.

### 3.4. Dropping Indexes in Operations

If you must drop a lookup index, retrieve its **exact existing name** from `SHOW LOOKUP INDEXES`:

~~~cypher
// Example only: use the actual index name on the target database.
DROP INDEX node_label_lookup_index IF EXISTS;
~~~

Dropping a lookup index can make label/type lookup queries more expensive; do not treat dropping it as a routine optimization. On a database serving live applications, assess impact, schema privileges, and recovery steps before acting.

## 4. Testing on a Small Graph

Suppose we create employee and company data:

~~~cypher
MERGE (p:Person {personId: 'P-001'})
SET p.name = 'An'
MERGE (c:Company {companyId: 'C-001'})
SET c.name = 'GraphLab'
MERGE (p)-[:WORKS_AT]->(c);
~~~

The example uses `MERGE` for easy re-execution while learning, but note that `MERGE` does not replace a **uniqueness constraint** under concurrent write transactions. For real data, design proper business keys and constraints.

Query nodes by label:

~~~cypher
MATCH (p:Person)
RETURN p.personId AS id, p.name AS name;
~~~

Query relationships by type:

~~~cypher
MATCH (p)-[r:WORKS_AT]->(c)
RETURN p.name AS person, type(r) AS relation, c.name AS company;
~~~

In both queries, `Person` and `WORKS_AT` are **tokens**; `personId`, `name`, and `companyId` are **properties**.

### Using EXPLAIN and PROFILE

`EXPLAIN` shows the plan Neo4j expects to use without running the query. `PROFILE` actually executes the query and reports row counts, storage accesses (*DB Hits*), and execution operators:

~~~cypher
EXPLAIN
MATCH (p:Person)
RETURN p.personId
LIMIT 10;

PROFILE
MATCH ()-[r:WORKS_AT]->()
RETURN r
LIMIT 10;
~~~

In the plan, you may see operators such as `NodeByLabelScan` (looking up nodes by label), `DirectedRelationshipTypeScan`, or `UndirectedRelationshipTypeScan` (scanning relationships by type), depending on pattern direction and Neo4j version. These indicate label/type-based access. **Do not judge solely by operator names:** examine the full plan, `ONLINE` index state, cardinality, and DB Hits.

Also avoid using queries like `MATCH (n:Person) RETURN count(n)` as strict proof that a lookup index was used: Neo4j can optimize counts using separate mechanisms such as the count store.

## 5. How Do Token Lookup Indexes Differ from Property Indexes?

This is the core of index design in a property graph.

~~~cypher
// Label present; property predicate checks email for a specific value.
MATCH (c:Customer)
WHERE c.email = $email
RETURN c;
~~~

A lookup index helps reach the set of nodes labeled `Customer`, yet **it does not index `email` values**. If that set is very large, filtering node by node is inefficient. When queries frequently search by email, consider adding a property index:

~~~cypher
CREATE RANGE INDEX customer_email_range IF NOT EXISTS
FOR (c:Customer)
ON (c.email);
~~~

Now the query planner can choose the property index to locate nodes by `email` value when cost-effective. There is no guarantee that every query with `WHERE` uses an index; the planner weighs predicates, statistics, and alternative graph access paths.

| Type | What It Indexes | Typical Query | Does Not Replace |
| --- | --- | --- | --- |
| **Node token lookup** | Node labels | `MATCH (n:Customer)` | Searching by `email`, `age`, `createdAt` |
| **Relationship token lookup** | Relationship types | `MATCH ()-[r:PLACED]->()` | Searching edges by `orderTime`, `amount` |
| **Range property index** | Property values on nodes or relationships | `c.email = $email`, suitable value ranges | Database-wide lookup of every label/type |
| **Text/full-text index** | Text content per each type's capabilities and syntax | Substrings/prefixes; text search | Token lookup of labels/types |
| **Uniqueness constraint** | Rule preventing duplicate keys; usually backed by an index | Unique `customerId` identity | Scanning an entire label or type |

A constraint such as:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

serves **customer identity integrity** and includes a backing index for key validation/lookup. It is not a token lookup index. Conversely, a lookup index **does not prevent** two `Customer` nodes from sharing the same `customerId`.

### When a Query Has Multiple Predicates

~~~cypher
MATCH (c:Customer)-[r:PLACED]->(o:Order)
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
RETURN o.orderId, r;
~~~

A reasonable plan might start from an index on `Customer.customerId`, then **expand** across `PLACED` relationships and filter `Order.status`. Neo4j does not necessarily have to use a lookup index for `Customer`, `Order`, or `PLACED` in this case. The goal is an **efficient plan**, not forcing every query to use a token lookup index.

## 6. Common Misconceptions

### "Every label needs its own lookup index"

No. One node lookup index covers label tokens across the database. `ON EACH labels(n)` does not single out `:Person` or `:Product`.

### "Having a lookup index makes property queries fast"

Not enough. A lookup index brings you to elements carrying the label/type; filtering `WHERE c.email = ...` still requires a suitable plan and usually benefits from a property index or constraint on the lookup key.

### "A relationship type lookup index indexes every edge traversal"

No. Once a starting node is already known, Neo4j can traverse relationships adjacent to that node and check the type without scanning all relationships of that type. Multi-hop path queries such as:

~~~cypher
MATCH (a:Person {personId: $personId})-[:KNOWS*1..3]->(b:Person)
RETURN DISTINCT b;
~~~

still depend heavily on branching factor, depth, and path count. A lookup index does not eliminate overall graph traversal costs.

### "Adding or removing labels has nothing to do with lookup indexes"

Lookup indexes reflect the labels and relationship types of current data. When adding/removing node labels or creating/deleting relationships, the system must maintain the corresponding lookup structures. That is part of write overhead in exchange for token-based lookup support.

### "Creating a lookup index prevents duplicate nodes/relationships"

No. Preventing duplicate business data requires **identifying keys**, appropriate `MERGE` logic, constraints, and concurrency control. Lookup indexes do not enforce that each label has only one node or each type has only one relationship.

### "Writing WHERE labels(n) or type(r) guarantees a lookup index is used"

You cannot conclude that. A Cypher pattern expressing static labels/types, such as `(n:Customer)` or `[r:PLACED]`, helps the planner recognize structural conditions. Dynamic expressions or function-based filters may produce different plans depending on the Neo4j version. Always verify with `EXPLAIN`/`PROFILE`, especially when labels/types are built from runtime inputs.

## 7. Observing and Operating Lookup Indexes

When a label/type query is unexpectedly slow, check in order:

1. **Current schema:** run `SHOW LOOKUP INDEXES` to confirm both `NODE` and `RELATIONSHIP` entries exist and check their states.
2. **Query shape:** determine whether the query selects by label/type or filters primarily by properties; many cases need a range index or property constraint.
3. **Execution plan:** run `EXPLAIN` first, and `PROFILE` on safe-to-run queries to examine operators, DB Hits, and row counts.
4. **Selectivity:** an `Event` label might encompass nearly the entire dataset, so even with a lookup index, iterating over huge numbers of nodes remains costly.
5. **Traversal starting point:** if an endpoint key is known, try structuring the query to start from the selective node before expanding relationships.
6. **Write impact:** under heavy node creation/deletion, label changes, or relationship churn, factor index maintenance costs into overall operational capacity.

Example query requiring strategy evaluation:

~~~cypher
MATCH (e:Event)
WHERE e.occurredAt >= datetime($fromTime)
RETURN e
ORDER BY e.occurredAt DESC
LIMIT 100;
~~~

A label lookup index on `Event` does not itself support time-range filtering or sorting by `occurredAt`. If this query runs frequently across many events, evaluate a property range index:

~~~cypher
CREATE RANGE INDEX event_time_range IF NOT EXISTS
FOR (e:Event)
ON (e.occurredAt);
~~~

Plan differences before and after adding a property index must be measured on representative data; do not infer speedup merely because DDL succeeded.

## 8. Self-Check Practice

**Scenario:** A school management graph contains `Student` nodes, `Course` nodes, and `ENROLLED_IN` relationships. Predict which index type suits each query:

~~~cypher
// A. Fetch a batch of students for display.
MATCH (s:Student) RETURN s LIMIT 10;

// B. Find a student by unique ID.
MATCH (s:Student {studentId: $id}) RETURN s;

// C. Find enrollment relationships by type.
MATCH ()-[r:ENROLLED_IN]->() RETURN r LIMIT 10;

// D. Find a course by code.
MATCH (c:Course) WHERE c.code = $code RETURN c;
~~~

**Suggested explanations:**

- **A:** the node label lookup index can help find the `Student` node set.
- **B:** a property index or uniqueness constraint on `Student.studentId` is usually more suitable when looking up by ID.
- **C:** the relationship type lookup index can help find `ENROLLED_IN` relationships when endpoints are unknown.
- **D:** a property index or uniqueness constraint on `Course.code` is appropriate if course codes are queried frequently.

To verify on a real database, run `SHOW LOOKUP INDEXES`, then use `EXPLAIN` or `PROFILE` for A–D and compare execution operators. Observe whether the planner starts from a token, property index, count store, or specific node before expanding relationships.

## 9. Checklist to Remember

- Token lookup indexes only index **node labels** and **relationship types**.
- Modern Neo4j usually pre-creates **one node lookup index** and **one relationship lookup index** for new databases; inspect before running DDL.
- Node syntax is `ON EACH labels(n)`; relationship syntax is `ON EACH type(r)`.
- `SHOW LOOKUP INDEXES` lets you inspect index names, target entities, and states.
- `EXPLAIN` and `PROFILE` reveal how the planner actually accesses data.
- For searches by **property value**, consider an appropriate property index or constraint.
- Lookup indexes assist in accessing graph elements; they **do not enforce uniqueness** and **do not replace path traversal optimization**.

**Conclusion:** Token lookup indexes form the structural access layer in Neo4j: finding nodes by label and relationships by type. Knowing that they operate at the **token** level rather than the **property value** level enables you to design Cypher queries and schema indexes purposefully while interpreting execution plans with solid grounding.
