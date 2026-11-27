# Choosing Active-Active or Active-Passive Based on Service Requirements

When a server, availability zone (AZ), or region experiences an outage, a service must keep handling requests within acceptable disruption and data-loss limits. Two common models are **active-active** and **active-passive**. In active-active, multiple sites or resource groups serve traffic concurrently. In active-passive, one site serves primary traffic while another remains on standby and takes over only when needed.

Neither model is universally better. Active-active can reduce traffic switchover time and utilize standby resources, yet demands more complex data design, state synchronization, and conflict resolution. Active-passive is often easier for maintaining a single primary write source and simplifying data consistency, yet requires reliable failover procedures and can leave standby resources idle.

The choice must start from **RTO**, **RPO**, target failure scope, workload type, data synchronization capabilities, cost, and operational capacity. This lesson shows how to evaluate both models for applications on VMs, containers, and cloud services, and highlights what must be tested before going to production.

## 1. High Availability and Fault Tolerance

**High availability (HA)** is the ability to keep a service operating with minimal disruption when one or more components fail. HA is commonly achieved through redundancy, health checks, failover, failure domain dispersion, and automatic recovery.

**Fault tolerance** is the ability to continue operating when a component fails, typically with very little or zero disruption within a defined failure scope. Higher fault tolerance generally requires deeper design across compute, network, storage, data, and application layers.

These terms should not be treated as absolute guarantees. An HA system can still experience outages when faults exceed design assumptions, when a shared dependency fails, or when failover fails.

### Redundancy Is Not Synonymous with Availability

Having an extra VM or an extra region is not enough to prove a service has HA. You must verify:

- Do backup resources reside in an independent failure domain?
- Does the standby have enough CPU, RAM, network, and storage to absorb the load?
- Is required data present and sufficiently up to date?
- Can traffic be shifted to healthy locations?
- Do identities, secrets, certificates, and access permissions work in the standby site?
- Does the application start and serve properly after failover?
- Can the operations team detect, decide, and recover within target timelines?

A standby placed on the same host, rack, or AZ as the primary can be lost in the same incident. An HA design must explicitly state which failure domains the system must survive.

## 2. RTO and RPO: Business Requirements Before Choosing a Model

The two most important metrics when designing HA and disaster recovery (DR) are RTO and RPO.

- **Recovery Time Objective (RTO):** the maximum outage duration the organization accepts before the service must be restored.
- **Recovery Point Objective (RPO):** the maximum amount of data that may be lost, typically expressed as a time window of data prior to the outage.

For example, a service sets an RTO of 10 minutes and an RPO of 1 minute. When an outage occurs, the organization expects service restoration within 10 minutes at most and accepts losing no more than roughly one minute of data according to an agreed definition and measurement method.

### RTO Is Not Just Machine Boot Time

Actual RTO can include:

1. Detecting the fault.
2. Confirming whether the fault is a genuine incident.
3. Making the failover decision.
4. Fencing or isolating the old primary if required.
5. Promoting database or storage replicas.
6. Starting/scaling the application.
7. Updating routes, load balancers, or DNS.
8. Running readiness checks and smoke tests.
9. Re-admitting traffic.
10. Confirming normal business operations.

A VM may boot in two minutes while the service remains down because the database is not yet promoted, secrets are missing, routes have not updated, or caches have not warmed up.

### RPO Depends on Data Replication

- **Synchronous replication:** writes are typically acknowledged only after data is saved to replicas meeting synchronization rules. Can achieve near-zero or zero RPO within the system's guaranteed scope, at the cost of higher latency and dependence on inter-site connectivity.
- **Asynchronous replication:** the primary acknowledges writes before replicas receive all data. Offers more flexibility in performance and geographic distance, yet un-replicated transactions may be lost if the primary fails.
- **Periodic backup/snapshot:** data is captured on a schedule. RPO can equal the interval between backups, plus operational factors.

Do not infer RPO solely from the label active-active or active-passive. An active-active system using asynchronous replication can still lose committed data from another site in certain failures. An active-passive system using synchronous replication can achieve a very low RPO while failover still takes time.

### RTO/RPO Must Be Measured Through Drills

RTO and RPO are merely targets until verified. Measure the elapsed time from fault injection until transactions succeed again, and reconcile data before/after to determine actual loss or duplication.

## 3. The Active-Active Model

Active-active runs at least two sites, zones, or resource groups serving traffic simultaneously. Traffic can be distributed by weight, geography, latency, hashing, or load-balancing algorithms.

### General Architecture

~~~mermaid
flowchart TB
    C["Clients"] --> G["Global traffic manager"]
    G --> A["Site A - active"]
    G --> B["Site B - active"]
    A --> ALB["Local load balancer A"]
    B --> BLB["Local load balancer B"]
    ALB --> A1["App replicas A"]
    BLB --> B1["App replicas B"]
    A1 --> D["Data layer / replication"]
    B1 --> D
~~~

Both Site A and Site B accept requests. The data layer may be a distributed database, multi-primary, partitioned data, or a coordinated write model. Never assume two sites can write all data into two independent databases and merge automatically.

### Advantages

- Both sites contribute capacity during normal operation.
- Traffic can shift quickly to the surviving site when one site fails.
- Redundant resources are actively exercised, avoiding completely idle standbys.
- Traffic can be served closer to users to reduce latency.
- One site can undergo maintenance while the other continues serving, given enough capacity.

### Cost and Complexity

- Requires data synchronization or partitioning.
- Requires handling write conflicts and consistency.
- Must avoid two sites taking traffic while a shared dependency can handle only one site's load.
- Requires designing shared or synchronized identity, sessions, caches, and queues.
- Requires split-brain controls during network partitions.
- Requires testing traffic shifting, failover, and failback.
- Requires monitoring replication lag and per-site health.

### Active-Active at One Layer Does Not Mean Full-Stack Active-Active

An application can run active-active across two AZs while its database uses a single primary with a standby. This is a common and often sensible pattern. Likewise, a load balancer can spread traffic across many web servers while underlying file storage or queues retain a single primary write region.

When describing an architecture, specify which layers are active-active: frontend, application, database, storage, message broker, or the entire stack.

## 4. The Active-Passive Model

Active-passive has one primary site or resource group serving traffic. The other site stays in standby, kept ready to take over when the primary stops responding.

### General Architecture

~~~mermaid
flowchart TB
    C["Clients"] --> G["Traffic manager"]
    G --> P["Primary site - active"]
    G -. "Failover when primary fails" .-> S["Secondary site - passive"]
    P --> PA["Application + primary data"]
    S --> SA["Standby application + replicated data"]
    PA -->|Replication| SA
~~~

Under normal operation, traffic flows primarily to the primary. The secondary receives data replicas and may run a subset of required components, yet does not serve regular production traffic for the primary workload.

When the primary fails, procedures isolate or fence the primary if needed, promote data on the secondary, start or scale the application, and switch traffic.

### Standby Tiers

| Standby Type | Resource State | Relative Recovery Time | Relative Cost |
|---|---|---|---|
| Cold standby | Keeps only backups/images/configs; machines must be provisioned on incident | Longer | Lower |
| Warm standby | Subset of resources running, data replicated; requires scaling or finishing setup | Medium | Medium |
| Hot standby | Resources and apps nearly ready, data updated continuously | Shorter | Higher |

Labels like cold/warm/hot are not always defined identically across providers. Document the exact state: whether VMs are booted, whether apps are running, whether database replicas are ready for promotion, whether routes are pre-configured, and whether secrets are accessible.

### Advantages

- Maintains a single primary write source, reducing multi-writer complexity.
- Easy to determine where normal traffic is served.
- Can lower compute cost if the standby does not need full capacity running.
- Data consistency procedures are typically simpler than active-active.
- Fits workloads with an RTO of several minutes or longer and an RPO supported by replication.

### Limitations

- The standby may lack capacity if untested.
- Failover can take time to promote data, scale apps, and update routes.
- Because the standby is rarely exercised, configuration drift can go unnoticed.
- Upon failover, full load shifts to one site, requiring spare capacity.
- Failing back to the old primary can be complex once data changes on the secondary.

## 5. Comparing Active-Active and Active-Passive

| Criterion | Active-Active | Active-Passive |
|---|---|---|
| Normal traffic | Multiple sites serve concurrently | Primarily one site serves |
| Resource utilization | Both sites contribute capacity | Standby may sit idle or partially running |
| Traffic failover | Shift weight to surviving site | Switch roles and traffic to standby |
| Data architecture | Requires partitioning, multi-writer, or coordinated writes | Usually easier to maintain single-writer |
| Write conflicts | Can occur in multi-primary setups | Lower if fencing and promotion are sound |
| RTO | Can be low if data and routing are ready | Depends on promotion, scaling, and traffic switch time |
| RPO | Depends on replication/consistency | Depends on replication/backups |
| Compute cost | Higher baseline, though resources are used | Low to high depending on cold/warm/hot |
| Operations | Complex consistency and traffic management | Complex failover/failback and standby drift |
| Best fit | Global services, high load, continuous availability, distributed data capability | Systems needing DR, single-writer workloads, RTO/RPO permitting role switchover |

Do not choose active-active solely to chase a low RTO. If the database cannot handle multi-writer concurrency and lacks a partitioning design, full-stack active-active can introduce more risk than benefit.

## 6. Choosing by RTO, RPO, and Service Criticality

Start by classifying services by business impact.

| Requirement | Candidate Design | Must Verify |
|---|---|---|
| Very low RTO, near-zero RPO | Active-active or hot standby with appropriate synchronous replication | Replication latency, fencing, capacity on site loss |
| RTO of a few minutes, RPO of seconds/minutes | Warm/hot active-passive or tiered active-active | Replication lag, promotion time, routing |
| RTO of tens of minutes, RPO matching backup interval | Cold/warm standby and backup/restore | Machine provisioning time, restore, DNS, and data checks |
| Read-heavy service, regionally partitioned data | Active-active may fit | Read/write routing, consistency, and failover |
| Single-writer workload, critical transactions | Active-passive is usually simpler | Synchronous/asynchronous replication, fencing, and recovery |
| Replayable batch workloads | Active-passive or queue-based worker groups | Idempotency, checkpoints, and duplicate handling |

### Classification Examples

- A catalog lookup API can serve reads from multiple regions while routing data updates to a single writer.
- A payment service may favor a single-writer database and hot standby to prevent transaction conflicts.
- An image-processing worker can run active-active across many nodes because jobs reside in a durable queue and are designed to be idempotent.
- An internal reporting system may use warm standby if several minutes of downtime are acceptable.

Each service needs its own SLO and recovery targets. Do not force a single HA pattern onto every component.

## 7. Designing Traffic Routing and Health Checks

### Global Traffic Manager

A traffic manager may use DNS-based routing, a global load balancer, anycast, or a cloud platform's traffic routing service.

Common strategies:
- Active-active splitting traffic by weight.
- Geo routing directing users to nearby regions.
- Latency-based routing choosing endpoints with favorable latency.
- Weighted routing enabling canaries or load balancing.
- Failover routing shifting traffic when an endpoint is unhealthy.
- Anycast directing connections to the nearest point on supported networks.

### Health Checks Must Reflect Serving Capability

A health check that only verifies a process is alive may miss a failed database or dependency. Conversely, overly deep checks on every probe can generate heavy load or mark an entire site unhealthy due to one temporarily slow dependency.

Separate checks into:
- **Liveness:** is the process still running or does it need a restart?
- **Readiness:** can the instance accept new traffic?
- **Dependency health:** are databases, queues, or dependent services responding?
- **Site health:** does the site have sufficient capacity and valid data state to keep serving?

Health checks need well-tuned timeouts, thresholds, intervals, and hysteresis. Avoid flapping when state oscillates near a threshold.

### DNS and Traffic Switchover Time

DNS failover depends on TTLs, resolver caches, and clients. A low TTL does not guarantee every client switches endpoints immediately; some resolvers cache longer or applications hold open connections.

A global load balancer can shift traffic faster in some architectures, yet must still account for open connections, sessions, health detection, and control-plane availability.

### Connection Draining

When pulling a site or instance out of traffic:
1. Stop accepting new connections/requests.
2. Let in-flight requests complete within a bounded timeout.
3. Close or migrate long-lived connections according to protocol.
4. Stop workers or consumers.
5. Terminate only after draining completes or the deadline expires.

WebSockets, gRPC streams, and long-lived TCP connections can persist for a long time. Client-side reconnect and retry policies are essential.

## 8. Application State: Sessions, Caches, Files, and Queues

Active-active or active-passive only works correctly when the application knows where every piece of state lives.

### Stateless Application

Stateless applications do not depend on session data held solely in one instance's RAM. Sessions can be stored in a shared store, signed tokens, or another mechanism so follow-up requests can land on any instance.

Statelessness simplifies scaling and failover, though a shared session store remains a dependency needing HA.

### Cache

Local caches at each site can diverge. When traffic shifts sites, cold caches raise latency and can trigger load spikes on the database.

Consider:
- Can the cache be regenerated from the source of truth?
- Cache invalidation and TTLs.
- Pre-warming before admitting traffic.
- Stampede protection.
- Bounding database load when cache misses spike.

Replicating the entire cache is unnecessary if it can be safely regenerated.

### Files and Object Storage

Files stored on a VM's local disk will not exist at another site. Use shared file storage, object storage, or appropriate replication/backup mechanisms.

For object storage, inspect versioning, replication lag, retention, and access permissions in the standby region. Never assume an object is immediately replicated upon upload if the service uses asynchronous replication.

### Queues and Background Jobs

Durable queues allow workers across multiple sites to pull tasks. However, manage:
- Consumer groups and partition ownership.
- Visibility timeouts or acknowledgements.
- Redelivery when a worker dies.
- Duplicate deliveries.
- Ordering requirements.
- Checkpoints and retry policies.

Design jobs to be idempotent so redelivering a task does not create duplicate business side effects.

## 9. Data Replication and Consistency

The data layer usually determines the true difficulty of active-active.

### Single-Writer Replication

One primary database accepts writes while replicas receive copies. In active-passive, a replica can be promoted when the primary fails. In an active-active app architecture, both sites may read from replicas or route writes to the single writer.

The advantage is avoiding concurrent multi-primary writes. The trade-off is that write routing and database failover must work accurately; replicas may carry replication lag if asynchronous.

### Multi-Primary Replication

Multiple sites can accept writes. This requires resolving cases where the same record is modified in multiple locations or a network partition prevents sites from communicating.

Approaches include:
- Partitioning data by tenant, user, or geography so each key has a clear writer.
- Business-rule conflict resolution.
- Version vectors or metadata versioning.
- Last-write-wins where appropriate, with clear awareness of its risks.
- CRDTs for data structures and operations that merge cleanly under supported models.
- Distributed transactions or consensus when strong consistency is mandatory and cost/latency are acceptable.

Last-write-wins is unsuitable for many transactions. If two financial updates write to the same balance concurrently, picking the newer timestamp can silently drop a valid transaction. Merge rules must reflect business semantics.

### Synchronous vs. Asynchronous Replication

| Property | Synchronous | Asynchronous |
|---|---|---|
| Write acknowledgement | Waits for synchronization criteria per implementation | Primary may acknowledge before replicas receive data |
| RPO | Can approach 0 within guaranteed scope | Un-replicated data may be lost |
| Latency | Higher due to network/replica waits | Typically lower for the primary |
| Partition behavior | May block or reject writes depending on consistency policy | Can keep accepting writes, raising divergence risk |
| Best fit | Transactions needing high durability and consistency | Workloads tolerating replication lag and non-zero RPO |

Synchronous replication across large geographic distances can add substantial latency. Some systems use quorum or synchronous replication within a region paired with asynchronous replication to a DR region. Understand exact commit acknowledgements and durability guarantees.

### Replication Lag

Monitor:
- Time delay between primary and replica.
- Unapplied transactions/log entries.
- Replication log positions.
- Log generation vs. apply rates.
- Replication connection health.
- Replication queue depth.

Failing over before a replica catches up can breach RPO targets. Consider blocking promotion or requiring explicit risk sign-off if lag exceeds thresholds.

## 10. Split-Brain, Quorum, and Fencing

**Split-brain** occurs when two nodes or two sites both believe they are primary and accept writes simultaneously, creating two diverging data histories.

### Why Does Split-Brain Happen?

- A network partition severs communication between primary and standby.
- Health checks falsely conclude the primary is dead.
- Control planes or failover controllers disagree on state.
- The standby is promoted while the old primary keeps running.
- An operator runs manual failover while automation is also acting.

### Quorum

Some systems use quorum to require majority agreement before changing state or electing a leader. With 3 voting members, quorum typically requires 2 members.

Quorum prevents both sides of a network partition from achieving a majority within the same membership configuration, yet must be deployed across proper failure domains. If all voting members sit in one AZ, losing that AZ breaks cluster quorum.

A witness can be placed in a third failure domain to aid decisions, though a witness neither replaces data nor provides serving capacity.

### Fencing

Fencing prevents an old node from continuing to write after primary authority moves to a new node.

Mechanisms include:
- Stopping or isolating the old VM via the control plane.
- Revoking storage access permissions.
- Leases with monotonically increasing epochs/generations.
- Fencing tokens validated by storage or the database.
- STONITH in physical/VM management clusters.

Merely changing DNS or load balancers is insufficient to fence a database writer. Old clients or direct connections can still write if the old primary retains permissions.

### Safe Failover

A typical sequence:
1. Detect an unresponsive primary.
2. Verify quorum and failure domain state.
3. Fence the old primary or prove it cannot write.
4. Identify a replica eligible for promotion.
5. Promote a single new writer.
6. Update service discovery/connection endpoints.
7. Admit traffic gradually.
8. Verify consistency and transactions.
9. Keep the old primary isolated until a resync plan is executed.

Automated failover must be engineered with the same rigor as data replication. Triggering failover too quickly on weak health signals can cause split-brain.

## 11. Multi-AZ vs. Multi-Region HA

### Multi-AZ

Multi-AZ distributes compute and dependencies across multiple Availability Zones within the same region. The typical goal is surviving a datacenter or AZ failure.

Advantages:
- Inter-AZ latency is usually lower than cross-region latency.
- Synchronous replication is feasible in several services.
- Intra-region traffic and control plane operations are generally simpler.

Verify:
- Are VMs/instances actually distributed across AZs?
- Does the load balancer route traffic to healthy AZs?
- Does the database have replicas in other AZs?
- Is storage zone-scoped or regional-scoped?
- Subnets, IPs, quotas, and capacity in every AZ.

### Multi-Region

Multi-region distributes services across geographically separated regions, reducing risk from broad regional outages and serving users closer to their locations.

Trade-offs:
- Higher network latency.
- Asynchronous replication may yield a larger RPO.
- Data residency and compliance become more complex.
- DNS/global routing and failover must be tested.
- Secrets, certificates, key management, and IAM must be ready in the standby region.
- Higher egress, replication, and resource costs.

### AZ Failover Does Not Replace Region DR

A regional incident can impact multiple AZs simultaneously. If surviving a region loss is required, you need a multi-region design or restore procedures to another region. Multi-AZ addresses a smaller failure domain and does not automatically guarantee DR.

## 12. Capacity During Failover

An HA model needs sufficient capacity in failure states, not just normal states.

### Active-Active

If two sites each serve 50% of traffic and one fails, the surviving site must absorb the shifted traffic. If each site is sized for only 50%, failover causes overload.

Options:
- Size each site to handle 100% of required load.
- Size each site to handle critical-tier load while shedding secondary features.
- Combine fast autoscaling with warm capacity.
- Implement load shedding to prioritize essential requests.

### Active-Passive

The standby needs enough capacity to absorb load within RTO. If the standby holds only 20% of primary compute, it may fail to meet throughput targets after failover.

Warm standby with fewer instances plus fast scaling can work, provided scale-out time and quota limits are measured. Never assume capacity will always be available on demand while a region is experiencing an incident.

### N-1 Failover Capacity

To tolerate losing one site out of N sites, calculate remaining capacity after losing the largest site. For instance, with two equal-capacity sites where either must carry the full load if the other fails, normal total capacity must hold two sites, each sized for 100% of target load. With three sites, size according to traffic distribution and specific failure scenarios.

Account for:
- CPU/RAM and instance quotas.
- Database connections and query capacity.
- Storage IOPS/throughput.
- Network egress and NAT.
- Load balancer capacity.
- API rate limits and licenses.
- Cache warm-up and replication apply rates.

## 13. Protecting Dependencies and Eliminating Single Points of Failure

Application-tier HA means little if a shared dependency remains a single point of failure.

Components to audit:
- DNS and service discovery.
- Global/local load balancers.
- Databases and connection proxies.
- Message brokers.
- Caches/session stores.
- Object/file storage.
- Secret managers and key services.
- Identity providers.
- NAT gateways, firewalls, and network routes.
- CI/CD, image registries, and bootstrap repositories.
- Monitoring, alerting, and control planes.

Not every dependency needs active-active. Managed multi-AZ services, replicated endpoints, backup/restore, or manual procedures aligned to RTO may suffice. What matters is that every dependency meets the service's availability goals.

### Control Plane vs. Data Plane

The control plane manages configuration, provisioning, and routing; the data plane handles live traffic. A system may continue serving traffic during a brief control-plane outage, yet cannot scale or update routes. Conversely, a healthy control plane does not guarantee the data plane is working.

The design must clarify:
- Does failover depend on control-plane APIs being available?
- Are routes pre-provisioned or created dynamically?
- Are secrets and images already present in the standby?
- Do DNS/global routing share any common dependency?
- Can recovery actions still execute if a managed service is degraded?

## 14. Sessions, Transactions, and Idempotency During Failover

When traffic shifts between sites, requests may be retried due to client timeouts or reset connections. A transaction may have committed on the primary while the response never reached the client. Client retries can create duplicate transactions if the application lacks idempotency.

### Idempotency Keys

For order creation, payment, or write operations, clients can pass a unique idempotency key. The server stores the processing outcome under that key and returns the saved result if retried.

Store idempotency records in a data store with appropriate consistency and retain them long enough for the retry window. If each site stores idempotency keys locally without replication, active-active can process duplicates when a retry hits the other site.

### Exactly-Once Is a Hard Target

Queues and distributed systems typically provide at-least-once or at-most-once semantics depending on configuration. Business-level exactly-once usually requires idempotency, transaction boundaries, and deduplication. Never claim a system is exactly-once merely because a broker advertises a toggle with that name.

### Sessions and Long-Lived Connections

In-memory sessions on a single instance can vanish during failover. Use a shared session store, stateless tokens, or session recovery mechanisms.

WebSockets, gRPC streams, and long-lived TCP connections often reset when sites or routes change. Clients must reconnect with backoff to avoid creating a connection storm.

## 15. Failback: Returning to the Primary Site

Failover shifts service to a backup site. Failback returns service to the original site or topology once the incident is resolved.

Failback must never be just flipping routes back to the old primary. While the secondary served traffic, data changed. The old primary may be stale and must not immediately resume writing.

### Safe Failback Procedure

1. Confirm the root cause on the primary has been resolved.
2. Keep the old primary blocked from accepting writes.
3. Synchronize data from the active site back to the old primary.
4. Check replication lag and consistency.
5. Verify capacity, versions, and configurations.
6. Switch writer ownership using a fenced procedure.
7. Shift traffic gradually or per plan.
8. Monitor errors, latency, replication, and transactions.
9. Retain the ability to revert to the current site if issues arise.
10. Complete failback after confirming data and SLO stability.

In active-active, failback may mean recovering one site and restoring its original traffic weight. Warm caches, verify replication, and ramp traffic gradually.

## 16. Backups, HA, and Disaster Recovery Do Not Replace One Another

- **HA:** maintains service when a component or failure domain fails.
- **DR:** restores service after a major disaster such as a region loss or widespread corruption.
- **Backup:** a data copy usable to restore a prior state.

Replication can propagate accidental deletions, ransomware encryption, or logic bugs. Independent, immutable, or retention-protected backups allow restoring to a point before the incident.

A sound architecture typically combines:
- Multi-AZ HA for common infrastructure faults.
- Multi-region DR for regional outages when required.
- Backups and restore testing for data corruption or human error.
- Runbooks and drills to prove RTO/RPO.

## 17. Example: Choosing Models for Two Services

### Read-Heavy Catalog Service

Requirements:
- Users across multiple regions.
- Catalog reads account for most traffic.
- Data updates are less frequent and can be coordinated.
- Minor replication lag is acceptable for non-critical updates.

Candidate design:
- Active-active application tier across multiple regions.
- Traffic manager routing by latency and health.
- Read replicas or data copies in each region.
- Writes routed to a primary writer or partitioned by tenant.
- Caches with TTLs and invalidation.
- Failover when one region fails.

Risks to verify include stale reads, cold caches, and write routing when the primary region fails.

### Payment Transaction Service

Requirements:
- Every transaction needs one consistent result.
- Duplicate writes are unacceptable.
- Very low RPO.
- Auditing and reconciliation are mandatory.

Candidate design:
- Active-active or multi-AZ application tier.
- Single-writer database with synchronous intra-region HA if supported by the service.
- Replicated standby region with a clear promotion procedure.
- Fencing before promoting a new writer.
- Idempotency keys on all payment operations.
- Outbox/event pattern to emit events post-commit.
- DR tests and post-failover reconciliation.

This model simplifies data consistency compared to multi-primary, though database latency and failover duration must be measured.

## 18. Testing HA and Fault Tolerance

You cannot verify HA simply by seeing green status in two sites. Induce controlled faults and measure outcomes.

### Scenarios to Test

- Terminating a VM or pod.
- Losing connectivity to an AZ.
- Load balancer unable to reach backends.
- Stopping the primary database.
- Increasing replication lag or cutting the replication link.
- Network partition between primary and standby.
- DNS or service discovery outage.
- Unreachable secret manager or key service.
- Overloading one site when absorbing full traffic.
- Simultaneous client retries and reconnects.
- Rolling out an app version while one site is degraded.
- Failing back after the primary recovers.

### Measuring Outcomes

Each drill should record:
- Fault start timestamp.
- Detection timestamp.
- Failover start timestamp.
- Traffic shift timestamp.
- Timestamp when requests succeed again.
- Actual RTO.
- Replication lag and actual RPO.
- Failed, timed-out, or duplicate requests.
- Post-failover capacity and latency.
- Required manual steps.
- Unclear runbook steps.

### Game Days and Chaos Testing

A game day is a planned drill to test procedures and coordination. Chaos testing can automate controlled fault injection over a small scope.

Start in staging or on a small traffic slice with explicit rollback and abort criteria. Never inject wide-scope production faults without appropriate guardrails and operational approvals.

## 19. Security and Operations in Multi-Site Models

Every site must maintain security parity with its serving scope.

Verify:
- IAM roles/service accounts and least privilege.
- Secrets, certificates, and encryption keys available in the standby site.
- Key policies and decrypt permissions.
- Network segmentation and firewall rules.
- TLS across clients, load balancers, apps, and databases.
- Centralized audit logs and time synchronization.
- Consistent image and configuration versions.
- Standby patch levels and security baselines.
- Backups, snapshots, and restore access permissions.

Never leave a standby unpatched for months. A standby site with expired certificates or stale images can fail at the exact moment failover is needed.

## 20. Active-Active vs. Active-Passive Decision Matrix

Use these questions to guide selection:

| Question | If the Answer Is "Yes" | Direction to Consider |
|---|---|---|
| Must the service serve users in multiple regions simultaneously? | Traffic benefits from local processing | Active-active at the application tier |
| Can data be partitioned by tenant/region? | A clear writer can be assigned per slice | Partitioned active-active |
| Must multiple sites write the exact same data? | Needs explicit conflict resolution and consistency | Multi-primary only with a suitable data model |
| Does the workload need single-writer transactional consistency? | Avoid concurrent multi-primary writes | Active-passive at the data tier |
| Is an RTO of several minutes acceptable? | Can scale/promote during an incident | Warm standby |
| Is RTO very low and must standby be immediately ready? | Requires pre-provisioned capacity and data | Hot standby or active-active |
| Is budget constrained? | Can accept a leaner standby | Cold/warm standby, while measuring RTO |
| Can the team operate multi-region data? | Capable of managing replication, partitions, and conflicts | Consider active-active |
| Are dependencies not yet HA? | App HA alone will not protect the service | Re-architect dependencies first |

### Selection Principles

- Choose active-active when concurrent multi-site serving justifies the added data, routing, and consistency complexity.
- Choose active-passive when a single primary writer reduces risk and RTO/RPO targets can be met with standby plus replication.
- Combine as needed: active-active for frontend/app with active-passive for the database; multi-AZ active-active in-region with warm standby in the DR region.
- Choose the simplest model proven to meet SLO, RTO, and RPO targets.

## 21. Pre-Production HA Architecture Checklist

- [ ] Identified target failure domains to tolerate: instance, AZ, or region.
- [ ] Defined SLO, RTO, and RPO per service.
- [ ] Selected active-active or active-passive for each layer.
- [ ] Verified capacity when losing one site or one AZ.
- [ ] Defined standby state: cold, warm, or hot.
- [ ] Designed traffic routing, health checks, and connection draining.
- [ ] Established primary write ownership and consistency model.
- [ ] Measured replication lag and defined promotion rules.
- [ ] Implemented quorum/fencing to prevent split-brain.
- [ ] Defined recovery strategies for sessions, caches, files, and queues.
- [ ] Added idempotency or deduplication for request retries.
- [ ] Critical dependencies have HA or documented recovery plans.
- [ ] Secrets, keys, certificates, and IAM are ready in the standby site.
- [ ] Independent backups exist and passed restore tests.
- [ ] Failover and failback runbooks are written.
- [ ] Drilled instance, AZ, region loss, and network partitions.
- [ ] Measured actual RTO/RPO and recorded gaps.
- [ ] Dashboards, alerts, and audits cover replication, health, and traffic.
- [ ] Abort criteria and rollback plans defined for game days.
- [ ] Accountable owners and recurring drill schedule assigned.

## Conclusion

Active-active lets multiple sites serve traffic concurrently and can shorten traffic switchover time, yet demands careful engineering of data consistency, replication, routing, and split-brain controls. Active-passive keeps one primary site and one standby site, often suiting single-writer workloads or goals to minimize data complexity, provided the standby retains sufficient capacity and failover/failback are tested. Decisions should rest on RTO, RPO, failure domains, data recoverability, dependency limits, budget, and operational maturity. An architecture is considered HA only when actual failover has been drilled, measured, and proven through both service behavior and data integrity.
