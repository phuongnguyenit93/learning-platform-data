# Identifying Scans, Index Seeks, and Relationship Expansions in Neo4j Execution Plans

## Learning Objectives

After this lesson, you will be able to:

- Read `EXPLAIN` and `PROFILE` outputs to see where Cypher fetches data, how it does so, and which step incurs cost.
- Identify three common groups of operations in an execution plan: **data scans**, **index seeks/scans**, and **relationship expansions**.
- Distinguish `AllNodesScan`, `NodeByLabelScan`, `NodeIndexSeek`, `NodeUniqueIndexSeek`, `Expand(All)`, and `Expand(Into)` at an application level.
- Use actual rows, estimated rows, and `DB Hits` to pinpoint why a query is slow, rather than looking solely at operator names.
- Improve search direction in a property graph: choose a highly selective starting point, index the right properties, and control path depth.

The **Execution Plans** chapter belongs to the **DATABASE_ENGINE_GRAPH_NEO4J** module. With the **property graph** model, Neo4j stores data as nodes, relationships, and properties. Cypher describes **the data pattern to find**, while the *query planner* decides how to retrieve nodes, traverse edges, and join results to satisfy that pattern. Being able to read plans helps you understand why a relationship or path query runs fast or slow.

> Examples and operator names below follow common Cypher/Neo4j 5.x semantics. Operator names, display formats, runtime options, and planner choices can vary across Neo4j versions, datasets, configurations, and statistics. Always check the actual plan on your target system.

## 1. From Cypher Query to Execution Plan

Suppose an e-commerce system has three node types and two relationship types:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, email"] -->|PLACED| O["Order<br/>orderId, status"]
    O -->|CONTAINS| P["Product<br/>sku, name"]
~~~

Business query:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId;
~~~

To execute this, Neo4j can:

1. Find the customer node with the requested `customerId`.
2. Traverse `PLACED` relationships originating from that customer.
3. Check that the target node has the `Order` label and `PAID` status.
4. Return `orderId`.

If an index or constraint exists on `Customer.customerId`, the first step can be an **index seek**. Otherwise, the plan may need to **scan the Customer label** and then filter by customer ID. If the planner sees starting from paid `Order` nodes has lower cost, it may choose that opposite direction. Order of appearance in the `MATCH` pattern **is not a commitment to execution order**.

~~~mermaid
flowchart TB
    Q["MATCH + WHERE + RETURN"] --> P["Query planner chooses plan"]
    P --> S["Find starting elements<br/>Scan or Index Seek"]
    S --> E["Traverse relationships<br/>Expand"]
    E --> F["Filter, join, sort, return results"]
~~~

## 2. How to Inspect EXPLAIN and PROFILE

### EXPLAIN: Projected, Query Not Run

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId;
~~~

`EXPLAIN` builds the plan without **executing the main query**. It is well suited for checking a query before running it on a large dataset, or before a write query that could alter data. You receive the operators, dependency order, and **Estimated Rows** (projected row counts, when supported by the interface).

### PROFILE: Actual Execution and Measurement

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId;
~~~

`PROFILE` **executes the query** and adds measurement metrics such as `Rows`, `DB Hits`, timing, and runtime stats (depending on version/UI). It helps when analyzing slow queries, while keeping in mind:

- `PROFILE CREATE ...`, `PROFILE SET ...`, or `PROFILE DELETE ...` **actually write data**; never run them casually in production.
- Parameters, data volume, cache, and load affect measurements; compare runs under conditions that are as similar as possible.
- `LIMIT` can avoid returning too many rows, yet it does not guarantee every preceding operator processes little data. For example, `ORDER BY` or aggregations may need to read very many rows before applying `LIMIT`.

### Reading a Plan by Data Flow

Many interfaces render plans as a tree where **input** operators sit near the bottom and pass result rows up to **parent** operators. An *illustrative* example (not an actual measured plan):

~~~text
ProduceResults
└─ Projection (o.orderId)
   └─ Filter (o.status = 'PAID')
      └─ Expand(All) ((c)-[:PLACED]->(o))
         └─ NodeUniqueIndexSeek (c:Customer(customerId = $customerId))
~~~

Reading bottom-up: find one `Customer` via index → expand relationships to `Order` nodes → filter status → project returned fields. This is **one possible plan**; the planner can reverse direction or insert different operators as statistics, indexes, and runtime change.

## 3. Group 1: Data Scans (scan)

A **scan** retrieves a broad range of graph elements, typically across all nodes, a label, or a relationship type. Scans are not inherently bad; they can be the fastest option when data is small or the query needs to read most elements.

| Common Operator | Meaning | Example Query |
| --- | --- | --- |
| `AllNodesScan` | Scan all nodes in the database | `MATCH (n) RETURN n` |
| `NodeByLabelScan` | Retrieve nodes carrying a label | `MATCH (c:Customer) RETURN c` |
| `DirectedRelationshipTypeScan` | Find relationships of a type in a given direction | `MATCH ()-[r:PLACED]->() RETURN r` |
| `UndirectedRelationshipTypeScan` | Look up relationships by type in an undirected pattern | `MATCH ()-[r:PLACED]-() RETURN r` |

Depending on the Neo4j version, label/type scan operators can leverage **token lookup indexes**. Therefore, seeing `NodeByLabelScan` **does not mean** the database uses no index at all. It simply shows the plan accesses nodes by *label*, rather than looking up nodes by a specific **property value**.

### 3.1. AllNodesScan: Starting from Every Node

~~~cypher
EXPLAIN
MATCH (n)
WHERE n.active = true
RETURN n;
~~~

Without a label, the starting point may be `AllNodesScan`, followed by `Filter` on `active`. When the graph holds tens of millions of nodes, scanning every node to locate a few elements is usually very expensive.

If the business logic only cares about customers, specifying the label narrows the search space:

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.active = true
RETURN c;
~~~

The plan can use `NodeByLabelScan` and then filter `active`, or use a property index if one exists and the planner judges it worthwhile.

### 3.2. NodeByLabelScan: Scanning a Labeled Set

~~~cypher
EXPLAIN
MATCH (o:Order)
RETURN o.orderId
LIMIT 20;
~~~

In a query that only needs any 20 `Order` nodes, scanning by label can make sense. If you add a highly selective condition such as `o.orderId = $id`, an index on `orderId` helps avoid scanning many unrelated orders.

### 3.3. Relationship Type Scan

~~~cypher
EXPLAIN
MATCH ()-[r:PLACED]->()
RETURN r
LIMIT 20;
~~~

When neither endpoint node is known and only the relationship type is given, the planner can locate `PLACED` relationships directly using a token lookup index. Do not confuse this operator with `Expand(All)`: **a relationship type scan starts from edges of a matching type**, whereas **expand starts from already-found nodes** to retrieve adjacent edges.

### When Can a Scan Be the Right Choice?

- Most nodes of a label need to be returned, such as for statistics or data export jobs.
- The label contains only a few dozen nodes; separate index lookup overhead may offer no meaningful benefit.
- There is no sufficiently selective property predicate, or no index supports that predicate.
- The query planner weighs data, cost, and statistics and chooses a scan.

Accordingly, evaluate a scan by **the volume of data read and actual row counts**, rather than labeling scans as "always slow".

## 4. Group 2: Index Lookup (index seek)

An **index seek** uses an index structure to locate elements satisfying a property condition. It is typically effective when only a small fraction of data matches the predicate.

Suppose the application frequently looks up `Customer` by `customerId` and `email`:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE RANGE INDEX customer_email_range IF NOT EXISTS
FOR (c:Customer)
ON (c.email);
~~~

These two statements target Neo4j versions supporting this DDL syntax. The unique constraint both protects `customerId` identity and provides a backing index for key lookups. The range index accelerates `email` lookups, yet **does not** enforce email uniqueness on its own.

Verify that indexes exist and are ready:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

Check `state`, labels, and indexed properties rather than only the name. An index must reach its query-serving state, normally `ONLINE`, before evaluating plan outcomes.

### 4.1. NodeIndexSeek and NodeUniqueIndexSeek

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId;
~~~

With an index on `Customer.email`, the planner can select an operator such as `NodeIndexSeek`. There could be **multiple** customers sharing the same email unless the schema has a separate constraint enforcing uniqueness.

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
RETURN c.email;
~~~

With a uniqueness constraint on `Customer.customerId`, a plan can use `NodeUniqueIndexSeek`. This condition identifies **at most one node** by the constrained key, narrowing the rows passed downstream.

Side by side:

| Operator | Condition Typically Leading to It | Implication When Reading the Plan |
| --- | --- | --- |
| `NodeIndexSeek` | Property index exists with an eligible predicate such as equality | Looks up keys matching the condition; can return multiple nodes |
| `NodeUniqueIndexSeek` | Predicate uses an index backing a uniqueness constraint | Looks up by a key value guaranteed to be unique |
| `NodeIndexScan` | Reads matching entries across a property index, e.g., property existence check | Still walks many index entries; not equivalent to a single-value seek |
| `NodeByLabelScan` | Fetches nodes with the label and may filter properties afterward | Not considered a property index seek |

Other index types, range operators, and exact operator names depend on version. For instance, a range index can also support range conditions (`<`, `>`, `>=`, `<=`) when the expression uses supported data types and query shapes.

### 4.2. An Index Can Change Where Graph Traversal Starts

Compare two queries with the same goal:

~~~cypher
// No key filter; may need to traverse many customers.
EXPLAIN
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.orderId;

// Key filter identifies one customer.
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

The second query can use an index to find `c` before expanding relationships. Still, this does not guarantee the entire query is cheap: a single customer with millions of orders can still make the expansion step expensive.

### 4.3. Property Indexes Differ from Token Lookup Indexes

- **Token lookup indexes** support finding nodes by **label** and relationships by **type**, powering the corresponding scan operations.
- **Property indexes** support looking up by **property values** under a given label/type.
- **Uniqueness constraints** protect key-value integrity and create a supporting index.

Looking up `:Order` differs from looking up `Order.orderId = 'O-42'`. Having a node-label lookup index does **not** replace an index on `orderId`.

### 4.4. Index Seek on Relationships

Modern Neo4j also supports indexes on relationship properties. For example:

~~~cypher
CREATE RANGE INDEX transfer_amount_range IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
ON (r.amount);

EXPLAIN
MATCH ()-[r:TRANSFERRED]->()
WHERE r.amount > $minimumAmount
RETURN r;
~~~

The plan can use a relationship property index seek operator when the condition qualifies and the index is cost-effective. If no index exists or filtering by `amount` is not selective, the planner may use a relationship type scan followed by a filter. This differs from expanding outward from an already-known account.

## 5. Group 3: Relationship Expansion (expand)

**Expand** is the operation that starts from a node or set of nodes **already located**, then traverses matching relationships to reach adjacent nodes/relationships. This is the hallmark of graph and path querying in Cypher.

### 5.1. Expand(All): From Known Node to Neighbors

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

A common operator sequence:

~~~text
NodeUniqueIndexSeek (find Customer by customerId)
    ↓
Expand(All) (find Orders via PLACED relationship)
    ↓
Projection / ProduceResults
~~~

In `Expand(All)`, each input node can produce **multiple output rows**: one row per matching relationship/target. If a customer has 10,000 orders, the expansion step can generate roughly 10,000 rows from one customer row before any later filters. Row count and `DB Hits` on expand are usually key indicators when a query touches high-degree relationships.

The `All` in `Expand(All)` refers to retrieving **all matching neighbors**, **not scanning the entire database** like `AllNodesScan`.

### 5.2. Expand(Into): Checking Links Between Two Known Nodes

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MATCH (c)-[:PLACED]->(o)
RETURN c.customerId, o.orderId;
~~~

If the planner has already bound **both `c` and `o`** before checking the edge, it may use `Expand(Into)`: checking whether a matching relationship exists between two known nodes instead of expanding from one node to discover new ones. This is a **possible plan choice**, not a syntax guarantee. When the optimizer picks another access path, the actual operator will differ.

Note: `Expand(Into)` does not guarantee a single row. If multiple `PLACED` relationships exist between the same two nodes, Cypher can return multiple rows for the distinct relationships. Use appropriate identifying keys/constraints or data modeling if business rules require at most one link.

### 5.3. Multi-Hop Expansion and Path Explosion

~~~cypher
EXPLAIN
MATCH (a:Person {personId: $personId})-[:KNOWS*1..3]->(b:Person)
RETURN DISTINCT b.personId;
~~~

The query traverses `KNOWS` relationships from one to three hops. Depending on version and planning, you may encounter `VarLengthExpand(All)`, `VarLengthExpand(Into)`, or another path-traversal operator. With an average branching factor `d`, possible expansions can grow quickly with depth, roughly around `d + d² + d³` in a simple model without deduplication. This is **not an exact cost formula**: cycles, repeated nodes, and filter predicates alter the actual path count.

To keep cost bounded:

1. Start from a selective node via key/index.
2. Cap depth reasonably, e.g., `*1..3` rather than unbounded.
3. Specify the required relationship types and directions.
4. Reduce intermediate results when possible; keep in mind `DISTINCT` deduplicates after much of the expansion work has already occurred.
5. Inspect row counts at each step in `PROFILE` to spot intermediate blow-ups.

### 5.4. How Relationship Type Scan Differs from Expand

~~~cypher
// Source node unknown: may scan by type.
MATCH ()-[r:PLACED]->()
RETURN r;

// Source node known: may expand relationships from that node.
MATCH (c:Customer {customerId: $id})-[r:PLACED]->(o)
RETURN r, o;
~~~

In the first example, a good access strategy is usually locating `PLACED` relationships across the database. In the second example, finding `c` first and traversing **edges adjacent to `c`** can be far better when a customer has few orders compared to total `PLACED` relationships.

## 6. Distinguishing the Three Operator Groups in a Plan

Ask questions in sequence:

| Stage to Inspect | Plan Indicators | Diagnostic Questions |
| --- | --- | --- |
| **Starting point** | `AllNodesScan`, `NodeByLabelScan`, `NodeIndexSeek`, `NodeUniqueIndexSeek` | Are we scanning too many nodes just to find a few elements? |
| **Fetching relationships** | `DirectedRelationshipTypeScan`, `Expand(All)`, `Expand(Into)` | Is there a known anchor? What is the branching degree per node? |
| **Multi-hop expansion** | `VarLengthExpand` or equivalent path-traversal operator | Are depth, intermediate row count, and stopping conditions reasonable? |
| **Filtering / joining data** | `Filter`, `NodeHashJoin`, `CartesianProduct`, and other operators | Does filtering occur early or after generating huge row counts? |
| **Returning results** | `Projection`, `Sort`, `Distinct`, `ProduceResults` | Are sorting or deduplication running over an oversized intermediate set? |

The following mock example is solely for **illustrating how to trace data flow**, not exact Neo4j output:

~~~text
ProduceResults
└─ Projection
   └─ Filter (Order.status = 'PAID')
      └─ Expand(All) [:PLACED]
         └─ NodeUniqueIndexSeek :Customer(customerId)
~~~

The starting point is already optimal thanks to the index, yet if `Filter` discards 99.9% of orders **after** expanding millions of relationships, cost can still be high. In that case, measure whether starting from `Order.status` or adjusting the model/query performs better. You cannot conclude from a mock tree alone; verify actual selectivity.

## 7. Reading PROFILE Measurements to Find Bottlenecks

In Neo4j Browser's execution plan table or equivalent tooling, columns may include:

| Metric | How to Understand | Signals to Watch |
| --- | --- | --- |
| **Estimated Rows** | Rows the planner estimated before execution | Large mismatch with `Rows` can lead to poor join or starting-point choices |
| **Rows** | Rows actually passing through the operator during the run | One input row expanding into hundreds of thousands of rows |
| **DB Hits** | Storage-data access touches at the query-engine level | Very high hits on scan/expand highlight areas to investigate |
| **Page Cache Hits/Misses** | Interactions with the page cache, when reported | High misses can increase physical I/O |
| **Time / Memory** | Time and resource usage, depending on runtime/UI | `Sort`, `Eager`, or joins buffering large amounts of data |

Do not read **DB Hits = disk reads**: a DB Hit can be served from cache. Never infer execution time solely from one DB Hits figure, nor compare environments with different data, cache warmth, or load without controlling conditions.

### Common Patterns to Recognize

- `AllNodesScan` reading millions of nodes when only a few pass `Filter`: missing label, predicate, or suitable property index.
- `NodeByLabelScan` returning huge rows before filtering `email` down to a few: consider indexing `email` if the query is common.
- `NodeIndexSeek` returning very few rows while `Expand(All)` blows up to millions of rows: the bottleneck is **relationship fan-out**.
- `CartesianProduct` across two large unconstrained sets: pair count can grow as the **product** of both branches' rows.
- `Sort` or `Distinct` receiving a massive intermediate set: check early filtering, output ordering, supporting indexes, and whether those operations are necessary.

A plan containing a scan does not automatically mean slow; a plan containing an index seek does not automatically mean fast. **Intermediate row volume** is what must be evaluated throughout the plan.

## 8. Hands-On Exercise with a Small Model

Assuming you have permission to run Cypher on a practice database, create a minimal dataset:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

MERGE (c:Customer {customerId: 'C-001'})
SET c.email = 'c001@example.org'
MERGE (o1:Order {orderId: 'O-001'})
SET o1.status = 'PAID'
MERGE (o2:Order {orderId: 'O-002'})
SET o2.status = 'PENDING'
MERGE (c)-[:PLACED]->(o1)
MERGE (c)-[:PLACED]->(o2);
~~~

Try each in turn:

~~~cypher
// A. Access by label; no property predicate.
EXPLAIN
MATCH (c:Customer)
RETURN c.customerId;

// B. Access by ID protected by a uniqueness constraint.
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})
RETURN c.email;

// C. Find customer by ID, then traverse PLACED relationships.
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})-[:PLACED]->(o:Order)
RETURN o.orderId;

// D. Only relationship type is known, no starting node.
EXPLAIN
MATCH ()-[r:PLACED]->()
RETURN r;
~~~

**Predict first, then verify**:

| Query | Candidate Operator | Why? |
| --- | --- | --- |
| A | `NodeByLabelScan` | Retrieve nodes by `Customer` label |
| B | `NodeUniqueIndexSeek` | Look up by a key with a uniqueness constraint |
| C | `NodeUniqueIndexSeek` + `Expand(All)` | Find one customer first, then fetch related orders |
| D | `DirectedRelationshipTypeScan` | Start from `PLACED` type when endpoints are unknown |

These are **candidates**, not promises that the planner must emit those exact operators. On tiny data, the planner may pick differently. To inspect actual metrics, switch `EXPLAIN` to `PROFILE` on read-only queries and observe `Rows` and `DB Hits`.

### Practice Identifying Expand(Into)

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})
MATCH (o:Order {orderId: 'O-001'})
MATCH (c)-[:PLACED]->(o)
RETURN c.customerId, o.orderId;
~~~

If both indexes allow the planner to resolve both endpoints first, you may see `Expand(Into)`. If not, explain **which starting point the actual plan chose** instead of trying to force the query into a preconceived template.

## 9. Optimization Workflow When Scans or Expansions Are Too Expensive

1. **Record the original query and real parameters.** Different parameters can lead to vastly different selectivity.
2. **Run `EXPLAIN`** to identify the starting point and dependency chain across scans, index seeks, and expansions.
3. **Run `PROFILE` safely** on representative data to inspect `Estimated Rows`/`Rows` gaps, `DB Hits`, and row-inflation points.
4. **Check schema indexes and constraints.** If frequently looking up `Customer.customerId`, ensure an appropriate index exists and is `ONLINE`.
5. **Provide accurate, sufficiently selective predicates.** Specify labels, relationship types, and business keys at the starting point; avoid filtering late after expanding many edges.
6. **Bound traversal depth and breadth where business logic allows.** Multi-hop or high-fan-out queries can grow explosively.
7. **Re-measure the same scenario.** Compare execution time, `Rows`, `DB Hits`, memory, and business results; do not optimize merely to change operator names.

### Should You Use Index Hints?

Cypher allows supplying planner hints when you need to steer the access strategy:

~~~cypher
EXPLAIN
MATCH (c:Customer)
USING INDEX c:Customer(customerId)
WHERE c.customerId = $customerId
RETURN c;
~~~

An index hint can help when you have evidence the planner picked a poor strategy due to statistics or data characteristics. However, a hint **does not create an index**, does not substitute for an appropriate index, and can become harmful as the dataset changes. Prioritize measurement and root-cause verification before forcing choices with hints.

### A Common Mistake When Joining Data

~~~cypher
// Two unconstrained sets; can cause a Cartesian product.
MATCH (c:Customer), (o:Order)
RETURN c.customerId, o.orderId;
~~~

With 100,000 customers and 1,000,000 orders, the pair set can reach 100 billion rows before limits or filters apply. For the business goal of finding a customer's orders, express the graph edge explicitly:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.customerId = $customerId
RETURN o.orderId;
~~~

This informs the planner of the relationship to traverse while avoiding generating unrelated pairs.

## 10. Self-Check Questions

**Question 1.** Does `NodeByLabelScan` prove the database has no indexes at all?

**Answer:** No. Label scan operators can be backed by a **token lookup index**. That is distinct from looking up by property values via a property index.

**Question 2.** A `NodeUniqueIndexSeek` returns one node, yet the query is still slow. What do you inspect next?

**Answer:** Check whether the subsequent `Expand(All)` or join/filter creates too many rows, especially if the node has very many relationships. Inspect `Rows`, `DB Hits`, and `Sort`, `Distinct`, or join operators.

**Question 3.** When is `Expand(Into)` a suitable candidate?

**Answer:** When both endpoints are already bound and the plan needs to verify whether a matching relationship exists between them; the planner may still choose another strategy if cheaper.

**Question 4.** Should you add property indexes to every property so no scans remain?

**Answer:** No. Indexes consume storage and add maintenance overhead on writes; some queries need to read most of the data or start from another node. Create indexes based on query needs and measurement results.

**Question 5.** Is `PROFILE` on a delete statement safe in production just because you are “inspecting the plan”?

**Answer:** No. `PROFILE` **actually executes** the delete statement; use `EXPLAIN` to view the plan without executing.

## 11. Summary Checklist

- **Scan**: retrieves many nodes or relationships across a broad scope; look for `AllNodesScan`, `NodeByLabelScan`, and relationship type scans.
- **Index seek**: accesses elements by indexed property values; look for `NodeIndexSeek` and `NodeUniqueIndexSeek`.
- **Expand**: starts from known nodes and traverses relationships; `Expand(All)` retrieves neighbors, while `Expand(Into)` verifies connections between two already-bound nodes.
- **A good starting point** is typically a small set with a highly selective predicate, though the planner can choose another direction based on cost.
- **`Rows`, `Estimated Rows`, `DB Hits`, cache, and memory** must be read together; an operator name alone does not tell the full performance story.
- **`EXPLAIN` only plans**, while **`PROFILE` executes the query**; be careful with write queries.
- **Token lookup indexes differ from property indexes**; indexes help find the right anchor, but do not automatically solve fan-out, multi-hop paths, joins, or large sorts.

**Conclusion:** Reading a Neo4j execution plan means following data flow from **scan/index seek** to **expand** and then to **filter/join/return results**. Once you identify the starting operator and where intermediate row counts surge, you can tune Cypher and schema using real evidence rather than guesswork.
