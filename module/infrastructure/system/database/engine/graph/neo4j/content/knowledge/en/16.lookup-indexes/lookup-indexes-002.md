# Distinguishing Indexes from Constraints and Backing Indexes

## 1. Context: Both Involve an "Index", Yet Serve Two Different Purposes

Neo4j stores data as a **property graph** consisting of nodes, relationships, labels, relationship types, and properties. When working with large graphs, two needs often arise together:

- **Fast lookups:** looking up a `Book` by `isbn`, finding `Customer` nodes with a specific `email`, or scanning nodes by label.
- **Data integrity:** preventing two books from sharing the same `isbn`, requiring an identifier to exist, or enforcing a property's data type.

An **index** primarily creates an access path so queries can locate data more efficiently. A **constraint** defines a validity rule that Neo4j checks when creating or modifying data. Some constraints require an **index owned by the constraint itself** to verify the rule quickly. Therefore, seeing an index in `SHOW INDEXES` is not enough to conclude whether an operator created it independently or a constraint created it.

This lesson belongs to the **Lookup Indexes** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module; it focuses on the relationship between lookup indexes, property indexes, and schema constraints. Examples use `CREATE … INDEX` and `CREATE CONSTRAINT … FOR … REQUIRE` syntax from Neo4j 5 and later. For older Neo4j versions, verify your version because schema management syntax may differ.

**Expected outcomes:** after this lesson, you will be able to identify which indexes are standalone indexes, which belong to a constraint, and which constraints have no associated index; inspect them yourself using `SHOW INDEXES` and `SHOW CONSTRAINTS`; and choose properly between performance requirements and data integrity requirements.

## 2. Three Concepts to Distinguish

| Object | Primary Function | Created With | When Data Violates Rules? | Who Manages Lifecycle? |
|---|---|---|---|---|
| **Standalone property index** | Provides fast access paths for matching filters/queries | `CREATE RANGE/TEXT/POINT INDEX`, etc. | Does not block duplicates, missing values, or wrong types | Administrator creates/drops via `CREATE INDEX` / `DROP INDEX` |
| **Token lookup index** | Looks up nodes by **label** or relationships by **type** | Usually pre-created on database creation; can be recreated with `CREATE LOOKUP INDEX` | Does not enforce uniqueness, existence, or type rules on properties | Maintained by the database; should not be dropped casually |
| **Constraint** | Enforces business validity rules on data | `CREATE CONSTRAINT` | Violating write statements are rejected | Administrator creates/drops via `CREATE CONSTRAINT` / `DROP CONSTRAINT` |
| **Backing index (constraint-owned index)** | Supports `UNIQUE`/`KEY` checks and can assist property queries | Created **automatically by Neo4j alongside the constraint** | The **constraint** itself determines whether a write is valid | Tied to the constraint; dropping the constraint drops its backing index |

> **Terminology note:** In official Neo4j terminology, "lookup index" specifically means a **token lookup index** (an index for node labels or relationship types). "Backing index" means an **index owned by a constraint**. These two terms are not synonymous, even though both are indexes.

The relationships can be visualized as follows:

~~~mermaid
flowchart TD
    A["Cypher Query"] --> B["Query Planner"]
    B --> C["Lookup index: label/type"]
    B --> D["Property index: RANGE/TEXT/POINT"]
    B --> E["Backing RANGE index"]
    F["Write command CREATE/SET/MERGE"] --> G["Constraint UNIQUE/KEY"]
    G --> E
    G --> H["Accept or reject data"]
~~~

Neo4j's query planner **may** use a suitable index when reading data; the mere existence of an index does not guarantee every query will use it. Conversely, constraints are enforced whenever data is modified, regardless of any specific read query plan.

## 3. Lookup Indexes: Looking Up Labels and Relationship Types

A new Neo4j database usually comes with **two token lookup indexes**: one for node labels and one for relationship types. Inspect them with:

~~~cypher
SHOW LOOKUP INDEXES;
~~~

If your version or administration tool uses the general index listing, you can view them with:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, owningConstraint
WHERE type = 'LOOKUP'
RETURN name, type, entityType, owningConstraint
ORDER BY entityType;
~~~

You will typically see one row with `entityType = 'NODE'` and one with `entityType = 'RELATIONSHIP'`; `type = 'LOOKUP'`, and `owningConstraint` is `null`. Index names may be system-generated, so do not rely on a hardcoded name in checks.

Two example queries assisted by token lookup indexes for label or relationship type conditions:

~~~cypher
MATCH (b:Book)
RETURN count(b) AS soSach;
~~~

~~~cypher
MATCH ()-[r:BOUGHT]->()
RETURN count(r) AS soQuanHeMua;
~~~

Lookup indexes **do not store property–value pairs** to directly resolve conditions such as `b.isbn = 'B-001'`. For efficient property lookups, look to property index types such as `RANGE`, or a backing index automatically generated from `UNIQUE`/`KEY`.

When you genuinely need to recreate a lookup index that was dropped, the reference syntax is:

~~~cypher
CREATE LOOKUP INDEX idx_labels IF NOT EXISTS
FOR (n) ON EACH labels(n);
~~~

~~~cypher
CREATE LOOKUP INDEX idx_rel_types IF NOT EXISTS
FOR ()-[r]-() ON EACH type(r);
~~~

**Do not run these two commands as a mandatory setup step.** Neo4j only allows one lookup index for node labels and one for relationship types at a time; they exist by default. Dropping a lookup index can degrade performance across many queries.

## 4. Property Indexes: Speeding Up Searches Without Enforcing Uniqueness

Consider a library system with `(:Book {isbn, title})` nodes. If you need to search books by `title`, you can create a **standalone RANGE index**:

~~~cypher
CREATE RANGE INDEX qa002_book_title IF NOT EXISTS
FOR (b:QA002Book) ON (b.title);
~~~

This command creates an index containing the `title` values of nodes carrying the `QA002Book` label. When a suitable query filters on `title`, the query planner can choose this index as an access path.

An index **does not prevent** two nodes from sharing the same `title`, nor **does it require** every node to have a `title`. That is the fundamental difference from a constraint.

Common property performance index types:

| Type | Suitable For | Key Points |
|---|---|---|
| `RANGE` | Equality, range comparisons, many property filtering and sorting cases | Most commonly used index type and the backing index type for `UNIQUE`/`KEY` |
| `TEXT` | Certain string predicates, notably `CONTAINS` and `ENDS WITH` | Not a constraint ensuring valid strings |
| `POINT` | Coordinate/distance or spatial region searches | Does not enforce business validity of locations |
| `LOOKUP` | Node labels / relationship types only | Does not resolve property-value filter conditions |

In addition, Neo4j provides full-text and vector indexes for relevance-based search; these are also **not** data integrity constraints. This lesson focuses on performance indexes and constraint-owned indexes.

## 5. UNIQUE Constraints: Automatically Generating a Backing RANGE Index

If business rules require that **no two `QA002Book` nodes share the same `isbn` value**, create a constraint:

~~~cypher
CREATE CONSTRAINT qa002_book_isbn_unique IF NOT EXISTS
FOR (b:QA002Book)
REQUIRE b.isbn IS UNIQUE;
~~~

Neo4j performs **both** actions:

1. Registers the rule that existing `isbn` values on `QA002Book` nodes must not collide.
2. Automatically creates a **RANGE backing index** for the label–property pair `(:QA002Book {isbn})`. Under current schema management syntax, this index shares the same name as the constraint.

The index enables faster violation detection and can also be used by the query planner to look up `isbn`. Nevertheless, **only the constraint represents a data integrity guarantee**. Creating a standalone RANGE index on `isbn` does not enforce a uniqueness rule.

### UNIQUE Does Not Mean a Property Is Required

`IS UNIQUE` only compares nodes **that have the corresponding property value**. With the constraint on `isbn`:

- `(:QA002Book {isbn: 'B-001'})` and `(:QA002Book {isbn: 'B-002'})` can coexist validly.
- Inserting a second `(:QA002Book {isbn: 'B-001'})` is rejected as a duplicate.
- A node `(:QA002Book {title: 'Draft'})` **missing `isbn` remains valid** under `IS UNIQUE` alone.

To require a property to exist, you must add a **property existence constraint** or use an appropriate **key constraint** (see Section 7). Do not interpret the name "unique" as "mandatory primary key" as in some relational database systems.

## 6. Hands-On Practice: Seeing Standalone and Backing Indexes

The examples use the `QA002Book` label and schema names prefixed with `qa002_` to stay isolated from other data. **Run these on a practice database**, not a production database. Execute each Cypher statement separately.

### Step 1 — Reset the Fixture to Its Initial State

If you have practiced this lesson before, drop the test objects in order:

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa002_book_title IF EXISTS;
~~~

~~~cypher
MATCH (b:QA002Book)
DETACH DELETE b;
~~~

These commands only target the lesson's constraint, index, and label names; still verify that no real data uses those names in your database.

### Step 2 — Create Baseline Data

~~~cypher
CREATE
  (:QA002Book {isbn: 'B-001', title: 'Graph Fundamentals'}),
  (:QA002Book {isbn: 'B-002', title: 'Advanced Cypher'}),
  (:QA002Book {title: 'Draft'});
~~~

The dataset has **3 nodes**: two nodes with distinct `isbn` values and one node without an `isbn`.

~~~cypher
MATCH (b:QA002Book)
RETURN count(b) AS totalBooks,
       count(b.isbn) AS booksWithIsbn;
~~~

Expected output: `totalBooks = 3` and `booksWithIsbn = 2`.

### Step 3 — Create the Two Schema Objects

Create a standalone index for `title`:

~~~cypher
CREATE RANGE INDEX qa002_book_title IF NOT EXISTS
FOR (b:QA002Book) ON (b.title);
~~~

Create a uniqueness constraint for `isbn` (which automatically creates a backing index):

~~~cypher
CREATE CONSTRAINT qa002_book_isbn_unique IF NOT EXISTS
FOR (b:QA002Book)
REQUIRE b.isbn IS UNIQUE;
~~~

Both commands succeed on the current three nodes. Because the constraint only checks existing `isbn` values, the `Draft` node does not cause an error.

### Step 4 — Observe Ownership in SHOW INDEXES

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, owningConstraint, state
WHERE name IN ['qa002_book_title', 'qa002_book_isbn_unique']
RETURN name, type, entityType, labelsOrTypes,
       properties, owningConstraint, state
ORDER BY name;
~~~

Identification and ownership output (`state` may temporarily be `POPULATING` before becoming `ONLINE`):

| name | type | entityType | labelsOrTypes | properties | owningConstraint |
|---|---|---|---|---|---|
| `qa002_book_isbn_unique` | `RANGE` | `NODE` | `['QA002Book']` | `['isbn']` | `qa002_book_isbn_unique` |
| `qa002_book_title` | `RANGE` | `NODE` | `['QA002Book']` | `['title']` | `null` |

Interpretation:

- Both are `RANGE` indexes, but only the index on `isbn` has a non-`null` `owningConstraint`.
- The index on `title` is **standalone**. It is not owned by any constraint.
- The index on `isbn` belongs to the constraint of the same name. You manage its lifecycle through the constraint.

You can quickly filter **all constraint-backing indexes** in the database with:

~~~cypher
SHOW INDEXES
YIELD name, type, owningConstraint
WHERE owningConstraint IS NOT NULL
RETURN name, type, owningConstraint
ORDER BY name;
~~~

This relies on official metadata, which is more reliable than inferring ownership from index names.

### Step 5 — Confirm from the Constraint Side

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties, ownedIndex
WHERE name = 'qa002_book_isbn_unique'
RETURN name, type, labelsOrTypes, properties, ownedIndex;
~~~

Expected output:

| name | type | labelsOrTypes | properties | ownedIndex |
|---|---|---|---|---|
| `qa002_book_isbn_unique` | `NODE_PROPERTY_UNIQUENESS` | `['QA002Book']` | `['isbn']` | `qa002_book_isbn_unique` |

Comparing both perspectives:

- `SHOW INDEXES` tells you **which constraint owns this index** via `owningConstraint`.
- `SHOW CONSTRAINTS` tells you **which index this constraint owns** via `ownedIndex`.

### Step 6 — Test Reads and Verify Duplicate Rejection

Read query:

~~~cypher
MATCH (b:QA002Book)
WHERE b.isbn = 'B-001'
RETURN b.isbn AS isbn, b.title AS title;
~~~

Expected output: exactly one node with `isbn = 'B-001'` and `title = 'Graph Fundamentals'`.

You can inspect the execution plan by prepending `EXPLAIN` or `PROFILE`:

~~~cypher
EXPLAIN
MATCH (b:QA002Book)
WHERE b.isbn = 'B-001'
RETURN b.title;
~~~

When the backing index is `ONLINE`, the planner can use an appropriate index access path (for example, a unique index seek operator). Operator names and index selection decisions can vary by version, statistics, and query shape; do not treat a specific operator name as the criterion for whether a constraint is functioning correctly.

**Intentionally test a violation** (the command below is expected to **fail**):

~~~cypher
CREATE (:QA002Book {isbn: 'B-001', title: 'Invalid Duplicate'});
~~~

Neo4j rejects node creation because the `isbn` value collides with an existing node. The node count remains **3**.

If instead you create a node with only `title` and no `isbn`, the `IS UNIQUE` constraint alone does not block creating that node. This illustrates why uniqueness and required existence must be distinguished.

## 7. Which Constraints Have a Backing Index and Which Do Not?

Not every constraint generates an index. Among common Neo4j schema constraints:

| Constraint Type | Enforced Rule | Has a RANGE Backing Index? | Notes |
|---|---|---|---|
| **Property uniqueness**: `IS UNIQUE` | Existing values of the property or property combination must be distinct | **Yes** | Missing properties may still be accepted |
| **Key constraint**: `IS NODE KEY` or `IS RELATIONSHIP KEY` | Property or property combination **must exist** and be **unique** | **Yes** | Requires Neo4j Enterprise Edition |
| **Property existence**: `IS NOT NULL` | Property must exist | **No** | Requires Enterprise Edition |
| **Property type** | Value must have the declared type | **No** | Requires Enterprise Edition |

**Key constraint example** on a separate label to avoid conflicting with the fixture's `UNIQUE` constraint:

~~~cypher
// Neo4j Enterprise Edition: illustrative example, no need to run for the fixture above.
CREATE CONSTRAINT qa002_tenant_book_key IF NOT EXISTS
FOR (b:QA002TenantBook)
REQUIRE (b.tenantId, b.isbn) IS NODE KEY;
~~~

Here, every `QA002TenantBook` must have **both** `tenantId` and `isbn`, and the **pair of values** must be unique. An `isbn` value may repeat across different tenants as long as each `(tenantId, isbn)` pair is distinct. The constraint creates a backing **composite RANGE index** on the two properties.

**Property existence constraint example** (also an Enterprise Edition feature):

~~~cypher
// Illustrative example on another label so it does not affect the QA002Book fixture.
CREATE CONSTRAINT qa002_required_isbn IF NOT EXISTS
FOR (b:QA002RequiredBook)
REQUIRE b.isbn IS NOT NULL;
~~~

This constraint guarantees `isbn` is present, but **does not** check whether values are duplicated, and **does not** create a backing index. If you run `SHOW CONSTRAINTS`, the `ownedIndex` column of an existence constraint will be `null`.

Note: if you applied `IS NOT NULL` directly to `QA002Book` in the Section 6 fixture, constraint creation would fail because the `Draft` node lacks `isbn`. Neo4j must validate existing data before activating a new constraint.

### What About Relationships?

Neo4j also supports property uniqueness and applicable constraints on relationships. Syntax example:

~~~cypher
CREATE CONSTRAINT qa002_transfer_external_id_unique IF NOT EXISTS
FOR ()-[r:QA002_TRANSFER]-()
REQUIRE r.externalId IS UNIQUE;
~~~

This constraint creates a backing RANGE index for the `externalId` property on the `QA002_TRANSFER` relationship type, similar to the mechanism for node uniqueness. Relationship uniqueness support was introduced in Neo4j 5.7; verify support when working with earlier versions.

## 8. Lifecycle: Dropping a Regular Index Differs from Dropping a Backing Index

A common source of errors during system maintenance:

- For a **standalone index**, drop it directly with `DROP INDEX index_name`. Other constraints are unaffected.
- For a **backing index**, the index is owned by its constraint, so it cannot be dropped separately like a standalone index. To remove the constraint, use `DROP CONSTRAINT constraint_name`; Neo4j also **drops the backing index**.
- If the application still needs property lookups after dropping the constraint, an administrator must **proactively create an appropriate standalone index**. Dropping the constraint also removes the corresponding uniqueness/key check.

For example, the following command is **not a valid way** to remove an index serving a constraint:

~~~cypher
// Expected to be rejected: the index is owned by a constraint.
DROP INDEX qa002_book_isbn_unique;
~~~

Whereas the command below drops the constraint itself (only run during cleanup):

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique;
~~~

When you drop the `qa002_book_isbn_unique` constraint, the backing index of the same name disappears from `SHOW INDEXES` as well. Meanwhile, the standalone index `qa002_book_title` remains until dropped separately.

**Do not create an additional standalone RANGE index with the same label/type and property list when a backing RANGE index already exists.** Neo4j prevents creating an equivalent index on the same schema. If `IF NOT EXISTS` is used, index creation may have no effect and return a notice depending on the conflict type; it does not convert a backing index into a standalone index.

## 9. How to Choose a Design for a Business Requirement

| Requirement | Appropriate Solution | Reason |
|---|---|---|
| Fast book lookup by `title` only, duplicate titles allowed | Index on `title` (e.g., RANGE/TEXT depending on filter predicates) | Search performance without enforcing uniqueness |
| Each book has a distinct `isbn`, though drafts may lack an ISBN | `IS UNIQUE` on `isbn` | Enforces no duplicates; backing index is created automatically |
| Every book must have an `isbn` and duplicates are forbidden | `IS NODE KEY`, or consider combining uniqueness + existence depending on edition/design | Guarantees both existence and uniqueness |
| Every order must have `createdAt`, though timestamps may repeat | Property existence constraint (Enterprise Edition) | No uniqueness needed; this constraint creates no backing index |
| Filter many nodes by label, traverse relationships by type | Default token lookup indexes | Supports selecting node/relationship sets by token |
| Query by `customerId` which already has a uniqueness constraint | Check that the backing RANGE index is `ONLINE` before adding an index on the same schema | Avoids redundant indexes or schema conflicts |
| Drop uniqueness while still needing fast filtering by `isbn` | Drop the constraint as planned, then create an appropriate standalone RANGE index | The constraint-backing index is removed once the constraint is dropped |

**Principle:** choose a **constraint for data rules**, and choose a **standalone index for query patterns**. A backing index is a technical artifact accompanying certain constraints, not a substitute for the constraint's role.

## 10. Common Misconceptions and How to Verify

**Misconception 1: "I created an index, so data cannot be duplicated."**

False. Creating a `RANGE INDEX` only prepares a fast access path. To block duplicate values within the same label/type, an appropriate `IS UNIQUE` or `KEY` constraint is required.

**Misconception 2: "Seeing a RANGE index in SHOW INDEXES means an administrator created it manually."**

False. Backing indexes for `UNIQUE` and `KEY` constraints are also `RANGE` indexes. Check `owningConstraint`, and cross-check `ownedIndex` in `SHOW CONSTRAINTS`.

**Misconception 3: "UNIQUE automatically ensures a field is required."**

False. `UNIQUE` can allow nodes or relationships missing the constrained property. Combine it with an existence rule or use a key constraint when business rules require presence.

**Misconception 4: "Every constraint creates an index."**

False. Property existence and property type constraints do not create RANGE backing indexes. Therefore, `ownedIndex = null` can be completely normal.

**Misconception 5: "You can drop the index behind a constraint to save disk space while keeping the constraint."**

False. A backing index is bound to its constraint. Dropping the constraint removes the backing index and simultaneously removes the data integrity rule. Evaluate impacts on data and queries before modifying the schema.

**Misconception 6: "If an index exists, EXPLAIN is guaranteed to show IndexSeek."**

Not true in all cases. The query planner selects a strategy based on the query and the data. To verify schema state, inspect `SHOW INDEXES`, `SHOW CONSTRAINTS`, and the `ONLINE` status; to evaluate performance, inspect `EXPLAIN` / `PROFILE` on representative data.

## 11. Self-Check Exercises

1. **Classification:** `SHOW INDEXES` displays two RANGE indexes for `(:Customer {email})` and `(:Customer {city})`; the `owningConstraint` column is `customer_email_unique` and `null`, respectively. Which index is tied to a data integrity rule?  
   **Answer:** the index on `email` belongs to the `customer_email_unique` constraint; the index on `city` is standalone and does not enforce validity of `city`.

2. **Prediction:** on the Section 6 fixture, run `CREATE (:QA002Book {isbn: 'B-001'})` and then count the books. What is the result?  
   **Answer:** the `CREATE` statement is rejected due to a duplicate `isbn`; the count of `QA002Book` nodes remains **3**.

3. **Distinguishing unique and key:** requirement: "every `Customer` node must have `customerId` and no two nodes may share the same ID." Is `IS UNIQUE` alone sufficient?  
   **Answer:** no; you must enforce **both existence and uniqueness**, such as `IS NODE KEY` in Enterprise Edition or two appropriate constraints.

4. **Impact of DROP:** if you drop the `qa002_book_isbn_unique` constraint, what happens to the index of the same name and to the `qa002_book_title` index?  
   **Answer:** the backing index of the same name is dropped along with the constraint; the standalone index `qa002_book_title` remains.

5. **Write the command:** display the name, type, and owning constraint of all constraint-backing indexes.  
   **Hint:** use `SHOW INDEXES YIELD name, type, owningConstraint WHERE owningConstraint IS NOT NULL RETURN ...`.

## 12. Practice Cleanup

If you did not already drop the constraint in Section 8, run each statement separately:

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa002_book_title IF EXISTS;
~~~

~~~cypher
MATCH (b:QA002Book)
DETACH DELETE b;
~~~

Then verify:

~~~cypher
SHOW INDEXES
YIELD name
WHERE name IN ['qa002_book_title', 'qa002_book_isbn_unique']
RETURN name;
~~~

Expected output is **0 rows** for the two test names. The database's two default token lookup indexes are unaffected.

## 13. Official Reference Documentation

- [Neo4j — Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/): classification of RANGE, TEXT, POINT, and LOOKUP indexes and how the planner uses them.
- [Neo4j — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): index creation syntax, label/type lookup support, and handling conflicts with constraints.
- [Neo4j — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/): especially the *Constraints and backing indexes* section.
- [Neo4j — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/) and [Show constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/): the `owningConstraint`, `ownedIndex`, and index state columns.

When operating Neo4j in production, always record schema definitions and verify your edition/version before using new constraints. The foundational distinction to remember: **indexes help find data; constraints ensure correctness; backing indexes are indexes created and managed by Neo4j to support uniqueness or key constraints**.
