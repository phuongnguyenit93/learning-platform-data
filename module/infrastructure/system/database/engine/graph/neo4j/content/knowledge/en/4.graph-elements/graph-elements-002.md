# Directed Relationships, Relationship Types, and Start–End Nodes

## 1. Objectives and Role of This Topic in Neo4j

In Neo4j's **property graph** model, a **node** represents an entity, while a **relationship** connects two nodes and expresses how entities relate to one another. Relationships are an essential component for modeling connected data, enabling relationship and path queries with **Cypher**.

In the **Graph Elements** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson focuses on three core characteristics of relationships:

1. **Directionality**: every relationship is stored with a direction from a **start node** to an **end node**.
2. **Relationship type**: a name describing the meaning of the connection, such as `FOLLOWS`, `WORKS_AT`, or `PURCHASED`.
3. **Two endpoints**: a relationship connects exactly two nodes; the nodes can carry their own labels and properties.

After completing this lesson, you will be able to create and query relationships by direction, inspect types and endpoints, update relationship properties, distinguish commonly confused cases, and design link directions suited for Java Driver, Spring Data Neo4j, and subsequent path queries.

## 2. What Is a Relationship in a Property Graph?

Consider a social network with two people:

```text
(:Person {personId: 'P001', name: 'An'})
                 |
                 |  [:FOLLOWS {since: 2024-01-20}]
                 v
(:Person {personId: 'P002', name: 'Bình'})
```

The diagram above states: **An follows Bình**. Here:

- Node **An** is the **start node** of the relationship.
- Node **Bình** is the **end node** of the relationship.
- `FOLLOWS` is the **relationship type**.
- `since` is a **relationship property**, indicating when the follow began.

The corresponding Cypher pattern:

```cypher
(an:Person)-[:FOLLOWS]->(binh:Person)
```

In this notation, `an` and `binh` are variables used in the query, `:Person` is the **node label**, and `:FOLLOWS` is the **relationship type**. The `->` arrow indicates the direction from the left node to the right node.

A relationship in Neo4j has the following characteristics:

| Characteristic | Explanation |
| --- | --- |
| Two endpoints | Connects **exactly two nodes**: one start node and one end node |
| Direction | Always has a stored direction from start to end |
| Type | Each relationship has **exactly one relationship type** |
| Properties | Can carry zero, one, or multiple key–value pairs |
| Identity | Is a distinct graph element; two relationships with the same two endpoints and the same type can still be distinct |
| Node dependency | A relationship must connect existing nodes in the graph; there are no standalone relationships unattached to nodes |

Neo4j supports **multiple relationships between the same pair of nodes**, even with the same type and direction. Therefore, you cannot assume that the pair `(An, Bình)` has only a single edge.

## 3. Directionality: Stored Direction vs. Query Direction

### 3.1. Stored Direction of a Relationship

In Neo4j, **every relationship is directed**. The following two patterns represent two different directions:

```cypher
(an)-[:FOLLOWS]->(binh)  // An follows Bình
(an)<-[:FOLLOWS]-(binh)  // Bình follows An
```

If only `(an)-[:FOLLOWS]->(binh)` exists, you cannot infer that the reverse relationship also exists. Especially for types like `FOLLOWS`, `OWNS`, `MANAGES`, and `PARENT_OF`, direction carries business meaning and must be chosen carefully.

Examples:

- `(employee)-[:WORKS_AT]->(company)`: employee works at company.
- `(customer)-[:PLACED]->(order)`: customer placed order.
- `(order)-[:CONTAINS]->(product)`: order contains product.
- `(serviceA)-[:CALLS]->(serviceB)`: service A calls service B.

Reversing these links without changing the interpretation will corrupt the semantics of the data.

### 3.2. Direction in Cypher Query Patterns

Cypher allows querying in the **outgoing direction**, **incoming direction**, or **without constraining direction**. Suppose `a` is a known node:

| Pattern | Meaning |
| --- | --- |
| `(a)-[:FOLLOWS]->(b)` | Find `b` that `a` is following |
| `(a)<-[:FOLLOWS]-(b)` | Find `b` that is following `a` |
| `(a)-[:FOLLOWS]-(b)` | Find `b` connected to `a` via `FOLLOWS` in **either direction** |
| `(a)-[r]->(b)` | Find all outgoing relationship types from `a`; bind the relationship to variable `r` |
| `(a)<-[r]-(b)` | Find all incoming relationship types to `a` |
| `(a)-[r]-(b)` | Find relationships of any type and in either direction |

**Important distinction:** The pattern `(a)-[:FOLLOWS]-(b)` **does not turn** the relationship into an undirected one in the database. It only allows the query to match edges in both directions. The stored start node and end node values remain unchanged.

For example, if the graph contains both `An -> Bình` and `Bình -> An`, an undirected-pattern query starting from `An` will see **both relationships**. When a query starts from two unbound variables, symmetric assignments of start–end nodes can appear; use an explicit direction or `DISTINCT` when you need non-duplicate results by entity.

### 3.3. Relationships with Bidirectional Meaning

In real life, there are symmetric links such as "is friends with" or "is connected to". Neo4j still requires a stored direction. There are two common design choices:

1. **Store one relationship**, such as `(a)-[:FRIENDS_WITH]->(b)`, and query with the direction-agnostic pattern `-[:FRIENDS_WITH]-`. Establish a convention to avoid creating a duplicate symmetric edge.
2. **Store two directed relationships**, `(a)-[:FRIENDS_WITH]->(b)` and `(b)-[:FRIENDS_WITH]->(a)`, when the business domain requires two independent actions or two separate records.

There is no single right choice for every problem: align **business semantics**, write logic, and query patterns. For example, `FOLLOWS` is inherently asymmetric, so only add the reverse relationship when the other person actually follows back.

## 4. Relationship Type: Expressing the Semantics of a Link

A **relationship type** is the name used to distinguish the meaning of links. In Cypher, write the type after `:` inside square brackets:

```cypher
(p:Person)-[:WORKS_AT]->(c:Company)
(p:Person)-[:FOLLOWS]->(q:Person)
(c:Company)-[:OPERATES_IN]->(city:City)
```

A person can simultaneously work at a company and follow another person, but these are **two different relationship types**. You should not collapse all links into a generic type like `:RELATED_TO` and rely solely on a `kind` property, unless there is a clear modeling reason to do so.

### 4.1. One Relationship Has Exactly One Type

Compare with node labels:

| Node label | Relationship type |
| --- | --- |
| A node can have multiple labels: `:Person:Employee` | A relationship has only one type: `:WORKS_AT` |
| Labels classify entities/roles | Type describes the nature of the connection |
| Read with `labels(n)` | Read with `type(r)` |
| Labels can be added or removed with `SET`/`REMOVE` | Cannot directly change the type of an existing relationship; when a type must change, create a new relationship and delete the old one after handling data appropriately |

By convention, type names are usually written in uppercase with underscores: `WORKS_AT`, `PLACED_ORDER`, `DEPENDS_ON`. This is a naming convention for readability, not a strict requirement of Neo4j. Type names are case-sensitive; `FOLLOWS` differs from `follows`.

### 4.2. Choosing Type Names Based on Clear Phrasing

Read the pattern `(a)-[:TYPE]->(b)` as a sentence:

| Pattern | Descriptive Sentence |
| --- | --- |
| `(user)-[:FOLLOWS]->(author)` | User follows author |
| `(order)-[:CONTAINS]->(product)` | Order contains product |
| `(developer)-[:CONTRIBUTES_TO]->(project)` | Developer contributes to project |
| `(topic)-[:PREREQUISITE_OF]->(lesson)` | Topic is a prerequisite of lesson |

If the sentence is awkward to read or the direction could be interpreted backward, adjust the **type name**, the **direction**, or both before ingesting large amounts of data.

## 5. Two Endpoints: Start Node and End Node

Every relationship has a **start node** and an **end node**. These are the roles of the two nodes **with respect to that specific relationship**, not fixed node types or labels.

A node can be the **end node** of one relationship and at the same time the **start node** of another relationship:

```text
(:Person {name: 'An'})
        |
        |  [:FOLLOWS]
        v
(:Person {name: 'Bình'})
        |
        |  [:WORKS_AT]
        v
(:Company {name: 'GreenTech'})
```

In the diagram, **Bình** is the end node of `An -[:FOLLOWS]-> Bình`, but the start node of `Bình -[:WORKS_AT]-> GreenTech`.

Cypher provides functions to inspect them directly:

```cypher
MATCH ()-[r:FOLLOWS]->()
RETURN type(r) AS relationshipType,
       startNode(r) AS startNode,
       endNode(r) AS endNode
LIMIT 10;
```

In large graphs, it is usually best to select nodes by label and identifier before traversing edges:

```cypher
MATCH (a:Person {personId: 'P001'})-[r:FOLLOWS]->(b:Person)
RETURN a.fullName AS follower,
       b.fullName AS followedPerson,
       type(r) AS relationshipType,
       startNode(r).personId AS fromId,
       endNode(r).personId AS toId;
```

`startNode(r)` and `endNode(r)` read the two endpoints according to the **stored direction**, even when the query found the relationship using an undirected pattern. These two functions return **nodes**, so you can access their properties such as `startNode(r).personId`.

### 5.1. Self-Loop: Both Endpoints Can Be the Same Node

A relationship still has **two endpoint roles (start–end)** even when both reference **the same node**. This case is called a **self-loop**:

```text
           ┌── [:RETRIES] ──┐
           │                │
           ▼                │
      (:Job {id: 'J001'}) ──┘
```

Cypher illustration:

```cypher
CREATE (s:State {stateId: 'S001', name: 'Waiting'})
CREATE (s)-[:TRANSITIONS_TO {reason: 'retry'}]->(s)
RETURN s;
```

This is a valid relationship: `startNode(r) = endNode(r)`. In a given application, a self-loop may be meaningful behavior or a data error; define the business rule rather than assuming all self-loops are invalid.

### 5.2. Direction Does Not Depend on Visual Layout

In a visualizer, the tool might draw An to the right of Bình, swap vertical/horizontal positions, or rearrange the entire diagram. **On-screen position does not determine direction**; direction is determined by the stored relationship and the arrow syntax in Cypher. Always rely on `startNode(r)`, `endNode(r)`, and type when verifying.

## 6. Practicing with a Sample Graph

The examples in this section can be run on a **test database**. `CREATE` always creates new elements; run the setup step only once to avoid duplicate nodes or duplicate relationships.

### 6.1. Creating Nodes and Directed Relationships

```cypher
CREATE (an:Person {personId: 'P001', fullName: 'An'})
CREATE (binh:Person {personId: 'P002', fullName: 'Bình'})
CREATE (company:Company {companyId: 'C001', name: 'GreenTech'})
CREATE (an)-[:FOLLOWS {since: date('2024-01-20')}]->(binh)
CREATE (binh)-[:FOLLOWS {since: date('2025-04-12')}]->(an)
CREATE (an)-[:WORKS_AT {
  since: date('2022-09-01'),
  position: 'Developer'
}]->(company)
RETURN an, binh, company;
```

We have created **three nodes** and **three relationships**:

```text
 (An:Person) -[:FOLLOWS]-> (Bình:Person)
 (An:Person) <-[:FOLLOWS]- (Bình:Person)
 (An:Person) -[:WORKS_AT]-> (GreenTech:Company)
```

The two `FOLLOWS` edges point in opposite directions and therefore carry two different meanings: An follows Bình, and Bình follows An.

### 6.2. Finding Outgoing Relationships

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]->(other:Person)
RETURN an.fullName AS source,
       other.fullName AS target,
       r.since AS followedSince;
```

Expected result from the sample data: `An` → `Bình`, starting `2024-01-20`.

### 6.3. Finding Incoming Relationships

```cypher
MATCH (an:Person {personId: 'P001'})<-[r:FOLLOWS]-(follower:Person)
RETURN follower.fullName AS follower,
       an.fullName AS followedPerson,
       r.since AS followedSince;
```

Expected result: `Bình` → `An`, starting `2025-04-12`. Simply changing the arrow direction in the pattern changes the meaning of the query.

### 6.4. Querying Without Direction Constraints

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]-(other:Person)
RETURN type(r) AS type,
       startNode(r).fullName AS fromName,
       endNode(r).fullName AS toName,
       r.since AS since
ORDER BY since;
```

This query finds **both `FOLLOWS` relationships** connecting An and Bình. `startNode(r)` and `endNode(r)` still show the stored direction of each individual edge; they do not depend on the direction the query used to traverse it.

### 6.5. Traversing Outgoing Relationship Types

```cypher
MATCH (an:Person {personId: 'P001'})-[r]->(destination)
RETURN type(r) AS type,
       labels(destination) AS targetLabels,
       properties(destination) AS targetProperties
ORDER BY type;
```

In the sample data, An has a `FOLLOWS` relationship to Bình and a `WORKS_AT` relationship to GreenTech. `type(r)` returns a string representing each relationship's type; `labels(destination)` returns the list of labels of the **end node**.

### 6.6. Counting Relationships by Type and Direction

```cypher
MATCH (p:Person {personId: 'P001'})-[r]->()
RETURN type(r) AS relationshipType, count(r) AS outgoingCount
ORDER BY relationshipType;
```

In this example, An has one outgoing `FOLLOWS` and one outgoing `WORKS_AT`. To count An's followers, you must count **incoming** relationships using `(p)<-[r:FOLLOWS]-()`.

## 7. Relationship Properties and How to Manipulate Them

Relationships in Neo4j also have **properties** just like nodes. A property belongs on a relationship when it describes **the connection itself**, for example:

- `FOLLOWS.since`: since what date the follow started.
- `WORKS_AT.position`: a person's role **at this company**.
- `TRANSFERRED.amount`: the amount **in this transfer**.
- `DEPENDS_ON.reason`: why component A depends on component B.

If the same person works for multiple companies, `position` can differ across each `WORKS_AT` relationship; attaching the job title directly to the `Person` node would lose that context.

### 7.1. Reading Properties from a Relationship

```cypher
MATCH (an:Person {personId: 'P001'})-[r:WORKS_AT]->(c:Company)
RETURN c.name AS company,
       r.position AS position,
       r.since AS startDate,
       properties(r) AS allRelationshipProperties;
```

`r` is the variable representing the relationship. `r.position` reads the relationship's own property, while `properties(r)` returns a map of its existing properties.

### 7.2. Adding, Updating, and Removing Properties

```cypher
MATCH (:Person {personId: 'P001'})-[r:WORKS_AT]->
      (:Company {companyId: 'C001'})
SET r.position = 'Senior Developer',
    r.updatedAt = datetime()
RETURN properties(r) AS properties;
```

Removing **one property** does not delete the relationship:

```cypher
MATCH (:Person {personId: 'P001'})-[r:WORKS_AT]->
      (:Company {companyId: 'C001'})
REMOVE r.updatedAt
RETURN keys(r) AS remainingPropertyKeys;
```

Just like on nodes, relationship properties do not store `null` as a regular value: `SET r.position = null` removes that property. `SET r += {position: 'Lead'}` updates/adds the keys in the map; `SET r = {...}` replaces the entire property set and should be used with caution.

### 7.3. Deleting a Relationship

```cypher
MATCH (an:Person {personId: 'P001'})-[r:FOLLOWS]->
      (binh:Person {personId: 'P002'})
DELETE r;
```

`DELETE r` deletes the **matched relationship** without deleting the two nodes An and Bình. This mutates data; if you want to keep using the original sample dataset in later sections, skip this command or recreate the relationship. Deleting a node that still has relationships requires handling its connected edges; `DETACH DELETE` deletes the node **and** all relationships attached to it.

## 8. Creating Relationships Properly: CREATE, MATCH, and MERGE

### 8.1. Do Not Create Extra Nodes When You Only Need to Add an Edge

When both nodes already exist, the standard approach is to **MATCH both nodes first**, then `CREATE` the relationship between them:

```cypher
MATCH (a:Person {personId: 'P001'})
MATCH (b:Person {personId: 'P002'})
CREATE (a)-[r:COLLABORATES_WITH {since: date()}]->(b)
RETURN a.fullName, type(r), b.fullName;
```

In this statement, `a` and `b` are bound to two existing nodes. If either node is not found, the query creates no edge. If run again, `CREATE` will create another `COLLABORATES_WITH` relationship between the same two endpoints.

### 8.2. MERGE to Find or Create a Connection

When business rules expect **at most one connection of the same type and direction between two nodes**, you can write:

```cypher
MATCH (a:Person {personId: $fromId})
MATCH (b:Person {personId: $toId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.since = date()
RETURN a.personId AS fromId,
       b.personId AS toId,
       r.since AS since;
```

The parameters `$fromId` and `$toId` come from a Java Driver, Spring Data Neo4j, or Cypher client. **Matching both nodes first** lets `MERGE` focus on the link to be created, avoiding patterns that accidentally create duplicate nodes when identifiers are unconstrained.

A few important points:

- `MERGE` matches the **direction** and **type** of the relationship. `(a)-[:FOLLOWS]->(b)` is not `(b)-[:FOLLOWS]->(a)`.
- `ON CREATE SET` sets properties only when creating a new edge; it does not overwrite the follow date on an existing edge.
- If the data already has **multiple relationships matching the pattern**, `MERGE` can match multiple results; it does not automatically merge or delete duplicate edges.
- Using `MERGE` does not replace concurrency-safe deduplication design when multiple transactions write simultaneously. You still need key conventions, available constraints, and proper transaction handling.
- `WHERE a <> b` in the example enforces the rule **cannot follow oneself**. Neo4j still allows self-loops without this check.

### 8.3. Are Multiple Edges of the Same Type Always a Bug?

Not necessarily. Neo4j allows:

```text
(:Person {id: 'P001'})
      |-- [:VISITED {on: 2025-03-01}] --> (:Place {id: 'L001'})
      |-- [:VISITED {on: 2025-04-15}] --> (:Place {id: 'L001'})
```

The two `VISITED` edges represent two different visits. By contrast, two identical `FOLLOWS` edges between the same people in the same direction are usually a duplicate-ingestion bug. When an action has its own identity, multiple fields, and its own lifecycle, consider an **event node** model such as `:Visit` connected to `Person` and `Place` for better management.

## 9. Choosing Relationship Models for Real-World Problems

### 9.1. Ordering System

```text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(:Product)
```

`PLACED` goes from customer to order because the buyer **places** the order. `CONTAINS` goes from order to product because the order **contains** the product. Reading the chain of relationships from left to right immediately reveals the business domain.

If an order contains multiple products and needs `quantity`, consider putting the quantity on the `CONTAINS` relationship. However, if there are multiple line items of the same product with different prices/promotions, a separate `:OrderLine` node can represent that more accurately.

### 9.2. Service Dependency Graph

```text
(:Service {name: 'payment-api'})
            |
            | [:DEPENDS_ON]
            v
(:Service {name: 'database'})
```

From `payment-api`, the pattern `-[:DEPENDS_ON]->` finds the components that this service depends on. From `database`, the pattern `<-[:DEPENDS_ON]-` finds the services that depend on `database`. Direction must be consistent because it directly impacts incident-analysis and blast-radius queries.

### 9.3. Learning Graph

```text
(:Lesson {code: 'L01'})
            |
            | [:PREREQUISITE_OF]
            v
(:Lesson {code: 'L02'})
```

Here, L01 is a prerequisite of L02. If the system chooses the name `REQUIRES`, the appropriate direction is `(L02)-[:REQUIRES]->(L01)`. Both express the same prerequisite order, but **type names and directions must remain consistent** across all data and queries.

## 10. Directed Relationships and Path Queries

When moving to path analysis, the direction of each edge affects how the graph can be traversed.

Example dependency chain:

```text
(:Service {name: 'A'}) -[:DEPENDS_ON]->
(:Service {name: 'B'}) -[:DEPENDS_ON]->
(:Service {name: 'C'})
```

To find a dependency path from A to C following the **dependency direction**, use a directed path pattern:

```cypher
MATCH p = (:Service {name: 'A'})-[:DEPENDS_ON*1..3]->
          (:Service {name: 'C'})
RETURN p;
```

The variable-length pattern `*1..3` is traditional Cypher syntax, specifying **one to three** directed `DEPENDS_ON` relationships; newer Neo4j/Cypher versions also offer quantified path patterns to describe similar paths. Replacing `->` with an undirected pattern allows traversal in both directions, changing the meaning of "A depends on C".

To optimize queries, start from nodes with clear identifiers, specify exact relationship types and directions, and inspect `EXPLAIN` or `PROFILE`. Traversing without type or direction constraints can expand the number of edges examined, especially on high-degree nodes.

## 11. Data Quality Control and Application Integration

### 11.1. What Should You Check When Ingesting Data?

| Check Question | Why Is It Necessary? |
| --- | --- |
| Do the start and end nodes exist? | Prevents linking to unidentified entities |
| Does the direction match the type name? | Prevents inverting business semantics |
| Does the type follow naming conventions? | `WORKS_AT` differs from `works_at`; type-filtered queries will not match |
| Are parallel edges allowed? | Distinguishes state relationships from repeated event occurrences |
| Does a property belong on a node or on the relationship? | Preserves context when a node participates in multiple links |
| Should relationship cardinality be validated? | An employee may hold multiple roles/companies depending on the model; a type does not automatically enforce edge count |

Neo4j provides indexes and constraints for appropriate elements, but **relationship types do not automatically define cardinality** such as "each employee may have only one active `WORKS_AT` relationship". Rules like that must be designed and enforced via the data model, write queries, transactions, and/or application checks.

### 11.2. Java Driver and Spring Data Neo4j

When a Java application creates a link between two entities, pass business identifiers and property values using **parameters**:

```cypher
MATCH (person:Person {personId: $personId})
MATCH (company:Company {companyId: $companyId})
MERGE (person)-[r:WORKS_AT]->(company)
ON CREATE SET r.since = date($startDate)
RETURN type(r) AS type,
       person.personId AS fromPersonId,
       company.companyId AS toCompanyId;
```

The client supplies parameters such as `personId`, `companyId`, and `startDate`; never concatenate raw input into Cypher strings. In **Spring Data Neo4j**, when mapping relationships between entities, declare the type and direction matching the stored data; declaring the wrong direction can cause mapped queries not to return the expected relationships.

### 11.3. What Role Do Indexes and Constraints Play?

It is generally good practice to create uniqueness constraints on endpoint node keys such as `Person.personId` and `Company.companyId`, then use those keys to locate nodes before adding edges. Appropriate indexes help node-lookup queries by property run more efficiently. For cases that frequently filter by a relationship property such as `WORKS_AT.since`, consider the relationship index types supported by your Neo4j version. Avoid creating indexes by guesswork; inspect actual query execution plans.

## 12. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Assuming `(a)-[:FOLLOWS]->(b)` is equivalent to `(b)-[:FOLLOWS]->(a)` | Wrong inference about who follows whom | Choose the right direction and query with the matching arrow |
| Thinking `(a)-[r]-(b)` creates an undirected relationship | Misunderstands stored data | Remember this is only a **direction-agnostic query pattern** |
| Using `RELATED_TO` as the type for every link | Loses semantics and makes query filtering difficult | Name types to express the specific action/relationship |
| Assuming one relationship can have multiple types | Invalid property graph structure | Use one type per edge; create another edge when a genuinely distinct link exists |
| Repeating `CREATE` when only one link is needed | Produces duplicate edges | Use `MATCH` followed by `MERGE` appropriately, combined with concurrency controls |
| Placing a link's property on one of the nodes | Loses context when the node connects to multiple entities | Move the property to the relationship or introduce an intermediate node |
| Renaming a type using `SET r:NEW_TYPE` | Invalid syntax/update model | Create a relationship with the new type and remove the old one via a data migration step |
| Deleting a node with relationships without considering the impact | Deletion errors or lost links when using `DETACH DELETE` | Identify connected edges and business rules before deleting |
| Confusing diagram layout position with edge direction | Reading start/end backward | Verify with `startNode(r)`, `endNode(r)`, and type |

## 13. Self-Check Exercises

**Exercise 1 – Reading a relationship.** Given `(a:User)-[:SUBSCRIBES_TO]->(channel:Channel)`. Which node is the start node and which is the end node? To find subscribers of a specific channel, which query pattern is appropriate?

<details>
<summary>Suggested Answer</summary>

`a` is the start node and `channel` is the end node. Find subscribers by traversing incoming edges into the channel:

```cypher
MATCH (u:User)-[:SUBSCRIBES_TO]->(c:Channel {channelId: $channelId})
RETURN u;
```

</details>

**Exercise 2 – Distinguishing direction.** For two nodes An and Bình, the database only contains `(An)-[:FOLLOWS]->(Bình)`. Does the query `(Bình)-[:FOLLOWS]->(An)` match? Which pattern matches this edge starting from Bình?

<details>
<summary>Suggested Answer</summary>

It does not match in the reverse direction. You can query `(binh)<-[:FOLLOWS]-(an)` or `(binh)-[:FOLLOWS]-(an)` if you only need to detect a connection regardless of direction.

</details>

**Exercise 3 – Inspecting type and endpoints.** Write a query that returns `type`, the start node ID, and the end node ID for every `WORKS_AT` edge.

<details>
<summary>Suggested Answer</summary>

```cypher
MATCH ()-[r:WORKS_AT]->()
RETURN type(r) AS relationshipType,
       startNode(r).personId AS fromPersonId,
       endNode(r).companyId AS toCompanyId;
```

The column naming assumes the direction and two node types follow the `Person -[:WORKS_AT]-> Company` model.

</details>

**Exercise 4 – Design.** The relationship `(:Person)-[:BOOKED]->(:Flight)` needs to store the booking date and ticket class. Where should those properties be placed? If a person can book multiple tickets on the same flight across different transactions, which model is appropriate?

<details>
<summary>Suggested Answer</summary>

Booking details can live on the `BOOKED` relationship when each link represents a simple single booking. If each transaction has its own ID, status, payment, passengers, and lifecycle, consider a `Booking` node, for example `(person)-[:MADE]->(booking)-[:FOR_FLIGHT]->(flight)`.

</details>

## 14. Summary

- Every relationship in Neo4j has a **stored direction** from **start node** to **end node**; both endpoints can be the same node in the case of a self-loop.
- Each relationship has **exactly one type** and can carry properties describing the connection itself.
- `->` and `<-` constrain traversal direction; `-[]-` matches relationships in both directions but **does not change the stored direction**.
- `type(r)`, `startNode(r)`, `endNode(r)`, and `properties(r)` allow inspecting type, endpoints, and properties.
- Operations `CREATE`, `MATCH`, `MERGE`, `SET`, `REMOVE`, and `DELETE` manage relationships; clearly distinguish creating a new edge from finding or creating an edge by pattern.
- Type names and directions must consistently express business semantics. This is the prerequisite for modeling relationships, querying paths, ingesting data, tuning queries, and mapping graphs into Java/Spring Data Neo4j applications.
