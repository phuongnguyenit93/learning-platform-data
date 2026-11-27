# Limits When Storing Lists, Maps, and Nested Structures in Neo4j

In Neo4j, a `node` or `relationship` holds **properties** as key–value pairs. Cypher lets you create and process `LIST`, `MAP`, and even multi-level lists of maps, yet **not every Cypher value can be stored directly as a property**. Understanding this boundary helps prevent errors when ingesting JSON, passing parameters from Java, and designing graph data models.

This lesson belongs to the **Data Types** chapter, focusing on using Neo4j to model connected data as a *property graph* and querying relationships and paths with Cypher. Scenarios involving data ingestion, the Java Driver, and Spring Data Neo4j follow the same principle: input data may be nested, while persisted data must be converted into **valid properties** or **appropriate nodes and relationships**.

## 1. Two Value Layers: Processing in Cypher vs. Storing in the Graph

Distinguish between:

1. **Values in expressions, parameters, and query results:** Cypher allows `MAP`, mixed-type `LIST`, `LIST<MAP>`, and nested structures. These are useful for `WITH`, `RETURN`, `UNWIND`, passing parameters, and shaping API responses.
2. **Values of a property on a node/relationship:** Neo4j accepts only supported **property values**. For lists, the storable case is normally a **homogeneous list of simple values, without `null`**. `MAP` and deeply nested structures are not valid property values.

The following example is **valid** because the data exists only during query execution:

~~~cypher
WITH {
  theme: 'dark',
  contacts: [
    {kind: 'home', city: 'Hanoi'},
    {kind: 'work', city: 'Da Nang'}
  ]
} AS settings
RETURN settings.theme AS theme,
       settings.contacts[0].city AS firstCity;
~~~

Conversely, this command is **invalid when assigning a property**:

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.settings = {
  theme: 'dark',
  contacts: [{kind: 'home', city: 'Hanoi'}]
};
~~~

The reason is that `u.settings` is assigned a `MAP`. Just because `MAP` is valid in a `WITH` clause does not mean it can be placed into a property.

> **Core rule:** "Cypher can read/accept it as a parameter" is different from "Neo4j can store it directly in a property". The rule applies equally to properties on nodes and on relationships.

## 2. Which Structures Can Be Stored Directly?

| Value to Store | Example | Allowed as a Property? | Reason |
| --- | --- | --- | --- |
| Scalar value | `'Lan'`, `42`, `true`, `date('2026-01-01')` | Yes | Belongs to supported property values |
| List of strings | `['java', 'neo4j']` | Yes | Elements are all `STRING` |
| List of integers | `[10, 20, 30]` | Yes | Elements are all `INTEGER` |
| List of dates | `[date('2026-01-01'), date('2026-02-01')]` | Yes | Homogeneous list of dates |
| List mixing strings and numbers | `[1, 'two', 3]` | No | Heterogeneous element types |
| List containing `null` | `['java', null]` | No | Lists stored as properties cannot contain `null` |
| Map | `{theme: 'dark', alerts: true}` | No | `MAP` is not a property value |
| List of maps | `[{city: 'Hue'}, {city: 'Hanoi'}]` | No | Each element is a `MAP` |
| Nested list of lists | `[[1, 2], [3, 4]]` | No | Elements of the outer list are `LIST`s |
| Node, relationship, path | Output of `MATCH` | No | They are structural graph values, not property values |

Neo4j also has specialized property types such as temporal values, durations, spatial points, and certain version- or edition-dependent types. The table describes typical cases; do not assume every new type can be stored in a list. For example, current documentation specifies not storing lists containing `VECTOR` values as properties.

### 2.1. Storing a Valid One-Dimensional List

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.name = 'Lan',
    u.tags = ['java', 'neo4j', 'graph'],
    u.scores = [85, 91, 88],
    u.active = true
RETURN u.id AS id, u.tags AS tags, u.scores AS scores;
~~~

`tags` and `scores` are stored as two separate properties. Elements within each list are homogeneous; element order is preserved.

You can access or process lists in Cypher:

~~~cypher
MATCH (u:User {id: 'u-007'})
RETURN u.tags[0] AS firstTag,
       size(u.tags) AS tagCount,
       'neo4j' IN u.tags AS knowsNeo4j,
       [tag IN u.tags WHERE tag <> 'graph'] AS filteredTags;
~~~

The query returns a new list for `filteredTags`; it does not modify the stored property unless `SET` is used.

### 2.2. Heterogeneous Lists Can Be Returned but Not Stored

~~~cypher
RETURN [1, 'two', true, null] AS mixedValues;
~~~

The `RETURN` statement is valid. The following statement fails when trying to store it:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.mixedValues = [1, 'two', true, null];
~~~

Do not assume simply removing `null` makes a list valid: the remaining elements must still have **compatible and homogeneous storable types**. Input data from JSON/APIs must be validated and normalized at the system boundary.

### 2.3. `null` Is Not Synonymous with an "Empty Element"

Two very different operations:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.nickname = null;  // Deletes the nickname property if it exists
~~~

~~~cypher
// Invalid example for stored properties:
MATCH (u:User {id: 'u-007'})
SET u.tags = ['java', null, 'neo4j'];
~~~

If the domain needs a string list and wants to **strip** `null` elements, filter them before saving:

~~~cypher
WITH ['java', null, 'neo4j'] AS incoming
MATCH (u:User {id: 'u-007'})
SET u.tags = [tag IN incoming WHERE tag IS NOT NULL]
RETURN u.tags AS tags;
~~~

Only do this when dropping missing values matches the business rules. If `null` carries specific meaning (such as "score at the second position is unknown"), model positions or missing states using dedicated nodes/properties rather than silently shifting indexes.

## 3. `MAP`: Used to Update Multiple Properties, Not Stored as a Single Property

A node's set of properties behaves like a key–value map. That is why `properties(u)` returns a `MAP`, yet each **value** inside that map must still belong to a storable type.

The following example is **valid**:

~~~cypher
WITH {theme: 'dark', alertsEnabled: true} AS preferences
MERGE (u:User {id: 'u-007'})
SET u += preferences
RETURN properties(u) AS properties;
~~~

`SET u += preferences` unpacks the valid key–value pairs into two properties, `u.theme` and `u.alertsEnabled`. It **does not** create a `u.preferences` property holding a map.

Comparison of forms:

| Statement | Meaning | Effect |
| --- | --- | --- |
| `SET u.theme = 'dark'` | Assigns one valid property | Adds/updates `theme` |
| `SET u += {theme: 'dark'}` | Adds/updates properties present in the map | Preserves other properties |
| `SET u = {theme: 'dark'}` | Replaces the **entire property set** with the map | Properties absent from the map, including `id`, are deleted |
| `SET u.preferences = {theme: 'dark'}` | Attempts to store a map as **one** property | Value type error |
| `SET u += {preferences: {theme: 'dark'}}` | Attempts to unpack a map containing a nested map | Fails because the value of `preferences` is not storable |

Be especially careful with `SET u = $props` when handling input data: this replacement operation can wipe out the identifier key and other properties. For partial updates, `SET u += $props` is usually safer to control, though **every value in `$props` must still be valid**; a `null` value in an update map also deletes the corresponding property.

## 4. Nested Structures: Choosing Representations by Query Needs

Suppose an application receives a JSON document:

~~~json
{
  "id": "u-007",
  "name": "Lan",
  "tags": ["java", "neo4j"],
  "settings": {
    "theme": "dark",
    "alerts": true
  },
  "addresses": [
    {"code": "home", "city": "Hanoi", "position": 0},
    {"code": "work", "city": "Da Nang", "position": 1}
  ]
}
~~~

This entire JSON cannot be assigned to `u.document` as a `MAP`. There are three common ways to represent it, depending on how the data is used.

### Approach A — Flatten Simple Fields into Properties

If `settings` only has a few stable fields that are frequently filtered directly:

~~~cypher
MERGE (u:User {id: 'u-007'})
SET u.name = 'Lan',
    u.tags = ['java', 'neo4j'],
    u.theme = 'dark',
    u.alertsEnabled = true;
~~~

Advantages: simple, readable via `u.theme`, and allows declaring appropriate indexes or constraints on scalar properties. Disadvantages: loses the original hierarchical structure; hard to manage fields with constantly changing names or multiple nested groups of the same kind.

### Approach B — Extract Child Objects into Nodes and Relationships

When `addresses` contains multiple records with their own attributes that need to be looked up, sorted, updated, or linked to other objects, the graph model is cleaner:

~~~text
(:User {id: 'u-007', name: 'Lan', tags: [...]})
    ├─[:HAS_ADDRESS]─> (:Address {
    │                      userId: 'u-007',
    │                      code: 'home',
    │                      city: 'Hanoi',
    │                      position: 0
    │                   })
    └─[:HAS_ADDRESS]─> (:Address {
                           userId: 'u-007',
                           code: 'work',
                           city: 'Da Nang',
                           position: 1
                        })
~~~

Complete example creating addresses from a **list of maps in a query expression**:

~~~cypher
WITH [
  {code: 'home', city: 'Hanoi', position: 0},
  {code: 'work', city: 'Da Nang', position: 1}
] AS incoming
MERGE (u:User {id: 'u-007'})
WITH u, incoming
UNWIND incoming AS item
MERGE (a:Address {userId: u.id, code: item.code})
SET a.city = item.city,
    a.position = item.position
MERGE (u)-[:HAS_ADDRESS]->(a)
RETURN u.id AS userId, count(a) AS addressCount;
~~~

Here `incoming` is a **transient** `LIST<MAP>`; `UNWIND` turns each map into a row to extract simple values. Each address is persisted as an `Address` node and a `HAS_ADDRESS` relationship.

Reading it back into an API structure as a list of maps is **valid**:

~~~cypher
MATCH (u:User {id: 'u-007'})-[:HAS_ADDRESS]->(a:Address)
WITH u, a
ORDER BY a.position
RETURN u.id AS userId,
       collect({
         code: a.code,
         city: a.city,
         position: a.position
       }) AS addresses;
~~~

`collect({...})` creates a list of maps **in the query result**, without attempting to store it as a property. If users with no addresses must also be returned, handle `OPTIONAL MATCH` and empty list cases appropriately.

Design notes:

- Relationships do not inherently guarantee order. If a list has business ordering, store `position` on the node or relationship and use `ORDER BY` when reconstructing it.
- The `{userId, code}` key in `MERGE` is merely an illustrative record-matching pattern. For concurrent or high-volume ingestion, design proper identifier keys and uniqueness constraints to prevent duplicates.
- Child nodes can have additional relationships (for example, an address belonging to a region), leveraging Neo4j's strength in connected queries and path traversals.

### Approach C — Store Serialized JSON as a String

If the entire structure only serves for auditing or verbatim storage/retrieval, the application can **serialize** the JSON first and store it in a `STRING` property such as `u.profileJson`:

~~~cypher
MERGE (u:User {id: $id})
SET u.profileJson = $jsonText;
~~~

`$jsonText` must be a **JSON string** produced by the application (such as Jackson in Java), not a `MAP` passed directly. Avoid this approach when the domain needs to frequently search addresses by city, traverse connections, or update a single element: Cypher will not treat string contents as a graph or nested properties. Searching, per-field validation, and partial updates also become harder.

### Choosing a Representation Based on Required Queries

| Requirement | Representation to Consider |
| --- | --- |
| List of tags, dozens of codes or numbers of the same type | `LIST` property |
| Small configuration options with stable field names | Scalar properties on one node |
| List of objects with their own attributes, IDs, and lifecycle | Child nodes + relationships |
| Multi-level objects needing path/relationship queries | Property graph model with multiple nodes and relationships |
| Arbitrary payload only stored/read as a whole, rarely queried inside | JSON string, paired with selective properties for lookup |
| Two-dimensional array where rows have distinct meaning | `Row` node holding `position` and 1D `values`; or `Cell` nodes if per-cell queries are needed |

There is no rule that "every array must become nodes". A short, stable list of strings often makes sense as a property; a list of address objects with attributes and relationships should be split into nodes.

## 5. Multi-Dimensional Arrays and Preserving Order

This value works in computations but **cannot be stored directly**:

~~~cypher
RETURN [[10, 20], [30, 40]] AS matrix;
~~~

You cannot write `SET m.cells = [[10, 20], [30, 40]]` because each element of the outer list is itself a `LIST`. One alternative:

~~~cypher
MERGE (m:Matrix {id: 'matrix-1'})
MERGE (r0:MatrixRow {matrixId: 'matrix-1', position: 0})
SET r0.values = [10, 20]
MERGE (r1:MatrixRow {matrixId: 'matrix-1', position: 1})
SET r1.values = [30, 40]
MERGE (m)-[:HAS_ROW]->(r0)
MERGE (m)-[:HAS_ROW]->(r1);
~~~

Reading it back:

~~~cypher
MATCH (m:Matrix {id: 'matrix-1'})-[:HAS_ROW]->(row:MatrixRow)
WITH row ORDER BY row.position
RETURN collect(row.values) AS matrix;
~~~

The `matrix` result is a nested list, completely valid **in query results**. The storage only requires saving `row.values` on each node as a one-dimensional list of numbers.

If you need to query individual cells or link cells to one another, a `(:Cell {row: ..., column: ..., value: ...})` model may fit better. For dense matrix algebra, consider specialized storage/compute engines rather than turning an entire matrix into countless nodes.

## 6. Ingesting Nested Data from the Java Driver and Spring Data Neo4j

### 6.1. Java Driver: Maps and Lists Are Valid Parameters

The Java Driver can pass `Map<String, Object>` and `List<?>` as Cypher parameters. This **does not relax** Neo4j's property storage rules.

The example below assumes `driver` is a connected `org.neo4j.driver.Driver` and the application uses a Java version supporting text blocks:

~~~java
Map<String, Object> params = Map.of(
    "id", "u-007",
    "addresses", List.of(
        Map.of("code", "home", "city", "Hanoi", "position", 0),
        Map.of("code", "work", "city", "Da Nang", "position", 1)
    )
);

driver.executableQuery("""
    MERGE (u:User {id: $id})
    WITH u
    UNWIND $addresses AS item
    MERGE (a:Address {userId: $id, code: item.code})
    SET a.city = item.city,
        a.position = item.position
    MERGE (u)-[:HAS_ADDRESS]->(a)
    """)
    .withParameters(params)
    .execute();
~~~

The Driver accepts `addresses` as a list of `Map`s **for Cypher to process**. After `UNWIND`, the code stores only `code`, `city`, and `position` as simple properties. Replacing the logic with `SET u.addresses = $addresses` would fail because it tries to store a `LIST<MAP>`.

When JSON needs to be stored as a string, the application can use Jackson or an equivalent library to turn the object into a `String` before passing `$jsonText`. Do not treat `toString(map)` as a proper JSON serialization solution.

### 6.2. Spring Data Neo4j: Distinguishing Properties and Relationships

For entities mapped by Spring Data Neo4j, fields like `String name`, `boolean active`, and `List<String> tags` correspond to properties (depending on mapping configuration and version). Conversely, a collection of `Address` objects representing connected entities should be modeled with `@Node` entities and `@Relationship` fields.

A Java field of type `Map<String,Object>` or `List<AddressDto>` **does not automatically turn a nested structure into a native Neo4j property**. If a custom converter serializes it into a JSON string, the database actually stores only a string. Inspect the final persisted model before designing repository queries, indexes, or constraints.

## 7. Implications for Indexes, Updates, and Operations

**Querying by element inside a list:** The condition `'neo4j' IN u.tags` expresses the right meaning, yet you should not assume a scalar property index will speed up element-level lookups. If queries like "find everyone tagged X" are a primary feature, consider a `Tag` node and `HAS_TAG` relationship, place an index/constraint on the tag key, and verify the plan using `EXPLAIN` or `PROFILE`.

~~~cypher
MERGE (t:Tag {name: 'neo4j'})
MERGE (u:User {id: 'u-007'})
MERGE (u)-[:HAS_TAG]->(t);
~~~

**Updating lists:** Add/remove elements by computing a new list and reassigning the property. Example:

~~~cypher
MATCH (u:User {id: 'u-007'})
SET u.tags = coalesce(u.tags, []) + ['cypher']
RETURN u.tags;
~~~

This command appends to the end and can create duplicate values if called repeatedly. To avoid duplicates, check membership or use a node/relationship model with identifying keys and appropriate `MERGE` logic. Do not treat a list property as an automatically deduplicated set.

**Large and frequently changing data:** A property holding a long list causes read/write operations to typically involve the entire list value while increasing Driver payload transfer. When elements need independent updates, permissions, links, search, or separate history, child nodes are usually more flexible. Do not cite a "fixed element-count limit" across all versions: performance depends on the model, value size, Neo4j version, and query patterns.

**Missing data:** `SET n.key = null` deletes the property; `[1, null, 2]` can exist as a Cypher result but is not a valid property list. Distinguishing "no property", "empty list", and "unknown element" must be defined at the business logic layer.

**Consistency:** For ingested data with nested objects, validate the schema before writing, choose stable identifier keys, create appropriate uniqueness constraints where needed, and use transactions to update nodes and relationships in one consistent operation.

## 8. Three Design Mistakes to Catch Yourself

**Scenario 1 — Storing an API profile as-is.** The API sends `{name, preferences: {theme}, addresses: [{...}]}`. Assigning the whole object to `user.payload` fails because `payload` is a map. Resolution: store `name` and simple settings as properties; create `Address` nodes for addresses that need querying; or serialize the entire payload into a JSON string if only verbatim storage is needed.

**Scenario 2 — Saving a list returned by `collect()` onto a node.** `collect({city: a.city})` returns a valid `LIST<MAP>` in `RETURN`. Running `SET u.addresses = collect(...)` (even if passed through `WITH` first) still fails because the target is a property. Persist `HAS_ADDRESS` relationships instead, and construct the list of maps only when querying to return data.

**Scenario 3 — Passing a mixed-type JSON array into `SET`.** `['neo4j', 2026, null]` can pass through Driver parameters. If written directly to a property, Neo4j rejects it. Decide the target type explicitly, convert or drop elements according to business rules, or split components into separate properties/nodes.

Remember: **nested `MAP` and `LIST` values are powerful expressive tools in Cypher; to persist them durably, represent them with valid property values or with the node–relationship structure of a property graph.**

## References

- [Neo4j Cypher Manual — Property, structural, and constructed values](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/): distinguishes value categories and property storage conditions.
- [Neo4j Cypher Manual — Lists](https://neo4j.com/docs/cypher-manual/current/values-and-types/lists/): lists in expressions and limits when storing lists.
- [Neo4j Cypher Manual — Maps](https://neo4j.com/docs/cypher-manual/current/values-and-types/maps/): maps used in queries.
- [Neo4j Cypher Manual — SET](https://neo4j.com/docs/cypher-manual/current/clauses/set/): assigning properties, `+=`, `=`, and handling `null`.
- [Neo4j Java Driver Manual — Data types and mapping to Cypher types](https://neo4j.com/docs/java-manual/current/data-types/): Java values, Cypher values, and Driver parameters.
