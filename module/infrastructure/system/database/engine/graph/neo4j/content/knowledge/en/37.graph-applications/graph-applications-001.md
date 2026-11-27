# Social Networks: Connections, Mutual Friends, and Relationship Distance

A social network often has to answer seemingly simple questions: **Has An friended Bình yet?**, **How many mutual friends do An and Dũng have?**, **Who should be recommended for An to connect with?**, or **How many relationship hops apart are two people?** All of these questions rely on **connections between entities**, making them well suited for representation and querying with Neo4j's property graph.

This lesson belongs to the **Graph Applications** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to model nodes, relationships, and properties; leverage Cypher to find relationships and paths; create indexes/constraints, optimize queries, and integrate via the Java Driver or Spring Data Neo4j. In this lesson, we build a **small social network with deterministic results**, moving from the data model to querying, testing, performance, and privacy protection.

> **Scope:** Examples use Neo4j 5.x and common Cypher 5 syntax. The examples focus on accepted friendships (`FRIEND`); friend request sending, user blocking, and visibility permissions are discussed as extensions. When using Neo4j with a newer Cypher version, verify the supported version and shortest-path syntax.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose the appropriate model between a **directed `FOLLOWS` relationship** and a **bidirectional `FRIEND` friendship**.
2. Design user nodes, relationships, and stable business keys; explain why uniqueness constraints are needed.
3. Write Cypher to find direct friends, check whether two people are connected, and **count mutual friends**.
4. Build a **two-hop friend recommendation** query that excludes the viewer themselves, existing friends, and blocked accounts.
5. Find the **shortest path by edge count** and distinguish graph distance from real-world closeness scores.
6. Use `EXPLAIN`/`PROFILE` and bound traversal scope to avoid query explosion on networks with many hubs.
7. Invoke queries via Java Driver/Spring Data Neo4j and write tests for correctness, privacy, and edge cases.

## 2. Why Are Social Network Relationships a Good Fit for Graphs?

In a relational model, you can store a `users` table and a `friendships(user_a_id, user_b_id)` table, then use JOINs to find mutual friends. That approach is completely valid, especially for simple tasks. A graph model becomes natural when questions focus on **variable-length paths** or multiple intertwined relationship types:

- User A is friends with B; B is friends with D.
- A and D are not direct friends, but can be **introduced through B**.
- A person may follow an author, belong to the same group, and work at the same company at the same time.
- Visibility permissions may depend on relationships and account status.

In Neo4j, we represent **entities** as nodes, **connections** as relationships, and **attributes** on both.

~~~mermaid
flowchart LR
    A["SocialUser<br/>A · An"]
    B["SocialUser<br/>B · Bình"]
    C["SocialUser<br/>C · Chi"]
    D["SocialUser<br/>D · Dũng"]
    A ---|FRIEND| B
    A ---|FRIEND| C
    B ---|FRIEND| C
    B ---|FRIEND| D
    C ---|FRIEND| D
~~~

The diagram represents friendship as **directionless at the business layer**. Neo4j still stores every relationship with a physical direction; when querying friendships, we can write an **undirected pattern** such as `(a)-[:FRIEND]-(b)`.

**The advantage of a graph does not replace good query design.** A two-hop expansion query on accounts with millions of neighbors can still be very expensive. We need a clear model, appropriate indexes, bounded traversal scope, and load testing.

## 3. Decide First: `FOLLOWS` or `FRIEND`?

This is the most important semantic decision in a social network:

| Relationship | Business Direction | Example | Typical Cypher |
|---|---|---|---|
| `FOLLOWS` | **Directed** | An follows Bình, but Bình does not necessarily follow back | `(an)-[:FOLLOWS]->(binh)` |
| `FRIEND` | **Bidirectional** at the business level | An and Bình have accepted a friend connection | `(an)-[:FRIEND]-(binh)` |
| `FRIEND_REQUEST` | Directed, stateful | An sends a friend request to Bình | `(an)-[:FRIEND_REQUEST]->(binh)` |
| `BLOCKED` | Usually directed | An blocks Bình | `(an)-[:BLOCKED]->(binh)` |
| `MEMBER_OF` | Directed per model | An is a member of group G | `(an)-[:MEMBER_OF]->(g)` |

### 3.1. Two Ways to Store Friendships

**Approach A — One relationship per pair of friends (used in this lesson):**

~~~cypher
// Store only one edge per pair.
(a:SocialUser)-[:FRIEND]->(b:SocialUser)
~~~

- The application treats friendship as bidirectional, so it queries using `-[:FRIEND]-`.
- Choose a **canonical** direction, such as smaller `userId` → larger `userId`.
- No need to create two symmetric edges.
- When reading `(a)-[:FRIEND]-(b)`, Cypher matches the edge in either direction.

**Approach B — Store two symmetric edges:**

~~~cypher
(a)-[:FRIEND]->(b)
(b)-[:FRIEND]->(a)
~~~

This approach may fit certain requirements, but you must strictly manage symmetry and prevent duplicates; otherwise, friend/relationship counts can be **double-counted**. For typical bidirectional friendships, a single edge is usually simpler.

> **Do not use `-[:FRIEND]->` to find all friends** if data is stored with Approach A. The arrow direction is only a storage convention; queries must use `-[:FRIEND]-` when the business domain treats the relationship as symmetric.

### 3.2. Do Not Mix "Following" with "Already Friends"

Two people following the same artist **does not mean they are friends**. Two people following each other is not necessarily equivalent to an accepted `FRIEND` relationship either. Name relationships after the **business event** and do not substitute meaning with a convenient path comparison.

## 4. The Property Graph Model Used in This Lesson

### 4.1. Nodes and Properties

We use the `:SocialUser` label with:

| Property | Example Type | Purpose |
|---|---|---|
| `userId` | String | Stable, unique business key |
| `displayName` | String | Display name |
| `isActive` | Boolean | Account status for business filtering |

In a real system, there may also be `createdAt`, privacy mode, account lock status, contact address, or profile details. **Do not include sensitive data in query results when unnecessary**.

The `:FRIEND` relationship can have:

| Property | Meaning |
|---|---|
| `pairKey` | Identifier key for the user pair, used to prevent duplicate edges |
| `since` | Timestamp when the relationship was accepted |
| `source` | Connection source if the business requires auditing |

In the sample section, `pairKey` is used to illustrate one way of protecting relationship uniqueness. Do not use internal IDs or `elementId()` instead of `userId` as a durable key.

### 4.2. Constraints Before Loading Data

Run on a **dedicated test database**:

~~~cypher
CREATE CONSTRAINT social_user_id_unique IF NOT EXISTS
FOR (u:SocialUser)
REQUIRE u.userId IS UNIQUE;
~~~

On Neo4j versions supporting relationship property uniqueness, you can protect `pairKey`:

~~~cypher
CREATE CONSTRAINT social_friend_pair_unique IF NOT EXISTS
FOR ()-[r:FRIEND]-()
REQUIRE r.pairKey IS UNIQUE;
~~~

The node constraint speeds up finding users by `userId` and prevents two nodes with the same key. The constraint on `pairKey` prevents two `FRIEND` edges from having the **same pair key** when all write flows set that property consistently.

**Limitation:** property uniqueness does not automatically require the property to exist. If a write flow creates `:FRIEND` **without `pairKey`**, a plain uniqueness constraint will not detect that pair as a duplicate. You need validation, centralized write rules, and, when supported by your edition, appropriate existence/key constraints.

## 5. Creating the Sample Graph: 7 People, 9 Friendships

User symbols:

| userId | displayName |
|---|---|
| A | An |
| B | Bình |
| C | Chi |
| D | Dũng |
| E | Em |
| F | Phúc |
| G | Giang |

### 5.1. Load Nodes

~~~cypher
UNWIND [
  {id: 'A', name: 'An'},
  {id: 'B', name: 'Bình'},
  {id: 'C', name: 'Chi'},
  {id: 'D', name: 'Dũng'},
  {id: 'E', name: 'Em'},
  {id: 'F', name: 'Phúc'},
  {id: 'G', name: 'Giang'}
] AS row
MERGE (u:SocialUser {userId: row.id})
SET u.displayName = row.name,
    u.isActive = true;
~~~

### 5.2. Load Relationships

The sample dataset stores one `FRIEND` edge per pair, ordered `left < right` (lexicographical string ID comparison):

~~~cypher
UNWIND [
  {left: 'A', right: 'B'},
  {left: 'A', right: 'C'},
  {left: 'B', right: 'C'},
  {left: 'B', right: 'D'},
  {left: 'C', right: 'D'},
  {left: 'C', right: 'E'},
  {left: 'D', right: 'F'},
  {left: 'E', right: 'F'},
  {left: 'F', right: 'G'}
] AS pair
MATCH (a:SocialUser {userId: pair.left})
MATCH (b:SocialUser {userId: pair.right})
MERGE (a)-[r:FRIEND {pairKey: pair.left + '|' + pair.right}]->(b);
~~~

In this dataset, the pairs are:

~~~text
A—B, A—C, B—C, B—D, C—D, C—E, D—F, E—F, F—G
~~~

~~~mermaid
flowchart LR
    A((A)) --- B((B))
    A --- C((C))
    B --- C
    B --- D((D))
    C --- D
    C --- E((E))
    D --- F((F))
    E --- F
    F --- G((G))
~~~

### 5.3. Verify the Fixture

~~~cypher
MATCH (u:SocialUser)
RETURN count(u) AS users;
// Expected: 7 on the sample database.
~~~

~~~cypher
MATCH (:SocialUser)-[r:FRIEND]->(:SocialUser)
RETURN count(r) AS friendships;
// Expected: 9 on the sample database.
~~~

~~~cypher
MATCH (u:SocialUser)-[:FRIEND]-(friend:SocialUser)
RETURN u.userId AS userId,
       count(DISTINCT friend) AS degree
ORDER BY userId;
~~~

Expected direct friend counts (`degree`):

| User | A | B | C | D | E | F | G |
|---|---:|---:|---:|---:|---:|---:|---:|
| Friends | 2 | 3 | 4 | 3 | 2 | 3 | 1 |

The sum of degrees equals `18 = 2 × 9` because each undirected edge is counted as a friend for **both endpoints**. This is a useful fixture check, but **do not** use this total as a substitute for verifying individual ID pairs when business requirements are strict.

**Run in order:** create constraints → load nodes → load relationships → verify. The `MERGE` statements are idempotent on a consistent sample dataset, but they do not automatically resolve pre-existing duplicate edges or data modified outside this setup.

## 6. Finding Direct Friends — One-Hop Traversal

**Question:** Who is An (`A`) friends with?

~~~cypher
MATCH (me:SocialUser {userId: 'A'})-[:FRIEND]-
      (friend:SocialUser)
RETURN DISTINCT friend.userId AS friendId,
       friend.displayName AS name
ORDER BY friendId;
~~~

Result:

| friendId | name |
|---|---|
| B | Bình |
| C | Chi |

The `-[:FRIEND]-` pattern does not specify a direction. If you write `(me)-[:FRIEND]->(friend)`, the result depends on the **physical direction** when the data was created; with single-edge storage ordered by key, a directed query can miss friends.

### 6.1. Parameterized Queries

In the Java Driver or Spring Data Neo4j, use parameters:

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (friend:SocialUser)
WHERE friend.isActive = true
RETURN DISTINCT friend.userId AS friendId,
       friend.displayName AS name
ORDER BY friendId;
~~~

Never concatenate a `userId` from an HTTP request directly into a Cypher string. Beyond the risk of Cypher injection, using parameters provides a clean query template that is easy to measure and test.

### 6.2. Checking Whether Two People Are Already Friends

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
RETURN EXISTS {
    MATCH (a)-[:FRIEND]-(b)
} AS areFriends;
~~~

With the sample data:

- `A` and `B` → `true`.
- `A` and `D` → `false`.

**Edge case:** if either ID does not exist, the two `MATCH` clauses produce no rows, so the query **does not return a record containing `false`**. The application layer must distinguish between **user does not exist** and **both users exist but are not friends**, such as checking accounts first or using a query with `OPTIONAL MATCH` and clear return semantics.

## 7. Mutual Friends — Intersection of Two Neighbor Sets

In set terms, let `N(u)` be the set of users having a `FRIEND` edge with `u`:

~~~text
N(A) = {B, C}
N(D) = {B, C, F}

Mutual friends of A and D = N(A) ∩ N(D) = {B, C}
~~~

Cypher can express this directly using two edges:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
WHERE a <> b
MATCH (a)-[:FRIEND]-(common:SocialUser)-[:FRIEND]-(b)
RETURN DISTINCT common.userId AS commonFriendId,
       common.displayName AS name
ORDER BY commonFriendId;
~~~

With `userA = 'A'`, `userB = 'D'`:

| commonFriendId | name |
|---|---|
| B | Bình |
| C | Chi |

**How does Cypher execute this?**

1. Look up nodes `a` and `b` by their unique business IDs.
2. Expand from `a` across one `FRIEND` edge to `common`.
3. Keep only `common` nodes that have another `FRIEND` edge connecting to `b`.
4. Return `DISTINCT` because dirty data may contain multiple edges for the same pair, causing duplicate rows.

`a <> b` prevents "comparing a person to themselves" from being misinterpreted as a mutual-friends check. With one friendship edge per pair, `common` cannot be `a` or `b` when the data has no self-loops; however, in systems where anomalous data is possible, you should still test self-loops and duplicate edges.

### 7.1. Counting Mutual Friends, Even When There Are None

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
WHERE a <> b
OPTIONAL MATCH (a)-[:FRIEND]-(common:SocialUser)-[:FRIEND]-(b)
RETURN count(DISTINCT common) AS mutualCount;
~~~

With `A` and `D`, the result is `mutualCount = 2`. If two people **exist and are distinct** but have no mutual friends, `OPTIONAL MATCH` combined with `count(DISTINCT common)` returns `0`. If either ID is missing, the initial `MATCH` produces no rows and the query **returns no record**.

### 7.2. "Mutual Friends" Is Not "Commonly Followed"

In a directed follow network:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
MATCH (a)-[:FOLLOWS]->(same:SocialUser)<-[:FOLLOWS]-(b)
RETURN DISTINCT same.userId AS bothFollow;
~~~

This query returns **accounts that both A and B follow**, which is different from accounts following both of them, and different from mutual friends via `FRIEND`. Always verify **edge direction and business semantics** before labeling a result as "mutual".

## 8. Friend Recommendations — People Two Hops Away

A simple recommendation heuristic is **friend-of-a-friend**: find people who are not yet directly friends with `me` but share many mutual friends. On the sample graph:

~~~text
A is already friends with B and C.

A → B → D    (mutual friend B)
A → C → D    (mutual friend C)
A → C → E    (mutual friend C)

Recommendations for A:
D has 2 mutual friends (B, C).
E has 1 mutual friend (C).
~~~

### 8.1. Basic Recommendation Query

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND candidate.isActive = true
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId,
       candidate.displayName AS name,
       mutualCount
ORDER BY mutualCount DESC, candidateId ASC
LIMIT 20;
~~~

With `userId = 'A'`:

| candidateId | name | mutualCount |
|---|---|---:|
| D | Dũng | 2 |
| E | Em | 1 |

**Why each condition is necessary:**

- `candidate <> me`: defensive condition so the viewer is not recommended to themselves. With one edge per pair, Cypher does not reuse the same relationship within a single `MATCH` path, so the loop `A → B → A` over the **same edge** does not actually occur; the condition remains useful if the model or query shape changes.
- `NOT EXISTS { MATCH (me)-[:FRIEND]-(candidate) }`: excludes people who are **already friends**.
- `count(DISTINCT bridge)`: counts **distinct intermediate people**, not paths that might be multiplied by duplicate relationships.
- `ORDER BY mutualCount DESC, candidateId ASC`: prioritizes more mutual friends while providing deterministic tie-breaking.
- `LIMIT 20`: caps the returned list, **not guaranteeing that the engine only inspects 20 candidates** before computing `mutualCount`.

### 8.2. Respecting Block Status

If there is a directed `BLOCKED` relationship, exclude candidates blocked by either side:

~~~cypher
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND candidate.isActive = true
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
  AND NOT EXISTS {
      MATCH (me)-[:BLOCKED]->(candidate)
  }
  AND NOT EXISTS {
      MATCH (candidate)-[:BLOCKED]->(me)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId,
       candidate.displayName AS name,
       mutualCount
ORDER BY mutualCount DESC, candidateId ASC
LIMIT $limit;
~~~

If the sample dataset has no `BLOCKED` edges, the result remains `D` then `E`. In production, you also need to check **pending requests, private accounts, age restrictions, organization scope, lock status, and permission to view mutual friends**. Do not rely solely on a single filter query to guarantee that all privacy policies have been enforced.

### 8.3. Multiple Ways to Score Recommendations

Counting mutual friends is **a heuristic**, not an absolute ground-truth metric:

| Score | Meaning | Pros / Cons |
|---|---|---|
| **Common neighbors** | `|N(a) ∩ N(b)|` | Easy to explain; favors users with many friends |
| **Jaccard similarity** | `|N(a) ∩ N(b)| / |N(a) ∪ N(b)|` | Normalizes by both users' network sizes |
| **Adamic–Adar** | Less-connected mutual friends receive higher weight | Reduces hub influence; more complex |
| **Graph embedding/ML** | Score from a machine learning model on the graph | Captures complex signals; requires pipeline and fairness/privacy evaluation |

For example, A has two friends B/C and D has three friends B/C/F, so `Jaccard(A,D) = 2 / 3`. E has two friends C/F, so `Jaccard(A,E) = 1 / 3`. The case where both neighbor sets are empty requires an explicit rule (such as returning 0 rather than dividing by 0).

If Graph Data Science (GDS) is available, certain link-prediction/similarity algorithms can support large-scale recommendations depending on edition and license. **Installing GDS is not required** to run the basic mutual-friend queries in this lesson.

## 9. Relationship Distance — Shortest Path

In a friendship graph, the **hop distance** between two people is the number of `FRIEND` edges on the **shortest path** connecting them.

Examples:

| Pair | Shortest Distance | A Valid Path |
|---|---:|---|
| A — B | 1 | A → B |
| A — D | 2 | A → B → D |
| A — E | 2 | A → C → E |
| A — F | 3 | A → C → E → F |
| A — G | 4 | A → C → E → F → G |

There may be **multiple shortest paths** of the same hop length. For instance, A to D has two paths of length 2: `A–B–D` and `A–C–D`. Do not hardcode tests asserting that the result **must pick a specific node sequence** when the algorithm only guarantees shortest length.

### 9.1. Hop-Based `shortestPath` Query

Using standard Cypher 5 syntax:

~~~cypher
MATCH (start:SocialUser {userId: $fromId})
MATCH (finish:SocialUser {userId: $toId})
WHERE start <> finish
OPTIONAL MATCH p = shortestPath(
    (start)-[:FRIEND*1..6]-(finish)
)
RETURN
    CASE WHEN p IS NULL THEN null ELSE length(p) END AS hops,
    CASE WHEN p IS NULL
         THEN []
         ELSE [u IN nodes(p) | u.userId]
    END AS pathUserIds;
~~~

With `fromId = 'A'` and `toId = 'G'`, expect `hops = 4`. A valid path is `['A', 'B', 'D', 'F', 'G']` or `['A', 'C', 'E', 'F', 'G']`, depending on which path Neo4j selects.

**Clause-by-clause explanation:**

- `shortestPath(...)` finds a path with the **fewest edges** matching the pattern.
- `*1..6` bounds the edge count from **1 to 6**. This is a query bound, **not** a universal relationship radius for every social network.
- `length(p)` returns the number of relationships in the path.
- `nodes(p)` returns the nodes along the path, and the list comprehension extracts `userId`.
- `OPTIONAL MATCH` returns `null`/`[]` when both people exist but **no path exists within at most six hops**.

**Edge cases:**

- If `start` or `finish` does not exist, the initial `MATCH` clauses produce no rows; the query **returns no record**. The application must handle this separately.
- If both IDs are equal, `start <> finish` filters out the row; mathematically, the distance from a node to itself is **0**. The application can return 0 before running the query.
- If `p IS NULL` with a bound of 6, you can only conclude that **no path of length at most 6 hops was found**, not that the entire network is completely disconnected.
- When multiple shortest paths exist, the specific path chosen is not guaranteed to be stable across versions or query plans.

On newer Neo4j versions supporting **path selectors** such as `ANY SHORTEST`, you can use the path-selector syntax instead of `shortestPath(...)` per the target version's documentation. Do not mix newer syntax with an older Cypher server that does not support it.

### 9.2. When You Need All Shortest Paths

~~~cypher
MATCH (a:SocialUser {userId: 'A'})
MATCH (d:SocialUser {userId: 'D'})
MATCH p = allShortestPaths((a)-[:FRIEND*1..3]-(d))
RETURN [u IN nodes(p) | u.userId] AS pathUserIds,
       length(p) AS hops
ORDER BY pathUserIds;
~~~

With the sample data, there are **two paths of length 2** via B and C. On a large graph, the number of shortest paths can grow dramatically; **do not use unbounded `allShortestPaths`** to return all paths between two people on a multi-million-node network.

### 9.3. Hop Distance Differs from Weighted Paths

In a social network, a path through two close friends may be valued differently from a path through two low-interaction accounts. However, standard `shortestPath` minimizes **edge count**, not total interaction weight.

If weighted distance is needed (e.g., non-negative connection costs), consider **Dijkstra** or weighted shortest-path variants supported by your Neo4j GDS edition. When choosing weights, explicitly define whether **smaller values mean a better path** or vice versa; a high interaction count is not automatically a "low cost" unless you transform the feature's semantics.

**A short path does not imply two people are close or trustworthy.** Friend-introduction systems must separate graph signals from safety policies, visibility controls, and personal-data inference risks.

## 10. When the Model Uses Directed `FOLLOWS`

If the application focuses on following (authors, channels, content), do not use undirected friend queries for `FOLLOWS`.

Assume the following data:

~~~cypher
MATCH (a:SocialUser {userId: 'A'})
MATCH (b:SocialUser {userId: 'B'})
MATCH (c:SocialUser {userId: 'C'})
MERGE (a)-[:FOLLOWS]->(b)
MERGE (c)-[:FOLLOWS]->(b)
MERGE (b)-[:FOLLOWS]->(a);
~~~

Note that these statements add `FOLLOWS` edges to the **same sample graph** without replacing the `FRIEND` edges. Then:

~~~cypher
// Accounts that B follows:
MATCH (b:SocialUser {userId: 'B'})-[:FOLLOWS]->
      (following:SocialUser)
RETURN following.userId AS followingId;
// Per the added FOLLOWS fixture: A
~~~

~~~cypher
// Accounts that follow B:
MATCH (follower:SocialUser)-[:FOLLOWS]->
      (b:SocialUser {userId: 'B'})
RETURN follower.userId AS followerId
ORDER BY followerId;
// A, C
~~~

Checking **mutual following**:

~~~cypher
MATCH (a:SocialUser {userId: $userA})
MATCH (b:SocialUser {userId: $userB})
RETURN EXISTS { MATCH (a)-[:FOLLOWS]->(b) } AS aFollowsB,
       EXISTS { MATCH (b)-[:FOLLOWS]->(a) } AS bFollowsA;
~~~

If both fields are `true`, that is **mutual following**; whether it automatically becomes a `FRIEND` relationship depends on product rules. In a directed graph, the distance `A → B` can **differ** from `B → A`; with undirected `FRIEND`, the distance between two endpoints is symmetric.

## 11. Designing Duplicate-Free Friendship Creation

In the one-edge-per-pair model, relationships must be created in **canonical ID order** so that a request `A friends B` and `B friends A` target **the same pair**.

~~~cypher
MATCH (u:SocialUser {userId: $userA})
MATCH (v:SocialUser {userId: $userB})
WHERE u <> v
WITH
    CASE WHEN u.userId < v.userId THEN u ELSE v END AS leftUser,
    CASE WHEN u.userId < v.userId THEN v ELSE u END AS rightUser
WITH leftUser, rightUser,
     leftUser.userId + '|' + rightUser.userId AS canonicalPairKey
MERGE (leftUser)-[r:FRIEND {pairKey: canonicalPairKey}]->(rightUser)
ON CREATE SET r.since = datetime()
RETURN r.pairKey AS pairKey;
~~~

**Preconditions before running:** the application has verified that the request **was accepted**, both accounts are eligible to connect, no block exists, and the caller is authorized. The query above **only handles storing the relationship**; never expose it directly as an unvalidated "friend anyone" endpoint bypassing validation/authorization.

### Why Are Constraints Needed?

`MERGE` detects an existing pattern within a transaction, but under concurrent transactions, **a `MERGE` statement alone does not replace database-level uniqueness constraints**. To prevent duplicates under load, maintain a unique constraint on `pairKey` and enforce that every write path sets it using the same rule.

If a transaction encounters a uniqueness error under contention, the Java Driver may return a non-transient schema error; do not retry infinitely. The service layer can re-read the relationship after the error to determine whether the request was already processed or represents a data conflict.

### Modeling Friend Requests Instead of Immediate Friendship

A real product typically goes through:

~~~mermaid
flowchart LR
    A["A sends request to B"] --> P["FRIEND_REQUEST<br/>PENDING"]
    P -->|"B accepts"| F["FRIEND<br/>one canonical edge"]
    P -->|"B declines"| R["REJECTED / retained per audit policy"]
    P -->|"A cancels"| C["CANCELLED"]
~~~

Request status can be stored on a relationship or a separate event node for auditing. If full request history over time is required, a single `FRIEND_REQUEST` relationship updated in place may not suffice to preserve history. The choice depends on business requirements, not a mandatory Neo4j rule.

## 12. Java Driver: Integrating Friend Recommendations into an Application

One integration pattern is to keep parameterized Cypher in a repository class, use a **managed read transaction**, and map results to a DTO. Example with Java 17+ and a Neo4j Java Driver version supporting `executeRead`:

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class SocialGraphQueries {
    private final Driver driver;
    private final String database;

    public record Suggestion(
            String userId, String displayName, long mutualCount) {}

    public SocialGraphQueries(Driver driver, String database) {
        this.driver = driver;
        this.database = database;
    }

    public List<Suggestion> suggestFriends(String viewerId, int limit) {
        if (viewerId == null || viewerId.isBlank()) {
            throw new IllegalArgumentException("viewerId is required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        try (Session session =
                driver.session(SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (me:SocialUser {userId: $viewerId})
                          -[:FRIEND]-(bridge:SocialUser)
                          -[:FRIEND]-(candidate:SocialUser)
                    WHERE candidate <> me
                      AND candidate.isActive = true
                      AND NOT EXISTS {
                          MATCH (me)-[:FRIEND]-(candidate)
                      }
                      AND NOT EXISTS {
                          MATCH (me)-[:BLOCKED]->(candidate)
                      }
                      AND NOT EXISTS {
                          MATCH (candidate)-[:BLOCKED]->(me)
                      }
                    WITH candidate,
                         count(DISTINCT bridge) AS mutualCount
                    RETURN candidate.userId AS id,
                           candidate.displayName AS name,
                           mutualCount
                    ORDER BY mutualCount DESC, id ASC
                    LIMIT $limit
                    """, Map.of(
                            "viewerId", viewerId,
                            "limit", limit))
                    .list(record -> new Suggestion(
                            record.get("id").asString(),
                            record.get("name").asString(),
                            record.get("mutualCount").asLong())));
        }
    }
}
~~~

Invocation:

~~~java
// Driver should be a long-lived, centrally managed instance.
SocialGraphQueries queries = new SocialGraphQueries(driver, "neo4j");
var suggestions = queries.suggestFriends("A", 10);
// Sample data: D has mutualCount 2, E has mutualCount 1.
~~~

**Technical notes:**

1. `Driver` is typically shared across threads and managed for the application's lifecycle; `Session` is short-lived per unit of work and **must not** be shared across threads.
2. `executeRead` marks the work as a **read transaction** and allows transient error retries per policy; the callback only reads and maps results, making it safe to replay.
3. `Map.of` and parameters `$viewerId`, `$limit` prevent interpolating user input into Cypher structure.
4. Mapping to a `Suggestion` DTO instead of returning entire nodes/relationships limits API data exposure.
5. Validating `limit` in Java prevents endpoints from requesting huge result sets; however, the number of candidates scanned/aggregated before `LIMIT` still depends on the graph.
6. The query expresses only **part** of product policy. The service layer must enforce caller authorization, mutual-friend visibility, candidate visibility, and API abuse protection.

### 12.1. Reading Relationship Distance from Java

The same `Driver` can be used for distance queries. Because `hops` can be `null`, do not call `asInt()` directly without checking:

~~~java
import java.util.Map;
import java.util.OptionalInt;

public OptionalInt distance(String fromId, String toId) {
    if (fromId.equals(toId)) {
            // Production APIs must verify the user exists and is authorized.
        return OptionalInt.of(0);
    }
    try (Session session =
            driver.session(SessionConfig.forDatabase(database))) {
        return session.executeRead(tx -> {
            var record = tx.run("""
                MATCH (a:SocialUser {userId: $fromId})
                MATCH (b:SocialUser {userId: $toId})
                OPTIONAL MATCH p = shortestPath(
                    (a)-[:FRIEND*1..6]-(b)
                )
                RETURN CASE WHEN p IS NULL
                            THEN null
                            ELSE length(p)
                       END AS hops
                """, Map.of(
                    "fromId", fromId,
                    "toId", toId)).single();
            return record.get("hops").isNull()
                    ? OptionalInt.empty()
                    : OptionalInt.of(record.get("hops").asInt());
        });
    }
}
~~~

This `distance` snippet is an **additional method** for `SocialGraphQueries` above and must be placed inside the same class to access `driver` and `database`. If either input user does not exist, `.single()` throws an exception; the application must distinguish `404 Not Found`, `403 Forbidden`, and "no path within bound" according to its API specification.

## 13. Spring Data Neo4j: Repositories and Mapping

With Spring Data Neo4j, a simple entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("SocialUser")
public class SocialUser {
    @Id
    private String userId;
    private String displayName;
    private boolean isActive;

    protected SocialUser() {}

    public SocialUser(String userId, String displayName) {
        this.userId = userId;
        this.displayName = displayName;
        this.isActive = true;
    }

    public String getUserId() { return userId; }
    public String getDisplayName() { return displayName; }
    public boolean isActive() { return isActive; }
}
~~~

Repository reading only direct friends:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface SocialUserRepository
        extends Neo4jRepository<SocialUser, String> {

    @Query("""
        MATCH (me:SocialUser {userId: $userId})
              -[:FRIEND]-(friend:SocialUser)
        WHERE friend.isActive = true
        RETURN DISTINCT friend
        ORDER BY friend.userId
        """)
    List<SocialUser> findActiveFriends(@Param("userId") String userId);
}
~~~

This entity model **only contains node properties** without mapped relationships. Therefore, `RETURN DISTINCT friend` works well for reading plain `SocialUser` objects. For entities with `@Relationship` and custom queries returning complex subgraphs, consult the SDN documentation on **relationship mapping and custom query results**; do not assume `RETURN friend` automatically loads all related edges.

**Notes:**

- `@Id` marks the identifier key in Java mapping; **it does not guarantee that a uniqueness constraint exists in Neo4j**.
- `@Query` executes developer-written Cypher; test it against a real Neo4j instance. Derived repository queries should also be tested because the framework may generate Cypher different from what you expect.
- For queries that only need mutual-friend statistics or recommendations, returning a **DTO/projection** or using `Neo4jClient` to map scalars is usually preferable to loading a large object graph.
- Use `@Transactional(readOnly = true)` at the service layer when appropriate, though this annotation **does not replace friend-visibility authorization**.

## 14. Optimizing Cypher on Large Social Networks

Real social networks can contain millions of users and "hub" nodes with huge numbers of connections. Two-hop queries can multiply intermediate rows dramatically:

~~~text
A node has 10,000 friends/neighbors.
Each neighbor connects to 10,000 people.

A two-hop expansion can generate up to 100,000,000
path combinations before deduplication and limiting.

This is an illustrative degree estimate, not a benchmark result.
~~~

### 14.1. Start from an Indexed Node

~~~cypher
CREATE CONSTRAINT social_user_id_unique IF NOT EXISTS
FOR (u:SocialUser)
REQUIRE u.userId IS UNIQUE;
~~~

Neo4j can look up `userId` rapidly via the constraint's backing index, then expand relationships from that single node. Rather than scanning **all** two-hop pairs across the entire network and filtering by `userId`, write queries with an explicit starting point.

### 14.2. Bound Traversal Depth and Relationship Types

- Mutual-friend recommendations: only **two `FRIEND` hops** are needed.
- Social distance: enforce a **hop limit** or resource budget if the API cannot wait on an unbounded search.
- If the graph has `FRIEND`, `FOLLOWS`, and `MEMBER_OF`, never use an untyped `--` pattern when the business logic only counts friendships.
- Never run unbounded `allShortestPaths` between hub pairs if the endpoint only needs **one** shortest path.

### 14.3. Inspecting the Execution Plan

~~~cypher
EXPLAIN
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId, mutualCount
ORDER BY mutualCount DESC, candidateId
LIMIT 20;
~~~

`EXPLAIN` only builds the plan; `PROFILE` **executes** the query and reports metrics such as `Rows`, `DB Hits`, and the operators used. For read-only queries in a test environment, you can run `PROFILE`:

~~~cypher
PROFILE
MATCH (me:SocialUser {userId: $userId})-[:FRIEND]-
      (bridge:SocialUser)-[:FRIEND]-(candidate:SocialUser)
WHERE candidate <> me
  AND NOT EXISTS {
      MATCH (me)-[:FRIEND]-(candidate)
  }
WITH candidate, count(DISTINCT bridge) AS mutualCount
RETURN candidate.userId AS candidateId, mutualCount
ORDER BY mutualCount DESC, candidateId
LIMIT 20;
~~~

What to observe:

| Plan Stage | Question |
|---|---|
| Finding `me` | Does it use the index on `userId` or scan all labels? |
| First `Expand` | How many neighbors does this user have? |
| Second `Expand` | Do intermediate rows spike sharply? |
| `AntiSemiApply` / `NOT EXISTS` check | What is the cost of excluding existing friends and blocked users? |
| `Aggregation` / `Distinct` | Are many duplicate rows being grouped? |
| `Sort` / `Top` | Does the query have to sort a huge candidate set before `LIMIT`? |

Operator names can vary across Neo4j versions and planners. **Do not write tests asserting that a specific operator name must appear** across all versions; what matters is correctness, selectivity, intermediate row counts, and actual cost.

### 14.4. When Should Results Be Precomputed?

If users open the recommendations page thousands of times per second, consider:

- Running a scheduled job to generate top recommendations per user and storing them in a cache.
- Refreshing recommendations when friendships or block statuses change.
- Computing online only within a narrow candidate pool; offloading heavy GDS/ML ranking to offline pipelines.
- Defining cache TTLs and invalidation/deletion when users revoke visibility permissions.

Never use **stale cached recommendations** to bypass block/private policies: at API response time, active security rules must still be checked.

## 15. Privacy and Relationship Safety

Social networks hold sensitive information about **who knows whom**, not just profile fields. Even without returning emails or real names, returning the full list of mutual friends or intermediate nodes on a path can reveal relationships a user wants to keep private.

### 15.1. Distinguish Three Control Layers

| Layer | Example | Responsibility |
|---|---|---|
| **Database RBAC** | Service account only reads required labels/properties | Prevent overly broad access at the Neo4j layer per edition capabilities |
| **Business authorization** | Can A view B's friend list? | Rules based on viewer, privacy settings, and relationship state |
| **API data minimization** | Return `candidateId, displayName, mutualCount` instead of whole nodes | Limit data exposed to clients |

Neo4j has no built-in awareness of the social network's "current HTTP viewer". A DB account having graph read privileges **does not mean every application user may see the whole graph**. The application tier must enforce visibility policies per viewer identity, combined with DB privileges and privacy tests.

### 15.2. Paths Can Leak Hidden Relationships

Suppose A is allowed to know they are "three hops away from B", but is not allowed to see that B is connected to a specific person. Returning `nodes(path)` verbatim can expose that intermediate node.

Therefore, the API must define clearly:

- Should only the **hop count** be returned, or the **intermediate list** as well?
- Is traversal allowed across edges/accounts marked private?
- Are blocked/hidden accounts excluded **during path traversal**, or only filtered after the path is found?
- Should the mutual-friend count be exposed when some mutual friends come from private relationships?

**Filtering only target nodes after computing the path may not be enough**: if a path is found through edges the viewer is not permitted to know about, the resulting distance or mutual-friend count can still leak information indirectly.

### 15.3. Practical Controls to Enforce

- Enforce authorization on **every endpoint**, not only in the UI.
- Run only **parameterized** Cypher, validate IDs, and bound result sizes.
- Keep block, private, disabled, and pending-request policies **consistent** with caches and background jobs.
- Apply rate limiting to prevent a client from scraping the friend graph via the API.
- Do not write real names, emails, mutual-friend lists, or sensitive query parameters into unprotected logs.
- Verify the actual read/write permissions of the Java Driver/SDN runtime identity; never use an admin account.

## 16. Integration Testing and Expected Results

Using the sample dataset from Section 5, you can write implementation-independent assertions:

| Feature | Input | Expected |
|---|---|---|
| Get direct friends | A | B, C |
| Friend count | C | 4 |
| Check friendship | A, B | `true` |
| Check non-friendship | A, D | `false` |
| Mutual friends | A, D | B, C |
| Mutual friend count | A, E | 1 (C) |
| Two-hop suggestions | A | D (2), E (1) |
| Distance | A, D | 2 |
| Distance | A, G | 4 |
| Shortest path A–D | A, D | Either A–B–D or A–C–D |
| Distance to self | A, A | 0 per mathematical definition |
| Non-existent user | A, Z | Application-defined "not found" response |

### 16.1. Anomalous Data Cases to Test

1. **Non-existent user:** distinguish missing IDs from an empty relationship result.
2. **User with no friends:** return an empty list and distance semantics per explicit policy.
3. **Two users in disconnected components:** no path, and must not report distance 0.
4. **Two users already friends:** must not appear in recommendation lists.
5. **Blocked candidate:** must not appear when the viewer blocks or is blocked by the candidate.
6. **Multiple shortest paths:** assert `length` and edge validity, not planner-dependent path selection order.
7. **Duplicate relationships:** check whether legacy parallel edges multiply rows or skew counts.
8. **Self-loop:** self-friending must not be allowed; test validation before writing.
9. **Inactive/private accounts:** filter properly in suggestions and relationship views per product policy.
10. **Concurrent friend requests:** constraints/transactions must preserve exactly one relationship per pair.

### 16.2. Testing Against a Real Neo4j Instance

With Java Driver, JUnit 5, or Spring Data Neo4j `@DataNeo4jTest`, run tests on **Neo4j Testcontainers or an isolated test database**, not only mocked repositories. Reasons:

- Only Neo4j executes `MATCH`, `EXISTS`, `shortestPath`, and uniqueness constraints.
- Java/SDN mappers can behave differently from expectations even when hand-written Cypher is valid.
- Transaction and race-condition tests require a real DB environment.
- Fixture data can be verified via a Cypher query **independent** of the repository under test.

Conceptual JUnit example with AssertJ:

~~~java
@Test
void suggestsTwoHopFriendsInExpectedOrder() {
    // Arrange: Neo4j test DB is seeded with exactly 7 nodes / 9 edges.
    var actual = queries.suggestFriends("A", 10);

    assertThat(actual)
            .extracting(SocialGraphQueries.Suggestion::userId)
            .containsExactly("D", "E");

    assertThat(actual)
            .extracting(SocialGraphQueries.Suggestion::mutualCount)
            .containsExactly(2L, 1L);
}
~~~

This is an **additional test method** that belongs inside a JUnit class with `queries`, the AssertJ dependency, and dedicated data setup. The test does not start Neo4j on its own; integration setup must ensure fixtures are created, rolled back, or cleaned up per lifecycle.

### 16.3. Verifying Edge Count Does Not Grow on Repeated Requests

~~~cypher
MATCH (a:SocialUser {userId: 'A'})-[r:FRIEND]-
      (b:SocialUser {userId: 'B'})
RETURN count(r) AS edgesBetweenAAndB;
// Expected: 1 when storing one edge per pair.
~~~

Repeat the write operation for the same pair through the business workflow, then run the query above. The result must still be **1**. If two edges are created by concurrent transactions, verify the `pairKey` constraint, direction canonicalization flow, and contention error handling.

## 17. Production Rollout Workflow

### Step 1 — Finalize the Business Contract

Define `FRIEND` as an accepted relationship, `FOLLOWS` as directed, block/private conditions, and whether multiple relationships of other edge types are permitted between the same pair.

### Step 2 — Design Keys and Migrations

Create unique constraints on `userId`; if using one edge per friend pair, canonicalize `pairKey`. Inspect legacy duplicate nodes/relationships **before** enabling new constraints. Do not blindly delete duplicate nodes if they still carry business relationships that must be reconciled.

### Step 3 — Test Queries on Small Data

Run the queries in this lesson and assert clear fixture outcomes: A has B/C, A–D share B/C as mutual friends, A–G are four hops apart. Test identical IDs, zero friends, disconnected nodes, and blocked pairs.

### Step 4 — Test with Realistic Degree Distributions

Generate a representative dataset for node counts, edge counts, and **high-degree hubs**. Measure API p50/p95/p99 latency, intermediate row counts, `DB Hits`, CPU, connection pool behavior, and capacity. Never extrapolate production performance from a 7-node graph.

### Step 5 — Enforce Privacy and API Limits

Run positive/negative authorization tests using the application's actual runtime identity, verifying that results do not leak private users/edges and that mutual counts are hidden per policy. Return only required DTOs, enforce rate limits, and maintain cache invalidation.

### Step 6 — Observe and Optimize Continuously

Monitor two-hop query frequency, candidate counts, p95/p99 latency, Java Driver/Neo4j errors, query plan shifts, and duplicate-data anomalies. For heavy recommendation workloads, consider batch/caching or validated GDS pipelines.

## 18. Common Misconceptions

| Misconception | Reality | How to Avoid |
|---|---|---|
| `FRIEND` stored in one direction means friendship is one-way | Physical direction differs from bidirectional semantics | Use `-[:FRIEND]-` on reads and one canonicalized edge |
| `FOLLOWS` is synonymous with `FRIEND` | Following is directed and may not be reciprocated | Define relationship types per product semantics |
| `count(*)` always equals mutual friend count | Parallel edges or multiple paths can multiply rows | Use `count(DISTINCT bridge)` and check for duplicates |
| A friend-of-a-friend is always a new suggestion | Could be the viewer or an existing friend | Exclude `candidate = me` and use `NOT EXISTS` |
| `LIMIT 20` guarantees only 20 rows are scanned | Limit is usually applied near the end of the query | Analyze `PROFILE` and constrain fan-out |
| Distance 2 means mutual trust | It only means two edges in the graph | Do not infer personal traits or trustworthiness |
| `shortestPath` always chooses the same ID sequence | Multiple shortest paths may exist | Test path length and edge validity |
| No path ≤ 6 means two people are disconnected | A path longer than 6 may exist | Distinguish "exceeded bound" from "disconnected" |
| `MERGE` prevents all concurrency duplicates on its own | Depends on constraints, keys, and write conventions | Canonical pair key + unique constraint |
| `@Id` in SDN creates a DB constraint | It is only Java mapping metadata | Create/verify constraints in Cypher |
| Filtering blocked candidates alone protects privacy | Intermediate nodes/edges or caches can also leak info | Enforce authorization during traversal and at the API |
| Mocking repositories is enough to test graph paths | Mocks do not run Cypher or check schema | Run integration tests with real Neo4j |

## 19. Practice Exercises

### Exercise 1 — Computing Mutual Friends

Using the 7-person graph from this lesson, find the mutual friends of `B` and `C`. Predict the answer before running the query.

**Hint / Solution:** `N(B) = {A,C,D}`, `N(C) = {A,B,D,E}`, so the mutual friends are `{A,D}`, count **2**. The Cypher matches Section 7 with `userA='B'` and `userB='C'`.

### Exercise 2 — Friend Recommendations for G

G is only friends with F. Which accounts are **exactly two hops** from G via `FRIEND` and are not yet direct friends?

**Hint / Solution:** D and E (via F), each with **1 mutual friend** with G. A/B/C are more than two hops away so they do not appear in two-hop recommendations from G on the sample data.

### Exercise 3 — Shortest Paths

Compute the distances `A → F` and `A → G`. Should you assert one specific A–F path?

**Hint / Solution:** `A–F = 3`, `A–G = 4`. A–F can go through B–D or C–D/C–E; tests should verify path length and edge connections rather than hardcoding a single path.

### Exercise 4 — Fixing a Recommendation Query Missing Filters

~~~cypher
MATCH (me:SocialUser {userId: 'A'})-[:FRIEND]-
      (f)-[:FRIEND]-(candidate)
RETURN candidate.userId;
~~~

What is wrong with the query above?

**Hint / Solution:** It can return existing friends (e.g., A–B–C), return duplicate candidates across multiple paths, and ignore block/private rules. You should keep a defensive check excluding `candidate = me`; the `A–B–A` loop over a single edge does not appear in this `MATCH` due to the rule against reusing the same relationship in one path. Exclude direct friends with `NOT EXISTS`, aggregate by `candidate` with `count(DISTINCT f)`, sort/limit, and apply visibility policies.

### Exercise 5 — Counting `FOLLOWS` Differently from `FRIEND`

User A follows B, but B does not follow back. You need to determine who A follows and who follows A; should you use `-[:FOLLOWS]-` for both queries?

**Hint / Solution:** No. Use `(A)-[:FOLLOWS]->(following)` for who A follows and `(follower)-[:FOLLOWS]->(A)` for who follows A. An undirected pattern mixes the two roles.

### Exercise 6 — Paths and Privacy

A user is permitted to see **relationship distance** but not **the friend list of a private account**. The API returns `pathUserIds` containing all intermediate users. What risk arises?

**Hint / Solution:** The path can reveal private relationships or block statuses. Enforce policy checks on edges/nodes during traversal, return only hop counts when appropriate, and test private/block data under the viewer's identity.

### Exercise 7 — Expanding on a Hub

An account has 50,000 friends, and each friend has 20,000 friends. Up to how many expansions can a two-hop query generate before deduplication? How should it be optimized?

**Hint / Solution:** A rough upper bound can reach `50,000 × 20,000 = 1,000,000,000` expansions (not necessarily one billion unique candidates). Inspect `PROFILE` and real data, filter by exact type, bound neighbor sets per business rules, consider precomputation/caching, use an appropriate pipeline, and do not rely on a trailing `LIMIT` alone.

## 20. References

- [Neo4j Cypher — Patterns and relationship direction](https://neo4j.com/docs/cypher-manual/current/patterns/)
- [Neo4j Cypher — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher — EXISTS subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/existential/)
- [Neo4j Cypher — Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher — Variable-length patterns](https://neo4j.com/docs/cypher-manual/current/patterns/variable-length-patterns/)
- [Neo4j Cypher — Indexes and constraints](https://neo4j.com/docs/cypher-manual/current/schema/)
- [Neo4j Cypher — Query tuning with EXPLAIN/PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Graph Data Science — Algorithms](https://neo4j.com/docs/graph-data-science/current/algorithms/)

`current` links may change across releases. For Neo4j 5, Cypher 25, or GDS on a specific managed plan, verify supported syntax, edition, permissions, and algorithms before applying in production.

## 21. Key Takeaways

- **`SocialUser` is the node, `FRIEND`/`FOLLOWS` are relationships**; choose the right direction and relationship semantics before writing Cypher.
- **One `FRIEND` edge per pair** is a clean model for bidirectional friendships; it requires a canonical pair convention and constraints to prevent duplicates.
- **Mutual friends are the intersection of two neighbor sets**; use two `FRIEND` hops and `DISTINCT` to avoid multiplying rows.
- **Two-hop recommendations** must exclude the viewer, existing friends, and blocked accounts; mutual-friend count is an explainable ranking signal, not the sole metric.
- **Relationship distance is the shortest hop count** within the permitted traversal scope; it does not mean closeness and does not implicitly allow exposing intermediate nodes.
- **Performance depends on node degree, traversal bounds, and the execution plan**; `LIMIT` does not replace query optimization.
- **Java Driver/SDN, constraints, integration tests, and privacy policies** are mandatory to bring graph queries from a demo into a real application.
