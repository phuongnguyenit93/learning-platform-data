# Testing Data Recovery and Deployment Rollback Capability

A backup plan is only valuable once an organization proves data can be recovered within the committed time and data-loss targets. Similarly, a deployment rollback plan is only trustworthy once operations has practiced reverting to a prior application or schema version without losing valid newly created data.

In Oracle Database, two related but distinct capabilities must be tested:

- **Data recovery test:** proves that backups, archived redo logs, control files, configurations, and procedures can restore the database or target scope to an objective point.
- **Deployment rollback test:** proves that the application and database schema can be reverted to a compatible state after a faulty release while preserving valid transactions according to business policy.

Neither test can be replaced by a single `RMAN VALIDATE` run or redeploying an old binary. Checking whether a backup is readable differs from actually restoring it; rolling back an application binary does not undo committed DDL or data migrations.

This lesson covers defining RPO/RTO targets, validating backups, provisioning isolated recovery environments, running restore/recover, validating recovered data, designing application/schema rollbacks, handling Oracle DDL implicit commits, and producing repeatable test evidence.

## 1. Distinguishing backup validation, restore testing, and rollback testing

These three activities are often lumped together, yet they prove very different things.

| Activity | Question answered | Primary evidence |
| --- | --- | --- |
| Backup validation | Are backup pieces and source files readable and verifiable? | RMAN validate output, read/corruption errors |
| Restore test | Can the database be rebuilt from backups and redo? | Cloned database opens at target, restore/recover logs |
| Deployment rollback test | Can we revert to the prior app/schema version with valid data intact? | Migration rollback tests, app compatibility, reconciliation, and service smoke tests |

### 1.1. Backup validation is not a complete restore

RMAN can read backup pieces and verify usability at the file level. However, passing validation does not prove the full restore/recover workflow will succeed on a new host.

An actual restore also depends on:
- Having all required backup levels and backup pieces.
- Having the necessary control file or recovery catalog.
- Having the `SPFILE`/`PFILE` and password file.
- Having continuous archived redo logs up to the target.
- Having the TDE wallet/keystore if the database is encrypted.
- Having compatible storage, permissions, Oracle Home, and configuration.
- Having sufficient time, network throughput, and storage capacity for restore/recover.
- Operators knowing the exact command sequence and database open conditions.

### 1.2. Application rollback is not database rollback

If a new release changes only Java code without altering schemas or data, the old artifact can simply be redeployed. However, if migrations already:
- Added, renamed, or dropped columns.
- Altered data types.
- Transformed data.
- Dropped partitions or tables.
- Modified constraints, indexes, or triggers.
- Bulk-updated business state.

then rolling back the old binary may render the application incompatible with the new schema. Oracle DDL also triggers implicit commits, so `@Transactional` cannot undo an entire migration.

### 1.3. Restoring to pre-release time may discard new transactions

Flashback Database or point-in-time recovery can rewind the database to before deployment. Valid transactions committed after that point may be excluded from the recovered state.

Therefore, full-database rollback requires explicit business decisions:
- Which transactions are acceptable to lose?
- Can post-target transactions be extracted and replayed?
- Can we repair only the schema or use a forward-fix?
- Who approves the rollback?
- Can application writes be paused during state transition?

## 2. Defining RPO, RTO, and test scope

Before writing a runbook, define measurable targets.

### 2.1. RPO — Recovery Point Objective

RPO is the maximum tolerable data loss measured in time or transaction point.

Examples:
- RPO 0: requires zero committed transaction loss within the defined failure model.
- RPO 5 minutes: accepts recovering to a point no older than 5 minutes before the incident.
- RPO 1 hour: tolerates up to a 1-hour data loss window.

RPO must align with how backups and redo are protected. Nightly full backups cannot meet a 5-minute RPO without properly retained and protected archived redo logs.

### 2.2. RTO — Recovery Time Objective

RTO is the maximum allowed time to restore service to a usable state.

RTO should account for:
1. Incident detection and triage.
2. Recovery target selection.
3. Host/storage/Oracle Home preparation.
4. Datafile/control file restoration.
5. Archived redo application.
6. Database and PDB opening.
7. Data, object, and service verification.
8. Traffic cutover and application validation.

Do not measure only `RMAN RESTORE DATABASE` runtime. An application is only recovered once services, credentials, jobs, and required dependencies are operational.

### 2.3. Scoping recovery types

A plan may require multiple test types:

- **Whole database recovery:** loss of host, storage, or the entire database.
- **Datafile recovery:** loss or corruption of a single datafile.
- **Tablespace recovery:** recovering a single tablespace via an appropriate method.
- **Point-in-time recovery (PITR):** rewinding the database or supported scope to an SCN/timestamp before a logical error.
- **Block media recovery:** recovering specific corrupted blocks under eligible conditions.
- **PDB recovery:** recovering a single pluggable database inside a CDB.
- **Logical recovery:** recovering accidentally modified tables/rows or business data.
- **Deployment rollback:** returning app/schema to a pre-release compatible state.

Not every incident warrants a full-database restore. Choose the smallest recovery scope that meets goals while preserving valid data.

## 3. Designing a recovery test plan

A good test plan defines triggers, environments, inputs, execution steps, pass/fail criteria, owners, and evidence.

### 3.1. Defining scenarios

Example:

| Scenario | Objective | Commonly evaluated techniques |
| --- | --- | --- |
| Loss of one datafile | Restore file and apply redo | `RMAN RESTORE`/`RECOVER DATAFILE` |
| Loss of entire database host | Rebuild database on another host | Restore database + media recovery |
| Accidental data deletion | Recover before erroneous operation | Flashback, PITR, export/restore, or logical repair |
| Block corruption | Recover affected blocks | RMAN block media recovery if eligible |
| Migration corrupts data | Recover data or reverse change | Compensating migration, PITR, or restore clone |
| Faulty new release | Revert app to old binary | Redeploy old artifact and verify schema compatibility |
| Incompatible schema migration | Return schema/app to compatible state | Tested rollback script, forward-fix, or restore strategy |
| Primary site loss | Restore service on standby | Data Guard failover per DR runbook |

### 3.2. Defining test data and verification checkpoints

Before taking a backup or restore point, prepare verifiable test data:
- Known primary keys.
- Row counts by partition or business date.
- Monetary totals/quantities by group.
- Sample LOBs/documents with hashes.
- Critical order/payment statuses.
- Sequence/identity state.
- Constraints and foreign key relationships.
- Records created before and after the recovery target.

Never rely solely on `COUNT(*)` over a large table. Row counts can match even when column contents or business states are wrong.

### 3.3. Selecting an isolated recovery environment

Prefer restoring/duplicating onto a separate host, VM, storage volume, or namespace:
- Never overwrite production datafiles.
- Never collide with ASM/filesystem paths of running databases.
- Never register duplicate service names matching production.
- Prevent production applications from auto-connecting to the clone.
- Never send real emails, payments, messages, or webhooks from cloned data.
- Use isolated credentials and restrict network egress.
- Protect sensitive data per masking/access policies.
- Set storage quotas and clone retention limits.

A restore test can cause a production outage if it touches the wrong control file, datafile path, or connect service. Environment isolation is a core test prerequisite, not an afterthought.

## 4. Preparing before running a restore test

Before recovering, gather full metadata and dependencies.

### 4.1. Database identity

Record:
- `DB_NAME`, `DB_UNIQUE_NAME`, and `DBID`.
- Oracle Database release, RU, and `COMPATIBLE`.
- CDB/PDB topology, database role, and open mode.
- Character set and national character set.
- Timezone file version if the application depends on it.
- RAC/ASM vs. filesystem.
- TDE encryption and wallet/keystore.
- `ARCHIVELOG` mode and FRA.
- Backup policy, retention, and recovery catalog.

Example query:

~~~sql
SELECT name,
       dbid,
       db_unique_name,
       open_mode,
       database_role,
       log_mode,
       force_logging
FROM v$database;
~~~

Version:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

### 4.2. Checking backup inventory

RMAN:

~~~text
RMAN> LIST BACKUP SUMMARY;
RMAN> LIST BACKUP OF DATABASE;
RMAN> LIST BACKUP OF ARCHIVELOG ALL;
RMAN> REPORT SCHEMA;
RMAN> SHOW ALL;
~~~

Verify:
- Most recent full/incremental backups.
- Control file and `SPFILE` backups.
- Archived redo logs spanning from the backup to the recovery target.
- Backup piece locations and accessibility.
- Retention policy and deletion policy.
- Recovery catalog availability.
- Whether backups are encrypted and keys remain accessible.

### 4.3. TDE wallet/keystore

If the database uses Transparent Data Encryption, datafile backups alone cannot open the database without the matching keystore.

Verify:
- Wallet/keystore backup.
- Password or auto-login wallet per policy.
- Key versions and key rotation history.
- Secure access permissions in the test environment.
- Ability to open the keystore post-restore.
- Never embed secrets in logs or test documentation.

Restore tests must include opening the keystore in the isolated environment whenever the database requires decryption.

### 4.4. Other files and details

Depending on architecture, prepare:
- `SPFILE`/`PFILE`.
- Password file.
- Control file autobackups.
- Archived redo logs.
- TNS/listener/service configuration.
- ASM disk groups or mount points.
- Directory objects and required external files.
- Database links, credentials, and external dependencies.
- Scripts to recreate services, jobs, and post-recovery privileges.

Not all of these components are captured inside an RMAN backup in the same way.

## 5. RMAN validation: checking before restoring

RMAN provides commands to validate backups and source files. They are very useful but do not replace an actual restore.

### 5.1. CROSSCHECK

~~~text
RMAN> CROSSCHECK BACKUP;
RMAN> CROSSCHECK ARCHIVELOG ALL;
~~~

`CROSSCHECK` compares metadata in the RMAN repository against physical files or the media manager. It marks backups `EXPIRED` if missing.

`CROSSCHECK` does not read full backup contents to prove restorability. Do not confuse `EXPIRED` with `OBSOLETE`:
- `EXPIRED`: RMAN could not locate the physical file during crosscheck.
- `OBSOLETE`: the backup is no longer needed under the current retention policy.

### 5.2. Validate backup set

~~~text
RMAN> VALIDATE BACKUPSET 123;
~~~

Replace `123` with an actual backup set key from `LIST BACKUP`. This reads and validates the backup set within supported scope; it does not stand up a database on a test host.

### 5.3. Restore preview

~~~text
RMAN> RESTORE DATABASE PREVIEW;
RMAN> RESTORE DATABASE PREVIEW SUMMARY;
~~~

`PREVIEW` displays which backups RMAN plans to use for a restore. It catches missing backup metadata or broken backup chains before starting the restore.

`PREVIEW` does not read full backup pieces and does not prove the restore will succeed.

### 5.4. Restore validate

~~~text
RMAN> RESTORE DATABASE VALIDATE;
~~~

This command reads all backups required by the restore plan without writing restored datafiles to the target location. It verifies backup pieces are readable during a simulated restore.

You can validate archived redo logs across the needed range:

~~~text
RMAN> RESTORE ARCHIVELOG ALL VALIDATE;
~~~

Scope the range carefully to avoid scanning excessive irrelevant logs.

### 5.5. Checking logical corruption

~~~text
RMAN> BACKUP VALIDATE CHECK LOGICAL DATABASE;
~~~

`CHECK LOGICAL` instructs RMAN to check logical block structures in addition to physical checks within the command scope. It reads current database files; it does not replace restore tests from backup.

Different validation commands cover different scopes. Save outputs, timestamps, `DBID`, and backup identifiers for audit traceability.

## 6. Actual restore testing into an isolated environment

This step proves real recoverability. Run on a dedicated host/target and verify every file path before execution.

### 6.1. Preparing the auxiliary host

- Install compatible Oracle software.
- Allocate adequate storage for datafiles, redo, temp, FRA, and recovery.
- Configure Oracle Home and environment variables.
- Prepare password file and `PFILE`/`SPFILE`.
- Verify read permissions to backups and archived redo logs.
- Prepare the TDE keystore if needed.
- Configure an isolated `DB_UNIQUE_NAME`/service for the clone.
- Block production traffic from reaching the clone.
- Double-check that no file paths point to production.

### 6.2. Using RMAN DUPLICATE or restore/recover

Two common approaches:

**RMAN DUPLICATE** creates an independent database from a target database or backups. It is often convenient for provisioning test clones when prerequisites and auxiliary setup are met.

**RESTORE/RECOVER** recovers the database from backups following a DR runbook. This is valuable for testing full disaster recovery procedures, including control files, `SPFILE`, archived redo, and file relocation.

`DUPLICATE` syntax depends on active vs. backup-based duplication, `DBID`, file naming, OMF, ASM, and Oracle release. Use scripts tested for your exact environment. Never copy commands verbatim from a different production system.

### 6.3. General recovery sequence

A database restore runbook typically includes these stages:

~~~text
1. Verify DBID, backups, and recovery target
2. Start auxiliary instance in NOMOUNT
3. Restore SPFILE/PFILE if needed
4. Restore appropriate control file
5. Mount database
6. Catalog backup pieces if unknown to repository
7. Restore datafiles
8. Recover database using available archived/online redo
9. Verify recovery state and file status
10. Open database in the appropriate recovery mode
11. Open required PDBs/services
12. Verify data and applications
~~~

Exact steps may vary when using backup control files, duplicate, RAC, ASM, or TDE.

### 6.4. Illustrative RESTORE and RECOVER commands

~~~text
RMAN> RESTORE DATABASE;
RMAN> RECOVER DATABASE;
~~~

These are the core commands once the database is mounted and backup/recovery targets are set. Before running, ensure control files, repository, and file name mappings are properly configured.

After complete recovery using a current control file, the database can open via standard `OPEN`. When performing incomplete recovery or recovering with a backup control file where required, `OPEN RESETLOGS` is needed. Never use `RESETLOGS` merely because a first `OPEN` attempt failed.

### 6.5. What should a restore test measure?

Record:
- Restore start timestamp.
- Backup read duration.
- Redo recovery duration.
- Volume of data/backups restored.
- Recovery target SCN/time.
- Any RMAN/ORA errors.
- Database `OPEN` timestamp.
- Service/app readiness timestamp.
- Actual storage consumed.
- Achieved RPO/RTO.

Do not stop the clock when RMAN reports `RESTORE` complete if the application still cannot access data.

## 7. Point-in-Time Recovery (PITR)

PITR recovers the database to a timestamp or SCN prior to an incident. It is useful for undoing unwanted logical changes, though its blast radius can be broad.

### 7.1. Determining the target

Targets can be specified by:
- Timestamp.
- SCN.
- Log sequence per appropriate procedures.

Use timestamps from a reliable clock source and record the timezone. When an incident is discovered late, target the moment immediately before the erroneous operation—not when a user reported the issue.

### 7.2. Illustrative time-based PITR

~~~text
RMAN> RUN {
  SET UNTIL TIME
    "TO_DATE('2026-11-14 09:30:00',
             'YYYY-MM-DD HH24:MI:SS')";
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

After incomplete recovery as required by procedure:

~~~sql
ALTER DATABASE OPEN RESETLOGS;
~~~

The timestamp in the example is illustrative. Verify timezone, SCN, and target semantics for your release. `RESETLOGS` creates a new database incarnation; update backup/recovery strategies after opening.

### 7.3. SCN-based PITR

~~~text
RMAN> RUN {
  SET UNTIL SCN 987654321;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
~~~

SCN represents a consistent point in the database. Determine the target SCN from audits, application logs, Flashback Query, alert logs, or monitoring data. RMAN applies SCN bounds per command semantics; confirm the exact target in the recovery plan.

### 7.4. Risks of whole-database PITR

Whole-database PITR discards all changes after the target, including valid transactions unrelated to the bug. Before performing it on production:
- Halt or gate writes.
- Identify post-target data that must be preserved.
- Extract/replay valid data if a mechanism exists.
- Assess impacts on sequences, external systems, and downstream consumers.
- Obtain explicit approval and follow a clear runbook.

In many cases, restoring a clone and extracting the needed data is safer than rewinding all of production.

## 8. Narrower-scope recovery options

Not every data error requires restoring the whole database.

### 8.1. Flashback Table

Flashback Table can return one or more tables to a prior timestamp/SCN within Oracle-supported bounds, typically requiring row movement enabled and sufficient undo retention.

~~~sql
ALTER TABLE app.orders ENABLE ROW MOVEMENT;

FLASHBACK TABLE app.orders
TO TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '20' MINUTE);
~~~

This is syntax illustration only; verify preconditions, dependencies, constraints, triggers, and flashback eligibility of the table. Flashback Table can change `ROWID`s and affect related tables. Test on a clone first.

### 8.2. Flashback Drop

The Recycle Bin can restore a dropped table if the object remains in the recycle bin and conditions are met:

~~~sql
FLASHBACK TABLE app.orders
TO BEFORE DROP;
~~~

Not every `DROP` can be flashed back. `PURGE`, certain object types, and other DDL operations may preclude recycle-bin recovery.

### 8.3. Tablespace Point-in-Time Recovery

TSPITR recovers a single tablespace to an earlier point without rewinding the entire database. It requires an auxiliary destination and must resolve dependencies between the recovered tablespace and the rest of the database.

Test:
- Whether the chosen tablespace qualifies for TSPITR.
- How dependent objects in other tablespaces are affected.
- Referential integrity and application consistency post-recovery.
- Auxiliary storage capacity.
- Metadata import/transport time and total recovery duration.

### 8.4. PDB point-in-time recovery

In a CDB, recovering a single PDB instead of the whole CDB may be needed depending on release capabilities and configuration. Tests must verify:
- CDB root and PDB state.
- Required backups/archived redo.
- PDB identity and services.
- Impact on shared data or external dependencies.
- Opening the PDB and validating application connections.

Do not run whole-CDB PITR for a fault confined to one PDB when a narrower PDB recovery option applies.

### 8.5. Block media recovery

If only a few blocks are corrupted and suitable backups/redo exist, RMAN can recover those blocks without restoring the entire datafile or database.

Tests must record:
- Block corruption locations.
- Backups containing clean blocks.
- Archived redo needed to recover the blocks.
- Exclusion conditions.
- `V$DATABASE_BLOCK_CORRUPTION` check results post-recovery.

## 9. Verifying data after recovery

An open database does not prove business data is valid. Multi-layer validation is required.

### 9.1. Checking database state

~~~sql
SELECT name,
       dbid,
       open_mode,
       database_role,
       resetlogs_change#,
       resetlogs_time
FROM v$database;
~~~

Check instance:

~~~sql
SELECT instance_name,
       status,
       database_status,
       startup_time
FROM v$instance;
~~~

Check files needing recovery:

~~~sql
SELECT file#,
       error,
       change#,
       time
FROM v$recover_file;
~~~

If using CDB, check PDB status:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

### 9.2. Checking block corruption

~~~sql
SELECT file#,
       block#,
       blocks,
       corruption_type,
       corruption_change#
FROM v$database_block_corruption
ORDER BY file#, block#;
~~~

Do not check this view only immediately after restore; compare against RMAN validation results and prior corruption records if available.

### 9.3. Reconciling row counts

Example:

~~~sql
SELECT status,
       COUNT(*) AS row_count
FROM app.orders
GROUP BY status
ORDER BY status;
~~~

Compare against:
- Pre-incident baseline.
- Expected state at the recovery target.
- Totals by date/partition.
- Totals by tenant/customer.
- Record counts by business status.

Row counts are only one signal. If a column was corrupted without changing row counts, `COUNT(*)` will not detect it.

### 9.4. Reconciling business aggregates

Example:

~~~sql
SELECT TRUNC(created_at) AS business_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
GROUP BY TRUNC(created_at)
ORDER BY business_day;
~~~

Compare totals at the same recovery target and matching timezone/business cutoff. Watch out for `NULL`, currency, rounding, soft deletes, and late-arriving data.

### 9.5. Hashing by key

To verify contents, compute digests by primary key or key ranges. Conceptual example:

~~~sql
SELECT order_id,
       STANDARD_HASH(
           TO_CHAR(order_id) || '|' ||
           TO_CHAR(customer_id) || '|' ||
           TO_CHAR(status) || '|' ||
           TO_CHAR(total_amount, 'FM9999999990D00'),
           'SHA256'
       ) AS row_hash
FROM app.orders
WHERE order_id BETWEEN :low_id AND :high_id
ORDER BY order_id;
~~~

This is an illustrative template; standardize date formats, number formats, NLS, `NULL`, and LOB representation for stable hashes. On large tables, hash by chunk/partition to limit load and pinpoint divergent ranges.

### 9.6. LOBs and external files

For `BLOB`/`CLOB`:
- Compare `DBMS_LOB.GETLENGTH`.
- Stream-hash contents in the application or an appropriate verification tool.
- Check LOB locators and read permissions.
- Verify external files if tables store only paths/URIs.

RMAN database backups do not automatically back up files stored outside the database, such as object storage objects or application-managed filesystem files.

## 10. Verifying objects and dependencies after recovery

A database can be `OPEN` while the application still fails because objects, grants, or services are not ready.

### 10.1. INVALID objects

~~~sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

Detailed list:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Compile schema when appropriate:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema      => 'APP',
        compile_all => FALSE
    );
END;
/
~~~

Never blindly run full-schema compilation on production. First identify why objects are invalid—missing dependencies, privileges, synonyms, or compile errors. Recompiling cannot fix objects referencing non-existent packages or tables.

### 10.2. Constraints and indexes

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated
FROM dba_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
~~~

~~~sql
SELECT owner,
       index_name,
       table_name,
       status,
       visibility
FROM dba_indexes
WHERE owner = 'APP'
ORDER BY index_name;
~~~

Verify constraints are `ENABLED`/`VALIDATED` as expected. `UNUSABLE` indexes can break queries/DML or shift execution plans.

### 10.3. Sequences and identity columns

If the application uses sequences for IDs:
- Verify sequence existence and privileges.
- Verify sequence values will not collide with recovered or replayed data.
- Verify `CACHE`/`ORDER` settings if required.
- Verify identity columns and generator strategies.

Never assume sequence values must equal `MAX(primary_key) + 1` in every system; sequences can have gaps from caching, rollbacks, or concurrency. The goal is preventing duplicate keys and preserving business semantics.

### 10.4. Other components

Check:
- Synonyms and database links.
- Grants/roles.
- Directory objects.
- Scheduler jobs and enabled state.
- Materialized views and refresh status.
- Triggers and packages.
- Services and listener registration.
- PDB saved state.
- TDE wallet.
- External table/file locations.
- Credentials and network ACLs.

External components often require reconfiguration after restoring onto a different host.

## 11. Testing Flashback Database and restore points

Flashback Database can rewind the database to a point prior to unwanted changes without restoring all datafiles from backup, provided prerequisites and flashback logs are met.

### 11.1. Guaranteed restore points

A guaranteed restore point retains the flashback logs needed to flash back to that point under Oracle conditions. It is useful before high-risk upgrades or deployments.

Example creating a restore point:

~~~sql
CREATE RESTORE POINT before_release
GUARANTEE FLASHBACK DATABASE;
~~~

Inspect:

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size
FROM v$restore_point
ORDER BY time DESC;
~~~

Prerequisites—`ARCHIVELOG`, Flashback Database, and FRA sizing—must be verified for your release and architecture before use. Guaranteed restore points retain flashback logs and can cause the FRA to grow rapidly.

### 11.2. Flashback Database

A typical runbook requires:
1. Stop write traffic and manage active sessions.
2. Shut down the database cleanly per procedure.
3. `STARTUP MOUNT`.
4. Confirm target restore point and sufficient flashback logs.
5. Execute `FLASHBACK DATABASE`.
6. Open the database with `RESETLOGS` as required.
7. Verify incarnation, data, and services.
8. Take an appropriate post-open backup.
9. Drop the restore point once retention is no longer needed.

Example core commands:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
FLASHBACK DATABASE TO RESTORE POINT before_release;
ALTER DATABASE OPEN RESETLOGS;
~~~

This is illustrative only, not an unadjusted production script. Check database role, RAC, PDBs, Data Guard, FRA, and recovery state before executing.

### 11.3. Limits of restore points

- Restore points do not replace independent backups.
- Flashback Database rewinds the entire database to before the target; post-target transactions may be lost.
- Restore points do not automatically revert external files or external systems.
- Guaranteed restore points retain flashback logs and can fill the FRA if left too long.
- After flashback/open resetlogs, backups and Data Guard must be re-evaluated under the new incarnation.

### 11.4. Dropping restore points after testing

Once confirmed no rollback to that point is needed:

~~~sql
DROP RESTORE POINT before_release;
~~~

Do not drop restore points immediately after deployment while the rollback window remains open. Conversely, never leave guaranteed restore points indefinitely as they can exhaust the FRA.

## 12. Testing application and schema rollbacks

A release typically spans multiple layers: application binaries, database schemas, data migrations, configuration, and external integrations. Rollbacks must address every layer.

### 12.1. Classifying changes

| Change | Commonly considered rollback approach |
| --- | --- |
| Java code/config without schema changes | Redeploy old artifact, restore config |
| Added nullable column | Often keep column and run old app if compatible |
| Added index | Drop index if no dependencies remain and safe |
| Added constraint | Disable/drop per tested migration, accounting for data |
| Renamed/dropped column | Old app may break; requires compatible migration or restore/forward-fix |
| Changed data type | Risk of data loss or incompatibility; requires backup/reverse transform |
| Data backfill | Requires inverse/compensating script or data restore |
| Dropped table/partition | May require PITR/backup restore; binary rollback cannot recover data |
| Complex DDL | Requires dedicated migration strategy and testing; never rely on transaction rollback |

### 12.2. Expand-contract

The expand-contract strategy reduces risk when applications and schemas must roll out across multiple steps.

**Expand**
- Add new columns/tables/indexes in a backward-compatible way.
- Keep old fields intact initially.
- Allow the old app version to continue running.
- Use dual-writes or temporary mappings where needed.

**Migrate**
- Backfill data in checkpointed batches.
- Reconcile row counts, checksums, and business aggregates.
- Switch application reads/writes to the new structures.
- Monitor errors and latency.

**Contract**
- Drop old columns/tables only after no older app versions remain active.
- Check jobs, reports, database links, and downstream consumers.
- Execute cleanup in a separate release with its own rollback plan.

Never bundle adding new fields, backfilling, switching application code, and dropping old fields into a single deployment when fast rollback is required.

### 12.3. Backward and forward compatibility

Minimum tests:
- Old app running against the post-expand schema.
- New app running against the post-migration schema.
- Old app able to run throughout the rollback window if needed.
- Both old and new jobs/consumers reading messages/data accurately.
- Migrations safely re-runnable or able to detect prior execution.
- Rollback scripts never deleting valid data created by the new app.

## 13. Oracle DDL and the limits of @Transactional

Oracle executes implicit commits around most DDL statements. Consequently, DDL migrations cannot be treated like normal DML reversible by a transaction rollback.

### 13.1. Example

~~~sql
UPDATE app.orders
SET status = 'READY'
WHERE order_id = 1001;

ALTER TABLE app.orders ADD source_code VARCHAR2(30);

ROLLBACK;
~~~

The `UPDATE` may already be implicitly committed before `ALTER TABLE` executes; the subsequent `ROLLBACK` does not revert the `UPDATE`. DDL also carries its own commit semantics.

Never wrap `ALTER TABLE`/`CREATE INDEX` scripts in `@Transactional` expecting the entire migration to roll back if a later statement fails.

### 13.2. Migrations can fail mid-way

A migration file with multiple DDL statements can partially execute before failing. The database may land in an intermediate state:
- Column added, but index not yet created.
- Some partitions converted.
- Constraint created, but validation failed.
- Backfill partially executed.
- Some objects compiled `INVALID`.

Migration tools record version state, but a migration status record does not undo DDL already executed.

### 13.3. Designing recoverable migrations

- Split migrations into small steps.
- Verify preconditions before mutating.
- Use explicit object names and check existence.
- Log checkpoints for long backfills.
- Include state verification queries after each step.
- Prepare inverse/compensating scripts when operations are reversible.
- Use restore points/PITR when whole-database rewind is required.
- Prepare forward-fixes when destructive rollbacks are unsafe.
- Never purge old data until the new app is proven stable.

## 14. Rollback strategies: binary rollback, schema rollback, and database restore

Three strategies carry different scopes and risks.

### 14.1. Binary rollback

Revert the application artifact to the prior version:
- Pull the exact immutable artifact previously released.
- Restore compatible config/secrets.
- Redeploy to the same environment or route traffic back to the old version.
- Verify the schema remains compatible with old code.
- Verify queues/messages contain no formats unreadable by the old app.

Binary rollback is fast, yet safe only while database schemas and data formats remain compatible.

### 14.2. Schema rollback

Execute a reverse migration or compensating migration:
- Check dependencies of the active app version.
- Determine whether newly written data can be transformed backward.
- Back up/export data that must be retained.
- Run rollback scripts pre-tested on a clone.
- Reconcile data after rollback.
- Check `INVALID` objects, constraints, and indexes.

Migrations do not always have an exact inverse. For example, collapsing multi-valued data into a normalized column may discard original detail. When irreversible, forward-fixes or restore/replay may be safer.

### 14.3. Database restore/flashback

Use when the whole database or supported scope must revert to pre-deployment state:
- Identify target and affected transactions.
- Stop writes.
- Execute flashback/PITR over the chosen scope.
- Open database in the right mode.
- Reconcile post-target data.
- Verify PDBs/services.
- Take backups and adjust Data Guard after incarnation changes.

This is a high-impact option. Never restore an entire database for a single broken API if a binary rollback or schema forward-fix suffices.

### 14.4. Blue-green or clone-based cutover

A new release can deploy onto a separate environment/clone database and cut over traffic after verification. On failure, route traffic back to the old environment if writes were synchronized by design.

Blue-green is safe only after solving:
- Data synchronization between both environments.
- Dual-write or change data capture.
- Cutover consistency point.
- External side effects.
- Services/DNS/connection pools.
- Handling post-cutover writes when switching back.

Never flip DNS to roll back if the new database already accepted transactions absent from the old database.

## 15. Release rollback test runbook

A rehearsal should follow a concrete execution checklist.

### 15.1. Before deployment

1. Record release ID and artifact checksum.
2. Record current schema version.
3. Record database identity and service.
4. Confirm latest backup and archived redo logs.
5. Create a restore point if using Flashback Database.
6. Verify FRA headroom and retention.
7. Export/capture application configuration.
8. Store migration scripts and inverse/compensating scripts.
9. Capture business baselines: row counts, aggregates, key samples.
10. Confirm RPO/RTO and rollback approver.

### 15.2. During deployment

- Run migrations in sequence.
- Log timestamps and output of each step.
- Verify schema version.
- Deploy application artifact.
- Run smoke tests and business transaction tests.
- Check alerts, invalid objects, and connection pools.
- Monitor errors, latency, locks, and jobs.
- Never drop old schemas until the rollback window expires.

### 15.3. Triggering rollback

Define triggers upfront:
- Error rate exceeds threshold.
- Business invariant violated.
- Data loss or duplicate data detected.
- Latency exceeds SLA.
- Migration causes severe locking/blocking.
- New app version incompatible with database/service.

Designate a clear rollback decision-maker. Never let multiple teams run competing rollback scripts simultaneously.

### 15.4. After rollback

- Confirm active serving application version.
- Confirm schema version and migration state.
- Inspect active transactions and connection pools.
- Reconcile data against business baselines.
- Verify constraints/indexes/`INVALID` objects.
- Verify jobs, queues, database links, and external integrations.
- Inspect the alert log.
- Account for data created during the deployment window.
- Decide whether to keep or drop restore points.
- Take a fresh backup if database incarnation or recovery state changed.

## 16. Testing data migrations and inverse migrations

Data migrations must be tested with representative data and near-production volume.

### 16.1. Checking preconditions

Examples:
- Source column exists.
- Target column does not exist or is in expected state.
- Zero duplicate keys.
- Data falls within expected value ranges.
- Constraints are not violated.
- Sufficient undo/temp/tablespace capacity.
- Adequate batch window.

If preconditions fail, the migration must halt before modifying data.

### 16.2. Idempotency

A migration can be re-run after failure if designed idempotently:
- Check object existence before creating.
- Upsert by deterministic keys.
- Backfill with checkpoints.
- Log progress and processed row counts.
- Avoid repeating non-idempotent side effects.
- Resume cleanly from the last committed chunk.

Idempotency does not mean a script can run blindly anytime without inspecting data. Clearly define pre- and post-conditions.

### 16.3. Testing inverse migrations

When an inverse script exists:
- Run the forward migration on a clone.
- Record baseline.
- Run the inverse migration.
- Reconcile data, schema, and objects.
- Run the old application version.
- Run business queries.
- Check sequences/identities, LOBs, grants, and indexes.
- Check data created during the migration window.

If the inverse cannot restore lost information, document limitations and adopt forward-fix or restore strategies.

## 17. Testing Data Guard and site recovery

If architecture includes Data Guard, recovery tests must cover role transitions and applications.

### 17.1. Planned switchover

Check:
- Primary/standby roles.
- Transport/apply lag.
- Archive gaps.
- SRLs on both members.
- Broker configuration.
- Role-based services.
- Client reconnection.
- Backups after role transition.

### 17.2. Simulated failover

Never test failover by damaging production. Run approved DR exercises:
- Isolate site/instance per test scenario.
- Confirm standby has latest redo.
- Measure RPO.
- Perform failover.
- Start services and test applications.
- Measure RTO.
- Reintegrate/reinstate or rebuild the old primary.

### 17.3. Standby does not replace backups

Data Guard replicates logical changes too. Tests must confirm independent backups can still restore to a point prior to a logical error even after the standby applied the erroneous operation.

## 18. Test evidence and pass/fail criteria

A test is complete only when evidence enables others to reproduce and evaluate it.

### 18.1. Evidence to archive

- Test ID, timestamps, and operator.
- `DBID`, `DB_UNIQUE_NAME`, Oracle release/RU.
- Backup tags, backup set keys, and archive ranges.
- Recovery target SCN/time.
- RMAN logs and alert logs.
- Restore/recover start/end timestamps.
- Database/PDB open mode.
- Data reconciliation report.
- Object/constraint/index status.
- Application smoke test output.
- Measured RPO/RTO.
- Deviations, blockers, and corrective actions.

Never store passwords, wallet secrets, tokens, or sensitive data in reports.

### 18.2. Pass criteria

Examples:
- Restore completed on isolated host.
- Database opened at exact target and role.
- No unexpected files requiring recovery remain.
- Required PDBs/services opened.
- Row counts and business aggregates match expected state.
- Sample hashes/keys match.
- No unresolved new corruptions.
- No critical objects `INVALID`.
- Application smoke tests pass.
- RPO/RTO meet targets.
- Evidence and logs archived.

### 18.3. Fail criteria

- Missing backups or archived redo logs.
- TDE keystore cannot be opened.
- Restore/recover exceeds RTO.
- Database fails to open at target.
- Data reconciliation mismatches.
- Services/applications fail to operate.
- Unable to revert schema/app to a compatible version.
- Rollback loses transactions that must be retained.
- Missing evidence or indeterminate final state.

On failure, record root cause and remediation actions. Never mark a test passed merely because the database instance is `OPEN`.

## 19. Periodic testing schedule

Frequency depends on RPO/RTO and criticality.

| Activity | Suggested frequency | Purpose |
| --- | --- | --- |
| Backup job monitoring | Daily | Detect failed jobs and missing archives |
| RMAN backup validation | Scheduled | Verify backups/files are readable |
| Restore validation | Weekly/monthly per risk | Verify restore paths |
| Isolated restore test | Quarterly or per policy | Prove real restore/recover execution |
| PITR/Flashback exercise | Before risky releases & periodic | Verify recovery targeting |
| Deployment rollback rehearsal | Every major release or schema change | Prove app/schema rollback |
| Data Guard DR exercise | Per DR policy | Measure site recovery RPO/RTO |
| TDE key recovery test | Per key management policy | Ensure backups can be decrypted |

This schedule is a reference. Systems with strict RPO/RTO need more frequent testing; lower-tier environments may adjust frequency while still requiring evidence.

## 20. Common errors in recovery and rollback tests

| Error/symptom | Possible cause | Mitigation |
| --- | --- | --- |
| `RMAN-06025` | Matching archived log/backup not found | Check backup inventory, thread/sequence, and archive range |
| `RMAN-06054` | RMAN requires archived log unknown to repository | Catalog/register logs or recover from backup |
| `ORA-01113` | Datafile needs media recovery | Identify file and apply matching redo |
| `ORA-01157` / `ORA-01110` | Cannot open datafile | Check paths, storage, permissions, and file status |
| `ORA-19809` | FRA limit exceeded | Check archive/backup retention and storage |
| `ORA-19870` | Error restoring backup piece | Read underlying error; check media/readability |
| `ORA-01555` | Snapshot too old | Check undo retention, query duration, and workload |
| `ORA-01578` | Data block corruption | Identify blocks and RMAN recovery plan |
| `ORA-01031` | Insufficient privileges | Check `SYSDBA`/RMAN/catalog privileges |
| TDE keystore error | Missing wallet/key or wrong password | Restore key material per procedure |
| Migration rollback failed | DDL committed or data change irreversible | Forward-fix, compensating migration, or PITR |
| Old app errors after binary rollback | Incompatible schema changes | Expand-contract or restore schema/data |
| Restore test overwrote production | Wrong file mapping/service isolation | Stop immediately, isolate, and follow incident runbook |

Always read the entire RMAN/ORA error stack and alert log. A single error code usually indicates only which step failed, not the full root cause.

## 21. Example: pre-release recovery rehearsal

Suppose release `R42` includes:
- Adding column `source_channel`.
- Backfilling values from a staging table.
- New app reading this column.
- Plan to keep binary `R41` ready for rollback for 48 hours.

A sound rehearsal:

1. Restore a clone from the latest backup.
2. Record baseline counts and aggregates.
3. Create a guaranteed restore point if the database rollback strategy relies on it.
4. Run expand migration: add nullable column and matching index.
5. Run chunked backfill.
6. Reconcile row counts and `source_channel` values.
7. Deploy app `R42` and run smoke/business tests.
8. Write new test data using app `R42`.
9. Redeploy app `R41` against the same expanded schema.
10. Verify app `R41` still reads/writes cleanly.
11. Verify data created by `R42` was not lost.
12. Test inverse migration on a separate clone if a reverse script exists.
13. If database flashback is needed, rewind the clone to the restore point and confirm post-restore-point transactions are discarded as expected.
14. Measure each step's duration and record RPO/RTO.

Results must distinguish:
- Binary rollback from `R42` to `R41` is safe because the new schema remains compatible.
- Dropping `source_channel` immediately on rollback could lose data created by `R42`.
- Whole-database flashback discards post-restore-point transactions, so it cannot replace binary rollback if new data must be preserved.

## 22. Example: reconciliation after PITR

Suppose an accidental order deletion happened at 10:15. The recovery target is chosen at 10:14:30.

After recovering the clone:
- Verify the deleted order ID exists at target.
- Verify other orders created before target still exist.
- Verify post-target transactions are absent in the clone under whole-database PITR.
- Recompute order totals by business date.
- Cross-check payment references and external payment providers.
- Verify sequences will not collide if extracting data from the clone.
- Export rows needing restoration into production using an approved procedure.

Do not swap the entire PITR clone back over production if valid post-target transactions must be preserved. Controlled extraction and merging may be required.

## 23. Data recovery runbook checklist

- [ ] Identified `DBID`, `DB_UNIQUE_NAME`, role, and Oracle release.
- [ ] Defined recovery scope: database, datafile, tablespace, PDB, block, or logical data.
- [ ] Defined RPO/RTO and recovery target.
- [ ] Verified backups, control files, `SPFILE`, and archived redo logs.
- [ ] Verified TDE wallet/keystore if applicable.
- [ ] Verified storage, Oracle Home, and file mappings.
- [ ] Isolated host/service/network of restore target.
- [ ] Executed appropriate `RMAN PREVIEW`/`VALIDATE`.
- [ ] Executed restore/recover on target.
- [ ] Opened database in right mode and handled `RESETLOGS` if required.
- [ ] Verified PDBs, services, and database role.
- [ ] Checked corruption, recovery files, and alert log.
- [ ] Reconciled row counts, business aggregates, and hashes.
- [ ] Checked constraints, indexes, sequences, and `INVALID` objects.
- [ ] Executed application smoke tests.
- [ ] Measured RPO/RTO and archived evidence.
- [ ] Created fresh backup if needed.
- [ ] Documented corrective actions for all discrepancies.

## 24. Deployment rollback testing checklist

- [ ] Archived pre-release artifact and config versions.
- [ ] Recorded schema version and database identity.
- [ ] Prepared migration scripts and preconditions.
- [ ] Evaluated backward/forward compatibility.
- [ ] Accounted for DDL implicit commits.
- [ ] Prepared inverse/compensating scripts where feasible.
- [ ] Prepared backups/restore points if database rewind is needed.
- [ ] Evaluated transactions occurring after the rollback target.
- [ ] Verified queues/messages/external side effects.
- [ ] Tested old app against new schema.
- [ ] Tested new app after migration.
- [ ] Reconciled data after migration and rollback.
- [ ] Checked `INVALID` objects, constraints, and indexes.
- [ ] Measured rollback duration and service restoration time.
- [ ] Defined approver, owner, and rollback triggers.
- [ ] Archived logs, evidence, and test results.

## 25. Self-practice exercises

1. Distinguish backup validation from restore testing.
2. Why does `RMAN RESTORE DATABASE VALIDATE` not replace an actual restore?
3. How does `CROSSCHECK` differ from `VALIDATE`?
4. What does `RESTORE DATABASE PREVIEW` prove?
5. Define RPO and RTO with concrete examples.
6. List components needed when preparing a restore on a new host.
7. Why is a TDE wallet/keystore a recovery dependency?
8. Distinguish complete recovery from point-in-time recovery.
9. When does PITR require `OPEN RESETLOGS`?
10. Why should `RESETLOGS` never be used merely to retry `OPEN`?
11. Distinguish Flashback Table from Flashback Database.
12. When can Flashback Drop recover a table?
13. List conditions to evaluate before TSPITR.
14. How does PDB recovery differ from whole-CDB recovery?
15. What types of failures does block media recovery address?
16. Write a query to inspect database role and open mode.
17. Write a query to check files needing recovery.
18. Write a query to inspect database block corruption.
19. Why is row count insufficient to prove data correctness?
20. Design business aggregates to reconcile orders after PITR.
21. Explain how to hash data by key range.
22. List objects to check after restore beyond datafiles.
23. Can `INVALID` objects always be fixed with `COMPILE_SCHEMA`?
24. Why do sequence values not necessarily equal `MAX(primary key) + 1`?
25. Distinguish binary rollback from schema rollback.
26. Why does Oracle DDL not roll back like DML inside `@Transactional`?
27. Explain the expand-contract strategy.
28. When is a forward-fix safer than an inverse migration?
29. Why can whole-database flashback lose valid transactions after a restore point?
30. Design a DR/deployment rollback rehearsal with targets, reconciliation data, RPO/RTO, evidence, and approver.

**A recovery plan is only proven when a database can be restored in an isolated environment, opened at the exact recovery target, and reconciled against business data. A rollback plan is only trustworthy once binaries, schemas, and related side effects have all been tested.** Distinguish RMAN validation from real restores, define RPO/RTO, verify backups alongside archived redo/TDE keys, validate data and objects post-recovery, and design backward-compatible migrations. In Oracle, DDL triggers implicit commits, so `@Transactional` can never replace a migration rollback or database recovery strategy.
