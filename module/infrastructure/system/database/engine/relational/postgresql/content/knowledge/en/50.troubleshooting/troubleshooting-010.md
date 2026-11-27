# Checksum Errors, Suspected Data Corruption, and Preserving Evidence

Checksums are a mechanism that helps PostgreSQL detect certain forms of page-level corruption. When PostgreSQL reports a checksum mismatch, raises a page read error, or shows signs of data inconsistency, the first priority is preserving state and evidence so the incident scope can be determined. Rushing into repair actions can overwrite corrupted pages, alter WAL, erase onset timestamps, or render the sole remaining readable copy unrecoverable.

This lesson explains how to recognize checksum warnings, gather relation and block information, inspect clusters and backups, distinguish page corruption from index corruption or logical data errors, and choose safe recovery from a verified copy. Examples assume PostgreSQL runs on operator-managed servers; specific paths, OS permissions, and commands must be adapted to your actual version and platform.

## 1. Distinguishing Checksums, Page Corruption, and Logical Data Corruption

PostgreSQL stores data in fixed-size pages, typically 8 KB. Tables, indexes, and many other storage objects are organized into pages inside relation files. When data checksums are enabled, PostgreSQL computes a checksum for each data page and verifies it when reading the page back from storage.

Checksums help detect unexpected modifications to page contents. They are not a copy of the data, cannot repair pages, and do not prove the entire database is intact. A cluster with checksums enabled can still suffer application logic bugs, accidental data loss, inconsistent indexes, WAL errors, or corruption outside what data page checksums cover.

Distinguish these problem categories:

| Problem Type | Common Symptoms | Appropriate Check Mechanism |
|---|---|---|
| Data page checksum mismatch | PostgreSQL reports calculated checksum differs from stored page checksum | Server logs, `pg_stat_database` if version supports it, `pg_checksums` while cluster is offline |
| Structurally corrupted page | Invalid page header, tuple, or page layout | Logs, specialized page inspection tools, `amcheck`, and analysis on a copy |
| Inconsistent index | Index points to invalid tuples, lookup errors, or `amcheck` errors | `amcheck` extension; comparing index against heap |
| Invalid WAL or backup | Recovery failure, missing WAL, or backup files failing manifest verification | Recovery logs, `pg_verifybackup`, WAL checks, and restore testing |
| Logical data error | Wrong values while pages and checksums remain valid | Business checks, constraints, audit trails, and change history |
| Storage/OS failure | I/O errors, device resets, filesystem or kernel errors | OS logs, storage tools, and hardware diagnostics |

A checksum mismatch indicates the read page does not match its stored checksum. It is evidence requiring investigation, not a root cause by itself. The cause could involve storage devices, controllers, RAM, caches, filesystems, power loss, software bugs, file copy mistakes, or another component in the data path.

If checksums were not enabled when the cluster was initialized, PostgreSQL cannot use data page checksums to detect such discrepancies. Queries succeeding does not prove data has never been corrupted.

## 2. Recognizing Incident Symptoms

Symptoms to record include:

- PostgreSQL logs reporting `page verification failed` or `checksum mismatch`.
- `invalid page`, `invalid page header`, or relation block read errors.
- Backends reporting I/O errors, unexpected zero pages, or undecodable data.
- PostgreSQL unable to read a specific table, index, or relation.
- Crash recovery failing or reporting errors while reading WAL.
- Replicas or backup jobs reporting page read, checksum, or WAL errors.
- OS logs recording I/O errors, filesystem errors, controller resets, or storage device timeouts.
- Applications receiving anomalous results, data decoding failures, or constraint violations on a specific dataset.

An example message may look like:

~~~text
WARNING:  page verification failed, calculated checksum ...
          but expected ...
ERROR:    invalid page in block 42 of relation base/16384/2619
~~~

Exact wording varies by version, context, and error type. Save the verbatim log lines, timestamp, process ID, database, user, client, and relation path if present. Never copy only the final error line because preceding lines often contain root causes such as I/O or recovery errors.

Even a single occurrence warrants investigation. If the same block fails repeatedly across reads, nodes, or copies, severity and blast radius may differ. Never dismiss a single error as harmless noise.

## 3. Data Checksums in PostgreSQL

Data checksums are configured at the cluster level. For a new cluster, enable them at initialization:

~~~bash
initdb --data-checksums -D /var/lib/postgresql/data
~~~

The path above is illustrative. When initializing via service management tooling, container images, or cloud platforms, use the corresponding configuration mechanism.

You can check checksum status from SQL:

~~~sql
SHOW data_checksums;
~~~

Or inspect the control file:

~~~bash
pg_controldata /var/lib/postgresql/data
~~~

In `pg_controldata` output, look for `Data page checksum version`. A value of `0` usually means data checksums are disabled; a non-zero value indicates the active checksum version. Verify against documentation for your running major version.

Data checksums have important limitations:

- They protect data pages verified by PostgreSQL's checksum mechanism.
- They do not replace WAL checksums, backup manifests, or storage-layer checksums.
- They do not detect logical errors in application data.
- They do not repair corrupted pages.
- They do not prove the disk itself is at fault; corruption can enter at any layer in the data path.
- Enabling checksums on an existing cluster requires major-version support and an offline cluster.

Starting in PostgreSQL 12, `pg_checksums` can check a cluster or enable/disable data checksums on a cleanly stopped cluster, depending on state and version. Never run this tool while the server is running. When enabling or disabling, follow documentation for your exact major version, confirm a clean shutdown, and ensure a verified backup exists.

## 4. Preserving Evidence Before Deep Investigation

When corruption is suspected, treat the original cluster as forensic evidence. The first objective is preserving data, logs, WAL, and configuration as of the incident time.

A practical handling sequence:

1. Record discovery time and reporter; note timezones and time synchronization across hosts.
2. Identify the affected service, database, relation, block, and failing operation.
3. Collect PostgreSQL logs, OS logs, storage logs, monitoring data, and application logs.
4. Record the state of primary, replicas, backups, recovery, and running jobs.
5. Take a snapshot or incident backup using a consistency mechanism supported by storage and PostgreSQL.
6. Keep one immutable original copy, restrict access permissions, and record checksums of exported evidence files.
7. Perform analysis and recovery experiments on a separate working copy.

Never delete logs, WAL, or old backups during investigation. Never overwrite the original cluster with a restore before preserving required snapshots or copies. Never run write operations that might alter suspect pages before securing evidence.

### 4.1. Snapshotting While PostgreSQL Is Running

A volume snapshot taken while writes occur may only be crash-consistent. It captures a state akin to a sudden power loss and requires WAL recovery when starting a clone. A crash-consistent snapshot is still valuable when created via well-understood storage mechanisms, though it must not be treated as a verified, ready-to-serve backup.

If your platform supports application-consistent snapshots, use PostgreSQL-integrated mechanisms or supported backup workflows. Depending on tooling, this may require coordinating backup mode, filesystem freezes, or stopping services. Never invoke filesystem freezes or stop processes without understanding application impact.

If a clean shutdown is needed to run `pg_checksums`, preserve the original state or snapshot per incident procedure first. Only then stop the cluster in a controlled manner and run the tool against a working copy. During an active incident, protecting data and recoverability takes priority over immediately running an offline check on the sole source copy.

### 4.2. What to Preserve

| Evidence Group | Contents to Collect |
|---|---|
| PostgreSQL logs | Logs before, during, and after the error; PID; database; role; client; verbatim messages |
| Control and configuration | Server version; `pg_controldata`; `postgresql.conf`; `pg_hba.conf`; included configs; checksum status |
| Relation | Schema, table/index name, OID, filenode, file path, and reported block |
| WAL and recovery | Relevant WAL segments, timeline, checkpoints, recovery status, and archive logs |
| Replicas | Replication state, replay LSN, lag, and errors on every node |
| Backups | Backup manifests, creation timestamps, backup type, required WAL, and last restore test result |
| Operating system | Kernel logs, filesystem logs, I/O errors, device resets, SMART, or cloud storage vendor reports |
| Application | Request ID, business action, input payloads, timestamps, and returned errors |

Evidence may contain personal data, SQL queries, account names, or connection details. Store it in access-restricted locations; redact secrets when sharing with teams that do not need them. Keep raw original logs untouched and produce separate redacted copies for discussion.

### 4.3. Creating a Working Copy for Analysis

When using block storage snapshots, record snapshot ID, source volume, timestamp, storage region, and snapshot state. When copying files, record tooling, timestamps, server state, copied files, and copy hashes.

Never copy a live data directory with plain file copy commands and treat it as a valid physical backup. Files change mid-copy, yielding an inconsistent dataset. Use `pg_basebackup`, properly coordinated snapshots, or supported backup tools.

Keep at least one copy read-only or write-protected. Run analysis on a separate copy so experiments, recovery attempts, or repair steps never alter original evidence.

## 5. Gathering Information from PostgreSQL

If the server is still running and administrative queries work, gather facts using read-only queries. Avoid broad scans or heavy operations on an impaired system if they add load.

### 5.1. Version and Checksum Configuration

~~~sql
SELECT version();

SHOW data_checksums;
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW log_destination;
~~~

Some settings may be restricted or differ on managed PostgreSQL services. Save results alongside server version and collection timestamp.

### 5.2. Checksum Statistics

On versions providing checksum statistics columns, query:

~~~sql
SELECT
    datname,
    checksum_failures,
    checksum_last_failure
FROM pg_stat_database
ORDER BY checksum_failures DESC NULLS LAST;
~~~

`checksum_failures` and `checksum_last_failure` exist in modern PostgreSQL versions, though do not assume every older version supports them. If the query reports missing columns, note the version and rely on server logs and corresponding tools.

This counter is server-level statistical data. It does not replace pinpointing relations and blocks, nor is it sole proof of corruption scope. Record before-and-after values across checks if tracking whether new failures occur.

### 5.3. Identifying Relations and File Paths

If the failing table or index is known, retrieve relation details:

~~~sql
SELECT
    c.oid,
    n.nspname AS schema_name,
    c.relname,
    c.relkind,
    pg_relation_filenode(c.oid) AS filenode,
    pg_relation_filepath(c.oid) AS relation_path,
    pg_relation_size(c.oid) AS relation_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'orders';
~~~

A large relation can span multiple segment files. Forks such as `main`, `FSM`, `VM`, and `init` also have distinct roles. `relation_path` locates the file inside the data directory; never infer a table name from an old filenode number alone because filenodes change after DDL or table rebuilds.

If logs report a block number, record the exact block alongside `relation_path`. Never use one relation's block number to inspect another relation's file.

### 5.4. Connection and Replication Status

Collect active connections:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start
FROM pg_stat_activity
ORDER BY backend_start;
~~~

On the primary, check WAL senders:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

On standbys, inspect recovery and receiver status with version-appropriate views. Note that active replication does not prove a replica is uncorrupted; inspect each node's logs and backups independently.

## 6. Checking a Cluster with `pg_checksums`

`pg_checksums` is an offline utility for verifying data page checksums across a cluster. It is useful for determining how many pages fail checksum verification in a data directory.

Before running, ensure:

- You use `pg_checksums` from the cluster's exact major version.
- You specify the exact data directory.
- PostgreSQL is cleanly shut down.
- A snapshot or original copy has already been preserved.
- You run against a working copy if the original cluster is the sole evidence.
- Sufficient disk I/O headroom and time exist, as the scan reads all data files.

Example verification:

~~~bash
pg_checksums --check -D /var/lib/postgresql/data
~~~

This command is illustrative. Depending on platform, you may need to run it as the PostgreSQL OS user or pass the full binary path. Never run it on a running cluster.

Save output intact, including blocks scanned, failure count, affected files, exit code, and duration. If the tool reports checksum mismatches, record affected files and blocks and correlate with server logs. Finding zero errors only shows no mismatches occurred within the scope checked; it does not prove the cluster is free of logical corruption or unread errors.

### 6.1. Enabling Checksums on an Existing Cluster

Some PostgreSQL versions support `pg_checksums` to enable checksums on an existing cluster when the server is cleanly stopped and meets utility prerequisites:

~~~bash
pg_checksums --enable -D /var/lib/postgresql/data
~~~

Never treat `--enable` as a fix for existing checksum errors. It merely changes cluster checksum state per supported procedure; it does not repair corrupted page contents. Verify backups, version, and cluster state before executing.

Likewise, `--disable` is not an incident resolution. Disabling checksums removes future detection of divergent pages on subsequent reads. Only change checksum state under an approved operational plan with full understanding of impact.

## 7. Checking Backups and WAL

A backup is only useful if it restores cleanly. A backup with a manifest and checksums helps detect files altered or missing since backup creation.

For backups created in formats supporting backup manifests, use `pg_verifybackup`:

~~~bash
pg_verifybackup /backups/basebackup_2026_11_14
~~~

Use a tool version compatible with the backup and server. It compares files against the backup manifest and performs version-supported WAL checks. Save output and exit code. Even a backup that passes verification must be test-restored in an isolated environment to confirm end-to-end recoverability.

A backup manifest has file-level checksums, distinct from PostgreSQL's internal data page checksums. Manifest verification does not replace running `pg_checksums` on a stopped cluster or checking logical data consistency.

### 7.1. Retaining Required WAL

WAL lets PostgreSQL replay changes after a checkpoint and enables point-in-time recovery given a valid base backup and contiguous WAL chain. When corruption is suspected, do not delete or recycle WAL archives under normal retention policies before identifying the investigation window.

Record:

- Relevant timelines and checkpoints.
- Available WAL segments in the archive.
- Windows where archiving was missing or broken.
- Final LSNs on primary and replicas.
- Logs covering WAL write, flush, archive, or replay errors.

`pg_waldump` can read and inspect WAL records from relevant files or segments. It is an analytical tool; never edit WAL or alter control files manually. Interpret output according to PostgreSQL version and transaction context.

### 7.2. Test Restores

Restore backups onto a separate host or isolated data directory. When using PITR, select the stop point from evidence: when page errors began, when anomalous data modifications occurred, or when an incident-triggering operation ran. Never pick an arbitrary timestamp solely because the latest backup looks runnable.

After restoring:

1. Confirm PostgreSQL starts and completes recovery.
2. Inspect server logs and check for page errors.
3. Run offline checksum verification when appropriate.
4. Check indexes and relation structures with appropriate tools.
5. Run business validation queries checking counts, totals, and constraints.
6. Confirm the application can read required data.
7. Document the restore results and recovered data point-in-time.

Switch production traffic to a recovered instance only after operational sign-off and confirmed data validation.

## 8. Distinguishing Heap Errors, Index Errors, and Logical Data Errors

An error querying a table does not necessarily originate in the heap table itself. Queries may traverse an index; a corrupted index can surface errors only for specific query plans. Conversely, a corrupted heap page can impact many different queries.

### 8.1. Checking Indexes with `amcheck`

The `amcheck` extension provides functions to verify consistency of certain index structures, particularly B-trees. For example, after installing the extension in a test database or appropriate environment:

~~~sql
CREATE EXTENSION IF NOT EXISTS amcheck;

SELECT bt_index_check('public.orders_pkey'::regclass);
~~~

`bt_index_check` performs a B-tree structural check. Deeper checks like `bt_index_parent_check` also verify parent-child page relationships, at the cost of higher resource use and stronger locks. Read `amcheck` documentation for your exact version before running in production.

If index corruption is suspected, check the specific index and compare against the heap on a copy. `REINDEX` can rebuild a corrupted index when the heap remains trustworthy. It does not repair corrupted heap pages, cannot restore lost tuples, and should not be run on the original cluster before preserving evidence.

### 8.2. Checking the Heap

Some PostgreSQL and `amcheck` versions provide heap-page verification capabilities. Scope, function signatures, and options depend on version. Use them only after reading version documentation and understanding read load, locking, and error reporting behavior.

If errors target a specific block, a PostgreSQL specialist may inspect raw pages using `pageinspect` or specialized tooling on a copy. Never manually edit page bytes or patch relation files with a hex editor.

### 8.3. Checking Logical Data

If checksums and page structures show no errors yet the application detects wrong data, inspect the logical layer:

- Constraints and foreign keys.
- Business rules and transaction boundaries.
- Audit logs and change history.
- Migrations, batch jobs, and manual interventions.
- Synchronization across primary, replicas, and downstream systems.
- Input payloads and type conversions.

A valid checksum only proves the page matches its stored checksum. A valid `UPDATE` statement writing wrong business values still produces a page with a valid checksum.

## 9. Actions to Avoid Before Preserving Evidence

Certain options allow PostgreSQL to keep running despite corrupted pages, but they are not safe repair tools.

### 9.1. Do Not Enable `ignore_checksum_failure` to Keep Serving Business Traffic

`ignore_checksum_failure` lets PostgreSQL proceed past certain checksum failures instead of aborting the query. This can cause applications to read corrupted data or return untrustworthy results. Never use it as a production workaround or to silence alerts.

If a specialist must use this option for emergency data extraction, run it strictly on a working copy with a defined target and scope, after preserving original evidence.

### 9.2. Do Not Use `zero_damaged_pages` as Routine Repair

`zero_damaged_pages` instructs PostgreSQL to replace damaged pages with zeroed empty pages during certain read paths. That behavior discards the data on those pages. It does not recover original contents and can cause permanent data loss.

If an emergency data-salvage procedure must try it, run strictly on an isolated copy, record exact settings, and accept that rows on zeroed pages are lost. Never apply it to the sole original copy.

### 9.3. Do Not Run `pg_resetwal` to Fix Checksum Mismatches

`pg_resetwal` addresses corrupted WAL or control state as a last resort in narrow recovery scenarios. It does not repair data page checksums. Misusing it can start the cluster in a transactionally inconsistent state and compound corruption.

Never run `pg_resetwal` simply because PostgreSQL reported a checksum mismatch or unreadable block. Any use requires assessment by experienced PostgreSQL specialists, preservation of the original copy, and explicit acceptance of data-loss risk.

### 9.4. Do Not Rebuild or Vacuum Arbitrarily

`VACUUM FULL`, `CLUSTER`, `REINDEX`, `ALTER TABLE` rewrites, or heavy write jobs read and rewrite many pages. They alter forensic evidence, add load, and can spread failures mid-operation.

`REINDEX` is appropriate only once corruption is confirmed isolated to an index and the heap is trustworthy. Never use it to treat heap or storage corruption. Never run `VACUUM FULL` just to see if warnings go away.

## 10. Phased Incident Handling Workflow

Organize incident response into clear phases so everyone understands current state and avoids conflicting actions.

### Phase A — Detection and Containment

- Record verbatim error messages, timestamps, and involved queries.
- Identify affected databases, relations, blocks, primary/replicas, and applications.
- Restrict further writes to suspect areas if safe to do so.
- Notify DBAs, SREs, and application owners per incident procedure.
- Do not delete logs, WAL, or backups, and do not run repair commands prematurely.

Decisions to halt traffic or switch applications to read-only must follow real impact and operational runbooks. Never kill all backends or shut down hosts before assessing effects on transactions, recovery, and evidence collection.

### Phase B — Preservation

- Collect logs, configuration, statistics, and relation metadata.
- Preserve WAL and timeline information.
- Snapshot or create backups via consistent mechanisms.
- Keep an immutable original copy and provision a working copy.
- Record hashes, sources, timestamps, and operators for every artifact collected.

### Phase C — Diagnosis

- Confirm whether checksums are enabled.
- Correlate PostgreSQL errors with OS I/O and storage logs.
- Run `pg_checksums` on a cleanly stopped cluster or appropriate copy.
- Verify backups with `pg_verifybackup` and perform test restores.
- Use `amcheck` or specialized tooling to separate index, heap, and logical errors.
- Inspect replicas independently—never assume replicas are unaffected.

### Phase D — Choosing Recovery

Common paths:

| Scenario | Options to Consider |
|---|---|
| Only index corrupted, heap trustworthy | Rebuild index on a copy or per DBA-verified procedure |
| Single heap page corrupted, valid backup and WAL exist | Restore/PITR to a new cluster, then reconcile data |
| Primary has storage failure, replica independently verified clean | Evaluate HA failover per runbook and validate replica data |
| Backup manifest invalid or WAL missing | Locate earlier backup with complete WAL chain; determine achievable RPO |
| Multiple pages corrupted or cluster fails recovery | Preserve original, test earlier backups/PITR, escalate to specialists |
| Logical data wrong while page checksums valid | Recover from business audit history or PITR prior to the bad operation |

Failover is not an automatic cure for corruption. If the cause was a logic bug or bad write replicated to standbys, replicas carry the same bad data. If the cause was localized storage hardware failure on one node, a replica might be clean, yet must still be independently verified before promotion.

### Phase E — Validation and Closure

- Restore into a new cluster or replacement environment.
- Run checksum, structural, and business validation checks.
- Confirm backups, WAL archiving, and restore procedures work.
- Monitor logs, replication, latency, and query errors after shifting traffic.
- Document identified root cause, impact, data loss (if any), recovery actions, and preventive measures.
- Retain evidence per retention policy and postmortem requirements.

## 11. Evidence and Decision Matrix

This table helps teams document justification before choosing a recovery path:

| Evidence | Question to Answer | Impact on Decision |
|---|---|---|
| Block checksum mismatch | Which relation and block are affected? Does it reproduce on a copy? | Identifies exact pages to investigate |
| I/O or filesystem logs | Were there device or filesystem errors at the same time? | Guides storage/OS investigation |
| `pg_checksums` | How many blocks fail on an offline copy? | Defines cluster-wide checksum mismatch scope |
| `pg_stat_database` | How did checksum failure counters change? | Tracks symptoms on servers supporting these columns |
| Backup manifest | Do backup files match the manifest? | Evaluates backup file integrity |
| WAL archive | Is the WAL chain contiguous and readable? | Assesses PITR viability |
| Replicas | Do replicas share the error or bad data? | Assesses failover safety |
| `amcheck` | Does the index have structural errors? | Determines whether index rebuild is viable |
| Business validation | Does data satisfy rules and reconciliation totals? | Confirms correctness post-recovery |

Never conclude root cause from a single log line. A reliable conclusion correlates timestamps, relations, blocks, checksum status, storage logs, backups, WAL, replicas, and restore test outcomes.

## 12. Prevention and Pre-Incident Readiness

Most incident value comes from preparation done before corruption strikes.

### 12.1. Enable Checksums at Cluster Initialization

For new clusters, consider enabling data checksums at `initdb`. For existing clusters, assess enabling via `pg_checksums` on your running version and schedule appropriate downtime. Never treat enabling checksums as a substitute for backups.

### 12.2. Regularly Test Backups

- Take backups aligned with agreed RPO/RTO targets.
- Retain WAL archives and test point-in-time recoverability over time.
- Verify backup manifests when available.
- Perform periodic restore drills in isolated environments.
- Protect backups with separate access controls, encryption, and off-domain copies.
- Record actual restore times and any remaining manual dependencies.

An untested backup is merely an assumption about recoverability.

### 12.3. Monitor Storage and OS Health

Track I/O latency, read/write errors, filesystem errors, capacity, controller resets, SMART attributes, or cloud storage health reports. Synchronize system clocks for log correlation. If hardware errors occur, inspect all affected volumes, nodes, and copies.

### 12.4. Keep Operational Runbooks Clear

Runbooks should document:

- Owners and incident escalation channels.
- How to collect logs and metadata.
- Snapshot, backup, and WAL archive locations.
- Procedure to clone a working investigation environment.
- Version-exact verification commands.
- Criteria for stopping traffic, failing over, and restoring.
- Approval gates for operations that alter data.
- Policies for evidence retention, access, and disposal.

## 13. Evidence Preservation Checklist

When a checksum mismatch or suspected corruption appears, record:

- [ ] Saved verbatim PostgreSQL logs with timestamp, PID, database, role, and client.
- [ ] Recorded PostgreSQL version, checksum status, and `data_directory` path.
- [ ] Identified relation, filenode, `relation_path`, and block if provided by logs.
- [ ] Saved OS, filesystem, storage, monitoring, and application logs.
- [ ] Recorded primary, replica, WAL archive, and backup states.
- [ ] Created a snapshot or copy using a supported consistency mechanism.
- [ ] Kept an immutable original copy, restricted access, and recorded evidence hashes.
- [ ] Ran deep diagnostics strictly on a working copy.
- [ ] Verified backups and ran test restores in an isolated environment.
- [ ] Avoided checksum-ignoring or page-zeroing options on the original source.
- [ ] Avoided `pg_resetwal`, `REINDEX`, or rewrite commands before securing evidence and copies.
- [ ] Documented operators, commands, outputs, timestamps, and recovery decisions.

A checksum mismatch is a signal for disciplined investigation. Preserving pages, logs, WAL, backups, and configuration state lets DBAs separate storage errors, structural corruption, and logical errors—enabling an evidence-backed recovery while minimizing further data loss.
