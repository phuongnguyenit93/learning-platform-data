# Recovery Drills and Verifying Actual RTO and RPO

## Learning Objectives

A Disaster Recovery (DR) plan has value only when the team can execute it under pressure with real data, access permissions, staffing, and dependencies. Standby architecture diagrams or untested runbooks do not prove the system can recover within committed timeframes. Credentials may expire, backups may fail to restore, DNS caching may prolong cutover, replication may lag, and on-call engineers may lack permissions to execute critical steps.

**DR drills** are the process of verifying service and data recoverability against defined disruption scenarios. Two core metrics are:

- **RTO (Recovery Time Objective):** the target maximum time to restore a service or business capability after an incident, per agreed start points and recovery criteria.
- **RPO (Recovery Point Objective):** the maximum acceptable data loss, expressed as the pre-incident time window of data an organization may have to recreate or accept losing.

RTO and RPO are targets to verify, not numbers automatically guaranteed simply by choosing a backup or multi-region service. Drill results must measure actual duration, recovered data point, business integrity, operational capability, and remaining limitations.

This lesson belongs to the **Disaster Recovery** chapter, focusing on **recovery drills and verifying actual RTO and RPO**. In the context of Cloud Architecture, drills must tie to business requirements, networking, compute, databases, storage, deployment models, security, and cost, while evaluating reliability, scalability, and operations under Well-Architected principles.

After this lesson, you will be able to:

- Distinguish RTO, RPO, MTD/MAO, MBCO, availability, and actual recovery time.
- Define start/end points for measuring RTO and methods for measuring RPO by data type.
- Classify workloads by criticality, dependencies, and recovery requirements.
- Select among tabletop exercises, walkthroughs, component tests, restore tests, failover tests, and game days.
- Design DR scenarios with hypotheses, scope, guardrails, success criteria, and stop conditions.
- Validate backups, point-in-time recovery, replication, DNS/networking, IAM, secrets, and capacity.
- Execute recovery in dependency order and verify data integrity and business transactions.
- Measure actual results, capture evidence, identify RTO/RPO deviations, and remediate issues.
- Design runbooks, command roles, communications, escalations, and failback decisions.
- Build improvement plans, drill schedules, and auditable DR budgets.

## 1. Why Must You Run DR Drills?

A system may be designed with daily backups and a cross-region database replica yet still fail to meet recovery targets during a real incident. For example:

- Backup jobs succeed yet backup files are corrupted or missing transaction logs needed for point-in-time recovery.
- Database replicas suffer severe lag; failing over to the replica loses more data than RPO allows.
- Applications boot in the standby region yet cannot reach secrets, KMS keys, private DNS, or external API allowlists.
- Capacity in the standby region handles only partial traffic; after failover, autoscaling cannot expand due to quotas.
- Queues and event consumers restart yet reprocess messages causing duplicate side effects.
- DNS records change yet client resolvers or connection pools hold onto old endpoints.
- On-call staff lack access to the recovery cloud account or lack MFA/devices/credentials in the DR environment.
- Runbooks assume sequential execution by one person, whereas in reality steps interlock or block waiting for approvals.

Drills expose the gap between **intended design** and **proven capability**.

### 1.1. Backup, High Availability, and Disaster Recovery Are Not the Same

| Concept | Objective | Examples |
| --- | --- | --- |
| Backup | Maintain data copies to restore when source data is lost/corrupted | Snapshots, database backups, object versioning |
| High Availability (HA) | Minimize disruption from single-component failures | Multi-AZ databases, redundant instances |
| Disaster Recovery (DR) | Restore workloads when a large failure domain is lost | Cross-region recovery |
| Business Continuity | Sustain business functions at an acceptable level | Temporary manual operating procedures |
| Resilience | Withstand, adapt to, and recover from faults | Bulkheads, retries, failover, restore |

HA does not replace DR. Multi-AZ can protect against zone failures yet does not necessarily protect against accidental deletions that replicate, widespread logic bugs, or region-wide outages. Nor do backups replace HA, because restoring from backups usually takes much longer than failover.

### 1.2. Failure Domains to Verify

Drills can target specific scopes:

- Instances, nodes, or containers.
- Availability Zones.
- Regions.
- Database clusters or storage services.
- Networking, DNS, identity providers, or KMS.
- Control planes, CI/CD, or artifact registries.
- SaaS/external providers.
- People, processes, and access permissions.
- Ransomware, credential compromise, or deleted/corrupted data.

A DR scenario must explicitly describe what is lost and what remains operational. "Region down" is too vague unless it specifies control plane, DNS, identity, data replicas, external dependencies, and operator access.

## 2. Setting RTO and RPO Targets from Business Requirements

### 2.1. What Is RTO?

RTO is the target time window to restore a service or business process to a defined operating level after an incident.

Example: the booking confirmation service has a 60-minute RTO. This means the organization must restore booking confirmation within 60 minutes per the approved definition. It does not necessarily mean all analytics, exports, and reports must return within the same window.

RTO must explicitly state:

- Start point: when the incident occurs, when monitoring detects it, or when the incident commander declares DR?
- End point: when system processes start, endpoints respond, transactions succeed, or full capacity/SLOs are met?
- Scope: a single service, a user journey, or an entire business process?
- Load condition: smoke test, minimum viable load, or production-representative load?
- Geographic/boundary scope: one AZ, region, account, or provider?

Without agreeing on start/end points, two drills cannot be compared.

### 2.2. What Is RPO?

RPO is the maximum acceptable data loss upon recovery. It can be expressed in time, yet measuring it in practice requires identifying the last protected data record or transaction.

For example, a 5-minute RPO means the organization accepts potentially recovering to a state up to 5 minutes prior to the incident, per the authoritative data and chosen recovery method. It does not guarantee every record from the last five minutes survives; replication/backups and transaction commits must be verified.

### 2.3. MTD/MAO and MBCO

- **MTD (Maximum Tolerable Downtime)** or **MAO (Maximum Acceptable Outage):** the maximum outage duration the business can endure before consequences exceed acceptable thresholds.
- **MBCO (Minimum Business Continuity Objective):** the minimum service level required during or immediately after an incident.
- **RTO:** target time to recover a specific service/capability.
- **RPO:** maximum tolerable data loss measured in time.

RTO should be smaller than MTD/MAO to leave time for verification, clearing backlog, and returning to normal operations. MBCO helps determine whether recovery can proceed in phases rather than waiting for every feature.

### 2.4. Business Classification Example

| Capability | Illustrative MTD | Target RTO | Target RPO | Recovery MBCO |
| --- | ---: | ---: | ---: | --- |
| Booking confirmation | 2 hours | 45 minutes | 1 minute | Core booking confirmation/lookup |
| Payment status | 1 hour | 30 minutes | 30 seconds | Status lookup and reconciliation |
| Search/recommendations | 8 hours | 4 hours | 1 hour | Basic search; recommendations may be omitted |
| Notifications | 24 hours | 8 hours | 15 minutes | Queues preserved and backfilled |
| Analytics dashboard | 48 hours | 24 hours | 24 hours | Latest report with clear watermark |

These numbers are examples for practice. Each target must be confirmed by the business owner based on revenue, customers, regulations, contracts, data, and investment capacity. Never copy one target table across every module.

## 3. RTO Must Measure the Entire Recovery Chain

A common mistake is measuring from when the database restore starts until the restore command reports success. In reality, business recovery includes many more steps.

~~~mermaid
flowchart LR
    D["Incident detected"] --> A["Declare DR / decide strategy"]
    A --> F["Provision/failover infrastructure"]
    F --> N["Network, DNS, IAM, secrets"]
    N --> DB["Restore/promote database"]
    DB --> APP["Deploy/start application"]
    APP --> V["Validate data and dependencies"]
    V --> T["Business transaction tests"]
    T --> C["Open traffic / scale capacity"]
~~~

End-to-end duration may include:

1. Incident detection and confirmation.
2. Declaring DR and activating roles.
3. Selecting the recovery point and recovery strategy.
4. Provisioning compute/network/storage or shifting traffic.
5. Restoring/promoting databases and verifying data.
6. Restoring secrets, identity, certificates, and configuration.
7. Deploying applications, workers, schedulers, and integrations.
8. Running smoke tests, integrity checks, and business transactions.
9. Opening traffic under control and scaling capacity.
10. Verifying SLOs, backlog, and post-recovery stability.

Measuring only the database restore step leaves critical time out of reported RTO.

### 3.1. Breaking Down RTO by Workstream

| Workstream | Planned Duration | Actual Duration | Dependencies/Owner |
| --- | ---: | ---: | --- |
| Declare incident | 5 minutes | Measured during drill | Incident commander |
| Network/IAM/secrets | 10 minutes | Measured during drill | Cloud/platform |
| Database recovery | 20 minutes | Measured during drill | DBA/data |
| Compute/application | 15 minutes | Measured during drill | App/platform |
| Validation/business tests | 10 minutes | Measured during drill | QA/business |
| Traffic ramp-up | 10 minutes | Measured during drill | SRE/operations |
| **Reference sequential total** | **70 minutes** | **Measured end-to-end** | |

Some workstreams can execute in parallel. Do not simply sum all durations if the dependency graph allows concurrent execution; measure the critical path. Conversely, never assume parallelism if data, permissions, or owners are missing.

## 4. Measuring RPO Using Real Data

RPO is not just the interval between two backup timestamps. Check which transactions were committed, replicated, logged, or persisted outside the failing system at the instant of failure.

### 4.1. Marker Transaction Set

During drills, you can generate periodic marker transactions with monotonically increasing sequences and timestamps from a synchronized source:

~~~sql
CREATE TABLE dr_recovery_marker (
    marker_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    payload_checksum VARCHAR(128) NOT NULL
);
~~~

A generator periodically writes markers to the source database. After failover/restore, the recovery team inspects the highest surviving marker, checksums, and sequence gaps. Ensure marker transactions traverse the exact protected commit path; a marker written to another DB or only to cache does not prove business data was protected.

### 4.2. Calculating the Recovery Point

Example:

- Simulated incident timestamp: 12:00:00 UTC.
- Last committed source transaction before incident: 11:59:58 UTC.
- Latest verified transaction present on recovery target: 11:59:52 UTC.

~~~text
Observed data gap
  = Incident time - Latest verified recovered commit
  = 12:00:00 - 11:59:52
  = 8 seconds
~~~

If target RPO is 30 seconds, this run passes. However, repeat under peak load, elevated replication lag, and different failure modes. One test does not prove RPO under all conditions.

### 4.3. Verifying Integrity, Not Just the Latest Record

Beyond markers, verify:
- Continuous transaction sequences or explain any gaps.
- Booking/payment/ledger record counts and totals.
- Foreign keys and business invariants.
- Checksums/manifests for objects/files.
- Outboxes/inboxes and event offsets.
- Absence of duplicate side effects after replay.
- Document any lost, reordered, duplicated, or reconciliation-needed records.

A database showing a recent timestamp yet missing intermediate transactions can still violate business RPO.

## 5. Classifying Recovery Strategies

DR strategies typically trade standby maintenance cost against recovery speed.

| Strategy | Description | Relative Cost | Potential RTO/RPO | What Must Be Verified |
| --- | --- | --- | --- | --- |
| Backup and restore | Restore from backups/snapshots and rebuild environment | Lower during normal ops | Longer RTO; RPO per backup/log | Restore duration, backup integrity, keys, catalogs |
| Pilot light | Minimal foundational tier always present in DR region | Medium | Faster than backup-only | Capacity scale-up, config, data replication |
| Warm standby | Nearly complete environment running at reduced capacity | Higher | Shorter RTO; RPO per replication | Promotion, scaling, DNS, data lag |
| Multi-site active/passive | Two ready sites; one primarily serving | High | Can be fast if failover automated | Split-brain, routing, consistency, capacity |
| Active/active | Multiple sites actively serving together | Very high and complex | Can sustain service when one site fails | Conflicts, routing, global state, cost |

A strategy name does not guarantee a specific RTO/RPO. A warm standby lacking quotas or updated images can recover slower than a well-automated pilot light.

### 5.1. Choosing Strategies by Workload

Not every service must use the same DR strategy. The booking write path may need warm standby; analytics may use backup/restore; static assets may replicate cross-region; notifications may rely on queue retention and replay.

Build a dependency map to avoid picking a fast strategy for a service that depends on another service using slower backup restore.

## 6. Pre-Drill Preparation: Inventory and Assumptions

### 6.1. Recovery Inventory

Minimum inventory items:

- Service name, owner, tier, and business criticality.
- RTO/RPO/MTD/MBCO.
- Region, account/project, VPC/VNet, subnets, routes, firewalls.
- Compute images, artifact registries, deployment manifests, and IaC.
- Databases, storage, backup vaults, replication topology.
- KMS keys, certificates, secrets, and identity dependencies.
- DNS zones, endpoints, CDN, WAF, and traffic routing.
- Queues, event topics, schedulers, workflows, and consumer offsets.
- External APIs, allowlists, webhooks, and quotas.
- Monitoring, alerts, logs, traces, and status communication.
- Backup retention, restore test evidence, and last verified date.

Inventories require owners and verification dates. An old documentation URL does not prove a resource still exists.

### 6.2. Recovery Dependency Graph

~~~mermaid
flowchart TB
    IAM["Identity / KMS / secrets"] --> NET["Network / DNS / certificates"]
    ART["Artifacts / images / IaC"] --> APP["Compute / application"]
    NET --> APP
    DATA["Database / object storage"] --> APP
    Q["Queue / event bus"] --> APP
    APP --> EXT["External providers"]
    APP --> TEST["Business validation"]
    DATA --> TEST
    EXT --> TEST
~~~

A restore sequence works only if dependencies are ready. For instance, applications cannot read encrypted backups if KMS keys are unavailable; workers cannot process events if queue policies/identities are unrestored.

### 6.3. Recovery Access

Verify:
- Do on-call engineers have access to the DR account/region?
- Do MFA/devices and break-glass credentials work?
- Which identity accesses secret managers/KMS?
- Do operators have permission to read backups and create compute/networking?
- Are emergency approval workflows functional after hours?
- Are emergency accounts tested and audited?

Never store passwords or recovery secrets in runbooks. Runbooks should point to secret managers and safe privilege-elevation procedures.

## 7. Designing a DR Drill Program

A good program escalates realism and risk progressively. Never test database restore for the first time by shutting down a production region.

### 7.1. Drill Levels

| Type | Execution | Risk Level | Evidence |
| --- | --- | --- | --- |
| Tabletop | Team discusses scenarios and decisions | Low | Decision log, gap list |
| Runbook walkthrough | Step-by-step review/simulation without system changes | Low | Step owners, missing access, ambiguous steps |
| Component restore test | Restore DB/files into an isolated environment | Low–medium | Duration, integrity, restore logs |
| Application recovery test | Stand up app in DR environment and run tests | Medium | End-to-end recovery time |
| Failover/failback exercise | Shift traffic/primary per plan | Higher | Routing, data, consistency, RTO/RPO |
| Game day | Bounded fault injection while real/canary load runs | Scope-dependent | Blast radius, detection, mitigation |
| Full-scale DR exercise | Simulate losing a large failure domain and run on DR site | High | End-to-end evidence, roles, costs |

### 7.2. Drill Objectives Must Be Measurable

Example of a strong objective:

"In staging under simulated traffic at 40% of peak, the recovery team can restore the booking API in Region B within 45 minutes; recovery point is no older than 60 seconds; 100% of valid pre-recovery-point marker transactions survive; payment reconciliation yields zero duplicate charges; the service achieves 95% of target throughput within 15 minutes of opening traffic."

This objective defines concrete measurement criteria. Specify environment, workload, clock, transaction markers, and business tests.

### 7.3. Exercise Charter

Before the drill, document:

- Purpose and scope.
- Scenario and assumed failure domain.
- Impacted systems/tenants/regions.
- Participants, roles, and decision authority.
- Start/stop conditions.
- Safety guardrails and rollback.
- RTO/RPO/SLOs under verification.
- Data classification and environments used.
- Evidence to capture.
- Communication channels.
- Maximum cost or budget guardrails.
- Handling plan if the drill triggers a real incident.

## 8. Roles and Coordination During Drills

Drills need explicit roles. The engineer typing commands should not simultaneously be the sole log keeper and approver for every decision.

| Role | Responsibilities |
| --- | --- |
| Exercise controller | Orchestrates scenario, injects events, keeps scope safe |
| Incident commander | Makes decisions, sets priorities, manages escalations |
| Recovery lead | Coordinates technical recovery workstreams |
| Data lead | Handles recovery, consistency checks, and RPO verification |
| Application lead | Handles deployments, config, integrations, and smoke tests |
| Network/security lead | Handles DNS, routing, IAM, keys, certificates, and firewalls |
| Business owner | Validates MBCO and business transactions |
| Scribe/timekeeper | Records timestamps, decisions, blockers, and evidence |
| Observer | Notes team dynamics and runbook gaps |

In small teams, one person may hold multiple roles, yet must clearly distinguish when they are executing versus approving.

### 8.1. Incident Timeline

Record timestamps using a single time source (UTC or specified timezone):

- T0: fault injected or scenario starts.
- T1: monitoring detects fault.
- T2: incident declared.
- T3: DR decision/activation.
- T4: recovery infrastructure ready.
- T5: data restored/promoted.
- T6: application ready.
- T7: business validation passes.
- T8: traffic opened and service reaches MBCO.
- T9: workload meets normal SLOs or defined steady state.

RTO may be measured from T0 to T8 or another pre-agreed milestone. Never alter definitions after seeing results to turn a failed test into a pass.

## 9. Database and Data Drill Scenarios

### 9.1. Backup Restore

Scenario:
1. Select a backup retained per policy.
2. Verify backup ID, timestamp, retention, and encryption metadata.
3. Restore into a test account/region.
4. Configure permissions, keys, and networking.
5. Open the database in an appropriate state.
6. Run integrity checks and marker validation.
7. Measure from trigger until the application queries successfully and business transactions pass.

Evidence to retain: backup identifier, recovery point, restore start/end, engine/version, error logs, checksums/record counts, cost, and manual steps taken.

### 9.2. Point-in-Time Recovery

PITR must verify that base backups and transaction logs/binlogs/WAL exist up to the desired point. Practice recovering to:
- Immediately before an accidental delete.
- After the last valid transaction.
- Before a faulty migration.

Confirm timezone and timestamp precision; clock skew can pick the wrong recovery point. Test in an isolated environment—never overwrite production sources.

### 9.3. Replication Failover

Scenario steps:
- Write transaction markers continuously on primary.
- Monitor replication lag.
- Simulate primary unavailability.
- Promote replica per procedure.
- Compare sequences/checksums/ledgers.
- Switch application endpoints.
- Test reads/writes, locks, transactions, and connection pools.
- Verify the old primary does not become a parallel writer.

Measure RPO by the last verified transaction on the replica; measure end-to-end RTO until business transactions succeed. Test split-brain and fencing to avoid two primaries accepting writes.

### 9.4. Object Storage and File Data

Test:
- Restoring object versions or backups.
- Verifying lifecycles/retention did not purge needed copies.
- Verifying KMS keys, bucket policies, replication rules, and object locks.
- Checking manifests, checksums, file counts, and partition completeness.
- Reading files using the DR application identity.
- Restoring metadata/catalogs if lakehouse tables rely on transaction metadata.

Object replication does not always synchronize all metadata, versions, delete markers, and permissions. Check exact storage service semantics.

## 10. Network, DNS, Identity, and Security Scenarios

DR may have intact data yet remain unreachable due to control plane dependencies.

### 10.1. DNS and Traffic Routing

Test:
- Do DNS records/zones exist in the recovery account/region?
- Do configured TTLs align with failover goals?
- How long do resolvers/clients cache responses?
- Do health checks accurately detect failures?
- Do CDN/WAF/certificates serve the new endpoint?
- Are outbound allowlists and webhook destinations updated?
- Do connection pools re-resolve endpoints after failover?

Low TTLs do not guarantee instant failover; resolvers and application runtimes have their own caches. Measure from the update timestamp until representative clients hit the new endpoint.

### 10.2. Identity and Secrets

Drill:
- Creating/assuming roles in DR.
- Accessing secret managers and decrypting keys.
- Rotating credentials or activating pre-staged credentials.
- Verifying service identities for applications, workers, and migrations.
- Checking certificate chains and expirations.
- Testing audit trails and break-glass procedures.

Never copy keys/secrets ad hoc from production to another region. Policies and key management must be designed for DR.

### 10.3. Network Capacity

The DR region may use different CIDRs, NAT, firewalls, load balancers, private endpoints, and quotas. Check:
- IP address/subnet capacity.
- Route tables and peering/transit gateways.
- Security group/firewall rules.
- NAT gateway/egress capacity.
- DNS resolvers, private zones, and service discovery.
- Cross-region bandwidth/latency.
- Quotas for load balancers, public IPs, and network interfaces.

## 11. Compute, Application, and Integration Scenarios

### 11.1. IaC and Artifacts

A DR deployment needs reproducible artifacts:

- IaC versions and state backends.
- Immutable container images/packages.
- Compatible runtime/configuration.
- Schema migrations and compatibility.
- Feature flags.
- Secret references.
- SBOMs/signatures where applicable.
- Dependency locks and package registry mirrors/caches.

Verify images/packages still exist and can be pulled from DR. If the artifact registry sits in the lost region, DR deployments may fail to start.

### 11.2. Capacity at the Recovery Site

Do not check only for Pods `Ready`. Run representative load:

- API request rates and latency.
- Worker throughput.
- Database connections and query latency.
- Queue consumer lag.
- CPU/memory autoscaling.
- Cache warm-up and cold-start impact.
- External provider rate limits.
- Compute/network/storage quotas in the standby region.

Warm standby may need to scale from 20% to 100% capacity; quota approval times or slow autoscaling must count toward RTO.

### 11.3. External Dependencies

Payment/email/tax providers may allowlist only production egress IPs. The DR region needs updated IP allowlists. Test webhook URLs, OAuth redirects, API credentials, certificates, rate limits, and provider accounts. Never assume external dependencies automatically recognize platform failover.

## 12. Ordered Recovery and Business Validation

Once infrastructure is up, validate business functionality. A healthy database does not prove bookings/payments work accurately.

### 12.1. Recovery Validation Layers

1. **Infrastructure validation:** active resources, routes, health checks, capacity.
2. **Data validation:** recovery point, checksums, schemas, transaction sequences.
3. **Application validation:** processes, dependencies, authentication, configuration.
4. **Integration validation:** payments, queues, storage, external APIs.
5. **Business validation:** creating/reading bookings, payment statuses, inventory, refunds/reconciliation.
6. **Operational validation:** alerts, logs, access, post-recovery backups.
7. **Traffic validation:** canary, error rates, p95/p99, and throughput.

### 12.2. Business Transaction Tests

Example test flow in DR:
- Create a uniquely tagged test booking.
- Check inventory invariants.
- Send a sandbox payment or test operation.
- Verify booking/payment state.
- Confirm outbox event emission.
- Check notification workers or queues.
- Reconcile the ledger and confirm no duplicates.
- Clean up/close test transactions per policy.

Never use real payments or real customer data without corresponding approvals and controls. Use synthetic/anonymized data and proper sandboxes.

### 12.3. MBCO and Phased Recovery

Not every feature needs to turn on simultaneously. Recovery can proceed in phases:

| Phase | Capabilities | Checks |
| --- | --- | --- |
| 1. Minimum safe service | Authentication, booking lookup, critical writes or read-only mode | Business owner confirms MBCO |
| 2. Core operations | Bookings/payments/inventory | Transaction tests and reconciliation |
| 3. Customer experience | Search, notifications, exports | Freshness and queue lag |
| 4. Full service | Analytics, reporting, non-critical jobs | SLOs, backlog, and data completeness |

Ordering follows business dependencies. In some scenarios read-only is safer than writes; in others, new bookings must pause while lookups stay up.

## 13. Failover, Failback, and Preventing Split-Brain

Failover moves workloads to the recovery site. Failback returns workloads to the primary site or a new steady topology. Failback is often complex because new data accumulated at the alternate site during DR.

### 13.1. Failover Checklist

- Incident commander declares DR and records the timestamp.
- Confirm primary failure domain no longer accepts writes or is fenced.
- Choose recovery point and accept actual RPO.
- Promote database/replica per procedure.
- Update DNS/routing/load balancers.
- Deploy or scale applications/workers.
- Temporarily throttle non-essential workloads.
- Verify transactions, data integrity, and business flows.
- Monitor backlogs, replication, and SLOs.
- Publish service status per communications procedure.

### 13.2. Fencing and Split-Brain

If the primary only lost connectivity from the application yet can still accept writes elsewhere, DR promotion can create two independent writers. Fencing is mandatory: disable writes on the old primary via an appropriate mechanism, confirm leadership/leases/quorum or network isolation before opening the new writer.

Do not rely solely on DNS to stop new clients from hitting the old primary; existing client connections and workers may still connect directly.

### 13.3. Failback

Before failback:
1. Establish the authoritative data source.
2. Sync data changes from the DR site to the target.
3. Reconcile transactions and backlogs.
4. Pause/coordinate writes per the cutover plan.
5. Verify replication lag is zero or within approved thresholds.
6. Shift traffic under control.
7. Monitor errors/latency and rollback triggers.
8. Restart replication/backups protecting the primary site.
9. Record any data divergence and transactions needing manual handling.

Never fail back merely because the primary region shows "green." Prove both sides' data and write authority are consistent.

## 14. Designing Sample Drill Scenarios

### 14.1. Scenario: Primary Region Loss

**Hypothesis:** Region A loses compute and primary database availability. Region B holds a warm standby database and minimum application capacity.

**Objectives:**
- Booking business flow recovers within 45-minute RTO.
- Booking RPO does not exceed 60 seconds.
- Zero duplicate payments or double bookings.
- Search/dashboards can recover after core transactions.
- Traffic opens via canary, reaching 80% of peak test throughput.

**Scope:** staging, synthetic data, provider sandbox, two test regions.

**Guardrails:** do not touch production DNS/traffic; do not delete backups; human controller present; kill switch if resources/costs exceed budget.

**Injects:**
- Replication lag rises prior to incident.
- Primary endpoint becomes unreachable.
- DNS resolvers hold stale caches.
- One secret in DR is expired.
- Primary image registry is unreachable.
- Queue consumers redeliver events after failover.

**Success criteria:** RTO/RPO recorded; markers and business invariants pass; DR app serves correct endpoints; backlogs drain; zero duplicate side effects; runbook backed by evidence.

### 14.2. Scenario: Accidental Data Deletion

**Hypothesis:** an administrative action deletes a set of bookings and event history. Replication propagated the deletion.

**Objective:** PITR to prior to the deletion timestamp, verify records to preserve, and restore recovered data via logical recovery without overwriting valid subsequent transactions.

This test validates backups/PITR and logical recovery procedures rather than merely regional failover.

### 14.3. Scenario: Credential/KMS Unavailable

**Hypothesis:** DR workloads cannot decrypt secrets or backups because permissions/keys depend on the primary region.

**Objective:** prove recovery roles, key replication/availability, and break-glass workflows operate within policy. Do not export/move keys outside controls just to pass the test.

## 15. Measuring and Reporting RTO/RPO Results

### 15.1. Observed RTO

~~~text
Observed RTO
  = Time business service meets the agreed recovery criteria
    - Time the exercise failure begins
~~~

If policy defines start at incident declaration rather than fault injection, record both numbers. Reports must state clock source and timezone.

### 15.2. Observed RPO

~~~text
Observed RPO
  = Incident time
    - Timestamp of latest verified recoverable business commit
~~~

If multiple data types have distinct replication/backup policies, calculate RPO separately per data domain. The booking database achieving 30 seconds does not mean object storage, queues, search indexes, and audit logs do too.

### 15.3. Target vs. Actual RTO/RPO

| Workload/Data Domain | Target RTO | Observed RTO | Target RPO | Observed RPO | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| Booking API | 45 minutes | 52 minutes | 60 seconds | 35 seconds | RTO fail, RPO pass |
| Payment ledger | 30 minutes | 28 minutes | 30 seconds | 42 seconds | RTO pass, RPO fail |
| Search index | 4 hours | 95 minutes | 1 hour | 20 minutes | Pass per example |
| Analytics | 24 hours | 7 hours | 24 hours | 8 hours | Pass per example |

This table only illustrates reporting format. Link every figure to timeline evidence, markers, backup IDs, and validation results. Never mark "Pass" if only process health was checked without business correctness.

### 15.4. Measuring Percentiles Across Multiple Drills

One drill measures a single sample. RTO/RPO vary with:
- Data volume.
- Load and replication lag.
- Regional quotas/capacity.
- Number of dependencies.
- Available staff and permissions.
- Backup age/retention.
- Time of outage and provider health.

Track history across runs, examining median and tail/worst observed values. For critical targets, never design around the fastest run. Maintain margin for adverse conditions and operational variance.

## 16. Post-Drill Evidence and Reporting

Every claim needs evidence:

| Claim | Appropriate Evidence |
| --- | --- |
| Restore completed in 20 minutes | Cloud operation timestamps, restore logs |
| 30-second RPO | Marker sequence, verified commit timestamps |
| Application healthy | Health checks and deployment status |
| Booking flow works | Test booking IDs, database rows, API results |
| Zero duplicate payments | Provider sandbox ledger + internal ledger reconciliation |
| DNS cutover complete | Authoritative/resolver queries and client observations |
| Security roles work | Audit logs, successful authorized operations |
| Capacity sufficient | Load test reports, CPU, latency, queue lag |
| Cost within budget | Cloud cost/resource report for the exercise |

Reports should include:
- Scenario and exercise version.
- Objectives/assumptions/guardrails.
- Timeline.
- Target and observed RTO/RPO.
- Business validation results.
- Impacts and blast radius.
- Manual vs. automated steps.
- Failures/gaps, root causes, severity.
- Action items, owners, due dates.
- Evidence links and how sensitive data was handled.

Never store access tokens, private keys, or PII payloads in evidence packages. Evidence must have proper access control and retention.

## 17. Post-Drill Improvements

Drills generate value only when gaps turn into owned changes.

### 17.1. Classifying Findings

- **Design gap:** architecture cannot meet committed RTO/RPO.
- **Automation gap:** too many manual steps or brittle scripts.
- **Data gap:** missing backups, replication, logs, catalogs, or integrity checks.
- **Security/access gap:** missing permissions, keys, secrets, or network rules.
- **Capacity gap:** DR site lacks quotas/compute/networking.
- **Runbook gap:** missing steps, wrong ordering, or unclear decision criteria.
- **People gap:** missing training, roles, on-call coverage, or vendor contacts.
- **Measurement gap:** missing clocks, markers, logs, or required evidence.

### 17.2. Verifiable Action Items

A good action item specifies:

| Field | Example |
| --- | --- |
| Finding | Database restore exceeded RTO by 15 minutes due to capacity limit |
| Root cause | Restore instance provisioned on low storage tier |
| Corrective action | Update recovery configuration and automate provisioning |
| Owner | Database platform team |
| Due date | Approved target date |
| Verification | Repeat restore test with representative dataset |
| Acceptance | p95 restore duration below target across 3 test runs |
| Evidence | Exercise report/version/run ID |

Avoid vague action items like "improve DR" lacking owners, deadlines, and closure criteria.

### 17.3. Re-Test After Changes

After fixing:
- Run relevant component tests.
- Run an end-to-end exercise if the change affects the critical path.
- Update runbooks and architecture decision records.
- Update RTO/RPO if business/cost decisions changed.
- Train operations teams and verify knowledge transfer.
- Close findings only once evidence meets acceptance criteria.

## 18. Drill Schedule and Maintaining Readiness

Cadence depends on risk, rate of change, and contractual obligations. Sample program:

| Illustrative Cadence | Activities |
| --- | --- |
| Monthly | Verify backup jobs, alerts, replication lag, access permissions |
| Quarterly | Database/file restore tests and tabletops for critical workloads |
| Semi-annually | Application recovery/failover test for one failure domain |
| Annually | Full-scale DR exercise with business owners and relevant vendors |
| After major changes | Re-test impacted paths: region, DB engine, IAM, networking, deployment |

These milestones are examples. Workloads with frequent changes, critical data, or strict regulations may require tighter schedules. Restore tests should happen often enough that backups do not become something that merely "exists on a dashboard."

### 18.1. Unscheduled Drill Triggers

Run out-of-band exercises when:
- Migrating regions/accounts or changing topology.
- Changing database engines, replication modes, or backup policies.
- Changing KMS, identity providers, DNS, or networking.
- Adding critical dependencies or SaaS providers.
- Changing retention, encryption, or data classification.
- An RTO/RPO miss or recent incident exposes gaps.
- Major changes occur in teams/on-call/vendor support.

## 19. Cost and Choosing Drill Depth

DR incurs costs from standby capacity, cross-region replication, backup storage, restore compute, test data, traffic, egress, observability, and engineering time.

### 19.1. DR Exercise TCO

~~~text
DR program cost
  = Standby infrastructure
    + Backup and replication
    + Test environment/runtime
    + Cross-region transfer
    + Monitoring and evidence storage
    + Engineering and exercise time
    + Vendor/support cost
    + Remediation work
~~~

Never skip drills to save money if disruption risk outweighs the savings. Reduce cost by:
- Using controlled synthetic/representative datasets.
- Automating post-test teardown.
- Testing individual components frequently and full exercises less often.
- Bounding load-test traffic within budget.
- Using isolated accounts/projects with quota guardrails.
- Optimizing warm standby by tier instead of duplicating every service.
- Tracking cost per verified recovery exercise.

### 19.2. Cost of False Confidence

If an organization publishes a 30-minute RTO without ever restoring under representative conditions, the business continuity plan rests on false assumptions. The cost of a DR strategy is not just infrastructure—it includes the probability of missing targets, downtime, data loss, and incident response costs.

Investment decisions should rely on business impact analysis and real evidence; do not choose active/active merely because it sounds safer if cost and complexity exceed actual needs.

## 20. Practice Exercise

A booking platform operates in Region A with a primary database, object storage, queues, and 8 application services. Region B maintains an asynchronous database replica, object storage backups, and pilot-light compute. Business requirements:

- Booking service: 45-minute RTO, 60-second RPO.
- Payment ledger: 30-minute RTO, 30-second RPO.
- Search: 4-hour RTO, 1-hour RPO.
- Notifications: 8-hour RTO, 15-minute RPO.

Complete the following:

1. Draw the dependency graph across identity/KMS, networking/DNS, databases, storage, queues, compute, and the external payment provider.
2. Define RTO start/end points and marker methods to measure RPO for each data domain.
3. Write an exercise charter for losing Region A, including scope, roles, guardrails, and stop conditions.
4. Build a recovery timeline showing sequential/parallel workstreams; calculate the critical path.
5. Design component restore tests for database PITR and object storage, including checksum/transaction validation.
6. Design database replica failover; explain split-brain prevention and replication lag measurement.
7. Verify DNS, certificates, secrets, KMS keys, egress IP allowlists, and Region B quotas.
8. Define phased MBCO and minimum business transaction tests.
9. Build an evidence table proving RTO/RPO; explain how to handle Booking passing RTO while Payment misses RPO.
10. Calculate backlog catch-up if queues accumulate 180,000 messages, consumers process 600 messages/second, and new events keep arriving at 300 messages/second.
11. Design the failback plan, fencing, and reconciliation after Region A recovers.
12. Create a post-exercise action register with owners, due dates, and acceptance tests.
13. Propose a drill schedule and TCO aligned with each workload's criticality.

**Self-assessment guidance:** A strong solution defines measurable RTO/RPO criteria, goes beyond infrastructure health checks, verifies data with markers/reconciliation, prevents split-brain during failover, and converts findings into re-testable action items.

## 21. Pre-, During-, and Post-Drill Checklists

### Pre-Drill

- [ ] Business owner approved RTO, RPO, MTD/MAO, and MBCO.
- [ ] Scope/failure domain and assumptions explicitly documented.
- [ ] Inventory of services, dependencies, data, regions, accounts, and owners up to date.
- [ ] Backups/replication/retention/keys verified.
- [ ] Recovery access, MFA, IAM, and break-glass tested.
- [ ] Runbooks cover commands/decisions/validation and escalation.
- [ ] Exercise charter includes guardrails, stop conditions, and rollback.
- [ ] Appropriate test data/sandboxes/providers prepared.
- [ ] Evidence capture, clock source, and timezone aligned.

### During Drill

- [ ] Record timeline T0...Tn and decision log.
- [ ] Inject faults strictly within approved scope.
- [ ] Monitor blast radius and stop conditions.
- [ ] Measure infrastructure, data, application, and business recovery.
- [ ] Measure recovery points via marker/commit evidence.
- [ ] Verify business invariants, duplicates, and reconciliation.
- [ ] Record all manual interventions and blockers.
- [ ] Record quotas, latency, capacity, backlog, and cost.

### Post-Drill

- [ ] Compare target vs. observed RTO and RPO per workload.
- [ ] Verify data integrity and discrepancies.
- [ ] Evaluate MBCO and SLOs after opening traffic.
- [ ] Publish report/evidence and conduct owner review.
- [ ] Log findings with severity, owner, due date, and acceptance criteria.
- [ ] Update runbooks, IaC, architecture, and training.
- [ ] Re-test critical findings before closing.
- [ ] Update DR strategy and TCO when targets prove infeasible.

## 22. Well-Architected Evaluation

| Pillar | Questions When Reviewing a DR Exercise |
| --- | --- |
| **Operational Excellence** | Are runbooks, roles, timelines, evidence, postmortems, and re-tests managed as operational processes? |
| **Security** | Are recovery access, keys, secrets, data masking, auditing, and break-glass secure in the DR region? |
| **Reliability** | Have backup restores, replication, failover/failback, RTO/RPO, and business integrity been empirically proven? |
| **Performance Efficiency** | Do recovery capacity, autoscaling, queue drain, and traffic ramps meet target workloads? |
| **Cost Optimization** | Are standby, backups, replication, exercises, and remediation proportional to business impact? |
| **Sustainability** | Are test resources torn down automatically, redundant replication/backups avoided, and retention managed sensibly? |

**Conclusion:** RTO and RPO are trustworthy only when measured in drills with clear scope, start/end points, marker data, and business criteria. A single successful database restore does not prove full DR; you must validate databases, storage, networking, identity, compute, external dependencies, failover, failback, and operational team readiness. Retain evidence, publish gaps against targets, assign owned action items, and re-test after fixes. That is how DR transforms from a hypothetical document into a proven capability in the spirit of Well-Architected design.
