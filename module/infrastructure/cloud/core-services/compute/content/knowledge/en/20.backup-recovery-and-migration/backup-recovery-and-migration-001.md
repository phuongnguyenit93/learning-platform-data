# RPO, RTO, and Backup Workload Protection Scope

A cloud workload can run across multiple components: virtual machines, containers, volumes, databases, object storage, queues, network configurations, identities, and encryption keys. When hardware failures, accidental data deletions, deployment errors, malware, or cloud region-wide outages occur, simply restarting a server may not restore the service. Operations teams need to know the maximum amount of data that can be lost, how long it can take to bring the service back online, and which components are actually covered by protection.

Two critical metrics for designing resilience are **RPO (Recovery Point Objective)** and **RTO (Recovery Time Objective)**. RPO describes the acceptable level of data loss; RTO describes the acceptable downtime. These two metrics guide backup frequency, copy storage methods, recovery capacity, and operational costs.

This lesson belongs to the **Backup, Recovery, and Migration** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute capacity models, from virtual machines and containers to serverless; how to select CPU, memory, networking, and security configurations; and how to deploy applications, scale under load, ensure availability, and optimize operational costs. Within that scope, RPO, RTO, and backup scope help determine which workloads need protection, how to protect them, and how to prove they can be recovered.

## 1. What Are RPO and RTO?

### 1.1. Recovery Point Objective (RPO)

**RPO** is the maximum amount of data loss an organization can tolerate when an incident occurs, usually expressed as a time interval.

For example, an RPO of 30 minutes means the organization accepts restoring data to a point that could result in losing up to roughly the last 30 minutes of changes. To meet this objective, a valid recovery point must exist close enough to the incident time, and the copy must contain consistent data.

RPO is not simply the backup creation frequency. If a backup schedule runs every 15 minutes but the job often takes 20 minutes to finish, fails, or produces an unrestorable copy, the actual RPO may exceed 15 minutes. It must be measured by the timestamp of a verified usable recovery point.

### 1.2. Recovery Time Objective (RTO)

**RTO** is the maximum allowed duration to restore a service or workload after a disruption to a level that meets defined operational requirements.

For example, an RTO of 4 hours means the service must be restored within 4 hours according to the agreed measurement method. Recovery may include creating new compute resources, attaching or restoring data, restoring configurations, checking dependencies, verifying the application, and routing traffic back.

RTO is not just the time required to copy data. Detection, decision-making, granting recovery access, provisioning infrastructure, restoring data, replaying logs, testing, and shifting traffic all consume time.

### 1.3. Distinguishing RPO and RTO

| Metric | Question Answered | Common Units | Key Design Factors |
|---|---|---|---|
| RPO | How much data can be lost? | Seconds, minutes, hours | Backup frequency, replication lag, log shipping, checkpoints |
| RTO | How long can downtime last? | Minutes, hours | Provisioning speed, restore speed, automation, recovery capacity, and testing |

Examples:

- A system with an RPO of 15 minutes and an RTO of 2 hours: needs a recovery point no older than about 15 minutes, and the service must be back online within at most 2 hours.
- A reporting archive with an RPO of 24 hours and an RTO of 2 days: can use scheduled backups and a slower restore process.
- A critical transactional system with an RPO of a few seconds and an RTO of a few minutes: typically requires continuous replication, automated failover or pre-provisioned standby, along with consistency protection mechanisms.

A low RPO does not automatically yield a low RTO. You may have very recent copies yet still need many hours to provision infrastructure and restore. Conversely, you may boot a standby very quickly, only to find its data lags behind by several hours.

### 1.4. RPO/RTO Are Objectives, Not a Tool's Promise

A backup product can provide snapshots, replication, or restore points, but the tool does not dictate business objectives. RPO/RTO must come from the impact of service downtime or data loss.

A system is only considered compliant with its objectives when there is measurable evidence. You must perform test restores, record actual timings, verify data integrity, and validate dependent components.

## 2. Defining Objectives from Business Requirements

### 2.1. Business Impact Analysis

Before choosing a backup schedule, you need to understand how critical the service is and the consequences of data loss or disruption.

Questions to clarify:

- Does the service serve external customers, internal users, or background processes?
- How does downtime affect revenue, safety, contracts, or legal obligations?
- Which data can be regenerated and which data is non-recreatable?
- Can operations temporarily fall back to manual processes?
- Does it depend on other systems?
- Are there peak seasons or blackout windows where downtime is unacceptable?
- Who decides to declare disaster recovery and accept data loss?

The results are typically documented in a Business Impact Analysis (BIA), criticality classifications, and business continuity plans.

### 2.2. Classifying Workloads by Criticality

You can start with illustrative tiers:

| Tier | Example Workload | Reference RPO | Reference RTO |
|---|---|---:|---:|
| Tier 0 - Mission Critical | Core transactions, identity, or internal control plane | Seconds to a few minutes | A few minutes |
| Tier 1 - Critical | Customer APIs, orders, payments | 5-15 minutes | 1-2 hours |
| Tier 2 - Standard | Operational reporting, asynchronous workers | 1-4 hours | 4-8 hours |
| Tier 3 - Deferrable | Regenerable analytics data, dev environments | 24 hours or more | 1-3 days |

These are only examples for discussion. Do not treat these figures as default SLAs. Organizations must approve objectives based on BIA, regulations, architecture, cost, and operational capability.

### 2.3. Each Workload Can Have Different Objectives

An application may contain multiple types of data:

- Transactional databases require a low RPO.
- Uploaded files may need frequent backups while being restored independently.
- Caches can be regenerated and do not require backups.
- Logs may need retention for audit purposes without necessarily being in the application recovery path.
- Aggregated reports can be regenerated from source data.
- Message queues need separate policies for message retention, dead-lettering, and replay.

Do not assign a single RPO to the entire application if components have different characteristics and recovery capabilities. Define the overall service RPO/RTO alongside the objectives for each dependency.

## 3. Measuring Actual RPO and RTO

### 3.1. Actual RPO

At the time of an incident, find the newest recovery point that is complete, consistent, and restorable. The gap between the point to which data must be recovered and the timestamp of that recovery point is the actual data loss.

Expressed simply:

**Actual RPO = incident timestamp - timestamp of the most recent valid recovery point**

The timestamp must reflect when the data in the copy was valid, not merely when the backup job started or ended. For multi-part backups or backups with transaction logs, you must determine the latest point that can be consistently reconstructed.

Example:

- An incident occurs at 14:00.
- The most recent verified recovery point is 13:42.
- The actual RPO is approximately 18 minutes.

If a backup at 13:57 exists but the file is corrupted or missing required transaction logs, it cannot be counted as a valid recovery point.

### 3.2. Actual RTO

RTO must be measured from an agreed starting point—typically when the service is disrupted or the incident is declared—until the service is restored and verified against minimum criteria.

**Actual RTO = timestamp when service recovery meets criteria - incident start timestamp**

Example:

| Phase | Duration |
|---|---:|
| Detection, confirmation, and recovery decision | 10 minutes |
| Provisioning compute and network | 15 minutes |
| Restoring database and volumes | 55 minutes |
| Restoring secrets, configuration, and dependencies | 15 minutes |
| Testing data, application, and traffic | 20 minutes |
| Total | 115 minutes |

If the RTO target is 2 hours, this example leaves a 5-minute buffer. In practice, you need to measure multiple times and account for slower scenarios rather than relying only on the best-case run.

### 3.3. Include Verification Time

Do not stop the RTO clock as soon as the VM boots or the database process reports running. A service is only considered recovered when it meets agreed criteria, such as:

- API health checks succeed.
- Users or upstream systems can access it.
- The database is no longer in recovery pending state.
- Data reaches the required level of consistency.
- Queues/streams can resume consumption.
- Monitoring, logging, and backups are active.
- Access permissions and auditing are restored.

### 3.4. Tracking Objectives via Dashboards

You can track:

- Target RPO and most recent actual RPO.
- Age of the newest recovery point.
- Backup success/failure rate.
- Replication lag.
- Restore duration by data size.
- Actual RTO across drills.
- Percentage of workloads with passing restore tests.
- Number of backup exceptions and their duration.
- Backup capacity and storage cost.

Alerts should trigger before an RPO breach occurs—for instance, when the recovery point age approaches the target threshold, or when replication lag exceeds its threshold.

## 4. Backup Workload Protection Scope

### 4.1. Backups Must Protect All Components Needed to Run the Service Again

A compute workload consists of more than just VMs or containers. When scoping backups, inventory all components:

| Component | Considerations | Common Protection Methods |
|---|---|---|
| Compute instance | OS, packages, runtime, host config | Golden images, image versioning, IaC, backup when needed |
| Persistent block volume | Files, database data, application state | Snapshots, scheduled backups, replication |
| Database | Data files, transaction logs, schema, metadata | Native backups, log backups, PITR, replicas |
| Object/file storage | Objects, versions, metadata, ACLs | Versioning, replication, backup/retention policies |
| Queue/stream | Messages, offsets, partition metadata | Retention, snapshots/checkpoints, replay |
| Container image | Published image layers and digests | Registry replication, artifact retention |
| Kubernetes config | Manifests, Helm values, CRDs, policies | Git/IaC, exports, and backups of required metadata |
| Serverless config | Function code, runtime, versions, triggers, layers | Source/artifact repositories, IaC, release archives |
| Network | VPC/VNet, subnets, routes, firewalls, DNS | IaC, config exports, version control |
| Identity and secrets | IAM policies, roles, certificates, key references | Secure config backups, secret managers, key recovery plans |
| Observability | Dashboards, alerts, log routing, agent configs | IaC and configuration exports |
| Recovery metadata | Catalogs, encryption metadata, dependency maps | Backup catalogs, independent recovery accounts |

Not every component needs to be copied as a binary backup. Some can be rebuilt from source code, image pipelines, or IaC. However, you must ensure the required artifacts, versions, and information remain accessible if the primary environment is lost.

### 4.2. Distinguishing Persistent and Ephemeral Data

- **Persistent data:** databases, user files, stateful volumes, objects, and transactional data. Generally requires explicit backup/replication.
- **Ephemeral data:** caches, temporary files, scratch space, and regenerable data. May not need backups if confirmed to hold no unique state.
- **Configuration:** can be regenerated from IaC or configuration management, but deployed versions and required values must be preserved.
- **Runtime artifacts:** images, packages, function bundles, and dependencies. Matching artifacts must be retained to avoid rebuilding a different version during recovery.

Do not assume data is ephemeral solely from a volume name or mount path. Consult the application owner and verify actual behavior.

### 4.3. VM Images Do Not Replace Data Backups

A VM image typically recreates the operating system and base software. It may not contain the latest data on detached volumes or managed databases.

A common design pattern:

- Use a standard image to stand up compute.
- Use IaC to create networks, security policies, and IAM.
- Restore persistent volumes or databases from a recovery point.
- Inject secrets and certificates via an appropriate management system.
- Deploy the tested application version.
- Run verification checks before opening traffic.

If you only back up the boot disk, you may restore the OS while losing all data residing on data disks.

### 4.4. Container Images Do Not Contain Full Application State

A container image contains the packaged filesystem and dependencies. Persistent volumes, external databases, object storage, secrets, and cluster configurations can live outside the image.

When protecting Kubernetes workloads, identify:

- Image digests and registries.
- Deployments, StatefulSets, Services, and Ingress/Gateways.
- Required ConfigMaps and custom resources.
- Secrets or a secure way to recreate them.
- PersistentVolumes and PersistentVolumeClaims.
- StorageClasses, CSI drivers, and snapshot support.
- CRDs, operators, and cluster versions.
- NetworkPolicies, service accounts, and RBAC.

Do not export plaintext secrets into repositories or unencrypted backups. Protect both access to the secret manager and the decryption keys needed for recovery.

### 4.5. Serverless and Managed Services

The provider may manage the compute hosts, but customers still need to back up:

- Source code and deployed artifacts.
- Runtime versions, layers, and extensions.
- Environment configurations and triggers.
- IAM roles/policies and resource bindings.
- Event source mappings, schedules, and permissions.
- Databases, object storage, queues, and external data outside the function.
- KMS keys, certificates, and secret references.

A function can be redeployed easily yet still fail to operate if its triggers, invocation permissions, secrets, or database endpoints are not restored.

## 5. Data Protection Methods

### 5.1. Full Backup

A full backup copies the entire selected data scope at a point in time.

Advantages:

- Relatively independent restore points.
- Restore procedures are typically straightforward.
- Easy to identify the contents of a backup.

Limitations:

- Consumes significant creation time and storage capacity.
- Can increase load on the source system.
- High transfer and storage costs for large datasets.

### 5.2. Incremental Backup

An incremental backup stores changes since the previous backup according to the product's design.

Advantages:

- Reduces the amount of data transferred and stored each run.
- Suitable for large datasets that change frequently.

Limitations:

- Restoring may require multiple components in the backup chain.
- If a dependent piece is missing or corrupted, related recovery points may become unusable.
- Requires catalog management and backup chain verification.

Some products use incremental-forever and synthesize data on the backend; restore behavior depends on the implementation. Do not assume all incremental systems require manually stitching every file together.

### 5.3. Differential Backup

A differential backup stores changes since the most recent full backup. Restoring typically requires the latest full backup and the selected differential backup.

Advantages:

- Restores can be simpler than long incremental chains.
- Each differential generally grows until the next full backup.

Limitations:

- Storage usage grows over time between full backups.
- Creating full backups can impose substantial load.

### 5.4. Snapshot

A snapshot captures the state of a volume or resource at a point in time using the platform's mechanism.

Snapshots can be fast and convenient for creating restore points, but check:

- Whether the snapshot is crash-consistent or application-consistent.
- Whether it includes all related volumes.
- Whether the snapshot is independent of the source account/region.
- Whether it can be deleted alongside the source account or administrative credentials.
- Whether immutable retention or vault lock is supported.
- Whether it can restore to a different volume type or zone.

Snapshots in the same account and failure domain can be deleted or encrypted alongside the source system. Therefore, snapshots do not automatically replace an independent backup strategy.

### 5.5. Replication

Replication copies data to a replica or another location, either synchronously or asynchronously.

- **Synchronous replication:** typically requires writes to be acknowledged at multiple locations before completing; can minimize data loss but increases latency and depends on network delay.
- **Asynchronous replication:** writes on the source are acknowledged before the replica receives everything; can incur replication lag and lose recent changes during an incident.

Replication aids availability and fast recovery, but logical errors, accidental deletions, or ransomware can be replicated to the replica. Combine it with historical backups and the ability to roll back to a point before the incident.

### 5.6. Continuous Data Protection and Point-in-Time Recovery

Some systems continuously capture transaction logs or changes to allow recovery to a specific point within a retention window.

For example, a database can restore a full backup and replay transaction logs up to the moment right before an accidental deletion. This mechanism supports low RPO and finer-grained recovery than periodic backups, but relies on complete, ordered logs and sufficient retention.

Determine the supported PITR window and how to restore to a new instance for verification before replacing production.

### 5.7. Comparing Methods

| Method | Achievable RPO | Restore Time | Key Considerations |
|---|---|---|---|
| Scheduled full backup | Depends on backup frequency | Can be long for large data | Simple but storage-intensive |
| Incremental/differential | Depends on schedule and valid chain | Depends on backup structure | Catalog and dependency management |
| Snapshot | Depends on snapshot frequency and consistency | Often faster than full restore, volume-dependent | Requires independent copies and testing |
| Asynchronous replication | Depends on replication lag | Can be fast | Can replicate logical errors |
| Synchronous replication | Can approach zero under supported conditions | Can fail over quickly | Latency, quorum, and failure domains |
| PITR/log backup | Can be very low if logs are continuously protected | Depends on restore and log replay | Requires an unbroken log chain |

No single method is best for all workloads. Designs typically combine multiple mechanisms.

## 6. Backup Consistency

### 6.1. Crash-Consistent Backup

A crash-consistent snapshot resembles the state of data after a sudden power loss: flushed writes may be present, while writes sitting in memory or cache not yet written to disk may be lost.

Filesystems or databases may recover journals/logs after a restore, but not all applications are safe with crash-consistent snapshots.

### 6.2. Filesystem-Consistent and Application-Consistent

- **Filesystem-consistent:** the filesystem is brought to a suitable state for snapshotting, typically via flush or freeze operations.
- **Application-consistent:** the application is instructed to prepare data, flush buffers, complete or pause transactions, and coordinate the snapshot.

For databases, use native backup tools or database-supported quiesce mechanisms. Snapshotting multiple independent volumes at different timestamps can produce an inconsistent state if data spans across volumes.

### 6.3. Multi-Volume Backups

If a database uses a data volume, log volume, and config volume, you need a consistent recovery point across all of them.

Execution steps may include:

1. Use native backups or quiesce the application.
2. Flush and freeze filesystems if required by the procedure.
3. Take synchronized snapshots according to platform capabilities.
4. Record metadata linking the snapshots into a single recovery set.
5. Thaw filesystems and resume the workload.
6. Test restoring the entire volume group as a single unit.

Do not freeze filesystems for prolonged periods in production; write-pause durations must be evaluated and tested.

### 6.4. Backups Do Not Replace Transaction Logs

For databases, periodic full backups may not suffice for low RPO targets. Protect transaction logs or use PITR/continuous backup according to the database engine's capabilities.

If a full backup succeeds but the log chain has gaps, you cannot replay to the desired point in time. Monitor both data backup and log backup status.

## 7. Designing Backup Schedules and Retention

### 7.1. Choosing Frequency Based on RPO

Backup frequency must be high enough to create recovery points newer than the RPO target, accounting for job duration, latency, and verification.

For example, if the target RPO is 1 hour, you might schedule backups every 30 minutes to leave a buffer. However, a 30-minute schedule does not guarantee a 30-minute RPO if the backup takes 45 minutes or fails repeatedly.

Track the timestamp of protected data, not just the job start timestamp.

### 7.2. Retention Policies

Retention defines how long backups are kept and how many restore points exist.

Illustrative example:

- Keep hourly recovery points for 48 hours.
- Keep daily copies for 30 days.
- Keep weekly copies for 12 weeks.
- Keep monthly copies for 12 months or per archival requirements.

Actual policies must align with regulations, investigative needs, cost, and restore capability. Overly short retention risks missing older logical errors; overly long retention increases costs and exposure of sensitive data.

### 7.3. GFS and Tiered Retention

The Grandfather-Father-Son (GFS) model retains multiple tiers of recovery points:

- Son: frequent copies, short-term retention.
- Father: weekly copies, medium-term retention.
- Grandfather: monthly or annual copies, long-term retention.

This model balances granularity and storage cost. Ensure long-term copies remain readable, decryptable, and restorable with supported tools.

### 7.4. Retention Lock and Legal Hold

Some platforms support immutable retention or retention locks to prevent deletion or modification of backups during a defined period. This mechanism helps defend against ransomware or destructive actions.

Distinguish between:

- **Retention policy:** defines how long data is kept.
- **Immutable backup:** a copy that cannot be modified or deleted under lock conditions.
- **Legal hold:** retains data beyond standard schedules for legal or investigative requirements.
- **Lifecycle policy:** automatically transitions storage tiers or deletes expired data.

Retention locks can be difficult or impossible to shorten once enabled. Obtain approval for duration, cost, and compliance requirements before enabling them.

## 8. Protecting Backups from Incidents and Ransomware

### 8.1. Separating Failure Domains

If backups live in the same account, under the same admin permissions, and in the same region as production, an attacker or administrative mistake can wipe out both.

Consider:

- A dedicated backup account or project.
- Separating backup write permissions from backup delete permissions.
- Cross-region or cross-account copies for critical workloads.
- Immutable storage or vault lock.
- MFA and least-privilege access for backup admins.
- Audit logging for create, delete, restore, and retention-change actions.
- Independent recovery mechanisms for catalogs and encryption keys.

A copy in another region protects against certain regional outages, but does not automatically protect against global deletion if the same admin identity controls both locations.

### 8.2. The 3-2-1 Rule and Variants

The 3-2-1 rule is commonly interpreted as:

- Keep at least 3 copies of data.
- Store them on 2 different media types or failure domains.
- Keep at least 1 copy in another location.

Some organizations extend this to 3-2-1-1-0:

- One offline or immutable copy.
- Zero undetected backup errors through verification.

This is a guiding principle, not a formula guaranteeing absolute safety. Adapt it to your data, cloud architecture, RPO/RTO, and operational capacity.

### 8.3. Protecting Identities and Encryption Keys

Encrypted backups cannot be restored if keys are lost or key access is revoked.

A recovery plan must specify:

- Which KMS keys or key vaults encrypt backups.
- Who holds decryption permissions in an emergency.
- Whether keys depend on the impacted account/region.
- How to recover key material or access permissions.
- Whether dual control or break-glass accounts are required.
- Auditing and approval when invoking recovery permissions.

Never store plaintext private keys or secrets inside the same unprotected backup. Test decryption permissions in the recovery account.

### 8.4. Protecting Backups Against Malware

Ransomware may attempt to delete snapshots, encrypt backup files, or compromise the backup service. Countermeasures include:

- Immutable/WORM backups.
- Separate accounts and credentials.
- MFA, privileged access management, and approvals.
- Restricting recovery point deletion.
- Monitoring for bulk deletions or retention modifications.
- Scanning for malware before returning files/VMs to production.
- Retaining clean copies predating the intrusion.
- Practicing recovery in an isolated environment.

Do not immediately restore a backup just because it is the newest. If malware was already present earlier, recent copies may contain malware or persistence mechanisms.

## 9. Backup Scope by Compute Model

### 9.1. Virtual Machines (VM)

For VMs, decide how to protect:

- Boot disks and OS configuration.
- Data disks and filesystems.
- Databases or file-based application state.
- VM metadata, instance types, NICs, IPs, and placement.
- Security groups, firewalls, and routes.
- IAM roles/service identities.
- Images, startup scripts, and configuration management.
- Certificates, secret references, and key dependencies.

You can use images to recreate the OS and snapshots/native backups to recover data. Do not treat a VM image as a complete backup if data disks, databases, or external storage reside outside the image.

### 9.2. Containers and Kubernetes

Containers are typically recreated from images, while state may reside in persistent volumes or external services.

Protection scope may include:

- Registries and image digests.
- Manifests, Helm charts, Kustomize, or GitOps repositories.
- CRDs and operator configurations.
- Secret managers and certificates.
- Persistent volume snapshots/backups.
- Databases, object storage, and queues.
- Cluster identities, network policies, RBAC, and storage configurations.
- Kubernetes version and CNI/CSI compatibility.

Cluster recovery requires checking the installation order of CRDs/operators, storage drivers, network plugins, and workloads. If PVCs are restored before the CSI driver is ready, volumes may fail to attach.

### 9.3. Serverless

For functions or managed compute, the host layer is typically managed by the provider within the service boundary. Customers still need to back up code, artifacts, configurations, triggers, IAM, secrets, and data.

During recovery, verify:

- Runtime is still supported.
- Artifact matches the exact version/digest.
- Environment variables and secret references.
- Event triggers and permissions.
- Concurrency/quotas.
- Network attachments and private endpoints.
- Restored databases and object storage.

### 9.4. GPU and Accelerator Workloads

For GPU workloads, critical data may include model checkpoints, training state, dataset references, optimizer states, batch progress, driver/runtime compatibility, and images.

It is not always necessary to frequently back up full GPU memory or VM images. Usually, you should checkpoint at framework-safe boundaries and save to durable storage. When restoring, verify GPU type, drivers, CUDA/runtime, and framework compatibility.

## 10. Recovery Strategies and Disaster Recovery

### 10.1. In-Place Restore

An in-place restore returns data or configuration back to the existing resource.

Suitable when:

- The source resource remains safe.
- The incident only affects a single dataset or volume.
- Switching failure domains is unnecessary.

The risk is that if the source environment is compromised or broadly damaged, an in-place restore puts data right back into the same failure domain.

### 10.2. Restore to New Resources

You can create a new VM, volume, database, or cluster and restore into it. This approach enables independent validation before replacing production.

Typical workflow:

1. Select a verified recovery point.
2. Create an isolated network and security boundary.
3. Provision new compute and storage.
4. Restore data.
5. Restore configuration, secrets, and identities.
6. Verify consistency and application health.
7. Run smoke tests and business validation.
8. Shift traffic via DNS/load balancer.
9. Monitor and maintain rollback capability if cutover fails.

### 10.3. Pilot Light

Pilot light keeps a minimal set of core foundation components running, such as networking, database replicas, or essential configurations. When an incident occurs, the team provisions additional compute and capacity.

- Typically lower cost than warm standby.
- Higher RTO because resources must still be created and scaled out.
- Requires tested automation and runbooks.

### 10.4. Warm Standby

Warm standby maintains a scaled-down recovery environment running with capacity smaller than production, typically with synchronized or periodically restored data.

- Can scale up capacity rapidly when needed.
- RTO is usually lower than pilot light.
- Incurs ongoing costs for compute, storage, and replication.
- Requires verifying that the standby stays compatible and ready to serve traffic.

### 10.5. Active-Active or Multi-Site

Multiple sites serve the workload simultaneously, distributing traffic and data by design.

- Potential for very low RTO.
- RPO can be low if synchronous replication or suitable consistency mechanisms are used.
- High cost and operational complexity.
- Must handle split-brain, conflicts, quorum, failover, and failback.

Active-active does not mean all errors self-heal. A logical bug or malicious data change can propagate across multiple sites.

### 10.6. Comparing DR Models

| Model | Recovery Environment Readiness | Relative RTO | Relative Cost |
|---|---|---|---|
| Backup and restore | Backups only; environment built upon incident | Higher | Lower |
| Pilot light | Core foundational components ready | Medium to high | Low to medium |
| Warm standby | Small environment actively running | Low to medium | Medium to high |
| Active-active | Multiple sites actively operating | Lower if well-designed | High |

This is a relative comparison. Data size, network speed, automation, quotas, approval processes, and application complexity can cause actual RTO to vary significantly.

## 11. Workload Recovery Procedure

### 11.1. Pre-Incident Preparation

Ensure the following are ready:

- Inventory and dependency map.
- Approved RPO/RTO.
- Backup policies and retention.
- Component-level restore runbooks.
- Versioned IaC and artifacts.
- Recovery accounts and access permissions.
- KMS keys and decryption instructions.
- DNS/load balancer cutover plan.
- Decision-makers and communication channels.
- Most recent restore test evidence.

### 11.2. Execution Steps

~~~mermaid
flowchart TD
    A["Detect and triage incident"]
    B["Decide to activate recovery"]
    C["Select RPO-compliant recovery point"]
    D["Prepare account, keys, network, and quotas"]
    E["Provision compute/storage"]
    F["Restore data and configuration"]
    G["Verify consistency and dependencies"]
    H["Smoke test and business validation"]
    I["Traffic cutover"]
    J["Monitor, reconcile, and close incident"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
~~~

Each step needs an owner, time target, and completion criteria. If a recovery point is invalid, fall back to another point rather than continuing an uncompletable restore process.

### 11.3. Dependency Recovery Order

A common ordering:

1. Identity, recovery access permissions, and encryption keys.
2. Network, DNS, routes, firewalls, and private endpoints.
3. Storage, database, and messaging infrastructure.
4. Compute platform, Kubernetes, or runtimes.
5. Application artifacts, configurations, and secrets.
6. Workers, schedulers, integrations, and background jobs.
7. Load balancers, ingress, and traffic routing.
8. Monitoring, logging, alerting, and backup policies.

This is a reference order, not a rigid sequence for every architecture. Networking may need to be restored first to reach identity or KMS; some platforms require break-glass identity before creating networks. Runbooks must document real dependencies and establish controlled emergency access.

### 11.4. Failback

After running on the recovery environment, you may need to return to the primary site. Failback is also a risky migration:

- Identify which site is currently the authoritative write source.
- Sync changes generated during the DR period.
- Check replication lag and consistency.
- Pause or shift traffic in sequence.
- Transfer write/leader authority.
- Verify application and data after cutback.
- Retain recovery copies until reconciliation is complete.

Never enable simultaneous writes in both locations unless the system supports multi-writer and conflict resolution.

## 12. Backups and Migration

### 12.1. How Backups Support Migration

Backups provide a rollback point before moving workloads. Before migration:

- Back up data and configurations.
- Verify backups completed and can be restored.
- Record application, schema, and runtime versions.
- Check CPU architecture, OS, driver, and storage compatibility.
- Define RPO during the cutover window.
- Prepare a rollback plan and its expiration boundary.

Backups are only one part of a migration plan. Check data transfer, delta sync, DNS, networking, IAM, and the ability to run both environments concurrently.

### 12.2. Cold Migration

Cold migration stops the source workload, copies data, and starts it at the destination.

- Easier to control consistency once writes stop at the source.
- Can simplify data synchronization.
- Downtime depends on data size and transfer speed.

### 12.3. Warm Migration

Warm migration copies data while the source remains active, then syncs final changes and cuts over.

Workflow:

1. Create a baseline copy.
2. Enable replication or delta sync.
3. Monitor lag.
4. Prepare the target environment and run non-production-writing tests.
5. Pause writes or set the source to read-only.
6. Sync the final delta.
7. Verify consistency.
8. Switch traffic/ownership.
9. Monitor and maintain rollback options.

### 12.4. Live Migration

Live migration attempts to move workloads with minimal disruption, potentially leveraging continuous replication, state transfer, or hypervisor/cloud capabilities.

Not every VM, database, or application supports live migration. It may be constrained by directly attached devices, accelerators, storage, networking, or hypervisor differences. Check compatibility matrices and measure actual downtime.

### 12.5. Cutover and Rollback

Before cutover:

- Freeze schema changes or deployments if needed.
- Identify the writable data source.
- Lower DNS TTL ahead of time per plan if using DNS cutover.
- Verify endpoints and certificates in the target environment.
- Prepare a method to shift traffic back.

Rolling back after the target has accepted writes is not as simple as pointing DNS back to the source. You must sync new data from target back to source or accept an approved data loss point. Without reverse replication, rollback can lose transactions created after cutover.

## 13. Testing Recoverability

### 13.1. A Successful Backup Does Not Prove a Successful Restore

A backup job can report success while:

- The backup is missing files or transaction logs.
- Encryption keys are inaccessible.
- The catalog is corrupted.
- Images are incompatible.
- Networking or quotas are insufficient to provision.
- Restore permissions differ from backup permissions.
- The recovery process is missing manual steps.
- The application starts up but data is inconsistent.

Therefore, periodically run restore tests in an isolated environment.

### 13.2. Testing Levels

- **Backup verification:** check jobs, checksums, catalogs, encryption, and metadata.
- **File-level restore:** restore a file or object to verify readability.
- **Volume/database restore:** restore a volume or database to a test environment.
- **Application recovery test:** stand up dependencies and run smoke tests.
- **Full DR exercise:** simulate losing a site or account and recover per the runbook.
- **Failback exercise:** drill syncing and returning to the primary environment.

Validate business data, not just service status.

### 13.3. Scenario-Based Drills

Example scenarios:

- Accidental deletion of a file or object.
- Logical database error or accidentally dropped table.
- Corrupted volume.
- Complete loss of a VM or node.
- Unavailable region or zone.
- Compromised production credentials.
- Ransomware encrypting data and snapshots.
- Lost KMS key or key access permissions.
- Inaccessible backup catalog.
- New application release causing data corruption.

Each drill should record actual RPO/RTO, runbook gaps, missing permissions, missing dependencies, and follow-up improvements.

### 13.4. Safe Testing

Restore into an isolated environment before reintroducing to production, especially when malware or data compromise is suspected. Do not allow recovered systems to automatically connect to production networks before checking images, files, and credentials.

Use appropriate test data, control access permissions, and clean up test environments according to retention policies after the drill.

## 14. Example Backup Design for an API Service

An API service has:

- 6 stateless VMs running the application.
- A managed relational database storing transactions.
- Object storage holding user files.
- A queue processing background tasks.
- A secret manager storing credentials.
- A load balancer and private network.

Business requirements set an illustrative target of 15-minute RPO and 2-hour RTO.

The design may include:

| Component | Protection Scope | Suggested Mechanism |
|---|---|---|
| API VMs | OS/runtime and base config | Golden images, IaC, versioned artifacts |
| Database | Data and transaction logs | PITR/log backups, scheduled backups, restore tests |
| Object storage | Files and metadata | Versioning, replication, or independent backups |
| Queue | Unprocessed messages and consumer state | Sufficient retention, replay, checkpoints |
| Secrets | Secret references, keys, and access | Secret manager, key recovery plan, break-glass |
| Network | Subnets, routes, firewalls, DNS | IaC and versioned config backups |
| Load balancer | Listeners, targets, health checks, cert bindings | IaC and stored configurations |
| Observability | Alerts, dashboards, log routing | IaC/exports and agent configs |

DR workflow:

1. Select a database recovery point within the RPO target.
2. Verify object versions and queue retention.
3. Create the recovery network in the approved account/region.
4. Restore key access, secrets, and IAM.
5. Provision the database and perform PITR restore.
6. Launch VMs from tested images and deploy the matching artifact.
7. Configure queue consumers in paused/non-consuming mode initially.
8. Validate APIs, transactional data, files, and permissions.
9. Cut over traffic via load balancer/DNS.
10. Enable workers, monitor queue lag, and reconcile transactions.

Measure the duration of each step during drills. If database restore takes 90 minutes and other steps take 50 minutes, the design misses the 2-hour RTO; optimize restore size/architecture or adopt an appropriate standby model.

## 15. Optimizing Cost While Meeting RPO/RTO

### 15.1. Backup Cost Drivers

Key factors:

- Data volume and growth rate.
- Backup frequency and number of recovery points.
- Retention and storage classes.
- Cross-region/cross-account copies.
- Data transfer and API requests.
- Restore tests and recovery environments.
- KMS, catalogs, and monitoring.
- Operational and drill costs.

### 15.2. Selecting Storage Classes

Backup data can be tiered:

- Recent recovery points needing fast restores: frequent access tier.
- Medium-term copies: infrequent access storage tier.
- Long-term copies: archive tier with suitable retrieval times and restore costs.

Do not move all backups to the cheapest archive tier if RTO requires recovery within minutes. Account for retrieval times, retrieval fees, minimum storage durations, and decryption capabilities.

### 15.3. Optimizing Scope

- Exclude regenerable caches or scratch data once verified.
- Use IaC and artifact repositories for rebuildable components.
- Use native database backups and log backups instead of raw snapshots when PITR is required.
- Use incremental or deduplication mechanisms where appropriate.
- Set retention per legal and business requirements.
- Audit redundant copies and orphaned snapshots.
- Automatically purge expired data under approved policies.

Do not exclude data from scope purely to cut costs without owner sign-off on regenerability and data loss tolerance.

### 15.4. Optimizing RTO

You can reduce recovery time by:

- Using IaC for fast provisioning.
- Pre-staging images and artifacts.
- Pre-creating recovery networks, quotas, and roles.
- Maintaining warm standby for critical workloads.
- Parallelizing independent steps.
- Using suitable snapshots/replicas.
- Automating verification and cutover.
- Drilling regularly to eliminate unnecessary manual steps.

Increasing automation reduces RTO, but requires strict permission controls, approvals, and trigger safeguards to avoid recovering into the wrong environment.

## 16. Common Mistakes

**Equating RPO with backup schedule.** Running on a schedule does not guarantee a valid recovery point. Measure the age of completed, restorable copies.

**Equating RTO with file restore duration.** RTO also includes decisions, provisioning, dependencies, validation, and traffic cutover.

**Backing up only the VM boot disk.** Databases, data volumes, objects, queues, and secrets may live outside the image.

**Relying solely on replication.** Logical errors, accidental deletions, and ransomware can replicate. Pair it with historical backups and independent retention.

**Keeping backups only in the same account.** Attackers or permission errors can delete both production and backups. Separate failure domains and admin identities.

**Failing to protect encryption keys.** Backups that exist but cannot be decrypted have zero recovery value.

**Ignoring consistency checks.** Snapshotting multiple volumes at different moments may yield an unrecoverable database.

**Never testing restores.** A successful backup job does not prove data, catalogs, keys, and runbooks actually work.

**Overlooking dependencies.** Having compute and a database without DNS, IAM, certificates, secrets, or quotas still prevents the application from running.

**Lacking a failback plan.** Failing over to a DR site may succeed, while returning to the primary site causes split-brain or loss of new data.

**Setting retention too short or too long.** Too short eliminates clean rollback points; too long drives up costs and sensitive data exposure.

**Never measuring RPO/RTO in drills.** Documented targets may differ dramatically from actual recovery times.

## 17. Checklist for Building Backup and Recovery Scope

### Objectives and Scope

- [ ] Have a BIA and owner for each workload.
- [ ] Approved RPO/RTO by criticality tier.
- [ ] Identified persistent, ephemeral, and regenerable data.
- [ ] Mapped dependencies across compute, storage, database, network, IAM, secrets, and keys.
- [ ] Defined recovery points and criteria for considering a service recovered.

### Backups and Copy Protection

- [ ] Selected appropriate backups, snapshots, log backups, PITR, or replication.
- [ ] Verified application consistency and multi-volume consistency.
- [ ] Configured schedules, retention, and lifecycle policies.
- [ ] Preserved catalogs and metadata required for restores.
- [ ] Separated backups from the production failure domain.
- [ ] Enabled immutable retention or deletion protection where appropriate.
- [ ] Protected credentials, KMS keys, and recovery permissions.
- [ ] Monitored failed jobs, replication lag, and recovery point age.

### Recovery and Drills

- [ ] Component-by-component restore runbooks and dependency order.
- [ ] Versioned IaC, images, artifacts, and configurations.
- [ ] Verified quotas, networking, and permissions in the recovery environment.
- [ ] Tested restoring files, volumes, databases, and applications.
- [ ] Measured actual RPO/RTO and compared against targets.
- [ ] Drilled zone/region loss, accidental deletion, and ransomware scenarios.
- [ ] Established cutover, failback, and data reconciliation plans.
- [ ] Documented findings and updated runbooks after each drill.

## 18. Key Takeaways

- **RPO** defines the maximum acceptable data loss; **RTO** defines the maximum time to restore service.
- Actual RPO is based on the newest valid recovery point, not merely the backup schedule.
- RTO encompasses detection, decision-making, provisioning, restoration, validation, and traffic cutover.
- Backup scope must cover data, artifacts, configurations, and dependencies required to rebuild the workload.
- VM images, container images, and serverless code do not automatically contain full application state.
- Snapshots, backups, replication, and PITR have distinct characteristics; replication does not replace independent backups.
- Ensure application consistency, log chains, encryption keys, and backup catalogs.
- Isolate copies from the production failure domain and protect them with separate permissions and immutable retention where appropriate.
- Restore tests and DR exercises provide the strongest evidence of recoverability.
- Migration requires backups, delta synchronization, cutover, and a controlled failback plan.

## Glossary

| Term | Meaning |
|---|---|
| RPO | Recovery Point Objective, the maximum acceptable data loss. |
| RTO | Recovery Time Objective, the maximum time allowed to restore a service. |
| Recovery point | A data state at a specific point in time usable for restoration. |
| Backup | A copy of data stored for recovery when an incident occurs. |
| Snapshot | A point-in-time capture of a volume or resource state. |
| Replication | Copying data to a replica or another location. |
| PITR | Point-in-Time Recovery, restoring data to a specific moment in time. |
| Transaction log | A database log of changes used to recover or replay transactions. |
| Crash-consistent | A consistency state similar to an abrupt system shutdown. |
| Application-consistent | A backup state coordinated with the application to guarantee valid data. |
| Retention | The duration or policy for keeping backup copies. |
| Immutable backup | A backup copy protected against modification or deletion during a lock period. |
| GFS | Grandfather-Father-Son, a multi-tiered retention model across hourly/daily/weekly/monthly copies. |
| BIA | Business Impact Analysis, evaluating the business impact of service disruptions. |
| Disaster Recovery (DR) | Processes and architecture for recovering after a disaster. |
| Pilot light | A DR model keeping minimal core components ready and scaling out during an incident. |
| Warm standby | A scaled-down recovery environment running and ready to scale up when needed. |
| Active-active | Multiple sites operating concurrently to serve a workload. |
| Failover | Shifting a workload to alternative resources or a secondary site. |
| Failback | Returning a workload back to the primary environment after recovery. |
| Cutover | The point at which traffic or write authority shifts from source to target. |
| Checkpoint | Saved progress state allowing processing to resume after interruption. |
| Recovery catalog | Metadata describing backup copies and how to restore them. |
| Failure domain | The scope of resources that can be impacted together by a single fault or event. |
| WORM | Write Once, Read Many, a storage mechanism preventing modification under specified conditions. |
