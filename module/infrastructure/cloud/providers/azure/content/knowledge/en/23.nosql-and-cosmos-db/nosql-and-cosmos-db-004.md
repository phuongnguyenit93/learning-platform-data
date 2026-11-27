# Request Units, Provisioned Throughput, Autoscale, and Serverless

An e-commerce application stores orders, shopping carts, and activity logs in **Azure Cosmos DB for NoSQL**. During the day it receives a few hundred requests per second, during promotions traffic surges tenfold, and at night there are almost no users. If the team only knows the HTTP request count without knowing **how many Request Units (RUs) each operation consumes**, costs and load capacity become unpredictable. Even for the same 1,000 requests, reading one document by `id` and partition key looks vastly different from running an `ORDER BY` query across multiple partitions.

Azure Cosmos DB supports managing capacity through several models: **manual provisioned throughput**, **autoscale provisioned throughput**, and **serverless**. Picking the wrong model can mean over-provisioning RU/s for off-peak hours, hitting HTTP 429 throttling during spikes, or paying per-request rates for a steady workload that should have used reserved capacity.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the **CLOUD_PROVIDERS_AZURE** module, tying together Azure subscriptions/resource groups, Entra ID, networking, Java applications, data modeling, monitoring, security, and cost management. The focus is understanding, measuring, calculating, and choosing the right throughput model for **Azure Cosmos DB for NoSQL**; do not mechanically apply every example to MongoDB, Cassandra, or Gremlin APIs, as their interfaces, quotas, and inspection tools differ.

> **Note:** Pricing, quotas, minimum RU/s floors, dynamic autoscale behavior, region availability, account capabilities, and billing mode conversion rules are updated by Azure over time. Calculations here serve as mental models and practice exercises—**not pricing quotes, SLAs, or guaranteed throughput figures**. Before production deployment, verify the exact capabilities of your account/API/region and current pricing in the Azure Pricing Calculator and Portal.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how **Request Units (RUs)** differ from **RU/s**, and what drives `request charge`.
2. Distinguish the billing and resource mechanics of **manual provisioned throughput**, **autoscale**, and **serverless**.
3. Understand the relationship between **database, container, logical partition, physical partition**, and throughput.
4. Estimate RU/s from operation counts, RU/op, peak windows, and regions.
5. Measure actual RUs using the Azure SDK for Java, response headers, and Azure Monitor.
6. Design partition keys to avoid **hot partitions**, alongside read/write limits, indexing, and cross-partition queries.
7. Explain **HTTP 429 Too Many Requests**, `retry-after`, retry/backoff behavior, and latency impacts.
8. Design consistency, indexing, TTL, bulk operations, and data models to fit an RU budget.
9. Calculate cost examples across manual, autoscale, and serverless without confusing **RUs with RU/s**.
10. Plan benchmarking, monitoring, autoscale alerts, capacity sizing, and cost controls before production.

## 2. The Big Picture of Azure Cosmos DB

**Azure Cosmos DB** is a managed distributed database service. With **API for NoSQL**, data is typically stored as JSON items inside containers and accessed via SDKs and the SQL-like query API. Conceptual hierarchy:

~~~text
Azure subscription
└── Resource group
    └── Azure Cosmos DB account (API for NoSQL)
        ├── Database: commerce
        │   ├── Container: orders      (partition key: /tenantId)
        │   ├── Container: carts       (partition key: /tenantId)
        │   └── Container: events      (partition key: /tenantId)
        └── Regions / consistency / network / identity
~~~

Resources inside an account are governed by account settings, API type, regional availability, and the chosen capacity mode. **Databases** and **containers** can carry dedicated throughput or share throughput in supported configurations.

### Do Not Conflate These Levels

| Level | Role | Throughput Relationship |
|---|---|---|
| Account | Endpoint, regions, consistency, identity/network, capabilities | Determines capability/billing mode and regional footprint |
| Database | Groups multiple containers | Can configure shared provisioned throughput where supported |
| Container | Holds items and defines partition key/indexing | Can have dedicated throughput or use shared database throughput |
| Logical partition | Set of items sharing one partition key value | Subject to size and distribution limits |
| Physical partition | Infrastructure unit distributing storage and throughput | Subject to capacity limits and allocated throughput share |
| Item | JSON document | Reads/writes/queries consume RUs proportional to work |

No amount of provisioned RU/s automatically fixes a **poorly distributed partition key**. If every order carries partition key `"global"`, load concentrates on one logical partition, causing bottlenecks even while the container has unused throughput overall.

## 3. What Is a Request Unit (RU)?

An **RU (Request Unit)** is a normalized measure of the system resources required for a request in Azure Cosmos DB, abstracting CPU, memory, and I/O work at the service layer. RUs let developers compare disparate data operations without directly sizing physical hardware.

Operations that consume RUs include:

- Point reading an item by `id` **and partition key**.
- Creating, upserting, replacing, or deleting an item.
- Running a SQL-like query across one or multiple partitions.
- Fetching subsequent pages of a query.
- Executing stored procedures, transactional batches, or bulk operations per API support.
- Background work such as indexing and TTL expiration can affect overall resource consumption and billing per product mechanics.

### RUs vs. RU/s

- **RU:** Units consumed by a single request—for example, a point read costing 1.2 RUs or a query costing 45 RUs.
- **RU/s:** Processing budget provisioned **per second** in throughput models—for example, 1,000 RU/s.
- **Consumed RUs:** Total RUs accumulated across requests over a time window—for example, 720,000 RUs in an hour.
- **Provisioned RU/s:** Reserved capacity billed over time in manual/autoscale modes, distinct from actual consumed RUs.

~~~text
1 operation:                      5 RUs
200 operations in one second:     200 × 5 = 1,000 RUs
Demand during that second:        ~1,000 RU/s
~~~

The example above assumes every request costs 5 RUs, spreads evenly across physical partitions, and faces zero spikes or overhead. In practice, add headroom, peak skew, retries, query variance, and verified partition distribution.

### The 1 RU Reference Benchmark

In commonly cited baseline conditions, a **point read of a ~1 KiB JSON document** costs roughly **1 RU**. This is a **reference point**, not a guarantee that every point read at every consistency level costs 1 RU. Larger items, stronger consistency, or different access patterns change the cost.

**Never assume 1 RU = 1 request.** A cross-partition query can consume tens, hundreds, or far more RUs; a small read can be near 1 RU.

## 4. Factors Affecting Request Charges

| Factor | Typical Impact | How to Optimize |
|---|---|---|
| Item size | Larger items cost more RUs to read and write | Store only needed fields; offload large blobs |
| Point read vs. query | Point reads are usually cheaper than querying for the same item | Use `id` + partition key whenever known |
| Number of returned items | Fetching more documents costs more RUs | Use pagination, projections, and result limits |
| Cross-partition query | Multi-partition fan-out increases RUs and latency | Filter by partition key whenever practical |
| Indexing policy | Updating indexes adds write RUs; queries benefit from indexes | Index only paths actually queried |
| Query complexity | `ORDER BY`, aggregates, filters, or joins increase work | Tune query plans/indexes and data model |
| Consistency | Some consistency choices carry different read costs | Pick per business need rather than always strongest |
| Regions and replication | Multi-region provisioned throughput/writes raise total cost | Measure demand and size the regional footprint |
| Hot partition | One key absorbs most traffic | Design an evenly distributed key before scaling |
| Retries / 429s | Extra attempts and latency shift effective load | Tune retry policies, concurrency, and RU/op |

Even the same query can change RU cost as item count, indexing policy, or query plans evolve. Always **benchmark on production-like data and workload shapes** instead of trusting an RU/op number from a single tiny sample item.

## 5. Observing RUs in Responses

The service returns **request charge** metadata in responses. Over HTTP, a standard header is:

~~~http
x-ms-request-charge: 3.14
~~~

The illustrative value `3.14` represents the **RUs consumed by that specific request**, not provisioned RU/s. SDKs expose methods to read this charge directly without manual header parsing.

Record the following in **client/service instrumentation**:

- Operation type, container, route, or use-case name.
- Request charge (RUs) and operation duration.
- Partition key category (avoid logging raw PII keys where prohibited by policy).
- HTTP status/substatus, retry count, and `retry-after` on errors.
- Query identifier or normalized query text stripped of sensitive values.
- Contacted region and SDK diagnostics (filtered with restricted access).
- Query page count and total RUs per business operation.

**Avoid treating a single request charge as the cost of an entire pipeline** when the SDK issues multiple pages, prefetches, or retries. For paginated queries, sum the charges across all pages read.

## 6. Three Capacity Models: Manual, Autoscale, Serverless

| Criterion | Manual Provisioned Throughput | Autoscale Provisioned Throughput | Serverless |
|---|---|---|---|
| Capacity allocation | Fixed configured RU/s | Configured **maximum RU/s**; service scales within supported bounds | No upfront RU/s provisioned |
| Throughput billing | Based on provisioned RU/s over time | Based on autoscaled RU/s per billing period, with a minimum floor | Based on actual consumed request RUs |
| When idle (zero requests) | Still billed for provisioned capacity | Still billed at the autoscale minimum floor | No continuous RU/s provision fee; storage and other resources still apply |
| Steady traffic | Usually easiest to optimize with manual | May pay extra for unneeded flexibility | Often less economical at high steady RU volume |
| Variable traffic | Prone to 429s if peaks exceed RU/s | Scales with load up to configured maximum | Pay-per-RU, though still subject to capacity limits |
| Key decisions | Target RU/s and partitioning | Maximum RU/s, floor/peak spread, and hourly cost | Peak burst tolerance, quotas, and RU consumption cost |
| Partition distribution | Yes | Yes | Service-managed, though partition design still matters |
| Database-shared throughput | Supported in applicable models | Supported in applicable models | Not modeled as buying shared provisioned RU/s |
| Changing / scaling modes | Subject to account/container rules and limits | Subject to supported rules and limits | Account capability and migration constraints apply |

**Autoscale and serverless are not the same feature.** Autoscale is **automatically adjusting provisioned capacity** within a band; serverless is **pay-per-consumed-RU** without reserving RU/s.

## 7. Manual Provisioned Throughput

With **manual provisioned throughput**, you set a fixed RU/s level on a container or shared database pool per resource rules. Example:

~~~text
Container orders provisioned: 2,000 RU/s

00:00-06:00:  traffic uses only ~100 RU/s
12:00-14:00:  traffic uses ~1,200 RU/s
20:00-21:00:  peak hits ~2,400 RU/s
~~~

During off-peak hours, unused RU/s are **not automatically refunded**. At the 2,400 RU/s peak, if demand exceeds deliverable capacity, requests experience 429s and retry latency—which also depends on **partition distribution**, not just container-wide RU/s.

### Strengths

- Predictable provisioned throughput costs based on configuration and hours.
- Fits steady, low-variance workloads well.
- Simple choice for continuous pipelines running at high utilization.
- Can be adjusted manually via schedules or automation where workload and features permit.

### Weaknesses

- Unused RU/s during quiet periods still incur charges.
- Requires forecasting peaks and scaling throughput proactively.
- Slow manual scaling exposes spikes to throttling.
- Hot partitions still trigger 429s even with spare container throughput.

### Sizing Manual RU/s

Suppose an API handles:

- 400 point reads/s × 1.5 RU/read = 600 RU/s.
- 80 writes/s × 7 RU/write = 560 RU/s.
- 10 queries/s × 18 RU/query = 180 RU/s.

Measured average demand per second: **1,340 RU/s**. Adding 30% test headroom gives **1,742 RU/s**. You might evaluate provisioning **2,000 RU/s**, provided it meets container minimums/increments, partition spread, and latency SLOs.

This calculation uses **assumed peak load and measured RU/op**—it is not a formula guaranteeing that a 2,000 RU/s container will serve 1,340 RU/s if one logical partition runs hot.

## 8. Autoscale Provisioned Throughput

With **autoscale**, operators configure a **maximum throughput** `Tmax` in RU/s. Azure Cosmos DB automatically scales provisioned RU/s within supported bounds to match demand.

In standard autoscale, the capacity range is typically described from **a minimum fraction of `Tmax` (commonly ~10%)** up to `Tmax`; the platform also offers **dynamic autoscale** variants and per-partition/region scaling behaviors with different billing details. Always verify exact limits and billing rules against current account documentation.

~~~text
Autoscale max throughput: 4,000 RU/s

Low load     -> service scales down within supported range
Medium load  -> service scales up to meet demand
Heavy spike  -> scales up to 4,000 RU/s max
Load > 4,000 -> 429s or higher latency can still occur
~~~

### What `Tmax` Actually Means

`Tmax` is **not consumed RUs**. It is the **RU/s ceiling** configured for autoscale. If a workload demands 7,000 RU/s while `Tmax` is 4,000 RU/s, autoscale will not exceed 4,000 unless you raise `Tmax` within allowed limits.

### Mental Model for Billing

In standard autoscale configurations, hourly provisioned throughput charges are based on the highest RU/s level scaled to during the billing hour, bounded by the `Tmax`-derived floor. Conceptual example:

~~~text
Tmax:                         4,000 RU/s
Illustrative floor:             400 RU/s
Hour peaking at 2,400 RU/s   -> billed at the recorded scaled capacity for that hour
Hour with zero load          -> still billed at the minimum capacity floor
~~~

This example does not hardcode specific unit rates or rounding rules. With **dynamic autoscale**, per-partition/region scaling and billing rules can differ from classic autoscale; verify actual metrics and current billing documentation.

### When Should You Use Autoscale?

- Hourly or daily peaks fluctuate significantly while still needing reserved throughput.
- Scheduled batch jobs cause short traffic surges.
- Seasonal events or promotions have predictable `Tmax` bounds.
- You want elastic scaling without manual intervention on every spike.
- Operations prefers the provisioned model for multi-region or high-capacity needs.

### Autoscale Does Not Replace the Partition Key

Suppose one `tenantId` drives 90% of requests. If the physical partition holding that tenant saturates, raising `Tmax` does not proportionally relieve it because throughput is distributed across physical partitions with per-partition limits. Inspect **normalized RU consumption per partition** and revisit the data model.

## 9. Serverless: Paying Per Consumed RU

**Serverless** requires no upfront RU/s reservation. You pay for **actual consumed request RUs** plus storage and related resource charges under applicable pricing. It fits:

- Development and prototype apps with light or sporadic workloads.
- Internal APIs triggered only by infrequent events.
- Feature experiments, demos, or low-volume batch pipelines.
- Environments with long idle stretches that do not justify always-on capacity.

### Example

~~~text
One day:
  10,000 point reads × 1 RU         = 10,000 RUs
  1,000 writes × 8 RU               =  8,000 RUs
  100 query pages × 40 RU           =  4,000 RUs
Daily total                          = 22,000 RUs
~~~

In serverless, you estimate **request cost from total billable RUs**, rather than multiplying `Tmax RU/s × hours` as in provisioned modes. Storage, networking/backups, and companion app services still apply.

### Serverless Does Not Mean Infinite Scale

Serverless still enforces **throughput/request, storage/partition, region, and account limits**, so bursts beyond supported capacity can trigger 429s. If your design requires a steady 100,000 RU/s, evaluate provisioned throughput and account architecture rather than assuming serverless scales without bounds.

### Choose Account Capability Upfront

Serverless is an **account-level capability/configuration** with its own creation rules and conversion constraints. Do not assume a running serverless account can instantaneously flip to manual/autoscale in place with one command, or vice versa. If your configuration does not support direct conversion, plan to **provision a new account, migrate data, switch endpoints, and validate**.

### When Serverless Can Cost More

A 24/7 workload with heavy RU consumption can incur higher total pay-per-RU fees than well-utilized provisioned throughput. Measure **cost per business operation** and compare realistically rather than focusing solely on “zero idle RU charges.”

## 10. Workload-Based Decision Table

| Workload | Characteristics | First Option to Evaluate | Why |
|---|---|---|---|
| Steady 24/7 production API | Even load, predictable RU/op | Manual provisioned | Maximizes utilization of fixed capacity |
| Campaign-driven spiky API | High peaks, quiet off-peak hours | Autoscale | Eliminates manual RU/s adjustments |
| Lightly used test environment | Idle most of the time | Serverless | Avoids paying for idle provisioned RU/s |
| One-hour daily batch import | Short, intense spike | Autoscale or scheduled manual | Evaluate peak-hour cost vs. capacity |
| Small, sporadic event-driven app | Low operation counts | Serverless | Pay strictly for consumed RUs |
| High-traffic global system | Multi-region, strict SLAs | Provisioned manual or autoscale per support | Controls throughput, replication, and regional capacity |
| Skewed multi-tenant load | A few ultra-hot tenants | **Fix partitioning first**, then pick mode | Billing modes cannot cure hot keys |
| Mixed analytics and OLTP | Fan-out queries hurting point reads | Redesign data/query architecture | Optimizes RUs and isolates workloads |

These are **starting points for a PoC**, not rigid answers for every project. A quiet serverless workload needing specialized multi-region features may run into account capability limits; an autoscale workload can still hit 429s on a hot partition.

## 11. Database-Level or Container-Level Throughput?

In supported provisioned throughput accounts, throughput can be set at:

1. **Container level:** Each container gets its own manual or autoscale budget.
2. **Database level (shared throughput):** Eligible containers inside the database share a provisioned RU/s pool, subject to allocation rules and container limits.
3. **Mixed model:** Some containers share the database pool while others have dedicated throughput, where supported.

### Container-Level Throughput

Advantages:

- Clean load and cost isolation between `orders`, `carts`, and `events`.
- Heavy queries on an analytics container cannot directly starve an OLTP container's dedicated RU/s.
- Easy to assign specific SLAs and capacity to critical workloads.

Trade-off: many separate containers mean each incurs its own minimum throughput floor and baseline cost. Across hundreds of tiny containers, baseline costs add up quickly.

### Database Shared Throughput

Fits when multiple containers have **light, uneven traffic** and can share capacity. The risk is one hot container draining the shared budget and throttling sibling containers.

**Never treat shared throughput as guaranteeing the full RU/s pool to every container.** Check how the service allocates capacity and measure real contention. Give business-critical containers dedicated throughput to prevent noisy neighbors.

### Serverless Is Not Shared Provisioned Throughput

Serverless bills per consumed RU under the serverless account model; you do not declare a `shared 4,000 RU/s` database pool as with provisioned throughput. You still must design partition keys and respect operational limits.

## 12. Logical Partitions, Physical Partitions, and Hot Keys

The **partition key** is a document property such as `/tenantId`. Documents sharing the same key value belong to the same **logical partition**. The service maps logical partitions onto **physical partitions** to distribute storage and throughput.

~~~mermaid
flowchart TD
  C["Container orders: partition key /tenantId"] --> L1["tenant-A logical partition"]
  C --> L2["tenant-B logical partition"]
  C --> L3["tenant-C logical partition"]
  C --> L4["tenant-D ..."]
  L1 --> P1["Physical partition 1"]
  L2 --> P2["Physical partition 2"]
  L3 --> P2
  L4 --> P3["Physical partition 3"]
  P1 --> RU["Allocated provisioned / autoscale RU/s"]
  P2 --> RU
  P3 --> RU
~~~

This diagram illustrates mapping conceptually; physical partitions split automatically as data or throughput scales, and allocation details vary by throughput mode.

### Hot Logical Partition

One large tenant generates 80% of requests while thousands of other tenants share the remaining 20%. If all items for that large tenant carry `tenantId="enterprise-1"`, its logical partition runs hot. **You cannot split an existing logical partition into multiple logical partitions just by raising RU/s** without changing the partition strategy or data model.

### Hot Physical Partition

Several small logical keys may happen to land on the same physical partition. When that partition's normalized RU consumption nears 100%, 429s occur on that partition even though the overall account or container has not exhausted its total provisioned RU/s.

**Spare container-wide RU/s does not prove every request has enough capacity.** Inspect partition distribution and per-key load.

### Questions for Choosing a Partition Key

- Is the key known in frequent point reads and queries?
- Does it have enough distinct values with reasonably even distribution?
- Could a single value grow too large in storage or RU/s?
- Can you use a synthetic key or hierarchical partition key within API/SDK support?
- Are transaction boundaries needed within one logical partition?
- Are cross-partition queries acceptable within budget?

Changing the partition key of a live container **is not a simple field rename**; it normally requires provisioning a new container and migrating data via supported tooling.

## 13. Partition Keys and Multi-Tenant Application Design

Sample item:

~~~json
{
  "id": "order-1024",
  "tenantId": "tenant-A",
  "orderDate": "2026-11-20",
  "status": "PAID",
  "totalAmountMinor": 259000,
  "currency": "VND"
}
~~~

With partition key `/tenantId`, point reads use both `id` and `tenantId`:

~~~text
id = "order-1024"
partitionKey = "tenant-A"
~~~

If a caller only sends `orderId` and the app does not know the tenant, lookup becomes a cross-partition query. Keep tenant identity from authentication/session context or a dedicated mapping rather than issuing fan-out queries on every `GET`.

### When a Large Tenant Runs Hot

Strategies to evaluate:

1. Design a **synthetic partition key** such as `tenant + bucket` with clear query routing rules.
2. Use **hierarchical partition keys** where supported by the API, SDK, and data model, mindful of key ordering and query patterns.
3. Isolate massive tenants into dedicated containers or accounts when capacity isolation and budgeting demand it.
4. Use queues/event streams to smooth bursty writes.
5. Enforce per-tenant rate limits to contain noisy neighbors.

**Never append random suffixes to keys without preserving lookup paths:** if the app cannot derive the bucket, point reads degrade into multi-bucket scans, inflating RUs and latency.

## 14. Throughput Distribution Across Physical Partitions

A container's provisioned throughput is distributed across its physical partitions by the service. Each physical partition has a **finite maximum capacity**, so throughput is not infinitely poolable onto one logical key in the same second.

Conceptual example:

~~~text
Container provisioned throughput: 12,000 RU/s
Suppose split across 3 physical partitions:
  Partition P1: 4,000 RU/s
  Partition P2: 4,000 RU/s
  Partition P3: 4,000 RU/s

Current workload:
  P1 demands 4,300 RU/s -> may throttle
  P2 demands 1,200 RU/s
  P3 demands 1,100 RU/s

Total app usage: 6,600 RU/s < 12,000 RU/s
Yet P1 can still return 429s
~~~

Even splits are illustrative only to demonstrate **hot partitions**; actual physical partition counts, RU splits, autoscale dynamics, and throttling must be observed in Azure Monitor for your specific resource.

### Physical Partition Splits

As data or throughput grows, Cosmos DB splits physical partitions automatically. Splitting does not alter logical partition key semantics. If one logical key carries most of the traffic, **a physical partition split will not fix the hot key**.

Monitor `Normalized RU Consumption` by partition/region alongside per-operation request charges; never rely solely on total `Total Request Units`.

## 15. HTTP 429: When Requests Exceed Throughput

**HTTP 429 Too Many Requests** in Cosmos DB signals that a request could not be served immediately due to throughput or partition capacity saturation at that moment. Responses typically include a wait hint, such as:

~~~http
HTTP/1.1 429 Too Many Requests
x-ms-retry-after-ms: 25
~~~

Here `25` is an **illustrative 25 milliseconds**, not a fixed retry delay. Respect `retry-after` hints and SDK retry policies rather than hammering immediately in a tight loop.

### Is a 429 Always an Incident?

Not necessarily. The Azure Cosmos DB SDK automatically retries throttled requests within configured limits. A low rate of 429s can simply reflect efficient high utilization; **however, sustained 429s or prolonged retries that push p95/p99 latency past SLOs or cause failures** must be investigated.

Distinguish between:

- `429` from insufficient overall RU/s.
- `429` from a hot partition while overall RU/s remain underutilized.
- `429` from serverless bursts hitting service limits.
- Retries that the SDK ultimately resolved cleanly.
- API/business timeouts triggered by cumulative retry delays.

### What Not to Do

- Never write `while(true) { retry(); }` loops with no delay.
- Never spawn unbounded threads to “power through” 429s.
- Never blindly map all 429s to HTTP 500 without logging cause and timing.
- Never disable SDK retries without understanding the impact.
- Never dump full Cosmos diagnostics containing sensitive payloads into unguarded logs.

### Step-by-Step Remediation

1. Inspect app latency/error rates alongside 429 rates and retry metrics.
2. Measure RU/op request charges for top operations.
3. Inspect normalized RU consumption **per partition**.
4. Verify `Tmax` or manual RU/s and utilization curves.
5. Investigate cross-partition queries, indexing, and oversized items.
6. Tune concurrency, batch sizes, or bulk ingestion to align with SLOs.
7. Scale throughput where appropriate and effective within physical/hot-key limits.
8. Re-run load tests before applying broad production changes.

## 16. SDK Retries, Timeouts, and End-to-End Latency

When a Cosmos DB REST call is throttled, the Java SDK retries under default or custom policies. Seeing an operation succeed at the application layer **does not mean zero retries or 429s happened underneath**.

Track:

- Total elapsed operation time.
- Response request charge and cumulative RUs across multi-page/multi-request flows.
- Diagnostics: contacted regions, retry counts, status/substatus codes.
- Completed business operations.
- Overall API timeout/deadline.
- Per-operation latency percentiles.

### Retries and Idempotency

On writes, updates, or upserts, clients can time out after the server commits but before the response arrives. On retry, rely on deterministic `id` + partition key, `ETag` optimistic concurrency, or business idempotency keys so retries do not create duplicate invoices or orders.

**SDK 429 retries do not replace business-level correctness.** Retries help ride out transient throttling, not guarantee external side effects execute once.

### Enforcing Timeout Budgets

If an API has an 800 ms latency budget, never execute a multi-dozen-page query with multi-second retries inline inside the HTTP request. Offload heavy work asynchronously via Azure Service Bus, Queue Storage, or Functions, track job status, and return `202 Accepted`.

## 17. Optimizing RUs: Point Reads Before Queries

A query such as:

~~~sql
SELECT * FROM c
WHERE c.id = "order-1024"
~~~

without a matching partition key filter **can fan out across all logical and physical partitions**. When both `id` and `tenantId` are known, use an SDK **point read**:

~~~text
container.readItem(
  id = "order-1024",
  partitionKey = "tenant-A"
)
~~~

Both return the same item, yet RU charges and latencies differ dramatically. Point reads are the lowest-RU way to fetch a single item by key.

### Partition-Scoped Queries

When querying is necessary:

~~~sql
SELECT c.id, c.status, c.totalAmountMinor
FROM c
WHERE c.tenantId = "tenant-A"
  AND c.status = "PAID"
~~~

Pass the partition key via **query request options** or an appropriately optimized filter, and parameterize queries to prevent SQL injection and data leakage. Never concatenate raw tenant IDs from incoming requests into production query strings.

### Projections and Pagination

- Project only needed fields instead of defaulting to `SELECT *`.
- Use continuation tokens to fetch subsequent pages.
- Load only pages actually needed by the UI.
- Track RUs **per page** and total RUs per business workflow.
- Remember that queries returning 0 items still consume RUs.

## 18. How Indexing Policies Affect RUs

Azure Cosmos DB for NoSQL automatically indexes properties per the container's **indexing policy**. That provides flexible ad hoc querying, but updating indexes adds RU overhead on writes.

Example scenario:

- Every order document has 60 properties, yet the app only queries `tenantId`, `status`, and `createdAt`.
- Indexing all 60 paths inflates write RUs unnecessarily.
- Dropping paths carelessly can slow down queries, spike RUs, or break queries requiring indexes.

### Evaluation Process

1. Capture real query workloads, query plans, and index utilization.
2. Measure baseline write and query RU charges before modifying anything.
3. Choose included/excluded paths and composite indexes matched to `ORDER BY` and filter patterns.
4. Test changes in a staging environment with representative data.
5. Monitor index transformation progress, costs, and performance impact.
6. Re-verify all critical queries after migration.

### Illustrative Indexing Policy

~~~json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {"path": "/tenantId/?"},
    {"path": "/status/?"},
    {"path": "/createdAt/?"}
  ],
  "excludedPaths": [
    {"path": "/*"}
  ]
}
~~~

This is a **conceptual policy example for discussion**, not a drop-in configuration safe for every workload. Designing exact includes/excludes requires checking **partition key behavior, default system index behavior, index path syntax, and every query hitting the container** against current JSON schema rules. Never alter production policies solely to tune one query if other workloads depend on those indexes.

## 19. High-RU Query Anti-Patterns and Improvements

| Anti-Pattern | Why It Burns RUs / Bottlenecks | Improvement to Test |
|---|---|---|
| Querying entire container when `id` + key are known | Cross-partition fan-out | Point read |
| `SELECT *` on every API | Transfers and processes unneeded data | Projection |
| Full OLTP reporting queries at peak hours | Multi-page scans competing for throughput | Data pipeline / analytical store or workload isolation |
| Complex `ORDER BY` without matching index | High RU scan or unsupported execution | Composite / targeted index design |
| Huge items storing giant blobs or text | Inflated read/write charges | Store blobs separately and reference them |
| Upserting entire large item to change one field | Rewrites full document | Partial document Patch where appropriate |
| Low-cardinality partition key | Hot partitions | Better key distribution / synthetic keys |
| Polling data continuously with queries | Repeated redundant reads | Change feed / event-driven processing |
| Discarding continuation tokens | Re-reads earlier pages repeatedly | Proper token-based pagination |
| Blindly retrying writes on timeout | Extra RUs + duplicate side effects | Idempotency and concurrency control |

**Never assume Patch is always cheaper than Replace:** Patch RU cost depends on path count, indexing, item size, and engine behavior. Measure actual `request charge` before optimizing.

## 20. Consistency Levels and RUs

Cosmos DB offers **consistency levels**—Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual—within API, account, and regional constraints. Consistency affects:

- How quickly and consistently reads observe recent writes.
- Latency and availability trade-offs in geo-distributed setups.
- Read RU calculations and replication mechanics.
- Session token management, read-your-writes, and conflict handling.

Mental model: stronger consistency levels can carry **different read costs** than Session or Eventual, though you should not apply a fixed RU multiplier across every API, operation, and region. Measure point reads and queries in your real configuration.

### Session Consistency

An app where a user creates an order and immediately reads it back often chooses **Session** consistency when it satisfies consistency needs. The SDK manages session tokens automatically within a client, though passing sessions across multiple backend services requires understanding token propagation and boundaries.

### When Strong Is Needed

If business invariants strictly require linearizable reads returning the latest committed write, evaluate Strong alongside topology, latency, supported regions, and cost. Do not pick Strong by default when eventual convergence suffices, yet never compromise business correctness just to shave RUs.

## 21. Multi-Region Throughput, Availability, and Billing

Azure Cosmos DB distributes data across multiple regions per account configuration, supporting single-write or multi-write failover topologies within SKU and consistency constraints.

### Key Points

1. **Provisioned throughput** typically scales cost across active regions, not just a single global number on an architecture slide.
2. Multi-region replication increases throughput, storage, and network transfer charges per pricing rules.
3. Multi-write topologies require explicit conflict resolution semantics and application safeguards.
4. Read/write latencies depend on client region, routing, and consistency.
5. Regional outages require tested failover, DNS/SDK endpoint discovery, and business recovery procedures.
6. Serverless carries **account and region constraints** that must be checked before designing global apps.

### Cost Estimation Oversight Example

~~~text
Flawed plan:
  "Container needs 4,000 RU/s, so we pay for exactly 4,000 RU/s globally."

Questions to ask:
  How many regions?
  How many reads and writes hit each region?
  Manual or autoscale?
  Multi-write or single-write?
  How do multi-region throughput billing and storage replication apply?
  Are dedicated gateways, integrated caches, or add-ons enabled?
~~~

Never apply an arbitrary flat multiplier across accounts or regions without checking the official pricing model.

### Private Networking

Cosmos DB accounts support network access controls and Private Endpoints per API and feature rules. When a Java client in AKS, Container Apps, or a VM connects over a VNet/Private Endpoint:

- Verify Private DNS resolution maps to the private IP.
- Check egress routing, NSGs, firewalls, and endpoint policies.
- Configure managed identity and data-plane RBAC properly.
- Do not confuse HTTP 403 permission/network errors with HTTP 429 throttling.
- Verify the SDK connection mode supports your network path.

## 22. Estimating RU/s Using a Workload Matrix

Start from **real use cases**, not just concurrent user counts.

| Operation | Peak Requests/s | Measured RU/op | RU/s Demand |
|---|---:|---:|---:|
| Read cart point read | 800 | 1.2 | 960 |
| Update cart | 180 | 8 | 1,440 |
| Create order | 70 | 12 | 840 |
| Query order history | 40 | 20 | 800 |
| **Total** | | | **4,040** |

Suppose this 4,040 RU/s instantaneous demand is evenly distributed. Adding 25% headroom for variance yields a target around **5,050 RU/s**. Pick a valid configurable value after checking minimum throughput, partition counts, and max RU/s constraints—a lab design might evaluate **~6,000 RU/s manual or autoscale `Tmax` ~8,000 RU/s**, without treating that as a hard throughput/latency guarantee.

### Why Average Requests/Day Is Misleading

Suppose an app handles 1 million requests per day:

~~~text
Average QPS = 1,000,000 / 86,400 ≈ 11.57 requests/s
~~~

This average **hides peaks**. If 500,000 of those requests arrive within a 10-minute flash sale, peak QPS hits ~833 requests/s—requiring vastly more RU/s than the daily average suggests.

### Include Batch and Background Traffic

Factor nightly ETL, TTL deletions, change feed processors, and reporting queries into capacity sizing—or isolate them in separate containers/workloads—rather than sizing solely for user-facing APIs.

## 23. Variable-Based Cost Comparison Examples

To avoid outdated hardcoded pricing, use variables:

- `P_manual`: unit price per provisioned RU/s per hourly billing cycle in a specific region/tier.
- `P_auto`: corresponding hourly unit price for autoscale provisioned RU/s.
- `P_serverless`: price per million consumed RUs in serverless.
- `S`: storage and non-throughput fees, tracked separately.

### Manual

~~~text
Manual RU/s: 2,000
Example monthly hours: 730

Throughput cost ≈ 2,000 × 730 × P_manual
Total ≈ throughput cost + S + network/monitoring/other costs
~~~

### Autoscale

Suppose `Tmax = 4,000 RU/s` with recorded hourly billable scaled capacity:

~~~text
Hours 00-05: capacity billed at floor / observed minimum
Hours 06-18: capacity tracks fluctuating workload
Hours 19-23: capacity tracks peaks and floor

Throughput cost ≈ sum over hours (billable autoscaled RU/s × P_auto)
~~~

This formula expresses the core concept; **dynamic autoscale** and multi-region/partition rules can determine billable RU/s differently. Validate against actual invoices and metrics.

### Serverless

~~~text
Monthly consumed RUs: 120,000,000 RUs

Request charge cost ≈ (120,000,000 / 1,000,000) × P_serverless
Total ≈ request cost + S + network/monitoring/other costs
~~~

In this example, **120 million RUs/month is not 120 million RU/s**, nor do you divide by 730 hours when pricing per million RUs. Confusing those units is one of the most common pricing mistakes.

### Break-Even Analysis

Place cost expressions side by side using identical traffic profiles and storage footprints. Base the comparison on **measured request charges**, hourly/regional distribution, physical partition count, real retries, and SKU/account capabilities. Never decide solely on raw request count: 1 million point reads cost orders of magnitude less than 1 million cross-partition queries.

## 24. Azure CLI: Inspecting Current Account and Throughput

Examples target **Azure Cloud Shell Bash** or any machine logged into Azure CLI. Reading and assessing existing resources creates no new charges. Replace placeholders with authorized resource names.

### Step 1 — Verify Subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table
~~~

### Step 2 — Read Account Configuration

~~~bash
RG="rg-cosmos-lab"
ACCOUNT="<COSMOS_ACCOUNT>"
DB="commerce"
CONTAINER="orders"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,location:location,kind:kind,capabilities:capabilities,locations:locations,consistencyPolicy:consistencyPolicy}" \
  --output json
~~~

Check the API type, regions, consistency, and capabilities (such as serverless) if present. Exact fields depend on ARM API/CLI versions; never infer the account mode solely from one absent property.

### Step 3 — Container Throughput

~~~bash
az cosmosdb sql container throughput show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --output json
~~~

If the container uses **database shared throughput**, querying container-level throughput may not return what you expect. Check database-level throughput instead:

~~~bash
az cosmosdb sql database throughput show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB" \
  --output json
~~~

With **serverless**, there is no provisioned RU/s to query like manual/autoscale. An empty or error response might indicate **shared throughput**, serverless mode, or a permissions/syntax error—cross-check account capabilities and resource properties.

### Step 4 — Inspect Container Partition Key and Indexing

~~~bash
az cosmosdb sql container show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --query "{id:resource.id,partitionKey:resource.partitionKey,indexingPolicy:resource.indexingPolicy}" \
  --output json
~~~

If your Azure CLI version returns a different JSON shape, inspect the allowed properties in the full resource output. Never paste account keys, connection strings, or credentials into reports.

## 25. Azure CLI: Creating a Container with Manual or Autoscale Throughput

**These examples modify resources and can incur costs.** Run them only inside an approved lab resource group, Cosmos DB for NoSQL account, and database with authorized permissions. The container names below are **distinct** to prevent collisions.

### Manual Provisioned Throughput

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "orders-manual-lab" \
  --partition-key-path "/tenantId" \
  --throughput 1000
~~~

### Autoscale Provisioned Throughput

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "orders-auto-lab" \
  --partition-key-path "/tenantId" \
  --max-throughput 4000
~~~

Verify flags and **account-supported minimums** via `az cosmosdb sql container create --help` and live settings. Never pass both `--throughput` and `--max-throughput` together as if requesting both modes at once; they represent mutually exclusive throughput models.

### Serverless

Serverless containers do not accept `--throughput` or `--max-throughput` when created in a supported serverless account. **Never spin up a brand-new production account just to experiment expecting to freely switch billing modes later.** Use a designated lab account or approved IaC/Portal workflow after verifying account capabilities and regional limits.

### Modifying Existing Throughput

Updating or migrating throughput modes is constrained by account/container rules, minimums, partition state, and API versions. Before raising throughput in production:

1. Capture **current provisioned RU/s, autoscale max RU/s, storage size, and physical partition state**.
2. Assess projected cost impact and downward scaling rules.
3. Verify whether the change requires a supported manual-to-autoscale migration command.
4. Test in staging and observe 429s and latency.
5. Document the configuration change, owner, timestamp, and rollback plan.

**Never run an ambiguous throughput update command** without confirming whether the container uses shared database throughput or dedicated throughput.

## 26. Azure SDK for Java: Measuring RUs with a Point Read

Use organization-approved Maven dependency versions:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>${azure.cosmos.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>${azure.identity.version}</version>
  </dependency>
</dependencies>
~~~

This is a **POM fragment**; declare version properties or use a compatible Azure SDK BOM/dependency management setup. The Java code assumes an **Azure Cosmos DB for NoSQL** account with proper Microsoft Entra data-plane RBAC.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class CosmosRuDemo {

    public static final class Order {
        public String id;
        public String tenantId;
        public String status;
    }

    public static void main(String[] args) {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
        }

        try (CosmosClient client = new CosmosClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient()) {

            CosmosContainer container = client
                .getDatabase("commerce")
                .getContainer("orders");

            CosmosItemResponse<Order> response = container.readItem(
                "order-1024",
                new PartitionKey("tenant-A"),
                Order.class
            );

            System.out.printf("RU charge: %.2f%n",
                response.getRequestCharge());
            System.out.println("Order status: "
                + response.getItem().status);
        }
    }
}
~~~

### Notes for Real Execution

- `COSMOS_ENDPOINT` looks like `https://<account>.documents.azure.com:443/` depending on the provisioned endpoint, and **contains no key**.
- `DefaultAzureCredential` uses a developer identity locally or a managed/workload identity in Azure; verify the active credential.
- **Control-plane** roles do not necessarily grant item read permissions; Entra auth requires properly scoped Cosmos DB **data-plane RBAC**.
- Item `order-1024` with partition key `tenant-A` must exist in the lab container.
- Database and container names must match existing resources.
- Check SDK/JDK compatibility if API signatures differ across Java SDK versions.
- `getRequestCharge()` returns the RU cost of that single read—**not** throughput RU/s.
- Never log full documents containing sensitive data.

### When Does the SDK Use Key Auth?

Some legacy environments rely on Cosmos DB account keys or connection strings. If used, store them in Key Vault/secrets, rotate them, restrict scope, and never commit them to repositories. For new apps, prefer Microsoft Entra identity and RBAC wherever supported.

## 27. Java SDK: Partition-Scoped Query and Total RUs Across Pages

To measure multi-page query costs, iterate pages via `CosmosPagedIterable` and `FeedResponse` in compatible SDK versions. Illustrative example:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.util.CosmosPagedIterable;

CosmosQueryRequestOptions options = new CosmosQueryRequestOptions()
    .setPartitionKey(new PartitionKey("tenant-A"));

String query = "SELECT * FROM c WHERE c.status = 'PAID'";

CosmosPagedIterable<CosmosRuDemo.Order> results =
    container.queryItems(query, options, CosmosRuDemo.Order.class);

double totalRu = 0.0;
long count = 0;

for (FeedResponse<CosmosRuDemo.Order> page :
        results.iterableByPage()) {
    totalRu += page.getRequestCharge();
    count += page.getResults().size();
}

System.out.printf("Items=%d, total query RU=%.2f%n", count, totalRu);
~~~

This is a **snippet** inside a method where `container` is already initialized. Supply class wrappers, imports, schemas, and compatible SDK versions. Use **parameterized queries** for user input; the literal `'PAID'` is illustrative only.

### Reading One Page Does Not Represent the Whole Query

If a result set spans 50 pages, the first page's request charge does not reflect the full cost of a report. Conversely, do not drain every page if the UI only needs page one—use continuation tokens to paginate on demand.

### Diagnostics

When troubleshooting 429s or high latency, SDK diagnostics surface retries, transport timings, partition routing, contacted regions, and request timelines. **Emit only approved diagnostic fields**, since raw diagnostics can contain URIs, partition metadata, or sensitive application details.

## 28. Monitoring with Azure Monitor, Metrics, and Alerts

Key signals:

| Signal | Purpose |
|---|---|
| Total Request Units | Total RUs consumed over time |
| Normalized RU Consumption | Normalized RU utilization per resource, partition, and region |
| Throttled requests / 429 count | Frequency of capacity throttling |
| Request count and status codes | Traffic volume and error patterns |
| Server-side latency | Service processing latency |
| Client-side p95/p99 latency | End-to-end user experience including retries and network |
| Data storage | Item and index storage size and growth rate |
| Provisioned/autoscale throughput | Allocated or maximum configured capacity |
| Physical partition distribution | Detecting hot partitions |
| Region availability/failover | Regional continuity and latency tracking |
| Cost by meter | Auditing provisioned, serverless, storage, network, and backup charges |

Exact metric names, dimensions, and availability vary by account type and API. In the Azure Portal, open your Cosmos DB account → **Metrics** and filter by database, container, partition, or region where supported. Never assume every metric is published at 1-second granularity or for every account tier.

### Listing Metric Definitions via Azure CLI

~~~bash
ACCOUNT_ID=$(az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$ACCOUNT_ID" \
  --output table
~~~

Once you know the exact published metric names, run `az monitor metrics list` with the verified metric name and time range. Never query an invented metric name and interpret `0` as zero RU consumption.

### Tie Alerts to SLOs

1. 429s exceed baseline over a window **alongside p95 latency spikes** or actual request failures.
2. Normalized RU Consumption hovers near 100% on one or more partitions for several minutes.
3. RU/op of a critical query jumps after a deployment.
4. Total Request Units or serverless consumption spikes abnormally.
5. Autoscale repeatedly hits `Tmax`.
6. Data storage or backup costs exceed budgets.
7. Private networking or authorization errors rise (kept distinct from throttling).
8. Regional availability or failover health anomalies appear.

**A single 429 is not automatically a severe incident.** Trigger alerts based on user impact, sustained saturation, retry overhead, and application SLAs.

## 29. Benchmarking Model for Choosing a Throughput Mode

A useful benchmark simulates a **representative workload**, not just 1 KiB point reads against an empty container.

### Preparation

- Sufficient data volume and realistic partition key skew.
- Production-like item sizes, fields, and indexing policies.
- Realistic mix of reads, writes, queries, and deletes.
- Representative client regions, network mode, and consistency level.
- Second-by-second/minute-by-minute peak bursts, not just flat average QPS.
- Long enough run duration to cover warm-up, burst, and recovery phases.
- Bounded retry policies, concurrency limits, and connection settings.

### Measurements to Collect

| Measurement | Unit | Why |
|---|---|---|
| Business operations/s | ops/s | Actual completed throughput |
| Consumed RU/s | RU/s | Real capacity demand |
| RU/op by use case | RUs | Tune individual access paths |
| 429 ratio | % attempts | Throttling / saturation rate |
| Client p50/p95/p99 | ms | User-facing SLO compliance |
| Normalized RU by partition | % | Detect hot keys |
| Physical partition count/distribution | count | Observe scaling behavior |
| Autoscale capacity / billable peak | RU/s | Verify cost efficiency |
| Total serverless RUs consumed | RUs | Compute pay-per-request cost |
| Storage, index, and network | GB, requests | Track secondary costs |

### Run Three Scenarios

1. **Steady baseline:** Run continuously for hours to measure manual utilization and baseline cost.
2. **Short bursts:** Ramp several-fold quickly; observe autoscale responsiveness and serverless 429s.
3. **Skewed key load:** Direct 80% of requests to one tenant to observe partition saturation.

Only commit to a capacity model once all three pass SLOs at an acceptable cost. **Never optimize solely for cost per million RUs** while ignoring 429s and tail latency.

## 30. Case Study: Multi-Tenant Retail Platform

### Context

A SaaS platform stores orders for 3,000 tenants in Azure Cosmos DB for NoSQL:

- 95% of the time it consumes roughly 350 RU/s.
- Daily peaks reach 4,000 RU/s, with promotional bursts hitting 7,000 RU/s.
- One large tenant drives 40% of writes during promotions.
- The Java application runs on Azure Container Apps.
- Data is accessed from one primary region; DR has separate requirements.
- Internal API SLAs enforce a team-defined p95 latency target.

### Initial Options

**Manual 8,000 RU/s:** Provides peak headroom when well-distributed, but pays for full capacity around the clock; weigh cost against SLO value.

**Autoscale `Tmax` ~8,000 RU/s:** Fits measured peaks well, though autoscale pricing and peak-hour charges must be modeled. If the hot tenant piles onto one logical partition, 429s can still occur despite the high max.

**Serverless:** Saves provisioned costs during quiet hours, but requires verifying throughput limits, regional/account capabilities, and actual RU costs during bursts. Do not pick serverless blindly if burst behavior or SLIs cannot be met.

### Hot-Tenant Mitigation Plan

1. Measure `RU/op` for that tenant's writes.
2. Inspect normalized RUs per partition.
3. Evaluate splitting the workload with buckets or hierarchical keys where semantics allow.
4. Apply per-tenant API rate limits and queue smoothing for batch writes.
5. Evaluate dedicated containers or tenant isolation if noisy-neighbor effects threaten the platform.
6. Re-benchmark before raising provisioned RU/s.
7. Track per-tenant costs and access without logging raw sensitive keys.

### Architecture Diagram

~~~mermaid
flowchart LR
  C["Multi-tenant clients"] --> API["Java API / Container Apps"]
  API --> CACHE["Optional cache"]
  API --> DB["Cosmos DB for NoSQL"]
  DB --> P1["Physical partition A"]
  DB --> P2["Physical partition B"]
  DB --> P3["Physical partition C"]
  API --> Q["Service Bus / Queue for batch writes"]
  Q --> W["Idempotent workers"]
  W --> DB
  DB --> MON["Azure Monitor: RUs, 429s, partitions"]
~~~

Caching reduces reads while introducing **cache invalidation, consistency, and cost** trade-offs. Queue smoothing flattens bursts, though it does not raise the physical throughput ceiling of one hot logical partition. Measure each mitigation independently.

## 31. Lab Exercise: Measuring RUs and Choosing a Model

> **Safety:** Commands that create accounts/containers, raise RU/s, or run load tests can incur charges and trigger throttling. Use only authorized lab resource groups and accounts; never run experiments against production or shared accounts without approval.

### Part A — Observe and Classify

1. Run `az account show` to verify the active subscription.
2. Run `az cosmosdb show` to inspect account type, capabilities, regions, and consistency.
3. Inspect database and container throughput; distinguish dedicated from shared.
4. Record the partition key and indexing policy of a lab container.
5. Determine whether the account is manual, autoscale, or serverless via resource properties or the Portal.
6. List available metrics in Azure Monitor and distinguish RU/s from Total RUs.

### Part B — Sample Data and Java SDK

1. Prepare a JSON dataset with `id`, `tenantId`, `status`, and `totalAmountMinor`.
2. Write 100–1,000 items using an approved script/SDK into a lab container.
3. Point-read items by `id` + `tenantId` and record the RU charge.
4. Run a partition-scoped query and sum total RUs across all pages.
5. Run a cross-partition query in the lab to compare RUs and latency (at small, authorized scale only).
6. Insert a larger item and observe how write RUs change.
7. Run an `ORDER BY` query and inspect indexing policies before and after tuning.
8. Collect client latency, status codes, and diagnostic retry counts without logging sensitive payloads.

### Part C — Formula-Based Mode Comparison

Assume 100,000 reads/day averaging 1.2 RU/read, 20,000 writes/day averaging 7 RU/write, and 2,000 query pages/day averaging 18 RU/page.

1. Compute **daily consumed RUs**.
2. Compute **monthly consumed RUs** for an assumed number of days.
3. If all traffic concentrates into 5 minutes per day, compute approximate peak RU/s.
4. Propose a manual RU/s level with headroom assuming even partition spread.
5. Propose an autoscale `Tmax` based on peak demand plus buffer.
6. Write the serverless cost expression using `P_serverless`.
7. Write manual and autoscale cost expressions using symbolic unit rates and billable capacities—**do not invent unverified prices**.
8. Explain why two workloads with identical monthly total RUs can need vastly different peak RU/s.
9. Evaluate a hot tenant receiving 90% of requests: will raising total throughput alone solve it?
10. Conclude which model fits best and list remaining risks to test.

### Part D — Monitoring and 429 Incident Drill

1. Build a dashboard for total RUs, 429s, latency, normalized RUs per partition, and cost.
2. Within lab bounds, ramp traffic in a controlled way to observe throttling.
3. Inspect `x-ms-retry-after-ms` and SDK diagnostics when 429s occur.
4. Observe automatic retries and client p95 latency.
5. Reduce concurrency or optimize a costly query, then measure the improvement.
6. Adjust throughput if needed per lab procedure and inspect cost impact.
7. Document a runbook for when serverless or autoscale hits capacity limits.
8. Clean up personal lab resources per authorization, verifying whether storage, backups, or monitoring still accrue fees.

### Self-Check Questions

**Question 1.** How do RUs and RU/s differ? Can you assume 1 RU = 1 request in all cases?

**Question 2.** Why can reading an item by `id` and partition key consume fewer RUs than querying for the same item?

**Question 3.** Does manual provisioned throughput bill by actual consumed RUs or by provisioned RU/s over time?

**Question 4.** Is autoscale `Tmax` a cap on RU/s or on total daily RUs consumed?

**Question 5.** Does serverless guarantee zero 429 errors and unlimited burst capacity?

**Question 6.** Why can Normalized RU Consumption on one physical partition hit 100% before the container exhausts total RU/s?

**Question 7.** How does database shared throughput differ from dedicated container throughput regarding noisy neighbors?

**Question 8.** Why isn't serverless simply autoscale with `Tmax=0` when idle?

**Question 9.** What do `x-ms-request-charge` and `x-ms-retry-after-ms` indicate?

**Question 10.** If a query returns 20 pages, is measuring only the first page's RUs enough to estimate report cost?

**Question 11.** Adding indexes helps reads, so how does it affect writes?

**Question 12.** One tenant has a hot logical partition; will raising container-wide RU/s always fix it?

**Question 13.** When the SDK automatically retries after a 429, why can API p95 latency still climb even if requests ultimately succeed?

**Question 14.** How can changing the consistency level impact RUs, latency, and correctness?

**Question 15.** In multi-region setups, why must throughput and cost be checked per region rather than using one global RU/s figure from a slide?

**Question 16.** If an account currently runs serverless but needs higher multi-region throughput, what limits and migration paths must be checked?

**Question 17.** When using a managed identity, why doesn't `Contributor` on the resource group necessarily grant permission to read items?

**Question 18.** Which metric is critical for distinguishing insufficient total RU/s from a hot partition?

**Question 19.** Why is counting application requests (`count()`) insufficient for cost estimation when RU/op varies widely?

**Question 20.** How can you approximate the break-even point among manual, autoscale, and serverless without fabricating unit prices?

**Completion criteria:** Learners accurately explain RUs vs. RU/s, make justified manual/autoscale/serverless choices, calculate a workload matrix, measure request charges in the Java SDK, inspect throughput via CLI, diagnose hot partitions and 429s, and design monitoring and cost controls.

## Conclusion

**Request Units** are the essential lens for understanding cost and processing capacity in Azure Cosmos DB for NoSQL, yet **RUs per request** must never be confused with **provisioned RU/s** or total monthly RUs. To design accurately, measure `request charge` per use case alongside operations per second, peak bursts, and partition keys.

**Manual provisioned throughput** suits steady, predictable loads; **autoscale** fits fluctuating workloads within a configured ceiling and floor; and **serverless** fits low or intermittent traffic billed by consumed RUs within supported account and region bounds. Whichever mode you choose, reliable scale and cost control require a **well-distributed partition key, optimized queries, deliberate indexing and consistency settings, safe 429 retries, RU/latency/partition monitoring, and clear budgets**.
