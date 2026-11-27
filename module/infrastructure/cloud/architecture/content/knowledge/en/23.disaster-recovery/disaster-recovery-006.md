# Designing Failover, Routing, and Recovery Orchestration

## 1. Disaster Recovery Is an Architectural Process, Not a Button

Disaster recovery (DR) is the capability to restore applications, data, and business operations after a severe incident. Incidents can start from a server, availability zone (AZ), region, provider, configuration error, ransomware, network outage, or operational action that corrupts data. A DR plan only has value when the organization knows how to accurately detect an incident, decide whether to fail over, prevent the old system from continuing to write, restore data and dependencies, route users to the alternate environment, and verify that business flows actually work.

**Failover is not simply switching DNS or promoting a database replica.** If traffic shifts to a new region while secrets, KMS keys, queues, identity providers, object storage, network routes, or capacity are not ready, the application can still remain down. If the old primary is not fenced, two regions can both accept writes and create split-brain. If a replica is asynchronous, transactions already acknowledged in the old region may not yet exist in the new region.

In the **CLOUD_ARCHITECTURE** module, DR design must connect business requirements with failure domains, replication, orchestration authority, routing, backups, security, and operability. The goal is recovering in the right order, within committed RTO/RPO, at a sustainable cost and complexity level following a Well-Architected mindset.

After this lesson, you will be able to:

- Distinguish backups, high availability, disaster recovery, failover, and failback.
- Identify failure domains, blast radius, RTO, and RPO for each workload.
- Design processes for incident detection, assessment, approval, and DR activation.
- Orchestrate the sequence of fencing, data recovery, dependency recovery, and traffic cutover.
- Select global routing, DNS, load balancers, service discovery, and endpoint strategies.
- Handle asynchronous data, replication lag, replay, and split-brain.
- Build runbooks, automation, game days, and DR exit criteria.

## 2. Distinguishing HA, Backup, and DR

Related concepts that do not replace one another:

| Concept | Question It Answers | Examples |
| --- | --- | --- |
| High availability (HA) | How do we keep serving when a small component/failure domain fails? | Multiple instances, multi-AZ database, load balancer health checks |
| Backup/recovery | How do we restore data to a state prior to an error or accidental deletion? | Snapshots, point-in-time recovery, immutable backups |
| Disaster recovery | How do we restore services when a large failure domain is lost? | Standby region, cross-region backup restore, DR orchestration |
| Failover | How do we shift the active role to an alternate environment? | Promote replica, open new writer endpoint, route traffic |
| Failback | How do we return to the chosen operating model after the old environment recovers? | Re-synchronize data, controlled writer handoff |

Multi-AZ typically reduces recovery time for node or AZ failures, yet does not necessarily protect against losing an entire region, logical data deletion, or admin account compromise. Replication can also copy accidental deletions; hence independent backups, retention, and restore tests remain essential.

## 3. Defining Failure Domains and Blast Radius

Before choosing a topology, identify which incidents the DR plan must address. A region may still be up while a control service, DNS, KMS, or network path fails. Conversely, an application may fail due to a bad deployment while underlying infrastructure remains healthy.

### 3.1. Incident Matrix

| Failure Domain | Symptoms | Initial Response |
| --- | --- | --- |
| Process/container/VM | Unhealthy instances, crash loops, lost nodes | Restart/reschedule or replace instances |
| AZ | Widespread network/storage/compute outage in one AZ | In-region HA; shift workloads to other AZs |
| Region | Multiple services in a region unreachable or severely degraded | Trigger regional DR procedure |
| Provider/control plane | Management APIs, identity, or foundational services affected | Verify control capability from another region/provider |
| Network/edge/DNS | Users cannot reach endpoints even though backends are healthy | Diagnose routing paths, resolvers, and health probes |
| Data corruption/ransomware | Corrupted or widely encrypted data | Halt risky writes, preserve evidence, and recover from clean sources |
| Identity/KMS compromise | Credentials/keys leaked, disabled, or inaccessible | Revoke credentials, restore trust/keys per security procedure |
| Human/configuration error | Routes, policies, firewalls, or databases misconfigured | Roll back configuration, inspect audits, and assess impact scope |

Not every regional error requires failover. Failing over when only a local dependency fails can widen blast radius, cause data loss, or overload the standby environment.

### 3.2. DR Scope per Application

For each application, identify mandatory components to complete the business journey:

- Entry points: DNS, CDN, WAF, global load balancer, and API gateway.
- Compute: VMs, Kubernetes, serverless, autoscaling groups, and images/artifacts.
- Data: databases, object/file storage, caches, and search indexes.
- Messaging: queues, streams, schedulers, and dead-letter queues.
- Identity/security: IAM, secret manager, KMS, certificates, and federation.
- Networking: VPC/VNet, subnets, routes, firewalls, NAT, private endpoints, and DNS.
- Operations: monitoring, logging, tracing, deployment pipelines, and automation.

A service's DR is complete only when required dependencies work and business flows complete end-to-end, not merely when a health endpoint returns HTTP 200.

## 4. RTO, RPO, and Recovery Objectives

Two foundational metrics:

- **RTO (Recovery Time Objective):** the target maximum time to restore a service or business capability after a disruption.
- **RPO (Recovery Point Objective):** the maximum tolerable data loss, typically expressed as a time interval or transaction checkpoint.

RTO/RPO must be approved by business owners according to criticality. Avoid setting a single identical value for the entire system.

### 4.1. Workload Classification

| Illustrative Tier | Recovery Target | Example Workloads |
| --- | --- | --- |
| Tier 0 – Critical | RTO of a few minutes or lower; near-zero RPO per platform capabilities | Ledgers, core checkout, identity for purchase journeys |
| Tier 1 – Essential | RTO around one hour; approved short RPO | Order management, inventory projection |
| Tier 2 – Important | Multi-hour RTO; bounded data-loss window acceptable | Reporting, search indexes, dashboards |
| Tier 3 – Deferred | Longer RTO; data regenerable or recoverable in batches | Sandboxes, caches, test data |

These milestones only illustrate tiering. Actual RTO/RPO depend on contracts, business impact, technical feasibility, and budget.

### 4.2. RTO Must Account for the Entire Chain

**Total RTO = detection + decision + fencing + data recovery/promotion + dependency recovery + traffic cutover + business validation.**

For example, if database promotion finishes in 3 minutes yet DNS caches, secrets, workers, and queues take another 25 minutes, business RTO is not 3 minutes. Measure each stage and identify which parts can run in parallel.

### 4.3. RPO Must Tie to Write Semantics

With asynchronous replication, RPO depends on logs not yet shipped or durably persisted in the standby region when failure strikes. Average lag is insufficient to commit an RPO; track tail lag, replication backlog, and link outage durations. With synchronous/quorum replication, verify ACK conditions and replica failure domains.

Beyond replication, define RPO for queues, object uploads, file shares, analytics, and configuration. A database with near-zero RPO paired with an unreplicated queue can leave accepted work unprocessed after DR.

## 5. DR Strategies and Costs

No single topology is optimal for every workload. Strategies are commonly arranged from minimal pre-provisioning to high readiness:

| Strategy | Description | Relative RTO/RPO | Cost/Complexity |
| --- | --- | --- | --- |
| Backup and restore | Backups stored in another failure domain; provision infra and restore when needed | Longer RTO; RPO per backup/log archive schedule | Lower standby cost; restore and capacity must be prepared |
| Pilot light | Core data/security/foundational components maintained; primary compute created on DR | Medium RTO; RPO depends on replication/backups | Medium cost; relies on automation and provisioning |
| Warm standby | DR environment runs at reduced capacity with replicated data | Shorter RTO; RPO depends on replication | Costs standby compute and parallel operations |
| Hot standby / active-passive | Standby region nearly full-ready, only one side serves primary writes | Lower RTO; RPO can be very low with proper design | High cost and requires failover/failback orchestration |
| Active-active | Multiple regions serve traffic concurrently; data distributed/synced per semantics | Can reduce traffic shift, yet conflicts and recovery are complex | Highest cost and complexity in many cases |

Names vary across providers. Evaluate which components actually run, how data synchronizes, how much spare capacity exists, and which steps remain manual.

### 5.1. Selecting a Strategy by RTO/RPO

~~~mermaid
flowchart TB
    Start["Business requirements and RTO/RPO"] --> RTO{"Can RTO be measured in hours?"}
    RTO -->|Yes| Backup["Backup and restore"]
    RTO -->|No| Warm{"Can wait for compute provisioning?"}
    Warm -->|Yes| Pilot["Pilot light"]
    Warm -->|No| Standby{"Need capacity ready immediately?"}
    Standby -->|Single writer| Hot["Warm / hot standby"]
    Standby -->|Serve multiple regions| Active["Active-active"]
    Backup --> Validate["Test restore and dependencies"]
    Pilot --> Validate
    Hot --> Validate
    Active --> Validate
~~~

The diagram is a discussion starting point, not a rigid rule. Active-active does not automatically deliver better RTO/RPO if conflict resolution, identity, queues, or routing are not designed properly.

## 6. Incident Detection and Triggering DR

Fault detection and failover decisions are two distinct steps. A failing health check may reflect a single node or route error; it is insufficient to conclude an entire region is unavailable. Overly sensitive automatic failover can trigger unnecessary cutovers or split-brain.

### 6.1. Combining Multiple Signals

| Signal | What to Confirm |
| --- | --- |
| Synthetic transactions | Are business journeys failing from multiple vantage points? |
| Service health | Are APIs, databases, queues, identity, and storage genuinely unavailable? |
| Network reachability | Is one route, one ISP, or all paths to the region down? |
| Provider status | Is there a service/region incident notice and what is its impact scope? |
| SLO/error budget | Do errors breach the agreed incident/DR trigger threshold? |
| Data replication | Are replicas keeping up, or are there apply errors or abnormal backlogs? |
| Dependency health | Do auxiliary services still operate from another region? |

Probe from multiple independent regions or networks to avoid mistaking a broken transit path for a backend outage. Signals must include timestamps, sources, and correlation so coordinators can gauge confidence.

### 6.2. Trigger Conditions

Runbooks must define:

- Conditions under which an incident escalates to a disaster.
- Who holds authority to declare a disaster and trigger failover.
- When automatic failover is permitted and when human approval is required.
- How to determine whether the primary is dead, partitioned, or merely slow.
- Acceptable data-loss thresholds and who approves RPO target exceptions.
- Safeguards preventing two operations teams from executing two failovers simultaneously.

For critical systems, detection and environment preparation can be automated while requiring accountable approval for destructive/irreversible data promotion. Automation levels must match detector reliability and fencing safety.

### 6.3. Incident Commander and Roles

During a disaster, clear role division prevents multiple people from modifying the system simultaneously:

| Role | Responsibilities |
| --- | --- |
| Incident commander | Coordinates decisions, priorities, timeline, and stakeholder updates |
| Technical lead | Assesses failure domains, topology, and recovery order |
| Data lead | Checks replication, selects recovery point, promotes, and verifies data |
| Network/edge lead | DNS, global routing, firewalls, connectivity, and endpoints |
| Application lead | Deploy/config, secrets, readiness, queue consumers, and smoke tests |
| Security lead | Identity, KMS, credentials, evidence, and access controls |
| Business owner | Approves RPO exceptions, validates business flows, and approves degraded mode |

One person may wear multiple hats in smaller teams, yet responsibilities and decision rights must be explicitly assigned.

## 7. Failover Procedure in Dependency Order

Safe failover requires a state machine or runbook with steps, entry criteria, actions, verifications, and stop conditions. Sequences vary by architecture, yet write authority and data state must be resolved before opening new write traffic.

### 7.1. Reference Orchestration Flow

~~~mermaid
flowchart TD
    A["Declare disaster / incident"] --> B["Assess blast radius and current primary"]
    B --> C["Freeze risky changes and writes if needed"]
    C --> D["Fence old writer / confirm ownership"]
    D --> E["Select recovery point and promote data"]
    E --> F["Restore identity, keys, network and secrets"]
    F --> G["Start compute and dependent services"]
    G --> H["Validate health and business invariants"]
    H --> I["Shift traffic gradually"]
    I --> J["Monitor SLO, errors, data and queue"]
    J --> K["Operate in DR mode / plan failback"]
~~~

Some steps such as restoring networking, identity, and keys should be prepared or executed in parallel with data assessment. However, never allow write traffic into the new database before confirming writer authority and recovery point.

### 7.2. Phase 1: Declare and Freeze

1. Record incident ID, commander, timestamp, and evidence sources.
2. Scope affected services, regions, tenants, and data.
3. Freeze unrelated deployments/config changes to reduce variables.
4. If corruption/ransomware risk exists, restrict writes or isolate compromised credentials/endpoints.
5. Record in-flight operations, queue backlogs, and transactions with ambiguous outcomes.

### 7.3. Phase 2: Fence the Old Primary

Fencing ensures the old primary cannot keep accepting writes once the DR region becomes writer. Implementation depends on the platform:

- Provider-managed promotion with leader epochs/leases.
- Revoking write routes or credentials of the old writer.
- Network isolation or disabling endpoints within controllable scope.
- Fencing tokens at the application/storage layer so requests from old generations are rejected.
- Quorum/witness confirming the new leader and preventing two sides from holding a majority simultaneously.

Updating DNS alone is not fencing. Clients may cache old endpoints; connection pools may keep open sessions; workers may keep retrying the old primary. A data-plane or database-permission mechanism is required to block the old writer.

### 7.4. Phase 3: Select Recovery Point and Promote

The data lead must determine:

- Which replica/backup is the best recoverable source.
- The last commit/log position durably confirmed in the standby region.
- Which data window may be missing or in an ambiguous state.
- Whether log/event replay or transaction reconciliation is required post-promotion.
- Whether signs exist of corrupted or compromised data having replicated.

Do not promote a stale replica when a cleaner/more accurate backup is required by security procedures. With asynchronous replication, record actual RPO and obtain business owner sign-off when exceeding limits.

### 7.5. Phase 4: Restore Dependencies

Restore along the dependency graph, for example:

1. Network routing, private endpoints, firewalls, internal DNS, and connectivity.
2. IAM/workload identities, secrets, certificates, and KMS permissions.
3. Databases, object/file storage, queues/streams, and caches.
4. Compute, service discovery, configuration, and autoscaling.
5. Background workers, schedulers, integrations, and observability.

Not every system follows this exact sequence. Build a concrete dependency graph and spot circular dependencies, such as a service needing a database to start while database restore needs credentials from a secret service.

### 7.6. Phase 5: Validate Before Cutover

Run layered checks:

- **Infrastructure:** resources healthy; routes/volumes/endpoints/replicas correct.
- **Security:** identities, roles, KMS, TLS, secrets, and auditing work.
- **Data:** schema versions, transaction invariants, row counts/checksums, or appropriate reconciliation.
- **Application:** readiness, connection pools, dependency health, and config.
- **Business:** creating/reading orders, simulated payment checks, reservations, event publish/consume, or representative workflows.

A green health check alone does not prove data correctness. Run smoke tests with safe test data that do not trigger real side effects in payment systems or send real customer notifications.

## 8. Designing Traffic Routing During Failover

Traffic routing determines which application/region clients reach. Options include DNS failover, global load balancers, anycast, CDN origin failover, application-level routing, or service meshes. Each has different convergence times, caching, health semantics, and failure modes.

### 8.1. DNS-Based Failover

DNS can return the standby region's address when primary health checks fail. Consider:

- Actual TTLs and resolver/client caching; a low TTL does not guarantee every client switches immediately.
- Negative caching and DNS propagation behavior.
- Do health checks run sufficient synthetic transactions or only TCP/HTTP endpoint checks?
- Is there split-view DNS between private resolvers and public DNS?
- Do clients hard-code IPs or hold long-lived connections?
- During failback, how do you prevent resolvers from switching back to primary too early?

DNS suits many architectures yet is not an instant cutover mechanism. Clients can hold connection pools or cached addresses longer than TTL.

### 8.2. Global Load Balancer / Traffic Manager

A global routing layer can select regions by health, latency, weight, geography, or priority. It generally offers finer traffic-splitting weights and clearer health states than raw DNS, while still depending on health probes, control plane, caching, and client connection behavior.

Common modes:

| Mode | Behavior | When to Use |
| --- | --- | --- |
| Priority/failover | Prefer primary region; shift to secondary on failure | Active-passive |
| Weighted | Split traffic by percentage | Canary cutover or active-active |
| Latency-based | Pick endpoint with lowest observed latency | Multi-region apps with matching data routing |
| Geo-based | Route by location or geographic policy | Data residency or locality |
| Anycast/edge | Bring clients to nearest edge, then route to backend | Edge/global services |

Latency-based routing has no awareness of which data copy is freshest. A closer region holding only a stale replica must not serve requests requiring read-after-write consistency.

### 8.3. Phased Traffic Cutover

Rather than moving all users at once, you can:

1. Run synthetic/internal traffic against the DR region.
2. Shift a small percentage of non-destructive traffic or a selected user cohort.
3. Inspect latency, errors, data correctness, queues, and capacity.
4. Increase percentages in predefined increments.
5. Keep the ability to pause/roll back if metrics breach thresholds.
6. Shift the remainder once business and technical criteria pass.

Canary cutover reduces blast radius, yet is safe only when routing and data ownership are clear. Never split write traffic across two regions just to test health if only one region holds writer authority.

### 8.4. Session Affinity and Client State

If sessions live in memory in Region A, routing the next request to B drops sessions. Use external session stores/replication, protected stateless tokens, or DR-aware session affinity. Evaluate refresh tokens, CSRF state, WebSockets, and long-lived connections.

## 9. Data Plane: Databases, Queues, Objects, and Files

Restoring compute without corresponding data and messaging creates an inconsistent system.

### 9.1. Databases

- Establish a single writer or database-supported multi-writer semantics.
- Check replication lag, log positions, promotion, and endpoints.
- Handle transactions with indeterminate outcomes from when clients lost connectivity.
- Use idempotency keys, operation IDs, or reconciliation to handle retries.
- Verify sequences/identities, extensions, schema migrations, and version compatibility.
- Prevent application pools and workers from using old endpoints after cutover.

### 9.2. Queues and Event Streams

Queues may not replicate synchronously with the database. Identify which messages were received, processed, in-flight, and unreplicated. For partitioned event streams, verify consumer offsets and retention.

Questions:

- Can producers in the old region still write?
- Does the DR queue contain sufficient messages and required ordering?
- Can duplicates occur during replay?
- Are consumers idempotent?
- Are visibility timeouts, retries, and DLQs restored?
- Should producers/consumers pause while selecting the recovery point?

### 9.3. Object and File Storage

Object replication may be asynchronous; verify versions, delete markers, lifecycles, and metadata. Signed URLs generated in the old region may point to old endpoints or be invalid. File storage requires verifying mounts, identity mapping, file locks, snapshot consistency, and open files. Never assume replicated bytes automatically mean filesystem state/ACLs are ready.

### 9.4. Caches and Search Indexes

Caches can usually be rebuilt from the source of truth; replicating every entry is unnecessary. However, a cold cache after failover can trigger a thundering herd against the database. Use bounded warm-up, cache stampede protection, and concurrency limits.

Search indexes/materialized views can usually be rebuilt or replayed from data sources. Determine freshness, checkpoints, and rebuild capacity before placing them on the DR critical path.

## 10. Failback: Returning to Normal Operations

Failback is a separate topology change, not a mechanical reversal of failover. The old region may contain unsynced data, faulty config, stale credentials, or modified infrastructure. During DR, the standby region may have become the authoritative data source.

### 10.1. Pre-Failback Conditions

- Incident root cause is understood and resolved or mitigated.
- The old region has been verified across networking, compute, storage, identity, and security.
- Data from the current writer has fully replicated/caught up to the target return region.
- No stale writers/consumers can still write with outdated credentials or endpoints.
- Schemas, migrations, extensions, encryption keys, and config are compatible.
- Capacity is sufficient for traffic and a rollback plan exists if failback fails.
- Business owner/incident commander approves the cutover window and risks.

### 10.2. Failback Procedure

1. Keep the DR region as writer while inspecting and rebuilding the old region.
2. Establish replication from the current writer to the recovering region.
3. Wait for replication to catch up; compare log positions/lag, checksums, or invariants.
4. Select a maintenance/cutover window; announce and minimize unrelated changes.
5. Fence or pause writes on the current writer per database procedure.
6. Confirm final sync and perform controlled writer promotion/handoff.
7. Update endpoints, service discovery, routing, and connection pools.
8. Shift traffic gradually; inspect latency, errors, data, and business flows.
9. Keep the DR region as the new replica/standby and verify reverse replication works.
10. Close the incident once stable; archive timeline and action items.

### 10.3. Avoid Premature Failback

Pressure to cut standby costs can push teams to return to the old region too early. If the region is unstable or data is unsynchronized, a second outage can lose more data. Failback should rely on verified criteria and a stability window, not merely a provider notice that services have recovered.

## 11. Coordinating Transactions, Backlogs, and Retries During DR

During failover, some requests may have committed without responses reaching clients; others never committed; messages may have been delivered without acks. DR must handle these indeterminate states.

### 11.1. Idempotency and Reconciliation

For critical write commands, persist operation IDs/idempotency keys alongside state and outcomes. When clients retry after timeouts, the new region looks up the operation before creating another side effect.

For payments, reconcile with the payment provider via transaction references before recharging. For orders, verify whether the order already exists/is confirmed. For inventory, reservations need unique operation keys or versions to avoid double-deduction.

### 11.2. Queue Backlogs After Failover

Before scaling consumers to full capacity:

- Inspect message counts, oldest message age, and priority classes.
- Check for poison messages, DLQs, visibility timeouts, and retry attempts.
- Cap consumer concurrency per DR region database/API quotas.
- Prioritize work by deadlines and criticality.
- Monitor backlog drain rate, not just desired worker count.

Scaling consumers too aggressively can trigger a connection storm and overwhelm an unsteady DR database. Replay in small batches, starting with low concurrency and ramping based on metrics.

### 11.3. Rebuilding Derived Data

Search indexes, caches, reporting projections, or feature stores may need rebuilding. Define sources of truth, watermarks, event retention, and replay procedures. Do not rebuild every dataset simultaneously if it competes for capacity with recovering customer transactions.

## 12. Networking, Identity, and Secrets in DR

A DR region needs more than a database endpoint.

### 12.1. Network Readiness

- VPC/VNet, subnets, route tables, firewalls/security groups, and private endpoints pre-created or provisionable.
- CIDRs do not overlap with on-premises, partner networks, or other regions.
- VPN/Direct Connect/ExpressRoute or private backbones have appropriate redundant paths.
- NAT, egress IPs, DNS resolvers, and third-party allowlists updated.
- Certificates, TLS policies, service meshes, and mutual TLS usable in the DR region.
- IP/subnet capacity sufficient for autoscaling and standby node pools.

If the DR region is built from infrastructure-as-code during an incident, quotas and provisioning times must be tested beforehand. A VPC template alone does not prove every route, firewall, and private DNS works.

### 12.2. Identity and KMS

Applications in DR must authenticate with identity providers, workload identities, secret managers, and KMS. If those systems run only in the primary region, DR may fail to decrypt data or fetch secrets.

Prepare:

- Roles/service accounts with trust policies tailored for the DR region.
- Secret replication/rotation and procedures to revoke old credentials.
- Encryption key policies for backups, replicas, and storage.
- Certificate lifecycles and CA trust.
- Break-glass access following least privilege, MFA, and auditing.

Do not blindly copy every secret to DR. Replicate only needed secrets, restrict permissions, and preserve separation of duties.

### 12.3. Security in Disaster Mode

Recovery urgency is no excuse to disable MFA, expose databases publicly, or grant broad admin access. DR needs break-glass controls with approvals, time bounds, auditing, and revocation workflows. If the incident potentially involves credential compromise or ransomware, prioritize a clean recovery environment, rotate keys/tokens, and preserve forensic evidence before opening traffic.

## 13. Runbooks and Orchestration Automation

A good runbook specifies who does what, where, what gates allow proceeding, and how to back out when a step fails. Repeatable, deterministic, idempotent tasks should be automated; decisions risking data loss or writer-authority changes need explicit guardrails.

### 13.1. Runbook Structure

| Component | Required Content |
| --- | --- |
| Trigger | Metrics, alerts, provider incidents, and declaration conditions |
| Owner/approver | Incident commander, data lead, security, and business approvers |
| Preconditions | Replica health, backups, credentials, capacity, and maintenance state |
| Action | Versioned commands/APIs/workflows with explicit parameters |
| Verification | Criteria confirming step success |
| Timeout/retry | Wait durations, retry counts, and handling indeterminate states |
| Stop condition | When to halt due to split-brain, data loss, or security risk |
| Rollback/compensation | How to return to a safe state if a step fails |
| Evidence | Timestamps, actors, request IDs, outputs, and decisions |
| Communication | Who updates the status page, customer support, and stakeholders |

### 13.2. Orchestration State Machine

Avoid writing a long sequential script that executes commands without persisting state. Workflow orchestration should maintain durable state:

~~~mermaid
stateDiagram-v2
    [*] --> Normal
    Normal --> Assessing: Disaster signal
    Assessing --> Aborted: Region recovered / false alarm
    Assessing --> Fencing: Approved DR
    Fencing --> DataRecovery
    DataRecovery --> DependencyRecovery
    DependencyRecovery --> Validation
    Validation --> TrafficShift: Checks passed
    Validation --> RecoveryBlocked: Checks failed
    TrafficShift --> DRActive: SLO and business checks pass
    TrafficShift --> RecoveryBlocked: Error threshold exceeded
    DRActive --> FailbackPlanning: Primary region stable
    FailbackPlanning --> Failback
    Failback --> Normal: Reconciled and verified
    RecoveryBlocked --> Assessing: New plan approved
~~~

Each transition requires idempotency, timeouts, actor/approval tracking, and evidence. If a workflow restarts, it must know whether the previous step finished so it never promotes twice or shifts traffic repeatedly.

### 13.3. Automation by Risk Level

- Automated: state collection, health probes, lag checks, incident context creation, compute/network prep, and alerting.
- Automated with guardrails: percentage traffic shifts, worker scaling, cache warming, and non-destructive smoke tests.
- Tight approval/control: database promotion, choosing a recovery point with data loss, writer fencing, identity/key changes, or deleting faulty sources.

Tiering should fit the product and runbook; do not assume every promotion must be manual if the database has a proven safe failover mechanism.

## 14. Observability and Communication During DR

While DR is underway, teams need a single shared view of service state and decisions.

### 14.1. DR Dashboard

| Group | Metrics |
| --- | --- |
| Incident | Detection time, declaration time, current phase, owners, and pending actions |
| Data | Replication lag, log positions, last backup, restore status, data validation |
| Routing | Traffic weights, DNS/edge health, connections to old/new endpoints |
| Application | Request rates, p95/p99, errors/timeouts, synthetic journeys |
| Dependencies | Queue depth/age, DB connections, cache, third-party APIs, and identity |
| Capacity | Ready instances/Pods, pending nodes, quotas/IPs, autoscaling state |
| Security | KMS/key status, secret access, IAM changes, audit gaps |
| Recovery objectives | Elapsed/remaining RTO, measured/excepted RPO |

### 14.2. Timeline and Evidence

Record unified timestamps for:

- Initial detection and incident confirmation.
- Disaster declaration and approver.
- Old writer fenced and new leader authority confirmed.
- Selected recovery point and actual RPO.
- Database promotion and dependency recovery.
- Phased traffic shifts.
- Business validation and moment service restoration was achieved.
- Failback, if performed.

Timelines are used to calculate actual RTO, investigate root causes, and improve runbooks. Store evidence with restricted access and proper retention.

### 14.3. Stakeholder Communication

Updates should distinguish:

- Investigating vs. disaster declared.
- Which services are affected and what users can do.
- Read-only/degraded mode vs. halted transactions.
- Confirmed scope of potential data delay/loss.
- When the next update will arrive.
- When the service is confirmed fully restored.

Never promise unverified recovery times. One responding endpoint does not mean all transactions and data are stable.

## 15. DR Testing: Prove the Plan, Not the Document

An untested DR plan is only a hypothesis. Run periodic tests to uncover drift between designed architecture and running configuration.

### 15.1. Drill Levels

| Test Type | Execution | What It Proves |
| --- | --- | --- |
| Tabletop exercise | Team walks through scenarios and decisions on paper | Roles, permissions, communication, and decision logic |
| Component restore | Restore individual databases/objects/volumes in a sandbox | Backups, keys, data consistency, and restore times |
| Partial failover | Shift a single service or test traffic cohort | Routing, endpoints, app config, and dependencies |
| Full regional failover | Shift full workload within the chosen DR scope | End-to-end RTO/RPO, capacity, and orchestration order |
| Failback exercise | Sync and cut back to the original region | Return workflow, fencing, routing, and replica topology |
| Chaos/fault injection | Simulate latency, packet loss, dependency outages, or node losses | Behavior under unexpected faults and guardrails |

Not every test requires a full production failover. Start in a sandbox/equivalent environment, then expand scope with a plan, owners, blast radius, and stop criteria.

### 15.2. Test Scenarios to Include

1. Primary database loses connectivity abruptly during active writes.
2. Primary region retains compute yet identity/KMS or private networking becomes unreachable.
3. Replication lag exceeds RPO due to traffic bursts or slow links.
4. DNS/global routing health probes false-positive or miss real failures.
5. DR region lacks quotas, IPs, or capacity to handle full traffic.
6. Queues/streams are incompletely replicated; workers retry after cutover.
7. Clients hold connections to old endpoints after DNS changes.
8. Backups are accessible yet keys are disabled or roles lack restore permissions.
9. Data is accidentally deleted/corrupted and replicated to the standby.
10. Failback begins when the old primary has only partially recovered.

### 15.3. Measuring Actual RTO/RPO

Record timestamps for declare, fence, data promotion, dependencies ready, routing cutover, and business validation. Business RTO ends when critical journeys succeed and meet SLOs, not when API health checks turn green.

Actual RPO must compare the last acknowledged transaction against recovered data. Use transaction IDs, commit LSNs/log positions, event sequences, or reconciliation against upstream systems. Do not rely solely on post-incident replication lag metrics.

### 15.4. Exit Criteria and Action Items

A drill passes when:

- Failover completes within approved RTO.
- Data loss does not exceed RPO; any exceptions are documented.
- Only the valid writer exists; no split-brain occurs.
- Identity, keys, networking, secrets, and dependencies operate.
- Synthetic transactions and business journeys pass.
- Queue backlogs clear within SLA without uncontrolled duplicate side effects.
- Operators understand system state and capture complete evidence.
- Failback or staying in DR mode has an explicit decision and owner.

Every failure or delay generates an action item with an owner, deadline, and retest in the next drill.

## 16. Cost and Capacity in the DR Region

The DR region must have enough capacity at incident time. If running only part of the workload, know actual scale-up speed and quotas. If two regions run active normally, verify whether one surviving region can carry full peak when the other fails.

### 16.1. Capacity Planning

- Calculate peak traffic and concurrency to serve in DR mode.
- Check VM/instance quotas, GPU quotas, serverless concurrency, Kubernetes node pools, and subnet IPs.
- Size database compute, connections, IOPS, storage, and post-promotion read/write capacity.
- Verify queue/broker partitions, consumer parallelism, and rate limits.
- Verify whether third-party providers allow new egress IPs/regions.
- Identify workloads that can be disabled or degraded to prioritize critical transactions.

### 16.2. Intentional Degraded Mode

Not every feature must operate fully during DR. You can:

- Pause heavy reporting, exports, and non-urgent batch jobs.
- Switch catalog/search to read-only or cached mode.
- Restrict video uploads or high-compute tasks.
- Prioritize checkout, payment status, and order lookups.
- Reduce analytics and background enrichment frequency.

Degraded modes must be predefined, owned, and clearly communicated to users. Never disable a dependency arbitrarily if it breaks transaction invariants.

### 16.3. TCO

DR costs include standby compute, replicas/databases, backup storage, cross-region data transfer, DNS/global routing, observability, security/key management, test environments, licenses, and operational labor. Backup and restore has lower standby cost yet may need significant provisioning capacity during recovery. Hot standby costs more yet reduces provisioning delay.

Evaluate cost against actual RTO/RPO and business impact, not merely average monthly infrastructure spend.

## 17. Well-Architected: Trade-Offs in Recovery Orchestration

| Perspective | DR Decision | Trade-Offs |
| --- | --- | --- |
| **Operational Excellence** | Runbooks, orchestration state machines, roles, timelines, and game days | Automation cuts manual errors yet demands versioning, guardrails, and testing |
| **Security** | Fencing, break-glass, key/secret recovery, immutable backups, and auditing | Strict controls add steps; skipping controls risks compromise or split-brain |
| **Reliability** | Multi-region, replication, backups, failover/failback, and business validation | Tighter RTO/RPO typically increases cost and complexity |
| **Performance Efficiency** | Spare capacity, warm caches, and traffic distribution | Idle capacity and replication traffic raise costs |
| **Cost Optimization** | Choose backup/restore, pilot light, warm/hot standby per criticality | Saving on standby can lengthen RTO |
| **Sustainability** | Right-size DR capacity, shut down non-essential workloads, backup lifecycles | Reducing resources while preserving sufficient disaster headroom |

Every decision must link to business requirements and test evidence. Never optimize cost by dropping backups for critical data; never optimize availability by enabling multi-writer if data lacks safe conflict semantics.

## 18. Common Mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Treating DNS failover as complete DR | Traffic shifts while data, identity, and dependencies remain unready | Orchestrate all dependencies and business validation |
| Shifting traffic before fencing old writer | Split-brain and data divergence | Enforce fencing/leader ownership before opening new writes |
| Measuring only database promote time | Reports unrealistically low RTO | Measure from declare through passing business journeys |
| Assuming replicas are always fresh enough | Lost transactions ACKed at primary | Track log positions/lag and record actual RPO |
| Not rehearsing failback | Topology drift and dual writers on return | Test failback as a dedicated procedure |
| DR region lacks quotas/capacity | Overwhelmed after traffic shift | Capacity reservations, quota reviews, and full-scale tests |
| Unprepared KMS/secrets/identity | Data exists yet cannot decrypt or apps fail to start | DR-ready key, secret, and identity paths |
| Non-idempotent queue replay | Duplicate charges/emails/orders | Operation IDs, deduplication, and reconciliation |
| Overly simplistic health checks | False failovers or undetected business failures | Synthetic transactions and multi-signal detection |
| Lacking degraded modes | Secondary features starve core transactions | Prioritize services by criticality |
| Backups and replicas sharing delete permissions | Ransomware/accidental deletes wipe both | Immutable/offline copies and separation of duties |
| Runbooks as static documents | Stale commands/config during incidents | Version, automate, and run regular game days |

## 19. Practice Exercise: DR for a Multi-Region Ordering Platform

An e-commerce platform operates in Region A with DR Region B. Region A hosts the API, PostgreSQL primary, queues, object storage, caches, and workers. Region B has an asynchronous database replica, object replication, smaller compute capacity, and a global traffic manager. Checkout requires a 20-minute RTO and 1-minute RPO; analytics dashboards can recover in 6 hours with a 1-hour RPO.

A widespread incident causes APIs in A to time out, replication lag fluctuates between 40–90 seconds, part of the queue has no copy in B, and KMS keys are managed under Region A's policies. Users can still reach the static site via CDN yet cannot place new orders.

**Assignment requirements:**

1. Determine whether criteria are met to declare a disaster or continue diagnosing; list signals to verify.
2. Draw the dependency graph and recovery sequence for networking, identity/KMS, databases, queues, objects, compute, and routing.
3. Specify how to fence primary A and prove B is the sole writer.
4. Calculate/record actual RPO from replication lag and propose how to handle transactions with indeterminate outcomes.
5. Design routing for static content, catalog reads, and checkout writes; explain DNS/global load balancer and client connection behavior.
6. Propose how to handle unreplicated queues, in-flight messages, retries, DLQs, and idempotency.
7. Size DR region capacity and propose a degraded mode to protect checkout while analytics/workers are unrecovered.
8. Design KMS/secret recovery and security gates before opening traffic.
9. Write a runbook state machine with approvals, verifications, stop conditions, and evidence per step.
10. Describe failback once A recovers, including reverse replication, final sync, writer switch, and traffic cutback.
11. Propose a game day scenario and a dashboard measuring end-to-end RTO/RPO.
12. Write an ADR comparing pilot light, warm standby, and hot standby by cost, RTO/RPO, and operational risk.

### Evaluation Guidance

A sound design does not switch checkout writes to B merely because a global health check marks A unhealthy. The team must verify blast radius, fence A, choose a recovery point, and document potentially missing data. KMS/identity must be ready in B before applications read encrypted data. Unreplicated queues need replay/reconciliation from source or business-accepted job recreation.

A 20-minute RTO must encompass decision, fencing, promotion, dependencies, routing, and business validation. If B runs smaller compute, prove it handles peak checkout or define a business-approved degraded mode. Failback is a separate cutover with reverse replication and final sync.

## 20. Pre-Production DR Checklist

- [ ] Workloads have defined owners, criticality tiers, dependency graphs, and failure domains.
- [ ] RTO/RPO are approved by business owners per application/dataset.
- [ ] Backup/restore, pilot light, warm/hot standby, or active-active strategy matches targets.
- [ ] Replication semantics, lag, data loss windows, and recovery points are measurable.
- [ ] Multi-signal detection, declaration criteria, incident commander, and approval authority exist.
- [ ] Fencing/leader ownership blocks the old primary from writing before opening a new writer.
- [ ] Runbooks include state, preconditions, actions, verifications, timeouts, stop conditions, and rollback.
- [ ] Networking, DNS, IAM, KMS, secrets, certificates, and private endpoints are ready in DR.
- [ ] Databases, queues, object/file storage, caches, and search/indexes have separate recovery strategies.
- [ ] Idempotency/reconciliation handles indeterminate transactions and message replays.
- [ ] Traffic routing includes health probes, TTL/cache considerations, gradual shifts, and rollback.
- [ ] Sessions, long-lived connections, and client endpoint behaviors are tested.
- [ ] DR region has sufficient quotas, IPs, compute, databases, storage, and third-party allowlists.
- [ ] Degraded modes and workload prioritization by criticality exist.
- [ ] Independent/immutable backups, key recovery, and restore tests are verified.
- [ ] Failback has reverse replication, final sync, fencing, routing, and an owner.
- [ ] Dashboards track incident phase, RPO/RTO, data lag, traffic, SLOs, dependencies, and security.
- [ ] Tabletops, restore tests, partial/full failovers, and failback game days are scheduled.
- [ ] Action items from drills have owners, deadlines, and retests.
- [ ] Costs for standby, transfers, backups, testing, and operations fit approved budgets.

**Takeaway:** Good failover design orchestrates data, writer authority, dependencies, and traffic through a stateful process. Verify the incident before declaring, fence the old source before opening writes on the new one, restore identity/keys/networking alongside data, shift traffic by criteria, and verify business journeys. Failback requires separate synchronization and cutover. Prove RTO/RPO through periodic game days and restore tests; DR documentation has value only when operators can execute it in real situations.
