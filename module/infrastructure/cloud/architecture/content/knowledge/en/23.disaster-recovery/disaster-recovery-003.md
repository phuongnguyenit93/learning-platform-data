# Backup–Restore, Pilot Light, Warm Standby, and Active–Active Strategies

> **Chapter:** Disaster Recovery  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements to networking, compute, data, and deployment model choices; balancing reliability, security, scalability, cost, and operations with a Well-Architected mindset.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish backup/restore, pilot light, warm standby, and active–active; recognize them as strategies with differing availability levels, costs, and complexity.
2. Translate business requirements into **RTO** and **RPO** targets, and determine recovery order and the minimum viable service level required.
3. Design protection and recovery for data, configuration, identity, encryption keys, applications, and required dependencies.
4. Analyze replica lag, consistency, split-brain, fencing, failover, and failback in single-region or multi-region environments.
5. Select active-passive/active-active topologies, DNS/global routing procedures, and mechanisms to validate recoverability.
6. Organize runbooks, decision authority, DR drills, recovery time measurements, and remediation for gaps between plans and actual capability.
7. Evaluate trade-offs across reliability, security, performance, cost, operations, and sustainability under Well-Architected principles.

## 1. What Problem Does Disaster Recovery Solve?

A cloud system may run across multiple instances, use managed databases, load balancers, and multiple availability zones, yet still face incidents extending beyond a single failure domain. For example:

- An entire region becomes unavailable due to a widespread outage or lost connectivity to foundational services.
- A bad configuration or faulty release propagates to every instance.
- A cloud account is compromised, data is encrypted/deleted, or administrative privileges are abused.
- Database corruption, accidental deletion, ransomware, or logically corrupted data is replicated to replicas.
- An external provider or identity system experiences a prolonged outage.
- A physical incident, natural disaster, or operational failure prevents the team from accessing the primary region.

**Disaster recovery (DR)** is the set of strategies, architectures, data protections, procedures, and organizational capabilities to restore services after a severe incident. The goal is not merely restarting servers. A system is truly recovered only when users can execute critical business workflows again, data reaches an acceptable level of consistency, access controls work, required integrations are ready, and operations teams can monitor the new state.

### 1.1. Distinguishing High Availability, Backup, and Disaster Recovery

| Concept | Goal | Examples | Limitations |
|---|---|---|---|
| **High availability (HA)** | Minimize disruption within anticipated failure domains | Multiple instances/zones, managed DB failover | Does not inherently resolve region-wide outages or logically deleted data |
| **Backup** | Maintain data/configuration copies for restoration | Snapshots, point-in-time recovery, object versioning | Having backups does not prove they are restorable or restorable fast enough |
| **Disaster recovery** | Restore services and data after a disaster | Cross-region restore, warm standby, active-active | Requires procedures, decisions, permissions, data, and end-to-end testing |
| **Business continuity** | Maintain business operations during and after an incident | Temporary manual workflows, fallback communication channels | Broader than technology; includes people, vendors, and business processes |

HA and DR complement each other. Multi-AZ handles certain localized infrastructure failures, yet does not necessarily protect against a bad configuration deployed across all zones simultaneously. Backups protect data recoverability at a point in time, yet do not necessarily provide endpoints ready to serve traffic. A DR plan must clarify the scope of each mechanism.

### 1.2. Scope of "System Recovery"

A workload comprises many components and dependencies:

- Compute, container images, VM templates, serverless functions, and runtime configuration.
- Databases, object storage, file systems, caches, and search indexes.
- Queues, brokers, event subscriptions, schedulers, and background workers.
- Networking, DNS, certificates, firewalls, private endpoints, and routing.
- IAM, workload identities, KMS keys, secrets, policies, and audit logs.
- CI/CD, source repositories, artifact registries, IaC state, and configuration registries.
- Monitoring, logging, alerting, tracing, on-call rotation, and incident communication.
- External systems such as payments, email/SMS, identity providers, and partners.

Restoring only the database without encryption keys or identities authorized to read the data leaves the service inoperable. Standing up compute without queue offsets or compatible schemas can create duplicate transactions or dropped events. A dependency map and recovery sequence are mandatory.

## 2. RTO and RPO: Starting from Business Requirements

### 2.1. Recovery Time Objective (RTO)

**RTO** is the maximum target time an organization sets to restore a service or business capability after disruption, according to agreed definitions and measurement points.

Example: The Booking API must restore its ability to accept and confirm bookings within 2 hours from when the incident commander declares DR. For RTO to be meaningful, you must define:

- Does the clock start when the fault occurs, when it is detected, when the incident is confirmed, or when DR is formally triggered?
- Is the endpoint returning 200, traffic shifted, business transactions confirmed, or the entire backlog cleared?
- Is the scope the core API, the full system, or every tenant/feature?
- Under what load, region, and conditions does the RTO apply?

RTO is not just the execution time of a failover command. It can include detection, decision-making, authorization, provisioning, data restoration, consistency checks, routing cutover, warm-up, and business validation.

### 2.2. Recovery Point Objective (RPO)

**RPO** is the maximum acceptable data loss, typically expressed as the time span of newly created data that may be absent from the recovered state after an incident.

For example, a 15-minute RPO means the organization accepts potentially losing up to 15 minutes of data relative to the defined reference point. That does not mean every backup must run strictly every 15 minutes: it also depends on replication lag, log retention, incident timing, consistency, and restore mechanics.

With asynchronous replication, actual RPO can exceed zero because data committed on the primary may not have reached the replica when a region fails. With synchronous replication, RPO can approach zero for specific failure modes and conditions, at the trade-off of latency and availability during cross-region network partitions. A service does not guarantee "zero RPO" merely because it has a replica.

### 2.3. Example Service Classification

| Business Capability | Target RTO (Hypothetical) | Target RPO (Hypothetical) | Rationale |
|---|---:|---:|---|
| Create and confirm bookings | 1 hour | 1 minute | Transactions directly impact customers |
| View existing bookings | 2 hours | 15 minutes | Can temporarily degrade, but data must be accurate |
| Analytical reports | 24 hours | 24 hours | Can be regenerated from source data |
| Email notifications | 4 hours | 1 hour | Backlog can be processed after recovery |
| Internal admin portal | 8 hours | 4 hours | Temporary alternative support workflows exist |

These numbers are examples for practicing analysis. Real RTO/RPO must be approved by business owners, risk/compliance, architecture, and operations based on the BIA (Business Impact Analysis), cost, and contractual obligations.

### 2.4. RTO/RPO Must Be Measurable

~~~text
RTO_measured =
  time(service meets agreed recovery criteria)
  - time(disaster declaration / agreed start event)

RPO_measured =
  time(last recoverable consistent business state)
  - time(disaster event / agreed reference point)
~~~

During drills, record milestones: detection, DR declaration, access granted, resources ready, restore/replication complete, data validation, traffic cutover, and passing business smoke tests. For RPO, compare the last recoverable checkpoint against business logs/commit markers at the source. Without recording timestamps and reference data, an organization cannot know whether targets are met.

## 3. Four Common DR Strategies

### 3.1. Backup–Restore

In the **backup–restore** model, the standby region or environment does not keep the full workload running. When a disaster occurs, operations provision the required infrastructure, restore data from backups, configure dependencies, and shift traffic.

~~~mermaid
flowchart TB
    U[Users] --> DNS[DNS / Global Router]
    DNS --> P[Primary Region]
    P --> APP[Application + Database]
    P --> BK[Backup / Replication to DR Storage]
    BK -.-> DR[(Protected backup in recovery region)]
    DR -. restore on disaster .-> R[Recovery Region]
    R --> RAPP[Provisioned Application]
    RAPP --> RDB[(Restored Database)]
    DNS -. cutover after validation .-> RAPP
~~~

**Pros:**

- Lower baseline cost because standby compute/databases do not run continuously at production scale.
- Easy to start with when RTO allows several hours or longer.
- Recovery can be built in an isolated account/region; immutable backups help defend against deletion or ransomware.
- Suits data that can be restored from backups or regenerated from source systems.

**Trade-offs:**

- RTO includes provisioning, restoration, and testing, typically higher than strategies with warm workloads.
- Must guarantee quotas, artifacts, IaC, secrets, KMS keys, and permissions in the recovery region.
- Backups can be corrupted, inconsistent, or stale; restore tests are required.
- Data created after the backup point may be lost per RPO unless supplemented by logs/PITR/replication.

Backup–restore does not mean "copy a snapshot and turn on the app." You need a recovery plan for dependency ordering, schema migrations, endpoints, certificates, queues, workers, and external integrations.

### 3.2. Pilot Light

**Pilot light** maintains a minimal core portion of the system in the recovery region, typically replicated/pre-configured data/metadata or essential foundational infrastructure. Primary application compute is provisioned or scaled up when DR is activated.

~~~mermaid
flowchart TB
    U[Users] --> G[Global Router]
    G --> P[Primary Region: Full Stack]
    subgraph DR[Recovery Region: Pilot Light]
        DATA[(Replicated / standby data)]
        BASE[Network / IAM / Keys / Minimal Services]
        TEMPLATE[Versioned IaC + Artifacts]
        DATA --- BASE
        BASE --- TEMPLATE
    end
    P -. asynchronous replication .-> DATA
    G -. after compute scale-up and validation .-> APP[Recovery Application Fleet]
    DATA --> APP
    BASE --> APP
~~~

**Pros:** reduces preparation time because networking, identity, keys, data, or certain core services already exist; cost is typically lower than warm standby/active-active.

**Trade-offs:** requires scale/provision automation and depends on startup speed, quotas, images, configuration, and testing. Having only a database replica without pipelines, DNS, secrets, or permissions can still leave RTO long.

Pilot light fits when you want a shorter RTO than backup–restore without running full compute continuously. Clearly define what the "pilot" includes; a data replica alone does not automatically make an architecture a recoverable pilot light.

### 3.3. Warm Standby

**Warm standby** maintains a scaled-down yet operational version of the workload in the recovery region. Data is replicated or synchronized per strategy; when primary fails, standby is scaled up, validated, and receives traffic.

~~~mermaid
flowchart TB
    U[Users] --> G[Global Router]
    G --> P[Primary Region: Full Capacity]
    G -. failover .-> S
    subgraph Primary[Primary]
        P --> PA[Application Fleet]
        PA --> PD[(Primary Database)]
    end
    subgraph Standby[Warm Standby]
        S[Standby Endpoint] --> SA[Small Application Fleet]
        SA --> SD[(Replicated Standby Database)]
    end
    PD -. replication .-> SD
~~~

**Pros:** the application is already running and dependencies are verified continuously; RTO is lower than backup–restore/pilot light when data and routing are ready; can serve test traffic or read traffic per policy.

**Trade-offs:** continuous compute and standby database costs; requires maintaining version parity, replication, scale-up capacity, and preventing standby neglect. If standby is much smaller, scaling up can take time or fail to absorb production load immediately.

Warm standby is a practical choice for workloads with RTOs ranging from minutes to under an hour depending on the system, though no universal standard time applies. Only drills can verify actual RTO.

### 3.4. Active–Active

In the **active–active** model, multiple regions/sites receive and process traffic normally together. When one region fails, remaining regions continue serving or scale up capacity. Data must be designed to handle concurrent writes or have clear ownership partitioning.

~~~mermaid
flowchart TB
    U[Global Users] --> G[Global Traffic Manager]
    G --> A[Region A: Active]
    G --> B[Region B: Active]
    subgraph RA[Region A]
        A --> AA[App + Workers]
        AA --> AD[(Region A Data)]
    end
    subgraph RB[Region B]
        B --> BA[App + Workers]
        BA --> BD[(Region B Data)]
    end
    AD <-->|Replication / conflict policy| BD
~~~

**Pros:**

- Multiple regions are actively serving, reducing compute/routing switchover time when a region fails.
- Can lower geographic latency and increase aggregate throughput.
- Utilizes standby capacity even during normal operation.

**Trade-offs:**

- High cost because multiple regions run workloads and typically require continuous data synchronization.
- Harder to handle write conflicts, consistency, ordering, duplicates, and retries.
- Losing one region can double load on the remaining region; headroom is required.
- Releases, schemas, and policies must remain compatible across active versions.
- Correlated failures from shared identity, control plane, DNS, brokers, or logic bugs can still impact all regions.

Active–active does not guarantee RPO=0. If replication is asynchronous, a region may lose data committed in another region that had not yet arrived. If cross-region replication is synchronous, write latency and network-partition behavior must be evaluated carefully. You must know clearly where authoritative data is decided and how conflicts are resolved.

## 4. Comparing Strategies and Choosing by Objective

### 4.1. Qualitative Comparison Table

| Criterion | Backup–Restore | Pilot Light | Warm Standby | Active–Active |
|---|---|---|---|---|
| Compute in DR region | Not running or minimal | Minimal | Running at small scale | Production scale across multiple regions |
| Data | Backup/PITR; optional log replication | Typically replication for essential data | Continuous replication/standby | Continuous sync/replication per model |
| Relative RTO | Highest | Medium–high | Lower | Potentially lowest for routing/compute |
| Relative RPO | Depends on backup/PITR schedule | Depends on replication/logs | Depends on replication | Depends on data sync semantics |
| Baseline cost | Low | Low–medium | Medium–high | High |
| Operational complexity | Restore/runbooks | Provisioning and scale automation | Parity, replication, scale-up | Data conflicts, routing, multi-region operations |
| Neglect risk | Unrestorable backups | Pilot infra insufficient to scale | Standby version drift/under-capacity | Split-brain and correlated failures |

The RTO/RPO labels are relative, not guaranteed SLAs. Well-automated backup–restore can be faster than poorly configured pilot light; a warm standby with severe replica lag can recover worse data than a timely backup/PITR.

### 4.2. Reference Decision Matrix

| Constraint | Potentially Suitable Strategy | Questions to Verify |
|---|---|---|
| Multi-hour RTO, multi-hour RPO, cost-sensitive | Backup–restore | How long does restoring large volumes take? |
| Roughly one to a few hours RTO, want less bootstrap | Pilot light | How long do compute provisioning and validation take? |
| Minutes to under an hour RTO, need pre-running environment | Warm standby | How fast can standby scale to production load? |
| Very low RTO, continuous multi-geography serving | Active–active | Data conflicts, consistency, failover load, and cost? |
| Regenerable data, stateless compute | Backup artifacts/config + recreate | Is the authoritative data source truly independent? |
| Global write transactions, zero conflict tolerance | Consider active-passive with a single writer | Do promotion, fencing, and failover meet RTO/RPO? |

### 4.3. One Strategy Does Not Have to Fit the Entire System

A single product can use:

- Booking database: warm standby or equivalent cross-region database recovery with tight RPO/RTO targets.
- Analytics warehouse: backup–restore or data regeneration from the raw lake.
- Image/file storage: replication or backups per retention policy.
- API compute: pilot light or scale-from-zero if containers/images/config are ready.
- Notification workers: queue replication or replay from event logs/outboxes, with deduplication.
- Admin console: backup–restore if the business tolerates longer recovery.

Strategies should be assigned by **business capability and data criticality**. Using the most expensive strategy everywhere wastes budget; using the cheapest everywhere can leave core business flows unable to meet RTO/RPO.

## 5. Backup: Designing Recoverability, Not Just Copies

### 5.1. Backup Types

| Type | Description | Best Suited For |
|---|---|---|
| Full backup/snapshot | Complete capture per service mechanism | Recovery baseline, clone/restore |
| Incremental backup | Stores only changes since the previous point | Saving time and storage compared to repeated fulls |
| Point-in-time recovery (PITR) | Restores to any timestamp within log retention | Recovering after accidental deletes/edits |
| Transaction log/WAL backup | Stores change logs to recover to a point | Databases needing lower RPO than full backup cadence |
| Object versioning | Retains multiple object versions | Recovering overwritten/deleted files per service capability |
| Immutable/offline backup | Copies with delete/retention locks or isolated from source | Defending against accidental deletion, compromise, and ransomware |

Not every database or object store supports the same mechanisms; feature names and limits depend on provider, tier, engine, and region. Verify backups are stored in an appropriate failure domain/credential boundary, with recoverable encryption keys, and cannot be deleted alongside the source account.

### 5.2. Backup Protection Rules

- **Separation of privileges:** application operations accounts must not have default permission to delete all backups.
- **Separation of failure domains:** store copies in a separate region/account/project or vault per the threat model.
- **Immutable/retention locks:** use when protecting against deliberate deletion; understand lock durations and exception procedures.
- **Encryption and key recovery:** protect backups with keys while maintaining key recovery procedures, decrypt permissions, and break-glass controls.
- **Catalog and inventory:** track which database/dataset each backup belongs to, timestamp, type, key, retention, and test status.
- **Monitoring:** alert on backup failures, missing coverage, anomalous sizes, or policy deletions.
- **Restore testing:** periodically restore into an isolated environment and verify data and applications.

A backup encrypted with a lost or permanently disabled KMS key may be unusable. A separate backup copy lacking metadata, schemas, logs, or documentation to read it may likewise fail recovery objectives.

### 5.3. Backup Consistency

Backups must represent a usable data state. A single database snapshot may be consistent per database semantics, yet backing up a database, object storage, and queue simultaneously does not automatically form a distributed transaction.

For example, a booking writes to the database, emits an event, and stores an attachment:

- The database snapshot includes the new booking.
- The object storage backup does not yet contain the attachment.
- The event backup may contain or lack the corresponding message.

Upon restore, the application may encounter references to missing files or send duplicate notifications. Define consistency boundaries: transaction/outbox, checkpoints, manifests, event versions, object versions, and reconciliation workflows.

### 5.4. Retention and Backup Schedules

Design retention based on:

- RPO and data classification.
- Legal/contractual obligations and legal holds.
- Late corruption detection; retain historical points long enough.
- Storage capacity/cost and storage tiers.
- Recoverability within backup/log chains.
- Personal data deletion policies and derived copies.

Keeping backups for 35 days does not mean up to 35 days of data can be lost; RPO depends on backup frequency/log replication. Conversely, hourly backups kept for only 2 hours are insufficient when corruption is discovered days later. Schedules and retention must be designed together.

## 6. Restore and Data Verification

### 6.1. Reference Restore Procedure

1. Identify the incident, blast radius, last known clean data point, and business owner.
2. Select the recovery strategy and restore target; isolate from the broken system.
3. Verify backup ID, timestamp, checksum/manifest, encryption keys, schemas, and permissions.
4. Provision required networking, storage, compute, and identity.
5. Restore databases/objects/tables in dependency order; apply logs/PITR if needed.
6. Run integrity checks, count/sum reconciliation, relationship checks, and business data validation.
7. Start consumers/jobs under control; deduplicate or replay messages per policy.
8. Smoke test business flows and security; confirm no accidental calls to old production endpoints.
9. Update routing after approval; observe SLIs and backlog.
10. Record results, timings, actual RPO/RTO, and deviations.

### 6.2. Do Not Confuse "Restore Succeeded" with "Service Recovered"

| Verification Layer | Example Evidence |
|---|---|
| Backup artifact | ID, timestamp, checksum, encryption/key metadata |
| Database | Instance online, correct schema, valid integrity/constraints |
| Data | Record counts, key ranges, reconciliation, last committed marker |
| Application | Health/readiness, startup, working connections and secrets |
| Business | Test booking create/lookup/cancel per policy without creating unintended real records |
| Integrations | Queues, events, payment sandbox/provider policies, callbacks |
| Security | IAM/tenant access, auditing, network boundaries, and encryption |
| Operations | Working dashboards, alerts, runbooks, and on-call routing |

Restore tests should use production-like data and scale; a 1 GB database restoring quickly does not prove a 20 TB database meets RTO.

### 6.3. Clean-Room Recovery

If the disaster involves account compromise or ransomware, restoring into the same environment may reintroduce malware, exposed credentials, or malicious configuration. **Clean-room recovery** stands up an isolated recovery environment using verified artifacts/baselines, fresh credentials, and validated immutable backups.

Steps to consider:

- Create accounts/projects and networks from trusted IaC sources.
- Verify images/container artifacts, dependencies, and pipelines.
- Rotate potentially compromised secrets/keys/tokens; revoke old credentials.
- Restore data from a clean pre-incident point and scan for malware/corruption per procedure.
- Allow connections only to essential dependencies; restrict egress.
- Test and verify security before opening traffic.

Clean-room recovery may increase RTO yet reduces the risk of reinfection or reusing compromised configurations. It is a specific requirement to weigh for the threat model, not a substitute for every zone outage.

## 7. Replication, Consistency, and Write Ordering

### 7.1. Synchronous vs. Asynchronous

| Mechanism | Behavior | Benefits | Trade-Offs |
|---|---|---|---|
| Synchronous replication | Commit waits for replica acknowledgment per engine semantics | Can reduce data loss under certain failure models | Increases latency, network-dependent; can impact availability |
| Asynchronous replication | Primary commits first, replica receives later | Lower commit latency and better tolerance for network delay | Replica lag, RPO greater than zero |
| Semi-synchronous/quorum | Waits for a subset of acknowledgments or intermediate condition | Balanced depending on engine/deployment | Complex semantics; must read exact service guarantees |
| Log shipping | Ships transaction logs to apply elsewhere | Can achieve small RPO and preserve log points | Lag/apply rate and promotion procedure |
| Snapshot replication | Copies data at point-in-time snapshots | Simple for certain datasets | Latency and changes lost since the last snapshot |

Do not infer RPO solely from words like "synchronous" or "cross-region." Read the failure model: when does the primary confirm a commit, how many replicas must ack, how are network partitions handled, which transactions are protected, and how does failover select a node.

### 7.2. Replica Lag

**Replica lag** is the delay between a change at the source and when the replica can serve that change. It can be measured in time, log position, byte/transaction backlog, or database-provided metrics.

Lag increases due to networking, throughput limits, workload spikes, apply conflicts, slow storage, or under-provisioned replicas. In DR, lag directly affects RPO and promotion correctness.

Example:

~~~text
Primary last committed marker: 12:00:00
Standby last applied marker:   11:59:42
Observed lag:                  18 seconds
~~~

If the primary is lost right at 12:00, the standby may miss transactions within the lag window depending on engine and commit semantics. Never treat a pre-incident lag measurement as absolute proof; monitor continuously and verify the final marker at promotion time.

### 7.3. Split-Brain and Fencing

**Split-brain** occurs when two regions both believe they are primary/leader and both accept writes. When connectivity splits, unilateral promotion on each side can create two divergent data histories.

Mitigations:

- Have an unambiguous mechanism to decide writer/leader authority.
- Use quorum/lease/epoch or fencing tokens per platform capabilities to block old writers.
- Never rely solely on DNS redirection; existing connections may remain active.
- Promote standby only after confirming the old primary can no longer write or isolation is enforced.
- Record generations/epochs so stale requests/workers cannot continue writing after role transitions.
- Maintain a runbook for indeterminate primary states; prioritize data safety over automatically creating two writers.

Fencing is a critical requirement in many active-passive and database failover designs. Specific implementation varies by database/cloud service; DNS, load balancers, or health states do not automatically provide fencing.

### 7.4. Active–Active and Conflict Resolution

If two regions write data simultaneously, choose a strategy:

- **Partitioned ownership:** each tenant/entity has only one writer region at a time.
- **Single-writer, multi-reader:** multiple regions read, while only one location performs authoritative writes.
- **Conflict-free/CRDT or merge logic:** use only when the data model and business domain support meaningful merges.
- **Optimistic conflict detection:** store versions/ETags and require clients to resolve conflicts.
- **Application-level reconciliation:** detect competing updates and resolve via business rules.

Never default to resolving conflicts with "newest timestamp wins." Clocks across regions can drift; a later timestamp is not necessarily more business-accurate. For exclusive bookings, two regions confirming the same slot and merging via last-write-wins can violate invariants.

## 8. Designing Failover and Failback

### 8.1. Failover Is a Gated Process

Failover shifts serving capability from the primary environment to the recovery site/region. A safe process requires:

1. Detecting and confirming an incident exceeding HA scope.
2. Assessing impacted scope, data, and dependencies.
3. Authorized DR declarer/incident commander activating the runbook.
4. Fencing or isolating writers/traffic at the source per design.
5. Determining the final data point and deciding whether actual RPO is acceptable.
6. Promoting/restoring databases and dependencies.
7. Starting/scaling applications, workers, and integrations.
8. Running integrity, security, and business smoke tests.
9. Switching global routing/DNS/traffic per policy.
10. Communicating status and monitoring SLIs/capacity in the new region.

Never auto-failover an entire region based on a single failing health probe. Probes can false-positive or test only application endpoints without reflecting data health. Require multiple signals and decisions proportional to impact.

### 8.2. Active-Passive Failover Diagram

~~~mermaid
sequenceDiagram
    participant Mon as Monitoring
    participant IC as Incident Commander
    participant Prim as Primary Region
    participant DR as Recovery Region
    participant GTM as Global Traffic Manager
    Mon->>IC: Region outage / SLI breach
    IC->>IC: Confirm DR criteria and declare
    IC->>Prim: Fence old writer / isolate if reachable
    IC->>DR: Verify replica or restore point
    DR-->>IC: Data point, lag and readiness evidence
    IC->>DR: Promote writer / start workloads
    DR-->>IC: Integrity + business smoke tests pass
    IC->>GTM: Approve traffic cutover
    GTM-->>DR: Route new traffic
    IC->>Mon: Observe SLI, errors and capacity
~~~

If the primary is unreachable for fencing, a quorum/lease mechanism or other authoritative evidence is needed. Declaring a primary dead based solely on one client's timeout does not guarantee the primary isn't still accepting writes from other clients.

### 8.3. DNS and Global Routing

Global traffic managers can use health checks, weighted/priority routing, latency/geographic policies, or failover policies. DNS-based failover must account for:

- Resolvers/clients caching DNS per TTL or custom policies.
- Long-lived connections/connection pools continuing to use old endpoints.
- DNS updates not guaranteeing every client switches immediately.
- Health checks verifying appropriate endpoints and readiness; routing layers do not verify data consistency.
- During cutover, certificates, CORS, callback URLs, allowlists, and external webhooks may need updating.

Plans should measure actual resolver/client convergence times and include retry/reconnect mechanisms. Never promise "instant" failover simply by setting a very low TTL.

### 8.4. Failback

Failback shifts the service back to the original site/region or a new primary after the incident is resolved. It is a data and routing change carrying risks similar to a migration:

1. Investigate the old primary's root cause; confirm the underlying fault is gone.
2. Keep a single writer in the currently active region.
3. Synchronize/reconcile data back to the intended return location.
4. Verify replica lag, schemas, and key/version compatibility.
5. Fence the old writer role; determine the new promotion moment.
6. Test under low traffic or in staging; verify routing and integrations.
7. Shift traffic under control, observing SLIs and rollback criteria.
8. Scale down the serving region only after confirming system stability.

Never fail back solely because the old primary looks green. If new data was created in the DR region, routing back without syncing can lose every transaction created during the disaster.

## 9. Recovery Dependencies and Recovery Order

### 9.1. Dependency Map

For each component, document:

| Component | Dependencies to Restore | Questions |
|---|---|---|
| Network/VPC/subnet | CIDRs, routes, private endpoints, firewalls, DNS | Are there CIDR conflicts or routes pointing to the old region? |
| Identity/IAM | Workload roles, federated identity, admin access | Who can grant permissions when the primary IdP fails? |
| KMS/secrets | Key replicas, decrypt permissions, secret versions | Can backups be decrypted and apps started? |
| Database | Backups/logs/replicas, schemas, endpoints | Which data point is selected and who promotes? |
| Object storage | Object versions, replication, lifecycle | Are all objects, metadata, and permissions present? |
| Queue/event | Topics, subscriptions, offsets, retention, DLQs | Are messages missing/duplicated and what is the replay method? |
| Compute | Images, artifacts, config, quotas | Are versions reproducible and quotas sufficient? |
| DNS/certificate | Domains, records, TLS certs, external allowlists | Can clients/partners connect? |
| Observability | Dashboards, alerts, logs, tracing, on-call | Can the DR site be monitored externally? |
| External providers | Payments, email, identity, webhooks | Do endpoints/credentials/allowlists match the new region? |

### 9.2. Recovery Order

A common sequence:

~~~mermaid
flowchart TD
    A[Declare DR / isolate incident] --> B[Recover access, account and keys]
    B --> C[Network, DNS prerequisites and security boundary]
    C --> D[Restore / promote data services]
    D --> E[Validate consistency and data integrity]
    E --> F[Start compute and application dependencies]
    F --> G[Start workers, schedules and integrations carefully]
    G --> H[Business smoke tests and security checks]
    H --> I[Traffic cutover]
    I --> J[Monitor, reconcile and stabilize]
~~~

This is a logical ordering, not a rigid universal runbook. Some control services may need to start before databases; queue workers should usually stay paused until offsets/deduplication and data states are verified. Prepare DNS early, but cut over only after validation.

### 9.3. Prioritizing Recovery by Business Need

Not every feature needs to recover simultaneously. Define:

- **Minimum viable service:** the minimum flows required for the business to keep operating.
- **Tier 0 dependencies:** identity, networking, keys, DNS, or control plane needed first.
- **Tier 1 workloads:** core transactions and authoritative data.
- **Tier 2 workloads:** lookups, notifications, operational support.
- **Tier 3 workloads:** reporting, analytics, deferrable background tasks.

The order must avoid corrupting data. For instance, the booking API can open before email workers recover if outboxes/events are durably stored and backlogs are controlled. However, never open writes before booking data is properly promoted.

## 10. Security in Disaster Recovery

### 10.1. DR Must Not Weaken Security

Pressure to recover quickly easily leads to dangerous shortcuts: opening databases publicly, using shared admin accounts, disabling MFA, bypassing tenant authorization, or copying long-lived secrets. DR plans must define emergency permissions before an incident occurs.

Principles:

- Enforce least privilege; separate DR operators, data restore operators, and security approvers.
- Break-glass accounts require MFA, time limits, auditing, approval, and post-incident revocation.
- Never store secrets inside backup scripts, runbooks, or output logs.
- KMS keys and decrypt permissions must have controlled recovery/replication paths.
- Keys/certificates/credentials assessed as potentially exposed during an incident must be rotated.
- The restore environment requires network segmentation, private access, and egress allowlists.
- Audit logs and critical backups need protection against deletion/modification outside application control.

### 10.2. Ransomware and Immutable Backups

If attackers gain production admin privileges, they may try to delete snapshots, keys, backup vaults, or copies in the same account. Risk mitigations:

- Separate backup accounts/security boundaries and restrict cross-account permissions.
- Use immutable retention or vault locks where appropriate.
- Protect control planes and admin credentials with MFA/approvals.
- Monitor mass deletions, retention changes, disabled backups, and key policy edits.
- Drill clean-room restores from verified backups rather than trusting artifacts touched by the incident.

Immutability can make legitimate deletions or mistake corrections harder during the lock period; design retention/legal holds and operational procedures accordingly.

### 10.3. Privacy and Data Residency

When copying data to a DR region, compliance with data residency regulations, contracts, and access controls still applies. Replication to another region is not automatically permitted simply because it is for DR. Specify which data is replicated, which must be encrypted/anonymized, who can access it, and how long backups are retained.

## 11. DR Drills and Plan Validation

### 11.1. Why Drills Are Essential

A runbook may look sound on paper yet fail because:

- Credentials expired or the on-call engineer lacks permissions.
- DR region quotas are insufficient or services are not enabled.
- Backups are missing objects, keys, or logs.
- IaC drifted or images are no longer accessible.
- DNS/provider webhooks still point to old endpoints.
- Replica lag exceeds RPO.
- Database restore runs longer than expected.
- Dashboards/alerts depend on the failing primary region.

Only **restore tests, failover drills, and measured exercises** prove capability. "Backup job success" is not a DR pass criterion.

### 11.2. Drill Levels

| Level | Approach | Objective | Risks |
|---|---|---|---|
| Tabletop | Discuss scenarios, roles, decisions, and communications | Spot runbook/authority gaps | Little technical evidence |
| Backup restore test | Restore copies into an isolated environment | Test backup usability and duration | Consumes compute/storage; can impact source if misconfigured |
| Component failover | Simulate database/zone/queue loss in test | Validate individual mechanisms | May impact shared dependencies |
| Regional DR drill | Trial workload cutover to the standby region | Measure end-to-end RTO/RPO | Complex; requires clear scope/stop conditions |
| Game day / chaos | Controlled fault injection by hypothesis | Test response and self-healing | Execute only with guardrails and clear blast radius |

### 11.3. Sample Drill Scenario

**Context:** Booking API in Region A cannot serve traffic; primary database is down. Region B holds a warm standby with asynchronous replication. Hypothetical targets: RTO 60 minutes, RPO 5 minutes.

| Step | Activity | Evidence to Record |
|---|---|---|
| 1 | Confirm incident and declare DR | Timestamp, decision-maker, scope |
| 2 | Inspect standby, replica lag, and data markers | Last applied transaction/marker |
| 3 | Fence primary or verify dual-write prevention | Evidence old writer can no longer accept writes |
| 4 | Promote standby | Timestamp, new role/generation |
| 5 | Verify schemas, booking counts, invariants, and outboxes | Reconciliation report |
| 6 | Start APIs/workers and secrets | Health, IAM, dependency tests |
| 7 | Shift traffic to Region B | DNS/GTM convergence, request success |
| 8 | Create/look up test bookings in a test tenant | Business smoke tests, audit |
| 9 | Monitor errors, p95, backlog, and capacity | Dashboards, alerts, queue age |
| 10 | Compute RTO/RPO and record lessons learned | Timeline and action owners |

If measured RTO is 78 minutes or RPO is 9 minutes, do not alter the report to "meet target." Document the gap and decide: increase replication, pre-provision compute, improve automation, negotiate business-accepted targets, or invest in a different strategy.

### 11.4. Success Criteria

- Both authorized DR declarers and actual technical access are available.
- The recovery site can launch within approved quotas and policies.
- Data meets RPO and integrity checks.
- Single writer/leader enforced, no split-brain.
- Minimum viable business flows operate and security controls remain intact.
- Traffic is shifted and clients can connect within RTO.
- Monitoring/alerting and on-call work at the recovery site.
- Failback or long-term post-DR operation has a concrete plan.
- Discovered issues have owners, deadlines, and closure evidence.

## 12. Cost Estimation and Total Cost of Ownership

### 12.1. Cost Components

| Component | Backup–Restore | Pilot Light | Warm Standby | Active–Active |
|---|---|---|---|---|
| Idle compute | Low | Low | Medium | High |
| Database/replicas | Backup/storage, optional logs | Data replicas/standby | Continuously running standby | Multiple active nodes/regions |
| Storage/backup | Medium, per retention | Backup + replication | Backup + replication | Multi-region replication and backup |
| Network/egress | During backup/restore | Continuous or periodic | Continuous replication | Continuous inter-region traffic |
| Testing/automation | Restore drills needed | Provision/scale drills | Failover/scale-up drills | Conflict/failover/load drills |
| Operations | Few running parts, complex restore | Orchestrating provisioning | Maintaining parity/lag/capacity | High, multi-region and consistency |

### 12.2. Qualitative Example

Suppose a production database and application cost \$10,000/month in a single region. DR options cannot be naively estimated as:

- Backup–restore: "\$0" because backup storage, transfer, vaults, testing, and labor still cost money.
- Pilot light: "10%" because certain databases/replication/keys/networking and minimal services run continuously.
- Warm standby: "50%" if compute is small while databases/replicas account for most of the cost.
- Active–active: "100% extra" is only a rough guess; regional traffic splits, data transfer, licensing, backups, and surge capacity alter actual costs.

For real budgeting, use provider pricing by region/discounts, storage classes, I/O, backup retention, inter-region transfer, requests, licenses, monitoring, and support. Add drill costs and operational staffing capacity.

### 12.3. Optimizing Cost Without Sacrificing Recoverability

- Select strategies per data/workload tier.
- Use elastic compute in pilot light/warm standby, while preserving measured quotas and scale times.
- Use lifecycle rules to move infrequently accessed backups to appropriate storage tiers after verifying restore times.
- Avoid replicating every data category if data is regenerable; keep complete sources and proof.
- Schedule restores/drills, budget for them, and clean up test resources afterward.
- Track backup/replica/egress costs by service owner.
- Never cut retention or disable automated backups merely to stay under monthly budget without formal risk approval.

## 13. Common DR Mistakes

| Mistake | Consequence | How to Improve |
|---|---|---|
| Having backups without testing restores | Copies may be incomplete, corrupted, or unreadable | Restore drills and integrity checks |
| Deriving RPO from backup cadence while ignoring lag/logs | Greater data loss than expected | Measure recoverable commit markers/replica lag |
| Restoring only the DB | APIs lack keys, secrets, queues, DNS, or permissions | Dependency map and end-to-end smoke tests |
| Active-passive where both accept writes | Split-brain, divergent data | Fencing, quorum/leases, and single writer |
| Treating low DNS TTL as instant failover | Clients keep using cached/existing connections | Measure resolver/client convergence |
| Failing to update warm standby | Version/schema/config drift from primary | Drift scans and parity checks |
| Under-provisioned standby capacity | Traffic shifts and the system crashes under load | Load testing and post-incident headroom |
| Replicating everything including logic errors | Corruption/accidental deletes spread to DR | Immutable backups, PITR, and clean-room |
| Failing back without syncing deltas | Transactions created in DR are lost | Reconcile, reverse sync/fix-forward, fencing |
| DR operators lack permissions during an incident | Delayed access and blocked recovery | Break-glass drills, time-bound permissions |
| Plan owned solely by infrastructure team | Business unaware of downtime/loss thresholds | Business owner approves BIA/RTO/RPO |
| Tabletop exercises only | Quotas, restore speeds, and DNS limits go undiscovered | Periodic technical restore/failover tests |

## 14. Practice Exercise: Selecting and Drilling DR for a Booking Platform

**Scenario:** A booking SaaS platform runs in Region A. Components include a Booking API, relational database, notification queue, object storage holding files, dashboard, and analytics warehouse. The primary region has 2 availability zones. The organization can deploy into Region B while balancing cost.

Hypothetical business requirements:

- Core booking create/read: RTO at most 60 minutes, RPO at most 5 minutes.
- Email notifications: 4-hour RTO; delays are acceptable, duplicates are not.
- Analytics: 24-hour RTO; rebuilding from source data is acceptable.
- Customer data must be encrypted and comply with region/retention policies.
- Failover must never allow both regions to confirm the same slot.

Complete these deliverables:

1. **BIA and dependency map:** classify business functions, owners, impacts, Tier 0/1/2 dependencies, and RTO/RPO measurement points.
2. **Compare the four strategies:** backup–restore, pilot light, warm standby, active–active; select options per layer for Booking DB, API, queues, object storage, and analytics.
3. **Backup design:** full/incremental/PITR schedules, log retention, immutable vaults, regions/accounts, KMS, retention, and restore tests.
4. **Replication/data consistency:** measure replica lag, identify writer, fencing, events/outbox, queue replay, and deduplication.
5. **Failover runbook:** who declares, required permissions, restore/promotion sequence, data checks, smoke tests, routing, and traffic-opening criteria.
6. **Failback:** delta sync method, maintaining a single writer, cutover, and rollback/fix-forward.
7. **Security/clean-room:** backup protection, credential rotation, network isolation, and account-compromise recovery.
8. **DR drill:** build a simulated timeline, record timestamps, compute actual RTO/RPO, identify gaps, and assign action owners.
9. **TCO:** estimate compute, database standby, storage, replication, egress, backups, testing, and operations.
10. **Well-Architected review:** list risks and corresponding evidence for each pillar.

### Sample Decision Table

| Component | Recommended Strategy | Target | Verification |
|---|---|---|---|
| Booking DB | Warm standby or equivalent managed DR option | RPO ≤ 5 minutes (hypothetical) | Replica lag, promotion, and consistency |
| Booking API | Pilot light/warm standby depending on RTO | RTO ≤ 60 minutes | Provision/scale and business smoke tests |
| Notification | Queue/outbox backup + deduplicated replay | 4-hour RTO | Duplicate/replay tests |
| Object storage | Cross-region replication + versioned/immutable backups per data | Per retention and business rules | Object inventory, checksums, restores |
| Analytics | Backup–restore or rebuild from raw | 24-hour RTO | Rebuild completeness and report validation |

### Drill Timeline Table

| Milestone | Timestamp | Accountable Owner | Evidence |
|---|---|---|---|
| Incident detected | Fill during drill | Operations | Alerts/events |
| DR declared | Fill during drill | Incident commander | Decision log |
| RPO/replica verified | Fill during drill | DBA/Data owner | Commit markers/lag |
| Writer fenced | Fill during drill | Database/Platform | Role/epoch evidence |
| Data restored/promoted | Fill during drill | Data recovery owner | Restore logs |
| Business tests passed | Fill during drill | Product/QA | Test booking results |
| Traffic cutover | Fill during drill | Network/Platform | DNS/GTM observations |
| Service meets criteria | Fill during drill | Service owner | SLIs and dashboards |

**Completion criteria:** Another on-call engineer can use the documentation to choose the right strategy, recover in the right order, prove data meets RPO, bring the business back within RTO, and perform failback without creating dual writers or losing transactions.

## 15. Well-Architected Evaluation

| Pillar | DR Questions | Evidence |
|---|---|---|
| **Operational Excellence** | Are runbooks, permissions, owners, contacts, and drills maintained? | Tabletops, drill timelines, action tracking, automation |
| **Security** | Are immutable backups, IAM/KMS, clean-room, and break-glass secure? | Restore tests, access reviews, audits, key recovery drills |
| **Reliability** | Are RTO/RPO met, and are dependencies and failover/failback verified? | Restore/failover/failback exercises, integrity checks |
| **Performance Efficiency** | Does standby have enough capacity and scale up in time? | Load tests, scale times, latency, queues/backlog |
| **Cost Optimization** | Are replication/standby/backup costs proportional to business tier? | DR TCO, cost allocation, utilization |
| **Sustainability** | Are idle standby compute and unnecessary retention avoided? | Utilization, lifecycle, backup policy reviews |

A sound DR model is an intentional choice between tolerable disruption/data loss and the cost of reducing those two risks. Not every component needs active–active; nor can backup–restore serve a business flow with a few-minute RTO without proving restore and bootstrap speed.

## 16. Summary Takeaways

- **RTO** addresses service recovery time; **RPO** addresses tolerable data loss. Both must have clear start/end points and measurement methods.
- **Backup–restore** has low baseline cost yet typically long RTO; **pilot light** pre-provisions core pieces; **warm standby** runs a scaled-down workload; **active–active** serves concurrently at higher data and operational complexity.
- **Backups are insufficient without restore tests.** Protect copies, keys, metadata, and permissions, and validate data/business flows.
- **Replication does not guarantee consistency.** Understand lag, commit semantics, writers, fencing, and conflicts.
- **Failover encompasses data, dependencies, applications, routing, and operators.** DNS is only one piece of the process.
- **Failback is a controlled data/routing migration**, not simply switching traffic back to the old primary.
- **Drills and measurements are proof of DR capability.** Record actual RTO/RPO, gaps, owners, and due dates.
- **Select strategies per capability and data tier**, rather than forcing one most-expensive or cheapest pattern onto the whole system.

Disaster recovery design starts from the disruption and data loss the business can accept, and only then selects backup, replication, pilot light, warm standby, or active–active. An architecture is trustworthy only when the recovery region has the necessary data, permissions, keys, compute, networking, and dependencies; failover/failback procedures have been drilled; and measured results prove the system meets its committed targets.
