# Parallel Relationships, Self-Loops, and Modeling Edge Cases to Watch Out For

## 1. Objectives and Context

Neo4j is a graph database that uses the **property graph** model to represent entities as **nodes**, links as **relationships**, facts as **properties**, and queries with **Cypher**. In the **Graph Elements** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module, this lesson analyzes two valid structures that are very easy to misunderstand:

- **Parallel relationships**: having **multiple distinct relationships** connecting the same pair of nodes.
- **Self-loop**: a relationship whose **start node and end node are the same node**.

Understanding these two structures helps you design accurate models, ingest data without unintended duplicates, control results when querying relationships/paths, apply indexes and constraints appropriately, and avoid bugs when integrating via **Neo4j Java Driver** or **Spring Data Neo4j**.

After this lesson, you will be able to:

1. Distinguish **valid multiple edges** from **duplicate data edges**.
2. Explain how **relationship type**, **direction**, **endpoints**, and **properties** determine the meaning of an edge.
3. Use Cypher to create, count, filter, and detect parallel relationships and self-loops.
4. Choose between a relationship with properties and an **intermediate event node** when an action occurs multiple times.
5. Design uniqueness rules, eliminate invalid self-loops, and avoid drawing wrong conclusions from result row counts.

> The two structures introduced here are **not technical errors by default** in Neo4j. They only become errors if they violate the system's business rules.

## 2. Reviewing Relationship Anatomy in a Property Graph

Every relationship in Neo4j has:

| Component | Meaning | Example |
| --- | --- | --- |
| **Start node** | Starting node according to stored direction | Account A |
| **End node** | Ending node according to stored direction | Account B |
| **Relationship type** | Link classification, **exactly one type per relationship** | `TRANSFERRED` |
| **Properties** | Properties specifically describing the link | `amount`, `eventId`, `occurredAt` |
| **Own identity** | Each relationship is an independent graph element | Two money transfers are two distinct relationships |

A Cypher pattern:

```cypher
(a:Account)-[r:TRANSFERRED {eventId: 'T001', amount: 200000}]->(b:Account)
```

This means **account A transferred an amount of money to B**. Variable `r` references a relationship; `a` and `b` are node variables. The `->` arrow denotes the stored relationship direction, independent of on-screen layout position.

**Foundational note:** Neo4j **does not automatically restrict** "at most one relationship between two nodes" or "a node cannot connect to itself". If those restrictions are needed, the application must explicitly design write logic and data checks.

## 3. What Are Parallel Relationships?

Suppose account A transfers money to B **two different times**. Both actions share the same endpoints, the same type, and the same direction, yet are **different events**:

```text
                [:TRANSFERRED {eventId: 'T001', amount: 200000}]
(:Account A) ──────────────────────────────────────────────→ (:Account B)
             ──────────────────────────────────────────────→
                [:TRANSFERRED {eventId: 'T002', amount: 350000}]
```

These are **two parallel relationships**. They do not merge automatically even though they share direction, type, and start–end nodes.

### 3.1. Cases Commonly Called Multiple Edges

Consider two nodes `a` and `b`:

| Structure | Example | Interpretation |
| --- | --- | --- |
| Same direction, same type | `(a)-[:TRANSFERRED {eventId: 'T1'}]->(b)` and `(a)-[:TRANSFERRED {eventId: 'T2'}]->(b)` | Two link records of the same type, potentially two independent events |
| Same direction, **different type** | `(a)-[:FOLLOWS]->(b)` and `(a)-[:MENTORS]->(b)` | Two business relationship types between the same node pair |
| **Opposite direction** | `(a)-[:FOLLOWS]->(b)` and `(b)-[:FOLLOWS]->(a)` | Two differently directed actions, such as mutual follows |
| Same endpoints, type, direction, and properties | Running `CREATE (a)-[:FOLLOWS]->(b)` twice | Two physically distinct relationships; likely a duplicate bug if the domain allows only one follow |

In general graph theory, edges of different types or opposite directions are also multiple edges involving the same pair of nodes. When **checking for duplicate data**, clarify whether you are checking **same direction and same type** or any pair of nodes regardless of direction/type.

### 3.2. Why Can Parallel Relationships Be Valid Data?

Many business domains involve repeated events:

- **Transactions:** A transfers money to B multiple times; each transfer has its own transaction ID, amount, and timestamp.
- **Travel:** A user travels from location A to B multiple times; each trip has its own date and mode of transport.
- **Access logs:** A user opens a document multiple times; each access has a timestamp and source.
- **Interactions:** Two people send messages to each other multiple times; each message is a separate event.
- **Diverse relationships:** One person both `FOLLOWS` and `MENTORS` another, even though the start–end nodes are identical.

In these cases, **keeping only a single relationship** could lose history, frequency, or per-event details.

### 3.3. When Are Multiple Edges a Bug?

Suppose a system specifies: **each person has at most one `FOLLOWS` relationship to the same person at a time**. If you run repeatedly:

```cypher
MATCH (a:Person {personId: 'P001'})
MATCH (b:Person {personId: 'P002'})
CREATE (a)-[:FOLLOWS]->(b);
```

Each `CREATE` creates a new relationship. If both nodes are found and the operation runs three times, **three parallel `FOLLOWS` edges** will exist between them, even though the domain expects only one.

Conversely, `CREATE` for two `TRANSFERRED` relationships with **two different `eventId` values** can be completely valid. Therefore, the first question is not "are there multiple edges?" but **"what distinct business fact does each edge represent?"**.

## 4. Creating and Inspecting Parallel Relationships in Cypher

The practice examples below use codes starting with `GE004-`. Run them in a **test database**, and execute the initial `CREATE` block **only once**. Running it again will create additional nodes and relationships; the codes shown in the example do not enforce uniqueness by themselves.

### 4.1. Preparing Sample Data

```cypher
CREATE (a:Account {accountId: 'GE004-A', ownerName: 'An'})
CREATE (b:Account {accountId: 'GE004-B', ownerName: 'Bình'})
CREATE (a)-[:TRANSFERRED {
  eventId: 'GE004-T001',
  amount: 200000,
  occurredAt: datetime('2026-01-10T10:00:00+07:00')
}]->(b)
CREATE (a)-[:TRANSFERRED {
  eventId: 'GE004-T002',
  amount: 350000,
  occurredAt: datetime('2026-01-11T09:30:00+07:00')
}]->(b)
CREATE (b)-[:TRANSFERRED {
  eventId: 'GE004-T003',
  amount: 50000,
  occurredAt: datetime('2026-01-12T08:00:00+07:00')
}]->(a)
RETURN a, b;
```

Expected result: **2 `Account` nodes** and **3 `TRANSFERRED` relationships**:

```text
Account A -- T001, 200000 --> Account B
Account A -- T002, 350000 --> Account B
Account A <-- T003,  50000 -- Account B
```

The first two edges are **parallel in the same direction**; the third goes in the **opposite direction**.

### 4.2. Listing Each Individual Relationship

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
RETURN
  type(r) AS relationshipType,
  startNode(r).accountId AS fromAccount,
  endNode(r).accountId AS toAccount,
  r.eventId AS eventId,
  r.amount AS amount,
  r.occurredAt AS occurredAt
ORDER BY eventId;
```

Expected two rows:

| fromAccount | toAccount | eventId | amount |
| --- | --- | --- | ---: |
| GE004-A | GE004-B | GE004-T001 | 200000 |
| GE004-A | GE004-B | GE004-T002 | 350000 |

`MATCH` does not pick a single representative edge nor collapse parallel edges. Each relationship matching the pattern contributes a result row.

### 4.3. Counting **Edges** vs. **Distinct Target Nodes**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->(b:Account)
RETURN
  count(r) AS transferCount,
  count(DISTINCT b) AS distinctDestinations,
  sum(r.amount) AS totalTransferred;
```

With the initial unmodified data:

| transferCount | distinctDestinations | totalTransferred |
| ---: | ---: | ---: |
| 2 | 1 | 550000 |

`count(r)` counts **two relationships**; `count(DISTINCT b)` counts **one node B** connected to A. These are two different measurements. If asking "how many times did A transfer?", use the edge/event count. If asking "to how many distinct accounts did A transfer?", use the distinct target node count.

### 4.4. Querying Without Direction Constraints

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]-
      (other:Account)
RETURN
  r.eventId AS eventId,
  startNode(r).accountId AS actualFrom,
  endNode(r).accountId AS actualTo
ORDER BY eventId;
```

Because the pattern `-[r:TRANSFERRED]-` does not specify a direction, querying from A sees **all three transactions** (A→B and B→A). However, the data still stores the original direction; `startNode(r)` and `endNode(r)` return the endpoints according to the actual direction of each edge.

**Caution when counting results:** When both endpoint variables are unbound and an undirected pattern is used, the pattern matcher can match the same edge through symmetric variable bindings. When you need to count each relationship exactly once, specify an explicit direction or normalize counting by edge identity rather than inferring edge counts directly from row counts of a broad undirected pattern.

## 5. Detecting Multiple Relationships Between the Same Pair of Nodes

### 5.1. Finding Pairs with Multiple Edges of the Same Type and Direction

```cypher
MATCH (from)-[r:TRANSFERRED]->(to)
WITH from, to, count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN
  from.accountId AS fromId,
  to.accountId AS toId,
  relationshipCount
ORDER BY relationshipCount DESC;
```

If only the practice data from Section 4 is present, the result will contain the pair **GE004-A → GE004-B** with `relationshipCount = 2`.

This query answers: "Which node pairs have more than one `TRANSFERRED` edge in the same direction?". It **does not prove the edges are erroneous duplicates**: for transactions, each edge carries a different `eventId`.

To find multiple-edge cases regardless of type, still grouped by **same direction and same type**:

```cypher
MATCH (from)-[r]->(to)
WITH from, to, type(r) AS relationshipType,
     count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN
  elementId(from) AS startElementId,
  elementId(to) AS endElementId,
  relationshipType,
  relationshipCount
ORDER BY relationshipCount DESC;
```

`elementId(n)` is used here solely for **diagnostics in query results**. Do not use it as a long-term business ID or exchange key across systems; store dedicated entity identifiers like `accountId`.

### 5.2. Checking Duplicates by Event Identifier

A money-transfer domain must distinguish "two transfers between the same accounts" from "the same event ingested twice". Check `eventId`:

```cypher
MATCH ()-[r:TRANSFERRED]->()
WHERE r.eventId IS NOT NULL
WITH r.eventId AS eventId, count(r) AS copies
WHERE copies > 1
RETURN eventId, copies
ORDER BY copies DESC;
```

If the same `eventId` appears on multiple relationships, it is a **signal to investigate**. Do not automatically delete rows based solely on a count query, because you must first verify input data and event sources.

### 5.3. Filtering by Timestamp and Payload

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
WHERE r.occurredAt >= datetime('2026-01-11T00:00:00+07:00')
RETURN r.eventId AS eventId, r.amount AS amount
ORDER BY r.occurredAt;
```

Expected result: only `GE004-T002`. This demonstrates that parallel edges can be **queried by each event's properties**, rather than only by node pair.

## 6. What Is a Self-Loop?

A **self-loop** is a relationship whose **start node and end node are the same**. Neo4j allows self-loops; the relationship still has a type, a stored direction, and properties.

```text
          ┌── [:CAN_TRANSITION_TO {event: 'RETRY'}] ──┐
          │                                          │
          ▼                                          │
       (:State {code: 'WAITING'}) ────────────────────┘
```

The example above models a workflow state `WAITING` that can transition **back to `WAITING` itself** when a retry action occurs. A self-loop has **two endpoint roles**, even though both roles reference **one node**.

### 6.1. Creating and Reading a Self-Loop

```cypher
CREATE (s:WorkflowState {
  code: 'GE004-WAITING',
  description: 'Waiting to be processed'
})
CREATE (s)-[:CAN_TRANSITION_TO {
  event: 'RETRY',
  maxAttempts: 3
}]->(s)
RETURN s;
```

Read the self-loop:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN
  type(r) AS type,
  startNode(r).code AS startState,
  endNode(r).code AS endState,
  r.event AS event,
  r.maxAttempts AS maxAttempts;
```

Result:

| type | startState | endState | event | maxAttempts |
| --- | --- | --- | --- | ---: |
| CAN_TRANSITION_TO | GE004-WAITING | GE004-WAITING | RETRY | 3 |

`MATCH` uses the same variable `s` at both ends, forcing the relationship to connect **node `s` to `s` itself**. Verify further with an expression:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN startNode(r) = endNode(r) AS isSelfLoop;
```

The expected value is `true`.

### 6.2. Practical Examples of Meaningful Self-Loops

| Problem Domain | Pattern | When Is It Reasonable? |
| --- | --- | --- |
| State machine/workflow | `(s)-[:CAN_TRANSITION_TO]->(s)` | A state can be retried without moving to a new state |
| Network infrastructure | `(device)-[:CONNECTS_TO]->(device)` | A device has a loopback connection or a path returning to itself in a specific topology model |
| Software dependencies | `(module)-[:DEPENDS_ON]->(module)` | Can represent a self-dependency, usually a bug indicator to inspect |
| Social networks | `(u)-[:FOLLOWS]->(u)` | Usually disallowed if business rules forbid following oneself |
| Organizational hierarchy | `(person)-[:MANAGES]->(person)` | Usually invalid when a person cannot manage themselves |

**Structurally valid self-loops** do not mean **valid in every business domain**. Define rules by relationship type: allow `CAN_TRANSITION_TO` self-loops for certain states, but reject `MANAGES` self-loops if the organizational model prohibits them.

### 6.3. Querying to Detect Self-Loops Across the Graph

```cypher
MATCH (n)-[r]->(n)
RETURN
  type(r) AS relationshipType,
  elementId(n) AS nodeElementId,
  properties(n) AS nodeProperties,
  properties(r) AS relationshipProperties
LIMIT 100;
```

This query is for **exploration** only and should be limited on large graphs. To check a specific type:

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId, count(r) AS selfFollowCount;
```

Note: because `count(r)` is present without an explicit `GROUP BY`, Cypher groups by the non-aggregate expressions in `RETURN`, here `p.personId`. If no `Person` node follows itself, the query returns no rows for that pattern.

## 7. Parallel Relationships Combined with Self-Loops

A node can have **multiple self-loops**, even of the same type:

```text
(:State {code: 'WAITING'})
     ↺ [:CAN_TRANSITION_TO {event: 'RETRY'}]
     ↺ [:CAN_TRANSITION_TO {event: 'RECHECK'}]
```

Cypher:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
CREATE (s)-[:CAN_TRANSITION_TO {
  event: 'RECHECK',
  maxAttempts: 1
}]->(s)
RETURN s;
```

After running this additional command **once**, node `GE004-WAITING` has two self-loops of the same `CAN_TRANSITION_TO` type, but with different `event` values:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN count(r) AS selfLoopCount,
       collect(r.event) AS events;
```

Expected: `selfLoopCount = 2` and `events` contains `RETRY`, `RECHECK` (do not rely on element order without an appropriate `ORDER BY`).

If the business domain requires **at most one self-loop per action type on the same state**, you need write rules or event identifiers. Neo4j does not infer uniqueness from node pair + type + `event` property.

## 8. Impact on Queries and Path Analysis

### 8.1. Multiple Edges Can Produce Multiple Result Rows

Suppose:

```text
(A) -- r1:TRANSFERRED --> (B)
(A) -- r2:TRANSFERRED --> (B)
```

Query:

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
RETURN a.accountId AS fromId, b.accountId AS toId;
```

On the data from Section 4, this statement returns **two rows** with the same `fromId` and `toId` because it matches two distinct relationships. If the question only cares about **connected account pairs**, use:

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[:TRANSFERRED]->
      (b:Account)
RETURN DISTINCT a.accountId AS fromId, b.accountId AS toId;
```

`DISTINCT` deduplicates rows with identical projected values. It **does not delete relationships** and should not be used to "fix" business logic that needs to count individual transactions.

### 8.2. Two Paths with the Same Node Sequence but Different Relationships

A *path* in Neo4j contains the sequence of nodes **and** the traversed relationships. If A has two different edges to B, there can be **two one-hop paths** A→B:

```cypher
MATCH p = (a:Account {accountId: 'GE004-A'})
          -[:TRANSFERRED]->(b:Account {accountId: 'GE004-B'})
RETURN
  length(p) AS numberOfHops,
  [r IN relationships(p) | r.eventId] AS traversedEvents
ORDER BY traversedEvents;
```

Expected results include the path using `GE004-T001` and the path using `GE004-T002`. These two paths share the **same two nodes** but use **different relationships**; if a path-optimization problem only cares about reachability, you must decide how to handle parallel edges.

### 8.3. Self-Loops Add Steps Without Changing Nodes

A self-loop contributes **one relationship/hop** to a path without **moving to a different node**. For example, a path from state `WAITING` back to itself via `CAN_TRANSITION_TO` is a path of length 1.

In variable-length queries, self-loops and parallel edges can multiply the number of matching paths. Decide:

- Should self-loops be allowed during path analysis?
- Do you care about **each edge event** or only reachable nodes?
- Does the direction of the type carry meaning that must be preserved?
- Should path length or the node/relationship set be bounded before traversal?

Example limiting hop count:

```cypher
MATCH p = (a:Account {accountId: 'GE004-A'})
          -[:TRANSFERRED*1..2]->
          (b:Account {accountId: 'GE004-B'})
RETURN length(p) AS hops,
       [r IN relationships(p) | r.eventId] AS events;
```

`*1..2` is traditional variable-length path syntax in Cypher, convenient for illustrating a 1–2 relationship bound. Newer Neo4j/Cypher versions also support quantified path patterns; the choice depends on your version. On the sample data, the two one-hop parallel edges produce **two distinct paths**.

**Performance:** Traversing graphs with many parallel edges or self-loops can increase result counts and search branching. When optimizing, prefer starting at a node with a specific ID, specifying type and direction, bounding hop count, and inspecting `EXPLAIN`/`PROFILE`.

## 9. Choosing Relationships vs. Intermediate Event Nodes

Even though Neo4j supports multiple relationships between two nodes, **not every repeated action should be modeled as multiple edges**.

### 9.1. Model Using Relationships with Properties

```text
(:Account A)
     ├──[:TRANSFERRED {eventId: 'T001', amount: 200000}]──→ (:Account B)
     └──[:TRANSFERRED {eventId: 'T002', amount: 350000}]──→ (:Account B)
```

Suitable when each event has a moderate set of properties, is primarily read via its two endpoints, and **the event itself does not need many other relationships**.

### 9.2. Model Using Event Nodes

```text
(:Account A)
   ├──[:SENT]──→ (:Transfer {eventId: 'T001'}) ──[:TO]──→ (:Account B)
   └──[:SENT]──→ (:Transfer {eventId: 'T002'}) ──[:TO]──→ (:Account B)
```

When each transaction has status, audit trails, fees, fraud checks, receipts, approval workflows, or multiple related nodes, consider a **`Transfer` node** with its own identifier.

| Criterion | Multiple Relationships | Intermediate Event Node |
| --- | --- | --- |
| Model conciseness | Usually more compact for simple event data | Requires extra nodes and relationships |
| Many detailed fields | Can store properties on the edge | Easy to extend properties and links |
| Event connects to additional entities | Awkward since relationships cannot point to another relationship | Convenient because the event is already a node |
| Querying by two endpoints | Very direct | Must traverse through the event node |
| Independent identity and lifecycle | Can use an event ID on the relationship | Clearer when the event is a first-class business entity |

**Principle:** Choose the model based on **query requirements and data lifecycle**. Do not split an event into a node merely because two edges share start–end nodes; equally, do not force a complex multi-entity event onto a single edge just to reduce node count.

## 10. Controlling Duplicates with CREATE, MERGE, and Identifiers

### 10.1. CREATE Does Not Check for Duplicates

Given two identified nodes:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
CREATE (a)-[:FOLLOWS]->(b);
```

Each successful execution creates **a new relationship**. This is the right choice if every execution represents **a new event**, but inappropriate for a stateful link that should have only one record.

### 10.2. MERGE for Single-Link Models

Suppose each person follows another person via at most **one** `FOLLOWS` relationship in the same direction, and business rules forbid self-follows:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.since = date()
RETURN r;
```

This statement:

1. Finds both nodes by **business identifier**.
2. Skips processing if both variables point to the same node.
3. `MERGE` attempts to match a `FOLLOWS` edge with the **exact type, direction, and endpoints**, creating it if absent.
4. `ON CREATE SET` sets the date only when the edge is newly created.

**Important limitation:** `MERGE` **does not clean up** pre-existing duplicate edges. When multiple transactions execute concurrently, `MERGE` also does not replace the locking/constraint mechanisms needed to enforce every uniqueness rule. Design write transactions and identifier safeguards according to business requirements.

### 10.3. Event Identifiers and Relationship Constraints

For events with an `eventId`, Neo4j supports uniqueness constraints on relationship properties in supported versions, such as Neo4j 5 syntax:

```cypher
CREATE CONSTRAINT transferred_event_id_unique IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
REQUIRE r.eventId IS UNIQUE;
```

This constraint restricts **`TRANSFERRED` relationships with the same `eventId` value**: once an ID exists, a second relationship of the same type cannot be created with that exact ID.

Distinguish carefully:

- **Restricting by `eventId`** does not mean "each pair A→B may have only one edge". Two transactions with different IDs are still allowed.
- A **uniqueness constraint** typically does not require every relationship of that type to possess `eventId`. Property existence constraints or relationship keys depend on version/edition.
- For advanced constraints or older versions, verify the **features and syntax** supported by your Neo4j version.

A transaction ingestion pipeline can use `eventId` as an idempotency key to avoid re-recording the same event. However, if each transfer is genuinely distinct, assign a **new ID** rather than reusing a previous one.

### 10.4. Using MERGE by an Existing Event ID

Once an appropriate uniqueness constraint is in place and both nodes are matched:

```cypher
MATCH (a:Account {accountId: $fromAccountId})
MATCH (b:Account {accountId: $toAccountId})
MERGE (a)-[r:TRANSFERRED {eventId: $eventId}]->(b)
ON CREATE SET
  r.amount = $amount,
  r.occurredAt = datetime()
RETURN r.eventId AS eventId, r.amount AS amount;
```

**Business note:** `MERGE` matches **both endpoints, direction, type, and `eventId`**. If `eventId` is already attached to a transaction between **different endpoints**, the statement may raise a constraint error rather than silently "moving" the event to the new pair. This is usually desirable to detect, because the same event ID should never silently change sender/receiver. The application needs appropriate error handling and reconciliation processes.

## 11. Detecting and Preventing Unintended Self-Loops

### 11.1. Checking Before Creation

Example preventing users from following themselves:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
RETURN r;
```

`a <> b` compares **node identity**, not merely display-name strings. If both IDs resolve to the same node, the `WHERE` clause filters out the self-loop case.

To fail fast at the API layer before sending a query, you can compare `followerId` and `followedId` in application code, while still keeping the write-time check for safety if inputs arrive from multiple sources.

### 11.2. Finding Data That Shows Signs of Violation

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId,
       count(r) AS selfFollows;
```

For the `MANAGES` type:

```cypher
MATCH (p:Person)-[r:MANAGES]->(p)
RETURN p.personId AS managerId, count(r) AS selfManagementLinks;
```

These queries only **detect** issues. If the data is live in production, do not bulk-delete edges before confirming business rules, root causes, and downstream impact on systems reading those edges.

### 11.3. Self-Loops and Longer Cycles Are Two Distinct Cases

A **self-loop** has a length of **one edge**:

```text
A ──[:DEPENDS_ON]──→ A
```

A **cycle** can involve multiple nodes, for example:

```text
A ──[:DEPENDS_ON]──→ B
↑                     │
└────[:DEPENDS_ON]─────┘
```

A self-loop detection query only finds patterns like `A → A`. It **does not** catch longer cycles such as `A → B → A`. When checking for circular dependencies in a system, add appropriate path queries or graph algorithms rather than stopping at `startNode(r) = endNode(r)`.

## 12. Modeling Edge Cases Requiring Special Attention

### 12.1. "Friends" Does Not Have to Mean Two Directed Edges

For a symmetric `FRIENDS_WITH`, Neo4j still stores a **technical direction**. You can choose to:

- Store **one edge** and use `(a)-[:FRIENDS_WITH]-(b)` to query both directions; enforce a convention to prevent unordered-pair duplicates.
- Store **two opposite edges** if each edge represents a separate action, confirmation state, or permission.

Do not default to storing two edges simply because friendship has a "bidirectional" meaning; doing so can double-count connection totals if analytics queries are not normalized.

### 12.2. Multiple Transactions Between the Same Pair of Nodes

A `Customer` can place many `Order`s. Consider the model:

```text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(:Product)
```

Each order has its **own `Order` node**, so there is no need to create multiple `PLACED` edges to **the same order node** just to represent separate placements. If a customer has two orders, create **two `Order` nodes**, each with a business ID, and connect them with appropriate relationships.

### 12.3. "Attended Event" Style Relationships

If the same person attends the same event on multiple different days, you can use multiple `ATTENDED` edges with timestamp properties. However, if each attendance also involves tickets, check-ins, payments, certificates, or audit history, a separate `Attendance` node preserves the identity and lifecycle of each attendance.

### 12.4. Repeated Data Ingestion and Job Reruns

When rerunning an ingestion job, incoming records can create:

1. **Duplicate nodes** because `CREATE` repeatedly creates people/companies.
2. **Duplicate relationships** because `CREATE` repeatedly links the same two nodes.
3. **Inflated path counts** because the graph accumulates redundant edges.

To control this, use **stable business IDs** on nodes, appropriate constraints, write queries that are idempotent according to **business semantics**, and reconciliation procedures. Do not slap `DISTINCT` onto every query just to mask genuine duplicate data.

### 12.5. Modeling and Java Mapping

When using the Neo4j Java Driver, pass IDs via **parameters** instead of concatenating Cypher strings:

```cypher
MATCH (a:Account {accountId: $fromId})
MATCH (b:Account {accountId: $toId})
MERGE (a)-[r:TRANSFERRED {eventId: $eventId}]->(b)
ON CREATE SET r.amount = $amount
RETURN r;
```

The application must clearly distinguish whether an operation is **creating a new event** or **retrying an existing event**. With Spring Data Neo4j, review relationship mappings and relationship properties to ensure they reflect **multiple edges of the same type** or **self-loops** if your domain uses them; in particular, never assume a pair of entities has only one relationship in the database.

## 13. Notes on Indexes, Constraints, and Performance

In Neo4j, node **labels** and relationship **types** along with properties can participate in supported index/constraint configurations. They help locate elements by property and enforce certain data rules, though you should keep these distinctions in mind:

| Goal | Mechanism Usually Applied | Limitation to Remember |
| --- | --- | --- |
| No duplicate account IDs | Uniqueness constraint on `Account.accountId` | Applies only to nodes carrying the `Account` label within constraint scope |
| No duplicate transaction IDs | Uniqueness constraint on `TRANSFERRED.eventId` if supported by version | Two transfers with different IDs can still share endpoints |
| No self-follows | `a <> b` predicate in write queries and application rules | Not automatically enforced by the `FOLLOWS` type |
| Only one `FOLLOWS` edge per directed pair | Link ID/key conventions, write transactions, duplicate checks | Plain `MERGE` does not clean up old duplicates and does not replace all concurrency controls |
| Fast property lookups | Appropriate indexes and selective query predicates | Must verify plans with `EXPLAIN`/`PROFILE` and realistic data |
| Avoid path explosion | Filter start node, type, direction, and bound path length | Self-loops and parallel edges can still multiply valid paths |

In large graphs, full-scan exploratory queries like `MATCH (a)-[r]->(b)` can touch a huge number of edges. Scope by label, ID, relationship type, and time range when applicable:

```cypher
EXPLAIN
MATCH (a:Account {accountId: $accountId})-[r:TRANSFERRED]->(b)
WHERE r.occurredAt >= $fromDateTime
RETURN b.accountId AS destination, count(r) AS transferCount;
```

`EXPLAIN` plans the query without executing it. When passing `$fromDateTime`, the application should supply a **matching temporal type** rather than relying on inconsistent string comparisons. Actual index selection depends on Neo4j version and data statistics.

## 14. Practice Exercises with Answers

The following questions assume the data from Section 4 and one `RETRY` self-loop from Section 6 have been created, with no other writes executed outside what is described.

### Exercise 1. Counting Transfers and Distinct Recipients

Account `GE004-A` has two `TRANSFERRED` edges to `GE004-B`. Write a query returning the **number of transactions** and the **number of distinct destination accounts**.

**Answer:**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->(b:Account)
RETURN count(r) AS transactions,
       count(DISTINCT b) AS distinctRecipients;
```

Result: `transactions = 2`, `distinctRecipients = 1`.

### Exercise 2. Distinguishing Valid Parallel Edges from Erroneous Duplicates

Given:

```text
A --[:TRANSFERRED {eventId: 'T1'}]--> B
A --[:TRANSFERRED {eventId: 'T2'}]--> B
A --[:FOLLOWS]---------------------> B
A --[:FOLLOWS]---------------------> B
```

Question: Why should you not delete all edges that "repeat the same endpoint pair"?

**Answer:** The two `TRANSFERRED` edges with distinct `eventId` values represent **two valid transactions**. The two `FOLLOWS` edges with identical type/direction/endpoints may be **two duplicate records**, if business rules allow only one follow relationship per pair. You must evaluate based on relationship type and business identifiers, not merely the pair of nodes.

### Exercise 3. Detecting Self-Following Users

Write a query to find `Person` nodes that have a `FOLLOWS` edge pointing to themselves.

**Answer:**

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId, count(r) AS countOfSelfFollows;
```

### Exercise 4. Querying Transactions in Both Directions

From account `GE004-A`, list all `TRANSFERRED` transactions involving it, including both **outgoing and incoming**, preserving the actual direction in the output.

**Answer:**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]-
      (other:Account)
RETURN
  r.eventId AS eventId,
  startNode(r).accountId AS sender,
  endNode(r).accountId AS receiver
ORDER BY eventId;
```

With the sample data, this returns three transactions `T001`, `T002`, `T003` with their true stored directions.

### Exercise 5. Modeling Decision

A system records multiple hotel bookings by the same person at the same hotel, where each booking has its own booking code, status, invoice, payment, and cancellation/refund flow. Should you choose multiple `BOOKED` relationships between `Person` and `Hotel` or a dedicated `Booking` node?

**Suggested Answer:** A `Booking` node with its own identifier is usually better because each booking has an independent lifecycle and multiple linked entities. For example:

```text
(:Person)-[:MADE]->(:Booking)-[:AT_HOTEL]->(:Hotel)
```

You can attach `(:Booking)-[:HAS_PAYMENT]->(:Payment)` and other relationships without overloading properties on a single edge.

## 15. Summary

- **Parallel relationships** allow multiple independent relationships between the same pair of nodes; they may share or differ in type and direction depending on the case.
- A **self-loop** has both endpoints on **the same node**; it is a valid property graph structure, but must be validated against business rules.
- **Valid parallel edges** typically represent distinct events; **erroneous duplicate edges** occur when a single business fact is accidentally recorded multiple times.
- `CREATE` always creates a new relationship; `MERGE` matches or creates by pattern and does not remove existing duplicate edges. Use business IDs, appropriate constraints, and write rules to prevent duplicate ingestion.
- `count(r)` counts edges, whereas `count(DISTINCT b)` counts distinct target nodes. `DISTINCT` changes query output and **does not delete duplicate data**.
- Parallel edges and self-loops affect result row counts, path counts, and traversal performance; choose direction, type, filters, and path bounds to match your goal.
- For events with their own identity, lifecycle, and multiple connections, consider moving from property-bearing relationships to an **intermediate event node**.

Mastering these edge cases helps you build reliable Neo4j models, write semantically accurate Cypher queries, control data ingestion, tune queries, and integrate graphs into Java Driver or Spring Data Neo4j applications.
