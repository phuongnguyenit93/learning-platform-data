# Multi-Tenant Applications: Data Isolation, Indexing, and Access Control in MongoDB

## 1. Problem Statement: One SaaS Serving Thousands of Customers

A SaaS platform lets thousands of businesses manage orders. Each business is a **tenant** (a customer/organization with its own data domain and access policies). Within the same application, there are:

- Tenant `north-shop` with roughly 20,000 orders.
- Tenant `big-mart` with roughly 60 million orders and heavy analytical queries.
- Tenant `legal-firm` requiring stricter isolation and auditing.
- Tenant `trial-17` on a trial plan with request and storage limits.

The application exposes endpoints:

```text
GET    /api/orders
GET    /api/orders/{orderId}
POST   /api/orders
PATCH  /api/orders/{orderId}
DELETE /api/orders/{orderId}
GET    /api/reports/revenue
```

A mistake such as:

```java
orders.find(eq("_id", orderId));
```

can return an order belonging to another tenant if `orderId` is predictable or leaked. Conversely, adding `tenantId` to every filter without a matching index can make queries scan across the entire dataset. If the application spins up a separate database per tenant without planning, connection, index, migration, and operational costs can surge.

Multi-tenancy is therefore more than adding a `tenantId` field. It is the unified design of:

1. **Data isolation** — do tenants share collections or get separate databases/clusters?
2. **Authorization** — who is allowed to read, write, and administer which resources?
3. **Query safety** — do all read and write paths enforce the tenant boundary?
4. **Indexing** — how do shared resources keep per-tenant queries efficient?
5. **Operational isolation** — preventing noisy neighbors, safeguarding backups, migrations, quotas, monitoring, and deletion.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **shared collection**, **collection per tenant**, **database per tenant**, **cluster per tenant**, and hybrid models.
- Choose a model based on tenant count, isolation level, compliance, size, workload, and cost.
- Design documents with immutable `tenantId`, **tenant-scoped** unique business keys, and references that do not cross boundaries.
- Write Java MongoDB Sync Driver code enforcing tenant filters across all CRUD, pagination, aggregation, and bulk operations.
- Explain MongoDB RBAC limits: resource-level permissions do not automatically provide row-level authorization across documents in a shared collection.
- Design compound indexes, unique indexes, partial indexes, TTL, text/search indexes, and inspect query plans.
- Understand index prefixes, sorting, cardinality, shard keys, and unique index requirements on sharded collections.
- Prevent leaks via `$lookup`, `$unionWith`, `$graphLookup`, `$facet`, change streams, caches, background jobs, and logs.
- Organize tenant provisioning, schema migrations, backup/restore, tenant deletion, noisy-neighbor controls, and observability.
- Build tests against cross-tenant data leakage, access control, and concurrency using a real MongoDB instance.

### 1.2. Scope

Examples use **MongoDB Java Sync Driver 5.x**, BSON documents, and JUnit/Spring Boot where applicable. APIs, URIs, and options may vary across driver and server versions; in production, use the exact versions verified by your project.

Administrative commands in this lesson are for learning on lab databases only. Moving to production requires evaluating security, topology, write concerns, load, backups, and change plans. Never run tenant drop/delete scripts in a real environment without authorization and a recovery plan.

## 2. What Is a Tenant? Distinguishing Tenant, User, and Resource

Example relational view:

```text
Tenant north-shop
  - owner Alice
  - staff Bob
  - orders N001, N002
  - products NP01, NP02

Tenant big-mart
  - owner Carol
  - staff Dan
  - orders B001, B002
  - products BP01, BP02
```

A single **user** can belong to one or more tenants with different roles. **Tenant is not synonymous with user**.

Example memberships:

```javascript
{
  _id: "membership:alice:north-shop",
  userId: "alice",
  tenantId: "north-shop",
  role: "TENANT_ADMIN",
  status: "ACTIVE"
}

{
  _id: "membership:alice:big-mart",
  userId: "alice",
  tenantId: "big-mart",
  role: "VIEWER",
  status: "ACTIVE"
}
```

When Alice switches active tenants, **her effective authorization context changes**, even though her user identity remains Alice.

### 2.1. Terms to Separate

| Term | Meaning |
|---|---|
| Tenant | Organizational unit owning/partitioning data |
| User | Authenticated identity |
| Membership | User–tenant relationship, role/status |
| Tenant context | The tenant currently authorized for a request/job |
| Resource | Order, invoice, document, report, config |
| Authorization | Deciding which user/service may operate on which resource |
| Isolation | Ensuring tenant A's activity cannot unauthorizedly access or affect tenant B's data |
| Noisy neighbor | One tenant consuming excessive resources and degrading other tenants |

### 2.2. Tenant IDs Must Be Stable

`tenantId` is a boundary key. Avoid using display names (which can change) as tenant IDs. Use UUIDs, ULIDs, ObjectIds, or opaque backend-issued strings; ensure uniqueness and never reuse them arbitrarily.

### 2.3. Never Trust a Tenant ID Just Because the Client Sent It

A client may send:

```http
X-Tenant-Id: big-mart
```

The header is only the **requested tenant selection**, not proof that the client has permissions in that tenant. The server must verify identity + membership/authorization before constructing the tenant context.

### 2.4. Cross-Tenant Admins

A support super-admin might need access across multiple tenants, yet must use a **separate business path**, an explicitly granted scope, a recorded reason, auditing, and a break-glass policy. Never put a `bypassTenant=true` boolean on a normal repository method and let client requests choose it.

## 3. Three Isolation Patterns: Logical, Database, and Infrastructure

### 3.1. Logical Isolation

```text
                 One MongoDB cluster
                         |
                     saas.orders
                         |
       +-----------------+------------------+
       |                 |                  |
tenant=north-shop   tenant=big-mart     tenant=trial-17
```

All documents reside in the same collection and are separated via the `tenantId` field and application logic.

### 3.2. Database Isolation

```text
                 One MongoDB cluster
                         |
          +--------------+--------------+
          |              |              |
      db_north_shop   db_big_mart    db_trial_17
          |              |              |
        orders          orders          orders
```

Each tenant gets its own database; MongoDB roles can scope permissions at the database level if identities are designed accordingly.

### 3.3. Cluster Isolation

```text
Tenant north-shop ---> MongoDB cluster A
Tenant big-mart   ---> MongoDB cluster B
Tenant legal-firm ---> Dedicated MongoDB cluster C
```

Provides stronger resource and permission isolation at higher cost and operational overhead.

### 3.4. “Separate Databases” Does Not Automatically Isolate All Resources

Within the same cluster, databases still share CPU, memory, disk/network, storage engine internals, connection limits, and parts of the control plane. Database-per-tenant **does not equal** a dedicated cluster for noisy-neighbor isolation.

## 4. Comparing Four Storage Models

| Model | Layout | Advantages | Key drawbacks |
|---|---|---|---|
| Shared collection | Single `orders`, every doc has `tenantId` | Many tenants, few namespaces, shared indexes/schema | App must enforce tenant scope strictly; noisy neighbors |
| Collection per tenant | `orders_tenantA`, `orders_tenantB` | Some per-collection index/policy separation | High collection/index/catalog overhead, dynamic names |
| Database per tenant | `dbTenantA.orders`, `dbTenantB.orders` | Separate database-level RBAC/management | Migration, provisioning, connection/DB metadata scale with tenant count |
| Cluster per tenant | Fully isolated infrastructure | Strong isolation, scaling, independent maintenance | High cost and operational complexity |

### 4.1. No Single Model Fits Every SaaS

A service with 50,000 tenants averaging a few hundred documents each typically favors shared collections or hybrid models. An enterprise customer processing hundreds of millions of records may need its own database or cluster.

### 4.2. Collection-per-Tenant Is Not a Good Default

With 30,000 tenants × 20 collections/tenant = **600,000 collections**, plus multiple indexes per collection, namespace and metadata counts can become an operational bottleneck. Do not pick this model merely because separate collection names look “more isolated”.

### 4.3. Database-per-Tenant Does Not Mean MongoClient-per-Tenant

Multiple databases on the same deployment can usually share a single long-lived `MongoClient`:

```java
MongoClient client = MongoClients.create(sharedClusterUri);
MongoDatabase db = client.getDatabase(tenantDatabaseName);
```

Creating tens of thousands of `MongoClient` instances spawns independent monitoring sockets and connection pools, which is usually unnecessary.

### 4.4. Cluster-per-Tenant Helps Limit Blast Radius

A tenant requiring isolated workloads, encryption keys, or backup/maintenance windows can be assigned a dedicated cluster. However, **never assume separate clusters = automatically secure application**: admin permissions, secrets, logging, caches, deployments, and endpoint routing must still be protected.

## 5. Criteria for Deciding Data Isolation

An architectural checklist:

| Criterion | Question |
|---|---|
| Tenant count | 10, 1,000, or 100,000? |
| Data volume | How many GiB is the average/largest tenant? |
| Query pattern | Per-tenant or cross-tenant analytics? |
| SLA | Do enterprise tenants have dedicated SLOs? |
| Regulatory | Are there specific residency/isolation/retention mandates? |
| Schema customization | Do tenants use different schemas/indexes? |
| Resource isolation | Can a large tenant spike CPU/IO heavily? |
| Lifecycle | How frequent are onboarding/offboarding and per-tenant restores? |
| Sharding | Does a large collection need sharding across shards? |
| IAM/RBAC | Are tenant-specific DB credentials required? |
| Cost | How many clusters/databases/collections can you operate? |

### 5.1. Hybrid Model

```text
Tenant router
      |
      +--> shared-cluster / shared-collections
      |        trial, small, medium tenants
      |
      +--> enterprise-cluster-A / database dedicated
      |        big-mart
      |
      +--> isolated-cluster-B
               legal-firm
```

Hybrid lets you promote a tenant from shared → dedicated as scale or SLA grows, requiring a safely designed router and migration workflow.

### 5.2. Routing Metadata

```javascript
{
  _id: "big-mart",
  storageMode: "DEDICATED_DATABASE",
  clusterKey: "enterprise-a",
  databaseName: "tenant_7f3a4d",
  state: "ACTIVE",
  routingVersion: NumberLong("5")
}
```

This is backend control metadata, **not** information clients are allowed to mutate.

### 5.3. Data Residency

If a tenant has regional residency rules, routing must ensure **data, backups, logs, analytics exports, and service integrations** all comply in practice. Do not just pick a cluster in the right region and assume all secondary copies follow suit.

## 6. Threat Model: Where Can Cross-Tenant Leaks Happen?

```text
               Authenticated request
                         |
                         v
                Tenant authorization
                         |
                         v
           Tenant-aware business service
                         |
           +-------------+-------------+
           |             |             |
       MongoDB CRUD   Aggregation    Cache/search
           |             |             |
        tenantId        $lookup       cache key
        filters         / $facet      tenant scope
           |             |             |
           +-------------+-------------+
                         |
                         v
                  Response / export
```

Common leak points:

- `findById(id)` missing a tenant filter.
- `updateOne` or `deleteMany` forgetting `tenantId`.
- `$lookup` joining by order/product code without joining on tenant.
- `$unionWith` querying another collection unscoped.
- Background jobs and workers running without request context.
- Cache keys using only `orderId`.
- Search indexes or report aggregations missing tenant constraints.
- Change stream consumers publishing events to non-tenant-aware queues.
- Logs/error messages returning another tenant's document.
- File exports/backup restores landing in the wrong tenant destination.
- Signed URLs, attachments, and object storage unbound to tenants.

### 6.1. Isolation Is an End-to-End Property

A correct MongoDB query is insufficient if an API cache serves the wrong response. When auditing multi-tenancy, inspect every data path, not just collection schemas.

### 6.2. Threat Actors Are Not Always External Attackers

Bugs can stem from:

- A user switching tenants in the UI.
- A developer forgetting a filter in a new method.
- A support script running with the wrong scope.
- A scheduled job picking the wrong tenant.
- An analytics pipeline replicating data to the wrong tenant.
- A data migration with checkpoints/partitions lacking tenant boundaries.

## 7. Shared Collection: Standard Document Design

Order:

```javascript
{
  _id: ObjectId("673400000000000000000451"),
  tenantId: "north-shop",
  orderNumber: "PO-2026-0007",
  customerId: ObjectId("673400000000000000000111"),
  status: "PAID",
  amountMinor: NumberLong("350000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T04:00:00Z"),
  updatedAt: ISODate("2026-11-14T04:05:00Z")
}
```

Customer:

```javascript
{
  _id: ObjectId("673400000000000000000111"),
  tenantId: "north-shop",
  displayName: "Customer N-01",
  status: "ACTIVE"
}
```

### 7.1. `tenantId` Is a Mandatory Attribute

Every tenant-owned domain document needs:

- A valid tenant ID.
- Protection against implicit tenant mutation.
- Consistent creation and update rules.
- Tenant filters on every read/write path.

### 7.2. Global `_id` or Composite Identity?

MongoDB creates a unique `_id` index per collection by default. Using `ObjectId` normally provides collection-wide uniqueness without embedding tenant into `_id`.

If the domain uses order numbers like `PO-2026-0007` that can repeat across two tenants, the unique key must be **`(tenantId, orderNumber)`**, not `orderNumber` alone.

### 7.3. Tenant References Must Respect Boundaries

Even if `customerId` is a globally unique ObjectId, the application should verify the customer belongs to **the same tenant**:

```javascript
db.customers.findOne({
  _id: customerId,
  tenantId: "north-shop"
});
```

Never infer validity solely because the ID exists.

### 7.4. Transferring Ownership Between Tenants

Changing an order's `tenantId` is a sensitive operation, not a regular PATCH. If business requirements genuinely require “moving a tenant”, use an approved workflow checking references, unique constraints, auditing, cache/search cleanup, and rollback; generally forbid direct updates to the boundary field.

## 8. Unique Keys Scoped to a Tenant

### 8.1. Wrong: Collection-Wide Unique Index

```javascript
db.orders.createIndex(
  { orderNumber: 1 },
  { unique: true }
);
```

This index prevents two tenants from both using `PO-0007`, even when business rules allow it.

### 8.2. Right: Compound Unique Index

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_tenant_order_number"
  }
);
```

Two documents:

```javascript
{ tenantId: "north-shop", orderNumber: "PO-0007" }
{ tenantId: "big-mart",   orderNumber: "PO-0007" }
```

are allowed to coexist. The same tenant creating a duplicate `orderNumber` receives a duplicate key error.

### 8.3. Indexes Do Not Replace Authorization

A compound unique index only prevents key collisions; it does **not** block a query lacking `tenantId`. `find({orderNumber:"PO-0007"})` can still read across multiple tenants if the DB identity's permissions allow it.

### 8.4. Duplicate Keys Need Domain Mapping

`E11000 duplicate key` on `uniq_tenant_order_number` is typically an intra-tenant conflict. The application should confirm which exact index was violated instead of mapping every duplicate key error to “order already exists”; it could be an index on email, externalId, etc.

### 8.5. Missing/Null Trap in Unique Indexes

If historical records lack `tenantId` or `orderNumber`, unique compound indexes have specific semantics for missing/null values and may fail to build. Run preflight checks on legacy data and schema validation before creating unique indexes.

## 9. Indexing: Tenant Filter Usually Leads the Compound Key

Suppose a common API runs:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50);
```

A fitting index:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

### 9.1. Why Does `tenantId` Usually Come First?

The application always filters by tenant. Putting `tenantId` as the prefix enables index lookups scoped to the tenant and lets trailing fields serve equality and sorting.

However, **there is no rigid rule that “tenantId must always lead every index”**. Query patterns, cardinality, sorting, range predicates, the MongoDB planner, sharding, and index costs dictate the actual best order.

### 9.2. Equality–Sort–Range (ESR)

A useful heuristic when designing compound indexes:

1. Equality fields.
2. Sort fields.
3. Range fields.

This is not an absolute law. For highly selective ranges, adjustments may help; verify with `explain` and real workload measurements.

### 9.3. Index for Querying by Order ID

`_id` already has a unique index. Query:

```javascript
db.orders.findOne({
  tenantId: "north-shop",
  _id: ObjectId("673400000000000000000451")
});
```

can use `_id_` to locate the single document rapidly and then check `tenantId`. You do not necessarily need an extra `{tenantId:1,_id:1}` compound index just for this query.

### 9.4. Index for Chronological Lists

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_created_id_desc" }
);
```

Supports tenant filtering and stable pagination sorting by createdAt and _id.

### 9.5. Index for Customer Search

```javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1 },
  { name: "idx_tenant_customer_created_desc" }
);
```

Fits a customer's order history screen within a tenant.

## 10. Index Selection Table by Access Pattern

| Common query | Filter/sort | Candidate index |
|---|---|---|
| Lookup order number | tenantId = ?, orderNumber = ? | `{tenantId:1,orderNumber:1}` unique |
| List recent orders | tenantId = ?, sort createdAt desc/_id desc | `{tenantId:1,createdAt:-1,_id:-1}` |
| Paid orders | tenantId = ?, status = PAID, sort createdAt | `{tenantId:1,status:1,createdAt:-1}` |
| Customer history | tenantId = ?, customerId = ?, sort createdAt | `{tenantId:1,customerId:1,createdAt:-1}` |
| External integration lookup | tenantId = ?, externalId = ? | `{tenantId:1,externalId:1}` |
| Open tasks | tenantId = ?, state = OPEN, sort priority | Consider compound/partial index per workload |
| Shared global support ops | Explicit permissions and scope | Separate index for administrative queries if needed |

### 10.1. Do Not Create Every Index “Just in Case”

Every index consumes storage/cache, requires write maintenance, and slows bulk migrations. Keeping dozens of “just-in-case” indexes increases ingestion costs for all tenants.

### 10.2. One Index Does Not Serve Every Sort

`{tenantId:1,status:1,createdAt:-1}` does not automatically optimize queries sorting by `amountMinor` or `customerName`. To optimize, inspect real queries and evaluate dedicated indexes.

### 10.3. Indexes Span the Entire Shared Collection

In a shared collection, this index holds keys across **all tenants**, not “a separate index per tenant” just because `tenantId` is the prefix.

### 10.4. Measuring `explain("executionStats")`

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
```

Observe:

- Whether the winning plan is `IXSCAN` or `COLLSCAN`.
- `totalKeysExamined`, `totalDocsExamined`, `nReturned`.
- Blocking `SORT` stages.
- Index bounds and whether the query is covered.

Never treat `IXSCAN` alone as proof of good performance; scanning millions of index keys to return 20 records can still be inefficient.

## 11. Partial Indexes, Sparse Indexes, and Soft Deletes

An application supporting soft deletes:

```javascript
{
  tenantId: "north-shop",
  orderNumber: "PO-0007",
  deletedAt: null
}
```

If reusing an orderNumber after deletion is allowed, clarify the policy: unique only across **active** records or unique across all history?

### 11.1. Partial Unique Index for Active Documents

Suppose the application convention is **active when `deletedAt` does not exist**, and deleted when `deletedAt` is a Date:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_active_tenant_order_number",
    partialFilterExpression: {
      deletedAt: { $exists: false }
    }
  }
);
```

The index only covers documents matching the partial predicate. If active records contain `deletedAt:null`, they do **not** match `$exists:false` and can slip past the intended unique constraint. Standardize schemas and states.

### 11.2. Atomic Soft Delete

```javascript
db.orders.updateOne(
  {
    tenantId: "north-shop",
    _id: orderId,
    deletedAt: { $exists: false }
  },
  {
    $currentDate: { deletedAt: true }
  }
);
```

### 11.3. Partial Indexes Do Not Replace Tenant Filters

If a query uses a partial index yet omits `tenantId`, it can return active orders from multiple tenants. Indexes only optimize plans or restrict indexed keys; they never enforce authorization.

### 11.4. Queries Must Match the Predicate

The MongoDB planner only uses a partial index when it can guarantee the query does not miss documents excluded by the partial filter. A query omitting the active condition may not use the index as expected; verify with `explain`.

### 11.5. Sparse Differs from Partial

Sparse indexes only include documents containing the indexed field(s) per index semantics; `partialFilterExpression` supports richer conditions. Never assume sparse indexes handle all unique-null or soft-delete cases.

## 12. Collation and Tenant-Specific Uniqueness

One tenant requires case-insensitive `orderNumber`:

```text
INV-001
inv-001
```

MongoDB collations can support comparison and case rules on compatible indexes/queries.

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_tenant_order_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

### 12.1. Watch Out for Query Collation

To leverage collation-based string comparisons/indexes, the query must match the index collation or collection default. Verify with `explain`.

### 12.2. Tenants with Different Rules?

If tenant A treats emails as case-insensitive while tenant B uses another locale rule, a single shared compound index with a fixed collation may not satisfy both.

Approaches:

- Normalize business keys into canonical forms under an explicit policy.
- Adopt one unified policy if permitted.
- Separate collections/databases/clusters for groups with differing requirements.
- Enforce uniqueness on normalized keys.

### 12.3. Do Not Blindly Lowercase Every Field

Personal names, addresses, and locale-sensitive data cannot always be lowercased with universal rules. Only normalize fields that genuinely have canonical equality semantics.

## 13. TTL and Per-Tenant Retention

Tenant A has 30-day retention, tenant B 365 days. One shared-collection design computes `expireAt` per tenant policy upon record creation/update:

```javascript
{
  tenantId: "trial-17",
  eventType: "SESSION_CREATED",
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  expireAt: ISODate("2026-12-01T10:00:00Z")
}
```

TTL index:

```javascript
db.tenantSessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_expire_at" }
);
```

### 13.1. TTL Does Not Delete at the Exact Expiration Second

MongoDB's TTL monitor runs asynchronously; deletions can lag under load. If data must strictly cease existing after a hard deadline, TTL is **not** a complete compliance solution; stronger controls and policies are needed.

### 13.2. Legal Holds

Do not set `expireAt` on documents currently under legal hold. Compute and update `expireAt` via an authorized retention workflow; policy changes may require timestamp backfills.

### 13.3. TTL Indexes Do Not Take a `tenantId` Prefix

Standard TTL indexes are declared on a single Date field matching TTL semantics. Per-tenant retention is expressed via each document's **expireAt value**, rather than trying to make a compound `{tenantId,expireAt}` index act as a standard TTL index.

### 13.4. Deletion Across Multiple Systems

TTL deleting a MongoDB record does not delete files in object storage, search indexes, caches, data lakes, analytics exports, or other backups. Tenant offboarding requires inventorying all data assets.

## 14. Tenant-Aware Pagination

A screen:

```http
GET /api/orders?status=PAID&limit=50&cursor=...
```

must enforce tenant scope on the server:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(50);
```

### 14.1. Why Not Rely Solely on `skip`?

`skip(1000000)` forces queries to scan past huge numbers of index entries and suffers drift from concurrent inserts/deletes. For deep pagination, **keyset/cursor pagination** is usually far better.

### 14.2. Keyset on `createdAt + _id`

Cursor from the end of the previous page:

```javascript
{
  lastCreatedAt: ISODate("2026-11-14T04:00:00Z"),
  lastId: ObjectId("673400000000000000000451")
}
```

Next page:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(50);
```

### 14.3. Cursors Must Be Bound to the Tenant

Never let a cursor issued for `north-shop` be reused under `big-mart` without verification. Opaque/signed cursors should encode (or bind server-side) the tenant, sort/filter version, expiry, and required metadata.

### 14.4. Preventing Cursor Tampering

- Sign cursors with an HMAC or maintain a server-side token map.
- Validate tenant equality against the authenticated context.
- Reject malformed or stale cursors.
- Never allow clients to supply raw MongoDB filter or aggregation JSON.

### 14.5. Sort Keys Should Be Immutable

If `createdAt` changes after issuing a cursor, a record can be duplicated or skipped. Usually `createdAt` is immutable, whereas sorting by `status` or `updatedAt` can shift during pagination. Choose an appropriate consistency contract.

## 15. Sharding for Shared Multi-Tenant Collections

When a shared collection reaches billions of documents, a single replica set may run out of storage or throughput. MongoDB sharding distributes data across multiple shards.

### 15.1. The Shard Key Dictates Routing and Distribution

Suppose the shard key is:

```javascript
sh.shardCollection(
  "saas.orders",
  { tenantId: 1, orderId: 1 }
);
```

Before running this, establish the proper indexes and sharding preconditions for your MongoDB version and deployment. This is an illustrative shape only, not a copy-paste production command.

### 15.2. Ask Three Questions Before Choosing a Shard Key

1. Do common queries include the shard key or a prefix sufficient for targeted routing?
2. Is tenant distribution skewed—does 1 tenant hold 80% of the data?
3. Will the write workload create a hotspot on one chunk or shard?

### 15.3. What Is Wrong with a `tenantId`-Only Shard Key?

If the shard key is solely `{tenantId:1}`, a single tenant's data cannot split finely by key, especially for a huge/hot tenant. Range/hashing strategies and key cardinality must match real data distributions.

### 15.4. Compound Key with `tenantId`

`{tenantId:1,orderId:1}` provides high cardinality within the same tenant and helps tenant-aware routing, though query targeting when trailing shard-key components are absent must be evaluated; do not assume every `tenantId=?` query hits only one shard.

### 15.5. Hashed Sharding

Hashed shard keys help distribute suitable values evenly, trading off range targeting, data locality, and unique index support. Never treat “hashing `tenantId`” as a universal trick for a giant tenant: the same `tenantId` still hashes to one shard key value.

### 15.6. Zone Sharding

Zone sharding helps apply data placement policies, requiring careful zone ranges, shard keys, and operations; it does not automatically guarantee end-to-end regulatory isolation or data residency on its own.

## 16. Unique Indexes on Sharded Collections

In a shared replica set, `{tenantId:1,orderNumber:1}` as a unique index is straightforward.

In a **sharded collection**, unique index rules depend on the shard key:

- Supported unique indexes must satisfy shard-key prefix requirements per MongoDB server rules.
- You cannot create an arbitrary unique index omitting the shard key and assume MongoDB enforces cluster-wide uniqueness.
- `_id` uniqueness on a sharded collection has caveats when `_id` is not the shard key; do not rely on the `_id_` index alone to block cross-shard collisions automatically.
- Hashed indexes do not provide unique constraints the way standard unique indexes do.

### 16.1. Conceptual Example

With shard key `{tenantId:1}`, the unique index `{tenantId:1,orderNumber:1}` has the shard key as its prefix. However, this still does not solve skew/hot tenants; evaluate scale as well.

### 16.2. When Tenant-Wide Uniqueness Is Needed

You may need to pick a constraint-compatible shard key or maintain a dedicated key-reservation collection/service using appropriate transactions/atomic inserts.

Never create a “unique business key” index without verifying the server accepts it and enforces the guarantee on your sharded topology.

### 16.3. Shard Keys Can Be Hard to Change

Shard key design requires long-term thinking. MongoDB provides mechanisms to refine or reshard in supported versions, yet those are resource-intensive operations requiring migrations and runbooks—not a band-aid for unmeasured designs.

## 17. Database per Tenant: Isolation and Provisioning

Each tenant has:

```text
tenant_north_shop
  orders
  customers
  invoices

tenant_big_mart
  orders
  customers
  invoices
```

### 17.1. Tenant Registry

A registry governs routing:

```javascript
{
  _id: "north-shop",
  mode: "DATABASE_PER_TENANT",
  databaseName: "tenant_b7f32",
  clusterKey: "shared-prod-a",
  schemaVersion: 7,
  status: "ACTIVE"
}
```

**Never** construct database names directly from unvalidated client strings. The registry is trusted metadata managed by backend/administrative workflows.

### 17.2. MongoClient Reuse

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;

public final class TenantDatabaseResolver451 {
    private final MongoClient client;
    private final TenantRegistry registry;

    public TenantDatabaseResolver451(
            MongoClient client, TenantRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public MongoDatabase databaseFor(AuthorizedTenant451 scope) {
        String dbName = registry.trustedDatabaseName(scope.tenantId());
        if (dbName == null || dbName.isBlank()) {
            throw new IllegalStateException("Tenant not provisioned");
        }
        return client.getDatabase(dbName);
    }
}
```

`AuthorizedTenant451` and `TenantRegistry` are application-defined abstractions; this snippet does not constitute a complete authorization library on its own.

### 17.3. When Must You Create Separate MongoClients?

If tenants reside on **different clusters or use distinct credentials/CAs/transport policies**, you may need one `MongoClient` per cluster/config group. Manage a client cache with explicit max size, TTL, and lifecycle instead of creating clients per request.

### 17.4. Database-Level Grants

MongoDB can grant roles scoped to specific databases. However, if the application connects with **one super-credential having full access across all tenant databases**, a routing bug in code can still read the wrong database. Stronger isolation requires separate DB identities, service deployments, or appropriate server-side policies.

## 18. Collection per Tenant: Practical Limits

One naming scheme:

```text
orders_7f3a4d
orders_b9c27e
orders_03d992
```

### 18.1. Do Not Put Raw Tenant IDs into Namespace Names

A tenant ID with special characters or excessive length makes namespaces hard to manage; user-controlled names also create collision and injection risks. Use backend-assigned namespaces mapped via the registry.

### 18.2. Operational Costs Scale with Tenant Count

Each collection brings its own:

- Indexes and index-build lifecycles.
- Collection options, validators, and collations.
- TTL and index metadata.
- Namespace catalog entries and statistics.
- Backup, restore, and monitoring overhead.

### 18.3. Real Benefits

Collection-per-tenant allows per-tenant indexes, retention, and validators without mixing documents across tenants; useful when there is a **bounded number of tenants** and moderate customization needs.

### 18.4. Never Treat Dynamic Namespaces as Security

`db.getCollection("orders_"+tenantId)` is only safe if `tenantId` is authorized and the name is resolved from the registry. Arbitrary raw input can point to another tenant's collection or internal collections.

## 19. MongoDB RBAC: What Can and Cannot MongoDB Do?

MongoDB **Role-Based Access Control (RBAC)** governs privileges on resources like clusters, databases, and collections.

### 19.1. Database/Collection Scope

You can grant:

- Read access to database A.
- Read/write access to collection `orders` in database B.
- Admin/monitoring privileges to operational accounts.

### 19.2. No Built-In Row-Level Authorization Just Because `tenantId` Exists

In a shared collection:

```javascript
db.orders.find({
  tenantId: "north-shop"
});
```

MongoDB does not automatically inject a `tenantId` filter into every command from an application user just because that user belongs to `north-shop`.

If the same DB credential has `find` on the shared `orders` collection, the MongoDB server **does not automatically know** the JWT or membership of each HTTP caller.

### 19.3. Application Authorization Is Mandatory for Shared Collections

The service must:

- Authenticate the caller and requested tenant selection.
- Verify membership and roles.
- Attach the tenant condition to every MongoDB operation.
- Block APIs that could bypass the filter.
- Test cross-tenant cases.

### 19.4. Database-per-Tenant Supports Server-Side Boundaries More Easily

If an application connects using a DB user restricted to tenant A's database, MongoDB rejects access to database B. This adds defense-in-depth beyond application checks.

### 19.5. Yet DB Identities Still Need Management

Secret rotation, credential mapping, pool reuse, support access, and tenant reassignments all need operational controls. One credential per tenant does not scale cleanly to 100,000 tenants without dedicated identity automation.

## 20. Example Database Permissions for a Dedicated Tenant

On a **test database**:

```javascript
use tenant_north_shop_lab;

db.createUser({
  user: "tenant_north_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "tenant_north_shop_lab" }
  ]
});
```

This user holds a read role on the specified database under RBAC and has no implicit privileges on other tenants' databases.

### 20.1. Practical Verification

```javascript
use tenant_north_shop_lab;
db.orders.findOne();
```

While connected as tenant A's read-only identity, attempt out-of-scope operations on tenant B or writes to tenant A and verify the server rejects them.

### 20.2. Authentication vs. Authorization

- **Authentication (AuthN):** who is connecting to MongoDB?
- **Authorization (AuthZ):** what can that identity do on which database/collection?

HTTP users and DB users can differ: a backend service typically connects using a service identity and enforces HTTP-level authorization per request.

### 20.3. Principle of Least Privilege

An order-processing service should never use the `root` role. Grant only the privileges needed on the collections the service actually touches; separate application, migration, and DBA accounts.

### 20.4. Secrets

Never store passwords or connection URIs with credentials in source code, test snapshots, logs, or a tenant registry readable by ordinary users. Use secrets management and rotation policies.

### 20.5. Views Do Not Replace All Row-Level Policies

MongoDB read-only views can provide a filtered query abstraction, and privileges can be granted on a view instead of the underlying collection under supported conditions. However, views do not automatically provide tenant-isolated arbitrary writes or protect every application path. When using views as a boundary, audit privileges, aggregation behavior, direct collection grants, and server version rules.

## 21. Building Tenant Context from Authenticated Identity

Request flow:

```text
Browser / API client
        |
        | JWT / session + desired tenant
        v
Authentication filter
        |
        v
Verify signature, expiry, audience, issuer
        |
        v
Membership & permission check
        |
        v
AuthorizedTenant tenant context
        |
        v
Tenant-scoped service/repository
        |
        v
MongoDB with mandatory tenantId filter
```

### 21.1. Never Treat Request Body `tenantId` as Authoritative

Example:

```json
{
  "tenantId": "big-mart",
  "orderNumber": "PO-100",
  "amountMinor": 550000
}
```

If Alice from `north-shop` sends this body, the server must never create an order under `big-mart`. The tenant ID must come from **an authenticated and authorized scope**.

### 21.2. Tenant Switching

A user with multiple memberships can request a specific tenant; the backend must:

1. Verify the tenant exists and is active.
2. Verify the user holds an active membership.
3. Verify the role permits the requested action.
4. Construct an `AuthorizedTenant` immutable from request body overrides.
5. Propagate the scope through request execution.

### 21.3. Service-to-Service

Batch/queue consumers have no direct human caller. They need a **service identity** and tenant context derived from validated/authorized messages, rather than blindly trusting an arbitrary `tenantId` in a queue payload.

### 21.4. Async Context Propagation

`ThreadLocal` carrying request scope can be lost across `CompletableFuture`, reactive chains, or message consumers. Prefer passing scope as an explicit parameter; if a framework propagates context automatically, test async boundaries thoroughly.

## 22. Tenant Scope Data Type in Java

An immutable type created only after authorization checks succeed:

```java
import java.util.Objects;

public record AuthorizedTenant451(
    String tenantId,
    String actorId,
    String role
) {
    public AuthorizedTenant451 {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(actorId, "actorId");
        Objects.requireNonNull(role, "role");
        if (tenantId.isBlank() || actorId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant scope");
        }
    }
}
```

### 22.1. Type Safety Alone Is Not Authorization

Any code could call `new AuthorizedTenant451("big-mart",...)`; the constructor only validates shape, not membership. In production, restrict scope creation to an authorized service/factory or enforce strong policy APIs.

### 22.2. Mock Authorization Factory

```java
public AuthorizedTenant451 authorizeTenant(
        VerifiedPrincipal principal,
        String requestedTenant,
        String requiredAction) {

    Membership membership = membershipService.findActive(
        principal.userId(), requestedTenant);

    if (membership == null
            || !permissionService.allowed(
                membership, requiredAction)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    return new AuthorizedTenant451(
        requestedTenant, principal.userId(), membership.role());
}
```

`VerifiedPrincipal`, `Membership`, and the services above are architectural abstractions, not built-in MongoDB Java Driver APIs.

### 22.3. Never Let Shared Repositories Accept Raw `tenantId` from Public Controllers

A method like `repository.findOrders(String tenantId)` risks being called with unverified input. Prefer:

```java
List<Order> listOrders(AuthorizedTenant451 scope, OrderFilter filter);
```

so callers are forced to pass through authorization before accessing data.

## 23. Java Sync Driver: Scoped Repository for CRUD

Minimal repository using a shared `orders` collection without **directly exposing `MongoCollection`** to controllers:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

import java.util.List;
import java.util.ArrayList;
import java.util.Objects;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class TenantOrderRepository451 {
    private final MongoCollection<Document> orders;

    public TenantOrderRepository451(MongoDatabase database) {
        this.orders = database.getCollection("orders");
    }

    private Bson tenantOnly(AuthorizedTenant451 scope) {
        Objects.requireNonNull(scope, "Authorized tenant required");
        return eq("tenantId", scope.tenantId());
    }

    private Bson byId(
            AuthorizedTenant451 scope, ObjectId id) {
        return and(tenantOnly(scope), eq("_id", id));
    }

    public Document findById(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.find(byId(scope, id)).first();
    }

    public List<Document> recent(
            AuthorizedTenant451 scope, int pageSize) {
        int safeLimit = Math.max(1, Math.min(pageSize, 100));
        return orders.find(tenantOnly(scope))
            .sort(Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")))
            .limit(safeLimit)
            .into(new ArrayList<>());
    }

    public long count(
            AuthorizedTenant451 scope, String status) {
        return orders.countDocuments(
            and(tenantOnly(scope), eq("status", status)));
    }

    public void insert(
            AuthorizedTenant451 scope,
            String orderNumber,
            long amountMinor) {
        if (amountMinor < 0L) {
            throw new IllegalArgumentException("Negative amount");
        }
        orders.insertOne(new Document("_id", new ObjectId())
            .append("tenantId", scope.tenantId())
            .append("orderNumber", orderNumber)
            .append("amountMinor", amountMinor)
            .append("status", "CREATED")
            .append("createdAt", new java.util.Date()));
    }

    public Document markPaid(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.findOneAndUpdate(
            and(byId(scope, id), eq("status", "CREATED")),
            combine(
                set("status", "PAID"),
                currentDate("updatedAt")),
            new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER));
    }

    public long deleteIfCreated(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.deleteOne(
            and(byId(scope, id), eq("status", "CREATED")))
            .getDeletedCount();
    }
}
```

### 23.1. More Important Than Imports: Every CRUD Path Is Scoped

In the example:

- `findById` — `tenantId + _id`.
- `recent` — only the tenant's documents.
- `count` — never counts another tenant's orders.
- `insert` — tenant taken from authorized scope.
- `markPaid` — tenant + id + business status.
- `deleteIfCreated` — tenant + id + domain condition.

### 23.2. Avoid Exposing Raw Collections

If a controller can access `orders` directly, a developer might bypass the safe wrapper with `orders.find()`. Enforce boundaries via modules, DI, code reviews, static analysis, and integration tests.

### 23.3. What to Return for Unknown IDs?

If `findById` finds no record in the tenant, APIs typically return 404 or generic not-found/forbidden per security policy. Never reveal “order exists in another tenant”.

### 23.4. Block Updates to `tenantId`

Never let clients choose arbitrary field names to update:

```java
// Forbidden: pass user-constructed body directly into an update.
orders.updateOne(filter, new Document("$set", userSuppliedPatch));
```

Whitelist allowed fields; strictly forbid modifying `_id`, `tenantId`, `ownership`, or internal migration/security fields.

## 24. A Base Filter Helper Prevents Forgetting Tenant Scope

Example:

```java
import org.bson.conversions.Bson;
import com.mongodb.client.model.Filters;

public final class TenantFilters451 {
    private TenantFilters451() {}

    public static Bson within(
            AuthorizedTenant451 scope,
            Bson domainPredicate) {
        if (scope == null) {
            throw new SecurityException("Missing tenant context");
        }
        if (domainPredicate == null) {
            throw new IllegalArgumentException(
                "Explicit domain predicate required");
        }
        return Filters.and(
            Filters.eq("tenantId", scope.tenantId()),
            domainPredicate
        );
    }
}
```

### 24.1. `$and` Is Safer Than Arbitrary Map Merging

If an app merges two JSON objects via `putAll`, a user filter containing `tenantId` can **overwrite** the server-generated tenant filter.

```text
Trusted:   { tenantId: "north-shop" }
Untrusted: { tenantId: "big-mart", status: "PAID" }

Unsafe object merge -> filter tenantId="big-mart"
```

Instead of merging, use:

```javascript
{
  $and: [
    { tenantId: "north-shop" },
    { status: "PAID" }
  ]
}
```

If the domain predicate tries to filter another tenant, the result is empty; it can never override the trusted scope.

### 24.2. Filter Guards Do Not Cover Every Operation

`TenantFilters451.within()` does not automatically protect:

- `aggregate` pipelines containing `$lookup`/`$unionWith`.
- Data read from caches.
- `insertOne` (which takes no filter).
- Index/admin commands.
- Background jobs bypassing the wrapper.

Therefore, repository/API design needs a **closed set of allowed methods**, full path testing, and operation-level authorization.

## 25. BulkWrite: One Unscoped Operation Can Harm Another Tenant

`bulkWrite()` accepts a list of models; if a single model lacks tenant scope, the batch can contain unsafe updates or deletes.

### 25.1. Wrong

```java
new UpdateOneModel<Document>(
    Filters.eq("_id", orderId),
    Updates.set("status", "PAID")
);
```

### 25.2. Right

```java
new UpdateOneModel<Document>(
    Filters.and(
        Filters.eq("tenantId", scope.tenantId()),
        Filters.eq("_id", orderId)
    ),
    Updates.set("status", "PAID")
);
```

### 25.3. Bulk Insert

Every document must have `tenantId` assigned by the backend from the authorized context, never preserving an arbitrary client-supplied `tenantId`.

### 25.4. Upsert Is Especially Dangerous

```java
orders.updateOne(
    Filters.eq("externalId", externalId),
    update,
    new UpdateOptions().upsert(true));
```

Without `tenantId` and matching unique constraints, a request can update another tenant's document or insert an un-tenanted resource.

Safer:

```java
orders.updateOne(
    Filters.and(
        Filters.eq("tenantId", scope.tenantId()),
        Filters.eq("externalId", externalId)
    ),
    Updates.combine(
        Updates.set("status", "READY"),
        Updates.setOnInsert("tenantId", scope.tenantId())),
    new UpdateOptions().upsert(true));
```

And create a `{tenantId:1,externalId:1}` unique index matching your topology. Concurrent upserts still require proper duplicate/retry handling.

### 25.5. Do Not Trust `updateCount` Blindly

`matchedCount=1` only confirms a record matched the filter. It does not prove the operation hit the right business resource if the filter omitted tenant scope. Get the filter right before interpreting results.

## 26. Aggregation: Early `$match` Is Necessary but Not Sufficient

Revenue report API:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "north-shop",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$currency",
      totalMinor: { $sum: "$amountMinor" },
      count: { $sum: 1 }
    }
  }
]);
```

### 26.1. Why Put `$match` Early

It restricts input documents to the tenant, enables index usage, and avoids mixing data across tenants before `$group`.

### 26.2. Never Let Clients Supply Arbitrary Stages

If the UI sends a raw MongoDB aggregation pipeline:

```json
[
  { "$match": { "tenantId": "big-mart" } },
  { "$group": { "_id": null, "count": { "$sum": 1 } } }
]
```

the backend must never execute it directly. Whitelist report types, metrics, sort/filter fields, and build the scoped pipeline server-side.

### 26.3. `$facet`

`$facet` runs multiple subpipelines. If the source pipeline is already scoped and no stages pull external data, facets operate on the scoped input; still audit nested pipelines and never rely on a leading `$match` to shield `$unionWith` or lookups.

### 26.4. `$out`/`$merge`

Aggregations can write to target collections; scope both source **and** target semantics. If a `$merge` key lacks tenant ID, two tenants can overwrite or merge into the same target record.

### 26.5. Cross-Tenant Reports

If admin reports span multiple tenants, use an **explicitly authorized** endpoint/job with auditing, never reusing a tenant-specific query method by passing `null` to skip the filter.

## 27. `$lookup`: Risk of Joining Cross-Tenant Data

An order stores `customerId`. If code joins only by customer ID and customer IDs are not globally unique, it can pull another tenant's customer.

### 27.1. Wrong: Joining Only by Business ID

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "customer"
    }
  }
]);
```

If `big-mart` also has `customerCode:"C001"`, results can include customers from both tenants.

### 27.2. Right: Joining on Tenant + Business Key

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $lookup: {
      from: "customers",
      let: {
        scopedTenant: "$tenantId",
        scopedCustomer: "$customerCode"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$scopedTenant"] },
                { $eq: ["$customerCode", "$$scopedCustomer"] }
              ]
            }
          }
        }
      ],
      as: "customer"
    }
  }
]);
```

### 27.3. Index Supporting the Join

```javascript
db.customers.createIndex(
  { tenantId: 1, customerCode: 1 },
  { unique: true, name: "uniq_tenant_customer_code" }
);
```

Pipeline-style `$lookup` with `$expr` has version- and operator-specific index eligibility rules. Check `explain` rather than assuming optimal index usage automatically.

### 27.4. One Correct `$lookup` Does Not Protect Other Stages

If `$unionWith` or nested lookups follow later, each data-retrieval path must be scoped individually.

### 27.5. Still Guard Joins by Global ObjectId

Even when `_id` is globally unique, joining with tenant equality adds protection against bad imports, ownership changes, and unchecked business references.

## 28. `$unionWith`, `$graphLookup`, and Nested Pipelines

### 28.1. `$unionWith` Requires Scope on the Secondary Collection

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $project: {
      tenantId: 1,
      eventType: { $literal: "ORDER" }
    }
  },
  {
    $unionWith: {
      coll: "supportTickets",
      pipeline: [
        { $match: { tenantId: "north-shop" } },
        {
          $project: {
            tenantId: 1,
            eventType: { $literal: "TICKET" }
          }
        }
      ]
    }
  }
]);
```

Without `$match` inside `$unionWith.pipeline`, the pipeline pulls tickets from all tenants even though the main input was scoped.

### 28.2. `$graphLookup`

Org-tree or project-reference traversals can hop between documents. Constrain traversal with tenant scope via `restrictSearchWithMatch` matching the authorized tenant.

### 28.3. Do Not Rely Only on a Pipeline AST Scanner

A check that “ensures the pipeline starts with `$match tenantId`” cannot catch every nested read source or implicit write stage. It is far safer to let services build only reviewed pipelines rather than letting users control arbitrary stages.

### 28.4. Other Collections Must Keep Tenant Boundaries

References to `files`, `messages`, `comments`, `invoices`, and `auditEvents` also need `tenantId` or verified ownership mappings. One unscoped auxiliary collection can leak data even when `orders` is locked down.

## 29. Search, Text Indexes, and Atlas Search

### 29.1. MongoDB Text Search

A shared collection can have a text index on searchable fields; every search query must scope the tenant:

```javascript
db.products.find({
  tenantId: "north-shop",
  $text: { $search: "wireless keyboard" }
});
```

Text indexes have constraints on count, types, and query behavior; design them to match your schema and server version.

### 29.2. Atlas Search

Atlas Search uses a dedicated `$search` stage; placing `$match` after `$search` filters output results, yet **does not necessarily reduce** the documents processed by the search engine.

When your index/feature supports `compound.filter`, scope the tenant **inside the search query** once designed and tested.

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "north-shop"
            }
          }
        ],
        must: [
          {
            text: {
              query: "wireless keyboard",
              path: "name"
            }
          }
        ]
      }
    }
  },
  { $limit: 20 }
]);
```

The search index mapping for `tenantId` must match the operator (`equals`); verify version, index definition, and output. This is **data filtering**, not a substitute for application-layer authorization.

### 29.3. Vector Search

With Atlas Vector Search, tenant filtering inside vector queries only works when index/filter mappings and operators support it. Never accept cross-tenant semantic similarity results and merely hide them on the frontend.

### 29.4. Search Pagination and Index Lifecycle

When a user switches tenant context, reset search cursors and continuation tokens. Include index build/mapping metadata and query rates in noisy-neighbor and cost controls.

## 30. Change Streams, Event Buses, and Tenant Isolation

Change streams detect modifications:

```javascript
const stream = db.orders.watch([
  {
    $match: {
      "fullDocument.tenantId": "north-shop",
      operationType: "insert"
    }
  }
]);
```

### 30.1. Pitfalls of `fullDocument`

Change events vary by operation type and `fullDocument` options. For deletes, the full document is generally absent from default events; filtering solely on `fullDocument.tenantId` can **miss or misroute events**.

### 30.2. Event Consumers Need Explicit Routing Context

A shared consumer serving all tenants may need to:

- Determine tenant from a stable event/lookup mapping.
- Check event type, namespace, and version.
- Route to properly permissioned queues/topics/buckets.
- Enforce idempotent processing and resume token management.
- Never publish tenant A's raw data to tenant B's subscription.

### 30.3. Resume Tokens Differ from Tenant Cursors

A change stream resume token is a stream position checkpoint; never treat it as proof of membership or authorization. A subscriber switching tenants must be authorized and governed by stream policies.

### 30.4. Guard Against Leaks When Events Lack Full Documents

Include `tenantId` in a trusted event envelope from the write path, look up document keys within a known scope, or use server-side pre/post images where supported by requirements and versions. Never assume every delete event includes `tenantId`.

## 31. Transactions: Atomicity Does Not Automatically Guarantee Tenant Correctness

Suppose creating an order and deducting inventory in a transaction:

```text
Tenant north-shop:
  insert order
  decrement inventory for P01
  insert audit event
  commit all or none
```

### 31.1. Transactions Still Must Filter Tenant

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    try {
        orders.insertOne(session, new Document("_id", new ObjectId())
            .append("tenantId", scope.tenantId())
            .append("orderNumber", "PO-451"));

        inventory.updateOne(
            session,
            Filters.and(
                Filters.eq("tenantId", scope.tenantId()),
                Filters.eq("sku", "P01"),
                Filters.gte("available", 1)),
            Updates.inc("available", -1)
        );

        // A real application must verify matchedCount before committing.
        session.commitTransaction();
    } catch (RuntimeException ex) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            ex.addSuppressed(abortError);
        }
        throw ex;
    }
}
```

The code above illustrates **tenant scoping**, not a complete production transaction recovery implementation. Production needs to validate inventory update results, retry according to transaction labels, enforce timeouts, and guarantee business idempotency.

### 31.2. A Transaction Mixing Two Tenants Can Still Commit

If code intentionally updates documents A and B in the same transaction under a DB identity with privileges, MongoDB does not reject it as a violation. Atomicity never replaces authorization.

### 31.3. Genuine Cross-Tenant Operations

An operator migration may need to move data between tenants, yet that must be a separate policy-governed, audited action. Never expose a public “transfer order” API accepting arbitrary source/destination tenant IDs.

### 31.4. Retrying Transactions

In MongoDB, `TransientTransactionError` can require retrying the transaction body, while `UnknownTransactionCommitResult` requires handling commit retries per semantics. Never charge payments or send emails directly inside a retriable callback without an outbox and idempotency.

### 31.5. Sharded Transactions

Distributed transactions carry different costs, limits, and performance than single-shard transactions. Tenant affinity with the shard key can reduce cross-shard work in some patterns, though actual routing must be measured.

## 32. Tenant-Scoped Caches: MongoDB Is Right Yet the API Still Leaks Data

Faulty cache example:

```java
String cacheKey = "order:" + orderId;
```

If order IDs are reused per tenant or an endpoint reads with the wrong scope, the cache can serve another tenant's resource.

### 32.1. Properly Scoped Cache Key

```java
String cacheKey =
    "order:v2:" + scope.tenantId() + ":" + orderId;
```

### 32.2. Cache Keys Also Need Authorization Scope When Required

A response may vary by role, region, masking policy, or version. For sensitive data, `tenantId` alone is sometimes insufficient; design around **exact authorization and visibility semantics**.

### 32.3. Cache Invalidation

When an order is updated or deleted:

- Invalidate only the corresponding tenant's cache key.
- Never invalidate another tenant via a colliding ID.
- Never reuse an admin's cached projection for a lower-privileged user.
- Ensure tenant migrations do not leave stale data in cache after cutover.

### 32.4. Caches Are Part of Tenant Isolation Testing

A test must warm the cache as tenant A, then query as tenant B with the same orderNumber/ID pattern and verify A's data is never returned.

## 33. Object Storage and Attachments

A MongoDB document might store a `fileKey` pointing to an S3-compatible bucket or blob storage:

```javascript
{
  _id: ObjectId("673400000000000000000451"),
  tenantId: "north-shop",
  fileKey: "tenant/north-shop/orders/PO-0007.pdf"
}
```

### 33.1. A File Key Is Not Authorization

Just because a path contains `tenantId` does not mean a user automatically has download rights. A backend issuing signed URLs must:

1. Verify tenant context.
2. Read attachment metadata using a tenant-scoped MongoDB filter.
3. Check permissions on the resource.
4. Generate a short-lived URL for the exact object/version.

### 33.2. Never Accept a Raw `fileKey` from the Client and Sign It

An endpoint `/download?key=tenant/big-mart/...` must never sign arbitrary keys just because the caller is logged in. Keys must be resolved from authorized documents.

### 33.3. Deleting a Tenant

Deleting MongoDB records does not delete attachments; inventory object ownership, event/audit trails, and retention policies.

## 34. Schema Versioning and Per-Tenant Custom Fields

Tenant A adds a custom field that tenant B lacks:

```javascript
{
  tenantId: "north-shop",
  schemaVersion: 4,
  status: "PAID",
  customFields: {
    deliveryZone: "HCM-Q1",
    salesChannel: "WEB"
  }
}
```

### 34.1. Custom Fields Must Not Become Arbitrary BSON

If clients can send any field name and type:

- Schema and index growth become uncontrollable.
- Query performance becomes unpredictable.
- Field names may collide with reserved names.
- Payloads bloat.
- Security/masking policies become hard to govern.

Maintain a per-tenant schema registry/config, cap field counts/types/lengths, and validate server-side.

### 34.2. Shared Schema + Extensions

One approach:

- Standard core fields: tenantId, _id, status, timestamps, amount.
- `customFields` with registry-governed names and types.
- Common indexes on core fields.
- Only key custom fields indexed per policy.

### 34.3. Wildcard Indexes

MongoDB supports wildcard indexes for flexible documents, yet they do not replace schema discipline and should not be used to index unbounded custom fields without measurement.

### 34.4. Schema Validators

Collection validators can require `tenantId` to be a string and `status` to match an enum, yet cannot prove that the `tenantId` in the payload matches the caller's authorized tenant.

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNumber", "status"],
      properties: {
        tenantId: { bsonType: "string" },
        orderNumber: { bsonType: "string" },
        status: {
          enum: ["CREATED", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "moderate"
});
```

This is a test-collection example, and `validationLevel:moderate` has specific semantics for pre-existing invalid documents; production rollouts choose strict/moderate and validationAction intentionally rather than copying defaults blindly.

## 35. Tenant Provisioning: Controlled Resource Creation

A new tenant requires:

```text
Signup approved
      |
      v
Create tenant registry record (PROVISIONING)
      |
      v
Allocate database/cluster or shared namespace
      |
      v
Create required collections/indexes/roles
      |
      v
Seed default configs
      |
      v
Verify connectivity and permission
      |
      v
Tenant state ACTIVE
```

### 35.1. Provisioning Must Be Idempotent

If a worker crashes after creating databases/indexes but before updating the registry, retries must detect existing resources and finish cleanly without creating duplicate tenants, credentials, or collections.

### 35.2. State Machine

```text
REQUESTED -> PROVISIONING -> ACTIVE
                    |
                    +----> FAILED / REPAIR_REQUIRED

ACTIVE -> SUSPENDED -> DELETING -> DELETED
```

Do not enable API traffic for a tenant in `PROVISIONING` until essential indexes and permissions are ready.

### 35.3. Registry Integrity

The tenant registry can enforce unique indexes on `_id`/slug and versioned routing metadata with restricted write privileges. Changing `clusterKey`/`databaseName` requires auditing and a careful cutover.

### 35.4. Index Creation Races

Multiple provisioning workers calling `createIndex` or initializing collections concurrently can cause configuration conflicts. Use orchestration/idempotent DDL plans and handle failed index builds explicitly.

### 35.5. Billing and Limits

Provisioning can initialize quotas and tiers. Avoid kicking off heavy index builds on a shared production cluster merely to onboard a small trial tenant if policy favors deferring or sharing.

## 36. Online Schema Migration in Multi-Tenancy

A migration adding `invoiceStatus` to `orders` may need to update millions of documents across many tenants.

### 36.1. Expand–Migrate–Contract

```text
Expand:
  allow old and new documents
  deploy readers/writers compatible

Migrate:
  backfill by tenant/range with checkpoints
  throttle to protect user traffic
  fix poison documents

Verify:
  missing/stale counts per tenant
  semantic correctness and sampled values

Contract:
  enforce schema after all tenants ready
  remove old fallback per cutover policy
```

### 36.2. One Checkpoint per Partition

```javascript
{
  _id: "invoice-status-v3:north-shop:range-0001",
  tenantId: "north-shop",
  migrationVersion: 3,
  state: "RUNNING",
  lastScannedId: ObjectId("673400000000000000000451"),
  highWatermarkId: ObjectId("6734ffffffffffffffffffff")
}
```

### 36.3. Per-Tenant and Cluster-Wide Throttling

If each tenant worker runs at 100 docs/s across 500 workers, total load hits 50,000 docs/s. Enforce global budgets, backpressure, and fairness.

### 36.4. Idempotency

Migrations should use deterministic `$set` / revision checks rather than `$inc` on derived values that would double on replay.

### 36.5. Verify Tenant Boundaries Never Cross

Every scan/filter, target update, and DLQ record must stay within the right tenant. If a worker partitions by tenant yet a query omits `tenantId`, tenant A's checkpoint could falsely mark tenant B's documents processed.

### 36.6. Schema Versioning

An enterprise tenant may cut over later than others. Registry `schemaVersion` must stay compatible with application read paths; avoid running an API that only understands version 5 against a tenant database still on version 3.

## 37. Moving a Tenant from Shared to Dedicated Storage

When tenant `big-mart` grows too large:

```text
Before:
  shared.orders (tenantId=big-mart)

After:
  dedicated_big_mart.orders
```

### 37.1. Never Just “Copy and Switch URI”

While copying runs, the application keeps receiving writes. Simply copying a snapshot and flipping routing loses updates written after the snapshot.

### 37.2. Conceptual Protocol

1. Provision the dedicated target with matching indexes and schemas.
2. Record source/version/cutover plan.
3. Backfill tenant data using bounded scans and checksums/counts.
4. Use dual-writes or CDC catch-up so writes occurring during copy are not lost.
5. Verify target parity and consistency.
6. Prevent split-brain writes via routing leases/versions or a brief controlled write gate.
7. Switch tenant routing metadata atomically from the application's perspective.
8. Canary reads and monitor.
9. Retain the source during a controlled rollback window.
10. Purge source data once approved.

### 37.3. Routing Version as a Safety Guard

```javascript
{
  tenantId: "big-mart",
  clusterKey: "enterprise-a",
  databaseName: "tenant_big_mart",
  routingVersion: NumberLong("6")
}
```

If two app pods cache different routing versions, they could write to two different clusters. Enforce TTL caches, invalidation, fencing/cutover gates, and observability.

### 37.4. Never Rely Solely on High-Water Marks

An ObjectId/orderId cursor does not produce a consistent snapshot by itself. Handoffs must handle concurrent inserts/updates/deletes, retries, CDC resume windows, and business idempotency.

### 37.5. Rollback

Rolling back routing after writes have occurred on the target requires reverse replay, dual-writes, or a controlled freeze; flipping a metadata string back does not automatically merge diverged data.

## 38. Backup and Restore per Tenant

### 38.1. Shared Collection

Backups/PITR typically protect clusters, databases, or collections per your backup tool. To restore a single tenant, **you cannot blindly restore a shared-collection snapshot over production**, as that affects all other tenants.

A safe plan:

1. Restore the snapshot into an **isolated temporary environment**.
2. Extract only documents matching the target `tenantId`.
3. Compare revisions/timestamps against production.
4. Decide merge vs. replace per domain rules.
5. Upsert/restore via a guarded migration.
6. Verify references, indexes, search, and caches.

### 38.2. Database-per-Tenant

Database scoping can simplify export/restore logistics for one tenant, though actual point-in-time or per-database restore capabilities depend on your Atlas/self-managed backup tool. Never assume every snapshot service offers one-click per-tenant restore.

### 38.3. Cluster-per-Tenant

Backup/restore is better isolated, yet you must still check external data stores, event buses, and cross-system consistency.

### 38.4. Tenant-Level Recovery Objectives

Define RPO/RTO by tier and know which tenants take priority during an outage; document backup policies and test restores as part of onboarding.

### 38.5. Backup Encryption and Retention

Backups may still contain data deleted from the live production database. Maintain retention/deletion policies, key management, and understand backup limits; never claim “deleting a document removes all copies everywhere”.

## 39. Tenant Offboarding and Data Deletion

### 39.1. Tenant Deletion Is a Workflow

```text
Tenant requests deletion
        |
        v
Check legal hold / retention obligations
        |
        v
Mark DELETING and reject new writes
        |
        v
Revoke sessions, API keys, service grants
        |
        v
Delete MongoDB records safely
        |
        v
Delete search/cache/object storage/exports
        |
        v
Verify counts and audit evidence
        |
        v
Mark DELETED
```

### 39.2. Shared Collection Deletion

For high volumes, avoid running one giant `deleteMany({tenantId})` during peak hours. Delete in throttled keyset/cursor batches with checkpoints to avoid violating latency SLOs.

### 39.3. Never Drop Shared Collections

`db.orders.drop()` wipes data for **all tenants**. Never use `drop` for tenant offboarding in a shared collection.

### 39.4. Database-per-Tenant Drop

`dropDatabase()` can be appropriate in dedicated-database mode **once tenant ownership is verified, backup/hold policies allow it, and an operator approves**. A single routing/namespace mistake can wipe another tenant's data.

### 39.5. Never Reassign Deleted Tenant IDs

Reusing a deleted customer's tenant ID can cause cache keys, backup metadata, and webhook/event references to collide with the new tenant. Use non-reusable IDs.

### 39.6. Verify Deletion Scope

Every deletion job must record the tenant registry ID, namespace mapping, expected document count, approvals, and dry-run counts; never trust raw database/collection names submitted via an API.

## 40. Per-Tenant Encryption

### 40.1. Encryption at Rest and in Transit

TLS protects data in transit; encryption at rest protects the storage layer per MongoDB/Atlas configuration. Neither prevents a DB credential with broad access from reading another tenant's documents.

### 40.2. Client-Side Field Level Encryption (CSFLE)

CSFLE lets the application encrypt specific fields before sending them to MongoDB, with separate key management.

### 40.3. Queryable Encryption

Queryable Encryption supports specific query types on encrypted data per capabilities/version; never assume every operator, aggregation, or index behaves identically to plaintext.

### 40.4. Tenant-Specific DEKs

A design can use a distinct Data Encryption Key (DEK) per tenant or document group. This helps satisfy key-separation requirements, with trade-offs:

- Managing many keys and key metadata.
- Rotation and rekey workflows.
- KMS latency and availability.
- Metadata needed to select the right key.
- Interactions with unique indexes, search, aggregations, and collations.

### 40.5. Never Equate Encryption with Authorization

If the application service can decrypt all tenants, a bug picking the wrong tenant key or an unscoped query can still leak data in the app. Enforce RBAC/authz and key-selection guards together.

### 40.6. Never Log Plaintext After Decryption

Encryption only protects data in database storage; application logs, traces, and exports can still leak plaintext without strict data-handling policies.

## 41. Noisy Neighbor: One Large Tenant Degrading All Tenants

Shared-collection SaaS:

```text
Tenant trial-17:
  10 requests/sec, 50 MB data

Tenant north-shop:
  100 requests/sec, 2 GB data

Tenant big-mart:
  5,000 requests/sec, 700 GB data,
  full aggregation scans

All share:
  mongod CPU
  WiredTiger cache
  disk IOPS
  storage/network
  connection capacity
```

An aggregation from `big-mart` can create I/O and CPU pressure that spikes latency for `north-shop`, even though tenants never read each other's data.

### 41.1. Layers of Protection

- Tenant-aware API rate limits.
- Per-tenant concurrency caps for expensive operations.
- Query deadlines/`maxTimeMS` or client-side timeouts per supported APIs.
- Bounded report/export jobs and background queues.
- Compound indexes for common patterns.
- Caps on record counts and export sizes.
- Per-tier quotas on data volume and retention.
- Workload partitioning: isolate analytics from OLTP where appropriate.
- Promote oversized tenants to dedicated clusters when needed.

### 41.2. Do Not Limit Only by Requests/Sec

100 cheap `find({_id})` calls cost far less than one aggregation scanning 300 million records. Build a **cost model** or at least classify operations (point lookup, list, report, export, write).

### 41.3. Database Profiler

Slow query logs and the profiler help identify expensive query shapes, yet do not automatically know tenant business context if logs lack authorized metadata. Never leave verbose profiling with sensitive payloads enabled indiscriminately.

### 41.4. Rate Limit Fairness

If rate limits apply per tenant and each tenant has many users/API keys, enforce limits at the tenant scope so creating multiple keys cannot bypass the aggregate quota.

### 41.5. Never Promise Absolute Performance Isolation

Shared clusters only mitigate noisy-neighbor risks; they cannot guarantee dedicated hardware isolation like a dedicated cluster.

## 42. Capacity Planning for the Shared Model

Volume estimate:

\[
\text{TotalData} =
\sum_{t=1}^{T} \text{DataSize}(t)
\]

Actual footprint also includes indexes, replication, oplog, temporary workspace, backups, and query working sets.

### 42.1. Example

```text
Tenants: 10,000
Average documents/tenant: 50,000
Average BSON document: 1 KiB

Raw logical data (before storage/index overhead):
10,000 * 50,000 * 1 KiB
≈ 477 GiB
```

This is a rough estimate; real storage size depends on compression, document sizes, indexes, replication, and storage internals.

### 42.2. P99 Tenants Can Differ Wildly from the Average

If 1% of tenants drive 90% of I/O, averages fail to predict hotspots. Measure:

- Top 1/10 tenants by storage.
- Top 1/10 tenants by read/write QPS.
- P95/p99 API latency by tenant tier.
- Large aggregations and index working sets.
- Peak seasonal spikes.

### 42.3. Namespace Overhead in Database-per-Tenant

If each tenant has 25 collections × 7 indexes/collection, 5,000 tenants generate massive collection and index metadata. Even with small data byte counts, catalog/index maintenance becomes its own scaling problem.

### 42.4. Dedicated Clusters Have Fixed Costs

Giving every tenant its own cluster adds overhead for compute, monitoring, backups, patching, credentials, and on-call support. Set tier promotion thresholds from empirical data, not a blanket desire for “maximum isolation”.

## 43. Connection Pools in a Java SaaS

`MongoClient` manages server discovery and connection pools; it should normally be long-lived.

### 43.1. Shared Cluster

```java
MongoClient client = MongoClients.create(sharedUri);

MongoDatabase shared = client.getDatabase("saas");
MongoCollection<Document> orders = shared.getCollection("orders");
```

Never create a new `MongoClient` per HTTP request or per tenant when they share a cluster and credentials.

### 43.2. Database-per-Tenant

```java
MongoDatabase tenantDb = client.getDatabase(trustedDbName);
```

Obtaining a `MongoDatabase` handle is far cheaper than opening a new client; always resolve the namespace from the registry.

### 43.3. Cluster-per-Tenant

Separate clients may be needed for distinct connection settings, hosts, credentials, or TLS certificates. Use a managed cache with:

- Maximum entries/capacity.
- Idle eviction and controlled close.
- Metrics for pools and active clients.
- Credential rotation support.
- Reference counting or lifecycle guards to avoid closing a client mid-request.

### 43.4. Calculating Connection Upper Bounds

With 100 app pods, each with max pool size 100 to one server:

```text
Potential pooled connections per server
≈ 100 pods × 100 = 10,000
```

That excludes monitoring sockets and other services; never assume `maxPoolSize=100` means the cluster receives at most 100 connections.

### 43.5. Dynamic Tenant Client Caches Are Not Inherently Safe

If connection config comes from untrusted tenant metadata, an attacker could trigger SSRF or credential leakage by altering the URI. Cluster keys must come from an allowlisted registry and trusted secrets store.

## 44. Monitoring, Alerting, and Cost Attribution

Suggested metrics:

| Metric | Unit | Labels to consider |
|---|---|---|
| `tenant_api_requests_total` | Requests | Tier, route, outcome |
| `tenant_api_latency_seconds` | Histogram | Tier, route |
| `tenant_query_errors_total` | Errors | Query family, error class |
| `mongodb_command_duration_seconds` | Histogram | Command name, service |
| `mongodb_pool_checkout_seconds` | Histogram | Cluster, service |
| `tenant_storage_bytes` | Bytes | Tenant bucket/tier or export outside TSDB |
| `tenant_report_queue_depth` | Jobs | Tier, priority |
| `tenant_quota_rejections_total` | Counts | Operation class, tier |
| `tenant_security_denials_total` | Counts | Reason class, route |

### 44.1. Tenant IDs and Cardinality

Attaching 50,000 tenant IDs to every Prometheus histogram across routes, statuses, and methods causes cardinality explosion. Consider:

- Aggregating metrics by tier, cluster, and plan.
- Separate top-N tenant dashboards.
- Access-controlled logs/traces with pseudonymous tenant IDs.
- Billing/cost attribution in a data warehouse rather than putting every ID in TSDB labels.

### 44.2. Counting Is Not Authorization

Metering shows tenant A sent 500 requests, not whether a request was authorized to read B. Security audits require correlating actor–tenant–resource/action–decision.

### 44.3. Alerts

- Sudden spikes in cross-tenant access denials.
- Queries rejected by guards for missing tenant scope.
- Elevated p99 latency by tier/cluster.
- One tenant saturating CPU/IO.
- Replica set elections and pool checkout timeouts.
- Tenant routing version mismatches.
- Stuck or failed provisioning.
- Data migration parity failures.

### 44.4. Missing Telemetry

If instrumentation is disabled, zero recorded failures does not prove zero errors. Monitor the metrics/logging pipeline itself and use independent application SLO checks.

## 45. Audit Logging and Support Access

Security logs should record:

```text
timestamp=...
actorId=staff-123
tenantId=north-shop
action=orders.read
resourceType=order
resourceId=opaque-order-id
decision=ALLOW
policyVersion=17
requestTraceId=...
```

### 45.1. Never Log Raw Order Documents

Orders can contain PII, payment, and shipping data. Logs need minimal metadata for investigation, never full BSON dumps or JWTs.

### 45.2. Break-Glass Support

Cross-tenant support access should require:

- Dedicated administrative identities.
- Reason/ticket reference and time-bounded validity.
- Policy checks or secondary approvals based on sensitivity.
- Reconcilable audit trails.
- Easy revocation.

### 45.3. Support Tool Reads Are Still Tenant Data Access

Never skip authorization just because the caller is an internal service. Internal endpoints often carry a larger blast radius than public APIs if credentials leak.

### 45.4. Switching Tenant Context

Every tenant switch must refresh UI, caches, and traces to the new scope; never leave results from the previous tenant visible on the new tenant's screen.

## 46. Spring Data MongoDB: Tenant-Filtered Repository Methods

Spring Data provides `MongoTemplate` and repositories. An explicit scoped query method:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class SpringTenantOrderQueries451 {
    private final MongoTemplate template;

    public SpringTenantOrderQueries451(MongoTemplate template) {
        this.template = template;
    }

    public Order451 findOne(
            AuthorizedTenant451 scope, ObjectId orderId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(scope.tenantId())
                .and("_id").is(orderId)
        );
        return template.findOne(query, Order451.class, "orders");
    }
}
```

`Order451` is a project-defined entity. This illustrates building strict queries, rather than assuming Spring Data automatically adds tenant filters to every repository.

### 46.1. Watch Out for `CrudRepository.findById`

A standard repository exposes `findById(id)` without requiring a tenant filter. If an app uses a shared collection and calls it directly, it can bypass tenant-aware rules.

Do:

- Build custom tenant-scoped repositories or service facades.
- Restrict exposed methods.
- Write integration tests for every public data access path.
- Audit derived query methods, custom `@Query`, and aggregation methods.

### 46.2. `@Query` Is a Per-Method Contract

```java
@Query("{ 'tenantId': ?0, 'orderNumber': ?1 }")
Optional<Order451> findByTenantIdAndOrderNumber(
    String tenantId, String orderNumber);
```

This notation is only safe when `tenantId` comes from an authorized context. Never expose a public controller allowing callers to pass an arbitrary `tenantId`.

### 46.3. Context-Bound Interceptors

Some applications build custom instrumentation/hooks to inject tenant filters. However, tenant-aware enforcement must cover reads, updates, deletes, aggregations, counts, exists checks, repository methods, pipeline lookups, and direct non-Spring driver calls.

Never trust a homegrown “automatic filter” to provide 100% protection without integration tests covering every operation.

### 46.4. Reactive Applications

In Spring WebFlux, tenant context can travel via Reactor Context rather than servlet `ThreadLocal`. Test async boundaries and message processing thoroughly.

## 47. Tenant Authorization Test Matrix

A minimal matrix:

| Action | Tenant A user | Tenant B user | Policy-governed global admin |
|---|---|---|---|
| Read A order | Yes if role permits | **No** | Yes if authorized and audited |
| Read B order | **No** | Yes if role permits | Yes if authorized and audited |
| Update A order | Per role/status | **No** | Per policy |
| Delete A order | Per role/status | **No** | Per policy |
| List A orders | Only A | No | Per explicit scope |
| Count A orders | Only A | No | Per explicit scope |
| Aggregate A revenue | Only A | No | Per explicit scope |
| Lookup A's customer | Only A | No | Per explicit scope |
| Download A's file | Only A | No | Per explicit scope |
| Export A report | Only A | No | Per explicit scope |

### 47.1. Also Test “Data Is Not Visible”

A method returning empty under scope B when passed tenant A's ID is a critical security assertion. Never test only that A can read A.

### 47.2. Test Updates and Deletes

Run update/delete from scope B targeting A's ID and assert:

- `matchedCount/deletedCount=0`.
- Document A remains untouched.
- Audit logs DENY/NOT_FOUND per policy without leaking A's contents.

### 47.3. Test Aggregations

Seed the same `customerCode` in two tenants, run `$lookup` from scope A, and assert only tenant A's customer appears in the response.

### 47.4. Test Pagination

A cursor issued for tenant A must be rejected for tenant B.

### 47.5. Test Concurrent Tenant Switching

Within the same browser/session, rapidly switch A→B while A's requests are in-flight; A's responses must not render under B's context if prohibited by UI policy.

## 48. JUnit 5 + Testcontainers: Testing Data Isolation

Example using **Testcontainers Java 2.x** with `org.testcontainers.mongodb.MongoDBContainer`, single-node replica set; a MongoDB container can still verify basic CRUD isolation.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class TenantBoundary451IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void tenantBCannotReadOrMutateTenantAOrder() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {
            MongoDatabase db = client.getDatabase("tenant_test_451");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            ObjectId aId = new ObjectId();
            orders.insertOne(new Document("_id", aId)
                .append("tenantId", "north-shop")
                .append("orderNumber", "PO-7")
                .append("status", "CREATED"));

            var filterForB = and(
                eq("tenantId", "big-mart"),
                eq("_id", aId));

            assertNull(orders.find(filterForB).first());

            long changed = orders.updateOne(
                filterForB, set("status", "PAID"))
                .getMatchedCount();
            assertEquals(0L, changed);

            long deleted = orders.deleteOne(filterForB)
                .getDeletedCount();
            assertEquals(0L, deleted);

            Document a = orders.find(
                and(eq("tenantId", "north-shop"), eq("_id", aId)))
                .first();
            assertNotNull(a);
            assertEquals("CREATED", a.getString("status"));
        }
    }
}
```

### 48.1. What Does This Test Prove?

MongoDB executes filters containing `tenantId` accurately. It does **not** by itself prove production repositories/controllers always pass those filters. Add tests through the service and API layers to prevent bypasses.

### 48.2. Negative Tests Matter More Than Smoke Tests Alone

Add tests for:

- A reads A successfully.
- B reads A's ID → not found.
- B updates/deletes A → nothing modified.
- Client sends a spoofed `tenantId` in the body → backend ignores/denies it.
- `$lookup` never joins B's customer onto A's order.
- Admin paths enforce separate auditing and authorization.

### 48.3. Never Use the Production Database

Use isolated test namespaces and disposable containers; never point integration tests that seed or drop data at a production URI.

### 48.4. Concurrency Testing

Run A and B requests concurrently across a thread pool to ensure no `ThreadLocal` leaks or reused mutable query objects carry over a prior tenant filter.

## 49. Property-Based Tests and Security Regressions

A stronger approach than a few hardcoded IDs:

1. Create 20 test tenants.
2. Give each tenant 100 orders with overlapping customer codes across tenants.
3. Generate random action sequences: insert, find, update, delete, count, aggregate.
4. Execute every action under an authorized scope.
5. Assert no returned document has `tenantId != scope.tenantId`.
6. Assert actions from another tenant never alter the target tenant's state.

### 49.1. Invariant

\[
\forall d \in \text{QueryResults}(t),\; d.\text{tenantId}=t
\]

For writes:

\[
\forall d \in \text{ChangedDocuments}(op_t),\; d.\text{tenantId}=t
\]

These invariants govern normal tenant-specific operations, not separately authorized cross-tenant admin workflows.

### 49.2. Conceptual Mutation Testing

Intentionally remove `tenantId` from a repository method in a test branch and verify the security regression test fails. If it still passes, you have a coverage gap.

### 49.3. Do Not Rely on Unpredictable Order IDs

Even when using globally unique ObjectIds, test a caller who already knows another tenant's ID. Security boundaries must never depend on unguessable IDs.

### 49.4. Test Error Responses

Never let exception messages, reports, or response logs expose fields from another tenant, even when an operation is denied.

## 50. API Test: Tenant Context Must Originate from the Server

A flow:

```text
POST /api/orders
Authorization: Bearer <valid user token>
X-Tenant-Id: north-shop

Body:
  { "orderNumber": "PO-451", "amountMinor": 350000 }

Backend:
  verify token
  check active north-shop membership + permission
  create AuthorizedTenant451
  insert document tenantId=north-shop
```

### 50.1. Client Deliberately Alters the Header

```text
Same user token
X-Tenant-Id: big-mart
```

If the user has no membership in `big-mart`, the backend must deny access; never “auto-switch tenants” based on the header.

### 50.2. Role Checks

A Viewer user may read orders in tenant A but must not cancel them or export sensitive data. Tenant equality is necessary yet **not sufficient** for authorization.

### 50.3. Client-Supplied Query Fields

The API should whitelist statuses, `createdAt` ranges, sort directions, and `pageSize`. Never let clients supply raw MongoDB operators like `$where`, `$lookup`, or serialized pipelines for unrestricted execution.

### 50.4. Default-Deny

If the tenant context is null, the membership service times out, or the registry is not ready, never fall back to `find({})` or a default database. Always fail closed per policy.

## 51. Runbook 1 — Suspected API Returning Wrong-Tenant Data

### Symptoms

- Users report seeing orders/customers not belonging to their organization.
- Response contains a `tenantId` differing from the authenticated scope.
- Logs show `findById` called with `_id` alone.
- Analytics/exports return broader data than the requested tenant.

### Response Priorities

1. **Contain impact immediately**: disable the affected endpoint/report or block via feature flag/gateway.
2. Preserve logs and trace metadata safely without leaking additional raw PII.
3. Identify actor, tenant, request time, affected document IDs, and cache keys.
4. Audit query paths: CRUD, aggregations, `$lookup`, caches, search, signed URLs.
5. Fix repositories to require `AuthorizedTenant` and guard all operations.
6. Add A/B tenant regression tests with overlapping business keys.
7. Evaluate incident reporting, notifications, and obligations per organizational policy.

### What Not to Do

Do not dismiss it as a UI bug and merely hide `tenantId` on the frontend. **Data transmitted to the client is still an exposure**, even if the UI does not render it.

### Incident Closure Criteria

Leak stopped, root cause identified, affected scope/time window mapped, reliable telemetry in place, regression tests added, and remediation plan executed for exposed data/caches.

## 52. Runbook 2 — One Tenant Slowing Down the Entire Cluster

### Symptoms

```text
Tenant big-mart starts massive report
Cluster disk IOPS and CPU rise
API p99 for north-shop increases
Pool checkout and command latency rise
```

### Investigation

1. Inspect resource usage and `currentOp`/slow query logs per policy.
2. Identify query shapes causing large scans, sorts, or aggregations.
3. Compare `totalDocsExamined` vs. `nReturned`.
4. Check `tenantId` index prefixes and sorting.
5. Check per-tenant concurrency and queues.
6. Evaluate whether the hot tenant's workload requires a separate cluster.

### Remediation

- Pause/throttle the offending tenant's report workers per policy.
- Add concurrency caps, rate limits, and bounded query deadlines.
- Optimize indexes, pagination, sampling, or materialized reports.
- Offload analytics workloads to appropriate resources.
- If necessary, plan migrating the tenant to dedicated infrastructure.

### What Not to Do

Do not increase connection pool sizes unboundedly to cure collection scans or I/O saturation.

## 53. Runbook 3 — Unique Index Prevents Two Tenants from Sharing an `orderNumber`

### Symptoms

Tenant A already has `PO-001`; tenant B inserts `PO-001` and hits `E11000 duplicate key` even though business rules allow it.

### Investigation

```javascript
db.orders.getIndexes();
```

Look for a collection-wide `{orderNumber:1}` unique index instead of `{tenantId:1,orderNumber:1}`.

### Remediation

1. Inspect existing data: null/missing `tenantId`, intra-tenant duplicates.
2. Confirm the business uniqueness scope.
3. Create the appropriate compound unique index per capacity and change plans.
4. Roll out query/code ensuring proper tenant filters.
5. Retire the old index per the migration plan.
6. Test that two tenants can reuse `orderNumber`, while one tenant cannot duplicate it.

### What Not to Do

Do not drop the old unique index before creating the compound unique index without understanding concurrent writes; never arbitrarily alter tenant B's `orderNumber` to mask a schema bug.

## 54. Runbook 4 — MongoDB DB User Unauthorized

### Symptoms

```text
MongoCommandException code 13 (Unauthorized)
MongoSecurityException / authentication error
```

### Investigation

- Is the tenant using shared or database-per-tenant mode?
- Does the service identity have privileges on the right namespace?
- Are `authSource` and role mappings accurate?
- Is the tenant registry pointing to the wrong database?
- Was a secret rotation rolled out completely?
- Did the app bypass the routing registry?

### Remediation

Fix DB roles, credentials, or registry mappings following least privilege and approvals; audit the change.

### What Not to Do

Never grant `root` to the app user or disable authentication to “temporarily silence errors”. Never treat code 13 as a transient error and retry infinitely.

## 55. Runbook 5 — Tenant Routing Split-Brain After Migration

### Symptoms

Two pods serve `big-mart`, yet one pod writes to the shared cluster while the other writes to the dedicated cluster.

### Possible Causes

- Stale routing cache.
- Inconsistent registry versions.
- Cutover lacked a write gate or fencing.
- CDC catch-up had not finished.
- Retries from an old background worker still writing to the source.

### Remediation

1. Pause affected tenant writes if needed to protect consistency.
2. Determine the authoritative target per the approved cutover version.
3. Collect `routingVersion` logs and operation IDs from pods.
4. Reconcile writes across both destinations by business identity.
5. Fence stale writers using routing versions/fencing.
6. Verify data parity and only then resume writes.

### What Not to Do

Never flip routing metadata back and forth repeatedly without reconciling data created on each side.

## 56. Runbook 6 — Backup Needs Per-Tenant Restore

### Symptoms

Tenant `north-shop` asks to restore records accidentally deleted at 10:00 while all other tenants continue operating normally.

### Safe Approach

1. Determine RPO/RTO, current state, and the exact business scope to restore.
2. Restore the snapshot/PITR to an **isolated temporary environment**.
3. Extract only the target tenant scope.
4. Inspect documents created after the restore point to avoid overwrites.
5. Run a merge/restore procedure with identity and version checks.
6. Rebuild/invalidate required indexes, search, and caches.
7. Verify references and audit impact.

### What Not to Do

Never restore the entire shared database over production just to recover one tenant: other tenants would lose valid writes.

## 57. Runbook 7 — Deleted Tenant Still Has Data in Cache/Search

### Symptoms

MongoDB records were deleted, yet search results, signed URLs, or old exports remain accessible.

### Response

- Inventory storage surfaces: MongoDB, object storage, search, caches, CDC sinks, backups.
- Disable API keys/sessions and tenant routing first.
- Purge cache keys scoped by tenant+resource.
- Delete search documents by tenant scope and verify index state.
- Revoke signed URLs where supported, or expire TTLs/rotate object keys per policy.
- Check legal holds/retention before destructive actions.
- Record verification evidence rather than merely logging “deleteMany succeeded”.

### What Not to Do

Never conclude “everything is deleted” solely because `db.orders.countDocuments({tenantId}) == 0`.

## 58. Runbook 8 — New Indexes Slow Down Writes

### Symptoms

After rolling out several compound indexes, insert/update latency spikes and the storage/index working set balloons.

### Investigation

1. List the new indexes and the access patterns they serve.
2. Run `explain` for representative queries.
3. Check index usage stats or hidden indexes where supported.
4. Measure write amplification, cache pressure, disk utilization, and index build impact.
5. Distinguish regressions caused by the app rollout vs. background index builds.

### Remediation

- Keep indexes proven beneficial for SLOs.
- Remove or restructure redundant indexes per a migration plan.
- Consider materialized views or tiered query/report paths.
- For huge tenants with custom patterns, evaluate database/cluster isolation if justified.

### What Not to Do

Never drop an index just because “no queries used it in the last 5 minutes”; weekly/monthly reporting workloads may depend on it.

## 59. Summary of Anti-Patterns in Multi-Tenant Design

| Anti-pattern | Consequence | Replacement |
|---|---|---|
| `find({_id})` in shared collection | Cross-tenant read | `tenantId + _id` |
| `updateOne/deleteMany` without tenant scope | Cross-tenant modification | Mandatory scoped filter |
| Trusting `X-Tenant-Id` or body | Client chooses any tenant | Authenticate + membership check |
| Signed header with revoked role | Stale permissions | Revalidate per policy/expiry |
| Mutable global currentTenant variable | Scope leaks across threads | Explicit immutable context |
| ThreadLocal without cleanup | Leftover scope from prior request | Safe lifecycle/context propagation |
| Accepting raw MongoDB filters/pipelines from clients | Policy bypass/expensive queries | Whitelisted query builder |
| `$lookup` joining only customerCode | Mixes customers across tenants | Join tenant+business key |
| `$unionWith` without secondary filter | Exposes other tenants' data | Scope subpipeline |
| `$merge` target key missing tenant | Overwrites shared report records | Tenant-aware target identity |
| Cache key using only orderId | Serves wrong cache entry | Scope key by tenant/visibility |
| Signing client-supplied raw fileKey | Leaks attachments | Resolve from authorized resource |
| Treating MongoDB RBAC as row-level | False security assumption | App authz + server scopes |
| All services using `root` | Huge blast radius | Least-privilege identities |
| DB-per-tenant with all-DB app credential | Routing bug still grants access | Separate identities/policies if needed |
| Missing `tenantId` on auxiliary collection | Leaks via relations | Ownership schema |
| Letting PATCH edit `tenantId` | Unauthorized data transfer | Immutable field/dedicated workflow |
| Collection-wide unique `orderNumber` | Tenants collide | Composite unique tenant+orderNumber |
| Indexing only `status` for tenant queries | Wide/slow scans | Query-aligned compound indexes |
| Defaulting to collection-per-tenant | Namespace/index explosion | Shared model/hybrid |
| Creating MongoClient per request/tenant | Connection storm | Reuse per cluster/config |
| `tenantId`-only shard key with giant tenant | Data/hotspot limits | Appropriate compound/distribution key |
| Sharded unique index ignoring shard key rules | Fails to guarantee uniqueness | Verify sharding constraints |
| Treating `tenantId` as global commit order | Misleading correctness | Stable IDs/versions/CDC |
| Filtering search tenant only on UI | Results already leaked | Server-side search filter |
| Reading change stream tenant solely from fullDocument | Delete events lack the field | Trusted event envelope |
| Restoring one tenant over shared DB | Loses other tenants' data | Temp restore + scoped merge |
| Treating MongoDB deletion as full offboarding | Cache/files/search remain | End-to-end deletion |
| Letting all tenants share 100% cluster budget | Noisy neighbor | Global/per-tenant quotas |
| Indexing every custom field | Memory/storage/write overhead | Allowlist/index by measured need |
| Claiming “encrypted = authorized” | App can read cross-tenant | RBAC + key selection + authz |
| Client supplying databaseName | Wrong namespace/SSRF risk | Trusted routing registry |
| Switching migration URI mid-writes | Split-brain/lost data | CDC/dual-write/fencing |
| Testing only happy-path tenant A | Misses cross-tenant leaks | Negative A/B security tests |
| Logging raw BSON, JWTs, or credentials | PII/secret exposure | Redacted structured metadata |
| Tagging Prometheus with every tenantId | Cardinality explosion | Tiered metrics/separate top-N views |
| Assuming separate clusters eliminate all risk | App/cache/exports can still leak | End-to-end threat model |

## 60. Scenario-Based Model Selection Table

| Scenario | Consider first | Questions to verify |
|---|---|---|
| 20,000 very small tenants | Shared collections | Are authz guards and indexing solid? |
| 100 tenants with differing schemas/retention | Database/collection per tenant | Is index/catalog overhead manageable? |
| One enterprise tenant drives most I/O | Hybrid/dedicated cluster | What are resource isolation/SLO needs? |
| Tenants with regional residency mandates | Region-based cluster routing | Do backups/logs/exports stay in-region? |
| Cross-tenant analytics across all tenants | Shared model or analytics copy | Is admin authorization/auditing enforced? |
| Per-tenant DB credentials mandatory | DB per tenant or cluster per tenant | How do identity/pool management scale? |
| Frequent per-tenant restores required | Dedicated DB/cluster or restore workflow | What granularity does your backup tool support? |
| Custom Atlas Search ranking per tenant | Hybrid/index strategy | Are index mappings/costs viable? |
| Billions of shared documents | Sharding | What are shard key targeting, skew, and uniqueness limits? |
| High volume of free-tier trial tenants | Shared model + quotas/TTL | How are noisy-neighbor and retention handled? |

These are design suggestions, not mandatory standards. Final decisions rest on prototypes, threat modeling, real compliance requirements, SLOs, and operational costs.

## 61. Hands-On Exercises

### Exercise 1 — Distinguishing Tenant and User

Alice belongs to tenant A as Admin and tenant B as Viewer. Explain why Alice's user identity alone is insufficient to authorize an action on an order.

### Exercise 2 — Choosing a Model

A SaaS has 30,000 tenants averaging 500 documents/tenant. Compare shared collection, collection per tenant, and database per tenant, noting namespace/index overhead.

### Exercise 3 — Enterprise Tenant

One tenant consumes 70% of disk IOPS and requires a dedicated SLO. Analyze when a dedicated database or cluster is needed, and what database-per-tenant still fails to isolate.

### Exercise 4 — Threat Model

Trace `GET /orders/{id}` through authentication, membership, service, MongoDB, cache, and response. Mark at least five points where data could leak.

### Exercise 5 — Spoofed Header

A user belonging only to tenant A sends `X-Tenant-Id:B`. Write pseudocode validating identity and membership before creating `AuthorizedTenant`.

### Exercise 6 — Global ObjectId

Explain why unpredictable ObjectIds cannot replace authorization. Write a safe filter for `findById`.

### Exercise 7 — Per-Tenant Unique Index

Two tenants both have orderNumber `INV-100`. Write a compound unique index permitting this while blocking intra-tenant duplicates.

### Exercise 8 — Soft Delete

Design a partial unique index when active documents are defined by `deletedAt` **not existing**. Why is `deletedAt:null` not necessarily equivalent?

### Exercise 9 — Case-Insensitive Uniqueness

Tenant A wants `INV-001` and `inv-001` treated as duplicates. Design a collation/index or canonical key with explicit rules.

### Exercise 10 — Access Pattern Indexing

Which index does `find({tenantId,status}).sort({createdAt:-1}).limit(50)` need? Explain equality/sort order and how to verify with `explain`.

### Exercise 11 — Over-Indexing

A service has 25 indexes on `orders` and write QPS surges. Describe how to measure index usage, query latency, and decide which indexes to drop.

### Exercise 12 — Pagination

Write a keyset query for `createdAt DESC, _id DESC` within a tenant without large offsets. Why is a tie-breaker necessary?

### Exercise 13 — Cross-Tenant Cursor Replay

Design a signed cursor carrying tenant/context. What happens when a user grabs a cursor in tenant A and switches to B?

### Exercise 14 — Upsert

An order import API uses `updateOne({externalId},...,upsert:true)`. Identify the vulnerability and rewrite the filter/index properly.

### Exercise 15 — BulkWrite

A batch of 500 updates for tenant A contains one `UpdateOneModel` filtering only by `_id`. Why is checking total `matchedCount` insufficient to detect an isolation leak?

### Exercise 16 — `$lookup`

Customer code `C001` exists in both A and B. Write a `$lookup` pipeline matching both `tenantId` and `customerCode`.

### Exercise 17 — `$unionWith`

A dashboard unions `orders` and `supportTickets`. Write tenant filters for both the main pipeline and the union pipeline.

### Exercise 18 — Aggregation Sandbox

A client sends an arbitrary pipeline containing `$lookup`/`$unionWith`. Why is simply prepending `$match tenantId` insufficient? Design an allowlisted report API.

### Exercise 19 — `$merge`

The app writes to a `monthlyRevenue` collection. Design a target identity with tenantId+month+currency so tenants never overwrite each other's results.

### Exercise 20 — Shard Key

One tenant has 200 million orders while 10,000 others are tiny. Compare shard key `{tenantId:1}` vs. a compound key, detailing skew, targeting, and uniqueness trade-offs.

### Exercise 21 — Unique Index on a Sharded Collection

Explain why you cannot create an arbitrary cross-shard unique constraint ignoring the shard key. Propose a unique key design supported by your target server version.

### Exercise 22 — Database-per-Tenant Registry

Design a registry mapping tenant ID → cluster/database name. How do you stop clients from injecting custom database names or URIs?

### Exercise 23 — RBAC

Create a read-only DB identity for tenant A and try accessing tenant B's database. Contrast server RBAC with HTTP application authorization.

### Exercise 24 — Read-Only Views

Evaluate when a MongoDB view helps restrict read access, and why views do not replace tenant isolation for writes, caches, or search.

### Exercise 25 — Spring Data

In a shared-collection app, what risk does `CrudRepository.findById(id)` pose? Design a custom repository requiring `AuthorizedTenant`.

### Exercise 26 — Caching

Two tenants use the same orderNumber `PO-001`. Write the cache key and a test for rapid tenant switching in the UI.

### Exercise 27 — Search

An app uses Atlas Search. Design a compound search query filtering tenant inside search if supported by your index/operator; explain why UI-only filtering is wrong.

### Exercise 28 — Change Streams

A consumer processes a delete event where `fullDocument` is missing. How do you route the event to the right tenant without guessing?

### Exercise 29 — Transactions

Create an order and deduct inventory in a transaction. Why does a successful commit not prove the code updated the right tenant?

### Exercise 30 — Tenant Provisioning

A worker crashes after creating databases/indexes before marking the tenant ACTIVE. Design idempotent provisioning with states and retries.

### Exercise 31 — Tenant Migration

Move `big-mart` from shared to a dedicated cluster while writes continue. Design backfill, CDC, `routingVersion`, cutover, and rollback.

### Exercise 32 — Restore

Tenant A accidentally deleted orders while tenants B/C keep running. Why not restore the whole shared database over production? Design a scoped restore.

### Exercise 33 — Deletion

A tenant requests account deletion. Inventory MongoDB, object storage, caches, search, exports, backups, and legal holds.

### Exercise 34 — Noisy Neighbor

One tenant fires 500 aggregations/sec. Design per-tenant concurrency caps, global resource budgets, query deadlines, and alerts.

### Exercise 35 — CSFLE

An enterprise tenant requires its own DEK. Describe key management/rotation and why encryption cannot replace application authorization.

### Exercise 36 — Cardinality

A system has 100,000 tenants. If Prometheus histograms attach `tenantId`, route, outcome, and method, what breaks? Propose aggregated metrics and alternative tracing.

### Exercise 37 — Negative Integration Test

Using Testcontainers, seed orders for tenants A/B with overlapping IDs and business keys. Write tests proving B cannot read/update/delete A and cannot join A's customer out of scope.

### Exercise 38 — Incident Response

After a deploy, logs reveal 10 requests missing a tenant filter. Determine blast radius, containment steps, auditing, data exposure review, and regression tests.

### Exercise 39 — Tenant Tier Capacity

A service has 100 app pods with `MongoClient` max pool 100/server. Estimate the upper bound on pooled connections to that server and discuss what changes if creating 50 separate `MongoClient`s per instance.

### Exercise 40 — Capstone

Design a MongoDB architecture for a B2B SaaS with:

1. 50,000 free tenants, 500 commercial tenants, and 20 enterprise tenants.
2. One large tenant driving 60% of traffic.
3. Per-tenant unique order numbers.
4. Recent orders listing/pagination and full-text search.
5. Customer lookups and monthly revenue reports.
6. Owner/Editor/Viewer roles and break-glass support.
7. Multi-region/residency constraints.
8. Onboarding/offboarding and per-tenant backup/restore.
9. Online migration from shared to dedicated.
10. SLOs, noisy-neighbor rate limits, security tests, and auditing.

Present routing/storage diagrams, indexes, access policies, query examples, migration/rollback protocols, and a test matrix proving tenant isolation.

## 62. MongoDB SaaS Architecture Blueprint

A synthesized example:

```text
  Web / Mobile / API clients
               |
               v
     Identity & Authentication
               |
               v
 Tenant Membership / Permissions
               |
               v
        AuthorizedTenant
               |
               v
         Application API
               |
          Tenant Router
               |
      +--------+-----------+
      |                    |
      v                    v
Shared deployment     Dedicated deployments
  saas.orders          tenant_X.orders
  saas.customers       tenant_X.customers
  saas.events          tenant_X.events
      |                    |
      +--------+-----------+
               |
          CDC / Outbox
               |
      +--------+-----------+
      |        |           |
      v        v           v
    Cache    Search     Analytics
      |        |           |
      +--------+-----------+
               |
       Tenant-aware access
               |
               v
        User-scoped response
```

### 62.1. Boundaries at Every Layer

| Layer | Invariant |
|---|---|
| Identity | Caller is authenticated |
| Membership | Caller is authorized for tenant/action |
| Router | Trusted tenant maps to the right storage |
| MongoDB shared | Every document read/write carries tenant scope |
| MongoDB dedicated | Credential/database scope matches tenant |
| Index | Unique keys/query plans match scope |
| Search | Queries include tenant filter and index support |
| Cache | Keys and visibility policies include tenant |
| Event bus | Event envelopes/routing/consumers are authorized |
| Object storage | File access goes through authorized metadata |
| Observability | Metadata supports auditing without leaking secrets |
| Backup/restore | Scoped recovery without impacting other tenants |

### 62.2. The Most Important Design Rule

**Never assume a tenant boundary exists just because one layer added `tenantId`.** Authorization must be enforced consistently from the incoming request all the way to MongoDB and every downstream data sink.

## 63. Pre-Production Checklist

### 63.1. Model Selection

1. Documented rationale for choosing shared/database/cluster/hybrid.
2. Forecasted tenant counts, p95/p99 tenant size, and QPS.
3. Defined thresholds for promoting large tenants to dedicated storage.
4. Evaluated noisy-neighbor, backup/restore, and data residency needs.
5. Established the tenant registry as the routing source of truth.

### 63.2. Data Model

1. Every tenant-owned document has a valid `tenantId`.
2. `tenantId` cannot be modified via public updates.
3. Related documents always verify tenant ownership.
4. Unique constraints include tenant ID where business scope requires.
5. Partial indexes/soft deletes have explicit schema semantics.
6. Time-based retention and legal holds have policies.

### 63.3. Authorization

1. Tenant context is created only after AuthN + membership/role checks.
2. Missing context fails closed.
3. Repository methods use tenant-scoped APIs.
4. Never expose raw MongoDB filters/pipelines from users.
5. CRUD/bulk/upsert/aggregation/search/change streams audited.
6. Admin cross-tenant access uses separate audited paths.
7. MongoDB service identities follow least privilege.
8. Cache/file/export/event paths preserve scope.

### 63.4. Indexing and Scale

1. Indexes match top query shapes.
2. `explain` verified on representative data.
3. No excessive redundant indexes.
4. Shard keys analyzed for hotspots and tenant skew.
5. Sharded unique indexes satisfy server constraints.
6. Pool/concurrency/quota metrics instrumented.
7. Growth plan in place for oversized tenants.

### 63.5. Operations

1. Tenant provisioning is idempotent.
2. Migrations use dual-write/CDC/checkpoints/verification.
3. Tenant moves use routing versions/fencing.
4. Per-tenant restores tested.
5. Offboarding covers all data sinks and retention tiers.
6. Logs/metrics redacted with bounded cardinality.
7. Security incident runbooks prepared.
8. Alerts and on-call ownership assigned.

### 63.6. Testing

1. Negative A/B tests at API/repository layers.
2. Tests proving updates/deletes never alter another tenant's data.
3. Tests for `$lookup`/`$unionWith` aggregations.
4. Tests for caches, search, exports, and file downloads.
5. Tests for admin path permissions and auditing.
6. Tests for tenant switching and async context propagation.
7. DB role tests when using DB-per-tenant.
8. Migration, cutover, and rollback tests.

## 64. Summary

A multi-tenant MongoDB application must choose **the right isolation model** based on workload, regulations, and cost. Shared collections serve huge numbers of tenants on one shared schema and index set, yet demand strict application-level tenant scoping. Database/collection per tenant adds namespace management flexibility and resource-level RBAC, yet does not isolate cluster CPU/IO. Dedicated clusters offer stronger operational and blast-radius isolation at higher cost and complexity.

**Data must carry proper identity and authorization.** `tenantId` must be a backend-controlled invariant, not arbitrary client input. MongoDB RBAC does not automatically provide document-level authorization inside a shared collection. Every `find`, `update`, `delete`, `bulkWrite`, `aggregate`, `$lookup`, `$unionWith`, search query, cache lookup, event consumer, and file download needs its own boundary.

**Indexes must align with access patterns.** Compound keys like `{tenantId:1,status:1,createdAt:-1}` or `{tenantId:1,orderNumber:1}` are essential, yet require `explain` verification, index maintenance awareness, and compliance with sharded unique index constraints. “Having an index” does not mean “data is isolated”.

**Operations are also multi-tenancy.** Provisioning, dynamic routing, online migrations, per-tenant backup/restore, data deletion, search/cache cleanup, encryption key selection, and quota/noisy-neighbor controls are all part of the design. Cross-tenant data leaks can happen outside MongoDB even when the underlying database query is spotless.

A trustworthy design must have **security regression tests proving tenant B cannot view or alter tenant A's data**, observability and runbooks to catch and remediate issues, and a clear upgrade path from shared to dedicated storage as customers grow.

## 65. References

- [MongoDB — Building with Patterns: Multi-Tenant Applications](https://www.mongodb.com/docs/atlas/build-multi-tenant-arch/): multi-tenant architecture options on Atlas.
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): resource privileges and role semantics.
- [MongoDB Manual — Create a User](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): users and database roles.
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/): least privilege, TLS, and security controls.
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/): index strategies and costs.
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): key order and prefixes.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): uniqueness semantics.
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partialFilterExpression and query applicability.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale comparison/index interactions.
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/): expiration behavior.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): shards, mongos, and shard keys.
- [MongoDB Manual — Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/): cardinality, frequency, and monotonicity.
- [MongoDB Manual — Unique Indexes and Sharded Collections](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters-and-unique-indexes): shard key prefix rules.
- [MongoDB Manual — Aggregation $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): joins and pipeline syntax.
- [MongoDB Manual — Aggregation $unionWith](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unionWith/): multiple collections.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): event streams, deletes, and resume tokens.
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): encryption and key management.
- [MongoDB Manual — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): query capabilities on encrypted fields.
- [MongoDB Java Sync Driver — Read and Write Data](https://www.mongodb.com/docs/drivers/java/sync/current/crud/): CRUD, filters, updates, and aggregation.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): MongoClient and pool lifecycles.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, repositories, and mapping.
- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): integration testing MongoDB with Testcontainers.
