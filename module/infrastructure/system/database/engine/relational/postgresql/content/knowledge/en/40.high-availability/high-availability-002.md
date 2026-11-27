# RPO, RTO Targets, and Multi-Failure-Domain Architecture in PostgreSQL

A high-availability PostgreSQL system must answer two questions before choosing a topology: **how much data loss is acceptable during an incident, and how quickly must the service return to operation?** Those two answers are expressed as RPO (Recovery Point Objective) and RTO (Recovery Time Objective).

RPO and RTO are business and operational targets. They dictate replica count, WAL synchronization mode, standby placement, backup strategy, failover mechanisms, spare capacity, testing procedures, and budget. A diagram with multiple PostgreSQL nodes does not necessarily achieve HA if those nodes share the same storage, network segment, identity system, or an operator who can delete everything at once.

In this lesson, a **failure domain** is a boundary within which a single common incident can disable multiple components simultaneously. A multi-failure-domain architecture must provide sufficient independence so that a failure in one domain does not bring down the entire system, while still allowing safe failover coordination.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Define RPO, RTO, RLO, availability, and SLO/SLA.
2. Translate business requirements into measurable recovery targets.
3. Distinguish HA, disaster recovery, backup, and business continuity.
4. Identify failure domains across process, host, rack, availability zone, region, and cloud account/provider.
5. Design primary/standby PostgreSQL topologies with synchronous or asynchronous replication.
6. Explain trade-offs among data loss, commit latency, and availability.
7. Understand quorum, fencing, leader election, split brain, and failover safety.
8. Design multi-AZ and multi-region topologies.
9. Combine streaming replication with WAL archiving, base backups, and PITR.
10. Calculate capacity headroom, replication lag, and recovery throughput.
11. Build runbooks, monitoring, alerting, and restore/failover drills.
12. Evaluate costs, limitations, and failure modes of an HA architecture.

## 2. What Is RPO?

### 2.1. Definition

**Recovery Point Objective (RPO)** is the maximum amount of data an organization accepts losing, typically measured as the time from the incident back to the latest recoverable recovery point.

Examples:

- RPO 0: for committed and acknowledged transactions within the stated failure assumptions, zero transaction loss is accepted.
- RPO 5 minutes: recovering to a data point at most 5 minutes prior to the incident is acceptable.
- RPO 1 hour: the organization can tolerate losing up to roughly one hour of transactions.

RPO does not mean “run a backup every 5 minutes.” Backup cadence is only one factor; streaming replication, WAL archiving, replication lag, archive latency, and failure modes determine the actual recovery point.

### 2.2. RPO Calculation Example

A primary writes WAL continuously. An asynchronous standby has replayed WAL up to 10:24:30. The primary fails at 10:25:00 and unsent/unflushed WAL cannot be retrieved from the primary.

The latest recovery point on the standby may correspond to 10:24:30. The RPO is approximately 30 seconds, assuming transaction timestamps and LSN mapping are properly understood.

This is a simplified example. In operations, rely on LSN/commit metadata and lag measurements; `pg_last_xact_replay_timestamp()` can appear stale even when the standby has replayed all available WAL if the primary had no recent transactions.

### 2.3. RPO Is a Target, Not a Measurement

Distinguish between:

- **Target RPO:** maximum data loss accepted by the business;
- **Observed RPO:** actual data lost during an incident or drill;
- **Potential RPO:** amount of data at risk given current replication/archive lag.

If the target RPO is 30 seconds but the standby routinely lags by 3 minutes, the architecture is already failing to meet the target even before an incident occurs.

### 2.4. RPO by Failure Type

RPO must be tied to specific failure scenarios:

| Incident | Recovery Mechanism | Achievable RPO |
| --- | --- | --- |
| PostgreSQL process crash | Crash recovery from local WAL | Usually zero loss for commits flushed under durability settings |
| Primary host loss | Promote standby | Depends on sync/async replication and received WAL |
| Single AZ outage | Promote standby in another AZ | Depends on standby placement and replication mode |
| Region outage | Promote replica / restore in another region | Depends on cross-region replication and archive lag |
| Logical corruption / accidental DELETE | PITR from base backup + WAL | Up to just before the erroneous operation, if WAL chain is complete |
| Ransomware / backup deletion | Restore from immutable/offline copy | Depends on latest clean copy |
| Loss of entire cloud account/provider | Restore in an independent provider/account | Depends on offsite copies and replicated data |

A stated RPO without specifying the failure scenario can be misleading. RPO 0 for a host failure does not mean RPO 0 if an entire region is destroyed or a user executes a valid deletion.

### 2.5. RPO and Asynchronous Replication

An asynchronous standby receives WAL after the primary has acknowledged the commit. When the primary fails abruptly, some recently committed WAL may not have reached the standby. RPO depends on:

- WAL generation rate;
- Network bandwidth/latency;
- Standby write/flush/replay throughput;
- Network outage duration;
- Queueing and disk capacity;
- How failover selects the candidate node.

You cannot infer RPO solely from a single-point `replay_lag` reading. Combine LSN distance with receive/flush/replay timing.

### 2.6. RPO and Synchronous Replication

With properly configured synchronous replication, the primary acknowledges a commit only after one or more synchronous standbys have flushed the WAL (or reached the configured `synchronous_commit` level). This reduces or eliminates loss of acknowledged commits within the covered failure scenario.

However, RPO 0 has conditions:

- A synchronous standby is actually active and selected;
- Commit acknowledgment waits for the appropriate durability level;
- Standby and primary do not share the failed domain;
- Storage on both nodes honors flush semantics properly;
- Failover picks a node holding the acknowledged WAL;
- No misconfiguration, manual override, or propagated corruption occurred.

Synchronous replication does not protect against accidental DELETEs, application bugs, malicious SQL, or simultaneous loss of all replicas.

## 3. What Is RTO?

### 3.1. Definition

**Recovery Time Objective (RTO)** is the maximum time an organization accepts to restore a service after an incident. RTO must be measured from an agreed starting point—such as when the service stops answering requests or when the incident is detected—until the service meets operational readiness criteria again.

RTO is not just PostgreSQL process startup time. It can encompass failure detection, failover decision, fencing, promotion, endpoint cutover, warm-up, validation, and traffic resumption.

### 3.2. RTO Decomposition

A useful breakdown:

| Phase | Content |
| --- | --- |
| Detection | Monitoring detects and confirms the incident |
| Decision | Incident triage, deciding to fail over or restore |
| Fencing | Preventing the old primary from continuing to accept writes |
| Recovery | Promoting a standby or restoring a base backup and replaying WAL |
| Cutover | Switching DNS/VIP/load balancer/connection routing |
| Validation | Verifying database, data, and application behavior |
| Stabilization | Monitoring load, replication, backups, and error rates |

The sum of these phases constitutes the observed RTO. If RTO is measured up to the first successful request, track post-cutover stabilization separately.

### 3.3. RTO Example

A system sets a 15-minute RTO for a primary host failure:

- Detection: 1 minute;
- Decision and fencing: 2 minutes;
- Standby promotion: 1 minute;
- Endpoint cutover: 2 minutes;
- Application validation: 4 minutes;
- Stabilization: 5 minutes.

Total: 15 minutes. If an actual drill takes 27 minutes, the architecture/runbook does not meet RTO even if promotion itself took only 30 seconds.

### 3.4. RTO Differs from Downtime

Downtime is the actual duration the service fails to serve requests. RTO is the pre-defined target limit. A system may meet RTO during a drill yet suffer longer downtime in a real incident if a larger failure domain is affected.

### 3.5. RTO and Database Size

Restoring from backup typically scales with:

- Total bytes to read and write;
- Storage throughput and IOPS;
- Number of tablespaces/volumes;
- Volume of WAL to replay;
- Number of incremental backups to combine;
- CPU and compression overhead;
- Extension initialization;
- Index/collation rebuilds;
- Validation and application warm-up.

For multi-terabyte clusters, downloading backups from object storage can take hours. If RTO is only a few minutes, a pre-built standby is typically required rather than starting a restore after the incident.

### 3.6. RTO and RPO Can Conflict

Synchronous replication can reduce RPO, but it increases commit latency and can block writes when synchronous standbys are unavailable, depending on configuration. Asynchronous replication can improve write availability but risks losing some WAL during failover.

Restoring from backup can reach an older recovery point but takes longer than promoting a standby. Designs must therefore balance RPO, RTO, and failure scenarios together.

## 4. Related Objectives: Availability, SLO, and RLO

### 4.1. Availability

Availability is typically expressed as the percentage of time a service is operational over a measurement window:

\[
\text{Availability} =
\frac{\text{Available Time}}{\text{Total Observed Time}}
\times 100\%
\]

For example, 99.9% availability allows roughly 0.1% unavailability within the measurement period. The equivalent minutes of downtime depend on whether the period is a month, quarter, or year.

### 4.2. SLO and SLA

- **SLO (Service Level Objective):** internal or published service quality targets, e.g., 99.95% availability, 1-minute RPO, 15-minute RTO.
- **SLA (Service Level Agreement):** contractual commitment with customers, potentially carrying penalties/credits if missed.
- **SLI (Service Level Indicator):** measured metrics such as request success rate, latency, error rate, or availability.

An SLO must specify measurement methodology, time window, data sources, and clear exclusions.

### 4.3. RLO and Business Recovery

Recovery Level Objective (RLO) describes the level of functionality or data that must be restored—for example, read-only access first, followed by full transactional writes. RLO is useful when a system can operate in a degraded mode while full recovery completes.

### 4.4. MTPD / MAO

Maximum Tolerable Period of Disruption (MTPD), sometimes called Maximum Acceptable Outage (MAO), is the longest disruption the business can endure before consequences become unacceptable. RTO must be lower than MTPD to leave margin for verification and operational resumption.

### 4.5. Example Targets for a Service

| Target | Example Value |
| --- | --- |
| Availability SLO | 99.95% per month |
| RPO on host/AZ loss | 0–30 seconds depending on replication mode |
| RPO on region loss | 5 minutes |
| RTO on host loss | 5 minutes |
| RTO on AZ loss | 10 minutes |
| RTO on region loss | 2 hours |
| RTO on logical corruption | 4 hours |
| Initial RLO | Read-only, then enable writes |

These values illustrate how to separate targets by scenario rather than acting as universal defaults.

## 5. What Is a Failure Domain?

### 5.1. Definition

A failure domain is a set of components that can be affected simultaneously by a single root cause. Separating nodes by hostname is insufficient if they still share power, network switches, storage arrays, or a control plane.

Goals of a multi-failure-domain architecture:

1. Reduce the probability that a single incident destroys all replicas;
2. Preserve enough data and capacity to continue serving;
3. Prevent isolated replicas from accepting conflicting writes;
4. Provide a recovery path when failures exceed normal HA boundaries.

### 5.2. Failure Domain Layers

| Layer | Incident Example | Isolation Measures |
| --- | --- | --- |
| Process | PostgreSQL backend/postmaster crash | Supervisor, restart, standby |
| VM/host | Kernel panic, host power loss | Replicas on separate hosts |
| Rack | PDU, top-of-rack switch, cooling | Cross-rack placement |
| Availability zone (AZ) | AZ power, network, or storage outage | Replica in another AZ |
| Region | Region-wide network/control-plane outage | Separate DR region |
| Cloud account/project | IAM lockout, accidental deletion, billing/suspension | Independent account/project |
| Cloud provider | Provider outage or policy event | Off-provider backup/DR |
| Identity/control plane | DNS, IAM, KMS, secrets, orchestration outage | Break-glass access and dependency redundancy |
| Human/operational | Accidental deletion, faulty deploy, leaked credentials | RBAC, approvals, immutable backups, audit |
| Software/data | Bug, corrupt migration, ransomware | PITR, logical copies, immutable/offline backups |

### 5.3. Correlated Failure Domains

Two separate VMs can still share a failure domain if:

- They run on the same physical host or rack;
- They share a single storage volume/array;
- They rely on the same AZ network gateway;
- They use the same KMS key or identity provider;
- Backups and primary reside in the same account with identical delete permissions;
- Both receive the same faulty deployment or configuration change.

Isolation must consider both physical infrastructure and operational dependencies.

### 5.4. AZ and Region

An availability zone is typically an isolated infrastructure zone within a region with independent power and networking as defined by the provider. A region covers a broader geographic area with stronger failure independence.

Multi-AZ generally protects against single-AZ outages with lower latency than multi-region. Multi-region protects against regional disasters but incurs higher replication latency, data transfer costs, and failover complexity.

### 5.5. Storage Failure Domains

If a primary and standby reside in two AZs yet rely on a single shared storage system with a single failure domain, losing that storage can affect both nodes. Shared storage may have internal redundancy, so you must understand its actual failure boundaries and SLA.

With PostgreSQL streaming replication, each node normally maintains its own data files on independent storage. This avoids certain shared-disk failures while requiring WAL synchronization and failover management.

### 5.6. Backup Failure Domains

Backups stored in the same region/account as the primary can be lost alongside it when:

- Credentials are compromised and an attacker deletes both;
- IAM policies or configurations are misapplied;
- The region/provider experiences an outage;
- Ransomware encrypts a mounted backup repository.

Keep immutable, offline, cross-account, or cross-region copies aligned with your threat model. Ensure DR accounts can still access backups even if the primary identity system is down.

### 5.7. Control Plane Failure Domains

A database may be healthy while applications still cannot connect if DNS, secrets manager, KMS, load balancers, service discovery, or the orchestration control plane fail. DR planning must cover these dependencies, not just PostgreSQL.

### 5.8. Human Failure Domains

A single action can span multiple regions if one automation role holds permission to delete all backups and replicas. Limit the blast radius with:

- Least privilege;
- Separating operational privileges from backup deletion privileges;
- Multi-person approval for destructive actions;
- Immutable retention / object lock;
- Isolated audit logs;
- Protected and tested break-glass accounts.

## 6. HA, Disaster Recovery, and Backup Are Different

### 6.1. High Availability (HA)

HA focuses on maintaining or rapidly restoring service during common component failures. An HA topology may use primary + standby, health checks, fencing, and automated failover.

HA targets are usually measured by short RTO and low RPO for host/AZ failures. HA does not automatically protect against logical corruption or accidental deletions.

### 6.2. Disaster Recovery (DR)

DR prepares for recovery when a large failure domain is lost: an entire region, provider, account, storage system, or site. DR commonly relies on cross-region replicas, base backups, WAL archives, immutable copies, and procedures to restart operations elsewhere.

DR may accept higher RTO/RPO than HA due to infrastructure provisioning, dependency recovery, data verification, and traffic rerouting.

### 6.3. Backup

A backup is a recoverable copy of data. It supports DR and protects against logical errors, but backups alone do not make a service HA. Backups must be independent of replication because replication faithfully propagates valid erroneous changes.

### 6.4. Business Continuity

Business continuity spans people, processes, applications, networking, partners, customer support, and business operations. Database recovery is only one part of a business continuity plan.

### 6.5. Quick Comparison

| Mechanism | Goal | Example |
| --- | --- | --- |
| Restart/recovery | Recover from process failure | PostgreSQL crash recovery |
| HA | Continue serving after host/AZ failure | Promote standby |
| DR | Recover from major disaster | Restore/promote in another region |
| Backup/PITR | Return to a historical data state | Restore base backup + WAL |
| Business continuity | Maintain business operations | Read-only/degraded mode, manual workflows |

## 7. Basic HA Architecture for PostgreSQL

### 7.1. Primary and Standby

PostgreSQL physical streaming replication uses WAL to synchronize changes from primary to standby. The primary accepts writes; the standby receives, flushes, and replays WAL to update its data files.

~~~text
              Application
                   |
              Write endpoint
                   |
              PostgreSQL
                Primary
                   |
              WAL streaming
                   |
              PostgreSQL
                Standby
~~~

A standby can serve read-only queries when hot standby is enabled. Promotion turns a standby into a new primary following a failover decision.

### 7.2. Streaming Replication Does Not Automatically Fail Over

PostgreSQL provides the replication protocol and recovery primitives. Detecting primary loss, choosing a standby, fencing the old primary, promoting, and updating endpoints require external orchestration or a managed service.

Common HA tools in the ecosystem include Patroni, repmgr, `pg_auto_failover`, and cloud managed database services. Choose a tool based on its consensus store, fencing mechanisms, supported PostgreSQL versions, operational expertise, and recovery behavior.

### 7.3. Two Nodes Are Not Enough to Decide Safely in Every Partition

With only two nodes, if connectivity between them breaks, neither node can tell whether the other died or is merely network-isolated. If both promote and accept writes, split brain occurs.

An HA system needs quorum/witnesses or out-of-band fencing/control to establish primary ownership. Node count alone does not create quorum logic.

### 7.4. Separating Data Plane and Control Plane

- **Data plane:** PostgreSQL, WAL, data files, replication network.
- **Control plane:** health checks, leader election, DCS/consensus, fencing, service discovery, VIP/DNS, automation.

The control plane must have its own failure model. If the DCS sits in a single AZ, a multi-AZ data topology may still fail to fail over when that AZ goes down.

### 7.5. Client Routing

Applications should not hard-code the primary's IP. Use a stable endpoint via proxy, VIP, DNS/service discovery, or a managed endpoint. Verify DNS caching, connection pool retries, TCP keepalives, and transaction retry semantics.

### 7.6. Failover Does Not Make Transaction Retries Automatically Safe

If a connection drops during COMMIT, the client may not know whether the transaction committed. Blindly retrying a request can cause duplicate business actions. Use idempotency keys, unique constraints, transaction status lookups, and explicit application retry policies.

## 8. Synchronous and Asynchronous Replication

### 8.1. Asynchronous Replication

The primary does not wait for a standby to acknowledge WAL before returning commit success. This minimizes commit latency and allows the primary to keep accepting writes when a standby or network link slows down, at the risk of losing unshipped WAL if the primary fails.

### 8.2. Synchronous Replication

The primary waits for one or more synchronous standbys to reach the specified acknowledgment level before confirming commit. This increases durability for acknowledged commits under the failure assumptions, but can stall writes when synchronous standbys are unavailable.

### 8.3. `synchronous_commit` Levels

Common levels:

| Setting | Standby Wait Condition |
| --- | --- |
| `off` | Does not wait for normal local WAL flush on commit; recently acknowledged transactions may be lost on crash |
| `local` | Waits for local WAL flush, does not wait for synchronous standby |
| `remote_write` | Waits for synchronous standby to write WAL to OS, not necessarily durable on storage |
| `on` | Waits for synchronous standby to flush WAL to durable storage |
| `remote_apply` | Waits for synchronous standby to replay WAL in addition to flushing |

Verify setting names and semantics against your major version. `synchronous_commit=on` only waits remotely if a synchronous standby is configured and active; without one, this setting alone does not make asynchronous replication synchronous.

### 8.4. `synchronous_standby_names`

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
~~~

Selects one synchronous standby in priority order. Quorum can also be configured:

~~~conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
~~~

This quorum example requires at least two standbys from the list to acknowledge. Check exact syntax and behavior for your version. `FIRST` and `ANY` have different semantics when selecting synchronous standbys.

### 8.5. Commit Latency

Synchronous commit latency is at minimum affected by network round-trip time to the standby, WAL flush latency, and scheduling. Cross-region synchronous replication can substantially increase latency due to geographic distance.

### 8.6. Availability Trade-off

If all synchronous standbys lose connectivity, commits may block while the primary remains up. This may be desirable to protect RPO, but requires a deliberate operational policy:

- Wait for a standby to recover;
- Shift the synchronous target to another healthy node;
- Temporarily fall back to async mode under explicit approval/risk policy;
- Fail over traffic to another node if eligible.

Never silently downgrade durability without alerting and recording the new effective RPO.

### 8.7. Quorum Replication

With `ANY N`, transactions wait for N standbys in the list to acknowledge. Quorum tolerates losing some standbys, but node count, failure domains, and promotion candidates must be carefully aligned.

Having a node acknowledge WAL does not help if failover promotes a different node that lacks that WAL. The failover controller must choose a candidate whose recovery point is at least as current as acknowledged commits.

### 8.8. Do Not Confuse `remote_write` with Durable Flush

`remote_write` confirms WAL was written to the standby's OS, which is not equivalent to a durable flush to physical media. To protect against standby power loss or storage crashes, understand acknowledgment levels and storage flush semantics.

### 8.9. Do Not Confuse `remote_apply` with Business Consistency

`remote_apply` ensures the standby has replayed WAL up to the commit, which helps read-after-write on that standby. It does not guarantee that downstream caches, search indexes, message queues, or external services have updated.

### 8.10. Replication Lag

Track separately:

- Send lag: WAL not yet sent by the primary to the standby;
- Write lag: WAL received but not yet written to OS;
- Flush lag: WAL written but not yet durably flushed;
- Replay lag: WAL flushed but not yet applied to data pages.

These metrics can be NULL depending on activity and state; pair them with LSN distance, WAL generation rate, and observation timestamps.

## 9. Multi-AZ Architecture

### 9.1. Primary/Standby Model Across Two AZs

~~~text
                    Region A
       +----------------+   +----------------+
       | AZ-a           |   | AZ-b           |
       |                |   |                |
App -->| Primary        |-->| Standby        |
       | local storage  |WAL| local storage  |
       +----------------+   +----------------+
                \               /
                 \-- HA control-/
                    plane
~~~

Primary and standby reside in different AZs with independent storage and separate network paths. If AZ-a fails, the controller can promote the standby in AZ-b after verifying the old primary can no longer accept writes.

### 9.2. Number of Standbys

A single standby handles a single failure but leaves no redundancy after promotion. For higher resilience, consider:

- One synchronous standby in another AZ to minimize RPO;
- A second asynchronous standby in a third AZ or another region;
- An independent WAL archive for PITR/DR.

You do not need a replica in every AZ if costs outweigh benefits; base the choice on failure scenarios and RTO/RPO.

### 9.3. Primary and Standby in the Same AZ

Two nodes on separate hosts in the same AZ protect against host/process failure but not an AZ outage. Document the exact protection level in your architecture docs.

### 9.4. Synchronous Standby in the Same Region

Placing a synchronous standby in another AZ within the same region balances latency and RPO. However, if the entire region experiences a partition or outage, synchronous commits may block and prevent the primary from maintaining write availability.

### 9.5. Three AZs and Quorum

With three AZs, you can place the primary and two standbys—or DCS/consensus voters—across all three AZs. Distinguish control-plane quorum from PostgreSQL synchronous standby count:

- DCS quorum decides which node is permitted to hold leadership;
- PostgreSQL synchronous quorum decides how many WAL acknowledgments a commit requires.

Both mechanisms work together without replacing each other.

### 9.6. Compute, Storage, and Network

Multi-AZ is effective only when all layers are separated:

- Compute instances in different AZs;
- Separate data volumes replicated via WAL;
- Ready network routes/firewalls/security groups;
- DNS/load balancer with failover endpoints;
- Backup repository not tied to a single AZ;
- Control plane quorum spanning beyond a single AZ.

### 9.7. AZ Outage and Failover

When an AZ goes down:

1. Verify the outage is not a local network partition;
2. Determine whether the primary can still receive writes via another path;
3. Fence the old primary;
4. Select the standby with the latest WAL meeting RPO;
5. Promote;
6. Switch endpoints;
7. Validate the application and rebuild redundancy.

### 9.8. An Availability Zone Is Not Fully Independent of the Region

AZs within a region can still share control planes, DNS services, identity services, or backbone networks. Multi-AZ mitigates many risks but does not replace cross-region DR.

## 10. Multi-Region Architecture

### 10.1. Why Is a Second Region Needed?

Multi-region protects against failures exceeding a single AZ or affecting an entire region: widespread infrastructure outages, backbone network failures, control-plane outages, physical disasters, or operational mistakes wiping the primary region.

### 10.2. Active-Passive

One region serves writes; the other maintains a standby/read-only copy ready to assume the primary role when DR is triggered.

~~~text
               Application
                    |
              Global endpoint
                    |
             Region A (active)
             PostgreSQL primary
                    |
             Async WAL stream
                    |
             Region B (passive)
             PostgreSQL standby
                    |
             WAL archive + backups
~~~

Active-passive is generally simpler for a single PostgreSQL cluster because there is only one write primary at any time.

### 10.3. Active-Active Does Not Mean Two Primaries Writing to One Cluster

PostgreSQL physical streaming replication is primary-to-standby. It does not offer multi-writer conflict resolution between two independent primaries.

Active-active at the application layer or via logical replication requires designing conflict handling, key allocation, transaction semantics, and consistency. Never assume active-active means two physical primaries writing to the same PGDATA/replication stream.

### 10.4. Cross-Region Asynchronous Replication

This is common because it keeps primary commit latency low. RPO depends on WAN latency/bandwidth and standby lag. The DR region needs sufficient capacity and WAL retention to replay cleanly.

### 10.5. Cross-Region Synchronous Replication

Can lower RPO for acknowledged commits, but increases commit latency by at least a WAN round-trip. If the inter-region link drops, the primary may block writes under sync policy. Only choose this when the business accepts the latency and availability trade-offs.

### 10.6. Regional Independence

The DR region must be sufficiently independent in:

- Compute capacity/quotas;
- Storage volumes/object storage;
- Network ingress/egress;
- DNS/global traffic manager;
- IAM roles and KMS access;
- Secrets/certificates;
- Monitoring/alerting;
- Backup catalog and restore tooling.

If the DR region has only a database replica without applications, network routes, credentials, or capacity to run the workload, actual RTO will be high.

### 10.7. Failover to Region B

Scenario steps:

1. Confirm Region A is lost or cannot recover within RTO;
2. Check which WAL LSN Standby B has received/replayed;
3. Quantify potential data loss against target RPO;
4. Fence Region A via network/IAM/compute controls if still reachable;
5. Promote Standby B;
6. Switch global endpoints and applications;
7. Verify writes and business invariants;
8. Start backups/WAL archiving on the new timeline;
9. Rebuild Region A as a standby once safe.

### 10.8. Failback Does Not Automatically Reverse Failover

Once B accepts writes, A is stale and divergent. To return to A, rebuild or rewind A from B, wait for catch-up, schedule a switchover, and fence B at cutover. Never bring A back online as the old primary.

### 10.9. DNS TTL and Endpoint Switching

Global DNS/traffic managers have TTLs, caches, and health-check delays. Some clients hold connection pools longer than TTL. RTO must include the time for clients to resolve the new endpoint and reconnect.

### 10.10. Data Sovereignty and Compliance

Cross-region replication can move data across borders. Verify data residency, encryption, key locality, retention, privacy rules, and vendor contracts before selecting a DR region.

### 10.11. Inter-Region Network Partition

If primary and DR regions lose connectivity while both remain operational, never auto-promote the DR region merely because it cannot reach the primary. Require fencing/quorum or a controlled decision process to prevent dual-primary writes.

## 11. Quorum, Leader Election, and Fencing

### 11.1. Quorum

Quorum is the minimum number of votes needed for a decision in a distributed system to be valid. For a consensus group of N voters, a majority quorum is typically floor(N/2)+1.

Examples:

| Voters | Majority Quorum |
| ---: | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |

Quorum prevents both sides of a network partition from achieving a majority when voters and protocols are properly deployed.

### 11.2. Witness

A witness is a voter/arbiter that does not necessarily hold PostgreSQL data. It helps break ties over leadership when two data nodes lose connectivity.

A witness does not replace a standby holding WAL/data. With only a witness and no healthy data replica, quorum cannot produce a runnable database.

### 11.3. Leader Election

The HA controller elects one node permitted to act as primary. Leadership requires leases/terms/epochs or consensus state so an old node stops writing once it loses authority.

### 11.4. Fencing

Fencing prevents the old node from continuing to access or write to production resources before promoting a new node. It can be enforced via:

- Stopping/terminating the instance or host;
- Power fencing via out-of-band management;
- Revoking storage/network access;
- Blocking write traffic at the network/load balancer;
- Cloud API/IAM/compute fencing;
- Cluster manager lease/leader token enforcement.

Merely removing an IP from DNS is not reliable fencing if applications can still connect directly to the old primary.

### 11.5. Split Brain

Split brain occurs when two nodes both believe they are primary and accept writes independently. Their histories diverge; PostgreSQL physical replication cannot automatically merge divergent branches.

Consequences:

- Lost or duplicated business transactions;
- Divergent WAL timelines;
- Inconsistent IDs/unique keys;
- Difficulty determining the source of truth;
- Complex manual recovery via logical reconciliation.

### 11.6. Failover Safety

Before promoting, the controller must:

1. Ensure the old primary is fenced or verifiably unable to write;
2. Identify candidate standbys and their WAL positions;
3. Verify the candidate is eligible for promotion;
4. Record the decision/epoch;
5. Promote exactly one node;
6. Only afterward route writes to the new endpoint.

### 11.7. DCS Quorum Does Not Guarantee Latest Data

A quorum-backed DCS safely elects a control-plane leader, yet the PostgreSQL candidate might still lag in WAL. Add candidate selection policies checking WAL LSN, synchronous replication guarantees, and business RPO.

### 11.8. Synchronous Quorum vs. Failover Quorum

Synchronous quorum answers “how many standby acknowledgments does a commit need?” DCS quorum answers “which node is allowed to be leader?” Never conflate the two quorums.

### 11.9. Manual Failover

Manual failover still requires a checklist covering fencing, candidate selection, promotion, endpoint updates, and validation. A DBA running `pg_ctl promote` does not automatically stop the old primary.

### 11.10. Failover Automation

Automation must handle timeouts, transient network glitches, false positives, DCS unavailability, lagging replicas, and stale endpoints. Test scenarios where the controller itself crashes mid-failover, not just happy paths.

## 12. How Replication, Backup, and PITR Complement Each Other

### 12.1. Replication Is Not a Backup

Streaming replication copies WAL changes nearly continuously. If a user runs DROP TABLE or an application writes bad data, the standby replays that change too.

### 12.2. Backup Is Not HA

Base backups and WAL archives can restore a cluster, but large restores can take hours. If RTO is a few minutes, a standby or managed failover is required.

### 12.3. PITR Protects Against Logical Errors

PITR uses a base backup + WAL archive to stop right before an erroneous transaction/operation. Restoring to a temporary cluster lets you extract accidentally deleted data without necessarily rolling back all of production.

### 12.4. Multi-Layer Architecture

~~~text
                 Primary
                    |
          +---------+----------+
          |                    |
     Sync standby        Async DR standby
       Multi-AZ             Other region
          |                    |
          +---------+----------+
                    |
              WAL archive
                    |
              Base backups
                    |
          Immutable/offsite copy
~~~

This diagram illustrates protection layers. Your actual topology must select replica counts, sync policies, archive paths, and failure domains to match RPO/RTO.

### 12.5. Independent WAL Archiving

WAL archives should reside in a different storage/account/failure domain from the primary. Monitor archive success, failed segments, retention, and timeline history. Streaming standbys do not replace WAL archiving.

### 12.6. Backup Encryption and Immutability

Encrypt backups in transit and at rest, protect keys independently, enforce immutable retention/object lock, and separate delete privileges. Test key recovery in the DR site.

### 12.7. Backup Cadence and WAL

More frequent base backups reduce WAL replay volume and shorten RTO, at higher storage/network cost. Incremental backups reduce transfer size but add chain complexity. Measure actual restore times before choosing a cadence.

### 12.8. Logical Backups

Logical dumps are useful for selective recovery, migrations, and table extraction. They supplement physical backups, especially when recovering a single object after an accidental change.

## 13. Capacity Planning for Standby and DR

### 13.1. Standbys Need Enough Capacity to Run Production

A standby with lower CPU/RAM/storage than the primary may keep up during normal load yet collapse under peak load after promotion. When the primary fails, the entire application workload shifts to the remaining node.

Capacity planning must check:

- CPU cores, clock speed, and NUMA;
- RAM and `shared_buffers`;
- Storage IOPS/throughput/latency;
- Network bandwidth;
- WAL receiver/replay throughput;
- Connection limits;
- Temporary files and sort/hash memory;
- Extension and background worker capacity.

### 13.2. N+1 Capacity

N+1 design means that after losing one node, remaining capacity still meets target workload demands. If primary and standby each handle only 50% of peak capacity, failover immediately overloads the cluster upon recovery.

### 13.3. Headroom

Reserve headroom for:

- Peak traffic;
- WAL replay;
- Autovacuum;
- Backup/restore;
- Index maintenance;
- Post-failover connection storms;
- Monitoring and management agents.

Never use low average CPU as proof that a standby has enough capacity.

### 13.4. WAL Replay Throughput

If a standby replays WAL slower than the primary generates it over a sustained period, lag will grow unbounded. If the primary fails, the standby's recovery point falls further behind.

Measure WAL generation rate and replay throughput under peak workload. If replay throughput is low, inspect storage random I/O, CPU, checkpoint behavior, hot standby query conflicts, and network performance.

### 13.5. Catch-Up Time

A standby lagging by 100 GB needs catch-up time governed by effective throughput. At 200 MB/s net replay throughput, the theoretical minimum is ~500 seconds, plus I/O contention, WAL arrival, and checkpoints. Measure via drills rather than dividing size by advertised bandwidth.

### 13.6. Storage Capacity

Provision storage space for:

- Data growth;
- WAL retention from replication slots;
- Archive staging;
- Temporary restore files;
- Incremental combine output;
- Index rebuilds;
- Backup retention;
- Emergency headroom.

An inactive slot can retain WAL indefinitely and fill `pg_wal`. Alert before disk pressure impacts the primary.

### 13.7. Connection Capacity

After failover, clients may reconnect simultaneously. `max_connections`, connection pool sizing, PgBouncer/proxy capacity, and application retry jitter must accommodate peak reconnection storms.

### 13.8. DR Region Capacity

If the DR region runs a smaller standby, know the scale-up time, quotas, instance availability, and storage resize times. An under-provisioned node may achieve database recovery yet miss service RTO.

## 14. Monitoring to Prove RPO/RTO

### 14.1. Replication Monitoring

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

On the standby:

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
~~~

View names/columns may vary by major version. Check system catalogs for your running version.

### 14.2. Tracking LSN Distance

On the primary, check current WAL LSN:

~~~sql
SELECT pg_current_wal_lsn();
~~~

On the standby, query:

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

Comparing LSNs requires calculating byte offsets with the appropriate function and ensuring both values belong to the same timeline/cluster history. Never compare LSNs across unrelated timelines as a direct lag metric.

### 14.3. Replication Lag Time

Lag columns in `pg_stat_replication` are helpful but are not an absolute RPO clock. During idle WAL periods, lag can be NULL or stale; during WAL bursts, lag spikes rapidly. Combine LSN gaps, WAL generation rates, and timestamps.

### 14.4. Archive Monitoring

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time
FROM pg_stat_archiver;
~~~

Alert when archive failures increase, `last_archived_time` falls behind WAL activity, or the repository stops receiving segments. Monitor chain continuity, not just command exit codes.

### 14.5. Primary Health Checks

Health checks should inspect multiple layers:

- PostgreSQL process/connectivity;
- Query responsiveness;
- Disk/memory pressure;
- WAL/archive progress;
- Replication state;
- Application-level write/read path;
- Control-plane leader/fencing state.

An open TCP port does not prove the primary can accept transactions.

### 14.6. Standby Health Checks

Verify:

- WAL receiver connected;
- Receive/flush/replay LSN advancing;
- Lag within target;
- Sufficient storage capacity;
- Standby is eligible for promotion;
- Compatible extensions/configurations;
- No abnormal recovery conflicts.

### 14.7. Potential RPO Alerts

Define alert thresholds aligned with targets:

- Warning when estimated potential RPO reaches 50% of budget;
- Critical when target RPO is exceeded;
- Page on-call if standby/archive cannot catch up.

Tune example thresholds to your workload and business goals. Do not wait for an outage to discover replica lag.

### 14.8. RTO Telemetry

Record automated timestamps for:

- First failure signal;
- Incident declaration;
- Failover decision;
- Fencing completion;
- Promotion completion;
- Endpoint switch;
- First successful application request;
- Business validation completion.

Use these to compute each RTO phase and pinpoint bottlenecks.

### 14.9. Alert Fatigue

Every alert needs clear severity, owner, runbook link, and action. Avoid paging on a single transient metric with no user impact; equally, avoid lumping all failures into one generic health check that is hard to diagnose.

### 14.10. HA/DR Dashboard

A dashboard should display:

- Primary/standby roles and node health;
- Timeline/system identifier;
- Synchronous standby state;
- Send/write/flush/replay LSN gaps;
- WAL generation/replay rates;
- Archive status/latest segment;
- Slot-retained WAL;
- Disk/CPU/network headroom;
- Potential RPO;
- Restore drill RTO history.

## 15. Failure Scenarios and Response Matrix

| Scenario | Detection | Primary Response | Target to Measure |
| --- | --- | --- | --- |
| Process crash | Process/SQL health check | Restart, crash recovery | Process recovery RTO |
| Primary host lost | Host/DB unreachable | Fence host, promote standby | Host RPO/RTO |
| AZ network partition | Cross-AZ health/consensus | Establish quorum, fence old side | Split-brain prevention |
| AZ outage | Cloud/AZ signals | Promote standby in other AZ | AZ RPO/RTO |
| Region outage | Multi-signal regional failure | DR decision, promote Region B | Region RPO/RTO |
| Standby lag | LSN gap/lag alert | Add capacity, fix network/I/O | Potential RPO |
| WAL archive failure | `pg_stat_archiver`/repository | Repair pipeline, protect WAL | PITR recoverability |
| Logical corruption | Data/business validation | Isolate, PITR restore | Logical RPO/RTO |
| Ransomware | Security/backup integrity | Isolate, restore immutable copy | Clean recovery point |
| Operator error | Audit/change event | Halt change, PITR/logical restore | Data loss window |
| KMS/IAM outage | Auth/key errors | Break-glass access, DR identity path | Dependency RTO |
| Control-plane outage | DCS/leader election alarms | Safe manual procedure | Failover safety |

## 16. Failure Mode Analysis

### 16.1. Primary Dies While Standby Lags

The standby can promote quickly but loses unreplicated commits. Compare potential RPO and pick the node with the latest LSN. If the primary's storage/WAL is still reachable, retrieve the WAL tail under a safe procedure before promotion.

### 16.2. Network Partition While Primary Is Alive

The standby may assume the primary died. If promotion proceeds without fencing the primary, split brain occurs. Health checks should combine multiple signals and fencing must operate independently of the partitioned network path.

### 16.3. Synchronous Standby Lost

The primary may stay connected while commits stall. Define an explicit fail-open/fail-closed policy. Relaxing sync mode improves availability at the expense of RPO; it must be monitored and audited.

### 16.4. Standby Loses Storage

The primary can continue serving. Rebuild the standby from backup or a fresh base backup; never treat a healthy primary as restored redundancy.

### 16.5. Primary and Standby Fail Together via Shared Dependency

For instance, disabling a single KMS key prevents both nodes from mounting encrypted volumes. Separating compute without separating key management leaves a common failure domain.

### 16.6. Bug or Faulty Migration Replicated

Standbys receive WAL for valid yet business-incorrect changes. PITR requires base backups and WAL archives to stop prior to the change; immutable backups protect when both primary and replicas are affected.

### 16.7. Backup Repository Deleted

Replication cannot recover deleted backups. Isolate accounts, IAM, retention locks, and auditing so an attacker or operator cannot erase all copies together.

### 16.8. DR Region Hits Quotas

A replica cannot scale or restore if Region B lacks instance or storage quota. Reserve capacity or test quota requests and scaling paths periodically.

### 16.9. DNS / Global Routing Fails to Update

The new database promoted, yet applications still call the old endpoint. Audit DNS TTLs, resolver caches, connection pools, proxy configs, and direct hostnames.

### 16.10. Restore Keys or Dependencies Unavailable

Database files exist, but extensions, KMS keys, or SSL secrets cannot be fetched in DR. Store encrypted copies, key recovery procedures, and a dependency inventory outside the primary failure domain.

## 17. Translating Business Requirements into Topology

### 17.1. Start with Workload and Business Impact

Before choosing node counts, gather:

- Data types and criticality;
- Which transactions cannot be lost;
- Maximum tolerable disruption;
- Peak hours and seasonality;
- Data and WAL volume;
- Application and third-party dependencies;
- Compliance and data residency requirements;
- Infrastructure budget and on-call staffing.

Never set RPO/RTO backward from whatever topology the engineering team already has.

### 17.2. Workload Classification

Examples:

| Workload | Criticality | Design Direction |
| --- | --- | --- |
| Ledger/payment | Very high | Synchronous HA, immutable backups, DR region |
| Order processing | High | Multi-AZ standby, WAL archive, PITR |
| Reporting | Medium | Async/read replica, lag tolerable |
| Analytics staging | Lower | Periodic backup, on-demand restore |
| Audit/legal records | Very high retention | Immutable/offsite backup and access controls |

A single cluster can host workloads with conflicting targets; when targets diverge, consider splitting clusters or separating data streams.

### 17.3. Failure Scenario Matrix

Build a table per failure mode:

| Scenario | Target RPO | Target RTO | Recovery Method | Owner |
| --- | --- | --- | --- | --- |
| Process crash | Near 0 | 1 minute | Restart/crash recovery | DBA/on-call |
| Host failure | 0–30 seconds | 5 minutes | Promote local standby | DBA/SRE |
| AZ outage | 0–1 minute | 10 minutes | Cross-AZ promotion | SRE |
| Region outage | 5 minutes | 2 hours | Cross-region DR | DR lead |
| Logical corruption | Before bad transaction | 4 hours | PITR + selective export | DBA/application |
| Ransomware | Latest clean copy | 8 hours | Immutable restore | Security/DR |

Targets must be approved by business owners and verified through drills.

### 17.4. Selecting Topology by Target

| Requirement | Suggested Topology | Accepted Limitations |
| --- | --- | --- |
| Few minutes RPO/RTO for host | Primary + async standby in same region | Risk of losing WAL tail |
| Very low RPO for host/AZ | Primary + synchronous standby in another AZ | Commit latency and write blocking when sync node is lost |
| DR region few minutes RPO | Async cross-region standby + WAL archive | Potential loss if region fails before WAL reaches DR |
| DR region near-0 RPO | Cross-region sync or tailored commit/quorum design | High WAN latency; partitions can stall writes |
| Protection from logical errors | Base backup + WAL archive + PITR | Restore testing and replay duration |
| Ransomware protection | Immutable/offline/cross-account backups | Cost, key management, restore time |

### 17.5. Do Not Optimize a Single Number

Optimizing RPO while ignoring availability can stall writes when WAN or synchronous standbys fail. Optimizing RTO with many replicas while ignoring backups lets logical errors hit every node. Optimizing availability while ignoring fencing invites split brain.

### 17.6. Business Impact Tiers

You can categorize into tiers:

- Tier 0: ledger/payment/core identity; lowest RPO/RTO and frequent DR testing;
- Tier 1: customer-facing transactional workloads;
- Tier 2: reporting and internal tools;
- Tier 3: batch, cache, rebuildable datasets.

Each tier carries different backup cadences, standby placements, alert responses, and budgets.

## 18. Reference Architecture Examples

### 18.1. Lab / Dev

Example target: 24-hour RPO, 1-day RTO.

Architecture:

- Single PostgreSQL primary;
- Daily base backup;
- WAL archiving if PITR is desired;
- Backups stored in object storage;
- Scheduled restore tests.

Automated multi-AZ failover is unnecessary if downtime is acceptable.

### 18.2. Internal Application

Example target: 5-minute RPO, 30-minute RTO.

Architecture:

- Primary + async standby on another host/AZ;
- Continuous WAL archiving;
- Periodic base backups;
- Health checks and manual/controlled failover;
- Stable application connection endpoint.

Monitor lag for actual RPO; RTO drills must include promotion and application reconnection.

### 18.3. Customer-Facing Transactional Service

Example target: 0–30 second RPO for host/AZ, under 5-minute RTO.

Architecture:

- Primary in AZ-a;
- Synchronous standby in AZ-b;
- Async standby in AZ-c or DR region;
- HA controller with quorum/fencing;
- Independent WAL archive;
- Immutable backups;
- Global endpoint/connection proxy;
- Automated drills and alerting.

If the synchronous standby becomes unavailable, policy must state whether to block writes or downgrade sync mode with approval.

### 18.4. Regional Disaster Recovery

Example target: 5-minute RPO, 2-hour RTO.

Architecture:

- Multi-AZ HA in the primary region;
- Async physical standby in the DR region;
- Cross-region WAL archiving;
- Base backups copied cross-account;
- Ready DR application infrastructure and secrets;
- Global DNS/traffic management;
- DR runbooks and annual/quarterly full-region drills.

### 18.5. Compliance / Archive Workload

Requirements: long retention, auditability, and clean copy recovery.

Architecture:

- Primary/standby for availability;
- Base backups + WAL archive;
- Immutable object retention;
- Separate account for deletion rights;
- Key recovery process;
- Periodic restore verification;
- Approved retention policy.

### 18.6. One Cluster or Multiple Clusters?

If payments and reporting share a cluster, reporting queries can degrade transaction latency, and a single failure or configuration change affects both. Consider separate clusters or read replicas/resource governance when business objectives differ.

## 19. Cost and Trade-Offs

### 19.1. Compute Cost

Continuously running standbys consume compute. A standby sized to absorb full production load costs nearly as much as the primary. A DR region may run smaller initially, provided scale-up time is accounted for.

### 19.2. Storage Cost

Each physical standby stores its own copy of the data. Base backups, incremental chains, WAL archives, and immutable copies increase storage spend. Long retention adds protection but requires backup-chain-aware lifecycle rules.

### 19.3. Network Cost

Cross-AZ and cross-region WAL streaming and backup transfers incur egress fees. Cross-region synchronous replication also increases commit latency due to RTT.

### 19.4. Operational Cost

Multi-region operations require:

- On-call coverage;
- DR exercises;
- Version/config synchronization;
- Secrets/key management;
- Failover/failback runbooks;
- Multi-region monitoring;
- Quota/capacity management;
- Incident coordination.

### 19.5. Complexity Budget

Every replica, controller, proxy, DCS, region, and backup tool introduces new failure modes. Add components only when they clearly reduce risk or achieve a concrete objective.

### 19.6. Managed PostgreSQL

Managed services may provide Multi-AZ, automated backups, cross-region replicas, and failover orchestration. Still, verify:

- RPO/RTO per failure scenario;
- Replication modes and acknowledgment semantics;
- Failover detection/fencing;
- Backup retention and restore times;
- Cross-region failover support;
- Limits/quotas and service maintenance behavior;
- Ability to export/restore outside the provider.

Never infer RPO 0 or a few minutes of RTO solely from a “Multi-AZ” label.

### 19.7. Self-Managed PostgreSQL

Self-managed deployments give deep control, but the team owns the controller, DCS, fencing, backups, patching, monitoring, restore tests, and incident response.

### 19.8. Decide Based on Total Cost of Ownership

Include expected outage cost, data loss impact, operational staffing, storage/network, and complexity. A cheaper topology can carry a far higher expected loss during an incident.

## 20. Testing HA and DR

### 20.1. Why Drill?

Untested runbooks often hide bad assumptions: expired credentials, stale DNS caches, missing extensions, WAL archive gaps, insufficient quotas, or a controller unable to fence the primary.

### 20.2. Testing Levels

1. Unit test scripts: verify commands, configs, and permissions;
2. Component tests: stop a standby, check monitoring and reattachment;
3. Failover drills: simulate primary host loss;
4. AZ drills: isolate an AZ or network path;
5. Region DR drills: restore/promote in another region;
6. PITR drills: recover to before a faulty transaction;
7. Ransomware/backup drills: restore from an immutable copy;
8. Full business continuity drills: validate applications, DNS, identity, and operations.

### 20.3. Do Not Start by Breaking Production

Run drills in staging or environments with controlled blast radii. If a production game day is approved, define strict scope, rollback, on-call coverage, customer impact controls, and stop conditions.

### 20.4. Test Process Restart

Verify PostgreSQL crash-recovers automatically, monitoring reports accurately, and applications reconnect. Measure downtime and ensure transaction retries do not create duplicates.

### 20.5. Test Standby Promotion

Simulate an unresponsive primary. Verify fencing, candidate selection, promotion, endpoint switching, application smoke tests, and redundancy restoration.

### 20.6. Test Network Partitions

Introduce controlled partitions across primary/standby/control plane. Confirm only one node can accept writes and the system does not falsely promote while the primary remains healthy.

### 20.7. Test WAL Archive Recovery

Restore a separate base backup, configure `restore_command`, and replay WAL to a target. Verify the archive holds all required segments/history and measure recovery duration.

### 20.8. Test Logical Error Recovery

In a lab, create a restore point, execute an accidental deletion, run PITR to a new cluster, and verify before/after data. Measure export/import time when recovering a single table.

### 20.9. Test Failback

After a failover drill, rebuild the old node as a standby via rewind or base backup. Wait for catch-up, run a controlled switchover, and verify no split brain occurred.

### 20.10. Record Results

For each drill, record:

- Scenario and failure domain;
- Target/observed RPO;
- Target/observed RTO;
- Candidate timeline/LSN;
- Detection/decision/fencing/promotion/cutover durations;
- Data/application validation outcomes;
- Manual steps and blockers;
- Follow-up owner and deadline.

### 20.11. Game Days After Major Changes

Re-run relevant tests after major upgrades, OS/extension updates, network redesigns, IAM/KMS changes, backup tool updates, topology changes, or storage migrations.

## 21. Failover Runbook for Primary Host Loss

### 21.1. Entry Criteria

Trigger the runbook only when the incident commander or HA controller confirms the primary can no longer serve and the failure scope is known. A single health-check timeout is not enough to promote.

### 21.2. Assess State

Gather:

- Primary process/host/network health;
- DCS/consensus leader state;
- Standby receive/flush/replay LSN;
- Synchronous standby status;
- WAL archive progress;
- Out-of-band access to fence the host;
- Application error rates and request queues.

### 21.3. Fencing

Fence the old primary prior to promotion using tested mechanisms. If isolation of the old primary cannot be verified, stop and follow escalation procedures. Never allow writes on two nodes simultaneously.

### 21.4. Candidate Selection

Select a standby with:

- Matching system identifier/cluster history;
- Valid timeline/WAL;
- Latest receive/flush/replay LSN;
- Compliance with agreed RPO;
- Adequate capacity for production load.

Document estimated data loss if asynchronous WAL has not been received.

### 21.5. Promote

Once fencing and candidate selection are confirmed:

~~~sql
SELECT pg_promote(wait => true);
~~~

Or trigger via the HA manager. Confirm the node exits recovery and accepts writes appropriately.

### 21.6. Switch Endpoints

Switch proxies/VIP/DNS/managed endpoints. Monitor connection pools, client retries, TLS, and application health. If clients still hit the old IP, remediate service discovery per the runbook.

### 21.7. Validation

Run smoke tests:

- Read critical records;
- Commit a controlled test transaction;
- Verify unique/foreign key constraints;
- Check sequences;
- Verify replication/archiving;
- Confirm application error rates.

### 21.8. Restore Redundancy

Rebuild a standby from the new primary via rewind if eligible or a fresh base backup. Never consider an incident closed while running on a single primary; redundancy must be restored and verified.

## 22. Disaster Recovery Runbook for Region Loss

### 22.1. Confirm DR Trigger

Activate DR when the primary region cannot recover within RTO or is confirmed lost. Document the decision-maker, timestamp, and outage scope.

### 22.2. Select Data Source

Prioritize candidates in pre-defined order:

- Healthy cross-region standby with the latest WAL;
- Base backup + WAL archive in the DR region;
- Immutable backup/offsite copy if replicas/archives are impacted.

Compare the recovery point to target RPO. If target RPO cannot be met, the incident commander must obtain business acceptance before cutover.

### 22.3. Fence the Old Region

If the old region might come back online, block write access via network/IAM/compute controls. Never rely solely on DNS TTL.

### 22.4. Restore Dependencies

Verify:

- Compute/storage quotas;
- Network routes/firewalls;
- IAM roles/KMS keys/secrets;
- TLS certificates/DNS;
- Application deployments/configs;
- Monitoring/alerting;
- Backup/WAL archive access.

### 22.5. Promote and Open Traffic

Promote the DR node after fencing. Switch global endpoints, reconnect clients, and run business validation. Enable WAL archiving and backups on the new timeline immediately after cutover.

### 22.6. Rebuild the Old Region

When the old region returns, keep the old primary isolated from write traffic. Use rewind or a base backup from the new primary to re-establish a standby. Execute failback later under a planned maintenance window.

## 23. Recovery Runbook When Replication Lag Exceeds RPO

### 23.1. Early Warning

When estimated lag hits the warning threshold:

1. Identify whether lag is at the send, write, flush, or replay stage;
2. Check network bandwidth and packet loss;
3. Check standby CPU and I/O;
4. Check for WAL generation bursts;
5. Check recovery conflicts and disk pressure;
6. Estimate catch-up time.

### 23.2. Deliberate Workload Reduction

If needed, throttle batch/bulk jobs or read workloads on the standby so WAL replay can catch up. Do not disable replication or drop slots without understanding the consequences.

### 23.3. Inspect Slots and WAL Retention

Inspect replication slots, retained WAL, and disk space. If a slot retains excessive WAL, fix the consumer/standby before changing slot policies. Dropping a slot can force a full standby rebuild via a new base backup.

### 23.4. Escalation

If lag breaches RPO:

- Notify business and on-call teams;
- Record potential data loss;
- Consider adding a replica or scaling capacity;
- Do not promote a lagging standby solely because it is the only node online if fresher WAL can still be recovered;
- Update RPO status in the incident channel.

### 23.5. After Catch-Up

Confirm lag drops steadily, archiving works, slot retention is healthy, and the root cause is resolved. Adjust capacity or alert thresholds if needed.

## 24. Multi-Failure-Domain Architecture Design Checklist

### 24.1. Business Objectives

- [ ] RPO defined separately for host, AZ, region, and logical corruption.
- [ ] RTO has defined start/end milestones and measured phases.
- [ ] SLO/SLI/availability windows agreed upon.
- [ ] MTPD exceeds RTO with margin for validation.
- [ ] RLO/degraded mode defined.
- [ ] Business owner accepts latency/data-loss trade-offs.

### 24.2. Failure Domains

- [ ] Primary/standby separated across hosts/racks/AZs.
- [ ] Storage replicas isolated per failure model.
- [ ] Control plane/DCS has appropriate quorum.
- [ ] Backups reside outside the primary failure domain.
- [ ] Account/IAM/KMS have DR access paths.
- [ ] DNS/network/load balancers have redundancy.
- [ ] Plan exists against common-mode software/human errors.

### 24.3. Replication and Failover

- [ ] Sync/async mode matches RPO.
- [ ] `synchronous_commit` and `synchronous_standby_names` well understood.
- [ ] Commit quorum and control-plane quorum distinguished.
- [ ] Failover candidate selection based on WAL position.
- [ ] Fencing tested.
- [ ] Split-brain scenarios drilled.
- [ ] Client retries/idempotency designed.
- [ ] Failback/standby rebuild runbooks ready.

### 24.4. Backup and DR

- [ ] Continuous base backups and WAL archiving.
- [ ] Immutable/offsite copies aligned with threat model.
- [ ] Backup retention covers the PITR window.
- [ ] Timeline history preserved.
- [ ] Keys/secrets have independent recovery procedures.
- [ ] Restore tests prove RPO/RTO.
- [ ] Logical backups available for selective recovery when needed.

### 24.5. Capacity and Monitoring

- [ ] Standby sized for peak production workload.
- [ ] WAL replay throughput matches or exceeds generation rate.
- [ ] Storage headroom covers WAL/backup/recovery.
- [ ] Connection storms controlled.
- [ ] Potential RPO monitored.
- [ ] RTO phase timestamps logged.
- [ ] Archive/slot/disk/replication alerts have owners and runbooks.
- [ ] DR region quotas/capacity verified.

### 24.6. Operations

- [ ] Runbooks have assigned owners and access rights.
- [ ] On-call staff can safely fence and promote.
- [ ] Manual failover practiced.
- [ ] AZ/region drills scheduled.
- [ ] Each drill logs observed RPO/RTO and follow-up actions.
- [ ] OS/DB/network/IAM changes trigger HA/DR review.

## 25. Practice Exercises: RPO, RTO, and Multi-Failure-Domain Architecture

Use a lab or simulated scenario for all exercises. Never perform fencing, partitioning, failovers, or destructive operations on production solely for practice. For version- or provider-specific settings, consult the exact documentation.

### Exercise 1 — Defining RPO

Explain RPO in business terms. Distinguish target RPO from observed RPO.

### Exercise 2 — Defining RTO

A system reports PostgreSQL restarted in 20 seconds, yet the application reconnected after 8 minutes. Up to which milestone should RTO be measured, and why?

### Exercise 3 — Calculating RPO from Lag

The primary failed at 10:00:00, and the standby had replayed data up to 09:59:42. Estimate RPO and list missing assumptions.

### Exercise 4 — RPO Is Not Backup Interval

Backups run every 5 minutes, but WAL archiving has been failing for 20 minutes. Why can you not claim a 5-minute RPO?

### Exercise 5 — RTO Decomposition

A failover took 12 minutes. Break it down into detection, decision, fencing, promotion, endpoint switching, and validation, and propose a metric for each step.

### Exercise 6 — Availability Calculation

Calculate maximum downtime over 30 days for 99.9% and 99.99% availability, assuming a 30-day month.

### Exercise 7 — MTPD

The business can tolerate at most 60 minutes of disruption. Why is a 60-minute RTO unsafe? Propose a safety buffer.

### Exercise 8 — RPO by Failure Scenario

A system has a sync standby in the same AZ and an async standby in another region. Define separate RPO targets for host, AZ, and region failures, and explain the trade-offs.

### Exercise 9 — Failure Domains

Two PostgreSQL VMs run on different hosts but share a single storage array. What failures can still take down both?

### Exercise 10 — Multi-AZ

Draw a topology with primary in AZ-a and standby in AZ-b. Include control plane, client endpoint, backups, and WAL archiving.

### Exercise 11 — Multi-Region

Design an active-passive setup between Regions A and B. List the non-database dependencies needed in Region B.

### Exercise 12 — HA vs. DR

Distinguish HA and DR using two incident examples. Why don't backups automatically create HA?

### Exercise 13 — Sync Replication

Explain the differences between asynchronous and synchronous replication in terms of commit acknowledgment, latency, and potential data loss.

### Exercise 14 — `synchronous_commit`

Compare `remote_write`, `on`, and `remote_apply`. Which setting waits for the standby to replay WAL?

### Exercise 15 — `synchronous_standby_names`

Explain `FIRST 1` and `ANY 2`. Give a scenario where one standby is no longer enough to satisfy quorum.

### Exercise 16 — Sync Standby Outage

The primary is healthy, but the synchronous standby loses connectivity. What happens to commits? Propose fail-closed and fail-open policies.

### Exercise 17 — Cross-Region Sync

Why does synchronous replication across regions increase commit latency? How does a network partition affect availability?

### Exercise 18 — Replication Lag

Distinguish send, write, flush, and replay lag. Which metric is closest to durable WAL on the standby?

### Exercise 19 — RPO Monitoring

Write queries to inspect primary and standby LSNs. Explain why timelines must be checked when comparing them.

### Exercise 20 — Quorum

A consensus group has 5 voters. How many votes are needed for a majority quorum? How many voters can fail while maintaining quorum?

### Exercise 21 — Witness

Does a witness store PostgreSQL data? How does it help when there are only two data nodes?

### Exercise 22 — Fencing

List three ways to fence an old primary. Why is updating a DNS record alone insufficient?

### Exercise 23 — Split Brain

Two primaries accept writes simultaneously. Describe the consequences and explain why PostgreSQL physical replication cannot auto-merge histories.

### Exercise 24 — DCS Quorum vs. Sync Quorum

Distinguish DCS/leader-election quorum from synchronous replication quorum.

### Exercise 25 — Candidate Selection

Two standbys have different replay LSNs. How do you pick the promotion candidate to minimize data loss? What else besides LSN must be checked?

### Exercise 26 — Multi-AZ Failure

AZ-a appears lost, but the primary may still be alive via another network path. What procedure prevents standby promotion from causing split brain?

### Exercise 27 — Region Partition

Regions A and B lose connectivity while both stay operational. Why should B not auto-promote just because it cannot see A?

### Exercise 28 — Failback

After promoting Region B, why must Region A not be turned back on as primary? Describe rebuild/rewind and switchover.

### Exercise 29 — Backup vs. Replication

A DROP TABLE was replicated to the standby. What mechanism recovers the table, and why is the standby insufficient?

### Exercise 30 — PITR

Describe restoring a base backup + WAL archive to before an erroneous transaction. Why restore to a temporary cluster first?

### Exercise 31 — N+1 Capacity

The primary runs at 70% CPU at peak, while the standby has 4 vCPUs compared to the primary's 16 vCPUs. What risks arise upon promotion?

### Exercise 32 — WAL Replay

The primary generates 300 MB/s of WAL while the standby consistently replays 250 MB/s. How does lag evolve over time? Propose solutions.

### Exercise 33 — Catch-Up Time

A standby lags by 60 GB with 120 MB/s net replay throughput. Calculate the theoretical time and list factors that make real-world catch-up longer.

### Exercise 34 — Disk Capacity

A replication slot retains 500 GB of WAL while a standby is offline. What alerts and limits are needed to protect the primary's disk?

### Exercise 35 — Connection Storm

After failover, 3,000 application connections reconnect simultaneously. Design pool, retry, jitter, and capacity controls.

### Exercise 36 — Control Plane Failure

The DCS is placed in a single AZ and that AZ fails. Why might a multi-AZ database still fail to fail over automatically?

### Exercise 37 — DNS TTL

The new database is promoted, yet clients still connect to the old primary. List DNS/client-cache causes and endpoint solutions.

### Exercise 38 — IAM/KMS Dependency

Primary and standby sit in two AZs but share one KMS key that gets disabled. Why is this still a common failure domain?

### Exercise 39 — RPO 0

A system claims RPO 0. List the failure assumptions that must be stated for this claim to be meaningful.

### Exercise 40 — Few-Minute RTO

A 6 TB cluster takes 90 minutes to restore from object storage. To achieve a 5-minute RTO, how must the topology change?

### Exercise 41 — Multi-Region Active-Active

Why can two PostgreSQL physical primaries not write to the same replication history? List conflict and key allocation challenges if using logical active-active.

### Exercise 42 — Managed Database

A provider advertises Multi-AZ. Write 8 questions to ask to verify RPO/RTO, fencing, backups, and cross-region DR.

### Exercise 43 — Cost Trade-Offs

Compare compute, storage, network, and operational costs of one primary + one standby versus multi-AZ + multi-region + immutable backups.

### Exercise 44 — Failure Matrix

Create a table for process, host, AZ, region, logical corruption, and ransomware, filling in RPO, RTO, recovery method, and owner.

### Exercise 45 — Failover Drill

Design a drill simulating primary host loss, covering fencing, promotion, endpoint switching, application validation, and standby rebuild.

### Exercise 46 — Network Partition Drill

In a lab, simulate broken connectivity among primary, standby, and control plane. What pass criteria prove no split brain occurred?

### Exercise 47 — DR Drill

Design a regional failover and failback test. Measure step durations and observed RPO.

### Exercise 48 — Logical Corruption Drill

Run an accidental delete transaction in a lab, perform PITR to before the transaction, and re-export the data. Record RTO.

### Exercise 49 — Monitoring Design

Design a dashboard displaying roles, LSN gaps, sync state, WAL archive status, potential RPO, disk headroom, and RTO history.

### Exercise 50 — Capstone: Multi-Failure-Domain PostgreSQL Architecture

A payment processing system has 2 TB of data, 5,000 transactions/second at peak, RPO under 30 seconds on AZ loss, 5-minute RTO on host loss, and 5-minute RPO / 2-hour RTO on region loss. The application runs across three AZs with a KMS service and object storage backups.

**Requirements:**

1. Choose primary/standby topology and assign sync/async modes.
2. Propose node and DCS voter placement to survive AZ failures.
3. Define fencing mechanisms and candidate promotion policies.
4. Design async cross-region DR and WAL archiving.
5. Calculate capacity headroom for peak load and failover.
6. Specify backup retention, immutable copies, and key recovery.
7. Design endpoint routing, connection pooling, and idempotent retries.
8. Build a failure matrix for host/AZ/region/logical/ransomware.
9. Design monitoring for potential RPO and RTO phases.
10. Write failover, failback, PITR, and full-region DR runbooks.
11. Create a drill schedule and acceptance criteria.
12. Analyze cost/latency/availability trade-offs and obtain business sign-off.

**Passing criteria:** every failure scenario has explicit RPO/RTO, the topology provides sufficient failure isolation, promotion cannot cause split brain, backups/PITR protect against logical errors, and results are proven through drills.

## 26. Frequently Asked Questions

### 26.1. Does RPO 0 mean data is never lost?

No. RPO 0 is meaningful only within stated failure assumptions, typically for commits acknowledged via synchronous replication. It does not protect against logical deletions, replicated corruption, simultaneous loss of all failure domains, or non-compliant storage flushes.

### 26.2. Is RTO equal to PostgreSQL startup time?

No. RTO is typically measured until the service/application meets operational requirements. It must include detection, decision, fencing, promotion/restore, endpoint cutover, and validation.

### 26.3. Does synchronous replication keep the primary always available?

No. It increases durability of acknowledged commits, but can block writes when synchronous standbys are unavailable. Availability and commit latency must be balanced by policy.

### 26.4. Does asynchronous replication always lose data on failover?

No. If the standby already received and flushed all necessary WAL before the primary failed, data loss can be zero. However, the mechanism cannot guarantee that across all failure timings.

### 26.5. Does Multi-AZ protect against region loss?

Not fully. Multi-AZ protects against certain intra-region failures. Cross-region DR and independent backups are needed for region-wide failures.

### 26.6. Does multi-region automatically mean HA?

No. You still need replication, fencing, leader election, endpoint cutover, dependencies, and runbooks. A lone replica in another region does not constitute safe failover.

### 26.7. Are two PostgreSQL nodes enough to prevent split brain?

Not automatically. During a network partition, each node may think the other is dead. Quorum/witnesses or reliable fencing mechanisms are required.

### 26.8. Can a witness replace a standby?

No. A witness assists leadership decisions but holds no database data or WAL to serve applications.

### 26.9. How many failures can a 3-voter quorum tolerate?

Majority quorum is 2/3, so decisions can continue with one voter down if placement and protocols are sound. Losing two voters breaks quorum.

### 26.10. Does DCS quorum guarantee the most up-to-date standby?

No. It governs leadership. Candidate selection by WAL position and synchronous replication guarantees are still needed.

### 26.11. Should we replicate synchronously across regions?

Only when the business requires very low RPO and accepts WAN commit latency plus write blocking during partitions. Many systems use intra-region sync and cross-region async.

### 26.12. Is `remote_write` as durable as `on`?

No. `remote_write` waits for WAL to be written to the standby OS; `on` waits for durable flush per PostgreSQL semantics. Understand your platform's storage flush behavior.

### 26.13. Is `remote_apply` required for every application?

No. It helps when read-after-write on a standby is required. It increases latency and does not ensure external systems or caches have updated.

### 26.14. Can a standby accept writes?

A physical standby in recovery mode is read-only. After promotion, the node becomes primary and can accept writes.

### 26.15. Does streaming replication replace WAL archiving?

No. Streaming serves live standbys; WAL archiving enables PITR, recovery after standby loss, and long-term recovery scenarios.

### 26.16. Do backups replace standbys?

No. Restoring a backup is generally slower than promoting a standby. Backups protect long-term data and guard against logical errors; standbys provide HA.

### 26.17. Does replication protect against DROP TABLE?

No. WAL for the DROP operation is replicated. Use PITR or logical backup/restore to recover the data.

### 26.18. Should we automatically promote a standby if lag exceeds RPO?

No, not blindly. Evaluate whether fresher WAL tails can still be retrieved from the primary, pick the node with the latest LSN, and inform the business of potential data loss.

### 26.19. Can failover be fully automated?

It can be automated in certain topologies, provided fencing, quorum, candidate selection, and network partition tests are in place. Ambiguous situations should require manual escalation.

### 26.20. Is updating DNS considered fencing?

No. DNS does not stop clients from connecting directly to the old primary. Fencing must prevent the old node from accepting writes.

### 26.21. Why do clients need idempotency?

If a connection breaks during COMMIT, the client cannot tell whether the transaction succeeded. Idempotency keys or unique constraints make retries safe without creating duplicate business actions.

### 26.22. Can a standby be smaller than the primary?

Possibly for light workloads, though after promotion it may collapse under peak load. Measure replay and production throughput and reserve appropriate headroom.

### 26.23. Is one standby enough for DR?

It mitigates some failures, but does not protect against logical corruption, ransomware, or loss of an entire region/account. Independent backups and WAL archives are required.

### 26.24. Is RPO measured by timestamp or LSN?

The business expresses it in time; engineering should monitor LSN/commit state alongside timestamps. Replay timestamps can appear stale during idle periods and are insufficient alone.

### 26.25. Up to what point should RTO be measured?

Up to the agreed business/service milestone, typically the first successful application request or full service restoration. Track post-cutover stabilization/cleanup separately if outside RTO.

### 26.26. Does Multi-AZ provide 100% availability?

No. Common-mode failures, control-plane outages, bugs, operator errors, dependency outages, and failover mistakes can still occur.

### 26.27. Does a cross-region standby need full compute capacity?

It needs sufficient capacity or a tested scale-up plan. Waiting too long for quotas or instance provisioning will breach RTO.

### 26.28. How do we prove RPO/RTO?

Monitor replication/archive lag and run timestamped drills. Document observed recovery points, phase durations, application validation, and blockers.

### 26.29. How often should DR drills run?

According to criticality and policy; mission-critical systems typically require frequent component/failover drills and periodic full-region drills. Re-test after major changes.

### 26.30. What is the best architecture?

The right architecture is one that meets RPO/RTO per failure scenario, provides proper failure isolation, and can be operated and tested within budget. No single topology is optimal for every workload.

## 27. Official PostgreSQL Documentation

The following links point to current PostgreSQL documentation. Select your exact major version and verify synchronous replication, recovery, and view semantics before deployment:

- [High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/current/high-availability.html): overview of HA, replication, and failover.
- [Warm Standby Servers](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication and standby operation.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): synchronous standbys and acknowledgment behavior.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): `synchronous_standby_names`, `synchronous_commit`, slots, and WAL senders.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): durability and WAL settings.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archives, and PITR.
- [Recovery Configuration](https://www.postgresql.org/docs/current/recovery-config.html): restore commands, recovery signals, and targets.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): replication, archiver, and statistics views.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating physical base backups and standbys.
- [pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html): verifying backup manifests.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): resynchronizing nodes after failover.
- [pg_checksums](https://www.postgresql.org/docs/current/app-pgchecksums.html): verifying data page checksums offline.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): major version upgrades.

## 28. Summary

RPO and RTO must start from business impact, be specified per failure scenario, and be verified through monitoring and drills. Multi-AZ and multi-region topologies are only effective when nodes, storage, networking, control plane, identity, backups, and operations are properly isolated across failure domains.

| Component | Role |
| --- | --- |
| RPO | Limit on acceptable data loss |
| RTO | Limit on service recovery time |
| Synchronous replication | Reduces data loss for acknowledged commits under failure assumptions |
| Asynchronous replication | Lower commit latency, may have unreplicated WAL tail |
| Quorum/fencing | Selects the right primary and prevents split brain |
| Multi-AZ | Tolerates loss of an infrastructure zone within a region |
| Multi-region DR | Recovers when the primary region suffers a disaster |
| Base backup + WAL archive | Enables PITR and recovery when replicas are insufficient |
| Immutable/offsite backups | Protects against logical errors, ransomware, and copy deletion |
| Restore/failover drills | Proves real-world RPO/RTO |

A sound architecture does not merely maintain multiple copies. It must know which copy is authorized to write, which copy holds the latest data, how to stop an old primary from continuing to operate, and how to recover when both replication and primary infrastructure are affected.

**Design by failure scenario, measure with real RPO/RTO, and test both failover and failback.** HA keeps the service running through component failures; DR recovers from major disasters; backup/PITR protects data against logical errors and incidents affecting all replicas.
