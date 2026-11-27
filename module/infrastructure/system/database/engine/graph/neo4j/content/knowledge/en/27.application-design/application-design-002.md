# Designing Use-Case-Driven Queries Instead of Loading the Entire Graph in Neo4j

## 1. Why Is "Fetch the Whole Graph and Filter in Java" a Dangerous Design?

Neo4j manages a **property graph** consisting of nodes, relationships, and properties. A graph database's strength lies in starting from a **well-defined entry point** and exploring only the links **relevant to the business question**, rather than always loading all nodes and relationships into application memory.

Suppose a B2B commerce platform has 20 million orders, 5 million customers, tens of millions of line items, and hundreds of millions of relationships. An order detail screen only needs:

> "Show the current customer order `o101` belonging to tenant `t1`, with the items in that exact order and its payment status."

If the application runs:

```cypher
// NOT suitable for a normal business API:
MATCH (n)
RETURN n;
```

and then loads all nodes into Java to search for the order, the application will face several problems:

- **Cost disproportionate to need:** the screen needs one order, yet the database and network must process data for the entire graph.
- **Java heap growth:** `Result.list()`, entity mapping, and serialization may hold millions of elements.
- **Increased storage reads:** scanning the graph can generate massive `DB Hits`, consuming page cache and CPU.
- **Increased data exposure risk:** loading customers/tenants outside the caller's access scope.
- **Hard pagination:** applying `LIMIT` at the end after expanding multiple relationships may limit **the number of rows**, not the number of orders.
- **Fails to leverage indexes purposefully:** fetching the entire graph keeps business-key indexes and constraints from doing their job.

Key principle: **query design starts from the use case, access boundaries, API output, and allowable payload size**. Only then do you decide labels, relationships, traversal direction, indexes, pagination strategy, and Java/Spring Data Neo4j mapping style.

## 2. Going from Screen/API Requirements to "Data Shape"

Before writing Cypher, create a **query contract** for each use case.

| Use Case | Starting Point | Relationships to Traverse | API Output | Limits |
| --- | --- | --- | --- | --- |
| View customer's order list | `tenantId` + `customerId` | `Customer-[:PLACED]->Order` | ID, created date, status | Max 20–50 orders/page |
| View single order details | `tenantId` + `customerId` + `orderId` | `Order-[:HAS_LINE]->Product` | Order info and line items | One order, line count bounded by business rules |
| Top-selling products stats | Tenant and date range | `Order-[:HAS_LINE]->Product` | SKU and total quantity | Top N, consider pre-aggregation |
| Check if customer may view order | Authenticated identity + tenant | `Customer-[:PLACED]->Order` | Boolean or allowed ID | Single target object |
| PageRank analysis on supplier network | A selected set of labels/relationship types | Entire or major portion of analysis graph | Score per node | Use a separate analytics/GDS job |

**Data shape** (*result shape*) is the design of the returned data: a single object, a short list, a summary, or a large stream. Never return full nodes and all relationships just to pick two properties.

### The 6-Question Process

1. **Who is requesting?** End user, internal service, analytics job; which tenant and role?
2. **What is the root entity?** By which keys is the customer/order/product identified?
3. **How many hops are needed?** Which relationship types, which direction, and are depth and fan-out bounded?
4. **Which properties are needed?** Which fields serve the API, report, or UI?
5. **What are the bounds?** `LIMIT`, time range, pagination, sampling, max depth, timeout.
6. **Consistency requirement?** Latest transactional data, snapshot reporting, or batch-updated read model?

In many cases, **one use case corresponds to one optimized read query**, rather than "loading a complete aggregate object" in an ORM.

## 3. Practical Graph Model: Customers, Orders, and Products

### 3.1. Schema Serving Access Paths

Suppose the system has:

```text
(:ShopCustomer {tenantId, customerId, name})
          |
        PLACED
          |
          v
(:ShopOrder {tenantId, orderId, customerId, createdAt, status})
          |
        HAS_LINE {quantity, unitPrice}
          |
          v
(:ShopProduct {tenantId, sku, title})
```

In this model:

- `ShopCustomer` belongs to a tenant, identified by the pair `(tenantId, customerId)`.
- `ShopOrder` has the key pair `(tenantId, orderId)`; `customerId` is additionally stored to support **a direct index-backed read access path**.
- `HAS_LINE` stores quantity and unit price at purchase time; this price differs from `ShopProduct`'s current listed price.
- The `PLACED` relationship preserves business linkage semantics, enabling verification of which customer owns an order.
- All queries start from the **tenant resolved from the authenticated identity**, never trusting an arbitrary `tenantId` passed by the client.

This is an illustrative model: if an order has **multiple lines for the same SKU**, `OrderLine` should be modeled as a node with its own `lineId` or an appropriate line-identification mechanism, instead of assuming only one `HAS_LINE` relationship between a pair of nodes.

### 3.2. Use-Case-Driven Constraints and Indexes

```cypher
CREATE CONSTRAINT shop_customer_key IF NOT EXISTS
FOR (c:ShopCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT shop_order_key IF NOT EXISTS
FOR (o:ShopOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT shop_product_key IF NOT EXISTS
FOR (p:ShopProduct)
REQUIRE (p.tenantId, p.sku) IS UNIQUE;
```

To fetch the latest order list using properties directly on the `ShopOrder` node:

```cypher
CREATE RANGE INDEX shop_order_customer_feed IF NOT EXISTS
FOR (o:ShopOrder)
ON (o.tenantId, o.customerId, o.createdAt, o.orderId);
```

To summarize orders by status/time range, you can also evaluate:

```cypher
CREATE RANGE INDEX shop_order_status_time IF NOT EXISTS
FOR (o:ShopOrder)
ON (o.tenantId, o.status, o.createdAt);
```

**Do not create every index just because it "might be used."** Indexes carry storage and write maintenance costs. Keep only indexes for access paths measured as necessary; check `SHOW INDEXES` and `EXPLAIN`/`PROFILE`. If a query starts from `ShopCustomer` and traverses `PLACED`, the planner will not necessarily use the `shop_order_customer_feed` index.

### 3.3. Repeatable Test Data

Create customers:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', name: 'An'},
  {tenantId: 't1', customerId: 'c2', name: 'Binh'},
  {tenantId: 't2', customerId: 'c1', name: 'T2 Customer'}
] AS row
MERGE (c:ShopCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
SET c.name = row.name;
```

Create products:

```cypher
UNWIND [
  {tenantId: 't1', sku: 'sku01', title: 'Keyboard'},
  {tenantId: 't1', sku: 'sku02', title: 'Mouse'},
  {tenantId: 't1', sku: 'sku03', title: 'Monitor'}
] AS row
MERGE (p:ShopProduct {tenantId: row.tenantId, sku: row.sku})
SET p.title = row.title;
```

Create orders and customer relationships:

```cypher
UNWIND [
  {tenantId: 't1', customerId: 'c1', orderId: 'o101',
   at: '2026-10-03T09:30:00+07:00', status: 'PAID'},
  {tenantId: 't1', customerId: 'c1', orderId: 'o102',
   at: '2026-10-04T11:00:00+07:00', status: 'NEW'},
  {tenantId: 't1', customerId: 'c2', orderId: 'o103',
   at: '2026-10-05T08:00:00+07:00', status: 'PAID'}
] AS row
MATCH (c:ShopCustomer {
  tenantId: row.tenantId,
  customerId: row.customerId
})
MERGE (o:ShopOrder {tenantId: row.tenantId, orderId: row.orderId})
SET o.customerId = row.customerId,
    o.createdAt = datetime(row.at),
    o.status = row.status
MERGE (c)-[:PLACED]->(o);
```

Create line items:

```cypher
UNWIND [
  {orderId: 'o101', sku: 'sku01', quantity: 2, unitPrice: 550000},
  {orderId: 'o101', sku: 'sku02', quantity: 1, unitPrice: 250000},
  {orderId: 'o102', sku: 'sku03', quantity: 1, unitPrice: 3000000},
  {orderId: 'o103', sku: 'sku01', quantity: 1, unitPrice: 550000}
] AS row
MATCH (o:ShopOrder {tenantId: 't1', orderId: row.orderId})
MATCH (p:ShopProduct {tenantId: 't1', sku: row.sku})
MERGE (o)-[line:HAS_LINE]->(p)
SET line.quantity = row.quantity,
    line.unitPrice = row.unitPrice;
```

In a clean test database, `t1` has 2 customers, 3 orders, and 4 `HAS_LINE` relationships. Using `MERGE` prevents duplicating sample relationship pairs when re-running, but it does not replace constraints for concurrent writes or complex line-item models.

## 4. Use Case 1 — Order List: Anchored Query with Compact Output

### 4.1. Counter-Example: Fetching All Orders System-Wide

```cypher
// Bad query for ONE customer's order screen:
MATCH (o:ShopOrder)
RETURN o;
```

Even if Java filters only orders where `customerId = 'c1'`, the database still has to send all orders. In a multi-tenant graph, this also increases data leakage risk.

### 4.2. Approach 1: Start from Customer and Traverse One Relationship Type

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)
WHERE o.tenantId = $tenantId
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Example parameter values:

```json
{
  "tenantId": "t1",
  "customerId": "c1",
  "limit": 20
}
```

This statement:

- Uses a **specific business key** to anchor the query to a single customer.
- Traverses only the **`PLACED` relationship in the right direction**.
- Returns only the **three properties** needed by the UI instead of entire nodes.
- Orders deterministically using `orderId` as a tie-breaker when multiple orders share a timestamp.
- Bounds the result count; the API must **validate limit** (e.g., between 1 and 50).

### 4.3. Approach 2: Direct Order Lookup via Read Path

If a customer has **very many orders**, consider querying directly via properties stored on the `ShopOrder` node:

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

The composite index `(tenantId, customerId, createdAt, orderId)` **can help filter and leverage sort order** when leading properties are equality-constrained. The planner decides based on statistics/cost; verify with `EXPLAIN` and `PROFILE`.

**Modeling trade-off:** `customerId` on the order is a **denormalized** property alongside the `PLACED` relationship. The application must keep both representations consistent inside write transactions, especially if business rules allow order ownership transfers. If that complexity is unacceptable, use the index-anchored customer traversal path or build a separate read model.

**Security:** querying directly by `customerId` is safe only when the value is derived/verified from identity and authorization. A customer must never be allowed to alter `customerId` in the URL to view someone else's orders. Filtering by `tenantId` alone is insufficient when multiple customers share a tenant.

## 5. Use Case 2 — Order Details and Line Items: Bounded Expansion

For `GET /orders/{orderId}`, we typically need one order and its list of items:

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
OPTIONAL MATCH (o)-[line:HAS_LINE]->(p:ShopProduct)
WHERE p.tenantId = $tenantId
WITH o, line, p
ORDER BY p.sku
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status,
  collect(
    CASE WHEN p IS NOT NULL THEN {
      sku: p.sku,
      title: p.title,
      quantity: line.quantity,
      unitPrice: line.unitPrice
    } END
  ) AS items;
```

**Why is this a use-case-driven query?**

1. The first `MATCH` simultaneously anchors **tenant, customer, and order**, enforcing the ownership boundary.
2. `OPTIONAL MATCH` fetches items for **just that single order**, without expanding the entire product graph.
3. `collect(...)` gathers line items into **a single list** for the DTO. Cypher's `collect` skips `null` values, so when there are no items it returns `[]` instead of a `[null]` element.
4. Properties are explicitly projected; there is no need for `RETURN c, o, p` when the UI does not display full nodes.

**Business note:** an order's line-item list can grow large. If there can be thousands of items or change history, design the API to **paginate line items separately** rather than always packing them into one huge response.

### N+1 Queries in Java Processing

A common anti-pattern:

1. Query 1 fetches 20 orders.
2. Java loops over the 20 orders, firing one extra query per order to fetch line items.
3. Total: **21 round-trips** to Neo4j for a single screen.

Ways to reduce N+1:

- If the screen only needs summaries, **do not load line items**.
- If the screen needs line items for 20 orders, select the 20 orders first, then expand and collect line items in **one bounded query**.
- If line items are numerous, use **two batched queries** (query the order list, then query all line items for that authorized set of IDs). Two round-trips are sometimes easier to bound in memory and cache than one query with a giant `collect`.

**Do not assume "fewer queries is always better"**: one giant query with multiple one-to-many branches can produce a Cartesian product and consume more resources than a few well-designed small queries.

## 6. Paginating **Before** Expanding Relationships

### 6.1. Mistake: Limiting Rows After Joining

```cypher
// Can cut line items mid-order and return fewer than $limit orders:
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)-[:HAS_LINE]->(p:ShopProduct)
RETURN o.orderId AS orderId, p.sku AS sku
ORDER BY orderId DESC
LIMIT $limit;
```

If an order has 30 product lines, `LIMIT 20` above may return **20 lines from a single order**, rather than 20 orders. Expanding relationships before `LIMIT` can also generate many intermediate rows.

### 6.2. Better: Select the Order Page First, Then Fetch Line Items

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:PLACED]->(o:ShopOrder)
WHERE o.tenantId = $tenantId
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit
OPTIONAL MATCH (o)-[line:HAS_LINE]->(p:ShopProduct)
WHERE p.tenantId = $tenantId
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status,
  collect(
    CASE WHEN p IS NOT NULL THEN {
      sku: p.sku,
      quantity: line.quantity
    } END
  ) AS items
ORDER BY createdAt DESC, orderId DESC;
```

`WITH ... ORDER BY ... LIMIT` bounds the **order nodes** before expanding `HAS_LINE`. The result corresponds to at most `$limit` orders (assuming no model-violating data attaches an order to a customer multiple times), each with an items list.

Notes:

- `LIMIT` on the order page **does not bound the number of line items inside one order**. If a single order has 100,000 lines, `collect` can still consume substantial memory.
- `ORDER BY` before `LIMIT` may need to inspect/sort many orders if the plan does not leverage index order; a small output count **does not guarantee low read cost**.
- If item ordering is required, add an appropriate sorting step before `collect` and inspect the plan; the final `ORDER BY` only sorts **orders**.
- If data is concurrently inserted or modified, multiple paginated requests do not automatically form a consistent snapshot of the entire list.

## 7. When Lists Are Very Large: Offset vs. Keyset Pagination

### 7.1. Offset Using `SKIP`

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId DESC
SKIP $skip
LIMIT $limit;
```

This approach is simple for pages near the beginning. However, a page with `SKIP 500000` can force the engine to inspect huge numbers of candidates before reaching the next page. When orders are inserted or deleted between calls, offset pagination easily causes users to see **duplicate or skipped** items.

### 7.2. Keyset (Seek) Pagination

Use the cursor pair from the last record of the previous page: `(createdAt, orderId)`. With descending order, the next page only fetches records lexicographically smaller than the cursor:

```cypher
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
WHERE o.createdAt < datetime($cursorTime)
   OR (
      o.createdAt = datetime($cursorTime)
      AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Example cursor built from the previous page's last record:

```json
{
  "tenantId": "t1",
  "customerId": "c1",
  "cursorTime": "2026-10-04T11:00:00+07:00",
  "cursorOrderId": "o102",
  "limit": 20
}
```

The first page does not use a cursor `WHERE`; the application should maintain **two separate queries** for first/next pages, keeping predicates clear and easier for the planner to optimize than one query full of `OR $cursor IS NULL`.

Points to ensure:

- `orderId` is a unique **tie-breaker** within the tenant/customer scope per the model. Otherwise, two orders with the same `createdAt` could be skipped.
- Cursors must be validated/formatted server-side; never interpolate user input directly into Cypher strings.
- Keyset pagination generally avoids deep offset skipping costs and reduces duplicates/omissions from inserts **before the cursor**, yet it **is not snapshot isolation across multiple requests**. Changing sort keys, deletions, or status updates can still change results.
- With compatible types for `createdAt` and `orderId`, inspect `PROFILE` to verify whether an index assists both filtering and ordering; multi-branch `OR` predicates can alter planner choices.

## 8. Avoiding Row Multiplication Across Multiple One-to-Many Branches

Suppose we need to display a customer's **order count** and **favorited product count**. Joining both branches simultaneously:

```cypher
// Easily blows up row counts by the product of both branches:
MATCH (c:ShopCustomer {tenantId: $tenantId, customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:ShopOrder)
OPTIONAL MATCH (c)-[:FAVORITED]->(p:ShopProduct)
RETURN c.customerId,
       count(o) AS orderCount,
       count(p) AS favoriteCount;
```

If the customer has 10 orders and 5 favorited products, the intermediate stream can become **50 rows**. Both `count(o)` and `count(p)` can be inflated—not only slow, but **business-wise wrong**.

In Cypher 5.23+, use **subqueries with variable scope** to aggregate each branch independently:

```cypher
MATCH (c:ShopCustomer {tenantId: $tenantId, customerId: $customerId})
CALL (c) {
  MATCH (c)-[:PLACED]->(o:ShopOrder)
  RETURN count(o) AS orderCount
}
CALL (c) {
  MATCH (c)-[:FAVORITED]->(p:ShopProduct)
  RETURN count(p) AS favoriteCount
}
RETURN c.customerId AS customerId, orderCount, favoriteCount;
```

The two `count` expressions compute over independent branches, avoiding Cartesian products. This form returns `0` for an empty branch in a non-grouping aggregation context. On older Neo4j/Cypher versions, use the version-appropriate `CALL { WITH c ... }` syntax.

**`count(DISTINCT o)` may fix the count but does not necessarily fix performance**, because row multiplication already occurred prior to deduplication. With two independent branches, separate subqueries usually express intent much more clearly.

## 9. Properly Designing Aggregation and Path Queries

### 9.1. Top-Selling Products Reads the Entire *Matching Set*

```cypher
MATCH (o:ShopOrder {tenantId: $tenantId, status: 'PAID'})
WHERE o.createdAt >= datetime($from)
  AND o.createdAt < datetime($to)
MATCH (o)-[line:HAS_LINE]->(p:ShopProduct {tenantId: $tenantId})
WITH p.sku AS sku, p.title AS title,
     sum(line.quantity) AS unitsSold
RETURN sku, title, unitsSold
ORDER BY unitsSold DESC, sku
LIMIT $top;
```

This query does not fetch "the whole graph," but it processes **all paid orders of a tenant within a date range**. Even when returning only the top 10, the engine may still have to read and sum **very many rows** before ranking.

If the dashboard is queried very frequently across hundreds of millions of rows, consider a **daily/monthly or per-SKU aggregated read model**, updated from write workflows/events with clear latency SLAs and reconciliation. This is a **use-case denormalization** choice, not a replacement for detailed operational reports.

### 9.2. Path Queries Require Type, Direction, and Depth

Dangerous query form on large graphs:

```cypher
// Avoid unbounded expansion unless truly necessary:
MATCH p = (a)-[*]-(b)
RETURN p;
```

Traversing paths with unbounded length and unanchored endpoints can generate massive path volumes; in cyclic graphs, candidate counts explode rapidly.

If the requirement is **"find up to three valid relationship hops from an authenticated customer"**, design an explicitly constrained pattern:

```cypher
MATCH (c:ShopCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
MATCH p = (c)-[:REFERRED_TO*1..3]->(other:ShopCustomer)
WHERE other.tenantId = $tenantId
RETURN other.customerId AS relatedCustomer, length(p) AS hops
ORDER BY hops, relatedCustomer
LIMIT 50;
```

The `REFERRED_TO` example is an **illustrative** relationship not present in the order dataset above. Before going to production:

- Specify a reasonable `max depth`, relationship types, and direction explicitly.
- Verify **intermediate** nodes also belong to the tenant if the graph mixes tenants; checking only the final node is insufficient to ensure the path does not cross into another tenant's data.
- Distinguish between **returning all paths**, **returning unique nodes**, and **returning a single shortest path**. Multiple paths can reach the same node; a trailing `LIMIT` does not prevent prior expansion work.
- Use bounded-path syntax suited to your deployed Cypher version, or dedicated GDS algorithms when appropriate.

**The use case defines the search space**, rather than writing the broadest `*` syntax possible and hoping `LIMIT` protects all resources.

## 10. Designing Indexes, Constraints, and Access Paths by Selectivity

Indexes help locate the **starting point**, while traversal follows graph links. An efficient query usually needs both.

| Use Case Type | Anchor and Predicate | Related Tooling | What to Verify |
| --- | --- | --- | --- |
| View order by ID | `ShopOrder(tenantId, orderId)` | Uniqueness constraint/index | `NodeIndexSeek`, input rows near 1 |
| Customer order list | `ShopOrder(tenantId, customerId)` + date order | Composite range index or traversal from `Customer` | Whether planner uses index/order or over-expands |
| Lookup customer by ID | `ShopCustomer(tenantId, customerId)` | Composite uniqueness constraint | Proper tenant/customer scoping |
| Search products by name | `ShopProduct.title` | Text/full-text index depending on query semantics | `CONTAINS` differs from full-text token search |
| Find pickup points near customer | `POINT` property + radius | Point index | CRS, distance, filtered node count |
| Find top-selling products | Tenant/status/time, aggregate | Range index or read model | Row-reading cost before `ORDER BY ... LIMIT` |
| Traverse recommendation network | Anchor node, rel type/direction, depth | Indexes and traversal/GDS as needed | Fan-out, cycles, uniqueness, tenant boundary |

Indexes do not automatically assist every predicate:
- An index on `o.createdAt` may not optimize a query filtering simultaneously on tenant and customer.
- Composite indexes generally help when leading properties are explicitly constrained; use `EXPLAIN` rather than guessing plans solely from column order.
- A query returning each order with all its products still has to traverse all relationships connected to the order, even if the starting node is found via an index.
- A uniqueness constraint prevents duplicate keys, unlike a range index which is only for lookup speed.

## 11. Java Driver API Design: Return Lean DTOs, Not the Whole Graph

### 11.1. Order List Endpoint Example

Assume the application layer has authenticated the user and resolved `tenantId` and `customerId` from identity/authorization, and holds a shared `Driver driver` instance.

```java
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record OrderSummary(
    String orderId,
    ZonedDateTime createdAt,
    String status
) {}

static List<OrderSummary> findOrders(
        Driver driver,
        String tenantId,
        String customerId,
        int requestedLimit) {

    int pageSize = Math.max(1, Math.min(requestedLimit, 50));

    String cypher = """
        MATCH (o:ShopOrder {
          tenantId: $tenantId,
          customerId: $customerId
        })
        RETURN o.orderId AS orderId,
               o.createdAt AS createdAt,
               o.status AS status
        ORDER BY createdAt DESC, orderId DESC
        LIMIT $limit
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {

        return session.executeRead(tx ->
            tx.run(cypher, Map.of(
                "tenantId", tenantId,
                "customerId", customerId,
                "limit", pageSize
            )).list(record -> new OrderSummary(
                record.get("orderId").asString(),
                record.get("createdAt").asZonedDateTime(),
                record.get("status").asString()
            ))
        );
    }
}
```

With at most 50 rows, `list()` is a sensible choice. Results are consumed **inside the transaction**, and then the session is closed. Tenant and customer must be authenticated/authorized at the API layer; never treat those two values as trustworthy access keys just because they are passed as parameters.

**Do not write:**

```java
// Anti-pattern for endpoints with large datasets:
var allRecords = session.run("MATCH (n) RETURN n").list();
// Only then search for orderId, filter tenant, and build JSON in Java.
```

That shifts database work onto Java, introducing unnecessary I/O, heap pressure, and authorization risk.

### 11.2. Large Results: Controlled Streaming

The Java Driver provides ways to consume a `Result` record by record instead of calling `list()`. Illustrative example for exporting a tenant report:

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    session.executeReadWithoutResult(tx -> {
        var result = tx.run(
            """
            MATCH (o:ShopOrder {tenantId: $tenantId})
            RETURN o.orderId AS orderId
            ORDER BY orderId
            """,
            Map.of("tenantId", "t1")
        );

        while (result.hasNext()) {
            var record = result.next();
            // Write each row to a sink with bounded backpressure/buffering.
            System.out.println(record.get("orderId").asString());
        }
    });
}
```

This illustration avoids buffering the entire output into a `List`, yet it still holds **a long-lived read transaction**; for millions of records, consider splitting into batches/keyset pages, bounding timeouts, and limiting sink write volume. Managed transaction callbacks can retry on transient errors, so **never put non-idempotent side effects** (such as emitting rows to an external system) inside the callback assuming it runs only once.

For real data exports, a separate batch job is usually safer than a user-facing endpoint holding an HTTP connection open for a long time. Client-side "streaming" does not turn a full-scan query into a cheap operation on the server.

### 11.3. Round-Trip Cost

An application can be slow not only due to DB Hits, but also because of:

- 20 queries fetching 20 product groups (**N+1**).
- 20 connection acquisitions and Bolt round-trips.
- Queries returning too many properties, huge JSON, and CPU-heavy serialization.
- Each query running in a separate transaction, stretching session duration or lock retention.
- The controller waiting for all data before returning any response.

Choose **one query returning the exact shape** or **a purposeful small number of batched queries**; use sync, async, or reactive Java Driver APIs according to your stack, while still writing proper Cypher.

## 12. Spring Data Neo4j: Entity Mapping Does Not Replace Read Model Design

Spring Data Neo4j maps nodes/relationships into objects and manages transactions, yet **a read screen does not necessarily need to load a full entity tree**.

There are three common approaches:

| Need | Design Approach |
| --- | --- |
| Updating small aggregates with clear boundaries | Entities and `Neo4jRepository`/template |
| List, filter, and paginated endpoints | `@Query` returning an appropriate projection/DTO or `Neo4jClient` |
| Analytics dashboards, flat data | Custom Cypher returning scalars/maps/DTOs, avoiding unnecessary entity-graph hydration |

Example custom query in a repository (illustrative):

```java
interface OrderReadRepository
        extends org.springframework.data.repository.Repository<
            ShopOrderEntity, String> {

    @org.springframework.data.neo4j.repository.query.Query("""
        MATCH (o:ShopOrder {
          tenantId: $tenantId,
          customerId: $customerId
        })
        RETURN o.orderId AS orderId,
               o.status AS status
        ORDER BY o.createdAt DESC, o.orderId DESC
        LIMIT $limit
        """)
    java.util.List<OrderSummaryProjection> findSummaries(
        String tenantId,
        String customerId,
        long limit
    );
}
```

With a projection interface `OrderSummaryProjection` declaring `getOrderId()` and `getStatus()`, **verify scalar/projection mapping support in the exact Spring Data Neo4j version in use**. When complex DTO structures or multiple `collect` branches are needed, use `Neo4jClient` with explicit mapping rather than assuming nested maps are automatically bound properly by the repository.

Notes:

- `@Relationship` on entities can cause over-fetching of the graph when repositories return large aggregates. Inspect framework-generated queries whenever performance matters.
- Do not attach a "very high-degree" relationship to an entity and repeatedly call `findById` just to read 2–3 properties.
- Separate the **write model** (business integrity) and **read model** (serving use-case data) when the two access patterns diverge significantly.
- In reactive services, use `ReactiveNeo4jClient`/reactive repositories properly; never invoke blocking repositories on an event loop and expect non-blocking behavior.
- If using `Driver` directly inside a service, that transaction does not automatically join a Spring Data Neo4j transaction simply because the calling method has `@Transactional`; design transaction boundaries explicitly.

## 13. Security and Query Bounds Are Part of Use-Case Design

### 13.1. Enforce Tenant Scope at the First Access Step

Do not build a query starting from `MATCH (o:ShopOrder)` and filter permissions in Java. Instead:

- Place `tenantId` in Neo4j's pattern/`WHERE` clause.
- Use `customerId` bound to the current user or verify order access.
- Control cross-tenant relationships; if the graph permits cross-tenant links, check **every intermediate node/edge** in sensitive paths.
- Use appropriate Neo4j permissions (RBAC, database access, data protection model) as an additional defense layer.

**Never treat `LIMIT 20` as an authorization control.** It only caps output size; an unfiltered query missing tenant scope can still return 20 unauthorized orders.

### 13.2. Do Not Let the API Allow Arbitrary Graph Queries

Parameters that should be tightly controlled by the application:

| Parameter | Recommended Use-Case Bound |
| --- | --- |
| `limit` | Small threshold for interactive pages, e.g., `1..50` |
| `maxDepth` | Finite bound matching the problem; never accept unchecked input |
| `sortBy` | Allowlist of valid columns/properties; never concatenate free-form strings into Cypher |
| Time range | Max range; prevent multi-year scans when the UI needs one month |
| Filters/labels/types | Allow only defined schema elements; avoid building arbitrary patterns from input |
| Timeout | Set at API/driver/transaction layers matching SLOs |
| Page cursor | Verify signature/type and bind to the corresponding user/tenant/query |

Certain Cypher syntax elements such as labels or property names **cannot be substituted directly with value parameters in all contexts**. If the application must support dynamic sorting, use a **Java allowlist**, never interpolating raw input into query strings.

### 13.3. Overload and Concurrency

A "logically correct" query can still overload the cluster when 1,000 concurrent users invoke it and each execution traverses millions of relationships. You must have:

- Rate limits / concurrency limits.
- Proper connection pools and timeouts.
- Metrics: p50/p95/p99, DB Hits, Rows, CPU, page cache.
- Data volume bounds and per-request query caps.
- Caches/read models for frequently queried, rarely changing use cases.

## 14. Using `EXPLAIN` and `PROFILE` to Verify the Design

Verifying correct results **is not enough**. Inspect the access path:

```cypher
EXPLAIN
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Then measure on a test database or under controlled load:

```cypher
PROFILE
MATCH (o:ShopOrder {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

**Reading plans by use case:**

1. **Leaf operator:** `NodeIndexSeek`, `NodeIndexScan`, or `NodeByLabelScan`? Did the planner pick the expected index?
2. **Estimated Rows/Rows:** how many rows are produced before `LIMIT` and after `Expand` steps?
3. **DB Hits:** which operator accesses storage most? Do not confuse DB Hits with physical disk I/O count.
4. **Sort/Top:** does `ORDER BY` process many rows or leverage index ordering?
5. **Aggregation:** does `collect`/`count` buffer too much data or mask fan-out?
6. **Returned payload:** is the JSON/payload small and true to the API contract?
7. **Representative parameters:** both a customer with 1 order and a customer with 500,000 orders, and both warm/cold cache states when relevant.

**Do not assume a query that "only returns 20 rows" reads only 20 nodes.** `ORDER BY`, aggregations, and traversals may still process a huge dataset before `LIMIT` takes effect. Adding an index only helps when predicates match and the planner finds it beneficial.

### Sample Before/After Measurement Table

| Metric | Broad-Fetch Query | Use-Case Query |
| --- | --- | --- |
| Nodes/relationships examined | Measure with `PROFILE` | Re-measure with narrowed predicates |
| `Rows` at leaf/Expand | High or low? | Did it drop at the entry point? |
| `DB Hits` | How many? | Reduced via appropriate index and traversal? |
| Response size | MB/GB? | Only fields needed for the screen? |
| Latency p95 | Measured under specific conditions | Actual improvement observed? |
| Java Heap | Calling `list()` on everything? | Page-bounded and DTO-mapped? |
| Business correctness | Enforces tenant/authorization? | Matches the same contract |

Only compare queries with **the same goal and valid result set**. A query scanning all orders and a query returning one page are not two ways of doing **the exact same job**; what matters is evaluating whether the query fits **the right use case**.

## 15. When Is "Processing Almost the Entire Graph" Actually Right?

The use-case-driven query principle **does not forbid full-graph analytics**. The following tasks legitimately need to scan or analyze a large portion of the data:

| Task | Appropriate Tooling / Operation |
| --- | --- |
| PageRank/Louvain/Connected Components on link networks | Neo4j Graph Data Science; explicit projection, memory estimation, separate batch/job |
| One-time data migration | `neo4j-admin database import full` or planned import |
| Full data export for backup/ETL | Batched backup/export/streaming with resource bounds and permissions |
| Periodic read-model recomputation | Orchestrated batch aggregation job with checkpoints/idempotency |
| Large-scale data integrity checks | Offline/low-load reconciliation workflow, verification counts, resource monitoring |

The common thread is: **these are intentional use cases requiring broad-scope processing** with dedicated time/memory/priority budgets. Never turn an interactive user API into a silent full-graph analytics job.

## 16. Common Design Mistakes

| Anti-Pattern | Consequence | Replacement |
| --- | --- | --- |
| `MATCH (n) RETURN n` then filter in Java | Full scans, huge payloads, data-leak risk | Pattern anchored by ID/tenant/use case |
| `RETURN *` or returning unneeded nodes/relationships | Excessive serialization and mapping | Return scalars/maps/DTOs with needed fields |
| Unbounded `MATCH p=(a)-[*]-(b)` | Path explosion | Anchor node, relationship type/direction, hop bound |
| `LIMIT` after expanding multiple line items | Wrong order count, truncated lines | Paginate **orders first**, then expand |
| One line-item query **per order** | N+1 round-trips | Batched/grouped query when appropriate |
| Two independent one-to-many `OPTIONAL MATCH` clauses | Row multiplication and wrong `count` | Separate aggregation subqueries |
| Very large `SKIP` | High cost skipping rows, drift during writes | Keyset/cursor pagination |
| Duplicated properties without maintenance | Fast reads but stale/wrong data | Maintain inside transactions and test consistency |
| Missing business-key constraints | `MERGE`/concurrent writes risk duplicates | Uniqueness constraints |
| Relying on `LIMIT` as resource protection | Sort/aggregate/traversal can still be heavy | Narrow upfront, profile, bound depth/time |
| Trusting user-supplied `tenantId` alone | Horizontal access vulnerability | Authorization from identity and database policy |
| Returning large entity graphs from repositories | High heap usage, unneeded mapping/relations | Custom read query/projection |
| Heavy aggregation query on every request | High CPU, I/O, and latency | Pre-aggregate/read model with acceptable lag |
| Looking only at final returned row count | Misses intermediate Rows/DB Hits | `EXPLAIN`/`PROFILE` the full plan tree |

## 17. Pre-Production Checklist for a Neo4j-Backed API

1. **Contract:** what does the endpoint need, which fields, and are all relationships truly required?
2. **Authorization:** resolve tenant/customer/role from trusted identity, never arbitrary input.
3. **Graph shape:** specify starting node, relationship types and direction, and max depth.
4. **Cardinality:** estimate normal customers and high-degree customers; are any one-to-many branches multiplying rows?
5. **Projection:** return only needed fields; do not return graph objects when DTOs suffice.
6. **Pagination:** deterministic ordering, page-size cap, keyset pagination for deep lists.
7. **Indexes & constraints:** unique keys, query-aligned indexes, no speculative indexes.
8. **Transactions:** clear read/write boundaries, avoid N+1 and non-idempotent side effects under retries.
9. **Driver/SDN:** appropriate session per operation, consume within transaction lifetime; never collect unbounded results onto heap.
10. **Performance:** run `EXPLAIN` and `PROFILE` on representative samples, inspecting `Rows`, `DB Hits`, sorts, memory, and latency.
11. **Operational safety:** timeouts, connection pool sizing, concurrency limits, production observability.
12. **Correctness:** test other tenants, invalid IDs, orders with zero lines, many lines, and concurrent inserts/deletes during pagination.

## 18. Practice Exercises

1. Design a query for the screen "10 newest orders for customer `c1` in tenant `t1`"; return only `orderId`, `createdAt`, and `status`. Explain the anchor and sorting.
2. Write the detail query for `o101` returning the order and line items using `OPTIONAL MATCH` + `collect`. Try altering the query by placing `LIMIT 1` right after matching line items and explain why items get lost.
3. Write the order list with `LIMIT 20` in two ways: traversal from customer and direct query on `ShopOrder(tenantId, customerId)`. Use `PROFILE` to evaluate when a customer has hundreds of thousands of orders.
4. Create a customer with 5 orders and 7 `FAVORITED` relationships. Compare the counts when chaining two `OPTIONAL MATCH` clauses versus using two `CALL (c) { ... }` blocks.
5. Build a keyset cursor on `createdAt DESC, orderId DESC`; test two orders sharing the exact same timestamp and explain the role of the tie-breaker.
6. An API returns the top 5 SKUs but scans 100 million line items. Why is `LIMIT 5` insufficient to guarantee low latency? Propose an aggregated read model.
7. In a multi-tenant graph, identify a 3-hop pattern that could cross into another tenant. Design tenant enforcement on intermediate nodes as well.
8. A Spring Data Neo4j entity has a collection of 100,000 relationships. The screen only needs node name and status. Propose custom Cypher/DTOs instead of loading the full aggregate.
9. An export requires 10 million orders. Compare `Result.list()` with batched/keyset streaming; describe how to avoid repeating side effects on transaction retries.
10. Produce an `EXPLAIN`/`PROFILE` checklist for a query using `ORDER BY ... LIMIT`: which indexes, sorts, Rows, DB Hits, heap, and payload aspects must be inspected?

## 19. Takeaways

- **Design from use case → access key → relationship pattern → result shape → bounds → index → measurement**, never starting with `MATCH (n) RETURN n`.
- Use **constraint-backed business keys** to anchor queries, with explicit relationship types and directions to bound the graph region.
- **Return only properties the application needs**; paginate the right entity and avoid `LIMIT` cutting results prematurely after fan-out.
- With multiple one-to-many relationships, watch for **N+1**, **Cartesian products**, and aggregate per branch via subqueries.
- **Keyset pagination** helps on deep lists, yet still requires a unique sort key and awareness of concurrent mutations.
- **Indexes, constraints, and read models** must serve real use cases; denormalized properties require consistent maintenance.
- **Java Driver/Spring Data Neo4j** should not materialize the whole graph just to build a DTO; avoid N+1 and manage sessions/transactions carefully.
- Use **`EXPLAIN`/`PROFILE`** to measure intermediate rows, storage access, sorting, and performance. A trailing `LIMIT` does not guarantee the query processes little data.
- **Full-graph processing** is only justified when the use case itself is large-scale analytics, export, import, or reconciliation, backed by dedicated resources and operational controls.

### Official References

- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual — WITH](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/)
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Java Driver Manual — Simple queries](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j GDS — Graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
