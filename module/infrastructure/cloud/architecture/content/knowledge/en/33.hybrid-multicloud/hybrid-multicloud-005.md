# Data Synchronization and Operations During Connectivity Interruptions

## 1. Why Is Data Synchronization a Challenge in Hybrid and Multi-Cloud?

Hybrid architectures combine on-premises infrastructure with the cloud; multi-cloud architectures distribute workloads or data across multiple cloud providers or regions. Environments connect via VPNs, private links, dedicated circuits, or the Internet. Connectivity can become slow, lose packets, suffer regional outages, face bandwidth constraints, or drop completely.

When connectivity is stable, systems synchronize databases, objects, events, files, and identities on a schedule or continuously. When a link drops, one side may continue accepting transactions while the other receives no updates. Both sides can diverge; messages can be queued, delivered multiple times, or arrive out of order; replication lag climbs; and applications may not know whether a prior transaction committed remotely.

A sound design must answer: which data needs synchronization; which system is the source of truth; which workloads keep operating when the link drops; how much data loss or staleness is acceptable; if both sides accept writes, how conflicts are resolved; and upon reconnect, in what order events replay and how duplicate side effects are prevented.

In the CLOUD_ARCHITECTURE module, these decisions connect networking, databases, storage, event architecture, identity, disaster recovery, and operations. The goal is to balance reliability, security, scalability, performance, cost, and operability under distributed conditions.

Running example: a booking platform with a cloud control plane and on-site hotel systems. Each hotel site must continue check-ins and room status updates when the cloud link goes down. The cloud still serves global search, though site data may be stale. When connectivity returns, both sides must merge changes without creating duplicate bookings or overwriting state incorrectly.

## 2. Classify Data Before Choosing a Synchronization Mechanism

Do not use a single replication mechanism for all data types. Each type differs in write authority, consistency, size, sensitivity, and rebuildability.

| Data type | Characteristics | Design questions |
| --- | --- | --- |
| Transactional records | Bookings, payments, inventory, ledger | Where is the authoritative write source? Must double bookings be prevented? |
| Reference/master data | Properties, room types, product catalog, policies | Who can update it? How stale can replicas be? |
| Operational events | Check-ins, cancellations, status changes | How are ordering, duplicates, and replay handled? |
| Read models/projections | Search indexes, dashboards, materialized views | Can they be rebuilt from sources/event logs? |
| Files/objects | Photos, invoices, exports, documents | How are versioning, checksums, delete markers, and metadata handled? |
| Configuration/secrets | Runtime configs, certificates, key references | Who distributes them? Must actual secrets be synchronized? |
| Telemetry | Metrics, logs, traces | Can they be buffered and sent later? Are retention/egress controlled? |

### 2.1. Define Ownership and Write Authority

For each aggregate or data type, clearly document the owner system; where writes are permitted; replicas/read-only consumers; fields editable at edge/local sites; ownership transfer rules during failover; and conditions and approvals required to change authority.

A safe principle is to avoid multi-site writes on critical data without a proven conflict resolution algorithm. You can partition ownership by tenant, property, region, or aggregate so each object has only one writer at a time.

## 3. Consistency Levels and Business Selection

| Model | Characteristics | Suitable examples |
| --- | --- | --- |
| Strong/linearizable consistency | Readers observe changes in a guaranteed global order | Ledgers or operations requiring strict ordering |
| Read-your-writes | Writers see their own updates immediately | Staff who just updated a room status |
| Monotonic reads | Readers never revert to older state already seen | Operational dashboards |
| Eventual consistency | Without new updates and while sync continues, replicas converge | Search indexes, analytics projections |
| Bounded staleness | Replicas may lag but remain within a defined bound | Catalogs/dashboards tolerating a few minutes of delay |

No single consistency level fits an entire application. You can use strong consistency for room holds at the authoritative service, read-your-writes for on-site UIs, and eventual consistency for search/analytics.

Strong consistency across sites typically requires network round trips or quorum/coordination. When links have high latency or partition, writes slow down or cannot commit if strict ordering must be preserved. If the business must keep operating during a partition, specify which data permits local authority, which enters a pending state, and which must be rejected.

## 4. Data Synchronization Strategies

| Strategy | How it works | Strengths | Limitations |
| --- | --- | --- | --- |
| Synchronous replication | Transactions wait for replica confirmation per system mechanism | RPO can be very low within defined failure models | Sensitive to latency/link outages |
| Asynchronous replication | Primary commits first, ships changes afterward | Lower commit latency, tolerates flaky links better | Replica lag; failover may lose unreplicated writes |
| Periodic batch sync | Synchronizes on a schedule or in batches | Simple, controlled windows and load | Data is stale between runs |
| Change Data Capture (CDC) | Reads transaction logs/change streams and ships deltas | Near real-time, preserves order within source/partition scope | Requires offset, schema, retention, and replay management |
| Event-driven sync | Domain events are published and applied by consumers | Decouples producers/consumers, scales with events | Requires schema evolution, idempotency, and ordering |
| File/object replication | Copies objects/versions across storage locations | Fits large files and binaries | Conflicts/deletes/metadata have distinct semantics |
| Store-and-forward | Writes to a local durable queue/store and ships when link works | Continues accepting work offline | Backlogs, disk capacity, and complex reconciliation |

### 4.1. Synchronous Replication

In synchronous replication, the primary may only report success after replicas confirm per the database’s quorum or durability mechanism. This shrinks the data-loss window in certain failure scenarios but increases network sensitivity. Understand whether “confirmed” means the replica received the log, persisted it durably, or committed the transaction; semantics differ across databases and topologies.

### 4.2. Asynchronous Replication

The primary returns results immediately while replication runs behind. Applications depend less on cross-region latency, but lag must be measured and RPO defined. If the primary fails before logs are shipped/applied, acknowledged transactions may be missing on replicas. Monitor lag in time/bytes/log sequence numbers, commit timestamp versus apply timestamp, backlog, auth/network/schema errors, and catch-up capability.

### 4.3. Batch Sync

Batch sync fits when data can tolerate delay and changes can be grouped. Jobs need checkpoints, watermarks, checksums, retries, and update/delete handling. Re-running a batch must be idempotent. Running a batch hourly does not mean data is at most one hour stale: execution time, retries, backlogs, and outages all add to actual staleness.

## 5. Store-and-Forward Architecture During Outages

Store-and-forward lets a site keep recording work in local durable storage/queues and synchronize to the cloud once the link returns.

~~~mermaid
flowchart LR
    APP["Local application"] --> DB["Local durable DB"]
    DB --> OUTBOX["Outbox / local event log"]
    OUTBOX --> Q["Forwarder queue"]
    Q --> LINK["VPN / private link / internet"]
    LINK --> CLOUD["Cloud ingestion API"]
    CLOUD --> CENTRAL["Central event store / DB"]
    CLOUD -.->|"ack / checkpoint"| Q
~~~

Local writes must be durable before reporting success when the business requires it. The outbox should be written in the same transaction as business data to prevent committing a record without emitting its event. Forwarders send in bounded batches with backpressure. Every message needs a unique ID, source, aggregate key, version, `occurredAt`, and schema version. The cloud returns explicit acks/checkpoints so local storage marks messages delivered only after valid confirmation. Retries use exponential backoff with jitter; poison messages must not retry indefinitely. Local queues need quotas, disk thresholds, retention, and alerts.

### 5.1. Transactional Outbox

If an application commits a booking to the database and then calls a broker, the process could crash between the two steps. The database has the booking, but the event is never published. A transactional outbox writes the event into an outbox table within the same transaction; a publisher reads and sends it later. Outbox solves atomicity between business state and event intent inside one database transaction. It does not guarantee the broker receives each message only once; the publisher may resend if an ack is lost, so consumers must still be idempotent.

## 6. Change Data Capture and Synchronizing Existing Databases

CDC reads changes from transaction logs or change streams instead of polling entire tables. Changes are delivered to streams/targets to build replicas, search indexes, or data warehouses.

A CDC pipeline requires a source database with enough log retention for consumer catch-up; a connector reading logs by position/offset; a schema registry or contract; a broker buffering during transient target or network failures; an idempotent consumer managing offsets; and reconciliation comparing source and target.

### 6.1. Snapshots and Incremental Changes

Bootstrapping typically requires an initial snapshot of existing data, followed by applying log changes starting from a matching watermark. If the snapshot and log boundary misalign, changes may be missed or duplicated. Record the snapshot timestamp/consistent point, starting log position/offset, consumer checkpoints, schema versions, and delete/tombstone handling; test resuming after connector restarts.

### 6.2. Schema Evolution

Adding or changing fields at the source can break connectors or consumers. Enforce backward/forward compatibility rules, version schemas, and deploy consumers able to handle transition periods. Do not drop fields from the source before all consumers have migrated.

## 7. Conflict Resolution When Multiple Sides Mutate Data

Conflicts happen when two replicas modify the same logical object before synchronizing. For example, at a hotel, staff member A marks a room clean while the cloud simultaneously receives an update from a housekeeping integration. Or two sites modify the same booking while the WAN is down.

| Strategy | Rule | Suitable for | Risks |
| --- | --- | --- | --- |
| Single-writer ownership | Each aggregate has one authoritative writer | Critical bookings/payments/inventory | Must handle offline owners |
| Last-write-wins | Pick the version with the latest timestamp | Low-stakes preferences | Clock skew can pick wrong winner; lost updates |
| Version/CAS | Write only if current version matches | Preventing concurrent overwrites | Conflicts must be handled |
| Field-level merge | Merge independent fields | Profiles/metadata with clear field ownership | Unsafe when fields share invariants |
| CRDT | Structures with convergent merge operations | Certain counters/sets | Does not fit all domains naturally |
| Manual/business resolution | Route conflicts to a review queue | Payments/bookings with financial impact | Requires staffing and SLAs |

Last-write-wins is not simply picking the largest timestamp. Clocks across sites can drift; client timestamps are untrustworthy; event creation time and receipt time differ. If used, define time sources, deterministic tie-breakers, and assess lost-update risk. For critical data, versions or explicit ownership are usually easier to reason about.

Version/ETag/aggregate versions detect two edits based on the same prior state. On mismatch, the server returns a conflict so callers re-read, merge, or escalate to business logic. Version vectors or causal metadata can capture causality at the cost of added complexity.

For example, booking B is CONFIRMED at version 10. An offline site receives a cancellation request while the cloud simultaneously captures payment. You cannot blindly pick the latest timestamp and ignore invariants: can it be canceled after payment capture, is a refund/void required, was inventory released, and did the guest receive confirmation? State machines and command validation must govern the rules.

## 8. Idempotency, Duplicate Delivery, and Ordering

When a link drops after the receiver processes a message but before the sender receives the ack, the sender does not know if it committed. Retries may resend the message. Assume at-least-once delivery unless the platform proves stricter semantics.

- Attach a stable event/message ID across retries.
- Consumers store inbox/dedup keys alongside business state in the appropriate transaction.
- External side effects use idempotency keys where providers support them.
- Aggregate versions prevent older events from overwriting newer state.
- Partition by aggregate when ordering within that scope is needed.
- Route poison messages to dead-letter/quarantine with alerts and replay tooling.
- Rate-limit batch replays to avoid overloading systems upon reconnect.

Do not claim exactly-once merely because a broker advertises that feature. You must evaluate transactions end-to-end across producers, brokers, consumers, databases, and external side effects.

## 9. Operating During Network Partitions

A partition is not only a complete link outage. One direction may work while the reverse is blocked; latency may spike causing timeouts; packet loss may occur; DNS/control planes may be unreachable; VPN tunnels may flap; or bandwidth may be saturated by bulk syncs or retry storms.

### 9.1. Choose Degraded Modes by Capability

| Capability | During connectivity loss | Safeguards |
| --- | --- | --- |
| Search | Serve local cache/index with freshness labels, or reject filters needing live data | Never present stale data as real-time |
| Check-in | Allow locally within defined quotas/ownership | Durable local log, idempotency, reconciliation |
| New bookings | Queue as pending or allow only within delegated inventory | Prevent overselling/double bookings |
| Payments | Show pending/unknown or use an approved fallback provider | Never treat timeouts as failures and double-charge |
| Notifications | Queue locally and send later | Dedup, expiration, provider rate limits |
| Analytics | Defer sync/reporting | Track freshness |
| Identity | Use valid cached tokens/credentials | Never open permissions when verification fails |

Degraded modes must be designed upfront. Not every operation should keep writing locally; sometimes fail-closed is the safer choice.

### 9.2. Timeouts, Retries, and Circuit Breakers

Timeouts must fit the latency budget. Retry only transient errors and idempotent/protected operations. Exponential backoff and jitter prevent synchronized retry storms. Circuit breakers temporarily stop calling failing dependencies to protect threads/connections. Queues need bounded sizes and backpressure when receivers slow down. Fallbacks must preserve invariants and expose appropriate staleness/degraded indicators.

Immediate retries while a link is down can saturate the WAN and services the moment connectivity returns. Separate retry traffic from new traffic.

## 10. Reconnecting and Catching Up After Connectivity Returns

Restored connectivity does not mean data is immediately consistent. Queue backlogs, replication lag, schema mismatches, or expired credentials may remain.

~~~mermaid
flowchart TD
    A["Link restored"] --> B["Authenticate and validate channel"]
    B --> C["Measure lag, backlog and capacity"]
    C --> D["Resume from durable checkpoint"]
    D --> E["Replay with rate limit and idempotency"]
    E --> F["Detect duplicates and conflicts"]
    F --> G["Reconcile source and target"]
    G --> H{"Integrity and lag acceptable?"}
    H -->|No| C
    H -->|Yes| I["Restore normal traffic"]
~~~

Reconnect sequence: authenticate tunnels/certificates/identities/routes; check schema compatibility; measure lag, queue depth, oldest message age, and disk; verify write authority; resume from durable checkpoints; drain backlogs with rate limits; handle duplicates/out-of-order events/conflicts; reconcile using counts/checksums/versions/business invariants; confirm SLOs/freshness before exiting degraded mode; and record outage metrics.

If a backlog accumulates 5 million events, sending them all at once can overwhelm ingestion, databases, and downstream consumers. Drain rates must account for receiver capacity, live traffic, priority order, provider rate limits, log retention, and egress quotas. Reserve capacity for both live traffic and backlog; if receivers cannot process faster than new events arrive, scale capacity or throttle event generation.

## 11. RPO, RTO, and Freshness in Hybrid Synchronization

RPO is the amount of data loss over time the business tolerates in a recovery scenario. Replication lag is the observed delay of the synchronization mechanism. They are related but distinct.

Example: target RPO is 5 minutes; normal lag is 20 seconds; the link drops for 40 minutes; local logs are stored durably; after the link recovers, the backlog takes 25 minutes to drain. If local logs are intact and replay completely, data is not necessarily lost, yet the central view is 40 minutes stale. If the local site fails before logs are protected elsewhere, data can be lost.

| Metric | Meaning |
| --- | --- |
| Replication lag | Time/bytes of logs not yet applied at the target |
| Data freshness | Age of the newest data visible to consumers |
| RPO | Acceptable data loss during recovery |

Freshness can be poor without data loss; RPO can be met even while a read model is temporarily stale. Dashboards should display all three separately.

## 12. Securing Cross-Environment Synchronization

Data synchronization introduces new network paths and access rights. Use VPN/private connectivity or appropriate TLS; mutual authentication where needed; workload identities/certificates with lifecycles and rotation; least privilege scoped by source, target, topic, table, and operation; encryption at rest and in transit; data classification and masking/tokenization before entering lower-privilege environments; auditing of sync/replay/checkpoint operations; unauthorized replay protection; controlled delete propagation; and protection for dead-letter queues since they may hold sensitive data.

Do not copy long-lived secrets to every site just so apps work offline. Prefer distinct local identities, short-lived credentials, or expiring caches. If offline credentials are unavoidable, enforce a threat model, minimal scope, expiration, rotation, and revocation procedures.

## 13. Object and File Synchronization

Object replication has different semantics from database replication. Object versioning identifies revisions; metadata/tags may require separate replication; deletes may create delete markers or permanently delete depending on configuration; incomplete multipart uploads must be handled; checksums verify integrity; and large files may need multipart/resume or bulk transfer.

If both sides modify the same object key while offline, use version IDs or ownership policies to avoid overwrites. Do not use last-modified timestamps as the sole truth if clocks across sites are unsynchronized.

## 14. Configuration and Identity Synchronization

| Component | Design recommendation |
| --- | --- |
| Application configuration | Clear source of truth, versioning, staged rollouts, and rollback |
| Network policies | Central approval; local enforcement via signed versions |
| Identity/role mappings | Clear federation or trust relationships, audit changes |
| Secrets | Per-environment secret managers; limit cross-domain copies |
| Certificates | Inventory, expiry alerts, renewal, and trust overlap |
| Software/image artifacts | Trusted registries, immutable digests, signature/provenance checks |

When the control plane is unreachable, sites may need to continue operating using valid signed policies/configs. Never fall back to allow-all simply because a new policy cannot be fetched.

## 15. Network Design for Cross-Region/Cross-Cloud Synchronization

Networking is the underlying dependency for replication, CDC, and store-and-forward. Provision redundant connectivity aligned with RTO; size bandwidth for baseline sync plus backlog catch-up; apply QoS/traffic shaping to prioritize live transactions over bulk replication; design DNS/endpoint discovery for provider/region failures; verify MTU, NAT, firewall state, and idle timeouts; preserve trust boundaries with private connectivity, encryption, and segmentation; and monitor tunnels, packet loss, latency, throughput, and route changes.

### 15.1. Catch-Up Capacity

Suppose a local site generates an average of 2 MB/s of logs and the link drops for 30 minutes:

~~~text
backlog = 2 MB/s * 30 * 60 s
        = 3,600 MB
~~~

If 10 MB/s of replication capacity is available after reconnect while live traffic continues generating 2 MB/s, the net drain rate is 8 MB/s:

~~~text
catch_up_time = 3,600 MB / 8 MB/s
              = 450 s
              = 7.5 minutes
~~~

This simplified estimate omits protocol overhead, compression, retries, bursts, and processing bottlenecks. It demonstrates that capacity must exceed data generation rates for backlogs to shrink.

## 16. Observability and Runbooks for Synchronization

Do not monitor only green tunnel status. A link can be up while replication stalls, consumers fail on schema errors, or queues retry endlessly.

| Group | Metrics |
| --- | --- |
| Network | Tunnel uptime, latency, packet loss, throughput, reconnect count |
| Replication | Lag seconds/bytes, log position, apply rate, failure count |
| Queue | Depth, oldest age, enqueue/dequeue rates, retries, dead-letter count |
| Data integrity | Checksum mismatches, record count deltas, conflict/duplicate counts |
| Freshness | Age of newest event/data visible at target |
| Capacity | Disk spool usage, network quotas, connector CPU/memory |
| Security | Auth failures, certificate expiry, policy changes, replay rejections |
| Business | Pending bookings/payments, duplicate operations, reconciliation backlog |

Dimension metrics by source/site/target/stream with controlled cardinality; never place raw customer IDs in time-series labels.

Trigger alerts when lag exceeds thresholds long enough; queues or spool disks near capacity; oldest message age breaches SLA; replication stalls despite an active tunnel; conflicts/duplicates spike; certificates approach expiration; or catch-up rate falls below backlog growth rate.

Runbooks should list owners, impact, safe sync pause steps, write authority checks, checkpoint resumption, poison message quarantine, reconciliation, and incident closure criteria.

## 17. Failure Scenarios and Recovery

| Incident | Consequence | Mitigation |
| --- | --- | --- |
| WAN/VPN down | No sync; local queues grow | Store-and-forward, quotas, alerts, degraded mode |
| Link flapping | Excessive retries, duplicates, session resets | Backoff/jitter, circuit breakers, checkpoints |
| Target database down | Backlogs grow despite healthy network | Bounded buffers, capacity planning, resume |
| Schema incompatibility | Consumers reject events | Versioned schemas, compatibility tests, quarantine |
| Disk spool full | Local site cannot accept more data | Threshold alerts, backpressure, admission policies |
| Clock skew | Broken ordering/last-write-wins | NTP, logical versions, avoid bare timestamps |
| Split-brain | Two sites write authoritative data | Fencing, ownership leases/quorum, or manual failover |
| Credential expired | Sync rejected | Refresh/rotation, certificate alerts |
| Poison message | Consumers retry infinitely | DLQ/quarantine, payload repair, controlled replay |
| Accidental delete/ransomware | Corruption replicates to target | Immutable backups, delete protection, clean-point restore |

## 18. Lab Exercise: Keep a Site Operating When the Cloud Link Drops

**Assumed scenario:** a booking platform runs its control plane in the cloud; each hotel has a local edge service managing check-ins, room status, and events. The VPN to the cloud can drop for up to 45 minutes. The site must continue check-ins, look up cached reservations, and record local status events. New bookings exceeding local quotas must go pending or be rejected per policy.

### Tasks

1. Classify bookings, payments, room status, property catalog, search projections, notifications, and telemetry by owner/consistency/RPO.
2. Design network paths/failure domains: VPN redundancy, DNS, identity, bandwidth, and traffic priority.
3. Choose which data uses synchronous replication, asynchronous replication, CDC, batch, or store-and-forward, and justify why.
4. Design the local durable database and transactional outbox with event IDs, aggregate versions, and checkpoints.
5. Write degraded-mode behavior for check-ins, new bookings, payment timeouts, and notifications.
6. Design conflict resolution for room status and bookings; define writer authority and business rules.
7. Simulate a 45-minute link outage and reconnect; calculate backlog and catch-up time.
8. Design retries/backoff, deduplication, ordering, DLQs, and replay.
9. Define RPO, replication lag, and data freshness targets for each capability.
10. Build dashboards/alerts for tunnels, lag, backlogs, spool disk, conflicts, and business reconciliation.
11. Test credential expiry, schema mismatches, split-brain, target outages, and disk full scenarios.
12. Write an ADR detailing trade-offs across availability, consistency, security, cost, and operational complexity.

### Sample Synchronization Decision Table

| Dataset | Source of truth | Sync method | Offline behavior | Conflict policy |
| --- | --- | --- | --- | --- |
| Booking/payment | Central booking/payment service | Async events + durable ledger/reconciliation | Pending or restrict risky actions | Single writer/business workflow |
| Room status | Local site within delegated scope | Outbox/store-and-forward | Continue local updates | Version/CAS and business rules |
| Property catalog | Central master | CDC/batch | Read-only cached snapshot | Central wins, refresh version |
| Search projection | Rebuildable projection | Events/CDC | Serve stale index with warning | Rebuild from source |
| Notifications | Event source/outbox | Queue/replay | Queue locally | Idempotency keys |
| Telemetry | Site-local buffer | Batch/stream | Bounded buffer | Loss policy by signal type |

### Completion Criteria

- Each dataset has clear ownership, write authority, consistency, and RPO.
- Multi-writer is avoided on critical data without proven conflict semantics.
- Outbox/store-and-forward is durable with checkpoints.
- Retries, duplicates, ordering, and replay are handled.
- Degraded modes clearly specify what continues, pends, or fails closed.
- Reconnect includes backpressure, catch-up capacity, and reconciliation.
- Metrics separate replication lag, freshness, and RPO.
- Identity, encryption, keys, auditing, and retention remain protected offline.
- Runbooks cover link outages, split-brain, full queues, and credential expiration.

## 19. Well-Architected Checklist for Hybrid/Multi-Cloud Sync

- [ ] Datasets are classified with clear sources of truth/owners for each.
- [ ] Consistency levels fit business invariants and failure scenarios.
- [ ] Synchronous, async, CDC, event, batch, or store-and-forward choices match data types.
- [ ] Replication semantics, lag, commit acknowledgments, and failure behavior are understood.
- [ ] Backups are independent of replication, immutable, and restore-tested.
- [ ] Local offline writes have durable storage/outboxes and quotas/backpressure.
- [ ] Messages carry IDs, schema versions, aggregate keys/versions, and checkpoints.
- [ ] Consumers are idempotent; duplicates, ordering, retries, poison messages, and replay have policies.
- [ ] Conflict resolution relies on domain semantics; avoid timestamp-only rules when clocks are untrusted.
- [ ] Write authority/fencing prevents split-brain and dual writers.
- [ ] Degraded modes clearly define capabilities that continue, degrade, pend, or fail closed.
- [ ] Reconnect has catch-up capacity, rate limits, jitter, and reconciliation.
- [ ] RPO, replication lag, and data freshness are measured separately.
- [ ] Networks have redundancy, segmentation, encryption, bandwidth, and traffic prioritization.
- [ ] Identities/credentials/certificates have clear lifecycles, rotation, and offline policies.
- [ ] PII/secrets are protected in streams, queues, logs, traces, and dead-letter queues.
- [ ] Dashboards/alerts cover links, lag, backlogs, disk, conflicts, and integrity.
- [ ] Runbooks define owners, recovery order, checkpoints, rollbacks, and exit criteria.
- [ ] ADRs document trade-offs across reliability, consistency, security, performance, cost, and operations.

**Core takeaway:** data synchronization is not merely copying records across a network. Architecture must establish authoritative sources, consistency levels, how offline writes are accepted, how duplicates/conflicts are handled, and how catch-up runs on reconnect. When durable queues, outboxes/CDC, checkpoints, idempotency, write authority, and observability are designed together, hybrid/multi-cloud systems can sustain operations within defined limits and converge cleanly after interruptions.
