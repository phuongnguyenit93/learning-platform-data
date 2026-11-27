# Declaring Variables for Nodes, Relationships, and Paths in Cypher

> **Chapter:** Cypher Basics  
> **Scope:** Neo4j uses the *property graph* model: nodes have labels and properties; relationships have a direction, a type, and properties. This lesson explains how to **name, bind, and use variables** in Cypher queries to access nodes, relationships, and entire paths.

## 1. Learning Objectives

After this lesson, you will be able to:

- Declare and use variables for nodes, relationships, and paths in Cypher patterns.
- Distinguish **variable names** from **labels**, **relationship types**, and **property names**.
- Access node and relationship properties, as well as manipulate paths using Cypher functions.
- Understand that variables are bound per **result row**, unlike variables assigned values in imperative programming languages.
- Control variable scope across `MATCH`, `OPTIONAL MATCH`, `WITH`, and `RETURN`.
- Avoid common mistakes when reusing variables, naming variables, traversing multiple relationships, and handling `null`.

## 2. What Is a Variable in Cypher?

In Java, we commonly see declarations like `Person person = ...`. In Cypher, there is no equivalent `var person` statement for graph entities. **A variable is introduced when a query pattern or clause binds it to a value**.

Example:

```cypher
MATCH (person:Person)
RETURN person;
```

`person` is a **variable** representing one `Person` node in each matched row; `Person` is a **label** stored on the node. Each row can hold a different `person` node.

A complete pattern:

```cypher
MATCH route = (person:Person)-[link:KNOWS]->(friend:Person)
RETURN person, link, friend, route;
```

| Component | Kind | Role |
|---|---|---|
| `person` | Node variable | References the starting node of the pattern. |
| `Person` | Label | Filter condition on the node's label; not a variable name. |
| `link` | Relationship variable | References the relationship connecting the two nodes. |
| `KNOWS` | Relationship type | Filter condition on the relationship type; not a variable name. |
| `friend` | Node variable | References the target node in the arrow's direction. |
| `route` | Path variable | References the **entire matched path**, consisting of nodes and relationships in order. |

```text
route = entire path
  ┌────────────────────────────────────────────┐
  │                                            │
  (person:Person)-[link:KNOWS]->(friend:Person)
       node         relationship      node
  └────────────────────────────────────────────┘
```

In the explanations below, **variable binding** means finding the entity or value corresponding to a variable name in a result row. Variables allow subsequent clauses to refer back to that exact entity.

## 3. Building a Sample Graph for Practice

Run the sample data in a **separate practice database**. Thanks to `MERGE`, re-running the same block finds existing matching nodes and relationships before creating more; the sample data assumes no conflicting entities with duplicate IDs or matching relationships already exist.

```cypher
MERGE (an:Person {id: 'p1'})
SET an.name = 'An', an.city = 'Hà Nội'

MERGE (binh:Person {id: 'p2'})
SET binh.name = 'Bình', binh.city = 'Hà Nội'

MERGE (chi:Person {id: 'p3'})
SET chi.name = 'Chi', chi.city = 'TP. Hồ Chí Minh'

MERGE (dung:Person {id: 'p4'})
SET dung.name = 'Dũng', dung.city = 'Đà Nẵng'

MERGE (api:Project {id: 'pr1'})
SET api.name = 'Graph API'

MERGE (an)-[anBinh:KNOWS]->(binh)
SET anBinh.since = 2021

MERGE (binh)-[binhChi:KNOWS]->(chi)
SET binhChi.since = 2023

MERGE (an)-[anApi:WORKS_ON]->(api)
SET anApi.role = 'lead';
```

The graph used in the examples:

```text
(An:Person {id:'p1'})
   │
   ├──[KNOWS {since:2021}]──> (Bình:Person {id:'p2'})
   │                                  │
   │                                  └──[KNOWS {since:2023}]──> (Chi:Person {id:'p3'})
   │
   └──[WORKS_ON {role:'lead'}]──> (Graph API:Project {id:'pr1'})

(Dũng:Person {id:'p4'})  -- no relationships in sample
```

Result tables in this lesson assume only this sample graph exists. If the database already contains additional nodes or relationships, queries that do not filter by ID may produce different results.

## 4. Declaring and Using Node Variables

A node variable is placed inside parentheses `(...)`:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p;
```

Here `p` is bound to the node with label `Person` and property `id = 'p1'`. `RETURN p` returns the **node**, including its graph identifier, labels, and properties, which visualization tools can render graphically.

To retrieve **property values**, use dot notation:

```cypher
MATCH (p:Person {id: 'p1'})
RETURN p.name AS ten, p.city AS thanhPho;
```

The result is `An` and `Hà Nội`. The name `p` is chosen by the query author, while `name` and `city` are property names stored on the node. A node that does not have a requested property yields `null` when accessing that property.

### 4.1. A Label Is Not a Variable

The following two patterns have different meanings:

```cypher
MATCH (member:Person)
RETURN member.name AS ten;
```

```cypher
MATCH (Person)
RETURN Person;
```

- In the first example, `member` is the variable and `Person` is the label.
- In the second example, `Person` is **only a variable name** because there is no colon; this pattern does not restrict nodes by label and can match `Project` nodes as well.

Therefore, use `(p:Person)` when you want to filter by the `Person` label. For a node you do not need to reference later, you can omit the variable name:

```cypher
MATCH (:Person)-[:WORKS_ON]->(pr:Project)
RETURN pr.name AS duAn;
```

`(:Person)` is a node with label `Person` but **without assigning a variable name** to it; `pr` remains a node variable for returning results.

### 4.2. Reusing a Variable Refers to the Same Node Within a Row

```cypher
MATCH (p:Person {id: 'p1'})
MATCH (p)-[:KNOWS]->(f:Person)
RETURN p.name AS nguoi, f.name AS ban;
```

In the second `MATCH`, `p` is already bound from the first `MATCH`. It still refers to **An's node**, rather than becoming a new variable or an arbitrary node. The variable `f` is the target node of the `KNOWS` relationship.

Result: **An – Bình**.

If you need to work with **two independent people**, use two distinct variables and explicitly express the joining condition:

```cypher
MATCH (a:Person {id: 'p1'}), (b:Person {id: 'p2'})
RETURN a.name AS nguoiA, b.name AS nguoiB;
```

With fixed IDs, the example produces only one pair. However, writing `MATCH (a:Person), (b:Person)` without a joining condition can cause Neo4j to generate a Cartesian product, making the row count grow very quickly.

## 5. Declaring and Using Relationship Variables

A relationship variable is placed inside square brackets `[...]`:

```cypher
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
RETURN a.name AS nguoi,
       b.name AS ban,
       r.since AS quenTuNam;
```

In the pattern `-[r:KNOWS]->`:

- `r` is the **relationship variable**.
- `KNOWS` is the **relationship type**.
- The arrow `->` requires the pattern to go from `a` to `b` in the stored direction of the relationship.
- `r.since` reads the `since` property on the relationship, just as `a.name` reads a node property.

Result: **An – Bình – 2021**.

You can return the relationship itself and inspect its metadata:

```cypher
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
RETURN rel,
       type(rel) AS loaiQuanHe,
       properties(rel) AS thuocTinh,
       startNode(rel).name AS nutDau,
       endNode(rel).name AS nutCuoi;
```

The functions above return the relationship, type, property map, start node, and end node **according to the direction stored on the relationship**.

### 5.1. Relationship Direction and Variable Naming

```cypher
// Following stored direction: An -> Bình
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
RETURN a.name, b.name;
```

```cypher
// Opposite to stored direction: find who knows Chi
MATCH (target:Person {id: 'p3'})<-[r:KNOWS]-(source:Person)
RETURN source.name AS nguoiBietChi, target.name AS chi;
```

```cypher
// Match relationships in either direction
MATCH (a:Person {id: 'p2'})-[r:KNOWS]-(other:Person)
RETURN other.name AS nguoiLienQuan, type(r) AS loai;
```

The third example can return **An** and **Chi**, because Bình is the target of one `KNOWS` relationship and the source of another `KNOWS` relationship. The syntax `-[r:KNOWS]-` does not require a specific direction; **the variable `r` still points to the matched relationship itself**, with its stored direction.

### 5.2. Not Every Relationship Needs a Variable

If you only want to check existence and retrieve a person's name:

```cypher
MATCH (a:Person {id: 'p1'})-[:KNOWS]->(b:Person)
RETURN b.name AS ban;
```

There is no relationship variable because the query does not reuse the relationship object. When you need to read properties, type, start/end nodes of a relationship, or carry the relationship to a later stage, assign a variable such as `r`.

### 5.3. One Pattern Can Match Multiple Relationships

```cypher
MATCH (a:Person)-[r:KNOWS]->(b:Person)
RETURN a.name AS nguoi, b.name AS ban, r.since AS tuNam
ORDER BY tuNam;
```

The sample graph has two `KNOWS` relationships, so it returns **two rows**: An – Bình – 2021 and Bình – Chi – 2023. The variables `a`, `r`, and `b` hold values **per row**, not as a global variable storing only the last relationship.

## 6. Declaring and Using Path Variables

A **path** is a sequence of connected nodes and relationships. To name an entire path, use the form:

```cypher
MATCH pathVariable = (startNode)-[relationship]->(endNode)
RETURN pathVariable;
```

In a real query, we can name it `route`:

```cypher
MATCH route = (an:Person {id: 'p1'})
              -[r1:KNOWS]->(binh:Person)
              -[r2:KNOWS]->(chi:Person)
RETURN route;
```

`route` represents the entire segment **An → Bình → Chi**, while `an`, `binh`, and `chi` are node variables; `r1` and `r2` are relationship variables. Declaring a path variable does not create new nodes or relationships in the database; it simply binds a name to **the matched pattern**.

### 6.1. Common Functions Used with Paths

| Expression | Result | In the An → Bình → Chi Example |
|---|---|---|
| `route` | The path value, containing nodes and relationships. | Path An → Bình → Chi. |
| `nodes(route)` | List of nodes in path order. | Nodes An, Bình, Chi. |
| `relationships(route)` | List of relationships in path order. | Relationships An→Bình, Bình→Chi. |
| `length(route)` | Path length measured in **number of relationships**. | `2`. |
| `[n IN nodes(route) \| n.name]` | List of node names in order. | `['An', 'Bình', 'Chi']`. |
| `[r IN relationships(route) \| r.since]` | List of `since` values for each relationship. | `[2021, 2023]`. |

Runnable example:

```cypher
MATCH route = (a:Person {id: 'p1'})
              -[:KNOWS]->(:Person)
              -[:KNOWS]->(c:Person)
RETURN length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNut,
       [r IN relationships(route) | type(r)] AS cacLoaiQuanHe,
       [r IN relationships(route) | r.since] AS cacNamBatDau,
       c.name AS nutCuoi;
```

Result:

| soCanh | cacNut | cacLoaiQuanHe | cacNamBatDau | nutCuoi |
|---:|---|---|---|---|
| 2 | `['An', 'Bình', 'Chi']` | `['KNOWS', 'KNOWS']` | `[2021, 2023]` | Chi |

Note: `length(route)` counts edges, not nodes. For the two-edge path in the example, `nodes(route)` has three elements.

### 6.2. Variable-Length Paths

Paths do not have to have a fixed number of edges. On Neo4j versions supporting **quantified relationships** (from Cypher/Neo4j 5.9), you can write:

```cypher
MATCH route = (start:Person {id: 'p1'})
              -[:KNOWS]->{1,2}
              (destination:Person)
RETURN destination.name AS dich,
       length(route) AS soBuoc,
       [n IN nodes(route) | n.name] AS cacNut
ORDER BY soBuoc;
```

`{1,2}` requires traversing between one and two `KNOWS` relationships. With the sample graph, we receive:

| dich | soBuoc | cacNut |
|---|---:|---|
| Bình | 1 | `['An', 'Bình']` |
| Chi | 2 | `['An', 'Bình', 'Chi']` |

In older Cypher documentation, you may see variable-length syntax such as `-[:KNOWS*1..2]->`. Quantified syntax and group variable behavior vary across versions, so check the Neo4j version you are using before copying multi-hop traversal queries. With the clause above, `route` is still a **path**, and `destination` is the target node of each result.

### 6.3. A Path Is Not the Same as a Relationship

`r` in `-[r:KNOWS]->` always points to **a single matched relationship** in a one-hop pattern. Meanwhile, `route` can include **multiple relationships and multiple nodes**.

For example, `type(r)` accepts a relationship, not an entire path. To get the type of every edge along a path, use:

```cypher
MATCH route = (a:Person {id: 'p1'})-[:KNOWS]->(:Person)-[:KNOWS]->(:Person)
RETURN [r IN relationships(route) | type(r)] AS cacType;
```

`nodes(route)` and `relationships(route)` return **lists**. From there, you can use list comprehensions, `UNWIND`, or list functions to process the data further.

## 7. Variable Scope: From `MATCH` Through `WITH` to `RETURN`

A variable only exists within the **query scope** where it was bound and forwarded. Within the same query part, a subsequent `MATCH` can use previously bound variables:

```cypher
MATCH (an:Person {id: 'p1'})
MATCH (an)-[friendship:KNOWS]->(friend:Person)
MATCH (an)-[assignment:WORKS_ON]->(project:Project)
RETURN an.name AS nguoi,
       friend.name AS ban,
       project.name AS duAn,
       friendship.since AS quenTu,
       assignment.role AS vaiTro;
```

In each subsequent `MATCH`, `an` still refers to An. The variables `friendship`, `friend`, `assignment`, and `project` are additionally bound. If An has many friends and many projects, combining the matches can create **many row combinations**, so consider aggregating or splitting into stages.

### 7.1. `WITH` Forwards Selected Variables

```cypher
MATCH route = (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b, route
RETURN b.name AS ban,
       length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNut;
```

After `WITH b, route`, only `b` and `route` remain in the subsequent scope. The variables `a` and `r` are not forwarded. However, we can still access the nodes and relationships **through the `route` value** using `nodes(route)` and `relationships(route)`.

**Invalid** example:

```cypher
// Error: rel is out of scope after WITH
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
WITH b
RETURN rel.since AS quenTu;
```

Valid version:

```cypher
MATCH (a:Person {id: 'p1'})-[rel:KNOWS]->(b:Person)
WITH b, rel
RETURN b.name AS ban, rel.since AS quenTu;
```

### 7.2. Aliasing Can Change the Variable Name Used Downstream

```cypher
MATCH (p:Person {id: 'p1'})
WITH p AS person
RETURN person.name AS ten;
```

In the `RETURN` stage, the name `person` is in effect; the name `p` is no longer passed through `WITH`. Similarly, you can forward **property values**:

```cypher
MATCH (p:Person {id: 'p1'})
WITH p.name AS ten, p.city AS thanhPho
RETURN ten, thanhPho;
```

In this query, `ten` and `thanhPho` are scalar values (strings), **not node variables**. Therefore, writing `ten.city` will not mean accessing a property of the `Person` node.

### 7.3. Passing a Path Variable Across Multiple Stages

```cypher
MATCH route = (a:Person {id: 'p1'})-[:KNOWS]->(b:Person)-[:KNOWS]->(c:Person)
WITH route, c
WHERE length(route) >= 2
RETURN c.name AS dich,
       [n IN nodes(route) | n.name] AS cacNut;
```

`route` is preserved across `WITH` and can still be used in `WHERE`/`RETURN`. Conversely, if you write `WITH c`, the `route` variable will no longer be available to subsequent clauses.

## 8. `OPTIONAL MATCH` and Variables with `null` Values

`MATCH` requires the pattern to match. `OPTIONAL MATCH` preserves the input row even when there is no matching relationship; the **new** variables from the unmatched pattern receive `null`.

```cypher
MATCH (p:Person)
OPTIONAL MATCH route = (p)-[work:WORKS_ON]->(project:Project)
RETURN p.name AS nhanSu,
       project.name AS duAn,
       work.role AS vaiTro,
       coalesce(length(route), 0) AS soCanh
ORDER BY nhanSu;
```

In the sample graph:

| nhanSu | duAn | vaiTro | soCanh |
|---|---|---|---:|
| An | Graph API | lead | 1 |
| Bình | `null` | `null` | 0 |
| Chi | `null` | `null` | 0 |
| Dũng | `null` | `null` | 0 |

`p` still has a value because it was bound earlier by `MATCH`. However, when there is no `WORKS_ON` relationship, the new variables `work`, `project`, and `route` receive `null`. The `coalesce` function returns the first non-`null` expression, so `coalesce(length(route), 0)` represents the absence of a path as 0.

A common mistake is requiring `work.role = 'lead'` in a `WHERE` after `WITH` and accidentally filtering out people who do not participate in any project. If the goal is to **keep everyone and only look for relationships with the lead role**, attach the condition to `OPTIONAL MATCH`:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[work:WORKS_ON]->(project:Project)
WHERE work.role = 'lead'
RETURN p.name AS nhanSu, project.name AS duAnLead
ORDER BY nhanSu;
```

In that case, every `p` still has a row; `project` is `null` when no relationship with `role = 'lead'` is found.

## 9. Variable Naming Rules and How to Read Syntax

### 9.1. Practical Rules

- Use meaningful names: `person`, `colleague`, `worksOn`, `route`; for short queries, `p`, `r`, and `path` are also suitable.
- Variable names are **case-sensitive**: `person` and `Person` are two different names.
- Simple names should start with a letter, followed by letters, digits, or underscores; avoid spaces or special characters when unnecessary.
- Cypher supports names enclosed in backticks when special characters are needed, though readable and consistent names are usually more convenient.
- Do not reuse the same name to represent different kinds of entities within the same scope; use `p` for nodes, `r` for relationships, and `route` for paths if you want clarity.

Example:

```cypher
MATCH (staffMember:Person)-[knowsRelationship:KNOWS]->(knownPerson:Person)
RETURN staffMember.name AS nguoi,
       knownPerson.name AS nguoiDuocBiet,
       knowsRelationship.since AS tuNam;
```

### 9.2. Distinguishing Commonly Confused Components

| Syntax | Meaning |
|---|---|
| `(p)` | Node bound to variable `p`, not filtered by label. |
| `(p:Person)` | Node `p` required to have label `Person`. |
| `(:Person)` | Node with label `Person`, without creating a node variable. |
| `(p {id: 'p1'})` | Node bound to variable `p`, filtering property `id`. |
| `[r]` | Relationship bound to variable `r`, not filtered by type. |
| `[r:KNOWS]` | Relationship `r` must have type `KNOWS`. |
| `[:KNOWS]` | Relationship with type `KNOWS`, without creating a relationship variable. |
| `route = (...)-->(...)` | Binds the name `route` to the matched path. |
| `p.name` | Accesses property `name` of node/graph value `p`. |
| `$personId` | Parameter passed in by the caller, not a node/relationship/path variable. |

### 9.3. Variables and Parameters Are Two Different Concepts

```cypher
MATCH (p:Person)
WHERE p.id = $personId
RETURN p.name AS ten;
```

`p` is a node variable bound to matched nodes; `$personId` is an **input parameter**, such as the string `'p1'` passed by Neo4j Browser, Java Driver, or Spring Data Neo4j when running the query. Parameters are suitable for passing **data values** and help avoid concatenating query strings from user input.

To run the example without setting parameters, you can replace `$personId` with the string `'p1'`. In applications, prefer passing values via parameters.

Variable names or graph pattern structures cannot automatically be substituted by a parameter containing a string like `'p'` or `'KNOWS'`. When you need dynamic labels, types, or pattern structures, you must use syntax supported by your Cypher version and design appropriate input validation.

## 10. Variables, Result Row Counts, and Duplicates

Naming a variable allows a query to reference an entity, but **does not automatically make results unique**. Example:

```cypher
MATCH (p:Person)-[r:KNOWS]->(friend:Person)
RETURN p.name AS nguoi, friend.name AS ban;
```

The graph has two `KNOWS` relationships, so there are two rows; the variables `p` and `friend` can take different values on each row.

If a node has three outgoing `KNOWS` relationships, a query expanding from that node can produce three rows for the same node variable `p`. To return a **deduplicated list of people**:

```cypher
MATCH (p:Person)-[:KNOWS]->(:Person)
RETURN DISTINCT p.name AS nguoi;
```

To count relationships instead of counting node names:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[r:KNOWS]->(:Person)
RETURN p.name AS nguoi, count(r) AS soQuanHeDiRa
ORDER BY nguoi;
```

The result on the sample graph is An 1, Bình 1, Chi 0, and Dũng 0. `count(r)` ignores `null` values produced by `OPTIONAL MATCH`; `count(*)` would also count the row preserved when no relationship matches.

For counting unique nodes or relationships after expansions, you can use `count(DISTINCT p)` or `count(DISTINCT r)` as appropriate. You should not use `DISTINCT` merely to mask an incorrect pattern join.

## 11. Putting It Together: Node, Relationship, and Path Variables Working Together

Requirement: **Starting from An, find acquaintances reachable through exactly two `KNOWS` relationships, returning the start/middle/end names, the starting year of each relationship, and the path length.**

```cypher
MATCH route = (source:Person {id: 'p1'})
              -[firstLink:KNOWS]->(middle:Person)
              -[secondLink:KNOWS]->(destination:Person)
WITH source, middle, destination, firstLink, secondLink, route
RETURN source.name AS batDau,
       middle.name AS trungGian,
       destination.name AS ketThuc,
       firstLink.since AS canhDauTuNam,
       secondLink.since AS canhSauTuNam,
       length(route) AS soBuoc,
       [n IN nodes(route) | n.name] AS thuTuNut;
```

| batDau | trungGian | ketThuc | canhDauTuNam | canhSauTuNam | soBuoc | thuTuNut |
|---|---|---|---:|---:|---:|---|
| An | Bình | Chi | 2021 | 2023 | 2 | `['An', 'Bình', 'Chi']` |

How to read the query:

1. `source` is bound to An's node via the condition `id = 'p1'`.
2. `firstLink` is the `KNOWS` relationship from An to `middle` (Bình).
3. `secondLink` is the `KNOWS` relationship from Bình to `destination` (Chi).
4. `route` is **a path** containing all three nodes and both relationships.
5. `WITH` explicitly forwards the required variables.
6. `RETURN` extracts node/relationship properties and computes the path length.

This serves as the foundation for extending to multi-hop path queries, dependency analysis, connection recommendations, or finding related components in connected-data systems.

## 12. Common Pitfalls

| Issue | Example / Cause | Resolution |
|---|---|---|
| Mistaking a label for a variable name | `MATCH (Person)` only declares variable `Person`. | Write `MATCH (p:Person)` to filter by label. |
| Mistaking a type for a variable name | `-[KNOWS]->` declares variable `KNOWS`, without filtering type. | Write `-[:KNOWS]->` or `-[r:KNOWS]->`. |
| Using an undeclared variable | `RETURN r.since` when the pattern does not bind `r`. | Declare `[r:KNOWS]` or use the existing bound variable. |
| Variable lost after `WITH` | `WITH p` followed by `RETURN r`. | Add `r` to `WITH` if it is still needed. |
| Reading a path like a relationship | Calling `type(route)` when `route` is a path. | Use `relationships(route)`, then iterate over each relationship. |
| Misinterpreting path length | Treating `length(route)` as node count. | It counts edges; nodes are retrieved with `nodes(route)`. |
| Missing entities without links | Using `MATCH` to query a mandatory relationship. | Use `OPTIONAL MATCH` if unmatched entities must be kept. |
| Duplicate rows or sudden row explosion | A node matches many edges, or two unrelated patterns form a Cartesian product. | Review the pattern, branch cardinality, `DISTINCT`, and aggregation. |
| Wrong direction | Writing `->` when data stores the relationship in the opposite direction. | Use `<-` or an undirected pattern `-[]-` if it fits the requirement. |
| Confusing variables with parameters | Using `$p` intending to reference a matched node. | Use `p` for query variables; use `$id` for passed-in input values. |

## 13. Self-Practice Exercises

### Exercise 1. Node Variables and Properties

Find the node with `id = 'p2'`, bind it to variable `person`, and return its name and city.

<details>
<summary>Reference Solution</summary>

```cypher
MATCH (person:Person {id: 'p2'})
RETURN person.name AS ten, person.city AS thanhPho;
```

Result: **Bình – Hà Nội**.

</details>

### Exercise 2. Relationship Variables and Direction

Find the person who has a `KNOWS` relationship pointing to Chi; return that person's name and the relationship's `since` property.

<details>
<summary>Reference Solution</summary>

```cypher
MATCH (chi:Person {id: 'p3'})<-[relation:KNOWS]-(p:Person)
RETURN p.name AS nguoiBietChi, relation.since AS tuNam;
```

Result: **Bình – 2023**.

</details>

### Exercise 3. Path Variables and Node Lists

Starting from An, find the path across exactly two `KNOWS` relationships, bind it to variable `journey`, and return the path length along with the list of node names.

<details>
<summary>Reference Solution</summary>

```cypher
MATCH journey = (p:Person {id: 'p1'})
                -[:KNOWS]->(:Person)
                -[:KNOWS]->(destination:Person)
RETURN destination.name AS dich,
       length(journey) AS soBuoc,
       [n IN nodes(journey) | n.name] AS cacNut;
```

Result: **Chi**, length **2**, list `['An', 'Bình', 'Chi']`.

</details>

### Exercise 4. Variable Scope After `WITH`

Why does the following query fail? Fix it to return the name and the year they met.

```cypher
// Intentionally erroneous query
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b
RETURN b.name AS ban, r.since AS tuNam;
```

<details>
<summary>Reference Solution</summary>

`r` is not forwarded through `WITH`, so it is out of scope in `RETURN`.

```cypher
MATCH (a:Person {id: 'p1'})-[r:KNOWS]->(b:Person)
WITH b, r
RETURN b.name AS ban, r.since AS tuNam;
```

</details>

## 14. Key Takeaways

Variables in Cypher are used to **name and reference the matched data of each row**:

- `(p:Person)`: `p` is a **node**, `Person` is a **label**.
- `-[r:KNOWS]->`: `r` is a **relationship**, `KNOWS` is a **type**.
- `MATCH route = (...)-->(...)`: `route` is a **path**; its nodes and relationships can be inspected in order using `nodes(route)`, `relationships(route)`, and `length(route)`.
- `WITH` determines which variables remain usable in the next part of the query.
- `OPTIONAL MATCH` can assign `null` to new variables when unmatched, so evaluate functions and filter conditions carefully.

Understanding how variables are bound and forwarded is the prerequisite for writing complex Cypher queries, traversing paths, controlling intermediate row counts, and progressing to Neo4j query tuning, the Java Driver, or Spring Data Neo4j.
