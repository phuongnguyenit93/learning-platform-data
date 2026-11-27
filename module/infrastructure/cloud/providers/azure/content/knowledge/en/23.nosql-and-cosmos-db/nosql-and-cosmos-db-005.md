# Consistency Levels and Read/Write Trade-Offs

A customer adds a product to their shopping cart on their phone and then opens the website on their laptop. If the application reads data from a replica in a different Azure region, will the newly added item show up yet? A booking site might tolerate view counts lagging by a few seconds, but it cannot afford to confirm two buyers holding the exact same ticket. These are questions of **data consistency**, paired with write correctness.

**Azure Cosmos DB** is a globally distributed database service where data replicas can span multiple regions. With **Azure Cosmos DB for NoSQL**, architects choose among **five consistency levels**: **Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual**. Stricter levels offer stronger freshness and ordering guarantees, at the potential trade-off of higher latency, reduced availability/scalability, higher Request Unit consumption, and multi-region topology constraints.

The key takeaway: **Consistency levels define what values read operations may observe relative to committed writes.** They **do not replace** transactions, version checks, business locks, authorization, or conflict resolution strategies when multiple writers exist.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the **CLOUD_PROVIDERS_AZURE** module. Across the Azure path—from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data to deployment, monitoring, security, and cost control—this forms the foundation for choosing business-aligned read/write strategies.

## Learning Objectives

After this lesson, you will be able to:

1. Explain consistency and distinguish **replication lag**, **stale reads**, and concurrent write conflicts.
2. Compare all five levels: Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual.
3. Explain read-your-writes, monotonic reads, consistent prefix, linearizability, and session tokens.
4. Evaluate the difference between **account default consistency** and requesting weaker read levels where supported by the API/features.
5. Understand trade-offs across data freshness, read latency, RUs, availability, and multi-region topology.
6. Select consistency levels for shopping carts, product catalogs, dashboards, telemetry, and financial workflows.
7. Distinguish consistency from **transactional batches**, **ETag/optimistic concurrency**, and **multi-region write conflict resolution**.
8. Safely verify configuration, telemetry, SDK sessions, and failure scenarios.

## 1. Why Can a Distributed Database Return Stale Data?

When Azure Cosmos DB maintains multiple replicas, every write must propagate through the service's replication protocol. Replicas and regions may not observe the same version at the exact same instant.

~~~text
                    Azure Cosmos DB

             Client A writes cart v2
                        |
                        v
              Write/replication path
                        |
             +----------+----------+
             |                     |
             v                     v
        Region East             Region West
        Replica has v2          Replica still has v1
             |                     |
             |                     v
             |               Client B reads
             |                     |
             +---------------------+

If consistency allows stale reads:
  Client B may observe v1 while replication catches up.
~~~

This diagram illustrates **data propagation delay** only; actual write paths, quorums, and topology depend on the account, partition, regions, and configured consistency.

### Simple Version Timeline

~~~text
12:00:00  Cart = [A]            (v1)
12:00:01  Client appends B      (v2)
12:00:02  One replica still holds v1
12:00:03  Replica catches up to v2
~~~

If a read occurs at 12:00:02 and the consistency model allows stale reads, it may return **[A]** even though the new write already succeeded elsewhere. Under stricter guarantees, the service enforces conditions to avoid violating the promise—sometimes requiring reads to wait or follow different routing paths.

### Replication Lag Is Not a Write Error

- **Replication lag:** A replica has not yet observed a recently committed write.
- **Stale read:** A client receives an older version than the latest committed state.
- **Write conflict:** Two writers update the same item with different values concurrently.
- **Lost update:** A later write unknowingly overwrites an earlier write without concurrency protection.
- **Application invariant violation:** A business rule—such as seat count never going negative—is broken.

Consistency levels relate closely to the first two items, yet do not by themselves solve the remaining three.

## 2. Five Consistency Levels in Azure Cosmos DB

From **strictest** to **most relaxed in replica observation**:

<table>
<tr><th>Order</th><th>Consistency Level</th><th>Core Guarantee</th></tr>
<tr><td>1</td><td><b>Strong</b></td><td>Reads observe the latest committed data under linearizable semantics promised by the service</td></tr>
<tr><td>2</td><td><b>Bounded Staleness</b></td><td>Reads may lag, but bounded by configured K versions or T time interval, preserving prefix ordering</td></tr>
<tr><td>3</td><td><b>Session</b></td><td>Strong consistency guarantees for operations within the same session, notably read-your-writes</td></tr>
<tr><td>4</td><td><b>Consistent Prefix</b></td><td>Reads may lag, but never observe write history out of order within guaranteed bounds</td></tr>
<tr><td>5</td><td><b>Eventual</b></td><td>If writes stop, replicas eventually converge; no freshness or ordering guarantee prior to convergence</td></tr>
</table>

**Session** is the common default consistency level on an Azure Cosmos DB for NoSQL account unless configured otherwise. “Default” does not mean every arbitrary SDK call guarantees read-your-writes if the application drops the session token.

### Qualitative Trade-Off Matrix

| Level | Freshness Guarantee | Observed Ordering | Relative Read Cost / Latency | Typical Use Cases |
|---|---|---|---|---|
| **Strong** | Highest; never returns stale data relative to linearizability guarantee | Strict | Usually higher; subject to topology constraints | Reads requiring latest committed state where supported |
| **Bounded Staleness** | Bounded by K/T | Consistent prefix | Usually higher than weaker levels | Quantitative staleness limits needed |
| **Session** | Read-your-writes within a session | Session guarantees | Balanced for most apps | Shopping carts, user profiles, typical SaaS |
| **Consistent Prefix** | No fixed time bound | Never observes out-of-order history | Usually flexible | Event feeds needing order while tolerating lag |
| **Eventual** | No fixed time bound | No prefix ordering guarantee | Usually flexible | Dashboards, counters, freshness-insensitive data |

“Higher/lower” in the table reflects **design direction**, not a fixed latency or RU SLA. Always benchmark against your actual workload, regions, and API.

## 3. Essential Terminology

| Term | Plain-Language Meaning |
|---|---|
| **Read-your-writes** | After your own successful write, subsequent reads within the guarantee scope never return an older value |
| **Monotonic reads** | Once a session observes a newer version, subsequent reads never regress to an older version |
| **Monotonic writes** | Writes issued by a session are applied in order |
| **Writes-follow-reads** | Writes in a session are ordered after states previously read by that session |
| **Consistent prefix** | If history has A then B, a reader never sees B without A under guaranteed ordering semantics |
| **Linearizability** | Operations appear to execute atomically at a single point in real-time order |
| **Staleness bound** | Maximum lag allowed between read state and latest committed writes |
| **Session token** | Consistency progress token used to preserve session guarantees across requests |
| **Commit** | A write accepted by the service per its consistency and replication protocol |

### Read-Your-Writes Does Not Mean “Every User Sees It Immediately”

~~~text
User A (session A):
    write cart v2 -> read cart -> observes at least v2 per session guarantee

User B (session B):
    read cart immediately after -> may still see v1 if consistency allows
~~~

Session consistency delivers the “I saved it, so I see it” expectation without forcing every independent session worldwide to coordinate synchronously.

### “Ordering” Has Scope Boundaries

Consistency levels govern replica and version observation within the service's model. They do **not** automatically enforce global business ordering across multiple containers, partitions, queues, or external systems. Workflows spanning Cosmos DB, Event Hubs, and Service Bus require dedicated orchestration.

## 4. Strong Consistency: Prioritizing Freshness and Order

**Strong consistency** ensures reads return the latest committed data under linearizable semantics provided by Azure Cosmos DB. When a read runs at this level, the service cannot arbitrarily return a version older than the committed state guaranteed to be visible.

~~~text
Client A:
  writes item version = 10
  receives success

Client B:
  reads after write has completed
  -> must satisfy Strong guarantee for version = 10
~~~

### When to Consider Strong?

- Reads must make decisions strictly against the most recently committed write.
- Business rules cannot tolerate reading an older version after a confirmed write.
- The system has strict consistency requirements and can accept the supported topology/tier constraints.

### Trade-offs

Strong consistency can increase read latency and RU consumption due to stricter coordination requirements. In geo-distributed accounts, cross-replica coordination overhead and regional restrictions can be substantial. **Strong has restrictions with multi-region write accounts and certain topologies**; never assume Strong can be turned on for every account or region layout.

### Strong Still Does Not Replace Business Transactions

Suppose two workers both read remaining seats = 1, and both send updates to decrement it to 0. Even if every read uses Strong, a separate “read then write” sequence still races without concurrent write protection.

Fixes include **optimistic concurrency with ETags**, conditional updates, or **transactional batches** for operations within the same logical partition, depending on the scenario.

## 5. Bounded Staleness: Allowing Lag Within Fixed Bounds

**Bounded Staleness** allows clients to read older versions within a configured **staleness window**. Cosmos DB expresses the bound via two parameters:

- **K (`maxStalenessPrefix`):** Maximum number of item versions/operations reads may lag behind.
- **T (`maxIntervalInSeconds`):** Maximum time interval reads may lag behind.

The service enforces mechanisms so reads stay within these configured bounds while preserving **consistent prefix** ordering.

~~~text
Version chain: v1 -> v2 -> v3 -> v4 -> v5

Reader using Bounded Staleness:
   May read an older version within allowed K/T bounds.
   Must not exceed the configured staleness bound.
   Must never observe out-of-order history.
~~~

### Thinking About K and T

Suppose business compliance states: “reporting views must never lag by more than ~5 minutes, with bounded skipped versions.” That makes Bounded Staleness worth **evaluating**. However, actual K and T values must fall within service-enforced ranges, especially in multi-region accounts.

**Never hardcode K=5, T=5 seconds across every setup.** Azure enforces valid parameter ranges and topology support; verify against current documentation and APIs when configuring.

### Trade-offs

- Stronger quantitative freshness guarantees than Session, Consistent Prefix, or Eventual.
- Incurs additional coordination overhead to enforce the bound.
- Carries topology and write-region restrictions; check the support matrix.
- Not a default pick for every dashboard: many systems tolerate Eventual or Session at lower cost and higher liveness.

### How Does Bounded Staleness Differ from Session?

**Session** guarantees a user sees what **their own session wrote**, without setting a global staleness time bound across independent sessions. **Bounded Staleness** caps staleness globally across readers and writers within the service's guarantee scope.

## 6. Session Consistency: The Practical Balanced Default

**Session** is a pragmatic choice for web and mobile applications:

1. A user updates their profile.
2. The API writes successfully to Cosmos DB.
3. The same session reads the profile back.
4. The user expects to see the update they just saved.

Session consistency provides **read-your-writes**, **monotonic reads**, **monotonic writes**, **writes-follow-reads**, and **consistent prefix** within the session whenever the token/context is preserved.

~~~text
Shopping cart application:

Session S:
  write cart: [A]         -> v1
  write cart: [A, B]      -> v2
  read cart               -> must observe state
                             satisfying session S guarantees.

Different Session T:
  read cart in another region -> may observe v1
                                 while replicas catch up.
~~~

### Why Is Session the Sweet Spot?

It matches user expectations—seeing your own changes immediately—without imposing Strong coordination costs on every unrelated reader.

**Session can still return stale data for writes from other sessions.** Exchange rates or inventory updated continuously by other writers must be evaluated against business requirements.

## 7. Session Tokens and Request Paths

Cosmos DB uses a **session token** to track the consistency progress needed for session guarantees. The SDK normally manages tokens automatically for operations executed through a long-lived **`CosmosClient`**.

~~~text
Client / API instance A
        |
        | Write item -> receives session progress/token
        v
Azure Cosmos DB
        |
        v
Client / API instance A
        |
        | Read with same session context
        v
Observes data satisfying read-your-writes
~~~

### The Problem with Multi-Instance Stateless Apps

~~~text
Mobile request 1
     |
     v
API instance A -> write -> session token held at A

Mobile request 2
     |
     v
API instance B -> read; B lacks the session token from A

Do not assume B automatically shares A's session guarantee.
~~~

If an app requires read-your-writes **across API instances, Functions invocations, or separate services**, design a mechanism to persist or propagate the **session token/context** using supported SDK/API features.

### Best Practices

- Reuse **`CosmosClient`** properly rather than creating a new client per request.
- Map out read and write regions for each service.
- Test session token behavior when requests hop across backend instances.
- When passing tokens across tiers, protect integrity, avoid logging them, and never treat them as credentials.
- Test load-balancer failover where a read hits a different backend instance immediately after a write.

**A session token is not a Microsoft Entra ID access token.** It tracks consistency progress, never authentication or data authorization.

## 8. Consistent Prefix: Preserving Order, Accepting Lag

**Consistent Prefix** guarantees reads observe a **valid prefix of the write history**—never seeing later updates before earlier ones within the guaranteed scope.

~~~text
Producer writes in order:
    Event A -> Event B -> Event C

Consistent Prefix may show:
    []
    [A]
    [A, B]
    [A, B, C]

It must never present:
    [B, C] without A in the same guaranteed ordered history
~~~

This example is an **observation-ordering metaphor**, not a claim that Cosmos DB automatically returns a globally ordered array of events across all partitions.

### When to Use It?

- Activity feeds or event logs where out-of-order updates confuse users.
- Analytics consumers needing causally valid ordering while tolerating lag.
- Read models that do not require per-user read-your-writes.

### No Staleness Time Bound

Consistent Prefix does not promise “at most three seconds behind.” If business rules demand a quantitative bound, evaluate Bounded Staleness where topology and cost permit.

### How Is Session Stronger Than Prefix?

Session adds per-session guarantees—most notably **read-your-writes** and **monotonic reads**. Consistent Prefix does not provide those guarantees.

## 9. Eventual Consistency: Converging Over Time

**Eventual** is the weakest of the five levels. Once new writes stop under normal operation, replicas eventually converge to the same state per service mechanics.

~~~text
Write v3
   |
   +-- Replica A already has v3
   +-- Replica B still has v2
   +-- Replica C still has v1

After replication converges:
   A, B, and C all reflect the resolved state.
~~~

### What Eventual Does Not Promise

- No fixed upper bound on staleness in the level contract.
- Does not guarantee read-your-writes.
- Does not guarantee monotonic reads like Session.
- Does not guarantee strict prefix ordering like Consistent Prefix.
- Does not guarantee business invariants or exactly-once processing.

### When Is It Appropriate?

- Aggregate dashboards where slight lag is acceptable.
- Observability/telemetry views that do not require instant latest values.
- Cache-like read models or reference catalogs insensitive to brief staleness.
- Counters or view counts designed for eventual convergence.

### Common Pitfall

Never rely on Eventual for a business check like “if 1 ticket remains, confirm purchase” without atomic conditional writes or transactions. A stale read can make multiple clients **all believe stock remains**, whereas oversell prevention requires conditional updates or an appropriate domain model.

## 10. Viewing All Five Levels Against One History

Suppose item **`stock`** is updated sequentially:

~~~text
v1: stock=10
v2: stock=9
v3: stock=8
v4: stock=7
~~~

In a distant region, replicas may not be fully caught up yet:

| Level | What Can a Reader Observe? |
|---|---|
| **Strong** | State matching the latest committed write under linearizability |
| **Bounded Staleness** | An older state still within K/T bounds and in prefix order |
| **Session** | At least as recent as writes from the reader's own session; writes from other sessions may lag |
| **Consistent Prefix** | Any valid historical prefix, with no freshness bound or read-your-writes guarantee |
| **Eventual** | May see stale state with none of the stricter freshness or ordering promises |

**Never conclude** “Strong always returns v4” before v4 commits, or “Session always returns v4” when v4 was written by another session. Always distinguish request timing, commit acknowledgment, and guarantee scope.

## 11. Consistency Is Not a SQL Transaction Isolation Level

In relational databases, you know **Read Committed**, **Repeatable Read**, or **Serializable**. Those govern transaction isolation, not one-to-one equivalents of Azure Cosmos DB consistency levels.

| Question | Relevant Mechanism |
|---|---|
| Can a remote replica read return stale data? | **Consistency level** |
| Will two concurrent writers overwrite each other on one item? | **ETag / optimistic concurrency**, conflict resolution |
| Do two changes commit atomically together? | **Transactional batch / transaction scope** |
| Can one tenant view another tenant's item? | **Authentication + authorization + application checks** |
| Will processing a request twice duplicate side effects? | **Idempotency / durable ledger** |
| How much data can be lost in a major regional outage? | **Replication topology, backup/DR, RPO/RTO** |

Selecting **Strong** does not turn writes across multiple logical partitions into a single atomic transaction.

## 12. Transaction Scope and Logical Partitions

In Azure Cosmos DB for NoSQL, **transactional batch** executes multiple operations atomically **within the same logical partition key**, subject to API rules and limits.

~~~text
Partition key: tenantId = tenant-A

Item order-1
Item order-summary
Item inventory-reservation

If same logical partition and valid operations:
   Can be designed as a transactional batch.

If across different partition keys:
   Cannot be treated as one atomic batch.
~~~

### Partition Key Design Affects Correctness

An ordering workflow that updates an order and a reservation atomically might evaluate partitioning by **orderId** or a fitting aggregate. However, packing too many items into one logical partition introduces hot-partition risks and size/throughput limits.

**Never design a partition key solely for consistency.** Balance transaction locality, throughput distribution, query patterns, and growth headroom.

### Transactional Batch Does Not Create Global Strong Consistency

A batch ensures its constituent operations commit or roll back together. Readers in remote regions remain governed by the account/request consistency level.

## 13. ETags and Optimistic Concurrency Control

Every item carries a system **`_etag`** property. On updates, clients can require the change to **succeed only if the ETag still matches** using SDK/API conditional requests.

~~~text
Item: {id: CART-01, quantity: 1, _etag: E1}

Worker A reads E1
Worker B reads E1

Worker A updates quantity=2 with condition ETag=E1
  -> succeeds; item becomes E2

Worker B updates quantity=3 with condition ETag=E1
  -> rejected because item is no longer E1
  -> must re-read, recompute, and safely retry
~~~

### Why Is This Still Needed Even with Strong Enabled?

Two workers can both read the latest version at the same moment, and then one writes before the other. Without a conditional check, the second write silently clobbers the first. **ETags protect write decisions based on item version**, an orthogonal layer from read consistency.

### Handling HTTP 412

When an `If-Match` ETag check fails, Cosmos DB returns **HTTP 412 Precondition Failed**. Your application should:

1. Never immediately retry blindly with the stale ETag in an infinite loop.
2. Re-read the latest item/state at the required consistency.
3. Re-evaluate business logic and invariants.
4. Attempt a new conditional update within a bounded retry count.
5. Surface a conflict error if changes cannot be merged.

Never default to careless client-side “last writer wins” when updates carry financial impact.

## 14. Multi-Region Reads and Locality

Cosmos DB can distribute data across multiple Azure regions; clients can read from nearby regions to cut network round-trips when the topology and consistency permit.

~~~text
             Write region
                Region A
                   |
         Replicate to read regions
             /             \
            v               v
         Region B          Region C
            ^                 ^
            |                 |
        Client B          Client C
~~~

### Common Trade-offs

- Reading from a nearby region typically lowers network latency.
- A local read replica may lag slightly in version.
- Stronger consistency levels may require extra coordination or restrict read/write paths.
- Inter-region link disruptions affect configurations differently.
- Measure RUs and latency against the actual regions the SDK contacts.

### Preferred Regions

Cosmos DB SDKs support configuring preferred regions / region routing per API version. If your app runs in AKS in Region B, listing preferred regions reduces latency and aids failover.

However, **preferred regions do not guarantee the newest data**. Freshness still depends on consistency, session tokens, replica health, and service rules.

### Strong and Multi-Region Writes

**Strong** is not universally supported with **multiple write regions**. In Cosmos DB, strict levels like Strong and Bounded Staleness carry restrictions on multi-write accounts and topologies; verify Azure's supported configurations before designing deployment layouts.

## 15. Multi-Region Writes and Conflicts

In supported multi-region write setups, two regions can accept updates to the same item nearly simultaneously. When values diverge, the system needs **conflict resolution**.

~~~text
Region A: update item quantity = 4
Region B: update item quantity = 5
        \               /
         \             /
          v           v
          Conflict resolution
                  |
                  v
             Final state
~~~

**Consistency levels do not decide the business correctness of a conflict.** A last-writer-wins or custom resolution policy (where supported) may work for user profiles, yet be unsafe for monetary balances.

### Business-Level Risks

If two regions decrement inventory based on stale local reads, Session or Eventual alone will not prevent overselling. Options include:

- Single authoritative writer / partition ownership for scarce resources.
- Conditional updates / ETags within supported scopes.
- Idempotency keys and clear transaction boundaries.
- Domain-defined conflict handlers.
- Reconciliation when downstream systems diverge.

Never promise a **globally serializable business transaction** just by enabling a replicated database.

## 16. Consistency and Request Units (RUs)

Azure Cosmos DB uses **Request Units (RUs)** to measure the resource cost of reads, writes, and queries against provisioned capacity. Operation RUs depend on:

- Item size.
- Operation type: point read, query, create, replace, patch, delete.
- Indexing policy and write overhead.
- Number of partitions scanned by a query.
- Query complexity and result set size.
- Consistency level and related service mechanics.

### How Consistency Level Affects Read RUs

In Cosmos DB for NoSQL, **Strong** and **Bounded Staleness** typically incur **higher read RU charges** than **Session, Consistent Prefix, and Eventual** for identical data and conditions. Azure documentation commonly describes stronger reads costing roughly **double** the weaker group in standard cases, though you should never apply that as a rigid financial multiplier for every query or topology.

~~~text
Same point read under identical illustrative conditions:

Session / Eventual:
   Lower reference read RU cost

Strong / Bounded Staleness:
   Potentially higher read RU cost

Actual figures:
   Measure Request Charge on your workload via SDK and metrics.
~~~

### Consistency Is Not the Only Cost Driver

A cross-partition query scanning thousands of items costs far more RUs than a point read, even when both run at Eventual. Before relaxing consistency to save RUs:

1. Switch to **point reads** whenever `id` + partition key are known.
2. Inspect partition keys and eliminate unnecessary cross-partition queries.
3. Tune the indexing policy.
4. Optimize data models and item sizes.
5. Measure real RUs and latency.

## 17. Latency, Throughput, and Availability

Read-heavy workloads balance three competing goals:

1. **Freshness:** Does the read reflect the latest write?
2. **Latency:** How fast is a read, especially at p95/p99?
3. **Availability:** Do reads keep succeeding if a replica, region, or link degrades?

### Strong: Strict Guarantees Have a Price

When read paths are constrained or cross-replica coordination is needed, Strong can raise response times and impose availability/topology constraints. Weigh this carefully against SLAs.

### Session: Great User Experience

For most web apps, Session lets users see their own mutations while retaining more flexibility than Strong—provided the app propagates session tokens properly.

### Eventual: Higher Flexibility, Weaker Freshness

Eventual works well for lag-tolerant read models at massive scale. However, never use it to infer **write correctness**.

### Avoid Hardcoding Fixed Millisecond Numbers

There is no universal rule like “Strong = 100 ms, Eventual = 5 ms.” Azure regions, client placement, replica count, item size, caching, network quality, and RU pressure cause wide variance. Load-test per region and during peak windows.

## 18. Read-After-Write Across Multiple App Instances

A common user flow:

~~~text
Mobile POST /cart/items
      |
      v
API Instance A -> Cosmos DB writes cart v7
      |
      v
HTTP 200 success

Mobile GET /cart
      |
      v
API Instance B -> Cosmos DB read
      |
      v
Must observe at least v7
~~~

### If the Account Uses Session

The application must ensure Request B carries **the required consistency context**. Reusing a `CosmosClient` inside one instance is not enough when consecutive requests hit different instances.

### Design Approaches

- Propagate session tokens/context safely across API tiers where SDK-supported.
- Consider session-consistent request routing if architecturally suitable, without relying on sticky sessions as your sole data guarantee.
- Return updated state directly in write responses to update the UI immediately, then reconcile.
- If every independent session must read the globally newest write, evaluate Strong and its supported topology.
- For critical mutations, enforce ETags/transactions rather than merely bumping consistency.

### Required Tests

1. Write to Region A.
2. Read immediately on the same SDK client/session.
3. Read via a different API instance.
4. Read in Region B using preferred regions.
5. Repeat during region switching/failover.
6. Compare item versions, ETags, and latency—not just HTTP 200 status.

## 19. Request-Level Consistency Overrides

A Cosmos DB account defines a **default consistency level**. Some SDKs/APIs let individual requests use a **weaker level** than the account default within supported bounds.

~~~text
Account default: Session
    |
    +-- Cart read: Session (inherits account default)
    |
    +-- Dashboard read: can request Eventual
                        if SDK/API supports override
~~~

**You cannot use a request override to escalate above the account default.** For example, an account defaulting to Eventual cannot turn a single read into Strong just by passing a header.

### Key Notes

- Which override levels are allowed depends on the API, SDK, and account configuration.
- Relaxing consistency on one read does not alter the account's global default.
- Verify session token behavior and routing inside your specific SDK.
- Never invent custom consistency headers unsupported by the API.
- Never treat overrides as authorization: an Eventual read still requires full authentication and RBAC.

### Do Not Compromise Correctness for Tiny RU Savings

When displaying financial balances or access controls, prioritize business guarantees. Only relax consistency after proving the app handles stale reads safely and has reconciliation.

## 20. Choosing a Level for Shopping Carts

### Requirements

Users add or remove items and must immediately see changes within the same session. Other devices can tolerate brief sync delays, provided duplicate orders are never created.

### Starting Recommendation

**Session consistency** is a strong candidate:

- Read-your-writes within the user's session.
- Rarely needs account-wide Strong consistency.
- Pairs well with point reads/writes by `id` and partition key.

### What Else You Must Implement Beyond Consistency

- Use **`_etag`** to detect two devices editing the same cart concurrently.
- Define merge semantics for concurrent item additions/removals.
- Use an idempotency key for checkout submission.
- Propagate session tokens when requests cross backend instances.
- Design the partition key by user/tenant while watching for hot partitions.

### Verification Question

If a user adds item A on their phone and opens their laptop immediately, does Session consistency across **two independent sessions** guarantee the laptop sees A? **Never assume yes** if no token/context was transferred and regions have not caught up.

## 21. Choosing a Level for Product Catalogs

A product catalog is edited a few times per day and read millions of times. Screens can tolerate brief staleness in product descriptions, but final checkout prices must be verified accurately.

### Recommendation

- **Eventual** or **Consistent Prefix** fits display read models well.
- If an admin user edits a product and needs to see the change immediately, **Session** with proper token handling works well.
- For checkout pricing, the backend must **re-validate prices at checkout** against the authoritative source and business rules.

### Caching Is a Separate Layer

Even if Cosmos DB returns fresh data under Strong consistency, a CDN or API cache with a 5-minute TTL can still serve stale prices. Database consistency **does not control Redis, CDN, or APIM cache TTLs**.

Design for end-to-end freshness:

~~~text
Cosmos DB consistency
      +
SDK caching/routing
      +
Application cache
      +
CDN / API cache
      +
Mobile offline state
      =
Actual data freshness seen by users
~~~

## 22. Choosing a Level for Dashboards and Analytics

A system writes telemetry or app events to Cosmos DB, and dashboards refresh every 10–30 seconds.

**Eventual** is often sufficient when:

- Metrics do not authorize real-time financial transactions.
- UI displays a clear **`last updated at`** timestamp.
- Short-lived discrepancies self-correct on the next refresh.

**Consistent Prefix** helps if users care about update sequence and must never see Event B appear before Event A within guaranteed ordered history.

If dashboards read from **Event Hubs → Stream Processor → Cosmos DB**, end-to-end freshness also depends on **consumer lag, checkpoints, batching/aggregation windows, and write delays**. Raising Cosmos DB consistency will not speed up an Event Hubs consumer that is 20 minutes behind.

## 23. Choosing a Level for Inventory and Financial Workflows

Reserving stock or deducting balances enforces strict invariants:

~~~text
stock = 1

Buyer A wants to buy 1
Buyer B wants to buy 1

If both simply execute:
  read stock
  if stock > 0: replace stock = stock - 1

Without concurrency control:
  overselling or lost updates can happen.
~~~

### Is Choosing Strong Enough?

**No.** Strong improves read freshness in supported topologies, yet two valid reads can still both observe `stock=1` before the first writer commits.

### Mechanisms Actually Required

1. Conditional updates using **`ETag`** or appropriate transactions.
2. Partitions/aggregates structured to protect invariants.
3. Idempotency keys and business ledgers.
4. Retries or compensation on conflicts.
5. Reconciliation with payment gateways and Service Bus.
6. Freshness checks across all upstream sources, not just Cosmos DB.

### When to Consider Another Database?

If business logic demands strong transactions spanning multiple entities, partitions, and external systems in ways awkward for Cosmos DB, re-evaluate your **data model or database engine**—such as Azure SQL Database or an event-sourcing architecture—rather than trying to solve it solely via consistency levels.

## 24. Freshness and Correctness in Event-Driven Architectures

An Azure application might follow this flow:

~~~text
API -> Service Bus Queue
        |
        v
      Worker
        |
        v
   Cosmos DB item
        |
        v
Change Feed processor
        |
        v
Search index / materialized view
~~~

### Distinct Boundaries

- Service Bus handles message delivery, locks, settlement, and retries.
- Cosmos DB handles write/read consistency and partition semantics.
- Change Feed observes mutations within its supported scope and mode.
- Search indexes carry their own replication and indexing delays.

If a user cannot find a new order in search, the culprit may be **Change Feed or search consumer lag**, not Cosmos DB Session consistency.

### Change Feed Is Not a Consistency Level

Change Feed provides a stream for reacting to mutations. It **does not** turn downstream projections into Strong consistency, nor does it create a global transaction between Cosmos DB and external systems.

## 25. Metrics to Measure

| Group | Metric / Telemetry | Meaning |
|---|---|---|
| **Request cost** | Request charge (RUs) per operation | Read/write/query resource cost |
| **Throughput** | RU/s consumed, provisioned/autoscale limits | Load relative to capacity |
| **Throttling** | HTTP 429s and `retry-after` | Are we exceeding RU budgets? |
| **Read latency** | p50/p95/p99 by region and consistency | User-perceived latency |
| **Write latency** | p50/p95/p99 by region | Transaction and API latency |
| **Replication** | Replication lag and provided regional metrics | Replica catch-up health |
| **Errors** | 412, 404, 403, 408, 429, 5xx | Classifying concurrency, auth, timeout, and quota errors |
| **Session** | Read-your-writes probes, token propagation failures | Verifying consistency context |
| **Query** | Cross-partition ratio, index metrics, query plan | RU optimization |
| **Partitioning** | Hot partitions, skew, and per-partition usage | Detecting load imbalance |
| **Business** | Duplicate orders, negative stock, stale-visible reports | Real business outcomes |

Not every row in this table is a **built-in Azure Monitor metric with that exact name**. Signals like read-your-writes violations or business stale-visible age require **synthetic probes, SDK diagnostics, and custom app telemetry**.

### Distinguishing 429s from Stale Reads

- **HTTP 429 Too Many Requests:** Throttling due to RU/s or partition saturation; check `retry-after` and SDK retries.
- **HTTP 412 Precondition Failed:** Conditional write / ETag mismatch.
- **Stale read:** Request returns **HTTP 200 OK with an older value** permitted by the active consistency level.

Never blame every delay on “Eventual consistency”; it could be a hot partition, 429 retries, networking, caching, or slow queries.

## 26. Observing RUs Instead of Guessing Costs

A clean experiment must hold variables constant:

- Identical test data and partition key.
- Identical operation type (especially point read vs. query).
- Identical SDK/runtime and client region.
- Comparable load conditions.
- Identical cache and indexing policies.
- Validly configured consistency level.

### Sample Lab Results Table

| Operation | Level | Measured RUs | Latency p95 | Notes |
|---|---|---|---|---|
| Point read of small item | Session | **Measure live** | **Measure live** | Baseline |
| Point read of same item | Strong | **Measure live** | **Measure live** | Test only if account/topology allows |
| Query with same predicate | Session | **Measure live** | **Measure live** | Watch cross-partition behavior |
| Query with same predicate | Eventual | **Measure live** | **Measure live** | When request override is supported |

Never fill in fabricated numbers and present them as official benchmarks. If the backend caches or spans multiple regions, document those conditions for fair comparisons.

### RU Capacity Is a Separate Layer

Cosmos DB offers throughput options such as provisioned RU/s, autoscale RU/s, or serverless capacity per service capabilities. **Consistency is not throughput sizing.** A Session account with insufficient RU/s still hits 429s nonstop; Strong does not stop costs from ballooning under unoptimized queries.

## 27. Azure Portal: Inspecting Account Consistency

### Step 1: Identify the Exact Resource

1. Sign in to the Azure Portal under an authorized subscription.
2. Open the Azure Cosmos DB account (API for NoSQL within scope).
3. Note the regions, read/write locations, and failover status.
4. Identify the database, container, and workload partition key.
5. Confirm the data owner and target SLO/RPO/RTO.

### Step 2: Locate Consistency Settings

Open **Default consistency** or the equivalent configuration blade in the Portal. Inspect the active level and K/T parameters if using Bounded Staleness.

**Read-only inspection only**—do not change consistency levels on production. Altering account-level consistency can affect every connected application, cost, and availability profile.

### Step 3: Inspect Operational Telemetry

Under **Metrics** or Azure Monitor:

- Total requests and HTTP status distribution.
- Normalized RU consumption and throttled requests.
- Server-side latency and available replication/availability metrics.
- Throughput and partition distribution.
- Region-specific behavior during failover events.

Pair these with SDK diagnostics and end-to-end API latency. Exact Azure Monitor metric layouts can differ by tier and API.

## 28. Azure CLI: Reading the Consistency Policy

The commands below are **read-only** against Azure configuration. Do not create accounts, alter regions, or modify consistency. Replace placeholders with authorized resources.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az cosmosdb show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<COSMOS_ACCOUNT_NAME>" \
  --query "{name:name,kind:kind,locations:locations,consistencyPolicy:consistencyPolicy}" \
  --output json
~~~

Output may resemble:

~~~json
{
  "name": "cosmos-shop-lab",
  "consistencyPolicy": {
    "defaultConsistencyLevel": "Session"
  }
}
~~~

**JSON above is an illustrative structure.** Actual responses include additional metadata; for Bounded Staleness accounts, the output includes fields like `maxStalenessPrefix` and `maxIntervalInSeconds`.

### Inspecting SQL Database and Container

~~~bash
az cosmosdb sql database show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --name "<DATABASE_NAME>" \
  --output json

az cosmosdb sql container show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --database-name "<DATABASE_NAME>" \
  --name "<CONTAINER_NAME>" \
  --output json
~~~

Verify the partition key path, indexing policy, and container settings without confusing them with account consistency level. These commands do not read item data.

### Never Run Update Commands Just to “Quickly Test”

Changing account consistency or regions affects every container and application sharing that account, carrying feature constraints and billing impacts. Any change requires an approved change plan, canary/benchmark testing, and rollback readiness.

## 29. Python SDK: Reading an Item Under Session Consistency

This example uses the **Azure Cosmos DB SDK for Python** with **`DefaultAzureCredential`**. It performs a read-only lookup without modifying data. Run only against a **lab** account and container where you hold read permissions.

### Prerequisites

- An existing Cosmos DB for NoSQL account and container.
- A test item with known **`id`** and **partition key**.
- An appropriate Microsoft Entra data-plane role, such as a supported data-reader role for Cosmos DB for NoSQL.
- Working network/DNS/Private Endpoint connectivity.
- Python and SDK libraries:

~~~bash
python -m pip install azure-cosmos azure-identity
~~~

Sample environment variables:

~~~bash
export COSMOS_ENDPOINT="https://cosmos-shop-lab.documents.azure.com:443/"
export COSMOS_DATABASE="shop-lab"
export COSMOS_CONTAINER="carts"
export COSMOS_ITEM_ID="cart-demo-001"
export COSMOS_PARTITION_KEY="tenant-demo"
~~~

### Performing a Point Read

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]
database_name = os.environ["COSMOS_DATABASE"]
container_name = os.environ["COSMOS_CONTAINER"]
item_id = os.environ["COSMOS_ITEM_ID"]
partition_key = os.environ["COSMOS_PARTITION_KEY"]

credential = DefaultAzureCredential()
client = CosmosClient(endpoint, credential=credential)

try:
    database = client.get_database_client(database_name)
    container = database.get_container_client(container_name)

    item = container.read_item(
        item=item_id,
        partition_key=partition_key,
    )

    # Do not print full customer payloads to stdout or logs.
    print({
        "id": item.get("id"),
        "partitionKey": partition_key,
        "_etag": item.get("_etag"),
    })
finally:
    client.close()
    credential.close()
~~~

**Key points:**

1. **`read_item`** executes a point read when given `id` and partition key, typically costing fewer RUs than a query.
2. The SDK uses the account, client, or request consistency configured; this code alone does not prove the account is set to Session without inspecting the account.
3. `DefaultAzureCredential` does not grant permissions by itself; you still need the proper data-plane role, tenant, and account access.
4. Reusing `CosmosClient` in long-running apps is best practice; this short lab script closes the client on exit.
5. If the item does not exist, the SDK returns 404—distinct from a stale read.
6. Never use this script to dump production payloads or extract keys/secrets.

### Session Tokens in the SDK

The SDK manages session consistency and tokens according to its documented API behavior. Do not try to scrape tokens from unstable internal attributes. For stateless apps passing tokens between services, follow the official SDK documentation, backed by tests and security controls.

## 30. Safe Read-Your-Writes Lab

The goal is to observe immediate reads after writes under the active consistency level. **Only run writes inside a lab container.** Never modify real user documents.

### Sample Document

~~~json
{
  "id": "cart-demo-001",
  "tenantId": "tenant-demo",
  "version": 1,
  "items": ["book"]
}
~~~

Assume partition key **`/tenantId`**; the actual container must have been created with that partition key upfront.

### Procedure

1. Verify the account's default consistency and regions via CLI or Portal.
2. Using the same `CosmosClient`/session, read item `v1`.
3. Write `v2` in the lab only, using conditional updates / ETag where appropriate.
4. Immediately read back from the same client/session.
5. Read from a separate client/process lacking the prior request's session token.
6. If multi-region is enabled, repeat from a client reading in another region where permitted.
7. Record version, `_etag`, latency, RUs, and any errors.
8. Evaluate outcomes against the level's guarantees—do not call it a bug if two independent sessions observe different values allowed by that consistency level.

### Acceptance Matrix

| Test | Expected Behavior |
|---|---|
| Same-session write then read under Session | Satisfies read-your-writes when session context is preserved |
| New process without token | Cannot assume the same session guarantee |
| Eventual read after write | May return stale data during convergence window |
| Competing ETag conditional updates | One update fails with 412 once ETag changes |
| Strong read (if supported by account) | Satisfies configured Strong guarantee |
| RU/latency comparison | Real measurements captured under identical conditions |

If a handful of runs show zero stale reads, **do not conclude Eventual is just as strong as Strong**. Under low load or in a single region, replication often catches up faster than your test loop.

## 31. Two-Writer Experiment and ETag

**Goal:** Prove that consistency levels alone do not prevent lost updates.

~~~text
Item v1: { id: "counter", value: 10, _etag: E1 }

Worker A reads v1/E1
Worker B reads v1/E1

Worker A wants to increment value to 11
Worker B wants to decrement value to 9

If both perform unconditional replaces:
  the second write silently overwrites the first.

If both use If-Match E1:
  A succeeds -> E2
  B sends E1 -> conditional write fails
  B must re-read E2 and recompute.
~~~

### Safe Test Guardrails

- Use only a throwaway test item with zero business impact.
- Count HTTP 412 responses and retries.
- Cap retries rather than looping indefinitely.
- Keep concurrency within provisioned RU/s.
- Verify logs never contain account keys.

### Question

If you switch the account from Session to Strong, will Worker B automatically know to increment/decrement from `v2`? **No**—application write logic still requires conditional updates or transactions.

## 32. Common Misconceptions

| Misconception | Why It Is Wrong | Correct Understanding |
|---|---|---|
| “Session means all users read the exact same state” | Session scope is bounded | Protects read-your-writes within that session |
| “Eventual means data can be lost forever” | Misstates the contract | Replicas converge once writes stop per service rules |
| “Strong prevents overselling” | Two-step read/write still races | Use atomic conditional updates or transactions |
| “Consistent Prefix caps staleness at 5 seconds” | Has no time bound like Bounded Staleness | Prefix guarantees ordering, not time bounds |
| “Bounded Staleness ignores K and T” | Bounds are its core definition | Check valid K/T values and constraints |
| “Cosmos DB always defaults to Strong” | Common default is Session | Inspect the actual account policy |
| “The SDK automatically syncs sessions across all app instances” | Token/context can be dropped | Design explicit session propagation |
| “Session tokens authenticate requests” | Tokens track consistency | Entra ID / RBAC / keys handle authentication |
| “Choosing Strong costs zero extra RUs” | Read RU costs can differ | Measure actual request charges |
| “Eventual is always exactly 10x faster” | No universal constant exists | Benchmark your real workload |
| “Adding RU/s makes reads fresher” | Capacity is orthogonal to consistency | Configure the proper level and tokens |
| “Raising consistency fixes stale Redis caches” | Caching is a separate layer | Manage cache TTL and invalidation |
| “Multi-write needs no conflict resolution” | Concurrent writes can collide | Design conflict resolution policies |
| “Cosmos DB gives SQL transactions across all partitions” | Transaction scope is bounded | Design logical partitions and batches |
| “HTTP 200 OK proves data is the newest version” | Could be a valid stale read | Check versions and freshness |
| “Zero stale reads in one test proves Strong” | Light load converges quickly | Compare formal guarantees and test multi-region |

## 33. Security, Access Control, and Networking

Consistency does not protect data from unauthorized access. Design all security layers:

### Identity

- Prefer **Microsoft Entra ID / managed identity** for Azure Cosmos DB for NoSQL wherever supported.
- Grant least-privilege **data-plane** permissions scoped to specific databases and containers.
- Distinguish Azure RBAC for account management from data-plane RBAC/role definitions for **data operations**.
- Never store account keys in source code, Docker images, repositories, or CI logs.

### Network

- Where required, deploy **Private Endpoints**, firewalls, VNets, and Private DNS.
- Verify outbound paths from AKS, App Service, Functions, or VMs to the Cosmos DB account.
- Enforce TLS and supported SDK versions.
- Never open public network access wide just to troubleshoot 403s or timeouts before diagnosing root causes.

### Data Protection

- Configure backup/restore and retention per API, account, and tier.
- Enforce tenant partitioning and application-level authorization checks.
- Follow service encryption policies and manage keys properly when required.
- Never log full session tokens, access tokens, or personal data.

**Returning a perfectly fresh item belonging to another tenant is still a critical security breach.** Consistency never grants authorization.

## 34. Cost and Architectural Capacity

A Cosmos DB account incurs costs across:

- Provisioned RU/s, autoscale, or serverless capacity per selected mode.
- Storage and indexing overhead.
- Region count, replication, and availability features.
- Backup/restore and extended retention where billed.
- Networking, private connectivity, and cross-region data transfer.
- Monitoring / Log Analytics ingestion and retention.
- Downstream compute for Change Feed processors.

### How Does Level Selection Affect Cost?

Strong and Bounded Staleness can raise read RUs, latency, and topology constraints—yet never evaluate cost on single-read RUs alone. If weaker consistency leads to heavy reconciliation logic, duplicate handling, customer support incidents, or corrupted data, **total business cost** can end up higher.

### Scenario Cost Comparison

~~~text
Option A:
  Strong reads + simpler backend logic
  but requires validating RUs, latency, and topology

Option B:
  Session reads + session token propagation
  + optimistic concurrency + idempotency

Option C:
  Eventual reads + cache/projections
  + reconciliation + freshness monitoring
~~~

No single option is always cheapest. Score **SLOs, RUs, latency, region count, complexity, and risk** against your real workload.

## 35. Diagnosing Read/Write Issues

| Symptom | Possible Cause | How to Check |
|---|---|---|
| User saves item, then immediate read returns old version | Session token lost or read hit another session/region | SDK client reuse, token propagation, request path |
| Two users see different data | Consistency permits stale reads or caches differ | Account level, regions, caches, item versions |
| 429s spike after switching to Strong | Higher read RU demand or insufficient capacity | Request charge, RU/s, retries, hot partitions |
| Read latency p99 climbs | Consistency, region routing, 429s, query, or network | Diagnostics by region and operation type |
| Update fails with 412 | ETag changed due to concurrent write | Re-read, recompute, bounded retry |
| Inventory state wrong despite Strong | Lost update or non-atomic multi-partition logic | Conditional writes, transactions/ledgers |
| New SDK client reads stale version | Session context not carried over | Session token + topology |
| Dashboard data lags significantly | Change Feed / Event Hubs consumer lag or caching | Downstream pipeline metrics |
| Multi-region write triggers conflicts | Two regions edited the same item concurrently | Conflict resolution policy and business keys |
| Read returns 404 after write | Wrong `id`/PK, region/session read path, or deleted item | Check keys, versions, TTL, diagnostics |
| Query burns high RUs even under Eventual | Cross-partition scan, suboptimal indexing | Partition key, query plan, index metrics |
| Account policy changed, client behaves unexpectedly | Request overrides, SDK session, caches, or stale rollout | Live config, SDK options, controlled test |
| API returns 200 with overly stale data | Consistency allows staleness or stale cache layer | Measure end-to-end business staleness |
| SDK receives 403 | Missing data-plane RBAC or network/auth block | Role assignments, identity, endpoint, TLS |

### Six-Step Diagnostic Workflow

1. **Account:** Verify subscription, API for NoSQL, default consistency, and region topology.
2. **Operation:** Point read or query; are `id` and partition key exact?
3. **Session:** Same SDK client/session token or different process/instance?
4. **Metrics:** Inspect RUs, HTTP 429s, latency, ETags, request diagnostics, and contacted region.
5. **Concurrency:** Are conditional updates, transactions, and conflict resolution implemented properly?
6. **Application:** Are caches, stream processors, auth, or business logic introducing lag or bugs?

Never change Strong/Session on production just to “fix” a 404 caused by a **wrong partition key**. Isolate the true failure layer first.

## 36. Case Study: Global Retail Platform

A retail company runs its application across three Azure regions:

- **Catalog:** Millions of daily views, products updated hourly.
- **Cart:** Users add/remove items and expect immediate feedback in the same session.
- **Inventory:** Finite SKU stock; overselling is forbidden.
- **Orders:** Publishes messages to Service Bus and must prevent duplicate orders.
- **Analytics:** Per-minute dashboards aggregating updates from the Change Feed.
- **Data regions:** Users span multiple continents, requiring low latency and regional failover recovery.

### Tasks

1. Select initial consistency levels for Catalog, Cart, Inventory, Orders, and Analytics.
2. Explain why Inventory is unsafe under Strong consistency alone.
3. Design ETag/conditional updates or a reservation pattern for Inventory.
4. Propose how to preserve session tokens when a user's requests hit two API instances.
5. Explain when Strong is warranted and its multi-region write restrictions.
6. Explain how Bounded Staleness provides quantitative lag bounds and why K/T must be verified.
7. Design partition keys for Cart/Orders aligned with transaction boundaries.
8. Evaluate two read regions for latency, read RUs, and failover.
9. Design idempotency keys for order placement and Service Bus workers.
10. Separate Cosmos DB staleness from Change Feed / analytics projection lag.
11. Build tests for same-session, cross-instance, and cross-region read/write flows.
12. Compare cost and risk between: default Session + conditional writes versus Strong in a supported topology.

### Suggested Solution

| Component | Candidate Level | Additional Mechanisms |
|---|---|---|
| Catalog | Eventual or Session depending on UX | Cache TTL/invalidation, price re-validation at checkout |
| Cart | Session | Token propagation, ETags for multi-device edits |
| Inventory | Session or Strong conditionally | Atomic conditional updates/reservations, ledger |
| Orders | Session per specific architecture | Idempotency, transactional scope, workflow |
| Analytics | Eventual / Consistent Prefix per ordering needs | Change Feed lag and freshness monitoring |

This is a **design starting point for discussion**, not a mandate to deploy five separate Cosmos accounts. Account-level consistency, overrides, partitioning, and data sensitivity determine whether workloads share accounts or split.

## 37. Practice Exercise: Selecting Levels for Quantitative Requirements

Three APIs have distinct needs:

**API A — dashboard:** Application SLO tolerates staleness up to tens of seconds without requiring a hard database-enforced bound; refreshes every minute.

**API B — profile:** After saving, users must immediately see updated data in their own session; other users can wait for sync.

**API C — transaction history:** Reads confirming business state must observe the latest committed write within an allowed topology, and concurrent updates must prevent conflicts.

### Questions

1. Does API A strictly require Bounded Staleness? If choosing Eventual, how do you monitor freshness in the app?
2. Can API B use Session? What must be done for a multi-replica stateless API?
3. What prerequisites must API C satisfy to evaluate Strong?
4. For API C, is enabling Strong alone safe without ETags or transactions?
5. When Bounded Staleness uses K/T bounds, which support matrix must be checked?
6. How do you measure RUs and p99 before and after changing settings?
7. If a consumer reads stale data from Redis, will raising Cosmos DB consistency help?

### Hints

**API A** can use Eventual paired with data-age/consumer-lag monitoring and cache freshness checks. **API B** is a textbook Session fit with token propagation. **API C** requires evaluating Strong against topology and cost while still enforcing conditional writes/transactions and invariant tests.

## 38. Production Deployment Checklist

| Group | Verification Item |
|---|---|
| Requirements | Are freshness and ordering requirements quantitative or perceptual? |
| Default policy | Are the account's actual consistency level and parameters verified? |
| Topology | Are read/write regions and consistency limits mutually compatible? |
| Session | Is session token/context preserved across API instances? |
| Partition | Does the logical partition key fit point reads, transactions, and throughput? |
| Strong | Is there a proven business need, with measured RUs, latency, and availability? |
| Bounded | Are K/T valid and backed by freshness evidence? |
| Prefix | Are ordering scope boundaries clearly understood? |
| Eventual | Are stale reads acceptable, with reconciliation designed? |
| Concurrency | Do ETags, transactions, and idempotency protect competing writes? |
| Multi-write | Does conflict resolution match the domain and pass failover tests? |
| SDK | Are SDK version, preferred regions, retries, and token propagation tested? |
| Cache | Are Redis/APIM/CDN TTLs kept distinct from DB consistency? |
| Monitoring | Are read/write latency, RUs, 412s, 429s, replication, and freshness tracked? |
| Security | Are Entra ID/RBAC, TLS, Private Endpoints, and secrets protected? |
| DR | Have backups, restore drills, RPO/RTO, and region failovers been verified? |
| Cost | Have RUs, regions, storage, monitoring, and app costs been compared? |
| Change | Are canary rollout, approvals, rollback, and documentation ready? |

## 39. Self-Check Questions

1. What relationship between reads and writes does consistency in Azure Cosmos DB govern?
2. Distinguish a stale read from a lost update.
3. List the five consistency levels from strongest to weakest.
4. What does Strong consistency guarantee regarding committed values?
5. What do `K` and `T` bound in Bounded Staleness?
6. Why can't you assume `K=5, T=5` is valid for every topology?
7. Does Session consistency guarantee read-your-writes across independent clients?
8. What does a session token do? Is it an authentication credential?
9. Why can a multi-replica stateless API lose expected session guarantees?
10. What ordering guarantee separates Consistent Prefix from Eventual?
11. Does Consistent Prefix enforce a time bound on staleness?
12. Does Eventual consistency mean replicas never converge?
13. With Strong enabled, can two workers still cause a lost update via unconditional writes?
14. Which class of bugs do ETags and `If-Match` solve?
15. How does HTTP 412 differ from HTTP 429 in Cosmos DB?
16. Does a transactional batch span all partitions?
17. What can preferred regions improve, and what do they fail to guarantee?
18. Why do multi-region writes require conflict resolution?
19. Can you upgrade an Eventual account to Strong using only a request header?
20. Why can Strong and Bounded Staleness consume more read RUs?
21. How do point reads differ from cross-partition queries in RU consumption?
22. Why is measuring latency once insufficient for comparing consistency levels?
23. What must you test when a user adds to cart and the next request hits a different API instance?
24. Why can a Redis cache return stale data even when Cosmos DB uses Strong?
25. How does Change Feed consumer lag differ from replication staleness?
26. Is Eventual suitable for product view counters? What caveats apply?
27. Which mechanism should protect inventory when only 1 unit remains?
28. Why is Session consistency often the balanced choice for web/mobile apps?
29. If a dashboard requires data at most 30 seconds old, what else must be measured besides consistency level?
30. In production, what steps should you take before changing account-level consistency?

## References

- Microsoft Learn — *Consistency levels in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels
- Microsoft Learn — *Strong consistency in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#strong-consistency
- Microsoft Learn — *Bounded staleness consistency*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#bounded-staleness-consistency
- Microsoft Learn — *Session consistency*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#session-consistency
- Microsoft Learn — *Consistency level choices in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/consistency-levels#consistency-levels-and-latency
- Microsoft Learn — *Azure Cosmos DB for NoSQL overview*: https://learn.microsoft.com/azure/cosmos-db/nosql/overview
- Microsoft Learn — *Partitioning and horizontal scaling*: https://learn.microsoft.com/azure/cosmos-db/partitioning-overview
- Microsoft Learn — *Transactional batch in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch
- Microsoft Learn — *Optimistic concurrency control with ETags*: https://learn.microsoft.com/azure/cosmos-db/nosql/database-transactions-optimistic-concurrency
- Microsoft Learn — *Request Units in Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/request-units
- Microsoft Learn — *Monitor Azure Cosmos DB*: https://learn.microsoft.com/azure/cosmos-db/monitor
- Microsoft Learn — *Global distribution and multi-region writes*: https://learn.microsoft.com/azure/cosmos-db/distribute-data-globally
- Microsoft Learn — *Azure Cosmos DB Python SDK*: https://learn.microsoft.com/python/api/overview/azure/cosmos-readme
