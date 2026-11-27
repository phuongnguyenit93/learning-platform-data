# Designing VM, Disk, and File Data Recovery

## 1. Purpose of recovery design

A backup is useful only if you can locate the right recovery point, rebuild resources, verify data, and return the service to an operational state. The job does not end when a backup command returns success.

On Google Cloud, distinguish three recovery units:

- **VM:** Compute Engine instance, boot disk, data disks, machine type, operating system, networking, IAM, service account, startup scripts, and dependencies.
- **Disk:** Persistent Disk or Hyperdisk holding block data. It can be restored from a snapshot/backup to create a new disk, though the application is not guaranteed to be consistent.
- **File data:** files or directories inside a VM filesystem, Filestore/NFS share, or Cloud Storage objects. Recovering a single file can differ completely from recovering an entire file share.

A deleted VM cannot rebuild itself solely from a data disk snapshot. An accidentally deleted file does not necessarily require restoring an entire VM. A region outage requires networking, DNS, KMS, and quotas—not merely a data copy.

In the **CLOUD_PROVIDERS_GCP** module, this lesson applies Compute Engine, VPC, IAM, Cloud Storage, Filestore, Infrastructure as Code, reliability monitoring, and cost optimization to create a measurable and verifiable recovery design.

## 2. Core terms: RPO, RTO, and recovery point

### 2.1. RPO: acceptable data loss

**Recovery Point Objective (RPO)** is the maximum duration of data loss an organization tolerates during an incident. For example:

- A daily published document directory might have a 24-hour RPO.
- A data disk continuously processing records might have a 4-hour RPO.
- A transactional database might demand a 15-minute RPO or lower.

These are **illustrative targets**, not automatic guarantees from Google Cloud. If snapshots run hourly yet the last three jobs failed, the nearest recovery point could be hours old. Actual RPO must be measured by the timestamp of data that can genuinely be recovered.

An hourly disk snapshot schedule does not automatically satisfy a 15-minute RPO. For targets shorter than snapshot frequency, you need data-layer mechanisms such as replication, transaction logs, or appropriate point-in-time recovery.

### 2.2. RTO: system downtime duration

**Recovery Time Objective (RTO)** is the target time to make the service usable again. Actual RTO includes:

~~~text
Incident detection
 + decision to activate DR
 + identifying a clean recovery point
 + recreating VM/disk/file share
 + restoring network, IAM, KMS, DNS, and dependencies
 + verifying OS, filesystem, data, and application
 + shifting traffic and testing business flows
 = recovery time
~~~

Measuring only the time until `gcloud compute disks create` succeeds reports a falsely low RTO. A booted VM that cannot connect to its database does not count as a recovered service.

### 2.3. Targets must map to failure domains

| Incident type | Recovery unit | Verification goal |
|---|---|---|
| Single deleted file | File from snapshot/backup | Preserve other files and access permissions |
| File altered by ransomware | Clean pre-incident point | Do not restore infected data |
| Disk corrupted or deleted | New disk from snapshot | Mount and read/write per contract |
| Boot disk failure | New boot disk or VM | OS and application operational |
| VM deleted | VM with config and disks | Networking, IAM, and dependencies |
| Zone outage | Resources in another zone | Quotas, capacity, and traffic cutover |
| Region outage | Infrastructure in another region | Backup location, KMS, DNS, RTO |
| Project/account compromised | Isolated backups | Backups not deleted alongside production |

A solid design documents recovery objects, accountable owners, and acceptable data loss for **each workload**.

## 3. Inventory before choosing technology

For each VM or file share, inventory:

1. Project, region, zone, resource ID, and owner.
2. Machine type, OS image, boot disk, disk type/size, filesystem, and mount paths.
3. Data disks, attachment modes, LVM/RAID, encryption keys.
4. Temporary data on Local SSDs vs. durable data on Persistent Disk/Hyperdisk.
5. Filestore instance, tier, NFS protocol, file share, client mounts, IP-based access controls.
6. Cloud Storage buckets, soft-delete policies, versioning, retention, object ownership.
7. VPC, subnets, firewalls, internal/external IPs, private DNS, and load balancers.
8. Service accounts, IAM bindings, OS Login, Secret Manager, and KMS keys.
9. Underlying databases, Pub/Sub, external APIs, and dependent on-prem systems.
10. Backup schedules, retention, storage locations, restore capabilities, RPO/RTO, and sign-off owners.

**Local SSD data is not included in machine images or persistent disk snapshots.** Cache/RAM and data residing only on ephemeral local storage must be regenerated or moved to an appropriate durable data store if the business requires recovery.

### 3.1. Data classification examples

| Workload | Data location | Primary protection |
|---|---|---|
| Stateless frontend VM | Boot disk + IaC | Recreate VM and deploy code |
| Document processing worker | Boot + data disk | Snapshot schedule, backups, and runbook |
| Shared reports | Filestore | Short-term snapshots + out-of-instance backups |
| PDF archive | Cloud Storage | Soft delete, versioning/retention as needed |
| Transactional database | Cloud SQL or DB on VM | Native backups, logs/PITR, and consistency workflow |

A file existing on disk does not mean a disk snapshot is the best tool. Select techniques based on consistency and how the application consumes data.

## 4. Distinguishing HA, replication, snapshots, and backups

| Mechanism | Protects best against | What it does not guarantee |
|---|---|---|
| Multi-zone VM or regional disk | Certain infrastructure/zone failures | Recovering deleted data or ransomware |
| Replication | Data latency between replicas | Prior versions when deletes/bad edits replicate |
| Disk snapshot | Point-in-time block data for one disk | Full VM config or multi-disk app consistency |
| Machine image | VM configuration and disk data | RAM, Local SSD data, external resources |
| Backup and DR vault | Managed backups and deletion-resistant retention | Automatic recovery of app DNS, network, IAM |
| Filestore snapshot | Fast file/share rollback on one instance | Complete instance loss |
| Filestore backup | Data stored outside the instance | In-place restore across all tiers |
| Cloud Storage soft delete | Deleted objects/buckets within retention window | End-to-end application workflow restoration |

HA and replication reduce downtime; backups and recovery points let you return to a **clean point in time**. Multiple layers must usually be combined to address different risks.

## 5. Multi-layered protection architecture

~~~mermaid
flowchart TB
    APP[Compute Engine application] --> BOOT[Boot disk]
    APP --> DATA[Data disk]
    APP --> FILE[(Filestore share)]
    APP --> OBJ[(Cloud Storage objects)]
    BOOT --> MI[Machine image / reviewed IaC]
    DATA --> SCHEDULE[Disk snapshot schedule]
    BOOT --> VAULT[Backup and DR vault]
    DATA --> VAULT
    FILE --> FSNAP[Filestore snapshot]
    FILE --> FBACK[Out-of-instance Filestore backup]
    OBJ --> SOFT[Soft delete / Object Versioning]
    MI --> REC[Recovery project / zone / region]
    SCHEDULE --> REC
    VAULT --> REC
    FBACK --> REC
    FSNAP --> VERIFY[File verification]
    SOFT --> VERIFY
    REC --> VERIFY
    VERIFY --> CUT[Approved cutover]
~~~

This diagram illustrates design options rather than claiming every disk type or Filestore tier supports every feature. Verify product, region, encryption type, and restore limits before choosing.

## 6. Compute Engine snapshots

Standard snapshots record point-in-time data from supported Persistent Disks/Hyperdisks. **Incremental snapshots** track changed blocks, saving capacity and time in many cases. Operators do not have to manually assemble full/incremental file chains.

Principles:

- A snapshot of **one disk** does not restore VM configuration.
- Snapshots can be taken while a VM is running, but do not automatically provide application consistency.
- Standard snapshots are global resources by default, though restore/access locations can be constrained by configuration.
- Snapshot storage location affects availability during a region outage, data residency rules, and network costs.
- Restoring from a snapshot typically **creates a new disk**; it does not automatically overwrite the source disk.
- The new disk must have capacity at least equal to the source disk size per restore requirements.
- Snapshot READY status and actual usability must be verified periodically.

### 6.1. Standard or archive snapshots?

Standard snapshots suit frequent restores or shorter RTOs. Archive snapshots suit infrequent access, long retention, and storage optimization; weigh retrieval time, retrieval fees, and recovery requirements. Never choose archive solely by per-GB storage unit price.

### 6.2. Creating a manual snapshot

~~~bash
gcloud compute snapshots create app-data-manual-001 \
  --project=PROJECT_ID \
  --source-disk=app-data \
  --source-disk-zone=asia-southeast1-b \
  --storage-location=asia-southeast2
~~~

This is an example for **a single disk only**. Running on real projects/disks requires IAM, quotas, location support, and cost approval. For VMs with multiple data disks, design ordering/quiescing so recovery points remain consistent.

## 7. Snapshot schedules and retention

A snapshot schedule is a Compute Engine resource policy attached to disks. Schedules can be hourly, daily, or weekly; start times execute within the configured start window and do not guarantee completion at the exact start minute.

Example daily schedule at 02:00 UTC keeping automated snapshots for 14 days:

~~~bash
gcloud compute resource-policies create snapshot-schedule app-data-daily \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --daily-schedule \
  --start-time=02:00 \
  --max-retention-days=14 \
  --storage-location=asia-southeast2 \
  --on-source-disk-delete=apply-retention-policy

gcloud compute disks add-resource-policies app-data \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --resource-policies=app-data-daily
~~~

The schedule must be placed in the region matching the disk; verify compatibility per disk type. Notable flags:

- `--daily-schedule` takes no argument value.
- `--start-time` uses UTC.
- `--max-retention-days` sets snapshot retention duration for the schedule.
- `--storage-location` picks storage location; evaluate cross-region implications.
- `--on-source-disk-delete=apply-retention-policy` preserves retention enforcement when the disk is deleted.
- `keep-auto-snapshots` keeps snapshots indefinitely after source disk deletion and requires a separate cleanup workflow.

Do not set retention too short if ransomware or corruption might go undetected. Monitor the **latest genuinely successful recovery point**, not merely scheduler events.

## 8. Crash-consistent vs. application-consistent snapshots

### 8.1. Crash consistency

A snapshot taken while a VM is actively writing resembles filesystem state during a power loss. Filesystem journals can repair some metadata inconsistencies, but do not guarantee consistent committed application transactions.

For example: the app updated an index while file contents still sat in memory cache. After restore, the index may point to an incomplete file.

### 8.2. Application consistency

To obtain a reliable application-level point in time:

1. Pause or quiesce write requests.
2. Flush application transactions and filesystem buffers.
3. Capture the snapshot/backup via a supported method.
4. Resume application writes once the safe checkpoint is reached.
5. Record the timestamp/transaction marker.
6. Upon restore, run the workload's consistency check.

On Linux with Persistent Disk, you can configure **guest-flush** and pre/post snapshot scripts. On Windows with Persistent Disk, VSS can be used. **Hyperdisk does not support guest-flush/VSS via this mechanism**; use manual quiescing or appropriate application-level backups.

When multiple disks back the same database or logical filesystem, individual disk snapshots do not inherently form a transaction-consistent set. A machine image can capture disk data across disks at a coordinated disk-level moment, yet OS/application participation is still required for application consistency.

### 8.3. Databases should not rely solely on block snapshots

Transactional databases typically require native backups, transaction logs, and point-in-time recovery. Plain disk snapshots cannot guarantee consistency, especially when a database writes concurrently across multiple disks. Design database DR around the dedicated capabilities of Cloud SQL/PostgreSQL/MySQL/SQL Server or your actual database engine.

## 9. Restoring a disk from a snapshot

When only a data disk is damaged, restoring a new disk limits impact on other components.

**Procedure:**

1. Block writes or place the application in maintenance mode if needed.
2. List snapshots, identify a pre-error recovery point in READY state.
3. Create a **new disk** from the snapshot with matching zone, disk type, and capacity.
4. Attach the disk to a recovery VM for inspection; never delete or overwrite the source disk.
5. Verify partitions, filesystem, ownership, ACLs, checksums, and sample data.
6. Cut over only after approval; maintain a rollback path.
7. Record measured RPO/RTO and clean up test resources.

Example:

~~~bash
gcloud compute snapshots list --project=PROJECT_ID

gcloud compute disks create app-data-recovered \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --source-snapshot=SNAPSHOT_NAME \
  --type=pd-balanced

gcloud compute instances attach-disk recovery-vm \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --disk=app-data-recovered
~~~

Inside the Linux recovery VM, **only after confirming the exact block device**:

~~~bash
lsblk -f
sudo blkid
sudo mkdir -p /mnt/recovery
# Replace DEVICE_PARTITION with the verified path from lsblk.
sudo mount -o ro /dev/DEVICE_PARTITION /mnt/recovery
find /mnt/recovery -maxdepth 2 -type f | head
~~~

Watch out for filesystems like XFS when a clone shares the same UUID as an already mounted disk; never mount read-write or alter UUIDs without evaluation. When recovering just one file, copy the file from the read-only cloned disk to a staging path, verify checksums and permissions, and only then move it into place.

## 10. Full VM recovery: disk snapshots, machine images, and IaC

### 10.1. A VM needs more than disk contents

When recreating a VM, verify: machine type, CPU architecture, boot disk, data disks, OS startup, instance metadata, service account, IAM, firewalls, VPC, subnets, DNS, load balancers, KMS, and dependent services. Disk snapshots do not contain those external components.

Use Terraform or versioned IaC to recreate networking/VMs, remembering that **Terraform state does not replace data backups**.

### 10.2. Machine images

A Compute Engine **machine image** stores most instance configuration, volume mappings, and disk data, making it suitable for recovering a VM with multiple disks. It can capture a disk-consistent state across attached disks, though it offers no application-level transaction consistency while the app keeps writing.

Machine images **do not include**:

- RAM contents.
- Data on attached Local SSDs (may only retain device mappings).
- All instance-specific attributes identically, such as IP addresses or original name.
- External resources outside the instance such as project IAM policies, VPCs, Cloud DNS, external secrets, and KMS keys.

After restoring a machine image, verify boot integrity, disk mounts, OS permissions, service account, networking, and workload health. For Shielded VMs, check secure boot/vTPM requirements when recreating from snapshots or images.

### 10.3. Choosing a strategy by workload

| Workload | Recovery approach |
|---|---|
| Stateless VM | Recreate via template/IaC and deploy image |
| Single corrupted data disk | Disk snapshot restore |
| Multi-disk VM needing a coordinated recovery point | Machine image or suitable VM backup |
| Requires deletion-resistant/immutable backups | Backup and DR vault with enforced retention |
| Very low RTO | HA/warm standby/replication combined with backups |
| VM running a transactional DB | Combine VM/IaC with database-specific recovery |

## 11. Backup and DR Service and backup vaults

Google Cloud Backup and DR Service creates backup plans, vaults, and restores for supported workloads, including Compute Engine VM/disk scenarios.

~~~mermaid
flowchart LR
    VM[Compute Engine VM / disk] --> PLAN[Backup plan association]
    PLAN --> VAULT[Backup vault]
    VAULT --> POINT[Backup recovery points]
    POINT --> RESTORE[New VM / disk in recovery target]
    RESTORE --> VERIFY[OS + data + IAM + network checks]
~~~

A **backup vault** stores managed backups with isolation and enforced retention. With protected retention, backups cannot be deleted before the applicable expiration. Choosing excessively long retention can lock in storage costs that cannot be trimmed early.

Basic design:

1. Enable the Backup and DR API per guidance on the appropriate projects.
2. Create a vault in a location supporting the workload.
3. Configure minimum enforced retention or policy lock after review.
4. Create a backup plan with schedule, backup window, and retention.
5. Associate the plan with protected VMs/disks.
6. Monitor job history and latest recovery points.
7. Periodically restore into a test project/zone and verify.

### 11.1. Restoring from a vault

A VM can be restored to a new VM or a standalone disk depending on backup scope and supported features. The service requires IAM permissions on the backup project, target project, service agent, KMS, and potentially Shared VPC host.

CLI example from Compute Engine backup vault documentation:

~~~bash
gcloud backup-dr backups restore compute BACKUP_ID \
  --project=BACKUP_PROJECT_ID \
  --location=BACKUP_REGION \
  --backup-vault=VAULT_NAME \
  --data-source=DATA_SOURCE \
  --name=app-recovery-vm \
  --target-project=RECOVERY_PROJECT_ID \
  --target-zone=RECOVERY_ZONE
~~~

Parameters are placeholders; verify backup ID, vault, data source, location, and target. The restorer may need `roles/backupdr.restoreUser` and `roles/compute.viewer`, while the service agent needs `roles/backupdr.computeEngineOperator` depending on the scenario. Never grant Owner just to bypass IAM errors.

**Enforced retention protects backups**, not automatic restoration of VPC, DNS, secrets, or business services. A complete runbook is still required.

## 12. Filestore: snapshots and backups are two distinct layers

Filestore serves file data over NFS. Understand where recovery points reside.

### 12.1. Filestore snapshots

A Filestore snapshot resides **inside the source instance** and captures share state at a point in time. As data on the instance changes, snapshots consume capacity to preserve older versions.

Use when:

- A file/directory is accidentally modified or deleted.
- Fast short-term version retrieval is needed.
- Reverting a share after a controlled change.

Limitations:

- Snapshots are not independent of the instance and do not replace DR backups.
- Reverting an entire share **destroys data newer** than the snapshot.
- Snapshots consume capacity inside the instance.
- Snapshot functionality is supported on **zonal, regional, and enterprise** tiers, not on **basic HDD/basic SSD** per current documentation.

### 12.2. Filestore backups

A Filestore backup is an **out-of-instance** resource with its own capacity that can be stored in another region where supported. It suits DR for instance/region loss, cloning, and file recovery when creating a new share.

A backup contains file data and some metadata, but does **not** automatically preserve VPC networks, IP addresses, IP-based access controls, file locks, lock states, or source instance snapshots.

Important restore limitations:

- **Basic HDD/SSD** supports restore scenarios to source/existing/new instances under supported conditions.
- **Zonal/Regional/Enterprise** backup restores generally require a **new instance**; do not attempt in-place restores assuming basic-tier behavior.
- Target must match service tier, capacity, protocol, region/location, and encryption constraints.
- Some backups are incompatible with Filestore multishares.
- Post-restore, clients must remount and applications may need to reconnect.

### 12.3. Quick comparison

| Attribute | Filestore snapshot | Filestore backup |
|---|---|---|
| Location | Inside instance | Outside instance |
| Single file recovery | Via `.snapshot` where supported | Restore instance or share, then copy |
| Full instance loss | No independent protection | Use backup to create a new instance |
| Cost | Consumes instance capacity | Separate backup storage / cross-region transfer |
| Revert | Can destroy newer changes | Depends on tier and supported restore targets |
| Primary use | Fast operational recovery | Disaster recovery and more durable backups |

## 13. Runbook for recovering a single file on Filestore

Suppose `/mnt/reports/summary.csv` was accidentally deleted.

1. Confirm owner, filename, and loss window.
2. Check Filestore instance tier and available snapshots.
3. Select the latest clean snapshot prior to the error.
4. Access the file via the `.snapshot` directory inside the mounted share.
5. Copy the file to a **temporary path**—do not overwrite live immediately.
6. Verify checksum, size, owner/group, permissions, and contents.
7. Restore to the live path only after approval.
8. Record snapshot used, actual time, and outcome.

Illustrative path layout:

~~~text
/mnt/reports/
  summary.csv
  .snapshot/
    before-upgrade/
      summary.csv
~~~

If the entire instance is lost, recover from an **out-of-instance Filestore backup**, create a new instance in a supported location, reconfigure networking/exports/access controls, mount the share, and verify the application before cutover.

Before restoring over an active basic-tier instance, pause writes and unmount clients per documentation. Never run an in-place restore just to retrieve one file if doing so destroys newer data.

## 14. Cloud Storage: files stored as objects

Cloud Storage uses **object name + generation + metadata**, not block disks or traditional NFS shares. Appropriate protection mechanisms include soft delete, object versioning, and retention.

### 14.1. Soft delete

Soft delete retains deleted or overwritten objects/buckets for a configured duration. Supported buckets currently carry a **7-day** default duration, though actual bucket policy must be verified rather than assumed.

Soft-deleted objects cannot be read as live objects; they must be restored. Restoring creates a **new live object**, which can overwrite a current live object of the same name. When recovering, check generations and whether a newer version exists that the business wants to keep.

### 14.2. Object Versioning

Object Versioning retains noncurrent generations when objects are modified or deleted. Useful when applications need to inspect specific prior versions, yet it **does not protect against bucket deletion** and does not prevent privileged principals from permanently deleting noncurrent generations.

Google Cloud recommends soft delete when the goal is protection against accidental/malicious deletion. Combine with versioning when version-history access is needed alongside proper lifecycle policies.

### 14.3. Retention and locks

Retention policies, Object Retention Lock, or Bucket Lock can restrict deletion/modification for a duration. Some lock types are irreversible, requiring legal, data, cost, and change-management review. Never accidentally lock a multi-day retention policy on a bucket holding temporary scratch files meant to be deleted.

## 15. Cross-zone and cross-region recovery

### 15.1. Zone outage

Using snapshots or backups to create disks/VMs in another zone typically requires checking:

- CPU, memory, and disk size/IOPS/throughput quotas in the new zone.
- OS image and machine type availability.
- Subnets, private IPs, firewalls, DNS, and load balancers.
- IAM/service accounts, OS Login, and API enablement.
- KMS key locations and service agent permissions.
- Dependencies such as Filestore, Cloud SQL, and private networking.

Low RTOs may require **warm standby or HA**. Periodic backups alone do not guarantee fast service failover.

### 15.2. Region outage

Recovery points must reside in a usable location if the source region fails. Standard disk snapshots can restore across regions within location/access rules; account for transfer fees and applicable limits. Out-of-instance Filestore backups can reside in another region; a new instance must be created in a supported target location.

With Backup and DR vaults, never assume backups can restore into any location or project. Verify the workload, vault location, backup plan, KMS, and restore access matrix.

### 15.3. Failback

Once the workload runs in the recovery region, new data continues to accumulate. When returning to the original region, **reconcile data** and plan a fresh cutover. Never restore an old snapshot over newer production data merely because the original region came back online.

## 16. IAM, KMS, and protection against malicious deletion

### 16.1. Separation of duties

Separate:

- Backup configuration/plan administrator.
- Backup service identity running schedules.
- Restore operator authorized to view and use designated backups.
- Compute/Filestore service agents holding required technical permissions.
- Security/compliance reviewing retention and audits.

Do not assign Owner to a service account that only creates snapshots. Do not let production VM admins delete all backups by default. Enable auditing on policy, role, and backup deletion changes per each product's logging capabilities.

### 16.2. CMEK

For disks, snapshots, or backups encrypted with a **customer-managed encryption key (CMEK)**:

- Ensure the KMS key still exists and is enabled at restore time.
- Service agents and recovery identities hold permissions to use the key.
- Key location and encryption compatibility match the target resource.
- Clear procedures exist for rotation, key disabling, key deletion, and break-glass access.
- Never destroy a KMS key merely because the source VM was deleted.

An existing backup that cannot be decrypted is an **unusable** recovery point. Cross-project/cross-region drills must include KMS permissions.

### 16.3. Ransomware resilience

When guarding against compromised accounts or ransomware:

1. Isolate backup vaults/projects/identities from production workloads.
2. Apply enforced retention or retention locks proportional to risk.
3. Minimize principals permitted to alter retention or delete backups.
4. Monitor anomalies across API/IAM and backup activity.
5. Restore first into an isolated environment, scan for malware, and inspect data.
6. Revoke compromised credentials before cutover.
7. Preserve audit evidence and incident response plans.

Never restore clean data into a VM still controlled by an attacker.

## 17. Automating recovery with IaC and runbooks

Terraform or IaC tools can provision networks, IAM, instance templates, VMs/disks, and supported resource policies. However, **IaC is configuration, not data backup**.

A runbook should contain fixed steps:

~~~text
1. Confirm incident and affected data scope.
2. Select a clean recovery point and verify backup READY status.
3. Verify RPO, retention, permissions, KMS, quotas, and target region.
4. Stop or isolate the source if needed to prevent split-brain writes.
5. Provision target resources from IaC/images/snapshots/backups.
6. Mount data safely and run consistency checks.
7. Run smoke tests, permission checks, and business reconciliation.
8. Obtain approval to switch DNS, load balancers, or mount targets.
9. Monitor metrics/logs; prepare rollback and failback.
10. Record actual RPO/RTO, resource IDs, owners, and cost.
~~~

Never build pipelines that automatically delete/overwrite production without checkpoints and approvals. Test restores should create **new resources** rather than modifying live serving data.

## 18. Periodic recovery testing

Green backup jobs do not prove data recovers cleanly. Schedule **restore** drills in a sandbox.

| Test | Criteria |
|---|---|
| Single Filestore file from snapshot | Exact data/owner/permissions, no loss of other files |
| Filestore instance from backup | NFS mounts cleanly, valid filesystem, working network |
| Cloud Storage soft-deleted object | Exact generation, no accidental overwrite of newer versions |
| Data disk from snapshot | Filesystem mounts, valid checksums and data |
| Boot disk or VM from machine image | OS boots, services run, accurate IAM/networking |
| Backup and DR vault restore | Exact recovery point, no service agent/KMS blockers |
| Cross-region DR | Quotas, DNS, network, dependencies, and cutover verified |
| Ransomware drill | Clean point chosen, attacker isolated, backups protected |

### 18.1. Metrics to track

- `backup_success_rate` and `backup_failed_count`.
- `latest_recovery_point_age` per workload.
- `restore_test_success_rate`.
- `restore_duration` until app usable.
- Actual RPO via timestamp of the last recovered record.
- Costs of backups/retention/cross-region transfers and test resources.
- Count of resources lacking policies or not drilled within the cycle.

Do not restore only the latest backup. Test an older recovery point as well to uncover retention and chain issues.

## 19. Costs and trade-offs

Protection/DR costs include:

~~~text
Snapshot or backup storage
+ noncurrent/soft-deleted object storage
+ cross-region transfer
+ backup management and retrieval fees where applicable
+ KMS and dependency resources
+ test VMs/Filestore or warm standby
+ operational labor and drills
~~~

Filestore snapshots consume capacity inside the instance and can reduce usable space. Filestore backups consume external storage. Cloud Storage soft delete/versioning retains extra data. Archive snapshots have distinct retrieval/retention profiles. Backup vaults with enforced retention continue incurring fees until expiration.

Optimize for **downtime and data loss cost**, not just unit GB/month pricing. A cheap plan incapable of meeting RPO/RTO can cost more than a real outage.

## 20. Case study: document processing service

Application `document-worker-prod` runs on a VM in `asia-southeast1-b`:

- Boot disk holds OS/agent and runtime.
- Data disk `documents-data` holds intermediate files.
- Filestore `shared-reports` holds PDFs shared across workers.
- Cloud Storage bucket `documents-archive` holds final PDFs.
- Cloud SQL holds metadata (backed up/PITR under a separate database plan).

### 20.1. Reference targets

| Resource | Example RPO | Example RTO | Solution |
|---|---|---|---|
| Stateless VM code | Re-provisionable | 1 hour | Image/template + IaC |
| Data disk | 4 hours | 2 hours | Disk schedule + risk-aligned backups |
| Filestore | 24 hours | 4 hours | Short-term snapshots + out-of-instance backups |
| Cloud Storage PDFs | Per data policy | 1 hour for selective files | Soft delete/versioning/retention |
| Cloud SQL metadata | Per DB SLA | Per DB SLA | Native backups/PITR |

These are not default GCP SLAs. Real drills are required, along with fallback plans if the recovery target hits quota limits or KMS keys are unavailable.

### 20.2. Incident A: report accidentally deleted

1. Locate a Filestore snapshot from before deletion.
2. Copy the target file to a staging path.
3. Verify checksum, permissions, content, and owner.
4. Move the file into place after approval.
5. Record recovery time; **do not** revert the entire share.

### 20.3. Incident B: zone outage

1. Locate a clean recovery point and verify status.
2. Provision VM/disks in another zone using images/snapshots/backups and IaC.
3. Restore the Filestore share if the file server is unavailable.
4. Restore VPC/DNS/firewalls/IAM/KMS and Cloud SQL connectivity.
5. Test upload → process → PDF → metadata reconciliation.
6. Cut over traffic after approval, monitor, and draft a failback plan.

### 20.4. Incident C: ransomware

1. Isolate suspected compromised machines and identities.
2. Select a clean recovery point prior to encryption.
3. Restore in an isolated project/network, scan, and verify checksums.
4. Patch configurations, rotate credentials, and audit permissions.
5. Cut over only verified clean data.
6. Audit backup vaults, retention, and deletion permissions.

## 21. Common design mistakes

| Mistake | Impact | Fix |
|---|---|---|
| Having a disk snapshot and assuming VM DR is covered | Missing OS/network/IAM/dependencies | Machine image/IaC + runbook |
| Daily snapshots while promising a 15-minute RPO | Data loss exceeds target | Use data-layer backups/logs/replication |
| Snapshotting while DB writes and assuming app-consistency | Data may be inconsistent | Quiesce or use native backups |
| Keeping only Filestore snapshots | Instance loss wipes recovery points | Out-of-instance backups |
| Using in-place restore on the wrong Filestore tier | Rejected or disrupts share | Check tier/restore matrix |
| Enabling Object Versioning without bucket deletion protection | Entire bucket can be lost | Appropriate soft delete/retention |
| Deleting CMEK keys alongside source | Backups cannot be decrypted | Protect key lifecycle |
| Restoring directly over source | Loses newer data and complicates rollback | Restore to a new resource and verify |
| Monitoring only backup job success | Unknown if data is readable | Restore drills with checklists |
| Granting Owner to backup jobs | Excessive blast radius | Least privilege, separation of duties |
| Omitting cross-region transfer fees | Unexpected cost spikes | Cost modeling and region selection |
| Measuring only disk creation time | Inaccurate RTO | Measure until app is usable |

## 22. Pre-production checklist

### Scope and objectives

- [ ] Business owner has approved RPO/RTO.
- [ ] VMs, boot/data disks, Local SSDs, Filestore, Cloud Storage, and databases are classified.
- [ ] File, disk, VM, zone, region, account compromise, and ransomware scenarios are analyzed.
- [ ] Inventories exist for IAM, KMS, quotas, VPC, DNS, and recovery target dependencies.

### Backup and retention

- [ ] Data disks have snapshots/backups matching churn rates.
- [ ] Backups have locations and access rules satisfying DR/residency.
- [ ] Apps use consistency workflows instead of relying on crash-consistent snapshots.
- [ ] Filestore tier supports planned restore operations.
- [ ] Out-of-instance Filestore backups exist where DR requires them.
- [ ] Cloud Storage soft delete/versioning/retention are deliberately selected.
- [ ] Retention is long enough to detect corruption or malicious deletion.

### Security and operations

- [ ] Backup/restore identities hold least privilege and are separated from production admins.
- [ ] Backup and DR enforced retention and policy locks have been reviewed.
- [ ] KMS keys/service agents are tested during restores.
- [ ] Audits/alerts cover backup failures, policy edits, and deletions.
- [ ] Runbooks cover containment, recovery, verification, cutover, and failback.

### Drills

- [ ] Test restores performed for a file, a disk, and a VM.
- [ ] Filestore backup restored into a new instance.
- [ ] Cloud Storage soft-deleted object restore tested.
- [ ] RPO/RTO measured until app runs and business data is valid.
- [ ] Cross-region/project recovery tested proportional to risk.
- [ ] Test resources cleaned up and drill reports archived.

## 23. Self-check questions

1. Why does a snapshot of one disk not equal a full VM backup?
2. How does RPO differ from RTO? Why does a schedule not guarantee actual RPO?
3. When should you use a machine image instead of individual disk snapshots?
4. Is a snapshot taken while a VM is running always application-consistent?
5. With Hyperdisk, why can you not assume guest-flush/VSS works like Persistent Disk?
6. When are native database backups required instead of disk snapshots?
7. Why do Filestore snapshots not replace out-of-instance backups?
8. Why should recovering a single file not revert the entire share?
9. How do soft delete and Object Versioning differ when a bucket is deleted?
10. What does Backup and DR vault enforced retention protect against?
11. Why can deleting a KMS key render backups useless?
12. What else is required for cross-region restore beyond the snapshot itself?
13. Why should a newly restored disk be mounted read-only when verifying data?
14. Which steps belong to RTO beyond VM creation time?
15. What evidence must a good restore drill measure and record?

## References

- [Compute Engine: About snapshots](https://docs.cloud.google.com/compute/docs/disks/snapshots)
- [Compute Engine: Create disk snapshots](https://docs.cloud.google.com/compute/docs/disks/create-snapshots)
- [Compute Engine: Snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Compute Engine: Restore snapshots](https://docs.cloud.google.com/compute/docs/disks/restore-snapshot)
- [Compute Engine: Snapshot best practices](https://docs.cloud.google.com/compute/docs/disks/snapshot-best-practices)
- [Compute Engine: Application-consistent Linux snapshots](https://docs.cloud.google.com/compute/docs/disks/creating-linux-application-consistent-pd-snapshots)
- [Compute Engine: Machine images](https://docs.cloud.google.com/compute/docs/machine-images)
- [Backup and DR: Backup vaults](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup and DR: Backup plans](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-plan)
- [Backup and DR: Restore Compute Engine instances](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/compute/compute-instance-restore)
- [Filestore: Compare snapshots and backups](https://docs.cloud.google.com/filestore/docs/compare-snapshots-and-backups)
- [Filestore: Snapshots](https://docs.cloud.google.com/filestore/docs/snapshots)
- [Filestore: Backups](https://docs.cloud.google.com/filestore/docs/backups)
- [Filestore: Backup limitations](https://docs.cloud.google.com/filestore/docs/backups-limitations)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
