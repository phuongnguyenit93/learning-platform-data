# Failover, Failback, and Post-Incident Data Synchronization

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, disaster recovery does not end once servers boot in another Region. Operations must also identify where the newest data resides, prevent two environments from accepting concurrent writes, shift traffic, verify application health, and transition the system into a sustainable operating state. Once the incident is resolved, failback must synchronize data generated in the standby environment back to primary, transfer write authority in a controlled manner, and re-establish DR protection.

AWS offers multiple building blocks for this lifecycle: AWS Elastic Disaster Recovery (DRS) for server-level replication and recovery instance launches; Amazon Route 53 and Amazon Application Recovery Controller (ARC) for traffic routing; ARC Region switch for orchestrating multi-Region recovery workflows; service-native replication for RDS, Aurora, DynamoDB, S3, and EFS; AWS Backup for recovery points; plus CloudWatch, EventBridge, and Systems Manager for observability and automation.

After this lesson, you will be able to:

- Distinguish failover, switchover, failback, recovery drills, and data replication.
- Design service cutover workflows to a DR Region driven by RTO, RPO, and data state.
- Choose replication mechanisms suited to EC2/on-premises servers, databases, object storage, and file systems.
- Control replication lag, data consistency, write fencing, and split-brain risks.
- Use AWS Elastic Disaster Recovery to recover workloads and run reverse replication for failback.
- Use Route 53 ARC routing controls or Region switch to orchestrate traffic and recovery workflows.
- Synchronize data from DR back to primary, verify the final sync checkpoint, and hand over write authority safely.
- Test failover/failback periodically, record measured RTO/RPO, and refine runbooks.

## 1. What Are Failover, Switchover, and Failback?

These terms describe distinct operations across the recovery lifecycle.

| Term | Meaning | Scenario |
|---|---|---|
| Failover | Shifting workloads or traffic from a failed primary environment to a standby environment | Primary Region becomes unavailable |
| Planned switchover | Swapping primary/secondary roles while both sides are healthy and can synchronize cleanly | Maintenance, drills, or planned Region rotation |
| Failback | Returning workloads from the active post-failover DR environment back to primary or a new operating target | Incident resolved; primary ready to resume |
| Recovery drill | Test-launching workloads from replicated/backed-up data to verify recoverability | Periodic DR testing |
| Reverse replication | Replicating changes from the recovery environment back to the source environment | Preparing failback after DR served writes |
| Resynchronization | Re-aligning two datasets after one side suffered interruption or divergence | Restoring replication post-outage |

Failover and failback alter serving authority. Replication merely transports data. Running active replication does not imply automatic failover, updated DNS, booted applications, or active write readiness.

In a planned switchover, both primary and secondary are healthy, so data can flush and writes can pause cleanly before swapping roles. In an unplanned failover, primary may be unreachable; the organization must choose a recovery point or secondary replica, accept actual RPO, and ensure the old primary cannot resume writes if it comes back online.

Failback is never as simple as pointing DNS back to the old address. While DR served production, data changed. If the old primary has not received those updates, shifting traffic back prematurely loses recent transactions or forks two inconsistent datasets.

## 2. Defining RPO, RTO, and DR Strategy

Before designing workflows, establish two objectives:

- **Recovery Point Objective (RPO):** maximum acceptable data loss, measured as the time window of unreplicated or unbacked-up data.
- **Recovery Time Objective (RTO):** maximum acceptable duration to restore a service to an agreed operational state.

Define RPO and RTO per application component. An API may need a few-minute RTO while analytics reporting tolerates several hours. A transactional database may require a very low RPO while logs or caches can be regenerated.

DR strategies generally span from lower cost / longer recovery time to higher cost / shorter recovery time:

| Strategy | DR Environment | Reference RPO/RTO | Relative Cost |
|---|---|---|---|
| Backup and restore | Data backed up/copied; infrastructure built on incident | RPO typically hours; RTO can be many hours | Low |
| Pilot light | Core components and data ready in DR; part of compute idle/unlaunched | RPO minutes to tens of minutes; RTO typically tens of minutes | Medium |
| Warm standby | Full stack runs at reduced scale ready to absorb traffic | RPO seconds to minutes; RTO minutes depending on architecture | High |
| Multi-site active/active | Multiple Regions concurrently serve traffic | RPO/RTO potentially near zero if properly designed | Very High |

These ranges reflect AWS architectural guidance, not service SLAs. Actual RPO/RTO depend on replication lag, data size, provisioning duration, quotas, DNS behavior, application readiness, and drill execution.

For example, an order system might adopt Aurora Global Database to shrink replication lag, warm standby for the app tier, and Route 53 ARC for traffic shifting. A lower-criticality internal tool might rely on AWS Backup cross-Region copies and Infrastructure as Code to rebuild on demand.

Never pick a strategy based on RTO alone. Weigh standby upkeep costs, operational complexity, testability, data consistency demands, and on-call team capacity.

## 3. Decomposing Applications into Recovery Layers

Real-world applications consist of interdependent components. Failover succeeds only when required components come up in the right order.

Three-tier architecture example:

~~~mermaid
flowchart TD
    U[Users and API clients] --> DNS[Route 53 or ARC routing]
    DNS --> P[Primary Region]
    DNS -. failover .-> D[DR Region]
    subgraph P[Primary Region]
      PA[Application fleet]
      PD[Primary database]
      PS[Secrets and configuration]
      PN[Network, endpoints and load balancer]
      PA --> PD
      PA --> PS
      PA --> PN
    end
    subgraph D[DR Region]
      DA[Recovery application fleet]
      DD[Replicated or restored database]
      DS[Regional secrets and configuration]
      DN[Network, endpoints and load balancer]
      DA --> DD
      DA --> DS
      DA --> DN
    end
~~~

Layers to include in a dependency map:

- **Traffic entry:** DNS, CloudFront, Global Accelerator, API Gateway, load balancers, routing controls.
- **Compute:** EC2, Auto Scaling, ECS, EKS, Lambda, or non-AWS servers.
- **Data:** RDS, Aurora, DynamoDB, S3, EFS, FSx, EBS, or self-managed databases.
- **Identity and secrets:** IAM roles, Cognito, Secrets Manager, Systems Manager Parameter Store, certificates.
- **Network:** VPCs, subnets, route tables, security groups, NACLs, NAT, Transit Gateway, VPN, and Direct Connect.
- **Shared services:** DNS resolvers, container registries, artifact repositories, logging, monitoring, queues, and event buses.
- **Operations:** backup vaults, KMS keys, Systems Manager, automation roles, runbooks, and incident communications.

Mapping dependencies reveals the recovery order. For instance, application servers fail if the database is not promoted yet or if Regional secrets still point to the old endpoint. DNS can cut over cleanly while traffic still fails if security groups, certificates, WAF rules, IAM roles, or quotas are unready.

## 4. Selecting Synchronization Mechanisms by Data Type

No single replication mechanism fits every data type. Choose based on consistency guarantees, RPO, churn volume, concurrent write support, and restore behavior.

| Workload / Data Type | Common Mechanisms | Failover Considerations |
|---|---|---|
| Servers and OS-level workloads | AWS Elastic Disaster Recovery | Continuous block replication to staging area; recovery instances must launch and validate |
| RDS DB instances | Cross-Region read replicas or snapshots/copies | Replication is typically asynchronous; measure lag and promote replica |
| Aurora | Aurora Global Database | Secondary Region can promote; unplanned failover can lose unreplicated transactions |
| DynamoDB | Global tables | Multiple Regions can accept writes; design conflict handling and app consistency |
| Amazon S3 | Cross-Region Replication (CRR) or Same-Region Replication | Asynchronous replication; verify versioning, delete markers, replication status, and object ownership |
| Amazon EFS | EFS replication | Asynchronous sync; check replication state, destination state, and write-promotion workflow |
| File servers / on-premises | AWS DataSync or suitable sync tools | Suits bulk/periodic sync; schedule runs, handle open files, and run final sync |
| Long-term backups | AWS Backup cross-Region/cross-account copies | Recovery points for restore; not live replication or active-active |

Mechanisms can be combined—for example, DRS for servers, Aurora Global Database for databases, S3 CRR for objects, and AWS Backup for independent recovery points. Still, explicitly define which dataset is authoritative and which component holds write permission at every phase.

Replication can also propagate corrupted data, ransomware encryption, or application logic deletions. Thus, replication does not replace backups with retention and point-in-time recovery. Complete DR architectures pair replication (to minimize RPO) with backups (to roll back prior to data corruption).

## 5. Replication Lag, Consistency, and Transaction Ordering

Replication lag is the elapsed time or backlog of changes not yet applied at the destination. Under asynchronous replication, primary commits transactions before secondary persists them. If primary fails immediately after committing, secondary may miss the final transactions.

Monitor these metrics:

- **Time lag:** how many seconds or minutes secondary trails primary.
- **Backlog:** volume of changes queued but not yet sent or applied.
- **Throughput:** rate of incoming writes versus replication apply rate.
- **Replication errors:** permission, network, quota, or invalid-data errors.
- **Last replicated position:** log sequence number, transaction ID, checkpoint, or watermark synced.
- **Data validation:** row counts, checksums, object counts, or business invariants post-sync.

Example: a database generates 5,000 transactions per minute while replication applies only 4,000 transactions per minute. Backlog grows by 1,000 transactions per minute. Replication lag will climb steadily even though service status still reports RUNNING.

Never rely on a single metric. For databases, inspect lag at both storage and DB instance tiers. For files/objects, inspect object replication statuses and completion timestamps. For DRS, track lag per source server and newest recovery point timestamp.

Some applications require cross-store consistency. Suppose a database stores orders while S3 stores invoices. If failover promotes a database holding a new order whose invoice object has not replicated to S3 yet, the app sees inconsistent state. Define transaction boundaries and use outbox/event patterns, idempotent consumers, or reconciliation jobs to repair discrepancies post-recovery.

## 6. Preventing Split-Brain and Controlling Write Authority

Split-brain occurs when two environments both believe they are primary and accept concurrent writes for the same dataset. Their updates diverge and become hard to merge.

Before shifting traffic or promoting a secondary, verify:

1. Whether the old primary still accepts write requests.
2. Whether you can stop applications, revoke writer credentials, disable endpoints, or fence old storage/databases.
3. Whether the secondary is ready to accept writes.
4. Whether replication has stopped or still flows one way.
5. Whether any clients or background workers continue writing to the old endpoint.

**Write fencing** prevents the old system from accepting writes. Execute it by stopping applications, revoking credentials, disabling writer endpoints, blocking network paths, switching databases to read-only, or enforcing application-managed fencing tokens/leases. Never assume changing DNS stops writes on the old primary: clients retain cached DNS entries and open connection pools.

In active/passive designs, only one Region may write authoritative data at a time. In active/active designs, implement explicit concurrent-write handling such as tenant/region partitioning, conflict resolution, versioning, or transactional coordination. Without conflict resolution, never enable dual writes merely because both Regions are healthy.

Maintain an explicit write-authority state table during operations:

| Phase | Old Primary | DR Region | Transition Criteria |
|---|---|---|---|
| Steady state | Read/write | Replica or read-only | Replication healthy |
| Declared disaster | Fenced or unreachable | Not yet accepting writes | Incident scope and recovery point identified |
| DR active | Writes blocked | Read/write | Secondary promoted and validated |
| Reverse sync | Read-only or isolated | Read/write | DR data is authoritative |
| Final failback | DR writes fenced | Preparing to take writes | Primary synced and verified |
| Primary restored | Read/write | Replica/read-only | Traffic, health, and replication stable |

## 7. Failover from Primary to DR

A failover runbook needs explicit checkpoints. Never shift traffic automatically from a single alarm without checking data state and DR capacity.

~~~mermaid
flowchart TD
    A[Alert and incident declaration] --> B[Assess primary health and blast radius]
    B --> C{Can primary safely serve writes?}
    C -- Yes --> D[Repair or controlled switchover]
    C -- No --> E[Fence old primary if possible]
    E --> F[Choose DR recovery point or replica]
    F --> G[Promote or launch DR data and compute]
    G --> H[Validate dependencies and application]
    H --> I{Health checks pass?}
    I -- No --> J[Stop traffic shift and troubleshoot]
    I -- Yes --> K[Shift traffic to DR]
    K --> L[Monitor errors, latency and data writes]
    L --> M[Declare DR as authoritative]
~~~

Detailed sequence:

1. **Declare incident:** designate the incident commander, failover decision-maker, and impacted apps/Regions.
2. **Assess primary:** distinguish localized app issues, AZ issues, or Regional outages. If primary remains safely operational, prefer repair or a planned switchover.
3. **Fence writes:** when primary is unfit, block writes on the old environment wherever possible.
4. **Select recovery point:** pick the secondary replica or recovery point with lowest lag meeting RPO.
5. **Promote/launch:** promote databases, launch EC2 recovery instances, scale ECS/EKS, restore resources, or activate services in DR.
6. **Restore dependencies:** verify secrets, IAM, certificates, endpoints, networking, queues, and storage.
7. **Validate:** run smoke tests, check transactions, test reads/writes, health checks, and business invariants.
8. **Shift traffic:** update DNS/routing controls/Global Accelerator toward DR.
9. **Observe:** watch error rates, latency, database connections, queue depth, and replication status.
10. **Declare authority:** formally record which Region holds authoritative writes and notify stakeholders.

If primary cannot be fenced due to a Region network partition, avoid letting both DR and primary accept writes when primary could reconnect on its own. Establish clear authority rules and confirm old-primary isolation before enabling DR writes.

## 8. Shifting Traffic with Route 53 and ARC

Traffic cutover is separate from data promotion. Options include Route 53 failover routing, health checks, weighted routing, or Amazon Route 53 ARC routing controls.

### 8.1. Route 53 DNS Failover

Route 53 failover routing returns primary or secondary endpoints based on health checks. When the primary endpoint turns unhealthy, DNS returns the DR endpoint.

Factor in:

- DNS record TTLs and resolver/client caching.
- DNS caching inside JVMs, container runtimes, proxies, and connection pools.
- Whether health checks measure real transaction processing or only superficial TCP/HTTP responses.
- Whether DR endpoints hold pre-tested capacity.
- Whether clients retry and handle connection resets cleanly.

DNS failover cannot force every client to switch instantaneously. Some clients hold persistent connections or cache beyond TTL. After switching DNS, monitor residual traffic hitting the old primary.

### 8.2. ARC Routing Controls

Amazon Application Recovery Controller routing controls provide On/Off switches to steer traffic between replicas. Routing controls bind to Route 53 health checks and DNS records. Toggling state updates the paired health check so Route 53 shifts traffic.

Routing controls do not monitor endpoints or measure latency themselves. They are traffic-steering switches that must pair with monitoring and human or automated failover decisions.

ARC enforces safety rules to prevent unsafe routing states—for example, assertion rules requiring at least one Region to stay enabled. For break-glass emergencies, safety rules can be overridden per approved runbooks with audit justification.

An ARC routing control cluster exposes five Regional endpoints. Automation should iterate through endpoints if the active endpoint is unreachable. AWS recommends calling data plane APIs/CLI in critical failover paths rather than depending on the console.

### 8.3. ARC Region Switch

Region switch in ARC orchestrates multi-Region recovery via plans. A plan organizes workflows, steps, and execution blocks running sequentially or in parallel. It supports active/passive or active/active, cross-account resources, and manual or CloudWatch alarm triggers.

Region switch includes plan evaluation to validate IAM permissions, resource configs, and capacity; evaluations run on plan creation/update and roughly every 30 minutes in steady state. Service quota checks detect quota discrepancies across accounts/Regions, though quota parity alone does not guarantee execution success—real drills remain essential.

At the time of writing, ARC Readiness Check is closed to new customers; AWS recommends new customers seeking multi-Region orchestration evaluate Region switch. ARC routing controls, zonal shift, zonal autoshift, and Region switch remain supported. Zonal shift mitigates single-AZ impairments within one Region and does not replace cross-Region failover.

## 9. AWS Elastic Disaster Recovery: Recovery and Reverse Replication

AWS Elastic Disaster Recovery (DRS) protects on-premises servers, AWS servers, and supported cloud environments via continuous block-level replication to a staging area subnet in a target AWS Region. Staging uses minimal storage and compute to sustain replication. On demand, DRS launches drill instances or recovery instances in AWS.

General DRS workflow:

1. Install the replication agent on source servers.
2. Configure replication settings, staging subnet, security groups, disks, and bandwidth.
3. Wait for initial sync to finish.
4. Monitor data replication and lag.
5. Configure launch settings so recovery instances receive appropriate instance types, subnets, security groups, IAM roles, and networking.
6. Run periodic recovery drills to confirm instances boot and applications function.
7. During a disaster, launch recovery instances from an appropriate point in time.
8. Validate the application and shift traffic using Route 53 or your traffic manager.

DRS launches recovery instances, while shifting traffic to them occurs outside DRS. Pair DRS with Route 53, ARC, or another traffic management solution.

### 9.1. Failback with DRS

Once the source environment is restored, data on recovery instances has changed. DRS supports reverse replication to send changes from recovery instances back to source servers.

Typical workflow:

1. Restore source infrastructure and verify it is safe to receive data.
2. Confirm recovery instances hold authoritative data.
3. Initiate reverse replication from recovery instances to source servers.
4. Monitor replication status and lag until Ready or Ready with lag per DRS status rules.
5. To minimize data loss, stop or quiesce writing applications in DR during the final sync window.
6. Run failback launch to boot updated servers on the source infrastructure.
7. Verify applications, networking, storage, identity, and business transactions on source.
8. Shift traffic back to source via Route 53 or traffic manager.
9. Confirm only source accepts writes; DR no longer receives writes.
10. Once stable, re-establish replication from source back to the DR Region to restore DR protection.

For on-premises sources, failback can use the Failback Client ISO or DRS Failback Automation. For same-account or cross-account EC2 sources, initiate reverse replication from the recovery instance per DRS guidance. Verify architecture and OS limits—for example, Failback Client supports x86_64, while ARM64 carries specific failback constraints.

DRS does not shift traffic during failback. Operations must steer DNS or routing after confirming data synced and source workloads are ready.

Never run steps that replace source replication during a routine recovery drill in ways that disturb production protection. Drills must leave live source servers and normal replication untouched.

## 10. Failover and Failback for Databases

Databases are often the hardest tier because transactions, replication lag, connection pools, and write authority require strict control.

### 10.1. Amazon RDS Cross-Region Read Replicas

RDS supports cross-Region read replicas for eligible engines and configurations. Replication is typically asynchronous. When primary fails, promote the read replica to a standalone DB instance accepting writes.

Before promoting:

- Check replication lag and last update timestamp.
- Estimate potentially lost tail transactions.
- Stop or fence writes at primary if still reachable.
- Verify engine version, parameter group, option group, subnet group, and security groups.
- Update applications to connect to the promoted DB's endpoint.

After failover, the promoted replica is no longer a read replica of the old primary. To fail back, rebuild a new replication relationship from the authoritative DB in DR to a new target or repaired primary. You cannot simply reverse an already-promoted replica without reconfiguring topology.

### 10.2. Aurora Global Database

Aurora Global Database uses physical asynchronous replication across Regions. Secondary Regions serve read traffic and can promote to primary when needed.

Distinguish:

- **Switchover:** used when all clusters and services are healthy, typically for maintenance or planned Region rotation. Aurora synchronizes secondaries before swapping roles, targeting zero RPO.
- **Unplanned failover:** used when the primary Region fails. Secondary promotes rapidly, yet RPO is typically non-zero in seconds depending on lag at failure time.

During unplanned failover, recent transactions may not have reached secondary. Aurora may snapshot the old storage volume to assist recovering missing data if possible. Post-failover, other secondary Regions may need rebuilding from the new primary.

Watch for split-brain risk. Aurora attempts best-effort write fencing on the old primary during managed failover, which may not complete immediately in every scenario. If the old primary remains reachable, check events confirming write suspension and confirm clients use the new endpoint before opening broad write traffic. Shortening DNS cache TTLs helps reduce stale writes to the old endpoint, yet does not replace fencing and application controls.

Planned switchover and unplanned failover serve different data guarantees. Never run switchover while primary or secondary is severely degraded without verifying sync health.

### 10.3. DynamoDB Global Tables

DynamoDB global tables replicate tables across Regions and support reads and writes in multiple replica Regions. This is a multi-Region, multi-active model. When creating a global table, pick one of two consistency modes: Multi-Region eventual consistency (MREC) or Multi-Region strong consistency (MRSC). Consistency mode cannot be changed after table creation.

| Mode | Replication and Consistency | RPO and Key Constraints |
|---|---|---|
| MREC | Asynchronous replication; updates typically propagate in about a second or less. Concurrent updates to the same item resolve via last-writer-wins using internal timestamps. | RPO equals replication delay, typically seconds; multi-account global tables support MREC only. Transactions are atomic only within the calling Region and other Regions may observe partial states. |
| MRSC | Writes replicate synchronously to at least one other Region before acknowledging success; strong reads at replicas return the latest version. | Zero RPO within supported model; requires exactly three Regions (three replicas or two replicas plus one witness) with restricted Region sets; no TTL, LSI, or transaction APIs. |

MRSC increases write and strong-read latency due to cross-Region coordination. Concurrent competing updates across Regions can raise ReplicatedWriteConflictException, requiring controlled retries. Confirm Region sets, account models, and feature limitations before selecting MRSC. For MREC, monitor CloudWatch ReplicationLatency; note this metric is not an SLA on replication timing.

Explicitly design:

- Which Region clients pick for reads and writes.
- How concurrent updates on the same item behave under your chosen conflict-resolution semantics.
- Which business invariants require single-Region enforcement or transactional workflows.
- Retries and idempotency keys to avoid duplicate transactions.
- How applications detect active Regions and stop writing to isolated Regions.
- Independent backups/PITR to recover from logic bugs or propagated deletions.

Global tables remove single-primary dependency without eliminating business conflicts. When two Regions concurrently update the same item, design data models around the platform's version resolution rules.

## 11. Failover for Object and File Storage

### 11.1. Amazon S3 Cross-Region Replication

S3 CRR copies new and updated objects per replication rules from a source bucket to a destination bucket in another Region. Both buckets require versioning. The IAM replication role needs read permissions on source versions and write permissions at destination. With SSE-KMS, configure KMS key policies on both sides.

Items to verify:

- Replication is asynchronous; never assume a newly PUT object exists immediately at destination.
- Monitor object replication status and replication metrics.
- Replication Time Control (RTC) helps track time-bounded targets for most objects, yet does not replace verifying critical individual objects.
- Delete marker replication and delete replication behavior vary by rule version; configure and verify them explicitly rather than assuming all deletes replicate identically.
- Objects predating the rule require S3 Batch Replication to copy historical data.
- Object Lock, ownership, ACLs, and KMS keys must align at destination.
- When failing over to the destination bucket, point applications to that bucket's endpoint and verify write permissions.

Once DR takes writes, failing back requires syncing changes back to the primary bucket. Configure reverse replication or run S3 Batch Replication/DataSync depending on scale and rules. Before shifting apps back, confirm all new objects, versions, and delete markers converged. Never blindly turn on bidirectional replication without loop-prevention and conflict rules.

### 11.2. Amazon EFS and DataSync

EFS replication copies a file system to another file system, typically in another Region. The destination serves as a recovery copy; before enabling writes at destination, inspect replication state, last sync timestamp, and promote/failover procedures per current EFS guidance.

AWS DataSync fits scheduled or task-based file transfers across on-premises, EFS, FSx, and S3. DataSync can run periodically to copy deltas, though it does not turn a file share into an active-active file system. Define handling for open files, files modified mid-copy, permission metadata, and final sync before cutover.

For file systems, verify file counts, byte sizes, checksums, or manifests after syncing. If both sides accepted writes, enforce explicit rules deciding which version wins.

## 12. Failback and Data Synchronization Back to Primary

Once DR has served production, treat failback like a major production change. Plan ahead, schedule maintenance or write-freeze windows if needed, and define abort criteria.

~~~mermaid
flowchart TD
    A[Resolve primary Region issue] --> B[Rebuild and secure primary]
    B --> C[Start reverse replication from DR]
    C --> D[Monitor lag and validate data]
    D --> E{Ready for final sync?}
    E -- No --> C
    E -- Yes --> F[Quiesce writes in DR]
    F --> G[Final sync and fence DR writer]
    G --> H[Promote or activate primary]
    H --> I[Run smoke and business validation]
    I --> J{Primary healthy?}
    J -- No --> K[Keep DR authoritative]
    J -- Yes --> L[Shift traffic to primary]
    L --> M[Re-establish replication to DR]
    M --> N[Verify protection restored]
~~~

Detailed steps:

1. **Confirm root cause resolution:** verify Region health, networking, account permissions, quotas, and dependencies.
2. **Prepare primary:** patch faults, restore capacity, configure security, secrets, KMS, DNS, monitoring, and endpoints.
3. **Establish authoritative source:** while DR is active, DR holds authoritative data. Never treat the stale primary as authoritative without reconciliation.
4. **Start reverse replication:** configure replication from DR to primary using service-appropriate tools.
5. **Monitor lag:** wait until backlog drops within approved thresholds and confirm the last checkpoint synced.
6. **Quiesce writes:** switch apps into maintenance/read-only mode or pause writers/queue consumers in DR.
7. **Final sync:** flush remaining deltas and verify record counts/transactions.
8. **Fence DR writer:** block DR from accepting further writes before opening primary writes.
9. **Promote/activate primary:** transition primary databases and storage to read/write.
10. **Validate:** verify business transactions, schemas, object counts, permissions, endpoints, and health checks.
11. **Shift traffic:** point DNS/routing back to primary.
12. **Monitor:** watch stray traffic still hitting DR, connection errors, replication, and fresh writes.
13. **Re-establish DR:** configure forward replication from the restored primary back to DR.
14. **Declare normal operations:** close the incident only after primary stabilizes and DR protection is restored.

If writes cannot pause completely, enforce a consistency protocol using versions/watermarks, transaction logs, or application-level fencing. Never rely on wall-clock timestamps to pick winners when clock skew is possible.

## 13. Reconciliation After Dual Writes

If both primary and DR accepted writes during an incident, datasets can diverge. Reconcile before failing back.

Strategies:

- **Single-writer:** allow only one Region to write per dataset—the simplest way to prevent conflicts.
- **Partition ownership:** assign each Region a disjoint set of tenants, accounts, or key ranges.
- **Version vectors or revision numbers:** detect concurrent edits via monotonic versions.
- **Conflict resolution:** apply business rules such as last-writer-wins, structural merge, or manual review.
- **Event replay:** persist event/transaction logs and replay missing items in order.
- **Idempotent operations:** attach idempotency keys so retries never duplicate transactions.
- **Reconciliation jobs:** compare totals, checksums, and business states to surface discrepancies.

Orders example:

- Each order has a unique OrderId and a version incremented on every update.
- Every transaction carries an idempotency key.
- DR maintains an event outbox recording all mutations created during DR.
- When primary returns, reconcile OrderId/version, payments, inventory, and invoices.
- Conflicts that cannot auto-merge route to a manual review queue.
- Open live write traffic on primary only after reconciliation finishes.

Never delete conflicting rows simply to make two databases match superficially. Maintain an audit trail, business rule rationale, and approvers for any reconciliation affecting financial or customer records.

## 14. Orchestrating Recovery with ARC Region Switch and Systems Manager

For multi-component applications, standalone failover scripts easily run out of order. Use ARC Region switch to model workflows as structured application recovery plans.

Example active/passive plan:

1. Verify target Region and resource states.
2. Scale up compute and database dependencies.
3. Promote databases or activate data endpoints.
4. Update secrets/configurations.
5. Run health checks and smoke tests.
6. Flip routing controls or DNS.
7. Check CloudWatch alarms and application metrics.
8. Log execution results and notify the incident commander.

Region switch executes blocks sequentially or in parallel. A parent plan can orchestrate child plans for application tiers or microservices. Parallelize steps only when they share no data or state dependencies.

Systems Manager Automation handles targeted operations like checking EC2 state, updating configs, calling APIs, or running commands on managed nodes. Step Functions orchestrates application logic across AWS APIs. EventBridge triggers workflows from alarms or events. Regardless of tool, enforce idempotency, bounded retries, approval gates, and post-condition checks.

Never trigger automated failover from a single alarm without ruling out false positives, maintenance windows, replication lag, and DR capacity. Require human approval or rehearsed break-glass gates for irreversible or potentially data-losing steps.

## 15. Testing Failover and Failback

A DR plan is trustworthy only after testing. Never wait for a real disaster to validate roles, quotas, networking, and DNS.

Test types:

| Test Type | Goal | Impact |
|---|---|---|
| Tabletop exercise | Walk through roles, decisions, and communications | Zero infrastructure impact |
| Component restore test | Restore databases/files from backups | Provisions isolated test resources |
| DRS drill | Boot drill instances from replication | Zero disruption to source workloads |
| Planned switchover | Swap primary/secondary while both are healthy | Possible brief interruption |
| Full failover exercise | Shift full live traffic to DR | High impact; requires change window |
| Failback exercise | Reverse-sync and return to primary | High impact; requires write controls |

Measure in every drill:

- Time to detect and declare the incident.
- Time to fence primary.
- Replication lag and actual data loss.
- Time to boot databases and compute.
- Time for DNS/routing shifts and client reconnection.
- Time for smoke tests and business validation.
- Time for reverse replication and final sync on failback.
- Actual RTO/RPO compared against targets.
- Number of manual steps and runbook defects.

ARC Region switch performs plan evaluations and quota checks to flag configuration issues. However, plan evaluation never replaces a real recovery drill. Execute plans in test environments and prove the application actually works.

## 16. Monitoring, Alerting, and Audit Trails

In steady state, continuously monitor replication and readiness. During incidents, maintain dashboards for both primary and DR.

Key metrics:

| Category | Metrics |
|---|---|
| DRS | Replication lag, data backlog, source server state, staging area health |
| RDS | ReplicaLag, DB connections, failover events, engine health |
| Aurora Global Database | AuroraGlobalDBRPOLag or engine-appropriate lag metrics |
| S3 | Replication latency, OperationsPending, BytesPendingReplication, OperationsFailedReplication |
| EFS | Replication status, last sync time, and throughput |
| Traffic | DNS health, routing control state, requests per Region, connection errors |
| Application | Availability, latency, error rates, queue backlogs, business transaction success |
| Capacity | EC2 capacity, Auto Scaling desired/in-service, DB quotas, IP/subnet capacity |

Record for every event:

- Incident ID and decision-makers.
- Source/target Regions, accounts, and resource identifiers.
- Chosen recovery point or replication checkpoint.
- Replication lag at failover/failback time.
- Step timestamps and execution IDs.
- Routing control states before and after cutover.
- Validation and reconciliation outcomes.
- Approvers, exceptions, and when writes reopened.

CloudTrail tracks who changed routing, database roles, IAM policies, security groups, or backup configs. CloudWatch and EventBridge detect incidents, send alerts, and trigger workflows. Restrict log read access and never write secrets or sensitive personal data into incident tickets.

## 17. Common Troubleshooting

| Symptom | Possible Cause | Investigation Steps |
|---|---|---|
| DR instance fails to launch | Bad launch settings, missing quotas, or missing AMI/network | Check DRS launch settings, instance type, subnet, security group, and quotas |
| Replication lag climbs | Network, staging storage, or source write-rate changes | Inspect DRS replication dashboard, throughput, and staging area |
| Secondary DB missing transactions | Async replication trailed primary | Check lag/checkpoints and quantify actual RPO |
| Aurora failover causes write errors in old Region | Old primary not fenced or clients hold stale connections | Check RDS events, writer endpoints, DNS caching, and app pools |
| DNS changed yet traffic still hits primary | Client resolver cache, long-lived connections, or proxy cache | Inspect per-Region access logs, TTLs, and connection pools |
| App in DR cannot reach database | Secrets, security groups, endpoints, or CA certs still point to primary | Verify target-Region configs/secrets and network paths |
| S3 objects missing at destination | Replication pending/failed or objects predated rule | Check replication status, Batch Replication, KMS, and IAM |
| Failback fails to start | Reverse replication unready or source server unreachable | Check DRS source/recovery instance states and failback prerequisites |
| Both sides hold divergent data | Both Regions accepted writes or duplicate replay occurred | Halt one writer, preserve snapshots/logs, and run reconciliation |
| DR Region lacks capacity | Quotas or capacity unprepared | Check quota parity, instance availability, and reserved capacity |
| Routing control update fails | ARC cluster endpoint unreachable or safety rule blocked it | Retry alternate endpoints, inspect control states, and check break-glass steps |
| Failback finished yet DR is unprotected | Reverse-direction replication not re-enabled | Verify replication direction, source server protection, and run a fresh drill |

When failures occur, preserve relevant data and logs. Never trigger overlapping promotions or reverse replications simultaneously before clarifying which path holds write authority. Verify database, replication, routing, and execution states before retrying.

## 18. Practical Walkthrough: Failover and Failback for an E-Commerce App

An online store runs on EC2/ECS in ap-southeast-1. The database uses Aurora Global Database; invoices reside in S3; Secrets Manager holds credentials; Route 53 ARC routing controls steer traffic. The DR Region is ap-southeast-2.

Assumed targets:

- Database RPO under 1 minute under normal replication.
- Application RTO under 30 minutes.
- Only one Region may write transactional data at a time.
- Once primary recovers, reverse-sync and validate before failing back.

### Steady State

- ap-southeast-1 is primary and serves live traffic.
- Aurora secondary in ap-southeast-2 replicates asynchronously.
- S3 CRR copies invoices and uploaded files.
- DR compute runs as warm standby at low baseline capacity.
- Secrets, IAM roles, certificates, networking, and monitoring exist in both Regions.
- ARC routing controls keep traffic on primary.

### When the Primary Region Fails

1. Incident commander confirms the outage exceeds primary recovery limits.
2. Database team inspects Aurora replication lag and selects the appropriate secondary.
3. Execute Aurora Global Database failover; record actual RPO and RDS events.
4. Confirm the application stopped writing to the old primary; verify writer endpoint and client connections.
5. Scale up compute in ap-southeast-2.
6. Verify secrets, S3 buckets, IAM, and networking in DR.
7. Run smoke tests: login, test order creation, inventory reads, and invoice writes.
8. Enable the DR routing control, disable primary per safety rules, and shift traffic.
9. Monitor error rates, DB connections, order success, and S3 replication.
10. Declare DR as the authoritative data source.

### When the Primary Region Recovers

1. Verify primary infrastructure is safe, patched, and holds sufficient capacity.
2. Confirm current DR data is authoritative.
3. Configure replication from DR back to primary using supported DB and object mechanisms.
4. Monitor lag and reconcile orders, payments, inventory, and invoices.
5. Schedule a maintenance window and place the app in write-restricted mode if needed for final sync.
6. Complete final sync and fence the DR writer.
7. Promote/activate databases and storage in primary.
8. Run smoke tests and verify business invariants.
9. Shift traffic back to primary via routing controls.
10. Monitor stray traffic hitting DR and watch app error rates.
11. Re-establish forward replication from primary to DR.
12. Run a post-failback recovery drill to confirm DR protection is active again.

Never shift traffic back to primary before reverse replication, reconciliation, and final sync complete. If primary fails health checks post-cutover, keep DR authoritative and roll back routing per runbook.

## Conclusion

Failover shifts workloads and traffic to an operational environment; failback returns systems to primary after synchronizing changes created during DR operations. Replication, backups, data promotion, and traffic routing are distinct steps that must be coordinated through checkpointed runbooks.

A dependable design governs RPO/RTO, replication lag, consistency, write authority, and split-brain risks. AWS Elastic Disaster Recovery supports server recovery and reverse replication; database, object, and file services provide native replication; Route 53 ARC and Region switch orchestrate traffic and recovery steps. After every failover, validate data, reverse-sync, fence writers, complete final sync, and test before failing back.

Rehearse both failover and failback directions. Only when real timings are measured, data consistency is verified, and DR replication is restored is the system ready for the next incident.

## References

- [Defining your disaster recovery strategy](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-database-disaster-recovery/defining.html)
- [Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [AWS Well-Architected REL13: recovery planning](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [What is AWS Elastic Disaster Recovery?](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Recovery and failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/failback.html)
- [Performing a failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/failback-performing-main.html)
- [Failback with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/guidance/latest/deploying-cross-region-disaster-recovery-with-aws-elastic-disaster-recovery/failback.html)
- [Routing control in Amazon Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.html)
- [About routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html)
- [Creating safety rules for routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.safety-rules.html)
- [Best practices for routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/route53-arc-best-practices.regional.html)
- [Region switch in Amazon Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/region-switch.html)
- [About Region switch plans](https://docs.aws.amazon.com/r53recovery/latest/dg/region-switch-plans.html)
- [Execute a Region switch plan](https://docs.aws.amazon.com/r53recovery/latest/dg/plan-execution-rs.html)
- [ARC readiness check availability change](https://docs.aws.amazon.com/r53recovery/latest/dg/arc-readiness-availability-change.html)
- [Using switchover or failover in Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html)
- [Cross-Region resiliency for Aurora Global Database](https://docs.aws.amazon.com/us_en/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-secondary-availability.html)
- [AWS disaster recovery with RDS read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.XRgn.html)
- [DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [How DynamoDB global tables work and consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)
- [Amazon S3 replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [S3 Replication Time Control](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-time-control.html)
- [Amazon EFS replication](https://docs.aws.amazon.com/efs/latest/ug/replication.html)
- [AWS DataSync](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html)
