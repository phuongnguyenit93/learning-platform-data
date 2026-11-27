# Building a Trade-Off Matrix Between Data Modeling, Consistency, Performance, and Operations in MongoDB Application Design

A MongoDB design should not be evaluated solely by asking "is this query fast?". A document that embeds all data may read quickly, yet grow in size, cause update contention, and make history difficult to store. A referenced model is easy to modify independently, yet requires multiple read round trips or `$lookup` aggregations. A sharded collection can distribute capacity, yet introduces cross-shard queries and operational complexity. A read preference that offloads the primary may serve staler data, which is unsuitable for transaction confirmation screens.

Therefore, when **designing a MongoDB application**, an engineer must build a trade-off matrix to decide **data modeling**, **consistency/durability levels**, **read–write performance**, and **operational cost** simultaneously. The matrix is not a generic technology leaderboard. It is a **decision record tailored to a specific workload and business invariants**, complete with assumptions, measured data, exclusion criteria, temporary choices, residual risks, and review triggers.

This lesson walks through the methodology from gathering requirements and classifying constraints to building a trade-off matrix, weighted scoring, designing experiments, and writing an Architecture Decision Record (ADR). Examples use a multi-tenant e-commerce system with `orders`, `products`, `inventory`, `payments`, and a near-real-time activity feed. It clearly separates illustrative assumptions from MongoDB properties to avoid forcing a single pattern onto every application.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Define the decision scope, workload, and business invariants before choosing a schema.
2. Distinguish **mandatory** criteria from **trade-off** criteria.
3. Build an access-pattern matrix by query, filter, sort, payload, and frequency.
4. Compare embedded documents, references, hybrid denormalization, and materialized views.
5. Choose aggregate boundaries based on single-document atomicity and rate of change.
6. Analyze consistency, durability, read/write concerns, and read preference per use case.
7. Trade off indexes, query plans, write amplification, RAM/IO, and growth over time.
8. Evaluate the performance of `$lookup`, aggregation, pagination, caching, and hot documents.
9. Identify the 16 MiB/document limit, unbounded arrays, and fan-out.
10. Evaluate replica sets, transactions, sharding, shard keys, and multi-tenant isolation.
11. Estimate storage, RAM, capacity headroom, backup, and operational costs.
12. Use a weighted scoring matrix without using points to rationalize violating an invariant.
13. Design benchmarks, load tests, and measurement plans for p95/p99, keys examined, and conflict rates.
14. Build an ADR with alternatives, assumptions, reversal conditions, and monitoring.
15. Apply the decision framework to three problems: checkout, catalog, and activity feed.

## 2. Why Is There No Single "Best MongoDB Schema"?

MongoDB stores data as BSON documents, allowing flexible modeling and co-locating data that is frequently read together in the same document. However, "putting everything into one document" also has limits:

- Each BSON document has a maximum size of **16 MiB**.
- A document containing an endlessly growing array tends to be updated continuously, creating hot spots and growth overhead.
- Data parts that must change independently or are shared across multiple aggregates may fit references better.
- References between collections do not automatically provide RDBMS-style foreign-key constraints; the application must design for integrity.
- Multi-document transactions can be used when the MongoDB deployment supports them, but they add complexity, contention, and cost compared to a single atomic document update.
- Sharding scales capacity/throughput via partitioning, but a query that cannot target a shard may incur scatter-gather.

**Optimizing along one dimension can degrade another.** Increasing denormalization typically reduces read count but increases the number of copies that must be updated. Adding indexes helps read queries but increases disk/cache consumption and write maintenance. Increasing consistency by reading from the primary and using a stronger write concern can change the latency/availability profile.

## 3. Four Core Decision Axes

| Axis | Question to Answer | Example Criteria |
|---|---|---|
| **Modeling** | Do documents, references, and aggregates accurately represent the domain? | Boundaries, cardinality, lifecycle, update ownership |
| **Consistency** | Which results must be visible immediately, and which writes must never be lost? | Atomicity, stale-read budget, uniqueness, write concern |
| **Performance** | Does the workload meet its SLO under realistic load and growth? | p95/p99, throughput, index use, read/write amplification |
| **Operations** | Can it be backed up, monitored, migrated, restored, and run safely? | Complexity, DR, costs, deployment, on-call, rollback |

A design may score high on two axes and low on the remaining two. The goal is to **satisfy all mandatory conditions** and select the option with the most appropriate overall trade-off, rather than hypothetically maximizing every axis.

### 3.1. Additional Axis: Security and Compliance

In real products, security, tenant isolation, retention, and compliance can be non-negotiable constraints. For example, reading another tenant's data is never allowed even if it makes queries faster. These can be placed in a separate "hard constraints" section instead of being scored like optional features.

### 3.2. "Simplicity" Is Also an Engineering Outcome

A design using one collection, two indexes, and one atomic update may outperform a design with five collections, multiple transactions, and CDC if both meet requirements. Cognitive load, operational cost, and debugging difficulty are all part of the decision.

## 4. Trade-Off Matrix Process

~~~mermaid
flowchart TD
    Scope["1. Define use case and boundaries"] --> Invariants["2. Record hard invariants/SLOs"]
    Invariants --> Workload["3. Gather access patterns and growth"]
    Workload --> Candidates["4. Generate viable candidates"]
    Candidates --> Gate{"5. Any hard constraint violated?"}
    Gate -->|"Yes"| Reject["Reject or revise option"]
    Reject --> Candidates
    Gate -->|"No"| Matrix["6. Build qualitative matrix"]
    Matrix --> Score["7. Score and attach confidence"]
    Score --> Measure["8. Prototype + benchmark"]
    Measure --> ADR["9. Decide + ADR + monitoring"]
    ADR --> Review["10. Revisit when workload changes"]
~~~

The process should start from **access patterns and business invariants**, not from a list of database features looking for a problem to apply them to.

### 4.1. Required Deliverables

At a minimum, an evaluation needs:

1. A problem statement with scope and out-of-scope boundaries.
2. Hard constraints and SLOs/SLIs.
3. An access-pattern and cardinality table.
4. At least two viable options.
5. An evidence-backed trade-off table, not just keywords like "fast/slow".
6. Risks, mitigations, test results, and an ADR.

## 5. Distinguishing Mandatory Constraints from Trade-Off Constraints

Example of a payment system:

| Requirement | Type | How to Prove |
|---|---|---|
| Never charge twice for the same request ID | Mandatory | Unique ledger + integration/idempotency tests |
| Non-negative balance on withdrawal | Mandatory | Atomic conditional update + concurrent tests |
| Never expose another tenant's orders | Mandatory | Security scope + permission tests |
| Checkout API p95 under 250 ms | SLO, threshold-based | Representative workload load test |
| Catalog page opens within 100 ms | Performance target | API p95/p99 + query stats |
| Cost lower by 20% | Tradeable target | Capacity/cost estimation |
| Easy migration rollback | Operational target | Rollback rehearsal and compatibility test |

Never add points to compensate for violating "no double charge". If an option has an unacceptable probability of domain error, it is **not a valid candidate** for that business flow.

### 5.1. Estimated Values Must Be Marked

Numbers like 250 ms, 20%, and the data sizes in this lesson are only **assumptions for learning the methodology**. Real projects must derive them from product SLOs, production data, load forecasts, and risk policies.

### 5.2. Do Not Use "Eventual Consistency" as a License to Break Invariants

A catalog price display may tolerate a few seconds of staleness. However, checkout must lock in pricing/payment per business policy and record an authoritative outcome. Distinguish **display data that may lag** from **financial decisions that must be atomic/reconcilable**.

## 6. Sample Problem: Multi-Tenant Store

Assume the system has these collections:

~~~text
products       catalog information, name, images, display price
inventory      sellable and reserved quantities per SKU/warehouse
orders         orders, line items, status history
payments       transactions and ledger for idempotency/audit
customers      customer profiles
activityEvents large, append-only activity events
~~~

Assumed load:

- 2 million products, 30 million orders, 300 million activity events.
- 90% of catalog requests are reads, mostly filtered by tenant/category and sorted by popularity or recency.
- Checkout spikes sharply during campaigns, with many customers competing for the same SKU.
- An order typically has 1–20 line items, while some B2B orders have hundreds of lines.
- Each user needs to view their 20 most recent orders or click "Load more".
- Financial audit data is retained for multiple years and requires reconciliation.

These figures are illustrative for workload design; they are not actual MongoDB performance forecasts.

## 7. Building the Access-Pattern Matrix

| ID | Operation | Filter/Sort | Required Data | Frequency/Depth | Consistency Level |
|---|---|---|---|---|---|
| Q1 | Search catalog | tenant/category, sort popular | product summary | Very high, shallow pages | Short staleness acceptable |
| Q2 | View product detail | tenant + productId | info + media metadata | High | Display price requires policy |
| Q3 | Checkout | tenant + SKU, qty | available, price snapshot | Burst write | No overselling per policy |
| Q4 | View order | tenant + orderId | items, totals, status | Medium | Confirmed order must be readable |
| Q5 | Order list | tenant/customer/status, createdAt desc | summary | High, paginated | Feed consistency defined |
| Q6 | Record payment | tenant + requestId | ledger + outcome | Write critical | Idempotent and auditable |
| Q7 | Revenue report | tenant + date/status | aggregate sums | Scheduled | Snapshot/cutoff policy |
| Q8 | Activity feed | tenant + actor, eventTime desc | a few fields | Very large, deep scroll | Eventual allowed |

### 7.1. Do Not Design Collections Before Knowing Queries

A collection with a "pretty" schema that fails to serve Q1–Q8 can cost network round trips and `$lookup` overhead. MongoDB schema design is closely tied to **critical queries and how data is updated**.

### 7.2. Write Concrete Query Shapes

"Find orders fast" is too vague. Write:

~~~javascript
db.orders.find(
  { tenantId: "t-01", customerId: "C-9", status: "PAID" },
  { orderNo: 1, totalMinor: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(20)
~~~

Only from this shape can you evaluate compound indexes, payload size, sort stability, deep pagination, and tenant routing.

## 8. Cardinality, Growth, and Ownership

For each relationship:

| Relationship | Cardinality | Bounded Count? | Changed By Whom? |
|---|---|---|---|
| Order → line items | Small/medium 1:N | Usually business-bounded | Checkout service |
| Product → comments | Large, ever-growing 1:N | No | Many users |
| Customer → orders | Large 1:N | No | Checkout service |
| Order → shipping address snapshot | 1:1 at order time | Yes | Order aggregate |
| Product → category | N:1 | Can be shared | Catalog admin |
| Tenant → activity events | Very large 1:N | No | Many services |

### 8.1. Do Not Measure Only the Average Count

If 99% of orders have 5 lines but 1% of B2B orders have 50,000 lines, assuming "the array is small" is dangerous. You must measure p50/p95/p99 sizes and identify extreme outliers.

### 8.2. Update Ownership

If a child is always created/modified/deleted with its parent, embedding may make sense. If multiple services update the child independently or the child is referenced by multiple parents, references/hybrid are usually easier to manage.

## 9. Three Basic Modeling Candidates

**Option A — embedding:** embed children/snapshots inside the parent; typically one document read is enough.

**Option B — references:** store a separate child collection with parentId/productId, joined via application queries or aggregation.

**Option C — hybrid:** store snapshots of needed fields inside the parent while keeping a reference to the source entity for independent operations.

~~~mermaid
flowchart LR
    A["A: Order { items: [...] }"] --> ARead["Read one document"]
    B["B: orders + orderItems"] --> BRead["Query children or lookup"]
    C["C: Order with item snapshots + productId"] --> CRead["Read snapshot, update catalog separately"]
~~~

Do not score before identifying hard constraints such as size, integrity, and read-after-write.

## 10. Embedding vs. References Trade-Off Table

| Criterion | Embedding | References | Hybrid |
|---|---|---|---|
| Reading parent + children | Usually one document | Requires multiple queries/`$lookup` | Fast snapshot read |
| Writing parent + embedded fields | Atomic within one document | May need multiple writes/transaction | Must define source of truth per field |
| Independent child updates | Can increase contention | Natural | Partially needs sync |
| Unbounded child growth | 16 MiB/hot array risk | Better suited | Embed only a bounded subset |
| Shared child across parents | Data duplication | Reference reuse | Reference + selected snapshot |
| Immutable historical data | Snapshots fit well | Must manage versions/history | Usually fits well |
| Querying children independently | Can be hard or complex indexes | Easier via child index | Depends on need |
| Consistency across copies | No copies if embed-only | References the authority | Risk of stale snapshot |
| Read cost | Fewer round trips, BSON may be large | More round trips/`$lookup` | Balanced |
| Write cost | Document growth, multikey indexes | Multiple collections/indexes | Write amplification |
| Operations/migration | Large parent schema | Referential cleanup | Copy reconciliation |

### 10.1. The Table Has No "Best" Column

If a child has a lifecycle tied to the parent, is read with the parent, and has a bounded size, embedding often stands out. If the child is an ever-growing history/event stream, references usually fit better. Hybrid is especially useful when a **historical snapshot** differs from the **current source state**.

### 10.2. Duplicated Data Can Be Intentional

An order should keep `productNameAtPurchase` and `unitPriceAtPurchase` so historical invoices do not change when the catalog is edited. This is not necessarily a "data duplication bug"; it is a snapshot with different semantics from the current price.

## 11. Embedded Order Schema Example

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  customerId: "C-9",
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  status: "PAID",
  totalMinor: NumberLong(245000),
  items: [
    {
      productId: "SKU-A",
      nameAtPurchase: "Thermos Bottle",
      unitPriceMinor: NumberLong(125000),
      quantity: 1
    },
    {
      productId: "SKU-B",
      nameAtPurchase: "Stainless Steel Straw",
      unitPriceMinor: NumberLong(60000),
      quantity: 2
    }
  ],
  shippingAddressSnapshot: {
    country: "VN", city: "Ho Chi Minh City"
  }
}
~~~

The item snapshots are used in order history. The product catalog still has its own collection; editing catalog names/prices **must not** alter finalized invoice contents.

### 11.1. Atomic Boundary

An update to fields of **the same order document** is atomic. If checkout also deducts stock in `inventory` and writes a `payment ledger` in other documents, single-document atomicity on the order does not automatically cover them.

### 11.2. Document Limit

A BSON document is capped at 16 MiB. Do not embed unbounded auditEvents, comments, click streams, or large attachments. Set an upper bound on `items`/notes and monitor p95/p99 document size.

### 11.3. Hot Aggregate

If multiple workers continuously update the same order to append statuses and metrics, the document can become a contention point. You can separate append-only events while keeping a summary/index of the current state on the order.

## 12. Referenced and Hybrid Schema Examples

Referenced:

~~~javascript
// orders
{ _id: "O-1001", tenantId: "t-01", totalMinor: NumberLong(245000) }

// orderItems
{ _id: "OI-1", tenantId: "t-01", orderId: "O-1001", productId: "SKU-A",
  unitPriceMinor: NumberLong(125000), quantity: 1 }
~~~

Hybrid:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  totalMinor: NumberLong(245000),
  itemSummaries: [
    { productId: "SKU-A", nameAtPurchase: "Thermos Bottle",
      quantity: 1, unitPriceMinor: NumberLong(125000) }
  ]
}
~~~

### 12.1. Reference Integrity

MongoDB does not enforce a foreign key from `orderItems.orderId` to `orders._id` by default. Application logic, transactions, or reconciliation must verify orphaned children, tenant ownership, delete policies, and migrated data.

### 12.2. Hybrid Requires Clear Ownership

`product.name` is the authority for the current name, whereas `order.itemSummaries.nameAtPurchase` is a historical snapshot. When the two fields serve different semantics, there is no need to "sync them to one value"; conversely, if one is merely a cache of the same business value, an invalidation/update consistency policy is required.

## 13. Unbounded Arrays

Anti-pattern:

~~~javascript
{
  _id: "P-1",
  productName: "Product A",
  allComments: [
    /* 5 million comments and still growing */
  ]
}
~~~

Problems:

- Hitting the 16 MiB limit.
- Document growth and update contention.
- Reading product metadata may inadvertently load far too many comments.
- Multikey indexes and array updates carry overhead.
- Hard to paginate comments by time/author.

Better model:

~~~javascript
// products
{ _id: "P-1", name: "Product A", commentCount: 5000000 }

// comments
{ _id: ObjectId(), productId: "P-1", authorId: "C-3",
  createdAt: new Date(), body: "Helpful" }
~~~

Index comments on `productId + createdAt + _id` for pagination, and treat `commentCount` as a derived value with a clear update/reconciliation policy.

## 14. Atomic Document Updates and Consistency

If an invariant stays within a single document, prefer putting the condition into **the same atomic write**:

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1, reserved: 1 }
  }
);
~~~

If 2 requests compete for the last item, at most one operation can match when `available=1`. Check `matchedCount` and acknowledgement; do not read `available` on the client and then decrement in an unconditional command.

### 14.1. This Is Not the Entire Checkout Yet

If the reservation also needs to create an order and ledger in other collections, **multiple documents** must remain consistent per business rules. Use a transaction on a supported MongoDB topology or a reservation model/protocol with reconciliation, rather than expecting an atomic inventory update to cover everything.

### 14.2. Atomicity Is Not Idempotency

Two different requests competing for stock need an atomic conditional update. A single request **retried** after a timeout needs a stable request ID / unique ledger so it does not deduct twice. These are two distinct problems and can occur at the same time.

## 15. Modeling Business Invariants

Example:

~~~text
INV-1: inventory.available >= 0
INV-2: one (tenantId, requestId) produces at most one payment outcome
INV-3: orders.PAID must reconcile with a corresponding payment ledger entry
INV-4: a given seatId for an event has at most one ACTIVE booking
INV-5: tenantId of every dependent record must match its parent
INV-6: order snapshots are not altered by current catalog edits
~~~

### 15.1. Invariant → Mechanism Map

| Invariant | Boundary | Candidate Mechanism |
|---|---|---|
| Non-negative stock | Single inventory document | Atomic conditional update |
| No double request | Business key namespace | Unique index + idempotency ledger |
| Order + ledger commit together | Multiple documents | Transaction or protocol/resolution |
| Unique active seat | Multiple booking documents | Unique/partial unique index per semantics |
| Historical order snapshot | Order document | Immutable snapshot fields |
| Tenant isolation | All queries/writes | Auth-scoped filters, indexes, permissions |

### 15.2. Do Not Substitute Scoring for Invariants

If an "eventual order/payment sync" option allows a user to be shown PAID permanently without a ledger in an allowed state, that option has not achieved correctness. Fix the protocol or eliminate the candidate before the scoring table.

## 16. Consistency Trade-Offs by Operation

| Operation | Acceptable Stale Data? | What Must Writes Protect? | Design Direction |
|---|---|---|---|
| Catalog browse | Possibly a few seconds per policy | Product updates/version | Cached/materialized read model |
| View own checkout | Usually not after success | Authoritative order/payment outcome | Appropriate primary/session consistency |
| Product stock display | UI drift acceptable | No overselling at reservation time | Conditional write on authority |
| Payment ledger | Effect must never duplicate | Idempotency + durable commit | Unique request ID, reconcile |
| Activity feed | Can be eventual | Do not drop required events | Append-only + checkpoint |
| Financial report | Per clear cutoff/snapshot | Accurate totals at boundary | Snapshot/aggregation/export policy |

### 16.1. Stale Reads Do Not Always Cause Overselling

The UI may display stock=1 from cache when actual stock is already 0. If the reservation decision relies on an atomic predicate on the write authority, the second request is rejected. What must be avoided is letting the UI cache make the final decision.

### 16.2. "Strong Consistency" Needs Concrete Description

Do not use standalone labels like "strong"/"eventual". Specify **read-your-writes**, **monotonic reads**, **majority-acknowledged writes**, **atomic multi-document commit**, **snapshot at time T**, or **maximum staleness of N seconds** per use case.

## 17. Read Concern, Write Concern, and Read Preference

MongoDB provides distinct configuration mechanisms:

| Setting | Question | Trade-Off |
|---|---|---|
| Write concern `w:1` | Did the primary acknowledge the write? | Often lower latency; durability across failover must be understood |
| Write concern `majority` | Did enough majority members acknowledge per policy? | Can increase latency/dependency on replicas |
| Read concern `local` | Read data the node currently has | May observe non-majority-committed data |
| Read concern `majority` | Read majority-committed data per semantics | Does not create a snapshot across multiple HTTP requests |
| Read concern `snapshot` | Snapshot semantics in supported contexts | Additional resource/topology requirements |
| Read preference `primary` | Prefer the authoritative read path | Primary read load |
| Read preference `secondaryPreferred` | Offload some reads | Possible staleness/lag/failover behavior |

### 17.1. Do Not Equate Durability with Freshness

A majority-acknowledged write concerns acknowledgement/durability under replication semantics; it does not guarantee any arbitrary secondary immediately returns the new value. Read preference, session causal consistency, and read concern still need to be considered.

### 17.2. Do Not Promise System-Wide Linearizability

Read concern majority is not equivalent to linearizability for arbitrary multi-document operations. If the business requires a very strong property, specify the exact linearization/transaction/snapshot scope and test it against the deployment.

### 17.3. Selection Flowchart

~~~mermaid
flowchart TD
    Q["Read request"] --> CR{"Must immediately see the user's own write result?"}
    CR -->|"Yes"| Primary["Appropriate primary/session semantics"]
    CR -->|"No"| Stale{"Stale data allowed?"}
    Stale -->|"Yes"| Secondary["Secondary/cache/materialized view with lag budget"]
    Stale -->|"No"| Primary
    Primary --> Verify["Verify actual concern/SLO"]
    Secondary --> Verify
~~~

## 18. Optimistic Locking and Write Contention

Two editors concurrently modify an order from revision 4:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001", tenantId: "t-01", revision: NumberLong(4) },
  {
    $set: { status: "APPROVED" },
    $inc: { revision: NumberLong(1) }
  }
);
~~~

When one writer wins, the revision increments; the later writer using the old revision will not match. This is **compare-and-swap**. Spring Data MongoDB supports optimistic locking via `@Version` for version-aware operations, but raw drivers/bulk scripts must follow the same protocol to avoid stale overwrites.

### 18.1. Cost of Consistency

CAS reduces silent lost updates but increases conflict handling/retries when multiple writers target the same document. Do not turn conflicts into infinite retries; sometimes returning an HTTP conflict so the user reloads/merges is necessary.

### 18.2. Prefer Atomic Predicates for Simple Business Conditions

If you only need to deduct sufficient stock, a conditional `updateOne` is usually simpler than an application-level read–modify–write CAS loop. If a form must be edited based on a multi-field snapshot, version CAS is more appropriate.

## 19. Multi-Document Transactions: Trade-Offs

When a checkout must jointly:

1. Deduct stock.
2. Create an order.
3. Create a reservation ledger.

A transaction on a supported deployment can place the writes inside the same atomic commit. Trade-offs:

| Strengths | Trade-Offs |
|---|---|
| Atomic commit/abort of writes included in the transaction | Transaction lifetime/resource limits |
| Snapshot reads within the transaction scope | Complex retry/abort/write-conflict logic |
| Maintains multi-document consistency inside MongoDB | Contention and latency when writing multiple records |
| Easy to reason about all-or-nothing | Does not roll back external payment gateway/Kafka/email |

### 19.1. Snapshot Isolation Does Not Replace All Business Guards

A counting invariant spanning multiple documents can suffer **write skew** if transactions read the same snapshot and then write to different documents without a shared guard. Place the invariant in a contended document/unique index/guard, or use an appropriate serialization protocol.

### 19.2. Callbacks and Retries

Driver transaction helpers can retry the transaction body/commit based on error labels like `TransientTransactionError` or `UnknownTransactionCommitResult`. Callbacks must not invoke non-idempotent external side effects because they may re-execute; use outbox, stable IDs, and reconciliation.

### 19.3. When Is a Transaction Unnecessary?

A single-document atomic update suffices to protect an invariant involving no other documents. Do not use transactions for every CRUD operation by default "to be safe" if they increase latency/contention without adding correctness.

## 20. Consistency Decision Table

| Option | Atomic Scope | Read Freshness | Complexity | Best Fit |
|---|---|---|---|---|
| Single document + conditional update | Single document | Per read strategy | Low | Stock/counters/compact aggregates |
| Versioned CAS | Single document | Detects stale writes | Medium | User editing entities |
| Multi-document transaction | Multiple documents in deployment | Snapshot per semantics | Higher | Order + ledger committed together |
| Async denormalized projection | Each target write separately | Eventual | Medium–high | Search/catalog/report reads |
| Outbox/inbox + dedupe | Across async processes per protocol | Eventual with audit | Higher | Cross-service events/external effects |

Mechanisms are often **combined**, not mutually exclusive: for example, a transaction containing a conditional stock update and an idempotency ledger, followed by an outbox publishing events for cache updates.

## 21. Indexes Are a Read–Write–Storage Trade-Off

Indexes speed up queries, sorts, and covered queries under the right conditions. In return, every index consumes storage/cache, adds work on insert/update/delete, and increases maintenance, backup, and migration costs.

| Index Design | Benefit | Trade-Off |
|---|---|---|
| No matching index | Low storage/index maintenance | `COLLSCAN` or broad sort |
| Compound index matching query shape | More efficient reads/sorts | Optimizes only certain patterns |
| Many general-purpose indexes | Supports many filters | Write amplification, cache pressure |
| Partial index | Indexes useful subset | Query must match partial filter |
| Multikey index | Queries nested arrays | Many index entries and constraints |
| Unique index | Protects business identity | Can return duplicate-key errors |
| TTL index | Auto-deletes per expiration policy | Not instantaneous, not a replacement for archival |

### 21.1. Compound Index Aligned to Access Pattern

For Q5: tenant, customer, status, sorted newest first:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_customer_status_created" }
);
~~~

Equality prefix followed by sort fields is a sensible candidate for this query, **not** an optimal index for every other filter. When a query omits `customerId` or `status`, the index may not serve the sort as expected; measure with `explain`.

### 21.2. An Index Is Not Security by Itself

An index containing `tenantId` helps targeting/filtering, but does not replace the service deriving the tenant from the authentication context. A unique index on `(tenantId,requestId)` can serve as a hard correctness constraint for an idempotency ledger.

### 21.3. Which Indexes Are Not Worth Keeping?

Rarely used indexes that increase insert latency/IO/storage should be re-evaluated. Review usage statistics and have a rollout/rollback plan before dropping; do not delete based on a single low-traffic observation.

## 22. Using `explain("executionStats")` to Measure Reality

~~~javascript
db.orders.find(
  {
    tenantId: "t-01",
    customerId: "C-9",
    status: "PAID"
  },
  {
    orderNo: 1,
    totalMinor: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Examine:

- `nReturned`: number of records returned.
- `totalKeysExamined`: number of index entries scanned.
- `totalDocsExamined`: number of documents fetched.
- `winningPlan`: `IXSCAN`, `COLLSCAN`, `SORT`, `FETCH`, and stages depending on engine/version.
- Execution metrics: server-side work/time breakdown.

### 22.1. Do Not Benchmark Only the First Page

A query that is fast with 100 documents can become slow with 30 million orders, skewed tenants, cold caches, and concurrent clients. You need representative cardinality/selectivity, p95/p99, and peak load.

### 22.2. Covered Projection

When the filter/sort/projection matches an index, MongoDB can avoid fetching documents; adding an unindexed field or a large field to a DTO can alter performance.

### 22.3. Explain Does Not Cover HTTP

Request duration also includes connection pool wait, network, BSON mapping, JSON serialization, and upstream calls. Combine application tracing with MongoDB metrics/slow logs where permitted.

## 23. Pagination: Offset or Keyset?

Newest-first order list:

~~~javascript
db.orders.find({ tenantId: "t-01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(100000).limit(20);
~~~

Offset allows jumping directly to page N, but deep `skip` often scans many entries. Keyset resumes after the last sort key pair:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-01T10:00:00Z") } },
    {
      createdAt: ISODate("2026-11-01T10:00:00Z"),
      _id: { $lt: ObjectId("64b000000000000000000123") }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

This example uses a BSON ObjectId for `_id` with descending sort, requiring a matching index and token validation.

| Criterion | Offset | Keyset/Seek |
|---|---|---|
| Jump to page N | Easy | Hard without a bookmark |
| Deep pages | Cost can grow | Can seek via index |
| Inserts/deletes before boundary | Prone to duplicates/missing items | Less position shifting |
| API | Page number/size | Last sort keys/token |
| Total page count | Countable if needed | Not directly available |
| Dynamic sort | Simpler | Needs dedicated comparator/token |

### 23.1. Ordering Must Be Deterministic

`createdAt` can collide, so add a unique `_id` as a tie-breaker. Keyset still does not create a snapshot when sort fields change between requests.

### 23.2. Choose Based on the UI

An admin screen with 300 records jumping to page 7 can use offset. An activity feed with 300 million events using only "Load more" typically fits keyset.

## 24. `$lookup` and Aggregation: Avoiding Bias

A referenced model may require joins:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "orderItems",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  }
]);
~~~

### 24.1. Joins Are Not Slow by Default

Performance depends on the source set, foreign index, cardinality, document size, server version, sharding, and resource budgets. Having an index on `orderItems.orderId` and joining only 20 parents may well meet SLOs; lacking an index or having huge fan-out can be very expensive.

### 24.2. Place `$limit` with Correct Semantics

If you only need the 20 newest orders based on fields in `orders`, reducing the parent set before lookup makes sense. If filtering/sorting depends on joined fields, do not blindly move `$limit` before the join because it changes the result.

### 24.3. A Bad Model Cannot Be "Saved" by Long Pipelines

If every API call must perform multiple `$lookup`/`$unwind` stages and burn network/compute, consider bounded embedding or a materialized read model—while accounting for the cost of synchronizing copies.

## 25. Materialized Views and Denormalization

~~~text
Authoritative orders / events
    → CDC/outbox/batch
        → productStats read collection
            → dashboard API
~~~

An aggregated record:

~~~javascript
{
  _id: "t-01:SKU-A",
  tenantId: "t-01",
  productId: "SKU-A",
  paidOrderCount: NumberLong(184200),
  refreshedAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

### 25.1. Benefits

Precomputes data for fast reads and avoids repeated aggregations. Well suited for dashboards, product popularity, search ranking, or read-heavy APIs.

### 25.2. Trade-Offs

You must operate pipelines, checkpoints/replays, drift reconciliation, delete handling, and lag SLAs. If the view serves analytics, brief staleness may be acceptable; never use asynchronously derived numbers as an authoritative payment ledger.

### 25.3. Write Amplification

One order update can trigger updates to `customerSummary`, `productStats`, the search index, and notifications. Evaluate total downstream writes and failure recovery, not just final read speed.

## 26. Caching: Fewer Reads, Larger Consistency Surface

| Cache | Benefit | Risk |
|---|---|---|
| Product detail | Reduces hot reads | Stale price/name |
| Search results | Reduces aggregation | Invalidation when filters change |
| User order summary | Reduces repeated queries | Read-your-writes may break |
| Payment response | Fast retry response | Does not replace durable ledger |

### 26.1. TTL Aligned with Business Contract

Product descriptions may be stale briefly; displayed stock can lag slightly as long as checkout still uses an atomic predicate. Never let a cache make the final inventory/payment decision.

### 26.2. Cache Invalidation Is a Real Cost

A MongoDB write succeeding while Redis is not yet invalidated can cause the UI to show old data. Use event-based invalidation, versioned keys, or short TTLs per SLO; measure stale-read violations.

### 26.3. Avoid Cache Stampede

Thousands of requests hitting an expired key at once can flood MongoDB. Use request coalescing, TTL jitter, bounded retries, and circuit breakers.

## 27. Sharding: Scaling Out or Adding Complexity?

Replica sets primarily provide high availability/replication; **sharding** partitions data and workload across shards. The two mechanisms are not synonymous.

| Sharding Benefit | Corresponding Cost |
|---|---|
| Splits storage/throughput | Choosing shard keys and monitoring skew |
| Targets queries to fewer shards | Queries missing the key may scatter-gather |
| Distributes writes | Hot shards if key distribution is poor |
| Scales with shard count | Balancer/chunk migration/resharding operations |
| Data larger than a single node's limits | Cross-shard aggregation/transaction costs |

### 27.1. Shard Keys Must Follow Access Patterns

If queries mostly include `tenantId`, a shard key supporting tenant targeting can help. However, a mega-tenant generating most of the writes can still run hot if the same key value targets only part of the cluster.

### 27.2. Ranged vs. Hashed

Ranged favors range locality but can overheat the upper end of the range under monotonic writes. Hashed can distribute key values, but alters range-query behavior. Check query shapes, cardinality, shard distribution, and hot-key risk.

### 27.3. Sharding Does Not Automatically Fix Deep Offset

Deep `skip` through `mongos` can still perform work across multiple shards before merging. Indexes, targeting, and keyset pagination still need evaluation.

## 28. Shard Key Evaluation Matrix

| Criterion | Question |
|---|---|
| Cardinality | Are there enough unique values? |
| Skew | Are there mega-tenants/hot keys? |
| Query targeting | Do critical APIs include the key predicate? |
| Time growth | Do inserts pile onto one end of the range? |
| Mutable key | Does the domain change the key frequently? |
| Unique indexes | Are constraints compatible with sharding? |
| Joins/aggregations | Is scatter-gather frequent? |
| Resharding | Is there a plan/cost if the workload shifts? |

For example, sharding solely by tenant may be easy to reason about for thousands of small tenants, but when one tenant accounts for 70% of traffic, you need to evaluate tenant+bucket partitioning or separate zoning/tiers. Do not randomly add a bucket suffix while forgetting to update query routing and global tenant invariants.

## 29. Multi-Tenancy and Noisy Neighbors

| Organization Approach | Strengths | Costs |
|---|---|---|
| Shared collection + tenantId | Few namespaces, centralized ops | Tenant scope mandatory on every query |
| Collection per tenant | Easy namespace-level separation | Many indexes/migrations |
| Database per tenant | Role/management separation at DB level | Complex backup and lifecycle |
| Cluster per tenant/tier | Stronger capacity isolation | High cost/provisioning |

### 29.1. Tenant Scope Is a Hard Constraint

`tenantId` must come from the authentication context. Do not filter by tenant in the application after scanning a broad collection; that wastes resources and risks data leaks.

### 29.2. Noisy Neighbors

One large tenant can monopolize index cache, CPU, or connection pools, degrading p99 for other tenants. Rate limits/quotas/dedicated tiers belong in the trade-off matrix.

## 30. Hot Documents and Contention

A single `inventory:SKU-HOT` document may receive thousands of concurrent updates. Single-document atomicity protects the invariant but does not eliminate contention.

- Atomic conditional stock updates are domain-correct, yet p99 may spike when requests contend on the same key.
- CAS must handle optimistic conflicts, retry budgets, and backoff.
- A sharded counter can raise throughput, yet **does not automatically enforce a strict global limit**.
- Queues/serialized reservations can reduce contention if SLAs allow.
- If a global invariant must hold, design a shared guard or corresponding transactional protocol.

### 30.1. Choose Correctness Before Throughput

Do not split a quota of 100 into 10 unguarded counters without reconciliation and then claim it is guaranteed not to oversell past 100. Invariants must be proven under concurrency.

### 30.2. Measure Tail Latency

A 20 ms average with a 2 s p99 may miss the checkout SLO. Collect success/rejection counts, conflicts, retry attempts, aborts, CPU, and pool wait metrics per hot key.

## 31. BSON Size and Write Amplification

When embedding a lot of data:

- What are the p50/p95/p99 document byte sizes?
- Are there unbounded child arrays?
- Do reads typically use projections only?
- Do independent child updates turn the parent into a hot document?
- Do multikey indexes significantly increase entry counts?
- Can audit logs/comments/events be moved to a separate collection?

### 31.1. Measuring Size

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $project: { bytes: { $bsonSize: "$$ROOT" } } },
  {
    $group: {
      _id: null,
      count: { $sum: 1 },
      avgBytes: { $avg: "$bytes" },
      maxBytes: { $max: "$bytes" }
    }
  }
]);
~~~

This query can be resource-intensive on large datasets; run it in a lab/sample or with appropriate capacity. The 16 MiB limit is **not** a target to design documents right up against 16 MiB.

## 32. Retention, TTL, and Archival

| Data Type | Policy | Candidate Model |
|---|---|---|
| Active order | Low latency, transactional | Hot operational collection |
| Order history | Long-term audit, rarely read | Cold/archive tier or collection |
| Session | Expiration | TTL index per policy |
| Activity event | Append-only, very large | Time-based partition/archive |
| Payment ledger | Strict retention | Durable immutable-ish records/audit |
| Derived stats | Rebuildable | Materialized views + rebuild plan |

### 32.1. TTL Is Not Archival

A TTL index deletes documents via a background process and does not guarantee millisecond precision. It **does not copy data to archive storage** and should not serve as the mechanism to enforce exact transaction deadlines.

### 32.2. Legal Hold and Retention

If compliance requires retaining a record longer, do not use a plain TTL without accounting for legal holds. Cleanup, restore, and backup processes must preserve retention requirements per policy.

## 33. Backup and Disaster Recovery Are Also Part of Data Design

A model with great p99 latency that cannot be restored within the RTO may be unsuitable for critical data.

Questions to record in the matrix:

1. Are backups and Point-in-Time Recovery available for the target deployment?
2. Has an actual restore been tested? How long until the app is operational?
3. Can index definitions, validators, roles, and necessary secrets be recovered?
4. Does recovering one tenant require affecting the entire cluster?
5. Are there external side effects in payments/email/Kafka requiring reconciliation after restore?
6. How much do retention, backup copies, and cross-region egress cost?

### 33.1. RPO and RTO Are Requirements

RPO is the amount of data that can be lost under recovery objectives; RTO is the recovery time. An RPO of 0 for acknowledged payments **cannot** be achieved solely with backups every 15 minutes.

### 33.2. Restore Drills

Run restores in an isolated environment, checking counts, keys, schema metadata, monetary totals, and the idempotency ledger. A "backup successful" dashboard does not prove restores work properly.

### 33.3. MongoDB and External Systems

Restoring a database to before a successful payment gateway charge can desynchronize payment state. You need reconciliation, durable business IDs, and a protocol for handling uncertain outcomes.

## 34. Schema Evolution and Reversibility

A major change should be broken into phases:

~~~text
EXPAND readers and schema compatibility
  → BACKFILL old data, CDC/reconcile
  → SHADOW and CANARY reads
  → WRITE CUTOVER with fencing/watermark
  → STABILIZE with rollback window
  → CONTRACT old fields and collections
~~~

### 34.1. Why Migrations Affect the Scoring Table

An embedded one-document model may be easy to update in one shot, yet hard to reshape nested structures when documents are large; a referenced model may require multi-collection migrations and integrity repairs; hybrid requires reconciling snapshots/projections. Evaluate the **cost of future changes**, not only initial creation design.

### 34.2. Big-Bang Is Sometimes Right

A small internal app with a maintenance window and a 10,000-record dataset may suit a well-rehearsed offline migration. Using change streams/dual writes for every change can add risk without adding value.

### 34.3. Rollback Can Lose Information

If the new schema introduces a state unrepresentable in the old schema, reverse mapping is lossy. You need compatibility extensions, a feature freeze during the rollback window, or a forward-fix policy.

## 35. Security and Compliance Are Hard Constraints

Never choose a faster schema if it violates:

- Tenant isolation/authorization for reads, writes, and aggregations.
- Retention, legal hold, regional residency, or encryption policies.
- Data minimization and PII redaction in logs, backups, exports, and CDC.
- Auditability for financial/identity changes.
- Separation of duties for production writes and data migrations.

### 35.1. Encryption Can Change Query Capabilities

Application/field-level encryption can affect sorting, filtering, and indexing depending on the chosen technique. Verify query compatibility before finalizing encryption rather than discovering after rollout that a critical query is no longer supported.

### 35.2. Query Isolation Differs from Infrastructure Isolation

Shared collection + `tenantId` filter provides logical isolation. Dedicated clusters for key tenants increase capacity/operational isolation at higher cost. Choose according to SLA/compliance/threat model instead of equating the two tiers.

## 36. Quantifying Operational Complexity

| Metric | Measurement / Hint |
|---|---|
| Services writing an aggregate | Ownership map and code inventory |
| Number of collections/indexes | Index storage, migration scripts |
| Number of background pipelines | CDC, outbox, cache invalidation, rebuild jobs |
| Retry/abort/conflict rates | APM metrics, transaction/optimistic counters |
| Restore duration | Recovery rehearsal |
| Incident frequency/MTTR | On-call runbooks and tickets |
| Deploy phases/rollback steps | Release plan, number of gates |
| Data needing reconciliation | Mismatch count, repair backlog |
| Human cost | On-call and maintenance effort |

### 36.1. A Fast Read Model Still Has Its Own Workers

A materialized view that makes GET requests fast may require an event-consuming service, checkpoint store, dead-letter queue, replays, alerts, and reconciliation. Do not score operations 5/5 just because the GET query is simple.

### 36.2. Ownership and Rebuild Mechanisms

Every derived collection needs an owner, freshness SLO, rebuild procedure, and data provenance. Lacking a rebuild runbook is an operational risk even when queries are currently very fast.

## 37. Availability and Failover

Replica sets provide high availability, yet during a primary election the application may experience transient errors, server selection timeouts, and uncertain commit outcomes.

### 37.1. Read Paths Can Be Stale

Secondary reads offload use cases that tolerate lag, but do not automatically satisfy newly committed confirmation reads. Read preference/concern, session causal consistency, and the staleness contract must be evaluated.

### 37.2. Retryable Writes Do Not Replace Idempotency

The MongoDB driver supports retryable writes on eligible operations/topologies, but a client retrying an **entire HTTP request** can create a new logical operation. Use stable business request IDs, a unique ledger, and reconciliation for payments/reservations.

### 37.3. Fault Tests Are Design Inputs

Test failovers, network timeouts, pool exhaustion, transaction conflicts, secondary lag, and restores on a compatible test topology. Observe both p99 latency and business invariants after retries.

## 38. Current Capacity and Growth

An illustrative forecast:

| Item | Current | After 12 Months | Risk to Monitor |
|---|---:|---:|---|
| Orders | 30 million | 80 million | Index/backup growth |
| Activity events | 300 million | 1.2 billion | Retention and working set |
| Peak checkout writes/s | 300 | 1,000 | Hot SKUs/transactions |
| Peak catalog reads/s | 6,000 | 20,000 | Cache misses/index CPU |
| Largest tenant | 15% traffic | 35% traffic | Hot shard/noisy neighbor |

These are illustrative, not benchmark measurements. Growth does not always scale linearly with node count; hot keys, index cache, retries, and scatter-gather create non-linear bottlenecks.

### 38.1. Headroom

Reserve capacity headroom for campaign spikes, failovers, index builds, backups, and migrations. If the entire cluster hits 95% CPU in a short benchmark, incident resilience is likely too low.

### 38.2. Workload Mix

Measure read/write ratios, request size distributions, status filter selectivity, and peak bursts. A 100%-read synthetic benchmark does not reflect contention during checkout bursts.

## 39. Minimalist Cost Model

Total cost should consider:

\[
\text{TotalCost}
= \text{Compute}+\text{Storage}+\text{Backup}
+\text{Network}+\text{Operations}
\]

| Component | Cost Examples |
|---|---|
| Compute | Replica/shard nodes, CPU/RAM, peak scaling |
| Storage | Documents, indexes, oplog, replication, compression |
| Backup | Retention, PITR snapshots, restore storage |
| Network | Cross-region reads/CDC, `$lookup`, large BSON payloads |
| Operations | Alerting, migrations, incidents, staff/on-call |

### 39.1. Write Amplification

Hybrid snapshots and materialized views create multiple copies/updates. One business write can fan out to `orders`, `productStats`, search, and analytics. Estimate total bytes/writes, latency, and pipeline costs.

### 39.2. Do Not Cut Costs by Dropping Durability

If missing backups/replication causes RPO/RTO failures, the option is disqualified before comparing price. Lower cost does not compensate for lost monetary records.

## 40. Qualitative Matrix for Three Order Model Options

Three candidates:

- **A — All-in-one embedding:** parent order contains items, shipping snapshot, and the **entire** unbounded audit history.
- **B — Fully referenced:** `orders`, `orderItems`, `auditEvents`, and catalog references; the application performs appropriate joins/queries.
- **C — Hybrid:** order contains **bounded** item/shipping snapshots; audit events and catalog stay separate, with an invariant protocol for checkout.

| Criterion | A — Embedded All | B — References | C — Hybrid |
|---|---|---|---|
| Order detail read | One document, potentially huge | Multiple queries/join | Compact snapshot, single read |
| Item update | Simple within parent | Independent children | Order snapshot immutable |
| Audit growth | 16 MiB/hot array risk | Appended separately | Appended separately |
| Atomic order fields | Single document | Boundary must be defined | Bounded order atomic |
| Reference integrity | Few intra-order links | Needs orphan checks | Needs catalog ref validation |
| Inventory/payment correctness | Still needs cross-doc protocol | Still needed | Still needed |
| Index/query performance | Large parent payload when history grows | Many indexes/joins | UI read optimized via snapshot |
| Migration | Large nested docs | Multi-collection changes | Snapshot + derived data policy |
| Operations | Fewer collections, higher risk at scale | Integrity cleanup | Projection/CDC if copied |
| Scale growth | Hard with unbounded histories | Independent child growth | Bounded aggregate |

### 40.1. Hard Gate Before Scoring

A is **rejected in the unbounded audit history example** because it triggers growth/16 MiB risks. Do not give A a high read-performance score and use it to offset a hard-limit violation. B and C must still prove their inventory/payment transaction/idempotency protocol rather than claiming high consistency merely from embedding or referencing.

### 40.2. Results Depend on the Workload

If orders always have at most 3 items and no audit history, A (bounded embedding) can be a very sound choice. The matrix does not conclude "hybrid is always best"; it concludes that **for the stated workload assumptions**, A is no longer valid.

## 41. Weighted Scoring Matrix

After eliminating options that fail hard gates, the team may use a 1–5 scale, where **5 represents stronger fit**. Assume these weights:

| Criterion | Weight |
|---|---:|
| Model/growth fit | 20% |
| Consistency/correctness when fully implemented | 30% |
| Read performance | 20% |
| Write performance | 15% |
| Operations/migration | 15% |
| **Total** | **100%** |

The scores below are **team discussion estimates**, not benchmarks; the consistency column assumes each option already includes a valid protocol to satisfy hard invariants.

| Option | Model 20% | Consistency 30% | Read 20% | Write 15% | Ops 15% | Total / 5 |
|---|---:|---:|---:|---:|---:|---:|
| A (all embedded, rejected by hard gate) | 3 | 4 | 5 | 2 | 3 | 3.55 |
| B (references) | 5 | 4 | 2 | 4 | 4 | 3.80 |
| C (hybrid) | 4 | 5 | 4 | 3 | 2 | 3.85 |

Calculation example for B:

\[
S_B = 0.20(5)+0.30(4)+0.20(2)+0.15(4)+0.15(4)=3.80
\]

Calculation example for C:

\[
S_C = 0.20(4)+0.30(5)+0.20(4)+0.15(3)+0.15(2)=3.85
\]

### 41.1. A 0.05 Difference Does Not Prove C Wins

Subjective scoring error can easily exceed 0.05. In a real decision, B and C require prototyping, benchmarking, and sensitivity analysis rather than claiming C is "1.3% better" as definitive proof.

### 41.2. Do Not Double-Count Consistency Semantics

If a candidate violates a business invariant, it is disqualified. The consistency score in the matrix only evaluates **the difficulty and confidence of the mechanism achieving the invariant**, never trading invariants away for read/ops points.

### 41.3. Weights Must Be Approved by Accountable Stakeholders

For a read-heavy feed, read performance may carry high weight. For a payment ledger, correctness/audit and durability are top priorities. Do not apply a single weight set across all endpoints.

## 42. Sensitivity Analysis: What If Weights Change?

Suppose the team worries about operating hybrid pipelines and increases the Ops weight. Instead of changing one weight so the sum exceeds 100%, **re-normalize all weights** and recalculate. If B overtakes C as the operations weight rises, the conclusion depends on operational priorities.

### 42.1. Scores Are Decision Models, Not Benchmarks

A 4/5 in write performance should be backed by QPS, p99, write amplification, and conflict/retry rates. If unmeasured, tag it **estimate/low confidence**, not as fact.

### 42.2. Apply Robustness Checks

Ask: if every estimated score shifts by ±1, does the chosen option still win? If not, gather more measurements or choose a simpler/more reversible option instead of accepting a fragile outcome.

### 42.3. Risks Without Exact Frequencies

Assessing impact and likelihood is helpful, yet risk scores do not automatically become true probabilities. Back them up with failure modes, historical incidents, tests, and runbooks.

## 43. A Complete Trade-Off Matrix Requires Evidence

| Criterion | Evidence Required for the Decision |
|---|---|
| Order detail latency | p95/p99 with representative payload/traffic |
| Checkout throughput | Accepted writes/s, stock invariants, retries |
| Query efficiency | Explain `totalKeysExamined`/`totalDocsExamined` |
| Storage growth | BSON size p95/p99, index bytes, archive plan |
| Consistency | Concurrency/transaction/fault-injection results |
| Migration | Expand/backfill/cutover rollback rehearsal |
| Availability | Failover and recovery tests |
| Ops | Number of pipelines, alert coverage, MTTR |
| Cost | Forecast nodes/storage/network/on-call |

### 43.1. Attach Confidence Levels to Each Cell

Example:

~~~text
Read latency C: 90 ms p95 — MEASURED, 10 million orders, warm cache
Write latency B: 75 ms p95 — ESTIMATED, not benchmarked
Rollback complexity C: HIGH — VERIFIED in staging drill
~~~

Never compare a measured number with an estimate as if they carry equal weight; add a confidence column and a plan to collect missing data.

### 43.2. Production Data Has Skewed Distributions

A uniform benchmark across 10,000 tenants may misrepresent production when 30% of traffic belongs to one tenant. Run skewed/hot-key workloads based on observed traffic.

## 44. Case Study A: Checkout and Inventory

**Hard invariants:**

~~~text
stock.available >= 0
one (tenantId,requestId) => at most one business effect
confirmed order must have consistent reservation/ledger
no double charge for a retry of the same payment request
~~~

**Candidates:**

- A: single `orders` collection, reads stock then writes order without conditional update → **rejected**, oversells.
- B: conditional stock update, separate order creation without transaction/reconciliation → risks partial success, must be fixed.
- C: conditional stock update plus order/ledger inside a MongoDB transaction using an idempotency key; external payment via provider idempotency/outbox → viable candidate if the topology and business process support it.

### 44.1. Atomic Predicate

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  { $inc: { available: -1, reserved: 1 } }
);
~~~

The condition lives inside the write, avoiding a check-then-act race. If the order/ledger must also be atomic, place them in an appropriate transaction/protocol; handle transient conflicts and unknown outcomes.

### 44.2. Idempotency

~~~javascript
db.requestLedger.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uniq_tenant_request" }
);
~~~

Client retries with the same request ID must not create a new effect. External payment gateways do not roll back automatically with a MongoDB transaction; use idempotent provider keys, reconciliation, and domain workflows.

### 44.3. Metrics to Verify

Checkout p95/p99, accepted/rejected requests, negative stock count, duplicate ledger count, transaction abort/retry rate, and payment reconciliation backlog. A test measuring only p95 without checking stock invariants is insufficient.

## 45. Case Study B: Read-Heavy Catalog

**Requirements:** 90%+ of operations are reads; products have images/names/categories; prices change by campaign; UI needs filtering by category/brand and sorting by popularity. Search result lag is acceptable per policy.

**Options:**

1. Embed all comments and inventory into `product` → huge documents, many writers/hot fields; reject the unbounded parts.
2. Product document for core metadata; separate comments, separate inventory, separate search/read model.
3. Cache product summary with TTL/invalidation; checkout still reads authoritative price/stock snapshots per policy.

### 45.1. Mini Matrix

| Axis | Core Product + References/Cache |
|---|---|
| Model | Bounded document, external comments |
| Consistency | Eventual for UI; authoritative for checkout |
| Read performance | Compound indexes/cache/search projection |
| Write performance | Independent price/inventory update paths |
| Ops | Cache invalidation, projection rebuild, index management |

### 45.2. Critical Tests

During campaign price changes, GET requests may serve stale cache, yet checkout must enforce the pricing policy (pre-confirmation snapshot, version/validation). Never let a cached price decide the charge without an explicit policy.

## 46. Case Study C: Activity Feed and Audit

**Requirements:** append-only events totaling hundreds of millions of records, queried by tenant/actor/time, deep pagination, retention policies; mandatory audit records must not be deleted early.

**Commonly Suitable Approach:**

- Separate events collection rather than embedding everything in user/order documents.
- Stable event ID, `eventTime`, and tenant ID.
- Indexes aligned to access patterns; consider partitioning/sharding when needed.
- Keyset pagination and retention-based archival/cold tier.
- Outbox/idempotent consumer if events originate from business transactions.

### 46.1. Mini Matrix

| Axis | Event Collection + Keyset |
|---|---|
| Model | Append-only, independent child growth |
| Consistency | Eventual reads if contract allows |
| Read performance | Keyset and targeted indexes |
| Write performance | Avoids hot parent array |
| Ops | Retention, archive, replay, backup |

### 46.2. Audit Differs from Entertainment Feeds

Audit data must preserve integrity/retention; UI feeds can use more aggressive caching/archival. Do not share a single TTL between both if one must be retained for multiple years.

## 47. Architecture Decision Record (ADR)

An ADR can be written as:

~~~markdown
# ADR-012: Select Bounded Hybrid Order Model

Status: Accepted (after benchmarks and review)

Context:
- 30M orders, bursty checkout, orders typically have <= 20 items
- Audit history can grow without bound
- No double charge and non-negative stock are hard constraints

Options:
- A: embed everything (rejected: unbounded audit)
- B: full references
- C: bounded order snapshot + separate audit (selected)

Decision:
- Embed purchase-time snapshots in order
- Store audit events in a separate collection
- Conditional inventory update + transaction/ledger when required
- Maintain indexes per Q1-Q8, monitor hot keys

Evidence:
- Link to internal benchmark/result artifacts
- Concurrent correctness tests, query explain plans, restore drill

Risks:
- Extra operational cost for audit and outbox
- Requires reconciliation and schema migration/backfill

Review triggers:
- p99 latency exceeds SLO
- p99 order document size increases sharply
- Item cardinality changes
- Cost or traffic mix shifts
~~~

This is an ADR template for the team to populate with **real measured data**. Do not mark "Accepted" based on illustrative scoring tables before proving hard gates and measurements.

## 48. Validation Plan Must Map to Every Axis

| Axis | Tests |
|---|---|
| Model | Max cardinality/size, schema variations, migrations |
| Consistency | Race tests, idempotency, failover, snapshot boundaries |
| Read performance | Query plans, projections, p95/p99 under load |
| Write performance | Burst QPS, hot-key contention, retries/aborts |
| Operational | Backup/restore, old/new deployment, rollback drill |
| Security | Tenant isolation, privileges, redaction/encryption |

### 48.1. Do Not Test with Mocks and Conclude MongoDB Semantics

A mock repository can exercise service branches, yet it does not prove server unique indexes, transactions, or atomic updates. Integration tests must run against a real MongoDB test deployment matching the target topology.

### 48.2. Fault Injection

Post-commit network timeouts, replica elections, connection pool pressure, and CDC worker crashes can affect data and latency. Test uncertain outcomes and business reconciliation, not just happy-path requests.

## 49. Benchmark Design

A meaningful benchmark must enforce:

1. **Identical workload/result definitions** between options B and C.
2. Sufficiently large dataset with representative cardinality skew and size distributions.
3. Clear separation between warm and cold cache runs.
4. Concurrency and request mixes exhibiting production-like bursts.
5. Recorded index definitions and `explain` plans for critical queries.
6. Measurement of p50/p95/p99, throughput, errors, conflicts, retries, and CPU/IO/RAM/network.
7. Comparison of total cost/write amplification, not just a single GET endpoint.
8. Verification of final business invariants after load.

### 49.1. Benchmarks Alone Do Not Decide the Model

Option B might be faster on a detail query over a small dataset, whereas C behaves more predictably under customer-specific traffic/large orders. A short benchmark cannot predict restore time, migration risk, or on-call cost.

### 49.2. Do Not Compare Mismatched Projections

If B returns only the order header while C returns all 20 items, comparing latency directly is unfair. Both must return **the same logical response** under the same consistency policy.

## 50. Experiment Results Table to Record

A template populated by the team with real numbers:

| Workload | B p95 | C p95 | SLO | Result |
|---|---:|---:|---:|---|
| Q4 order detail | TBD | TBD | Per API | Not measured |
| Q5 list 20 orders | TBD | TBD | Per API | Not measured |
| Checkout burst | TBD | TBD | Per API | Not measured |
| Audit append | TBD | TBD | Per pipeline | Not measured |
| Restore 80M orders | TBD | TBD | Per RTO | Not rehearsed |

Do not fill measured columns with invented numbers. When evidence is missing, the table should show `TBD`/low confidence to create a **concrete action item** rather than creating an illusion of an evidence-backed decision.

## 51. Data Modeling Decision Tree

~~~mermaid
flowchart TD
    Relationship["Parent/child data"] --> Bounded{"Is child cardinality bounded with lifecycle tied to parent?"}
    Bounded -->|"Yes"| ReadTogether{"Are parent+child usually read together?"}
    Bounded -->|"No"| Reference["Reference or separate collection"]
    ReadTogether -->|"Yes"| Embed["Bounded embedding candidate"]
    ReadTogether -->|"No"| Reference
    Embed --> Shared{"Is child shared or updated independently in many places?"}
    Shared -->|"Yes"| Hybrid["Hybrid snapshot + reference"]
    Shared -->|"No"| Guard["Check BSON size/hot writes/invariants"]
    Guard --> Decision["Measure queries/consistency/operations"]
    Hybrid --> Decision
    Reference --> Decision
~~~

### 51.1. Do Not Decide from a Flowchart While Ignoring the Workload

A decision tree generates **candidates**, not final decisions. A bounded child can still be huge; a reference join can still be fast with proper indexes and small parent counts.

### 51.2. Surface Atomicity Early

If parent and child must be modified together to protect an invariant, embedding helps when size and lifecycle permit. If embedding is not feasible, evaluate transactions or redesign the protocol; never drop an invariant just to save a query.

## 52. Consistency Decision Tree

~~~mermaid
flowchart TD
    I["Business write"] --> One{"Invariant within one document?"}
    One -->|"Yes"| Atomic["Atomic update + predicate / CAS"]
    One -->|"No"| Multi{"Within same MongoDB deployment supporting transactions?"}
    Multi -->|"Yes"| Tx["Transaction + constraints + retries"]
    Multi -->|"No"| Saga["Idempotency / outbox / reconciliation"]
    Atomic --> External{"Any external side effects?"}
    Tx --> External
    Saga --> External
    External -->|"Yes"| Idem["Stable business ID + provider idempotency + recovery"]
    External -->|"No"| Verify["Verify business invariants"]
    Idem --> Verify
~~~

### 52.1. Do Not Choose Transactions Just Because Relations Exist

An order references a product, yet does not update the product when the order changes; you do not automatically need a transaction merely to read two collections. Transactions are chosen when a **business operation requires atomic multi-document changes**.

### 52.2. Write Skew

If two transactions read a count across multiple documents and then write to two separate documents, snapshot isolation does not always protect a global invariant. You need a unique index, a guard document, or a shared serialization pattern per use case.

## 53. Summary of Hard Gates for Decisions

Every candidate must pass these checks:

| Gate | Question |
|---|---|
| Business correctness | Impossible to oversell, double charge, or lose confirmed orders? |
| Security | Are tenant ownership and PII policies enforced? |
| Data bound | No unbounded array/document growing toward limits? |
| Durability | Meets write acknowledgement, RPO, and restore requirements? |
| Compatibility | Do reader/writer versions have a migration path? |
| Operability | Are backups, monitoring, runbooks, and owners in place? |
| SLO | Is there a plausible path to meet p95/p99 and throughput? |

If a gate fails, **fix the option or eliminate it**—never compensate with other scores. Some gates require benchmarks or proof before concluding; "unverified" does not mean PASS.

## 54. Techniques to Avoid Biased Scoring

Common biases in reviews:

- **Confirmation bias:** favoring embedding beforehand and benchmarking only single-document reads.
- **Metric cherry-picking:** looking only at p50 while ignoring p99/conflicts.
- **Survivorship bias:** omitting timed-out or retried requests.
- **Unknowns treated as zero risk:** treating missing evidence as "simple operations".
- **Double-counting:** rewarding the same benefit twice under both modeling and performance.
- **Sunk cost:** keeping an old design merely because a month was invested even though a hard gate fails.

### 54.1. Independent Review

Have consistency owners, DBA/operations, and the application team score independently before discussing. Use identical workload/spec/weight definitions and document score divergences.

### 54.2. Track Confidence

Every assessment carries `MEASURED`, `PROTOTYPED`, `ESTIMATED`, or `UNKNOWN`. Low-confidence cells form the experiment backlog rather than being masked behind a 4/5 score.

## 55. When Should a Decision Be Revisited?

A schema that fits today can become problematic in 18 months. Review triggers:

1. API p99 breaches the SLO across multiple representative periods.
2. Document p95/p99 size rises sharply.
3. Item/comment/event counts diverge from assumptions.
4. New tenant skew or hot-key contention emerges.
5. New product features require different queries/transactions.
6. Index/backup/restore costs exceed budget.
7. RPO/RTO/compliance requirements change.
8. CDC lag or reconciliation incidents rise.
9. Migrations drag on or rollouts frequently require rollback.

### 55.1. Design for Changeability

Prefer stable IDs, versioned schemas, bounded arrays, clear ownership, and backfill/reconciliation capability when needed. This reduces future risk, rather than merely being "clean architecture".

## 56. Practice Exercise A — Building an Access-Pattern Matrix

A clinic booking app has `patients`, `doctors`, `appointments`, and `auditEvents`. Write at least 5 query shapes, including:

- Finding a patient's appointments within 30 days.
- Viewing a doctor's schedule by day.
- Booking an open slot that has no active booking.
- Viewing an appointment's change history.
- Summarizing appointment counts per doctor.

For each query, specify filters, sort, projection, frequency, data size, and consistency requirement. Then propose indexes (without assuming they are already optimal).

## 57. Practice Exercise B — Embedding or Reference?

A product has 5 static attributes, at most 10 images, and 2 million comments over time. Choose where to store images and comments, explaining via cardinality, read patterns, size bounds, ownership, and query pagination. What changes if the images are large binary files?

## 58. Practice Exercise C — Immutable Order Snapshot

A customer orders at 125,000 VND. The next day the catalog updates the price to 130,000 VND and renames the product. Design fields in `orders.items` and `products` so historical invoices remain unchanged while the catalog still reads the current name and price.

## 59. Practice Exercise D — Two Requests Competing for Stock

Initial stock=1. Two qty=1 requests arrive concurrently. Write the conditional MongoDB atomic update and expected outcomes. If order and ledger records must also be created in other collections, describe the transaction/reconciliation boundary.

## 60. Practice Exercise E — Consistency Table

Given three paths:

1. A user has just paid and wants to view the confirmation.
2. The homepage displays 20 featured products.
3. A BI report calculates last month's total revenue.

Choose an appropriate stale-read budget, read preference/concern, or snapshot/cutoff strategy, and explain why **not** to apply one uniform policy to all three.

## 61. Practice Exercise F — Index Trade-Off

Given the query:

~~~javascript
db.orders.find(
  { tenantId: "t-01", customerId: "C-9", status: "PAID" }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Propose a compound index, then describe how to inspect the explain results. If the application also filters solely by tenant with the same sort, why might the initial candidate index fall short?

## 62. Practice Exercise G — Bounded Arrays and Hot Documents

A `customer` document embeds an array of all 1 million transactions and 300 workers append concurrently. Identify at least four problems. Choose an alternative design and specify the query to list transactions with keyset pagination.

## 63. Practice Exercise H — Multi-Tenant Sharding

A cluster has 2,000 tenants; the largest tenant generates 40% of writes. Evaluate a `tenantId` shard key, compound/partitioned shard key options, and the impact on tenant-scoped queries. Do not assume a hashed tenant key eliminates a hot tenant.

## 64. Practice Exercise I — Materialized View

A dashboard requires the top-10 products over 7 days, with a maximum refresh lag of 60 seconds. Design the source events, derived collection, update worker, checkpoint/idempotency, and rebuild procedure if data drifts. Define monitoring for lag and mismatches.

## 65. Practice Exercise J — Computing Weighted Scores

Using weights `20% model, 30% consistency, 20% read, 15% write, 15% ops` and the scoring table for B/C, compute the totals. Then discuss: is a 0.05 difference enough to select C? Which measurements are missing?

## 66. Practice Exercise K — Hard Gate Beats Scores

A design scores 4.9/5 on performance but allows a timed-out payment request to be processed twice. Can it be selected? Design an idempotency ledger, unique key, and recovery path, then re-evaluate.

## 67. Practice Exercise L — Backup/Restore

A payment database has RPO=0 for acknowledged writes and RTO=30 minutes. Currently there are only hourly snapshot backups with untested restores. Document the hard gaps, test plan, and potential architecture/SLA changes needed.

## 68. Practice Exercise M — Writing an ADR

Choose between B (references) and C (hybrid) for order detail. Write an ADR containing context, hard constraints, alternatives, evidence, selected option, risks, mitigations, owners, review triggers, and a rollback/migration plan.

## 69. Practice Exercise N — Sensitivity Analysis

The team raises operations weight from 15% to 30% and lowers read weight so the total stays 100%. Recompute B/C scores, explain what it means if the ranking flips, and why a prototype should run before hard-to-reverse decisions.

## 70. Suggested Practice Solutions

**A:** Patient schedule query: filter patientId/time, sort startAt; doctor schedule: doctorId/time; booking: unique business key for active slot; audit: appointmentId/time; aggregate stats: doctorId/time/status, optionally materialized. Hard gate: no double booking; indexes must be verified with query plans.

**B:** Bounded image metadata can be embedded if small and always read with the product; large binary images usually live in object storage with references. Two million comments belong in a separate collection with a productId/time index and pagination; never embed an unbounded array.

**C:** `orders.items` retains `productId`, `nameAtPurchase`, `unitPriceMinor`, and `quantity` as a snapshot. `products` retains `currentName`/`currentPrice`; catalog edits do not alter invoices.

**D:** `updateOne({_id:sku,available:{$gte:1}},{$inc:{available:-1}})`, at most one matched; stock≥0. Order/ledger in separate records require a transaction/protocol with reconciliation and an idempotency key.

**E:** Payment confirmation uses an appropriate authoritative/session-consistent path; homepage can use cache/secondary with bounded staleness; BI uses cutoff/snapshot/reconciliation so totals reconcile cleanly at a boundary.

**F:** Candidate index `{tenantId:1,customerId:1,status:1,createdAt:-1,_id:-1}`. Inspect keys/docs examined, plan, `nReturned`; queries omitting `customerId`/`status` may need another index for sorting.

**G:** Risks include 16 MiB limit, document growth, hot contention, large payloads, and poor array pagination; extract transactions into a collection indexed on `customerId + createdAt + _id` using keyset pagination.

**H:** A tenant-only shard key can make one mega-tenant hot; measure skew, targeting, shard key cardinality, compound/partition strategies, and consistency constraints before altering.

**I:** Authoritative event source, windowed top-10 derived collection, idempotent worker with checkpoints, rebuild from event history on drift; monitor p99 lag ≤60s per requirement plus late events/deletes.

**J:** B = 3.80; C = 3.85. Do not choose solely on a 0.05 margin; benchmark read/write, restore, operational effort, and confidence intervals.

**K:** Reject candidates violating non-double-charge. Fix with a stable `requestId`, unique ledger key, payload hash, and unknown-outcome reconciliation; then re-benchmark.

**L:** Hourly snapshots do not guarantee RPO=0. Protect acknowledged writes via replication/PITR and matching recovery procedures, rehearse restores under 30 minutes, or obtain approved SLO adjustments.

**M:** The ADR must state hard gates, evidence, selected option, and review conditions—not merely write "hybrid is better".

**N:** Weights must be normalized; ranking changes show the decision depends on business priorities rather than fixed truth. Measure low-confidence criteria further.

## 71. Common Mistakes in Trade-Off Reviews

| Mistake | Consequence | Fix |
|---|---|---|
| Picking schema solely from an ERD | Query patterns are ignored | Access-pattern matrix first |
| "Embed everything because MongoDB is document-based" | Unbounded arrays, hot parents | Bound cardinality/lifecycle |
| "Reference everything to stay normalized" | Excessive lookups/round trips | Embed snapshots/owned children when fitting |
| "Transactions solve all consistency" | Write skew, external side effects | Invariant modeling + idempotency |
| "ReadConcern majority is cross-HTTP snapshot" | Misunderstood consistency | Scope read session/snapshot clearly |
| "More indexes always means faster" | Write/storage overhead | Choose per workload/explain |
| "Sharding fixes every slow query" | Scatter-gather/hot shards | Shard key evaluation |
| "Cache does not affect business logic" | Broken read-your-writes | Freshness policy/invalidation |
| "TTL equals archival" | Unarchived data loss | Retention/archival pipeline |
| "Having backups means restore works" | RTO misses targets | Restore drills |
| "Equal counts mean data parity holds" | Missing/mismatched IDs/fields | Key/canonical parity |
| "High score overrides a hard constraint" | Data corruption/tenant leakage | Exclusion gates |
| "Fast p50 means healthy production" | Tail latency, retries | p95/p99 + failover/load |
| "Scoring unknowns as 5/5" | Decisions on assumptions | Confidence labels + benchmarks |
| "No ADR needed because team agreed" | Lost rationale, hard to revisit | ADR + review triggers |

## 72. Review Questions

**1. Why is there no single best MongoDB schema for all apps?** — Workloads, cardinality, consistency, and operations differ.

**2. What are the four decision axes?** — Modeling, consistency, performance, operations.

**3. How does a hard constraint differ from a weighted score?** — Hard-constraint violations must be eliminated or fixed, never offset with points.

**4. When does embedding fit?** — Bounded children, lifecycle tied to parent, usually read/written together.

**5. When do references fit?** — Children grow large, are updated/queried independently, or are shared.

**6. What does hybrid offer?** — Fast snapshot/summary reads while keeping a separate entity authority.

**7. What does hybrid trade off?** — Copy synchronization, write amplification, reconciliation/ops.

**8. What is the maximum MongoDB BSON document size?** — 16 MiB.

**9. Does single-document atomicity cover a ledger in another collection?** — No.

**10. How does an atomic update differ from idempotency?** — Atomicity protects a single write; idempotency prevents the same business request from applying multiple times.

**11. What does a unique index provide?** — Enforces uniqueness of an indexed business key under supported semantics.

**12. Are transactions needed for every reference?** — No; only when a business operation requires atomic multi-document changes.

**13. Does snapshot isolation prevent all write skew?** — Not automatically; guards/invariant design are still required.

**14. Is write concern majority the same as read preference primary?** — No; they address different concerns.

**15. Can secondary reads be stale?** — Yes, depending on lag, read concern, and sessions.

**16. What do indexes cost?** — Disk/cache space and write index maintenance.

**17. What does `explain` help inspect?** — Query plans, keys/docs examined, `nReturned`, and execution details.

**18. Can deep `skip` still be slow with an index?** — Yes.

**19. Does keyset pagination create a snapshot across multiple HTTP requests?** — No.

**20. Is `$lookup` always slow?** — No; it depends on indexes, fan-out, and query plans.

**21. Is a materialized view synchronously consistent by default?** — No; it requires pipelines and a freshness contract.

**22. How do sharding and replica sets differ?** — Sharding partitions data/workload; replica sets provide replication/HA.

**23. Does a hashed shard key automatically cure a single hot key?** — Not automatically.

**24. Is a multi-tenant shared collection automatically secure?** — No; queries must be auth-scoped.

**25. Does TTL archive records?** — No; TTL deletes per policy.

**26. Why are restore drills needed?** — Successful backups do not prove recovery meets RTO/RPO.

**27. Where do matrix weights come from?** — Approved business, SLO, and risk priorities.

**28. Is a 0.05 score difference conclusive?** — No, especially when scores are subjective and unmeasured.

**29. What must be tested?** — Model bounds, correctness, query plans, load, failover, and rollback/restore.

**30. How is an ADR useful?** — Records rationale, alternatives, evidence, risks, owners, and review triggers.

## 73. Pre-Approval Design Checklist

- [ ] Are use cases, scope, and out-of-scope boundaries clearly written?
- [ ] Are hard business invariants and tenant/security gates specified?
- [ ] Do access patterns include filters, sorts, projections, cardinality, and traffic?
- [ ] Have p50/p95/p99 document sizes been measured or estimated?
- [ ] Do all child arrays have bounds or growth plans?
- [ ] Have embedding, references, and hybrid been compared based on lifecycle?
- [ ] Is there a clear source of truth for denormalized fields?
- [ ] Are atomic boundaries, transactions, and idempotency designed?
- [ ] Do read concern, write concern, and read preference match the consistency policy?
- [ ] Are unique indexes and business constraints genuinely enforced?
- [ ] Are compound indexes chosen from real query shapes?
- [ ] Have `explain` plans and p95/p99 for critical queries been analyzed?
- [ ] Have deep pagination, sort tie-breakers, and keyset pagination been evaluated?
- [ ] Have lookup/aggregation/materialized projection costs been calculated?
- [ ] Is there a freshness and cache invalidation policy?
- [ ] Have hot keys, write contention, and skew been evaluated?
- [ ] If sharded, have key selection, routing, and uniqueness been verified?
- [ ] Do tenant isolation, auth scope, and PII controls meet requirements?
- [ ] Have storage, index growth, retention, and TTL been projected?
- [ ] Are backup/PITR, restore drills, and RPO/RTO covered?
- [ ] Is there a schema migration/expand-contract plan and rollback window?
- [ ] Are alternatives, hard gates, and weighted scores documented?
- [ ] Does the scoring matrix carry measured/estimated/unknown confidence labels?
- [ ] Has sensitivity analysis been run on weights?
- [ ] Do B/C benchmarks use identical logical responses and consistency?
- [ ] Have concurrency, fault injection, and restores been tested?
- [ ] Are ADR, ownership, monitoring, and review triggers in place?

## 74. Conclusion

In MongoDB application design, **data modeling, consistency, performance, and operations are four faces of the same decision**. Embedding can reduce round trips and leverage single-document atomicity, yet risks hitting size limits and hot-document contention when children grow without bound. References support independent lifecycles, yet require proper queries/indexes and integrity/transaction protocols. Hybrid accelerates read paths with explicit snapshots while increasing synchronization and operational costs.

**A good trade-off matrix does not start with scores.** It starts from business invariants and hard constraints, describes access patterns, proposes multiple candidates, builds a qualitative matrix, eliminates invalid options, applies weights tied to real priorities, validates via benchmarks, and records an ADR. A score of 3.80 versus 3.85 is not engineering truth by itself when scores remain unverified.

Ultimately, evaluate options across the entire lifecycle: data growth, failover, contention, backup/restore, schema migration, security, and on-call operations. A successful design does not merely run fast today—it **preserves business invariants, meets SLOs, and remains operable, recoverable, and evolvable for years to come**.
