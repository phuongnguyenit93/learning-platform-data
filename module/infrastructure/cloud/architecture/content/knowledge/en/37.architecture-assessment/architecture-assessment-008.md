# Testing Data Recovery and Region Failover

## 1. Why Must Architecture Assessment Test Recoverability?

A cloud application architecture can have multiple Availability Zones, database replicas, scheduled backups, and a standby Region, yet still fail to recover during a real outage. The reason is that **having redundant components does not mean having a verified recovery procedure**. Backups might fail to decrypt; replicas might contain accidental deletions; apps in the secondary Region might lack configs, encryption keys, or fail to receive traffic; operations might take hours just to determine where write ownership resides.

In the **CLOUD_ARCHITECTURE** module, architectural design starts from business requirements before choosing networking, compute, data, and deployment models. This lesson belongs to the **Architecture Assessment** chapter, focusing on gathering empirical evidence for two capabilities:

1. **Data recovery:** returning data to a complete, accurate, and usable state from backups, snapshots, point-in-time recovery (PITR), or appropriate replicas.
2. **Region failover:** continuing service in another Region when the primary Region becomes unavailable or during planned migration, while protecting write ownership, consistency, and user experience.

The goal is evaluating trade-offs in the spirit of **Well-Architected**: reliability, security, performance, cost, operability, and sustainable resource usage.

After this lesson, you will be able to define RPO/RTO targets, distinguish backup restores from replica failovers, build drill scenarios, measure end-to-end results, validate data and applications post-recovery, and make evidence-based architectural decisions.

## 2. Concepts to Distinguish

| Concept | Meaning | Do Not Confuse With |
|---|---|---|
| **Backup / snapshot** | Stored copy of data for point-in-time or policy-based restoration. | An always-up-to-date replica; backups must be restored and verified. |
| **PITR** | Restoring to a selectable timestamp within a supported window, typically via backups and transaction logs. | Instant rollback of any mistake or arbitrary point in time. |
| **Replication** | Maintaining one or more data copies, synchronously or asynchronously per config. | Independent backups guarding against logic bugs, ransomware, or accidental deletion. |
| **Failover** | Transferring serving roles—especially write ownership—to a standby component or Region during an outage. | Failback: switching back after the original Region recovers. |
| **Planned switchover** | Scheduled ownership transfer, potentially pausing writes briefly to reconcile and lower data-loss risk. | Unplanned failover when the source suddenly becomes unreachable. |
| **Restore** | Rebuilding data or systems from usable stored backups. | Automatic network traffic rerouting. |
| **DR (Disaster Recovery)** | Technical and operational capabilities to restore service after a major disaster. | Merely owning a replica or a written document. |
| **RPO** | Maximum data loss tolerated by the business, typically expressed as a time interval. | Instantaneous replication lag; lag is only one signal. |
| **RTO** | Maximum acceptable time to restore a service or capability to its committed level. | VM boot time or single DB connection success alone. |

**Backups, replication, and traffic shifting solve different failure classes.** For example, hardware failures can be handled by failover; accidental deletes or malicious encryption propagate to replicas, requiring clean, isolated backups and point-in-time recovery.

### 2.1. Defining RPO and RTO at the Business-Journey Level

A requirement like "30-minute RTO" is insufficient without specifying what counts as restored: homepage loads, API reads data, or customers can place orders and complete payments?

For each service, record:

- **RTO start mark:** when the service stopped meeting criteria (to measure real impact), alongside detection timestamp and incident declaration timestamp.
- **RTO end mark:** when all minimum defined functions pass transaction checks and satisfy accepted recovery SLOs.
- **RPO measurement:** timestamp of the latest consistent commit surviving in the recovered system versus outage onset or designated cutoff.
- **Scope:** which apps, tenants, data classes, and regions; are reporting or secondary features excluded?
- **Post-recovery target:** full service or controlled degraded mode, such as read-only or temporarily paused payments.

One system may set different RPOs per data class: transactional data may require near-zero loss within design limits, cache data can be rebuilt, and analytics data may lag by hours.

### 2.2. Calculating RPO and RTO from Evidence

Suppose Region A goes down at **14:07:32**. The latest committed transaction in A was at **14:07:30**, yet Region B had only applied changes up to **14:07:12**. In a scenario activating B from that state:

\[
\text{Potential data-loss window}
\approx 14{:}07{:}32 - 14{:}07{:}12 = 20\ \text{seconds}
\]

This is an illustrative estimate based on verified last-commit timestamps, not a guarantee that exactly 20 seconds of transactions were actually lost. Reconcile transaction IDs, versions, or log positions: there may have been zero writes in that window, or many critical writes.

If users cannot complete a verification transaction in B meeting recovery criteria until **14:14:02**, observed RTO is **6 minutes 30 seconds** from 14:07:32. Measuring only up to DNS updates or VM boot produces a smaller number that does not represent service recovery.

## 3. Selecting a Data Protection Strategy Matching Risk

| Option | Recovery Method | Advantages | Limits Requiring Testing |
|---|---|---|---|
| **Periodic backup in one Region** | Provision resources, restore latest backup. | Relatively simple to set up; usually cheaper than warm standby. | RPO depends on backup/log schedule; RTO can be long; if Region dies, backup storage may be unreachable. |
| **Backups copied to independent Region/account** | Build system elsewhere and restore. | Copy isolated from source; fits infrequent DR needs. | Must prove backups, decryption keys, metadata, networking, and rebuilds all work. |
| **Pilot light** | Keep data and core foundations in secondary Region; spin up/scale app compute during outage. | Balances cost and recovery time. | Emergency provisioning, config, and scaling can take significant time. |
| **Warm standby** | Maintain a scaled-down running secondary system. | Usually shorter RTO than pilot light if sized properly. | Ongoing parallel spend; must test scaling, replication, and ownership transfer. |
| **Multi-Region active-passive** | Region A actively takes traffic/writes; B waits to take over. | Clearer write ownership than active-active. | RPO depends on replication mode; requires fencing and routing cutover. |
| **Multi-Region active-active** | Multiple Regions serve concurrently via partitioning or consistency schemes. | Can improve user proximity and availability. | Write conflicts, event ordering, split-brain, high cost, and complex data design. |

Tight RTO/RPO targets usually demand major investment in standby resources, data transport, automation, and testing. Never pick active-active just because it sounds like "zero downtime"; prove the consistency mechanics and exact failure scope the architecture actually withstands.

### 3.1. Synchronous vs. Asynchronous Cross-Region Replication

- **Asynchronous replication:** primary may acknowledge writes before Region B receives them; lower write-path latency, yet RPO on losing A can exceed 0. Monitor replication lag, log backlog, and verified commit positions.
- **Synchronous replication:** writes must await replica acknowledgments per system mechanics; improves zero-data-loss guarantees under specific conditions while adding latency and potentially lowering availability during network partitions. Verify **cross-Region** synchronous support for the exact DB engine; never assume every DB supports it.
- **Partitioned regional ownership:** can shrink blast radius if each tenant or shard has a clear owner, provided routing stays clean and concurrent dual writes are prevented.

**Never look at a "multi-region" label and conclude RPO = 0 or RTO = 0.** Recovery also depends on failure detection time, primary election conditions, capacity headroom, DNS/client retries, encryption keys, and reconciliation capability.

## 4. Reference Architecture for Assessing Recovery

~~~mermaid
flowchart LR
    Client[Users and integrated systems] --> Route[DNS / Global traffic routing]
    subgraph RA[Region A - primary]
       LB_A[Load balancer] --> APP_A[App A]
       APP_A --> DB_A[(Primary DB A)]
       DB_A --> BAK_A[(Backup/PITR)]
    end
    subgraph RB[Region B - standby]
       LB_B[Load balancer] --> APP_B[App B]
       APP_B --> DB_B[(Data B)]
       BAK_B[(Independent backup)] --> DB_B
    end
    Route -->|Normal| LB_A
    Route -.->|On approved failover| LB_B
    DB_A -->|Replication: may lag| DB_B
    BAK_A -->|Protected cross-region copy per policy| BAK_B
    MON[Monitoring / Audit / Runbook] -.-> RA
    MON -.-> RB
~~~

This diagram illustrates an **active-passive** layout—it does not imply every component works instantly upon routing cutover. During assessment, confirm:

1. Can Region B launch or scale all apps, databases, queues, object storage, caches, certificates, keys, secrets, and IAM roles?
2. Can data copies in B recover to a **consistent, writable** state per DB mechanics?
3. Does write-ownership transfer block the old primary from accepting writes during a cross-Region network partition?
4. Do global routing, DNS, health checks, and client connections actually shift live traffic to B?
5. Are external dependencies (payment gateways, email, identity providers, license servers, webhooks, batches) permitted and able to operate from B?
6. Are backups/PITR isolated from logical errors in the primary DB and restorable even if Region A's control plane is unreachable?

The reliability pillar demands examining the **entire transaction path**, not just one replicated component.

## 5. Testing Data Recovery: Complete Workflow

### 5.1. Securing Backup Stores Before Testing Restores

A usable backup must simultaneously satisfy *exists, accessible, decryptable, restorable, data-accurate, and within time budget*. Inspect:

| Check Layer | Verification Details |
|---|---|
| Backup artifact | Backup schedule, table/volume/object coverage, transaction logs, retention, and age of latest backup. |
| Independence | Backups isolated from accounts/roles able to delete the source; stored cross-Region when DR goals require. |
| Security | Encryption, key management, restore permissions, auditing, and testing recovery when source credentials are gone. |
| Integrity | Checksums or tool-native verification, backup logs, trial restores, and data-structure checks. |
| Restorability | Engine versions, storage/IOPS, quotas, capacity, OS images, and network prerequisites. |
| App consistency | Whether backups capture all dependent stores needed for a valid business state. |

**A "backup succeeded" message confirms only that the tool's creation step finished.** It does not prove users can transact after a restore.

### 5.2. Restore Test in an Isolated Environment

1. **Define objective:** select dataset, target objects, target RPO/RTO, security constraints, and acceptance criteria.
2. **Set evidence markers:** record backup/PITR timestamp, app version, DB schema, transaction ID, or watermark; seed non-sensitive test records with known expected outcomes.
3. **Isolate:** restore into a test environment whose networking, accounts, identity, and endpoints are separated from production. Disable real emails/payments/webhooks to prevent external side effects.
4. **Restore:** pick the target backup or PITR timestamp; measure elapsed time from restore request through resource provisioning until DB readiness.
5. **Verify data:** compare row counts, key records, checkpoints, and checksums across consistency boundaries; verify foreign keys, formatting, change history, and business invariants.
6. **Verify application:** run compatible app versions against restored data; smoke-test reads, test-env writes, authorization, and transaction flows.
7. **Measure and log:** completion timestamp, achieved RPO/RTO, limits, bugs, and recommendations; clean up test data per policy.

Example verification query for an ordering system:

~~~sql
-- Illustrative SQL example; run across data pinned to the same cutoff marker.
-- total_minor_unit stores money in minor units to avoid floating-point errors.
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    SUM(total_minor_unit) AS amount_total
FROM orders
WHERE created_at < :recovery_cutoff
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

Matching aggregate totals alone is insufficient: two errors can cancel out and leave sums identical. Compare per order ID and critical fields, or compute checksums across fixed key ranges and investigate mismatches. When restoring to a pre-incident point, records **after the recovery cutoff** being absent may be the expected PITR outcome rather than a restore bug.

### 5.3. Testing Different Classes of Data Failure

| Scenario | Recommended Test | Success Criteria |
|---|---|---|
| Loss of a volume/instance | Build fresh system and restore. | Data and app operate together; RTO met. |
| Accidental table or object drop | Restore from clean backup or PITR prior to drop. | Business state restored; post-cutoff writes handled cleanly. |
| Faulty schema migration | Restore data/schema matching app version. | App reads/writes validly; no critical fields lost. |
| Logical DB corruption replicated to standby | Use isolated versioned backup. | Restore prior to corruption point; do not overwrite valid state. |
| Encryption key inaccessible | Rehearse backup key/permission access per policy. | Backup decrypts properly under controlled emergency permissions. |
| Backup Region unavailable | Restore from prepared cross-Region/account copy. | Zero dependency on resources existing solely in failed Region. |

Destructive tests must use **synthetic data in isolated environments**, or a strictly scoped production game day with explicit permissions, abort switches, and safeguards. Never trigger hard-to-reverse errors on real data merely to test restore mechanics.

## 6. Testing Region Failover: Traffic Shifting Is Just One Step

### 6.1. Three Drill Types to Separate

| Drill Type | Context | How to Execute |
|---|---|---|
| **Simulation / tabletop** | Assume primary Region lost; staff walk through decisions. | Tests runbooks, escalation, permissions, contacts, and disagreements; does not prove RTO. |
| **Isolated technical drill** | Provision test environment or synthetic traffic in standby Region. | Restore/promote replica, spin up test primary, run E2E tests without shifting live writes. |
| **Controlled switchover / game day** | Shift a slice of real traffic or perform planned primary transfer. | Requires write fencing, approvals, rollback/roll-forward plans, SLO monitoring; yields closest-to-real evidence. |

A dry-run test cannot fully replace live traffic and write-ownership cutover tests, yet it uncovers most bugs before accepting real risk. Match drill depth to business criticality.

### 6.2. Reference Region Failover Runbook

**Pre-Incident Preparation**

1. Define incident commander, data, networking, application, and security leads; specify who holds authority to trigger Region failover.
2. Sync IaC, images, configs, secrets, certificates, policies, quotas, and capacity in B; test building B independently of A.
3. List services required to run in B; prepare health checks, synthetic transactions, reconciliation tools, and backup comms channels.
4. Document primary election rules, fencing, current RPO, acceptable data-loss caps, and handling of in-flight transactions.
5. Prepare global routing, DNS/TTLs, connection pool draining, and caching; test partner and third-party endpoints from B.

**When the Primary Region Fails**

1. **Detect and declare:** verify outage impacts business functions; mark t0 for RTO measurement, assess blast radius, and activate the runbook.
2. **Assess data integrity:** check B's last-applied position, backlog, unshipped logs, and estimated RPO; prevent users from writing to the wrong owner while A's state is uncertain.
3. **Fence old write path:** ensure only one site accepts writes via the designed mechanism (e.g., epoch/lease blocking old primary resurgence, quorum, or infrastructure fencing). If split-brain cannot be reliably prevented, prefer read-only mode or pausing writes over activating dual primaries.
4. **Activate B:** finish data promotion/restore, update primary roles, scale compute, start required queues/workers; verify keys/secrets and integrations.
5. **Shift traffic:** adjust global traffic steering or DNS per design; watch caching, long-lived connections, and client retries to prevent traffic lingering on A.
6. **Verify recovery:** run controlled reads and writes; verify critical data, exactly-once business effects for webhooks/queues, latency, and error rates in B.
7. **Record milestones:** log when users genuinely resume transacting, last safe commit timestamp, and any data loss/gap; communicate status per company process.

**Post-Stabilization**

1. Reconcile writes submitted by users during the outage window; resolve retries/idempotency and uncertain outcomes.
2. Back up the new state in B, restore monitoring and capacity buffers, and track added costs.
3. When A returns, never let A automatically accept writes. Confirm B is authoritative and choose a verified failback strategy.

### 6.3. Why Split-Brain Is a Critical Risk

Suppose the network link between two Regions breaks while both A and B still receive separate traffic. If A keeps confirming orders while B is also promoted to primary, the system can accept conflicting inventory updates or charges. When connectivity returns, blindly merging both streams corrupts business state.

~~~mermaid
flowchart LR
    CLIENT[Client / API] --> G[Write-ownership coordinator]
    G -->|Epoch n: only A writes| A[(Region A)]
    G -.->|Standby| B[(Region B)]
    A -->|Replication| B
    F[Fencing + primary election] -->|Advance to epoch n+1| G
    F -->|Revoke A write access| A
    G -->|Epoch n+1: only B writes| B
~~~

This diagram shows **control intent**; real fencing/epoch enforcement must be honored by every write path and verified under network partitions and restarts. Changing DNS alone is unreliable fencing because older clients hold open sockets or hit A directly.

## 7. Verifying Data After Failover

Once B is promoted, do not stop at checking HTTP 200. Reconcile across business dimensions:

| Layer | What to Check | Example |
|---|---|---|
| **Committed transactions** | Do transactions A confirmed before the outage exist in B? | Match order IDs, payment references, commit markers. |
| **Uncertain commands** | Timed-out requests may have committed before client retries. | Look up by idempotency key before creating duplicate orders. |
| **Ordering and keys** | Are dependent records and versions ordered properly? | No `order_item` without an `order`; inventory revisions never regress. |
| **Non-relational data** | Are objects, messages, caches, and search indexes present or rebuildable? | Invoice files, unprocessed events, product search indexes. |
| **Business invariants** | End-to-end consistency of recovered state. | Order total = line-item sum; zero duplicate payments; inventory non-negative per rules. |
| **Apps and integrations** | APIs, auth, batches, external callbacks, queues work properly. | End-to-end purchase and refund test in sandbox. |

Key reminders:

- With async replication, **A's commit mark can sit ahead of B's applied mark**. Document the exact loss window, classify transactions recoverable from upstream sources, and handle per business policy.
- Never blindly replay all messages post-failover. If commands succeeded on A or were applied on B before ACKs were lost, enforce entity- and side-effect-level idempotency.
- Caches and search indexes may lag or need rebuilding; never treat caches as source of truth.
- Keys, certificates, and identities tied to encrypted data are recovery prerequisites. A byte-complete backup without valid decryption keys remains unusable.
- Across multiple data stores, define **cross-system consistency marks** or reconciliation rules. Clock-aligned snapshots alone do not guarantee transactional consistency across DBs, queues, and object stores.

## 8. Overlooked Dependencies in Region Drills

Region failover fails if the DR setup depends on a resource residing only in Region A.

| Component | Risk Scenario | Expected Evidence |
|---|---|---|
| DNS / global routing | Bad TTLs, caches, connection pooling, or health checks keep sending clients to A. | Measure live traffic post-cutover and per-endpoint/region error rates. |
| Config and IaC | Templates, state files, artifact registries, or images live only in A. | Provision B cleanly while simulating A completely unreachable. |
| IAM and secrets | Under-privileged roles; secrets/KMS keys unavailable in B. | App B decrypts data and reaches dependencies with valid identities. |
| Networking | Missing CIDRs, peering, routes, private endpoints, or partner IP allowlists in B. | End-to-end checks on B's network. |
| Data plane | DB, queues, objects, caches, search indexes out of sync or absent. | Verify contents, replay, and dependency wiring. |
| Capacity / quotas | B runs small standby and fails to scale due to quotas or stockouts. | Ramp up to recovery load and watch saturation. |
| External integrations | Payment gateways, webhooks, or IdPs trust only A's IPs/URLs. | Test transaction from B confirmed by external partner. |
| Observability and process | Dashboards, logs, or comms channels also hosted in A. | Observe and coordinate operations while A is simulated down. |

**Distinguish data-plane vs. control-plane failures:** running workloads may keep serving while resource-control APIs are down, or vice versa. Runbooks must never assume you can spin up VMs, edit policies, or restore via the failing Region's console; test critical steps from the exact vantage point and permissions available during an outage.

## 9. Designing Safe, Repeatable Drills

A sound test defines its hypothesis, pass criteria, blast radius, and evidence upfront. Minimum template:

| Field | Example Content |
|---|---|
| **ID and Scope** | DR-REGION-01, ordering app and test-tenant transaction data. |
| **Hypothesis** | With Region A unreachable, Region B absorbs read/write traffic within 15 minutes. |
| **Target RPO/RTO** | RPO ≤ 60 seconds, RTO ≤ 15 minutes per agreed definitions. |
| **Injected Fault** | Isolate test access paths to A and revoke control over A components within drill scope. |
| **Safeguards** | Do not shift live traffic outside test cohort; mock email/payments; rollback and abort thresholds ready. |
| **Signals Observed** | Synthetic success, p95/p99, DB applied position, split-brain alarms, queue backlog, traces. |
| **Output Evidence** | Outage/recovery timestamps, data marks, state snapshots, decision logs, reconciliation results. |
| **Owners** | Incident commander, data, application, networking, security, approvers. |

### 9.1. Essential Test Matrix

| ID | Simulated Incident | What to Prove |
|---|---|---|
| DR-01 | Restore DB/volume from backup | Restore succeeds, data valid, app works, RTO/RPO met. |
| DR-02 | Accidental data deletion requiring PITR | Clean recovery point chosen; post-cutoff writes handled cleanly. |
| DR-03 | Complete loss of Region A | B builds/runs independently; traffic and ownership shift safely. |
| DR-04 | A↔B link severed while both remain running | Never two active writers for the same data; fencing engages. |
| DR-05 | Replication lag breaches threshold | Monitoring alerts; process denies/delays promotion or gets authorized risk sign-off. |
| DR-06 | B lacks quotas/secrets/keys | Caught before traffic cutover; remediation runbooks and owners clear. |
| DR-07 | API committed write but client timed out | Retries cause zero duplicate transactions/side effects. |
| DR-08 | Failback to A after hours running in B | Resync, reconciliation, and ownership transfer cause zero data divergence. |
| DR-09 | Backup or replica contains logical error | Able to pick clean copy, restore, and bound data loss per policy. |

Drill frequency depends on criticality and architectural change. For example, test restores monthly/quarterly, runbook drills quarterly, and Region failover after major changes; this is only a reference cadence and never overrides regulatory mandates or organizational SLOs.

### 9.2. Evidence Maturity Levels

1. **Level 1 – Documentation only:** diagrams, runbooks, and backup lists exist; functionality unproven.
2. **Level 2 – Component test:** DB restores or app boots in B, without end-to-end business checks.
3. **Level 3 – Integration test:** end-to-end transactions, data, and dependencies work in test env per targets.
4. **Level 4 – Controlled switchover drill:** measures scoped/live traffic, write fencing, SLOs, and user behavior.
5. **Level 5 – Repeatable operations:** fresh evidence, automation, alerts, postmortems, and results across repeated drills or major changes.

These levels are an **illustrative learning scale**, not a formal certification standard. When grading an architecture, state exact test type and evidence; never declare "DR passed" from backup status alone.

## 10. Evaluating Results: Pass/Fail Criteria and Numbers

### 10.1. Acceptance Criteria Set

| Category | Sample Acceptance Criterion | Measurement Method |
|---|---|---|
| RPO | ≤ 60 seconds for order data. | Latest commit ID or watermark present at target vs. outage onset. |
| RTO | ≤ 15 minutes for order creation. | Actual outage time until synthetic/E2E order creation succeeds within SLO. |
| Integrity | Zero unexplained gaps in transaction data prior to recovery point. | Reconcile by keys, monetary totals, states, and invariants. |
| Write ownership | Never two primaries accepting writes for the same scope. | Audit logs, fencing tokens/epochs, partition fault tests. |
| Operability | Login, ordering, history reads, and essential integrations work. | Representative business scenarios; logs/traces and user outcomes. |
| Operational readiness | On-call locates runbooks, permissions, and executes step-by-step. | Timeline, action evidence, coordination errors. |
| Load capacity | B sustains agreed recovery load. | Load tests, p95/p99, errors, CPU/DB/queue saturation. |
| Security & compliance | Zero data leaks; Region B complies with residency and access rules. | Verify data location, IAM, encryption, audits, retention. |

These are **hypothetical thresholds** for practice only. Every system must negotiate RPO/RTO and SLOs from business impact versus cost. If a critical gate fails, mark the overall assessment **FAIL or CONDITIONAL**, even when all other items pass.

### 10.2. Example Restore Reconciliation

An app takes full backups only at **09:00** without transaction log recovery afterward. An incident hits at **09:47**. The DB finishes restoring and passes app transaction checks at **10:42**.

- **Maximum observed time-based RPO:** 47 minutes, since the latest backup restores to 09:00. If transaction logs/PITR apply up to a fresher point, use that mark rather than mechanically picking 09:00.
- **Observed RTO:** 55 minutes, from 09:47 to 10:42.
- Against hypothetical targets of RPO ≤ 15 min and RTO ≤ 60 min, verdict is **RPO FAIL, RTO PASS**.
- Data accuracy holds only up to the exact recovery point; explain how transactions committed between 09:00 and 09:47 are handled.

This example shows why measuring "restored within an hour" alone fails to evaluate the data strategy.

### 10.3. Evidence Log to Archive

~~~text
Exercise: DR-REGION-01
Scope: order-api, region A -> region B, test tenant
Target: RPO <= 60 s; RTO <= 15 min
Outage started: 14:07:32
Last verified commit on A: 14:07:30
Last applied commit on B: 14:07:12
Service restored (E2E passed): 14:14:02
Observed potential data-loss window: 20 s
Observed RTO: 6 min 30 s
Write fencing: verified by audit + controlled test
Integrity check: orders and payments within recovery watermark PASS
Remaining risk: third-party callback retries need further test
Decision: conditional pass; follow-up assigned to integration owner
~~~

Reports should attach evidence links (dashboards, sanitized logs, diff outputs, decision logs), approvers, and test dates. A bare note saying "tested, looks fine" cannot be audited or tracked for progress later.

## 11. Failback: Returning to the Original Region Also Needs Testing

Once A recovers, B likely holds many new transactions. **Never automatically shift traffic and writes back to A** if A lacks all recent changes or if some clients still treat A as primary.

Reference workflow:

1. Keep B as write owner while A is rebuilt or synced from B; accept zero independent writes on A.
2. Verify A's data catches up to B's watermark via supported replication; reconcile key transactions and confirm zero unresolved error events.
3. Schedule a planned switchover window; block/buffer or route writes per design, lock the watermark, and swap primary roles as atomically as supported.
4. Shift global traffic to A; verify reads/writes, authentication, queues/webhooks, latency, and watch for lingering connections to B.
5. Return B to standby, re-establish replication direction, and validate the next DR plan.

If no safe reverse transition exists, the better option may be **staying on B (roll forward)** and repairing A while write-fenced. Base decisions on transaction preservation, not eagerness to return to the original topology quickly.

## 12. Well-Architected Trade-offs

| Pillar | Assessment Questions | Typical Trade-offs |
|---|---|---|
| **Reliability** | Are clean data and an independent standby Region, fencing, failover, and restore all proven? | Tight RPO/RTO usually demands more replication, capacity, and automation. |
| **Security** | How are backups, encryption keys, and emergency privileges isolated; do drills risk data exposure? | Least privilege must pair with audited emergency break-glass workflows. |
| **Operational Excellence** | Are runbooks, on-call, monitoring, periodic drills, postmortems, and improvements active? | Automation cuts manual toil, yet the DR pipeline itself must be tested. |
| **Performance Efficiency** | Does Region B have enough quotas, DB IOPS, network, and compute at recovery load? | Small warm standby saves money yet adds scaling lag during outages. |
| **Cost Optimization** | Are cross-Region replication, backups, egress, standby, drills, log storage, and staffing fully budgeted? | Hot standby raises ongoing spend while lowering business downtime losses. |
| **Sustainability** | Are standby resources right-sized, with storage/deletion policies and lean drill plans? | Over-trimming standby compute can cause missed RTOs. |

An architecture without cross-Region DR may fit an internal workload able to tolerate multi-day downtime; conversely, critical payment flows require far stricter targets. **Architecture assessment must tie technical choices to business impact** instead of forcing one multi-Region blueprint onto every app.

### 12.1. Accounting for Recovery Cost, Not Just DR Maintenance Cost

A rough comparison model:

\[
\text{Expected cost}
= \text{periodic DR cost}
+ \text{drill cost}
+ \text{outage probability}\times\text{outage impact cost}
\]

This is a simple comparison framing, not a complete financial formula. Probabilities and impact costs are hard to estimate precisely; run sensitivity scenarios across downtime, data loss, SLA penalties, and affected transactions rather than inventing false precision.

## 13. Common Assessment Mistakes

| False Conclusion | Why It Is Wrong | Required Replacement Evidence |
|---|---|---|
| "Backups are enabled, so we can restore." | Backups may be corrupt, missing permissions/keys, or version-incompatible. | Trial restore and run the app against restored data. |
| "Replica lag is 0, so RPO is 0." | Lag metrics do not prove every commit applied or survived deletion/corruption. | Commit marks, watermarks, reconciliation, and data-loss policy. |
| "DNS points to B, so failover is done." | Client caches, stale sockets, missing services, and DB issues keep breaking flows. | End-to-end synthetic checks and controlled multi-client transactions. |
| "Two Regions writing together is always more available." | Split-brain, write conflicts, and clock skew corrupt data. | Ownership rules, partition tests, fencing, and reconciliation. |
| "Staging region failover proved production RTO." | Data sizes, traffic, quotas, and integrations differ from live systems. | Representative drills, capacity checks, and production-gap analysis. |
| "Failback just flips routing back." | A may miss all transactions created on B. | Reverse sync, reconciliation, controlled role swap, and failback drill. |
| "DB is up, so the app recovered." | Auth, queues, objects, email/payments, and frontend may still fail. | Test agreed minimum business flows. |
| "Failover mechanism exists, no drill needed." | Misconfigs surface mainly during role swaps or missing dependencies. | Periodic game days, reports, and root-cause fixes. |

## 14. Practice Architecture Assessment Exercise

### Prompt

An e-commerce platform uses Region A as primary and Region B as warm standby. The transactional DB replicates asynchronously to B; object storage replicates via a separate policy; daily backups stay in A with copies transferred to B after creation. App B runs at 25% of A's capacity and must scale during outages. The payment partner allowlists only one outbound IP from A.

Business requirements: **RPO ≤ 2 minutes**, **RTO ≤ 20 minutes** for order creation and payment confirmation. During a simulated outage of A, ops takes 4 minutes to detect; 8 more minutes to promote the DB and scale the app; 6 more minutes to shift traffic. Payment tests from B fail due to the allowlist; another 12 minutes pass before the partner updates its config. At failure onset, Region B lagged by 90 seconds per verified commit marks.

### Learner Tasks

1. Calculate potential RPO and observed end-to-end RTO.
2. Score PASS/FAIL against both targets.
3. Identify three main weaknesses and additional tests needed.
4. Propose a way to cut RTO without switching to active-active.
5. Explain why separate restore testing is still needed despite async replicas in B.

### Analysis Guide

- **Potential RPO:** 90 seconds if no further logs/transactions can be pulled from A; within the 2-minute threshold assuming verified commit marks and no missing changes. Reconcile critical transactions; base final RPO conclusions on surviving records.
- **RTO:** 4 + 8 + 6 + 12 = **30 minutes** from outage onset until payments work; since payment confirmation is inside scope, **RTO FAILS** against 20 minutes. The 18-minute traffic-cutover mark is not end-to-end recovery.
- **Weaknesses:** partner allowlist omits Region B; warm standby scaling duration unproven; backup schedule risks failing on logical errors or backup-region unavailability if overly tied to A. Add scale-under-load tests, network/partner coordination drills, and clean backup restores from B.
- **Improvements:** pre-configure partner allowlists/standby endpoints; pre-stage capacity/quotas and images in B; automate promotion once fencing rules pass; monitor business impact and run periodic synthetic payments from B.
- **Why restore testing matters:** accidental deletes, bad edits, and logic bugs replicate straight to B; rolling back to a clean point requires independent backups/PITR that decrypt and restore cleanly.

### Advanced Variant

If A is not completely gone but merely network-partitioned, test whether both A and B accept writes simultaneously. If yes, the system fails write-ownership validation even if full-Region-loss RPO/RTO passed. Propose write fencing or falling back to read-only mode whenever a single authoritative owner cannot be confirmed.

## 15. Acceptance Checklist for Recovery and Region Failover Architecture

### Requirements and Data Protection

- [ ] Data/app tiers, RPO/RTO, SLOs, and end-to-end measurement rules confirmed by business.
- [ ] Backups/PITR have clear scope, retention, isolation, encryption policies, and restore permissions.
- [ ] Restored into an isolated environment, decrypted, and passed schema and app transaction checks.
- [ ] Reconciliation rules check commit marks/watermarks, keys, and business invariants with zero unexplained discrepancies.
- [ ] Tested a logical error or accidental deletion that replicas cannot protect against.

### Region Failover and Operations

- [ ] Standby Region provisions without depending on resources located solely in the primary Region.
- [ ] Capacity/quotas, networking, DNS, TLS, IAM/secrets/keys, and external integrations verified in the standby Region.
- [ ] Write-ownership rules, fencing, or split-brain prevention tested under network partition faults.
- [ ] Runbooks cover detection, go/no-go decision, data/traffic cutover, smoke tests, monitoring, and incident coordination.
- [ ] Tests accurately measure RPO/RTO, error rates, and real transactions with logged timestamps.
- [ ] Rehearsed failover-failure recovery, failback or roll-forward plans, and reconciliation of newly written data.
- [ ] Evidence report, open-item owners, due dates, and re-drill schedule documented after major changes.

### Architectural Trade-offs

- [ ] Costs for backups, cross-Region replication, standby, network egress, observability, and drills budgeted.
- [ ] Security, data residency, and compliance obligations enforced across both backup stores and recovery Regions.
- [ ] Architecture conclusion states pass conditions, unverified gaps, and accepted risk levels.

**Conclusion:** the assessment question is not "does the architecture have backups and Region B?", but **"have we proven data integrity, safe write ownership, and usable end-to-end service within RPO/RTO?"** Only when restores, Region failover, reconciliation, and failback are rehearsed with measured evidence is the recovery design ready for acceptance.
