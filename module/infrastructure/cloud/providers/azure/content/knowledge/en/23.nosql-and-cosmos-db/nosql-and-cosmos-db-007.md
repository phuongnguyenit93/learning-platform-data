# Indexing Policies and Query Optimization in Cosmos DB

A Java API stores millions of orders as JSON documents in **Azure Cosmos DB**. Lookups by order ID run fast, yet the page listing the latest orders for a customer burns hundreds of Request Units (RUs), frequently triggers HTTP 429s, and slows down as data grows. The team considers doubling provisioned RU/s. That might buy temporary breathing room, but the first questions to ask are: **does the request know the partition key, can it use a point read, does the query span multiple partitions, does the current index support the FILTER and ORDER BY clauses, and is the response returning too many fields?**

An **indexing policy** determines which JSON property paths are indexed and with which index types. A sound policy lowers read costs, keeps write and index-storage overhead in check, and supports critical query shapes. Conversely, an unsuitable policy can force broad scans, inflate RUs, create resource contention, or even prevent multi-property `ORDER BY` queries from executing if required composite indexes are missing.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, combining deployment, monitoring, security, and cost control for application architectures. Here we focus on **Azure Cosmos DB for NoSQL (API for NoSQL, formerly known as Core/SQL API)**, where queries use a SQL-like language over JSON. APIs for MongoDB, Cassandra, Gremlin, and Table have different indexing mechanisms, syntax, and limits; **never apply this JSON indexing policy verbatim across all Cosmos DB APIs**.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the relationship among **JSON items, containers, partition keys, logical/physical partitions, RUs, and indexes**.
- Distinguish **point reads** from SQL queries, and **single-partition** from **cross-partition queries**.
- Read and design an **indexing policy** using `includedPaths`, `excludedPaths`, `indexingMode`, `automatic`, `compositeIndexes`, and `spatialIndexes`.
- Understand the **default range index**, and when to use **composite indexes** or **spatial indexes**.
- Optimize filters, `ORDER BY`, `TOP`, pagination, projections, aggregates, and array queries.
- Write parameterized queries in the **Azure Cosmos DB Java SDK v4**, supply partition keys, and read request charges.
- Evaluate queries using **RUs, query metrics, index metrics, latency, and partition counts**.
- Update indexing policies safely and account for **index transformation** duration.
- Detect **hot partitions**, indexing overhead, high-cardinality query patterns, and expensive queries.
- Build a checklist for benchmarking, monitoring, security, and budgeting before shipping production changes.

## 2. Cosmos DB for NoSQL Data Model

Core concepts:

| Concept | Role | Example |
|---|---|---|
| **Account** | Top-level Cosmos DB resource governing API, regions, consistency | `cosmos-commerce-prod` |
| **Database** | Logical grouping of containers | `commerce` |
| **Container** | Data boundary and configuration for partition key, indexing policy, and throughput | `orders` |
| **Item** | JSON document carrying an `id` field and partition key | A single order |
| **Partition key path** | Path defining an item's logical partition | `/tenantId` |
| **Logical partition** | Group of items sharing the same partition key value | `tenant-a` |
| **Physical partition** | Service-managed storage/throughput unit holding one or more logical partitions | Allocated by Cosmos DB |
| **RU** | Resource consumption unit for an operation | Point reads, queries, writes, indexing work |
| **RU/s** | Provisioned or autoscaled throughput capacity | Container/database throughput |

A container can span multiple physical partitions. When a query does not scope down to a logical partition, Cosmos DB may evaluate multiple physical partitions and merge results—usually consuming more RUs and latency than targeted routing, depending on data and query shape.

~~~text
Java Orders API
       |
       | Does the request have tenantId?
       v
Cosmos DB container: orders
  partition key path = /tenantId
       |
       +-- Logical partition tenant-a
       |       +-- order-101
       |       +-- order-102
       |
       +-- Logical partition tenant-b
       |       +-- order-501
       |       +-- order-502
       |
       +-- Logical partition tenant-c
               +-- order-900

Indexing policy applies at the container level;
Query scope and RUs also depend on partition key and query shape.
~~~

**You cannot change the partition key of an existing container with data merely by editing `indexingPolicy`.** Fixing an unsuitable partition key usually requires provisioning a new container and planning a data migration/cutover, subject to any specialized service features.

## 3. Sample JSON Document for This Lesson

Suppose the **`orders`** container uses partition key **`/tenantId`**. One item:

~~~json
{
  "id": "order-102",
  "tenantId": "tenant-a",
  "customerId": "customer-17",
  "status": "CONFIRMED",
  "createdAt": "2026-11-20T08:15:30Z",
  "totalAmount": 1250000,
  "currency": "VND",
  "region": "southeast-asia",
  "items": [
    {"sku": "SKU-123", "quantity": 2, "price": 500000},
    {"sku": "SKU-456", "quantity": 1, "price": 250000}
  ],
  "shipping": {
    "city": "Ho Chi Minh City",
    "method": "EXPRESS"
  },
  "largePayload": {
    "rawImportRecord": "A large audit/import payload not searched by the API"
  }
}
~~~

All values are **synthetic sample data**. Never put real customer records, tokens, secrets, or payment card numbers into examples, logs, or telemetry.

Expected access patterns:

| Pattern | Access Path | Priority |
|---|---|---|
| Look up an order given `id + tenantId` | **Point read** | Very frequent |
| List 20 latest orders for a tenant | `WHERE tenantId`, `ORDER BY createdAt` | Frequent |
| Filter orders by `status` and date within tenant | `WHERE tenantId/status/date` | Frequent |
| Report order counts by status within tenant | `COUNT`/`GROUP BY` | Scheduled |
| Search for a SKU inside `items` array | `ARRAY_CONTAINS`/`EXISTS`/`JOIN` depending on shape | Occasional |
| Search across all tenants by arbitrary string | Likely cross-partition / scan | Re-evaluate design |

**Index design starts from workloads and query patterns**, not by indexing every conceivable path. Every added index affects write costs, storage footprint, and policy update transformations.

## 4. What Is a Request Unit (RU) and Why Do Queries Cost RUs?

In Cosmos DB, an **RU** is the composite resource measure for executing an operation: CPU, memory, and I/O within the service model. Every request incurs an RU charge returned via headers like **`x-ms-request-charge`**, SDK responses, or metrics.

Factors influencing RUs include:

1. Item size and returned payload size.
2. Number of items examined, index lookups, and filter selectivity.
3. Whether the query routes to a single logical partition.
4. Number of physical partitions involved.
5. `ORDER BY`, `DISTINCT`, array `JOIN`s, aggregates, and query complexity.
6. Type and number of indexes maintained on writes.
7. Consistency level and replica access under deployment conditions.

~~~text
Illustrative example, NOT an official Cosmos DB benchmark:

Point read (id + partition key)     -> Low RUs, direct routing
Single-partition filtered query     -> RUs depend on filter, index, and results
Cross-partition query               -> Can raise RUs + latency substantially
Scanning many items / huge payloads -> Can consume high RUs
~~~

There is no fixed RU price for all point reads or queries. Larger items, different predicates, different consistency levels, and service configurations change consumption.

### RUs vs. RU/s

**RUs** measure what a single operation consumed. **RU/s** is provisioned or autoscaled throughput capacity. When concurrent requests demand more throughput than available capacity, Cosmos DB returns **HTTP 429 Too Many Requests** with a suggested retry delay.

~~~text
Preliminary RU/s budget
= Sum (requests/sec per type × average RUs per type)
+ headroom for peaks, background jobs, and variance
~~~

This is a **capacity estimation formula**, not a substitute for load testing. **Raising RU/s without fixing bad queries or partition keys** simply inflates your bill.

## 5. How Indexes Work Conceptually in Cosmos DB

Cosmos DB for NoSQL automatically indexes items per the container's **indexing policy**. When an item is written, properties matching the policy are indexed. The query engine uses those indexes to locate matching items without scanning every raw document sequentially.

~~~text
Orders JSON document
  |
  | Indexing policy
  +-- /tenantId
  +-- /status
  +-- /createdAt
  +-- /totalAmount
  +-- /items/[]/sku
  |
  v
Index structures
  |
  +-- Filter / range / sort lookups
  +-- Composite ordering if declared
  +-- Spatial lookups if spatial index is configured
~~~

This diagram illustrates paths conceptually, not the exact internal storage layout of the index.

### Indexing Trade-offs

| Indexing Many Properties | Selective Indexing |
|---|---|
| Supports broad ad hoc queries easily | Optimized for known query patterns |
| Can raise write RUs and index storage | Can lower write and storage costs |
| Low risk of missing common index paths | Requires governance whenever new queries appear |
| Fits early exploration phases | Fits stable, benchmarked workloads |

**Fewer indexes do not automatically mean faster reads.** Removing an index on a frequently filtered or sorted property can make queries burn far more RUs or prevent certain `ORDER BY` queries from running.

## 6. Default Indexing Policy and JSON Components

A default policy in Cosmos DB for NoSQL typically indexes most item properties using a **range index**, while excluding specific system properties/paths per platform defaults. Always **read the container's actual policy** rather than assuming from a generic snippet.

General policy example:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/*"}
  ],
  "excludedPaths": [
    {"path": "/\"_etag\"/?"}
  ],
  "compositeIndexes": [],
  "spatialIndexes": []
}
~~~

This matches the structural schema of **API for NoSQL** policies; exact defaults can vary by SDK version, container configuration, or specialized features.

### Fields

| Field | Meaning |
|---|---|
| **`indexingMode`** | How indexes are maintained—typically `consistent`; some workloads conditionally use `none` |
| **`automatic`** | Whether new/updated items are automatically indexed per policy |
| **`includedPaths`** | Property paths included in the index |
| **`excludedPaths`** | Property paths excluded from indexing |
| **`compositeIndexes`** | Property combinations and sort directions indexed together |
| **`spatialIndexes`** | Indexes supporting GeoJSON spatial queries and functions |

Some configurations also include indexing definitions for **vector/full-text** or newer capabilities depending on account/API support. **Never treat specialized index policies as automatically covered by default range indexes.**

## 7. Indexing Mode: `consistent` vs. `none`

**`consistent` indexing** is the standard mode: indexes update synchronously with item mutations so queries observe index updates consistent with the service model. It fits almost all applications querying across attributes.

**`none`** disables policy-driven indexing on that container, useful in rare specialized bulk-ingestion scenarios, at the cost of normal indexed query capabilities. Queries may fail, be unsupported, or fall back to expensive scans depending on configuration.

| Setting | When to Consider | Risks |
|---|---|---|
| **`consistent`** | APIs using filters, `ORDER BY`, JSON reports | Writes maintain indexes, costing more RUs than unindexed writes |
| **`none`** | Specialized batch ingestion or pure `id + PK` key-value lookups | Property queries become extremely expensive or unavailable |

**Never disable indexing on a production container just to save write RUs** when APIs rely on queries. For heavy ingestion jobs, evaluate separate staging containers or bulk execution, verify index restoration, and benchmark thoroughly.

### `automatic: true` Does Not Mean Zero Limits

**`automatic: true`** means Cosmos DB maintains indexes for paths defined in the policy. It does not automatically detect and build **composite indexes** for your application's multi-field sorts, nor does it cure a bad partition key.

## 8. Path Syntax for `includedPaths` and `excludedPaths`

Paths follow JSON structure syntax:

| Pattern | Conceptual Meaning |
|---|---|
| Root wildcard: `/*` | Entire tree and all descendant properties |
| **`/status/?`** | Scalar value of `status` at that exact path |
| **`/shipping/city/?`** | A nested scalar property |
| Descendant wildcard: `/largePayload/*` | All subtrees under `largePayload` |
| **`/items/[]/sku/?`** | `sku` scalar values across elements of the `items` array |

In JSON, write exact path strings like `/*` and `/largePayload/*` with no spaces. `?` targets a scalar value at a leaf path, whereas `*` traverses all child levels; exact path and index-kind syntax must follow API for NoSQL rules.

### Paths Are Case-Sensitive

JSON properties `createdAt` and `CreatedAt` are completely distinct names. Case mismatches or inconsistent types across documents will cause filters and sorts to behave unexpectedly.

### Precedence Between Included and Excluded Paths

Policies allow combining includes and excludes, where more specific paths override wildcards according to service precedence rules. Keeping the root wildcard with targeted exclusions looks like:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [
    {"path": "/largePayload/*"},
    {"path": "/\"_etag\"/?"}
  ]
}
~~~

Intended effect: keep indexing across most properties while skipping fields inside `largePayload` (when never filtered or sorted) plus the system `_etag` path. **Never exclude `id`, `tenantId`, `status`, or `createdAt` when APIs query them without measuring the impact.**

## 9. Strategy: Index Only Queried Paths

For stable workloads with bloated documents, you can exclude the root wildcard and explicitly include only queried paths:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"},
    {"path": "/customerId/?"},
    {"path": "/items/[]/sku/?"}
  ],
  "excludedPaths": [
    {"path": "/*"}
  ]
}
~~~

This is an **intentional example for specialized containers**, not a universal default recommendation. Certain system paths receive special engine handling, and query behavior on unindexed paths must be verified. **Switching to exclude-all in production can cause existing queries to spike in RUs or fail.**

### When to Choose Selective Indexing?

- Query contracts are stable and APIs filter on only a handful of fields.
- Items carry large metadata or `largePayload` blocks never used in filters or sorts.
- The workload is write-heavy and index maintenance drives major RU costs.
- You have performance regression tests covering every common query.
- You have a controlled policy rollout, reindexing monitor, and rollback plan.

During early product discovery with frequent ad hoc queries, the **default indexing policy** prevents unexpected query failures.

## 10. Which Query Patterns Need Composite Indexes?

A **composite index** defines an **ordered tuple of properties** and **ascending/descending directions** to support queries with multi-property `ORDER BY` or multi-field filter/sort combinations.

Example query:

~~~sql
SELECT c.id, c.status, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

A **multi-property `ORDER BY`** in API for NoSQL typically requires a matching composite index. Single-property range indexes alone **do not satisfy** multi-column sort orders.

Example declaration inside the indexing policy:

~~~json
{
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

This is a **policy fragment** that must sit inside the complete policy document (with `indexingMode`, paths, etc.) applied via the API or Portal. Never submit this fragment alone as the entire indexing policy.

### Sort Direction Matters

For the query:

~~~sql
ORDER BY c.status ASC, c.createdAt DESC
~~~

A composite index of **`status ASC, createdAt DESC`** matches the pattern. Path order and sort directions must match query rules in Cosmos DB. Reversing every sort direction simultaneously can leverage the reverse scan of the same index in supported cases; **never assume arbitrary ASC/DESC permutations are equally optimized**.

### Equality Filters Combined with `ORDER BY`

Example:

~~~sql
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAt DESC
~~~

With both equality filters and sorting, a composite index covering **`status + createdAt`** (and optionally other fields depending on workload) can reduce RUs. Yet **never assume a composite index is mandatory or always faster**: a single-property `ORDER BY` can use a range index, and the biggest lever remains **proper partition-key routing verified by query metrics**.

### Do Not Create Unbounded Composite Indexes

Each composite index adds write maintenance overhead and counts toward policy path/definition limits. Add composite indexes only for frequent, critical queries, and measure **write RUs**, **query RUs**, **index storage**, and reindexing time.

## 11. Spatial Indexes and GeoJSON Queries

When items store **GeoJSON** locations and the app runs proximity or region searches, configure a **spatial index** for Cosmos DB spatial functions.

Sample item:

~~~json
{
  "id": "store-001",
  "tenantId": "tenant-a",
  "name": "Demo Store",
  "location": {
    "type": "Point",
    "coordinates": [106.70, 10.78]
  }
}
~~~

GeoJSON coordinates follow **`[longitude, latitude]`** order—never swap them to latitude, longitude. Values above are illustrative only.

Illustrative `spatialIndexes` fragment:

~~~json
{
  "spatialIndexes": [
    {
      "path": "/location/*",
      "types": ["Point"]
    }
  ]
}
~~~

**Verify exact path syntax, geometry types, and index capabilities in your active API for NoSQL version before applying.** Spatial indexes accelerate spatial predicates like **`ST_DISTANCE`, `ST_WITHIN`, and `ST_INTERSECTS`** per supported syntax; they do not replace range or composite indexes for standard order queries.

Distance query example (in meters) using illustrative coordinates:

~~~sql
SELECT c.id, c.name
FROM c
WHERE ST_DISTANCE(
  c.location,
  {"type":"Point", "coordinates":[106.70,10.78]}
) < 5000
~~~

Never treat this query as driving distance or travel time; **spatial distance** is straight-line/geodesic distance, not road-network routing.

## 12. Indexing Policies Do Not Replace the Partition Key

Partitioning is one of the strongest determinants of RU cost. For an `orders` container partitioned by **`/tenantId`**:

~~~sql
SELECT c.id, c.status
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

When the SDK passes **`partitionKey = tenant-a`** in request options, the query stays scoped to that logical partition rather than fanning out container-wide.

However, if `/tenantId` is the partition key and one tenant generates most traffic or storage, that tenant's queries can trigger a **hot logical partition**. Even optimal composite indexes cannot spread a single hot tenant across multiple logical partitions.

### Choose Partition Keys Around the Workload

A strong partition key balances:

- **High cardinality and stability** to avoid concentrating storage or throughput on one value.
- Most requests **know the partition key** at access time.
- Query and transaction contracts fit cleanly within one logical partition.
- Stays well within actual logical partition limits.
- Scales cleanly as tenants and data grow over time.

For SaaS workloads with massive tenants, evaluate **hierarchical partition keys** or alternative key designs where supported, carefully checking routing, transactions, SDK support, and migration complexity. **Never change a partition key just to speed up one slow reporting query** when the vast majority of point reads run smoothly.

## 13. Point Reads: Cheap Lookups Before SQL Queries

Whenever **`id`** and the **partition key value** are known, prefer a **point read**:

~~~text
Order ID      = order-102
Partition key = tenant-a

Cosmos SDK readItem(id, partitionKey)
       |
       v
Routes directly to the logical partition and item
~~~

Compare with:

~~~sql
SELECT * FROM c
WHERE c.id = "order-102"
  AND c.tenantId = "tenant-a"
~~~

The SQL query looks equivalent yet **is not identical** to a point read in execution path or cost. SDK **`readItem(id, partitionKey)`** is typically more efficient for fetching a single known item.

### When Can't You Use a Point Read?

- You only know `email` or `externalOrderId`, not the Cosmos `id`.
- You do not know the item's partition key.
- You need filtering, aggregation, sorting, or multiple items.
- The API searches across multiple non-key attributes.

If most requests look up by `ExternalOrderId`, consider mapping `id` deterministically, maintaining a lookup container/map with clear sync and idempotency rules, or reshaping the data model—rather than firing cross-partition queries on every primary request.

## 14. Single-Partition vs. Cross-Partition Queries

Queries on the `orders` container either route to one partition or scan across multiple partitions.

### Narrow (Single-Partition) Query

~~~sql
SELECT c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
~~~

When the SDK supplies **`PartitionKey(tenantId)`** and proper configuration/permissions hold, Cosmos DB scopes execution to that single logical partition.

### Broad (Cross-Partition) Query

~~~sql
SELECT c.id, c.tenantId, c.totalAmount
FROM c
WHERE c.status = "PENDING"
~~~

Without a partition key, the request may inspect multiple physical partitions, adding RU and latency overhead to query and merge results. As the container grows into more partitions, that same query costs more RUs even if it returns only 10 items.

### Valid Use Cases for Cross-Partition Queries

- Scheduled system-wide reports.
- Privileged administrative searches across tenants.
- Analytics without a natural partition key, better exported to a dedicated analytics platform.

For frequent global reporting, consider **materialized views / aggregate containers, the change feed**, or an analytical store rather than buying huge RU/s to run container-wide scans every second.

### Filtering by Partition Key Does Not Automatically Make Every Query Cheap

Even when scoped to one tenant, if a query:

- Scans millions of items inside that tenant;
- Returns an oversized `largePayload` field;
- Sorts across multiple fields without a composite index;
- Joins across huge arrays;

RU costs will still climb. **Partition routing is essential, yet does not replace query and index tuning.**

## 15. Equality, Range, `IN` Filters, and Parameterization

Common query patterns:

~~~sql
-- Exact status match within a tenant
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
~~~

~~~sql
-- Normalized UTC time range
SELECT c.id, c.status, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.createdAt >= @fromUtc
  AND c.createdAt < @toUtc
~~~

~~~sql
-- Two business statuses
SELECT c.id, c.status
FROM c
WHERE c.tenantId = @tenantId
  AND c.status IN ("PENDING", "CONFIRMED")
~~~

**Parameterization** improves reuse and prevents concatenating raw user input into SQL text. Avoid assuming the Cosmos DB NoSQL query engine shares SQL Server's exact optimizer plans or transaction isolation semantics.

### Data Types Matter

- Consistent ISO 8601 UTC formatting on **`createdAt`** supports clean lexicographical string comparisons and sorting. Mixed formats or timezones yield wrong results.
- Store **`totalAmount`** in clear numeric units (e.g., integer VND or `amountMinorUnits`), avoiding uncontrolled floats for money.
- Standardize **`status`** casing (`CONFIRMED` != `confirmed`).
- Missing fields and **`null`** are not identical; handle `undefined`/`null` carefully in filters and `ORDER BY`.

If queries filter on dates frequently, store **canonical normalized types** rather than calling conversion functions inside every `WHERE` clause.

## 16. Single-Field vs. Multi-Field `ORDER BY`

### Single-Field Sort

~~~sql
SELECT c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
~~~

A range index on **`createdAt`** normally handles a **single-property `ORDER BY`**. Do not add a composite index just for one sort field unless benchmarks on filter+sort combinations prove a gain.

### Two-Field Sort

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

Multi-expression `ORDER BY` queries require a matching composite index per API for NoSQL rules:

~~~json
{
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

### Stable Ordering and Pagination

If multiple orders share the same **`createdAt`**, sorting solely by `createdAt` leaves tie order non-deterministic. Adding a tie-breaker such as `id` may require a **new composite index** and testing across the query, SDK, and pagination:

~~~sql
SELECT c.id, c.createdAt, c.status
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC, c.id ASC
~~~

Here, evaluate a composite index on **`createdAt DESC, id ASC`** against engine rules. **Never assume page 1 and page 2 stay frozen while items are concurrently inserted or deleted**: even with a tie-breaker, live mutations between requests affect paging; see continuation tokens next.

## 17. Projection: Return Only the Fields You Need

Compare two queries:

~~~sql
SELECT *
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

~~~sql
SELECT c.id, c.status, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

**`SELECT *`** returns the entire JSON document, including `items[]`, metadata, `largePayload`, and unused fields. **Projection** returns only what the UI needs, trimming payload bytes, network transfer, and serialization work; exact RU savings depend on the query engine, indexes, and documents and should be measured.

### When to Avoid `SELECT *`

- List APIs displaying 20 orders that only need 4 fields.
- Admin dashboards calculating counts/totals without needing full documents.
- Items carrying `largePayload` or large nested arrays.
- Data exports requiring an explicit allowlist of safe fields rather than leaking newly added fields.

**Projection does not turn a query into a point read** and does not eliminate RUs spent locating or aggregating items. Nor is projection a substitute for field-level authorization on sensitive fields.

## 18. `TOP`, `OFFSET LIMIT`, and Continuation Tokens

### `TOP` Caps Results, Not Query Scope

~~~sql
SELECT TOP 20 c.id, c.createdAt, c.totalAmount
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
~~~

`TOP` limits returned items in Cosmos DB syntax, yet still relies on effective filters and indexes. In a cross-partition query, `TOP 20` may still inspect multiple partitions to identify the global top 20.

### `OFFSET LIMIT` Is Unsuitable for Deep Pagination

~~~sql
SELECT c.id, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.createdAt DESC
OFFSET 10000 LIMIT 20
~~~

`OFFSET 10000` forces the engine to skip large numbers of results before emitting 20 items; **RUs and latency grow with offset depth**. Avoid it as the default pattern for APIs paging through hundreds of thousands of records.

### Continuation Tokens

Cosmos DB query execution emits **continuation tokens** to resume at the next page. The Java SDK exposes paged iterables/fluxes for page-by-page traversal and lets apps pass tokens explicitly. Prefer **SDK paging / continuation tokens** over deep `OFFSET` for multi-page lists.

~~~text
GET /orders?limit=20
   |
   v
Query page 1 -> 20 items + continuation token
   |
   v
GET /orders?cursor=<OPAQUE_TOKEN>
   |
   v
Query page 2 -> 20 items + next token
~~~

Tokens are opaque SDK/service query-state strings—**never parse or hand-edit them**. Never treat a continuation token as authorization; still validate tenant access, query parameters, and avoid logging tokens if they may expose metadata.

**Continuation tokens do not guarantee a frozen snapshot across a mutating list.** If business rules require strict snapshot consistency across pages, design an explicit key/timestamp/cursor contract.

### Items Per Page

A page may return fewer items than `maxPageSize` due to time, throughput, or partition execution bounds. Never assume “end of results” just because a page returned 12 of 20 items while a continuation token is still present. Continue paging until no continuation token remains or your application limit is met.

## 19. Aggregations: `COUNT`, `SUM`, `GROUP BY`

Counting confirmed orders:

~~~sql
SELECT VALUE COUNT(1)
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

Summing totals:

~~~sql
SELECT VALUE SUM(c.totalAmount)
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = "CONFIRMED"
~~~

Grouping by status:

~~~sql
SELECT c.status, COUNT(1) AS orderCount
FROM c
WHERE c.tenantId = @tenantId
GROUP BY c.status
~~~

Aggregations still incur work proportional to matching items and index entries. **`COUNT` is not automatically O(1)** like reading a precomputed counter; cross-partition `COUNT` queries can be costly.

### When Should You Maintain Separate Aggregates?

If dashboards run `COUNT`/`SUM` across millions of orders every few seconds, store pre-aggregated totals by tenant/status/date in a dedicated read container updated via **change feed processing** or an idempotent event-driven workflow.

Trade-offs:

- Dashboard queries become cheap and fast.
- Introduces update lag and consistency management.
- Aggregates require replay and reconciliation if a consumer fails.
- You must govern permissions, partition keys, and indexes on the aggregate container.

Never maintain a “total amount” by blindly incrementing on events that can retry or duplicate; enforce deduplication and business consistency checks.

## 20. Querying Arrays and Nested Properties

An item containing an **`items`** array:

~~~json
{
  "id": "order-102",
  "tenantId": "tenant-a",
  "items": [
    {"sku": "SKU-123", "quantity": 2},
    {"sku": "SKU-456", "quantity": 1}
  ]
}
~~~

### `EXISTS` / `JOIN` to Find a SKU

~~~sql
SELECT c.id
FROM c
WHERE c.tenantId = @tenantId
  AND EXISTS (
    SELECT VALUE i
    FROM i IN c.items
    WHERE i.sku = @sku
  )
~~~

Or using an intra-item `JOIN`:

~~~sql
SELECT c.id, i.sku, i.quantity
FROM c
JOIN i IN c.items
WHERE c.tenantId = @tenantId
  AND i.sku = @sku
~~~

**`JOIN` in Cosmos DB for NoSQL operates within a single item's array data**, not as a relational `JOIN` across two separate containers like Azure SQL. `JOIN`s can multiply intermediate and output rows when arrays are large.

### Array Index Paths

Illustrative path:

~~~text
/items/[]/sku/?
~~~

Using `includedPaths`, array element properties can be indexed. Verify the policy does not exclude this path, queries match exact property casing/types, and **query metrics** confirm the index is utilized.

### When Arrays Grow Too Large

If one order holds thousands of line items, updating a single line rewrites a huge JSON document, inflating write RUs and risking item size limits. Splitting line items into separate documents sharing the same partition key lets you use transactional batches where API-supported, at the cost of extra reads/queries and modeling complexity.

Design models around **aggregate boundaries and access patterns** instead of forcing relational table structures into Cosmos DB indiscriminately.

## 21. String Functions, Expressions, and Scan Risks

Not every predicate optimizes as cleanly as an equality check on a range-indexed path.

### Fuzzy Search Example

~~~sql
SELECT c.id, c.customerId
FROM c
WHERE CONTAINS(c.customerName, @term, true)
~~~

String functions and computed expressions utilize indexes differently depending on the query engine and version; **`CONTAINS`** can use range indexes in certain forms, yet still burn high RUs when patterns have low selectivity or queries span partitions. **Never assume every `CONTAINS` is a full scan, or that every `CONTAINS` is cheap.**

### Anti-Patterns to Measure Carefully

- Running cross-account searches with no partition key filter.
- Applying transformation functions to item fields inside `WHERE`.
- Combining broad `OR`/`IN` clauses with few matches but huge index candidate sets.
- Returning thousands of items only to filter them in Java.
- Querying continuously on paths excluded from the index.
- Using queries instead of point reads when `id + partition key` are known.

If the product needs **full-text search, relevance ranking, typo tolerance, or vector similarity**, evaluate Cosmos DB's dedicated search/index features and/or Azure AI Search against the support matrix, latency/cost, and consistency needs. **Never expect the default range index to replace a dedicated search engine.**

## 22. Java SDK v4: Point Reads with a Partition Key

**Azure Cosmos DB Java SDK v4** uses the **`com.azure.cosmos`** namespace. Example assuming a configured **`CosmosContainer`** using a secure endpoint and credential:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

// container is initialized from a CosmosClient with an appropriate identity.
String orderId = "order-102";
String tenantId = "tenant-a";

CosmosItemResponse<Order> response =
    container.readItem(orderId, new PartitionKey(tenantId), Order.class);

Order order = response.getItem();
double requestCharge = response.getRequestCharge();

System.out.println("RU for point read: " + requestCharge);
~~~

This is a **snippet inside a method with `container` and `Order` already defined**, not a complete standalone program. Combine it with **`CosmosClientBuilder`**, connection settings, repository/service classes, and proper exception handling.

### Why Must You Pass `tenantId` Too?

Cosmos DB requires **`id + partition key`** to route a point read. The same **`id`** can exist in two logical partitions if container rules permit. Passing the wrong partition key returns **404 Not Found** even if an item with that `id` exists in another partition.

### Client Lifecycle

In Spring Boot, instantiate and reuse **`CosmosClient`** and container references across the application lifecycle rather than creating a new client per HTTP request. Configure identity, connection mode, thread safety, and timeouts per SDK guidance, and close the client on shutdown.

## 23. Java SDK: Parameterized Queries with Partition Keys

Example using **`SqlQuerySpec`** with parameters instead of string concatenation, assuming `Order` has fields `id`, `tenantId`, `status`, `createdAt`, and `totalAmount`:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;
import com.azure.cosmos.util.CosmosPagedIterable;
import java.util.List;

String tenantId = "tenant-a";
String status = "CONFIRMED";

String sql = """
    SELECT c.id, c.tenantId, c.status, c.createdAt, c.totalAmount
    FROM c
    WHERE c.tenantId = @tenantId
      AND c.status = @status
    ORDER BY c.createdAt DESC
    """;

SqlQuerySpec query = new SqlQuerySpec(
    sql,
    List.of(
        new SqlParameter("@tenantId", tenantId),
        new SqlParameter("@status", status)
    )
);

CosmosQueryRequestOptions options = new CosmosQueryRequestOptions();
options.setPartitionKey(new PartitionKey(tenantId));
options.setPopulateQueryMetrics(true);

CosmosPagedIterable<Order> results =
    container.queryItems(query, options, Order.class);

for (FeedResponse<Order> page : results.iterableByPage(20)) {
    System.out.println("Page RU: " + page.getRequestCharge());
    for (Order order : page.getResults()) {
        System.out.println(order.id);
    }
}
~~~

This snippet uses **Java text blocks** (JDK 15+) and assumes `Order` exposes `id` directly; real apps typically use getters or Java records depending on serialization setup. On older JDKs, use standard string concatenation. Verify **Azure Cosmos Java SDK v4** method signatures and query-metric accessors against your pinned SDK version.

### Key Points

1. **`setPartitionKey`** scopes the query to one tenant; never trust an unvalidated `tenantId` from client input.
2. **`SqlParameter`** avoids string interpolation in SQL; data access authorization must still be enforced separately.
3. **Projection** fetches only displayed fields; ensure POJO mapping/deserialization handles partial objects.
4. **`iterableByPage(20)`** sets a page-size hint, not a total result cap.
5. **`getRequestCharge()`** returns **per-page** RUs—sum across pages when iterating multiple pages.
6. **`setPopulateQueryMetrics(true)`** enables query diagnostics where supported; log metrics safely without sensitive payloads.
7. Underlying items can mutate between pages; never assume a multi-page query provides snapshot isolation.

### Never Hardcode Account Keys in Code

Wherever supported, use **Microsoft Entra ID / managed identity** for Cosmos DB data-plane access with proper `TokenCredential` and role assignments. Conceptual client setup:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

CosmosClient client = new CosmosClientBuilder()
    .endpoint("https://<ACCOUNT_NAME>.documents.azure.com:443/")
    .credential(new DefaultAzureCredentialBuilder().build())
    .buildClient();

CosmosContainer container =
    client.getDatabase("commerce").getContainer("orders");
~~~

Verify Azure SDK dependencies, Cosmos data-plane roles, networking, and Entra support for your account. **Azure RBAC `Contributor` on a Cosmos account does not grant data-plane query permissions**; Cosmos DB for NoSQL enforces its own data-plane RBAC. Never bake primary account keys into Git or container images to work around identity errors.

## 24. Query Metrics: What to Measure Before Changing Indexes?

Portal Data Explorer, SDK diagnostics, or observability tools can expose **request charges**, **query metrics**, and **index metrics** (depending on SDK, tool, and configuration).

| Metric | Question Answered |
|---|---|
| **Request charge (RU)** | How many RUs did each query or page consume? |
| **End-to-end latency** | How long did it take the client to receive results? |
| **Backend / query execution time** | How long did engine execution take? |
| **Retrieved document count** | How many documents were read/processed internally? |
| **Output document count** | How many matching documents were actually returned? |
| **Index utilization / index metrics** | Were indexes used, and are composite or other paths recommended? |
| **Partition count / fan-out** | How many partitions were visited? |
| **Throttled requests (429)** | Did the query hit throughput limits or a hot partition? |
| **Page count / continuation** | How many round-trips were needed to drain results? |

**Exact metric field names** vary across the Azure Portal, REST headers, and the Java SDK. Query metrics are only meaningful when checked against exact queries, datasets, pages, and tool versions—never invent a “100% index hit” metric if the tool does not report it.

### Low RUs Yet High Latency?

Possible causes:

- Client hosted in a region far from the Cosmos DB region.
- Network, proxy, DNS, or TLS handshake overhead.
- Connection mode, SDK retries, or app-tier resource contention.
- Many continuation pages or cross-region reads.

### High RUs Yet Latency Looks Fine?

Over-provisioned RU/s can mask expensive queries today while inflating bills and risking 429s when traffic rises. **Optimizing RUs matters even when p95 latency currently meets SLOs.**

### Are Index Metrics the Whole Story?

No. A query can have great index utilization and still be expensive due to huge result sets, cross-partition fan-out, array `JOIN` expansion, or oversized payloads. Always read **RUs, retrieved/returned counts, index metrics, partition counts, timing, and query shape** together.

## 25. Before/After Policy Benchmarking

Change policies only after capturing a **baseline** and **reproducible test cases**.

### Preparation

1. Build a representative dataset covering item counts, tenant skew, nested arrays, and payload sizes.
2. Use a **dedicated lab container** or authorized test/clone environment.
3. Record throughput mode (manual/autoscale/serverless), max RU/s, regions, consistency, and SDK version.
4. Back up the **current indexing policy** and query templates/parameters.
5. List the top N queries from logs/telemetry grouped into reads, queries, and writes.
6. Supply exact partition keys in SDK calls whenever known by the use case.
7. Verify permissions/identities and avoid copying real PII into labs unless required.

### Measurement Matrix

| Test | Request Pattern | What to Measure |
|---|---|---|
| **P1** | Point read `id + PK` | RUs, p50/p95 latency |
| **Q1** | Tenant + status equality | RU/page, retrieved vs. output count |
| **Q2** | Tenant + `createdAt` range, `ORDER BY` | RUs, latency |
| **Q3** | Multi-field `ORDER BY` | Composite index support and RUs |
| **Q4** | Deep `OFFSET` vs. continuation paging | Total RUs and duration |
| **Q5** | Per-tenant aggregation | RUs, duration, accuracy |
| **Q6** | SKU search inside nested array | RUs, index metrics |
| **W1** | Bulk writes with representative payload | RU/item, throughput |
| **W2** | Updates to `largePayload` | RU/write, index storage growth |
| **H1** | Peak load with a hot tenant | 429s, throttling, latency |

### Ensuring a Fair Comparison

- Hold data, query parameters, and throughput configuration constant.
- Collect enough samples for median and p95—never rely on one single call.
- Wait until **index transformation completes** before capturing final measurements.
- Isolate unrelated batch loads and background queries when possible.
- Sum **total RUs across the entire result set**, not just page 1.
- Track both **query RU savings** and **write RU / storage increases**.

### Illustrative Evaluation Table

| Query / Operation | Policy A: Avg RUs | Policy B: Avg RUs | Conclusion |
|---|---:|---:|---|
| Q1 tenant + status | 8.0 | 5.5 | B improves this query |
| Q3 multi-order | Index unsupported | 12.0 | B enables the new `ORDER BY` |
| W1 write item | 6.0 | 7.2 | B makes writes costlier |
| W2 update payload | 10.5 | 7.0 | Excluding payload may help |

**All numbers above are hypothetical illustrations for learning comparison methods**, not actual Cosmos DB measurements or guaranteed RU rates. Weight policies by **request frequency × RU/query** and SLO compliance rather than optimizing a single eye-catching query.

## 26. Reading Policies and Query Metrics in the Azure Portal

On an authorized lab subscription:

1. Open the [Azure Portal](https://portal.azure.com) and navigate to your **Azure Cosmos DB account**.
2. Open **Data Explorer** and select the API for NoSQL database and container.
3. Inspect the container's **Indexing Policy**; note `indexingMode`, included/excluded paths, composite, and spatial indexes.
4. Run a read-only query with explicit partition key and parameters.
5. View **Query Stats, Query Metrics, and Index Metrics** where exposed by the current Portal UI.
6. Record RUs, latency, retrieved/output counts, and partition/query plan observations.
7. Compare queries with and without a partition key on **lab data** within allowed resource limits.
8. Never edit a production indexing policy to experiment without benchmarks and a rollback plan.

Portal blade names change over time, and **Data Explorer does not always expose every SDK metric**. If a metric is missing in the Portal, use SDK diagnostics or Azure Monitor rather than concluding the query skipped indexes.

### Note on Query Permissions

Azure control-plane **`Reader`** does not necessarily grant permission to query items in the Cosmos DB data plane. You need appropriate database/container data-plane RBAC or policy-compliant key auth, plus matching network/firewall/Private Endpoint access.

## 27. A Complete Indexing Policy for the Orders API

Suppose the API must:

- Read orders by `id + tenantId`.
- List orders sorted by `createdAt`.
- Filter by `status` and sort by `createdAt`.
- Support a report sorting by **`status ASC, createdAt DESC`**.
- Never query **`largePayload`**.

An **illustrative policy for discussion**:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {
      "path": "/*"
    }
  ],
  "excludedPaths": [
    {
      "path": "/largePayload/*"
    },
    {
      "path": "/\"_etag\"/?"
    }
  ],
  "compositeIndexes": [
    [
      {
        "path": "/status",
        "order": "ascending"
      },
      {
        "path": "/createdAt",
        "order": "descending"
      }
    ]
  ],
  "spatialIndexes": []
}
~~~

### Why These Choices?

1. **`includedPaths: /*`:** Preserves compatibility across known and evolving query patterns.
2. **`excludedPaths: /largePayload/*`:** Cuts indexing overhead for blocks never filtered or sorted.
3. **Composite `status + createdAt`:** Supports the real multi-property `ORDER BY` query.
4. **Empty `spatialIndexes`:** The Orders API runs no GeoJSON spatial queries.
5. **`consistent` / `automatic`:** The app relies on up-to-date indexes for queries.

**This policy is not automatically optimal everywhere**: if 99% of writes update broad fields while only 3 fields are ever queried, selective `includedPaths` could be cheaper. Conversely, if another feature starts filtering inside `largePayload`, excluding it will hurt. Validate every choice with benchmarks and regression tests.

### Remember Indexes for Other Read Models

An **`orders`** container should stay focused on transactional order access patterns. If dashboards need long-term national summaries by date, region, and SKU, build a **projection/aggregate container** or export to an analytics engine instead of stuffing the transactional container with dozens of composite indexes.

## 28. Updating an Indexing Policy and Index Transformation

Updating a policy is not like tweaking a Java query string. Cosmos DB must rebuild or update indexes across **existing items**—a background process called **index transformation**, whose duration depends on data size, throughput, and the nature of the change.

~~~text
Current policy: A
        |
        v
Create proposed policy B
        |
        v
Benchmark on representative lab container
        |
        v
Backup/revision + change approval
        |
        v
Update container indexing policy
        |
        v
Index transformation in progress
        |
        v
Monitor progress, RUs, 429s, and live queries
        |
        v
Transformation complete -> production acceptance tests
~~~

### Why Not Edit Directly in Production?

- Reindexing can **consume throughput** during transformation.
- Query plans and index availability can behave differently while transformation is still running.
- Changing included/excluded paths can slow down or break existing queries.
- Write RUs, index storage, and RU/s requirements may shift.
- Long transformations on large containers mean rolling back is not instantaneous.

### Policy Change Runbook

1. Save **indexing policy A** and baseline query metrics.
2. Verify partition key, throughput model, regions, and consistency.
3. Clone or simulate a representative dataset in a lab environment.
4. Apply policy B in the lab and wait for transformation to finish.
5. Benchmark top queries, writes, and cross-partition reports.
6. Review impacted consumers and prepare halt/rollback criteria.
7. Apply B to production through an approved change process.
8. Monitor index transformation progress via the Portal, SDK, or response headers.
9. Evaluate p95 latency, RUs, 429s, index storage, and application errors.
10. Declare success only after transformation finishes and production metrics stabilize.

### What If Policy B Breaks Queries?

You may have to **restore policy A** via the management plane and wait for a fresh index transformation per service behavior, while throttling load or temporarily adapting queries to protect the system. Never promise an instant rollback just because the policy JSON lives in Git.

### Transactional Considerations

Updating a policy is not like changing a partition key and usually requires no manual item migration—yet **that is no excuse to skip correctness and operational testing**. Whenever excluding paths, audit every query referencing those paths.

## 29. Observing Index Transformation and Query Regressions

A tracking matrix for the change window:

| Metric | Before | During Transformation | After |
|---|---|---|---|
| Index transformation progress | N/A | Track actual percentage | Complete |
| Read / query RUs | Baseline | May fluctuate | Re-measure |
| Write RUs | Baseline | May fluctuate | Re-measure |
| 429 throttling | Baseline | Watch closely | Within SLO |
| p95 API latency | Baseline | Alert if rising | Meets SLO |
| Index storage | Baseline | Changes with index work | Final footprint |
| Application errors | Baseline | Track 4xx/5xx | Meets criteria |

When measuring:

- Separate **Cosmos DB query errors** from **app authorization or network errors**.
- Group metrics by query pattern rather than looking only at account-wide total RUs.
- If manual or autoscale throughput changes concurrently, record it so you do not misattribute effects to the indexing policy.
- Watch per-region metrics and partition heat in multi-region setups.

**Never crank up request rates to stress-test while production is actively reindexing** unless you have dedicated capacity headroom and an approved change window.

## 30. Query Optimization Affects Write RUs Too

Every inserted or updated item maintains index entries according to the active policy. For wide documents or deep arrays, write RUs can be significant.

### Trade-Off Example

JSON item:

~~~json
{
  "id": "order-103",
  "tenantId": "tenant-a",
  "status": "PENDING",
  "createdAt": "2026-11-20T09:00:00Z",
  "largePayload": {
    "rawImportFields": "many fields here",
    "debugContext": "large transient metadata"
  }
}
~~~

If **`largePayload`** is never queried, excluding it reduces index entries, write RUs, and index storage. However, if **`largePayload`** keeps the JSON document huge, you still pay to store, read, and write those payload bytes; excluding from indexes **does not remove the payload from the item**.

### When Payloads Are Very Large

- Offload large raw blobs/documents to **Azure Blob Storage** with a secured reference where fitting.
- Keep only searchable and transactional metadata in Cosmos DB.
- Apply TTL/retention if items expire under policy.
- Mind Change Feed/ETL impacts when mutating many elements triggers extra downstream writes.

**Never split an item across multiple containers just to shave a few RUs** at the expense of consistency, atomicity, query complexity, and security. Data models must reflect real access patterns and transaction boundaries.

## 31. Throughput, Autoscale, 429s, and Hot Partitions

Azure Cosmos DB supports throughput at the **database** or **container** level depending on setup, offering **manual provisioned throughput**, **autoscale**, and **serverless** models per account capabilities.

### 429 Too Many Requests

HTTP 429 indicates requests are being throttled by throughput or service limits. The SDK retries automatically using **`Retry-After`**, yet:

- Never configure infinite retries, as user latency will balloon.
- Evaluate request rates, RU/query, and actual RU/s capacity.
- Hunt for **hot logical partitions**, not just account-wide utilization.
- Check autoscale max throughput and burst shapes.
- Bound concurrency or batch write rates when needed.

### Hot Partitions

~~~text
Container throughput spreads across physical partitions

Tenant A: 80% traffic  ---> one very hot logical partition
Tenant B: 10% traffic
Tenant C: 10% traffic

Result:
  Container-wide RU/s may not even be maxed out
  yet Tenant A can still be throttled.
~~~

**You cannot cure a hot partition merely by adding a composite index.** Lowering RUs per query helps, yet if one partition key value concentrates almost all reads and writes, revisit partitioning, caching, rate shaping, hierarchical/synthetic keys, or tenant isolation.

### Autoscale Is Not Free

Autoscale scales provisioned throughput within its configured band based on demand and billing rules. An expensive query spiking under load pushes autoscale higher, raising bills without fixing the underlying data model.

**Before raising RU/s**, calculate: RU/query × QPS, per-tenant distribution, 429s, p95 latency, retry overhead, and peak forecasts.

## 32. Consistency and Multi-Region Queries

Cosmos DB supports consistency levels—**Strong, Bounded Staleness, Session, Consistent Prefix, Eventual**—per account/region settings and API. Consistency shapes how apps observe writes and can impact latency and RUs depending on topology.

### Key Concepts

- **Session consistency** fits many applications needing read-your-writes when session tokens are handled properly.
- **Eventual consistency** can observe stale data for a period.
- **Strong consistency** carries topology limits and trade-offs per service configuration.
- Multi-region reads/writes require factoring in replication, conflict resolution, network latency, and availability.

**Indexing policies do not govern consistency levels**, and an indexed query **does not guarantee** a remote region's replica has already received the newest write.

### Session Tokens and Pagination

If a user creates an order and immediately queries from another region, verify session handling and SDK request context to ensure expected behavior. Never blame every “new order not visible yet” symptom on indexing.

### Never Infer RPO/RTO from Index Metrics

Index metrics measure query and index execution. RTO and RPO belong to DR, replication, and cutover design and require dedicated drills. Never treat “index updated” as proof that multi-region data replication is complete.

## 33. Data Security and Query Diagnostics

Cosmos DB metrics and logs can contain container names, partition values, query text, IDs, or application context.

Essential rules:

1. **Never log account primary keys, connection strings, or Bearer tokens.**
2. Avoid logging raw query parameters containing emails, `customerId`, PII, or business secrets.
3. Restrict Data Explorer and data query access via scoped data-plane RBAC.
4. For Managed Identities, verify the **Cosmos data-plane role**, not just Azure resource `Contributor`.
5. Enforce network restrictions and **Private Endpoints / Private DNS** where required.
6. Encrypt data using platform features and sound key management processes.
7. Maintain audit trails and retention for indexing policy, throughput, and container changes.
8. Ensure queries always bind `tenantId` from the authorized principal, never trusting client-supplied query strings.
9. Disallow cross-tenant queries in non-admin API clients.
10. Use synthetic data for benchmarks so PII never leaks into lab environments.

### Enforcing Multi-Tenant Isolation via App Authorization

Cosmos DB NoSQL **does not automatically provide SQL-style Row-Level Security like Azure SQL Database** for arbitrary queries. A shared-tenant container enforces tenant isolation across the **app/service layer, identity, resource tokens/roles, data model, and API tests**. Never assume having `/tenantId` as the partition key stops a malicious client if your backend accepts arbitrary `tenantId` inputs.

### Query Parameterization Does Not Replace Authorization

Parameterization prevents SQL injection and keeps query syntax safe, yet it never checks whether the user is allowed to view `tenant-a`. The backend must derive `tenantId` from trusted token claims and verify authorization before returning responses.

## 34. Scenario A: Order Listing Query Burns RUs as Tenant Count Grows

**Context:** Initially the container held 100,000 orders across 10 tenants. A year later it holds 20 million orders across 1,000 tenants. Endpoint:

~~~sql
SELECT TOP 50 c.id, c.createdAt, c.status
FROM c
WHERE c.status = "PENDING"
ORDER BY c.createdAt DESC
~~~

Because `tenantId` is omitted, the query fans out across partitions and merges results, driving RUs higher as data and partitions grow.

### Diagnosis

1. Inspect RUs/query, query metrics, partition counts, and retrieved item counts.
2. Confirm whether the endpoint serves **one tenant** or truly requires global data.
3. If single-tenant, add **`WHERE c.tenantId = @tenantId`** and pass the SDK `PartitionKey`.
4. Check the `createdAt` range index, `status` filter, and composite indexes via benchmarks.
5. Trim projections and use continuation tokens instead of deep `OFFSET`.
6. If global dashboards are mandatory, build an aggregate/read model.

### What Not to Do

Do not immediately 10x RU/s for a query missing its partition key. **Changing the query shape or data model for the exact same functional requirement can cut costs dramatically**—always verify RUs on a realistic dataset.

## 35. Scenario B: Two-Column `ORDER BY` Missing a Composite Index

**Context:** A product manager requests sorting by status and date:

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
ORDER BY c.status ASC, c.createdAt DESC
~~~

Previously the app sorted by one column; once enabled, the query fails requiring a matching composite index or does not run as expected.

### Remediation

1. Verify the exact query, property names/types, and `ORDER BY` directions.
2. Check whether the current indexing policy already includes the composite index.
3. Add the proposed **`status ASC, createdAt DESC`** composite index in a lab container.
4. Wait for index transformation to complete before benchmarking.
5. Validate query correctness, RUs, latency, and write impact.
6. Deploy the **indexing policy first**, then turn on the new query/feature in the app.
7. Monitor post-release metrics and keep policy A ready if rollback is needed.

**Never ship a query to production before its required index is ready** when missing indexes cause execution errors. Feature flags and sequenced rollouts prevent outages.

## 36. Scenario C: Excluding `largePayload` Cuts Write RUs, Breaks a Report

**Context:** The team excludes `/largePayload/*` to lower write costs. The core app only queries `status`, yet an older batch report still filters on:

~~~sql
SELECT c.id
FROM c
WHERE c.largePayload.rawImportRecord = @value
~~~

After the change, the report burns far more RUs or can no longer leverage path indexes efficiently.

### Diagnosis and Fix

1. Audit all real query patterns historically, not just primary API endpoints.
2. Verify whether excluding the path conflicts with reporting needs.
3. Measure RUs, query metrics, and latency before and after.
4. If the report is critical, index only the specific property needed, build a **lookup/read model**, or offload raw data to an analytical store.
5. Re-measure write costs to confirm overall cost efficiency.
6. If rolling back the policy, account for index transformation time and release sequencing.

**A policy tuned for a write-heavy API can hurt read-heavy reporting.** Map ownership and lifecycles for every consumer.

## 37. Scenario D: 429s Despite Spare Container RU/s

**Context:** An autoscale container is well below its max RU/s, yet requests for `tenant-a` receive 429s while `tenant-b` and `tenant-c` run smoothly.

### Hypotheses

- `tenant-a` is a **hot logical partition**.
- One physical partition is locally saturated.
- Expensive queries or bursty writes are piling onto one partition key value.
- Concurrent retries are amplifying load.

### Runbook

1. Inspect 429s by tenant/partition key using safe SDK diagnostics.
2. Measure RU/request, `tenant-a` QPS, and traffic skew.
3. Check whether queries are point reads or cross-partition scans.
4. Cut RU/query via projections, indexing, and query shape.
5. Enforce concurrency caps/backpressure and jittered retries.
6. If skew persists, evaluate **partitioning redesign**, synthetic/hierarchical keys, or isolating the large tenant into its own container.
7. Verify migration/cutover preserves consistency and transaction boundaries.

**Never assume autoscale splits one hot logical partition into infinite throughput.** Partition key selection is a foundational data-model decision.

## 38. Scenario E: Account-Wide `COUNT` Dashboard Is Too Expensive

**Context:** An admin dashboard refreshes every 5 seconds:

~~~sql
SELECT VALUE COUNT(1)
FROM c
WHERE c.status = "CONFIRMED"
~~~

Without a tenant/region filter, the query scans the entire container; returning a single integer still burns substantial RUs.

### Options

- Increase the refresh interval to match real operational need.
- If tenant-scoped counts suffice, pass the partition key.
- Maintain **daily/status aggregate documents** via change feed processing.
- Offload long-term analytics to a dedicated analytics platform.
- Add a TTL cache and surface data freshness clearly.
- Monitor both read and write RUs incurred by the aggregate pipeline.

**Returning one count value does not mean the operation costs one RU.** For financial or accounting counts, build reconciliation and correction workflows rather than relying on non-idempotent event increments.

## 39. Lab Exercise: Optimizing the Orders API in a Cosmos DB Lab

### Objective

Design and evaluate an indexing policy for the **`orders`** container partitioned by **`/tenantId`**, using only an **approved lab Cosmos DB account/container**. If you lack an active subscription, complete the design and hypothetical cost analysis on paper without creating live resources.

### Context

The application features:

- 10 simulated tenants with uneven traffic levels.
- Months of orders with `status`, `createdAt`, `totalAmount`, and `items[]`.
- A **`largePayload`** block never searched by the API.
- Three endpoints: **`GET /orders/{id}`**, **`GET /orders?status=...`**, **`GET /orders/recent`**.
- A dashboard counting orders by status, refreshing every minute.

### Part A: Build an Access Pattern Matrix

| Access Pattern | Parameters / Inputs | Cosmos Operation | Needed Index? |
|---|---|---|---|
| Read exact order | `id + tenantId` | Point read | No custom SQL query index needed |
| Orders by status | `tenantId + status` | Query with `PartitionKey` | Range path `status` |
| Latest orders | `tenantId + createdAt` | Query + `ORDER BY createdAt` | Range path `createdAt` |
| Sort status then date | `tenantId + status/date` | Multi-property `ORDER BY` | Matching composite index |
| Count by tenant/status | `tenantId + status` | Aggregate query | Evaluate with query metrics |
| Search SKU | `tenantId + sku` | `EXISTS`/`JOIN` on `items[]` | Matching array path |
| Account-wide summary report | `status/date` | Likely cross-partition | Consider read model / analytics |

### Part B: Prepare Synthetic Data

In a lab container with the matching partition key, insert sample orders like:

~~~json
{
  "id": "order-lab-0001",
  "tenantId": "tenant-lab-a",
  "status": "PENDING",
  "createdAt": "2026-11-20T08:00:00Z",
  "customerId": "customer-lab-001",
  "totalAmount": 50000,
  "items": [
    {"sku": "SKU-LAB-01", "quantity": 1}
  ],
  "largePayload": {
    "rawImportRecord": "synthetic test data"
  }
}
~~~

**Never generate millions of items for learning without an approved budget and capacity plan.** Start small and scale up only when the lab has dedicated capacity and a cleanup plan.

### Part C: Run Baseline Queries

1. Point read using **`id + partition key`**.
2. Query **`WHERE tenantId/status`**, projecting only `id`/`status`.
3. Query **`ORDER BY createdAt DESC`** within a tenant.
4. Query **`ORDER BY status ASC, createdAt DESC`**.
5. Query `COUNT` by status within a tenant.
6. Run container-wide summary queries only if permitted.

For each query, record **RUs/page**, p50/p95 latency given enough samples, output count, and index/query metrics where available.

### Part D: Propose Policy B

Pick one of two approaches:

**Approach 1 — Keep wildcard include, exclude `largePayload`, and add a composite index**:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [{"path": "/*"}],
  "excludedPaths": [
    {"path": "/largePayload/*"},
    {"path": "/\"_etag\"/?"}
  ],
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ],
  "spatialIndexes": []
}
~~~

**Approach 2 — Index only paths serving core queries**, if you have full regression tests for all other queries:

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"},
    {"path": "/items/[]/sku/?"}
  ],
  "excludedPaths": [{"path": "/*"}],
  "compositeIndexes": [
    [
      {"path": "/status", "order": "ascending"},
      {"path": "/createdAt", "order": "descending"}
    ]
  ]
}
~~~

**Apply only on a lab container** and verify API for NoSQL schema/path syntax. The two policies do not behave identically for every query. Wait for index transformation to finish before comparing.

### Part E: Re-Benchmark

| Item | Policy A | Policy B | Pass? |
|---|---|---|---|
| Point read RUs | Record value | Record value | Evaluate |
| Tenant + status query RUs | Record value | Record value | Evaluate |
| Multi-`ORDER BY` works | Yes / No | Yes / No | Functional |
| Write RUs/item | Record value | Record value | Within budget |
| Index storage | Record value | Record value | Expected |
| 429s during lab peak | Record value | Record value | No outage |
| API p95 latency | Record value | Record value | Meets lab SLO |

If Policy B saves 5 RUs/query while adding 3 RUs/write, weigh it by actual traffic frequency:

~~~text
Assumed rates:
  100 queries/sec × 5 RUs saved = 500 RUs/sec saved
  200 writes/sec  × 3 RUs added = 600 RUs/sec added

Estimated net difference:
  500 - 600 = -100 RUs/sec
~~~

This illustration shows Policy B **is not guaranteed to save RUs** under high write volume—before even counting latency, storage, or 429s. Decide using real workload telemetry.

### Part F: Prepare a Production Change Runbook

Draft a one-page runbook covering:

1. Deployment window, owner, and approver.
2. Versioned Policy A and B definitions and diff.
3. List of affected queries and consumers.
4. Estimated index transformation time and how progress will be tracked.
5. Pre-change RU, latency, and 429 baselines.
6. Halt/rollback criteria and API fallbacks if query errors spike.
7. Temporary throughput/reindexing cost estimate if needed.
8. Post-transformation validation and ongoing monitoring window.

Never modify production indexing policies during a lab without explicit owner approval. Keep this exercise to **design and documentation** unless running inside an authorized lab.

## 40. Pre-Production Checklist for Indexing Policies

- [ ] Verified the account is **Azure Cosmos DB for NoSQL**.
- [ ] Built an access pattern matrix covering APIs, reports, batch jobs, and admin queries.
- [ ] Partition key aligns with data/throughput distribution and query routing.
- [ ] Distinguished `id + PK` point reads from SQL single-item queries.
- [ ] Captured baseline RUs, p95 latency, output counts, 429s, and query metrics.
- [ ] Critical paths match exact property names, types, and casing.
- [ ] Included/excluded paths are justified; no actively queried field is excluded.
- [ ] Multi-property `ORDER BY` queries have matching composite indexes.
- [ ] Spatial indexes added only when GeoJSON/spatial queries actually require them.
- [ ] Queries pass the partition key whenever possible; admin cross-partition queries are governed separately.
- [ ] Projections limit returned fields; avoided unnecessary `SELECT *` on bloated documents.
- [ ] Pagination uses continuation tokens where appropriate; deep `OFFSET` avoided.
- [ ] Large aggregations measured for RUs and evaluated for read models / change feed.
- [ ] Java SDK uses parameterized queries, managed identity, and client reuse.
- [ ] No Cosmos keys, secrets, or PII in source code or query diagnostics.
- [ ] New policy tested in lab with **index transformation completed** prior to benchmarking.
- [ ] Measured read/write RUs, index storage, query latency, and peak 429s.
- [ ] Strategy in place to detect hot partitions and mitigate skew.
- [ ] Autoscale/manual throughput sized realistically—not used to mask query anti-patterns.
- [ ] Multi-region consistency and session token behavior verified for the use case.
- [ ] Change approval, archived old policy, and rollback plan (including reindex time) ready.
- [ ] Dashboards and alerts segmented by tenant, container, region, and request type where supported.
- [ ] Budgets, tags/owners, and cleanup policies established for lab copies.

## 41. Self-Check Questions

1. Is the indexing policy in Cosmos DB configured at the account level or the container level?
2. How do Azure Cosmos DB for NoSQL's query language and indexing differ from Azure SQL Database?
3. How do RUs differ from RU/s?
4. Why does a point read require both `id` and the partition key?
5. When does a query execute cross-partition?
6. Why can a cross-partition query returning only 10 items still burn high RUs?
7. How does `indexingMode: consistent` differ from `none`?
8. Does automatic indexing automatically generate every composite index?
9. What is the effect of `includedPaths: /*` paired with `excludedPaths: /largePayload/*`?
10. How do `/status/?` and `/items/[]/sku/?` differ in JSON structure?
11. When is a composite index required for multi-property `ORDER BY`?
12. Do path order and ASC/DESC directions matter in a composite index?
13. When do you use a spatial index and GeoJSON?
14. How does indexing many paths affect write RUs and index storage?
15. Why shouldn't you disable indexing on a production container solely to lower write RUs?
16. Can a bad partition key be completely fixed by adding composite indexes?
17. If 50 AKS pods query Cosmos DB concurrently, which metrics should you inspect?
18. How does `SELECT *` hurt performance on items with `largePayload`?
19. Why is `OFFSET 10000 LIMIT 20` usually unsuitable for deep pagination?
20. Do continuation tokens guarantee an immutable snapshot?
21. Is `COUNT` across millions of items O(1) by default?
22. How does `JOIN` in API for NoSQL differ from a relational SQL `JOIN`?
23. When should you consider a read model or aggregate container?
24. How should the Java SDK configure partition keys and SQL parameters?
25. Why must you sum RUs across **all pages** rather than reading only the first page?
26. What insights do query metrics and index metrics provide beyond raw latency?
27. Why must policy benchmarks wait until index transformation completes?
28. Are the savings from excluding `largePayload` reduced if the raw JSON document stays huge?
29. How can a hot partition trigger 429s even when total RU/s is not exhausted?
30. Does autoscale automatically fix partition key skew?
31. How does the consistency level affect visibility of recent writes from another region?
32. Why must `tenantId` be bound to the authenticated principal?
33. When should you prefer dedicated full-text/vector search tools over API for NoSQL range indexes?
34. If query RUs drop while write RUs jump sharply, what criterion guides your policy decision?

## 42. References

- [Azure Cosmos DB indexing overview](https://learn.microsoft.com/azure/cosmos-db/index-overview) — indexing architecture and fundamentals for API for NoSQL.
- [Indexing policies in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/index-policy) — JSON policies, paths, composite/spatial indexes.
- [Composite indexes for Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/index-policy#composite-indexes) — query patterns requiring multi-property indexes.
- [Optimize query cost in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/optimize-cost-reads-writes) — RUs, queries, and optimization strategies.
- [Optimize query cost with indexing and query metrics](https://learn.microsoft.com/azure/cosmos-db/optimize-cost-reads-writes#optimizing-queries) — inspecting query plans and costs.
- [Partitioning and horizontal scaling](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview) — logical/physical partitions and partition keys.
- [Request Units in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/request-units) — RUs, RU/s, and cost models.
- [Azure Cosmos DB for NoSQL SQL query language](https://learn.microsoft.com/azure/cosmos-db/nosql/query/) — `SELECT`, `WHERE`, `ORDER BY`, and functions.
- [Pagination in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/query/pagination) — continuation tokens and page sizes.
- [Index metrics for Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/index-metrics) — evaluating index utilization.
- [Azure Cosmos DB Java SDK v4](https://learn.microsoft.com/azure/cosmos-db/nosql/quickstart-java) — Java client, point reads, and queries.
- [Microsoft Entra RBAC for Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access) — data-plane identity and scope.
- [Autoscale provisioned throughput](https://learn.microsoft.com/azure/cosmos-db/provision-throughput-autoscale) — throughput for fluctuating traffic.
- [Monitor Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/monitor) — metrics, diagnostics, and alerts.
- [Azure Cosmos DB pricing](https://azure.microsoft.com/pricing/details/cosmos-db/autoscale-provisioned/) — pricing model; verify current region and tier.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating lab and production costs.

**Conclusion:** Optimizing Cosmos DB queries goes far beyond toggling a single index. Start from **access patterns and the partition key**, prefer **point reads**, scope queries tightly, apply sound projections and pagination, and add **composite or spatial indexes only for real needs**. Measure every indexing policy change across **RUs, latency, retrieved/output counts, write overhead, index storage, and 429s** on representative datasets, and track index transformation to completion. Only by measuring first, rolling out safely, and aligning data, networking, and authorization can you optimize performance, reliability, and Azure costs together.
