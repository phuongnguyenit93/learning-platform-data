# Data Recovery, Divergence Handling, and Preventing Split-Brain

A distributed system can keep operating when a node, availability zone, or region fails, yet recoverability is more than booting a standby server. After failover, data may lack a subset of transactions, two nodes may have accepted different writes, or an old node may return and continue writing with stale state. Without controlling these scenarios, the system can create divergent data, overwrite valid updates, or confirm two conflicting outcomes.

**Data recovery** restores data and services to an accepted state after an incident. **Divergence handling** identifies and resolves differences between replicas or data branches that evolved independently. **Preventing split-brain** guarantees only one valid writer/leader holds authority to create new state within the same consistency scope. These three parts must be designed together: backups and recovery logs provide the restoration path; replication and reconciliation surface and resolve discrepancies; quorum, leases, epochs, and fencing prevent conflicting writers from continuing to operate.

This lesson belongs to the **Disaster Recovery** chapter of the **Cloud Architecture** track. It focuses on designing data recovery, controlling divergence, and protecting correctness during failover/failback. Decisions must tie to business objectives, RPO/RTO, durability, consistency, security, and real-world operability.

After this lesson, you will be able to:

- Distinguish backups, replication, snapshots, archives, and point-in-time recovery.
- Choose recovery strategies based on RPO, RTO, retention, and data criticality.
- Recover using backups combined with transaction logs/WAL/binlog or change streams.
- Detect missing, duplicate, out-of-order, and divergent data across replicas.
- Design reconciliation, replay, conflict resolution, and controlled recovery procedures.
- Explain split-brain and its causes from network partitions, leader-detection faults, or concurrent failovers.
- Apply quorum, leases, fencing tokens, epochs, and writer isolation per system semantics.
- Design failover, failback, old-node rejoin, and test failure scenarios.

## 1. Recovery Is a Business Objective

Disaster recovery (DR) is not merely restoring infrastructure. A system is considered recovered when critical functions operate again and data meets committed loss, consistency, and reliability targets.

For example, an equipment-rental platform may have differing requirements:

- Payment ledger must retain every confirmed transaction per durability policy.
- Booking service may tolerate losing up to a few seconds of data in a region failure scenario if business contracts permit.
- Notifications may be delayed yet must not drop durably accepted messages.
- Analytics can be rebuilt from raw events and accept a longer RTO.
- Search indexes can be regenerated from databases or event logs and do not need the same backup level as primary data sources.

Using the same backup strategy across every dataset can waste money where data is easy to rebuild and under-protect where data is irreplaceable.

## 2. RPO and RTO

Two foundational metrics for determining a DR strategy are **Recovery Point Objective (RPO)** and **Recovery Time Objective (RTO)**.

- **RPO:** maximum tolerable data loss, typically expressed as the time interval from the incident back to the last recoverable data point.
- **RTO:** target time to restore a service or business function to an acceptable operating level.

For example, if RPO is 5 minutes, the organization accepts recovering data to a point no older than 5 minutes before the incident per the agreed definition. If RTO is 30 minutes, the function must recover within 30 minutes. RPO/RTO do not imply every transaction in those 5 minutes is guaranteed lost; they are design and measurement targets, not exact predictions for each incident.

### 2.1. Conceptual Timeline

~~~mermaid
flowchart LR
    A["Last recoverable point"] --> B["Data changes"]
    B --> C["Failure time"]
    A -. "RPO window" .-> C
    C --> D["Detection / decision"]
    D --> E["Restore / promote / replay"]
    E --> F["Service recovered"]
    C -. "RTO window" .-> F
~~~

### 2.2. Breaking Down RTO by Phase

Total RTO is not just database restore time. It can be decomposed:

| Phase | Work Involved |
| --- | --- |
| Detection | Detect and confirm the incident |
| Decision | Select recovery site/backup/replica and approve cutover |
| Provision/restore | Create resources or restore the database |
| Replay/reconciliation | Apply logs, verify data, resolve discrepancies |
| Routing | Switch endpoints, DNS, traffic, or tenant routing |
| Validation | Smoke tests, invariant checks, and permissions |
| Business recovery | Re-enable transactions and process backlog |

If restore takes 15 minutes yet consistency checks and traffic switching take another 25 minutes, actual RTO is nearly 40 minutes. Measure from the user's perspective and business journeys.

### 2.3. Recovery Tiers

| Data/Service Tier | Hypothetical RPO/RTO | Protection Patterns to Consider |
| --- | --- | --- |
| Ledger/payment | Near-zero RPO within committed scope; short RTO | Sync/quorum replication, log durability, independent backups |
| Booking core | Low RPO, RTO of a few minutes | Multi-zone HA, cross-region replicas, PITR |
| Notifications | Deferrable; prioritize keeping accepted messages | Durable queues, replicated storage, replay |
| Curated analytics | Rebuildable; longer RTO | Raw archives, pipeline replay, catalog backups |
| Search/cache | Regenerable | Periodic snapshots or rebuild from source |

Numbers must be determined through business impact analysis, contracts, and technical feasibility. Never promise zero RPO merely because synchronous replication exists: acknowledgment semantics, quorum, storage durability, and concurrent failures must be verified.

## 3. Backups, Snapshots, Replication, and Archives

These mechanisms complement rather than replace one another.

| Mechanism | Objective | Strengths | Limitations |
| --- | --- | --- | --- |
| Backup | Recover after accidental deletes, corruption, or outages | Can recover to pre-incident points | Has latency; requires restore and verification |
| Snapshot | Capture storage/database state at a point in time | Faster recovery point creation or environment cloning | Depends on consistency and retention; does not inherently guard against all logic bugs |
| Replication | Maintain updated copies on another node/site | Fast failover; can serve reads | Can replicate deletes/corruption; async has lag |
| Transaction log/WAL archive | Store changes after full/incremental backups | Point-in-time recovery and replay | Requires continuous, ordered log chains and retention |
| Archive | Long-term/historical retention | Storage cost efficiency and compliance | Slower restore/rehydration; complex retrieval |
| Export/versioned objects | Keep versioned copies of data | File/dataset recovery and overwrite protection | Does not replace transaction-consistent backups if exports are unsynchronized |

### 3.1. Why Is a Replica Not a Backup?

If an operator accidentally drops a table, the drop command typically replicates to replicas. If data is corrupted by an application bug, replicas may receive the same corrupted data. Replication helps availability yet does not preserve clean pre-incident state.

Backups should have copies residing in a different failure domain and administrative boundary from production, with appropriate retention/immutability and periodic restore testing.

### 3.2. Snapshot Consistency

Volume or database snapshots must have clear semantics: crash-consistent or application-consistent? A snapshot that merely captures blocks close together in time is not necessarily equivalent to a transaction-consistent database backup. Use database quiesce/checkpoint mechanisms or database backup APIs when transactional consistency is required.

## 4. Full Backups, Incremental Backups, and Log Backups

A database recovery strategy typically combines:

- **Full backup:** complete copy at a point in time.
- **Incremental/differential backup:** changes since the previous backup or last full backup per tool semantics.
- **Transaction log backup/archive:** continuous logs to recover to a specific timestamp.

Example workflow:

~~~text
Sunday 00:00    Full backup B0
Monday 00:00    Incremental I1
Monday 12:00    Log segments L001...L120
Monday 14:20    Accidental data deletion
Recovery:
    Restore B0
    Apply I1
    Replay transaction logs up to 14:19:59
    Validate recovered database
    Open application traffic
~~~

Naming and chaining for incremental/differential backups differ across database/backup engines. Runbooks must match exact tool semantics rather than assuming every log can replay independently.

### 4.1. Point-in-Time Recovery (PITR)

PITR restores a database to a specific point by restoring a base backup and applying logs up to a target timestamp or log position. It is useful when recovering to just before a mistaken operation or logical corruption entered the database.

PITR depends on:

- A readable full/base backup.
- An unbroken chain of all required logs.
- Accurately determined target timestamp/position.
- Accessible backups, logs, and encryption keys.
- A restore target with sufficient capacity and compatible version.
- Rehearsed validation and endpoint-cutover procedures.

If a transaction committed right around an ambiguous target timestamp, clarify inclusive/exclusive semantics and verify outcomes using log positions or business records.

## 5. Backups Must Be Protected Like Production

Attackers with rights to delete a database may also try to delete backups, snapshots, keys, and logs. Backups in the same account, under the same credentials, and on the same control plane can be destroyed alongside production.

Measures:

- Separate backup accounts/projects or vaults where appropriate.
- Immutable/WORM retention or object locks per policy.
- Separate permissions for create, read, delete, and retention changes.
- MFA/approvals for destructive operations.
- Encrypt backups and protect keys independently.
- Monitor backup jobs, log gaps, retention, and delete events.
- Verify backup integrity and restore in isolated environments.
- Keep copies in another region/failure domain per RPO/RTO.
- Protect metadata, catalogs, configuration, and recovery credentials.

Immutability can complicate policy-driven or legal data deletion. Retention locks, legal holds, and privacy erasure must be designed together and confirmed with authorized owners.

## 6. Recovering Data Does Not Mean Recovering the Whole System

One database backup is insufficient to restore an application. The system also depends on:

- Application artifacts and versions.
- Infrastructure as Code and network configuration.
- DNS, certificates, and identity providers.
- Secrets, keys, and access permissions.
- Schema migrations and compatibility.
- Queues, event offsets, and workflow state.
- Object storage, file attachments, and search indexes.
- Tenant directories and feature/config data.
- Monitoring, alerts, and runbooks.

Build a recovery dependency map and determine recovery order. For instance, starting the application before secrets/KMS/identity work can leave instances unready; restoring the database before choosing the matching schema version can make the application incompatible.

## 7. Recovery Sequence and Dependency Order

A typical recovery workflow may follow these steps:

1. Activate incident response and scope the failure.
2. Preserve evidence/logs and block further writes to the broken system if needed.
3. Select the recovery point and target environment.
4. Recover control dependencies: identity, keys, networking, DNS, and secrets in order.
5. Restore databases/storage or promote replicas per strategy.
6. Replay transaction logs/events and verify consistency.
7. Restore queue/workflow checkpoints and handle backlogged messages.
8. Run data-quality/invariant/reconciliation checks.
9. Open traffic by cohort or read-only first if appropriate.
10. Monitor errors, latency, duplicates, and backlogs.
11. Record recovery decisions, potential data loss, and compensating actions.

Never open writes the instant the database comes online. Confirm the node is the valid writer, the recovery point is accepted, schemas/versions match, and no old writer remains active.

## 8. What Is Data Divergence?

**Data divergence** occurs when two replicas or data branches no longer reflect the same valid history. It can arise when:

- Primary and replica evolve independently after a network partition.
- Two regions accept writes in active-active while replication is asynchronous.
- Failover promotes a replica that had not received all logs.
- An old node returns and replays data from stale state.
- Replays/retries create duplicates or apply events out of order.
- Replication conflicts are resolved using last-write-wins unsuited to the business domain.

Divergence is not simply replica lag. Lag is falling behind; divergence means contents or ordering have already differed. A lagging replica can catch up by continuing to replay; two branches that accepted independent writes may require conflict resolution or recovery from an authoritative source.

### 8.1. Divergence Example

Suppose a booking is in state `CONFIRMED` on primary A and replica B. A network partition leads to B being promoted while A still accepts writes. A records `BookingCancelled`; B records `BookingRescheduled`. When connectivity returns, the two branches cannot simply merge logs by timestamp because both transitions started from the same prior state and carry conflicting business meanings.

~~~mermaid
sequenceDiagram
    participant A as Region A
    participant B as Region B

    Note over A,B: Both hold Booking v10 = CONFIRMED
    A->>A: Append v11 BookingCancelled
    B->>B: Append v11 BookingRescheduled
    Note over A,B: Network partition; two branches diverge
    A--xB: Replication unavailable
    Note over A,B: Link recovers; conflict must be resolved
~~~

A larger timestamp does not make an event more accurate. You need business rules or an upfront single-writer/quorum mechanism to prevent conflicts.

## 9. Detecting Divergence

Not every discrepancy can be caught merely by inspecting online nodes. Multiple verification layers are needed:

- **Replication position:** compare log sequences/offsets per engine semantics.
- **Checksums/hashes:** compare partitions/tables/pages or data across key ranges.
- **Row counts/aggregates:** record counts, financial totals, and state counts at a matching snapshot point.
- **Business invariants:** a booking cannot be both cancelled and confirmed; ledger debits/credits balance.
- **Event sequences:** detect gaps, duplicates, sequence conflicts, and out-of-order arrivals.
- **Reconciliation:** compare authoritative sources against projections/replicas.
- **Version/fencing metadata:** check leader epochs, writer identities, and generations.
- **Audit timelines:** identify which node accepted writes during the partition window.

Matching checksums do not prove business rules hold if both copies share a logic bug. Matching row counts do not prove identical content. Combine technical checks with business reconciliation.

### 9.1. Domain-Level Reconciliation

Example for bookings:

| Check | Objective |
| --- | --- |
| Booking ID uniqueness | No two records created for the same business identity |
| State transitions | No illegal transitions |
| Payment references | One payment transaction not linked to two bookings |
| Reservation ownership | One asset not confirmed for two overlapping bookings |
| Amount/currency | Totals and currencies match confirmed events |
| Event sequences | No missing versions or duplicate applies |
| Tenant ownership | Records belong to the right tenant post-recovery |

For ledgers, verify debit/credit balance per transaction/currency rather than merely comparing row counts.

## 10. Handling Divergence: Establish the Authoritative Source First

Before merging branches, identify the **source of truth** for each domain/aggregate and affected time window.

Options:

1. **Single-writer authority:** only one node/region holds write authority; unauthorized branches are discarded or quarantined.
2. **Quorum-committed history:** recognize only operations carrying commit certificates/quorum per the consensus protocol.
3. **Business reconciliation:** domain owners determine which events are valid based on evidence and invariants.
4. **Replay from authoritative log:** rebuild projections/nodes from confirmed history.
5. **Manual adjudication:** conflicts unresolvable automatically go to an audited review queue.

Never merge two databases by copying whichever row has a newer timestamp. Examine transactions, versions, actors, authority, and business consequences.

### 10.1. Conflict Resolution Strategies

| Strategy | How It Works | Best Suited For | Risks |
| --- | --- | --- | --- |
| Last-write-wins | Pick update with higher timestamp/version | Non-critical attributes with reliable clocks/ordering | Lost valid updates, clock skew |
| Version-based rejection | Accept writes only against expected version | Single-writer aggregates/optimistic concurrency | Callers must retry or handle conflicts |
| Field-level merge | Merge non-conflicting fields | Collaborative data with per-field semantics | Can produce invalid state combinations |
| CRDT/commutative operations | Use mergeable, convergent operations | Counters, sets, or suitable structures | Unsuitable for many business invariants |
| Domain-specific resolution | Rules driven by business semantics | Bookings, payments, inventory, ledgers | Requires domain logic and possibly manual handling |
| Quarantine/manual review | Do not auto-merge; isolate conflicts | High financial/legal impact | Slow recovery; requires handling team |

### 10.2. Example of an Unsafe Field Merge

A profile receives two independent updates: the user changes display name and an agent updates contact status. Merging per-field may work if semantics allow. However, a booking with two transitions `CONFIRMED→CANCELLED` and `CONFIRMED→RESCHEDULED` cannot be mechanically field-merged; the domain must select one outcome or trigger a compensating workflow.

## 11. Replay and Rebuild from the Authoritative Source

If a replica or projection has diverged, it can be wiped/rebuilt from the authoritative source when complete history exists.

Conceptual workflow:

1. Fence the faulty node so it accepts no writes.
2. Identify the authoritative stream/log and recovery point.
3. Back up the diverged state for investigation; do not destroy evidence.
4. Provision a clean node or create a new projection target.
5. Restore an appropriate snapshot/base backup.
6. Apply logs/events up to the recognized checkpoint.
7. Rebuild indexes/materialized views/projections.
8. Reconcile business invariants and counts/checksums.
9. Shift traffic once validation passes.
10. Keep the old node in read-only/quarantine before retiring per policy.

Replay must be idempotent without repeating side effects. Rebuilding read models must never re-send emails, call payment gateways, or create external transactions. Separate state projectors from integration handlers.

## 12. What Is Split-Brain?

**Split-brain** is a state where two or more nodes both believe they hold leader/writer authority for the same dataset or consistency scope. This commonly arises when a network partition prevents nodes from confirming leader status while failover mechanisms or health checks allow multiple sides to continue accepting writes.

Consequences:

- Two transaction histories diverge concurrently.
- The same resource gets allocated twice.
- Updates are overwritten or become unmergeable.
- Sequences/versions collide.
- Reconnecting replicas cannot tell which branch holds authority.
- Financial data or booking states become inexplicable.

Split-brain differs from intentional multi-primary architectures. Multi-primary has explicit replication/conflict management; split-brain is uncoordinated write authority.

### 12.1. Network Partitions and Uncertainty

When A cannot reach B, A cannot tell for sure whether B crashed or is merely network-partitioned. If both self-promote based on independent timeouts without quorum/leases/fencing, both may accept writes.

Health checks prove a node responds; they do not prove the node holds leadership authority. Leadership decisions must rely on protocols and authority, not merely whether a node responds to pings.

## 13. Quorum and Consensus

**Quorum** is the number of members required to agree on a decision, such as electing a leader or committing an entry. In a consensus cluster with $2f+1$ voting members, majority quorum is typically $f+1$, tolerating $f$ member faults under the protocol and network assumptions.

For example, a 3-voter cluster needs 2 votes to elect a leader/commit per protocol. When one node is isolated, the 2-voter side still achieves quorum; the isolated node lacks votes and must reject writes. This prevents both sides from committing concurrently.

~~~mermaid
flowchart TB
    subgraph QUORUM["3 voting members"]
        A["Node A"]
        B["Node B"]
        C["Node C"]
    end
    A --- B
    B --- C
    C --- A
    A --> L["Quorum-elected leader"]
    B --> L
~~~

The diagram illustrates only majority quorum. Production systems may use witnesses, weighted voting, joint consensus, or other topologies. Never arbitrarily alter node counts or quorum configs without understanding the protocol; a witness may vote without storing full data.

### 13.1. Why Two Nodes Are Usually Not Enough

With two voters and a majority requirement, quorum is 2. If one node disconnects, neither side has enough votes to commit safely. Some architectures add a witness/third voter as a tie-breaker. This is a trade-off between availability and preventing two leaders.

### 13.2. Quorum Does Not Automatically Solve Every Failure

Quorum consensus protects decisions within the defined cluster/protocol boundary. It does not automatically protect external systems, such as a payment provider or an external secondary database outside the quorum. Integrations and side effects still need idempotency, fencing, or proper authority checks.

## 14. Leases, Epochs, and Fencing Tokens

The following mechanisms often work together to protect write authority.

### 14.1. Leases

A lease grants time-bounded ownership. A leader holds write authority while its lease remains valid under the system's clock/coordination assumptions. When the lease expires without renewal, the leader must stop performing actions requiring that authority.

Leases must account for clock drift, long pauses, network delays, and revocation/renewal. A process may pause for a long time and wake up believing its lease is still valid; hence a lease alone is not always sufficient.

### 14.2. Epochs/Generations

Each leader election or writer handoff increments an epoch/generation. Requests carrying an older epoch are rejected once the resource/server knows about a newer epoch.

Example:

~~~text
Epoch 41: Region A is writer
Failover / new leader election
Epoch 42: Region B is writer

Any write carrying epoch 41:
    reject as stale leader
~~~

Epochs must be issued by a consistent authority, increase monotonically, and be stored/checked where writes are executed.

### 14.3. Fencing Tokens

A fencing token is a monotonically increasing token validated at the protected resource. When a new leader receives a higher token, the resource rejects requests from the old leader carrying lower tokens.

This is critical: merely asking an application to stop when its lease expires may fail if an old process pauses or is partitioned. The resource/database/storage must enforce fencing, or the system must ensure the old node is disabled at an equivalent layer before the new writer starts.

### 14.4. Fencing Sequence

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Old leader
    participant B as New leader
    participant S as Protected storage

    C->>A: Epoch 41 lease
    A->>S: Write with token 41
    S-->>A: Accepted
    C->>B: Grant epoch 42
    B->>S: Register / write with token 42
    S-->>B: Accepted
    A->>S: Delayed write with token 41
    S-->>A: Rejected: stale token
~~~

Some databases do not accept application-supplied fencing tokens directly. In those cases, use database promotion/role mechanisms, revoke writer access, apply network fencing, or use a proven control plane to prevent the old node from writing.

## 15. Which Layers Require Fencing?

Fencing must block write authority across all resources capable of creating conflicting state:

- Database primary/writer endpoints.
- Object storage if multiple leaders write the same keys/manifests.
- Queue producers or workflow state stores.
- Distributed locks/resource coordinators.
- Schedulers/job executors capable of producing side effects.
- File systems/shared volumes.
- External services if they support idempotency/lease/ownership tokens.

Blocking traffic at a load balancer while the old node retains DB credentials and connects directly is insufficient. Revoking credentials can also incur delay while existing connections/sessions stay open. Understand enforcement points and actual invalidation times.

## 16. Safe Failover: Sequence Matters

Failover should never be a "promote replica" command fired the instant a health check times out. A safe procedure must ensure the old node no longer holds authority before the new node accepts writes.

A conceptual flow:

~~~mermaid
flowchart TD
    A["Primary suspected failed"] --> B["Confirm failure scope"]
    B --> C{"Can establish quorum / authority?"}
    C -- "No" --> D["Keep writes disabled or degraded"]
    C -- "Yes" --> E["Fence old writer"]
    E --> F["Select eligible candidate"]
    F --> G["Check log position and RPO"]
    G --> H["Promote with new epoch"]
    H --> I["Update writer routing"]
    I --> J["Validate invariants and transactions"]
    J --> K["Enable writes"]
~~~

If fencing the old writer cannot be proven, the safe choice for critical data may be pausing writes. This is a consistency/availability trade-off; not every outage allows safely continuing writes.

### 16.1. Candidate Selection

Candidates should be evaluated by:

- Replication position/last durable commit.
- Health and storage readiness.
- Region/zone placement.
- Engine version and schema compatibility.
- Ability to achieve quorum or satisfy promotion policy.
- RPO impact if unreplicated logs must be sacrificed.
- Capacity to serve production workloads.

Never pick a node solely because it responds fastest.

## 17. Failback and Rejoining the Old Node

After the DR site is promoted, the old node/region may return. Never automatically restore it as primary or merge logs bidirectionally without verification.

Safe rejoin workflow:

1. Keep the old node fenced/read-only.
2. Preserve logs and snapshots for investigation if needed.
3. Identify the current epoch/leader and authoritative history.
4. Assess whether the old node contains divergent data.
5. Re-seed from the new primary or restore/replay per protocol.
6. Verify versions, checksums, business invariants, and replication lag.
7. Configure it as a new replica without letting it reclaim the writer role.
8. Rehearse failback inside a controlled window.
9. Move primary back to the old site only with an explicit plan, fencing, and approvals.

Failback does not have to be rushed. Many systems should keep the DR site as primary for a period and cut back only when risk is low and capacity is full.

## 18. Unknown Commits and Idempotency in DR

A difficult case arises when a client sends a command to primary, primary commits successfully, yet the response is lost due to a network partition. The client does not know whether the transaction committed. Retrying against the new writer can create a second record or transaction.

Required safeguards:

- Stable idempotency keys per business operation.
- Unique constraints on business identifiers where applicable.
- Persist command results and transaction states.
- Query/reconcile against the new authoritative writer before retrying.
- Never trigger external side effects before durable state is clear.
- Use provider idempotency support for payments/refunds.
- Maintain `PENDING/UNKNOWN` states to represent indeterminate outcomes.

Never generate a fresh random request ID on each retry if you need to identify the same business operation.

## 19. Event Sourcing and Log-Based Recovery

In event-sourced systems, the event store serves as the source history to rebuild aggregates/projections. However, distinguish:

- Events committed to the authoritative event store.
- Events published to the message broker.
- Events applied by consumers.
- Projections committed and checkpointed.
- External side effects completed.

Each stage has distinct failure modes. If only the event store is authoritative, projections can be rebuilt from the stream; however, do not assume emails or payment providers can be "undone" via replay.

### 19.1. Rebuilding Projections

Projections can be rebuilt into a new table, verified for counts/checksums/metrics, and then readers switched to the new version. Throttle replay rates to avoid starving production resources. Consumer side effects must be isolated and disabled during rebuild mode.

## 20. Active-Active and Conflict Policies

Active-active allows multiple regions to serve traffic and potentially accept writes. This improves geographic availability while adding consistency demands.

Options:

- **Home-region per tenant/aggregate:** only one region owns writes for each entity.
- **Partitioned ownership:** shards/tenants have explicitly partitioned writers.
- **Single-writer with local reads:** other regions read replicas while commands route to the home writer.
- **Conflict-free data types:** use only when operations and semantics are genuinely commutative/convergent.
- **Application-level conflict resolution:** suits certain data mergeable via business rules.
- **Manual reconciliation:** for sensitive transactions that cannot auto-merge safely.

Never use last-write-wins for ledgers, booking allocations, or inventory merely for implementation ease. Clock skew and semantically distinct updates can discard valid data.

### 20.1. When Is Single-Writer Better?

Single-writer generally protects invariants more easily for an aggregate with strict ordering. The trade-off is higher latency for distant regions and needing failover if that region fails. Sharding by tenant/aggregate distributes home writers while increasing routing and migration complexity.

## 21. Post-Recovery Data Validation

After restoring/promoting, validate data before opening full traffic.

Validation layers:

1. **Physical/integrity:** database recovery completed; pages/checksums/storage healthy.
2. **Log continuity:** no missing transaction logs/sequences within the committed window.
3. **Schema compatibility:** migration versions and application builds match.
4. **Referential integrity:** foreign keys or business references are valid.
5. **Business invariants:** balances, reservations, payment states, uniqueness, and valid statuses.
6. **Completeness:** record counts/amounts reconciled across the target window.
7. **Security:** credentials, roles, tenant isolation, and encryption work.
8. **Operational readiness:** new backups, replication topology, monitoring, and alerts are ready.

If validation spots discrepancies, keep writes disabled or restrict traffic to unaffected functions; quarantine suspect records, preserve evidence, and run owned reconciliation.

## 22. Data Recovery Runbook

A practical runbook must include:

- Triggers and scope to initiate recovery.
- Decision-makers and executors.
- Recognized backup/log/replica sources.
- Recovery target, RPO/RTO, and data-loss choices if any.
- Exact commands or automation matching tool versions.
- Steps to fence the old writer.
- Order of restore, replay, and migrations.
- Technical/business validations.
- Routing, DNS, certificate, and secret updates.
- Controlled cohort write opening.
- Reconciliation/compensation and message backlog handling.
- Communication with business owners.
- Incident closure criteria and evidence retention.

Runbooks must fetch secrets/credentials through a vault—never hard-code passwords or keys directly. Documents need versions, owners, last drill dates, and platform dependencies.

## 23. DR Testing and Drills

A green backup job does not prove recoverability. Perform real restores and measure durations.

Required tests:

- Restore a full backup into an isolated environment.
- PITR to just prior to an accidental deletion.
- Drop a transaction log segment and verify the system raises an error rather than silently recovering incomplete data.
- Lose the primary during active writes.
- Partition networks between nodes and verify two writers never emerge.
- Return an old leader with a stale epoch/token and verify rejection.
- Trigger replica lag above RPO prior to promotion.
- Time out a client right at commit and verify idempotent retry.
- Rebuild projections from raw/event logs.
- Failback and rejoin the old node.
- Restore secrets, KMS access, DNS, identity, and application dependencies.
- Measure actual RPO/RTO using timestamps and business transaction IDs.

Each test needs a hypothesis, scope, guardrails, stop conditions, an owner, and PASS criteria. After drills, update runbooks, automation, and capacity plans.

## 24. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Treating replicas as backups | Deletes/corruption spread to copies | Independent backups and PITR |
| Not aligning RPO/RTO with business needs | DR strategy fails critical functions | Tier services/data and measure real recovery |
| Untested backup restores | Failures discovered mid-disaster | Scheduled restore drills |
| Backups sharing production permissions/account | Attackers delete backups too | Immutable/offsite copies and privilege separation |
| Promoting a lagging node | Transactions committed on old primary are lost | Candidate criteria and log-position checks |
| Failing over via DNS only | Old writer keeps accepting writes, causing split-brain | Resource-level fencing and writer authorization |
| Both regions writing during partition | Two conflicting data branches | Quorum, home writers, or conflict protocols |
| Merging by timestamp | Valid updates lost due to clock skew/semantics | Versions and domain-specific reconciliation |
| Replaying side effects | Duplicate emails/charges/refunds | Separate projectors and integration handlers |
| Ignoring unknown commits | Retries create duplicate transactions | Idempotency and reconciliation |
| Rejoining old nodes directly | Divergent data writes back into primary | Fence, re-seed, and rejoin as replica |
| Checking row counts only | Content/business mismatches go unnoticed | Checksums and invariant reconciliation |
| Enabling writes before validation | Corruption spreads post-recovery | Read-only validation gates |
| Rushing failback | Second outage or fresh split-brain | Dedicated failback plan and drills |
| Not backing up control metadata | Database exists yet lacks keys/config to run | Recovery dependency map |

## 25. Design and Implementation Process

1. **Classify data and services:** define business criticality, owners, and reproducibility.
2. **Set RPO/RTO:** align with user journeys and financial/legal impacts.
3. **Select recovery mechanisms:** backups, PITR, snapshots, replication, archives, or replay.
4. **Design backup isolation:** offsite/immutable, permissions, encryption keys, and retention.
5. **Build recovery dependency map:** identity, KMS, DNS, networking, secrets, apps, and data.
6. **Design authority model:** single writer, quorum, home regions, epochs, and fencing.
7. **Define divergence detection:** log positions, versions, checksums, and business reconciliation.
8. **Define conflict policies:** auto-merge when safe; quarantine/manual review when unprovable.
9. **Design failover:** fence old writer, pick candidate, check RPO, promote, and route.
10. **Design failback/rejoin:** keep old node read-only, re-seed, validate, and switch under control.
11. **Protect commands/side effects:** idempotency, unknown commits, replay modes, and compensation.
12. **Set up monitoring/runbooks:** backup age, log gaps, replica lag, recovery progress, epochs, and writer identity.
13. **Drill:** restores, PITR, partitions, split-brain, failover, failback, and reconciliation.

## 26. Well-Architected Evaluation

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Are backups/PITR restorable? Are RPO/RTO measured? Does failover enforce fencing? Is divergence detected and resolved before enabling writes? |
| **Security** | Are backups/keys separated by privileges? Are recovery credentials protected? Who can promote writers, restore, or export data? |
| **Performance Efficiency** | Do restores/replays finish within RTO? Are backfills/reconciliation rate-limited? Do recovery nodes hold enough capacity? |
| **Cost Optimization** | Are retention/replication/archives tiered? Is DR spend proportional to business impact? |
| **Operational Excellence** | Do runbooks, owners, log-gap/backup-age/lag alerts, epoch audits, and failover/failback drills exist? |

### Acceptance Checklist

- [ ] Datasets/services classified by criticality, source of truth, and reproducibility.
- [ ] RPO/RTO defined by business needs and proven via drills.
- [ ] Backups, snapshots, replication, archives, and PITR have distinct goals.
- [ ] Backups isolated from production failure domains/permissions, encrypted, and restore-tested.
- [ ] Transaction log/WAL/binlog retention suffices for PITR per policy.
- [ ] Recovery dependency map covers identity, KMS, DNS, networking, secrets, apps, and data.
- [ ] Writer/leader authority uses quorum/leases/epochs or equivalent mechanisms.
- [ ] Fencing enforced wherever side effects or data writes can occur.
- [ ] Replica candidates chosen by freshness, capacity, and RPO.
- [ ] Divergence detected via log positions, checksums, and business invariants.
- [ ] Conflict resolution follows domain rules; no blind timestamp merges.
- [ ] Unknown commits/retries use idempotency and reconciliation.
- [ ] Replays avoid repeating side effects; projections rebuild safely.
- [ ] Failback keeps old nodes fenced, re-seeds, and validates before rejoining.
- [ ] Writes open only after integrity, schema, security, and business validation.
- [ ] Runbooks include owners, guardrails, stop conditions, and evidence.
- [ ] Restores, PITR, partitions, split-brain, failover, and failback have been drilled.

## 27. Practice Exercise

An equipment-rental platform has a primary database in Region A and an asynchronous replica in Region B. Target RPO is 30 seconds and RTO is 10 minutes. A network incident severs communication between the regions. Operations suspects primary A failed and promotes replica B. However, primary A remains alive serving some clients on existing connections. During the partition, A records `BookingCancelled` while B records `BookingRescheduled` for the same booking. After 4 minutes, the network recovers.

Design:

1. How do you determine which region holds authority and whether replica B has enough data within RPO?
2. What is the sequence for fencing primary A before and after promoting B?
3. How do you detect two event versions that both branched from the same prior state?
4. Which booking is authoritative to resolve cancel/reschedule? Who decides?
5. Can this auto-merge or must it go to quarantine/manual review? Why?
6. How do you preserve logs and evidence from both branches before rebuilding?
7. How will node A be re-seeded and rejoined as a replica?
8. How are client transactions with indeterminate commit results handled via idempotency/reconciliation?
9. Which checks must pass before reopening full writes?
10. Which drill proves the 30-second RPO and 10-minute RTO in practice?

A safe solution must prove B was promoted with new authority and A was fenced. Conflicting business events must be resolved using business evidence and domain policies; never pick an event simply because its timestamp is larger. After preserving evidence, correct state can be applied on the current writer via audited commands/reconciliation, followed by re-seeding A from the authoritative source. If authority cannot be confirmed or data loss may exceed RPO, keep writes restricted and escalate the decision rather than allowing two nodes to continue writing.

**Core takeaway:** backups and recovery logs provide a path back to a known state; reconciliation and replay address missing/duplicate/divergent data; quorum, epochs, and fencing stop two writers from creating competing histories. Safe failover demands establishing authority, disabling the old writer, checking recovery points, and enabling writes only after validation. Recovery is complete only when data satisfies business invariants and the system continues operating in a controlled topology.
