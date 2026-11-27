# Designing a Backup Strategy for Compute, Storage, and Database

In Oracle Cloud Infrastructure (OCI), an application typically depends simultaneously on Compute instances, various Storage services, databases, VCN networking, and IAM permissions. Backing up each resource in isolation is not enough to restore the entire service: a virtual machine may boot without its data volume; a database may open while the documents referenced by its records are gone.

This lesson belongs to the **Backup and Disaster Recovery** chapter and focuses on designing a backup strategy that can be implemented and verified on OCI. The expected outcome is a plan specifying protected data, mechanisms used, schedules, retention periods, access permissions, restore destinations, and evidence that business targets are met.

## 1. Start with recovery requirements

### 1.1. RPO, RTO, and recovery window

**Recovery Point Objective (RPO)** is the maximum acceptable data loss, measured in time. A 15-minute RPO means that when an incident occurs, the organization tolerates losing at most the last 15 minutes of changes.

**Recovery Time Objective (RTO)** is the maximum acceptable downtime to bring a service back to an agreed operational level. RTO includes detection, decision-making, provisioning infrastructure, retrieving data, restoring, verifying, and reopening traffic.

**Retention** is how long a copy is kept. **Recovery window** is the time span over which a restore point can be chosen; for databases, this also depends on base backups and the required log chain. Keeping a backup for 30 days does not automatically provide the ability to recover to every single second within those 30 days.

For example: an incident occurs at 10:20; the latest protected and recoverable data point is 10:00. Potential data loss is 20 minutes. If the plan requires a 15-minute RPO, the target is missed even though the latest backup job reported success.

Distinguish three timestamps:

- The data point the backup represents.
- The time the backup completes and becomes usable.
- The time the copy at the standby recovery location becomes ready.

When evaluating a region outage, use only restore points accessible in the destination region. A recent backup still sitting inside the unreachable region does not reduce RPO for that scenario.

### 1.2. Evaluate by incident type

| Incident | Required capability | Design question |
| --- | --- | --- |
| Accidental file or object deletion | Retrieve previous version | Can the right version be found and its contents verified? |
| OS failure after update | Restore boot volume or rebuild instance | Is application data decoupled from the OS? |
| Logical data corruption | Roll back before the faulty transaction | Are backups, logs, and error-time details sufficient? |
| Availability domain (AD) loss | Restore in another AD if the region supports it | Are networking, Compute, and permissions ready at the target? |
| Region loss | Operate from another region | Are destination copies, keys, quotas, and configs usable? |
| Admin account compromised | Copies protected against deletion/modification | Can a single identity delete both the source and the history? |

Define separate RPO/RTO values for each scenario. Restoring a volume within the same region does not prove recovery capability during a region loss.

### 1.3. Distinguish backup, replication, and high availability

Backup preserves historical data points for rollback. Replication maintains a copy following source changes, enabling operations to shift to another location. High availability reduces disruption when a component fails.

A system with replicas still needs backups to handle logical corruption or accidental deletions that have propagated to the replica. Conversely, daily backups may suit slowly changing data but struggle to meet recovery targets measured in minutes. When RPO/RTO exceed what backup restore can deliver, add an appropriate DR mechanism such as a standby database or standby infrastructure.

## 2. Inventory resources and protection boundaries

Catalog by **business service** rather than merely listing disconnected resources.

| Information to record | Example |
| --- | --- |
| Owner | Order management application operations team |
| Location | Tenancy, compartment, region, AD if applicable |
| Identifier | OCID of instance, volume, file system, or database |
| Actual contents | Operating system, transactional data, attachments, logs |
| Size and change rate | 500 GiB, roughly 20 GiB changed/day |
| Reproducible sources | Golden images, source code, Terraform, release packages |
| Targets | RPO/RTO for local incidents and region loss |
| Constraints | Sensitive data, allowed storage locations, retention duration |
| Dependencies | Encryption keys, secrets, DNS, IAM, networking, app versions |

Classify data into three groups:

1. **Irreplaceable:** orders, user documents, configurations existing only inside the system.
2. **Rebuildable:** application servers built from images, source code, and version-controlled configuration.
3. **Regenerable at a known cost:** caches, search indexes, summary reports.

The third group still affects RTO. If rebuilding an index takes six hours while RTO is two hours, change the recovery approach or protect the index as well.

Document consistency relationships across groups. If a database stores paths to files on File Storage, a database at 10:15 and a file system at 08:00 may not form a valid application state. A shared reconciliation point, business log, or compensation procedure is required.

## 3. Choose mechanisms for each OCI resource type

| Component | Mechanism to evaluate | Additional items required |
| --- | --- | --- |
| Compute boot volume | Boot volume backup | Instance configuration, networking, and bootability |
| Block Volume holding data | Volume backup | Filesystem check and application consistency |
| Multiple related volumes | Volume group backup | Coordination with application or database when needed |
| Object Storage | Versioning or independent historical copy | Delete permissions, retention, and retrievability |
| File Storage | Policy-based snapshots | Protection against failures beyond source scope |
| Self-managed Oracle Database on Compute | RMAN and log protection | Control file, configuration, keys, and DBA procedures |
| Managed Oracle Database | Built-in backup of the specific service | Recovery window, destination, handling on database deletion |
| Infrastructure and configuration | Infrastructure as Code, config management | State, provider versions, secrets, and rebuild permissions |

No single backup policy automatically protects every row. For each row, assign an owner and define how recovery is verified.

## 4. Strategy for Compute and Block Volume

### 4.1. Separate VM data from control configuration

A virtual machine consists of:

- Boot volume containing the OS and software.
- Block volume or file system containing data.
- Control configuration: shape, VNIC, subnet, NSG, metadata, volume attachments.
- External dependencies: databases, buckets, secrets, keys, and network services.

Custom images are suited for provisioning instances from a standardized boot disk. Data on attached block volumes **is not included in a custom image**, so it must be protected separately. [Source: Managing Custom Images](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/managingcustomimages.htm).

For rebuildable application instances, store image versions, configuration, and deployment packages while backing up generated data. For instances with frequent manual changes, increase boot volume protection frequency and gradually bring configuration under version control.

Restoring a disk does not automatically recreate subnets, NSGs, or load balancers. Those components require infrastructure definitions and dedicated procedures.

### 4.2. Full, incremental, and volume restoration

OCI supports backups for boot volumes, block volumes, and volume groups. With Block Volume, both full and incremental backups allow restoring full contents as of the backup point; the service manages underlying data dependencies. Do not mechanically apply self-managed backup rules requiring you to manually retain an entire chain of incremental files. [Source: Block Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

Base operational evaluation on the data point, completion status, actual storage size, and time to bring the application back. Do not use filesystem used space as the sole cost estimate; measure actual backup consumption after a trial period.

### 4.3. Data spanning multiple volumes

A volume group can include boot volumes and block volumes, supporting point-in-time copies with **crash-consistent** semantics. This state resembles an abrupt power loss; it does not automatically guarantee all application transactions have completed. [Source: Working with Volume Groups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/volumegroups.htm).

For instance, file content sits on volume A and metadata sits on volume B. Backing up each volume at different times can produce a copy where metadata references nonexistent content.

If application-consistent backups are needed:

1. Identify the backup mechanism supported by the application.
2. Pause writes or use an appropriate checkpoint/quiesce mechanism.
3. Flush data to the storage layer per application instructions.
4. Coordinate backup point creation via a tested procedure.
5. Resume writes, handling error and timeout cases.
6. Verify state after restoration.

Flushing the filesystem alone does not prove a database is consistent. For Oracle Database, center the data protection strategy on database-native mechanisms.

### 4.4. Schedules, retention, and cross-region copies

Use user-defined policies when adjusting schedules, retention, or automatic cross-region copying. Exact start times are not guaranteed; OCI also notes that copying daily backups to a destination region can take up to 24 hours. Therefore, a daily copy does not prove a 24-hour RPO for region loss. [Source: Backup Policies](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/schedulingvolumebackups.htm).

A starting schedule for low-churn servers:

| Copy tier | Purpose | Illustrative retention |
| --- | --- | --- |
| Daily | Recent operational errors | 14 days |
| Weekly | Late-detected errors | 8 weeks |
| Monthly | Internal audit milestones | 12 months |
| Pre-change | Patch or upgrade rollback | Until change sign-off |
| Standby region | Source region loss | Per specific DR requirements |

This is a design proposal, not an OCI default schedule. Select schedules based on change rate and the limits of the chosen mechanism.

Specify whether long-term backups are policy-managed or manually created, who owns expiration, and what happens when the source is deleted. Do not rely on source resource deletion as a substitute for backup lifecycle management.

## 5. Strategy for Object Storage and File Storage

### 5.1. Object Storage: version history and delete protection

When versioning is enabled, overwrites create new versions; standard object deletion creates a delete marker. Directly deleting a specific version can still permanently remove that version. Thus, versioning must pair with delete permission controls and version lifecycle rules. [Source: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

You can separate two needs:

- An operational bucket needing multiple versions to recover from accidental actions.
- An independent backup bucket needing immutable content for a defined retention period.

Retention rules prevent modifying or deleting objects during the protection window. Versioning and an active retention rule cannot be enabled simultaneously on the same bucket. Locking a retention rule is irreversible; test policies on sample data before applying. [Source: Object Storage Data Retention Rules](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

For independent copies, use timestamped names or prefixes:

~~~text
orders-backup/2026-11-21T020000Z/manifest.json
orders-backup/2026-11-21T020000Z/attachments/...
~~~

The manifest should list objects, source versions if applicable, sizes, appropriate checksums, and related business checkpoints. Never place credentials or secret keys in a manifest.

### 5.2. Replication does not automatically provide independent history

Object Storage replication is asynchronous. Only objects uploaded after policy creation enter the replication stream; preexisting data is not automatically transferred. Deletions at the source can propagate to the destination; prior version history is not replicated. [Source: Object Storage Replication](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingreplication.htm), [Versioning and Related Features](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Given these characteristics, the plan must:

1. Inventory and transfer preexisting data via a separate process.
2. Reconcile object lists and contents after the initial transfer.
3. Maintain independent history if rollback prior to a deletion or bad overwrite is required.
4. Test retrieving data at the standby location when the source is unreachable.

An active replica bucket and a historical archive serve two distinct functions.

### 5.3. Storage tier affects RTO

Objects in Archive must be restored before downloading. Add that restore time to RTO, along with data transfer and content verification. [Source: Overview of Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Archive/Concepts/archivestorageoverview.htm).

Design lifecycle policies by data group. Do not move all recent backups to Archive simply for lower storage unit cost. Keep recent points in a fast-access tier, transition older rarely used milestones to long-term tiers, and test both restore paths.

### 5.4. File Storage: snapshots and location protection

A File Storage snapshot is a point-in-time consistent view of an entire file system using copy-on-write. Scheduled snapshot policies can automate this. [Source: Managing Snapshots](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/managingsnapshots.htm).

For example, taking snapshots every four hours and retaining for seven days handles recent accidental deletions but does not inherently satisfy a one-hour RPO. History inside the same source scope also does not prove recoverability during region loss.

When location protection is needed, evaluate File Storage replication to supported targets and independent backup options per requirements. This replication is asynchronous; monitor replication completion points and maintain a procedure to use destination data. [Source: Replication Technologies](https://docs.oracle.com/en/solutions/mid-tier-replication-oci-dr-arch/replication-technologies1.html).

After file restoration, verify content, permissions, UID/GID, export configurations, and mountability. Files with valid checksums that the application cannot read still represent an incomplete recovery.

## 6. Strategy for Oracle Database

### 6.1. Identify the management model

| Model | Focus |
| --- | --- |
| Self-managed Oracle Database on Compute | DBA designs RMAN, logs, metadata, keys, and automation |
| Base Database or Exadata using managed backups | Supported mechanisms, destinations, policies, and monitoring |
| Autonomous Database | Backup/recovery capabilities of that exact deployment model |
| Other database engines on OCI | Engine-specific backup and log mechanisms |

Service name, deployment type, and version can alter protection capabilities. Do not apply one service's retention or restore method to another service.

### 6.2. Self-managed database: protect both data and recovery metadata

For an open database, an RMAN strategy must account for datafiles, archived redo logs, control files, and SPFILE. Point-in-time recovery depends on suitable backups and required logs; a standalone datafile copy does not prove this capability. [Source: RMAN Backup Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-backup-concepts.html).

The plan must answer:

- Which logging mode and configuration does the database use?
- Do the base backup schedule and archived log protection satisfy RPO?
- How do copies leave the host and the source fault domain?
- Where are the control file, SPFILE, password file, and connection configs stored?
- If TDE is used, are the wallet/keystore and opening procedure still usable?
- How is the RMAN repository or recovery catalog, if used, protected?
- Does the log deletion policy account for recovery needs and log consumers?

Do not delete archived logs solely to free disk space before verifying recovery requirements. Never keep the sole copy on the same Compute instance hosting the source database.

Data Pump export is useful for migrations or recovering specific logical objects. It does not replace a full database physical and log recovery plan.

### 6.3. Managed services: verify backups are configured

For services supporting Autonomous Recovery Service, you can enable automatic backups, choose a destination, and assign a protection policy. The managed mechanism sends a base backup followed by incremental backups; the policy governs retention. [Source: About Using Recovery Service to Backup and Recover Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/recovery-service/doc/about-automatic-backup-recovery.html).

| Item to record | What must be confirmed |
| --- | --- |
| Status | Enabled on the right database with actual completed runs |
| Destination | Service, location, and accessibility during an incident |
| Protection policy | Recovery window satisfies requirements |
| Redo protection | Active option and observed lag |
| On termination | How long backups are kept and how to restore |
| Restore method | Creating a new database or service-supported method |
| Monitoring | Health, successes, failures, data loss exposure |

Recovery Service offers an option to retain backups after termination; real-time data protection must be checked separately and carries additional cost. Oracle also warns that running parallel backups to two destinations can risk data loss during recovery. Do not combine custom backup scripts with managed mechanisms without verifying supported coordination. [Source: Enable Automatic Backups to Recovery Service](https://docs.oracle.com/en-us/iaas/recovery-service/doc/enable-automatic-backup.html).

### 6.4. Autonomous Database: use actual specifications

Autonomous Database provides service-managed automatic backups and recovery. For serverless deployments in Oracle documentation, backup retention and billing differ by compute model. Do not assume every database shares identical settings and pricing. [Source: About Backup and Recovery on Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-intro.html).

Document configured retention, available restore points, long-term storage options, and cross-region mechanisms if needed. Test restoring and then connecting from a test application: a running database does not prove connection wallets, secrets, DNS, and application permissions are all correct.

## 7. Protection scope, IAM, and encryption keys

### 7.1. Apply a verifiable multi-copy principle

Use the 3-2-1-1-0 mindset as a design framework:

- Multiple copies of critical data.
- Sufficiently independent mechanisms or failure domains.
- One copy off-site from the source location.
- One isolated copy or one with appropriate immutable protection.
- Zero unresolved recovery errors in the most recent tests.

This is a design principle, not a single-toggle OCI feature. Two buckets in the same region managed by the same full-admin group can both suffer from a regional outage or privilege abuse.

Compartments organize and authorize resources; they do not create independent geographic regions. Moving backups to another compartment does not provide deletion protection if a compromised identity administers both compartments.

### 7.2. Separate duties by operation

| Role | Permissions to evaluate | What to control |
| --- | --- | --- |
| Backup agent | Read source, create required copies | Do not delete history beyond policy needs |
| Restore operator | Read backups, create resources in recovery location | Do not modify production by default |
| Retention admin | Modify policies within delegated scope | Separate from day-to-day operational agents |
| Key admin | Manage key lifecycle | Control actions that remove decryption capability |
| Auditor | View configurations, status, and Audit logs | No need to modify or delete data |

Write IAM policies by resource type, compartment, and actual action. Permission to create backups does not equal permission to restore; restoring may also require creating Compute instances, volumes, networking configs, and using keys.

For automation, use supported workload identities such as instance principals or resource principals when appropriate. Do not embed personal API keys in source code or manifests.

### 7.3. Verify key dependencies

The runbook must specify:

1. Does the backup use Oracle-managed keys or customer-managed keys?
2. Which key decrypts the backup at the recovery location?
3. Does the recovery principal hold the required permissions?
4. Does restored data require its own encryption configuration?
5. Does disabling or deleting a key affect historical backups still under retention?

For scheduled cross-region backup copies of Block Volume, source Vault keys are not automatically copied to the destination. If using customer-managed keys for destination copies, configure a valid key in the destination region. [Source: Scheduling Volume Backup Copies Across Regions](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/schedulingvolumebackups.htm#Scheduling_Volume_Backup_Copies_Across_Regions).

Never bundle decryption secrets inside the backup itself so anyone reading the backup obtains the secret. Protect secrets with an appropriate manager and test emergency access procedures.

## 8. Example strategy for an order-management application

### 8.1. Context and targets

Suppose an application has two Compute instances rebuildable via Terraform and images; a managed Oracle Database storing orders; a bucket storing documents with non-overwriting names; and File Storage holding regenerable reports.

| Scope | Target RPO | Target RTO |
| --- | --- | --- |
| Orders during local incident | 15 minutes | 2 hours |
| Service including orders and documents | 1 hour | 4 hours |
| Service during region loss | 48 hours | 24 hours |

These are hypothetical example requirements, not measured results or service commitments.

### 8.2. Translating requirements into an approach

| Component | Initial approach | Evidence to collect |
| --- | --- | --- |
| Compute | Versioned images and IaC; boot backup when state needs preserving | Provisioning time, deployment time, health check |
| Database | Integrated backup, 35-day window if policy supports; redo protection meeting target | Usable restore points, time until database is usable |
| Documents | Versioning on operational bucket; hourly independent historical copies | Lag, manifest, content verification |
| Reports | Rebuild from restored data | Rebuild duration and minimum usability |
| Cross-region | Dedicated mechanism per service | Full recovery without source |

A 35-day retention is a design choice that must map to a supported policy. If the database lacks an accessible recovery plan during region loss, full-service DR remains incomplete even when boot volumes and objects are transferred.

### 8.3. Selecting a shared restore point

Each hour, the application can emit a business checkpoint containing UTC time, the set of completed uploaded documents, and corresponding transaction identifiers. The backup workflow writes the checkpoint manifest to the historical archive.

During recovery:

1. Select a checkpoint whose documents are all present at the recovery location.
2. Select a compatible database point or execute the designed reconciliation procedure.
3. Verify no order references a missing document.
4. Reconcile transactions with external systems using idempotency keys.
5. Open writes only once consistency satisfies requirements.

This mechanism must be implemented in the application; storage backups do not create business checkpoints on their own. A database with a 15-minute RPO paired with documents only recoverable from an hour earlier does not let you claim a 15-minute RPO for the whole service.

## 9. Automating and monitoring recoverability

### 9.1. Operational workflow

~~~mermaid
flowchart TD
    A["Inventory and assign protection tiers"] --> B["Policy or scheduler"]
    B --> C["Back up using appropriate mechanism"]
    C --> D["Verify completion and data point"]
    D --> E["Copy to standby location if needed"]
    E --> F["Reconcile copies and access permissions"]
    F --> G["Restore in isolated environment"]
    G --> H["Measure RPO, RTO, and run business checks"]
    D --> I["Alert on failure or overdue run"]
    F --> I
    G --> I
~~~

Prefer built-in schedules and retention when they meet requirements. For parts requiring custom orchestration, persist request IDs, states, and resource identifiers to avoid duplicates on retry.

Never retry indefinitely. A client-side timeout does not prove the OCI operation was canceled; check existing operation status before creating a new copy.

### 9.2. OCI CLI example to back up a volume group

The Bash example below is for a lab environment. It requires a configured OCI CLI, appropriate permissions, and a volume group containing the target volumes. The command triggers a manual backup and does not configure schedules or application consistency.

~~~bash
set -euo pipefail

OCI_REGION='ap-singapore-1'
VOLUME_GROUP_OCID='ocid1.volumegroup.oc1...REPLACE_WITH_REAL_OCID'
BACKUP_NAME="orders-before-change-$(date -u +%Y%m%dT%H%M%SZ)"

BACKUP_OCID="$(
  oci bv volume-group-backup create \
    --region "$OCI_REGION" \
    --volume-group-id "$VOLUME_GROUP_OCID" \
    --display-name "$BACKUP_NAME" \
    --type INCREMENTAL \
    --wait-for-state AVAILABLE \
    --max-wait-seconds 7200 \
    --query 'data.id' \
    --raw-output
)"

oci bv volume-group-backup get \
  --region "$OCI_REGION" \
  --volume-group-backup-id "$BACKUP_OCID"
~~~

The command supports FULL/INCREMENTAL and waits for AVAILABLE. If it times out, check the current operation before retrying. AVAILABLE only checks resource state; a restore test is still required. [Source: OCI CLI volume-group-backup create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/bv/volume-group-backup/create.html).

Record the OCID in a protected tracking log, set expiration rules for manual copies, and perform test restores using service procedures.

### 9.3. Indicators to monitor

| Indicator | Meaning |
| --- | --- |
| Resource missing policy or backup | Coverage gap |
| Age of latest usable restore point | Risk of RPO breach |
| Age of restore point in target region | Risk of RPO breach on region loss |
| Failed or long-running backup | Needs intervention before losing another window |
| Capacity and cost by tier | Retention or data churn exceeding budget |
| Latest successful test restore | Freshness of recovery evidence |
| Changes to IAM, policy, retention, or keys | Risk of data loss or lost accessibility |

Combine Events/Notifications for supported events, Monitoring for available metrics, and periodic checks for remaining gaps. You must also detect **backups that were never created**; job-failure alerts do not catch resources that have no policy assigned.

Alert thresholds should fire before business limits. If RPO is one hour, alerting at 45 minutes can leave intervention time; tune according to collection lag and actual remediation speed.

## 10. Recovery runbook and drills

### 10.1. Recover in dependency order

1. **Contain:** determine error onset and which backups might already hold corrupted data.
2. **Select restore point:** verify manifests and cross-component compatibility.
3. **Prepare environment:** IAM, keys, VCN, subnets, DNS, quotas, and Compute.
4. **Restore data:** databases, volumes, files, or objects via their respective mechanisms.
5. **Deploy application:** pick a version compatible with schema and data.
6. **Verify:** integrity, access permissions, connectivity, and business rules.
7. **Bring into service:** update endpoints, run verification transactions, and monitor.
8. **Re-protect:** enable backup schedules for new resources and confirm ownership.

Drill environments should be isolated from production endpoints. Block tasks that send customer notifications, process payments, or write to live systems; use test endpoints when integration checks are needed.

### 10.2. Measure service RTO

~~~text
T0: Hypothetical incident start
T1: Detection and recovery decision
T2: Target environment ready
T3: Data restore/recovery completed
T4: Application verification completed
T5: Service reaches agreed operational level

Observed RTO = T5 - T0
Observed data loss = T0 - recovered data point
~~~

If drilling on pre-provisioned environments, explicitly document what time was excluded from measurement. Results represent only the tested conditions.

A 40-minute database restore does not prove a 40-minute RTO if 70 minutes of network setup and 30 minutes of business testing still remain.

### 10.3. Multi-layer testing

| Test layer | Example | Conclusion |
| --- | --- | --- |
| Status | Backup completed, right metadata/location | Expected resource was created |
| Readability | Sample object fetch, check via backup tool | Needed data can be read |
| Technical restore | Create volume, mount file system, test database restore | Recovery path works under test conditions |
| Business | Reconcile orders, documents, totals | Recovered state is usable |
| Region loss | Use destination resources without source dependency | Specific DR scenario verified |

For self-managed Oracle Database, RMAN supports RESTORE ... VALIDATE to verify backups. This is a useful verification layer but does not replace an actual restore and application run. [Source: RMAN VALIDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/VALIDATE.html).

Run drills by criticality and after major changes to schema, encryption, IAM, or architecture. When a drill fails, log the defect, owner, due date, and retest.

## 11. Cost and capacity control

~~~text
Projected cost =
  source backup storage
  + standby copy storage
  + data transfer
  + retrieval or restore operations
  + drill resources
  + tooling and operational effort
~~~

This is an estimation model; map each line item to actual service billing models.

Ways to optimize:

- Rebuild application servers from versioned configuration to reduce data needing protection.
- Tier by RPO/RTO, avoiding long retention for all data indiscriminately.
- Monitor growth of object versions and snapshots.
- Select lifecycle tiers based on retrieval time and retention needs.
- Limit drill environment lifetime after capturing results.
- Track manual backups lacking expiration rules.
- Apply tags for application, environment, owner, and protection tier where supported.

Do not estimate simply by multiplying data size by days. Change rate, cross-copy block sharing, object versions, retention, and compression all affect cost. Measure during a pilot phase and adjust.

Never delete needed restore points solely to hit a monthly budget. When costs exceed targets, revisit storage tiers, regenerable data, frequency, and retention together with business requirements.

## 12. Backup strategy handover package

| Document | Minimum contents |
| --- | --- |
| Protection matrix | Resources, owners, RPO/RTO, and scenarios |
| Execution policies | Mechanisms, schedules, time zones, retention, and storage locations |
| Dependency map | Networking, IAM, keys, secrets, versions, and quotas |
| Runbook | Restore points, ordering, checks, and service reopening |
| Monitoring | Coverage, freshness, destination copies, failures, and cost |
| Drill evidence | Backups used, timings, technical/business outcomes |
| Lifecycle | Source deletion, owner changes, expiration, or decommissioning |

Example internal policy record:

~~~yaml
workload: orders-production
owner: platform-team
scope:
  - application-compute
  - oracle-database
  - object-attachments
targets:
  local:
    service_rpo_minutes: 60
    service_rto_minutes: 240
  regional:
    service_rpo_hours: 48
    service_rto_hours: 24
controls:
  application_configuration: versioned-iac
  database_backup: service-managed
  attachment_history: independent-timestamped-copies
  restore_environment: isolated
verification:
  recovery_point_age: monitored
  regional_recovery: requires-successful-drill
~~~

This is a plan description template, **not an OCI or Terraform configuration to apply directly**. These values only become proven capabilities when matched against real resources, accessible copies, and drill evidence. The handover recipient must immediately know: which copy to use, where to restore, under which identity, and based on what checks to allow the application back into service.
