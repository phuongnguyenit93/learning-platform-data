# Disaster Recovery Drills and Verifying RTO and RPO

An AWS system can run smoothly for months and still fail when recovering from a major incident. Backups may exist yet fail to restore; a standby Region may be provisioned yet lack secrets, images, or quotas; a database may recover yet the application fails to switch endpoints; DNS may update yet clients hold stale connections. Therefore, Disaster Recovery (DR) must be designed, rehearsed, and measured with concrete evidence.

Two essential metrics for setting recovery targets are Recovery Time Objective (RTO) and Recovery Point Objective (RPO). RTO defines the maximum acceptable time for the organization to restore a service after a disruption. RPO defines the maximum acceptable data loss, measured as the interval between the disruption and the most recent recoverable point in data. Both targets stem from business impact and should not be chosen merely because a particular AWS service supports a given figure.

A DR drill tests the full chain: detection, activation decision, infrastructure and data recovery, traffic cutover, business validation, backlog processing, and operational handover. Results must reveal actual RTO/RPO, which step caused delays, what data was lost or inconsistent, recovery costs, and follow-up actions. This lesson guides building an AWS DR capstone from requirements, architecture, and runbooks through to a verification plan.

In the CLOUD_PROVIDERS_AWS module, learners explore Region/AZ infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless to design secure, observable, resilient, and cost-controlled systems. This lesson brings those concepts together into a reviewable, repeatable drill workflow.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between high availability, backups, disaster recovery, and business continuity.
- Explain RTO, RPO, MTD/MAO, and how to measure actual results.
- Use Business Impact Analysis to set recovery targets by business process.
- Build a workload inventory, dependency map, and recovery tiers.
- Compare Backup and Restore, Pilot Light, Warm Standby, and Multi-Site Active/Active.
- Select AWS services for backup, replication, restore, and traffic failover.
- Design DR for S3, DynamoDB, RDS/Aurora, EBS, EFS, and compute.
- Identify requirements for IAM, KMS, secrets, networking, DNS, quotas, and artifacts.
- Write runbooks with owners, activation triggers, stop conditions, and rollback/failback steps.
- Design tabletop, component restore, failover, and failback exercises.
- Measure RTO/RPO using timestamps, data reconciliation, and business validation.
- Estimate DR costs and create post-drill improvement plans.

## 2. Distinguishing HA, Backups, DR, and Business Continuity

### 2.1. High Availability

High Availability (HA) reduces downtime caused by component or infrastructure failures within the designed architecture scope. Examples:

- Deploying compute across multiple Availability Zones.
- Using load balancers for health checks and traffic distribution.
- Using RDS Multi-AZ for intra-Region database failover.
- Using queues to decouple producers from consumers.
- Automatically replacing unhealthy instances or tasks.

HA typically handles single-component or localized failures. It does not guarantee recovery when an entire Region becomes unavailable, data is accidentally deleted, ransomware encrypts data, or a logic bug corrupts data across all replicas.

### 2.2. Backups

Backups create point-in-time or scheduled copies of data for restoration. Backups are essential when:

- Users accidentally delete data.
- Applications write corrupted data.
- A database suffers corruption.
- An account or workload is compromised.
- Data must be restored to a timestamp prior to an incident.

Backups must be isolated from the accounts and workloads that could trigger the original incident. If an application role has permissions to delete both production data and backups, those backups no longer provide independent recovery.

### 2.3. Disaster Recovery

Disaster Recovery is the ability to restore systems and business processes after a major disruption. DR spans data, compute, networking, identity, security, DNS, external dependencies, people, and decision workflows.

A backup alone is not a complete DR plan. To restore a service, you must know:

- Where will data be restored?
- Which infrastructure must be rebuilt?
- Where do secrets, certificates, and KMS keys come from?
- How do endpoints and DNS shift?
- How do you prevent two Regions from accepting writes simultaneously?
- Who validates the data and approves opening traffic?

### 2.4. Business Continuity

Business Continuity (BC) covers plans to keep business operations running during and after an incident, even before IT systems fully recover. For instance, stores may record orders offline, switch to manual workflows, or reconcile transactions once systems return.

DR is one component of BC. Technical recovery targets must align with how the business sustains operations during an outage.

### 2.5. Comparison

| Concept | Core Question | Example |
|---|---|---|
| HA | How do we keep serving when a single component fails? | Multi-AZ, health checks, autoscaling |
| Backup | Can we recover historical data? | AWS Backup, PITR, S3 Versioning |
| DR | How do we restore the service after a major disaster? | Restore in a recovery Region and shift traffic |
| BC | How does the business keep serving customers during downtime? | Offline order capture procedures |

## 3. Understanding and Setting RTO and RPO

### 3.1. Recovery Time Objective

RTO is the target maximum duration to restore a service or process to an acceptable operating level after a disruption. RTO must specify:

- When the clock starts.
- What conditions define the service as restored.
- Which functional scope must be operational.
- Who signs off on recovery.

A practical definition measures from when the disruption renders the service unresponsive until critical business flows operate and the accountable owner confirms recovery. If an organization starts the clock only when an incident is declared, state that explicitly, as detection and decision time would otherwise be excluded.

RTO is more than the duration of a restore command. It can include:

1. Detecting and confirming the disruption.
2. Assessing blast radius.
3. Deciding to activate DR.
4. Isolating or fencing the failed system.
5. Restoring data and infrastructure.
6. Configuring endpoints, identity, and networking.
7. Shifting traffic.
8. Running smoke tests and business validation.
9. Reopening the service and monitoring stability.

### 3.2. Recovery Point Objective

RPO is the maximum data loss acceptable to the business, typically expressed as time. If an outage strikes at 10:00 and the latest recoverable data point is 09:52, potential data loss is 8 minutes.

RPO depends on the backup or replication mechanism:

- Hourly backups can leave nearly an hour of data loss without supplementary logs or replication.
- Point-in-time recovery restores to a chosen second within the service's supported window.
- Asynchronous replication incurs lag and can lose un-replicated recent writes.
- Synchronous replication trades off latency, availability, and failure scope.

Do not infer RPO from nominal backup schedules. Measure the timestamp of the latest data actually recoverable during a drill.

### 3.3. MTD and MAO

Maximum Tolerable Downtime (MTD), sometimes called Maximum Acceptable Outage (MAO), is the longest outage the business can endure before consequences become unacceptable.

RTO must be shorter than MTD and leave room for Work Recovery Time (WRT) if the business must reconcile data, drain backlogs, or catch up on manual entries after systems come back online.

~~~text
Disruption begins
    |
    +-- Detection / decision / technical recovery --> Service restored (RTO)
    |
    +-- Reconciliation / backlog drain / catch-up --> Normal operations
    |
    +-----------------------------------------------> MTD/MAO
~~~

### 3.4. Measurement Formulas

Actual RTO:

\[
RTO_{actual} = T_{service\_restored} - T_{disruption}
\]

Actual RPO:

\[
RPO_{actual} = T_{disruption} - T_{latest\_recoverable\_data}
\]

This is a straightforward calculation for a single point-in-time disruption. For systems with multiple datasets or workloads, measure each dataset and process separately. Actual RPO should rely on verified timestamps or sequences, not merely when a backup job reported success.

### 3.5. Example

Suppose:

- Disruption begins at 10:00.
- The system is confirmed operational at 11:25.
- The latest recoverable data point is 09:48.
- Target RTO is 2 hours.
- Target RPO is 15 minutes.

Then:

\[
RTO_{actual} = 11{:}25 - 10{:}00 = 85\ \text{minutes}
\]

\[
RPO_{actual} = 10{:}00 - 09{:}48 = 12\ \text{minutes}
\]

In this example, both targets are met. The conclusion is valid only if "service operational" and "recoverable data" were verified against agreed criteria.

### 3.6. Setting Targets by Business Impact

Not every feature needs the same RTO and RPO. Examples:

| Workload | Target RTO | Target RPO | Rationale |
|---|---:|---:|---|
| Order creation | 2 hours | 15 minutes | Revenue-critical transaction |
| Product catalog | 4 hours | 1 hour | Partially reconstructible from upstream sources |
| Analytics dashboard | 24 hours | 24 hours | Does not block live order processing |
| Audit records | 8 hours | 5 minutes | History preservation required |

These are illustrative targets only. A Business Impact Analysis (BIA) must confirm financial, operational, regulatory, and customer impacts before finalizing numbers.

## 4. Business Impact Analysis and Recovery Tiers

### 4.1. Conducting a BIA

A BIA identifies business processes, criticality, time-based impact, and dependencies. For each process, collect:

- Process owner.
- Peak operating windows.
- User/transaction volume.
- Impact of 15-minute, 1-hour, 4-hour, and 1-day outages.
- Tolerable data loss.
- Internal and external dependencies.
- Manual workarounds.
- Approved RTO/RPO and MTD/MAO.

Never set RTO solely from technical estimates. A database may restore in 30 minutes, yet post-restore business reconciliation may take another 90 minutes.

### 4.2. Classifying Workloads

Workloads can be grouped into recovery tiers:

| Tier | Criticality | Reference Strategy |
|---|---|---|
| Tier 0 | Essential safety, identity, or control plane | Redundant, tightly controlled access |
| Tier 1 | Core business transactions | Warm standby or enhanced pilot light |
| Tier 2 | Operational support applications | Pilot light or rapid backup/restore |
| Tier 3 | Reporting and re-runnable batch jobs | Backup/restore or rebuild |

Tier names and strategies must be defined by the organization. One workload can span multiple data tiers: order records need a low RPO, whereas caches can be rebuilt.

### 4.3. Dependency Mapping

Map dependencies for every workload:

- DNS and certificates.
- Identity providers and IAM.
- KMS keys and secrets.
- Compute images, packages, and container registries.
- Networks, subnets, routes, security groups, and endpoints.
- Databases, object storage, queues, and event buses.
- Third-party APIs.
- Monitoring, alerting, and incident communications.

Missing a single dependency can leave you with a restored database while users cannot log in, decrypt data, or reach external services.

### 4.4. Recovery Order

Recovery typically follows dependency order:

1. Account baseline, IAM, KMS, and access controls.
2. Networking, DNS, and security boundaries.
3. Storage and databases.
4. Messaging and integration.
5. Compute and application services.
6. Monitoring, alerting, and user traffic.
7. Batch/backlogs and reconciliation workflows.

Actual order depends on architecture. Some managed services can provision in parallel; runbooks must reflect true dependencies rather than a rigid checklist.

## 5. Choosing a DR Strategy

### 5.1. Backup and Restore

Backup and Restore stores backups safely and provisions infrastructure when an incident strikes.

Advantages:

- Lowest ongoing standby cost.
- Simpler architecture than active standby.
- Fits workloads with longer RTOs.

Trade-offs:

- Restore and deployment times can be lengthy.
- Requires automation and regular testing.
- May face delays waiting on capacity, quotas, and dependencies.

Fits workloads that do not require recovery within minutes and have reliable backups.

### 5.2. Pilot Light

Pilot Light maintains a minimal core footprint in the recovery Region—typically replicated data or backups, foundational components, and automation. During a disaster, the team scales up compute, deploys remaining components, and shifts traffic.

Advantages:

- Lower ongoing cost than warm standby because most compute stays off or minimal.
- Key dependencies and data paths are already staged.
- Shortens recovery time compared to building from scratch.

Trade-offs:

- Still requires time to scale and deploy.
- Must verify quotas and capacity.
- More complex runbooks than basic backup/restore.

### 5.3. Warm Standby

Warm Standby keeps a scaled-down copy of the environment running continuously, capable of serving a fraction of traffic or scaling rapidly when needed.

Advantages:

- Infrastructure and dependencies are already running.
- Allows continuous health verification.
- Typically delivers shorter RTO than pilot light.

Trade-offs:

- Ongoing compute, database, and networking charges.
- Requires ongoing data and configuration sync.
- Must manage version parity between primary and standby.

### 5.4. Multi-Site Active/Active

Multi-Site Active/Active serves live traffic from multiple Regions simultaneously. It can achieve very low RTO for certain components but requires designing traffic distribution, data replication, consistency, and conflict resolution.

Trade-offs:

- Highest or near-highest cost.
- Operational complexity.
- Risk of split-brain and write conflicts.
- Requires thorough failure-mode and failback testing.

Do not choose active/active unless the application's data model and business logic genuinely support multi-Region writes.

### 5.5. Comparison

| Strategy | Standby Footprint | Relative RTO | Relative RPO | Relative Cost |
|---|---|---|---|---|
| Backup and Restore | Primarily backups/artifacts | Longer | Per backup/replication | Low |
| Pilot Light | Core foundation and data | Medium | Per replication/backup | Low to medium |
| Warm Standby | Scaled-down live environment | Shorter | Per replication | Medium to high |
| Active/Active | Multiple Regions actively serving | Can be very short | Depends on consistency/replication | High |

These ratings are relative. Actual RTO and RPO depend on services, data size, workload, automation, quotas, and human procedures; never infer them solely from the strategy name.

### 5.6. Selecting a Strategy by RTO/RPO

Selection process:

1. Determine MTD and acceptable disruption impact.
2. Set RTO/RPO per workload and dataset.
3. List viable strategies.
4. Measure restore and replication times in tests.
5. Calculate standby and operating costs.
6. Choose the option meeting targets with acceptable trade-offs.
7. Obtain sign-off from business, security, operations, and finance.

If no affordable strategy meets the target, adjust the architecture, business target, or budget. Never document a low RTO without evidence backing it up.

## 6. AWS Services for Backup and Recovery

### 6.1. AWS Backup

AWS Backup centralizes backup management across supported AWS services. You can define backup plans, schedules, lifecycles, retention, vaults, and cross-Region/cross-account copies.

Key capabilities:

- Scheduled or policy-driven backups.
- Backup vault management.
- Cross-Region or cross-account backup copies where supported by resource and Region.
- Vault Lock for compliance/governance retention protection.
- Backup auditing and reporting.
- Automated restore testing for supported resources and backup types.

Not every resource shares identical backup/copy/restore features. Check the service support matrix and Regional availability before committing.

### 6.2. Backup Vaults and Vault Lock

A backup vault stores recovery points. Use encryption, access policies, and separation of duties to restrict who can delete or alter backups.

AWS Backup Vault Lock offers governance and compliance modes with configurable retention and deletion protection. Compliance mode can create irreversible locks for the configured retention period; carefully review retention durations and workflows before enabling.

For ransomware or account-compromise resilience, consider a dedicated backup account, cross-account copies, organization guardrails, and independent administrative access.

### 6.3. Amazon S3

Features supporting object protection and recovery:

- Versioning retains multiple object versions.
- Lifecycle rules transition older versions to appropriate storage classes.
- Rule-based replication across buckets or Regions.
- Object Lock enforces configurable retention and legal holds.
- AWS Backup supports documented S3 backup scenarios.
- Cross-Region Replication (CRR) replicates objects to another Region.

Replication is not immutable backup. If an object is deleted or overwritten with corrupted data, replication and delete-marker behavior depends on configuration. Combine versioning, Object Lock, or independent backups as required.

CRR is asynchronous; replication lag affects RPO. S3 Replication Time Control can provide an SLA for replicating a percentage of objects under service terms, though it does not make replication strictly synchronous.

### 6.4. Amazon DynamoDB

DynamoDB provides:

- Point-in-time recovery (PITR) within the service's supported retention window.
- On-demand backups.
- AWS Backup integration for supported configurations.
- Global Tables for multi-Region replication.

Restoring from PITR or backup creates a new table; the application must switch to the restored table, and you must verify indexes, streams, autoscaling, TTL, encryption, and access policies. Never assume a restore overwrites the existing table in place.

Global Tables support multi-Region replication per configured mode. Asynchronous replication can introduce lag; design conflict handling and traffic switching explicitly. Global Tables do not replace backups because accidental deletes or bad writes replicate to other Regions.

### 6.5. Amazon RDS and Aurora

Available mechanisms:

- Automated backups and point-in-time recovery for supported engines and setups.
- Manual snapshots to preserve specific milestones.
- Cross-Region snapshot copies or automated backup replication where supported by engine/Region.
- Multi-AZ for intra-Region availability.
- Read replicas or Aurora Global Database for replication and DR needs.

RDS Multi-AZ is primarily an intra-Region HA/failover feature, not a full-Region DR strategy. Read replicas and Aurora Global Database carry their own replication semantics, lag, and promotion procedures. Test promotion, endpoints, application reconnects, and data consistency.

### 6.6. EBS, EFS, and EC2

- EBS snapshots back up volumes; snapshots are typically incremental after the first snapshot. Ensure application-consistent backups when workloads span multiple volumes or databases.
- AMIs store configured EC2 images to launch new instances.
- EFS backups can be managed via AWS Backup per service capabilities.
- AWS Elastic Disaster Recovery (AWS DRS) provides continuous replication and recovery for supported servers/workloads, suited for certain lift-and-shift scenarios.

A standalone snapshot does not guarantee application consistency. For databases or multi-volume systems, use filesystem freeze/quiesce, native backups, or an appropriate application-consistent method.

### 6.7. Compute and Artifacts

To rebuild compute:

- Store source code and IaC in backed-up, access-controlled repositories.
- Store container images in ECR and evaluate replication to the recovery Region.
- Store Lambda deployment packages or build artifacts somewhere reachable if the primary Region fails.
- Manage AMIs and launch templates.
- Document runtimes, versions, environment variables, and dependencies.
- Check service quotas and capacity in the recovery Region.

A recovery Region is not ready if it has a database replica but lacks container images, packages, configurations, or deployment permissions.

### 6.8. AWS Elastic Disaster Recovery

AWS DRS recovers servers and workloads from supported sources into AWS using continuous block-level replication and recovery launch templates. DRS fits certain server-based, migration, or DR workloads; it does not replace native backup strategies for managed services.

During drills, verify staging areas, replication health, launch templates, network mappings, boot order, licensing, and application health once recovery instances boot.

## 7. Designing DR for a Recovery Region

### 7.1. Choosing Primary and Recovery Regions

Evaluate:

- Data residency and regulatory constraints.
- Service availability in both Regions.
- Geographic distance and replication latency.
- Compute, storage, and data transfer pricing.
- Quotas and capacity.
- Connectivity to users and external non-AWS systems.
- Operations team access and familiarity with the recovery Region.

Do not pick a recovery Region solely for lower pricing if required services or network paths are unavailable there.

### 7.2. Preparing Account and Baseline

The recovery Region must already have or be able to recreate:

- IAM roles, trust policies, and permission boundaries.
- KMS keys and key policies.
- VPC, subnets, routes, security groups, and endpoints.
- DNS zones/records or traffic management.
- Secrets and TLS certificates.
- ECR images, Lambda artifacts, and AMIs.
- Database, table, or bucket recovery points.
- Queues, event buses, and workflow definitions.
- Monitoring, alarms, dashboards, and notifications.

Use IaC for repeatable infrastructure provisioning. Remember that IaC templates do not automatically ensure secrets or data have replicated; verify those separately.

### 7.3. KMS and Secrets

Backups may be encrypted with a KMS key. When copying backups to another Region, ensure the recovery Region has an appropriate KMS key and decrypt permissions. KMS keys are regional resources; never assume a primary Region key automatically exists in the secondary Region.

Secrets Manager supports replicating secrets to other Regions. Verify secret versions, replica status, KMS keys, and role access. Parameter Store parameters may need automated deployment or copying depending on architecture.

### 7.4. DNS and Traffic Routing

Options include:

- Amazon Route 53 failover routing and health checks.
- AWS Global Accelerator to steer traffic to healthy endpoints.
- CloudFront origin failover for supported origin setups.
- Load balancers or API endpoints in the recovery Region.

DNS failover is subject to TTLs and resolver/client caching; updating a record does not shift every client instantaneously. Global Accelerator provides anycast entry points and routes via health checks and traffic dials, though endpoints and health checks must still be configured accurately.

Test client reconnects, connection pools, TLS certificates, CORS, authentication callbacks, and webhook endpoints after shifting traffic.

### 7.5. Preventing Split-Brain

Split-brain happens when both primary and recovery Regions believe they are the active writer. This causes conflicts, overwrites, or two diverging business flows.

Before promoting:

- Confirm the primary is down or isolated.
- Prevent old workloads from accepting writes wherever possible.
- Use fencing, leader controls, or routing controls.
- Verify replication state and recovery data point.
- Open writes in the new Region only after authorized sign-off.

For multi-active setups, define explicit conflict-resolution rules and test simultaneous dual-Region writes.

## 8. Sample DR Architecture for the Order Platform

### 8.1. Context

An order management platform operates in a primary Region. Core components:

- CloudFront and API Gateway.
- Lambda handling orders.
- DynamoDB storing orders and outbox records.
- EventBridge and SQS handling fulfillment.
- S3 storing invoices and attachments.
- Cognito or an enterprise identity provider.
- Secrets Manager storing payment provider credentials.
- CloudWatch, X-Ray, and CloudTrail.

Illustrative targets:

- RTO: 2 hours.
- RPO for orders: 15 minutes.
- RPO for catalog: 1 hour.
- RTO for analytics: 24 hours.

### 8.2. Recommended Strategy

Choose Pilot Light or Warm Standby depending on budget and restore test results:

- IaC, IAM baselines, VPC, KMS, and monitoring can be pre-deployed in the recovery Region.
- DynamoDB Global Tables or backup/PITR chosen based on consistency and RPO.
- S3 CRR or backup strategy for invoices and attachments.
- ECR images and Lambda artifacts stored or replicated.
- SQS/EventBridge resources pre-created or deployed via IaC.
- Secrets Manager replicas and KMS keys prepared.
- Compute runs at minimal capacity or scales up on DR activation.
- Route 53/Global Accelerator configured for traffic shifting.

Do not assume every component requires active-active. Order writes need a single authoritative Region at a time unless business logic supports multi-Region conflict resolution.

### 8.3. Reference Diagram

~~~mermaid
flowchart TB
    U[Customers] --> ROUTE[Route 53 / Global Accelerator]
    ROUTE --> PRIMARY
    ROUTE -. failover .-> RECOVERY
    subgraph PRIMARY["Primary Region"]
        PAPI[API Gateway]
        PL[Order Lambda]
        PD[(DynamoDB primary)]
        PS3[(S3 primary)]
        PQ[SQS / EventBridge]
        PAPI --> PL
        PL --> PD
        PL --> PS3
        PL --> PQ
    end
    subgraph RECOVERY["Recovery Region"]
        RAPI[API Gateway]
        RL[Order Lambda standby]
        RD[(DynamoDB recovery)]
        RS3[(S3 recovery)]
        RQ[SQS / EventBridge]
        RAPI --> RL
        RL --> RD
        RL --> RS3
        RL --> RQ
    end
    PD -. replication / backup .-> RD
    PS3 -. CRR / backup .-> RS3
    ART[Code / IaC / ECR artifacts] --> PRIMARY
    ART --> RECOVERY
    OBS[Central monitoring and audit] --- PRIMARY
    OBS --- RECOVERY
~~~

This diagram is a logical view. In the deployment design, specify replication types, lag tolerances, promotion steps, account boundaries, keys, secrets, queues, and traffic routing.

### 8.4. Data Consistency

Order records and outbox events require consistency rules. If an order replicates without its outbox event—or vice versa—recovery can leave inconsistent state.

The design needs:

- Transaction boundaries covering both order and outbox.
- Unique event IDs.
- Consumer idempotency.
- Reconciliation jobs to detect records missing events.
- Rules for events emitted before failover but not yet acknowledged by consumers.
- Post-failover reconciliation with the payment provider.

Do not check record counts alone. Verify relationships across orders, payments, fulfillment, and events.

## 9. DR Activation Runbook

### 9.1. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| Incident Commander | Coordinate response, confirm severity, decide escalation |
| DR Lead | Coordinate technical execution and recovery order |
| Database Lead | Verify replication/backups, restore/promote, validate data |
| Platform/Network Lead | IAM, KMS, VPC, DNS, and traffic routing |
| Application Lead | Deploy, configure, run smoke tests, validate business logic |
| Security Lead | Assess compromise, access controls, and audit evidence |
| Business Owner | Accept recovered data point and service readiness |
| Communications Lead | Update stakeholders and end users |

In small teams, one person may wear multiple hats, though approval authority and execution duties must still be documented explicitly.

### 9.2. Activation Triggers

The runbook must define:

- Which incidents are severe enough to activate DR?
- Who holds authority to declare a disaster?
- How quickly must the decision be made?
- What evidence indicates the primary Region cannot recover within RTO?
- When does waiting on the primary become riskier than failing over?
- Who approves switching to the recovery Region?

Never trigger a regional failover from a single isolated alarm. Assess blast radius, AWS Health, networking, application state, and in-Region recovery options.

### 9.3. Runbook Phases

**Phase A – Declare**

1. Open an incident and record the UTC timestamp.
2. Confirm affected accounts, Regions, and services.
3. Assemble the Incident Commander and technical leads.
4. Assess remaining RTO/RPO budget.
5. Decide to activate DR and record the approver.

**Phase B – Contain**

1. Isolate compromised credentials or workloads if needed.
2. Block uncontrolled writes to the primary.
3. Check for split-brain and active background workers.
4. Preserve logs and audit evidence.
5. Identify the latest trusted data point.

**Phase C – Recover Infrastructure**

1. Verify recovery account/Region and service quotas.
2. Deploy IaC or scale up Pilot Light.
3. Verify VPC, subnets, routes, security groups, and endpoints.
4. Verify IAM, KMS, secrets, and certificates.
5. Deploy exact-version compute artifacts.
6. Provision or verify queues, event buses, workflows, and alarms.

**Phase D – Recover Data**

1. Select the approved recovery point.
2. Restore or promote databases per runbook.
3. Verify S3 objects/versions and replication status.
4. Verify encryption keys and read permissions.
5. Run data integrity checks.
6. Record the latest recoverable timestamp/sequence.
7. Block new application writes until data validation passes.

**Phase E – Switch Traffic**

1. Verify recovery endpoints and health checks.
2. Confirm the primary is fenced or no longer accepting writes.
3. Switch DNS/traffic routing per plan.
4. Verify TLS, authentication, and client reconnects.
5. Run smoke tests from representative networks and identities.
6. Ramp traffic in stages if feasible.

**Phase F – Validate and Stabilize**

1. Execute and read back a safe synthetic test transaction.
2. Verify order, payment, and event consistency.
3. Monitor error rates, latency, queue age, and business metrics.
4. Drain backlogs cleanly with bounded concurrency and deduplication.
5. Confirm acceptance with the business owner.
6. Record the timestamp when the service is declared restored.

### 9.4. Stop Conditions

Pause or hold traffic if:

- Recovery point cannot be verified or exceeds RPO without formal waiver.
- KMS keys or secrets are unavailable.
- Dual-Region split-brain writes remain a risk.
- Data integrity checks fail.
- Security compromise is not yet contained.
- Recovery Region lacks quota or capacity for minimum viable load.
- Health checks or smoke tests fail.

Stop conditions prevent opening traffic to a system that is online yet unsafe or serving corrupted data.

### 9.5. Failback

Failback moves workloads from the recovery Region back to the primary or a new target Region. You do not have to fail back the instant the primary Region recovers.

Procedure:

1. Confirm the primary outage root cause is resolved.
2. Schedule the window and notify stakeholders.
3. Establish data synchronization from recovery back to primary.
4. Verify schema and version compatibility.
5. Pause or coordinate writes to prevent split-brain.
6. Replicate and reconcile data.
7. Verify KMS, secrets, endpoints, and workloads.
8. Shift traffic in controlled steps.
9. Verify business flows and metrics.
10. Retain the recovery environment for an observation window before scaling down.

Failback must also measure duration and potential data loss. Never tear down the recovery environment immediately after traffic switches back.

## 10. Designing DR Tests and Tabletop Exercises

### 10.1. Why Rehearse?

Runbooks go stale; on-call engineers may lack permissions; quotas change; endpoints and secrets expire; actual restore times run longer than planned. Drills uncover these gaps before a real disaster hits.

### 10.2. Exercise Tiers

| Tier | Description | Objective |
|---|---|---|
| Tabletop | Walk through scenarios on paper | Validate decisions, owners, and runbooks |
| Walkthrough | Step through commands and permissions without full failover | Catch missing details and dependencies |
| Component restore | Restore a single resource or dataset | Measure restore time and verify data |
| Technical failover | Fail over a test workload to the recovery Region | Test automation and traffic shifting |
| Full DR exercise | Multi-component drill with business validation | Measure end-to-end RTO/RPO |
| Failback exercise | Shift back to primary or a new target Region | Validate the full DR lifecycle |

Start with tabletop and component restore exercises, then scale up once automation and guardrails are solid.

### 10.3. Drill Scenarios

Example scenarios:

- Total loss of the primary Region.
- Database deletion or corruption.
- Unavailable IAM role or KMS key.
- Ransomware or account compromise.
- Accidental S3 object overwrite or deletion.
- Queue consumer outage causing backlog buildup.
- Payment provider outage.
- Single Availability Zone connectivity loss.
- Faulty deployment corrupting data.

Every scenario must specify scope, objectives, entry criteria, stop conditions, and environment reset steps.

### 10.4. Preparing a Drill

Before the exercise:

1. Select the workload and approved RTO/RPO targets.
2. Define the test environment and synthetic dataset.
3. Assign a facilitator and observers.
4. Verify IAM permissions and break-glass access.
5. Check backup and replication health.
6. Verify quotas, KMS, secrets, DNS, and artifacts.
7. Lock down blast radius and stop conditions.
8. Prepare dashboards, log queries, and timestamp tracking sheets.
9. Notify stakeholders.
10. Capture baseline metrics before starting.

### 10.5. Tabletop Prompts

A facilitator can ask:

- Who detects the outage and who declares a disaster?
- What evidence proves the primary cannot recover within RTO?
- Which recovery point is selected and who approves it?
- How do we confirm the primary is fenced?
- What if a KMS key is inaccessible?
- What if the recovery Region hits a service quota?
- Who verifies order/payment consistency?
- What if client DNS caches hold stale records longer than expected?
- When is traffic allowed to reopen?
- Who decides when to fail back?

Capture unclear answers, single-person dependencies, or missing documents as tracked action items.

## 11. Measuring and Verifying RTO and RPO

### 11.1. Mandatory Timestamps

Record UTC timestamps:

| Milestone | Meaning |
|---|---|
| T0 | Disruption starts or disruption timestamp is established |
| T1 | Monitoring detects the disruption |
| T2 | Incident is confirmed |
| T3 | DR is declared |
| T4 | Recovery execution begins |
| T5 | Data restore or replication promotion completes |
| T6 | Application health checks pass |
| T7 | Traffic shifts to recovery |
| T8 | Business validation passes |
| T9 | Service is declared restored |

RTO can be measured as T9 − T0 or per the organization's formal definition. If measuring only T9 − T3, explicitly label it recovery execution time rather than end-to-end RTO.

### 11.2. Verifying RPO with Data

Do not look solely at backup job timestamps. Use sequenced or timestamped test data:

- Write test events with monotonically increasing sequence numbers.
- Record checkpoints in an independent source if feasible.
- Capture the last commit timestamp prior to disruption.
- Restore or promote data.
- Locate the highest present sequence number and check consistency.
- Reconcile against event logs or an independent business source.

For transactional systems, check both records and side effects. An order record might exist while its payment or fulfillment event is missing.

### 11.3. Distinguishing Replication Lag from Data Loss

Replication lag is the delay between source and replica at a moment in time. When an outage hits, un-replicated data becomes data loss if the source cannot be recovered.

Measure lag before and during drills:

- Replication timestamp.
- Sequence number or checkpoint.
- Pending objects or records.
- Time required to drain backlog.

Never use an average lag metric alone to conclude all records have replicated.

### 11.4. Defining "Service Restored"

An endpoint returning HTTP 200 does not prove service restoration. Criteria can include:

- User authentication succeeds.
- Creating and reading test transactions succeed.
- Database reads and writes behave properly.
- Events are published and processed by consumers.
- Zero duplicate or orphaned data records.
- Dashboards and alarms are active.
- Error rates and latency remain within thresholds.
- Business owner signs off on critical workflows.

### 11.5. Results Scorecard

| Metric | Target | Drill Result | Met? |
|---|---:|---:|---|
| Detection time | 5 min | 3 min | Yes |
| Decision time | 10 min | 12 min | No |
| End-to-end RTO | 120 min | 95 min | Yes |
| RPO – orders | 15 min | 11 min | Yes |
| RPO – attachments | 60 min | 18 min | Yes |
| Backlog drain | 30 min | 42 min | No |
| Business validation | 15 min | 10 min | Yes |

Numbers in this table are illustrative examples. Real results must come from timestamps and data reconciliation during the drill.

## 12. Service-Specific Backup and Restore Testing

### 12.1. AWS Backup Restore Test

Test flow:

1. Identify a recovery point and supported resource.
2. Check backup job status and vault state.
3. Restore to a uniquely named resource in a test account/Region.
4. Verify KMS keys and decrypt permissions.
5. Inspect resource configuration post-restore.
6. Run application-level validation.
7. Record restore duration and recovered data point.
8. Delete test resources per cleanup procedures.

AWS Backup restore testing can automate periodic restore drills for supported resources. Confirm service coverage, test configuration, and validation criteria.

### 12.2. S3 Restore

Verify:

- Restoring a prior version after an object overwrite.
- Restoring a deleted object using the appropriate version/delete marker.
- Confirming Object Lock/retention behavior.
- Checking replication status and replication lag.
- Reading restored objects with the application's IAM role.
- Checking metadata, checksums, and encryption.

An object may exist yet remain unreadable by the application due to KMS key or bucket policies. Test using a principal mirroring production.

### 12.3. DynamoDB Restore

Procedure:

1. Enable PITR or create an on-demand backup as required.
2. Write sequenced test records.
3. Select a recovery timestamp.
4. Restore to a new table.
5. Verify items, indexes, encryption, and capacity mode.
6. Verify streams, TTL, and downstream dependencies.
7. Update aliases, configuration, or deployments to target the new table.
8. Run read/write smoke tests and reconciliation.

Restoring a table does not automatically rewire consumers, stream ARNs, alarms, or downstream integrations to the new resource. Update and test all dependencies.

### 12.4. RDS/Aurora Restore

Verify:

- Snapshot or point-in-time recovery.
- Restore duration relative to database size.
- Engine version and parameter groups.
- Subnet groups and security groups.
- KMS keys and secrets.
- Endpoints and connection pools.
- Schema migrations and data consistency.
- Replication lag and promotion if using read replicas or global databases.

Post-restore, run integrity queries and business tests. Do not stop at checking that the instance status is `available`.

### 12.5. EBS/EFS/EC2 Restore

Verify:

- Snapshots match the intended volume and encryption key.
- Instances/AMIs boot cleanly.
- Device mappings and filesystem mounts succeed.
- Application services start automatically.
- Multi-volume data is consistent.
- DNS and security groups are accurate.

If using AWS DRS, measure time from recovery launch initiation until the application is confirmed ready—not merely until the EC2 instance hits `running`.

## 13. Failover and Failback Testing

### 13.1. Failover Checklist

- [ ] Primary and recovery Regions are defined.
- [ ] Backup/replication health is verified.
- [ ] Recovery point is accepted by business and technical owners.
- [ ] Primary writes are fenced or controlled.
- [ ] KMS keys, secrets, and certificates are available.
- [ ] VPC, routes, security groups, and endpoints are accurate.
- [ ] Compute images/artifacts match the expected version.
- [ ] Databases/tables are restored or promoted.
- [ ] Queues, event buses, and consumers are ready.
- [ ] DNS/traffic routing has switched.
- [ ] Smoke tests and business validation pass.
- [ ] RTO/RPO are recorded.

### 13.2. Failback Checklist

- [ ] Primary is confirmed healthy and safe.
- [ ] Data synchronization direction is clearly planned.
- [ ] Writes are coordinated to prevent split-brain.
- [ ] Schemas and versions are compatible.
- [ ] Data reconciliation passes.
- [ ] Endpoints, secrets, and KMS keys are ready.
- [ ] Traffic shifts in controlled steps.
- [ ] Business validation passes.
- [ ] Post-failback stability monitoring completes.
- [ ] Recovery environment is retained per policy.

### 13.3. Traffic Shifting

When using Route 53:

- Verify record types and routing policies.
- Ensure health checks accurately reflect service health.
- Account for TTLs and resolver/client caching.
- Test DNS resolution across multiple networks.
- Never assume record updates propagate instantaneously to all clients.

When using Global Accelerator:

- Verify listeners, endpoint groups, and health checks.
- Verify traffic dials and endpoint weights.
- Confirm recovery Region endpoints are ready.
- Test client connections and TLS handshakes.

### 13.4. Post-Failover Verification

Verify:

- Authentication and authorization.
- Business reads and writes.
- Event routing and consumers.
- Payment reconciliation.
- Object and file access.
- Error rates, latency, and queue backlogs.
- Alarms, dashboards, traces, and auditing.
- Data consistency and absence of duplicates.

Open full traffic only after critical checks pass and the Incident Commander and business owner approve.

## 14. Security in DR

### 14.1. Separating Backup and Production Permissions

Production workloads should never hold arbitrary permissions to delete backups or alter vault policies. Separate roles:

- Backup operator.
- Restore operator.
- Security/audit.
- Application deployment.
- Incident Commander.

Use cross-account backups or a dedicated backup vault account so a single compromised account cannot wipe both live data and backups.

### 14.2. Break-Glass Access

DR may require emergency elevated access. Design break-glass controls:

- Strongly protected emergency credentials or roles.
- MFA and policy-defined approvals.
- Short session durations.
- Real-time alerts upon activation.
- CloudTrail logging.
- Post-incident review.
- Never embed access keys inside runbooks.

Drills must verify assigned responders can assume the right break-glass role when needed. Never store passwords or secrets directly in documents.

### 14.3. Ransomware and Immutable Backups

A ransomware scenario must verify:

- Can backups be deleted or encrypted alongside the workload?
- Do isolated copies exist in another account or Region?
- Are Vault Lock or Object Lock properly configured?
- Are KMS keys still intact and protected?
- Can a clean recovery point predating malware infection be identified?
- Have compromised credentials been isolated?

Restoring the latest backup could restore encrypted or malicious data. Locate a clean recovery point and scan/validate before opening traffic.

### 14.4. Audit Evidence

Retain:

- CloudTrail events.
- Backup and restore job statuses.
- IAM roles and sessions used.
- Change sets and deployment IDs.
- Recovery point identifiers.
- Data validation reports.
- Traffic switch timestamps.
- Approvals and incident notes.

Evidence needs appropriate access restrictions and retention so workloads undergoing recovery cannot tamper with or delete it.

## 15. Monitoring DR Readiness

### 15.1. Readiness Metrics

Monitor regularly:

- Age of latest recovery point.
- Backup job success/failure rates.
- Cross-Region replication lag.
- Recovery Region resource health.
- Service quota headroom.
- Secret and certificate expiration dates.
- KMS key availability.
- ECR image replication status.
- IaC drift and deployed versions.
- DNS and health check statuses.

### 15.2. AWS Resilience Hub

AWS Resilience Hub assesses applications and resilience posture against defined configurations, workloads, and policies. It can estimate RTO/RPO and suggest improvements for supported architectures.

Assessment scores do not replace live restore and failover drills. Actual RTO/RPO must be measured through exercises because outcomes depend on people, data, quotas, dependencies, and procedures.

### 15.3. AWS Fault Injection Service

AWS Fault Injection Service (FIS) runs controlled fault-injection experiments on supported resources to simulate failure modes like network disruptions or resource impairment.

Before running:

- Define a hypothesis.
- Bound targets and blast radius.
- Configure stop conditions and CloudWatch alarms.
- Verify permissions and notify stakeholders.
- Run in an appropriate environment.
- Have operators watching with manual abort ready.

FIS does not automatically validate end-to-end DR. Use it to generate controlled failure signals, then verify how the application and runbooks respond.

### 15.4. AWS Fault Injection Service and DR Tests

Example hypothesis: "When one AZ loses connectivity, load balancers and compute in remaining AZs continue serving within SLO." FIS injects supported fault conditions; CloudWatch/X-Ray measure impact; operations verifies alarms and runbooks.

Never trigger a real Region-wide outage in production just to prove DR. Use sandboxes, staging, or approved controlled game days with strict stop conditions.

## 16. Measuring Outcomes and Continuous Improvement

### 16.1. Exercise Report

A post-drill report should include:

- Objectives and scenario.
- Workload, Region, and resource scope.
- Target RTO/RPO.
- Full timeline.
- Measured RTO/RPO.
- Data loss or consistency findings.
- Failed steps or manual workarounds.
- Cost of the exercise and recovery.
- Residual risks.
- Owners and due dates for corrective actions.

### 16.2. Gap Analysis

Examples:

| Gap | Impact | Action |
|---|---|---|
| Table restore took 70 minutes | Consumed most of RTO | Optimize dataset, test parallel recovery |
| Secret replica not ready | App failed to start | Automate secret replication and validation |
| Low Lambda quota in recovery Region | Missed peak throughput | Review quotas and request pre-increases |
| Long DNS client caching | Slow traffic shift | Tune TTLs and test client behavior |
| DLQ not replayed | Stuck workflows | Build replay runbook with deduplication |
| No off-hours approver | Decision time breached target | Establish on-call escalation and delegation |

### 16.3. Corrective Actions

Every action item requires:

- Problem description.
- Supporting evidence.
- Priority level.
- Owner.
- Due date.
- Completion criteria.
- Which exercise must re-run to verify.

Never close an action item just because a document was edited. If a gap impacted RTO or RPO, re-run the relevant test to verify closure.

### 16.4. Drill Cadence

Cadence depends on criticality, architecture changes, and governance requirements. Example cadence:

- Quarterly tabletop exercises.
- Scheduled restore tests aligned with backup policies.
- Annual technical failovers or prior to major releases.
- Re-testing after Region, database, KMS, IAM, or routing changes.
- Game days after resolving major gaps.

Adjust this reference schedule to match organizational risk, compliance, and business needs.

## 17. DR Costs and Trade-Offs

### 17.1. Cost Components

DR costs can include:

- Backup storage and lifecycle transitions.
- Cross-Region/cross-account copies.
- Replication requests and data transfer.
- Warm standby compute and databases.
- Networking, VPC endpoints, NAT Gateways, and load balancers.
- KMS keys and API requests.
- Monitoring, logs, traces, and auditing.
- Restore and failover exercises.
- AWS Support and operational staffing.

### 17.2. Cost Comparison by Strategy

| Strategy | Typical Cost Items | Primary Drivers |
|---|---|---|
| Backup and Restore | Backup storage and drills | Data volume, retention, restore frequency |
| Pilot Light | Backups/replication and minimal foundation | Data replication, artifacts, quota readiness |
| Warm Standby | Continuously running standby compute/databases | Standby capacity ratio, networking, replication |
| Active/Active | Two or more Regions serving traffic | Compute, data replication, conflict handling, traffic |

You cannot assign a universal cost multiplier to each strategy. Use AWS Pricing Calculator and real workload data to compare options fairly.

### 17.3. Drill Costs

An exercise can incur:

- Temporary restored resources.
- Compute running during the test window.
- Data transfer.
- Log and trace ingestion.
- New snapshots or backups.
- Load generators and synthetic test data.
- Staffing and controlled downtime.

Budget for exercises, clean up temporary resources afterward, and track costs as part of the recurring DR schedule.

### 17.4. Cost vs. RTO/RPO

Lower RTO/RPO generally requires faster replication, larger standby capacity, greater automation, and more frequent testing. However, the most expensive option is not always warranted.

Compare options across:

- Business loss if RTO/RPO are breached.
- Ongoing steady-state run cost.
- Implementation and testing cost.
- Complexity and team maintainability.
- Proven confidence level backed by evidence.

Choose the optimal design based on business impact, not infrastructure price alone.

## 18. Sample Drill: Order Platform Primary Region Outage

### 18.1. Objectives

Suppose the Order Platform has:

- Target RTO of 120 minutes.
- Target RPO of 15 minutes for orders.
- A primary Region and a recovery Region.
- Chosen DynamoDB Global Tables or backup/restore strategy.
- S3 CRR for invoices.
- IaC, ECR artifacts, secret replicas, and recovery endpoints.

The exercise objective is to prove traffic failover and restore order create/read flows in the recovery Region.

### 18.2. Preparation

1. Use a test account or isolated sandbox environment.
2. Generate sequenced test orders.
3. Record an independent checkpoint.
4. Verify backup and replication health.
5. Check KMS keys, secrets, images, quotas, and DNS.
6. Prepare dashboards and runbooks.
7. Confirm stop conditions.

### 18.3. Execution

1. The facilitator announces T0 for the scenario.
2. Incident Commander assesses impact and activates DR.
3. Database Lead verifies the recovery point.
4. Platform Lead validates recovery networking, IAM, and KMS.
5. Application Lead deploys/scales compute.
6. The team fences the primary inside the test environment.
7. Promote/restore data and check sequence integrity.
8. Switch traffic to the recovery endpoint.
9. Run order create/read flows, event processing, and attachment downloads.
10. Business Owner signs off.

### 18.4. Sample Measurement Results

| Milestone | Illustrative Timestamp |
|---|---|
| Disruption starts (T0) | 10:00 |
| Incident detected (T1) | 10:04 |
| DR declared (T3) | 10:12 |
| Recovery starts (T4) | 10:15 |
| Data validation passes (T5) | 10:58 |
| Application health passes (T6) | 11:08 |
| Traffic switch completes (T7) | 11:20 |
| Business validation passes (T8) | 11:28 |
| Service declared restored (T9) | 11:30 |

Actual RTO:

\[
11{:}30 - 10{:}00 = 90\ \text{minutes}
\]

If the latest recoverable order record carries timestamp 09:49:

\[
RPO_{actual} = 10{:}00 - 09{:}49 = 11\ \text{minutes}
\]

In this illustrative drill, the 90-minute RTO meets the 120-minute target, and the 11-minute RPO meets the 15-minute target. Continue measuring backlog drain and payment reconciliation because those tasks still count toward MTD even after the service reopens.

### 18.5. Exercise Conclusions

Document clearly:

- Were RTO and RPO met?
- Which step consumed the most time?
- Did any manual step lack an owner?
- Are orders, payments, events, and invoices consistent?
- Any duplicate or split-brain risks?
- Total exercise cost.
- Corrective actions and re-test schedule.

## 19. Common Mistakes in DR Drills

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only that backup jobs succeeded | Unknown whether restores actually work | Run regular restore tests |
| Treating Multi-AZ as full-Region DR | Fails to recover on Region outage | Add cross-Region backups/copies or a recovery Region |
| Guessing RTO/RPO intuitively | Targets detached from business impact | Conduct a BIA |
| Measuring only database restore duration | Misses deploy, DNS, and validation time | Measure end-to-end from disruption |
| Ignoring data timestamps | RPO lacks objective proof | Use sequences/checkpoints and reconciliation |
| Skipping KMS/secret checks | Resources restore but app fails to run | Test keys, secrets, and IAM |
| Ignoring quotas | Recovery Region fails to scale | Review quotas and capacity plans |
| Replicating corrupted data to DR | Restores ransomware or corruption too | Maintain immutable backups and clean recovery points |
| Allowing both Regions to accept writes | Split-brain and data conflicts | Enforce fencing and single-writer control |
| Tabletop only, never restoring live | Real timings and technical bugs stay hidden | Run component restores and failover tests |
| Never rehearsing failback | Cannot safely return to primary | Maintain failback runbooks and drills |
| Skipping cleanup | Unnecessary costs and leftover risks | Teardown and post-exercise reviews |

## 20. DR Capstone Checklist

### Business and Targets

- [ ] BIA completed with a business owner.
- [ ] RTO/RPO/MTD formally approved.
- [ ] Clear start and end definitions for RTO measurement.
- [ ] Recovery tiers assigned to every workload and dataset.
- [ ] Business workarounds defined while systems recover.

### Architecture and Data

- [ ] DR strategy selected based on RTO/RPO and cost.
- [ ] Dependency map and recovery order documented.
- [ ] Backups/replication configured and monitored.
- [ ] Backups isolated from production workloads.
- [ ] KMS keys, secrets, certificates, and IAM ready.
- [ ] Recovery Region has quotas, networking, and artifacts.
- [ ] Fencing mechanisms prevent split-brain.
- [ ] Data consistency and reconciliation defined.

### Runbooks and Exercises

- [ ] Incident Commander and recovery roles assigned.
- [ ] Activation triggers and stop conditions defined.
- [ ] Restore, failover, and failback runbooks written.
- [ ] Tabletop and technical exercises completed.
- [ ] Timestamps, checkpoints, and test datasets prepared.
- [ ] Smoke tests and business validation ready.
- [ ] Cleanup and rollback plans documented.

### Measurement and Improvement

- [ ] Actual RTO measured end-to-end.
- [ ] Actual RPO verified against data.
- [ ] Drill report and evidence archived.
- [ ] Gaps have owners, due dates, and acceptance criteria.
- [ ] Exercises re-run after fixing gaps.
- [ ] Ongoing DR and drill costs tracked.

## 21. Conclusion

DR is more than copying data or turning on Multi-AZ. It is the ability to restore a business process—with trustworthy data, identity, networking, applications, dependencies, and people—within approved RTO and RPO limits. A BIA grounds targets in business impact; dependency maps and recovery tiers guide strategy selection; AWS Backup, S3, DynamoDB, RDS/Aurora, EBS, EFS, and AWS DRS provide protection and recovery mechanisms matched to each workload.

A meaningful drill tests real restores, traffic shifting, data validation, split-brain prevention, backlog drain, and failback. RTO is measured from disruption until both service health and business logic are confirmed restored; RPO is measured from the latest recoverable data point back to disruption. A green backup job or an HTTP 200 endpoint alone never proves recovery targets are met.

After every exercise, retain timelines, evidence, costs, and owned corrective actions. Re-run tests after remediations to verify gaps are closed. When drills become routine practice, DR transforms from a theoretical document into measurable recovery capability.

## 22. Official References

- [AWS Well-Architected Framework – Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html)
- [Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [AWS Backup Developer Guide](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)
- [AWS Backup restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [Amazon S3 replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Amazon DynamoDB backup and restore](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/BackupRestore.html)
- [Amazon DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon RDS backup and restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html)
- [Amazon Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Amazon Route 53 routing policies](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html)
- [AWS Global Accelerator](https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html)
- [AWS Resilience Hub](https://docs.aws.amazon.com/resilience-hub/latest/userguide/what-is.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
