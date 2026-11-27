# Multi-Region Design and Consistency Control

An application running in two regions may still return HTTP 200 when one region loses connectivity, yet its transactions are not necessarily safe. If both deployments accept balance updates into two unsynchronized databases, users could see stale values or suffer duplicate charges. Conversely, if every write must wait for acknowledgments from multiple regions, latency rises and an isolated side may have to halt writes. **Multi-region design is a simultaneous problem of availability, latency, consistency, data durability, and operability.**

In the **GCP Architecture Design** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects knowledge of project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases into a verifiable architectural decision. The goal is knowing **who is permitted to write**, **which reads are valid**, **what happens during a region outage or network partition**, and **how to prove failover meets SLO/RTO/RPO**. These decisions also shape security, deployment automation, observability, and cost.

## Learning Objectives

After this lesson, you will be able to distinguish zone vs. region fault tolerance; choose among active-passive, active-active with single or multiple writers, and geo-partitioning; explain strong consistency, read-your-writes, and eventual consistency; compare the data mechanics of Spanner, Cloud SQL, Firestore, Bigtable, and Cloud Storage; and design fencing, idempotency, failover/failback, and testing against business invariants.

## 1. A Region Is a Failure Domain, Not Just Where Compute Runs

A Google Cloud region contains multiple zones. Running workloads across multiple zones reduces single-zone dependency, but does not protect against a full-region failure. To survive a region outage, **every critical component on the transaction path** must be able to operate from another region: compute, storage, databases, networking, IAM, secrets, traffic routing, and integrated services.

| Scope | Example | Protection | Limitations |
|---|---|---|---|
| Zonal | VM, zonal Persistent Disk | Requires replicas or restores elsewhere | Losing one zone can stop the component |
| Regional / multi-zone | Regional MIG, regional GKE cluster, Cloud SQL HA | Survives select zone failures per configuration | Losing an entire region still disrupts service |
| Multi-region | Two Cloud Run services/GKE clusters; Spanner multi-region; Cloud Storage dual-region | Can continue after a region outage depending on model | Does not protect against bad code, IAM mistakes, or data deletion |
| Global frontend | Global external Application Load Balancer | Single endpoint routing to multi-region backends | Does not automatically make backends or databases multi-region |

**End-to-end assessment:** if the frontend spans two regions while the database has only one primary in region A, region B may keep passing health checks yet fail to write orders. If both rely on a secret, certificate, or IdP only reachable in A, an outage in A can also incapacitate B.

Scenarios to test include single-zone failure, full-region loss, **network partition** (both regions alive yet unable to communicate), and **logical/common-mode failures** such as bad rollouts, broken schema migrations, revoked IAM, or simultaneous data deletions. Replication does not replace backups, change controls, least privilege, or logical data-recovery plans.

## 2. SLO, RTO, RPO, Latency, and Consistency Contracts

Before picking a managed service, align targets by business flow, not infrastructure alone:

| Requirement | Design Question | Illustrative Example (Not a Google Cloud SLA) |
|---|---|---|
| Availability SLO | What percentage of valid requests are served in the measurement window? | 99.95% successful checkouts monthly |
| RTO | After a region outage, how long until critical functions recover? | 15 minutes |
| RPO | How much **committed/acknowledged data** can maximally be lost? | 5 minutes; some transactions require zero data loss |
| Consistency | After commit, who must see the new state and when? | Payments must never observe stale balances |
| Latency | p95/p99 for reads/writes at user locations? | Checkout p99 under 800 ms |
| Data residency | In which jurisdictions may data be stored and processed? | PII strictly in approved regions |
| Capacity | Can the surviving region absorb full traffic on failover? | Sufficient quotas, DB connections, and autoscaling |

**RPO is neither replica lag nor read staleness.** A healthy replica may normally lag very little yet still lose unshipped transactions if the primary vanishes abruptly. Conversely, a quorum-durable datastore can allow reads at older timestamps to lower latency on client request.

Define consistency contracts by data class:

- **Payments, balances, and inventory:** must enforce business invariants, preventing double debits or double stock deductions.
- **Orders:** post-commit state must be readable per API semantics; all retries must be idempotent.
- **Carts / user preferences:** may allow merges or session-scoped read-your-writes if business rules permit.
- **Catalogs and reports:** may use stale reads or eventual consistency within declared bounds.
- **Events and analytics:** can be processed asynchronously and replayed; never assume producer and consumer commit atomically.

## 3. Consistency Levels to Distinguish

| Level / Property | Meaning | Use Case |
|---|---|---|
| Strong consistency / linearizability | Reads after a completed write observe state consistent with a single global order | Just-committed transaction status |
| External consistency | Serializable transaction ordering that also respects real-time commit order | Spanner read-write transactions |
| Read-your-writes | A client never reads a version older than its own most recent write | User updates profile and reloads |
| Monotonic reads | Once a client sees a newer version, subsequent reads never regress to older ones | Switching routes from region A to B |
| Bounded staleness | Accepts reading an older snapshot bounded by time/timestamp | Dashboards tolerating 15-second lag |
| Eventual consistency | Once updates stop, replicas eventually converge | Multi-cluster Bigtable by default |
| Durability | Protects committed data from loss | Data may be durable even while temporarily unreachable from another region |

**Strong consistency inside one database does not create transactions across multiple systems.** For example, committing an order in a DB and publishing to Pub/Sub are two separate steps; if the process crashes in between, a transactional outbox, CDC, or reliable workflow is needed to avoid dropping events.

### During a Network Partition: Choose Availability or Safe Writes?

With **quorum synchronous** replication, a minority side lacking quorum may have to reject writes to preserve consistency. With **asynchronous multi-writer** replication, both sides can keep accepting writes independently, requiring conflict resolution, handling stale reads, and subsequent reconciliation. Designs must state the choice per operation rather than claiming the system stays both strongly consistent and writable everywhere during a partition.

## 4. Four Multi-Region Topology Patterns

### 4.1 Active-Passive

Region A serves primary traffic; region B maintains cold/warm/hot standby. Data is backed up or replicated to B. When A fails, runbooks activate compute, transfer write ownership and endpoints, and verify transactions.

**Strength:** single writer, relatively straightforward operations. **Trade-off:** RTO depends on detection/startup/routing time; RPO depends on replication. An under-provisioned standby leads to a technically successful failover where the system promptly collapses under load.

### 4.2 Active-Active Frontend, Single-Writer Database

Stateless APIs run in A and B. Both serve requests, yet only one primary/leader commits writes—or one database service coordinates writes through a leader. Frontends in B may traverse the network to reach the data leader in A.

**Strength:** higher frontend availability while avoiding split database writers. **Trade-off:** cross-region RTT on writes and a procedure to transfer write ownership when A goes down.

### 4.3 Active-Active Application and Multi-Region Data

Both regions accept write requests, yet data must be managed by **one system with suitable transaction/consensus semantics** or a custom-designed conflict resolution mechanism. Spanner multi-region is one option for quorum-consistent transactions; that is not the same as two independent Cloud SQL primaries magically forming a multi-writer database.

**Strength:** serves geographically distributed users with high availability. **Trade-off:** cross-region write coordination latency, replica costs, operations, and application compatibility.

### 4.4 Geo-Partitioned Ownership

Each tenant/shard has one owner region. Users in A write A-owned data, users in B write B-owned data; permitted datasets can replicate elsewhere. When transferring ownership during failover, use **fencing tokens/epochs or conditional transactions** so two regions never hold write ownership over the same shard simultaneously.

This pattern reduces write latency and supports data residency, but requires key-based routing, ownership-transfer logic, and cross-region access handling.

~~~mermaid
flowchart TB
  USER[Global users] --> LB[Global Application Load Balancer]
  LB --> A[Region A: application]
  LB --> B[Region B: application]
  A --> DATA[Data layer with clear consistency contract]
  B --> DATA
  DATA --> RA[Replicas / quorum Region A]
  DATA --> RB[Replicas / quorum Region B]
  DATA --> W[Witness if topology requires]
  A --> OBS[Monitoring / tracing / audit]
  B --> OBS
~~~

This is a **logical diagram**, not an exact configuration for every service. Spanner, Cloud SQL, Bigtable, and Firestore have very different topologies and write semantics. Every option needs its own concrete infrastructure diagram before implementation.

## 5. Routing: One Global Endpoint Is Not Enough for Failover

With **Cloud Run**, each service deploys to a single region. To run in two regions, deploy matching application versions in both and configure a global external Application Load Balancer with corresponding serverless NEGs. With **GKE**, you need multiple regional clusters/backends and proper routing policies; a single regional GKE cluster is not multi-region.

~~~bash
# Two regional deployments; does not yet include creating the load balancer
gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=REGION_A \
  --image=IMAGE_URL_BY_DIGEST

gcloud run deploy orders-api \
  --project=PROJECT_ID \
  --region=REGION_B \
  --image=IMAGE_URL_BY_DIGEST
~~~

The digest-pinned image path must be a valid Artifact Registry URL; uppercase tokens are placeholders. These two commands **do not** automatically create routing, IAM invoker bindings, certificates, a global load balancer, DNS, or DR policies. Provision those separately and synchronize configs/secrets/schemas across regions under change control.

### Application Health Checks and Cloud Run Service Health

Adding a serverless NEG does not automatically ensure every HTTP 5xx triggers traffic failover. Cloud Run provides **service health** integrated with the global load balancer for automatic failover/failback when a region becomes unhealthy; this requires readiness probes and prerequisites such as **at least one service-level or revision-level minimum instance per region** to compute health. Otherwise, use manual failover or another supported mechanism and drill it.

In GKE, readiness and backend health control where traffic lands; liveness controls when a process/Pod restarts. Avoid letting a transient dependency blip mark every Pod unhealthy simultaneously when controlled degradation is possible. Combine timeouts, retries with jitter, circuit breakers, and bulkheads.

### DNS, Sessions, and Capacity

DNS TTLs do not guarantee clients switch routes strictly on expiry: resolvers, browsers, SDKs, and connection pools cache differently. Keep sessions stateless or store them in a shared store with fitting consistency; sticky sessions do not survive losing a region.

If two regions normally split traffic 50/50, after losing one region, the survivor must handle nearly **100% of valid load**. Check quotas, min/max instances, cold starts, DB connection counts, dependency throughput, CPU budgets, egress traffic, and scale-out speed. Never size DR capacity around average load.

## 6. Comparing Multi-Region Data Options on GCP

Never choose a database just because it says “replicated”. Ask **where writes can happen, what commit conditions apply, whether reads see just-committed writes, whether region loss requires promotion, and whether two sites could write conflicting data**.

| Service / Config | Primary Replication & Consistency | Behavior on Region Failure | Key Decision Factors |
|---|---|---|---|
| **Spanner multi-region** | Cross-region quorum; external consistency for transactions; strong or stale reads | Capable of automatic leader failover per topology | Write latency, leader location, edition, cost, and data residency |
| **Firestore multi-region** | Replicated across a defined region set; supports reads/writes during single-region loss | Continues serving per managed topology | Location picked from supported configs; higher latency/cost vs. regional |
| **Cloud SQL HA + cross-region replica** | Synchronous HA within region; cross-region read replica is **asynchronous** | Typically requires replica promote/failover and switching write endpoint; RPO may be > 0 | Single-primary model, replication lag, DR runbooks |
| **Bigtable multi-cluster** | Inter-cluster replication is **eventual** by default | Can route to another cluster; risks stale reads post-failover | App profile/routing, conflict resolution, consistency contract |
| **Cloud Storage dual-/multi-region** | Strong consistency for metadata/object operations; object data replicates asynchronously across regions | Continues serving replicated objects; newly written un-replicated objects may be unavailable | Default vs. turbo replication, object RPO, data placement, backups |

A **regional** configuration often suffices for most workloads when the business accepts hour-scale RTO and backup/restore DR. Conversely, strong consistency on the datastore does not automatically make APIs, secrets, networking, or identity providers available in the second region.

## 7. Spanner: Quorum, Leaders, Transactions, and Stale Reads

A Spanner regional configuration maintains read-write replicas across multiple zones in one region. **Spanner multi-region** distributes voting/read-write replicas across multiple regions—often with a witness region per instance configuration—and requires a supporting edition such as **Enterprise Plus**. Supported configurations and locations are published by Google Cloud; you cannot arbitrarily pair any two regions and call it a Spanner multi-region configuration.

In multi-region, most topologies designate a **leader region**; clients can live in multiple regions, yet write transactions coordinate with the leader and must reach quorum per the replication topology. **External consistency** keeps committed transactions ordered consistently with real-world time. When the leader region fails, managed consensus can elect a new leader as long as quorum remains. This differs fundamentally from two app instances racing to write to two separate databases.

### Transaction and Read Patterns

- **Read-write transactions:** use for global invariants such as placing orders and deducting stock; handle transaction aborts/retries via client libraries.
- **Strong reads:** observe all transactions committed before the read started per Spanner's guarantees.
- **Bounded/exact stale reads:** accept an older snapshot to cut latency for dashboards, feeds, or analytics; never use stale reads for payment decisions needing current balances.
- **Read-only regions:** serve local reads well, yet cannot act as standalone DR if the instance's write quorum is lost.
- **Read-lease regions:** in select configs reduce strong-read latency in non-leader regions at a trade-off in write latency; benchmark before enabling.

~~~mermaid
sequenceDiagram
  participant C as Client in Region B
  participant L as Spanner leader Region A
  participant Q as Voting replicas
  C->>L: Read-write transaction
  L->>Q: Replication / quorum
  Q-->>L: Quorum acknowledgments
  L-->>C: Commit succeeded
  Note over C,Q: Logical illustration only; replica counts and quorum vary by instance configuration
~~~

**Write latency follows geography:** the farther voting replicas sit from the leader, the higher network RTT climbs. Co-locate write-heavy workloads near the leader region where fitting, measure real transaction latency, consider read-only/stale reads for distant users, and verify compliance before picking replica locations.

Never claim “Spanner multi-region = zero RTO for the entire app”: the database quorum may stay healthy while the global frontend, auth, caches, or SaaS dependencies go down. Nor does transaction RPO mean post-commit events or separate file uploads are automatically replicated.

## 8. Cloud SQL: Intra-Region HA vs. Cross-Region DR

Cloud SQL high availability (regional availability) protects against single-zone failures via a primary and standby in different zones. **A cross-region read replica is asynchronous**, not a managed synchronous standby like intra-region HA. When the primary's region fails, the cross-region replica may be missing recently committed transactions.

### Standard DR Pattern

~~~mermaid
flowchart LR
  APP_A[Application Region A] --> PRIMARY[Cloud SQL HA primary Region A]
  PRIMARY -. asynchronous replication .-> REPLICA[Read replica Region B]
  APP_B[Application Region B] -. post-DR .-> REPLICA
  REPLICA --> PROMOTE[Promote / replica failover per edition]
  PROMOTE --> NEW[New write primary in Region B]
~~~

When region A becomes unavailable:

1. Incident commander confirms the outage and DR activation threshold.
2. Check recent **replication state/lag** near failure time to assess potentially un-replicated data.
3. **Fence** the old primary if reachable; prevent two endpoints from receiving independent writes once connectivity returns.
4. Promote the cross-region replica per the DR runbook, or trigger configured replica failover.
5. Switch the database write endpoint, refresh connection pools, and verify transactions/business invariants.
6. Re-enable HA on the new primary and establish a reverse cross-region replica to restore DR capability.

**Promotion is generally a deliberate decision**, unlike automatic zonal HA. Cloud SQL **Enterprise Plus** offers **advanced disaster recovery** supporting designated DR replicas, replica failover, and planned switchover. Planned switchover can execute with zero data loss under service conditions; **replica failover during a disaster can still lose data due to replication lag**. Never cite zero-loss planned switchover to promise RPO 0 for an unplanned region outage.

In an active-active frontend / single-writer Cloud SQL design, enforce **one write primary** at all times. If B holds only a cross-region read replica, reports can read from B if stale reads are acceptable, while writes from both A and B must target the primary. Enabling writes to two independent primaries creates un-reconcilable transaction conflicts and breaks single-primary Cloud SQL replication semantics.

### Recovery and Failback

Never flip traffic back to region A the instant A comes back online. Region B may now be the authoritative source of truth with new commits. Failback must sync changes in reverse, verify checkpoints, re-establish replication, perform a planned ownership switch, and decommission old resources only after zero active clients remain.

## 9. Firestore Multi-Region vs. Bigtable Multi-Cluster: Fundamentally Different

**Firestore multi-region** is a managed database location distributing replicas per supported configurations (typically two read-write regions plus a witness). The database is designed to keep serving reads and writes during a single-region failure per topology. Firestore is not equivalent to manually creating two regional databases and syncing them with scripts. Location is chosen at database creation; verify supported regions, latency, and residency constraints beforehand because locations cannot be arbitrarily changed afterward.

Firestore executes transactions inside its storage system with database-level consistency guarantees. Clients must still retry on transaction contention, implement idempotency, and respect document/query/indexing limits. Never assume a Firestore write automatically joins an atomic distributed transaction with external message publishing.

**Bigtable replicated instances** allow multiple clusters across zones/regions. By default, mutations replicate **asynchronously** and clusters converge under **eventual consistency**. App profiles dictate routing—either multi-cluster (automatically failing over to another cluster when one is unavailable) or single-cluster (pinning reads/writes to one cluster for stronger consistency semantics under usage conditions).

Watch-outs with Bigtable:

- Reading from another cluster immediately after a write can return stale values.
- Certain single-cluster app-profile configurations achieve read-your-writes under normal conditions, yet failover can break that expectation.
- If two clusters update the same cell key/timestamp, the service applies its built-in conflict resolution; last-write-wins semantics are unsuitable for many financial transactions.
- Distinguish single-row transactions under single-cluster routing from multi-cluster routing; never extrapolate single-cluster transaction guarantees across a replicated multi-cluster topology.

If user-facing data must continuously read the newest version across regions, do not pick multi-cluster Bigtable by default and claim strong consistency. Conversely, for time-series analytics or catalogs tolerating staleness at high throughput, eventual consistency may fit well.

## 10. Cloud Storage: Strong Metadata Consistency, Asynchronous Cross-Region Replication

Cloud Storage regional buckets replicate redundantly across zones within one region. Dual-region or multi-region buckets store copies across geographies and are designed to keep serving from surviving regions during a region outage—**for data that has finished replicating**.

There is no contradiction between Cloud Storage having strong consistency yet having cross-region RPO: **object metadata and write operation results are strongly consistent**, whereas **newly written object bytes replicate across regions asynchronously**. If the ingesting region goes down before replication completes, the object may be temporarily unreachable until recovery—and in rare physical destruction scenarios, data loss is possible.

| Mode | Replication Target for New Objects | Notes |
|---|---|---|
| Default dual-/multi-region | Designed for 99.9% within 1 hour and 100% within 12 hours | Service target; not every object is immediately available in region B upon write |
| Dual-region with turbo replication | Designed to replicate 100% of new objects within a 15-minute RPO target | Applies only to supported dual-regions and incurs extra cost |
| Two separate buckets with cross-bucket replication | Replication depends on configured mechanism/job | Does not share the same RPO or strong single-bucket semantics as a dual-region bucket |

Architecture diagrams should separately trace **transactional state** (Spanner/Cloud SQL), **object storage** (Cloud Storage), and **event delivery** (Pub/Sub). A durable order record does not prove the invoice PDF or notification email event has already replicated to the backup region.

Multi-region storage still needs object versioning, retention/backups, and delete protections. Replication faithfully propagates both legitimate edits and logical mistakes; it never substitutes for independent restore points.

## 11. Events and Messaging: The Same Business Action Can Run Multiple Times

In multi-region architectures, apps often use **Pub/Sub** to decouple synchronous requests from email, invoicing, or analytics processing. However, region switchovers, timeouts, retries, or consumer restarts can cause a message to execute multiple times. **Message delivery does not equal an exactly-once business effect.**

Specify in the contract:

- **Producer:** when is an event considered emitted? Are unique event IDs and source transaction IDs persisted?
- **Consumer:** if two messages with the same event ID arrive, do business side effects duplicate?
- **Ordering:** is ordering required per order or tenant? Are out-of-order arrivals tolerated during retries/failovers?
- **Retry/DLQ:** on downstream failures, how long to retry, where does the dead-letter queue live, and who is authorized to replay?
- **Regional location:** do message storage/processing regions satisfy residency and DR mandates?
- **Backlog:** does the surviving region have enough consumer capacity for both accumulated backlogs and live traffic?

Pub/Sub supports **message storage policies** restricting which regions may store/process payloads. A global endpoint does not mean every message is stored in all regions; nor does adding a region to the policy create complete DR if publishers/consumers run in only one region. With `enforceInTransit`, clients outside allowed regions may need regional/locational endpoints. Weigh latency, egress, ordering requirements, and availability trade-offs.

### Transactional Outbox When DB and Pub/Sub Are Independent Systems

Most applications cannot span a single atomic transaction across a database and Pub/Sub. Two failure modes arise:

1. **DB commits, event publish fails:** the order exists, yet downstream workers never learn of it.
2. **Event publishes, DB rolls back:** downstream processes a phantom order that never existed.

The **transactional outbox** pattern records the business mutation and an event record in **the same database transaction**. Post-commit, a publisher/CDC worker reads outbox rows and sends to Pub/Sub; if it publishes yet crashes before marking sent, the message may be republished. Consumers must be idempotent.

~~~mermaid
sequenceDiagram
  participant API as orders-api Region A/B
  participant DB as Consistent database
  participant PUB as Outbox publisher
  participant MQ as Pub/Sub
  participant CON as Consumer
  API->>DB: Transaction: update order + INSERT outbox
  DB-->>API: Commit
  PUB->>DB: Read unsent outbox rows
  PUB->>MQ: Publish event_id
  MQ-->>PUB: Acknowledge
  MQ->>CON: Deliver event_id
  CON->>CON: Dedupe by event_id
  CON-->>MQ: Ack on completion
~~~

An outbox reduces dropped-event risk, yet does not prevent duplicate emails or payments on its own. Consumers must record **processed-event IDs** inside the same transaction as their local database update, or supply an idempotency key to external systems.

## 12. Preventing Split Brain with Write Ownership and Fencing

**Split brain** occurs when two sides both believe they hold write authority over the same dataset. A dangerous scenario is region A losing control-plane contact while still accepting requests, while region B has already been promoted as the new primary. Once networking heals, two divergent write histories may have no valid merge order.

Safeguards:

1. **Enforced single writer:** not merely “config says B is primary”, but actual write permissions and routing endpoints enforce it.
2. **Quorum / consensus:** the datastore accepts writes only where commit quorum holds.
3. **Fencing tokens / monotonic epochs:** each leadership transfer issues a higher epoch; storage targets reject stale tokens.
4. **Controlled leases:** lease expiry alone fails if a paused worker wakes up and writes; enforce fencing at the target resource rather than relying solely on local clocks.
5. **Explicit promotion procedures:** confirm the old primary can no longer write, or rely on managed datastore quorum consensus.
6. **Reconciled failback:** never re-enable the old primary as writer simply because the original region comes back up.

### Illustrating Optimistic Concurrency and Fencing

A transaction inside a **single datastore with suitable consistency** can require a record version to match expectations:

~~~sql
-- Example logic inside one transaction-supporting database; not a protocol
-- for transferring ownership between two independent databases.
UPDATE inventory
SET available = available - 1,
    version = version + 1
WHERE sku = :sku
  AND available > 0
  AND version = :expected_version;
~~~

If 0 rows update, the caller checks remaining inventory and version, retrying or aborting per business rules. For fencing, require a valid epoch verified against a single authoritative source. **Crucial:** conditional `UPDATE`s on two independent databases do not eliminate split brain between them; you need a shared ownership authority or single-writer isolation.

### When the Old Region Recovers

The old primary may hold accepted transactions that never replicated out. Never merge two write histories by picking “whichever timestamp is newer” for balances, payments, or inventory. Establish the authoritative source of truth, match transaction IDs/checkpoints, run compensating entries where feasible, and get owner sign-off on the reconciliation plan.

## 13. Designing Idempotency, Versioning, and Conflict Resolution

A request may succeed on the server while the response drops during failover. A client retrying in region B cannot tell whether region A already committed. Prevent duplicate execution with an **idempotency key** supplied by the client or gateway, stable across retries of the same logical operation.

### Simple PostgreSQL Pattern for Idempotency

~~~sql
CREATE TABLE request_dedup (
  idempotency_key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  response_payload JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbox_events (
  event_id UUID PRIMARY KEY,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ
);
~~~

In a Spring Boot service handling orders, design the transaction:

1. Receive the idempotency key and hash the payload; reject mismatched payloads reusing an existing key instead of returning a wrong cached response.
2. Claim the key via unique constraint / transaction; if another worker is actively processing that key, wait briefly or return a retryable status.
3. Check inventory and write the order **in the same transaction** as the idempotency record and outbox event.
4. Commit; return the stored response if the client resends the same key.
5. Workers publish outbox events; consumers deduplicate using event IDs or business transaction IDs.

Every atomicity step inside the database must run in **one real transaction**, not sequential API calls hoping things “run in order”. For Spanner, adapt syntax/schemas and use matching transaction APIs; never copy PostgreSQL SQL directly to Spanner without adjustments.

### Conflict Resolution Strategies

| Strategy | Appropriate For | Unsuitable For |
|---|---|---|
| Single writer / per-key serialization | Money, inventory, order state | Workloads needing independent writes everywhere without routing |
| Compare-and-swap / optimistic versioning | Profile updates, aggregates inside one consistent datastore | Two independent databases lacking shared version sync |
| Field-by-field merge | Carts, user settings with clear rules | Concurrent updates to a single financial transaction field |
| CRDTs or commutative operations | Counters, sets, or collaboration with fitting semantics | Irreversible or non-commutative business actions |
| Last-write-wins | Low-risk data tolerating lost updates | Payments, ledgers, audits, or access permissions |
| Saga + compensating actions | Multi-service workflows without distributed transactions | Guaranteeing full physical rollback of all external effects |

**Wall-clock timestamps do not establish true ordering** across regions. Use sequences, transaction versions, or business command IDs, and define policies for late, out-of-order, or duplicate events. In distributed Sagas, design compensations carefully: a sent email cannot be “rolled back”, and a settled payment may require an independent refund transaction.

## 14. Design Case Study: Java/Spring Boot Ordering Application

Suppose a business serves customers across two regions; the frontend must keep accepting traffic during a region outage, payments must never double-charge, invoice PDFs must stay in compliant locations, and events must be replayable.

**Reference design:** two Cloud Run services (or two regional GKE clusters) running identical image digests, a global external Application Load Balancer with service-health/failover policies; transactional order data in a Spanner multi-region configuration **supported in the chosen geography**; objects in a geographically compatible Cloud Storage dual-region; Pub/Sub as the event bus with transactional outboxes and idempotent consumers.

~~~mermaid
flowchart TB
  USER[Clients] --> GLB[Global external ALB]
  GLB --> API_A[Cloud Run Region A]
  GLB --> API_B[Cloud Run Region B]
  API_A --> SP[Spanner multi-region: orders / ledger]
  API_B --> SP
  SP --> OUT[Outbox table / publisher]
  OUT --> PUB[Pub/Sub]
  PUB --> WORKER_A[Consumer Region A]
  PUB --> WORKER_B[Consumer Region B]
  API_A --> OBJ[Cloud Storage dual-region: invoice object]
  API_B --> OBJ
  API_A --> OBS[Cloud Monitoring / Logging / Tracing]
  API_B --> OBS
~~~

Consumers in A/B must share **the same subscription or intentionally scoped subscriptions**; giving each side an independent subscription delivers every message to both, which the application must intend. This diagram is conceptual: do not assume Pub/Sub acts like a quorum-replicated database, nor assume any arbitrary pair of regions is supported by Spanner or Cloud Storage.

### Per-Component Consistency Contracts

| Flow | Contract | Mechanism |
|---|---|---|
| Order creation & stock deduction | Two orders never consume the same valid inventory unit; post-commit reads are accurate | Spanner transactions and unique business keys |
| Payment | Retries never trigger a second charge | Idempotency key honored by payment provider or controlled ledger |
| `order-created` event | Zero dropped events post-DB commit; duplicates tolerated | Transactional outbox and consumer deduplication |
| Cart | Slightly stale session-scoped state tolerated | App/session policy, merge/version rules |
| Invoice PDF | Never rely on backup region copy before replication completes if strict RPO applies | Dual-region storage, replication monitoring, and business retries |
| Reporting | Stale reads allowed within approved lag bounds | Stale reads / analytics pipeline |

If the business mandates **RPO 0 for customer-confirmed invoice files**, 15-minute turbo replication alone is insufficient. Adjust the confirmation flow (complete only once target durability is reached), write a second confirmed copy separately, or ensure invoices can be deterministically regenerated from the transactional database.

### Critical Request Flow

1. Gateway authenticates the request and routes to a healthy application region per policy.
2. Application validates the idempotency key; a single transaction mutates inventory/order state.
3. The same transaction persists the outbox event and idempotency/response state.
4. API returns success after valid commit; if the client disconnects, retries return the exact same business outcome.
5. Publisher forwards outbox rows to Pub/Sub; idempotent consumers process them.
6. Invoice generation runs asynchronously, monitoring replicated objects and updating status appropriately.

Separate **transactional consistency** from **experience availability**: the app may temporarily defer emails or dashboard updates without ever violating payment invariants.

## 15. Failover and Failback: More Than Just Shifting Traffic

A multi-region architecture needs **two distinct procedures**:

- **Failover:** recover in the surviving region while preserving write ownership, data correctness, and RTO/RPO.
- **Failback:** once the original region recovers, synchronize data in reverse as needed, safely transfer ownership and traffic back. Never auto-failback merely because a health check turned green.

### Ordered Failover Runbook

1. **Detect and verify:** correlate multi-vantage synthetic checks, user errors, backend health, database status, and cloud status. Rule out bad configs, rollouts, or localized network blips.
2. **Declare DR:** incident commander triggers failover per defined thresholds; log timestamps and approvers.
3. **Verify consistency:** does the database have self-healing quorum or require promotion? If single-primary, verify replication lag and potential RPO loss.
4. **Fence:** verify the old writer is invalidated by the authoritative system; never allow both A and B to commit to the same dataset.
5. **Activate capacity:** scale workloads in region B; verify quotas, secrets, IAM, KMS, network routes, external allowlists, and DB connections.
6. **Shift traffic:** execute global LB/service health, routing policies, or DNS changes per design; update write endpoints when actually switching the database primary.
7. **Verify:** run idempotent smoke tests, business reads/writes, check event backlogs, object access, SLOs, and data invariants.
8. **Stabilize:** observe for a full operational window, keeping region B as primary/owner per policy rather than flipping back immediately.
9. **Plan failback:** re-establish reverse replication, audit all transactions, transfer ownership under control, and rehearse failback rollback.

In **Spanner multi-region**, quorum-based leader failover is managed; applications should not build Cloud SQL-style manual promote scripts for a managed quorum service. In **Cloud SQL DR**, replica promotion/failover and connection re-pointing are part of the runbook; advanced DR has specific procedures. Branch runbooks by datastore instead of using one generic “promote database” command for every technology.

### Go / No-Go Decision Points

Set clear criteria upfront: how long must a region outage last before declaring DR? If replication lag exceeds RPO, do you halt writes to wait for sync or accept restoring from an older point? Who is authorized to sign off on potential transaction loss? If old-primary fencing cannot be confirmed, should the system enter read-only/degraded mode or pause writes? Lock these decisions with business owners **before** an incident.

### Avoiding the “Auto-Failover = Guaranteed Correct Data” Fallacy

Automated traffic routing often completes faster than databases, caches, and consumers synchronize. If frontends shift to B while the database only serves stale reads, returning HTTP 200 on payments is worse than a temporary refusal. Gate readiness and feature flags by **capability**: allow catalog browsing while blocking checkout until consistency gates pass.

## 16. Monitoring SLOs and Consistency

Dashboards must correlate signals across **applications, datastores, messaging, and traffic routing**, broken down by region and release version:

| Signal | How to Use |
|---|---|
| Per-region request success/error, p95/p99 latency | Spot user-facing errors and asymmetric backend performance across regions |
| Global LB backend health, traffic split, service health | Detect misrouting, lost backends, or stalled failovers |
| DB write/read latency, transaction aborts/retries | Detect quorum/leader shifts and WAN RTT impact |
| Cloud SQL replication state/lag | Estimate potential data loss prior to promoting a replica |
| Spanner transaction latency, lock contention, leader region | Validate topology choice and commit latency shifts |
| Bigtable per-cluster replication lag and errors | Monitor convergence and stale-read risks during cluster shifts |
| Cloud Storage replication/RPO metrics | Spot objects lagging behind cross-region redundancy targets |
| Pub/Sub backlog, oldest unacked message, retries/DLQ | Detect regional consumer lag and duplicate processing risks |
| Idempotency conflicts, event dedupes, fencing rejections | Verify safe retries and catch competing writers |
| IAM/secret/KMS failures, DNS, and egress latency | Catch non-database dependency outages |

**Proactively measure consistency**, rather than waiting for users to report missing data. For example, run synthetic transactions on a test tenant, write a unique ID, read from both regions per the consistency contract, and measure convergence time for stale-read views (when staleness is permitted). Clean up synthetic test data and isolate it from real user transactions.

Measure **actual RTO** from incident onset (or detection, documented clearly) until critical transactions meet SLOs again. Measure **actual RPO** via transaction IDs/checkpoints confirmed before the failure versus those present in the surviving system post-failover. Never treat “replica healthy” as proof of zero lost writes.

### Observability for Java/Spring Boot

Emit structured logs including region, release, request ID, **sanitized** idempotency key, transaction ID, and retry/rollback outcomes. Propagate W3C trace context across HTTP, gRPC, and event headers where appropriate. Alert on error-budget burn and invariant violations, not merely CPU or running Pod counts. Never log payloads containing PII, credentials, tokens, card numbers, or full financial events.

## 17. Game Days: Testing When Networks and Data Misbehave

Every scenario requires an approver, sandbox/staging scope, rollback plan, target load, and acceptance metrics. Never inject production outages purely for testing without change approvals and safety guardrails.

| Scenario | What to Prove | Failure Signals |
|---|---|---|
| One region backend unhealthy | Global LB / service health shifts traffic to healthy region | Requests keep hitting broken backend; region B overloads |
| Loss of Cloud SQL write-primary region | Promotion/replica failover runbook completes within approved RTO | Missed fencing, stale write endpoints, unrecognized lag exceeding RPO |
| Spanner leader region unavailable | Quorum/leader failover and transaction retries recover | App retry storms, business errors, or prolonged latency breach |
| Bigtable cluster switch | App handles/flags stale data per contract | Reading stale values as current for payment decisions |
| Unreplicated new object | App handles temporary object unavailability gracefully | Returning permanent failures or assuming un-replicated files are safe |
| Pub/Sub consumer failover | Zero lost business actions; replay and dedupe hold | Duplicate emails/charges, ignored DLQs |
| A and B partitioned yet both alive | Only authorized writer commits; client errors stay bounded | Split brain, two irreconcilable ledgers |
| Bad IAM or secret rollout in both regions | Break-glass/rollback works with bounded blast radius | Common-mode outage despite multi-region compute |
| Failback after recovery | Data stays consistent; old region never double-writes | Dropping transactions created in DR region |

### Measurement Drill Procedure

1. Record a 30–60 minute baseline (or fitting load window): throughput, latency, lag, error rates, and capacity.
2. Inject controlled failure into **one component** (avoid stacking scenarios before understanding single outcomes).
3. Measure MTTD, decision time, routing shift time, database recovery, and time until business transactions succeed again.
4. Reconcile confirmed transaction counts and exact IDs before/after failure; catch missing or duplicate IDs, not just row counts.
5. Verify the consistency contract: strong/read-your-writes/bounded staleness, ordering, and compensation.
6. Recover and test failback; confirm zero clients remain pinned to old endpoints.
7. File action items: fix runbooks, raise quotas, sharpen monitoring, tune retry loops, or revise architecture.

Archive game-day results as evidence for SRE/architecture reviews. If RPO fails, do not simply crank up retries—revisit data synchronization methods or renegotiate targets with business owners.

## 18. Security, Residency, Cost, and Operations

**Multi-region expands the governance surface.** Every region needs IAM bindings, runtime service identities, KMS/secret access, network egress policies, registry/image access, telemetry, and quotas. Verify encryption in transit across regions, TLS, audit logs, data locality, and key availability when a region goes down. For geographically restricted data, pick approved database/bucket region pairs; never assume “multi-region” automatically satisfies residency laws.

Costs and trade-offs to budget:

- **Standby compute:** active-active keeps replicas warm continuously; warm/hot standbys cost capacity to cut RTO.
- **Database replication / quorum:** replica/storage fees and WAN transaction latency; Enterprise Plus or higher editions may be required for topologies.
- **Network transfer / egress:** writes from B to leader A, cross-region objects, apps calling on-prem DBs or third parties.
- **Storage and backups:** object versioning, dual-region/turbo replication, snapshots, and isolated backups.
- **Observability and testing:** synthetic probes, log/trace ingestion, DR game days, private connectivity.
- **Business risk:** cost of downtime and corrupted transactions often dwarfs infrastructure spend.

Never multiply two regions' availability numbers as if failures are independent. One bad image, rollout, policy, or secret can break both simultaneously; end-to-end SLOs and common-mode testing reveal true redundancy value.

### Initial Option Selection Matrix

| Primary Need | Direction to Consider | What to Verify Before Deciding |
|---|---|---|
| Hour-scale RTO, tight budget | Active-passive with DR backups / cross-region replica | Restore time, RPO, and sufficient quotas |
| Frontend must survive region outage, DB has one writer | Active-active compute + Cloud SQL DR or single-leader DB | Write RTT, promotion, fencing, and app reconnects |
| Global transactions must be strongly consistent | Spanner multi-region | Edition, supported topology, quorum/leader latency, and cost |
| Managed document DB surviving region outage | Firestore multi-region location | Immutable location, query/transaction semantics, latency, and quotas |
| Time series tolerating stale reads | Bigtable replicated clusters | App profiles, conflicts, replication lag, and read semantics |
| Object data serving multiple regions | Cloud Storage dual/multi-region | Replication RPO, turbo availability, residency, and backups |
| Per-tenant data pinned by geography | Geo-partitioning with explicit ownership | Cross-tenant access, fencing, and ownership-transfer workflows |

## 19. Design Exercise

**Context:** an e-commerce platform with a Spring Boot API, PostgreSQL, RabbitMQ, invoice image objects, and an external payment gateway. Users span two regions; business mandates checkout never double-charges, catalog can lag slightly, transaction RTO is 20 minutes, and order-data RPO must be explicitly defined.

1. Map failure domains: region, zone, DB writer, identity provider, external payment, event bus, object storage, and DNS.
2. Compare **active-passive Cloud SQL cross-region replica** vs. **active-active API + Spanner multi-region**. Detail RTO, RPO, write latency, cost, schema/code changes, and regional support conditions for each.
3. Write consistency contracts for payments, orders, carts, catalogs, and invoices.
4. Design idempotency keys, transactional outboxes, and consumer deduplication. Describe what happens if the API commits and disconnects before sending the HTTP response.
5. If choosing Cloud SQL, write a runbook for promotion, fencing, endpoint switching, and failback. If choosing Spanner, describe quorum/leader behavior and transaction retries.
6. Design global load balancing and health-based failover checks. Specify minimum instances, timeouts, and region B capacity.
7. Propose alerting dashboards for replication lag, transaction latency, object replication RPO, event backlogs, and invariant violations.
8. Plan three game days: region loss, network partition, and duplicate messages. Define go/no-go criteria and how to measure RPO beyond checking Pod health.
9. Estimate cost categories across cross-region replication, egress, standby, and monitoring; verify data residency.

**Deliverables:** an architecture diagram, datastore selection table, consistency contract, failover/failback runbook, test matrix, and open risks. No production resources required; a PoC may run in an authorized sandbox.

## 20. Pre-Approval Multi-Region Architecture Checklist

- [ ] SLOs, RTO, RPO, and consistency contracts are signed off by business/data owners.
- [ ] All critical failure domains and dependencies are mapped.
- [ ] Every dataset has a designated system of record, write owner, read policy, and conflict policy.
- [ ] Sync/quorum replication is distinguished from async replication, with promotion triggers defined.
- [ ] Fencing prevents the old primary from writing post-failover; no uncontrolled split brain is possible.
- [ ] Clients use idempotency keys and consumers enforce deduplication where needed.
- [ ] Outboxes or reliable workflows bridge database transactions and event publication.
- [ ] Traffic routing is tested under unhealthy backend/app states, not just VM shutdowns.
- [ ] Backup region holds adequate capacity, quotas, IAM, KMS, networking, secrets, and DB connections.
- [ ] Databases, storage, and messaging each track separate RPO/consistency guarantees without conflation.
- [ ] Objects/transactions are protected against accidental deletion or bad rollouts; backup restores are tested.
- [ ] Data residency, privacy, and cross-region transfers are reviewed.
- [ ] Per-region monitoring tracks SLOs, latency, replication lag, stale reads, and invariant violations.
- [ ] Failover runbooks designate decision makers, stop/go gates, and read-only fallback modes.
- [ ] Failback plans include reverse synchronization and checks confirming zero dual writers.
- [ ] Game days measured real RTO/RPO and standby costs fit within budget.

## 21. Conclusion

Multi-region design does not end with deploying an app in two places. Architecture teams must choose a write-ownership model, specify consistency guarantees per data class, understand how Google Cloud products replicate and fail over, and validate latency, availability, and RTO/RPO trade-offs. Spanner, Firestore, Cloud SQL, Bigtable, and Cloud Storage carry distinct semantics; the right choice rests on business invariants and tolerance for stale or lost data. Only when safe transactions, idempotency, fencing, tested routing, cross-region observability, and failback runbooks work together can a system recover **while preserving business correctness** during a region outage.

## References

- [Google Cloud Architecture Center — Architecting disaster recovery for cloud infrastructure outages](https://docs.cloud.google.com/architecture/disaster-recovery)
- [Google Cloud Well-Architected Framework — Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Cloud Run — Serve traffic from multiple regions](https://docs.cloud.google.com/run/docs/multiple-regions)
- [Cloud Run — Automate cross-region failover with service health](https://docs.cloud.google.com/run/docs/configuring/configure-service-health)
- [Spanner — Regional, dual-region, and multi-region configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations)
- [Spanner — Reads outside transactions, strong and stale reads](https://docs.cloud.google.com/spanner/docs/reads)
- [Spanner — Leader-aware routing](https://docs.cloud.google.com/spanner/docs/leader-aware-routing)
- [Spanner — Replica region types and voting quorum](https://docs.cloud.google.com/spanner/docs/region-types)
- [Cloud SQL for PostgreSQL — About disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/intro-to-cloud-sql-disaster-recovery)
- [Cloud SQL for PostgreSQL — Promote cross-region replicas](https://docs.cloud.google.com/sql/docs/postgres/replication/cross-region-replicas)
- [Cloud SQL — Advanced disaster recovery](https://docs.cloud.google.com/sql/docs/postgres/use-advanced-disaster-recovery)
- [Firestore in Native mode — Database locations](https://docs.cloud.google.com/firestore/native/docs/locations)
- [Firestore in Native mode — Understand reads and writes at scale](https://docs.cloud.google.com/firestore/native/docs/understand-reads-writes-scale)
- [Bigtable — Replication overview](https://docs.cloud.google.com/bigtable/docs/replication-overview)
- [Bigtable — Examples of replication configurations](https://docs.cloud.google.com/bigtable/docs/replication-settings)
- [Cloud Storage — Data availability and durability](https://docs.cloud.google.com/storage/docs/availability-durability)
- [Pub/Sub — Message storage policies](https://docs.cloud.google.com/pubsub/docs/resource-location-restriction)
