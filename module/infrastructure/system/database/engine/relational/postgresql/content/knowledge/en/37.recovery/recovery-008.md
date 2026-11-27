# Restoring Into an Isolated Environment Before System Replacement

When PostgreSQL suffers an incident, restoring a backup straight into the production slot and immediately opening traffic can turn a data incident into a far larger service outage. The backup may be from the wrong point in time, the WAL chain may have gaps, roles/extensions may not be ready, or the recovered data may still contain the exact accidental deletion the operations team is trying to fix. For logical errors, replacing the primary before verifying the recovery point can also wipe out valid transactions recorded after the desired recovery time.

A safer workflow is **restoring into an isolated recovery environment, inspecting and verifying the data, and only then deciding whether to extract specific data or replace the live system**. An isolated environment lets DBAs build a copy from a logical dump or physical backup, replay WAL to a recovery target, verify schemas and business invariants, compare against any still-healthy source, and rehearse cutover without allowing applications or users to accidentally write into the recovering cluster.

This approach is especially critical when handling accidental deletions, logical corruption, ransomware, migrations, major version upgrades, or DR drills. The goal is maintaining clear boundaries between **technical recovery**, **data verification**, **replacement decision**, and **traffic cutover**. Each stage has its own completion criteria, owner, and evidence.

This lesson belongs to the **Recovery** chapter of the **Database Engine Relational PostgreSQL** module. It focuses on restoring into an independent environment before replacing the live system, from preparing artifacts through validation, promotion, cutover, and returning to normal protection.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why restoring into an isolated environment is necessary before replacing a primary.
- Distinguish test restores, isolated recovery, selective data recovery, and production cutover.
- Select the appropriate logical dump, physical base backup, WAL/PITR, or standby source.
- Prepare the required PostgreSQL version, extensions, roles, tablespaces, keys, and configuration.
- Isolate networks, credentials, DNS, application clients, and external side effects.
- Restore a logical database using `pg_restore`/`psql` into a fresh target.
- Restore a physical backup and replay WAL to a recovery target.
- Use recovery pause to inspect data before promoting when the PITR strategy supports it.
- Verify schemas, constraints, indexes, sequences, grants, RLS, and business data.
- Handle recovery points for logical errors and reconcile data with a still-running production primary.
- Plan fencing, write freezes, promotion, and cutover to prevent split-brain.
- Measure RPO/RTO, rehearse runbooks, and preserve recovery evidence.
- Protect sensitive data in recovered copies and clean up isolated environments afterward.

## 2. Why Restore Into an Isolated Environment?

A successful backup only proves the tool produced an artifact per its own mechanism. It does not prove the artifact represents the right point in time, includes all dependencies, is restorable, or contains business-valid data.

### 2.1. Avoid Replacing Production with the Wrong Recovery Point

During PITR, choosing the wrong timestamp or timeline can roll the database back past a batch of valid transactions. Restoring into a dedicated environment lets you inspect state before touching production endpoints.

### 2.2. Detect Backup Failures Early

A backup might miss a WAL segment, manifest, tablespace, extension, or encryption key. Discovering this only after production has been replaced increases downtime and risk.

### 2.3. Enable Investigation of Logical Errors

When a user accidentally drops a table, you rarely need to roll all of production back prior to that operation. You can restore an isolated PITR instance, extract the table/rows to rescue, and merge them into the live system after checking dependencies.

### 2.4. Prevent Applications from Writing to an Unverified Database

A newly started cluster might accept connections before data is verified. If applications auto-connect via DNS/service discovery, they may generate transactions on the recovery copy before DBAs sign off.

### 2.5. Keep Current Production as a Reference Source

If the primary is still running and uncompromised, you can compare transactions after the recovery point, determine what to retain, what to recover, and how to merge.

## 3. Concepts to Distinguish

| Concept | Meaning | Expected Outcome |
|---|---|---|
| Backup verification | Inspecting artifacts/manifest/checksums | Knowing the backup appears complete and readable |
| Restore test | Restoring into a test environment | Proving the restore procedure executes |
| Isolated recovery | Recovering inside an isolated environment | A database ready for safe investigation/validation |
| PITR | Replaying WAL to a recovery target | Database at a chosen point in time |
| Selective recovery | Extracting a subset of data/objects | Rescuing targeted records |
| Promotion | Ending recovery/standby and enabling writes | Cluster becomes a writable primary |
| Cutover | Switching applications/traffic to target | New system serves live users |
| DR declaration | Decision to invoke disaster procedures | Incident managed under formal runbook |

### 3.1. Restore Test Is Not Cutover

A restore test can run in a subnet with no production applications. It does not change DNS, promote the main system, or open live traffic.

### 3.2. Isolated Recovery Can Be Read-Only

In some scenarios, the goal is solely reading pre-incident data and extracting a few records. The cluster can remain in recovery pause or allow only read-only access.

### 3.3. Cutover Is an Operational Decision

Promote/cut over only after verifying recovery point, data, dependencies, access privileges, write capability, and split-brain prevention.

### 3.4. Production Replacement Differs from Selective Merge

If a logical error affects one table, restoring the whole cluster and replacing the primary may be inappropriate. Selective merge keeps current production intact and brings rescued data in via controlled transactions.

## 4. Isolated Environment Model

A common design separates the production primary, backup storage, and an independent recovery target.

~~~text
                   Production environment
                 +-------------------------+
Application ---->| Current PostgreSQL      |
                 +------------+------------+
                              |
                       Base backup / dump
                              |
                              v
                 +-------------------------+
                 | Backup + WAL repository |
                 | offsite / immutable     |
                 +------------+------------+
                              |
                         restore copy
                              |
                              v
                  Isolated recovery network
                 +--------------------------+
                 | Recovery PostgreSQL      |
                 | separate data directory  |
                 | separate port/endpoint   |
                 +------------+-------------+
                              |
                       validation / extract
                              |
                     approved decision only
                              |
                  +-----------+-----------+
                  |                       |
             Selective merge          DR cutover
                  |                       |
                  v                       v
             Current primary       Recovered primary
~~~

### 4.1. Network Separation

The recovery instance should sit inside a dedicated subnet/VLAN/security group, allowing connections only from bastions or recovery operators. Block application subnets, public ingress, and automatic service discovery paths.

### 4.2. Credential Separation

Use dedicated roles for recovery. Never reuse application credentials that carry production write privileges. Secrets and KMS access must be available yet audited.

### 4.3. Storage and Data Directory Separation

Never restore over the PGDATA of a running primary. Use a dedicated host/VM/container/volume and explicit paths.

### 4.4. Endpoint and DNS Separation

The recovery cluster must have its own hostname/port. Never point production DNS aliases to it until a cutover plan is approved.

### 4.5. External Side Effects

Block email, payment gateways, webhooks, message consumers, scheduled jobs, ETL writers, and background workers. A recovery copy may contain pending jobs that fire immediately if applications connect.

## 5. Isolation Tiers by Objective

| Objective | Suggested Isolation Level | Write Access |
|---|---|---|
| Periodic backup testing | Lab/test network | Operator only |
| Accidental deletion investigation | Recovery subnet, no app clients | Read-only or controlled writes |
| Extracting tables/rows | Isolated DB + controlled export path | Operator per transaction |
| DR drill | Independent DR account/region | Runbook/automation only |
| Cutover preparation | Candidate environment, traffic still closed | Controlled write tests |
| Live primary replacement | Cutover network after fencing | Writes opened after approval |

### 5.1. Network Isolation

Ensure no route exists from production applications to the recovery instance. This prevents accidental client connections.

### 5.2. Identity Isolation

Only recovery roles may access the environment. Use separate IAM/DB roles, policy-compliant MFA/break-glass access, and audit logs.

### 5.3. Side-Effect Isolation

If you must run applications for testing, point email/payment/webhook settings to sandbox endpoints and disable consumers/schedulers. Never let tests trigger real external actions.

### 5.4. Data Isolation

If the environment is opened to developers/testers, address masking/anonymization. A restored copy of production still contains production data and is subject to equivalent security controls.

### 5.5. Isolation Does Not Mean Skipping Monitoring

Monitor disk, CPU, restore progress, logs, and network; only restrict which clients can connect.

## 6. Choosing the Recovery Source

Before restoring, determine which data source fits the failure mode and RPO.

### 6.1. Logical Dump

Use `pg_dump`/`pg_dumpall` when you need database/schema/table objects as of a snapshot. Suitable for selective restores, migrations, and small-to-medium databases.

### 6.2. Physical Base Backup

Use a base backup to recover the full cluster physically. Combine with a WAL archive when replaying past the base backup point.

### 6.3. PITR

Select a valid base backup and complete WAL chain/timeline, then configure a recovery target. This is the primary option when rewinding prior to an erroneous operation.

### 6.4. Standby or Replica

You can clone from a standby or promote a standby for HA, yet evaluate lag, timeline, and logical corruption. A standby does not replace backup history.

### 6.5. Managed Service Snapshots

You can restore a snapshot/PITR to a new instance using provider mechanisms. Check region, version, parameter group, extensions, IAM, quotas, and exact restore behavior.

## 7. Gathering Information Before Restoring

A recovery ticket/runbook should record at minimum:

- Incident ID and operator.
- Failure mode: host/disk/region loss, accidental deletion, corruption, ransomware, or drill.
- Incident timestamp and timezone.
- Approved RPO/RTO.
- PostgreSQL version, platform, and extension inventory.
- Backup ID, backup type, snapshot/LSN/time, and checksums/manifest.
- WAL segment range, timeline history, and archive location.
- Tablespaces and storage paths.
- Roles, ownership, grants, RLS, and secret/key references.
- Database size, WAL volume, expected restore duration.
- Recovery target and rationale.
- Network/identity isolation controls.
- Validation criteria and approvers.

### 7.1. Record the Recovery Point Explicitly

Never write "yesterday's backup." Record backup identifier, UTC timestamp, timezone, LSN/timeline if applicable, and WAL coverage.

### 7.2. Verify Artifacts Exist at the DR Site

A backup stored in the same storage account/region as the primary may be unavailable during a regional disaster. Verify using the DR identity and network.

### 7.3. Verify Checksums/Manifests

If the tool provides a manifest/checksum, verify before downloading/restoring. Checksums prove byte integrity, not business correctness.

### 7.4. Verify Encryption Keys

Test key access using the DR identity. Never wait until after restore finishes to discover a missing key or revoked permission.

### 7.5. Check Version and Extensions

Know the PostgreSQL major version, tool version, and extension binaries/versions. Physical restores normally require an environment compatible with the backed-up cluster.

## 8. Preparing the Target PostgreSQL Environment

The target must be capable of holding the data and running the workload to verify.

### 8.1. PostgreSQL Major Version

For physical restores, use a major version compatible with the base backup. Never treat a physical backup from one major version as a data directory for another major version. Logical migrations can cross major versions when objects/extensions are compatible.

### 8.2. Minor Version and Binaries

Use a minor release matching support and compatibility policies. Prepare binaries, shared libraries, locale/collation dependencies, and extension packages.

### 8.3. Extensions

List installed extensions in the database and install matching packages before restoring/starting. SQL extension metadata does not substitute for shared libraries on the host.

### 8.4. Locale, Encoding, and Collation

Logical database creation requires matching encoding/locale. Differing collation providers/versions can affect sort order, indexes, and query behavior.

### 8.5. Capacity

Provision space for data files, indexes, TOAST, WAL replay, temporary files, logs, and headroom. The restore target must not run out of disk mid-process.

## 9. Preparing Roles, Tablespaces, and Configuration

Logical dumps and physical backups cover different metadata scopes.

### 9.1. Global Objects

A single-database `pg_dump` does not include all cluster-level roles and tablespaces. Use `pg_dumpall --globals-only` to capture global objects per workflow.

### 9.2. Roles and Ownership

Verify login roles, memberships, role attributes, grants, default privileges, and ownership. Never grant superuser to application roles just to simplify a restore.

### 9.3. Password Verifiers and Secrets

When recovering role definitions, handle password verifiers per policy. Out-of-database secrets must be provisioned via a secret manager, never written into scripts or logs.

### 9.4. Tablespaces

Physical backups may reference tablespace locations. The target must prepare matching paths/permissions or mappings; never restore to nonexistent paths.

### 9.5. Server Configuration

Save/restore necessary settings in a controlled way, including memory, WAL, archiving, authentication, TLS, logging, and connection limits. Do not copy production configs verbatim if they contain paths, credentials, or network bindings unsuitable for an isolated environment.



## 10. Restoring a Logical Backup Into a New Database

Logical restore creates objects and loads data into a target database. Use a fresh database/cluster in the recovery environment with its own endpoint and block production applications from connecting.

### 10.1. Inspecting the Dump Before Restore

For a custom archive:

~~~bash
pg_restore --list appdb.dump
~~~

The TOC listing confirms the archive is readable and shows objects inside the backup. For plain SQL, inspect the file/header and use a test environment to run `psql`.

### 10.2. Restoring Global Objects When Needed

A workflow may capture globals separately:

~~~bash
pg_dumpall --globals-only --file=globals.sql
~~~

Restore globals onto a new target only after reviewing roles/tablespaces. If the target already has colliding role names, resolve conflicts per plan; never run blindly on an active cluster.

### 10.3. Creating an Empty Database

~~~bash
createdb --template=template0 --encoding=UTF8 recovery_app
~~~

This example uses UTF8; if production uses a specific locale/collation, create the database with matching platform-appropriate requirements. Locale syntax varies by OS and PostgreSQL version.

### 10.4. Restoring a Custom Archive

~~~bash
pg_restore --verbose --exit-on-error --dbname=recovery_app appdb.dump
~~~

If preserving ownership, roles, and grants, prepare global objects/roles first and do not carelessly pass owner-stripping options.

### 10.5. Restoring Plain SQL

~~~bash
psql -X --set ON_ERROR_STOP=on --dbname=recovery_app --file=appdb.sql
~~~

`ON_ERROR_STOP` tells `psql` to halt on SQL errors instead of silently continuing past failed objects.

## 11. Logical Restore: Parallelism and Object Selection

### 11.1. Parallel Restore

Custom and directory archives can support parallel restore:

~~~bash
pg_restore --jobs=4 --exit-on-error --dbname=recovery_app appdb.dump
~~~

Choose job count based on CPU, storage throughput, memory, and database size. Increasing jobs does not always speed up restores; many concurrent index builds can saturate disk I/O.

### 11.2. Directory Format

Directory format splits an archive into multiple files and suits parallel dump/restore per tool behavior. Copy the entire directory and preserve its structure.

### 11.3. Schema-Only Restore

~~~bash
pg_restore --schema-only --dbname=recovery_app appdb.dump
~~~

Useful for checking DDL, though it does not prove data is recoverable.

### 11.4. Data-Only Restore

~~~bash
pg_restore --data-only --dbname=recovery_app appdb.dump
~~~

The target must already have a compatible schema; constraints, triggers, and ordering can affect loading.

### 11.5. Selecting a Single Table

~~~bash
pg_restore --table=public.orders --dbname=recovery_app appdb.dump
~~~

Selective restore can omit dependencies such as types, sequences, functions, referenced tables, grants, or extension objects. It is usually safer to restore into a complete temporary database and extract the needed data from there.

## 12. Logical Restore: Ownership, Grants, and Constraints

### 12.1. --no-owner

`--no-owner` skips ownership-change statements in the archive and creates objects under the restoring role. Use when the target lacks original roles or when intentionally remapping ownership.

### 12.2. --no-acl

`--no-acl` skips `GRANT`/`REVOKE` statements in the archive. Use only when grants will be applied separately by policy; otherwise, post-restore privileges will differ from production.

### 12.3. --clean

`--clean` tells `pg_restore` to drop objects before recreating them. For an empty isolated target, this is usually unnecessary. If used on a populated database, it can drop objects unexpectedly.

### 12.4. --if-exists

Can be combined with `--clean` to avoid errors when an object does not exist yet, though it does not turn a destructive restore into a safe operation. Confirm target and scope first.

### 12.5. Constraint Validation

After restore, verify constraints exist and are valid. Do not conclude success solely from exit code 0 if logs contain warnings or options skipped objects.

## 13. Selective Recovery from an Isolated Database

When a logical error affects only a subset of data, the recovery copy can serve as a merge source.

### 13.1. Do Not Immediately Roll Back All of Production

Production may have accepted valid transactions after the error. Replacing the entire database with an older PITR copy would lose those transactions.

### 13.2. Restore Into a Temporary Database

Restore the logical dump or PITR cluster in a separate environment. Use an explicit name like `recovery_before_delete`, distinct from application database names.

### 13.3. Extract Tables or Rows

You can use `COPY`/`psql`, FDWs, table dumps, or queries over an isolated connection to extract data. Keep extraction artifacts with checksums and audit trails.

### 13.4. Review Dependencies

Rows may reference foreign keys, sequences, lookup tables, audit histories, or object storage keys. Determine ordering and completeness.

### 13.5. Merge Using Controlled Transactions

Use staging tables, unique keys, conflict rules, and clear transaction boundaries. Verify before/after row counts, duplicate handling, and business invariants.

## 14. Preparing for Physical Restore

Physical restore rebuilds a cluster from a base backup. This is the standard approach for PITR and recovering large databases.

### 14.1. Selecting the Base Backup

Choose a valid backup able to replay to the recovery target. Record backup ID, PostgreSQL version, timeline, start/end LSN, and tablespaces.

### 14.2. Verifying the WAL Chain

Ensure WAL segments from the base backup to the target are present, along with required timeline history files. Missing segments can stop recovery before the target.

### 14.3. Preparing a Dedicated Data Directory

Create an empty directory/volume with proper owner/permissions and ample space. Never restore over a running primary's data directory.

### 14.4. Tablespaces

Restore tablespaces into target-appropriate paths. When mapping/relocating, verify symbolic links and permissions per the backup tool.

### 14.5. WAL Directory and Archive Access

Prepare the local WAL directory, archive read permissions, and credentials/network for the recovery server to fetch WAL. Avoid giving the recovery server permission to delete from the source archive.

## 15. Restoring a Physical Base Backup

An example taking a base backup from a source server to a separate target:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --username=replicator \
  --pgdata=/srv/recovery/pgdata \
  --format=plain \
  --wal-method=stream \
  --progress
~~~

This illustrates a case where the source is still reachable. During a disaster, you normally restore from a backup repository using the chosen tool/catalog.

### 15.1. Replication Privileges

The role used by `pg_basebackup` needs appropriate privileges, and `pg_hba.conf` must allow the connection. Use short-lived credentials/secret managers per policy.

### 15.2. Never Take Backups from a Suspected Compromised Primary

If the failure mode involves ransomware or unauthorized access, use artifacts only from a verified clean backup domain.

### 15.3. --wal-method=stream

Streaming WAL during a base backup collects the WAL needed for backup consistency under `pg_basebackup`'s mechanism. It does not replace the WAL archive required for PITR past the backup point.

### 15.4. --write-recovery-conf / -R

This option generates configuration to run the instance as a standby connecting upstream. If the goal is standalone PITR archive recovery, do not use `-R` mechanically; verify recovery mode and signal files.

### 15.5. Verify Backup Completion

Check exit codes, logs, backup manifest, and file sizes. If the tool provides a verify command, run it before starting the target.

## 16. PITR: Configuring Archive Recovery

On PostgreSQL 12 and newer, recovery settings are placed in PostgreSQL configuration (e.g., `postgresql.conf` or `postgresql.auto.conf`) and a signal file triggers recovery. The legacy `recovery.conf` file is no longer supported in newer versions.

Sample configuration for an isolated target:

~~~conf
restore_command = 'cp /mnt/pg-archive/%f %p'
recovery_target_time = '2026-11-14 09:42:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Paths and commands depend on OS, storage backend, and backup tool. The command must return proper exit codes when a WAL file is absent and never overwrite the wrong destination.

### 16.1. recovery.signal

Create an empty `recovery.signal` file in the data directory to instruct PostgreSQL to perform archive recovery. Do not accidentally create `standby.signal` when the goal is standalone PITR rather than streaming standby operation.

### 16.2. restore_command

PostgreSQL invokes the command with placeholders like `%f` (filename to retrieve) and `%p` (destination path). Backup tools may use a wrapper command to download from object storage and decrypt.

### 16.3. recovery_target_time

Timestamps require an explicit timezone. Pick a target prior to the offending transaction based on audit/application logs and transaction commit semantics.

### 16.4. recovery_target_timeline

`latest` selects the newest timeline available in the archive. When recovering a specific historical branch, identify the right timeline and keep history files.

### 16.5. recovery_target_action=pause

Upon reaching the target, the server pauses recovery instead of auto-promoting. You can connect to inspect read-only state during recovery before deciding to promote.

## 17. Recovery Targets and Semantics

PostgreSQL supports multiple ways to specify a target, depending on version and recovery configuration:

- `recovery_target_time`: timestamp.
- `recovery_target_lsn`: log sequence number.
- `recovery_target_xid`: transaction ID.
- `recovery_target_name`: named restore point.
- `recovery_target_timeline`: timeline to follow.

### 17.1. Cross-Check Timestamps with Logs

Clock skew, timezones, and transaction commit timing can cause targets to land differently than expected. Use UTC or explicit timezone offsets.

### 17.2. Inclusive/Exclusive

`recovery_target_inclusive` controls whether the target transaction/record is included for applicable recovery targets. Read semantics for your target type and PostgreSQL version before selecting.

### 17.3. Named Restore Points

You can create a named restore point before a risky change using the appropriate SQL, then recover to that name if the WAL archive contains the record. Restore points do not help if the WAL segment was not protected.

### 17.4. Target Too Early

Can discard valid transactions you needed to keep. Restoring into an isolated environment lets you inspect and extract data before deciding to replace the primary.

### 17.5. Target Too Late

May have replayed the transaction causing corruption or accidental deletion. Rebuild from the same base backup with an earlier target or use another suitable recovery chain.

## 18. Starting and Monitoring PITR Recovery

After configuring the target and signal file, start PostgreSQL via the appropriate service/`pg_ctl`. Monitor server logs and recovery status.

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

### 18.1. pg_is_in_recovery

Returns `true` while the server remains in recovery/standby state. This is an essential check prior to promotion.

### 18.2. Replay LSN and Timestamp

Helps track replay progress, though the last transaction timestamp can appear stale during quiet workloads. Never treat a single value as proof that all WAL has replayed.

### 18.3. Server Logs

Look for archive recovery startup messages, WAL files requested/received, target reached, and recovery paused. `restore_command` errors typically appear in the logs.

### 18.4. When WAL Is Missing

Recovery may keep retrying to fetch a segment or stop once no further required WAL is available. Check archive paths, credentials, timeline history, and command output.

### 18.5. Do Not Open Production Traffic

During this stage, only recovery operators may connect. Never allow application pools or background jobs to hit the endpoint automatically.



## 19. Holding PITR in Pause State for Verification

When the recovery target is reached and `recovery_target_action` is `pause`, PostgreSQL stops replaying at that point. The cluster remains in recovery state, so permitted connections can read data without performing regular writes.

### 19.1. Confirming Recovery Is Paused

~~~sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
~~~

Cross-check outputs against log messages showing recovery target reached/paused. Do not rely merely on whether the server accepts connections.

### 19.2. Reading Data During Recovery

Use `SELECT` to inspect schemas, rows, and business invariants. To export data, use logical dump/`COPY` or read-only-compatible tools.

### 19.3. Never Run DDL/DML During Recovery Pause

You cannot create staging tables, adjust sequences, or run `ANALYZE` as writes on a cluster in recovery. If those actions are required, create a writable clone from the recovery point or promote the isolated copy once decided.

### 19.4. Resume or Promote?

If you need to replay further past the target, resume recovery per procedure. If the target is verified and you want the cluster to become primary, promote ends recovery at the current recovery point and starts a new timeline.

### 19.5. Do Not Promote Just to "Peek"

Promotion is a significant state transition. It creates a new timeline and complicates returning to another recovery point. Use read-only inspection first.

## 20. Validation: Verifying Database Structure

Having data from the right point in time yet missing objects or privileges can still break the application.

### 20.1. Checking Databases

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size,
    datallowconn,
    datistemplate
FROM pg_database
ORDER BY datname;
~~~

Compare database list and sizes against the backup catalog/expected inventory.

### 20.2. Checking Schemas and Tables

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

### 20.3. Checking Extensions

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Confirm matching extension binaries exist on the host, not just database metadata.

### 20.4. Checking Constraints

~~~sql
SELECT
    conrelid::regclass AS relation,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE NOT convalidated
ORDER BY 1, 2;
~~~

Unvalidated constraints must be accounted for. Do not ignore them just because tables contain rows.

### 20.5. Checking Indexes

~~~sql
SELECT
    indrelid::regclass AS table_name,
    indexrelid::regclass AS index_name,
    indisready,
    indisvalid
FROM pg_index
WHERE NOT indisready OR NOT indisvalid
ORDER BY 1, 2;
~~~

An invalid index can alter query plans or constraint behavior unexpectedly.

## 21. Validation: Roles, Grants, and Security Policies

### 21.1. Roles and Attributes

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication
FROM pg_roles
ORDER BY rolname;
~~~

Verify required roles and their attributes. Never grant superuser to the app just to bypass post-restore permission errors.

### 21.2. Role Memberships

~~~sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member ON member.oid = m.member
JOIN pg_roles AS parent ON parent.oid = m.roleid
ORDER BY 1, 2;
~~~

### 21.3. Table Privileges

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3, 4;
~~~

### 21.4. Row-Level Security

Check tables with RLS enabled/forced:

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND (c.relrowsecurity OR c.relforcerowsecurity)
ORDER BY 1, 2;
~~~

Policies must also be checked, confirming application roles see the expected rows.

### 21.5. Authentication and HBA

Check `pg_hba.conf`, TLS certificates, `password_encryption`, `listen_addresses`, firewalls, and secrets. Do not broaden access just to speed up testing.

## 22. Validation: Sequences, Identity, and Business Data

### 22.1. Checking Sequences

Logical dumps usually save sequence states, yet you must verify them after restore, especially after data-only restores or explicit-ID imports.

~~~sql
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

Sequence read access and available columns may depend on version/privileges.

### 22.2. Preventing nextval Primary Key Collisions

Compare sequence state against max key values per table/sequence. If `setval` is needed, perform it on a writable clone or after promoting the isolated copy, not on a cluster in recovery pause.

### 22.3. Selective Row Counts

~~~sql
SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.order_items;
SELECT count(*) FROM public.payments;
~~~

Exact counts on massive tables can be slow. Choose key tables and combine with aggregates/checksums or appropriate metadata.

### 22.4. Business Invariants

Examples: daily payment totals, order counts by status, zero orphaned order items, balanced ledgers, valid foreign keys, tenant counts, and latest transaction timestamps.

### 22.5. Meaningful Data Comparisons

Do not compare total row counts alone. Two copies with identical row counts can still differ in contents. Use aggregates, partition/key-range checksums, or predefined business queries.

## 23. Validation: Data and Recovery Point

### 23.1. Confirming the Recovery Target

Cross-check the target timestamp/LSN/restore point against the incident timeline and logs. Record the exact point where PostgreSQL stopped.

### 23.2. Checking the Last Transaction

Use audit/event tables or transaction markers to identify the latest recovered transaction. Do not rely on `pg_last_xact_replay_timestamp()` alone, as it can look stale when the workload is quiet.

### 23.3. Confirming the Offending Transaction Is Absent

When recovering prior to an accidental `DELETE`, confirm the rows to rescue still exist and the offending operation was not replayed.

### 23.4. Inspecting Data After the Recovery Point

For selective recovery, list valid transactions recorded after the PITR point in production along with rules to merge them. Avoid overwriting them with older data.

### 23.5. Saving Evidence

Record recovery point, LSN/timeline, query results, checksums, business owner approvals, and validation timestamps. Avoid pasting unnecessary PII/secrets into tickets.

## 24. Validation: Application and Dependencies

Databases do not run in isolation. A restore may be accurate while the application still fails to start or behave properly.

### 24.1. Smoke Tests

Run key read queries, authentication, health checks, sample transactions, and business workflows in a sandbox environment.

### 24.2. External Integrations

Use sandbox credentials for payment/email/SMS/webhooks. Disable consumers/schedulers or route to mock endpoints to avoid real side effects.

### 24.3. Connection Pools

Check hostnames, ports, TLS, DNS TTL, pool sizes, retry policies, and secret rotation. Never let production pools connect before cutover.

### 24.4. Application Version

Confirm schema/migration versions match the application binary. Never run automatic migrations against the recovery copy if the goal is preserving exact state at the recovery point.

### 24.5. Scheduled Jobs

Disable cron jobs, background workers, ETL writers, notification jobs, and event consumers until the environment is approved. Jobs can trigger immediately upon app boot.

## 25. Consistency Checks Before Deciding Replacement

A verification checklist should combine technical and business checks:

| Group | Question to Answer |
|---|---|
| Recovery point | Does it match the exact pre/post-incident point? |
| WAL chain | Replayed completely to target on the right timeline? |
| Schema | All tables, views, functions, triggers, extensions intact? |
| Integrity | Constraints/indexes valid? |
| Security | Roles, grants, RLS, TLS right? |
| Data | Rows/aggregates/business invariants passing? |
| Application | Smoke tests passing? |
| Dependencies | Queues, object storage, keys, DNS ready? |
| Capacity | CPU/RAM/disk/network sufficient for production load? |
| Ownership | DBA and business owner signed off? |

### 25.1. Separate Pass/Fail Criteria

If a critical criterion fails, do not cut over. Document which discrepancies are acceptable, which block recovery, and who has authority to accept risk.

### 25.2. Never Alter Data Just to Make Tests Pass

If an invariant fails, investigate the root cause. Modifying the recovery copy can destroy evidence about backup state; keep the original intact and create a working clone if testing repairs.

### 25.3. Keep the Recovered Copy Intact

For forensic or legal incidents, preserve a forensic/read-only copy with checksums. Run repair experiments on a second clone.

### 25.4. State Confidence Explicitly

Distinguish what was verified by queries, inferred from logs, or unverified. Never label a backup "guaranteed" just because a few tables have matching counts.

### 25.5. Business Sign-Off

DBAs confirm technical integrity; business owners confirm data and business rules. Cutover requires authorized sign-off per the incident/change process.


## 26. Promotion: When Is the Recovery Copy Allowed to Accept Writes?

A paused PITR cluster normally serves read-only inspection only. Promotion ends recovery and enables writes. This is the crucial boundary between inspection and operating as primary.

### 26.1. Pre-Promotion Conditions

- Recovery target and timeline are confirmed.
- WAL chain has no unresolved errors.
- Schemas, roles, constraints, indexes, and business checks pass.
- Network remains isolated with no production app clients.
- Evidence is saved and the responsible owner has approved.
- Confirmed whether this copy replaces the live system or serves only as a working copy.

### 26.2. Promoting with pg_ctl

~~~bash
pg_ctl promote --pgdata=/srv/recovery/pgdata
~~~

The path is an example. Use the service manager/orchestration appropriate for your actual host.

### 26.3. Promoting with SQL

On supported versions, you can run:

~~~sql
SELECT pg_promote();
~~~

The function requests/executes promotion per version semantics; check logs and status afterward.

### 26.4. Post-Promotion Verification

~~~sql
SELECT pg_is_in_recovery();
~~~

`false` confirms the server is no longer in recovery. Check logs, timeline history, write access, and cluster status before opening traffic.

### 26.5. Promotion Starts a New Timeline Branch

Once promoted, the cluster writes on a new timeline. Retain WAL/history and metadata needed for new backups, standby rebuilds, and auditing.

## 27. Do Not Promote When the Goal Is Only Data Extraction

For logical errors on an active production primary, you often only need to read from the recovery copy.

### 27.1. Keep the Recovery Copy Read-Only

If PITR is paused, use `SELECT`/exports to extract data. Do not turn it into a primary just to extract one table.

### 27.2. Use a Separate Staging Target

If data normalization or transformation is needed, copy into a writable staging database. Keep the original PITR copy untouched as a reference.

### 27.3. Extracting with COPY

~~~sql
COPY (
    SELECT order_id, customer_id, total, created_at
    FROM public.orders
    WHERE created_at < TIMESTAMPTZ '2026-11-14 09:42:00+07'
) TO STDOUT WITH (FORMAT csv, HEADER true);
~~~

Illustrative example; choose filters/columns per business need and avoid exporting PII beyond necessary scope.

### 27.4. Extracting with pg_dump Table

You can run `pg_dump` with specific table/schema flags against the recovery copy if a logical artifact is needed. Check dependencies before restoring that piece into production.

### 27.5. Compare Before Merging

Use the live primary as a reference source if it remains trustworthy. Identify deleted keys, modified rows, foreign keys, and transactions occurring after the recovery point.

## 28. Selective Merge Procedure Into Production

Selective merge brings rescued data from the isolated environment into the live database while preserving other valid transactions.

### 28.1. Define the Dataset to Rescue

Build a list of primary keys, time ranges, tenants, or business objects. Avoid broad generic `INSERT` statements without understanding the dependency graph.

### 28.2. Load Into a Staging Schema

~~~sql
CREATE SCHEMA recovery_staging;
~~~

Load extracted data into staging tables; check types, encoding, constraints, and duplicate keys.

### 28.3. Check Conflicts

~~~sql
SELECT r.order_id
FROM recovery_staging.orders AS r
JOIN public.orders AS p USING (order_id);
~~~

Duplicate-key rows require an explicit decision: keep current production, replace, merge columns, or skip.

### 28.4. Merge in Bounded Transactions

~~~sql
BEGIN;

INSERT INTO public.orders (order_id, customer_id, total, created_at)
SELECT order_id, customer_id, total, created_at
FROM recovery_staging.orders
ON CONFLICT (order_id) DO NOTHING;

COMMIT;
~~~

This example covers inserting missing rows only. Never use `DO NOTHING` as a blanket rule if updates or dependent rows must be restored.

### 28.5. Reconcile Dependent Systems

If orders trigger payments, shipments, emails, or events, handle idempotency/reconciliation. Restoring a database row does not automatically reconcile external side effects.

## 29. Cutover: Replacing the System with the Recovery Target

Execute only when the decision is to replace the primary or fail over workload to a DR site.

### 29.1. Declare Cutover

The incident/change owner confirms the recovery target, validation results, RPO/RTO impact, and cutover timing.

### 29.2. Fence the Old Primary

Prevent the old primary from accepting writes by stopping the service, blocking network access, revoking app routing, or applying appropriate fencing. Never let two primaries accept writes simultaneously.

### 29.3. Freeze Writes and Drain Clients

Pause application writes, background workers, and scheduled jobs per runbook. Wait for in-flight transactions to complete or handle them intentionally.

### 29.4. Final Recovery Point

If final commits before cutover must be preserved, ensure the last WAL was archived/replayed or perform a final sync procedure. Document any potential RPO data loss.

### 29.5. Promote and Shift Traffic

Promote the recovery target, verify writable state, update service discovery/DNS/connection strings, refresh pools, and open traffic in stages.

## 30. Preventing Split-Brain When Replacing the Primary

Split-brain occurs when two instances are both treated as primary and accept writes independently.

### 30.1. Fencing Must Be Provable

Do not rely solely on DNS changes. Existing clients may hold DNS caches, connection pools, or endpoint IPs. Fencing must block writes to the old primary at the network/service/storage layer.

### 30.2. Stop All Writers

Shut down application writers, cron jobs, queue consumers, ETL pipelines, and admin jobs. A single overlooked background client can continue writing to the old primary.

### 30.3. Check Replication Topology

After failover, old standbys may need reconfiguration/reseeding. Never allow old nodes to reconnect automatically under a stale topology.

### 30.4. Do Not Open All Traffic at Once

Open client groups incrementally and monitor error rates, write paths, replication, and business metrics before full rollout.

### 30.5. Record the New Timeline/LSN

After promotion, record timeline, LSN, recovery target, and cutover timestamp. This establishes the baseline for the new backup chain and standby provisioning.

## 31. Handling the Old Primary After Cutover

The old primary does not automatically become a valid standby simply by changing its connection string.

### 31.1. Keep the Old Node Fenced

Keep the old node blocked from writes until deciding to rejoin/rebuild. Preserve logs and evidence if investigation is needed.

### 31.2. Identify Timeline Divergence

The old primary may hold transactions absent from the recovered primary or vice versa. Never copy data directories back and forth manually.

### 31.3. pg_rewind or Fresh Base Backup

Under certain conditions, `pg_rewind` can align the old node onto the new timeline if prerequisites such as data checksums or `wal_log_hints` and required WAL are satisfied. Otherwise, rebuild the standby from a fresh base backup.

### 31.4. Do Not Assume Rewind Is Always Available

Verify version compatibility, WAL retention, timeline history, checksums/`wal_log_hints`, and `pg_rewind` documentation. When uncertain, rebuilding from a base backup is the cleaner path.

### 31.5. Recreate Replication Slots/Configuration

Reconfigure slots, `primary_conninfo`, synchronous standby policies, `archive_command`, and monitoring. Confirm standby replay catches up before declaring HA restored.

## 32. Rollback and Fallback Planning

Rolling back after cutover is far more complex than flipping DNS once the new primary has accepted writes.

### 32.1. Before Writes Open

If the recovery target has not accepted writes and cutover fails, you can revert to the old primary (if it remains safe) and abort traffic shifting per plan.

### 32.2. After the New Primary Accepts Writes

You cannot simply route traffic back to the old primary because it lacks new transactions. A forward-recovery/replication/reconciliation workflow is required to avoid losing writes.

### 32.3. Single-Writer Rule

At any point in time, there is only one authoritative writer for business data. Multi-primary setups require dedicated consistency designs and are not default PostgreSQL failover behavior.

### 32.4. Rollback Decision Window

Define the last moment when rolling back without write reconciliation is possible. Past that point, only recovery plans accounting for newly committed data apply.

### 32.5. Define Rollback Ownership

The incident commander, DBA, and application owner must know who holds authority to halt cutover and who decides to proceed with forward recovery.

## 33. Protecting Data in the Isolated Environment

A restored copy typically holds production data, including PII, secrets, or password verifiers.

### 33.1. Apply the Same Data Classification

Never treat a recovery host as a harmless sandbox. Encrypt storage/network, restrict users, and audit access.

### 33.2. Masking for Dev/Test

If using a clone for non-production testing, mask/anonymize data per policy before granting access to developers or vendors.

### 33.3. Do Not Use Production Credentials

Create dedicated recovery identities with time-bounded credentials, and never grant application identities permission to access or delete from the backup repository.

### 33.4. Control Exports

CSVs/dumps extracted from a recovery copy can easily leak to laptops or personal buckets. Require approved destinations, encryption, and retention limits.

### 33.5. Post-Incident Cleanup

Once required evidence is archived per retention rules, securely wipe recovery copies, temporary dumps, session keys/credentials, and storage. Never delete forensic copies under legal hold.

## 34. RPO/RTO in Isolated Restore

Isolated recovery lets you measure actual elapsed time and the recoverable data boundary.

### 34.1. RPO

Record the achieved recovery target, last replayable WAL, and remote archive status. Measure RPO from incident time to the actually available recovery point.

### 34.2. RTO

Measure from incident declaration per convention until applications/services are ready post-cutover. Include provisioning, retrieval, restore, replay, validation, and routing.

### 34.3. Restore Test vs. Production RTO

A lab restore measures technical steps yet may omit incident approvals or real DNS propagation. Document the exact scope measured.

### 34.4. Parallelism

Provisioning hosts, checking keys, and preparing DNS can run in parallel with backup retrieval if permitted by the runbook. Never assume parallelism where dependencies exist.

### 34.5. Buffer

Build targets with buffer for archive lag, cold storage retrieval, peak network load, index builds, and business validation.



## 35. Lab: Logical Restore Into an Isolated Database

This lab illustrates restoring a custom dump into a fresh database. Run in a test environment with appropriate privileges.

### 35.1. Create a Logical Dump

~~~bash
pg_dump --format=custom --file=appdb.dump --dbname=appdb
~~~

Creates a logical snapshot of the database. Ensure the file is stored with adequate space and access controls.

### 35.2. Inspect the Archive List

~~~bash
pg_restore --list appdb.dump
~~~

Review objects in the archive and confirm the file is readable.

### 35.3. Create a Dedicated Target Database

~~~bash
createdb --template=template0 recovery_app
~~~

If specific locale/encoding is needed, create the database with options matching production.

### 35.4. Restore

~~~bash
pg_restore --verbose --exit-on-error --dbname=recovery_app appdb.dump
~~~

Wait for the command to finish and save logs. Do not allow applications to connect to `recovery_app`.

### 35.5. Basic Verification

~~~sql
SELECT current_database();
SELECT count(*) FROM public.orders;
SELECT count(*) FROM public.customers;
SELECT extname, extversion FROM pg_extension ORDER BY extname;
~~~

Compare results against expected inventory and prepared business checks.

## 36. Lab: Restoring a Logical Dump with Roles and Ownership

### 36.1. Create a Globals-Only Backup

~~~bash
pg_dumpall --globals-only --file=globals.sql
~~~

This file may hold role definitions and tablespaces. Protect it as sensitive data and inspect before restoring.

### 36.2. Review Contents Before Execution

Read the SQL to understand roles, tablespaces, ownership, and grants to be created. Never apply an unverified globals file onto a populated cluster.

### 36.3. Restore Globals Into a New Lab Cluster

~~~bash
psql -X --set ON_ERROR_STOP=on --dbname=postgres --file=globals.sql
~~~

If the target already has roles, resolve conflicts per plan. An empty lab cluster avoids collisions.

### 36.4. Restore the Database Archive

~~~bash
pg_restore --exit-on-error --dbname=recovery_app appdb.dump
~~~

### 36.5. Verify Real Privileges

Connect using a test application role and run permitted queries/workflows. Never use superuser to validate application permissions.

## 37. Lab: Building Physical PITR in a Dedicated Data Directory

This lab requires a valid base backup and WAL archive. Paths are illustrative; never run against a production data directory.

### 37.1. Prepare the Data Directory

Create a dedicated volume/directory on the recovery host; verify owner, permissions, and disk space. Extract/restore the base backup using the tool that created the artifact.

### 37.2. Configure Archive Retrieval

~~~conf
restore_command = 'cp /mnt/pg-archive/%f %p'
recovery_target_time = '2026-11-14 09:42:00+07'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Replace the command with your backup tool/object storage wrapper if needed. The command must return proper exit codes when files are missing and never read from the wrong archive.

### 37.3. Create recovery.signal

Create an empty `recovery.signal` file inside the restored PGDATA on PostgreSQL 12 and later. Never create signal files inside production data directories.

### 37.4. Start the Target

~~~bash
pg_ctl start --pgdata=/srv/recovery/pgdata --log=/srv/recovery/recovery.log
~~~

Watch logs to confirm recovery started, fetched WAL, and reached the target.

### 37.5. Confirm Pause

~~~sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
~~~

Connect only from the recovery network. Confirm logs report target reached/paused and inspect required data.

## 38. Lab: Investigating Accidental Deletion Using a Recovery Copy

Suppose the `orders` table was accidentally deleted at 10:15. Live production continues receiving valid transactions.

### 38.1. Select a Target Prior to the Error

Choose a timestamp prior to the `DELETE` commit, with a small buffer if clock/log uncertainty exists. Explicitly record timezone and recovery target.

### 38.2. Restore PITR Into an Isolated Cluster

Use base backup + WAL up to the target. Hold in recovery pause for querying/exporting.

### 38.3. Verify Rows

~~~sql
SELECT count(*) FROM public.orders;
SELECT min(created_at), max(created_at) FROM public.orders;
SELECT status, count(*) FROM public.orders GROUP BY status;
~~~

Cross-check with audit records and business invariants.

### 38.4. Export Rescued Data

Use `COPY` or a table dump into an approved staging artifact. Avoid exporting unnecessary columns when only a subset is needed.

### 38.5. Merge Into Current Production

Load into a staging schema, compare conflicts, resolve foreign keys and transaction events, and merge in controlled transactions. Never replace the entire primary with an older PITR copy when production has valid writes after 10:15.

## 39. Lab: Rehearsing Cutover in an Isolated Network

### 39.1. Prepare the Candidate Instance

Restore a backup onto the recovery host, configure a dedicated endpoint, and restrict firewall access to operators only.

### 39.2. Verify No Application Clients Are Connected

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
ORDER BY application_name, pid;
~~~

Confirm only expected connections appear. Querying this view does not replace network firewalls.

### 39.3. Run Smoke Tests

Verify authentication, key read queries, and sample transactions on a writable clone. If the cluster remains in recovery pause, run read checks only.

### 39.4. Rehearse Fencing

In the lab, simulate blocking the old primary and switching endpoints. Confirm old clients cannot write to the old node.

### 39.5. Measure Timings

Record provisioning, retrieval, restore, replay, validation, promotion, and routing durations. Compare against the RTO target and log action items.

## 40. Runbook: Isolated Restore Before Replacement

A practical runbook may follow this sequence:

1. Declare incident/drill and record T0, timezone, and failure mode.
2. Confirm whether the primary remains trustworthy and usable as a reference source.
3. Choose the recovery point based on RPO and business impact.
4. Verify backup artifacts, manifests, WAL chain, timeline, and encryption keys.
5. Provision isolated recovery host/network/storage.
6. Prepare PostgreSQL binaries, extensions, locales, roles, and tablespaces.
7. Restore logical or physical backup into the isolated target.
8. If PITR, replay WAL to the target and pause recovery.
9. Verify schemas, data, constraints, indexes, sequences, grants, and RLS.
10. Run business invariants and application smoke tests in sandbox.
11. Decide between selective merge vs. primary replacement.
12. If cutting over, freeze writes, fence old primary, promote target, and shift traffic.
13. Verify application health and business transactions.
14. Rebuild standbys/backup chain on the new timeline.
15. Record actual RPO/RTO, evidence, and post-incident actions.
16. Retain or wipe recovery artifacts per retention/legal hold policies.

### 40.1. Accountable Owners

Explicitly designate incident commander, DBA/recovery lead, application owner, network/security owner, and business approver. Unowned steps are easily skipped under time pressure.

### 40.2. Stop Criteria

If WAL is missing, the target is unclear, integrity checks fail, keys are inaccessible, or fencing is unready, halt cutover and escalate per the incident process.

### 40.3. Decision Authority

DBAs confirm technical validity; business owners accept potential data loss; incident commanders coordinate; authorized leads approve opening traffic.

### 40.4. Log Every Change

Record commands, timestamps, recovery target, promotion event, DNS updates, and approvals. Never log passwords/tokens.

### 40.5. Incident End Is Not Recovery End

Re-establish backup/standby protection, check archive lag, verify monitoring, and revoke temporary access.

## 41. Troubleshooting: Restore Fails to Start

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `pg_restore` cannot read archive | Corrupted file/wrong format | `pg_restore --list`, checksum, tool version |
| Permission denied | File/dir owner or IAM | OS permissions, storage identity |
| Database creation fails | Locale/encoding/template mismatch | `createdb` options, locale packages |
| Role already exists | Globals collision | Review globals SQL, role mapping |
| Extension missing | Shared library not installed | Package/version/extension inventory |
| Tablespace path missing | Target path not created | Tablespace mapping/permissions |
| Disk full | Underestimated capacity | Free space, temp/index/WAL growth |
| TLS/auth failure | HBA/cert/secret mismatch | Recovery-only credentials and TLS config |

### 41.1. Do Not Blindly Retry Without Reading Errors

Save logs and identify whether the error occurred during archive reading, database creation, object restoration, or runtime startup. Fix the exact dependency, then retry on a clean target.

### 41.2. Target Database May Be Partially Created

If restore fails midway, decide how to clean the target per runbook. Never run `--clean`/drop on a database outside intended scope.

### 41.3. Tool Versions

`pg_dump`/`pg_restore` follow version compatibility rules relative to servers. Verify client version, archive format, and target server beforehand.

## 42. Troubleshooting: PITR Fails to Reach Target

### 42.1. WAL Segment Not Found

Check archive path, filename, permissions, object lifecycle rules, credentials, and `restore_command` output.

### 42.2. Missing Timeline History

If the target lies on a newer timeline, both timeline history files and matching WAL segments are required. Do not just copy WAL filenames without verifying the chain.

### 42.3. Recovery Stops Early

The target may not exist in the WAL archive, the archive may have gaps, or the target timestamp may lie past the last WAL. Cross-check logs and LSNs.

### 42.4. Recovery Overshoots Target

Check recovery target settings, signal file, configuration sources, and version. Ensure no stale/other configuration overrides it.

### 42.5. Wrong Timezone

Timestamps without an offset may be interpreted in the server's timezone. Specify explicit offsets/UTC and check incident clocks.

## 43. Troubleshooting: Database Restored Yet Application Fails

- Insufficient roles/memberships.
- Missing grants/default privileges or stripped via `--no-acl`.
- RLS policies hide rows from the application role.
- Incompatible extension binary/version.
- Collation/locale changes alter index/query behavior.
- Out-of-sync sequence/identity states.
- Schema version mismatches application binary.
- Wrong TLS/HBA/DNS/network settings.
- Unprovisioned secrets or KMS keys.
- Queues, object storage, or external services unrecovered.
- Scheduled jobs/consumers ran unexpectedly in the isolated environment.
- Connection pool retains stale endpoints or improper retries.

### 43.1. Read Logs on Both Sides

PostgreSQL logs show server/auth/SQL errors; application logs show query/connection/workflow errors. Correlate using timestamps/request IDs.

### 43.2. Do Not Broaden Privileges Arbitrarily

Permission errors require identifying the specific role/object/grant. Avoid granting `ALL` or `SUPERUSER` just to make smoke tests pass.

### 43.3. Never Run Auto-Migrations Before Confirming the Target

Migrations alter the recovery copy and break comparability against the recovery point. Run them on a clone or per a controlled migration plan.

## 44. Common Misconceptions

1. **"A successful backup means it can restore."** False; restore tests and validation are required.
2. **"We can overwrite production and inspect afterward."** False; risks losing live state and extending downtime.
3. **"Database started means the service is recovered."** False; roles, network, application, and business checks remain.
4. **"Standbys replace backups."** False; logical errors replicate too.
5. **"PITR only needs a base backup."** False; a continuous WAL chain and proper timeline are needed.
6. **"A single `pg_dump` includes global roles."** False; globals require separate handling.
7. **"`pg_dumpall` creates an atomic cluster-wide snapshot."** False; separate databases do not share a single MVCC snapshot.
8. **"Recovery pause allows writing data."** False; the server remains in recovery state.
9. **"Promote just opens a port."** False; promotion ends recovery and creates a new timeline.
10. **"Changing DNS alone fences the old primary."** False; existing clients may keep cached endpoints/connections.
11. **"We can roll back by pointing DNS back to the old primary after the new primary took writes."** False; reconciliation/forward recovery is needed.
12. **"A single-table restore is always self-contained."** False; sequences, types, functions, foreign keys, and grants exist.
13. **"Valid checksums prove business data is valid."** False; checksums verify bytes, not business semantics.
14. **"Matching `count(*)` means data is valid."** False; identical counts can hide differing rows.
15. **"A recovery copy holds no sensitive data."** False; it usually contains live production data.
16. **"Production credentials can be reused for testing."** False; increases blast radius and side effects.
17. **"Stopping only the web app is enough."** False; workers, cron, ETL, and consumers can also write.
18. **"`pg_rewind` can always resync the old primary."** False; it has strict prerequisites and WAL requirements.
19. **"After restore, backup monitoring can wait."** False; protection must be re-established on the new timeline immediately.
20. **"One tabletop exercise proves DR readiness."** False; technical restore and cutover drills are essential.

## 45. Practice Exercises

### Exercise 1 — Isolated Recovery

Why should you restore into an isolated environment before replacing production?

**Hint:** Verify the recovery point, artifacts, dependencies, and data before opening traffic.

### Exercise 2 — Selective Recovery

Production keeps running after a table was accidentally dropped. Why should you avoid replacing the entire primary with an older PITR copy?

**Answer:** Valid transactions committed after the recovery point would be lost.

### Exercise 3 — Logical Dump

Which command lists the table of contents of a custom archive?

**Answer:** `pg_restore --list`.

### Exercise 4 — Restoring a Database

Which command restores a custom archive into an already-created database?

**Hint:** `pg_restore` with `--dbname` and the archive file.

### Exercise 5 — Globals

Which tool exports global objects such as roles?

**Answer:** `pg_dumpall --globals-only`.

### Exercise 6 — Physical Backup

Which core PostgreSQL tool creates a base backup over the replication protocol?

**Answer:** `pg_basebackup`.

### Exercise 7 — Recovery Signal

On PostgreSQL 12+, which file triggers archive recovery?

**Answer:** `recovery.signal`.

### Exercise 8 — Standby Signal

Which file is used to start in standby mode?

**Answer:** `standby.signal`.

### Exercise 9 — Restore Command

What are the two common placeholders in `restore_command`?

**Answer:** `%f` for the WAL filename and `%p` for the destination path.

### Exercise 10 — Recovery Target

Which parameter selects a PITR timestamp?

**Answer:** `recovery_target_time`.

### Exercise 11 — Pause

Why set `recovery_target_action=pause` during isolated validation?

**Hint:** Pauses at the target for read inspection before promoting.

### Exercise 12 — Recovery State

Which function indicates whether the server is still in recovery?

**Answer:** `pg_is_in_recovery()`.

### Exercise 13 — Promotion

Which command promotes an isolated recovery server via `pg_ctl`?

**Answer:** `pg_ctl promote`.

### Exercise 14 — Timeline

Why must timeline history be preserved after promotion?

**Hint:** WAL recovery/standby rebuilds need to know timeline branches.

### Exercise 15 — Extensions

Why can a restore still fail even when `CREATE EXTENSION` is in the dump?

**Answer:** The matching shared library/package may not be installed on the target.

### Exercise 16 — Roles

Why is `pg_dump` of a single database insufficient to recover all roles?

**Hint:** Roles are cluster-wide global objects.

### Exercise 17 — Ownership

Which option skips ownership commands during `pg_restore`?

**Answer:** `--no-owner`.

### Exercise 18 — Grants

Which option skips ACL/`GRANT` statements during `pg_restore`?

**Answer:** `--no-acl`.

### Exercise 19 — Constraints

Which catalog holds constraint validation state?

**Answer:** `pg_constraint`, column `convalidated`.

### Exercise 20 — Index Validity

Which catalog shows `indisvalid`/`indisready`?

**Answer:** `pg_index`.

### Exercise 21 — RLS

Why must row-level security be tested after restore?

**Hint:** Policies can cause application roles to see different row sets than expected.

### Exercise 22 — Sequences

Why might sequence states require verification after a data-only restore?

**Hint:** Explicit IDs/imports can leave sequence values behind the max key.

### Exercise 23 — Business Invariants

Name two checks beyond simple row counts.

**Hint:** Ledger balances, payment totals, order status counts, foreign-key orphan checks.

### Exercise 24 — Side Effects

What must be blocked when running an application against a recovery copy?

**Answer:** Payments/emails/webhooks, scheduled jobs, ETL writers, queue consumers, and other external side effects.

### Exercise 25 — Split-Brain

Why is changing DNS insufficient to fence the old primary?

**Hint:** Client caches/connection pools may keep using the old endpoint.

### Exercise 26 — Cutover

What is the critical sequence before opening writes on the recovered primary?

**Hint:** Freeze/drain writes, fence old primary, promote target, switch endpoints, open traffic.

### Exercise 27 — Old Primary

After timeline divergence, what can be done with the old primary?

**Hint:** `pg_rewind` if prerequisites are met; otherwise, reseed from a fresh base backup.

### Exercise 28 — Rollback

Once the recovered primary has accepted writes, why can you not simply revert to the old primary?

**Answer:** The old primary lacks the new writes; forward recovery/reconciliation is required.

### Exercise 29 — Recovery Data Privacy

Why must a recovery copy be protected just like production?

**Answer:** It contains the same sensitive data and may hold credentials/verifiers/PII.

### Exercise 30 — Restore Evidence

Which metadata should be recorded for a recovery point?

**Hint:** Backup ID, timestamp/timezone, LSN, timeline, WAL coverage, checksums, and target.

### Exercise 31 — PITR Failure

If a WAL segment is missing, what must be checked?

**Hint:** Archive path, permissions, `restore_command`, object retention, timeline history.

### Exercise 32 — RTO

Which phases must be counted beyond just the restore command?

**Hint:** Detection, decision, provisioning, retrieval, replay, validation, cutover.

### Exercise 33 — Recovery Pause

Can `CREATE TABLE` run on a cluster in recovery pause?

**Answer:** No; create a writable clone or promote the isolated copy once decided.

### Exercise 34 — Selective Merge

Why load rescued data into a staging schema first?

**Hint:** Compare conflicts, validate, and apply merge rules before modifying production.

### Exercise 35 — Global Consistency

Why do multiple `pg_dump` database dumps not guarantee a single shared snapshot?

**Answer:** Each database dump takes its own snapshot; there is no distributed cross-database snapshot.

### Exercise 36 — Managed Restore

Besides the backup snapshot, which dependencies must be checked?

**Hint:** KMS, IAM, quotas, parameter groups, extensions, networking, and DNS.

### Exercise 37 — Cutover Approval

Who approves technical validity and who approves business validity?

**Hint:** DBA/recovery lead approves technical validity; business/service owner approves data and behavior.

### Exercise 38 — Forensic Copy

Why keep the recovered copy untouched during investigations?

**Answer:** Preserves evidence and enables re-verification; perform repairs on a separate clone.

### Exercise 39 — DR Drill

Is a tabletop exercise enough to prove cutover readiness?

**Answer:** No; technical restore and cutover drills in a proper environment are required.

### Exercise 40 — Capstone Design

A 2 TB PostgreSQL system suffers accidental data deletion at 10:15 while production continues receiving new transactions; RPO target is 5 minutes and RTO is 45 minutes. Propose a procedure.

**Hint:** Fence the faulty operation, pick a PITR target before 10:15, restore base backup + WAL into an isolated cluster, pause at target, verify rows/business invariants, export rescued data, and merge via staging with conflict rules into live production. Replace the primary only if production is untrustworthy; in that case, freeze writes, fence old primary, promote, cut over, and rebuild standbys. Measure RPO/RTO from artifacts/restore drills.

## 46. Pre-Isolated-Restore Checklist

- [ ] Incident/drill ID and failure mode recorded?
- [ ] Recovery point and timezone/LSN determined?
- [ ] Backup artifacts/checksums/manifests readable?
- [ ] WAL chain and timeline history complete if PITR?
- [ ] Encryption keys accessible by DR identity?
- [ ] PostgreSQL version/extensions compatible?
- [ ] Tablespaces/locale/encoding/permissions ready?
- [ ] Dedicated recovery host/data directory/volume prepared?
- [ ] Network and firewalls isolated?
- [ ] No application credentials/clients auto-connecting?
- [ ] External side effects/jobs/consumers blocked?
- [ ] Disk/CPU/RAM/network headroom sufficient?
- [ ] Validation criteria and owners defined?

## 47. Pre-Promotion/Cutover Validation Checklist

- [ ] Recovery target and timeline accurate?
- [ ] WAL replay reached target with clean logs?
- [ ] Databases/schemas/tables complete?
- [ ] Extensions and shared libraries working?
- [ ] Constraints/indexes valid?
- [ ] Sequences/identity states aligned?
- [ ] Roles/memberships/grants/default privileges accurate?
- [ ] RLS policies and authentication verified?
- [ ] Business invariants passing?
- [ ] Application smoke tests passing in sandbox?
- [ ] External integrations pointed to sandbox/no-op?
- [ ] Capacity sufficient for production load?
- [ ] DBA and business owner sign-off obtained?
- [ ] Fencing and cutover plan ready?

## 48. Cutover Checklist

- [ ] Incident commander declared cutover?
- [ ] Application writes/jobs/consumers paused?
- [ ] Old primary fenced and receiving zero writes?
- [ ] Final recovery point/WAL confirmed?
- [ ] Recovery target promoted cleanly?
- [ ] New timeline/LSN recorded?
- [ ] DNS/endpoints/service discovery updated?
- [ ] Connection pools refreshed?
- [ ] Traffic opened in stages?
- [ ] Error rates/latency/business transactions monitored?
- [ ] Standby/backup/WAL archive protection re-established?
- [ ] Old primary kept fenced until rejoin/rebuild completes?

## 49. Quick Reference Table

| Component | Role |
|---|---|
| Isolated recovery | Recovering in an environment isolated from production traffic |
| Logical restore | Creating objects/loading data from dump |
| Physical restore | Building cluster from base backup |
| WAL archive | Supplying logs for replay |
| PITR | Recovering to a specific recovery target |
| `recovery.signal` | Starting archive recovery on PostgreSQL 12+ |
| `standby.signal` | Starting standby mode |
| `restore_command` | Fetching WAL archive files |
| `recovery_target_time` | Choosing recovery timestamp |
| `recovery_target_timeline` | Choosing timeline |
| `recovery_target_action=pause` | Pausing replay at target for inspection |
| `pg_is_in_recovery()` | Checking recovery state |
| `pg_promote()` | Promoting server |
| `pg_restore` | Restoring logical archives |
| `pg_dumpall --globals-only` | Exporting global objects |
| `pg_constraint` | Constraint metadata |
| `pg_index` | Index validity metadata |
| `pg_roles` | Role attributes |
| `pg_auth_members` | Role memberships |
| `pg_stat_activity` | Session visibility |
| `pg_locks` | Lock monitoring |
| Fencing | Blocking old primary from accepting writes |
| Cutover | Switching traffic to recovered primary |
| Selective merge | Bringing rescued data into live production |
| `pg_rewind` | Aligning a node onto the new timeline when eligible |
| Recovery drill | Rehearsing restore/validation/cutover |

## 50. Conclusion

**Restoring into an isolated environment is a critical control step before replacing a PostgreSQL system.** It creates space to verify backups, pick recovery points, replay WAL, inspect schemas/privileges/data, and run business checks without letting production accidentally connect to an unverified cluster.

For logical backups, restore into a fresh database and verify dependencies/ownership/grants. For physical backups and PITR, build a dedicated data directory, provide the WAL archive, configure a recovery target, and pause at the target for read-only inspection prior to promotion. When only a subset of data needs rescuing, keep the recovery copy read-only and merge via staging with conflict rules; avoid rolling back all of production when valid post-recovery-point transactions must be preserved.

When primary replacement is required, the procedure must freeze writes, fence the old primary, verify the target, promote the recovery cluster, switch endpoints, open traffic safely, and rebuild standby/backup protection on the new timeline. Changing DNS alone does not prevent split-brain, and rolling back after the new primary accepts writes requires reconciling newly committed transactions.

Operational principle: **restore first, verify in isolation, decide between selective merge or replacement, and only then promote/cut over**. Measure RPO/RTO through real drills, retain evidence, and protect recovery copies like production data.
