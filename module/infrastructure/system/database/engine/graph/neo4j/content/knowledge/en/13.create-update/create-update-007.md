# DELETE and DETACH DELETE Both Affect Relationships

In Neo4j, data is stored as a **property graph**: nodes represent entities, relationships represent links between two nodes, and both nodes and relationships can carry properties. Because relationships directly connect two nodes, deleting a node always raises the question: **what happens to the relationships attached to that node?**

Cypher provides two common deletion clauses:

- **DELETE** directly deletes the specified node or relationship. To delete a node, that node must have **no remaining relationships**; if any remain, Neo4j rejects the operation.
- **DETACH DELETE** deletes the specified node **along with all relationships directly connected to it**, regardless of direction or relationship type.

Core point: **both commands can affect relationships**, but their scope and preconditions differ. DELETE lets you target specific relationships to delete individually; DETACH DELETE lets you delete a connected node by automatically deleting its adjacent relationships.

## 1. Relationships Have Their Own Lifecycle

Consider the graph:

~~~text
(An) --[:FOLLOWS]--> (Bình)
(An) --[:AUTHORED]--> (Article)
(Bình) --[:LIKES]--> (Article)
~~~

These three relationships are three distinct relationship records in the graph. They are not merely ID fields embedded inside nodes. A relationship can carry properties, for example:

~~~cypher
(an)-[:FOLLOWS {since: 2024, source: 'community'}]->(binh)
~~~

A relationship in Neo4j must have two existing endpoints. Therefore, Neo4j does not permit deleting node An while leaving **FOLLOWS** or **AUTHORED** relationships pointing to a node that no longer exists.

Distinguish three actions:

1. Deleting the **FOLLOWS relationship**: An and Bình still exist; the follow link disappears.
2. Deleting **node An with DELETE**: succeeds only when An has no remaining relationships.
3. Deleting **node An with DETACH DELETE**: An, FOLLOWS, and AUTHORED disappear; Bình, Article, and LIKES between them remain.

DETACH DELETE processes only **relationships directly attached to the deleted node**. It does not automatically delete neighboring nodes, other relationships of those neighbors, or entire indirectly connected paths.

## 2. DELETE: Precisely Deleting Specified Elements

### 2.1. Deleting a Relationship While Keeping the Nodes

~~~cypher
MATCH (a:Person {personId: 'an'})-[r:FOLLOWS]->(b:Person {personId: 'binh'})
DELETE r;
~~~

In this example, **r** is the relationship found by MATCH; DELETE r deletes that relationship. Both **a** and **b** remain intact, including their labels, properties, and other relationships.

If the MATCH pattern matches multiple FOLLOWS relationships between the specified nodes, all matched relationships can be deleted. Therefore, verify the MATCH criteria when you only intend to delete one specific link. Relationship properties, such as **since**, can be used for further filtering if needed.

### 2.2. Deleting a Node with No Relationships

~~~cypher
MATCH (p:Person {personId: 'khong-lien-ket'})
DELETE p;
~~~

This command is valid if node **p** has no relationships at the time of deletion. The node and its properties disappear. Neo4j also updates the index structures associated with the node according to database mechanics.

### 2.3. Deleting a Node That Still Has Relationships: Error

~~~cypher
MATCH (p:Person {personId: 'an'})
DELETE p;
~~~

If An still has FOLLOWS, AUTHORED, or any other relationship (including incoming relationships), Neo4j raises an error because the node is still connected. There is no default behavior that silently deletes relationships just because the statement uses DELETE p.

This rule applies to **outgoing**, **incoming**, and **self-loop** relationships from a node to itself. Deleting some relationships while leaving even one remaining is still not enough for DELETE node to succeed.

## 3. DETACH DELETE: Deleting a Node and All Adjacent Relationships

~~~cypher
MATCH (p:Person {personId: 'an'})
DETACH DELETE p;
~~~

Assuming the graph still has the original three relationships, the command above produces:

~~~text
Before:
(An) --[:FOLLOWS]--> (Bình)
(An) --[:AUTHORED]--> (Article)
(Bình) --[:LIKES]--> (Article)

After DETACH DELETE An:
(Bình) --[:LIKES]--> (Article)
~~~

What gets deleted are **node An**, **FOLLOWS**, and **AUTHORED**. What remains are **node Bình**, **node Article**, and **LIKES**. If a relationship ran from Bình **into** An, or An had a self-loop relationship, it would also be deleted because it is adjacent to An.

This syntax does not require naming the relationships' types or directions beforehand. That convenience is also why caution is required: a highly connected node can cause DETACH DELETE to remove a large volume of relationship data.

## 4. Behavior Comparison Table

| Scenario | DELETE | DETACH DELETE |
|---|---|---|
| Delete a node with no relationships | Node deleted successfully | Node deleted successfully |
| Delete a node with relationships | Raises error; node not deleted | Deletes node and adjacent relationships |
| Incoming relationship to node | Blocks DELETE node | Deleted along with node |
| Outgoing relationship from node | Blocks DELETE node | Deleted along with node |
| Self-loop relationship on node | Blocks DELETE node | Deleted along with node |
| Neighbor nodes | Not deleted when only DELETEing relationship | Not deleted when DETACH DELETEing target node |
| Relationships between neighbor nodes | Unaffected unless explicitly selected for deletion | Unaffected unless adjacent to target node |
| Typical purpose | Delete a specific link or an already isolated node | Delete an entity together with all its direct links |

**Note:** The DELETE column for a connected node refers to **DELETE node**. If the variable represents a relationship, such as DELETE r, the command can still delete that relationship directly without deleting either endpoint node.

## 5. Hands-On with a Small Graph

The queries below should be run in a **test database**. The labels **DeleteLabPerson** and **DeleteLabArticle** are isolated so examples do not mix with production data. Run the steps sequentially to observe the differences.

### Step 1. Create Illustrative Data

~~~cypher
CREATE
  (an:DeleteLabPerson {personId: 'an', name: 'An'}),
  (binh:DeleteLabPerson {personId: 'binh', name: 'Bình'}),
  (bai:DeleteLabArticle {articleId: 'bai-1', title: 'Cypher Fundamentals'})
CREATE
  (an)-[:FOLLOWS {since: 2024}]->(binh),
  (an)-[:AUTHORED]->(bai),
  (binh)-[:LIKES]->(bai);
~~~

The newly created data has three nodes and three relationships. To view the connections:

~~~cypher
MATCH (n)-[r]->(m)
WHERE n:DeleteLabPerson OR n:DeleteLabArticle
RETURN labels(n) AS sourceLabels,
       coalesce(n.personId, n.articleId) AS sourceId,
       type(r) AS relationship,
       coalesce(m.personId, m.articleId) AS targetId;
~~~

Run the data creation step once in an empty test database or clean up old sample data before recreating, avoiding duplicate nodes since CREATE always creates new records.

### Step 2. Try DELETE on a Connected Node

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
DELETE an;
~~~

**Expected outcome:** the statement raises an error because An participates in FOLLOWS and AUTHORED. The graph's nodes and relationships remain intact; this delete cannot succeed.

### Step 3. Intentionally DELETE One Relationship

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
      -[r:FOLLOWS]->
      (binh:DeleteLabPerson {personId: 'binh'})
DELETE r;
~~~

Now **FOLLOWS** disappears while An and Bình still exist; An remains connected to Article via **AUTHORED**. Because An is not yet completely detached from the graph, **DELETE an** still cannot succeed.

Check which relationships remain attached to An:

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
OPTIONAL MATCH (an)-[r]-()
RETURN an.personId AS person,
       count(DISTINCT r) AS remainingRelationships,
       collect(DISTINCT type(r)) AS relationshipTypes;
~~~

After Step 3, **remainingRelationships = 1**, with relationship type **AUTHORED**. The pattern **-[r]-** ignores direction, counting both incoming and outgoing relationships.

### Step 4. DETACH DELETE a Still-Connected Node

~~~cypher
MATCH (an:DeleteLabPerson {personId: 'an'})
DETACH DELETE an;
~~~

Neo4j deletes An and the remaining AUTHORED relationship. Bình, Article, and their LIKES relationship remain:

~~~cypher
MATCH (binh:DeleteLabPerson {personId: 'binh'})
      -[r:LIKES]->
      (bai:DeleteLabArticle {articleId: 'bai-1'})
RETURN binh.name AS person,
       type(r) AS relationship,
       bai.title AS article;
~~~

The result has one row corresponding to **Bình — LIKES — Cypher Fundamentals**. If you ran DETACH DELETE An **right after Step 1**, the command would delete **both FOLLOWS and AUTHORED** in the same operation.

### Step 5. Clean Up Remaining Sample Data

Apply only in the test database after finishing the lab:

~~~cypher
MATCH (n)
WHERE (n:DeleteLabPerson AND n.personId IN ['an', 'binh'])
   OR (n:DeleteLabArticle AND n.articleId = 'bai-1')
DETACH DELETE n;
~~~

This query targets the sample IDs. In real systems, use distinct identifying criteria and inspect matched records before deleting.

## 6. Choosing the Right Command for Business Logic

### 6.1. User Unfollows Another User

Requirement: keep both accounts, but remove the follow relationship.

~~~cypher
MATCH (u:User {id: $followerId})-[r:FOLLOWS]->(v:User {id: $followeeId})
DELETE r;
~~~

Choose **DELETE r** because only the FOLLOWS relationship needs removal; deleting a User with DETACH DELETE would destroy all other relationships tied to the account.

### 6.2. Completely Deleting an Entity Cleared for Removal

Requirement: delete a draft node and every direct link pointing to or from it.

~~~cypher
MATCH (d:Draft {id: $draftId})
DETACH DELETE d;
~~~

Choose **DETACH DELETE d** when business rules dictate that all links on Draft must be removed along with Draft. Verify whether any relationship carries historical, auditing, or shared meaning that the system needs to preserve through another model.

### 6.3. Deleting a Node Only After Handling Each Relationship Type

Some business cases require transferring ownership, logging events, or selectively deleting relationships before deleting a node. In that case, handle the necessary relationships per business rules, confirm the node has no remaining relationships, and only then **DELETE node**.

For example, deleting all attached relationships in a separate command and then deleting the node:

~~~cypher
MATCH (d:Draft {id: $draftId})-[r]-()
DELETE r;
~~~

~~~cypher
MATCH (d:Draft {id: $draftId})
DELETE d;
~~~

This example only illustrates the step-by-step difference. If executed across **two separate transactions**, a new relationship could appear between the two commands and cause DELETE d to fail. When the requirement is to delete a node together with all direct links, DETACH DELETE usually expresses the intent more clearly and handles the operation in a single statement.

## 7. Checking Deletion Scope Before Running

In applications, the most dangerous bug usually lies not in the DELETE keyword itself, but in a **MATCH** clause selecting the wrong nodes or too many nodes.

### 7.1. Verify How Many Nodes and Relationships Will Be Affected

~~~cypher
MATCH (u:User {id: $userId})
OPTIONAL MATCH (u)-[r]-()
RETURN count(DISTINCT u) AS matchedNodes,
       count(DISTINCT r) AS adjacentRelationships,
       collect(DISTINCT type(r)) AS relationshipTypes;
~~~

- **matchedNodes** should match the expected number of entities to delete, usually 1 when IDs are unique.
- **adjacentRelationships** estimates how many direct relationships DETACH DELETE will delete.
- **relationshipTypes** reveals which link types will be affected, including unexpected ones.

To inspect neighbor node details before deleting:

~~~cypher
MATCH (u:User {id: $userId})-[r]-(neighbor)
RETURN type(r) AS relationshipType,
       labels(neighbor) AS neighborLabels,
       properties(neighbor) AS neighborProperties;
~~~

For a node with no relationships, a mandatory MATCH with **-[r]-** returns 0 rows. Use **OPTIONAL MATCH** as in the counting query above so you still see that node.

### 7.2. Avoiding Unintended Mass Deletion

~~~cypher
MATCH (n)
DETACH DELETE n;
~~~

This statement means **delete every node and relationship in the queried graph**. It is appropriate only when the explicit goal is emptying the database and proper authorization is held. In normal business flows, always use labels and specific identifier filters.

If **MATCH** finds no nodes, the corresponding DELETE/DETACH DELETE statement deletes zero records. Conversely, if IDs are not constrained to be unique and MATCH returns multiple nodes, all matched nodes can be deleted.

### 7.3. Reading Query Plans and Considering System Load

~~~cypher
EXPLAIN
MATCH (u:User {id: $userId})
DETACH DELETE u;
~~~

**EXPLAIN** shows the execution plan without running the write command; this is the safer check before destructive operations. **PROFILE** executes the query to collect actual runtime metrics, so never use PROFILE to "preview" a delete command on real data.

At large scale, performance is affected by the number of matched nodes, the number of relationships adjacent to each node, and whether indexes/constraints support looking up nodes by ID. A very high-degree node can make DETACH DELETE far more expensive than deleting an isolated node.

If bulk deletion is needed, consider splitting into **batched transactions**, monitoring execution time and memory/lock pressure. For instance, on Neo4j versions supporting batched subquery syntax:

~~~cypher
MATCH (n:ArchivedEvent)
CALL (n) {
  DETACH DELETE n
} IN TRANSACTIONS OF 1000 ROWS;
~~~

Subquery variable-import syntax and **IN TRANSACTIONS** availability differ across Neo4j versions. Check your running version and the transaction mode of the Java Driver or execution tool before applying; certain explicit transaction modes do not support this batching syntax.

## 8. Common Misconceptions

**Misconception 1: DELETE node automatically deletes relationships like DETACH DELETE.** False. DELETE on a node with relationships fails; only DETACH DELETE also deletes adjacent relationships.

**Misconception 2: DETACH DELETE deletes all connected nodes.** False. It deletes the selected node and its direct relationships, not neighbor nodes. Any other relationship between two neighbors remains intact.

**Misconception 3: Deleting a relationship also deletes both endpoints.** False. DELETE r deletes only relationship r; the nodes at both ends are preserved.

**Misconception 4: You only need to delete outgoing relationships before DELETE node.** False. Incoming relationships and self-loops also cause DELETE node to fail.

**Misconception 5: Deleting a property and deleting a relationship are the same.** False. Removing a property, e.g., **REMOVE r.since**, does not delete relationship r; only DELETE r removes the link itself.

**Misconception 6: DETACH DELETE is equivalent to deleting a specific relationship type.** False. DETACH DELETE node deletes **every type of relationship** directly attached to that node; if you only want to remove **FOLLOWS**, MATCH and DELETE the FOLLOWS relationship.

## 9. Self-Check Questions

**Question 1.** Node A has three relationships: two outgoing and one incoming. What happens when you run DELETE A?

*Answer:* Neo4j refuses to delete A because A still has relationships, regardless of their direction.

**Question 2.** When running DETACH DELETE A, is a node B connected to A deleted? What about B's relationships to node C?

*Answer:* B is not deleted. The A–B relationship is deleted; the B–C relationship remains unless adjacent to another node also selected for deletion.

**Question 3.** You want to remove a follow relationship between two users while keeping both accounts. Which command should you use?

*Answer:* MATCH the specific follow relationship and DELETE the relationship variable, e.g., DELETE r.

**Question 4.** Why check count(DISTINCT r) with OPTIONAL MATCH (n)-[r]-() before running DETACH DELETE?

*Answer:* Because it shows how many direct relationships are affected, including incoming, outgoing, and self-loop links; DISTINCT avoids double-counting when a relationship can appear multiple times due to the query pattern.

## 10. Takeaways

**DELETE r** deletes one or more selected relationships while preserving endpoint nodes. **DELETE n** deletes a node only when it has no remaining relationships. **DETACH DELETE n** deletes a node together with **all of its direct relationships**, without automatically deleting neighbor nodes. Before deleting data, verify the MATCH scope, affected relationship types, and business data-retention requirements.
