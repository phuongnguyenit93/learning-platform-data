# Multi-Region Deployment and Avoiding Shared Dependencies

An application with multiple replicas can still go down if all replicas reside in the same cloud region and that region suffers an outage. Likewise, deploying across two regions does not guarantee real resilience if both depend on a single primary database, DNS provider, identity system, KMS key path, or control pipeline. Multi-region architecture is only valuable when the system can continue delivering critical functions when a failure domain is isolated or completely lost.

**Multi-region deployment** places application components and data across multiple geographic regions to reduce the impact of broad outages, support latency requirements, or satisfy data compliance. **High availability (HA)** is the ability to keep a service operating within acceptable disruption limits when one or more components fail. **Disaster recovery (DR)** is the capability to restore services and data after a major incident within agreed time and data-loss objectives.

A design may achieve HA within a single region using multiple availability zones yet still fail to withstand a region-level outage. Conversely, deploying in two regions does not automatically ensure HA if failover, data, identity, or shared dependencies are unavailable. This lesson focuses on multi-region architecture and how to identify and mitigate shared dependencies that undermine redundancy.

Within the **CLOUD_ARCHITECTURE** module, this topic connects directly to reliability, security, networking, compute, data architecture, operations, and cost. The goal is to evaluate failure domains, select an appropriate topology, define RTO/RPO, design replication and traffic failover, prevent split-brain, audit shared dependencies, and prove recoverability through drills.

## 1. Availability Zones, Regions, and Failure Domains

A cloud provider typically organizes infrastructure into geographic regions, and each region may contain multiple availability zones (AZs) or equivalent independent infrastructure zones. AZs are generally designed to reduce correlated failures in power, cooling, and networking within a region, though exact isolation details depend on the provider.

A **failure domain** is the scope of resources that can be affected together by a single root cause. It can be:
- A process or container.
- A VM or node.
- A rack or hardware cluster.
- An availability zone.
- A region.
- A provider or control plane.
- A shared dependency such as DNS, identity, certificate authority, or KMS.

~~~mermaid
flowchart TB
    P["Cloud provider"] --> R1["Region A"]
    P --> R2["Region B"]
    R1 --> A1["AZ A1"]
    R1 --> A2["AZ A2"]
    R2 --> B1["AZ B1"]
    R2 --> B2["AZ B2"]
    A1 --> N1["Compute / Data"]
    A2 --> N2["Compute / Data"]
    B1 --> N3["Compute / Data"]
    B2 --> N4["Compute / Data"]
~~~

Having two AZs in the same region helps handle certain localized failures, yet many managed services, endpoints, quotas, control planes, and datasets remain region-scoped. Losing a region can affect every AZ inside that region.

### 1.1. Multi-AZ HA vs. Multi-Region DR

| Scope | Primary goal | Example incidents mitigated | Limitations |
|---|---|---|---|
| Multiple processes/containers | Survive single-process failure | Crashes, local memory leaks | Cannot survive node/zone failure if co-located on one host |
| Multiple nodes | Tolerate server failure | VM/node crash | May share an AZ or storage/network dependencies |
| Multiple AZs | Tolerate certain zone-level failures | Power, network, or infrastructure loss in one AZ | Does not protect against region-wide outages |
| Multiple regions | Recover from region-level outages | Region loss, wide-scale disruption | Complexity in data, routing, consistency, and cost |
| Multi-provider | Reduce certain provider-dependency risks | Provider-wide or control-plane outages | Substantially increases complexity, data, and operational overhead |

Not every application needs multi-region active-active. First assess the consequences of downtime and data loss, then select failure domains matching business requirements.

## 2. Defining RTO and RPO Objectives

The two foundational DR objectives are:

- **RTO (Recovery Time Objective):** the maximum acceptable time to restore service after an incident.
- **RPO (Recovery Point Objective):** the maximum acceptable amount of data loss, usually expressed as a time interval of data.

For example:
- A public content site might tolerate a 4-hour RTO and 1-hour RPO.
- A critical booking API might need a 15-minute RTO and near-zero RPO, subject to technical feasibility, cost, and the exact definition of committed transactions.
- An analytics dashboard can tolerate a longer RTO and rebuild from source data.

RTO/RPO are **business objectives**, not default guarantees of cloud services. They must be verified against replication lag, detection time, failover decision time, provisioning time, DNS/traffic propagation, startup, database recovery, and business validation.

### 2.1. Availability vs. Recovery

Availability typically measures the percentage of time a system meets its SLO over an observation period. DR focuses on recovering from a major incident and controlling data loss. A multi-region system whose failover takes 6 hours still fails a 30-minute RTO target.

### 2.2. Example RTO/RPO by Tier

| Service tier | Illustrative RTO | Illustrative RPO | Typical approaches considered |
|---|---:|---:|---|
| Tier 0: core transactions | Minutes | Near 0 or a few seconds | Multi-zone, tight replication, hot standby, or carefully engineered multi-region |
| Tier 1: critical business APIs | 15–60 minutes | A few minutes | Warm standby, database replication, automated/orchestrated failover |
| Tier 2: reporting/operations | Several hours | 1 hour or more | Pilot light, backup/restore, batch rebuild |
| Tier 3: reproducible content | Hours/days | Reproducible | Backups, object versioning, redeploy from artifacts |

These values are illustrative only. Agree on RTO/RPO per capability and data type rather than assigning one number to the entire system and assuming every component is equally critical.

## 3. Choosing a Multi-Region Topology

Multiple topologies exist. No single topology is best in all circumstances.

### 3.1. Active-Passive

One region serves production traffic; the other maintains data replicas and standby compute. When the primary region fails, the system promotes the database or spins up compute in the standby region and shifts traffic.

~~~mermaid
flowchart TB
    U["Users"] --> G["Global routing"]
    G --> A["Region A - Active"]
    G -. "Standby" .-> B["Region B - Passive"]
    A --> DA[("Primary data")]
    DA ==>|"Replication"| DB[("Standby replica")]
    B -.-> DB
~~~

Pros:
- A single primary write location simplifies consistency.
- Standby can hold fewer resources, lowering cost compared to active-active.
- Clear ownership and write flow.

Trade-offs:
- Standby may lack sufficient capacity if kept minimal.
- Failover requires promoting data, scaling compute, checking dependencies, and shifting traffic.
- Replication lag can lose recent transactions.
- Without failover drills, manual procedures easily exceed RTO.

Active-passive fits when clear DR is needed, traffic can shift regions, and the business tolerates a failover window.

### 3.2. Warm Standby

The standby region runs a minimal or scaled-down version of the application, database replicas, and required dependencies. When the primary fails, capacity is scaled up and traffic shifts over.

The advantage is a generally better RTO than pilot light because many components are already running. In return, you must verify warm capacity, scale-up time, model/artifact/cache warm-up, and quotas. The standby must be continuously verified so it does not drift into an outdated or misconfigured state.

### 3.3. Pilot Light

The standby region holds minimal foundational components for recovery, such as networking, identity integration, database replication, artifacts, and configuration. Application compute may not be running or may run at minimal scale.

Cost is lower than warm standby, but RTO is longer due to provisioning compute, deploying the app, loading artifacts, and verifying health. Ensure automation, image registries, and secret access all work in the standby region.

### 3.4. Backup and Restore

No running application is maintained in a second region. When DR is needed, backups are restored and infrastructure and data are deployed elsewhere.

This can suit less critical systems or reproducible data, though RTO is typically longer. Backups are only useful if they can be restored, keys remain accessible, schemas are compatible, and restore times have been measured.

### 3.5. Active-Active

Multiple regions serve production traffic concurrently. Each region may serve nearby users, or all regions may serve the entire user base.

~~~mermaid
flowchart TB
    U["Users worldwide"] --> G["Global traffic manager"]
    G --> A["Region A - Active"]
    G --> B["Region B - Active"]
    A --> DA[("Regional data A")]
    B --> DB[("Regional data B")]
    DA <-->|"Replication / conflict policy"| DB
~~~

Pros:
- Can reduce latency for users across multiple geographies.
- Compute across multiple regions is actively utilized.
- If one region fails, traffic can route to others without booting a full stack from scratch.

Trade-offs:
- Concurrent writes across locations require conflict resolution or partition ownership.
- Duplicates, lost updates, or write conflicts can arise.
- Traffic shifting to remaining regions can overload them if capacity was only sized for normal distribution.
- Requires explicit consistency models, routing policies, and data locality.
- Testing and operations are significantly more complex.

Active-active makes sense only when the workload and data model genuinely support distributed writes or consistent coordination, and latency/availability gains justify the cost.

### 3.6. Topology Comparison

| Pattern | Compute in DR region | Data complexity | Typical cost | Relative RTO |
|---|---|---|---|---|
| Backup/restore | None or minimal | Backup restoration | Lower during normal ops | Long |
| Pilot light | Minimal | Replication/restore | Low–medium | Medium–long |
| Warm standby | Scaled down but running | Replication and promote | Medium | Shorter than pilot light |
| Hot active-passive | Full standby capacity | Single primary writer, standby | Higher | Short |
| Active-active | Multiple regions actively serve | Multi-writer/partition/conflict | Often high and complex | Potentially short, barring data bottlenecks |

Actual RTO still depends on failure detection, failover decisions, promotion, routing propagation, dependencies, and validation. Never infer RTO solely from a topology's name.

## 4. Traffic Routing and Failover

Multi-region traffic can be steered via DNS-based routing, global load balancers, anycast networks, CDNs, or service-specific traffic managers.

Strategies:
- **Priority/failover:** prefer primary region; switch to standby when health checks fail.
- **Weighted routing:** distribute traffic proportions across regions.
- **Latency-based routing:** direct users to the region with lowest latency.
- **Geographic routing:** route by location or data residency.
- **Anycast/global edge:** route to the nearest or healthiest network ingress per provider mechanics.

### 4.1. Health Checks Must Reflect Serving Readiness

A health endpoint checking only that the process is alive can return healthy even after losing database connectivity. Conversely, if a health check depends on every optional service, one minor dependency outage can pull an entire region out of rotation.

Distinguish between:
- **Liveness:** does the process need to be restarted?
- **Readiness:** can the instance accept new traffic?
- **Regional health:** does the region have minimum capabilities to serve specific request types?
- **Dependency health:** which dependency failed and which features can degrade?

Health checks should verify critical dependencies appropriately without triggering thundering herds or turning a secondary feature outage into a region-wide failover.

### 4.2. DNS Failover Has Latency and Caching

DNS-based failover is not always instantaneous:
- Resolvers and clients can cache records per TTL.
- Some clients ignore TTL expectations.
- Health checks have intervals and thresholds before changing routing.
- Open connections may keep using the old endpoint.
- The DNS control plane or authoritative DNS itself is a dependency that must be evaluated.

Global load balancers may shift traffic faster in some architectures, yet they carry their own failure domains and dependencies. Measure actual traffic shift times from diverse networks and regions.

### 4.3. Failover Procedure

1. Detect failure using telemetry independent of the affected region.
2. Verify scope and incident type: zone, region, data, network, or dependency.
3. Decide on automated vs. approval-gated failover.
4. Block new writes on the old primary if needed to avoid split-brain.
5. Inspect replication lag and select a promotable data point.
6. Promote the database/partition or transfer writer ownership per procedure.
7. Ensure secrets, identity, KMS, DNS, certificates, and endpoints work in the target region.
8. Scale compute and workers to required capacity.
9. Shift traffic gradually or per tested policy.
10. Run smoke tests and business verification, not just HTTP 200.
11. Monitor errors, latency, queue backlogs, duplicates, and data consistency.
12. Record recovery duration and reconcile data.

Never fail over into bidirectional writes simply because the primary endpoint stopped responding. Without knowing whether the primary can still accept writes, promoting another writer risks split-brain.

## 5. Replication and Data Consistency

A second region is useful only when it holds sufficiently fresh data to serve the business.

### 5.1. Synchronous Replication

Transactions are acknowledged after data is synchronously written to one or more required replicas. This reduces RPO but increases latency and network dependency across failure domains. If a replica stops responding, write availability may drop.

### 5.2. Asynchronous Replication

The primary acknowledges writes before replicas receive the full data. This lowers latency and insulates the primary from cross-region links, but replicas lag. If the primary is lost abruptly, unreplicated transactions may be lost.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant P as Primary DB
    participant R as Remote replica
    A->>P: Commit transaction
    P-->>A: Commit acknowledged
    P-->>R: Replicate asynchronously
    Note over P,R: Replica may lag behind primary
~~~

### 5.3. Semi-Synchronous and Quorum

Some systems acknowledge writes after a subset of replicas/quorum receives logs or data under specific semantics. Quorum does not mean "a majority of regions always hold complete data" in every product; understand the commit rules, fault tolerance, leader election, and consistency guarantees.

### 5.4. Replication Types to Distinguish

- **Storage/block replication:** copies blocks or volumes; may be crash-consistent but not necessarily application-consistent.
- **Database replication:** copies transactions/logs or row-level changes via DB mechanisms.
- **Object replication:** copies objects/versions/metadata; often asynchronous and without cross-object business ordering guarantees.
- **Event replication:** forwards events across brokers/streams; requires handling duplicates, ordering, and replay.
- **Application-level replication:** application writes to multiple targets or syncs via custom workflows.

Do not treat backup, replication, and consistency as synonyms. Replication can propagate accidental deletions or data encrypted by a lost key; backups preserve isolated historical recovery points.

## 6. Split-Brain, Quorum, and Single-Writer Ownership

**Split-brain** occurs when two nodes/regions both believe they are primary or authorized to write when the system intends only one writer. During a network partition, both sides can accept writes and create conflicting data.

Mitigations:
- Use leader election/quorum mechanisms with well-understood semantics.
- Use time-bounded leases and fencing tokens to stop an old writer from writing after losing leadership.
- Block or fence the old primary before promoting a new writer.
- Use single-writer per dataset/partition if workloads do not support multi-writer.
- Design idempotency and conflict resolution for duplicates.
- Do not trigger promotion solely from application health checks.

In multi-region setups, cross-region quorum can suffer from inter-region latency and network splits. Three failure domains or a witness can help some systems establish a majority, though a witness cannot replace a full data replica needed to serve writes. Review the exact algorithm and requirements of your database/broker.

### 6.1. Fencing Tokens

A fencing token is a monotonically increasing sequence number/epoch issued to the lock or leadership holder. Storage or resources check the token and reject older writers carrying lower tokens. This protects against cases where a lease expires yet an old process keeps running due to pauses or network delays.

Not every database or cloud service exposes a direct fencing API; sometimes logic must reside in the data tier or leverage consensus/provider mechanisms.

## 7. Avoiding Shared Dependencies That Defeat Redundancy

This is the most frequently overlooked area in multi-region design. Two regions may run independent apps and databases yet rely on one shared service to boot, authenticate, decrypt secrets, resolve names, or deploy. If that dependency fails, both regions go down together.

A shared dependency can be:
- Identity provider, federation, or authentication control plane.
- Authoritative DNS, registrar, or DNS management account.
- KMS, HSM, certificate authority, and certificate issuance services.
- Secret manager or centralized configuration store.
- Container/image registry, package repository, or model registry.
- CI/CD, source control, or deployment orchestrator.
- Global load balancer, WAF, or CDN control plane.
- Centralized logging, monitoring, tracing, or alerting.
- Network hub, transit gateway, firewall, or egress proxy.
- Database control plane, replication coordinator, or shared metadata store.
- Third-party SaaS, payment providers, or email/SMS providers.

~~~mermaid
flowchart TB
    A["Region A"] --> APPA["Application A"]
    B["Region B"] --> APPB["Application B"]
    APPA --> SHARED["Shared identity / KMS / DNS / registry"]
    APPB --> SHARED
    SHARED --> X["Shared dependency failure"]
    X --> DOWN["Both regions affected"]
~~~

### 7.1. Building a Dependency Inventory

For each dependency, record:
- Owner and operations team.
- Failure domain/regional scope.
- Endpoints and network paths.
- Needed at runtime or only during deploy/startup?
- Local caches/credentials/fallbacks available?
- Reachable from the DR region?
- Provider RTO/RPO and SLA.
- Workaround when the dependency is unavailable.
- Testing procedure and authorized operators.

Do not merely ask "is the service multi-region?"—ask **how its control plane, data plane, identity, key access, and quotas are made redundant**.

## 8. Designing Multi-Region Identity and Access

A standby application may fail to start if workload identity or federation is configured only for the primary region.

Evaluate:
- Is workload identity created/authorized for the target region, account/subscription/project?
- Are token issuers, audiences, federation trusts, and endpoints reachable when the primary region is lost?
- Do credentials depend on the identity control plane at token-acquisition time?
- How long can runtime keep using existing short-lived tokens?
- Are roles/policies in the DR region provisioned and permission-tested?
- Does break-glass admin access work if primary SSO/IdP is disrupted?

Prefer dedicated workload identities with least privilege. Avoid creating roles only when failover happens because provisioning may sit on the RTO critical path.

### 8.1. Control Plane vs. Data Plane

The control plane manages configuration/resources; the data plane handles runtime traffic or operations. Some services continue data-plane operations during control-plane disruptions, yet cannot create new resources, change policies, or issue credentials. Know the exact behavior of every service used.

A DR design must never assume that because containers run in region B, all identity, secret retrieval, policy refresh, and scaling actions will also work.

## 9. KMS, Encryption Keys, and Certificates

A database replica or replicated object may be unreadable in the standby region if keys or decryption permissions are unavailable.

Ensure:
- Keys can be used in the target region per policy/provider rules.
- Multi-region keys or key replicas exist with proper rotation semantics.
- Backup encryption keys are escrowed/managed safely.
- DR workload identities hold properly scoped decrypt permissions.
- Certificate systems can issue/renew when the primary CA or account fails.
- Trust bundles and certificates have expirations suitable for DR duration.
- Private keys are not stored in a single centralized dependency.

Never copy raw private keys arbitrarily to another region. Use provider-supported KMS/HSM and key replication; verify policies, audits, and residency. DR drills must test decrypting backups or reading replicated data using DR region identities, not merely check that objects exist.

## 10. DNS, Networking, and Inter-Region Connectivity

DNS and networking are essential infrastructure for both applications and failover procedures.

Evaluate:
- Are authoritative DNS and its management account independent of the application region?
- How are TTLs, resolver caching, and propagation measured?
- Are standby addresses/endpoints and matching certificates ready?
- Do transit networks, firewalls, NATs, or egress proxies have shared failure points?
- Are routing tables, peering, private endpoints, and security groups ready in the DR region?
- Has connectivity to data stores, object storage, identity, and third parties been tested?
- Have single points of failure like a lone VPN appliance or network hub been avoided?

A region with healthy compute that cannot reach its database or identity endpoint still cannot serve. Separate network paths or hub redundancy may be needed; however, adding network paths requires managing routing loops, security boundaries, and cross-region costs.

### 10.1. Egress and Data Transfer

Replication, backups, log shipping, and traffic failover all generate cross-region egress. When designing, calculate:
- Replicated data volume per second/day.
- Bursts during backlog catch-up.
- Inter-region application traffic.
- Backup/restore and object replication costs.
- Global load balancer/CDN fees and cross-zone transfers.

An active-active architecture can create substantial bidirectional replication traffic; benchmark costs and latency upfront.

## 11. Registries, Artifacts, and Pipelines in DR

The standby region may fail to deploy if container registries, package repositories, or model artifact stores exist only in the primary region.

Prepare:
- Promoted images and artifacts replicated to the DR region.
- Preserved digests/signatures and provenance.
- Runtime dependencies installable without calling the primary registry.
- Mirrors or caches for required IaC/modules/providers/versions.
- Deployment secrets/configs prepared securely.
- Deployment pipelines able to run from an independent failure domain.
- Approvals and break-glass access maintained outside a single SSO/control plane if required.

Never let a DR runbook instruct "rebuild images from source" when primary source control, package registries, or CI/CD are down. Maintain vetted, production-ready artifacts with versioned deployment manifests.

## 12. Observability and Operations During Region Loss

Centralized observability gives a unified view, yet it can itself become a shared dependency. If all metrics/logs/alerts flow to a single region and that region fails, operators can lose visibility into the remaining incident.

Consider:
- Agents with local buffering when the central collector is unavailable.
- Monitors/alerts outside the primary region and primary account/subscription.
- Incident communication channels independent of the application system.
- Per-region dashboards alongside global dashboards.
- Reliable clock/time synchronization for log correlation.
- Correlation IDs and trace context propagated across regions.
- Sensitive data redacted from logs before replication.
- Observability access that still works when primary SSO fails.

Separate control-plane telemetry from data-plane telemetry. A green dashboard does not prove user journeys succeed; test with external synthetic transactions against each region.

## 13. Active-Active Data Design and Write Partitioning

To run active-active safely, choose an appropriate data model.

### 13.1. Single-Writer per Record/Partition

Each aggregate/tenant/partition has one region responsible for writes at any time. Other regions can read replicas or handle other workloads. On failover, ownership transfers with epochs/fencing and replication reconciliation.

The advantage is fewer write conflicts. The trade-off is that a partition must relocate when its owner fails, and users far from the writer may see higher latency.

### 13.2. Multi-Writer with Conflict Resolution

Multiple regions can write to the same data. Define conflict resolution clearly:
- Last-write-wins using managed timestamps/clocks.
- Version vectors/causal metadata.
- CRDTs for suitable data types.
- Application-level merges or compensating workflows.

Last-write-wins is simple but can overwrite meaningful updates; clock skew can produce wrong outcomes. CRDTs apply only to structures and operations with matching algebraic properties, not as a general solution for booking or payment transactions.

### 13.3. Partitioning by Geography/Tenant

A tenant or data group is assigned a home region. Users may connect via a global endpoint, but writes route to the owning region. This reduces conflicts yet requires:
- High-availability tenant-to-region mapping.
- Procedures to migrate tenants when a region fails.
- Cross-region read strategies.
- Data residency compliance.
- Handling cross-tenant transactions or global reporting.

This option is typically easier to govern than arbitrary multi-writer designs for transactional data.

## 14. Failback: Returning to the Original Region

After failing over to region B, do not automatically shift traffic back to region A as soon as A reports healthy. A may still hold stale data, mismatched schema versions, or outdated config.

Failback procedure:
1. Confirm region A has recovered and the root cause is resolved.
2. Keep A blocked from accepting writes.
3. Sync data from the current writer B back to A.
4. Reconcile replication lag, schemas, key access, and object versions.
5. Verify app/runtime/image/config along with model/secret versions.
6. Run business verification and capacity tests in A.
7. Choose a maintenance window and write-ownership transfer plan.
8. Fence writer B or transfer ownership per protocol.
9. Shift traffic gradually and monitor closely.
10. Retain the option to return to B until stability is confirmed.
11. Record failback duration and reconciled data.

Failback is a high-risk data and traffic operation; it is not equivalent to simply flipping a DNS record back.

## 15. Security in Multi-Region Architectures

Expanding across regions multiplies data copies, endpoints, keys, policies, and principals. Security must stay consistent while honoring data residency.

- Enforce least privilege for runtimes, replication agents, and operators.
- Separate permissions for failover, writer promotion, redrive, and purge.
- Encrypt data in transit and at rest; manage keys in the target region.
- Maintain independent or securely replicated audit logs.
- Protect control planes, break-glass paths, and emergency credentials.
- Identify which data must never leave a region/country.
- Do not open broad networks between regions merely for replication convenience.
- Control secret/config drift and image provenance.
- Audit security policies in the DR region, not only the primary region.
- Preserve incident response procedures if a region/IdP is compromised.

A DR site becomes a production site during emergencies. Never weaken security posture to make critical data easier to access just for faster recovery.

## 16. Multi-Region Testing and Drills

Undrilled DR documentation is merely an assumption. Test across multiple levels:

| Test type | Scope | Goal |
|---|---|---|
| Component failover | Process/node/AZ | Verify health checks, rescheduling, and load balancing |
| Region simulation | Block selected regional dependencies or routes | Test detection and fallbacks |
| Planned regional failover | Planned traffic shift | Validate runbooks, data promotion, and DNS/routing |
| Unplanned DR exercise | Simulated unannounced region loss in a controlled environment | Measure actual RTO/RPO |
| Dependency outage | IdP, KMS, DNS, registry, observability | Uncover shared dependencies |
| Restore test | Restore backups into an isolated environment | Confirm backups and keys work |
| Failback rehearsal | Sync back to original region | Test reverse replication and ownership transfer |
| Capacity failover test | Shift 100% load to remaining region | Verify headroom and quotas |

### 16.1. Controlled Game Days

A game day should define:
- Scope, owner, and incident commander.
- Scenario, stop conditions, and rollback plan.
- Target RTO/RPO and success criteria.
- User journeys to verify.
- Controls protecting real customers and production data.
- Recorded timeline and decisions.
- Post-drill review and tracked action items.

You do not need to start by shutting down an entire production region. Simulate blocked dependencies, fail over staging, or shift a small cohort before running larger drills.

## 17. Shared Dependency Audit Table

Use the following table during architecture reviews:

| Dependency | Region A | Region B | Shared failure domain? | Control measure |
|---|---|---|---|---|
| Identity/token issuer | Local/federated | Local/federated | Needs verification | Token strategy, alternate admin access |
| DNS/traffic management | Global service | Global service | Possibly | Redundant authoritative DNS, tested routing |
| KMS/HSM | Regional key | Regional replica/key | Possibly | Cross-region key policy, decrypt test |
| Secret/config store | Runtime endpoint | Runtime endpoint | Possibly | Replica/cache, local bootstrap config |
| Container/artifact registry | Local mirror | Local mirror | Possibly | Replicated immutable artifacts |
| CI/CD and source control | Primary pipeline | Independent deployment path | Possibly | DR deploy pipeline and runbook |
| Network hub/firewall | Path A | Path B | Possibly | Redundant paths and routing tests |
| Observability/alerting | Local buffer | Local buffer | Possibly | Independent monitors and incident channel |
| Certificate authority | Issuer access | Issuer access | Possibly | Pre-issued certs, renew/rotation exercises |
| Third-party provider | Same endpoint | Same endpoint | Usually yes | Alternative provider or graceful degradation |
| Quotas/control plane | Account/service quota | Account/service quota | Provider-dependent | Pre-approved quotas and warm capacity |

This table is a starting point. For every dependency, document endpoints, accounts, control plane, data plane, identity, and actual failure scope. Two distinct endpoints are not necessarily independent failure domains if they share a backend or control plane.

## 18. Well-Architected Trade-Offs

| Dimension | Multi-region benefits | Risks/costs to manage | Evidence |
|---|---|---|---|
| **Reliability** | Recovers from zone/region loss, cuts downtime | Replication lag, split-brain, untested failover, insufficient DR capacity | DR drills, measured RTO/RPO, failover tests |
| **Security** | Can isolate failure domains and sustain service | More PII copies, key/policy drift, weak break-glass | IAM reviews, encryption tests, audits, residency |
| **Performance Efficiency** | Serves closer to users, lower latency, load distribution | Cross-region write/replication latency, misrouting, cold caches | Regional p95/p99, replication lag |
| **Cost Optimization** | Avoids major outages; can use pilot light/standby | Idle compute, replication, network egress, DR exercises | Cost per tier, standby utilization, transfer costs |
| **Operational Excellence** | Clear recovery processes and ownership | More topologies, runbooks, and control planes | Game days, runbooks, dependency inventory |
| **Sustainability** | Sustains services and recovers critical data | Replicating unnecessary data wastes storage/network/compute | Data classification, lifecycle, replication scope |

Common trade-offs:
- Active-active can lower latency but complicates consistency and conflict resolution.
- Active-passive makes single-writer simpler but requires standby capacity and failover.
- Synchronous replication lowers RPO but increases latency and network coupling.
- Asynchronous replication reduces write latency but risks losing recent data.
- Shared global services reduce operational duplication yet introduce shared failure domains.
- Splitting services per region increases isolation yet requires consistent provisioning, policies, and automation.

## 19. Multi-Region Design Process

1. **Classify capabilities:** determine which services truly need multi-zone or multi-region.
2. **Assess business impact:** downtime, data loss, data residency, and SLAs.
3. **Set RTO/RPO:** per capability, database, and data type.
4. **Map failure domains:** compute, AZ, region, provider, and shared services.
5. **Select topology:** active-passive, pilot light, warm standby, active-active, or backup/restore.
6. **Design traffic routing:** health checks, DNS/global load balancing, propagation, and capacity.
7. **Design data replication:** sync/async, writer ownership, lag, conflicts, and consistency.
8. **Eliminate single-point shared dependencies:** identity, KMS, DNS, registry, secrets, network, CI/CD, and observability.
9. **Prepare capacity/quotas:** compute, storage, GPUs if needed, IPs, endpoints, and provider quotas in the target region.
10. **Design security:** identity, keys, encryption, auditing, residency, and break-glass.
11. **Write failover/failback runbooks:** triggers, authority, fencing, promotion, traffic, and validation.
12. **Test and drill:** measure RTO/RPO, user journeys, dependency outages, and capacity.
13. **Monitor drift:** config, images, schemas, policies, and artifacts across regions.
14. **Review costs:** standby, replication, egress, licensing, and ongoing operations periodically.

### Illustrative ADR — Booking API Running Active-Passive

> **Context:** The Booking API handles critical transactions. The business goal is recovery within 30 minutes and zero loss of confirmed transactions per the system's commit semantics. Traffic is concentrated primarily in one geographic area.
>
> **Option A:** Multi-region active-active for both application and database. Keeps traffic across regions, but requires multi-writer or data partitioning, conflict resolution, and reconciliation.
>
> **Option B:** Active region handles writes; second region runs warm standby with database replication and scaled-down application capacity. On failover, fence the old writer, promote standby, and shift traffic.
>
> **Illustrative Decision:** Choose B if measured RTO/RPO meets commitments and the business does not require multi-region write locality. Keep a single writer to simplify booking transactions.
>
> **Shared Dependencies:** Prepare identity, KMS key access, secrets/config, DNS routing, container images, and deployment pipelines in the standby region. Run monitoring independent of the active region.
>
> **Recovery:** Check replication lag, fence primary, promote standby, scale capacity, shift traffic, smoke-test booking/payment, and reconcile transactions near the time of failure.
>
> **Verification:** Planned/unplanned failover, AZ loss, region loss, IdP/KMS/DNS failures, quota exhaustion, backup decryption, and failback.
>
> **Revisit Triggers:** Users/traffic spread across multiple geographies, inter-region latency misses SLOs, or write locality is required; then evaluate partition ownership or controlled active-active.

## 20. Hands-On Exercise: Finding Shared Dependencies in a DR Architecture

A booking platform deploys:
- Booking API and Notification Worker in Region A.
- An application copy and database replica in Region B.
- Global DNS routing shifts traffic when A fails.
- Both regions share the same identity provider, KMS account, secret manager endpoint, container registry, CI/CD pipeline, and central logging in Region A.
- Database replication is asynchronous with typical 20-second lag.
- Region B runs only 30% of A's capacity.

The team claims a 10-minute RTO and RPO of 0.

**Tasks:**
1. Identify shared dependencies that could prevent Region B from starting or serving.
2. Evaluate whether an RPO of 0 is consistent with 20-second asynchronous replication lag.
3. Identify capacity shortfalls when shifting 100% of traffic to B.
4. Design safe writer failover to prevent split-brain.
5. Propose redundancy for identity, KMS, secrets, registry, pipeline, DNS, and observability.
6. Specify which steps must be measured to establish actual RTO.
7. Design failback and reconciliation for bookings near the time Region A failed.
8. Propose a game day testing both a region outage and a shared dependency outage.

### Solution Approach

- Region B still depends on Region A's identity, KMS, secret manager, registry, CI/CD, and logging. When A fails, B may be unable to fetch tokens/secrets, decrypt data, pull images, scale, or observe the incident.
- Asynchronous replication with 20-second lag cannot substantiate RPO 0. Measure lag, determine which committed transactions reached the replica, and either change replication/consistency or adjust RPO.
- 30% capacity cannot handle 100% peak load without rapid scaling, admission control, or graceful degradation. Verify quotas and startup/warm-up times beforehand.
- Before promoting B, fence writer A via appropriate database/epoch/lease mechanisms; verify the old primary cannot accept writes; only one writer may be active.
- Prepare identity federation/credentials, key decrypt permissions, local or replicated secrets/config, artifact mirrors, an independent DR pipeline, authoritative DNS outside the failure domain, and local/independent telemetry.
- Measure RTO from detection until the service passes user journeys and SLOs, including decision, fencing, promotion, scaling, traffic propagation, and validation.
- Failback must sync data B→A, block writes on A first, reconcile bookings/payments, and check versions/config before transferring ownership and traffic.
- Game days isolate Region A, IdP, KMS, registry, and observability sequentially; set stop conditions, test data protection, and measure RTO/RPO.

### Self-Check Questions

1. Which failure domains do multi-AZ and multi-region protect against?
2. How do RTO and RPO differ? Why must they be measured instead of inferred from topology?
3. How do active-passive, warm standby, pilot light, and active-active differ?
4. Why can DNS failover be slower than health checks?
5. Which transactions can asynchronous replication lose during failover?
6. When does split-brain happen and how do fencing tokens help?
7. Why can KMS, identity, or registries bring down both regions simultaneously?
8. How does a control-plane outage differ from a data-plane outage?
9. When is single-writer per tenant/partition better than multi-writer?
10. Why does failback require its own dedicated procedure?
11. How can centralized observability become a shared dependency?
12. What evidence proves a DR site actually meets RTO/RPO?

A reliable multi-region architecture is more than adding a second copy of the application and database. It must **isolate failure domains, maintain sufficiently fresh data, transfer write ownership safely, preserve identity/keys/networking/artifacts, and keep the system observable when the primary region is lost**. Choosing the right topology begins with RTO/RPO and data semantics, and is proven through measured failover, failback, and dependency-outage drills.
