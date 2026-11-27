# Data Access Patterns and Key Design for NoSQL

In serverless applications, Java functions typically spin up upon an HTTP request, message, or event, perform a portion of the business logic, and exit. The database must persist state across invocations and serve many functions running concurrently. With distributed NoSQL, performance and cost depend heavily on how the application accesses data and how data is partitioned. A schema that looks clean on paper but fails to support primary queries can force each request to scan many records, generate multiple network round-trips, or concentrate load on a single partition.

NoSQL design therefore starts with the question: **how does the application need to read and write data?** Only after listing access patterns do we choose item/document structure, partition keys, sort keys, indexes, and load distribution strategies. This approach suits many distributed key-value and wide-column stores. Document and graph databases have their own query characteristics, yet still require identifying workloads, indexes, query limits, and scaling strategies before designing.

## 1. NoSQL is not a single database type

NoSQL is a family of database management systems with differing models and trade-offs. You should not apply a single key formula to all of them.

| Data group | Typical structure | Strong queries | Considerations |
|---|---|---|---|
| Key-value | One key identifies one value/item | Key-based reads/writes | Query capability depends on supported keys and indexes |
| Wide-column | Partition key, clustering/sort columns, and columns | Reading a partition or an ordered key range | Partitioning, clustering, and partition size must be designed |
| Document | JSON/BSON or similar documents | Searching by fields, nested fields, and indexes | Indexes, document size, and query plans affect performance |
| Graph | Nodes, edges, and properties | Traversal along relationships | Relationship model and traversal depth determine cost |

Partition keys, sort keys, and item collections are especially critical for distributed key-value/wide-column stores. In document stores, a primary key typically identifies a document while secondary indexes serve field-based queries. In graph stores, design prioritizes relationships and traversals. This article focuses on access patterns and key design for key-value/wide-column distributed NoSQL stores, while pointing out parts that apply more broadly.

## 2. Start from access patterns

An access pattern describes a data operation the application must perform, including filter criteria, ordering, result limits, and update behavior. Do not merely write "read order"; write specifically "read one order by tenant and order ID", "list a customer's newest orders", or "find orders awaiting payment in a region".

For example, an ordering application might have the following access patterns:

| Code | Operation | Criteria | Expected result |
|---|---|---|---|
| AP1 | Get order | `tenantId + orderId` | One order |
| AP2 | List customer orders | `tenantId + customerId`, sorted newest first | One page of orders |
| AP3 | Get orders awaiting payment | `tenantId + status`, sorted by creation time | One page of work items |
| AP4 | Get order details | `tenantId + orderId` | Order and line items |
| AP5 | Update order status | `tenantId + orderId`, check current version | One conditional update |
| AP6 | Look up processed event | `consumerName + eventId` | One inbox marker or absent |

For each pattern, determine read/write frequency, average and maximum item counts, data size, target latency, consistency requirements, and growth potential. A pattern invoked very frequently can influence partition design far more than a pattern run only in rare administrative tasks.

A useful design table can add columns for `Read QPS`, `Write QPS`, `Target p95`, `Page size`, `Consistency`, and `SLA`. These estimates do not need to be exact upfront; they help catch patterns that risk creating hotspots or high index costs early.

## 3. Query-driven data design rules

In relational databases, modeling typically starts from entities and relationships, then uses joins to produce results. In many distributed NoSQL stores, joining across entities is neither cheap nor even supported. Applications typically read an item collection pre-sorted by key, or use a pre-built index tailored to a pattern.

This leads to several principles:

1. List the queries to support before deciding on the storage structure.
2. Every important query must have a suitable key or index access path.
3. Place data commonly read together into the same item collection or document if size and lifecycle align.
4. Accept deliberate denormalization when it reduces read counts or avoids hot joins.
5. Define how copies of data are updated and what degree of eventual consistency the business tolerates.
6. Check service-specific limits on partitions, item/document size, transactions, indexes, and throughput.

Denormalization does not mean copying every field everywhere. Each copy needs a clear query purpose, a data owner, and an update strategy. If the same information is replicated into multiple projections, accept update lag and build a rebuild mechanism in case consumers miss events.

## 4. Partition keys and sort keys

In distributed key-value/wide-column stores, the partition key determines the group of data stored or routed together in a logical partition. The sort key (also called clustering key or range key depending on the engine) orders items within that group. A primary key may consist solely of a partition key or a composite of partition key and sort key.

Example with order data:

```text
Partition key (PK)        Sort key (SK)                 Item type
TENANT#t-42#ORDER#o-1001  META                         Order metadata
TENANT#t-42#ORDER#o-1001  LINE#0001                    Order line 1
TENANT#t-42#ORDER#o-1001  LINE#0002                    Order line 2
TENANT#t-42#ORDER#o-1001  PAYMENT#p-88                 Payment reference
TENANT#t-42#ORDER#o-1002  META                         Order metadata
TENANT#t-42#CUSTOMER#c-7  ORDER#2026-11-17T10:30#o-1001 Customer order index
```

Items sharing the same partition key form an item collection. With `TENANT#t-42#ORDER#o-1001`, the application can retrieve metadata, line items, and payment references in a single query by partition key, optionally constraining the sort key by prefix or range depending on the database.

The sort key should encode order or item type in a queryable way. A common pattern is `TYPE#timestamp#uniqueId`; the timestamp uses a format whose lexicographical order matches chronological order, such as ISO-8601 UTC with uniform precision. Append a unique ID so two items at the same timestamp do not overwrite each other.

### Key-based read examples

```text
GetItem:
  PK = TENANT#t-42#ORDER#o-1001
  SK = META

Query:
  PK = TENANT#t-42#ORDER#o-1001
  SK begins_with LINE#

Query:
  PK = TENANT#t-42#CUSTOMER#c-7
  SK between ORDER#2026-11-01 and ORDER#2026-12-01
  ScanIndexForward = false
```

The syntax above illustrates the query model, not universal vendor syntax. A database may use `partition key`, `clustering column`, `range key`, or document indexes under different names.

## 5. Choosing partition keys to distribute load

The partition key affects where data is distributed and how read/write load is split across partitions. A good key typically has sufficiently high cardinality and relatively even activity distribution. Keys with few distinct values or where a single value receives most requests easily create hot partitions.

Example choices:

| Partition key | Advantages | Risks |
|---|---|---|
| `status` | Easy to query all orders by status | Few distinct values; `PENDING` can become a hotspot |
| `tenantId` | Easy data isolation per tenant | Large tenants may concentrate most load in one logical partition |
| `orderId` | High cardinality, good distribution | Cannot directly list all orders for a customer |
| `customerId` | Convenient per-customer order queries | Very large or highly active customers can create hot partitions |
| `tenantId#shard` | Splits load of large tenants | Queries must know or fan out across multiple shards |

Do not look solely at the count of distinct keys. Examine the request distribution across keys. A key with millions of values can still run hot if 30% of traffic concentrates on a single customer or tenant. Historical growth matters too: a partition key that is balanced today can become skewed as one tenant grows.

### Hot partitions and write sharding

A hot partition occurs when one partition receives more requests or capacity demand than the service can stably handle. Common symptoms are throttling, rising latency, increased retries, and skewed capacity distribution.

If a tenant or aggregate experiences very high write throughput, you can add a shard suffix:

```text
PK = TENANT#t-42#SHARD#00
PK = TENANT#t-42#SHARD#01
...
PK = TENANT#t-42#SHARD#15
```

The application picks a shard via a hash of a stable ID or round-robin distribution. This increases the number of partitions able to absorb writes, but tenant-wide queries must read multiple shards and merge results. Global pagination also becomes harder because continuation state must be maintained per shard. Use write sharding only when metrics reveal a hotspot and the read fan-out cost is acceptable.

Another option is adding time to the key for append-only data, such as `TENANT#t-42#DAY#2026-11-17`. This bounds group size by day, though queries spanning multiple days must read multiple partitions. Choose time granularity based on write rate, retention, and query window.

## 6. Designing sort keys and composite keys

Sort keys commonly support fetching an item type, a time range, or an ordered subset. Composite keys join multiple components into one string with a delimiter and encoding convention.

Example:

```text
PK = TENANT#t-42#CUSTOMER#c-7
SK = ORDER#2026-11-17T10:30:00.000Z#o-1001
```

Queries by customer can read the newest orders first. When filtering by item type is needed, prefixes distinguish `ORDER#`, `ADDRESS#`, or `PREFERENCE#`.

Rules for building composite keys:

- Use meaningful prefixes to prevent collisions across entity types.
- Normalize letter case, Unicode, delimiters, and timezones.
- Encode or escape input values if they can contain the delimiter.
- Place sorting fields in the appropriate position; use fixed-width formats or ISO-8601 UTC when lexicographical order is needed.
- Add a unique tie-breaker when two records can share the same timestamp.
- Do not put secrets or personal information directly into keys.
- Keep key rules stable; changing how keys are constructed usually means migrating data or supporting two key versions during transition.

Do not cram too many fields into a key just to avoid creating an index. Keys should serve real access patterns while preserving load distribution. If a query needs to search by an attribute outside the primary key, consider a secondary index or dedicated projection instead of an overly complex key.

## 7. Item collections and single-table design

Some NoSQL stores allow storing multiple item types in the same table with a partition key and sort key. This model is often called single-table design. Each item type can have different attributes while sharing the key structure.

Example:

| PK | SK | Key attributes | Access pattern |
|---|---|---|---|
| `TENANT#t-42#ORDER#o-1001` | `META` | status, total, createdAt | Get order by ID |
| `TENANT#t-42#ORDER#o-1001` | `LINE#0001` | productId, quantity, price | Get order line items |
| `TENANT#t-42#ORDER#o-1001` | `PAYMENT#p-88` | paymentStatus, providerRef | Get order payments |
| `TENANT#t-42#CUSTOMER#c-7` | `ORDER#2026-11-17T10:30#o-1001` | orderId, total, status | List customer orders |
| `TENANT#t-42#STATUS#PENDING` | `2026-11-17T10:30#o-1001` | orderId, customerId | List pending orders via index or projection |

Single-table design can reduce read counts and fetch related items in one query. In return, key structures and access patterns must be designed carefully; attribute names may differ across item types, indexes require careful management, and ad hoc queries are usually harder.

Multiple tables or collections are also a sound choice when entities have very different lifecycles, ownership, throughput, or access patterns. There is no rule that every NoSQL application must use a single table. Compare the operational complexity and query cost of each option.

## 8. Secondary indexes: expanding access paths

When the primary key does not serve an important access pattern, the database may support secondary indexes. An index provides an additional access path based on different attributes.

Common forms:

- **Global secondary index (GSI):** has its own partition/sort keys, enabling queries partitioned differently from the base table. Index data may be updated asynchronously and reads may be eventually consistent depending on the service.
- **Local secondary index (LSI):** shares the base table's partition key with a different sort key, if supported by the database. Typically has structural limits and must be defined at table creation.
- **Document store secondary index:** indexes one or more fields, potentially including compound, sparse, partial, or multikey indexes depending on the product.

Example to find orders by status and time:

```text
Base table:
  PK = TENANT#t-42#ORDER#o-1001
  SK = META

GSI1:
  GSI1PK = TENANT#t-42#STATUS#PENDING
  GSI1SK = 2026-11-17T10:30:00.000Z#o-1001
```

When status changes from `PENDING` to `PAID`, the application updates the index attributes so the item leaves the pending group and appears in the paid group. If the index updates asynchronously, a brief window may return stale results or omit new ones. The API must decide whether eventual consistency is acceptable or whether to re-read from the primary source.

Every index incurs storage and write costs. When an item is inserted, updated, or deleted, affected indexes must also be updated. Indexing every field increases write amplification, storage footprint, and complexity. Only create indexes that support high-value access patterns; measure query counts and latency before keeping an index long-term.

### Sparse indexes

Some databases include an item in an index only when the item contains the index key attribute. This is a sparse index. For example, only orders with `nextActionAt` appear in an index for due tasks. Completed orders do not need to appear in that index. Sparse indexes can reduce storage and scan costs compared to indexing every item, if the service supports these semantics.

## 9. Denormalization and read models

NoSQL often uses denormalization to serve queries without joins. For example, an order item might store `customerName` at the time of ordering to display order history without an extra read of the customer profile. A dashboard read model might aggregate order counts by day and status.

When source data changes, copies must be updated. Updates can happen synchronously within the same transaction if supported by the database, or by emitting events for consumers to update projections asynchronously. Asynchronous updates introduce eventual consistency: the read model can lag behind the primary source.

Before denormalizing, answer:

1. Which query does the copy serve and who owns it?
2. When source data changes, is the copy updated via transaction, outbox, or event consumer?
3. If events are delivered twice or out of order, how does the projection handle it?
4. Can the copy be rebuilt from the primary source or event history?
5. How long can the API tolerate displaying stale data?

For historical data, storing a snapshot of values at the time of the business event can be more accurate than continuously syncing with the current profile. For instance, invoices typically must preserve the name and address at issuance for historical integrity.

## 10. Pagination and range queries

For large datasets, avoid loading all results into a single function invocation. Use page limits and continuation tokens/cursors. Many NoSQL databases return a continuation key such as `LastEvaluatedKey`, continuation token, or cursor; the next request sends the token back to resume from where reading stopped.

API example:

```http
GET /customers/c-7/orders?limit=25&cursor=eyJwayI6Li4ufQ
```

```json
{
  "items": [
    { "orderId": "o-1001", "status": "PAID" },
    { "orderId": "o-1000", "status": "PENDING" }
  ],
  "nextCursor": "eyJwayI6Li4ufQ"
}
```

Cursors should be encoded and signed or protected server-side if they contain internal keys. Do not allow clients to arbitrarily alter partition keys, tenant IDs, or query criteria through a cursor. Cap page sizes to prevent a single request from pulling excessive data and exhausting function memory/time.

Offset pagination (`page=100`) is usually a poor fit for partitioned NoSQL because the database may have to skip many items before returning a page. Cursor/keyset pagination is typically more stable and economical. If data changes while a user paginates, results may not reflect a consistent snapshot; if business rules require a snapshot, use native snapshot features or an appropriate version/cutoff.

With queries fanning out across multiple shards, each shard has its own continuation token. The API can bundle them into a composite cursor and merge results in order. This design increases complexity and cost; avoid fan-out if the pattern can be served by a single well-distributed partition or index.

## 11. Consistency, conditional updates, and concurrency

Serverless functions can run concurrently across many instances. Two invocations can read the same value and overwrite each other's updates. Do not rely on function call ordering or an in-memory variable to protect data.

Common mechanisms:

- **Conditional writes:** update only when a condition holds, such as `status = PENDING` or the item does not yet exist.
- **Optimistic locking:** store `version`; update under the condition that the current version equals the value read, then increment version.
- **Atomic counters:** use atomic increment/decrement operations when supported by the database, instead of application-level read-modify-write.
- **Transactions:** group changes that must commit or roll back together within the database's item, partition, and time limits.
- **Idempotency keys:** protect resource creation against request retries or message redeliveries.

Optimistic locking example:

```text
Read order:
  orderId = o-1001
  status = PENDING
  version = 7

Conditional update:
  SET status = PAID, version = 8
  IF version = 7 AND status = PENDING
```

If another invocation already updated version to 8, the condition fails. The application must re-read and decide whether to retry, return a conflict, or apply another business rule. Do not infinitely retry a business conflict.

Not all NoSQL databases support transactions identically. Some support atomicity only within a single item, while others support multi-item transactions within specific bounds. Design transaction boundaries according to actual capabilities rather than assuming ACID across multiple partitions or services.

## 12. Java example: centralizing key construction

Separating key-building logic from handlers prevents functions from generating inconsistent keys. The example below illustrates a convention for an orders table; a repository adapter maps it to a specific SDK.

```java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class OrderKeys {
    private static final DateTimeFormatter SORT_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private OrderKeys() {}

    public static String orderPk(String tenantId, String orderId) {
        return "TENANT#" + safe(tenantId) + "#ORDER#" + safe(orderId);
    }

    public static String metadataSk() {
        return "META";
    }

    public static String lineSk(int lineNumber) {
        return "LINE#%04d".formatted(lineNumber);
    }

    public static String customerOrderPk(String tenantId, String customerId) {
        return "TENANT#" + safe(tenantId) + "#CUSTOMER#" + safe(customerId);
    }

    public static String customerOrderSk(Instant createdAt, String orderId) {
        return "ORDER#" + SORT_TIME.format(createdAt) + "#" + safe(orderId);
    }

    private static String safe(String value) {
        if (value == null || value.isBlank()
                || value.contains("#") || value.contains("\n")) {
            throw new IllegalArgumentException("Invalid key component");
        }
        return value;
    }
}
```

In production code, an encoding function can be used instead of rejecting delimiters, depending on ID formats. Ensure all writers and readers follow the exact same rule. The timestamp format in the example has millisecond precision; if multiple records share the same timestamp, the order ID acts as a tie-breaker. Do not alter the formatter once data exists without a migration plan.

## 13. Java example: access-pattern-driven repository

The domain layer should not know vendor-specific index names or key structures. The repository can express operations in business terms, while the adapter translates them into `GetItem`, `Query`, index queries, or equivalent commands.

```java
import java.util.List;
import java.util.Optional;

public record OrderSummary(
        String orderId,
        String status,
        long total) {}

public record Page<T>(List<T> items, String nextCursor) {}

public interface OrderRepository {
    Optional<Order> findById(String tenantId, String orderId);

    Page<OrderSummary> findRecentByCustomer(
            String tenantId,
            String customerId,
            int pageSize,
            String cursor);

    boolean changeStatus(
            String tenantId,
            String orderId,
            long expectedVersion,
            String newStatus);
}
```

`findRecentByCustomer` maps to access pattern AP2 and can use the customer partition key with a time-ordered sort key. `changeStatus` maps to AP5 and should be implemented via a conditional update. `cursor` is decoded and validated by the adapter; the domain does not need to depend on the database's continuation token format.

Do not create a generic method like `findByAnyField(Map<String, Object> filters)` if the database cannot execute arbitrary filter combinations efficiently. Such flexible APIs easily lead to table scans, expensive queries, and difficult access control enforcement. Expose explicit methods for supported access patterns.

## 14. Serverless impact on NoSQL design

FaaS can scale invocation counts very rapidly. This places special demands on the database:

- **Connections and clients:** safely reuse SDK clients at the instance scope to avoid initializing connections on every request; never store mutable business state in static variables.
- **Concurrency:** bound maximum concurrent invocations according to database throughput and connection limits. If a function scales to thousands of instances, even a small pool per instance can create a huge total connection count.
- **Retries:** throttling errors can trigger synchronized retry storms. Use backoff/jitter, concurrency limits, and queues to smooth traffic.
- **Timeouts:** set sensible function, SDK, and database timeouts; do not leave clients waiting longer than the invocation limit without cancellation or workflow continuation.
- **Cold starts:** minimize client creation and config loading overhead; measure initialization time and query latency in a production-like environment.
- **Cost:** monitor read/write capacity or request units, storage, indexes, backups, networking, retries, and function cost. An access pattern that scans many items can cause cost to grow alongside data volume.

For bursty workloads, queues help smooth write rates. Set maximum concurrency on event source mappings or equivalent mechanisms so the database is not overwhelmed. When queue backlog grows, track oldest message age and completion throughput to decide whether to add workers or investigate bottlenecks.

## 15. Multi-tenancy and key security

In multi-tenant systems, the tenant ID is often part of the partition key or query filter so data is partitioned by tenant. However, including tenant ID in the key does not automatically guarantee data isolation. Every request must derive the tenant from an authenticated identity or trusted context, never trusting an arbitrary tenant ID in the request body.

Rules to enforce:

1. Repositories always accept tenant context and build tenant-prefixed keys or apply corresponding filter/partition conditions.
2. Never allow clients to pass raw PK/SK values directly into public APIs.
3. Verify authorization on every resource, even when the order ID is known.
4. Set limits and monitor high-traffic tenants; sharding may be needed for large tenants.
5. Never embed emails, phone numbers, access tokens, or secrets inside keys.
6. Encrypt data, scope permissions by function/service, and restrict read access to backups/exports.

If tenant ID is the sole partition key, a large tenant can create a hot partition. If shards are added, you must have a tenant mapping rule and cross-shard query support. Security and load distribution must be considered together.

## 16. TTL, data lifecycle, and long-term retention

Time to live (TTL) lets the database automatically expire items after a timestamp, if supported by the service. TTL is useful for sessions, idempotency records, cache metadata, temporary workflow state, or ephemeral data. Deletion may occur asynchronously after the TTL timestamp; do not treat TTL as a precise timer to trigger business logic at an exact moment.

Before setting a TTL, determine:

- After how long can data be deleted, and are there audit requirements?
- Over what window can consumers still retry or replay?
- How much longer than the retry window must idempotency records persist?
- Do copies in indexes, backups, streams, or archives have separate retention policies?
- Must data be exported to object storage/a data lake before expiration?

For order history, invoices, or audit data, do not apply a TTL solely to save storage without explicit retention policies and archival obligations.

## 17. Key changes and migrations

A key schema is part of the data contract. When changing a partition key, sort key, or index, existing data does not automatically move to the new structure. Migration may require reading and rewriting items, creating new indexes, backfilling, verifying counts, and shifting traffic in phases.

A safe transition process typically includes:

1. Design the new key version, documenting which access pattern improves and what costs are incurred.
2. Create the new index/table and test with sample data or shadow traffic.
3. Backfill existing data in bounded batches so the database is not overloaded.
4. During transition, dual-write or use outbox/CDC to keep new data synchronized; avoid dual-writes without drift detection.
5. Compare read results between old and new keys; measure latency, throttling, and missing records.
6. Switch readers to the new key while keeping a rollback path for a defined window.
7. Stop writing to and delete the old structure once confirmed that no consumers still depend on it.

If keys are built in code across multiple functions, publish a shared library or module and test compatibility before changing conventions. Do not let individual services unilaterally change delimiters, timezones, or casing.

## 18. Observing and optimizing access patterns

Monitor performance per access pattern rather than only at the aggregate database level. Useful metrics include:

- Counts of `Get`/`Query`/`Scan` or equivalent operations.
- Read/write units or request units by table, index, and tenant.
- p50/p95/p99 latency by repository method and access pattern.
- Items read vs. items returned; scan/filter ratio.
- Throttling, retries, conditional check failures, and transaction conflicts.
- Item/document sizes, partition sizes, and load distribution across partition keys.
- Index, storage, backup, TTL cleanup, and network costs.

If a query reads thousands of items and filters down to a few, an index may be missing or the key may be poorly suited. If one partition receives unusually high load, review cardinality and skew. If many requests read multiple individual items, consider batch gets or an item collection design to fetch related data together. Only alter schemas after measuring patterns and understanding impacts on writers, readers, indexes, caches, and event consumers.

Do not log full documents for diagnostics. Log the access pattern name, duration, items read/returned, index used, outcome, and sanitized correlation IDs. Avoid putting partition keys containing personal data into high-cardinality metric labels.

## 19. When does NoSQL fit and when to consider other models?

Distributed NoSQL fits when access patterns are predictable, high throughput is required, data structure is flexible, or partition-based scaling is needed. It is especially useful for key lookups, item collections, event projections, sessions, and serverless workloads with spiky traffic.

A relational database may be a better fit when the application needs flexible joins, complex multi-table transactions, strong relational constraints, or frequent ad hoc queries. Graph databases fit when relationship traversal is central. Search engines fit full-text search and ranking. Multiple stores can be combined, each serving an access pattern, provided the canonical data source and synchronization mechanism are clearly defined.

Do not choose NoSQL merely because the system is serverless. Decisions must balance latency, throughput, consistency, query models, cost, operability, and team skills.

## 20. Design checklist

- [ ] Specific access patterns, frequencies, latencies, and data sizes have been listed.
- [ ] Every important pattern has an access path via a primary key or suitable index.
- [ ] Partition keys have sufficient cardinality and load distribution; large tenants/aggregates have been accounted for.
- [ ] Sort keys support required prefix/range/ordering and include a unique tie-breaker.
- [ ] Composite keys follow stable delimiter, encoding, casing, and timezone conventions.
- [ ] No critical query performs a full table scan without clear justification and budget.
- [ ] Indexes serve only valuable access patterns, with write/storage amplification accounted for.
- [ ] Denormalized copies have clear ownership, update mechanisms, and rebuild plans.
- [ ] Pagination uses cursors/continuation tokens and caps page sizes.
- [ ] Conditional writes/versions/idempotency protect concurrent updates.
- [ ] Transactions stay within practical database limits.
- [ ] Multi-tenant access always binds tenant from a trusted identity.
- [ ] TTL aligns with retries, replays, auditing, and retention.
- [ ] A migration plan exists for changing keys or indexes.
- [ ] Throttling, latency, item reads/writes, hot partitions, and cost are measured per access pattern.
- [ ] Function concurrency, retries, and queues are configured to match database capacity.

Good NoSQL design routes critical queries along intended key/index paths, distributes load evenly, and preserves correctness when many functions run concurrently. Start from access patterns, pick partition and sort keys for both queries and load distribution, and validate with real metrics. For serverless applications, this approach reduces scans and data round-trips, controls concurrency, and keeps business state durable across function invocations.
