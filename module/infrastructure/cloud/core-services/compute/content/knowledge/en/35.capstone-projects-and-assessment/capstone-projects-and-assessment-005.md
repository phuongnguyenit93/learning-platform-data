# Designing a Backup, Recovery, and Cutover Rehearsal Plan

A cloud system can run stably for a long time and still suffer severe incidents: accidental data deletion, application bugs corrupting records, database corruption, loss of an availability zone, a region outage, or networking misconfigurations blocking user access. Having backups alone does not prove a system can recover; having a standby environment alone does not prove traffic can safely cut over to it.

This capstone requires building an executable backup and disaster recovery (DR) plan, then designing and rehearsing a cutover from the primary environment to the recovery environment. The outcome must prove that data is recoverable, services meet RPO/RTO targets, traffic routes to the right destination, dependencies function, and operations teams can roll back or fail back under defined conditions.

In **CLOUD_CORE_SERVICES_COMPUTE**, this project integrates compute, storage, networking, identity, automation, high availability, and cost optimization. The plan applies to workloads running on VMs, containers, or serverless; implementation details should match the actual system architecture.

## 1. Project Objectives

Upon completion, learners will be able to:

1. Classify workloads, data, and dependencies by criticality.
2. Define RPO, RTO, recovery tiers, and service recovery criteria.
3. Design a backup strategy covering retention, encryption, immutability, and restore testing.
4. Select an appropriate DR model: backup and restore, pilot light, warm standby, or hot standby.
5. Map dependencies and recovery ordering across compute, storage, database, networking, identity, and applications.
6. Build runbooks for cutover, validation, rollback, and failback.
7. Design rehearsals with explicit scope, guardrails, owners, timelines, and abort criteria.
8. Measure actual RPO/RTO, DR costs, and gaps against targets.
9. Convert rehearsal findings into action items with owners, deadlines, and retest schedules.

## 2. Hypothetical Context

An enterprise operates an online ordering platform. The production system comprises:

- Orders API running on containers with multiple replicas.
- Workers handling payments, notifications, and report generation as container jobs.
- Managed relational database storing customers, orders, and payment status.
- Object storage storing invoices, images, and export files.
- Message queue passing events from the API to workers.
- Shared cache reducing database load.
- DNS, load balancer, and API gateway ingesting traffic.
- Identity provider, secret manager, and KMS supplying identities, secrets, and encryption keys.
- Monitoring, logging, and alerting observing the system.

The primary environment runs in Region A across three availability zones. The business can recover in Region B. Stateless components can be rebuilt using Infrastructure as Code; databases and object data require dedicated protection strategies.

### 2.1. Current System Diagram

~~~mermaid
flowchart TD
    U["Users / partners"] --> DNS["DNS / WAF / API Gateway"]
    DNS --> LB["Load balancer"]
    LB --> API["Orders API containers"]
    API --> DB["Managed relational database"]
    API --> CACHE["Shared cache"]
    API --> Q["Message queue"]
    Q --> W["Background workers"]
    API --> OBJ["Object storage"]
    W --> DB
    W --> OBJ
    W --> EXT["Payment / Notification APIs"]
    API --> ID["Identity / KMS / Secrets"]
    W --> ID
    API --> OBS["Logs / metrics / traces"]
    W --> OBS
~~~

This serves as a reference architecture for the exercise. When applying it to another system, adjust service names, data flows, failure domains, and business requirements accordingly.

### 2.2. Initial Business Assumptions

| Component | Criticality | Impact if Disrupted |
| --- | --- | --- |
| Orders API | Very high | Cannot create or query orders |
| Orders database | Very high | Loss of ability to read/write transactional data |
| Payment worker/queue | Very high | Transactions may stall or process twice |
| Invoice object storage | High | Users cannot download invoices |
| Notification worker | Medium | Notifications delayed; can be sent retroactively |
| Reporting pipeline | Lower | Reports can catch up later |
| Cache | Medium | Higher latency and database load |

Do not assume every component shares the same RPO/RTO. Caches are regenerable; transactional data demands stricter protection; reports can tolerate slower recovery.

## 3. Defining DR Scope and Assumptions

Before designing, explicitly document which systems, data, and incident types are in scope.

### 3.1. Protection Scope

Categorize:

- Production workloads and direct dependencies.
- Transactional data versus regenerable data.
- Artifacts, images, IaC, and runtime configuration.
- Identities, secrets, certificates, and encryption keys.
- Networking, DNS, routes, firewalls, and endpoints.
- Monitoring, logging, alerts, and communication channels.
- Operational procedures, runbooks, and emergency access.

### 3.2. Incident Scenarios

Select at least three scenarios with distinct impact profiles:

| Scenario | Example | Validation Goal |
| --- | --- | --- |
| Data corruption/accidental deletion | Faulty update statement corrupts data | PITR, backup integrity, and reconciliation |
| Compute failure | Node pool or group of VMs lost | Rebuild compute and restore endpoints |
| Zone outage | One availability zone stops serving | Replica distribution and remaining capacity |
| Region outage | Primary region loses connectivity or services | Cutover to recovery region |
| Identity/config failure | Misconfigured secret, certificate, or policy | Ability to restore identity and configuration |
| Application release failure | New release causes data or request errors | Application rollback and data compatibility |

You do not need to simulate every scenario in a single rehearsal. Choose a scope small enough to control risk yet broad enough to validate dependencies end to end.

### 3.3. Out of Scope

Explicitly state boundaries, for example:

- Do not test simultaneous loss of both regions.
- Do not send real payment transactions in the rehearsal environment.
- Do not delete production data to simulate corruption.
- Do not shift public traffic without a change window and approval.
- Do not assume the provider can supply unlimited capacity on demand at any moment.

Scoping boundaries clarify for participants what has been verified versus what remains an assumption.

## 4. Business Impact Analysis and Setting RPO/RTO

### 4.1. Business Impact Analysis

For each service, answer:

- Which business operations does the service support?
- What is the impact of a 15-minute, 1-hour, or 1-day outage?
- Which data is regenerable and which cannot be lost?
- Are there peak periods or regulatory deadlines?
- Which services must recover before others?
- Who holds authority to accept downtime or data loss?

RPO/RTO targets must be agreed upon by business, engineering, security, and operations owners. Infrastructure teams should not invent targets unilaterally on behalf of the business.

### 4.2. RPO

Recovery Point Objective is the maximum acceptable data loss, typically expressed as a time interval. A 5-minute RPO means the restored consistent data point cannot trail the agreed incident timestamp by more than 5 minutes.

RPO is influenced by:

- Backup frequency and completion duration.
- Replication lag.
- Continuity of transaction logs.
- Point-in-time recovery (PITR) capability.
- Cross-system consistency across databases, object stores, queues, and events.
- When data is durably committed.

Backing up every 5 minutes does not guarantee a 5-minute RPO on its own. You must verify actual restore points and replayable transaction logs.

### 4.3. RTO

Recovery Time Objective is the maximum tolerable service disruption duration. Actual RTO must be measured from the defined start marker until the service meets recovery criteria.

Steps typically included in RTO:

- Detecting and confirming the incident.
- Declaring DR and mobilizing responders.
- Selecting the recovery site and restore point.
- Provisioning networking, identity, keys, and compute.
- Restoring databases, objects, and volumes.
- Starting APIs, workers, and dependencies.
- Validating data and business workflows.
- Shifting traffic and verifying SLOs.

A VM showing `Running` or a database showing `Online` is insufficient to declare RTO met.

### 4.4. Reference Target Table

The values below are capstone assumptions and should be adjusted per BIA:

| Workload/Data | Target RPO | Target RTO | Recovery Tier |
| --- | ---: | ---: | --- |
| Orders database | 5 minutes | 30 minutes | Tier 1 |
| Payment state/queue | 1 minute | 15 minutes | Tier 0/1 |
| Orders API | Not directly applicable to stateless compute; data follows DB | 15 minutes | Tier 1 |
| Invoices/object data | 1 hour | 2 hours | Tier 2 |
| Notification backlog | 15 minutes | 2 hours | Tier 2 |
| Reporting output | 24 hours | 1 day | Tier 3 |
| Cache | Regenerable | 30 minutes | Tier 2 |

For stateless APIs, data RPO belongs to databases and storage services. Do not assign a data RPO to a container image as if the image itself were transactional data.

### 4.5. Defining Measurement Markers

Specify:

- `T0` disruption: when the service stops meeting criteria.
- `T_detect`: when monitoring or an on-call responder detects the issue.
- `T_declare`: when the commander activates DR.
- `T_data`: when consistent data becomes ready.
- `T_app`: when the application reaches readiness.
- `T_cutover`: when traffic shifts to the recovery site.
- `T_restore`: when smoke tests and business checks pass.

Actual RTO is normally measured from `T0` to `T_restore`. If a report uses `T_declare` as the start marker, state that explicitly to avoid understating real disruption time.

## 5. Designing the Backup Strategy

Backups must protect data against accidental deletion, corruption, application bugs, credential compromise, and infrastructure outages. Replication maintains a near-real-time copy, but can also replicate deletions or corruption; therefore, replication does not replace backups.

### 5.1. Data Classification

| Data Category | Recommended Protection | Verification Points |
| --- | --- | --- |
| Transactional database | Full/incremental backups and transaction logs/PITR | Restore points, consistency, log chain |
| Invoice objects | Versioning, replication, and independent backup/retention | Object versions, delete markers, checksums |
| Queues/events | Retention, replay, or archive per requirements | Offsets, duplicates, ordering |
| Cache | Regenerate from primary data sources | Never treat cache as sole source of truth |
| VM disks/configs | Snapshots, images, and IaC | Application consistency, encryption |
| Container images | Registry replication and artifact retention | Digests, signatures, dependency versions |
| IaC/configuration | Version control and protected artifacts | Drift, secret references, and versions |
| Secrets/keys/certificates | Backup/escrow per policy and recovery access | Recovery permissions, key lifecycle, expiry |

### 5.2. Backup Rules

The 3-2-1-1-0 rule can serve as a baseline checkpoint:

- Maintain multiple copies of data, including production and backups.
- Use at least two distinct media types or appropriate failure domains.
- Keep at least one copy off-site/outside the primary region.
- Keep one offline or immutable/tamper-resistant copy per your threat model.
- Maintain zero unverified errors via backup and restore testing.

This is a design guideline, not a substitute for legal, retention, or specific architectural requirements. In the cloud, "offline" can be implemented via an isolated backup vault or immutable storage with separate access boundaries.

### 5.3. Database Backups

Minimum design elements to specify:

- Scheduled full backups.
- Incremental/differential backups if supported by the service.
- Continuous transaction logs/binlog/WAL shipped per RPO requirements.
- Daily/weekly/monthly retention tiers.
- Encryption with managed keys.
- Copies in a separate account/project/subscription or region.
- Separation of restore permissions from backup deletion permissions.
- Automated checks on job status and backup age.
- Periodic restore tests into an isolated environment.

Illustrative schedule:

| Type | Frequency | Sample Retention |
| --- | --- | --- |
| Transaction logs | Continuous or per service capability | Long enough to satisfy PITR |
| Incremental | Every 6 hours | 7 days |
| Full backup | Daily | 35 days |
| Monthly archive | Monthly | 12 months |

Frequency and retention must fit RPO, RTO, cost, and data compliance rules. Do not adopt this sample table without verifying the database's actual PITR capabilities.

### 5.4. Object Storage Backups

Evaluate:

- Is versioning enabled on critical buckets/containers?
- Is object lock or immutable retention configured?
- Does replication guard against accidental deletion or corruption?
- Is an independent backup needed alongside replication?
- Are metadata and access policies protected?
- Could lifecycle rules purge prior versions prematurely?
- Are checksums and sample restores tested?

Cross-region replication keeps a copy close to the source, but deletes or overwrites can propagate to the replica. Versioning, retention locks, and independent backups preserve historical recovery.

### 5.5. Configuration and Artifact Backups

Data is not the only thing requiring backups. Retain:

- Infrastructure as Code and pinned module versions.
- Container image digests and SBOMs.
- Released deployment manifests/Helm charts.
- Policies, firewall rules, and route configurations.
- DNS records and certificate inventories.
- Runbooks, dependency diagrams, and contact/escalation lists.
- Restore and business validation scripts.

Never store plaintext secrets in backup repositories. Secret backups must use controlled vault/key management mechanisms with dedicated recovery procedures.

### 5.6. Immutable Backups and Privilege Separation

To mitigate ransomware or compromised credentials:

- Use a dedicated backup vault/account.
- Separate permissions to create, read, and delete backups.
- Enable retention locks or immutability where supported.
- Require multi-party approval for destructive actions.
- Enforce MFA and break-glass access procedures.
- Ship audit logs to an independent destination.
- Test restores using a separate DR identity.

A backup that the same production credential can delete immediately carries high risk if that credential is compromised.

## 6. Choosing a DR Model

### 6.1. Backup and Restore

The recovery site maintains no full compute footprint. During an incident, the team provisions networking, identity, and compute, and restores data from backups.

Pros:

- Lower ongoing cost due to minimal standby capacity.
- Simpler architecture.
- Suitable for workloads with longer RTOs.

Trade-offs:

- Provisioning and restoring can take substantial time.
- Depends on quotas, capacity availability, and artifact reachability.
- RTO must be proven via rehearsal.

### 6.2. Pilot Light

Minimal core data or foundation components remain active in the recovery site. When needed, scale up compute, configure applications, and shift traffic.

Pros:

- Faster than backup and restore.
- Avoids maintaining full production capacity.
- Fits critical workloads with moderate scale.

Trade-offs:

- Requires reliable automation to scale up.
- RTO depends on quotas and compute provisioning time.
- Standby configuration can drift if not tested regularly.

### 6.3. Warm Standby

The recovery site runs a scaled-down copy of the workload at low capacity. On failover, scale up replicas or node capacity, verify data, and shift traffic.

Pros:

- Achieves shorter RTOs.
- Most dependencies are already provisioned.
- Supports continuous health verification.

Trade-offs:

- Incurs cost to maintain the standby environment.
- Must keep configs, images, secrets, and databases synchronized.
- Scaled-down capacity may fail to absorb peak load immediately on failover.

### 6.4. Hot Standby or Active-Active

Hot standby maintains a near-ready recovery environment, typically with active replication and substantial capacity. Active-active serves live traffic from multiple sites simultaneously.

Pros:

- Minimizes switchover time.
- Can distribute load and increase resilience.

Trade-offs:

- High cost.
- Complex consistency, split-brain, and conflict management.
- Demands strict routing, data ownership, and failback engineering.

### 6.5. Selection Matrix

| Strategy | Relative RPO/RTO | Standby Cost | Complexity |
| --- | --- | --- | --- |
| Backup and restore | Higher | Low | Low to medium |
| Pilot light | Medium | Low to medium | Medium |
| Warm standby | Low to medium | Medium to high | High |
| Hot standby | Low | High | High |
| Active-active | Potentially very low | Very high | Very high |

No single model is optimal for every service. Choose based on BIA, consistency needs, RPO/RTO, operational maturity, and budget.

## 7. Designing the Recovery Region Architecture

A recovery region requires components arranged along the proper dependency graph—not merely VMs or containers.

### 7.1. Layers to Prepare

**Foundation**

- Accounts/projects/subscriptions and billing.
- VPC/VNet, subnets, routes, firewalls, and NAT.
- DNS, private zones, endpoints, and connectivity.
- IAM, workload identities, KMS, and secret access.
- Quotas, capacity, and image availability.

**Data**

- Database replicas or backups/PITR.
- Object replication/versioning.
- Queue retention/archival or replay strategy.
- Regenerable caches.
- Encryption keys and backup catalogs.

**Compute/Application**

- Container registry mirrors or image pull access.
- VM images/templates or node pools.
- Deployment manifests and IaC.
- APIs, workers, schedulers, and background tasks.
- Load balancers, ingress, and health checks.

**Operations**

- Monitoring, logging, and alerting.
- Runbooks, contact lists, and change records.
- DR identities and break-glass access.
- Test data and business validation scripts.

### 7.2. Recovery Dependency Graph

~~~mermaid
flowchart TD
    A["DR declaration / recovery decision"] --> B["Account, quota and access"]
    B --> C["Network, DNS private, firewall"]
    B --> D["KMS, identity and secrets"]
    C --> E["Storage and database recovery"]
    D --> E
    C --> F["Compute capacity and runtime"]
    D --> F
    E --> G["Deploy API and workers"]
    F --> G
    G --> H["Service discovery and load balancer"]
    H --> I["Smoke test and data validation"]
    I --> J["Traffic cutover"]
    J --> K["Business verification and monitoring"]
~~~

Some steps can run in parallel, such as network provisioning and artifact verification. However, applications must not accept traffic before databases, identities, and critical dependencies are ready.

### 7.3. Quotas and Capacity

Quotas are permitted usage ceilings; capacity is the physical/logical hardware the provider can actually allocate at a given location and moment. Available quota does not guarantee VM/GPU/instance type capacity will be available.

Before rehearsing:

- Check compute, IP, disk, load balancer, and database quotas.
- Verify target instance families/zones can be provisioned.
- Procure capacity reservations if RTO requires them and the service supports them.
- Verify subnets have sufficient free IPs.
- Check API rate limits, database connection limits, and queue throughput limits.

## 8. Building the Recovery Runbook

The runbook must be executable by another on-call engineer even when the original author is unavailable.

### 8.1. Roles

| Role | Responsibility |
| --- | --- |
| Incident commander | Coordinates response, authorizes state transitions, maintains timeline |
| DR lead | Coordinates technical steps and recovery site operations |
| Database owner | Selects restore point, executes restore, verifies consistency |
| Platform/compute owner | Provisions compute, node pools, containers, and scaling |
| Network/DNS owner | Manages networking, ingress, routing, and traffic cutover |
| Security/IAM owner | Manages identity, KMS, secrets, audits, and emergency access |
| Application owner | Executes smoke tests and business validation |
| Communications lead | Updates stakeholders on status |
| Scribe/observer | Records timestamps, evidence, blockers, and action items |

In smaller teams one person may wear multiple hats, but approval authority and execution of sensitive operations should still be clearly separated.

### 8.2. DR Activation Criteria

Sample criteria:

- Primary region is unavailable beyond a defined duration threshold.
- Estimated production recovery time exceeds RTO.
- Widespread data corruption requires restoring from a clean backup.
- Incident commander and business owner jointly approve activation.

Do not trigger automatic failover on a brief health check blip. Require clear thresholds, verification, and anti-flapping safeguards.

### 8.3. Phased Runbook

| Phase | Tasks | Evidence to Capture |
| --- | --- | --- |
| 1. Declare | Confirm incident, T0, scope, and DR decision | Incident ID, timestamp, approver |
| 2. Select | Choose recovery site and restore point | Backup ID, log position, rationale |
| 3. Foundation | Verify access, quotas, networking, keys, and secrets | IaC run output, policy checks |
| 4. Data | Restore DB/objects/queues in order | Restore job ID, checksums, data validation |
| 5. Compute | Create nodes/VMs/tasks and deploy workloads | Image digest, replica count, health |
| 6. Validate | Check dependencies, APIs, and business flows | Smoke tests, reconciliation report |
| 7. Cutover | Shift traffic per plan | DNS/LB changes, traffic share |
| 8. Stabilize | Monitor SLOs and post-switch errors | Dashboards, alerts, business sign-off |
| 9. Close | Record RPO/RTO, cleanup, and failback plan | Timeline, report, action items |

## 9. Preparing for Cutover

Cutover shifts workloads or traffic from a source environment to a target environment in a controlled sequence. Cutover occurs during planned migrations as well as DR failovers. Regardless of context, data, traffic, dependencies, and rollback must be tightly controlled.

### 9.1. Choosing a Cutover Method

| Method | Execution | Pros | Risks |
| --- | --- | --- | --- |
| DNS switch | Update DNS records to new endpoint | Simple, works across architectures | TTL/caching prevents instant cutover |
| Load balancer switch | Switch backend or target group | Faster traffic control in some architectures | Depends on control plane and health checks |
| Gateway route switch | Shift routes/weights at gateway | Enables canary or traffic splitting | Must keep policies and routes synchronized |
| Blue-green | Build parallel environment, then shift traffic | Clear rollback point before new writes occur | Requires schema compatibility and dual-environment cost |
| Weighted traffic shift | Gradually increase target traffic share | Lower risk when validation is strong | Unsuitable if writes are asynchronous |

Low DNS TTLs help resolvers update faster, but do not flush caches in every client. Verify application connection pooling, keep-alive settings, and client DNS caching.

### 9.2. Pre-Cutover Data Consistency

If a system allows concurrent writes to both source and target without a consistency design, conflicts or lost transactions can occur.

A single-writer cutover typically includes:

1. Confirming replication health and lag within thresholds.
2. Posting maintenance notice or switching the API to read-only if required.
3. Stopping producers from generating new writes.
4. Draining in-flight requests and waiting for active transactions to complete.
5. Letting queue consumers finish or recording remaining offsets.
6. Syncing final transaction logs/objects.
7. Verifying the target reached the final data point.
8. Switching write authority to the target.
9. Shifting traffic and running business checks.

Never declare zero data loss solely because replication lag displays zero at a single instant. Verify the final transaction, log position, queue offsets, and out-of-band data flows.

### 9.3. Freeze Window

Systems without multi-writer support may require a freeze window:

- Reject or queue new writes.
- Return a controlled maintenance response.
- Allow read requests if data remains consistent.
- Wait for in-flight transactions to finish.
- Capture final log/offset markers.
- Open writes on the target only after verification.

The freeze window must fit inside the RTO budget and be communicated in advance.

## 10. Detailed Cutover Runbook

### 10.1. Pre-Cutover

- [ ] Change window and approvers confirmed.
- [ ] Recovery site foundation fully provisioned.
- [ ] Backup/replication health meets requirements.
- [ ] Restore point and transaction log chain verified.
- [ ] Images, manifests, and IaC match target versions.
- [ ] Secrets, certificates, and workload identities verified.
- [ ] Target database is in the proper role and not accepting premature writes.
- [ ] Queue producers/consumers have a pause/resume plan.
- [ ] DNS/LB/gateway routes prepared.
- [ ] Smoke test and business validation owners assigned.
- [ ] Rollback/failback criteria agreed.
- [ ] Communication and escalation channels active.

### 10.2. During Cutover

1. Incident commander declares cutover start and logs `T_cutover_start`.
2. Scribe logs every action and timestamp.
3. Stop or restrict writes on the source per runbook.
4. Drain active API requests and running workers.
5. Wait for replication and log shipping to reach the final point.
6. Promote database role or restore target to writable per procedure.
7. Update secret/config endpoints if required.
8. Switch load balancer/gateway backends or DNS.
9. Run smoke tests over a user-representative network path.
10. Execute synthetic transactions and validate data.
11. Ramp traffic incrementally if using weighted shifts.
12. Business owner confirms full traffic opening.

### 10.3. Post-Cutover

- [ ] Error rates and latency within thresholds.
- [ ] Database connections and query latency stable.
- [ ] Queue backlog draining or not growing abnormally.
- [ ] No duplicate payment/order transactions.
- [ ] Objects and files accessible.
- [ ] Logs, metrics, and traces arriving in the expected systems.
- [ ] Alerts active and not pointing to stale endpoints.
- [ ] DNS, certificates, and third-party callbacks working.
- [ ] Single authoritative data writer confirmed.
- [ ] Service restoration timestamp recorded to compute actual RTO.

## 11. Rollback and Failback

Rollback reverts to the previous version or environment when cutover fails acceptance criteria. Failback transitions the service from the recovery site back to the primary site after the primary site recovers. The two operations are related but distinct.

### 11.1. Rollback Before New Writes on Target

If the target has not accepted new writes and the source remains consistent, rollback can be simpler:

1. Stop traffic to the target.
2. Restore routing back to the source.
3. Verify the source remains the authoritative writer.
4. Re-open traffic and run smoke tests.
5. Document rollback rationale and evidence.

### 11.2. After the Target Has Accepted New Writes

Never simply flip traffic back to the source once the source is behind. Doing so risks losing recent writes or causing split-brain.

You must:

1. Halt or fence writes on the target.
2. Establish the current source of truth.
3. Synchronize new data from the target back to the source or another recovery destination.
4. Verify transaction logs, sequences, queue offsets, and object versions.
5. Run consistency checks and business reconciliation.
6. Switch roles/traffic only after the data owner signs off.

If safe reverse replication is unavailable, remain on the recovery site and plan a separate failback.

### 11.3. Failback Plan

A failback plan requires:

- Verification that the primary site is stable.
- Confirmation that the root cause has been remediated.
- Plan to synchronize data back from the recovery site.
- Procedure for switching database roles.
- Verification of identities, secrets, certificates, and networking.
- Cutover window and rollback plan.
- Post-switchover business validation.

Do not fail back just because the primary site came back online. Verify its capacity, data consistency, and fault tolerance first.

## 12. Rehearsing Cutover Safely

Rehearsals must validate runbooks in a controlled setting. Start in staging or an isolated recovery environment, and move to partial production cutovers only with explicit approval.

### 12.1. Rehearsal Types

| Type | Scope | Objective |
| --- | --- | --- |
| Tabletop | Paper-based discussion and decision walkthrough | Roles, escalation, and decision points |
| Restore drill | Restore backups into an isolated environment | Verify backup usability |
| Component cutover | Switch a single service or dependency | Networking, identity, and health |
| Partial traffic shift | Shift a controlled slice of test traffic | Routing and application behavior |
| Full DR exercise | Recover entire defined scope | End-to-end RPO/RTO |
| Failback rehearsal | Test returning data and traffic back | Consistency and return workflow |

### 12.2. Guardrails

Before rehearsing:

- Appoint a facilitator and an authority empowered to abort.
- Use test tenants/data or tightly controlled traffic.
- Block outbound side effects to payments, email, SMS, or external systems unless authorized.
- Set explicit cost and time caps.
- Confirm production endpoints will not be altered unexpectedly.
- Take safe snapshots/backups before any write-risking steps.
- Define explicit abort criteria.

### 12.3. Abort Criteria

Examples:

- Target data is inconsistent or source of truth is ambiguous.
- Encryption keys or access permissions cannot be verified.
- Smoke tests trigger unintended real external side effects.
- Production error rate breaches threshold.
- Remaining RTO is insufficient to finish safely.
- Authorized lead requests an abort.

When aborting, record data and traffic state at the moment of halt. Do not automatically tear down the test environment until confirming no investigation artifacts are still needed.

### 12.4. Sample Rehearsal Scenario

**Scenario:** Region A becomes unavailable. Recovery Region B hosts a database replica and warm standby compute. Goal is to fail over Orders API to Region B.

| Time | Action | Evidence |
| --- | --- | --- |
| T0 | Simulate incident and start timeline | Incident record |
| T+2 min | Monitoring alerts; incident commander confirms | Alert and acknowledgment |
| T+4 min | Declare DR, select recovery site | Decision log |
| T+7 min | Verify quotas, networking, identity, and KMS | Checklist pass |
| T+10 min | Freeze writes on simulated source | Application state |
| T+12 min | Verify replication/log position | Database evidence |
| T+16 min | Promote/restore target per runbook | DB role/status |
| T+20 min | Validate API, queue, objects, and payment sandbox | Smoke/business tests |
| T+23 min | Shift test traffic | LB/DNS/gateway changes |
| T+27 min | Confirm SLOs and business owner sign-off | Dashboards/approval |

Timings are illustrative for scenario planning. Actual RTO must come from real timestamps captured during the exercise.

## 13. Measuring Actual RPO and RTO

### 13.1. Actual RPO

Actual RPO is the gap between the incident timestamp and the newest recoverable consistent data point.

~~~text
Actual RPO =
    T_incident
  - T_latest_consistent_recovery_point
~~~

Example:

| Milestone | Timestamp |
| --- | --- |
| Incident starts | 10:00:00 |
| Latest full backup | 08:00:00 |
| Last replayable transaction log | 09:57:30 |
| Consistent data point after restore | 09:57:30 |
| Actual RPO | 2 minutes 30 seconds |

If the target RPO is 5 minutes, the result passes. If logs are missing and recovery only reaches 08:00, actual RPO is 2 hours and fails.

Never treat backup completion timestamp as the data recovery point if the backup requires transaction logs or additional recovery steps.

### 13.2. Actual RTO

~~~text
Actual RTO =
    T_service_restored
  - T_disruption_start
~~~

Example:

| Milestone | Timestamp | Cumulative Duration |
| --- | --- | ---: |
| Service disrupted | 10:00 | 0 min |
| Incident detected | 10:02 | 2 min |
| DR declared | 10:04 | 4 min |
| Network/identity ready | 10:08 | 8 min |
| Database restore/promote complete | 10:16 | 16 min |
| API healthy | 10:20 | 20 min |
| Traffic shifted and smoke test passed | 10:24 | 24 min |

If the target RTO is 30 minutes, an actual RTO of 24 minutes passes the defined criterion. Measuring only until the database comes online at minute 16 understates the time required before users can actually use the service.

### 13.3. Time Breakdown

Break down elapsed time by stage:

- Detection and declaration.
- Access/approvals.
- Foundation provisioning.
- Data recovery.
- Application startup.
- Traffic cutover.
- Validation.

Some stages run concurrently. When totaling, use the actual timeline to avoid double-counting overlapping intervals.

### 13.4. Timestamp Accuracy

- Synchronize clocks against a standard time source.
- Record UTC and keep timezones explicit.
- Prefer timestamps from audited systems when available.
- Log start time, completion time, and actor.
- Record log positions/offsets alongside timestamps if supported by databases or queues.

## 14. Post-Restore Consistency Checks

A successful restore means more than a database reporting `Online`. Validate across multiple layers.

### 14.1. Database

- Schema/version matches expectations.
- Row counts or key aggregates align.
- Latest transactions are readable and in valid states.
- Foreign keys and constraints remain valid.
- Sequences/identity counters have not regressed.
- Required indexes and stored procedures exist.
- Applications can read/write using intended identities.

### 14.2. Objects and Files

- Object counts or manifests are complete.
- Checksums/hashes match.
- Versions and metadata are intact.
- Access permissions and encryption keys work.
- No incomplete multipart uploads are treated as complete objects.

### 14.3. Queues and Events

- Offsets/sequences are restored accurately.
- Unprocessed messages are not lost beyond RPO.
- Messages can be redelivered without duplicate side effects.
- Dead-letter messages are preserved for investigation.
- Producers/consumers do not dual-write or process out of order.

### 14.4. Business Workflows

Run synthetic end-to-end transactions:

- Create a test order.
- Fetch the order by ID.
- Confirm sandbox payment status.
- Generate an invoice or artifact.
- Verify event emission and worker processing.
- Reconcile input versus output transaction counts.

Never use synthetic test data to declare production data integrity verified. For production rehearsals, tag test records clearly and isolate side effects.

## 15. Security in Backup and Recovery

Backups may hold the entire system's sensitive data. The recovery environment must be protected to production standards.

- Encrypt backups at rest and in transit.
- Protect KMS keys, key policies, and decryption permissions.
- Separate backup, restore, and delete permissions.
- Enforce MFA/break-glass procedures.
- Enable immutable retention where appropriate.
- Restrict network access in the recovery environment.
- Never make databases or object buckets public just for rehearsals.
- Sanitize or anonymize data if only structural testing is needed.
- Audit all restore and cutover actions.
- Never write secrets or personal data into logs or runbooks.
- Maintain a credential rotation procedure after incidents if exposure is suspected.

If encryption keys cannot be recovered, backups may be unusable. Therefore, test KMS/key vault recovery alongside backups—without duplicating keys insecurely.

## 16. Automation and Change Control

### 16.1. Infrastructure as Code

IaC rebuilds:

- VPC/VNet, subnets, routes, and firewalls.
- Load balancers, gateways, and DNS.
- Compute node pools, VMs, and container services.
- Identities, roles, and policies.
- Storage, backup vaults, and replication.
- Monitoring, alerts, and log destinations.

IaC must be version-controlled, reviewed, and pre-tested. Never store plaintext secrets in state files or repositories; use encrypted state backends with access controls.

### 16.2. Automation Pipeline

A DR pipeline can be divided into stages:

1. Preflight: verify permissions, quotas, backups, and recovery site readiness.
2. Foundation: provision networking, identity, and secret integration.
3. Data: restore or promote databases/objects.
4. Compute: deploy images and workloads.
5. Validate: run health, consistency, and smoke checks.
6. Cutover: execute only past an explicit approval gate.
7. Observe: monitor SLOs and automate alerting.

Never automate destructive steps or write-authority switches without an approval gate and pre-flight checks.

### 16.3. Drift Detection

Compare live configuration against IaC:

- Network rules.
- IAM roles/policies.
- Database parameters.
- Backup schedules/retention.
- Deployed images/configs.
- DNS and load balancer routes.

Drift can cause the recovery site to diverge from the tested environment. Run drift checks before every rehearsal and prior to renewing DR readiness sign-off.

## 17. Costing the Plan

DR cost includes both data protection costs and recovery readiness costs.

| Category | Items to Account For |
| --- | --- |
| Backup | Storage, requests, retrieval, retention, and immutable vaults |
| Replication | Data transfer, replica compute/storage, and log shipping |
| Standby | VM/node/container capacity, standby databases, and load balancers |
| Recovery | Restore operations, temporary capacity, and data transfer |
| Security | KMS, auditing, secret vaults, and access reviews |
| Observability | Logs, metrics, traces, and alerts in the recovery region |
| People | On-call, rehearsals, reviews, and maintenance |
| Cutover | Change windows, dual-run periods, and validation |

### 17.1. Strategy Cost Comparison

| Strategy | Steady-State Cost | Incident-Time Cost |
| --- | --- | --- |
| Backup and restore | Lower backup/storage; near-zero standby compute | Spike in compute, restore, and data transfer |
| Pilot light | Data replication and minimal foundation | Provision compute and scale up |
| Warm standby | Maintaining scaled-down workload capacity | Scale standby up to production |
| Hot standby | Maintaining most capacity | Faster cutover, ongoing high operating cost |
| Active-active | Two or more sites running live | Higher load on surviving site and consistency overhead |

Do not simply pick the lowest monthly bill. Weigh DR cost against the business loss incurred if RPO/RTO targets are missed.

### 17.2. Cost per Recovery

Calculate:

~~~text
Cost per recovery exercise =
    Backup/retrieval cost
  + Temporary compute
  + Data transfer
  + Test environment
  + Labor cost
~~~

Tracking cost per exercise helps calibrate rehearsal frequency and automation investment. However, never skip critical restore tests just to save test spend.

## 18. Capstone Deliverable Pack

Learners should submit a documentation pack thorough enough for another team to review and execute.

### 18.1. Architecture Pack

- Production and recovery site diagrams.
- Dependency graph and data flows.
- Failure domains and recovery boundaries.
- Inventory of protected components.
- Ownership responsibility matrix.

### 18.2. Backup Policy

- Data classification.
- Backup frequencies and retention.
- Encryption, key management, and immutability.
- Replication and off-site copies.
- Restore test cadence.
- Alerts for stale/failed backups.

### 18.3. DR Strategy

- Recovery tiers.
- RPO/RTO targets.
- Chosen DR model and rationale.
- Recovery capacity and quotas.
- Recovery sequence.
- Dependencies and assumptions.

### 18.4. Runbook Pack

- DR declaration criteria.
- Roles and escalation paths.
- Preflight checklist.
- Restore procedures.
- Cutover steps.
- Validation checklist.
- Abort/rollback/failback procedures.
- Cleanup and evidence retention.

### 18.5. Exercise Report

- Scenario, scope, and rehearsal date.
- Participants and approvers.
- Actual timeline.
- Actual RPO/RTO.
- Consistency and business test results.
- Pre/post-cutover SLOs.
- Findings, root causes, and action items.

## 19. Sample Backup Policy

Use the table below as a template to populate for an actual system:

| Data Asset | Owner | Backup Method | Frequency | Retention | Off-Site/Immutable | Restore Test |
| --- | --- | --- | --- | --- | --- | --- |
| Orders DB | Database owner | Full + log/PITR | Per RPO | Per policy | Yes | Monthly |
| Payment state | Payment owner | Native backup + logs | Per RPO | Per policy | Yes | Monthly |
| Invoice objects | Storage owner | Versioning + replication/backup | On change | Per policy | Yes | Quarterly |
| Queues/archive | Platform owner | Retention/archive/replay | Continuous | Per policy | Yes | Quarterly |
| Container images | App owner | Registry replication | Every release | Per release policy | Yes | Every DR exercise |
| IaC/config | Platform owner | Version control + protected backup | Every change | Per policy | Yes | Every DR exercise |
| Secrets/keys | Security owner | Vault recovery procedure | Per lifecycle | Per policy | Controlled | Per key policy |

Do not leave "Per policy" placeholders in a final production policy. Populate explicit values, named owners, and concrete verification methods.

## 20. Sample Cutover Decision Record

Before shifting traffic, the incident commander records:

| Question | Required Evidence |
| --- | --- |
| Does the recovery site have sufficient capacity? | Pass/Fail and evidence |
| Are backups/replicas at the valid restore point? | Backup ID, log position, timestamp |
| Is data consistency satisfied? | Checksums, transaction IDs, reconciliation |
| Are KMS/secrets/identities operational? | Access test and audit log |
| Are APIs/workers healthy? | Probes, smoke tests, and dependency status |
| Are queues safe to resume? | Offsets, backlog, deduplication strategy |
| Are traffic routes prepared? | DNS/LB/gateway diff |
| Has the business owner approved? | Approver name and timestamp |
| Is rollback/failback viable? | Criteria, owners, and concrete steps |

If any mandatory check fails, do not shift full traffic. Continue investigating, run scoped partial tests, or abort per the runbook.

## 21. Sample Rehearsal Timeline

| Event | Timestamp UTC | Owner | Evidence | Notes |
| --- | --- | --- | --- | --- |
| Disruption start |  |  |  | Defined T0 |
| Detection |  |  |  | Alert/acknowledgment |
| DR declaration |  |  |  | Incident commander |
| Recovery site ready |  |  |  | Networking/identity/capacity |
| Data recovery complete |  |  |  | Restore point and validation |
| Application ready |  |  |  | Replicas and dependencies |
| Traffic cutover |  |  |  | DNS/LB/gateway |
| Service restored |  |  |  | Smoke tests and business sign-off |
| Exercise closed |  |  |  | Evidence and cleanup |

Actual RTO runs from disruption start to service restored per the agreed definition. Log exercise closed separately if report wrap-up finishes after service restoration.

## 22. Acceptance Criteria

The capstone passes when evidence covers the following areas:

### 22.1. Backup Readiness

- Backup jobs succeed with alerts for stale/failed runs.
- Copies exist outside the source failure domain.
- Retention/immutability and deletion controls are enforced.
- Data restores cleanly into an isolated environment.
- Encryption keys and restore identities function properly.

### 22.2. Recovery Readiness

- Dependency map and recovery sequence exist.
- Recovery region has verified quotas/capacity or provisioning plans.
- IaC/images/configs are accessible.
- Databases/objects/queues have restore or replay procedures.
- APIs and workers reach readiness after recovery.

### 22.3. Cutover Readiness

- Preflight, approval gates, and cutover runbooks are in place.
- Source/target writer roles are clearly controlled.
- Queues and background processing have pause/resume plans.
- DNS/LB/gateway switch to the correct endpoints.
- Smoke tests and business validation pass.
- Abort, rollback, and failback criteria are defined.

### 22.4. RPO/RTO Evidence

- Actual RPO is computed from the consistent restore point.
- Actual RTO is computed from disruption to service restoration.
- Timestamps and evidence are auditable.
- Results are compared against targets with explicit pass/fail verdicts.

### 22.5. Operational Readiness

- Owners, on-call rotations, and escalations are assigned.
- Logs, metrics, traces, and dashboards exist.
- Findings have tracked action items.
- Retest schedules and accountable owners are assigned.

## 23. Self-Assessment Rubric

| Category | Weight | Passing Standard |
| --- | ---: | --- |
| BIA, scope, and RPO/RTO | 15% | Targets have owners, definitions, and business rationale |
| Backup policy and data protection | 20% | Covers frequency, retention, encryption, off-site/immutable copies, and restore proof |
| Recovery architecture | 15% | Clear dependencies, quotas, capacity, and recovery ordering |
| Cutover/rollback/failback | 20% | Runbooks enforce approval gates, writer control, validation, and return criteria |
| Rehearsal and evidence | 15% | Includes timeline, actual RPO/RTO, consistency, and business tests |
| Security, cost, and operations | 10% | Covers IAM, KMS, audits, cost, and ownership |
| Documentation quality | 5% | Another engineer can execute directly from the runbook |

Rating levels:

- **Not Passing:** missing any core component or lacking restore/cutover evidence.
- **Passing:** meets objectives with runbooks and a controlled rehearsal.
- **Good:** includes automation, complete evidence, bottleneck analysis, and retested action items.
- **Excellent:** validates multiple failure scenarios, failback, cost optimization, and data-driven improvements from rehearsal metrics.

## 24. Review Questions

1. Which business requirements drive the RPO/RTO for each data asset?
2. Can backups be deleted by the same production identity?
3. If transaction logs are missing, what is the fallback restore point?
4. Does the recovery site have sufficient quotas, IPs, and capacity in the required zones?
5. Are KMS keys and secrets accessible if the primary region is lost?
6. How do you prevent both source and target from accepting writes simultaneously?
7. Which queue messages require replay and how are duplicates prevented?
8. What criteria authorize shifting 100% of traffic?
9. When is rollback no longer safe, requiring continued operation in the recovery site?
10. Who holds authority to declare DR, approve cutover, and confirm business recovery?
11. Which exact timestamps anchor actual RPO and RTO measurements?
12. Which findings must be resolved before the next rehearsal?

## 25. Project Execution Roadmap

1. **Initiate:** identify owners, scope, systems, failure scenarios, and change boundaries.
2. **BIA:** classify services/data and agree on RPO/RTO targets.
3. **Inventory:** catalog compute, storage, networking, identities, artifacts, and dependencies.
4. **Backup design:** specify backup methods, frequencies, retention, encryption, and immutability.
5. **DR design:** choose strategy, recovery region, capacity, and dependency order.
6. **Runbooks:** author restore, validation, cutover, rollback, and failback steps.
7. **Automation:** prepare IaC, scripts, health checks, and approval gates.
8. **Preflight:** verify permissions, quotas, backup freshness, keys, and recovery endpoints.
9. **Rehearsal:** execute in an isolated environment or approved scope.
10. **Measure:** record timeline, actual RPO/RTO, SLOs, consistency, and costs.
11. **Improve:** analyze root causes, assign owners/deadlines, and update runbooks.
12. **Retest:** rehearse remediated steps and confirm targets are met.

## 26. Principles to Remember

1. Backups are trustworthy only once restored and post-restore data is verified.
2. Replication does not replace backups because corruption or deletions can propagate to replicas.
3. RPO measures distance to the newest consistent data point; RTO measures time until the service truly recovers.
4. Recovery must encompass compute, storage, networking, identity, keys, secrets, and dependencies.
5. Cutover requires controlling writer roles, transactions, queues, and traffic.
6. Never roll back to an old source after the target accepted new writes without synchronizing data first.
7. Rehearsals require explicit scope, guardrails, abort criteria, owners, and evidence.
8. Capacity reservations, quotas, and physical capacity are distinct concepts.
9. Every finding needs an owner, deadline, and retest.
10. Runbooks must be clear enough for another on-call responder to execute under pressure.

A backup, recovery, and cutover plan is complete only when it proves three things: data can recover to an acceptable point, workloads resume operating within target time, and traffic can shift to the recovery environment without uncontrolled data loss or duplicate processing. This capstone turns those requirements into reviewable architecture, policies, runbooks, rehearsals, and evidence.
