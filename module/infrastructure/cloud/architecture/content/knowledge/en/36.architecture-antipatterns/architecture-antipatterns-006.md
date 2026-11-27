# Architecture antipattern: using multi-region without resolving write ownership and data conflicts

## 1. Context: multiple regions do not automatically equal high reliability

A cloud system can run applications across two or more geographic regions to serve users closer to them, maintain service during a regional outage, or satisfy data residency regulations. However, **deploying multiple copies of an application and database does not automatically turn them into a consistent write system**.

The antipattern appears when a design team enables **active-active** mode—allowing users to write to the same dataset in multiple regions—without answering:

- **Who owns writes?** Which region holds write authority over an entity such as an order, wallet balance, or inventory count at any given moment?
- **Which write wins?** How are two concurrent updates in two regions ordered, merged, or rejected?
- **When inter-region connectivity breaks,** does the system prioritize continuing to accept writes or preserving data invariants?
- **Once the network recovers,** by what business rules is divergent data detected, reconciled, and repaired?
- **When transferring primary write ownership,** what prevents the old region from continuing to accept writes?

This topic belongs to the **architecture antipatterns** group of the **Cloud Architecture** module: evaluating cloud application design from business requirements to networking, compute, data, and deployment choices. The focus is on trade-offs across **reliability, security, scalability, cost, and operations**, applying **Well-Architected** thinking to scrutinize decisions.

**Core message:** Before distributing **write** capabilities, define the business invariants that must hold at all times, transaction scope, write ownership, and the protocol for handling regional disagreements.

## 2. Identifying the antipattern

### 2.1. Common shape

~~~mermaid
flowchart TB
    C[Users / Global DNS] --> GLB[Global Traffic Manager]
    GLB --> A[App in Region A]
    GLB --> B[App in Region B]

    subgraph Ra["Region A"]
        A --> DA[(Database A: writes enabled)]
    end

    subgraph Rb["Region B"]
        B --> DB[(Database B: writes enabled)]
    end

    DA <-->|Asynchronous replication| DB

    classDef bad fill:#fde9e7,stroke:#c04d45,color:#6b1f1f
    class DA,DB bad
~~~

In the diagram above, both Database A and Database B accept writes independently, then exchange data via asynchronous replication. Under normal connectivity, most records may eventually converge. Yet if both regions update **the same object** before receiving each other's updates, conflicts arise.

Example of a storefront with only **1 unit left**:

| Time | Region A | Region B |
| --- | --- | --- |
| T0 | Replica reads stock = 1 | Replica reads stock = 1 |
| T1 | Customer X orders 1 unit | Customer Y orders 1 unit |
| T2 | Local write: stock drops from 1 to 0; confirms order | Local write: stock drops from 1 to 0; confirms order |
| T3 | Replicates state to B | Replicates state to A |
| T4 | Both orders are confirmed | Only 1 physical unit exists to ship |

If merging uses **last-write-wins (LWW)**, the resulting stock count may simply be 0; that number looks valid, yet **two customers received confirmations for the exact same unit**. Picking the “latest” update cannot undo a business invariant already violated.

This bug can happen even without a full network outage: replication lag alone only needs to be long enough for both sides to decide from stale data.

### 2.2. Symptoms in real systems

| Symptom | Possible root cause |
| --- | --- |
| Duplicate orders, payments, or transactions when a user switches regions | Retried requests lack global idempotency; two regions process them |
| Negative inventory, overselling, or over-redeemed promo codes | Invariants checked locally per region |
| “Unique” usernames/order codes duplicated across regions | Unique constraint enforced only within one local DB |
| Recently edited data reverts to old values | Write conflicts, stale reads, or failback from an unsynced replica |
| “Orphaned” records appear after failover | Confirmed writes in the old region had not replicated to the new region |
| Both clusters claim to be primary | Split-brain; missing fencing/quorum and write ownership |
| System reports no errors while aggregate figures drift | Timestamp-based merges drop updates; duplicate or out-of-order events |

**The most dangerous sign** is when every service appears healthy with low latency while business data no longer satisfies invariants. Load balancer or database health checks alone are never enough to declare an architecture safe.

## 3. Concepts to distinguish

| Concept | Meaning for multi-region |
| --- | --- |
| **Multi-AZ** | Running across multiple availability zones within one region, typically with lower latency than cross-region links. Not synonymous with multi-region. |
| **Multi-region** | Application/data present in multiple regions; says nothing by itself about write authority or consistency level. |
| **Active-passive** | One region handles writes; a standby region activates when needed. |
| **Active-active** | Multiple regions serve traffic concurrently; verify carefully whether they only **read** together, write **distinct keys**, or write **the same key**. |
| **Single-writer** | Each entity at any point has exactly one authorized writer. Could be one global writer or a distinct owner per key. |
| **Multi-writer** | Multiple locations can write concurrently; if targeting the same key, conflict resolution and invariant protection are required. |
| **Synchronous replication** | Writes are acknowledged only after meeting confirmation policies across replicas/quorum; impacts latency and write availability during partitions. |
| **Asynchronous replication** | Writes are acknowledged at the source before replicas receive everything; introduces replication lag and risk of losing acknowledged writes on failover. |
| **RPO** | Maximum acceptable data loss on recovery, measured in data/time window. |
| **RTO** | Maximum acceptable duration to restore service functionality after an outage. |
| **Split-brain** | Two or more parties simultaneously believe they hold primary write authority over the same dataset. |
| **Fencing** | Mechanism ensuring a former writer loses authority and its operations are rejected at the write-enforcement point. |

You cannot conclude **active-active = stronger than active-passive** in every dimension. If a workflow needs a consistent cross-region transaction, an active-active design can introduce extra network dependencies and reduce write availability during partitions.

### 3.1. Why network partitions force an architectural choice

When two regions cannot communicate, a system cannot simultaneously let **every** region keep freely writing **the same data** while guaranteeing **global ordering and strong invariants** without coordination. Viewed through CAP, during a network partition, the design must define behavior between accepting operations and keeping shared state consistent.

More precisely, write availability **can still be preserved** for independent keys or operations, but you cannot promise that conflicting writes will all be accepted while preserving strict invariants. Even when inter-region links are healthy, tighter synchronization raises latency compared to local writes—a trade-off often discussed alongside PACELC.

Examples:

- Profile updates touching unrelated fields can be merged under explicit rules.
- View counters can use additive mergeable structures (accepting delayed reads).
- **Deducting balances, reserving stock, or booking the last ticket** must not be decided independently by two regions from lagged replicas.

## 4. Failure analysis from a correctness perspective

### 4.1. Lost updates and same-record conflicts

Suppose a user edits their shipping address in A and B nearly simultaneously. If A receives “Street 1” and B receives “Street 2,” a final timestamp comparison picks one version. Which version wins depends on clocks and merge rules, and the other update may vanish. System clocks across regions can drift; physical timestamps are unreliable proof of causal order.

Even **last-write-wins** with better clocks is only a **contention-resolution policy**, not a general solution for all data. If an update gets dropped, decide upfront whether losing that update is acceptable.

### 4.2. Cross-region unique constraint violations

Two users register the same unique promo code in A and B. Both local DBs see no conflict and commit. Per-region unique indexes cannot enforce **global** uniqueness without a coordination point or partitioned namespaces.

Remedies depend on requirements: global uniqueness locking via a namespace-owning service; region-prefixed/partitioned ID generation to avoid collisions; or a database providing matching transactional guarantees. Partitioning IDs avoids technical primary-key collisions, yet **does not** protect business uniqueness of usernames or vouchers.

### 4.3. Split-brain during failover

Region A is the current writer. Health checks in B lose contact with A and automatically promote B to writer. Meanwhile, A still serves some clients and keeps committing. Both clusters accept writes:

~~~mermaid
sequenceDiagram
    autonumber
    participant CA as Client in A
    participant A as Region A (old writer)
    participant N as Inter-region network
    participant B as Region B (new writer)
    participant CB as Client in B

    N--xA: Connection lost
    N--xB: Connection lost
    Note over A,B: B cannot tell if A is dead or merely unreachable
    CA->>A: Write version X
    A-->>CA: Commit OK
    CB->>B: Write version Y for same entity
    B-->>CB: Commit OK
    Note over A,B: Concurrent write promises cause split-brain
~~~

A health check reporting “primary unreachable” does not mean the primary **lost write authority**. Safe automatic failover requires a proper election/lease/quorum mechanism **and** a way to stop the old writer from committing later.

### 4.4. Non-zero RPO: acknowledged writes lost after regional failover

With asynchronous replication, when A returns “success,” some changes may still sit in the replication queue. If A is lost completely and B becomes writer, B may lack those changes. This is not merely “stale reads”: it can mean **losing a write already confirmed to the user**.

Therefore, specify clearly:

1. After what acknowledgment is a write considered **durable** (local commit, in-region multi-replica, or cross-region quorum)?
2. What are the designed RPO and the observed RPO at failover time?
3. How is missing data located, backfilled, or compensated if the old region returns?
4. Do client retries hitting B carry durable, properly scoped idempotency keys?

Never advertise “zero data loss” if the real setup uses asynchronous replication without mechanisms guaranteeing RPO=0 under the committed failure modes.

### 4.5. Stale reads and “read-your-writes”

A customer updates their profile in A, then their next request routes to B before replication catches up. The customer sees old data and may resubmit. This is a **session consistency** issue even with only a single writer.

Common mitigations:

- Route the session to the writer or a replica caught up to a specific version/commit token.
- Read from the writer for flows requiring **read-your-writes**.
- Display sync-pending states where delayed data is acceptable.
- Use database-supported consistency levels and verify their exact guarantee scope.

Do not assume “read from the nearest region” fits every screen, especially right after payments, permission changes, or order confirmations.

## 5. Start from invariants and write-authority scope

### 5.1. Classify data before choosing active-active

| Data / business domain | Typical invariant | Better-suited strategy |
| --- | --- | --- |
| Balances, transaction ledgers | Never overdraw; never double-post entries | Centralized write authority per account, strong transactions, immutable ledger |
| Stock per SKU/warehouse | Never sell beyond available quantity | Single owner per stock bucket or controlled escrow/quota allocation |
| Seats/tickets/reservations | A slot is allocated at most once | Owner/transactional lock per resource, consistent confirmation |
| Unique usernames | No duplicates across the global namespace | Global allocation service or rule-partitioned namespaces |
| Shopping carts, personal notes | May tolerate merging certain edits | Business-defined merge rules, potentially CRDTs on suitable fields |
| Engagement/telemetry counters | Prioritizes aggregation, tolerates lag | Additive counters, eventual consistency, deduplication |
| Rarely changing product catalogs | Tolerates bounded stale reads | Single write location, multi-region caches/replicas for reads |

One entity can hold **fields with different consistency needs**. Never switch an entire database to multi-region writes just because a few datasets merge easily.

### 5.2. Define the write owner

For each **consistency boundary** (unit whose invariants must be protected), know:

- **Ownership key:** e.g., accountId, orderId, sku + warehouseId, or seatId.
- **Current owner:** a region, partition leader, or quorum group.
- **Owner lookup:** static key-based routing, consistent metadata, or data-platform APIs.
- **Valid write condition:** token/epoch/term, version, or transaction processed by the authorized owner.
- **Ownership handoff:** fencing the old writer, recovering data, verifying state, and recording the new owner.

**Single-writer does not have to mean one region for the whole system.** You can partition write ownership by account or warehouse: Region A owns group-A accounts while Region B owns group-B accounts. Both regions accept writes, yet **never concurrently write the same consistency boundary**. When a transaction spans resources across multiple owners, you still need coordination, latency trade-offs, or adjusted data boundaries.

### 5.3. Fencing tokens and stale write authority

One writer-management pattern uses a monotonically increasing **generation/epoch**:

1. Owner A is granted **epoch 41**.
2. After a valid handoff, Owner B is granted **epoch 42**.
3. The write-enforcement layer accepts requests only from the current epoch's owner; epoch-41 requests are rejected even if A recovers and still thinks it is leader.

~~~text
request:
  resource_key: SKU-123|Warehouse-1
  write_epoch: 42
  operation_id: reserve-order-879
  expected_version: 7

authoritative write path:
  verify current_owner and write_epoch
  atomically validate invariant and expected_version
  apply mutation and persist operation_id
  commit
~~~

**Design warning:** If each region stores an owner/epoch table in an **asynchronously replicated** DB, both sides can still accept their own epochs. Tokens are safe only when **the write-enforcement point actually verifies the valid epoch** through a sufficiently consistent mechanism (such as consensus/quorum or a fenced leader DB). A token passed in a request without storage-level enforcement is just metadata.

Time-based leases must also handle clock drift, scheduling delays, and process pauses. When lease validity is in doubt, the writer must halt writes—never rely solely on “not having seen a new leader yet.”

## 6. Alternative architectures and applicability conditions

### 6.1. Option A — One write region, multiple read regions

~~~mermaid
flowchart LR
    U[Multi-region Clients] --> R[Global Router / CDN / WAF]
    R --> AA[App Region A]
    R --> AB[App Region B]
    AA --> P[(Primary DB: writes in A)]
    AB --> P
    P -->|Lagged replication| RP[(Read Replica in B)]
    AB -->|Lag-tolerant reads| RP
    AB -->|Fresh reads| P
~~~

- Only the **primary** accepts writes; app instances in B forward write requests to A.
- Read replicas reduce read latency, but queries must be classified by freshness needs.
- If A fails, B **does not automatically** become writer merely because it has a replica. Promotion, fencing, and replication-lag handling are required.
- Data and logs cross regional boundaries; factor in transfer costs, security, and data residency.

**Suitable when** most workflows require strong consistency and cross-region write latency is not the top constraint. This option is usually easier to operate and prove invariant-safe than same-key multi-writer designs.

### 6.2. Option B — Partitioning owners by entity

~~~mermaid
flowchart TD
    C[Global API] --> OW[Ownership / Routing Service]
    OW -->|account A or bucket X| RA[Region A: Owner of partition A]
    OW -->|account B or bucket Y| RB[Region B: Owner of partition B]
    RA --> DA[(DB A)]
    RB --> DB[(DB B)]
    RA -.->|Read projection / event| DB
    RB -.->|Read projection / event| DA
~~~

The upside is accepting writes in multiple regions while avoiding concurrent writes to **the same entity**. The trade-off is managing owner migration, consistent directories, stale routing, hotspots, and cross-partition workflows.

Example: every balance change for account X routes to account X's owner; two different accounts can be processed concurrently in two regions. If a transfer touches both X and Y on different owners, a dedicated business protocol (such as reservation and saga) is needed, or ledgers requiring atomicity must share one consistency boundary.

### 6.3. Option C — Multi-writer with defined conflict semantics

Multiple regions can write to the same dataset when the business **explicitly defines merge semantics**. Options include:

- **CRDTs:** suited to data types with convergent merge operations (counters, sets under specific semantics). They do not magically make balance deductions or last-seat bookings safe; invariants must hold under every merge order.
- **Application-level merge:** uses versions, change history, and field/object rules, sometimes asking users to resolve conflicts.
- **Escrow/quota allocation:** pre-allocates consumption rights (e.g., each region receives up to N units of stock); each region consumes only its quota and rebalances via a consistent protocol.
- **Globally consistent database:** uses a DB engine with cross-region transactions/quorum; verify its exact isolation model, transaction scope, and behavior on quorum loss.

Not every product labeled “global,” “multi-master,” or “active-active” guarantees serializability, global uniqueness, or RPO=0. Read the consistency contract for the **exact service, version, and deployment mode**, then test under expected load and failure modes.

### 6.4. Decision matrix

| Model | Same-entity write authority | Typical write latency | Complexity and trade-offs |
| --- | --- | --- | --- |
| Single primary + cross-region replicas | Single writer | Remote clients travel to primary | Relatively simple; must solve failover and RPO under async replication |
| Per-key/partition single-writer | One writer per key | Writes at owner, potentially cross-region | More complex routing/ownership; cross-partition transactions are hard |
| Multi-writer + business merge | Multiple writers | Fast local writes possible | Must prove invariants still hold or accept compensating repairs |
| Cross-region consensus DB | Leader/quorum per DB contract | Can add inter-region RTT | Trades latency/availability/cost for consistency; must understand quorum placement |
| Multi-region reads, primary writes | Single writer | Local reads, remote writes | Easy caching; requires explicit read-your-writes handling |

Choose a model based on **RPO/RTO, target latency, contending write frequency, invariants, data residency, and operational capability**—not region count as a vanity metric.

## 7. Data conflicts: resolve by business semantics, not clocks alone

### 7.1. Commonly misused strategies

**Last-write-wins**:

- Acceptable for a few attributes where lost updates are tolerable, such as ephemeral display state.
- **Unsuitable** for ledgers, inventory, or voucher counts when concurrent operations have physical/financial effects.
- Relying on physical timestamps suffers from clock skew; even logical or hybrid logical clocks do not automatically protect business invariants.

**Blind JSON merge**: field-by-field overwrites or object unions can produce states that never existed in any valid record. Define semantics and versions for related fields together.

**“Let replication resolve it”**: replication only moves data; DB conflict detection/resolution follows mechanical rules and does not equate to a valid business transaction.

**“Retry until it succeeds”**: on lost responses, retries can double financial charges or oversell stock without stable operation IDs and deduplication.

### 7.2. Conflict policy table

| Business action | When two regions request concurrently | Rule to define |
| --- | --- | --- |
| Deduct the last 1 item | Both see 1 left | Only the owner/quorum grants the unit, or use pre-split quotas. The other request is rejected/queued. |
| Change account balance | Two concurrent withdrawals | Single ledger/serialization boundary for that balance—never LWW. |
| Shopping cart “add item” | Both add different lines | Merge by operation identity and cart semantics; avoid re-adding duplicate retry events. |
| Edit two independent profile fields | Two unrelated fields | Merge per field/version; if same field, surface or resolve conflict. |
| Create username | Both claim the same name | Global uniqueness reservation or partitioned namespace. |
| View counter | Both increment independently | Additive CRDT/counter with unique operation IDs under at-least-once delivery. |

### 7.3. Versioning, idempotency, and event ordering

A crucial distinction is separating **concurrent updates** from **redelivery of the same operation**:

- **Idempotency key** identifies the same retried business request. Keys must remain valid across regional failover; the new region must be able to read proof of prior execution or run proper recovery.
- **Entity version** or compare-and-swap predicates detect lost updates at the write authority.
- **Operation ID** is stored alongside business outcomes to avoid double side effects.
- **Event ID / aggregate version** helps consumers deduplicate, detect stale events, or reorder per rules.
- **Transactional Outbox** commits local state alongside outbound event intent, though it does not solve concurrent writes in two regions.

The SQL example below is **correct only when executed on a single consistent SKU owner**; running the exact same query on two async multi-master DBs can still oversell stock:

~~~sql
-- Operations within one transaction on the current owner's DB.
-- Ownership/epoch verification must be enforced by the write path.
UPDATE sku_inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE sku = :sku
  AND warehouse_id = :warehouse_id
  AND available >= :quantity
  AND version = :expected_version
RETURNING version;
~~~

If zero rows update, the app must distinguish insufficient stock, stale version, or owner handoff—never retry blindly forever. Reservations, deduplication records, and outbox events must be saved in the **same local transaction** when using this pattern.

## 8. Fixing the antipattern: order-system architecture example

### 8.1. Hypothetical requirements

A retailer serves customers across continents:

- The API must stay available if one application region fails.
- Must never sell beyond real physical stock for any **SKU + warehouse**.
- Retried order requests caused by timeouts must never create two orders or two charges.
- Catalog pages may read from slightly lagged replicas/caches; payment confirmation screens need fresh data.
- Order latency, acceptable data loss, and recovery time must be agreed with the business before selecting technology.

A viable design starts with **multi-region application + single-owner per stock bucket**:

~~~mermaid
flowchart TB
    U[Shopper] --> EDGE[Global Edge / WAF / DNS]
    EDGE --> APP_A[Order API - Region A]
    EDGE --> APP_B[Order API - Region B]

    APP_A --> DIR[Ownership Directory / Routing]
    APP_B --> DIR
    DIR -->|SKU/warehouse owned by A| INV_A[Inventory Write Owner A]
    DIR -->|SKU/warehouse owned by B| INV_B[Inventory Write Owner B]

    INV_A --> DB_A[(Transactional Store A)]
    INV_B --> DB_B[(Transactional Store B)]
    DB_A --> OB_A[Outbox A]
    DB_B --> OB_B[Outbox B]
    OB_A --> BUS[(Event Bus)]
    OB_B --> BUS
    BUS --> SAGA[Saga / Reconciliation]
    SAGA --> PAY[Payment Service with idempotency]
    PAY --> PSP[Payment Provider]
~~~

**Note on the diagram:** The Ownership Directory must be backed by a mechanism with strong enough consistency for write authority. Arrows from the directory to owners depict routing logic; the live system must **enforce authority at the write point**, not merely check routing at the gateway.

### 8.2. Safe write flow

1. The customer submits an order request with an **Idempotency-Key**.
2. Order API looks up or allocates an order ID via a unified ownership mechanism; retries return the same result or an in-progress status.
3. The Saga identifies the stock bucket and current owner for each reservation item.
4. The Inventory owner validates authority/epoch and remaining stock inside a transaction, persisting the reservation and outbox event together.
5. Payment Service authorizes payment using a stable idempotency key with the payment gateway.
6. Only after both reservation and payment succeed per policy does Order Service confirm the order.
7. If a step fails, the saga triggers compensating actions; if PSP status is ambiguous, run reconciliation before retrying.

For orders spanning stock buckets owned by different owners, there is no free global transaction. You can use a saga to reserve piece by piece and release on partial failure, accepting an intermediate window. If the business demands **all-or-nothing immediately** under strict isolation, adjust boundaries or use a database/coordinator providing those guarantees.

### 8.3. Limitations you must still acknowledge

The model above prevents two regions from concurrently writing the same stock bucket when ownership is properly enforced. However, the application can still be affected by:

- An owner region outage slowing or blocking writes for that partition until failover completes.
- Stale directories on clients causing redirects or retries.
- Lagged read replicas showing users a different stock figure than at checkout time.
- Multi-step sagas requiring compensation when payment fails.
- Ownership handoffs needing careful handling of in-flight and ambiguous operations.

These are architectural trade-offs to document explicitly; you cannot wish them away by adding more load balancers or DB replicas.

## 9. Failover: transfer write authority before shifting traffic

### 9.1. Separate traffic routing from write authority

**Traffic failover** merely points requests to another endpoint. **Data failover** determines which data is eligible to serve and who holds commit authority. Shifting traffic before isolating the old writer invites split-brain.

Reference single-writer procedure:

~~~mermaid
flowchart TD
    D[Incident detected / multi-signal confirmation] --> H{Evidence old writer is fenced?}
    H -->|No| STOP[Hold sensitive writes / read-only mode]
    STOP --> F[Isolate or fence old writer via authoritative mechanism]
    H -->|Yes| R[Inspect replica lag and data integrity]
    F --> R
    R --> Q{Data meets RPO & promotion criteria?}
    Q -->|No| DEC[Decide recovery / data-loss trade-off per runbook & authority]
    Q -->|Yes| P[Promote new writer, increment epoch]
    DEC --> P
    P --> T[Update routing and verify stale-epoch rejection]
    T --> V[Run canary transactions, check idempotency & monitoring]
    V --> REC[Reconcile operations with unknown status]
~~~

This diagram shows the principle. Never promote a replica merely because a “timeout expired” without proof that the old writer is fenced or consensus prevents two active writers.

### 9.2. Detailed operational runbook

| Phase | Action | Gate to proceed |
| --- | --- | --- |
| **Detect** | Combine app, DB, network, and replication health; scope impact | Rule out local gateway glitches causing false positives |
| **Decide** | Weigh outage duration, latency, and RPO/RTO against thresholds | Authorized owner/automation approves failover mode |
| **Fence** | Revoke lease/epoch or block old writer at storage; optionally set write path read-only | Proof the old writer can no longer commit validly |
| **Catch up / Assess** | Check replica lag, commit position, and unacknowledged operations | Actual RPO and ambiguous-operation exposure are known |
| **Promote** | Issue new epoch/owner and initialize read/write paths | New region satisfies required invariants/consistency |
| **Route** | Switch traffic manager, refresh client routing, handle retries | Sensitive writes route to the right owner |
| **Verify** | Canaries, synthetic transactions, duplicate alerts, outbox/queue lag | Metrics and invariants stabilize |
| **Reconcile** | Reconcile orders, payments, inventory, and unsynced events | Zero duplicated or dropped financial effects |
| **Failback** | Restore old region as replica, sync, and hand back authority safely | Old writer cannot resume with a stale epoch |

When safe fencing is impossible, the right choice may be **pausing sensitive writes** or entering degraded mode: allow catalog browsing and cached views while temporarily locking checkout/transfers. Preserving financial invariants usually beats “returning HTTP 200 at all costs.”

### 9.3. Failback is also an ownership transfer

Region A coming back online does not mean it can immediately resume writes. Before failback:

1. Rebuild A from the authoritative source and catch A up to the current writer.
2. Resolve remaining ambiguous transactions, duplicate messages, and divergent records.
3. Mint a new epoch, fence the current writer per procedure, transfer ownership, and then shift routing.
4. Verify A accepts the new epoch and B rejects writes carrying the old epoch.

Never perform “silent failback” driven merely by default DNS weights.

## 10. Deliberate consistency design

### 10.1. Reads and writes do not need the same SLA

An application can tier operations by consistency level:

| Operation | Consistency level to consider | Behavior when nearest region only has stale data |
| --- | --- | --- |
| Browse catalog | Eventual consistency with bounded lag | Serve from cache/replica and display freshness timestamp if needed |
| View newly created order | Read-your-writes / session consistency | Read from owner or wait for replica to reach commit token |
| Reserve inventory | Atomic conditional write on bucket owner | Route to owner; if unavailable, queue or temporarily reject |
| Transfer balance | Ledger-appropriate transaction/isolation | Never accept writes on a lagging replica |
| Update UI preferences | May allow per-field merge | Apply agreed conflict-resolution rules |

**API clarity matters:** “accepted for processing” is different from “committed” and different from “replicated across regions.” Returning an ambiguous status encourages client retries that cause duplicate side effects.

### 10.2. Quorums and fault tolerance

A platform using consensus/quorum for leader election reduces split-brain risk when writes require an authoritative quorum. However, quorum placement affects write availability:

- If most voting replicas sit in Region A, losing A can cost quorum even while B's apps remain up.
- Distributing quorum across failure domains improves resilience while adding cost and network latency.
- A data-less witness cannot necessarily substitute for a promotable data replica; verify its exact role in the product.
- Quorum designs intentionally reject writes under certain partitions, trading availability to preserve consistency.

Never roll your own consensus out of a “leader=true” row across two asynchronously replicated DBs. Unless truly justified, rely on battle-tested leader/replication management from your data platform.

### 10.3. Replication does not replace backups

Logical errors such as accidentally dropping a table, bad bulk updates, or ransomware can replicate rapidly to every region. You still need backups with independent retention and access controls, restore testing, key/secret protection, and point-in-time recovery targets. Multi-region HA and DR backups mitigate different classes of risk.

## 11. Sizing, cost, and latency

Suppose a system handles **W writes/second**, average replicated payload size is **S bytes/write**, and there are **N** cross-region replica targets. Raw replication bandwidth is roughly:

~~~text
replication_egress_bytes_per_second ≈ W × S × N
~~~

This is only a starting point: add WAL/metadata, indexes, retries, snapshots, compression overhead, network delays, read traffic, and reconciliation traffic. Do not treat this formula as a billing quote.

Cross-region synchronous commit latency typically adds **network round-trip** time to required participants. Region placement, quorum policy, and client location shape p95/p99 latency. Writing locally and syncing later lowers latency while raising conflict risk and non-zero RPO exposure. Never judge an option solely by average latency under healthy networks.

Budget for commonly overlooked factors:

- Inter-region data transfer fees and cross-region synchronous write traffic.
- Replicated databases, brokers, caches, storage, backups, and logs.
- 24/7 operational capacity: failover drills, incident response, data reconciliation, conflict support.
- Standby capacity large enough to absorb load when a region goes offline.
- Added complexity in deployments, schema migrations, and multi-region change control.

**Validate with representative load:** hot writes hitting a single SKU or ledger account face contention even when aggregate system throughput looks low. Benchmarks using uniformly distributed keys easily mask this problem.

## 12. Well-Architected evaluation

| Pillar | Questions to answer | Design measures |
| --- | --- | --- |
| **Reliability** | On losing 1 region or network link, can two writers exist? Are RPO/RTO measured? | Ownership, fencing, proper quorum, backups, failover drills, reconciliation |
| **Security** | Are data and keys allowed to leave the country/region? Who can promote a writer? | Least-privilege IAM, encryption, auditing, data residency, controlled failover permissions |
| **Operational Excellence** | Can you detect split-brain, broken replication, and data drift before customers report it? | Runbooks, SLOs, traces, dashboards, canaries, chaos drills, incident reviews |
| **Performance Efficiency** | How much latency do cross-region writes add? How are hot keys handled? | Owner-based routing, read/write split, smart caching and partitioning, p95/p99 tracking |
| **Cost Optimization** | How much do extra replicas, egress, and staffing add across regions? | Multi-region only where justified; optimize replication and retention |
| **Sustainability** | Are standby regions sized and utilized sensibly? | Cut redundant replication, track resource efficiency, scale to real load |

### 12.1. Security and compliance in multi-region replication

Replicating data to another region can change regulatory, contractual, and customer-compliance scope. Map everywhere data rests—storage, logs, backups, caches, DR snapshots, and events—avoiding checking only the primary database.

Consider:

- Encryption in transit and at rest; key management, key scope, and losing KMS access in one region.
- Service identities and owner-scoped write privileges; promote and routing-change rights are sensitive privileges.
- Egress controls, firewalls, private connectivity, and internal endpoint protection.
- Auditing failover decisions, owner transfers, snapshot access, and conflict repairs.
- Separating PII, financial records, and logs; replicate only data needed for business objectives.

### 12.2. Observability to catch logic failures

Recommended metrics:

| Category | Metric / signal | Purpose |
| --- | --- | --- |
| Ownership | Concurrent owners per key, stale-epoch rejections | Detect split-brain risk |
| Replication | Lag in time/commit position, backlog, apply errors | Assess latency and RPO ahead of failover |
| Consistency | Conflict rate, divergence rate, reconciliation results | Detect diverging data and lost updates |
| Business invariants | Negative stock, duplicate payments, double allocations, ledger drift | Measure business correctness |
| Traffic | Cross-region write hops, routing retries, p95/p99 latency | Understand latency and failover impact |
| Recovery | Fencing, promotion, replication convergence, and failback times | Verify RTO empirically rather than on paper |
| Reliability | Requests rejected due to partition/quorum, writes in degraded mode | Evaluate availability–consistency choices |

Emit structured logs with **entity key, owner region, epoch/term, operation ID, correlation ID, entity version, and replication position** without exposing sensitive fields. Logs saying only “success” without write-authority context make split-brain investigations painful.

## 13. Architecture evaluation practice

### 13.1. Problem statement

An engineering team proposes running checkout in Regions A and B with both databases writable. Data replicates asynchronously two ways; conflicts resolve via **LWW on updated_at**. They argue that losing one region lets the other keep selling immediately, improving reliability.

Tasks:

1. List at least **three invariants** LWW may fail to protect.
2. Walk through two concurrent requests buying the last item in both regions; why can both succeed?
3. Design write authority for **SKU + warehouse**, specifying which region decides available quantity.
4. Define behavior when one region loses connectivity without confirmed death: which operations stop, and which can continue?
5. Specify who/what has promotion authority and what blocks the old writer from continuing.
6. Select business RPO/RTO targets and verify whether the replication mode actually meets them.
7. Propose how to distinguish “a new record has not arrived yet” from “two conflicting updates were both confirmed.”

**Reference solution direction:** Maintain a single owner per stock bucket or use consistent reservation/escrow mechanisms. Protect order-creation and payment idempotency; never use LWW for inventory. During a network partition, only the region holding valid ownership commits reservations; the other returns a pending/temporary-reject status or forwards to the owner if reachable. Before promoting a new owner, fence the old one and account for RPO exposure.

### 13.2. Fault-injection matrix

| Fault injection | Expected observable outcome |
| --- | --- |
| Sever network between A and B while clients hit both | Never two write owners committing the same key |
| Accept writes on A, delay replication to B, then route client to B | Reads follow freshness policy; already-processed effects do not re-trigger |
| Pause old leader then promote new leader | Writes carrying the old epoch are rejected at enforcement point |
| Kill process after local commit before returning HTTP response | Retry with same operation ID produces no second side effect |
| Two shoppers buy the last SKU concurrently in two regions | At most one reservation is validly confirmed |
| Shut down a critical quorum member | Write behavior matches documented consistency/failure model; never silently allows unsafe writes |
| Increase replication lag then trigger failover | RPO gate triggers; never silently treats stale data as synced |
| Recover old region after failover | Old region rejoins as replica/standby, never auto-resuming as writer |
| Redeliver or reorder events | Idempotent consumer handles versions cleanly |
| Restore from backup missing recent transactions | Payment/order reconciliation detects and resolves discrepancies |

Testing should use isolated environments, synthetic data, and recoverable scenarios. Measure both **perceived availability** and **invariant correctness**; HTTP 200 counts alone are insufficient.

### 13.3. Pre-approval deployment checklist

- [ ] Multi-region drivers (DR, latency, residency) and business SLOs are explicitly stated.
- [ ] Written data is classified: which keys are independent vs. which carry protected invariants?
- [ ] Each consistency boundary has a documented write-ownership model enforced at storage.
- [ ] Policies exist for concurrent writes, duplicates, stale reads, and out-of-order events.
- [ ] Timestamps/LWW are not used for financial or resource-allocation data without proven business safety.
- [ ] Replication mode, durability scope, and real RPO are accurately understood.
- [ ] Failover covers fencing, replica verification, promotion, routing, and reconciliation.
- [ ] Failback never re-enables old write authority automatically; requires a valid new epoch/term/owner.
- [ ] Idempotency holds across regions for APIs and external systems like payments.
- [ ] Metrics detect invariant violations, conflicts, and replication lag.
- [ ] Network partitions, lost acks, duplicates, delayed replication, and failback have been tested.
- [ ] Inter-region latency, egress costs, data residency, and operational readiness are estimated.

## 14. Conclusion

**The antipattern is not using multiple regions; it is letting multiple regions make write decisions on the same dataset without defining authority and conflict handling.** Consequences include lost updates, overselling, duplicate payments, split-brain, or losing previously acknowledged writes.

Sound design starts with **business invariants → consistency boundaries → write authority → replication/failover → divergence detection and repair**. Only then select single-writer, partitioned ownership, merge-safe multi-writer, or globally consistent databases as appropriate. A reliable system knows **when writes are allowed, when to reject or wait, and how to recover without corrupting data**.
