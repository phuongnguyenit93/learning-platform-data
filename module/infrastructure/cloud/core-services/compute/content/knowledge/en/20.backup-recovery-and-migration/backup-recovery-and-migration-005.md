# Copying Images and Data for Recovery in Another Region

When a cloud region experiences a widespread outage, workloads may become unreachable even if the VMs and applications inside that region remain undamaged. To maintain service continuity, an organization needs the ability to provision compute in a backup region, connect to recoverable data, and shift users to the new environment. This requires preparing **machine images**, **data**, **infrastructure configurations**, **identities**, **encryption keys**, and **region-switching procedures**.

Copying an image to another region lets you launch VMs with matching operating systems, runtimes, and base software. However, an image does not necessarily hold the latest application data, databases, or user files. Consequently, multi-region DR must pair images with backups, replication, and data recovery testing. An image that boots cleanly still does not prove the application can serve transactions properly.

Within the scope of CLOUD_CORE_SERVICES_COMPUTE, this lesson focuses on recovering compute workloads in another region: producing usable images at the backup site, transferring data there within RPO/RTO targets, recreating networking and identities, and executing controlled failover and failback.

After this lesson, you will be able to:

- Distinguish machine images, snapshots, data backups, and replication.
- Plan the copying of images and dependent components to a backup region.
- Choose data protection methods aligned with RPO, RTO, and consistency.
- Verify encryption keys, IAM, networking, quotas, licenses, and dependencies in the target region.
- Build restore, failover, and failback sequences.
- Test VM bootability and post-recovery business integrity.

## 1. Multi-Region DR and Recovery Objectives

Disaster Recovery (DR) is the set of architecture, data, processes, and operational capabilities that restore service after a severe disruption. In the cloud, a backup region is an independent geographic area capable of hosting compute, storage, networking, and supporting services required to run the workload.

### RPO and RTO

Two foundational targets:

- **RPO (Recovery Point Objective):** the maximum acceptable data loss, typically expressed as the time interval from the incident back to the recoverable data point.
- **RTO (Recovery Time Objective):** the maximum target duration to restore service to an acceptable operating level.

For example, a service sets an RPO of 5 minutes and an RTO of 60 minutes. This means the recovered data point must be no older than 5 minutes under the defined target, and the service must return to serving status within 60 minutes of incident onset per the organization's measurement method.

RPO/RTO are targets to engineer and validate—not automatic provider guarantees. If snapshots run every 24 hours, you cannot claim a 5-minute RPO for data protected solely by those snapshots. If standing up networking, requesting quotas, provisioning keys, restoring databases, and testing the app takes 3 hours, you cannot claim a 60-minute RTO without automating or pre-staging those steps.

### Example Target Classification

| Workload Type | Illustrative RPO | Illustrative RTO | Potentially Suitable Strategy |
|---|---:|---:|---|
| Dev/test environment | 24 hours | 1 day | Scheduled backups, on-demand image copies |
| Low-criticality internal API | 1 hour | 4 hours | Periodic backups/replication, warm recovery |
| Critical transactional service | 5 minutes | 1 hour | Database replication, pre-staged images in DR region, IaC, and warm standby |
| High-continuity system | Near zero or by design | A few minutes | Multi-region active/active or active/passive with replication and automated failover |

These numbers merely illustrate selection trade-offs. Actual targets must reflect business impact, cost, service capabilities, and drill results.

## 2. Distinguishing Images, Snapshots, Backups, and Replication

These concepts relate closely but do not replace one another.

| Component | Typical Contents | Purpose | What Not to Assume |
|---|---|---|---|
| Machine image | OS, boot volume, software, base config, and VM launch metadata | Create new VMs with an equivalent baseline | Does not contain latest app data or every attached disk by default |
| Disk snapshot | Block storage state at a point in time | Create new disks or restore volumes | A single snapshot may be inconsistent with an actively writing database |
| Application/database backup | Logical data or application-consistent copy | Recover data and transactions | Does not automatically create networking, compute, identity, or endpoints |
| Replication | Data changes shipped to a remote copy | Reduce recovery point lag | Replication can propagate deletions or corruption as well |
| Infrastructure as Code | Declarations for VMs, networks, roles, load balancers, and policies | Recreate environments | Does not hold runtime data unless specifically designed |
| Configuration/secret backup | Configs, parameters, and secrets per policy | Reconfigure applications securely | Never export plaintext secrets into repositories or images |

A complete DR plan typically uses several mechanisms together: image copies to launch compute, database backups/replication to recover data, object replication for files, IaC to stand up infrastructure, and secret/key management for access.

### Why Is an Image Not a Complete Backup?

An image captures machine state at build time. If an image was built last week, the application may launch with an outdated version or miss newer configurations. Data generated after that timestamp does not magically appear in the image.

Baking databases or business files into images also introduces risks: images grow bulky, embedded data stales quickly, secrets or sensitive data may leak, and consistency becomes hard to control. Best practice is keeping images reproducible while protecting business data with dedicated backup/replication mechanisms.

## 3. Selecting a Backup Region

Choose a backup region based on technical, business, and governance requirements.

Criteria to evaluate:

- Geographic distance and correlated risk with the primary region.
- Inter-region latency and its impact on replication.
- Availability of VM types, CPU architectures, GPUs, disk types, and network features.
- Quota headroom and compute provisioning capacity during a regional outage.
- Availability of database, object storage, queue, key management, and monitoring services.
- Data residency, privacy, industry regulations, and permissible storage locations.
- Costs for storing copies, replication, cross-region traffic, and standby compute.
- Operational readiness of teams in the target region, including access and on-call support.
- Time required to update DNS, certificates, firewalls, and endpoints.

Do not pick a region solely for proximity or low pricing. The target region must offer sufficient services and capacity for the workloads requiring recovery. For specialized needs like GPUs, software licenses, or specific instance families, verify provisioning availability beforehand.

### Active/Passive vs. Active/Active

| Model | How It Works | Advantages | Cost and Complexity |
|---|---|---|---|
| Backup and restore | Backups/images reside in another region; compute is built on incident | Low ongoing cost | Longer RTO; many restore steps during incident |
| Pilot light | Core foundational components and data stay prepared | Faster recovery than backups alone | Requires automated compute scale-out and dependency checks |
| Warm standby | Backup region runs a scaled-down ready version | Scales up faster | Ongoing compute and replication costs |
| Hot standby/active-passive | Near-full stack in secondary region; primary serves live traffic | Lower RTO if failover is drilled | High cost; requires synchronization and split-brain control |
| Active/active | Two or more regions serve traffic concurrently | Continues serving if one region fails | High complexity in data, consistency, routing, and operations |

Not every application needs active/active. Choose the model that meets RPO/RTO at a cost and operational complexity the organization can sustain.

## 4. Preparing Machine Images for Copying

Images serve as the input to launch VMs in the target region. A DR-ready image should be explicitly versioned, free of sensitive runtime data, and bootable in another environment.

### Image Contents

An image typically includes:

- Operating system and security patches.
- Required kernels, drivers, and agents.
- Runtimes such as Java, .NET, Python, or web servers.
- Versioned application code or artifacts.
- Non-secret default configurations.
- Bootstrap scripts and health check hooks.
- Monitoring, backup, and endpoint protection agents if required.

Never embed private keys, database passwords, long-lived access keys, or user data inside images. Fetch those at runtime via workload identity and a secret manager.

### Immutable Images and Versioning

Every image should carry an immutable identifier or explicit version. Never overwrite an image actively used in production without history and rollback capability.

Metadata should record:

- Image ID and version.
- OS version, architecture, and patch baseline.
- Application/artifact version.
- Build date and build pipeline.
- Source region and copied regions.
- Encryption key or key reference.
- Boot test, vulnerability scan, and compliance results.
- Approving person or pipeline.

Images must be tested in the target region because differences in instance families, drivers, firmware, boot modes, architectures, or metadata services can prevent booting as expected.

### Image Copying and Accompanying Components

Cloud provider copy workflows copy images, underlying snapshots, or metadata with provider-specific semantics. Check:

- Which disks belong to the image vs. separate data disks.
- Whether copying preserves encryption or requires specifying a target key.
- Whether the image depends on a customer-managed key in the source region.
- Whether the image works with instance families and architectures in the target region.
- Whether separate licenses or subscriptions apply.
- Whether marketplace images or licensed images are permitted for cross-region copying and use.
- Whether metadata, boot config, or agents need post-copy updates.

Never assume a source-region image ID works directly in the target region. Most platforms create a new image resource in the target region.

## 5. Procedure for Copying Images to Another Region

A controlled workflow typically includes:

1. Select an approved image and confirm the version required for recovery.
2. Verify the image boots, matches OS/architecture, and contains no secrets.
3. Identify dependent disk snapshots and encryption keys.
4. Grant the pipeline or operator permissions to copy the image.
5. Prepare the encryption key and usage policies in the target region.
6. Initiate the copy/replication task via the cloud service.
7. Monitor copy status until completion.
8. Verify the image resource and matching snapshots exist in the target region.
9. Launch a test VM from the target image inside an isolated subnet.
10. Verify boot, drivers, agents, bootstrap, identity, and readiness.
11. Record the target image ID/version in inventory or IaC variables.
12. Repeat on schedule whenever new images or critical patches release.

### Copy Flow Diagram

~~~mermaid
flowchart TD
    A[Tested image in primary region] --> B[Check metadata, disks, and encryption]
    B --> C[Prepare permissions and key in target region]
    C --> D[Copy image and dependent snapshots]
    D --> E{Copy completed?}
    E -- No --> F[Check quotas, keys, policies, and task errors]
    F --> D
    E -- Yes --> G[Verify image in target region]
    G --> H[Launch test VM in isolated network]
    H --> I{Boot and readiness succeeded?}
    I -- No --> J[Investigate compatibility and bootstrap]
    I -- Yes --> K[Register image version in DR inventory]
~~~

Copy completion only confirms the platform finished copying bits. It does not prove the application can restore data or serve transactions.

## 6. Encryption Keys and Cross-Region Access Permissions

A common reason images or snapshots fail to work in the target region is missing keys or mismatched policies.

### Encryption Keys

If the source volume/image is encrypted with a customer-managed key, determine how the service supports cross-region copying:

- Must a separate key be created in the target region?
- Must the copy be re-encrypted with the target key?
- Which principal is permitted to decrypt at the source and encrypt at the target?
- Is the key disabled, pending deletion, or expired?
- Does the policy allow the copy service to use keys in both regions?
- Are key rotation and recovery procedures documented?

A key from one region often cannot be used directly in another region. Some services offer multi-region keys or key replication, but semantics vary by provider. Verify the exact key type and service rules.

### Key Protection Principles

- Separate key administration permissions from VM administration permissions where possible.
- Grant decrypt/encrypt permissions only to required principals and services.
- Never export key material or secrets to unprotected files.
- Enable audit logging for key operations.
- Ensure key backup/recovery satisfies organizational requirements.
- Never delete source keys until copies and restore capabilities in the target region are verified.
- Test restores whenever key rotation or key policies change.

### IAM and Service Identities

The DR pipeline needs permissions to read the source image, copy snapshots, use keys, create the target image, and test VMs. Grant a dedicated narrowly scoped role rather than using Owner/Administrator accounts across the workflow.

Beyond copy permissions, prepare runtime workload permissions in the target region: new VMs must fetch secrets, read configs, write logs, access databases/queues/object storage, and register health checks per their role.

## 7. Replicating and Protecting Application Data

Images and data have distinct schedules, consistency needs, and churn rates. Design protection per data type based on RPO/RTO.

### Data Protection Methods

| Method | How It Works | Potential RPO | Notes |
|---|---|---|---|
| Scheduled backup | Captures copies on schedule | Depends on backup interval | Simple, though changes after last backup may be lost |
| Cross-region snapshot copy | Copies snapshots to another region | Depends on snapshot cadence and copy delay | Requires app consistency and target-region key |
| Continuous/asynchronous replication | Ships changes continuously with some delay | Can be low, depending on replication lag | Unreplicated writes may be lost |
| Synchronous replication | Confirms writes only per synchronous copy rules | Can approach zero within guaranteed scope | Increases latency and depends on inter-region links; not universally supported |
| Object replication | Copies objects and versions to another bucket/region | Depends on replication delay and versioning | Must handle delete markers, metadata, retention, and object lock |
| Native database replication | Engine or managed service replicates transactions/logs | Per engine semantics and lag | Must handle promotion, consistency, failover, and split-brain |

Actual RPO must account for copy delay, snapshot intervals, fault detection time, and copy accessibility. "Replication enabled" does not mean lag is always zero.

### Databases

Databases usually determine RPO. Options include:

- Full and incremental/differential backups.
- Transaction log or write-ahead log archiving.
- Point-in-time recovery.
- Read replicas or cross-region replicas.
- Native database replication and promotion.
- Application-consistent backups.

Determine whether a database replica can be promoted in the target region or is strictly read-only. With async replication, inspect replication lag and determine the exact last applied data point before promoting.

For self-managed databases on VMs, protect both data disks and log disks, ensure consistent snapshots, and test recovery. Crash-consistent snapshots may require database crash recovery on boot; application-consistent backups usually require quiescing or native database backup tools.

### Files and Objects

For object storage, check:

- Versioning and how overwritten or deleted objects are recovered.
- Replication rules and replication status.
- Whether delete markers are replicated.
- Whether object locks/retention carry over to the target.
- Whether metadata, tags, ACLs, and encryption are preserved.
- Bucket policies and IAM in the target region.
- Whether replication covers existing objects or only new objects written after enabling the rule.

For shared filesystems, verify replication, snapshots, mount targets, protocols, ACLs, and consistency. Never assume a source-region filesystem endpoint can simply be mounted from the target region.

### Queues and Workflows

Queues may hold in-flight messages, so determine whether messages replicate cross-region or if new queues must be stood up and replayed from event logs/outboxes. Understand ordering, deduplication, visibility timeout, redelivery, and dead-letter queue semantics.

If queues are not replicated, databases/outboxes or event archives can serve as replay sources. Event replay must be idempotent to avoid duplicate side effects.

## 8. Ensuring Consistency Between Images and Data

An image built at 02:00 and a database snapshot taken at 02:30 may contain application/config versions mismatched with the schema or data. DR must know whether these versions are compatible.

### Crash-Consistent vs. Application-Consistent

- **Crash-consistent:** resembles data state after sudden power loss. Filesystems or databases may need journal/log recovery.
- **Application-consistent:** the application is quiesced or uses backup-aware hooks to capture a consistent copy across related files/data.

For multi-component systems, snapshotting individual volumes at different timestamps can produce an inconsistent state. Use snapshot groups, backup coordinators, or proper write-pause procedures.

### Version Synchronization

DR inventory should track:

- Image version and build timestamp.
- Application artifact version.
- Database backup/snapshot ID and timestamp.
- Replication lag or applied transaction sequence.
- Object replication status.
- Config version and schema version.
- Encryption key ID/version.
- IaC release/commit used to provision the environment.

When restoring, choose a compatible combination of image, config, schema, and data backup. Never blindly pick the "newest" copy of each piece if they were not captured around a compatible recovery point.

### Example

Application version 2.4 requires at least database schema 18. If the target region only has a database backup at schema 17, launching image 2.4 may crash or corrupt data. You may need an image compatible with schema 17, a planned schema migration, or a verified newer database restore.

## 9. Recreating Networking and Dependencies in the Target Region

A VM that boots cleanly still cannot serve requests without networking and dependencies. Pre-stage or define:

- VPC/VNet, subnets, route tables, and network addressing plan.
- Security groups/firewall rules and network ACLs.
- Private DNS zones, service discovery, and endpoints.
- NAT/egress gateways, internet gateways, or private connectivity.
- Load balancers, target pools, and health checks.
- VPNs, dedicated interconnects, or on-premises links.
- Certificates, TLS trust chains, and hostnames.
- Database endpoints, caches, queues, object storage, and secret managers.
- Logging, metrics, tracing, alerting, and audit pipelines.

### IP Addresses and DNS

Never assume a VM's private IP in the primary region will be available in the target region. Use DNS/service discovery or load balancer endpoints to decouple applications from instance IPs.

During failover, update DNS, traffic managers, or global load balancers per procedure. Low TTLs accelerate switching but do not guarantee every resolver or client updates immediately; DNS caches and persistent connections may stick to old endpoints.

### Egress and Partner Connectivity

If partners allowlist source public IPs, the target region needs pre-registered stable NAT/egress IPs. Without this preparation, the app may start yet fail to reach payment gateways, email providers, or partner APIs.

### Capacity and Quotas

Check quotas before an incident:

- vCPUs, VM families, and instance counts.
- GPUs or accelerators if required by the workload.
- Disk capacity, IOPS, and throughput.
- Public IPs, NICs, load balancers, and NAT gateways.
- Database instance/storage/connection quotas.
- Queue, object storage, and API request quotas.
- Certificate, key, and secret limits.

Having quota on paper does not guarantee physical capacity during a major regional event. For critical workloads, consider capacity reservations, warm standby, or tested fallback instance families.

## 10. Compute Recovery Plan in the Target Region

A DR runbook should define build order according to dependencies.

Conceptual order:

1. Confirm the incident and decide to activate DR.
2. Select an RPO-compliant valid recovery point.
3. Verify images, backups, keys, and permissions in the target region.
4. Provision networking, routes, firewalls, internal DNS, and secure links.
5. Restore the database or promote the replica per runbook.
6. Restore required object/file stores and queues/workflows.
7. Launch VMs/instances from copied images or deploy containers from the target registry.
8. Bootstrap configs, secrets, identities, and service discovery.
9. Run compatible migrations if needed.
10. Verify health, readiness, dependencies, and representative transactions.
11. Register backends into load balancers or traffic managers.
12. Shift user traffic and monitor SLOs.

Never route public traffic to VMs before databases and critical dependencies are ready. If the API starts ahead of the database, readiness probes must withhold traffic until serving is safe.

### Recovery Diagram

~~~mermaid
flowchart TD
    A[Detect primary region outage] --> B[Incident commander approves DR activation]
    B --> C[Select recovery point per RPO]
    C --> D[Verify images, backups, keys, and permissions]
    D --> E[Build network and security boundary in target region]
    E --> F[Restore or promote database]
    F --> G[Restore objects, files, queues, and config]
    G --> H[Launch compute from copied image]
    H --> I[Bootstrap identity, secrets, and telemetry]
    I --> J[Health/readiness and business checks]
    J --> K{Meets serving criteria?}
    K -- No --> L[Keep traffic safe, investigate]
    L --> J
    K -- Yes --> M[Shift traffic to target region]
    M --> N[Monitor SLOs and stabilize service]
~~~

## 11. Failover and Failback

### Failover

Failover shifts operations from the primary region to the backup region. It is a high-impact operational decision requiring clear ownership and criteria.

Before switching:

- Confirm the primary region is genuinely unable to serve rather than a single dependency failing.
- Prevent both regions from writing to the same dataset unless the architecture supports active/active.
- Select the replica/database recovery point and verify replication lag.
- Fence or isolate the old writer if split-brain is possible.
- Verify target-region permissions and keys.
- Confirm DNS/global traffic switching and rollback methods.

During switching:

- Promote databases/replicas in sequence.
- Start compute and check readiness.
- Shift traffic gradually or by percentage if supported.
- Monitor errors, latency, queues, transactions, and data.
- Log cutover timestamps, recovery points, and decisions.

### Split-Brain

Split-brain occurs when two sites both believe they are primary and both accept writes. This causes conflicts or data loss when reconciling.

Preventive measures:

- Fencing or mechanisms enforcing single-writer authority.
- Quorum/consensus where supported by the data system.
- Explicit runbooks stating who is authorized to promote.
- Blocking or isolating the old writer before activating the new one.
- Never auto-promote based solely on network timeouts without understanding failure modes.

### Failback

Failback returns service from the backup region back to the primary region after the outage resolves. Never simply flip traffic back to the old region.

Typical sequence:

1. Confirm the primary region is healthy and has sufficient capacity.
2. Verify image, application, schema, and configuration versions.
3. Establish reverse replication from the active region back to the recovering primary.
4. Synchronize data and track lag down to an acceptable threshold.
5. Test compute and dependencies in the primary region.
6. Choose a traffic cutover window, drain requests, and prevent concurrent writes.
7. Switch writer/traffic per runbook.
8. Verify data, SLOs, and health.
9. Return the backup region to DR standby and resume forward replication.

Failback can be harder than failover because new data was generated in the backup region. Plan reverse synchronization rather than overwriting new writes with old snapshots.

## 12. Automating with Infrastructure as Code and Pipelines

IaC provisions networks, security groups, load balancers, VM templates, roles, and policies in a reviewable way. Pipelines can automate image copying, status checks, inventory updates, and boot tests in the target region.

### Separating Artifacts and Region-Specific Configs

Keep parameters like region, subnet ID, key ID, instance family, and endpoints in environment configs. Never hardcode primary-region resource IDs inside images.

Conceptual DR manifest example:

~~~yaml
disaster_recovery:
  primary_region: region-a
  recovery_region: region-b
  compute:
    image_version: orders-api-2.4.1
    instance_family: general-purpose
    desired_capacity: 3
  data:
    database:
      recovery_method: cross_region_replica
      max_replication_lag_seconds: 300
    object_storage:
      replication_enabled: true
  security:
    encryption_key_reference: dr-region-b-key
    workload_identity: orders-api-dr
  validation:
    readiness_path: /health/ready
    smoke_test: create-and-read-order
~~~

This is an illustrative example, not a provider-specific schema. Recovery points and replica lag must come from actual runtime telemetry; never assume lag stays below threshold simply because the config specifies a value.

### Image Pipeline Steps

- Build the image in a trusted pipeline.
- Scan for vulnerabilities and verify baselines.
- Record version, checksum/digest, and provenance.
- Copy the image/snapshot to the target region.
- Apply proper encryption keys and policies.
- Launch a test VM in an isolated subnet.
- Run OS, agent, bootstrap, and application smoke tests.
- Record results and image ID in the DR inventory.
- Alert if copying or testing fails.

Pipelines must not automatically shift production traffic merely because an image copy succeeded. Failover requires data checks, dependency checks, and operational approval.

## 13. Protecting Backups Against Accidental Deletion and Ransomware

Copying backups to another region is insufficient if the same principal can delete both originals and copies.

Measures to consider:

- Separate backup accounts/projects or admin roles from workload accounts where appropriate.
- Use immutable backups, retention locks, or object locks if supported.
- Enable versioning and retention policies for critical objects.
- Restrict delete permissions on snapshots, images, backup vaults, and encryption keys.
- Require MFA or approvals for destructive operations.
- Audit backup, restore, key, and policy actions.
- Maintain offline or isolated copies when required by the threat model.
- Test restoring from isolated backups.
- Maintain key recovery procedures separately; encrypted backups without keys may become unusable.

Replication can propagate ransomware-encrypted files or valid deletion actions. Combine versioning, retention, point-in-time recovery, and immutable backups to preserve clean recovery points.

## 14. Testing Recoverability in Another Region

A DR plan is trustworthy only after testing. An image listed in inventory does not prove it boots; a backup marked completed does not prove data can be restored.

### Testing Levels

- **Image validation:** launch a test VM from the target image; verify boot, drivers, agents, and bootstrap.
- **Data restore test:** restore databases, objects, and files into an isolated environment; run integrity checks and business queries.
- **Dependency test:** test DNS, secret manager, keys, networking, endpoints, and runtime permissions.
- **Application recovery test:** run smoke tests, synthetic transactions, and health checks.
- **Failover exercise:** shift traffic per approved scenarios; measure actual RTO and RPO.
- **Failback exercise:** reverse-sync data and return to the primary region.
- **Ransomware recovery exercise:** confirm ability to select a clean backup predating compromise.

### Testing Matrix

| Scenario | Check | Pass Criteria |
|---|---|---|
| Copy image to target region | Image and snapshots complete, key valid | Test VM boots with exact expected version |
| Restore database | Backup/replica recoverable | Integrity checks and representative queries pass |
| Slow object replication | Check newest objects and replication status | Exact missing data is known rather than assuming sync |
| Missing IAM permissions | Run bootstrap using DR workload identity | Only needed permissions granted and secret retrieval succeeds |
| Disabled key | Test restore per key recovery procedure | Detected early and valid key usage restored |
| Primary region lost | Run tabletop or failover test | Service stands up within RTO and data within RPO |
| New backend lacks old IP | Test DNS/service discovery | Clients reach new endpoints successfully |
| Failback | Reverse sync and traffic switch | Zero split-brain, zero loss of DR-generated data |

### Measuring Actual RPO/RTO

Record timestamps:

- T0: incident starts or is detected.
- T1: decision made to activate DR.
- T2: recovery point selected and data ready.
- T3: compute/network/dependencies ready.
- T4: smoke tests and business validation pass.
- T5: traffic shifted and SLOs stabilized.

Actual RTO must follow organizational definitions, usually measured from T0 until the service meets operational criteria. Actual RPO measures the gap between the last recoverable data point and the incident timestamp. Document calculation rules so exercises remain comparable over time.

## 15. Example: Recovering an API and Database in Region B

An order system runs in region A:

- Three API VMs behind a load balancer.
- Managed database with a replica in region B.
- Object storage holding invoice images and attachments, with replication enabled.
- API image copied to region B after every release.
- IaC defining networks, subnets, firewalls, roles, and load balancers.
- Secrets managed via secret manager; separate keys per region.

Assumed targets: 5-minute RPO, 60-minute RTO.

### Before the Incident

- Image version 2.4.1 copied and boot-tested in region B.
- Database replica monitored for replication lag with alerts above 5 minutes.
- Object replication status tracked.
- Quotas for VMs, disks, IPs, and load balancers verified in region B.
- DNS/traffic manager endpoint cutover procedure ready.
- DR secrets and keys accessible from the region B workload identity.
- Runbook approved with smoke tests defined.

### When Region A Fails

1. Incident commander confirms DR activation.
2. Check latest replication lag and choose recovery point.
3. Fence the writer in region A if possible or confirm the old site cannot accept writes.
4. Promote the database replica in region B per runbook.
5. Verify required objects replicated; list any missing objects if applicable.
6. Provision network and load balancer via IaC.
7. Launch three API VMs from image 2.4.1.
8. Bootstrap configs, secrets, identities, and telemetry.
9. Verify database connectivity, object access, and readiness.
10. Test creating orders, reading orders, and downloading invoices.
11. Shift traffic via DNS/global routing.
12. Monitor error rates, latency, transaction counts, and replication.

If newest objects have not finished replicating, do not claim full data completeness. Temporarily restrict object-dependent features, recover from an alternate backup, or communicate status per business procedure.

### After Service Stabilizes

- Record actual RTO/RPO.
- Audit transactions processed during cutover.
- Establish replication from region B to a secondary backup or prepare reverse failback.
- Review alerts, capacity, and costs.
- Return region A to primary only after data is synchronized and failback is tested.

## 16. Cross-Region Image and Data Copy Checklist

### Images and Compute

- [ ] Images have clear versions, provenance, and security baselines.
- [ ] Images contain no secrets or sensitive runtime data.
- [ ] Identified disks/snapshots inside the image vs. separate data disks.
- [ ] Image copied to the target region with a local ID/version.
- [ ] Test VM boots cleanly from the target image.
- [ ] Instance family, architecture, drivers, licenses, and quotas verified.
- [ ] Bootstrap, agents, and application readiness work.

### Data

- [ ] RPO defined for each data type.
- [ ] Database backups/replicas have observable recovery points and lag.
- [ ] Backups use appropriate consistency and pass restore tests.
- [ ] Object/file replication, versioning, delete markers, and retention are understood.
- [ ] Queues, events, outboxes, and workflows have recovery plans.
- [ ] Encryption keys in the target region are usable.
- [ ] Immutable/isolated backup sources exist if required by the threat model.

### Networking, Identity, and Dependencies

- [ ] VPC/VNet, subnets, routes, firewalls, and DNS provisioned.
- [ ] Load balancers, health checks, and traffic managers configured.
- [ ] Workload identities and IAM roles in the target region follow least privilege.
- [ ] Secret managers, certificates, KMS/key services, and endpoints are reachable.
- [ ] NAT/egress IPs and partner allowlists are ready.
- [ ] Quotas/capacity verified for VMs, storage, IPs, LBs, and dependencies.
- [ ] Logging, monitoring, tracing, and auditing active in the target region.

### Failover, Failback, and Testing

- [ ] Runbooks, incident commander, owners, and DR activation criteria exist.
- [ ] Mechanisms prevent split-brain or dual writers.
- [ ] Recovery sequence for database, objects, compute, and traffic is defined.
- [ ] Smoke tests validate transactions and data integrity.
- [ ] RTO/RPO measured via drills.
- [ ] Failback plan covers reverse sync and safe writer/traffic switching.
- [ ] Backups and images are tested regularly, not just checked for copy status.
- [ ] Delete permissions for backups/keys are separated and audited.

## 17. Common Mistakes

**Assuming copying an image equals having DR.** Images only launch compute. Databases, objects, queues, networks, identities, keys, and DNS still require preparation.

**Copying snapshots without checking consistency.** Snapshots of actively writing databases may require crash recovery or diverge across volumes. Use backup-aware tools and test restores.

**Forgetting encryption keys in the target region.** Snapshots may exist yet fail to decrypt or create volumes. Check key policies and perform actual restore tests.

**Enabling replication without monitoring lag.** Replicas may lag past RPO or miss recent objects. Monitor replication status and determine actual recovery points.

**Using the same admin credentials for both regions.** A compromised account can delete both primaries and backups. Separate permissions and protect backups.

**Overlooking quotas and capacity.** The target region has the image but cannot provision the instance family, GPUs, IPs, or storage. Verify ahead or test fallback resource types.

**Shifting traffic before databases are ready.** Requests may fail writes or corrupt state. Use readiness probes and smoke tests before admitting traffic.

**Failing to fence the old region.** When networking recovers, both regions could write simultaneously. Enforce single-writer safeguards and split-brain runbooks.

**Failing back by simply turning the old region back on.** Newer data may exist only in the backup region. Reverse-sync, check consistency, and switch writers in a controlled sequence.

**Only running tabletop drills.** Tabletop reviews miss image boot bugs, key permissions, quotas, DNS issues, and database restore failures. Execute technical drills in isolated environments.

## 18. Self-Check

1. How does a machine image differ from a disk snapshot, database backup, and replication?
2. Why is copying an image to another region insufficient to recover an application that uses a database and object storage?
3. How do RPO and RTO differ? How does backup frequency affect RPO?
4. Why must images and database backups be checked for version compatibility?
5. When an image is encrypted with a customer-managed key, what must be prepared in the target region?
6. Distinguish crash-consistent and application-consistent snapshots.
7. How can async replication cause data loss when promoting a replica?
8. Why must the old writer be fenced before opening writes in the backup region?
9. Which networking, IAM, quota, and dependency checks are required before failover?
10. How does failback differ from failover once new data has been generated in the backup region?
11. How do you measure actual RPO/RTO during a drill?
12. Design a recovery sequence for a stateless API, database, and object storage in another region.

Multi-region recoverability must be engineered as a complete system: images that rebuild compute, data with valid recovery points, keys and identities enabling secure access, recreatable networking and dependencies, and clearly ordered failover/failback procedures. When components are versioned, automated, and tested regularly, an organization knows precisely what it can recover, the maximum data at risk, and how long it takes to restore service.
