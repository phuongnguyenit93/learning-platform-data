# Compression, Encryption, Retention, and Off-Host Copies

In the **DATABASE_MYSQL** module, backup and recovery are part of relational database operations. A backup is only valuable when the data is consistent, decryptable, recoverable within target times, and still survives if the primary host or an administrative account is compromised.

This lesson focuses on four operational decisions: **compression** to reduce storage and transfer costs, **encryption** to protect data, **retention** to balance recoverability against cost, and **off-host copies** to keep data safe when primary infrastructure fails. These decisions must coordinate with MySQL's full backup, incremental backup, and binary log strategy.

Within `DATABASE_MYSQL`, this topic bridges table design, data types, keys, SQL queries, indexes, transactions, and concurrency control with reading execution plans, query tuning, privilege management, backups, and operational incident response for relational databases.

## 1. Objectives and Principles

After this lesson, you will be able to:

- Choose a compression method aligned with backup type and CPU, storage, and bandwidth limits.
- Distinguish in-MySQL data encryption, disk encryption, backup file encryption, and encryption in transit.
- Design key lifecycles so backups remain decryptable throughout their entire retention window.
- Build retention policies for full backups, incremental backups, and binary logs.
- Replicate backups to independent infrastructure, verify integrity, and protect copies from unauthorized deletion or tampering.
- Run recovery drills to confirm backups meet RPO and RTO.

Two metrics to align with the system owner:

- **RPO (Recovery Point Objective):** the maximum acceptable data loss, usually expressed in time. An RPO of 15 minutes means the goal is to recover data to a point no older than roughly 15 minutes before an incident.
- **RTO (Recovery Time Objective):** the target maximum duration to return the service to operation after an incident.

RPO drives backup creation frequency and binary log shipping cadence. RTO drives backup type, restore speed, data transfer volume, and drill durations. You cannot choose a backup schedule solely from disk capacity while ignoring these two targets.

## 2. Compressing Backups

### 2.1. Why Compress?

Logical backups typically contain SQL statements and text-formatted data. Repetitive text compresses well. Physical backups contain data pages, redo logs, and storage engine metadata; compression ratios depend on the underlying data and the tool creating the copy.

Compression can help:

- Reduce storage footprint and off-host copy costs.
- Reduce network transfer volume when copying to remote storage.
- Shorten transfer time when bandwidth is the primary bottleneck.
- Retain longer history within the same storage budget.

Compression also consumes CPU and can slow down backup or recovery jobs. If the system is already under heavy CPU load, overly aggressive compression can impact business queries. If data is already compressed—such as JPEG images, video, ZIP archives, or encrypted data—savings are usually low.

### 2.2. Where to Compress in the Pipeline?

For logical backups, you can pipe the export stream through a compressor without writing an uncompressed SQL file:

~~~bash
set -o pipefail
mysqldump --login-path=backup \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases shop | gzip -c > shop.sql.gz
~~~

This example illustrates creating a dump and streaming compression with `gzip`. `--single-transaction` establishes a consistent snapshot for InnoDB tables within a transaction; it does not guarantee a consistent snapshot for non-transactional tables. During the dump, restrict DDL changes that could disrupt metadata reads. If non-transactional tables exist or consistency requirements are complex, use locking methods or backup tools suited to the architecture.

`--routines`, `--events`, and `--triggers` include the corresponding objects in the dump. However, dumping a business schema does not automatically replace backing up accounts, roles, grants, server configurations, plugins, and operational runbooks. Verify the actual scope of each backup type.

For physical backups, tools like MySQL Enterprise Backup or Percona XtraBackup may offer dedicated compression modes and stream optimizations. Exact syntax, parallelism, and version requirements depend on the tool and version in use. Check the exact version's documentation and verify prepare/restore workflows before deploying.

### 2.3. Choosing Compression Algorithms and Levels

| Compression Method | Characteristics | When Suitable |
|---|---|---|
| gzip | Ubiquitous, widely compatible, balanced ratio and speed | Simple pipelines needing easy decompression across many hosts |
| zstd | Offers wide range of speed vs. ratio levels; often well-suited to large streams | Tuning against CPU, bandwidth, and recovery speed |
| Tool-integrated compression | Can leverage tool's native format and parallel workers | Physical backups or environments standardized on a dedicated tool |

Do not pick a compression level solely for the smallest file size. Measure backup creation time, CPU usage, resulting size, transfer speed, and decompression time during recovery. The goal is finishing backups inside the operational window and recovering within RTO.

### 2.4. Compress Before Encrypting

The standard order is **backup → compress → encrypt**. Encrypted data has high entropy and is nearly incompressible. Encrypting before compressing wastes CPU and time with negligible size reduction.

For multi-step pipelines, check the exit code of every command in the pipeline. In Bash, enable `set -o pipefail` so failures from export or compression commands are not masked by downstream commands. Only mark a backup successful when the entire pipeline succeeds and the output file passes checks.

## 3. Encrypting Backups

### 3.1. Distinguishing Encryption Layers

Multiple layers protect data, and they do not substitute for one another:

| Protection Layer | What It Protects | Key Limitations |
|---|---|---|
| TLS on MySQL connections | Data in transit between client and server | Does not protect the backup file after creation |
| Disk or volume encryption | Data at rest on device if device or volume is accessed without authorization | Files can be read by processes running against an unlocked volume |
| Tablespace or in-MySQL encryption | Certain MySQL data files on disk | Depends on version, edition, engine, and keyring setup; does not auto-encrypt exported dumps |
| Backup file encryption | Exported or packaged backup artifacts | Requires key management to decrypt during recovery |
| Encryption in transit to storage | Data moving over the network to backup hosts or object storage | Does not replace encryption at rest |

For instance, InnoDB tablespace encryption can protect tablespace files based on MySQL version capabilities and configuration. An exported SQL dump remains readable text unless encrypted separately. Therefore, clarify which data is encrypted at every stage.

### 3.2. Encrypting Files After Compression

You can use GnuPG to symmetrically encrypt a compressed dump file:

~~~bash
set -o pipefail
mysqldump --login-path=backup \
  --single-transaction --quick \
  --routines --events --triggers \
  --databases shop \
  | gzip -c \
  | gpg --symmetric --cipher-algo AES256 \
      --output /srv/backups/shop.sql.gz.gpg
~~~

GPG will prompt for a passphrase according to the configured interactive mechanism. Never put MySQL passwords, encryption passphrases, or secret keys directly in commands, shared scripts, logs, or easily exposed environment variables. The backup account should also hold least-privilege permissions and be managed separately.

Decrypting and restoring the dump:

~~~bash
set -o pipefail
gpg --decrypt /srv/backups/shop.sql.gz.gpg \
  | gzip -dc \
  | mysql --login-path=restore
~~~

The restore command illustrates a dump created with `--databases shop`, so the dump contains database creation/selection statements. Run it in a prepared recovery environment, verifying the exact host and target before loading data. For production data, test-restore on an isolated machine first.

Some physical backup tools offer built-in encryption. When using it, check the algorithm, key provisioning, key recovery, and tool version compatibility. Avoid double-encrypting without assessing impact on speed and recovery procedures.

### 3.3. Managing Keys and Passphrases

Losing a decryption key renders a backup unusable even if the file is intact. Conversely, anyone holding both the key and read access to the backup can read sensitive data. Key management must be part of the recovery plan.

Principles to apply:

- Store encryption keys in a controlled KMS, HSM, or secret management system; restrict which people and services can use keys.
- Separate key administration permissions from backup deletion or download permissions. A compromised account should never be able to both delete backups and destroy keys.
- Never store keys or passphrases in the same directory, account, or backup archive as the encrypted data.
- Maintain backup copies of key material under a controlled workflow with accountable owners and retrieval verification.
- Record key version, creation timestamp, usage scope, and rotation procedures.
- Test decryption with real keys during recovery drills.

When using envelope encryption, data is encrypted with a Data Encryption Key (DEK), and the DEK is protected by a Key Encryption Key (KEK) in a KMS/HSM. When rotating KEKs, ensure older DEKs can still be unwrapped or re-wrapped. Never delete old keys while backups depending on them remain retained.

Key retention must be at least as long as the retention of associated backups, plus a policy buffer. A backup kept for 12 months whose key is deleted after 90 days cannot be restored when historical inspection is needed.

## 4. Retention Policies

### 4.1. Designing Around RPO, RTO, and Business Needs

Retention determines how far back in time you can recover. A policy must answer:

- How far back do we need to recover if an error is discovered late?
- How long must data be kept under contracts, regulations, or audit rules?
- How often is a backup superseded by a newer one?
- Which full backup do incremental backups depend on?
- How long must binary logs be retained for point-in-time recovery?
- Until when will encryption keys and recovery metadata be preserved?

Keeping backups longer is not automatically better without access controls, encryption, and scheduled deletion under policy. Conversely, retaining too briefly can mean silent corruption or data errors are discovered only after clean copies have been overwritten.

### 4.2. Example Retention Schedule

The table below is an example for discussion with system owners; it is not a mandatory schedule for every workload:

| Copy Type | Example Frequency | Example Retention | Purpose |
|---|---|---|---|
| Full backup | Weekly | 8 weeks | Periodic standalone recovery checkpoint |
| Incremental backup | Daily | Until the corresponding full chain expires | Reduce daily backup data volume |
| Binary logs | Recorded continuously, shipped periodically | 14–35 days or per RPO and PITR needs | Recover to a specific point in time |
| Long-term full backup | Monthly | 6–12 months or as required | Audits, investigations, or archival obligations |

Actual durations must be grounded in legal rules, contracts, data sensitivity, growth rate, and budget. If incrementals depend on a full backup and earlier incrementals, retain the entire required chain. Deleting a base full backup while keeping dependent incrementals invalidates the recovery chain.

### 4.3. Binary Logs and Point-in-Time Recovery

Full or incremental backups establish data checkpoints. Binary logs record eligible changes for replay after those checkpoints, enabling **point-in-time recovery (PITR)**. For PITR to work, you need:

1. A recoverable full backup or backup chain.
2. Continuous binary logs from the backup checkpoint to the target time.
3. Metadata such as GTID set or binlog coordinates matching the backup.
4. Tools and procedures to replay logs to the exact target timestamp or position.
5. Keys and configurations required to open data post-recovery.

Binary log retention must account for incident detection time. If a data error is discovered after 20 days while binary logs are only kept for 7 days, the system may lack logs to roll back prior to the error.

Never purge binary logs merely because a new full backup finished. Confirm the new backup was copied off-host, verified, and that old logs are no longer needed for any recovery chain before cleaning up.

### 4.4. Capacity Estimation

Storage sizing is not just the size of one full backup. Account for:

- Compressed full backup size.
- Daily changed data and incremental sizes.
- Binary log generation rate.
- Number of retained copies per cycle.
- Off-host copies and scratch space used during creation or recovery.
- Long-term archives, metadata, checksums, and key material per policy.

A rough estimate:

\[
S_{\text{total}} \approx
N_f S_f + N_i S_i + N_b S_b + S_{\text{temp}} + S_{\text{overhead}}
\]

Where \(N_f\), \(N_i\), and \(N_b\) are the counts of full backups, incrementals, and binary log retention units; \(S_f\), \(S_i\), and \(S_b\) are their respective average sizes. This is an initial budgeting model; measure real-world figures because incrementals and binary logs vary with workload.

Monitor capacity over time. When data growth or log generation rates shift, recalculate how much retention fits within the current budget.

## 5. Off-Host Copies

### 5.1. Why Independent Copies Are Needed

If all backups sit on the same server, volume, or administrative account as MySQL, a single failure can destroy both primary data and backups. Common scenarios include:

- Storage hardware failure or volume corruption.
- Accidental deletion of the backup directory during operations.
- Compromise of an administrative account or backup host.
- Ransomware encrypting live data alongside online-mounted backups.
- Data center or availability zone outages.
- Configuration, operator, or software bugs corrupting multiple copies at once.

Off-host copies require independent failure boundaries: a different host, different storage zone, different cloud account or project, and separate credentials. If regional disaster recovery is required, store an additional copy in another geographic region.

### 5.2. The 3-2-1-1-0 Principle

A common design check is:

- **3 copies:** primary data plus at least two backup copies.
- **2 storage media or domains:** lowers the risk of one device type or service failing everywhere.
- **1 off-site copy:** isolated from the primary data center.
- **1 offline or immutable copy:** protected from alteration/deletion during the retention lock window.
- **0 undetected errors:** verified via checksums, decryption checks, and recovery drills.

This is a design guideline, not an absolute guarantee. Copies still require access controls, health monitoring, and actual restore testing.

### 5.3. Off-Host Transfer Workflow

A safe operational flow may include:

1. Create the backup into a staging directory with restricted permissions.
2. Wait for the tool to finish and check exit code, size, format, and consistency.
3. Compress and encrypt before leaving the host's trust boundary, if encryption happens at the application/host layer.
4. Generate checksums or signed manifests to validate files in transit and at rest.
5. Transfer over an encrypted channel to a backup host or object storage.
6. Verify the copy from the destination side: size, checksum, read permissions, and retrievability.
7. Apply retention and immutability policies on the destination storage.
8. Purge temporary local copies per policy only after the remote copy is verified.

You can use `rsync` over SSH for a standalone backup host or TLS-enabled object storage sync tools. Example of copying a completed file:

~~~bash
rsync -a --partial \
  /srv/backups/shop.sql.gz.gpg \
  backupuser@backup-host:/srv/mysql-backups/
~~~

This command illustrates transferring a file to another host. It does not inherently provide immutability, nor does it prove the remote copy is decryptable. Verify the file at the destination, isolate permissions, and enforce accidental-delete/tamper protection.

With object storage, consider versioning, Object Lock, or retention locks supported by the chosen storage model. Configure immutability durations to align with data deletion policies and compliance rules. The backup writer account should not have permission to shorten lock periods or delete locked versions.

### 5.4. Separation of Duties and Credential Protection

- Use a dedicated account to write copies to remote storage.
- Restrict the backup account to writing only into the designated destination prefix/area.
- Use a separate account for deletion or retention changes; protect it with MFA and proper approval workflows.
- Never store SSH private keys, cloud access keys, or passwords inside the backup directory or committed scripts.
- Rotate credentials on schedule, audit upload/delete activity, and alert on unexpected changes.
- Verify repository access from an independent recovery environment, even when the primary MySQL host is down.

Off-host copies can still be exposed if read credentials or decryption keys are compromised. Therefore, separate storage locations, separation of duties, and encryption must be implemented together.

## 6. Verifying Integrity and Recoverability

### 6.1. File Verification Is Not Recovery Verification

A reasonable file size or matching checksum only proves part of the picture. Verification steps should escalate progressively:

- Check tool exit codes and logs.
- Confirm the file is non-empty and within an expected size range.
- Verify compression structure, e.g., `gzip -t` for gzipped files.
- Perform a test decryption to verify keys/passphrases still work.
- Compare source and destination checksums after transfer.
- Restore onto a test server and verify data, objects, privileges, and queryability.

Using the encrypted file example above, you can stream-decrypt and test the gzip structure without loading data into MySQL:

~~~bash
set -o pipefail
gpg --decrypt /srv/backups/shop.sql.gz.gpg | gzip -t
~~~

Generate a checksum for the file:

~~~bash
sha256sum /srv/backups/shop.sql.gz.gpg \
  > /srv/backups/shop.sql.gz.gpg.sha256
~~~

After transfer, verify the destination checksum against a manifest delivered through a trusted channel. If the threat model includes an adversary able to alter both files and manifests, plain checksums are not enough to authenticate origin; use digital signatures or a key-protected MAC.

### 6.2. Recovery Drills

Schedule drills on an isolated host or environment running a compatible MySQL version. A drill should verify:

1. Full backups and all dependent incrementals can be retrieved.
2. Sufficient binary logs can be fetched for the target recovery point.
3. Keys or passphrases can be retrieved without relying on the failed primary server.
4. All data can be decrypted and decompressed.
5. Recovery tooling completes without unresolved errors.
6. Schemas, tables, indexes, triggers, routines, events, and required privileges restore within scope.
7. Data validation queries and business checks return expected results.
8. Actual duration meets RTO and recovered data point meets RPO.

Measure time from starting backup retrieval until the application can serve traffic. Record transfer, decryption, decompression, prepare, restore, binary log replay, and post-recovery verification times. If RTO is missed, adjust backup sizing, recovery infrastructure, compression level, bandwidth, or runbook steps.

### 6.3. Commonly Overlooked Components

When building a backup inventory, also check:

- Data and schema structures.
- Triggers, stored procedures, functions, and events.
- Accounts, roles, grants, and required authentication settings.
- MySQL configuration such as replication parameters, binary logging, and critical operational variables.
- Binary logs alongside matching GTID metadata or coordinates.
- Key material/keyrings if data or backups rely on encryption.
- Certificates, TLS configuration, and details needed for secure connections.
- Deployment docs, startup ordering, and recovery runbooks.

Do not toss secrets into an ordinary backup bundle without classification and encryption. Keyrings, keys, and credentials need separate backup workflows, separate permissions, and matching recovery tests.

## 7. Sample End-to-End Workflow from Creation to Archival

A workflow can be standardized into stages:

| Stage | Actions | Evidence to Record |
|---|---|---|
| Preparation | Confirm schedule, scope, capacity, MySQL state, and backup account privileges | Job ID, timestamp, host, backup type |
| Creation | Run logical or physical backup per chosen method | Logs, exit code, snapshot metadata |
| Compression | Use benchmarked algorithm and compression level | Pre/post sizes, duration, CPU usage |
| Encryption | Encrypt files and reference key version | Algorithm, key ID, encryption status |
| Verification | Check format, checksums, and decryptability | Checksums, check outcomes, warnings |
| Off-host copy | Transfer to independent storage | Destination path/object ID, remote checksum |
| Retention application | Tag expiration date, immutability lock, and purge policy | Retention class, expiration date |
| Drill | Periodically restore and validate business flows | Actual RTO, recovery point, findings |

Each copy should carry enough metadata for an on-call operator to know: source MySQL host, version, start/end timestamps, backup type, database scope, GTID or binlog coordinates, compression method, encryption algorithm, key ID, checksum, remote copy location, and expiration date. Never record passwords or secret keys inside metadata.

## 8. Troubleshooting Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Compressed file larger than expected | Data already compressed or low compression level | Measure ratios by data type; avoid raising compression if CPU or RTO suffers |
| Slow backup, high CPU load | Compression level too aggressive or competing with MySQL | Lower compression level, throttle resources, or schedule in an appropriate window |
| Encrypted file fails to decrypt | Wrong passphrase, missing key, wrong key version, or unreachable keyring | Look up key ID and key recovery procedure; test on an isolated copy |
| Source and destination checksums differ | Incomplete transfer, file tampered/corrupted, or mismatched manifest | Re-transfer from verified source, inspect logs, and regenerate manifest over trusted channel |
| Remote copy deleted alongside primary | Shared administrative account/permissions or missing immutability | Separate accounts and admin domains; enable versioning/retention locks |
| Cannot PITR to target time | Missing binary logs, gaps in log chain, or missing position metadata | Audit log chain, GTIDs/coordinates, and retention; fix log shipping pipeline |
| Restore exceeds RTO | Backup too large, slow transfer, under-resourced host, or manual steps | Profile each phase, optimize bandwidth, backup tooling, and recovery host |
| Restored database missing objects or privileges | Dump scope excluded routines/events/users/grants or config metadata | Expand inventory checklist and validate with post-restore checklist |

When a backup fails, never mark the job successful simply because a destination file exists. Inspect exit codes across the entire pipeline, logs, sizes, checksums, and replication/upload status. If a copy is suspect, preserve it for investigation per policy, take a fresh copy, and verify recovery before treating it as the sole baseline.

## 9. Self-Check

**Scenario 1:** An SQL dump is compressed with `gzip` and then encrypted. Why should compression happen before encryption?

**Hint:** Encrypted data has high entropy and resists compression. Compressing first usually achieves much better size and transfer time reductions.

**Scenario 2:** A company retains encrypted backups for 12 months but only retains decryption keys for 3 months. What is the risk?

**Hint:** Older backups may remain intact yet become impossible to decrypt. Key material and key retrieval capability must be maintained for at least the entire lifecycle of associated backups.

**Scenario 3:** A MySQL server has daily full backups, but binary logs are kept for only two days. A data error is discovered after one week. Is PITR right before the error still possible?

**Hint:** Only if a valid backup and a continuous chain of binary logs from that backup checkpoint to the target time still exist. If required logs have been purged, replay cannot reach that point.

**Scenario 4:** Backups are synced to another directory on the same server under the same administrative account. Which incidents does this protect against, and what is missing?

**Hint:** It may help recover from certain local accidental file deletions, but it provides no independent failure boundary against hardware failure, ransomware, or compromised admin credentials. You need copies in an independent server/account/region plus an immutable or offline copy.

**Scenario 5:** Backup checksums on the source host and object storage match. Does this prove the database can be recovered?

**Hint:** No. Checksums only verify file integrity against a manifest. You must decrypt, decompress, test-restore, and verify both data and recovery time.

## 10. Key Takeaways

- Compression reduces storage and bandwidth at the cost of CPU; measure both backup and restore durations.
- Compress before encrypting because encrypted data scarcely compresses further.
- TLS, disk encryption, tablespace encryption, and backup file encryption protect distinct layers.
- Decryption keys must be managed independently and retained throughout the full lifetime of associated backups.
- Retention must honor dependencies among fulls, incrementals, and binary logs; PITR needs a continuous log chain plus position metadata.
- Off-host copies require independent failure domains and administrative privileges; immutable/offline copies guard against unauthorized deletion or tampering.
- Checksums, decryption checks, and decompression checks are necessary steps; only a test restore proves recoverability.
- Run periodic drills, measure actual RPO/RTO, and update runbooks whenever infrastructure or MySQL versions change.
