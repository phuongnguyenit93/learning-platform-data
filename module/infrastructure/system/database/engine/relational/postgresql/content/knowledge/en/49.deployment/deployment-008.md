# Failure Distribution, Off-Cluster Backups, and Disaster Recovery Planning

A PostgreSQL system can run smoothly for months and still suffer data loss or downtime when an infrastructure zone fails, an administrative account is compromised, an accidental deletion replicates to standbys, or a backup turns out to be unrecoverable. Resilient deployment design must therefore address three concerns simultaneously: placing components into independent failure domains, keeping data copies outside the operating cluster, and maintaining rehearsed recovery procedures.

Backups, replication, and high availability serve different roles. A standby keeps service running when the primary fails. Backups let you rebuild data at a point in time before a failure or destructive operation occurred. A Disaster Recovery (DR) plan combines infrastructure, data, people, access permissions, and operational decisions to return the service to a usable state within committed RTO and RPO limits.

This lesson focuses on PostgreSQL in real-world deployment environments: analyzing failure domains, choosing redundancy architectures, designing physical and logical backups, storing WAL off-cluster, performing Point-in-Time Recovery (PITR), switching the primary, protecting backup copies, and organizing recovery drills.

## 1. Identifying Failure Domains Before Choosing an Architecture

A failure domain is the blast radius within which a single incident can simultaneously impair multiple components. Two servers with different hostnames or two distinct volumes do not necessarily belong to two independent failure domains. If they share a rack, an availability zone, a cloud account, an identity management system, or a network link, a failure in the shared layer can still take both down together.

When designing PostgreSQL deployments, evaluate at least the following domains:

| Failure Domain | Incident Examples | Potential Impact |
|---|---|---|
| Process or instance | PostgreSQL crash, out of memory, config error | Single instance stops serving |
| Server or host | Power supply, RAM, disk failure, kernel panic | Primary or standby on that host is lost |
| Rack or storage cluster | Switch, controller, power, or SAN failure | Multiple hosts lose connectivity together |
| Availability Zone (AZ) | Power, network, or infrastructure outage in one AZ | Multiple nodes in the AZ are affected |
| Region | Broad cloud provider outage, natural disaster, or inter-region network failure | Main cluster and same-region standbys become unreachable |
| Account or control plane | Compromised cloud account, abused admin privileges, automation bug | Attackers or bad commands can delete both databases and backups |
| Identity and secrets | Lost KMS key, secret, certificate, or backup account | Backups exist but cannot be decrypted or accessed |
| Software and logical data | Application bug, faulty migration, accidental DELETE statement | Error is replicated to standbys |
| Human and process | Accidental deletion, wrong command, retention change | Data or backups are unexpectedly destroyed |

Map out dependencies for every component: primary, standby, proxy, connection pool, DNS, object storage, key management system, secret manager, monitoring, CI/CD, and operational accounts. The map must show which components share infrastructure, accounts, or administrative privileges. This reveals hidden single points of failure masked by a diagram showing only two database servers.

### Examples of two configurations that merely look redundant

- Primary on host A and standby on host B, both in the same AZ: survives certain host failures, does not survive an AZ outage.
- Primary in region A and backups in a bucket within the same administrative account: survives host or region failures, but a compromised account can delete the bucket too.
- Primary and standby in two AZs, backups in object storage in another region, a separate backup account, and immutable retention: mitigates multiple independent risks.
- Two backup copies in two directories on the same volume: does not create two independent copies. Volume corruption or encryption destroys both.

The goal is not to eliminate every risk. The goal is to define clearly which failures the architecture handles automatically, which require restoring from backup, and which require manual decisions.

## 2. Distinguishing HA, Replication, Backups, and DR

These concepts are often used interchangeably, leading to recovery plans missing a critical layer of protection.

| Mechanism | Primary Goal | Helpful When | Cannot Solve on Its Own |
|---|---|---|---|
| High Availability (HA) | Minimize downtime when a component fails | Primary or host fails | Accidental deletion, corruption replicated to standby, loss of entire region |
| Physical streaming replication | Keep standby close to primary via WAL | Primary fails, standby promotion needed | Recovering state prior to a committed DELETE |
| Logical replication | Synchronize a subset of tables or logical changes | Migrations, integrations, certain read/write splits | Replacing a consistent full-cluster backup |
| Base backup | Create a baseline to rebuild the cluster | Data loss or building a new cluster | Recovering to any arbitrary point without required WAL |
| WAL archiving | Store the change sequence after a base backup | PITR and recovery past a base backup | Self-recovering if a compatible base backup is missing or WAL has gaps |
| Logical dump | Store structure and data at the SQL level | Restoring selective databases or objects, version migrations | Fast full-cluster recovery at scale or continuous PITR |
| Disaster Recovery plan | Coordinate the entire recovery process | Broad outage, region loss, credential loss, or site cutover | Replacing backups or creating recoverable data by itself |

Streaming replication ships WAL from primary to standby. When the primary commits an accidental deletion, the corresponding WAL is replayed on the standby as well. A standby therefore typically reflects the latest data, including committed logical errors.

Backups preserve historical states independent of the primary's current state. If an erroneous operation is discovered late, you can restore a backup to before the error occurred, or spin up a temporary cluster to extract the data that needs to be rescued.

HA and backups complement each other. HA handles operational disruptions; backups and PITR handle reverting to an earlier data state. DR is the plan combining these mechanisms with infrastructure and procedures.

## 3. Defining RPO and RTO

The two foundational DR metrics are Recovery Point Objective (RPO) and Recovery Time Objective (RTO).

- **RPO** is the maximum amount of data an organization can afford to lose, measured as the time interval between an incident and the newest recoverable data point.
- **RTO** is the maximum time an organization can accept to restore the service to its defined operating level.

For example, a system with a 5-minute RPO and a 1-hour RTO must ensure the recovery data point is no older than 5 minutes and the service can resume within 1 hour of declaring an incident. These are design and testing targets, not outcomes guaranteed merely by enabling a PostgreSQL option.

RPO and RTO must be defined per business workload. A payment system may demand a very low RPO, while an analytics warehouse may tolerate restoring older data. Do not apply a single number across all databases when business value and protection costs differ.

### RPO depends on the recoverable data path

With a backup and WAL archiving architecture, the newest recovery point depends on a valid base backup and a continuous WAL chain stored off-cluster. If the newest WAL has not been archived successfully or a segment is missing, the actual recovery point may be older than the current time.

With an asynchronous standby, RPO depends on how much WAL was shipped, durably written, and replayed on the standby when the primary failed. A low-lag standby generally reduces data loss but does not automatically guarantee zero RPO.

With synchronous replication, the level of guarantee depends on synchronous configuration, required standby count, and commit policy. PostgreSQL offers different wait levels via synchronous_commit: remote_write waits for the standby to write WAL to the OS, on waits for WAL to be durably flushed on the standby, and remote_apply waits for the standby to replay WAL. These levels have different durability guarantees and latency costs; remote_write is not equivalent to a durable flush across an OS crash. Inspect the actual running configuration and test behavior when a standby disconnects. Synchronous replication can increase write latency or block transactions when no standby satisfies the sync condition.

### RTO must account for the entire recovery path

Do not measure only the restore command runtime. Actual RTO includes:

1. Detecting and confirming the incident.
2. Deciding to fail over or restore from backup.
3. Provisioning servers, networking, volumes, and access permissions.
4. Fetching, decrypting, and decompressing backups.
5. Replaying WAL to the target.
6. Starting PostgreSQL, verifying consistency and extensions.
7. Validating business logic, application connectivity, and permissions.
8. Switching DNS, proxies, or endpoints.
9. Monitoring load, latency, and errors after reopening service.

Measuring only the time to restore one database on a pre-provisioned test machine does not represent system-wide RTO. Record each stage during drills, including approval wait times, resource provisioning, decryption key retrieval, and traffic cutover.

## 4. Choosing Redundancy Architecture by Failure Domain

No single configuration fits all systems. Architecture must balance RPO, RTO, cost, complexity, and operability.

### Same-AZ redundancy

A standby on a different host protects against hardware or process failures. This setup has low network latency and is easier to synchronize. However, it does not protect against outages taking down the entire AZ, internal network, or shared storage service.

### Cross-AZ redundancy

Primary and standby sit in independent AZs within the same region. When one AZ fails, the standby in the remaining AZ can be promoted if consistency and access conditions are met. Verify that the AZs are genuinely independent in power, networking, and storage infrastructure per the provider's guarantees.

### Cross-region redundancy

A standby or recovery environment in another region mitigates region-loss risk. Inter-region latency often makes replication asynchronous and risks losing WAL not yet received when the primary fails abruptly. Measure replication lag, define promotion rules, and explicitly accept the resulting RPO.

### Off-region and cross-account backups

Backups are pushed to object storage or a backup system in another region. The storage account should have independent permissions and credentials separate from database admin accounts. Deleting a cluster or compromising application credentials must not automatically allow deleting all backups.

### Cold, warm, and hot standby models

| Model | Standby Site State | Advantages | Costs and Limitations |
|---|---|---|---|
| Cold site | No or minimal infrastructure provisioned | Low cost | Long provisioning and restore time; RTO is typically long |
| Warm site | Infrastructure exists and partial data is synced or pre-staged | Balances cost and recovery time | Requires maintaining configuration, sync checks, and capacity |
| Hot standby | Running standby continuously receiving WAL | Low RTO, faster cutover | High cost; still needs independent backups and logical-error protection |

A practical design typically pairs a hot or warm standby for infrastructure failures with off-region backups for broad disasters, accidental deletions, or data corruption.

## 5. Designing a PostgreSQL Backup Strategy

A backup strategy should have multiple protective layers, each serving a distinct purpose.

### Physical base backups

Physical backups capture the physical layout of the PostgreSQL cluster, including the data files needed to rebuild a compatible cluster. They form the standard foundation for full-cluster recovery and PITR.

Base backups can be taken using pg_basebackup or specialized tools such as pgBackRest, Barman, or WAL-G. Specialized tools typically support scheduling, retention, compression, encryption, object storage repositories, WAL archiving, verification, and multi-backup catalog management. Choose one tool and operate it with a tested configuration; never assume all tools share the same naming, formats, or restore commands.

Example creating a directory-format physical backup with pg_basebackup:

    pg_basebackup \
      -h pg-primary.internal \
      -U backup_repl \
      -D /backup/staging/base-2026-11-14 \
      -Fp \
      -Xs \
      -P

Key parameters:

- -h specifies the source server.
- -U specifies the role used to take the backup; the role needs appropriate replication/backup privileges.
- -D specifies the destination directory.
- -Fp requests plain directory format.
- -Xs streams the WAL needed during the backup.
- -P displays progress.

This is an example for a test or staging area. The destination directory must have sufficient space and permissions and be safely transferred to an off-cluster repository. Never leave the only copy in a directory on the same host or volume as the database. Use a secret manager or secure system authentication rather than writing passwords directly into commands or logs.

Physical backups carry compatibility constraints with PostgreSQL version, CPU architecture, and cluster layout. When performing a major version upgrade, plan backups and restores appropriate for the target version; do not treat a physical backup from one major version as data files arbitrarily openable by another major version.

### Logical backups

Logical backups store data as SQL commands or a logical dump format. pg_dump typically backs up a single database; pg_dumpall can export cluster-wide objects such as roles and tablespaces.

Example:

    pg_dump -h pg-primary.internal -U backup_user \
      -Fc -d appdb -f /backup/staging/appdb.dump

    pg_dumpall -h pg-primary.internal -U backup_user \
      --globals-only -f /backup/staging/globals.sql

You can inspect the contents list of a custom-format dump with:

    pg_restore --list /backup/staging/appdb.dump

Logical backups are useful for selectively restoring a database, schema, or table, migrating data across versions, or creating an export independent of physical file layout. They do not natively provide continuous PITR. Restoring to an arbitrary point in time requires combining physical base backups and WAL archives, or an appropriate application-layer change capture strategy.

When taking logical backups, save required global objects such as roles and tablespaces as well. If you have only the database dump without roles, ownership, or privileges, restoring may fail to reproduce application behavior. Protect globals files because they may contain hashed credentials and sensitive configuration.

### Storage-layer snapshots

Volume snapshots can be useful when the provider supports consistent snapshots and the backup workflow understands PostgreSQL. Arbitrary snapshots across multiple volumes at slightly different instants can produce an inconsistent copy, especially if PGDATA, WAL, and tablespaces reside on separate volumes.

Use snapshots only after verifying how the system coordinates database state, WAL, and volumes. Do not treat cloud-layer snapshot creation success as proof that the database can start from that snapshot. Test restoring onto an independent machine.

### Combining multiple layers

A common strategy includes:

- Periodic physical base backups as full-cluster restore baselines.
- Continuous WAL archiving for PITR between base backups.
- Periodic logical dumps for databases or datasets requiring selective recovery.
- Separate backups of configuration, infrastructure as code, certificates, and operational runbooks.
- Off-region copies with independent retention and delete permissions.
- Restore drills verifying every layer works end-to-end.

The 3-2-1 rule is a helpful mnemonic: keep at least three copies of data, across two independent media types or storage domains, with at least one copy off the primary site. In cloud systems, interpret this rule in terms of real failure domains: separate region, separate account or permission boundary, immutable copies, and a tested recovery procedure.

## 6. Storing WAL Off-Cluster for PITR

PostgreSQL writes changes to the Write-Ahead Log (WAL). WAL is the stream of records enabling crash recovery and standby replay. With WAL archiving enabled, PostgreSQL or a backup tool ships completed WAL segments to an independent repository.

PITR (Point-in-Time Recovery) combines a base backup with the continuous sequence of WAL segments after that backup's timestamp. During restore, PostgreSQL restores the base backup and replays WAL up to the chosen timestamp, transaction, or named restore point.

### Configuring WAL archiving

Basic parameters are typically set in postgresql.conf:

    archive_mode = on
    archive_command = 'test ! -f /var/lib/pg-archive/%f && cp %p /var/lib/pg-archive/%f'
    archive_timeout = '60s'

The example above copies only to a local archive directory to illustrate how archive_command receives filenames and source paths. In production, this directory must be managed staging or data must be shipped off-cluster by an appropriate backup tool. Never use a directory on the same volume as PGDATA as your sole backup.

In archive_command:

- %p is the source WAL file path.
- %f is the WAL filename to store.
- The command returns exit code 0 when stored successfully.
- The command returns non-zero on failure so PostgreSQL can retry.

Never return success before the file is durably stored at the destination required by your backup policy. If the archive command reports success before object storage confirms persistence, monitoring may show archiving healthy while the off-cluster copy does not exist.

archive_timeout can force switching WAL segments after an interval to bound archive lag during low write load. It does not replace archive monitoring and does not guarantee RPO if the network or repository fails.

For object storage or dedicated backup systems, use tools supporting retries, checksums, encryption, multipart uploads, retention management, and alerting. Never cobble together a naive archive_command with an upload script lacking error handling or atomicity.

### Monitoring WAL archiving

Archive status can be queried from PostgreSQL:

    SELECT
        archived_count,
        last_archived_wal,
        last_archived_time,
        failed_count,
        last_failed_wal,
        last_failed_time,
        stats_reset
    FROM pg_stat_archiver;

Monitor the latest archive timestamp, failure counts, archive lag, and pending WAL volume. An increasing archived_count alone does not prove the copy in the backup region is accessible and decryptable. Cross-check the backup tool or object storage state.

If archive_command fails persistently, PostgreSQL retains unarchived WAL in pg_wal. Disk usage can grow until it disrupts database operation. Alerts must trigger early before the filesystem fills up.

Replication slots can also retain WAL not yet confirmed by consumers. Abandoned slots or stopped standbys can cause WAL accumulation. Monitor pg_replication_slots, pg_wal disk usage, and consumer status; do not delete slots arbitrarily, as doing so can leave a standby without enough WAL to resume.

## 7. Performing Point-in-Time Recovery

PITR lets you recover a cluster to a point right before a logical or data incident occurred. This is crucial when a bad migration, accidental delete, or application bug committed unwanted changes.

General procedure:

1. Select a valid base backup taken prior to the recovery target.
2. Verify the WAL chain from the base backup to the target is complete and decryptable.
3. Provision an independent recovery server and volume.
4. Restore the base backup into the target PGDATA.
5. Configure WAL archive retrieval via restore_command or the backup tool.
6. Set the appropriate recovery target.
7. Create recovery.signal on PostgreSQL 12 or later.
8. Start PostgreSQL and monitor replay progress.
9. Upon reaching the target, inspect the data and decide whether to promote or continue recovery per plan.
10. Open traffic only after completing technical and business verification.

Example recovery target configuration on PostgreSQL 12 or later:

    restore_command = 'cp /var/lib/pg-archive/%f %p'
    recovery_target_time = '2026-11-14 10:25:00+07'
    recovery_target_action = 'pause'

This example assumes WAL segments were downloaded to a local archive directory. For object storage repositories, restore_command must invoke the appropriate tool to fetch the requested WAL file. Ensure the command handles exact filenames, returns an error when a file is missing, and never overwrites invalid data.

Create the recovery signal file inside the restored PGDATA:

    touch /var/lib/postgresql/data/recovery.signal

Then start PostgreSQL. In modern PostgreSQL versions, recovery settings live in postgresql.conf or an included config file; PostgreSQL 12 and later use recovery.signal for standby/PITR workflows. Older versions used recovery.conf differently, so follow the documentation for the exact major version in use.

recovery_target_time is just one way to specify a target. PostgreSQL also supports targeting by transaction ID, LSN, or named restore point; these options are helpful when the application records business markers or when recovering right before a specific operation. Understand the inclusive/exclusive behavior and recovery_target_action of your version. Never estimate target times from an application clock if timestamps and timezones are unsynchronized.

### Finding the exact recovery timestamp

When a logical error is discovered, identify:

- When the erroneous operation committed.
- When the error began propagating to related tables or services.
- Valid transactions that occurred afterward and must be preserved.
- Events already emitted to external systems.
- Available backup points and WAL archives.

Restoring the entire cluster to before the error is not always the best choice. If many valid transactions occurred afterward, you can spin up a temporary recovery cluster, extract the data to salvage, and apply it to a new or current cluster via a reconciliation procedure. Avoid overwriting an active primary before clearly identifying which data must be preserved.

### PITR creates a new timeline branch

After recovering to an earlier point and promoting the cluster, WAL history switches to a new timeline. Never mix WAL segments from different timelines by guesswork. Manage timeline history properly and choose the right history branch according to PostgreSQL or your backup tool's procedures.

When building a new cluster from PITR, update endpoints, monitoring, and backup schedules. The newly recovered cluster must be placed back under full backup and WAL archiving immediately; otherwise, a subsequent incident could leave you unrecoverable.

## 8. Protecting the Off-Cluster Backup Repository

Off-cluster backups are only valuable if attackers or mistakes in production cannot easily delete, alter, or render backups undecryptable.

### Separating accounts and permissions

- Use a separate account, project, or subscription for the backup repository if infrastructure allows.
- Separate the backup-writing role from roles that read, restore, and manage retention.
- Production hosts should only have permission to write to their designated prefix or repository, never to delete all backups.
- Permissions to modify retention, object locks, and KMS keys must be restricted to an independent administrative group.
- Use short-lived credentials or workload identity whenever possible; rotate secrets and revoke old credentials.
- Protect emergency accounts with MFA and approval workflows.

### Immutability and versioning

Object versioning, retention locks, or immutable storage protect backups from deletion or overwriting. Understand your provider's governance vs. compliance modes, retention-bypass permissions, and expiration rules. If a production account has permission to disable immutability policies, protection against ransomware or account compromise remains limited.

Retention design must cover both base backups and WAL. Deleting WAL too early can leave a base backup intact yet unable to perform PITR to the desired target. A base backup is only usable over the WAL range needed for its recovery chain.

### Encryption and key management

Backups hold sensitive data and must be encrypted in transit and at rest. You can use backup-tool encryption, object storage encryption, or both layers. Encryption keys must be managed independently from the encrypted data.

The DR plan must specify key retrieval, decryption permissions, and recovery procedures when the KMS in the primary region is unavailable. If backups are encrypted with a key that exists only in a lost region, the data cannot be recovered. Store key metadata copies and key recovery procedures per organizational security policy; never put raw keys in the same backup bucket.

### Integrity verification

Use checksums or manifests provided by the backup tool to detect missing or altered files. For backups created by pg_basebackup with a manifest, pg_verifybackup can verify backup integrity against the manifest:

    pg_verifybackup /backup/staging/base-2026-11-14

Manifest verification does not prove every application can start or all business data is valid. Only a test restore into an independent environment proves the entire chain of backups, WAL, permissions, configuration, and extensions actually works.

### Retention and data lifecycle

Retention must align with RPO, regulatory requirements, and storage capacity. An example schedule might include daily, weekly, and monthly backups, though actual schedules depend on size, WAL churn rate, audit requirements, and historical retention needs.

Before deleting an old base backup, the tool must determine which dependent WAL segments and backups can be safely purged. Never delete WAL files manually at the filesystem level without understanding backup catalog dependencies. Improper cleanup can break the recovery chain.

## 9. Backing Up Configuration and Non-Data Dependencies

A PostgreSQL cluster can be restored at the data-file level and still fail to operate if configuration and environment dependencies are missing.

Store and manage separately:

- postgresql.conf, pg_hba.conf, pg_ident.conf, and include files.
- Startup flags, systemd units, or container configurations.
- Extension configurations, shared_preload_libraries, and corresponding OS packages.
- Roles, grants, ownership, tablespaces, and connection settings.
- TLS certificates, CAs, proxy configuration, and DNS.
- Application secrets, replication credentials, backup credentials, and KMS access.
- Infrastructure as Code, deployment manifests, firewall rules, and network routes.
- Migration scripts, compatible application versions, and operational runbooks.
- Monitoring, alerting, and backup scheduler configurations.

Never put raw secrets into Git or backup repositories merely for recovery convenience. Store references to the secret manager and ensure an independent emergency access procedure exists. DR documentation must clearly state who can grant access and how identities are verified if the primary login system is down.

Extensions must be installed at the exact compatible versions on the recovery host before startup or before accessing dependent objects. Also account for collation providers, locales, encodings, and OS library versions. Differences between source and target environments can affect indexes, string comparisons, or query behavior.

## 10. Failover and Avoiding Split-Brain

Failover is the process of transferring the primary role to a standby or DR site when the current primary can no longer serve. It is a high-impact consistency operation; never trigger it based solely on a single failed health check.

### Confirming the old primary is fenced

Split-brain occurs when two nodes both act as primary and accept writes independently. If the old primary merely lost connectivity to the monitoring system while still accepting writes from some clients, promoting a standby without isolating the old node creates two divergent data branches that cannot merge automatically.

Before promoting, the system must confirm the old primary has been fenced or definitely cannot accept further writes. Fencing can involve powering down the machine, revoking storage access, network isolation, or quorum-based leader coordination. Simply changing DNS is not full fencing because clients may hold existing connections or use cached endpoints.

### Deciding to promote

Before promoting a standby, verify:

- The standby belongs to the expected cluster and timeline.
- How much WAL the standby has received and replayed.
- Whether unshipped WAL remains on the old primary needed to meet RPO.
- Synchronous mode and synchronous standby status at the time of failure.
- Whether any risk exists that the old primary continues accepting writes.
- Which endpoints, write permissions, proxies, and applications will route to the new node.

If the standby is asynchronous, transactions committed on the primary but not yet shipped to the standby can be lost. Document the expected data loss window and decide per business policy. Never claim zero RPO simply because the standby showed low replication lag at the last observation.

PostgreSQL can promote a standby using an administrative mechanism such as pg_promote() or the provider's orchestration tool. The exact command depends on version and architecture. In automated setups, clearly understand which component holds leader-election authority and how to prevent dual promotion by two coordinators.

### Reintroducing the old primary

After failover, never restart the old primary as a standalone primary. That node may contain transactions on the old timeline. Keep the node isolated, evaluate resynchronizing with pg_rewind if eligible, or rebuild it from a backup/new standby. Rejoin the node as a standby only after verifying timeline, WAL, and replication configuration.

A solid failover procedure also includes a failback step. Failback is moving the role back to the original or preferred site after the incident is resolved. It is a new topology change requiring data synchronization, fencing, application verification, and a dedicated traffic-cutover plan. Never fail back automatically the moment the old site comes back online.

## 11. End-to-End Disaster Recovery Procedure

A DR runbook must be written so an on-call team can execute it under high pressure, even if the original architect is unavailable.

### Phase A: Detection and incident declaration

1. Receive alerts from database, infrastructure, backups, or users.
2. Determine scope: single instance, single AZ, single region, access loss, or logical data error.
3. Verify using multiple independent signals; do not promote on a single failed health check.
4. Record detection time, estimated start time, affected systems, and incident commander.
5. Declare DR per defined thresholds; notify application, security, and business teams.

### Phase B: Preserving remaining data

1. Stop jobs or operations that could continue corrupting data.
2. If compromise is suspected, isolate exposed credentials and lock down the backup repository.
3. Do not delete or overwrite the old primary before collecting needed diagnostics.
4. Confirm backups and WAL archives remain accessible from an independent account.
5. Record replication state, archive lag, and recoverable data points.

### Phase C: Selecting a recovery option

Possible paths include:

- Promote a standby when the primary fails, the standby qualifies, and the old primary is fenced.
- PITR when logical data is corrupted or rolling back to a prior point is required.
- Restore a base backup and WAL in another region when the primary site is unavailable.
- Restore a logical dump when only a specific database or subset of objects needs recovery.
- Stand up a temporary cluster to extract valid data when full production rollback is unacceptable.

Document the selected option, expected RPO, expected RTO, and transaction loss risks. When the exact recovery point is uncertain, do not mask uncertainty with a guessed number.

### Phase D: Restoring infrastructure and data

1. Provision required servers, networking, volumes, and permissions at the target site.
2. Verify PostgreSQL version, extensions, locale, tablespaces, and configuration.
3. Fetch backups using independent credentials; verify manifest and decrypt.
4. Restore base backup or logical dump per runbook.
5. Replay WAL up to the approved recovery target.
6. Check startup logs, recovery completion, timeline, and replication status.
7. Configure backups/WAL archiving for the newly recovered cluster.

### Phase E: Verification before opening traffic

Technical checks:

- PostgreSQL is ready and holding the expected role.
- No unexpected ongoing recovery or stuck transactions.
- Required databases, schemas, extensions, and roles exist.
- Application connections, TLS, DNS, proxies, and connection pools work.
- New replicas and archiving are established.
- Monitoring and alerting are reporting to observability systems.

Business checks:

- Reconcile key record counts and statuses.
- Verify totals, ledgers, orders, payment statuses, or domain invariants.
- Inspect transactions near the incident timestamp.
- Reconcile event outbox/inbox tables and messages already sent externally.
- Identify transactions needing replay, compensation, or reconciliation.

Do not open traffic merely because PostgreSQL accepts connections. Data must pass predefined checks.

### Phase F: Traffic cutover and stabilization

1. Switch endpoints, DNS, proxies, or service discovery to the recovered cluster.
2. Verify applications write to the right primary.
3. Monitor errors, latency, connection pools, locks, WAL, and replication lag.
4. Ramp up load in stages if the system supports progressive rollout.
5. Preserve incident backups and logs for post-incident investigation.
6. Close the incident only when business owners confirm service and data meet criteria.

### Phase G: Restoring redundancy

Once production stabilizes:

- Rebuild standbys and verify replication.
- Enable or verify WAL archiving to the off-cluster repository.
- Take a new base backup if the prior recovery chain is no longer suitable.
- Verify retention, permissions, and encryption.
- Update topology diagrams, endpoints, and runbooks.
- Plan failback if needed.
- Conduct a post-incident review and document lessons learned.

## 12. Verifying Integrity After Restore

A file-level restore succeeding does not mean business data is accurate. Multi-layer verification is needed.

### PostgreSQL layer

- Verify required databases and schemas.
- Check roles, memberships, ownership, and grants.
- Check extensions and versions.
- Check constraints, indexes, sequences, and partitions.
- Check tablespaces, locale, encoding, and collation.
- Verify replication, WAL archiving, and backup schedules post-recovery.

Useful inspection queries:

    SELECT datname, pg_database_size(datname)
    FROM pg_database
    ORDER BY datname;

    SELECT extname, extversion
    FROM pg_extension
    ORDER BY extname;

    SELECT
        application_name,
        state,
        sync_state,
        write_lag,
        flush_lag,
        replay_lag
    FROM pg_stat_replication;

Views can vary by major version and node state; query pg_stat_replication only on the primary. An empty result is normal if no standby is connected yet.

### Data and business layer

Do not merely count rows. Define invariants that must hold, such as:

- Ledger debits and credits balance.
- Each idempotency key produces only one business effect.
- Paid orders have corresponding payment transactions.
- Foreign keys and tenant relationships are intact.
- Record counts by date or status fall within reasonable ranges.
- Events requiring replay are identified without causing duplicate effects.

Use reconciliation queries, range checksums, summary tables, or business reports. If restoring to a time prior to some valid transactions, prepare the list of affected transactions and a business-approved replay/compensation process.

## 13. Monitoring and Alerting for Backups and DR

Do not alert only when a backup job returns an error. A backup job can report success while data never reached off-cluster storage, or a backup can exist while required WAL segments were already purged.

Metrics to monitor:

| Metric | Meaning | Alert When |
|---|---|---|
| Last successful base backup time | Age of newest baseline | Exceeds backup schedule or internal RPO |
| Last successful WAL archive time | Freshness of archived WAL | Too long without WAL while database has writes |
| Archive failure count | WAL shipping errors | Increasing continuously or a segment stays failed |
| Archive lag | Delay from WAL creation to archive | Exceeds RPO threshold |
| pg_wal disk usage | WAL retained on primary | Growing rapidly or filesystem nearing full |
| Replication lag | WAL send/write/replay delay | Exceeds failover/RPO threshold |
| Slot retained WAL | WAL pinned by replication slots | Approaches disk-full risk threshold |
| Backup repository capacity | Available backup storage | Nearly full or retention cannot run |
| Backup checksum/manifest | Backup file integrity | Verification fails |
| Restore drill duration | Measured recovery time | Exceeds RTO |
| Restore success rate | Drill restore pass rate | Any failure or missing WAL chain |
| KMS/key availability | Backup decryption capability | Key unreachable from DR site |

Alert on recoverable data age, not just job status. For instance, a last successful backup 24 hours ago is normal on a daily schedule, yet fails a 15-minute RPO if WAL archiving is broken. A job reporting success does not replace checking the newest recoverable point.

PostgreSQL provides pg_stat_archiver for tracking archiving and replication views for observing standbys. Backup tools typically maintain their own catalog of backups, WAL, and retention. Monitoring must combine PostgreSQL metrics with repository status.

## 14. Periodic Restore and DR Drills

An untested backup is only an assumption of recoverability. Drills confirm that backups, WAL, encryption keys, documentation, permissions, and people all work when needed.

Include the following drill types:

### Standalone restore

Take a base backup and restore it to an isolated host. Verify PostgreSQL starts, databases open, extensions load, and basic queries succeed.

### PITR

Choose a specific timestamp, restore a base backup and WAL up to the target. Verify a change before the target is present and a change after the target is absent. Repeat with targets close to commit timestamps to verify precision.

### Off-region recovery

Use DR-site accounts and networking to fetch backups from the off-region repository. Do not use credentials stored on the primary. Measure provisioning, download, decryption, restore, WAL replay, and verification times.

### Standby failover

Simulate primary loss, verify fencing, promote standby, switch endpoints, and test writes. Then rebuild the old node as a standby per the approved procedure.

### Access-loss or ransomware drill

Simulate production credentials being revoked or untrusted. Verify the backup repository remains accessible via an independent account, retention cannot be bypassed by application roles, and decryption keys remain available.

### Tabletop exercise

Operations, security, application, and business teams walk through a scenario on paper: who declares DR, who approves RPO, who is authorized to promote, who communicates with customers, who validates data, and who authorizes opening traffic. This uncovers permission and ownership gaps missed by technical tests.

Each drill should record:

- Date, PostgreSQL version, and backup tool version.
- Backup ID, base backup timestamp, and WAL range.
- Recovery target and timeline.
- Duration of each stage.
- Technical and business check results.
- Issues encountered, root causes, and corrective actions.
- Action owners and due dates.

Drill frequency should match system criticality. Systems with strict RTO/RPO require more frequent testing, as well as drills after major changes to topology, backup tools, KMS, or authentication workflows.

## 15. Common Mistakes

**Treating a standby as a backup.** A standby receives WAL and reproduces deletions or data corruption. Historical backups and WAL archives for PITR remain necessary.

**Storing backups in the same failure domain as the primary.** A host, AZ, account, or ransomware incident can destroy both primary data and backups. Separate repository failure domains and administrative permissions.

**Backing up only databases and forgetting global objects.** Restores can miss roles, tablespaces, or privileges. Save globals and verify ownership after recovery.

**Having base backups without complete WAL.** A base backup may restore yet fail to reach the desired recovery target. Monitor WAL continuity and retention dependencies.

**Failing to verify encryption keys.** Backups remain intact yet undecryptable if the primary KMS or credentials are lost. Drill key and access recovery at the DR site.

**Promoting a standby before fencing the old primary.** This can create split-brain and two independent write branches. Isolate the old primary before switching roles.

**Setting RPO/RTO by guesswork.** Numbers without measured restores or replication metrics are unfounded commitments. Measure during drills across every stage.

**Checking only whether backup jobs succeeded.** A successful job does not prove backups decrypt, WAL is complete, or the cluster starts. Verify checksums, run restore drills, and run business checks.

**Omitting configuration and dependencies.** Missing extensions, TLS, secrets, DNS, or IaC can prolong RTO even after data finishes restoring.

**Having no failback plan.** The old site coming back online does not mean traffic can shift back immediately. Resynchronize data and enforce a single unambiguous primary.

**Not protecting backups from production permissions.** Compromised application or database admin accounts can wipe backups too. Separate permissions, accounts, and immutable retention.

## 16. Design and Operations Checklist

### Architecture

- [ ] Documented failure domains: host, rack, AZ, region, account, KMS, network, and people.
- [ ] Primary and standbys placed according to HA objectives.
- [ ] Backups stored outside the primary failure domain with off-region copies as needed.
- [ ] Fencing mechanism in place prior to promotion.
- [ ] Failback procedure defined.

### Backups and WAL

- [ ] Appropriate base backup and logical backup schedules configured.
- [ ] WAL archiving runs continuously and is monitored.
- [ ] Recovery chain contains complete base backups and WAL.
- [ ] Backups include checksums/manifests and integrity checks.
- [ ] Retention covers error-detection lead time and PITR requirements.
- [ ] Configuration, globals, extensions, and dependencies are backed up.
- [ ] Backup repository enforces versioning or immutable retention.
- [ ] Backup credentials and KMS keys are separated from production accounts.

### RPO/RTO

- [ ] RPO and RTO defined per business workload.
- [ ] RPO measured from actual recoverable data points.
- [ ] RTO includes provisioning, backup download, decryption, replay, validation, and traffic cutover.
- [ ] Alerts trigger when backup/WAL age exceeds thresholds.
- [ ] Objectives validated through drills.

### Recovery

- [ ] Failover and PITR runbooks exist.
- [ ] Runbooks exist for region loss or primary account loss.
- [ ] Data and business verification procedures exist before opening traffic.
- [ ] Emergency access to secrets and KMS is established.
- [ ] Post-incident standby rebuild and backup restoration procedures exist.
- [ ] Explicit owners and approval paths exist for every step.

## 17. Practice Exercises

1. Diagram a primary, standby, backup repository, KMS, DNS, and monitoring setup. Highlight shared failure domains and propose how to separate them.
2. Build an RPO/RTO table for three workloads: payments, order management, and an analytics warehouse. Explain the cost trade-offs of each tier.
3. Create a base backup using pg_basebackup in a test environment. Verify the backup with its manifest if available and restore it onto another server.
4. Enable WAL archiving, generate data changes, and confirm WAL segments ship to an off-cluster repository.
5. Perform PITR to right before a test UPDATE or DELETE statement. Verify state before and after the recovery target.
6. Create a logical dump with pg_dump, export globals with pg_dumpall, and restore into a test database. Check roles, owners, and grants.
7. Simulate archive_command failure. Observe pg_stat_archiver, logs, and pg_wal disk usage; then restore archiving and verify queued WAL is processed.
8. Set up an asynchronous standby and observe write_lag, flush_lag, and replay_lag. Discuss which data could be lost if promoted at different moments.
9. Design a fencing and failover procedure. Simulate the old primary losing contact with monitoring while still reachable by one client; specify how split-brain is prevented.
10. Stand up an isolated DR site using only backup credentials. Measure provisioning, backup retrieval, decryption, restore, WAL replay, and business check times.
11. Design immutable retention so production accounts cannot delete backups early. Review bypass permissions and key recovery workflows.
12. Run a tabletop exercise for a full-region outage. Assign who declares DR, who chooses the recovery target, who validates data, and who switches traffic.
13. Write a drill report covering actual RPO, actual RTO, slowest steps, discovered issues, and corrective actions.
14. Explain why a succeeded backup job does not prove recoverability, and propose three additional verification checks.
15. Outline the handling procedure when an accidental deletion has already replayed to the standby while backups and WAL remain intact.

## 18. PostgreSQL Reference Documentation

When implementing, consult the documentation for your cluster's exact major version, as parameters, monitoring views, and recovery procedures can differ across versions.

- PostgreSQL Documentation — Backup and Restore: https://www.postgresql.org/docs/current/backup.html
- PostgreSQL Documentation — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL Documentation — pg_basebackup: https://www.postgresql.org/docs/current/app-pgbasebackup.html
- PostgreSQL Documentation — pg_verifybackup: https://www.postgresql.org/docs/current/app-pgverifybackup.html
- PostgreSQL Documentation — pg_dump: https://www.postgresql.org/docs/current/app-pgdump.html
- PostgreSQL Documentation — Warm Standby: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Monitoring Statistics: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Runtime Configuration, Replication: https://www.postgresql.org/docs/current/runtime-config-replication.html

Reference documentation must be checked against the deployed PostgreSQL version. Parameter names, recovery configuration syntax, and backup tool capabilities can vary across major versions.
