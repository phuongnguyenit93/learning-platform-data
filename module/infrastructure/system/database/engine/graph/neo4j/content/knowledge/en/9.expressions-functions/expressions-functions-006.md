# Functions for Inspecting Labels, Relationship Types, and Entity Properties in Neo4j Cypher

## 1. Why Inspect Entity Structure?

In Neo4j's **property graph**, a **node** can carry multiple **labels**, a **relationship** has exactly one **type**, and both nodes and relationships can hold **properties** as `key: value` pairs. When querying with Cypher, we often need to answer questions such as:

- Does this node have the label `Person`, `Actor`, or both?
- Is a connection between a person and a movie `ACTED_IN` or `DIRECTED`?
- Which properties does an entity currently have; does `birthYear` or `role` exist?
- Can we inspect the data structure without knowing all property names in advance?

These checks are useful when data is heterogeneous, when importing from multiple sources, when writing data-quality audit queries, or when building applications with the **Neo4j Java Driver** and **Spring Data Neo4j**. The sections below focus on Cypher expressions and functions: `labels()`, `type()`, `keys()`, `properties()`, property access, and `IS NULL` / `IS NOT NULL`.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish node labels, relationship types, and entity properties.
2. Use `labels(n)` and label expressions to classify nodes; use `type(r)` to classify relationships.
3. Use `keys()`, `properties()`, and dynamic property access to explore data.
4. Check for property presence using `IS NOT NULL` and understand the semantics of `null`.
5. Choose appropriate expressions when optimizing Cypher queries.

## 2. Preparing the Sample Graph

Suppose an application stores information about people involved in movie production. A person can be a `Person` as well as an `Actor` or `Director`; a movie is a `Movie`. Relationships can carry their own properties.

```text
(an:Person:Actor {personId, name, birthYear})
     |
     +--[:ACTED_IN {role, screenTime}]-->(phim:Movie {movieId, title, year})
                                              ^
                                              |
                                 [:DIRECTED]--+
                                              |
                          (binh:Person:Director {personId, name})
```

Create the sample data with Cypher:

```cypher
MERGE (an:Person {personId: 'p-001'})
SET an:Actor, an.name = 'An', an.birthYear = 1993
MERGE (binh:Person {personId: 'p-002'})
SET binh:Director, binh.name = 'Binh'
MERGE (phim:Movie {movieId: 'm-001'})
SET phim.title = 'Summer', phim.year = 2024
MERGE (an)-[vai:ACTED_IN]->(phim)
SET vai.role = 'Lan', vai.screenTime = 42
MERGE (binh)-[:DIRECTED]->(phim);
```

`MERGE` allows re-running the example to update matched entities. In real applications, create a **unique constraint** on business identifiers such as `Person.personId` and `Movie.movieId` to guarantee uniqueness under concurrent writes.

| Component | Example Syntax | Meaning |
| --- | --- | --- |
| Node label | `:Person`, `:Actor` | A node can carry multiple labels. |
| Relationship type | `:ACTED_IN` | A relationship has a single type. |
| Node property | `an.birthYear` | Value stored directly on the node. |
| Relationship property | `vai.role` | Value stored directly on the relationship. |

**Note:** `Actor` is a label, not a property `an.Actor`; `ACTED_IN` is a relationship type, not a property `vai.type`. These are three distinct parts of the property graph.

## 3. Inspecting Node Labels with `labels()`

### 3.1. What Does `labels(node)` Return?

`labels(n)` returns a **list of strings** containing the labels of node `n`. A node with no labels returns an empty list `[]`; a `null` input returns `null`. The order of elements in the label list is **not guaranteed**, so do not rely on `labels(n)[0]` to determine a “primary label”.

```cypher
MATCH (p:Person)
RETURN p.name AS ten,
       labels(p) AS danhSachNhan
ORDER BY ten;
```

With the sample data, An's node has labels `Person` and `Actor`; Binh's node has `Person` and `Director`. The display order of labels may vary.

To check whether a label is present in the list, use the `IN` operator:

```cypher
MATCH (p:Person)
WHERE 'Actor' IN labels(p)
RETURN p.name AS dienVien;
```

The query above returns **An**. You can also check against a list of required labels:

```cypher
MATCH (n)
WHERE all(requiredLabel IN ['Person', 'Actor']
          WHERE requiredLabel IN labels(n))
RETURN n.name AS ten;
```

The `all(...)` predicate is true only if the node has **both labels**.

### 3.2. Checking Labels Directly in a Pattern or `WHERE`

When labels are known at query-writing time, a more concise and clear expression is to check them directly in the node pattern:

```cypher
MATCH (p:Person:Actor)
RETURN p.name AS dienVien;
```

Here, `:Person:Actor` expresses an **AND** condition: the node must have both labels. An equivalent way to write this condition is:

```cypher
MATCH (p:Person)
WHERE p:Actor
RETURN p.name AS dienVien;
```

If you need to check for any of multiple labels, write:

```cypher
MATCH (p:Person)
WHERE p:Actor OR p:Director
RETURN p.name AS nguoiLamPhim;
```

Modern Cypher also supports richer label-expression syntax (for example using `&` and `|`). The examples with `:Person:Actor`, `WHERE p:Actor`, and `OR` above are easy to read and well suited for learning basic checks.

**When should you use `labels(n)`?** Use it when you need to **return the list of labels**, check a dynamically supplied label (such as `$requiredLabel IN labels(n)`), or explore data. When labels are static, declare them directly in `MATCH` so the Cypher planner has better opportunities to leverage label indexes.

## 4. Inspecting Relationship Types with `type()`

### 4.1. `type(relationship)`

`type(r)` returns **a string** representing the type of relationship `r`; when `r` is `null`, the result is `null`. This function is for **relationships**, not nodes; conversely, `labels()` is for nodes, not relationships.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       m.title AS phim
ORDER BY nguoi;
```

Expected output includes An with type `ACTED_IN` and Binh with type `DIRECTED`.

Filter by type using string comparison:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE type(r) = 'ACTED_IN'
RETURN p.name AS dienVien, m.title AS phim;
```

Or allow multiple types:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE type(r) IN ['ACTED_IN', 'DIRECTED']
RETURN p.name, type(r), m.title;
```

### 4.2. When the Relationship Type Is Known, Put It in the Pattern

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p.name AS dienVien, r.role AS vaiDien, m.title AS phim;
```

The pattern `-[r:ACTED_IN]->` constrains both the **relationship type** and the **direction** of the link. When the type is known upfront, specifying it in the pattern is clearer and helps the planner restrict traversal earlier than matching all types and filtering with `type(r)`.

One key point: although a node can have multiple labels, **a relationship has only one type at a time**. To represent two distinct relationship semantics, you typically create two relationships with different types, or adjust the graph model to fit the domain.

## 5. Exploring Property Keys and Values

### 5.1. `keys(entity)` Lists Property Names

`keys(n)` or `keys(r)` returns a list of the property names currently present on a node or relationship. `keys()` also accepts a map. It does not list labels or relationship types. The order of property names is not guaranteed.

```cypher
MATCH (p:Person)
RETURN p.name AS ten, keys(p) AS tenThuocTinh
ORDER BY ten;
```

For An, the list includes `personId`, `name`, and `birthYear`; for Binh, it includes only `personId` and `name`.

Relationships also have properties:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       keys(r) AS tenThuocTinhQuanHe;
```

An's `ACTED_IN` relationship has `role` and `screenTime`; Binh's `DIRECTED` relationship has no properties assigned, so `keys(r)` returns `[]`.

To count the **number of properties** on an entity:

```cypher
MATCH (p:Person)
RETURN p.name AS ten, size(keys(p)) AS soThuocTinh;
```

Do not confuse `size(keys(p))` with the number of labels or degree (number of relationships) of the node: it is strictly the **number of property keys**.

### 5.2. `properties(entity)` Returns a Property Map

`properties(n)` or `properties(r)` returns a **map** containing the entity's key–value pairs. For an entity with no properties, the result is an empty map `{}`. It also accepts a map and returns that map's contents.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       properties(p) AS thongTinNguoi,
       type(r) AS loaiQuanHe,
       properties(r) AS thongTinQuanHe;
```

For example, `properties(r)` on the `ACTED_IN` relationship looks like:

```json
{"role": "Lan", "screenTime": 42}
```

Whereas `properties(r)` on the `DIRECTED` relationship is `{}`. `properties(p)` does **not** include node labels; to get labels, call `labels(p)` separately.

### 5.3. Accessing Properties Directly or Dynamically

When a property name is known in advance, use dot notation:

```cypher
MATCH (p:Person)
RETURN p.name AS ten, p.birthYear AS namSinh;
```

If the property name comes from an expression or parameter, Cypher supports bracket access:

```cypher
WITH 'birthYear' AS tenTruong
MATCH (p:Person)
RETURN p.name AS ten,
       p[tenTruong] AS giaTri;
```

This is **dynamic property access**, unlike `p.birthYear` which uses a fixed key name. If the key does not exist, the value read is `null`.

To unnest a property map into rows:

```cypher
MATCH (p:Person {personId: 'p-001'})
UNWIND keys(p) AS tenTruong
RETURN tenTruong, p[tenTruong] AS giaTri
ORDER BY tenTruong;
```

This is useful in data inspection screens or export pipelines for flexible schemas. When only a few fixed fields are needed, select them directly rather than returning the entire `properties(p)` map.

## 6. Checking Property Presence with `IS NOT NULL`

### 6.1. Does the Property Exist?

In modern Neo4j versions, the standard way to check whether a property has a value assigned is `entity.property IS NOT NULL`:

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NOT NULL
RETURN p.name AS ten, p.birthYear AS namSinh;
```

This query returns only An, because Binh has no `birthYear` property. The opposite predicate finds entities missing the value:

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NULL
RETURN p.name AS thieuNamSinh;
```

With the sample data, the result is Binh.

For relationship properties:

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE r.role IS NOT NULL
RETURN p.name, type(r), r.role;
```

In this example, only An's `ACTED_IN` relationship has `role`.

### 6.2. Understanding `null` Correctly in a Property Graph

In Neo4j, node and relationship properties do not store `null` as an ordinary property value. **Assigning `null` removes that property**:

```cypher
MATCH (p:Person {personId: 'p-002'})
SET p.birthYear = null
RETURN p.birthYear IS NULL AS thieuNamSinh;
```

The result is `true`, because `birthYear` does not exist on the node. In fact, Binh already lacked this property, so the command leaves the sample data unchanged. In Cypher expressions, `null` also means “no value”, such as when reading a missing property or when `OPTIONAL MATCH` finds no match.

**Do not use `= null` or `<> null` to find missing properties**. Standard comparisons with `null` produce `null` (not `true`), which does not satisfy `WHERE`. Use `IS NULL` or `IS NOT NULL`.

Additionally, `0`, `false`, and empty string `''` are **not `null`**. For instance, a property with value `false` still satisfies `IS NOT NULL`:

```cypher
WITH {active: false, note: ''} AS thongTin
RETURN thongTin.active IS NOT NULL AS coActive,
       thongTin.note IS NOT NULL AS coNote,
       thongTin.missing IS NULL AS thieuMissing;
```

All three results in this query are `true`. Data stored in maps can be inspected using the same property-access syntax.

> Compatibility note: some older Cypher examples use `exists(n.property)` to check for a property. That syntax was removed in newer Neo4j versions; use `n.property IS NOT NULL` instead. Do not confuse this property check with `EXISTS { ... }`, which checks for the existence of a graph pattern or subquery.

## 7. Combining Label, Relationship Type, and Property Checks

### 7.1. Finding Actors with Valid Birth Year and Role

```cypher
MATCH (p:Person:Actor)-[r:ACTED_IN]->(m:Movie)
WHERE p.birthYear IS NOT NULL
  AND r.role IS NOT NULL
RETURN p.name AS dienVien,
       p.birthYear AS namSinh,
       m.title AS phim,
       r.role AS vaiDien;
```

In this query:

1. `p:Person:Actor` ensures the node has both labels.
2. `r:ACTED_IN` ensures the relationship has the right type.
3. `p.birthYear IS NOT NULL` and `r.role IS NOT NULL` verify that the properties have values.
4. `RETURN` selects only the fields needed in the output.

### 7.2. Auditing Data and Identifying Records Missing Fields

```cypher
MATCH (p:Person)
RETURN p.personId AS id,
       p.name AS ten,
       'Actor' IN labels(p) AS laDienVien,
       p.birthYear IS NOT NULL AS coNamSinh,
       keys(p) AS cacTruongHienCo
ORDER BY id;
```

The query returns one row per `Person`, including Boolean flags for data completeness and the list of present keys. This is a clean way to build an inventory report before enforcing data constraints.

### 7.3. Reading the Graph Flexibly When Relationship Types Are Unknown

```cypher
MATCH (p:Person)-[r]->(m:Movie)
RETURN p.name AS nguoi,
       labels(p) AS nhanNguoi,
       type(r) AS quanHe,
       properties(r) AS duLieuQuanHe,
       m.title AS phim;
```

This query pattern is helpful for data exploration, though once the target labels and relationship types are known, move them into `MATCH` to narrow the search scope.

## 8. Quick Reference Cheat Sheet

| Check / Retrieve | Cypher Syntax | Return Type | Notes |
| --- | --- | --- | --- |
| All labels of a node | `labels(n)` | List of strings | A node can have multiple labels. |
| Node has a specific label | `n:Person` or `'Person' IN labels(n)` | Boolean | Prefer constraining static labels in `MATCH`. |
| Node has both labels | `MATCH (n:Person:Actor)` | Node pattern | AND semantics. |
| Type of a relationship | `type(r)` | String | A relationship has one type. |
| Relationship has a specific type | `type(r) = 'ACTED_IN'` or `[r:ACTED_IN]` | Boolean or pattern | Patterns with fixed types are easier to optimize. |
| Property names | `keys(n)`, `keys(r)` | List of strings | Excludes labels and types. |
| Property map | `properties(n)`, `properties(r)` | Map | Excludes labels and types. |
| Property has a value | `n.name IS NOT NULL` | Boolean | Standard way to check property presence. |
| Property is missing | `n.name IS NULL` | Boolean | True when the property does not exist. |
| Dynamic property access | `n[tenTruong]` | Value or `null` | Can use a variable or parameter for the key name. |

## 9. Performance and Query Design Notes

- **Put known labels and relationship types in the pattern.** `MATCH (p:Person)-[:ACTED_IN]->(m:Movie)` expresses the target structure more clearly than `MATCH (p)-[r]->(m) WHERE 'Person' IN labels(p) AND type(r) = 'ACTED_IN'`.
- **Filter on properties as early as possible.** With an appropriate index, a query with a fixed label and property—such as `MATCH (p:Person {personId: 'p-001'})`—can avoid scanning the entire graph.
- **Avoid using `keys()` or `properties()` unnecessarily in place of direct predicates.** When checking only `birthYear`, `p.birthYear IS NOT NULL` expresses the intent more clearly than `'birthYear' IN keys(p)` and is easier for the planner to optimize.
- **Avoid returning all properties when unnecessary.** `properties(n)` can produce large payloads and expose fields the application does not need. List the required properties explicitly in `RETURN`.
- **Use `EXPLAIN` / `PROFILE` to verify.** Actual query execution strategies depend on Neo4j version, indexes, data distribution, and Cypher phrasing; never claim a function is universally fast or slow in all cases.

Example query with fixed label and key to inspect the execution plan:

```cypher
EXPLAIN
MATCH (p:Person {personId: 'p-001'})
RETURN p.name;
```

`EXPLAIN` only generates the plan, whereas `PROFILE` executes the query and reports actual metrics. On large systems, create appropriate unique constraints or indexes before evaluating performance.

## 10. Common Mistakes

| Mistake | Why It Is Wrong | Proper Approach |
| --- | --- | --- |
| Calling `labels(r)` on a relationship | `labels()` is for nodes only. | Use `type(r)`. |
| Calling `type(n)` on a node | `type()` is for relationships only. | Use `labels(n)`. |
| Using `n.Actor` to check for the `Actor` label | This reads a property named `Actor`. | Use `n:Actor` or `'Actor' IN labels(n)`. |
| Using `r.type` to read the relationship type | This reads a property named `type`, if present. | Use `type(r)`. |
| Using `p.name = null` | Comparing with `null` does not return `true`. | Use `p.name IS NULL`. |
| Treating `labels(n)[0]` as the primary label | Label order is not guaranteed. | Check labels by name. |
| Assuming `keys(n)` includes labels | It only lists property keys. | Combine `keys(n)` with `labels(n)` when needed. |
| Scanning all nodes to filter a static label | May miss label-index optimizations. | Use `MATCH (n:Label)`. |

## 11. Self-Check Practice Exercises

**Exercise 1.** List each person's name, list of labels, and number of properties.

```cypher
MATCH (p:Person)
RETURN p.name AS ten,
       labels(p) AS nhan,
       size(keys(p)) AS soThuocTinh
ORDER BY ten;
```

**Exercise 2.** List relationships pointing into `Movie`, keeping only relationships that have at least one property.

```cypher
MATCH (p:Person)-[r]->(m:Movie)
WHERE size(keys(r)) > 0
RETURN p.name AS nguoi,
       type(r) AS loaiQuanHe,
       properties(r) AS thuocTinh;
```

With the sample data, only the `ACTED_IN` relationship is returned.

**Exercise 3.** Find people labeled `Person` who do not yet have a `birthYear` property; indicate whether each person is a `Director`.

```cypher
MATCH (p:Person)
WHERE p.birthYear IS NULL
RETURN p.name AS ten,
       'Director' IN labels(p) AS laDaoDien;
```

The expected result is Binh with `laDaoDien = true`.

**Exercise 4 (extension).** Count relationships by type without knowing in advance which types exist.

```cypher
MATCH ()-[r]->()
RETURN type(r) AS loaiQuanHe, count(*) AS soLuong
ORDER BY soLuong DESC, loaiQuanHe;
```

With the standalone sample dataset, `ACTED_IN` and `DIRECTED` each have one relationship. If the database contains other graphs, the result will include their relationships as well; constrain `MATCH` with node labels when needed.

## 12. Summary

In Cypher, clearly distinguish the three information layers of a property graph: **`labels(n)` inspects node label structure; `type(r)` identifies relationship type; `keys()`, `properties()`, and property access work with key–value data**. When the requirement is to check whether a specific property has a value, use **`IS NOT NULL`** or **`IS NULL`**. When labels and types are known, put them directly in the `MATCH` pattern for clearer queries and better optimization opportunities.
