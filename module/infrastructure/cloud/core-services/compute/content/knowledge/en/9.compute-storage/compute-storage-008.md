# Consistent Snapshots and Coordinating with Actively Writing Applications

## Lesson Objectives

Snapshots capture the state of a volume or group of volumes at a point in time for recovery, environment cloning, or creating copies for testing. However, a snapshot taken while an application is actively writing data does not necessarily represent a valid business state. Writes may still sit in memory buffers, a transaction may be only partially written, or related data may span multiple disks.

After this lesson, you will be able to:

- Distinguish crash-consistent and application-consistent snapshots.
- Explain why filesystems, databases, and applications must coordinate before taking a snapshot.
- Sequence quiesce, flush, freeze, snapshot, and resume operations properly.
- Choose backup strategies for databases, multi-volume VMs, and distributed workloads.
- Verify recoverability, RPO/RTO, and snapshot protection in cloud environments.

## 1. What Is a Snapshot and Why Does Consistency Matter?

A snapshot is a record of the state of a volume or storage resource set at a logical point in time. Platforms may implement snapshots using copy-on-write, redirect-on-write, or other internal mechanisms. Users typically see a restore point that can be used to create a new volume.

Snapshots are useful when:

- Recovering a volume after a system error or accidental action.
- Creating data copies for testing, analytics, or development.
- Capturing a storage state before upgrading an OS or application.
- Serving as a source for backups, cloning, or disaster recovery.

The key concern is that a snapshot reflects storage state at the instant of capture. If an application is actively writing data, the snapshot may contain some written blocks and some unwritten blocks. A file may be updated while its metadata or a related file is not; a database may have new pages written without its transaction logs fully persisted.

Therefore, **a successful infrastructure-level snapshot does not automatically prove the data inside the application is consistent**. You must define the consistency level required by the application and recovery workflow.

## 2. Crash-Consistent vs. Application-Consistent

Two common terms used to describe snapshot quality are crash-consistent and application-consistent.

### 2.1. Crash-Consistent Snapshot

A crash-consistent snapshot resembles the state of a machine immediately after an abrupt power loss. The platform captures block state at a single point in time; data already flushed durably to storage before that point is generally preserved, while data sitting only in memory buffers may not appear.

Modern operating systems and filesystems typically maintain journals or metadata recovery mechanisms. After restoring a volume, the filesystem can replay its journal to return to a mountable state. However, this does not guarantee all applications completed their transactions or that multiple related files reflect the same business version.

Crash-consistent snapshots are typically suitable when:

- The application is designed to recover after a crash.
- Transaction logs or journaling mechanisms enable recovery.
- Running application recovery on startup is acceptable.
- Snapshots are only one layer of the backup strategy and restore testing is established.

### 2.2. Application-Consistent Snapshot

An application-consistent snapshot is created after the application or OS coordinates to bring data to a recoverable state following the application's rules. Depending on the workload, the process may include blocking new writes, waiting for in-flight transactions to finish, flushing data, taking a checkpoint, preserving required transaction logs, and pausing writes while capturing the snapshot.

Examples:

- A database completes or controls in-flight transactions, creates a checkpoint, and preserves the WAL/binlogs needed for recovery.
- Windows workloads can use Volume Shadow Copy Service (VSS) with compatible writers to coordinate the application and filesystem.
- Linux workloads can use application scripts/agents, flush data, and briefly freeze the filesystem if required by the platform's workflow.

Application-consistent snapshots typically shorten or avoid unexpected recovery steps and preserve cross-file relationships required by the application. However, they are only trustworthy when the writer, agent, or script genuinely supports that application and the workflow has been tested.

### 2.3. Comparison

| Criterion | Crash-consistent | Application-consistent |
|---|---|---|
| Equivalent state | Machine loses power at a point in time | Application coordinated to a recoverable point |
| Application coordination | Not required | Yes |
| In-flight transactions | May require recovery when reopened | Handled according to application procedures |
| Preparation time | Typically short | May require draining, checkpointing, or flushing |
| Assurance level | Primarily at block/filesystem level | Dependent on application, writer, and workflow capabilities |
| Best suited for | Workloads capable of crash recovery | Databases and workloads needing high consistency |

An application-consistent snapshot does not automatically guarantee distributed consistency across multiple machines or services. The consistency boundary must be clearly defined: a single filesystem, multiple volumes on one VM, a database cluster, or an entire business system.

## 3. Consistency Layers to Consider

Multiple state layers exist between the application and physical storage. Addressing only one layer may not be enough.

1. **Business consistency:** an order, transaction, or workflow has its related steps completed or recorded per business rules.
2. **Transactional consistency:** the database is not captured mid-transaction without being committed or rolled back.
3. **Filesystem consistency:** file data and metadata are written in a way the filesystem can recover.
4. **Block storage consistency:** blocks are captured at a defined point in time per platform guarantees.
5. **Cross-volume consistency:** related volumes are captured at the same consistent point or via a platform-supported snapshot group mechanism.
6. **Cross-machine/service consistency:** dependent nodes or systems coordinate to produce a mutually compatible restore point.

~~~mermaid
flowchart TD
    A["Business: order / transaction"] --> B["Application: requests and buffers"]
    B --> C["Database: transactions and logs"]
    C --> D["Filesystem: files and metadata"]
    D --> E["Block storage: volumes"]
    E --> F["Snapshot"]
    G["Coordination at each layer"] -.-> A
    G -.-> B
    G -.-> C
    G -.-> D
    G -.-> E
~~~

For example, a database may store data files on volume A and WAL on volume B. If the two volumes are captured at incompatible instants, data and log states may not align. If the platform supports multi-volume snapshot groups, verify the group's atomicity scope and limits. Otherwise, use the database's native backup mechanism or write coordination to create a valid restore point.

## 4. Pre-Snapshot Coordination Workflow

A general workflow for write-active workloads can be broken into the following steps:

1. **Define scope:** list the VMs, volumes, databases, files, logs, and dependent services that belong in the same restore point.
2. **Prepare:** check capacity, volume status, existing snapshots, access permissions, and maintenance windows.
3. **Quiesce the application:** pause accepting new writes or switch the app to maintenance mode; wait for in-flight requests and transactions to finish.
4. **Flush data:** instruct the application, database, and OS to push pending data down to storage.
5. **Checkpoint/backup mode:** use database-supported backup APIs or tools to establish a restore point and preserve transaction logs.
6. **Freeze filesystem when appropriate:** if required by the workflow, briefly freeze the filesystem to prevent file changes during snapshot capture.
7. **Take snapshot:** invoke the snapshot or snapshot-group API and confirm the platform has registered the snapshot point.
8. **Thaw and resume:** always unfreeze the filesystem, re-enable writes, and return the application to serving state.
9. **Verify:** confirm snapshot completion, source volume health, backup log persistence, and resumed application traffic.
10. **Test restore:** periodically restore into an isolated environment and run filesystem, database, and business checks.

~~~mermaid
flowchart TD
    A["Define scope and check prerequisites"] --> B["Quiesce: block new writes, drain requests"]
    B --> C["Commit/flush/checkpoint"]
    C --> D["Freeze filesystem if needed"]
    D --> E["Create snapshot or snapshot group"]
    E --> F["Confirm snapshot point registered"]
    F --> G["Thaw filesystem"]
    G --> H["Resume application and traffic"]
    H --> I["Verify and record outcome"]
    I --> J["Scheduled restore test"]
~~~

Quiesce duration must be brief and bounded. If the snapshot API takes a long time to finish, determine whether the platform only needs the initial point-in-time marker registered or requires holding the filesystem frozen until all data is copied. On many cloud services, snapshots continue copying asynchronously in the background once the point-in-time marker is established; follow the specific service documentation to know when thawing is safe.

Never leave an application or filesystem frozen indefinitely. Implement timeouts, error handling, and a cleanup branch that always runs to thaw/resume even if the snapshot command fails.

## 5. How Do Quiesce, Flush, and Freeze Differ?

These three operations are related but are not interchangeable.

| Operation | Purpose | Examples |
|---|---|---|
| Quiesce | Stop new modifications and bring the application to a safe point | Switch API to read-only, drain requests, pause consumers |
| Flush | Push data sitting in buffers down to the next storage layer | Application calls `fsync`, database flush/checkpoint |
| Freeze | Temporarily block filesystem modifications so the snapshot sees a stable state | Linux filesystem freeze or Windows VSS freeze |

Quiescing operates with business semantics at the application layer. Flushing pushes data emitted by the application down to storage. Freezing prevents filesystem changes for a brief window. Freezing a filesystem does not commit database transactions, nor does it know whether a business workflow has finished.

A solid workflow selects the right operation for each component. Never run a freeze command alone and assume the database and application are consistent.

### Linux Example: Freezing and Thawing a Filesystem

On Linux, `fsfreeze` can temporarily pause modifications on supported filesystems. The illustrative example below assumes a data volume is mounted at `/data` and the operator holds appropriate privileges:

~~~bash
# Flush written data through system buffers
sync

# Freeze the filesystem for a brief window
sudo fsfreeze --freeze /data

# Here, automation invokes the provider's snapshot API.
# Proceed only after confirming the platform has registered the snapshot point.

# Unfreeze the filesystem
sudo fsfreeze --unfreeze /data
~~~

This is an illustrative sequence, not a complete backup script. In real automation, use `try/finally` or an equivalent `trap` so the filesystem is always thawed if the API fails, times out, or the process is interrupted. Identify the exact filesystem and mount point; never accidentally freeze the root filesystem or a filesystem containing binaries needed to execute the unfreeze command.

If using a database with its own online backup workflow, follow the database's documentation. Freezing a filesystem does not replace database backup APIs, checkpoints, or transaction logs.

## 6. Coordinating Snapshots with Databases

Databases manage buffer pools, transaction logs, checkpoints, open transactions, and multiple interrelated data files. Volume-level snapshots see only block storage and do not understand transaction semantics.

### 6.1. Crash-Recoverable Databases

Many databases write transaction logs before writing data pages (write-ahead logging). When starting up after a crash, the database replays logs to recover committed transactions and discard or roll back uncommitted ones.

If a snapshot preserves all required files with valid temporal alignment, the database may recover via crash recovery. However, you must verify that the database officially supports that backup method, whether transaction logs are included in the snapshot or stored separately, and whether snapshots are consistent across all related volumes.

### 6.2. Native Online Backups

For production databases, prefer database-supported backup mechanisms, such as:

- The database's native online or physical backup tools.
- Snapshot/backup APIs provided by a managed database service.
- Checkpoints and transaction log archiving for point-in-time recovery.
- Backup tools capable of coordinating with storage snapshots and generating manifests identifying required logs.

For PostgreSQL, physical backup workflows can use supported backup functions such as `pg_backup_start` and `pg_backup_stop` on current versions while archiving required WAL segments per version guidance. For MySQL, use a consistent backup tool suited to the engine and version while preserving binary logs if point-in-time recovery is needed. Exact syntax and prerequisites must follow your specific database version.

### 6.3. Why Snapshotting Only the Data Volume Is Not Enough

Suppose a database has:

- Data files on `/db-data`.
- WAL on `/db-wal`.
- Configuration files and certificates on `/etc/db`.

If you snapshot only `/db-data`, the restored copy may lack required WAL segments or configuration. If individual volumes are snapshotted at different times, they may not represent the same database state.

How to handle it:

1. Identify every volume and file within the backup scope.
2. Prefer native backups or tools supporting snapshot coordination.
3. If using snapshot groups, confirm all volumes are captured at the same consistent point.
4. Preserve required transaction logs independently and save backup manifests/metadata.
5. Test restoring the entire volume set alongside logs and run recovery per database documentation.

Do not assume multi-volume snapshots are always atomic or automatically produce a valid database backup. That depends on the storage service, snapshot group API, guest agent, and how the database writes data.

## 7. Workloads on Windows and Virtual Machines

On Windows, Volume Shadow Copy Service (VSS) provides coordination among requestors, writers, and providers to create shadow copies. An application's VSS writer can prepare data, flush, or pause I/O per the VSS protocol. Once the snapshot is taken, the writer finalizes and the application resumes normal operation.

A VSS-enabled VM snapshot workflow typically includes:

- A backup agent or service sends a VSS request.
- Compatible VSS writers prepare application components.
- The provider creates the shadow copy or coordinates with the storage snapshot.
- Writers are notified of completion and the workload resumes writing.

Verify that the application's VSS writer is healthy and the backup workflow supports the exact workload. Snapshots fall back to crash-consistency if no compatible writer exists or coordination fails.

On Linux, guest agents or script hooks can invoke flush commands, quiesce databases, and freeze filesystems. Verify timeouts, execution permissions, and unfreezing behavior across all failure branches.

In cloud environments, some snapshot services provide guest-agent integration or application-consistent options. Feature names and support levels vary across providers, operating systems, and volume types. Check the completion status of the agent/writer; if coordination fails, classify the snapshot by its actual consistency level rather than labeling it application-consistent.

## 8. Multi-Volume Snapshots and Distributed Workloads

A single VM may use multiple volumes, while an entire system may span multiple VMs or services. These two scenarios require different coordination.

### 8.1. Multiple Volumes on the Same VM

If data is split across boot, data, and log disks, determine which volumes must be captured together. Snapshot groups or multi-volume snapshots can create synchronized snapshot points within the scope supported by the platform.

Before using them, verify:

- Whether the API captures all specified volumes simultaneously.
- Whether limits exist on volume count or volume types.
- Whether encryption keys, cross-zone, or cross-region operations are supported.
- Whether the snapshot group guarantees consistency only at the block level or includes guest/application quiescing.
- Which volumes are skipped or unsupported.

Simultaneous multi-volume snapshots solve block-level timing skew across disks, yet application coordination is still required to ensure transactional and business consistency.

### 8.2. Multiple VMs or Database Clusters

Snapshotting individual VMs does not automatically create a cluster-wide restore point. One node may have accepted new transactions while another node remains at an earlier state. For distributed systems, consider:

- The database cluster's native backup/restore mechanisms.
- Quorum, replication logs, and confirmed commit positions.
- Pausing writes at the application tier or coordinating leader/follower roles per product documentation.
- Taking per-shard or per-node backups with a unified manifest and recovery rules.
- Recording checkpoints or watermarks to track how far data has been processed.

For example, an order-processing system writes to a database, emits events to a message broker, and updates object storage. Independently snapshotting the database and broker at different times can introduce state skew between orders and events. Use transactional outbox patterns, checkpoints, or coordinated backup/restore workflows to reconcile deltas during recovery.

## 9. Example Backup Workflow for a VM Application

Suppose a Linux VM runs an order management service. PostgreSQL stores data and WAL on two separate volumes. The goal is to create snapshots for full-VM recovery.

A workflow can be designed as follows:

1. The load balancer switches the application to maintenance mode or stops sending new write requests.
2. The application waits for in-flight requests to finish; message queue consumers pause and record their offsets/checkpoints.
3. The database runs its supported online backup procedure, ensuring checkpoints and required WAL segments are preserved.
4. The guest agent issues a flush; if required by the snapshot solution, it briefly freezes the relevant filesystems.
5. The system creates a snapshot group across the data and WAL volumes using platform capabilities.
6. The agent thaws the filesystems immediately after the platform confirms the snapshot point has been registered.
7. The application and consumers resume; the load balancer restores traffic.
8. The backup pipeline stores a manifest recording VM ID, volume IDs, snapshot IDs, timestamp, database version, WAL range, encryption config, and writer status.
9. On schedule, the operations team launches a test VM, attaches the restored volumes, runs database recovery, verifies record counts, and runs API smoke tests.

It is critical to define the resume moment clearly. Do not hold the application quiesced for the entire duration of background snapshot copying if the service only needs writes paused until the point-in-time snapshot marker is established. That timing depends on the API and provider.

## 10. Restoring and Validating Snapshots

A snapshot has value only when it can be restored successfully. A `completed` status in the console/API usually indicates the infrastructure snapshot task finished; it does not replace application validity checks.

Restore test workflow:

1. Select a snapshot and verify its metadata, source, timestamp, encryption key, and retention.
2. Create new volumes from the snapshot in an isolated environment.
3. Attach the volumes to a recovery VM or launch a machine from an appropriate image.
4. Mount the filesystems and inspect journal/recovery logs.
5. Start the database following the documented recovery procedure.
6. Replay WAL/binlogs if required by the backup.
7. Verify data integrity, row counts, relationships, and checkpoints.
8. Start the application with test configuration, ensuring it never connects accidentally to production.
9. Run smoke tests and verify critical business flows.
10. Record recovery time, discovered issues, any data loss, and reconciliation results.

Never restore a production snapshot directly over a live running volume without a cutover plan. Restore to separate volumes or an isolated environment, validate thoroughly, and only then switch traffic or replace resources.

## 11. RPO, RTO, and Snapshot Schedules

Snapshot frequency and coordination must align with recovery objectives.

- **RPO (Recovery Point Objective):** maximum acceptable data loss, measured in time. A 15-minute RPO means the system aims to recover to a point no older than roughly 15 minutes when the solution functions properly.
- **RTO (Recovery Time Objective):** target duration to bring the service back online after an incident.

Taking snapshots every 24 hours cannot satisfy a 15-minute RPO. You must combine periodic snapshots with transaction log shipping, continuous backups, or appropriate replication. RTO also depends on volume creation time, VM startup, database recovery, application validation, and traffic cutover.

| Requirement | Approaches to consider |
|---|---|
| Multi-hour RPO, low-churn workload | Periodic snapshots, separate backups for critical data |
| Sub-hour RPO for databases | Snapshots combined with transaction log archiving and point-in-time recovery |
| Very low RPO | Replication/continuous data protection alongside independent backups |
| Short RTO | Pre-built images/templates, automated restores, and periodic drills |
| Regional outage recovery | Cross-region backup/snapshot replication and tested DR runbooks |

Snapshots are typically one component of a backup strategy, not the entire strategy. Protect backups against account compromise, regional failures, accidental deletion, and ransomware. Use retention locks/immutability, separate backup accounts, separated permissions, and copies in another region or account.

## 12. Snapshot Security and Operations

Snapshots can contain the entirety of a volume's data, including configuration files, logs, personal data, and credentials. Protect snapshots with the same rigor as production data.

Safeguards to consider:

- Encrypt volumes and snapshots using keys managed per organizational policy.
- Restrict permissions to create, read, share, copy, and delete snapshots.
- Control snapshot sharing across accounts, projects, or subscriptions.
- Enforce retention policies and deletion protection for critical backups.
- Audit snapshot creation, copy, restore, and delete operations.
- Apply tags/metadata identifying owner, workload, environment, source, and retention period.
- Monitor failed snapshots, stale snapshots, or critical volumes missing backups.
- Avoid leaving production secrets inside test snapshots shared with teams lacking production clearance.
- Maintain safe expiration/deletion procedures and check impacts on dependent snapshots.

A snapshot encrypted with a customer-managed key may become unrecoverable if the key is disabled or deleted. DR procedures must protect key usage permissions, key rotation policies, and key availability in the recovery account/region.

## 13. Common Mistakes and How to Avoid Them

**Snapshotting a writing application without coordination:** the snapshot may only be crash-consistent and require recovery. Define required consistency, quiesce the application, or use appropriate backup APIs.

**Flushing only the filesystem while ignoring the database:** data in database buffers or active transactions may still be inconsistent at the application layer. Use native database backups/checkpoints and preserve logs.

**Snapshotting individual volumes at different times:** data and logs may become misaligned. Use supported snapshot groups or coordinated backup workflows.

**Holding a filesystem frozen too long:** applications can suffer blocked I/O, timeouts, and outages. Freeze only for the window required to establish the snapshot point, enforce timeouts, and always thaw in cleanup.

**Assuming multi-volume snapshots equal application-consistency:** snapshot groups only guarantee platform-level synchronization. Database and application coordination is still required.

**Assuming snapshotting one VM recovers a cluster:** nodes and dependent services may be at different points in time. Use cluster-aware and checkpoint-aware backup/restore procedures.

**Omitting transaction logs:** snapshots may fail to recover to the desired point in time. Preserve WAL/binlogs or equivalent logs and record manifests.

**Skipping restore tests:** backups may lack encryption keys, configuration files, permissions, or required logs. Run periodic restore tests and record actual RTO.

**Using snapshots as the sole copy:** snapshots in the same account or region can be deleted or lost to the same failure. Maintain independent backups and copies in a separate fault domain.

## 14. Pre- and Post-Snapshot Checklist

- [ ] Identified all workloads, volumes, databases, and dependent services in snapshot scope.
- [ ] Determined whether snapshots must be crash-consistent or application-consistent.
- [ ] Verified quiesce/flush/checkpoint mechanisms appropriate for the application.
- [ ] Verified all related volumes and snapshot group capabilities.
- [ ] Checked agent/writer health and status before starting.
- [ ] Implemented timeouts and cleanup so thaw/resume always run on failure.
- [ ] Confirmed snapshot API registered the snapshot point before resuming.
- [ ] Saved snapshot ID, volume IDs, timestamp, log range, and backup metadata.
- [ ] Confirmed the application resumed normal operation after snapshotting.
- [ ] Applied encryption, access controls, and retention to snapshots.
- [ ] Maintained independent copies per disaster recovery requirements.
- [ ] Tested restores at the filesystem, database, and business levels.
- [ ] Measured actual RPO/RTO and updated the runbook.

Consistent snapshots require understanding write state from the application, database, and filesystem down to storage. Crash-consistent captures simulate power loss; application-consistent requires coordinating workloads to create a recoverable point under application rules. Choose the right combination of quiesce, flush, checkpoint, freeze, and snapshot groups, always release the workload once the snapshot point is established, and test restores to prove backups genuinely work.
