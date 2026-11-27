# Recovering from Accidental Deletions vs. Infrastructure Failures in PostgreSQL

When PostgreSQL data is accidentally deleted, the first reflex is often restarting the database or failing traffic over to a standby. Neither action may recover the lost data. With physical replication, a valid `DELETE` or `DROP` on the primary is normally replayed onto the standby as well. Failing over to a replica can therefore carry the exact deleted state straight over to the new node.

Proper recovery starts by determining **what happened, when, which data was affected, and what copies/WAL remain**. If the deletion already committed, the standard recovery path is using a base backup and WAL archive for Point-in-Time Recovery (PITR) to a point just before the operation, on an independent cluster. Afterward, extract the required data and bring it back into the live system following a controlled plan.

Infrastructure failures are fundamentally different. If a host, volume, availability zone, or entire region is lost, the goal may be failing over to a standby, restoring from backups, or rebuilding in another location. You must distinguish the two because **HA maintains service availability when nodes/infrastructure fail; backups and PITR rewind data state prior to an event**.

This lesson covers responding to accidental deletions, choosing recovery targets, standing up a recovery cluster, rescuing rows/tables, handling `DELETE`/`TRUNCATE`/`DROP`, distinguishing data errors from infrastructure failures, along with runbooks and hands-on exercises.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Classify uncommitted `DELETE`, committed `DELETE`, `TRUNCATE`, `DROP TABLE`, and `DROP DATABASE`.
2. Determine the incident time and scope of affected data.
3. Preserve evidence and prevent subsequent operations from destroying recovery options.
4. Explain why physical standbys normally replay accidental deletions too.
5. Distinguish failover, PITR, base backup restore, and logical restore.
6. Use a base backup and WAL archive to recover to a recovery target.
7. Understand `recovery_target_time`, `recovery_target_lsn`, `recovery_target_xid`, inclusive semantics, and `recovery_target_action`.
8. Recover on an isolated cluster and extract the required data.
9. Bring data back into production via `INSERT`, `COPY`, `pg_dump`/`pg_restore`, or application workflows.
10. Avoid overwriting new valid data created after the PITR point.
11. Handle host, disk, filesystem, network, availability zone, and region outages.
12. Choose failover vs. restore based on failure type and RPO/RTO.
13. Establish procedures protecting WAL archives, base backups, credentials, and restore environments.
14. Plan post-recovery verification and recurrence prevention.

## 2. Classifying the Incident Before Acting

Not every database incident requires PITR. Classify first:

| Scenario | Example | Initial Response Direction |
| --- | --- | --- |
| Uncommitted operation | `DELETE` inside an open transaction | `ROLLBACK` if right transaction and uncommitted |
| Committed operation | Accidental `DELETE` of a customer cohort | PITR onto separate cluster, extract data |
| Structural drop | `DROP TABLE` or `DROP DATABASE` | PITR/backup restore; then extract object/data |
| Partial deletion | `DELETE` with wrong `WHERE` clause | PITR or alternate data source; controlled row merge |
| Application logic bug | Job erroneously updates millions of rows | Stop job, pinpoint time and scope, PITR/repair |
| Host/VM failure | OS or instance down | Failover or rebuild from backup |
| Storage failure | Volume fault, filesystem corruption | Stop writes, preserve storage, restore/DR |
| AZ/region outage | Primary and storage unreachable | DR failover or restore in another region |
| Network partition | Primary and standby lose connectivity | Evaluate quorum/fencing, prevent split-brain |
| Database process crash | PostgreSQL stops abnormally | Crash recovery; check WAL/data integrity |

### 2.1. Accidental Deletion Is Logical Data Loss

A valid SQL statement can delete data without raising any PostgreSQL error. The server executes the request faithfully; the mistake lies in operator action or business logic. Once the transaction commits, the change becomes part of database history and propagates to standbys via physical replication.

### 2.2. Infrastructure Failure Is an Availability or Physical Integrity Failure

A host power loss, unmountable volume, or unreachable network makes the database unavailable even though logical data was not deleted. Determine whether you can restart/crash-recover on the old node, promote a standby, or restore onto new infrastructure.

### 2.3. An Incident Can Involve Both

For example, a volume fails while an erroneous deletion job is running. You must address data integrity and infrastructure recovery together. Never lock into a single plan based solely on the first symptom.

## 3. The First Question: Has the Transaction Committed?

If the deletion sits inside an uncommitted transaction, PostgreSQL can still roll back all changes.

~~~sql
BEGIN;

DELETE FROM app.orders
WHERE created_at < DATE '2020-01-01';

-- Notice wrong WHERE condition before COMMIT
ROLLBACK;
~~~

`ROLLBACK` discards that transaction's changes.

### 3.1. Transaction Already Committed

~~~sql
BEGIN;

DELETE FROM app.orders
WHERE order_id = 12345;

COMMIT;
~~~

After `COMMIT`, running `ROLLBACK` in a new transaction cannot undo the earlier transaction. PostgreSQL has no general-purpose "undo commit" command to automatically restore deleted rows.

### 3.2. Transaction Still Open in Another Session

If you hold the exact session/backend executing the operation and its transaction has not committed yet, it can be rolled back from that session. Never terminate backends blindly; verify PID, owner, and transaction state first.

### 3.3. Savepoints

A savepoint only rewinds to a point inside the active transaction:

~~~sql
BEGIN;
SAVEPOINT before_delete;

DELETE FROM app.customers WHERE ...;

ROLLBACK TO SAVEPOINT before_delete;
COMMIT;
~~~

Savepoints cannot recover a transaction that already committed in the past.

### 3.4. DELETE Under Autocommit

Many clients execute each statement in its own transaction and auto-commit upon completion. If a user runs `DELETE` directly in autocommit mode, the change commits immediately when the statement finishes.

## 4. Immediate Actions Upon Detecting an Accidental Deletion

The first priority is preserving recovery options and containing blast radius.

1. Stop the job, script, deployment, or operation continuing to delete/modify data.
2. Identify the database, schema, table, tenant, and `WHERE` condition involved.
3. Record detection time and estimated operation time.
4. Save query text, `application_name`, PID, user, transaction ID, and logs if available.
5. Determine whether the transaction committed.
6. Check primary, standbys, base backups, WAL archive, and retention.
7. Avoid running cleanups or deleting backups/WAL during investigation.
8. Select a restore target and an independent target cluster.
9. Notify data owners and recovery decision-makers.
10. Log every operational action taken since the incident began.

### 4.1. Stop the Faulty Source

If an application worker is running a bad `DELETE`, pause the worker or block the offending execution path. You do not need to shut down the entire database if the faulty source can be stopped precisely.

### 4.2. Preserve Logs and Metadata

Collect PostgreSQL logs, application logs, job logs, audit records, deployment timestamps, query IDs, and the backup catalog. These artifacts pinpoint the recovery target.

### 4.3. Never Run PITR on the Live Primary

PITR restores a cluster to a past state. Perform it in a separate data directory/instance so you preserve the current primary and valid post-incident changes.

### 4.4. Do Not Reflexively Promote a Standby

If the standby already replayed the `DELETE`, promoting it merely creates a new primary with the data still deleted. Before failing over, check the standby's replay position to see whether it actually holds the desired data state.

## 5. Finding When the Deletion Occurred

PITR requires a recovery target precise enough to stop prior to the data-losing transaction.

### 5.1. Time Sources

Combine PostgreSQL server logs, application logs and request IDs, job scheduler history, audit extensions or audit tables, transaction timestamps in surviving data, monitoring/alert timestamps, and appropriate WAL decoding tools.

### 5.2. Client and Server Clocks May Differ

Clients, application servers, database hosts, and log collectors may use different timezones or clocks. Normalize to UTC, check NTP/clock drift, and distinguish when a query was sent from when the transaction committed.

### 5.3. Query Start Is Not Commit Time

A `DELETE` can run for a long time. Query start is when execution began; commit happens later. The recovery target must precede the data-losing commit, not necessarily the query start.

### 5.4. Multi-Statement Transactions

If a transaction deleted data and also performed valid changes before `COMMIT`, PITR before that commit removes the entire transaction. After restore, evaluate valid changes from the same transaction to re-apply them if needed.

### 5.5. Tracing via Application Requests

If application logs capture request IDs, correlate them with jobs, database sessions, `application_name`, or query logs. Avoid estimating timestamps from coarsely sampled dashboards.

## 6. Determining the Scope of Deleted Data

Before restoring, compile a specific inventory:

- Database/schema/table names.
- Affected primary keys or business keys.
- Creation/update time range of affected rows.
- Estimated row count.
- Foreign keys and dependent tables.
- Related triggers, audit tables, outbox/event tables.
- Valid post-incident changes that must be preserved.

### 6.1. Conditional DELETE

Example:

~~~sql
DELETE FROM app.orders
WHERE tenant_id = 42
  AND status <> 'archived';
~~~

The scope may be all orders for tenant 42 except archived ones. Find the actual executed query and parameter values; query templates alone may be insufficient to identify affected rows.

### 6.2. TRUNCATE

`TRUNCATE` removes all rows from a table faster than a normal `DELETE` and carries distinct transaction semantics. It can `CASCADE` if specified. Recovery normally requires PITR/backups or another copy.

### 6.3. DROP TABLE

`DROP TABLE` removes the relation and associated metadata. Once committed, you must recover the schema/table from a pre-DROP state and then extract needed data.

### 6.4. DROP DATABASE

`DROP DATABASE` removes the entire database. Recovery normally requires standing up the cluster/database from a base backup or PITR prior to the `DROP`. Other databases on the same cluster may remain intact, yet confirm scope.

### 6.5. CASCADE

`DROP ... CASCADE` can drop dependent objects. During recovery, identify the full dependency graph: views, foreign keys, functions, types, and related objects.

## 7. Why Cannot a Physical Standby Save an Accidental Deletion?

Physical replication copies WAL to reproduce physical changes on the standby. Once `DELETE` commits on the primary, the standby normally replays that change.

~~~text
Primary
  DELETE FROM app.customers WHERE id = 42;
       |
       v
      WAL
       |
       v
Physical standby replays WAL
       |
       v
Row id=42 also vanishes on standby
~~~

### 7.1. Standbys Fit Node Failures

If the primary host dies while a standby is healthy and has received required WAL, promoting the standby minimizes downtime.

### 7.2. A Standby Is Not a Historical Snapshot

A standby constantly tries to stay caught up with the primary. It does not automatically retain yesterday's data state for rewinding.

### 7.3. Replication Delay Is Not a Recovery Policy

An asynchronous standby might lag by a few seconds or minutes. Relying on incidental lag to rescue a `DELETE` is unreliable. Once the standby replays the delete transaction, that window is gone.

### 7.4. Delayed Standbys

PostgreSQL can configure `recovery_min_apply_delay` to defer applying WAL on a standby. This is a bounded defense layer: the delay must exceed detection-plus-action time; WAL must still be retained; and operators must pause recovery before the delete transaction applies. Delay increases lag and can impact failover/RPO. It does not replace backups/PITR.

## 8. Distinguishing HA, Backups, PITR, and DR

| Mechanism | Goal | Recovers Accidental Deletion? | Recovers Node/Region Loss? |
| --- | --- | --- | --- |
| Physical standby | Availability, failover | Normally no; deletes are replayed | Possible |
| Synchronous replication | Reduce commit loss on failover | No; delete commits are also acknowledged/replayed | Possible |
| Base backup | Starting point for restore | Yes, given pre-incident state/appropriate WAL | Yes |
| WAL archive + PITR | Rewind to a point in time | Yes | Yes, if backup/archive remain reachable |
| Logical dump | Recover dumped objects/data | Yes if dumped before incident | Yes for dumped scope |
| Delayed standby | Window to spot logical errors | Possible if replay paused in time | Limited |
| Storage snapshot | Storage copy at snapshot time | Yes if taken pre-incident and consistent | Architecture-dependent |

### 8.1. High Availability

HA minimizes downtime when a component fails. It prioritizes bringing the service back online quickly.

### 8.2. Backup

Backups provide independently restorable copies of data. They must be stored in an appropriate failure domain and regularly tested.

### 8.3. Point-in-Time Recovery

PITR combines a base backup with WAL to reconstruct database state at a historical point.

### 8.4. Disaster Recovery

DR encompasses people, infrastructure, credentials, backup copies, networking, DNS, applications, and recovery procedures in an alternate failure domain. A single backup file is not a DR plan.

## 9. How Does PITR Work?

A base backup is a consistent physical copy of the cluster over a backup window. PostgreSQL needs WAL to replay required changes and complete recovery.

~~~text
Base backup
    |
    v
Start recovery
    |
    v
Replay WAL continuously
    |
    v
Recovery target reached
    |
    +--> Pause
    +--> Promote
    +--> Shutdown
~~~

### 9.1. Base Backup and WAL Chain

To recover to a point in time, you must have:

1. A valid base backup.
2. Continuous WAL from the backup's required starting point to the recovery target.
3. Timeline history files if recovery crosses timeline switches.
4. A working `restore_command` able to fetch WAL.
5. Compatible storage, permissions, and PostgreSQL version.

### 9.2. WAL Is Not a Human-Readable SQL Log

WAL holds storage- and transaction-level records. Do not expect to find a `DELETE` statement by grepping WAL files. Use logs/audits to locate queries; use WAL to recover via PostgreSQL's mechanism.

### 9.3. PITR Is Cluster-Scoped

Physical PITR recovers the state of the cluster/database system at a point, not an isolated undo button for a single row. To rescue just one table, restore the cluster elsewhere and export the needed table/rows.

### 9.4. A Restore Creates a New Timeline When Promoted

If recovery stops at a target and promotes, the instance begins writing WAL on a new timeline. Keep the PITR cluster separate for investigation or extraction; never confuse its new timeline with current production history.

## 10. Choosing a Recovery Target

PostgreSQL supports recovery targets such as `recovery_target_time`, `recovery_target_lsn`, `recovery_target_xid`, `recovery_target_name`, and `recovery_target = immediate`. Exact names, behaviors, and configuration vary by major version. Consult the documentation for your exact version before running.

### 10.1. recovery_target_time

Stops recovery by timestamp:

~~~conf
recovery_target_time = '2026-11-14 02:17:30+00'
~~~

Commonly used when reliable timestamps exist in logs. Place the target prior to the offending commit and verify inclusive semantics.

### 10.2. recovery_target_lsn

Stops by LSN:

~~~conf
recovery_target_lsn = '0/7A120F0'
~~~

LSNs fit when exact WAL positions are captured from replication/diagnostic tools. Never guess an LSN from a timestamp.

### 10.3. recovery_target_xid

Stops by transaction ID once the offending transaction is identified and target semantics are understood. Transaction IDs can wrap around; never pull a bare number from old logs without verifying context.

### 10.4. recovery_target_name

You can create a named restore point prior to a deployment or risky operation:

~~~sql
SELECT pg_create_restore_point('before_customer_cleanup');
~~~

Then use `recovery_target_name` with the matching name in recovery config. Restore points must be created beforehand; they cannot be added retroactively after an accidental deletion.

### 10.5. recovery_target = immediate

Stops at the earliest point where the backup achieves consistency under recovery rules. Useful for cloning/testing workflows, yet it does not mean "right before a `DELETE`."

## 11. Inclusive and Exclusive Targets

PostgreSQL provides `recovery_target_inclusive` to control whether the transaction/record at the target is included or recovery stops prior to it, depending on the target type.

~~~conf
recovery_target_time = '2026-11-14 02:17:30+00'
recovery_target_inclusive = false
~~~

### 11.1. Verify Semantics Carefully

Inclusive semantics depend on target type and how PostgreSQL resolves the stop point. For time targets, transaction commit boundaries matter. Never assume setting a timestamp equal to a log entry guarantees the deletion transaction was excluded.

### 11.2. Choosing a Safe Target

If commit occurred around `02:17:30`, choose a target clearly prior to that moment, then inspect data on the restored cluster. If uncertain, restore a few candidate targets in disposable environments.

### 11.3. recovery_target_action

Common choices:

- `pause`: pauses replay at the target and keeps the instance in recovery for inspection.
- `promote`: finishes recovery and promotes into a new primary.
- `shutdown`: shuts down the server upon reaching the target.

For accidental deletions, `pause` is typically helpful to inspect state before deciding to promote. If the goal is solely reading/exporting, promotion is unnecessary when data can be accessed in recovery state.

## 12. Configuring PITR on a Separate Cluster

Sample workflow with modern PostgreSQL:

1. Prepare the base backup in a separate directory.
2. Prepare a complete WAL archive.
3. Copy the base backup into the restore instance's PGDATA.
4. Create `recovery.signal`.
5. Configure `restore_command` and target.
6. Start the instance on a separate port and isolated network.
7. Watch logs until recovery stops.

Sample configuration:

~~~conf
restore_command = 'cp /backup/archive/%f %p'
recovery_target_time = '2026-11-14 02:17:00+00'
recovery_target_inclusive = false
recovery_target_action = 'pause'
~~~

This illustrates a filesystem-based archive. For object storage, use an appropriate fetch command/script. Never use production paths if there is any risk of overwriting or reading the wrong cluster.

### 12.1. recovery.signal

In modern versions, create `recovery.signal` inside the data directory to request archive recovery/PITR. Older versions use different configuration; check your major version's docs.

### 12.2. standby.signal

`standby.signal` is for standby mode, typically paired with `primary_conninfo`/streaming. Do not confuse standby bootstrapping with standalone PITR.

### 12.3. Never Configure Recovery on a Live Production Primary

Never place `recovery.signal` or recovery targets into a PGDATA actively serving production. Always use a separate data directory copy.

### 12.4. Restore Commands Must Handle Errors Properly

The command must return the right exit status when a WAL file is absent and must be safely re-invocable. With object storage, enforce bounded timeouts/retries and keep secrets out of logs.

## 13. Runbook: Recovering a Committed DELETE

Suppose an accidental `DELETE` committed at time T.

### Step 1: Stop the Offending Actor

Pause the worker/job or deploy a hotfix so deletions do not continue. If possible, switch the app to read-only mode or disable the offending feature.

### Step 2: Pinpoint Commit Timestamp

Gather logs and select a target immediately prior to transaction commit. Normalize timestamps to UTC and document confidence.

### Step 3: Verify Recovery Assets

Confirm a suitable base backup, continuous WAL archive, timeline history, and encryption key access.

### Step 4: Stand Up an Isolated PITR Cluster

Restore the backup onto a separate host/volume with a separate port, isolated network, and recovery target prior to the deletion transaction.

### Step 5: Verify Results

Confirm deleted rows/keys are present. Confirm valid data prior to the target is intact. Determine the exact rows to extract.

### Step 6: Export Data

Use `pg_dump` for a table or conditional `COPY`/queries. Preserve schema, constraints, indexes, and needed dependency metadata.

### Step 7: Bring Data Back to Production

Import into a staging table, check conflicts/duplicates/foreign keys, then merge via a reviewed transaction or migration script.

### Step 8: Verify Application State

Run business queries, row counts, aggregate checks, and smoke tests.

### Step 9: Document

Record recovery target, backup ID, WAL range, restored row count, scripts, approver, and completion time.

## 14. Why Restore Onto a Separate Cluster?

Suppose the deletion occurred at 02:17 and production continued accepting orders until 03:00.

If you rolled all of production back to 02:16:
- Valid orders created after 02:17 would disappear.
- Other legitimate updates would also be lost.
- Applications might be unaware that post-target requests had succeeded.

Instead:

~~~text
Current production (03:00)
  New data + accidental deletion state
          |
          | Do NOT roll back this cluster
          |
PITR cluster (02:16)
  State prior to DELETE
          |
          v
Export rows to recover
          |
          v
Production staging table
          |
          v
Controlled merge
~~~

### 14.1. Preserve Valid Writes

Restoring separately preserves production writes made after the incident. Only the targeted data is extracted and merged.

### 14.2. Compare Both States

You can diff current production against the PITR cluster to find missing rows, rows already recreated/updated, or conflicting rows.

### 14.3. Prevent Split-Brain

The PITR cluster is strictly for reading/exporting. Never allow production applications to write to it or let both clusters serve independent write traffic.

### 14.4. Retain the PITR Cluster Until Investigation Ends

Do not delete the restore instance immediately after export if evidence is needed or additional data may need extraction. Apply appropriate retention and access controls.

## 15. Extracting a Table with pg_dump

If you need an entire table as of the recovery target:

~~~bash
pg_dump \
  --host=pitr-db.example.internal \
  --port=55432 \
  --username=restore_reader \
  --dbname=appdb \
  --table=app.customers \
  --format=custom \
  --file=/recovery/export/customers.dump
~~~

Restore into a staging database:

~~~bash
pg_restore \
  --host=production-staging.example.internal \
  --port=5432 \
  --username=restore_operator \
  --dbname=recovery_staging \
  --no-owner \
  --no-privileges \
  /recovery/export/customers.dump
~~~

### 15.1. A Table Dump Does Not Always Include All Dependencies

A table dump may omit dependent objects such as roles, grants, functions, types, or referenced tables. Inspect schema and dependencies.

### 15.2. Use Schema-Only When Comparing

`pg_dump` can export schema alone. Diff DDL between PITR and production before restoring data if schemas changed after the incident.

### 15.3. Never Restore Directly Over a Live Production Table

Restore into a staging table/database first. Matching table names or differing schemas can cause collisions, overwrites, or constraint errors.

## 16. Extracting Rows with COPY

If only a subset of rows is needed:

~~~sql
COPY (
    SELECT customer_id, email, created_at, status
    FROM app.customers
    WHERE tenant_id = 42
) TO '/recovery/export/customers.csv'
WITH (FORMAT csv, HEADER true);
~~~

File paths in `COPY` are server-side paths requiring PostgreSQL process access. When running from a client, use `psql`'s `\copy` to write files on the client machine.

Example:

~~~sql
\copy (SELECT customer_id, email, created_at, status FROM app.customers WHERE tenant_id = 42) TO '/recovery/export/customers.csv' WITH (FORMAT csv, HEADER true)
~~~

### 16.1. Specify Columns Explicitly

Avoid `SELECT *` in long-lived recovery scripts if schemas might differ between PITR and production. List columns explicitly and map types.

### 16.2. Binary Data and Encoding

CSV may require attention to quoting, NULLs, delimiters, encoding, and `bytea`. For complex data, custom-format `pg_dump` or binary `COPY` may fit better.

### 16.3. Protect Export Files

Export files may hold PII or payment-related data. Store in encrypted staging, restrict permissions, set short retention, and securely wipe per policy once finished.

## 17. Merging Rows Back Into Production

Before importing, determine whether current rows were recreated or modified after the incident.

### 17.1. Use a Staging Table

~~~sql
CREATE SCHEMA IF NOT EXISTS recovery_stage;

CREATE TABLE recovery_stage.customers_restore
(LIKE app.customers INCLUDING DEFAULTS);
~~~

Load rows into the staging table via `COPY` or `pg_restore` per workflow.

### 17.2. Check Duplicate Keys

~~~sql
SELECT r.customer_id
FROM recovery_stage.customers_restore AS r
JOIN app.customers AS c
  ON c.customer_id = r.customer_id;
~~~

Colliding keys may represent recreated rows or existing rows needing reconciliation. Never overwrite automatically.

### 17.3. Conditional INSERT

If business rules allow inserting only missing keys:

~~~sql
INSERT INTO app.customers (
    customer_id, email, created_at, status
)
SELECT
    r.customer_id, r.email, r.created_at, r.status
FROM recovery_stage.customers_restore AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM app.customers AS c
    WHERE c.customer_id = r.customer_id
);
~~~

This is only a template. Check foreign keys, unique constraints, defaults, generated columns, triggers, and dependent data before applying.

### 17.4. Upsert Is Not Always Right

`ON CONFLICT DO UPDATE` can overwrite valid changes made after the recovery target. Use only with explicit precedence and versioning rules.

### 17.5. Transaction Boundaries

Merge inside a transaction if volume and lock duration allow. For large datasets, batch with checkpoints and idempotency, recording exact progress so work can resume.

### 17.6. Foreign Keys

Restore parent rows before child rows. If a parent was recreated with a new key or child references changed, reconcile rather than forcing constraints.

## 18. Recovering Accidental DELETE While Preserving Valid Updates

A row may have been deleted and later recreated or updated in another system after the incident.

Example:
- Customer deleted at 02:17.
- Support recreated the customer record at 02:30.
- Current production holds a new row with the same business email yet a different ID.

Importing the old row verbatim can create duplicates or break foreign keys.

### 18.1. Compare by Business Key

Compare customer numbers, external IDs, or stable business keys rather than relying solely on surrogate IDs.

### 18.2. Compare Row Versions

If `updated_at`/version columns exist, use them to identify the newer record. Timestamps are not always trustworthy if clock skew or inconsistent app updates exist.

### 18.3. Audit Trails

If audit tables or event logs exist, use them to reconstruct valid post-target changes. Never overwrite newer history using an older snapshot blindly.

### 18.4. Domain-Specific Reconciliation

Orders, payments, inventory, and accounts each carry distinct semantics. An order paid after an incident cannot simply be restored by inserting an old row while ignoring ledgers/payment providers.

## 19. Recovering from DROP TABLE

When a table is dropped:

1. Determine when `DROP` committed.
2. Restore a cluster to before `DROP` in an isolated environment.
3. Capture table definition, indexes, constraints, triggers, ownership, and grants.
4. Export table schema/data.
5. Compare against the current production schema.
6. Create a staging or target table via controlled migration.
7. Load data and verify dependencies.

### 19.1. The Table May Have Been Recreated

If production created a new table with the same name after `DROP`, do not overwrite immediately. Compare OIDs/DDL, business meaning, and current data.

### 19.2. Sequences and Identity

If the table uses a sequence, set an appropriate next value after importing. Never set a sequence lower than already-used values.

Check/adjust example:

~~~sql
SELECT setval(
    'app.orders_order_id_seq',
    (SELECT COALESCE(MAX(order_id), 1) FROM app.orders),
    true
);
~~~

Use only after verifying sequence name, ownership, cache, and concurrency. Run during a maintenance window if needed to avoid racing with writers.

### 19.3. Dependencies

A table may be referenced by views, functions, triggers, foreign keys, publications, or application code. Restoring data while ignoring dependencies can break the application.

## 20. Recovering from TRUNCATE

`TRUNCATE` rapidly removes all rows in a table and can cascade to dependent tables.

### 20.1. Transactional Behavior

In PostgreSQL, `TRUNCATE` can run inside a transaction and roll back if uncommitted. After commit, PITR/backups or another data source is needed.

### 20.2. Identity Behavior

`TRUNCATE` accepts `RESTART IDENTITY` or `CONTINUE IDENTITY`. During recovery, verify sequence state against current rows.

### 20.3. CASCADE

`TRUNCATE ... CASCADE` can wipe dependent tables. List every affected table from query/logs and schema dependencies.

### 20.4. Restoring the Whole Table

If the current table holds zero new post-incident data, it can be replaced from a PITR table dump after checking schemas. If new data exists, merge and reconcile.

## 21. Recovering from DROP DATABASE

A committed `DROP DATABASE` cannot be reversed by a new `ROLLBACK`.

### 21.1. Cluster-Wide PITR

Stand up a PITR cluster prior to `DROP DATABASE`. The database will appear in its state as of the recovery target.

### 21.2. Exporting the Database

Use `pg_dump` against the database in the PITR cluster:

~~~bash
pg_dump \
  --host=pitr-db.example.internal \
  --port=55432 \
  --username=restore_reader \
  --dbname=appdb \
  --format=custom \
  --file=/recovery/export/appdb.dump
~~~

Restore into a new database:

~~~bash
createdb -h production-staging.example.internal -p 5432 -U restore_operator appdb_recovered

pg_restore \
  -h production-staging.example.internal \
  -p 5432 \
  -U restore_operator \
  -d appdb_recovered \
  /recovery/export/appdb.dump
~~~

### 21.3. Roles and Globals

`pg_dump` does not dump cluster-wide roles/tablespaces like `pg_dumpall --globals-only`. If the database needs roles, grants, or tablespace definitions, prepare them separately and review before applying.

### 21.4. Database Name Conflicts

Never create a database with the same name on production if another database already exists or applications are connecting. Use a staging/recovered name, then plan an explicit cutover.

## 22. Recovering Without a Complete WAL Archive

If required WAL is missing:
- You may only recover to the base backup state or the last available WAL point.
- You may use another logical dump/replica/snapshot if available.
- You may recover data from application event logs, CDC sinks, or external sources.
- You may have to accept losing some post-backup changes.

### 22.1. Check Alternate Sources

Inventory recent base backups, WAL archives on primary/standby/DR storage, physical and delayed standbys, logical replicas, CDC sinks/data lakes, storage snapshots, logical dumps, and application audit/event logs.

### 22.2. Never Fabricate Fake WAL

You cannot invent segments or rename files to plug WAL gaps. Missing chains can halt recovery or leave inconsistent states.

### 22.3. Identify Reconstructible Data

Certain caches, materialized tables, or externally sourced datasets can be rebuilt. Separate source-of-truth data from derived data to shrink restore scope.

### 22.4. Document the Actual Recovery Point

If only a 01:00 base backup exists with no subsequent WAL, never claim recovery to 02:00. Record the exact recoverable timestamp/LSN and affected data.

## 23. Distinguishing Database Process Failures from Storage Failures

### 23.1. PostgreSQL Process Crash

If the server process crashes while data files and WAL remain intact, PostgreSQL normally runs crash recovery on restart. Read logs, verify checkpoints, and confirm recovery completion.

### 23.2. OS Crash / Power Loss

May resemble a process crash, yet you must verify filesystems and storage flushed writes properly. Do not repeatedly restart if the volume shows signs of corruption.

### 23.3. Disk Full

A full disk causes writes, WAL, archiving, or temporary operations to fail. Identify which filesystem filled: `PGDATA`, `pg_wal`, tablespaces, temp, archive, or OS root.

### 23.4. Disk/Media Corruption

I/O errors, checksum failures, or filesystem errors indicate failing storage. Prioritize taking volume snapshots/clones and preserving logs; never run destructive repair tools before taking a copy.

### 23.5. Network Failure

A network partition can separate primary and standby. Never promote a standby casually when the primary could still be accepting writes on the other side.

## 24. Failing Over When the Primary Host Fails

If the primary host is lost while a standby is healthy and sufficiently current:

1. Confirm the primary truly cannot serve or has been fenced.
2. Check standby receive/replay LSNs.
3. Evaluate async replication gap and RPO.
4. Confirm no other primary is accepting writes.
5. Promote the standby per failover procedure.
6. Shift connection routing/DNS/proxies.
7. Verify application writes and data consistency.
8. Rebuild redundancy by provisioning a new standby.

### 24.1. Fencing

Fencing guarantees the old primary node cannot keep writing once a new node is promoted. If two primaries accept writes simultaneously, the system suffers split-brain.

### 24.2. Do Not Rely Only on Ping

An unpingable host may reflect a network path fault rather than a dead host. Check multiple signals and cluster manager mechanisms.

### 24.3. Asynchronous Replication Gap

If the standby has not received all WAL, failover can lose recent commits. Record LSNs and estimate data loss; synchronous replication reduces this risk yet does not replace backups.

## 25. Storage or Filesystem Failures

If `PGDATA` or `pg_wal` sits on failing storage:

1. Stop PostgreSQL if still running and showing severe I/O corruption.
2. Collect kernel/storage logs and PostgreSQL logs.
3. Take a volume snapshot/clone if safely possible.
4. Inspect filesystem and mount health.
5. Never run `fsck` or overwriting repairs on the sole copy without backing it up first.
6. Determine whether an independent standby, snapshot, or backup can be used.
7. Restore onto fresh storage.
8. Run integrity checks and restore validation.

### 25.1. pg_checksums

If data checksums are enabled, checksum errors help detect page corruption. Not all page/file errors are caught by checksums.

### 25.2. Page Corruption

In some cases a standby or backup can replace corrupted pages/files; never manually copy a relation file from another node without understanding physical consistency and WAL state.

### 25.3. WAL Corruption

WAL corruption can block crash recovery or PITR. Retrieve valid segments from archive/standby/backup chains. Never edit bytes manually.

## 26. Availability Zone or Region Failures

Cross-region DR requires advance preparation:
- Base backups or backup repositories replicated to another region.
- WAL archive replication to the DR region.
- Networking, DNS, certificates, firewalls, and secrets.
- Compute/storage capacity.
- PostgreSQL binaries/extensions.
- Application artifacts and configuration.
- Promote/restore and cutover runbooks.

### 26.1. Standby in Another Region

Can be promoted if the standby has received sufficient WAL and its failure domain remains intact. Evaluate replication lag before claiming RPO.

### 26.2. Backups in Another Region

If both primary and standbys are lost, restoring from backups/archives may be the only option. Downloading and replaying WAL can extend RTO.

### 26.3. Cross-Region Archiving

WAL archives must replicate continuously and be audited for completeness. Seeing green object storage replication status alone does not prove the PITR chain is recoverable.

### 26.4. DNS/Cutover

After restoring or promoting, check connection pools, DNS TTLs, read replicas, background jobs, schedulers, and writers. Prevent applications from writing to both old and new clusters.

## 27. Network Partitions and Split-Brain

When a primary loses contact with a standby, you must determine which node is authorized to accept writes.

### 27.1. Quorum and Leader Election

Cluster managers/consensus layers use quorum to elect leaders. Core PostgreSQL does not provide built-in distributed leader election for every topology.

### 27.2. Fence Before Promoting

Ensure the old primary is isolated or unable to write. Otherwise, both nodes can generate independent histories.

### 27.3. Rejoining the Old Node

After failover, the old primary must never simply reopen and accept writes. It must be rewound or rebuilt according to timeline and WAL divergence.

### 27.4. pg_rewind

`pg_rewind` can synchronize a diverged data directory after a timeline switch when prerequisites are met, typically requiring data checksums or `wal_log_hints` and sufficient WAL. It is not a tool to recover an accidental `DELETE`; it aligns an old node onto the new primary's timeline.

## 28. When to Use pg_rewind vs. PITR?

| Scenario | Appropriate Tool / Strategy |
| --- | --- |
| Old node diverged after failover, needs to rejoin new primary | `pg_rewind` if prerequisites met, otherwise fresh base backup |
| Accidental `DELETE` committed, need pre-operation rows | Separate PITR cluster then export/merge |
| Primary host died, standby sufficiently current | Fence and promote standby |
| Primary storage failed, independent standby healthy | Promote standby; then rebuild redundancy |
| Need database at a historical point in time | Base backup + WAL archive + PITR |
| Need only specific tables from a backup | Isolated restore then `pg_dump`/`COPY` |

`pg_rewind` does not create a snapshot prior to a deletion. If the old node already replayed `DELETE`, rewinding it onto the current primary preserves the `DELETE` history.

## 29. Recovering When Deletions Span Multiple Databases

Physical PITR recovers the cluster at the instance level, preserving all databases in the cluster as of the recovery target. When exporting a single database, verify whether the database exists on the target, along with roles/grants, tablespaces, extensions, publications/subscriptions, sequences/ownership, and out-of-database objects like scheduled jobs.

Do not confuse a database-level logical dump with a cluster-wide physical restore.

## 30. Sequences, Identity, and Generated Data After Merge

When merging rescued rows back into current production, sequence state may not match the PITR cluster's state.

### 30.1. Sequence Collisions

If production inserted new rows after the incident, current sequences may be ahead of PITR. Never `setval` sequences back down to lower values from an older backup.

### 30.2. Identity Columns

Inspect identity generation and sequence dependencies. `pg_dump`/`pg_restore` handles sequence states in some workflows, yet importing a row subset requires manual verification.

### 30.3. UUIDs

UUIDs do not suffer integer sequence collisions, yet business keys/unique constraints can still collide. Check unique indexes.

### 30.4. Generated Columns

Generated columns are computed from other columns; consider omitting them from direct imports if the target schema has differing expressions.

## 31. Triggers, Constraints, and Side Effects

When importing rows back into production:
- Triggers may fire events or insert audit entries.
- Foreign keys may reject rows if parents are absent.
- Unique constraints may flag duplicates.
- Exclusion constraints may block overlapping ranges.
- Application event/outbox logic may trigger side effects.

### 31.1. Inspect Triggers

Read trigger definitions and determine whether importing fires unintended business logic. Never disable triggers in production without understanding which invariants are bypassed.

### 31.2. Deferrable Constraints

Some constraints can be deferred until transaction end. This helps when importing dependency graphs, yet consistency must be verified before `COMMIT`.

### 31.3. Audit Trails

Record the origin of recovered rows and a recovery operation ID. Avoid making audit history look as if end users newly created those rows.

## 32. Recovering with an Existing Logical Dump

If a pre-incident `pg_dump` exists, you can restore into a temporary database and extract data without PITR, provided the dump contains the exact rows needed.

### 32.1. Advantages

- No need to replay an entire WAL chain.
- Can contain a single database or specific objects.
- Fits selective restores.

### 32.2. Limitations

- Reflects only the snapshot when dumped.
- Lacks rows created after the dump.
- May omit roles, tablespaces, or external dependencies.
- Restore may require compatible extensions/schemas.

### 32.3. Logical Backups Are Not PITR

`pg_dump` does not provide arbitrary timestamps between two dumps. To recover to `02:17:00`, base backup + WAL is normally required.

## 33. Post-Recovery Verification

After exporting/importing or promoting/restoring, verify across multiple layers.

### 33.1. Database State

~~~sql
SELECT
    current_database(),
    pg_is_in_recovery(),
    current_timestamp;
~~~

### 33.2. Row Counts and Keys

Compare expected row counts, primary key lists, min/max timestamps, and tenant/status breakdowns.

### 33.3. Constraints

Check foreign keys, unique constraints, and application-enforced invariants. If constraints were bypassed during import, validate and re-enable them per procedure.

### 33.4. Application Smoke Tests

Test read, create, and update flows in staging before opening traffic. Verify connection pools, permissions, extensions, and background workers.

### 33.5. Replication

After promoting or replacing production, rebuild standbys and verify streaming/slots/archiving. A new primary's HA is incomplete until redundancy is restored.

### 33.6. Post-Recovery Backups

After a PITR promotion/cutover, take a fresh base backup and verify WAL archiving on the new timeline. Do not continue retention as though the cluster stayed on the old timeline.

## 34. Cutover Plan After PITR

If deciding to replace production with a PITR cluster:

1. Stop or restrict writes on the old system.
2. Lock in the recovery target and verify data.
3. Confirm WAL replay finished.
4. Promote the instance if paused.
5. Configure permissions/credentials/networking.
6. Verify the application and dependencies.
7. Switch connection routing/DNS/proxies.
8. Monitor error rates, latency, and data consistency.
9. Keep the old cluster isolated for reference.
10. Rebuild replicas and take fresh backups.

### 34.1. Post-Target Writes Risk

Any commits after the recovery target are absent from the PITR cluster. Determine whether they can be replayed from audit/event logs or must be accepted as data loss.

### 34.2. Idempotent Replay

If replaying post-target events, pipelines need event IDs/idempotency keys to avoid duplicate side effects.

### 34.3. Cutover Gate

Switch traffic only once data owners approve the recovery point, the application passes tests, and dependent services are ready.

## 35. RTO and RPO

### 35.1. RPO

Recovery Point Objective is the time-equivalent amount of data an organization tolerates losing.

Examples:
- RPO = 0 within commits confirmed by synchronous standbys can be achieved under suitable semantics/config, yet it does not mean zero data loss across every failure mode.
- A 5-minute RPO with PITR depends on archive cadence, archive success, and actual recovery chain continuity.

### 35.2. RTO

Recovery Time Objective is the target duration to return the service to operation.

RTO covers detection and classification, choosing the recovery path, provisioning hosts/storage, downloading/restoring the base backup, replaying WAL, validating data, cutover, and smoke testing.

### 35.3. PITR Can Take Longer Than Failover

Failing over to a healthy standby is usually faster than restoring terabytes from object storage and replaying extensive WAL. However, failover fails to help if the standby already replayed the accidental deletion.

### 35.4. Measure Realistically

Time every step in drills. Never equate theoretical copy speed or backup creation time with RTO.

## 36. Designing Accidental-Deletion Prevention

### 36.1. Least Privilege

Applications should not hold `DROP DATABASE`, `DROP SCHEMA`, or `TRUNCATE` privileges unless required. Separate migration/admin roles from runtime application roles.

### 36.2. Guardrails in SQL Workflows

For risky operations:
- Use explicit transactions.
- Run a `SELECT` with the same `WHERE` clause before `DELETE`.
- Verify row counts.
- Use `RETURNING` to capture affected rows when workflow allows.
- Require approval for bulk destructive operations.

Example:

~~~sql
BEGIN;

DELETE FROM app.customers
WHERE tenant_id = 42
  AND status = 'test'
RETURNING customer_id, email;

-- Verify row count and contents before deciding
-- COMMIT or ROLLBACK
~~~

### 36.3. Soft Deletes

For business data needing rapid recovery, consider `deleted_at`/`deleted_by` instead of physical `DELETE`. Address uniqueness rules, query filters, retention, and restore permissions.

### 36.4. Auditing

Log actor, timestamp, request ID, table, keys, and operation into an audit system with separate access controls. Avoid logging excessive sensitive payloads.

### 36.5. Pre-Change Restore Points

Before risky deployments or maintenance, create a named restore point. Restore points do not replace backup/WAL retention, yet they simplify target selection.

## 37. Delayed Standbys as a Defense Layer

A standby with `recovery_min_apply_delay` defers applying WAL.

~~~conf
recovery_min_apply_delay = '15min'
~~~

### 37.1. Reaction Window

If an accidental deletion is caught within 15 minutes and operators pause the standby before it replays the delete transaction, an older state copy is preserved.

### 37.2. Does Not Protect Against Late Detection

Once the standby applies the operation after the delay window, the delayed standby no longer holds the pre-incident state.

### 37.3. Standby Impact

Delay increases replay lag, affecting read queries and failover freshness. Never use a delayed standby as a synchronous failover target if SLAs cannot tolerate the lag.

### 37.4. Pausing Replay Properly

You need monitoring and runbooks to pause recovery before the dangerous transaction applies. Cutting networking alone may not suffice if WAL already reached local storage and recovery continues.

### 37.5. Does Not Replace Backups

Delayed standbys help yet remain single nodes vulnerable to shared failure domains or WAL loss. Independent base backups and archives are still mandatory.

## 38. Notes on Managed PostgreSQL Services

With managed database services, users may lack direct access to `PGDATA`, WAL directories, or `recovery.signal`. Providers may offer point-in-time restore via control planes, snapshot restores, cross-region replicas/failover, backup retention settings, and log/audit exports.

### 38.1. PITR Usually Creates a New Instance

Many managed services provision a brand-new database instance at the target time rather than rolling back the live instance. This remains a safe strategy for exporting/comparing data.

### 38.2. Check Provider Limits

Verify retention windows, timezone semantics, restore granularity, extension support, parameter groups, networking, and how data is extracted from restored instances.

### 38.3. Do Not Assume Shell Access

`pg_verifybackup`, `pg_basebackup`, or `restore_command` may not be exposed directly to users. Use the provider's supported tools/workflows and request verification reports.

### 38.4. Managed Does Not Eliminate Restore Drills

Providers manage backup infrastructure, yet application owners must still verify data, permissions, integrations, and RTO.

## 39. Runbook: Incident Triage in the First 15 Minutes

### Minutes 0–3: Preserve State

- Stop the offending job/query.
- Do not restart or promote prematurely.
- Record detection timestamp and reporter.
- Identify current primary and standbys.

### Minutes 3–7: Classify

- Data deletion or infrastructure failure?
- Has the transaction committed?
- Single table/database or whole cluster?
- Is the primary still healthy?
- How far has the standby replayed?

### Minutes 7–12: Check Recovery Options

- Latest base backup.
- WAL archive completeness.
- PITR retention window.
- Delayed standby/snapshot/logical dump.
- Available restore capacity.

### Minutes 12–15: Choose Direction

- Uncommitted transaction: roll back the exact transaction.
- Committed logical deletion: separate PITR cluster and selective restore.
- Primary host failure: fence, assess standby, then fail over.
- Storage/region loss: DR restore or failover per recovery plan.

Timings are illustrative for an incident checklist; never let time pressure skip fencing, data-loss assessment, or evidence preservation.

## 40. Runbook: PITR to Rescue Deleted Rows

1. Stop the offending source.
2. Pinpoint commit timestamp/LSN/transaction.
3. Select base backup and WAL chain covering the target.
4. Provision an isolated restore environment.
5. Restore backup into a fresh data directory.
6. Configure `restore_command` and recovery target prior to deletion.
7. Start PostgreSQL and read recovery logs.
8. Pause/stop recovery per plan.
9. Verify rows and schema.
10. Export needed table/rows.
11. Import into staging on production.
12. Reconcile duplicates, updates, foreign keys, and sequences.
13. Merge with transaction and approval.
14. Verify application/business invariants.
15. Save recovery report and retain the PITR instance per policy.

## 41. Runbook: Primary Host Failure

1. Confirm the primary node can no longer accept writes.
2. Fence the old node or storage to prevent split-brain.
3. Check standby state and replay LSN.
4. Evaluate asynchronous replication gap.
5. Decide promotion per HA policy.
6. Shift traffic.
7. Verify application and writes.
8. Rebuild standby from the new primary/rewind if eligible.
9. Verify archiving and take a new backup.
10. Record actual RPO/RTO.

## 42. Runbook: Disk or Storage Corruption

1. Stop writes if continued writing risks further corruption.
2. Collect OS/kernel/storage/PostgreSQL logs.
3. Preserve a volume snapshot/clone if possible.
4. Check independent standbys and the backup repository.
5. Never delete WAL/data files manually.
6. Select a valid restore target/backup.
7. Build the cluster on fresh storage.
8. Verify checksums, WAL replay, and startup.
9. Run business/application validation.
10. Re-establish HA/backups and investigate storage root cause.

## 43. Runbook: Region DR

1. Confirm the primary region cannot recover within SLA.
2. Obtain formal DR activation decision.
3. Select cross-region standby or backup restore.
4. Check replication lag or WAL archive completeness.
5. Fence/disable writers in the old region if needed.
6. Promote/restore in the DR region.
7. Restore secrets, certificates, networking, DNS, and application services.
8. Run smoke tests and business validation.
9. Shift traffic incrementally.
10. Monitor latency, errors, lag, and capacity.
11. Record RPO/RTO and plan failback.

## 44. Post-DR Failback Plan

Failback returns workloads to the original failure domain after it is repaired. It is never just flipping DNS back.

1. Confirm which cluster is currently the source of truth.
2. Choose how to sync data back from DR.
3. Check timeline divergence and replication compatibility.
4. Use `pg_rewind` if eligible or take a fresh base backup.
5. Establish replication and verify lag.
6. Test failover/failback in staging.
7. Pick a maintenance window and drain writes cleanly.
8. Cut over traffic.
9. Retain the DR node in its new standby/backup role.
10. Update runbooks, DNS, monitoring, and backup policies.

## 45. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Promoting standby immediately on `DELETE` | Standby may have already replayed `DELETE` | Check replay LSN and recovery target |
| Thinking a new `ROLLBACK` undoes old commits | Fails to recover data | Use PITR or selective restore |
| Running PITR over live production | Loses valid post-target writes | Restore onto a separate cluster |
| Targeting by query start time | May still include deletion commit | Identify commit boundary |
| Not normalizing timezones | Picks wrong recovery target | Use UTC and check clock drift |
| Keeping base backups without WAL | Cannot reach desired target | Maintain continuous WAL archiving |
| Assuming delayed standbys always save you | Delay window may have elapsed | Monitoring, pause runbooks, and backups |
| Using `pg_rewind` to undo `DELETE` | Node follows current primary history | Use PITR |
| Importing table dump straight into production | Duplicates/overwrites and constraint failures | Staging + reconciliation |
| Blindly upserting from an old backup | Overwrites newer valid updates | Define precedence via business rules |
| Forgetting sequence state | ID collisions or backward sequences | Inspect and synchronize sequences |
| Ignoring triggers | Unintended side effects | Review triggers/audit/outbox |
| Ignoring `CASCADE` | Misses dependent tables | Map all affected objects |
| Treating a standby as a backup | Logical deletions replicate | Independent backups/PITR |
| Promoting on network loss alone | Split-brain | Fencing and quorum |
| Testing only database startup | App may still fail | Smoke tests and business invariants |
| Skipping backup after PITR promotion | Missing recovery chain on new timeline | Take fresh base backup and archive |
| Skipping DR drills | Actual RTO exceeds SLA | Restore/failover drills |

## 46. PostgreSQL Hands-On Exercises

Execute in a lab/staging environment with test backups and WAL archives. Never simulate destructive commands on production.

1. **Transaction:** open a transaction, `DELETE` a row, then `ROLLBACK`.
2. **Commit:** `DELETE` and `COMMIT`; explain why a new transaction cannot undo it.
3. **Savepoint:** use `ROLLBACK TO SAVEPOINT` before committing.
4. **Autocommit:** inspect client behavior when running a standalone `DELETE`.
5. **Query evidence:** enable appropriate logging in the lab and locate the query text.
6. **Application logs:** correlate a request ID with a database operation.
7. **Timezones:** convert log timestamps to UTC.
8. **Commit time:** distinguish query start from transaction commit.
9. **Scope:** run a conditional `DELETE` and identify affected keys.
10. **TRUNCATE:** simulate `TRUNCATE` inside a transaction and roll back.
11. **DROP TABLE:** simulate dropping a table and record its dependency list.
12. **DROP DATABASE:** create a lab database, drop it, and identify recovery assets.
13. **CASCADE:** observe objects affected by `DROP ... CASCADE`.
14. **Physical standby:** build a standby and observe `DELETE` being replayed.
15. **Delayed standby:** configure `recovery_min_apply_delay` in the lab.
16. **Pause replay:** practice pausing replay prior to a test transaction.
17. **Failover:** distinguish promoting a standby from PITR.
18. **Base backup:** take a base backup with `pg_basebackup`.
19. **WAL archive:** configure archiving in the lab.
20. **WAL continuity:** identify segments required for a backup.
21. **Restore point:** create a named restore point prior to an operation.
22. **PITR time:** recover to `recovery_target_time`.
23. **PITR LSN:** locate an LSN in the lab and use `recovery_target_lsn`.
24. **PITR XID:** explore `recovery_target_xid` for your version.
25. **Inclusive:** compare `recovery_target_inclusive` true vs. false.
26. **Target action:** test `pause`, `promote`, and `shutdown` on disposable clusters.
27. **Recovery signal:** create `recovery.signal` and observe archive recovery.
28. **Standby signal:** distinguish `standby.signal` from `recovery.signal`.
29. **Restore command:** write a command fetching WAL segments from a lab archive.
30. **Missing WAL:** create an archive gap and read the recovery error.
31. **Timeline:** observe timeline history after promotion.
32. **PITR isolation:** restore a backup onto a cluster with a separate port/network.
33. **No overwrite:** verify PITR does not touch production `PGDATA`.
34. **Selective export:** use `pg_dump --table` to export one table.
35. **COPY:** export a subset of rows with `psql \copy`.
36. **Staging import:** import rows into a `recovery_stage` schema.
37. **Duplicate keys:** detect colliding keys between staging and production.
38. **Merge:** write `INSERT ... WHERE NOT EXISTS` for a lab row subset.
39. **Upsert:** simulate conflicts and explain overwrite risks.
40. **Foreign keys:** restore parents before children.
41. **Sequence:** test `setval` after selective restore.
42. **Identity:** check identity sequences after subset import.
43. **Triggers:** check side effects when inserting rescued rows.
44. **Audit:** record a recovery operation ID for imported rows.
45. **DROP recovery:** recover a dropped table in a separate cluster.
46. **TRUNCATE recovery:** recover pre-truncate rows and merge.
47. **Database recovery:** export a database from a PITR cluster.
48. **Globals:** identify roles/tablespaces requiring separate recovery.
49. **Logical dump:** restore `pg_dump` into a lab database and check schema/data.
50. **No WAL:** simulate having only a base backup and assess the recovery point.
51. **Alternative sources:** inventory snapshots, CDC sinks, audit logs, and delayed standbys.
52. **Process crash:** inspect crash recovery logs after an abnormal lab shutdown.
53. **Disk full:** simulate a filesystem quota in the lab and distinguish which filesystem filled.
54. **Storage error:** inspect kernel/PostgreSQL logs when simulated storage reports errors.
55. **Fencing:** diagram a fencing workflow prior to promotion.
56. **Split-brain:** diagram a network partition and propose a quorum decision.
57. **pg_rewind:** practice rewinding a diverged standby in the lab.
58. **pg_rewind prerequisites:** verify data checksums/`wal_log_hints` and WAL availability.
59. **Region DR:** diagram primary, standby, and backup archive across regions.
60. **Cross-region restore:** restore a backup from the DR region copy.
61. **DNS cutover:** outline steps to switch endpoints and connection pools.
62. **Failback:** outline syncing an old node back to a new DR primary.
63. **Managed service:** study the PITR workflow of a managed PostgreSQL provider.
64. **Recovery target:** choose a pre-deletion target from logs with clock drift.
65. **Business reconciliation:** restore customer rows while keeping valid post-incident updates.
66. **Order recovery:** analyze side effects on orders/payments during selective restore.
67. **Inventory:** restore stock rows and reconcile against ledger/event logs.
68. **RTO:** measure provisioning, download, replay, validation, and cutover durations.
69. **RPO:** determine the latest recoverable WAL point.
70. **Incident timeline:** write a timeline from detection to recovery complete.
71. **Runbook DELETE:** write a PITR and selective merge runbook.
72. **Runbook DROP:** write a runbook for recovering dropped tables/databases.
73. **Runbook host failure:** write a fencing, promotion, and standby rebuild runbook.
74. **Runbook storage:** write a volume preservation and fresh-storage restore runbook.
75. **Runbook region:** write a DR activation and failback checklist.
76. **Privileges:** create an application role without `DROP`/`TRUNCATE` privileges.
77. **Soft delete:** design `deleted_at`/`deleted_by` and a restore workflow.
78. **Restore drills:** schedule PITR drills across multiple target times.
79. **Backup protection:** design base backups, WAL archiving, immutable copies, and key recovery.
80. **Capstone design:** build a combined strategy for accidental `DELETE` and infrastructure outage covering classification, evidence, PITR isolation, selective merge, failover/fencing, RTO/RPO, monitoring, and periodic drills.

## 47. Recovery Path Decision Checklist

### Classification

- [ ] Determine logical deletion vs. infrastructure failure.
- [ ] Determine whether the transaction committed.
- [ ] Identify affected database/table/rows and dependencies.
- [ ] Identify current primary/standbys and replay positions.
- [ ] Stop the offending source and preserve logs.

### Selecting Recovery

- [ ] Uncommitted: roll back the exact transaction.
- [ ] Committed deletion: determine the PITR target.
- [ ] Standby exists: check whether it already replayed the operation.
- [ ] Base backup and continuous WAL archive available.
- [ ] Delayed standby/snapshot/logical dump available if needed.
- [ ] Infrastructure failure: verify fencing and RPO before promoting.

### Execution

- [ ] Restore/PITR onto a separate cluster.
- [ ] Use a target prior to the data-losing commit.
- [ ] Check rows/schemas/tablespaces.
- [ ] Export to staging.
- [ ] Reconcile duplicate keys and newer updates.
- [ ] Check foreign keys, sequences, triggers, and side effects.
- [ ] Obtain approval before merging/cutting over.

### Post-Recovery

- [ ] Application smoke tests passing.
- [ ] Business invariants verified.
- [ ] Replicas and WAL archiving re-established.
- [ ] Fresh base backup taken if timeline changed.
- [ ] RTO/RPO and any data loss recorded.
- [ ] Root cause and guardrails updated.

## 48. Summary

Recovering from accidental deletions and recovering from infrastructure failures solve two different problems:

~~~text
COMMITTED ACCIDENTAL DELETION
  -> Pinpoint commit time
  -> Base backup + WAL
  -> PITR onto separate cluster
  -> Export rows/table/database
  -> Reconcile and merge

PRIMARY / INFRASTRUCTURE FAILURE
  -> Confirm failure domain
  -> Fence if split-brain risk exists
  -> Promote standby or restore backup
  -> Cut over application
  -> Rebuild redundancy
~~~

Key principles:

- **Uncommitted transactions can roll back; committed transactions cannot be undone with a new `ROLLBACK`.**
- **Physical standbys normally replay valid deletions too.** Check replay state before promoting.
- **PITR recovers cluster state to a historical point.** To keep valid post-incident writes, restore onto a separate cluster, then extract and merge data.
- **Pick recovery targets by commit boundary**, normalize timezones, and understand inclusive semantics.
- **Base backups require continuous WAL and matching timeline history.** Missing WAL can prevent recovery from reaching the target.
- **`DELETE`, `TRUNCATE`, `DROP TABLE`, and `DROP DATABASE` have different scopes.** Identify dependencies, constraints, sequences, and side effects.
- **`pg_rewind` rejoins a diverged node to a new timeline; it does not undo deletions.**
- **Failover requires fencing and RPO assessment.** A network partition does not prove the primary is dead.
- **Verified backups still require restore drills and business validation.** Measure RTO/RPO through real procedures.
- **Least privilege, soft deletes, auditing, named restore points, and drills** reduce recurrence risk.

A solid recovery plan never starts with the restart or promote button. It starts with accurate classification, preserving recovery options, and choosing the recovery path suited to the data you must keep. By separating PITR from failover, you can rescue deleted data while preserving valid production changes, and handle infrastructure outages according to availability and disaster recovery objectives.
