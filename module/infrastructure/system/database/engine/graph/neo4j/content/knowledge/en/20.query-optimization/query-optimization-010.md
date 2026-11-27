# Identifying Data Model Limitations Instead of Only Tuning the Query

A slow Cypher query is not always caused by a poorly written `MATCH`, a missing `WITH`, or a forgotten index. There are cases where Neo4j has already picked a sensible starting point, used an index, and avoided full node scans, yet still must expand hundreds of thousands of relationships just to return ten results. In those cases, **the high cost stems from the structure and distribution of data in the graph**, so syntax changes alone cannot solve the problem.

This lesson belongs to the **Query Optimization** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses Neo4j to model connected data as a **property graph**, query relationships and paths with Cypher, design indexes/constraints, and integrate with the Java Driver and Spring Data Neo4j. This topic focuses on distinguishing **query-level limitations** from **data-model limitations**, then deciding when to adjust labels, relationships, properties, history storage, or precomputed data.

After this lesson, you will be able to:

- Read `EXPLAIN`/`PROFILE` to locate operators producing excessive intermediate rows, `DB Hits`, and latency.
- Recognize overly high-degree nodes, multi-layer traversal blowups, duplicate edges, over-fragmented data, and predicates that cannot be applied early.
- Measure *degree distribution* instead of relying solely on average node and relationship counts.
- Weigh query rewrites against model changes, including write overhead, synchronization, storage, and data freshness.
- Design before/after experiments proving a solution truly improves performance while preserving business correctness.

## 1. Distinguishing Two Kinds of Bottlenecks

Start with the question: **is Neo4j doing wasted work because of a suboptimal query, or because the data organization makes that work unavoidable?**

| Signal | Points Toward a Query/Index Issue | Points Toward a Data Model Issue |
| --- | --- | --- |
| Starting point | Starts with a label scan despite selective filter properties. | Already pinpoints one node, which connects to too many other nodes. |
| Intermediate rows | Accidental Cartesian product from two independent patterns. | Valid business paths inherently produce huge combinations. |
| Filtering | Misplaced `WHERE`/`LIMIT` keeping unnecessary rows. | Selective condition only exists at the end of a long path. |
| Data | Suitable index exists, yet the query fails to leverage it. | Presence of a "supernode," heavily skewed data by tenant/product/time. |
| Outcome after rewrite | Changing patterns and pushing filters early drops cost sharply. | Multiple Cypher rewrites still traverse nearly the same number of relationships. |
| Long-term fix | Rewrite query, add appropriate indexes/constraints, drop duplicates. | Change relationship representation, store aggregated results, or manage data lifecycle. |

These are directional indicators, **not automatic conclusions**. A query can suffer from both issues simultaneously. Measure execution plans and data distributions before deciding.

### 1.1. One Model, Two Cost Layers

Suppose you have a behavioral graph:

~~~text
(:User {tenantId, userId})
      |
      | [:VIEWED]
      v
(:Product {sku, name})
      ^
      | [:VIEWED]
      |
(:User {tenantId, userId})
~~~

The application wants to recommend other users who viewed the same products. A user views 20 products; if each popular product was viewed by 10,000 other users, traversing `User → Product → User` can generate roughly **20 × 10,000 = 200,000 candidate pairings** before deduplicating and selecting the top 10. These numbers are illustrative; actual cost also depends on duplicate relationships, product popularity skew, and the execution plan.

Adding an index on `User(tenantId, userId)` helps Neo4j locate the initial user quickly. It **does not reduce the number of relationships on those 20 popular products**. Putting `LIMIT 10` after scoring every candidate also cannot skip traversing the candidate set needed to determine the top 10.

This limitation stems from the model and recommendation algorithm, not merely Cypher syntax.

## 2. Identifying Actual Work with EXPLAIN and PROFILE

`EXPLAIN` shows the estimated plan without executing the query; `PROFILE` actually runs it and records runtime statistics in the plan. Test in a representative environment with realistic parameters and data volumes:

~~~cypher
EXPLAIN
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Follow up by measuring with:

~~~cypher
PROFILE
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

`$tenantId` and `$userId` must be supplied by the test harness or application. If no starting record matches, the query returns empty; that is not proof that the query is fast on dense data.

When reading the plan, watch for these items:

| Common Metric / Operator | What to Ask |
| --- | --- |
| `NodeIndexSeek`, `NodeByLabelScan`, and equivalents | How many nodes does Neo4j start from? Are tenant and ID filters applied properly? |
| `Expand(All)` / `Expand(Into)` or path expansion operators | How many rows does each input row expand into? Does any node fan out massively? |
| `Filter` | Are too many rows discarded **after** an expensive expansion? |
| `Distinct`, `Aggregation`, `EagerAggregation` | How many rows must the engine aggregate before emitting results? |
| `Sort`, `Top` | Is it ranking a huge candidate set just to return a few top rows? |
| `Rows` and `DB Hits` | Where do row counts and database accesses jump sharply? |
| Memory, page cache, and time if displayed | Is the bottleneck relationship expansion, storage reads, or allocation/aggregation? |

Operator names and displayed statistics vary across Neo4j versions, runtimes, and execution modes. `DB Hits` is a plan-level signal of storage access work, **not an absolute time unit**. Read it alongside `Rows`, timing, memory, and output.

**Suspect model signature:** starting from 1 `User` node via index (1 row), stepping to `Product` yields 20 rows, yet stepping back to `User` yields hundreds of thousands of rows. Next, `Aggregation` collapses them to a few thousand people and `Top` keeps 10. Tweaking syntax at the end of the query will not eliminate that initial expansion cost.

## 3. Checking Degree Distribution: Do Not Rely Only on Averages

A **node's degree** is the number of relationships attached to it for a given direction/type. A model averaging 50 views per product can still contain one viral product with millions of views. Nodes with extraordinarily high degree are commonly called *supernodes* or *dense hubs* in performance contexts.

To inspect the sample model:

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (p)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewDegree
RETURN count(*) AS productCount,
       min(viewDegree) AS minViews,
       percentileCont(viewDegree, 0.50) AS p50Views,
       percentileCont(viewDegree, 0.95) AS p95Views,
       percentileCont(viewDegree, 0.99) AS p99Views,
       max(viewDegree) AS maxViews;
~~~

A separate query identifies which nodes cause the explosion:

~~~cypher
MATCH (p:Product)
OPTIONAL MATCH (p)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewDegree
RETURN p.sku AS sku, viewDegree
ORDER BY viewDegree DESC, sku ASC
LIMIT 20;
~~~

These statistics queries **still read many relationships** and can be expensive on large datasets. Run them in an analytics environment, on a replica, or during an appropriate window; in multi-tenant systems, measure distributions per tenant and segment rather than only globally. Different properties or relationship directions can have completely different distributions.

Example hypothetical dataset:

| `VIEWED` Count per Product Metric | Value |
| --- | ---: |
| Median (p50) | 8 |
| p95 | 170 |
| p99 | 4,000 |
| Max | 2,100,000 |

A tiny median helps little if queries regularly traverse a product with 2.1 million relationships. Bounding queries based on "average branching factor" mispredicts worst-case performance.

### 3.1. Cost of Multi-Hop Traversals

In a graph with average branching factor roughly `d`, expanding `k` steps **can** generate paths growing rapidly as `d^k` in low-convergence structures. This illustrates growth rather than providing an exact Neo4j prediction formula: cycles, converging relationships, direction/type constraints, and path-uniqueness rules all alter actual counts.

Example:

~~~cypher
MATCH (start:User {tenantId: $tenantId, userId: $userId})
MATCH p = (start)-[:FOLLOWS*1..4]->(candidate:User)
WHERE candidate.tenantId = $tenantId
RETURN candidate.userId AS userId, length(p) AS hops
ORDER BY hops ASC, userId ASC
LIMIT 20;
~~~

The pattern above **enumerates matching paths**, so a destination user can appear on multiple paths. `LIMIT 20` at the end does not guarantee the engine inspects only 20 paths to find the top 20 in desired order. If business logic only needs unique destination users or shortest paths, change the **result definition** and pick the right query construct before optimizing.

## 4. Signs That the Model Is Imposing Limits

### 4.1. Overcrowded Junctions: Supernodes

Nodes like `:GlobalCatalog`, `:Everyone`, `:PopularTopic`, or an intensely interacted product force many queries through a single high-degree "gateway." Neo4j has internal optimizations for dense nodes, yet cannot eliminate the expansions genuinely needed to produce results.

Consider semantics-preserving solutions:

- If the goal is finding a product by `sku`, go straight to `(:Product {sku})` via an index instead of traversing from `GlobalCatalog` through every product.
- If finding similar users, avoid expanding through **every** viral product when the algorithm allows skipping ultra-popular items that carry minimal personalization signal.
- If top-K recommendations are queried repeatedly, consider precomputing similarity edges with a clear refresh policy.

Never split a supernode into arbitrary shards in ways that distort domain semantics, break queryability, or create duplicate relationships.

### 4.2. Turning Every Attribute into a Node and Relationship

The model below can be over-fragmented if `status` is merely a simple order attribute:

~~~text
(:Order)-[:HAS_STATUS]->(:Status {code:'PAID'})
~~~

If millions of `Order`s link to one `PAID` status node, queries filtering orders may scan an enormous group or take an unnecessary detour. When there is no need to attach independent metadata or business links to a status, storing `status` as a property is often cleaner:

~~~text
(:Order {orderId, status:'PAID', createdAt, tenantId})
~~~

With the second model, you can evaluate a range index for searching by tenant, status, and timestamp:

~~~cypher
CREATE RANGE INDEX order_scope_status_created IF NOT EXISTS
FOR (o:Order)
ON (o.tenantId, o.status, o.createdAt);
~~~

This index does not automatically guarantee every query can use index-backed sorting. Check `EXPLAIN`/`PROFILE` against actual filter and sort patterns. In domains where `Status` is a first-class entity with its own lifecycle, permissions, translations, transition history, or extra relationships, a dedicated node remains valuable; do not mechanically turn every small node into a property.

### 4.3. Storing Repeated Events as Multiple Identical Relationships

Suppose every product view creates a brand-new relationship:

~~~text
(:User)-[:VIEWED {at}]->(:Product)
(:User)-[:VIEWED {at}]->(:Product)
(:User)-[:VIEWED {at}]->(:Product)
~~~

For the question "which products has a user ever viewed?", these three relationships repeat the same user–product pair, inflating rows to expand and `DISTINCT`. Yet for "how many times per day did the user view it?", three separate events are vital information.

You can choose dual representations for the two query patterns:

~~~text
(:User)-[:HAS_VIEWED {count, lastSeenAt}]->(:Product)

(:ViewEvent {eventId, at})
    -[:BY_USER]->(:User)
    -[:OF_PRODUCT]->(:Product)
~~~

`HAS_VIEWED` can be designed so each user–product pair maintains a single summary edge; `ViewEvent` nodes retain granular history for audit/analytics. **Two representations require synchronization or recomputation rules**, because if an event writes successfully without updating the summary edge, recommendations go stale.

Neo4j has no built-in constraint enforcing "at most one relationship between the same two endpoints" solely from using a single relationship type. Design write flows, identity constraints, and concurrency tests to protect the summary structure.

### 4.4. Filter Properties Sitting Only at the End of the Path

A query seeking related items **within the current tenant**, when `tenantId` lives only on `User`, may have to expand global interactions before filtering by tenant:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other.tenantId = $tenantId AND other <> u
RETURN other.userId AS candidateId, count(DISTINCT p) AS sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

If a product links to millions of users across many tenants, expanding to `other` can produce vast numbers of discarded rows. Moving tenant scope to a more selective entry point, partitioning the graph by domain, or modeling tenant-scoped links can help—**provided every approach strictly enforces access control and data consistency**.

Never assume adding `WHERE other.tenantId = $tenantId` stops Neo4j from traversing edges belonging to other tenants. Inspect the plan to see which stage applies the filter, then change the anchor or data structure if large fan-out persists.

### 4.5. Unbounded History Makes Current-State Queries Progressively Slower

For example, if every price change is stored as a node:

~~~text
(:Product)-[:HAD_PRICE]->(:PriceEvent {amount, effectiveAt})
~~~

Price history is essential for auditing and reporting, yet the product page only needs the **current price**. As `PriceEvent`s accumulate over years, walking the entire history on every request to find the latest entry grows slower and slower. You can retain history while maintaining a controlled current price:

~~~text
(:Product {currentPrice, currentPriceUpdatedAt})
(:Product)-[:HAD_PRICE]->(:PriceEvent {amount, effectiveAt})
~~~

Current price is a **materialized projection derived from history**: define how to handle concurrent updates, retroactive edits, drift, and reconciliation. If querying price at a historical timestamp, still read the event/version valid at that time. Materializing reduces read cost at the expense of extra write and reconciliation responsibility.

## 5. Classic Case: "Indexed Yet Still Very Slow"

Consider a query recommending similar users based on viewed products. First, create an index to locate the starting user by tenant-scoped ID:

~~~cypher
CREATE RANGE INDEX user_tenant_id_lookup IF NOT EXISTS
FOR (u:User)
ON (u.tenantId, u.userId);
~~~

Query:

~~~cypher
PROFILE
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[:VIEWED]->(p:Product)<-[:VIEWED]-(other:User)
WHERE other <> u AND other.tenantId = $tenantId
WITH other, count(DISTINCT p) AS sharedProducts
RETURN other.userId AS candidateId, sharedProducts
ORDER BY sharedProducts DESC, candidateId ASC
LIMIT 10;
~~~

Suppose `PROFILE` shows: Neo4j finds 1 `u` node via index; stepping to `Product` yields 20 rows; stepping back to `other` yields 200,000 rows; deduplication and aggregation leave a few thousand candidates. If this reflects representative data, **the primary cost is the two relationship hops**.

Several query-only fixes are still worth checking:

- Restrict `VIEWED` edges to a valid business time window, if edges carry timestamps and the requirement allows it.
- Filter by more specific labels, types, or properties where data permits higher selectivity.
- Remove redundant patterns or expansions that contribute nothing to the output.
- Choose a `DISTINCT`/aggregation strategy with smaller intermediate rows; compare plans using `WITH`.

However, if "users sharing products" strictly requires scanning **every interaction**, the engine must still traverse a massive relationship set. At that point, revisit the recommendation algorithm or data storage model.

### 5.1. Modeling Option: Storing Precomputed Similarity Edges

If product requirements allow recommendations without recomputing from raw views on every request, materialize summary edges:

~~~text
(:User)-[:SIMILAR_USER {
  score,
  calculatedAt,
  modelVersion
}]->(:User)
~~~

A batch job precomputes top similar users per user, e.g., storing at most 50 candidates per person. The read path becomes:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})
      -[r:SIMILAR_USER]->(other:User)
WHERE other.tenantId = $tenantId
  AND r.calculatedAt >= $minCalculatedAt
RETURN other.userId AS candidateId,
       r.score AS similarityScore,
       r.calculatedAt AS calculatedAt
ORDER BY similarityScore DESC, candidateId ASC
LIMIT 10;
~~~

Read-time input size is bounded by the **maximum stored similarity edges** per `User`, provided the write job enforces that cap. `ORDER BY` is still needed for top 10 selection, but ranks a tiny candidate set. Trade-offs:

| Benefit | Cost / Limitation |
| --- | --- |
| Far fewer relationships read per request. | Must build and run the scoring pipeline first. |
| Candidate count per user can be capped. | Results may miss brand-new candidates or truncate at top-K. |
| Easy to cache across requests. | Must handle updates, expiration, deleted users, and permissions. |
| Decouples analytics load from online queries. | Consumes extra edge storage and operational effort. |

This is an **operational semantics change**: scores reflect a snapshot in time, carry a model version, and have refresh lag. If business rules demand real-time accuracy across every interaction, never replace a live query with precomputed state without stakeholder sign-off.

## 6. Model Refactoring Options and When to Use Them

| Situation | Option to Consider | Mandatory Trade-Off |
| --- | --- | --- |
| One node connects millions of nodes just for key lookup. | Look up items via label + property index, bypassing the hub. | Must enforce keys and tenant boundaries properly. |
| A relationship stores repeated interactions while queries ask "ever." | Maintain a single business summary edge; keep events if history is needed. | Must sync summary with events and handle write races. |
| Deep multi-hop paths are expensive and queried repeatedly. | Precompute shortcut links or top-K candidate sets. | Data can lag; adds write and refresh workload. |
| Low-churn attributes modeled as separate nodes. | Store as properties on the source node when domain-appropriate. | Loses ability to attach independent links to that concept. |
| Reading current state requires scanning full history. | Store current state alongside history. | Must guard consistency and support retroactive edits. |
| One label mixes distinct sub-entities, making filters unselective. | Evaluate meaningful labels/types, indexes, and new entry points. | Schema management, ingestion, and label consistency overhead. |
| Multi-tenant queries routinely fan out past intended scope. | Include tenant keys on access paths and tenant-scoped structures. | Must enforce security, tenant migration, and valid cross-tenant rules. |

**Principle:** changing the model does not necessarily mean adding more nodes. Sometimes the best move is **removing a relationship**, **adding a property**, or **keeping a pre-aggregated subset**. Choose based on the questions your application actually needs to answer.

## 7. Data Models Can Change Results, Not Just Speed

Optimizing via structural changes always requires verifying *business equivalence*.

### 7.1. Does Collapsing Edges Lose Events?

Replacing ten `VIEWED {at}` relationships with one `HAS_VIEWED {count: 10}` still answers "has ever viewed," yet "viewed at 9 AM vs. 10 PM" cannot be reconstructed from `count` alone. If keeping separate events, define the system of record and how summaries are rebuilt on drift.

### 7.2. Do Shortcuts Preserve Access Control?

A `SIMILAR_USER` edge computed across multi-tenant data could accidentally leak links between user groups. Even with `WHERE other.tenantId = $tenantId`, audit how the batch job creates edges, how permissions are checked on both endpoints, and how revocations propagate. A shortcut is valid only when **the new relationship reflects the exact security boundaries** of the underlying data.

### 7.3. Does Moving Current Price onto Product Break Order History?

An order must record price **at purchase time**, independent of later changes to `Product.currentPrice`. Hence `(:OrderLine {unitPriceAtPurchase})` is often distinct from `Product.currentPrice`. This is not wasteful duplication: the two prices represent two distinct facts.

### 7.4. Does Removing an Intermediate Node Lose Relationship Context?

Model:

~~~text
(:Order)-[:HAS_LINE]->(:OrderLine {
  quantity, unitPriceAtPurchase
})-[:OF_PRODUCT]->(:Product)
~~~

Storing `OrderLine` as a node preserves quantity and price per line item, even when a product appears across many orders. Collapsing it to `(:Order)-[:CONTAINS]->(:Product)` without keeping those properties loses business data. If choosing `CONTAINS {quantity, unitPriceAtPurchase}` instead of a node, verify whether line items need their own identity, history, discounts, returns, or extra relationships.

Therefore, model optimization must go hand in hand with **modeling facts accurately**, not merely shaving off hops.

## 8. When Is Query Tuning Still the Right First Step?

Never use "bad model" as an excuse to ignore an easily fixable query. Several query-level changes slash work without touching schema:

### 8.1. Start from a Selective Node

When the user is known, look up by user key and expand outward rather than scanning all `VIEWED` edges before filtering user:

~~~cypher
MATCH (u:User {tenantId: $tenantId, userId: $userId})-[:VIEWED]->(p:Product)
RETURN p.sku AS sku
ORDER BY sku ASC;
~~~

An index on `User(tenantId, userId)` supports locating the source node. Still check the actual plan: if a single user viewed a huge number of products, traversed edge volume can remain substantial.

### 8.2. Eliminate Unintended Row Multiplication

Two independent patterns create a Cartesian product:

~~~cypher
MATCH (u:User {userId: $userId}),
      (p:Product)
RETURN u.userId AS userId, p.sku AS sku
LIMIT 10;
~~~

If you need products **that user actually viewed**, adding the relationship pattern and tenant condition fixes both correctness and performance. Never use `LIMIT 10` to mask a disconnected `MATCH`.

### 8.3. Apply Bounds at the Right Stage

~~~cypher
MATCH (p:Product)<-[v:VIEWED]-(:User)
WITH p, count(v) AS viewCount
ORDER BY viewCount DESC, p.sku ASC
LIMIT 10
RETURN p.sku AS sku, viewCount
ORDER BY viewCount DESC, sku ASC;
~~~

This asks for the **top 10 most-viewed products across the entire dataset**. Neo4j still has to count views per product to rank them accurately; `LIMIT 10` after aggregation does not erase the cost of counting all relationships. If the business question only asks for "top products for tenant X in the last 24 hours," narrowing the query predicates can shrink input **provided the model stores tenant and timestamp where filtering can leverage them**.

### 8.4. Use Index Types for the Right Problem

Indexes help locate nodes by property, scan ranges, or accelerate text searches; constraints protect business keys. No index turns enumerating all valid multi-hop paths into a constant-time operation. Excessive indexing also increases write cost and storage footprint.

If a query already locates one node via an index and spends most of its work expanding relationships, shift focus from "what index should I add?" to "why must all these relationships be expanded?".

## 9. Evidence-Based Decision Process

A six-step workflow for a slow Neo4j query:

1. **Lock down business output:** which entities must be returned, for what time/tenant scope, and is real-time freshness required? Distinguish exact calculations from approximate top-K recommendations.
2. **Sample representative data metrics:** total nodes/relationships, per-tenant skew, top degrees, null/duplicate rates, history depth. Tiny dev datasets often hide production supernodes.
3. **Measure the current query:** record `PROFILE`, parameters, rows, DB Hits, app-side p50/p95/p99 latency, along with Neo4j version and configuration for fair comparison.
4. **Fix query-level causes first:** eliminate accidental Cartesian products, start from selective filters, use proper indexes, trim bloated projections. Re-measure on the same dataset.
5. **If unavoidable cost remains high, prototype a new model:** build on cloned data or fixtures—try summary/shortcut edges, split history, reduce fan-out—and document impacts on semantics and freshness.
6. **Run correctness and operational tests:** compare outputs across standard cases, read/write load, storage footprint, refresh cadence, tenant safety, backfill, and migration rollback.

### 9.1. Before/After Measurement Table

Before altering schema, prepare a table for **real measured metrics**, avoiding treating illustrative figures as benchmarks:

| Metric | Before Change | After Cypher/Index Fix | After Model Change |
| --- | --- | --- | --- |
| Read latency p50/p95 (ms) | *measure* | *measure* | *measure* |
| `Rows` at largest expansion step | *measure* | *measure* | *measure* |
| `DB Hits` | *measure* | *measure* | *measure* |
| Correctness on test suite | *measure* | *measure* | *measure* |
| Recommendation freshness lag | *measure* | *measure* | *measure* |
| Write speed and storage size | *measure* | *measure* | *measure* |
| Error rate / tenant security checks | *measure* | *measure* | *measure* |

Numbers should come from comparable data volumes, parameter sets, cache conditions, and hardware. Test normal users alongside power users, viral products, large tenants, and freshly written data. Optimizing only for "easy" queries can make p50 look great while leaving p99 broken.

### 9.2. Migration Cost Is Part of the Solution

When migrating from event-style `VIEWED` relationships to summary `HAS_VIEWED` edges, explicitly answer:

- How is historical data backfilled, and how are live events arriving during backfill captured/merged?
- How do concurrent workers avoid creating duplicate summary relationships?
- How long do both representations coexist, and what reconciliation checks verify consistency?
- How do application reads switch over, and if a bug forces rollback, is historical data intact?
- How do indexes, constraints, storage usage, and Java Driver/Spring Data Neo4j write paths change?

An optimization that speeds up a query while corrupting data or making operations fragile is not a successful optimization.

## 10. Case Study Exercises

### Exercise 1 — Diagnosing from PROFILE

A query finding 10 similar users produces the following plan profile (**hypothetical** figures):

| Stage | Output Rows |
| --- | ---: |
| Find user via index | 1 |
| Expand user → product | 24 |
| Expand product → other users | 320,000 |
| Filter tenant and exclude starting user | 110,000 |
| `Aggregation` by candidate | 5,000 |
| Top 10 | 10 |

Answer: which step causes the largest row explosion? Why wouldn't adding an index on `User.userId` solve it? Which questions about degree distribution, tenant skew, and `VIEWED` history should be verified before changing the model?

### Exercise 2 — Preserving Business Semantics

A team wants to replace all `VIEWED {at}` relationships with a single `HAS_VIEWED {count}` edge. List at least three queries that **keep equivalent results** (or can be derived from summary data) and three queries that **cannot be answered accurately** if event history is deleted. Propose a design keeping events and summaries without prolonged drift.

### Exercise 3 — Designing Top-10 per Tenant

A system has a popular topic node connected to millions of products across many tenants. Users need the 10 most recent products for **one tenant**. Propose two distinct access designs, sketch their Cypher, and explain how to verify `PROFILE` and tenant access control. Do not assume appending `LIMIT 10` automatically reduces traversed relationships.

### Exercise 4 — Evaluating Shortcuts

For `SIMILAR_USER` edges computed nightly, product now requires recommendations to reflect new behavior within at most five minutes. Can a nightly batch job satisfy this? Propose at least two architectural changes (e.g., incremental updates or blending precomputed edges with recent signals), then analyze costs and required tests.

### Exercise 5 — Deciding Between an OrderLine Node and a Relationship

An order can contain multiple line items, each holding quantity, price at purchase, and return info. The team wants to remove the `OrderLine` node to eliminate one hop. Identify which data can live on a relationship, which needs independent identity/links, and the correctness test suite required for migration.

## 11. Self-Check Questions Before Modifying the Model

When a query is repeatedly slow, check in order:

1. Is Neo4j already starting from a sufficiently selective node using an appropriate index?
2. Which operator produces the most `Rows` or `DB Hits`? How does that number scale with tenant, time, and node degree?
3. Does the query need only a small output yet have to read a massive relationship set under the current structure?
4. Does cost come from a few supernodes, unbounded history, or event-duplicated relationships?
5. Can we adjust the algorithm or store aggregated data while **preserving business invariants, access control, and freshness requirements**?
6. How will the new solution be benchmarked and tested, including write costs, migrations, and other queries sharing the model?

**Core takeaway:** the query determines **how** Neo4j traverses the graph; the data model determines **which paths and how many relationships exist to traverse**. When `PROFILE` reveals most work goes into expanding valid yet overwhelmingly dense relationships, tweaking `MATCH`/`WITH`/`LIMIT` alone hits a wall. Prove the bottleneck with data, then select a model change aligned with the business question and verify both performance and correctness.
