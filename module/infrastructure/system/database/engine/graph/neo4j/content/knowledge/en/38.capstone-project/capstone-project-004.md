# Building a Suite of Read, Write, Aggregation, and Pathfinding Queries — Neo4j Capstone Project

## 1. Problem Statement and Expected Deliverables

This capstone requires building **a complete Cypher query suite** for a B2B commerce and logistics system using Neo4j. Instead of studying `MATCH`, `MERGE`, `WITH`, or `shortestPath` in isolation, you will solve business scenarios complete with **sample data, correctness constraints, result bounds, transactions, and clear test criteria**.

Context: a company has vendors, products, clients, orders, and transit depots. The Java / Spring Data Neo4j application needs to:

1. **Read**: query products by vendor, inventory by depot, and order lists/details by client.
2. **Write**: create orders and order lines by business key, prevent duplicates on application retries, and update status per business rules.
3. **Aggregate**: compute paid order counts, revenue by SKU/period, and high-value orders.
4. **Pathfind**: find the fewest-hop route and minimum-travel-time route between two depots, explaining when the two answers differ.
5. **Integrate**: map results to Java DTOs, manage sessions/transactions, enforce tenant isolation, and inspect performance via `EXPLAIN`/`PROFILE`.

This lesson is self-contained with domain rules, schema, seed data, and reference solutions. You can work through each section and compare against the explanations; neither GDS nor APOC is required for the core sections.

**Deliverables** for a real capstone submission: graph diagram, constraint/index and seed scripts; parameterized Cypher queries; Java API/repository code; expected result tables and negative tests; measured execution plans; and documentation of limitations and reset instructions.

> **Version scope:** core syntax follows Neo4j 5.23+ and current releases; Java examples use Java Driver 6.x and Java 17+; `CALL (variable)` syntax and GDS features depend on server version. When running against a different database, verify edition, privileges, and version compatibility. Never run write-test scripts on production data.

## 2. Turning Requirements into a Query Contract

Before creating nodes, define each query's **inputs, outputs, bounds, and invariants**.

| ID | Use case | Inputs | Outputs | Key invariant |
| --- | --- | --- | --- | --- |
| R1 | Order list by client | `tenantId, clientId, limit` | Most recent orders | Never leak other tenants'/clients' orders |
| R2 | Order details and lines | `tenantId, clientId, orderId` | Single order DTO with lines | Never multiply order totals |
| R3 | Depot stock and vendors | `tenantId, depotId, sku` | Product, stock count, vendors | Traverse only valid relationships |
| W1 | Create single-line order | Business keys, request ID, SKU, quantity, price | Order ID, line ID, and status | Retrying same request creates no duplicates |
| W2 | Transition order status | `tenantId, orderId, current status` | New status or rejection | Never mutate orders outside authorization |
| A1 | Top SKUs by revenue | `tenantId, from, to, topN` | SKU, units sold, total revenue | Count only `PAID` orders in window |
| A2 | Total per order | Tenant, date range | Order, total amount | Never multiply rows across joins |
| P1 | Fewest-hop route | Tenant, source/target depot, maxDepth | Depot list, hop count | Never traverse across tenants |
| P2 | Minimum-minute route | Tenant, source/target depot, maxDepth | Path, total minutes | Weight differs from hop count |

**Multi-tenant scope:** `tenantId` in every query must originate from an **authenticated and authorized identity**, never trusting a self-asserted client parameter. Example queries filter by tenant, yet query filters alone never replace full RBAC/authorization policies.

### 2.1. Lab Non-Functional Criteria

- Every read query returns the exact expected record count on the seed dataset—never run `MATCH (n) RETURN n` and filter in application code.
- List endpoints enforce an application-controlled `LIMIT` and deterministic ordering.
- Records use **business keys**, never `id(node)` or `elementId` as public API identifiers.
- Write queries use `MERGE`/constraints and **managed transactions** with input validation.
- Aggregation queries never load the entire graph into a Java `List`.
- Path queries bound traversal depth in Cypher variable-length patterns and recognize when to switch to GDS.
- Include at least one cross-tenant negative test, one missing-ID test, and one same-request retry test.

## 3. Property Graph Model for the Capstone

### 3.1. Nodes and Relationships

```text
(:CapClient {tenantId, clientId, name})
       |
    CAP_PLACED
       v
(:CapOrder {tenantId, orderId, clientId, requestId?, createdAt, status})
       |
    CAP_HAS_LINE
       v
(:CapLine {tenantId, lineId, orderId, sku, quantity, unitPrice})
       |
    CAP_OF_ITEM
       v
(:CapItem {tenantId, sku, title})
       ^
       | CAP_OFFERS
(:CapVendor {tenantId, vendorId, name})

(:CapDepot {tenantId, depotId, city})
    |  \ 
    |   \ CAP_ROUTE_TO {travelMinutes}
    |    ----------------------------> (:CapDepot)
    |
    +--[CAP_STOCKS {available}]--> (:CapItem)
```

| Label | Unique key within tenant | Core properties | Meaning |
| --- | --- | --- | --- |
| `CapClient` | `(tenantId, clientId)` | `name` | Purchasing client |
| `CapVendor` | `(tenantId, vendorId)` | `name` | Product supplier |
| `CapItem` | `(tenantId, sku)` | `title` | Product catalog item |
| `CapDepot` | `(tenantId, depotId)` | `city` | Warehouse / transit hub |
| `CapOrder` | `(tenantId, orderId)` | `clientId, status, createdAt, requestId?` | Order header |
| `CapLine` | `(tenantId, lineId)` | `orderId, sku, quantity, unitPrice` | Order line with price at purchase time |

**Why model `CapLine` as a node?** An order can contain multiple lines, even multiple lines for the same SKU across batches or prices. Using only a direct `Order-[:CONTAINS]->Item` edge and `MERGE`ing on endpoints could accidentally collapse two valid lines. Modeling `CapLine` as a node gives it a distinct key, clean quantitative properties, and straightforward testability.

**Why does `clientId` appear on both `CapOrder` and `CAP_PLACED`?** It acts as a denormalized lookup property for indexed order-feed queries. In exchange, every write must keep both representations consistent. In production, you may rely solely on relationships or build a dedicated read model depending on workload needs.

### 3.2. Data Semantics

- `quantity` is a positive integer.
- `unitPrice` is a non-negative integer in **VND**; avoid `float` for monetary amounts.
- `available` is an illustrative stock count on `CAP_STOCKS`, with **no concurrent reservation mechanism** in this foundational lab.
- `travelMinutes` is a positive integer edge weight; `CAP_ROUTE_TO` is **directed**.
- Order `status` belongs to a finite set such as `NEW`, `PAID`, `CANCELLED`.
- `createdAt` uses `DATETIME` (with timezone).
- `tenantId` must match across both endpoints of every business relationship; Neo4j does not enforce cross-node equality via simple uniqueness constraints.

## 4. Environment Setup and Execution Workflow

You can use Neo4j Browser, Cypher Shell, or Java Driver. For safety:

1. Use a **dedicated lab database**, never sharing with production data.
2. Create constraints and indexes before seeding so duplicate keys fail immediately.
3. Execute **each Cypher block in order**. The `UNWIND`/`MERGE` scripts are designed to re-run without duplicating nodes or endpoint-pair relationships.
4. Reconcile baseline counts **before running write operation W1**, or use a fresh lab dataset.
5. In Neo4j Browser, define parameters with Browser syntax, for example:

```cypher
:param tenantId => 't1'
:param clientId => 'c01'
:param limit => 20
```

`:param` is a **Browser command**, not valid Cypher to send via Java Driver; in Java, pass a `Map<String,Object>`. Queries below use `$` parameters, except seed scripts which use fixed literals.

### Data and Version Prerequisites

- Privileges to create constraints/indexes and read/write the lab database.
- A Cypher-compatible Neo4j database; foundational examples require neither APOC nor GDS.
- Java 17+ and Java Driver 6.x for the integration section.
- Prefer a `neo4j+s://...` connection string for secured services; self-managed local labs may use `bolt://localhost:7687` if configured accordingly.

## 5. Initializing Constraints and Indexes

### 5.1. Composite Uniqueness Constraints

Execute **six separate statements**:

```cypher
CREATE CONSTRAINT cap_client_key IF NOT EXISTS
FOR (n:CapClient)
REQUIRE (n.tenantId, n.clientId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_vendor_key IF NOT EXISTS
FOR (n:CapVendor)
REQUIRE (n.tenantId, n.vendorId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_item_key IF NOT EXISTS
FOR (n:CapItem)
REQUIRE (n.tenantId, n.sku) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_depot_key IF NOT EXISTS
FOR (n:CapDepot)
REQUIRE (n.tenantId, n.depotId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_order_key IF NOT EXISTS
FOR (n:CapOrder)
REQUIRE (n.tenantId, n.orderId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT cap_line_key IF NOT EXISTS
FOR (n:CapLine)
REQUIRE (n.tenantId, n.lineId) IS UNIQUE;
```

These constraints prevent two nodes in the same tenant from sharing a key. **Uniqueness does not require every node to possess the properties**: if business rules mandate existence, evaluate node-key/existence constraints for your edition or enforce presence in service/import validation.

### 5.2. Constraint for the Idempotency Key

To prevent two different requests from accidentally reusing a `requestId` within the same tenant:

```cypher
CREATE CONSTRAINT cap_order_request_key IF NOT EXISTS
FOR (n:CapOrder)
REQUIRE (n.tenantId, n.requestId) IS UNIQUE;
```

In the initial seed, historical orders have no `requestId`; the uniqueness constraint does not reject them simply because the property is absent. Orders created via API W1 will supply their own `requestId`.

### 5.3. Access-Path Indexes

```cypher
CREATE RANGE INDEX cap_order_client_feed IF NOT EXISTS
FOR (o:CapOrder)
ON (o.tenantId, o.clientId, o.createdAt, o.orderId);
```

```cypher
CREATE RANGE INDEX cap_order_paid_period IF NOT EXISTS
FOR (o:CapOrder)
ON (o.tenantId, o.status, o.createdAt);
```

The feed index supports plans querying a client's orders chronologically; the reporting index filters `PAID` orders by tenant and time window. **Neither guarantees the planner always selects the index or eliminates every sort**; inspect `EXPLAIN`/`PROFILE` on appropriately scaled data.

Verify:

```cypher
SHOW CONSTRAINTS;
```

```cypher
SHOW INDEXES;
```

## 6. Seeding Sample Data — Nodes

### 6.1. Clients

```cypher
UNWIND [
  {tenantId: 't1', clientId: 'c01', name: 'Linh'},
  {tenantId: 't1', clientId: 'c02', name: 'Minh'},
  {tenantId: 't2', clientId: 'c01', name: 'T2 Client'}
] AS r
MERGE (c:CapClient {
  tenantId: r.tenantId,
  clientId: r.clientId
})
SET c.name = r.name;
```

### 6.2. Vendors

```cypher
UNWIND [
  {tenantId: 't1', vendorId: 'v01', name: 'North Vendor'},
  {tenantId: 't1', vendorId: 'v02', name: 'South Vendor'},
  {tenantId: 't2', vendorId: 'v01', name: 'T2 Vendor'}
] AS r
MERGE (v:CapVendor {
  tenantId: r.tenantId,
  vendorId: r.vendorId
})
SET v.name = r.name;
```

### 6.3. Items

```cypher
UNWIND [
  {tenantId: 't1', sku: 'skuA', title: 'Keyboard'},
  {tenantId: 't1', sku: 'skuB', title: 'Mouse'},
  {tenantId: 't1', sku: 'skuC', title: 'Monitor'},
  {tenantId: 't2', sku: 'skuA', title: 'T2 Exclusive Item'}
] AS r
MERGE (p:CapItem {
  tenantId: r.tenantId,
  sku: r.sku
})
SET p.title = r.title;
```

### 6.4. Transit Depots

```cypher
UNWIND [
  {tenantId: 't1', depotId: 'HN', city: 'Hanoi'},
  {tenantId: 't1', depotId: 'DN', city: 'Da Nang'},
  {tenantId: 't1', depotId: 'SG', city: 'Ho Chi Minh City'},
  {tenantId: 't1', depotId: 'CT', city: 'Can Tho'},
  {tenantId: 't2', depotId: 'HN', city: 'T2 Dedicated Depot'}
] AS r
MERGE (d:CapDepot {
  tenantId: r.tenantId,
  depotId: r.depotId
})
SET d.city = r.city;
```

The IDs `HN`/`DN`/`SG`/`CT` are **fictional depot codes in the dataset**, not real coordinates or transit times. In particular, `travelMinutes` below is a synthetic algorithmic weight, not a real-world traffic estimate.

## 7. Seeding Sample Data — Supply and Route Relationships

### 7.1. Vendor Offers

```cypher
UNWIND [
  {tenantId: 't1', vendorId: 'v01', sku: 'skuA'},
  {tenantId: 't1', vendorId: 'v01', sku: 'skuB'},
  {tenantId: 't1', vendorId: 'v02', sku: 'skuC'},
  {tenantId: 't2', vendorId: 'v01', sku: 'skuA'}
] AS r
MATCH (v:CapVendor {
  tenantId: r.tenantId,
  vendorId: r.vendorId
})
MATCH (p:CapItem {tenantId: r.tenantId, sku: r.sku})
MERGE (v)-[:CAP_OFFERS]->(p);
```

### 7.2. Depot Stock Levels

```cypher
UNWIND [
  {depotId: 'HN', sku: 'skuA', available: 120},
  {depotId: 'DN', sku: 'skuA', available: 60},
  {depotId: 'SG', sku: 'skuB', available: 150},
  {depotId: 'CT', sku: 'skuC', available: 40}
] AS r
MATCH (d:CapDepot {tenantId: 't1', depotId: r.depotId})
MATCH (p:CapItem {tenantId: 't1', sku: r.sku})
MERGE (d)-[stock:CAP_STOCKS]->(p)
SET stock.available = r.available;
```

Re-running the seed executes `SET stock.available` and **resets inventory back to sample values**. That is intentional for a lab, yet **unsuitable for production seeding** alongside live inventory mutations.

### 7.3. Directed Shipping Route Network

```cypher
UNWIND [
  {from: 'HN', to: 'DN', travelMinutes: 60},
  {from: 'HN', to: 'SG', travelMinutes: 150},
  {from: 'DN', to: 'SG', travelMinutes: 60},
  {from: 'DN', to: 'CT', travelMinutes: 170},
  {from: 'SG', to: 'CT', travelMinutes: 45}
] AS r
MATCH (a:CapDepot {tenantId: 't1', depotId: r.from})
MATCH (b:CapDepot {tenantId: 't1', depotId: r.to})
MERGE (a)-[route:CAP_ROUTE_TO]->(b)
SET route.travelMinutes = r.travelMinutes;
```

Network diagram:

```text
HN ----60----> DN -----60----> SG -----45----> CT
 |              |                              ^
 |              +-------------170--------------+
 |
 +-------------------150-----> SG
```

The data is intentionally crafted so the **fewest-hop** path and the **lowest-total-minutes** path do not necessarily coincide. Edges are directed: `HN→DN` does not imply `DN→HN`.

## 8. Seeding Sample Data — Orders and Order Lines

### 8.1. Orders, Placing Clients, and Timestamps

```cypher
UNWIND [
  {tenantId: 't1', clientId: 'c01', orderId: 'o101',
   at: '2026-11-01T09:00:00+07:00', status: 'PAID'},
  {tenantId: 't1', clientId: 'c01', orderId: 'o102',
   at: '2026-11-02T09:00:00+07:00', status: 'PAID'},
  {tenantId: 't1', clientId: 'c02', orderId: 'o103',
   at: '2026-11-03T09:00:00+07:00', status: 'NEW'},
  {tenantId: 't2', clientId: 'c01', orderId: 'o201',
   at: '2026-11-02T09:00:00+07:00', status: 'PAID'}
] AS r
MATCH (c:CapClient {
  tenantId: r.tenantId,
  clientId: r.clientId
})
MERGE (o:CapOrder {tenantId: r.tenantId, orderId: r.orderId})
SET o.clientId = r.clientId,
    o.createdAt = datetime(r.at),
    o.status = r.status
MERGE (c)-[:CAP_PLACED]->(o);
```

### 8.2. Order Lines

```cypher
UNWIND [
  {tenantId: 't1', orderId: 'o101', lineId: 'l101a',
   sku: 'skuA', quantity: 2, unitPrice: 100000},
  {tenantId: 't1', orderId: 'o101', lineId: 'l101b',
   sku: 'skuB', quantity: 1, unitPrice: 50000},
  {tenantId: 't1', orderId: 'o102', lineId: 'l102a',
   sku: 'skuA', quantity: 1, unitPrice: 100000},
  {tenantId: 't1', orderId: 'o103', lineId: 'l103a',
   sku: 'skuC', quantity: 3, unitPrice: 200000},
  {tenantId: 't2', orderId: 'o201', lineId: 'l201a',
   sku: 'skuA', quantity: 4, unitPrice: 999000}
] AS r
MATCH (o:CapOrder {tenantId: r.tenantId, orderId: r.orderId})
MATCH (p:CapItem {tenantId: r.tenantId, sku: r.sku})
MERGE (li:CapLine {tenantId: r.tenantId, lineId: r.lineId})
SET li.orderId = r.orderId,
    li.sku = r.sku,
    li.quantity = r.quantity,
    li.unitPrice = r.unitPrice
MERGE (o)-[:CAP_HAS_LINE]->(li)
MERGE (li)-[:CAP_OF_ITEM]->(p);
```

**Note:** seed statements use `SET` to reproduce a deterministic demo state. Run only in a lab environment cleared for resets; seeding is not meant to preserve business edits made by later write tests.

### 8.3. Expected Baseline Counts

On a clean lab database containing only `Cap*` labels:

| Component | Tenant t1 | Tenant t2 |
| --- | ---: | ---: |
| `CapClient` | 2 | 1 |
| `CapVendor` | 2 | 1 |
| `CapItem` | 3 | 1 |
| `CapDepot` | 4 | 1 |
| `CapOrder` | 3 | 1 |
| `CapLine` | 4 | 1 |
| Total nodes per tenant | 18 | 6 |

In t1, there are 3 `CAP_PLACED`, 4 `CAP_HAS_LINE`, 4 `CAP_OF_ITEM`, 3 `CAP_OFFERS`, 4 `CAP_STOCKS`, and 5 `CAP_ROUTE_TO` relationships.

Verify counts by label/tenant:

```cypher
MATCH (n)
WHERE n:CapClient OR n:CapVendor OR n:CapItem
   OR n:CapDepot OR n:CapOrder OR n:CapLine
RETURN n.tenantId AS tenantId, count(*) AS nodeCount
ORDER BY tenantId;
```

**Expected:** `t1 = 18` and `t2 = 6` before running new order creation and without leftover lab records. After exercise W1, t1's node count grows; verify against **specific seeded IDs** rather than relying rigidly on totals.

## 9. R1 — Reading a Client's Order List

Requirement: fetch up to 20 orders for client `c01` in tenant `t1`, newest first.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN
  o.orderId AS orderId,
  o.createdAt AS createdAt,
  o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

Parameters:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "limit": 20
}
```

Result on seed data:

| orderId | status | Position |
| --- | --- | --- |
| `o102` | `PAID` | Newer |
| `o101` | `PAID` | Older |

Must never include `o103` (belongs to c02) or `o201` (belongs to t2).

### Why Is This Better Than Loading the Whole Graph?

- Uses a clear **anchor** via tenant and client.
- Projects only the three properties needed for display.
- Uses deterministic `ORDER BY` with `orderId` as tie-breaker.
- Applies the row limit in Neo4j rather than shipping all nodes to Java.
- Composite index `cap_order_client_feed` can support filtering and ordering; verify via the execution plan.

**In the API**, `$clientId` must match the caller's authenticated identity/authorization. Never let a client arbitrarily swap `clientId` in the URL to inspect another customer's orders in the same tenant.

## 10. R2 — Single Order Details and Total

Requirement: view order `o101` for client `c01`, including SKUs, quantities, and original unit prices per line.

```cypher
MATCH (c:CapClient {
  tenantId: $tenantId,
  clientId: $clientId
})-[:CAP_PLACED]->(o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
                 -[:CAP_OF_ITEM]->(p:CapItem {tenantId: $tenantId})
WHERE li.tenantId = $tenantId
WITH o, li, p
ORDER BY li.lineId
RETURN
  o.orderId AS orderId,
  o.status AS status,
  collect(
    CASE WHEN li IS NULL THEN NULL ELSE {
      lineId: li.lineId,
      sku: p.sku,
      title: p.title,
      quantity: li.quantity,
      unitPrice: li.unitPrice
    } END
  ) AS items,
  sum(
    CASE WHEN li IS NULL THEN 0
         ELSE li.quantity * li.unitPrice END
  ) AS totalVnd;
```

Parameters:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "orderId": "o101"
}
```

**Expected:**
- `orderId = "o101"`, `status = "PAID"`.
- Two lines: `skuA × 2 × 100000` and `skuB × 1 × 50000`.
- `totalVnd = 250000`.

`OPTIONAL MATCH` returns the order even if it has zero lines. `collect` ignores `NULL`, producing an empty `items` list when no lines exist. This fits small line counts; for orders with tens of thousands of lines, build a **paginated line-items API** rather than a massive `collect`.

**Correctness note:** tenant predicates on items and lines act as defense-in-depth; a graph containing cross-tenant edges still requires dedicated integrity checks. If `CAP_PLACED` is missing, the query returns 0 rows even if `CapOrder` exists—ensuring **ownership checks cannot be bypassed**.

### 10.1. Negative Testing

Switch `clientId = "c02"` while keeping `orderId = "o101"`. The query must return **0 rows**. Setting `tenantId = "t2"` with a t1 order ID must also return 0 rows.

Zero rows alone does not distinguish “order does not exist” from “unauthorized.” Depending on security policy, the API may return `404` to avoid leaking order existence to unauthorized callers.

## 11. R3 — Available Depot Stock and Vendors

Query inventory at depot `HN`:

```cypher
MATCH (d:CapDepot {
  tenantId: $tenantId,
  depotId: $depotId
})-[stock:CAP_STOCKS]->(p:CapItem {tenantId: $tenantId})
WHERE stock.available > 0
RETURN p.sku AS sku,
       p.title AS title,
       stock.available AS available
ORDER BY sku
LIMIT $limit;
```

Parameters `{tenantId:'t1', depotId:'HN', limit:20}` return `skuA` with `available=120`.

Find vendors offering a SKU:

```cypher
MATCH (p:CapItem {tenantId: $tenantId, sku: $sku})
MATCH (v:CapVendor {tenantId: $tenantId})-[:CAP_OFFERS]->(p)
RETURN v.vendorId AS vendorId, v.name AS vendorName
ORDER BY vendorId
LIMIT $limit;
```

For `t1/skuA`, expect only `v01`. For `t2/skuA`, despite the identical SKU string, only the matching t2 vendor is returned.

**Business distinction:** `stock.available > 0` reflects a point-in-time inventory snapshot; it does not reserve units for a new order. Under concurrent purchasing, add a **race-safe inventory write transaction** rather than treating the read above as an order reservation.

## 12. Paginating the Right Entity: Page Orders First, Lines Second

A common design bug:

```cypher
// WRONG for the goal "fetch 20 orders":
MATCH (o:CapOrder)-[:CAP_HAS_LINE]->(li:CapLine)
RETURN o.orderId AS orderId, li.lineId AS lineId
LIMIT 20;
```

`LIMIT 20` caps **expanded line rows**, not 20 orders. A single 25-line order fills the entire page and pushes out all other orders.

Fix by selecting orders first:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
WITH o, li
ORDER BY o.createdAt DESC, o.orderId DESC, li.lineId
RETURN o.orderId AS orderId,
       o.status AS status,
       o.createdAt AS createdAt,
       collect(
         CASE WHEN li IS NULL THEN NULL ELSE {
           lineId: li.lineId,
           sku: li.sku,
           quantity: li.quantity
         } END
       ) AS items
ORDER BY createdAt DESC, orderId DESC;
```

Here, `WITH o ... LIMIT` selects up to `$limit` **order nodes** first. Note that `LIMIT` still **does not bound lines per order**; if orders can hold huge line counts, separate out a line-pagination endpoint.

### 12.1. Keyset Pagination for Large Order Sets

Across millions of orders, deep `SKIP` incurs traversal overhead and shifts under concurrent inserts/deletes. Use a timestamp + key cursor:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
WHERE o.createdAt < datetime($cursorAt)
   OR (
       o.createdAt = datetime($cursorAt)
       AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY createdAt DESC, orderId DESC
LIMIT $limit;
```

This is the **next-page query**; the first page omits the cursor predicate. Keyset pagination requires deterministic ordering with a unique tie-breaker; it does not provide a global snapshot across concurrent mutations.

## 13. W1 — Idempotent Order Creation in One Transaction

### 13.1. Write Requirements

Create order `o900` for client `c01` in tenant `t1`, with one line for `skuA`, quantity `2`, unit price `100000`, status `NEW`. If the API is retried with the **same requestId and payload**, the outcome must remain equivalent without creating extra orders, lines, or relationships.

Example input:

```json
{
  "tenantId": "t1",
  "clientId": "c01",
  "orderId": "o900",
  "requestId": "req-900",
  "createdAt": "2026-11-25T10:00:00+07:00",
  "lineId": "l900a",
  "sku": "skuA",
  "quantity": 2,
  "unitPrice": 100000
}
```

In production:
- `tenantId` and `clientId` are authenticated and authorized.
- `quantity > 0`, `unitPrice >= 0`, all IDs valid and length-bounded.
- `requestId` is tenant-scoped and managed under idempotency rules.
- Product prices should typically come from an approved price list; **never trust a browser-supplied `unitPrice`** for real billing.

### 13.2. Query Executed Inside a Managed Transaction

```cypher
MATCH (c:CapClient {
  tenantId: $tenantId,
  clientId: $clientId
})
MATCH (p:CapItem {
  tenantId: $tenantId,
  sku: $sku
})
MERGE (o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
ON CREATE SET
  o.clientId = $clientId,
  o.requestId = $requestId,
  o.createdAt = datetime($createdAt),
  o.status = 'NEW'
WITH c, p, o
WHERE o.clientId = $clientId
  AND o.requestId = $requestId
MERGE (c)-[:CAP_PLACED]->(o)
MERGE (li:CapLine {
  tenantId: $tenantId,
  lineId: $lineId
})
ON CREATE SET
  li.orderId = $orderId,
  li.sku = $sku,
  li.quantity = $quantity,
  li.unitPrice = $unitPrice
WITH o, p, li
WHERE li.orderId = $orderId
  AND li.sku = $sku
  AND li.quantity = $quantity
  AND li.unitPrice = $unitPrice
MERGE (o)-[:CAP_HAS_LINE]->(li)
MERGE (li)-[:CAP_OF_ITEM]->(p)
RETURN o.orderId AS orderId,
       o.status AS status,
       li.lineId AS lineId;
```

**Critical:** this query is designed to run inside an **application managed transaction**, where the application **strictly requires exactly one returned record**. If the client/SKU is missing, `orderId` already holds a different `requestId`, or `lineId` is reused with a conflicting payload, the query returns **0 rows**. The Java layer must treat that as an error and throw an exception **before commit** so every intermediate write rolls back.

Running this query standalone as an auto-commit statement in Browser without checking record count could **commit partial mutations** even when a trailing `WHERE` filter drops all rows. Thus W1 treats **query + transaction callback + result assertion as a single design unit**.

### 13.3. Why Does `MERGE` Not Replace Constraints?

`MERGE` on business keys provides idempotency on sequential retries, yet two concurrent writers can still race. The composite uniqueness constraints from section 5 guard against duplicate keys; application code must catch conflict errors explicitly rather than treating all constraint failures as transient.

**There is no free “exactly-once HTTP delivery.”** Network failures can occur after DB commit and before the client receives the ACK. Request IDs, unique constraints, and status checks enable safe retries. Because `executeWrite` may re-invoke its callback on transient errors, **never send emails, generate external invoices, or charge payment gateways directly inside the callback**.

## 14. W2 — Conditional Status Transition

For `NEW` orders, transition to `PAID` enforcing authorization and state rules.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
WHERE o.clientId = $clientId
  AND o.status = 'NEW'
SET o.status = 'PAID',
    o.paidAt = datetime($paidAt)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.paidAt AS paidAt;
```

The application layer must assert **exactly one record**. Zero records indicates a missing order, wrong owner, or disallowed state transition. A production service also needs:
- Identity-based authorization and transition permissions.
- Verification that the payment event is genuine and not previously applied.
- A dedicated **payment/event ID with a unique constraint** for deduplication.
- Concurrency handling when two transition requests race; `WHERE status = 'NEW'` alone does not prove a payment workflow achieves exactly-once business effects.
- External side effects placed into an outbox or idempotent consumer when integrating other systems.

Minimal state diagram:

```text
NEW -------PAID
  \
   \------CANCELLED

PAID never reverts directly to NEW.
```

**Do not run W2 before running aggregation tests against baseline expectations**; transitioning `o103` from `NEW` to `PAID` changes period revenue.

## 15. Java Driver 6.x — Properly Scoped Session Reads and Writes

### 15.1. Dependencies and Connectivity

Use `org.neo4j.driver:neo4j-java-driver` **6.x compatible with your Neo4j server and Spring stack**; avoid hardcoding an unverified “latest” version in real projects.

```java
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

record OrderSummary(
    String orderId,
    ZonedDateTime createdAt,
    String status
) {}

record OrderWriteResult(
    String orderId,
    String status,
    String lineId
) {}
```

Bootstrap/CLI initialization example:

```java
String uri = System.getenv("NEO4J_URI");
String username = System.getenv("NEO4J_USER");
String password = System.getenv("NEO4J_PASSWORD");

try (Driver driver = GraphDatabase.driver(
        uri, AuthTokens.basic(username, password))) {
    driver.verifyConnectivity();
    // Call query methods below.
}
```

In a Spring service, `Driver` should be a **long-lived shared bean**, not created/closed per HTTP request. In clusters, use an appropriate routing URI (typically `neo4j+s://`) and select the database via `SessionConfig.forDatabase(...)`.

### 15.2. API to Read Order Lists

```java
static List<OrderSummary> findOrders(
        Driver driver, String tenantId,
        String clientId, int requestedLimit) {

    int limit = Math.max(1, Math.min(requestedLimit, 50));

    String query = """
        MATCH (o:CapOrder {
          tenantId: $tenantId, clientId: $clientId
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
            tx.run(query, Map.of(
                "tenantId", tenantId,
                "clientId", clientId,
                "limit", limit
            )).list(r -> new OrderSummary(
                r.get("orderId").asString(),
                r.get("createdAt").asZonedDateTime(),
                r.get("status").asString()
            ))
        );
    }
}
```

Here `list()` is safe because `LIMIT` is small. For multi-million-row exports, paginate or stream in batches; never materialize the whole graph into the Java heap.

### 15.3. API to Create an Order and Assert Record Count Before Commit

```java
static OrderWriteResult createSingleLineOrder(
        Driver driver,
        String tenantId,
        String clientId,
        String orderId,
        String requestId,
        String lineId,
        String sku,
        long quantity,
        long unitPrice,
        String createdAt) {

    if (quantity <= 0 || unitPrice < 0) {
        throw new IllegalArgumentException(
            "Invalid quantity or unitPrice");
    }

    String query = """
        MATCH (c:CapClient {
          tenantId: $tenantId, clientId: $clientId
        })
        MATCH (p:CapItem {
          tenantId: $tenantId, sku: $sku
        })
        MERGE (o:CapOrder {
          tenantId: $tenantId, orderId: $orderId
        })
        ON CREATE SET
          o.clientId = $clientId,
          o.requestId = $requestId,
          o.createdAt = datetime($createdAt),
          o.status = 'NEW'
        WITH c, p, o
        WHERE o.clientId = $clientId
          AND o.requestId = $requestId
        MERGE (c)-[:CAP_PLACED]->(o)
        MERGE (li:CapLine {
          tenantId: $tenantId, lineId: $lineId
        })
        ON CREATE SET
          li.orderId = $orderId,
          li.sku = $sku,
          li.quantity = $quantity,
          li.unitPrice = $unitPrice
        WITH o, p, li
        WHERE li.orderId = $orderId
          AND li.sku = $sku
          AND li.quantity = $quantity
          AND li.unitPrice = $unitPrice
        MERGE (o)-[:CAP_HAS_LINE]->(li)
        MERGE (li)-[:CAP_OF_ITEM]->(p)
        RETURN o.orderId AS orderId,
               o.status AS status,
               li.lineId AS lineId
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {

        return session.executeWrite(tx -> {
            Record r = tx.run(query, Map.of(
                "tenantId", tenantId,
                "clientId", clientId,
                "orderId", orderId,
                "requestId", requestId,
                "lineId", lineId,
                "sku", sku,
                "quantity", quantity,
                "unitPrice", unitPrice,
                "createdAt", createdAt
            )).single();  // 0 or >1 records -> exception -> rollback.

            return new OrderWriteResult(
                r.get("orderId").asString(),
                r.get("status").asString(),
                r.get("lineId").asString()
            );
        });
    }
}
```

Key properties:
- A single transaction writes the order, line, and two relationships.
- `.single()` enforces exactly one record; if zero records return, the callback throws and the driver **rolls back** instead of committing partial work.
- `executeWrite` may automatically retry transient failures. Inputs and `requestId` must remain invariant across retries.
- Unique constraints prevent duplicate IDs. Application logic should map business/idempotency conflicts to HTTP `409`/`422` rather than retrying indefinitely.
- Never place external side effects inside the transaction callback.

**This example creates a single line**. Extending to multiple lines can use `UNWIND $lines` inside the same transaction, provided **every SKU and line is verified**; if any SKU does not exist, roll back *the entire order*. Never report “partial success” unless explicitly required by business rules.

### 15.4. Error and Timeout Mapping

| Situation | API response strategy |
| --- | --- |
| Missing client/SKU or wrong owner | Do not create order; business error / `404` / `403` per policy |
| `orderId` tied to a different `requestId` | Conflict; do not modify existing order |
| `requestId` reused on a different `orderId` | Unique constraint violation → conflict |
| Database temporarily unavailable | Bounded retry within driver/gateway timeout budget |
| Ambiguous write outcome due to lost ACK | Reconcile by `requestId`/`orderId`; never double-charge |
| DBMS reports syntax/permission error | Fix code/role; never retry as transient |

## 16. A1 — Aggregating Revenue by Product and Time Window

Requirement: in tenant `t1`, from Nov 1 up to before Nov 4, 2026, list top SKUs across **paid orders** by total revenue.

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  status: 'PAID'
})
WHERE o.createdAt >= datetime($from)
  AND o.createdAt < datetime($to)
MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
         -[:CAP_OF_ITEM]->(p:CapItem {tenantId: $tenantId})
WHERE li.tenantId = $tenantId
WITH p.sku AS sku,
     p.title AS title,
     sum(li.quantity) AS unitsSold,
     sum(li.quantity * li.unitPrice) AS revenueVnd
RETURN sku, title, unitsSold, revenueVnd
ORDER BY revenueVnd DESC, sku
LIMIT $topN;
```

Parameters:

```json
{
  "tenantId": "t1",
  "from": "2026-11-01T00:00:00+07:00",
  "to": "2026-11-04T00:00:00+07:00",
  "topN": 10
}
```

**Expected on seed before running W2:**

| sku | unitsSold | revenueVnd |
| --- | ---: | ---: |
| `skuA` | 3 | 300000 |
| `skuB` | 1 | 50000 |

`skuC` belongs to a `NEW` order and is excluded. t2's `skuA` is excluded by tenant isolation. Total paid revenue for t1 is **350000 VND**, matching `o101 = 250000` and `o102 = 100000`.

### 16.1. Common Aggregation Pitfalls

- **Never substitute current `CapItem` catalog prices** for `CapLine.unitPrice` captured at purchase time.
- `LIMIT 10` after `ORDER BY revenue` does not mean the engine scans only ten lines; it aggregates all qualifying lines first.
- Avoid joining extra one-to-many branches (vendors, depots, reviews) inside the same `sum`, which **multiplies rows**.
- For very large monetary totals, 64-bit integers can overflow; production systems need explicit numeric precision/bounds.
- For high-traffic dashboards, consider scheduled pre-aggregation or read models with source reconciliation and documented staleness.

## 17. A2 — Total Amount per Order and Order Count

Query totals for paid orders within a tenant:

```cypher
MATCH (o:CapOrder {
  tenantId: $tenantId,
  status: 'PAID'
})
MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
WITH o.orderId AS orderId,
     sum(li.quantity * li.unitPrice) AS totalVnd
RETURN orderId, totalVnd
ORDER BY totalVnd DESC, orderId;
```

Seed results for t1:

| orderId | totalVnd |
| --- | ---: |
| `o101` | 250000 |
| `o102` | 100000 |

When you need the **count of paid orders**, do not count order lines:

```cypher
MATCH (o:CapOrder {tenantId: $tenantId, status: 'PAID'})
RETURN count(o) AS paidOrders;
```

Expect `paidOrders = 2`. If an order has five lines, `count(li)` counts **five lines**, not one order.

### 17.1. Two Multi-Branch Joins and Multiplication Risk

A query counting both orders and interacted vendors via two consecutive `OPTIONAL MATCH` clauses produces a Cartesian product of rows. In Cypher 5.23+, isolate each count inside a subquery:

```cypher
MATCH (c:CapClient {tenantId: $tenantId, clientId: $clientId})
CALL (c) {
  MATCH (c)-[:CAP_PLACED]->(o:CapOrder)
  RETURN count(o) AS orderCount
}
RETURN c.clientId AS clientId, orderCount;
```

This illustrates the pattern for one branch. When adding a second branch, place an **independent `CALL (c) { ... }`** rather than multiplying two relationship expansions before aggregating. `count(DISTINCT ...)` can fix the count yet still pays intermediate expansion cost.

## 18. P1 — Finding the Fewest-Hop Path Between Two Depots

In Neo4j, a path with the fewest relationships is the **shortest path by hop count**, not necessarily the path with the lowest total time or cost.

Neo4j Cypher supports `shortestPath` over a variable-length relationship pattern. Example between `HN` and `CT` in tenant `t1`:

```cypher
MATCH (src:CapDepot {tenantId: $tenantId, depotId: $from})
MATCH (dst:CapDepot {tenantId: $tenantId, depotId: $to})
MATCH p = shortestPath(
  (src)-[:CAP_ROUTE_TO*1..4]->(dst)
)
WHERE all(n IN nodes(p) WHERE n.tenantId = $tenantId)
RETURN
  [n IN nodes(p) | n.depotId] AS depots,
  length(p) AS hops,
  reduce(minutes = 0, r IN relationships(p) |
         minutes + r.travelMinutes) AS travelMinutes;
```

Parameters `{tenantId:'t1', from:'HN', to:'CT'}`.

The seed contains two **2-hop** routes:
- `HN → SG → CT`: `150 + 45 = 195` minutes.
- `HN → DN → CT`: `60 + 170 = 230` minutes.

`shortestPath` returns **one** minimum-hop path; when ties exist, the returned path is **not guaranteed to have the lowest weight**. If you need all minimum-hop paths before ranking by secondary criteria, check `allShortestPaths`/`ALL SHORTEST` for your version.

**Tenant warning:** `WHERE all(n IN nodes(p) ...)` guards output on a seed graph free of cross-tenant edges, yet **does not replace a graph model prohibiting cross-tenant routes**. In a multi-tenant graph with accidental cross-links, a post-filter could reject the single shortest path found while missing a valid longer path. Production systems must enforce tenant boundaries within traversal/projection scope and validate intermediate nodes.

### 18.1. Avoid Unbounded Path Patterns

Patterns like this are **unsuitable** for large systems:

```cypher
// Avoid on wide, cycle-rich graphs:
MATCH p = (a)-[:CAP_ROUTE_TO*]->(b)
RETURN p;
```

Path counts explode rapidly with branching factor and cycles. This lab bounds depth to `1..4`; production systems must bound search space, timeouts, and memory, or use dedicated shortest-path algorithms.

## 19. P2 — Finding the Minimum-Travel-Time Path

### 19.1. On a Small Demo Graph: Bounded Path Enumeration and Weight Sum

```cypher
MATCH (src:CapDepot {tenantId: $tenantId, depotId: $from})
MATCH (dst:CapDepot {tenantId: $tenantId, depotId: $to})
MATCH p = (src)-[:CAP_ROUTE_TO*1..4]->(dst)
WHERE all(n IN nodes(p) WHERE n.tenantId = $tenantId)
WITH p,
     reduce(minutes = 0, r IN relationships(p) |
            minutes + r.travelMinutes) AS totalMinutes
RETURN
  [n IN nodes(p) | n.depotId] AS depots,
  length(p) AS hops,
  totalMinutes
ORDER BY totalMinutes ASC, hops ASC, depots
LIMIT 1;
```

**Expected on seed data:**

```text
depots          = ["HN", "DN", "SG", "CT"]
hops            = 3
totalMinutes    = 165
```

This path takes **3 hops** yet totals `60 + 60 + 45 = 165` minutes—faster than both 2-hop paths in P1.

Because of `*1..4`, this query finds the optimum **within paths of at most four relationships**, without proving global optimality on larger networks. It also enumerates and sorts candidate paths, so **this approach does not scale directly to millions of nodes**.

### 19.2. When Do You Need Neo4j Graph Data Science?

On large networks, **non-negative weighted** shortest-path problems are suited to Dijkstra in **Neo4j Graph Data Science (GDS)**. You must:

1. Install a compatible GDS plugin/version, license, and procedure privileges.
2. **Project** a graph containing only the **target tenant's** `CapDepot` nodes and `CAP_ROUTE_TO` edges—never project all tenants indiscriminately.
3. Load `travelMinutes` as `relationshipWeightProperty`.
4. Estimate memory for projection/execution and monitor jobs.
5. Run `gds.shortestPath.dijkstra.stream`, and drop the projection once finished.

Syntax example **assuming** named graph `cap_t1_routes` already contains only t1's depots and routes:

```cypher
MATCH (src:CapDepot {tenantId: 't1', depotId: 'HN'})
MATCH (dst:CapDepot {tenantId: 't1', depotId: 'CT'})
CALL gds.shortestPath.dijkstra.stream('cap_t1_routes', {
  sourceNode: src,
  targetNodes: dst,
  relationshipWeightProperty: 'travelMinutes'
})
YIELD totalCost, nodeIds
RETURN totalCost,
       [nodeId IN nodeIds |
          gds.util.asNode(nodeId).depotId] AS depots;
```

This is a **conditional advanced section** that cannot run from the Cypher seed script alone; you must create the GDS projection first and ensure source/target nodes belong to it. GDS Dijkstra requires valid weights (non-negative/positive per algorithm requirements). Never run hop-based `shortestPath`, sum edge weights afterward, and claim it is the fastest route.

## 20. Spring Data Neo4j Integration: Separating Write Models and Read Queries

Spring Data Neo4j (SDN) works well with entity aggregates for domain writes and custom Cypher for flat read models.

### 20.1. Suggested Layering

```text
REST Controller
    |
    +-- Validation + authorization
    |
    v
OrderApplicationService
    |
    +-- OrderWriteAdapter (transaction + idempotency)
    +-- OrderReadAdapter  (Cypher + DTO)
    +-- ReportReadAdapter (aggregation)
    +-- RouteReadAdapter  (bounded Cypher or GDS)
    |
    v
Neo4j Driver / Spring Data Neo4j
    |
    v
CapClient / CapOrder / CapLine / CapDepot ...
```

Use `Neo4jClient`/`ReactiveNeo4jClient` for scalar/map/DTO queries to avoid hydrating entire entity graphs when the UI needs only a few fields. For repositories:
- `Neo4jRepository` fits imperative stacks.
- `ReactiveNeo4jRepository` fits Reactor/WebFlux and backpressure.
- `@Query` handles custom queries; verify projection/DTO mapping on your exact SDN version.
- Never mix raw `Driver.session(...)` transactions with Spring `@Transactional` assuming both share one transaction.

### 20.2. Suggested API Design

| HTTP endpoint | Underlying query | Response shape |
| --- | --- | --- |
| `GET /clients/me/orders?limit=20` | R1 | `List<OrderSummary>` |
| `GET /orders/{orderId}` | R2 | `OrderDetail` |
| `GET /depots/{depotId}/stock` | R3 | `List<StockSummary>` |
| `POST /orders` | W1 | `OrderWriteResult` |
| `POST /orders/{orderId}/pay` | W2 | `PaymentResult` |
| `GET /reports/top-items?from=&to=` | A1 | `List<ItemRevenue>` |
| `GET /routes?from=HN&to=CT` | P1/P2 | `RouteResult` |

Every endpoint should bound record counts/depth, timeouts, and input schemas, never serializing unnecessary object graphs. HTTP codes are suggestions only and do not substitute for real authorization, payment workflows, and API contracts.

## 21. Multi-Tenant Security and Data Governance

### 21.1. Minimum Rules

1. Derive `tenantId` from a trusted security context.
2. Verify `clientId`/order ownership against authenticated identity and business rules.
3. Anchor every node lookup by composite business key `(tenantId, id)`.
4. Never traverse relationships across tenants unless explicitly permitted.
5. Run the Java service with least-privilege Neo4j credentials; never use admin accounts for CRUD.
6. Never concatenate raw input into Cypher strings; pass property values via parameters.
7. When dynamic labels, relationship types, or sort fields are required, use strict **allowlists** compatible with your Cypher version, never raw input interpolation.
8. Cap `LIMIT`, `maxDepth`, lines per order, and `UNWIND` batch sizes.
9. Log request IDs, query names, and durations—never PII, secrets, or raw payment payloads.
10. Test both Neo4j database roles/privileges and application-layer authorization.

### 21.2. Checking for Cross-Tenant Relationships

```cypher
MATCH (c:CapClient)-[:CAP_PLACED]->(o:CapOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(*) AS crossTenantPlaced;
```

```cypher
MATCH (o:CapOrder)-[:CAP_HAS_LINE]->(li:CapLine)
WHERE o.tenantId <> li.tenantId
RETURN count(*) AS crossTenantOrderLines;
```

```cypher
MATCH (a:CapDepot)-[:CAP_ROUTE_TO]->(b:CapDepot)
WHERE a.tenantId <> b.tenantId
RETURN count(*) AS crossTenantRoutes;
```

On the seed dataset, all three must equal `0`. If tests intentionally introduce cross-tenant edges, path and read queries must enforce policy explicitly rather than leaking records silently.

## 22. Measuring Query Quality with `EXPLAIN` and `PROFILE`

For query R1:

```cypher
EXPLAIN
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Then measure on a representative dataset:

```cypher
PROFILE
MATCH (o:CapOrder {
  tenantId: $tenantId,
  clientId: $clientId
})
RETURN o.orderId, o.createdAt
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $limit;
```

Metrics/operators to capture in the report:

| Metric / Operator | Meaning |
| --- | --- |
| `NodeIndexSeek` / `NodeByLabelScan` | Does the plan seek by key or scan labels? |
| `Estimated Rows` vs. `Rows` | Are planner cardinality estimates accurate? |
| `DB Hits` | Storage engine accesses; **not identical to physical disk reads** |
| `Expand(All)` / `VarLengthExpand` | Is fan-out or path explosion occurring? |
| `Sort`, `EagerAggregation` | Are large intermediate sets buffered in memory? |
| `Rows` before/after `LIMIT` | Is the limit pushed down early enough? |
| Response payload size | Are full nodes/relationships serialized unnecessarily? |
| Latency p50/p95/p99 | Actual user experience under load and parameter skew |

**Never run `PROFILE` on W1/W2 in production**: `PROFILE` executes write operations, not a dry run. In the lab, run only against test data knowing exactly what the transaction modifies.

### 22.1. Meaningful Query Comparisons

A query returning `LIMIT 20` and a query scanning 20 million records **do not perform equal work**; compare queries only after verifying both satisfy the exact same contract. A `PROFILE` on three demo orders proves nothing about a plan at three million orders.

Your submission should include:
- A small dataset verifying correctness.
- A larger dataset (including high-degree skew) to evaluate execution plans.
- Application and database metrics collected under the same load window.
- Analysis explaining why the chosen indexes and traversal direction work, not merely plan screenshots.

## 23. Automated Testing and Result Reconciliation

### 23.1. Read / Aggregation Test Suite

| Test ID | Action | Expected result on seed |
| --- | --- | --- |
| T01 | R1 tenant t1, client c01 | `o102, o101` in descending time order |
| T02 | R1 tenant t1, client c02 | Only `o103` |
| T03 | R1 tenant t2, client c01 | Only `o201` |
| T04 | R2 t1/c01/o101 | Two lines, total `250000` |
| T05 | R2 t1/c02/o101 | 0 rows |
| T06 | R3 depot HN in t1 | `skuA` with `available=120` |
| T07 | Vendors for t1/skuC | Only `v02` |
| T08 | A1 tenant t1, Nov 01–04 | `skuA=300000`, `skuB=50000` |
| T09 | A2 paid orders tenant t1 | `o101=250000`, `o102=100000` |
| T10 | Count paid orders tenant t1 | `2` |
| T11 | P1 HN → CT | A `2`-hop route, `195` or `230` minutes |
| T12 | P2 HN → CT, maxDepth 4 | `[HN,DN,SG,CT]`, total `165` |
| T13 | Cross-tenant relationship audit | All counts equal `0` |
| T14 | Tenant t2 query for shared SKU `skuA` | Sees only t2 data |

If prior data exists, reset the **lab environment** via an approved procedure or filter by test ID—never run `MATCH (n) DETACH DELETE n` on a shared database.

### 23.2. Write Transaction Test Suite

1. **T15 — First write**: call W1 with `o900 / req-900 / l900a` → one order, one line, and both required relationships.
2. **T16 — Exact retry**: resend identical payload → still one order and one line.
3. **T17 — Conflicting request ID**: same `requestId` with different `orderId` → unique constraint rejects; no new order created.
4. **T18 — Conflicting line ID**: reuse `lineId` with different SKU/quantity → managed transaction fails and rolls back.
5. **T19 — Non-existent client**: must create neither order nor line.
6. **T20 — SKU from another tenant**: no matching item, no order created.
7. **T21 — Zero/negative quantity or negative price**: validation rejects before query execution.
8. **T22 — Network drop after commit**: application looks up by `requestId/orderId` and retries safely.
9. **T23 — Two concurrent requests with same orderId**: at most one succeeds per business rule.
10. **T24 — Unauthorized status transition**: order remains unchanged for wrong owner or invalid state.

**Concurrent write tests must run against a lab instance with real parallel connections**, asserting constraints and post-completion state. Never assume “having `MERGE` eliminates all races” when business logic also checks stock, triggers side effects, or updates related state.

### 23.3. Sample Cypher Verification for W1

After calling the W1 API (do not run before creating the order):

```cypher
MATCH (o:CapOrder {tenantId: 't1', orderId: 'o900'})
OPTIONAL MATCH (o)-[:CAP_HAS_LINE]->(li:CapLine)
RETURN count(DISTINCT o) AS orders,
       count(DISTINCT li) AS lines;
```

**Expected:** `orders=1, lines=1`. Also inspect `requestId`, `li.quantity`, and the `CAP_OF_ITEM` relationship; those two counts alone do not prove all business invariants.

## 24. Error Handling, Performance, and Operations

| Error / Incident | Likely cause | Proper response |
| --- | --- | --- |
| `ConstraintValidationFailed` | Duplicate composite key or request ID | Report conflict; do not retry indefinitely |
| `ClientException` from syntax | Version/parameter mismatch in query | Fix code and re-test |
| `TransientException` | Cluster leader switch, network blip, or lock conflict | Bounded, idempotent retry |
| Java timeout | Slow DB, pool wait, network, ambiguous commit | Separate request vs. tx timeout; reconcile writes |
| `OutOfMemoryError` on Java client | `list()` materializing huge result | Paginate/stream/DTOs and profile JVM heap |
| Neo4j transaction memory limit | Oversized `collect`/`UNWIND` | Shrink batches/fan-out; never raise limits blindly |
| Path query too slow | High branching factor, large `*1..N` | Bound search, use GDS Dijkstra, profile |
| Dashboard aggregation slow | Scanning extensive historical lines | Indexes, read models, scheduled pre-aggregation |
| Request leaks another tenant's data | Missing authorization or traversal scope | Lock API, patch query, add negative tests |
| Retry creates duplicate orders | Missing business ID/constraint/outbox | Enforce unique keys, verify commit outcome |

In production:
- Use a shared Driver pool and short-lived sessions.
- Choose `executeRead`/`executeWrite` appropriately for cluster routing and retry support.
- Configure transaction timeouts and retry budgets per SLO; never hold a transaction open while awaiting HTTP/Kafka calls.
- Monitor p95/p99 latency, error rates, pool wait, Rows/DB Hits, page cache, and JVM heap/GC.
- Backup/restore and RBAC testing remain essential requirements beyond the query suite once the project becomes a real service.

## 25. Milestone-Based Project Workflow

### Milestone 1 — Model and Data

- Diagram the graph, justifying `CapLine` as a node and directed routes.
- Create the 7 uniqueness constraints and 2 indexes.
- Seed nodes and relationships in order; verify t1/t2 counts.
- Re-run seed to verify no duplicates, noting that `SET` resets properties to baseline demo values.

### Milestone 2 — Core Read Use Cases

- Implement R1, R2, and R3 with parameters and DTOs.
- Add result bounds and tenant/client negative tests.
- Document index and traversal choices.

### Milestone 3 — Safe Writes

- Implement W1 inside a managed transaction.
- Enforce record-count validation, idempotency, and uniqueness tests.
- Implement W2 with validation and authorization; omit real payment processing in the lab.

### Milestone 4 — Aggregations

- Implement A1/A2, verifying `300000`/`50000` and total `350000`.
- Prove no row multiplication across joins.
- Document when large scale requires pre-aggregation.

### Milestone 5 — Pathfinding

- Implement P1/P2.
- Contrast the 2-hop routes with the 165-minute 3-hop route.
- Explain `maxDepth` bounds, branching factor, cross-tenant risks, and when GDS is needed.

### Milestone 6 — Integration and Verification

- Demonstrate runnable Java Driver / SDN code.
- Run listed tests and capture `EXPLAIN`/`PROFILE` safely for read/aggregation/path queries.
- Document known limitations, test data, reset procedures, timings, and tuning hypotheses.
- Include a README with startup steps and measured results (if packaged as a real repo).

## 26. Capstone Grading Rubric (100 Points)

| Category | Max points | Passing criteria |
| --- | ---: | --- |
| Graph model, keys, constraints, indexes, and seed | 15 | Sound schema, repeatable controlled seed |
| R1/R2/R3, pagination, tenant protection | 20 | Accurate results, no over-fetching, ownership tests |
| W1/W2, managed transactions, idempotency | 20 | Zero duplicates, rollback on invalid input |
| A1/A2, accuracy and aggregation correctness | 15 | Exact `350000` total, fan-out explained |
| P1/P2 and hop vs. weight distinction | 15 | Correct paths, understands bounds and GDS |
| Query plans, security, performance, negative tests | 10 | Measured evidence, risks identified |
| Documentation of run steps, results, limitations | 5 | Reproducible by another engineer |
| **Total** | **100** | |

This rubric rewards **correctness and design clarity**, not raw lines of Cypher. A system with 30 endpoints that leaks tenant data or duplicates orders on retry fails the capstone's core goal.

## 27. Pitfalls to Catch in Submissions

| Pitfall | Why it is wrong | How to fix |
| --- | --- | --- |
| `MATCH (n) RETURN n` then filter in Java | Full graph scan, heavy network/heap, data leak risk | Anchor on composite business keys |
| Using `id(n)` as public API ID | Unstable across store lifecycle/restores | `tenantId + businessId` with constraint |
| Merging lines straight onto `Order->Item` | Cannot represent multiple lines per SKU | Separate `CapLine` node with `lineId` |
| `CREATE` on every retry | Duplicates data if commit ACK is lost | `MERGE` + request ID + unique constraints |
| W1 returns 0 rows yet Java commits | Partial writes persist prior to trailing filter | `.single()` inside managed tx to force rollback |
| Computing revenue from current catalog price | Corrupts historical price accuracy | Use `CapLine.unitPrice` |
| Counting `count(li)` as order count | Multi-line orders inflate order counts | Count `count(o)` or aggregate at order grain |
| `LIMIT` after expanding order lines | Truncates orders mid-stream | Page `CapOrder` first, then expand lines |
| Using `shortestPath` for minimum minutes | Optimizes hop count only | Weighted path search / GDS Dijkstra |
| Unbounded `*` traversals | Exponential path explosion | Bounded traversal or dedicated algorithm |
| Filtering tenant only on path endpoints | Paths may cross other tenants | Enforce tenant scope across traversal/projection |
| Skipping t2 tests | Shared SKUs/IDs collide silently | Mandatory multi-tenant negative tests |
| Mixing Driver and Spring transactions | Breaks assumed atomicity | Manage one explicit transaction boundary |
| Running `PROFILE` on write queries in prod | Executes actual writes | Profile write queries only in the lab |
| Calling GDS without projecting a graph | Named graph does not exist | Project tenant subgraph, estimate memory |
| Loading huge results into `List`/`collectList` | Client `OutOfMemoryError` | `LIMIT`, DTOs, batching/streaming |

## 28. Defense Questions for Capstone Review

1. Why model `CapLine` as a node rather than properties on a direct relationship?
2. How does a composite uniqueness constraint differ from a plain range index?
3. If two requests submit the same `orderId` concurrently, how do `MERGE` and constraints behave?
4. In W1, if the SKU does not exist after the query matched/created the order, how is rollback guaranteed?
5. Why must external payment calls never run inside the `executeWrite` callback?
6. If a client times out right after commit, how do you verify whether `o900` was created?
7. Why must a 20-order list apply `LIMIT` **before** expanding order lines?
8. Why is `o103` excluded from initial paid revenue?
9. Why might a top-10 SKU query still scan millions of lines on a large graph?
10. Why can P1 return a 195- or 230-minute path while P2 returns 165 minutes?
11. What happens if a valid route takes 5 hops while P2 caps depth at 4?
12. Why is a tenant filter placed after `shortestPath` insufficient for both security and completeness?
13. In a multi-tenant system, may a user with `tenantId='t1'` arbitrarily request `clientId='c02'`?
14. Why is `PROFILE` never a “dry run” when a query contains `SET`?
15. If switching to Spring WebFlux, how do record consumption and session lifecycle change?

## 29. Key Takeaways

A solid Neo4j system is about more than creating nodes and edges. **The core discipline is turning each use case into a query with a clear anchor, minimal return payload, sound transaction boundaries, and verifiable correctness.**

- **Reads:** anchor on business key + tenant, project properties/DTOs, and paginate before expanding children.
- **Writes:** validate inputs and authorization, enforce uniqueness constraints, use `MERGE`, managed transactions, idempotency keys, and roll back invalid outcomes.
- **Aggregations:** aggregate at the right grain, separate order counts from line counts, preserve historical prices, and avoid fan-out multiplication.
- **Pathfinding:** distinguish fewest hops from lowest total weight; bounded Cypher fits small labs, while GDS Dijkstra fits large properly projected weighted graphs.
- **Operations:** inspect `EXPLAIN`/`PROFILE`, watch memory/pools, test multi-tenant boundaries, and document limitations instead of assuming small-seed speed holds in production.

A capstone is complete only when it delivers **data, queries, API integration, positive/negative tests, expected baselines, and documented trade-offs**—not merely a collection of Cypher snippets that run without syntax errors.

### Official References

- [Neo4j Cypher Manual — MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/match/)
- [Neo4j Cypher Manual — MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual — UNWIND](https://neo4j.com/docs/cypher-manual/current/clauses/unwind/)
- [Neo4j Cypher Manual — WITH](https://neo4j.com/docs/cypher-manual/current/clauses/with/)
- [Neo4j Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual — List functions: reduce, nodes, relationships](https://neo4j.com/docs/cypher-manual/current/functions/list/)
- [Neo4j Cypher Manual — Shortest paths](https://neo4j.com/docs/cypher-manual/current/patterns/shortest-paths/)
- [Neo4j Cypher Manual — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual — Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Neo4j GDS — Dijkstra Source-Target shortest path](https://neo4j.com/docs/graph-data-science/current/algorithms/dijkstra-source-target/)
- [Neo4j GDS — Graph projection](https://neo4j.com/docs/graph-data-science/current/management-ops/graph-creation/graph-project/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
