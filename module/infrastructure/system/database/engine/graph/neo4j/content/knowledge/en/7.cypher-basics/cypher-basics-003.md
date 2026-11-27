# Reading and Writing Graph Patterns with Parentheses, Arrows, and Labels in Cypher

> **Chapter:** Cypher Basics  
> **Context:** Neo4j is a *property graph* database that stores nodes, relationships, and their properties. Cypher uses concise symbolic patterns to describe connections to find or create. This lesson helps you **accurately read and write graph patterns** before moving on to path queries, query optimization, the Java Driver, or Spring Data Neo4j.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish nodes, relationships, labels, relationship types, and properties via Cypher syntax.
2. Read arrow directions and distinguish directed patterns from undirected patterns.
3. Write patterns for a single node, a single relationship, chained relationships, or multiple branches from one node.
4. Combine patterns with `MATCH`, `WHERE`, `OPTIONAL MATCH`, `CREATE`, and `MERGE` according to your intent.
5. Translate back and forth between a graph diagram, a natural-language description, and a Cypher snippet.
6. Recognize common syntax or semantic mistakes when placing parentheses, colons, arrows, and labels.

## 2. What Is a Graph Pattern?

In a *property graph*:

- **Nodes** represent entities such as people, projects, teams, or servers; a node can have multiple **labels**.
- **Relationships** connect two nodes, have a **type** and a **stored direction**; relationships can also have properties.
- **Properties** store key–value pairs on nodes or relationships, such as `name`, `id`, or `since`.

Business example: "An is working on the Graph API project in the lead role."

```text
(An:Person) ──[:WORKS_ON {role: 'lead'}]──> (Graph API:Project)
```

Corresponding Cypher pattern:

```cypher
(a:Person {name: 'An'})-[work:WORKS_ON {role: 'lead'}]->(pr:Project {name: 'Graph API'})
```

This is only a **pattern**, not a standalone query. We place it inside a clause:

```cypher
MATCH (a:Person {name: 'An'})-[work:WORKS_ON {role: 'lead'}]->(pr:Project {name: 'Graph API'})
RETURN a.name AS nhanSu, work.role AS vaiTro, pr.name AS duAn;
```

`MATCH` uses the pattern to find existing data. `CREATE` and `MERGE` use patterns in write operations, though their semantics differ; Section 10 explains this in detail.

## 3. Notation Reference Table

| Syntax | How to Read It | Meaning |
|---|---|---|
| `()` | Any node | No variable assigned, no label or property requirements. |
| `(p)` | Node bound to `p` | Can reference `p` elsewhere in the query. |
| `(p:Person)` | Node `p` with label `Person` | The `:` precedes the label name. |
| `(p:Person {id: 'p1'})` | `Person` node with `id` equal to `p1` | Curly braces form a **property map**. |
| `(p:Person:Employee)` | Node with both labels | Multiple-label syntax supported in traditional patterns. |
| `--` | A relationship, any direction | Used in read patterns, without specifying a type. |
| `-->` | A relationship directed from left to right | Without specifying a type. |
| `<--` | A relationship directed from right to left | Without specifying a type. |
| `-[r]->` | A relationship bound to `r` | Does not constrain the type. |
| `-[:KNOWS]->` | A relationship of type `KNOWS` | Directed from left to right. |
| `-[r:KNOWS]->` | Relationship `r` of type `KNOWS` | Allows accessing `r.since`. |
| `-[r:KNOWS {since: 2021}]->` | Relationship with type and property filter | Combines variable, type, and property map. |
| `<-[:KNOWS]-` | A `KNOWS` relationship directed from right to left | Read according to the arrow. |
| `-[:KNOWS]-` | A `KNOWS` relationship in either direction | Used when only the link itself matters. |
| `path = (a)-[:KNOWS]->(b)` | Assigns `path` to the matched path | The path value contains both nodes and relationships. |

**Visual rule of thumb:** parentheses `(...)` enclose nodes; square brackets `[...]` enclose relationships; colons `:` introduce labels or relationship types; curly braces `{...}` enclose properties; dashes and arrows indicate connections and direction.

### 3.1. Read Left to Right, but Always Watch the Arrow

```text
(a)-[:FOLLOWS]->(b)   a follows b
(a)<-[:FOLLOWS]-(b)   b follows a
(a)-[:FOLLOWS]-(b)    a and b have a FOLLOWS relationship in either direction
```

In the second pattern, even though `a` appears on the left, **the relationship direction is still from `b` to `a`**. Do not infer direction from word order or left-to-right reading habits; look at the arrowhead.

## 4. Creating a Sample Graph for Practice

Run the statements below in a **practice database**. The IDs start with `cypher003-` so you can easily distinguish them from other data. The example uses `MERGE` for nodes and relationships so re-running it normally does not create duplicate elements matching the same pattern.

```cypher
MERGE (an:Person {id: 'cypher003-an'})
SET an.name = 'An', an.city = 'Hà Nội'
SET an:Engineer

MERGE (binh:Person {id: 'cypher003-binh'})
SET binh.name = 'Bình', binh.city = 'Đà Nẵng'

MERGE (chi:Person {id: 'cypher003-chi'})
SET chi.name = 'Chi', chi.city = 'Hà Nội'

MERGE (api:Project {id: 'cypher003-api'})
SET api.name = 'Graph API', api.status = 'active'

MERGE (team:Team {id: 'cypher003-platform'})
SET team.name = 'Platform'

MERGE (an)-[knowsBinh:KNOWS]->(binh)
SET knowsBinh.since = 2021

MERGE (binh)-[knowsChi:KNOWS]->(chi)
SET knowsChi.since = 2023

MERGE (an)-[works:WORKS_ON]->(api)
SET works.role = 'lead'

MERGE (binh)-[helps:WORKS_ON]->(api)
SET helps.role = 'developer'

MERGE (an)-[:MEMBER_OF]->(team);
```

Corresponding diagram:

```text
     [Person, Engineer]                        [Team]
           An ────────────[:MEMBER_OF]─────────> Platform
            │
            ├─────────────[:KNOWS {since:2021}]──────> Bình:Person
            │                                             │
            │                                             └─[:KNOWS {since:2023}]──> Chi:Person
            │
            └─────────────[:WORKS_ON {role:'lead'}]─┐
                                                    v
                                               Graph API:Project
                                                    ^
                         Bình ─[:WORKS_ON {role:'developer'}]─┘
```

**Note on results:** the row counts illustrated below assume the relevant nodes/relationships consist solely of the sample data just created. If running in a database with other data, filter by `id` to avoid mixing samples. If the database already contains multiple nodes with the same `id`, `MERGE` does not replace a uniqueness constraint.

## 5. Reading and Writing Node Patterns with `(...)`

### 5.1. Node Only, Without a Label

```cypher
MATCH (n)
RETURN n
LIMIT 5;
```

`(n)` is **any node**, bound to variable `n`. It could be a `Person`, `Project`, `Team`, or a node with any other label. `()` is also any node, but without assigning a name:

```cypher
MATCH ()-[:MEMBER_OF]->(t:Team {id: 'cypher003-platform'})
RETURN t.name AS nhom;
```

In the second example, the left-hand node does not need a variable because we only need the team's information. Omitting the variable does not remove the node from the pattern.

### 5.2. Labels Use a Colon

```cypher
MATCH (p:Person {id: 'cypher003-an'})
RETURN p.name AS ten, labels(p) AS cacNhan;
```

`Person` is a **label**, and `p` is a **variable**. On An's node, `labels(p)` contains `Person` and `Engineer` (the order of labels in the list should not be assumed).

A node can have multiple labels. The pattern:

```cypher
MATCH (p:Person:Engineer)
WHERE p.id = 'cypher003-an'
RETURN p.name AS kySu;
```

matches only nodes that have **both labels** `Person` and `Engineer`. Label names are case-sensitive: `Person` and `person` are not identical.

**Easy mistake to make:**

```cypher
MATCH (Person)
RETURN Person;
```

In the query above, `Person` is **a variable named Person**, not a label, because the `:` is missing. To filter by label, write `(p:Person)` or `(:Person)`.

### 5.3. Properties Go Inside `{...}`

```cypher
MATCH (p:Person {id: 'cypher003-binh', city: 'Đà Nẵng'})
RETURN p.name AS ten;
```

A property map after the label means: find a node whose corresponding properties match the given values. You can also separate the conditions:

```cypher
MATCH (p:Person)
WHERE p.id = 'cypher003-binh' AND p.city = 'Đà Nẵng'
RETURN p.name AS ten;
```

If an application passes an ID from the Java Driver or Spring Data Neo4j, use **parameters** instead of concatenating values into the query string:

```cypher
MATCH (p:Person {id: $personId})
RETURN p.name AS ten;
```

In this snippet, `p` is a pattern variable, while `$personId` is a parameter value supplied by the caller, such as `'cypher003-binh'`.

## 6. Reading and Writing Relationship Patterns with `-[]-` and Arrows

### 6.1. An Edge with Type and Left-to-Right Direction

```cypher
MATCH (a:Person {id: 'cypher003-an'})-[:KNOWS]->(b:Person)
RETURN a.name AS nguoiA, b.name AS nguoiB;
```

Read as: "From node An, follow **one** outgoing `KNOWS` relationship to another `Person` node." Result on sample data: **An → Bình**.

The pattern `-[:KNOWS]->` consists of:

1. `-` connecting the starting node to the relationship.
2. `[ ... ]` enclosing relationship details.
3. `:KNOWS` requiring type `KNOWS`.
4. `->` indicating direction from the left node to the right node.

`KNOWS` is a type, not a variable name. If you do not need to reference the relationship later, you do not have to assign a variable to it.

### 6.2. Right-to-Left Directed Relationship

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})<-[:KNOWS]-(other:Person)
RETURN other.name AS nguoiBietChi;
```

Read as: "Who has a `KNOWS` relationship **pointing to** Chi?" Result: **Bình**.

The same connection can be written as two directionally equivalent patterns:

```text
(binh)-[:KNOWS]->(chi)
(chi)<-[:KNOWS]-(binh)
```

Swapping the two nodes' positions and flipping the arrow **does not reverse the stored direction of the data**.

### 6.3. Undirected Pattern (Direction Not Required)

```cypher
MATCH (binh:Person {id: 'cypher003-binh'})-[:KNOWS]-(other:Person)
RETURN other.name AS ketNoi
ORDER BY ketNoi;
```

`-[:KNOWS]-` allows matching relationships in **either direction**. Because Bình has an incoming edge from An and an outgoing edge to Chi, the result contains **An** and **Chi**.

This **does not mean relationships in the database become undirected**. Relationships still have a stored direction; the pattern simply asks for a connection in either direction.

### 6.4. Omitting Square Brackets When Not Filtering by Type

```cypher
MATCH (an:Person {id: 'cypher003-an'})-->(destination)
RETURN labels(destination) AS nhanDich,
       destination.name AS tenDich;
```

`-->` requires an outgoing relationship but **does not specify a type**. In the sample graph, the target can be Bình, Graph API, or Platform because An has three types of outgoing relationships. Similarly:

```cypher
MATCH (an:Person {id: 'cypher003-an'})--(other)
RETURN other.name AS ketNoi;
```

`--` filters neither type nor direction. When you need a specific business relationship, put the type in square brackets, such as `-[:WORKS_ON]->`.

### 6.5. Attaching a Variable and Property Filter to a Relationship

```cypher
MATCH (a:Person {id: 'cypher003-an'})
      -[r:KNOWS {since: 2021}]->(b:Person)
RETURN b.name AS ban,
       r.since AS quenTu,
       type(r) AS loaiQuanHe;
```

`r` is the relationship variable, `KNOWS` is the type, and `{since: 2021}` filters by a property on the **relationship**. In the result, `r.since = 2021` and `type(r) = 'KNOWS'`.

With only `-[r]->`, the query still binds `r` but **does not filter by type**:

```cypher
MATCH (a:Person {id: 'cypher003-an'})-[r]->(b)
RETURN type(r) AS loai, b.name AS dich;
```

Be careful to distinguish `-[KNOWS]->` from `-[:KNOWS]->`: the former binds a variable **named KNOWS** without requiring type `KNOWS`; only the latter filters by that type.

## 7. Combining Multiple Nodes and Relationships into Larger Patterns

### 7.1. Two Consecutive Edges

To find "An knows someone who in turn knows another person", write:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
      -[:KNOWS]->(middle:Person)
      -[:KNOWS]->(last:Person)
RETURN an.name AS batDau, middle.name AS trungGian, last.name AS ketThuc;
```

In the sample graph: **An → Bình → Chi**. Two `-[:KNOWS]->` segments mean **two consecutive edges**, not one edge with two types.

You can name the entire path to inspect the pattern:

```cypher
MATCH route = (an:Person {id: 'cypher003-an'})
              -[:KNOWS]->(:Person)
              -[:KNOWS]->(last:Person)
RETURN last.name AS dich,
       length(route) AS soCanh,
       [n IN nodes(route) | n.name] AS cacNode;
```

`length(route)` counts **relationships**, so it returns `2`; `nodes(route)` returns the three nodes in the path. Details on declaring variables for nodes, relationships, and paths are covered in their own lesson; here, focus on the **pattern shape**.

### 7.2. Multiple Branches Starting from One Node

Requirement: "Someone who both knows another person and participates in a project."

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[:KNOWS]->(friend:Person),
      (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nhanSu, friend.name AS ban, pr.name AS duAn;
```

Both patterns share **variable `p`**, so both start from An's node. Result: **An – Bình – Graph API**.

If replaced by two independent variables `p` and `x`, Neo4j could pair each match of the two patterns into a **Cartesian product**. When you want to express two branches from the same node, reuse the exact same variable name.

### 7.3. Multiple Labels, Multiple Relationship Types

A pattern with multiple labels is an **AND** condition:

```cypher
MATCH (p:Person:Engineer {id: 'cypher003-an'})
RETURN p.name AS nguoiCoHaiNhan;
```

When **any one of several types** is acceptable, Cypher allows type alternation in read patterns:

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[r:KNOWS|WORKS_ON]->(other)
RETURN type(r) AS loai, other.name AS dich
ORDER BY loai;
```

This query can return `KNOWS – Bình` and `WORKS_ON – Graph API`; `MEMBER_OF` does not satisfy the type choice. Do not confuse `|` in relationship type selection with requiring a node to carry multiple labels simultaneously.

### 7.4. Fixed Step Count vs. Variable Step Count

Two consecutive edges as in Section 7.1 form a pattern of **exactly two hops**. In Neo4j/Cypher versions supporting *quantified relationships* (Neo4j 5.9 and later), you can write:

```cypher
MATCH route = (an:Person {id: 'cypher003-an'})
              -[:KNOWS]->{1,2}
              (end:Person)
RETURN end.name AS dich, length(route) AS soBuoc
ORDER BY soBuoc;
```

`{1,2}` allows traversing one or two `KNOWS` edges. With the sample data, the targets are Bình (1 hop) and Chi (2 hops). In older Cypher versions or modes, you may encounter the syntax `-[:KNOWS*1..2]->`; use the syntax appropriate for the version you are running.

## 8. Reading Patterns in `MATCH` and `OPTIONAL MATCH`

### 8.1. `MATCH` Requires the Entire Pattern to Match

```cypher
MATCH (p:Person {id: 'cypher003-chi'})-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

Chi has no `WORKS_ON` relationship in the sample data, so the query returns **0 rows**, even though Chi's node exists. That is because **the entire pattern** must match.

### 8.2. `OPTIONAL MATCH` Preserves the Node When an Edge Is Missing

```cypher
MATCH (p:Person {id: 'cypher003-chi'})
OPTIONAL MATCH (p)-[:WORKS_ON]->(pr:Project)
RETURN p.name AS nguoi, pr.name AS duAn;
```

The result has **one row**: `nguoi = 'Chi'` and `duAn = null`. `OPTIONAL MATCH` is useful when generating reports that include nodes without links yet.

### 8.3. `WHERE` Placement with Optional Patterns

```cypher
MATCH (p:Person)
WHERE p.id IN ['cypher003-an', 'cypher003-binh', 'cypher003-chi']
OPTIONAL MATCH (p)-[w:WORKS_ON]->(pr:Project)
WHERE w.role = 'lead'
RETURN p.name AS nguoi, pr.name AS duAnLead
ORDER BY nguoi;
```

`WHERE` after `OPTIONAL MATCH` is a condition **on the optional part**: An matches the Graph API project, while Bình and Chi are still kept with `duAnLead` equal to `null`.

If you move `w.role = 'lead'` to a `WHERE` **after a `WITH`**, rows containing `null` can be filtered out. The placement of the condition therefore directly affects how the graph pattern is interpreted.

## 9. Distinguishing a Pattern from a Complete Statement

A pattern:

```cypher
(p:Person)-[:KNOWS]->(q:Person)
```

does not return results on its own. To query, add the appropriate clauses:

```cypher
MATCH (p:Person {id: 'cypher003-an'})-[:KNOWS]->(q:Person)
RETURN q.name AS ban;
```

Comparing purposes:

| Purpose | Clause Attached to Pattern | Notes |
|---|---|---|
| Find existing nodes/relationships | `MATCH` | Does not create new data. |
| Find if present, keep row if missing | `OPTIONAL MATCH` | Unmatched new variables receive `null`. |
| Create new nodes/relationships | `CREATE` | Can create duplicates if re-run. |
| Find or create matching a pattern | `MERGE` | Should pair with an appropriate constraint if uniqueness is required. |
| Update properties or add labels | `SET` | Usually follows `MATCH`/`MERGE` to target the right entities. |
| Return nodes, properties, or paths | `RETURN` | Defines the output fields. |

Patterns can be combined with `WHERE`, `WITH`, or other clauses to further filter and transform results. Organizing clauses is covered in detail in the lesson on Cypher query structure.

## 10. Writing Graph Data with `CREATE` and `MERGE`

Node and relationship notation is the same for reading and writing, but the **clause** determines the effect. In particular, when creating relationships, explicitly specify direction and type so the stored structure matches business semantics.

### 10.1. `CREATE` Always Creates New Elements

```cypher
CREATE (d:Department {id: 'cypher003-dept', name: 'Engineering'})
RETURN d.name AS tenPhong;
```

If you re-run the `CREATE` snippet above, another `Department` node with the same properties is created. In a real application, this behavior can cause duplicate records if the intent is "one Department per ID".

Creating a relationship between **two already-found nodes**:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
MATCH (binh:Person {id: 'cypher003-binh'})
CREATE (an)-[:MENTORS {since: 2024}]->(binh);
```

This snippet **intentionally creates** a new `MENTORS` edge every time it runs, even if such an edge already exists. Run it only when you genuinely want to create another relationship.

### 10.2. `MERGE` Finds or Creates

```cypher
MERGE (d:Department {id: 'cypher003-dept'})
ON CREATE SET d.name = 'Engineering'
RETURN d.id AS id, d.name AS tenPhong;
```

`MERGE` attempts to match the node pattern and creates it if absent. `ON CREATE SET` updates only when the create branch is taken. For relationships, bind the two endpoint nodes first:

```cypher
MATCH (an:Person {id: 'cypher003-an'})
MATCH (binh:Person {id: 'cypher003-binh'})
MERGE (an)-[r:MENTORS]->(binh)
ON CREATE SET r.since = 2024
RETURN type(r) AS loai, r.since AS tuNam;
```

`MERGE` checks for the `(an)-[:MENTORS]->(binh)` pattern before creating it. Because both nodes are already bound via `MATCH`, the query avoids accidentally creating new `Person` nodes—as can happen when merging a large node–relationship pattern without specifying which nodes already exist.

**Regarding uniqueness:** `MERGE` does not replace schema-level uniqueness under concurrent transactions. For identifying properties such as `Person.id`, design an appropriate **uniqueness constraint** in production systems.

### 10.3. `SET` Updates Selected Properties and Labels

```cypher
MATCH (p:Person {id: 'cypher003-binh'})
SET p.city = 'Đà Nẵng'
SET p:Engineer
RETURN p.name AS ten, labels(p) AS nhan;
```

In the example, `SET p.city` updates a property, while `SET p:Engineer` adds the `Engineer` label to the node without recreating it. Remember to distinguish a property map in a pattern `{city: 'Đà Nẵng'}` from an assignment `p.city = 'Đà Nẵng'` in `SET`.

## 11. Translating Descriptions into Cypher Patterns

| Requirement Description | Cypher Pattern | Key Point |
|---|---|---|
| Any person | `(p:Person)` | Label after `:`. |
| Person with a specific ID | `(p:Person {id: $id})` | Filter property inside curly braces. |
| Person A knows person B | `(a:Person)-[:KNOWS]->(b:Person)` | Arrow from A to B. |
| Person A is known by person B | `(a:Person)<-[:KNOWS]-(b:Person)` | Stored direction from B to A. |
| Two people have a KNOWS relationship in either direction | `(a:Person)-[:KNOWS]-(b:Person)` | Pattern does not constrain direction. |
| Person works on a project in the lead role | `(p:Person)-[:WORKS_ON {role: 'lead'}]->(pr:Project)` | Property placed on the relationship. |
| Person knows a friend of a friend | `(p:Person)-[:KNOWS]->(:Person)-[:KNOWS]->(q:Person)` | Two consecutive relationships. |
| An engineer who is also a person | `(p:Person:Engineer)` | Node satisfies both labels. |
| Person belongs to a team | `(p:Person)-[:MEMBER_OF]->(t:Team)` | Type distinct from `WORKS_ON`. |

When writing patterns yourself, walk through four questions:

1. **Which entities?** Write nodes with `(...)`, adding labels and known properties.
2. **Which links?** Place a relationship between the two nodes and add `:TYPE` if needed.
3. **In which direction?** Check the arrow based on how the relationship is stored.
4. **Read or write?** Choose `MATCH`, `OPTIONAL MATCH`, `CREATE`, or `MERGE` as appropriate.

## 12. Common Mistakes When Reading Graph Patterns

| Confusing Syntax or Result | Cause | Fix |
|---|---|---|
| `MATCH (Person)` returns many different labels | `Person` is a variable, missing `:`. | `MATCH (p:Person)`. |
| `-[KNOWS]->` returns multiple relationship types | `KNOWS` is a **variable**, no type specified. | `-[:KNOWS]->` or `-[r:KNOWS]->`. |
| `(a)-[:KNOWS]->(b)` returns no results | Data only stores the relationship from `b` to `a`. | Change to `(a)<-[:KNOWS]-(b)` or use an undirected pattern if appropriate. |
| `(a)-->(b)` returns other relationship types too | Pattern has no `:TYPE`. | Add the exact relationship type. |
| Query misses people without projects | `MATCH` requires the edge to exist as well. | Use `OPTIONAL MATCH` if unmatched people should be kept. |
| Running `CREATE` repeatedly increases node/edge count | `CREATE` always creates new elements. | Use `MERGE` when find-or-create semantics are needed, and design appropriate constraints. |
| Results multiply into many rows | A node has multiple matching edges or patterns lack a shared variable. | Check connection counts, shared variables, and `DISTINCT`/aggregation as needed. |
| Confusing `:Person` with `:WORKS_ON` | Both use a colon, but one is on a **node** and the other on a **relationship**. | Labels go inside `(...)`, types go inside `[...]`. |
| Using `length(path)` to count nodes | `length` counts relationships. | Use `size(nodes(path))` when you want the number of nodes on the path. |
| Assuming `-[:KNOWS]-` creates an undirected relationship | Read patterns can omit direction, but stored data is always directed. | Specify an arrow when writing or when business semantics require direction. |

Another case to keep in mind: if `(a)-[:KNOWS]->(b)` matches three relationships, the result can have **three rows** for the same node `a`. A pattern is a matching condition, not an automatic grouping of one row per person. Use `RETURN DISTINCT a` or aggregate when you genuinely want deduplication.

## 13. Practice Exercises

Perform these on the sample graph from Section 4. For exercises using IDs, keep the `cypher003-` prefix.

### Exercise 1. From Diagram to Query

Write a query to find the person to whom An has an outgoing `KNOWS` relationship; return the target person's name.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (an:Person {id: 'cypher003-an'})-[:KNOWS]->(friend:Person)
RETURN friend.name AS ban;
```

Result: **Bình**.

</details>

### Exercise 2. Swap Node Positions While Preserving Direction

Find the person **who has a KNOWS relationship pointing to Chi**. Place Chi's node on the **left side** of the pattern.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})<-[:KNOWS]-(p:Person)
RETURN p.name AS nguoiBietChi;
```

Result: **Bình**.

</details>

### Exercise 3. Reading a Relationship Property

Find An's role in the Graph API project. Return the project name and the `role` property from the relationship.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (an:Person {id: 'cypher003-an'})
      -[w:WORKS_ON]->(pr:Project {id: 'cypher003-api'})
RETURN pr.name AS duAn, w.role AS vaiTro;
```

Result: **Graph API – lead**.

</details>

### Exercise 4. Two Consecutive Hops

Find the person reachable from An through **exactly two** `KNOWS` edges. Return the destination name and the number of edges in the path.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH journey = (an:Person {id: 'cypher003-an'})
                -[:KNOWS]->(:Person)
                -[:KNOWS]->(destination:Person)
RETURN destination.name AS dich, length(journey) AS soCanh;
```

Result: **Chi – 2**.

</details>

### Exercise 5. Missing Relationship

Chi does not participate in any project in the sample graph. Write a query that **still returns one row for Chi** with project name equal to `null`.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})
OPTIONAL MATCH (chi)-[:WORKS_ON]->(pr:Project)
RETURN chi.name AS ten, pr.name AS duAn;
```

Result: **Chi – null**.

</details>

### Exercise 6. Find or Create a Directed Relationship

Write a query ensuring there is a `COLLABORATES_WITH` relationship **from Chi to An**, without intentionally creating duplicate edges on repeated runs.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (chi:Person {id: 'cypher003-chi'})
MATCH (an:Person {id: 'cypher003-an'})
MERGE (chi)-[:COLLABORATES_WITH]->(an);
```

Both nodes are located first, and then `MERGE` checks for or creates the relationship with the requested type and direction.

</details>

## 14. Summary

To read Neo4j/Cypher patterns, break the structure into three layers:

- `(p:Person {id: '...'})` describes a **node**: variable, label, and properties.
- `-[r:KNOWS {since: 2021}]->` describes a **relationship**: variable, type, properties, and direction.
- Chaining `(...)` and `-[...]->` pairs expresses the **connection shape**: a single edge, a multi-edge chain, or branches sharing a node.

The read diagram and the Cypher query must always preserve exact business semantics. `MATCH` finds existing patterns; `OPTIONAL MATCH` allows missing connections; `CREATE` creates new elements; `MERGE` finds or creates according to a pattern. Once you can read and write parentheses, arrows, and labels accurately on your own, you have the foundation to query multi-hop relationships, evaluate result row counts, build indexes/constraints, and connect Neo4j to Java applications.
