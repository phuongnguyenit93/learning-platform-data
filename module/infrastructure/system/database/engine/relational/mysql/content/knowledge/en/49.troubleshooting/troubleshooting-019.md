# Distinguishing Data Corruption from Application Bugs and Limits of `innodb_force_recovery`

When an application reports "lost data", "wrong record read", or "database error", you cannot automatically conclude InnoDB is corrupted. The cause may lie in a query, transaction, cache, replica lag, ORM mapping, time zone, access privileges, or valid SQL writing wrong values. Physical corruption of a tablespace, page, or index is a different failure class requiring dedicated data-preservation workflows. Misdiagnosing the issue can lead operators to enable `innodb_force_recovery` unnecessarily, overwrite salvageable data, or ruin backup recovery options.

This lesson belongs to the **Troubleshooting** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backup, and operations—the ability to distinguish application bugs from data corruption guides you to the right remediation path. The focus is on preserving evidence, verifying scope, protecting copies, recovering from backups, and understanding the limits of each `innodb_force_recovery` level.

## 1. Distinguishing Three Incident Categories

Do not lump every data issue under "corruption". In practice, separate at least three categories:

| Category | Nature | Examples |
|---|---|---|
| Application or query bug | Database works properly, but app reads/writes wrongly or misinterprets data | Wrong `JOIN`, missing tenant filter, stale cache, wrong entity mapping, transaction rollback |
| Logical data corruption | Physical structures may be intact, yet business values were overwritten or deleted | Mistaken `UPDATE`, bad import, business duplicate, accidental delete, buggy migration |
| Physical/InnoDB structural corruption | Pages, indexes, tablespaces, or storage metadata are damaged or inconsistent | Checksum mismatch, page corruption, missing tablespace, storage read/write faults |

All three categories can overlap. For instance, an app bug writes bad values, and replication faithfully propagates that change. Source and replica stay replication-consistent while business data is wrong. Conversely, a disk page on one replica may suffer physical corruption while the source remains healthy.

**Never use `innodb_force_recovery` to fix query bugs, wrongly written business data, or replica lag.** This setting exists solely for emergencies when InnoDB cannot start or read data normally and you must salvage data.

## 2. Signs Pointing to an Application Bug

These symptoms usually warrant inspecting code, SQL, transactions, or read routing before suspecting physical corruption:

- An endpoint returns wrong results while direct SQL on the primary returns accurate results.
- Only one tenant, user, or request type fails.
- Data is accurate on the primary yet stale on a replica or cache.
- Displayed timestamps shift by hours due to time zones or `TIMESTAMP`/`DATETIME` conversions.
- ORM reads wrong columns due to mapping, projection, or lazy loading issues.
- A `JOIN` query multiplies rows or drops rows due to bad filter conditions.
- Data vanishes after a failing request because the transaction rolled back.
- Errors appear only in a specific application version after a deploy or migration.
- Certain requests hit privilege, SQL mode, or type conversion errors while other queries succeed.

Run an independent read query with explicit primary key and schema on the exact instance the application hits. Compare raw SQL output against application logs, request parameters, transaction boundaries, and cached entries. If SQL returns valid data while the API returns bad data, look at the application or middleware tiers.

### Verify Whether the Application Reads the Expected Instance

~~~sql
SELECT
  @@hostname AS hostname,
  @@port AS port,
  @@server_uuid AS server_uuid,
  DATABASE() AS current_database,
  CONNECTION_ID() AS connection_id,
  VERSION() AS mysql_version;
~~~

Capture this on the same connection path the request uses if possible. The application may be connecting to the wrong database, hitting a replica, routing via a different Router endpoint, or running in the wrong environment. A query from a DBA workstation against the primary does not prove the failing request also read from the primary.

Inspect connection pools, routing datasources, read/write splitting, transaction propagation, and replica setup. For freshly written data, immediately reading from an asynchronous replica can exhibit read-after-write inconsistency without any data corruption.

## 3. Signs Pointing to Logical Data Corruption

Logically wrong data usually remains readable with intact pages and indexes. Examples:

- Order totals do not match the sum of order line items.
- A customer sits in an invalid business state.
- Multiple records share an external key despite business uniqueness rules.
- Records reference nonexistent entities because an import disabled foreign key checks.
- A batch job updated the wrong date range or wrong tenant.
- Data was deleted or overwritten by an authorized account.
- A type-changing migration rounded or truncated values.

These errors typically require logical recovery from audit logs, backups, binary logs/PITR, or upstream data sources. `innodb_force_recovery` has no awareness of business correctness and cannot undo a syntactically valid `UPDATE`.

### Checking Business Consistency

Example finding orders referencing missing customers:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL
LIMIT 100;
~~~

Reconciling order headers with line items:

~~~sql
SELECT
  o.id,
  o.total_amount,
  SUM(oi.quantity * oi.unit_price) AS calculated_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.id
GROUP BY o.id, o.total_amount
HAVING o.total_amount <> SUM(oi.quantity * oi.unit_price)
LIMIT 100;
~~~

Adjust queries for real rounding, tax, shipping, discount, and status rules. Mismatches prove business-rule violations requiring investigation—not automatically page corruption.

## 4. Signs Pointing to Physical InnoDB Corruption

Suspect physical corruption when storage engine or filesystem evidence appears, such as:

- Error log records InnoDB page corruption, checksum mismatches, or unreadable pages.
- InnoDB throws errors accessing a specific page/table and repeats on the exact same page/space ID.
- Server crashes or hits assertion failures reading a specific table/index.
- Tablespace is missing, fails to open, or metadata mismatches the file.
- Storage volume, disk controller, filesystem, or I/O errors coincide with MySQL errors.
- A table or key range cannot be read despite verified SQL and privileges.
- InnoDB crash recovery repeatedly fails during startup.

Error messages often include page numbers, space IDs, indexes, or tablespaces. Preserve those exact details to cross-check logs and files. Never conclude from a generic message like "Got error from storage engine"; capture the full error log and InnoDB status.

### Gathering Evidence from MySQL

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Save full output, especially `TRANSACTIONS`, `FILE I/O`, `LOG`, `BUFFER POOL`, and `LATEST DETECTED DEADLOCK` if present. This is a point-in-time snapshot; it does not replace error logs or crash history.

Capture error log path and related settings:

~~~sql
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'innodb_page_size';
SHOW VARIABLES LIKE 'innodb_checksum_algorithm';
SHOW VARIABLES LIKE 'datadir';
~~~

Variable names/readability and paths depend on version, privileges, and deployment platform. Managed MySQL services may expose error logs via a console or log aggregator rather than direct filesystem access.

Cross-check error logs with OS logs: I/O errors, device resets, read-only filesystem remounts, disk full, volume faults, kernel panics, or storage maintenance events. A page error can originate at the storage layer, so SQL checks alone are insufficient.

## 5. Preserving Evidence Before Repairing

When physical corruption is suspected, prioritize preserving an investigable and recoverable state.

- Record timestamps, MySQL version, host, `server_uuid`, `datadir`, and topology.
- Save error logs, `SHOW ENGINE INNODB STATUS`, processlist, and failing queries.
- Record exact schema/table/index, page number, space ID, and first occurrence.
- Inventory available backups, binary logs, replicas, and storage snapshots.
- Stop or restrict write workloads if further writes could worsen damage; coordinate with app owners on read-only mode or halting writes.
- If a physical copy is needed, take a consistent storage snapshot or use a proper backup tool. Never copy a live `datadir` with ordinary file copy commands and treat it as a valid backup.
- Keep the original intact and work only on copies when testing salvage steps.

**Never delete or manually replace** `ibdata1`, redo logs, undo tablespaces, `.ibd` files, system tablespace files, or InnoDB metadata. Never run `REPAIR TABLE` on InnoDB tables; that command is not an InnoDB corruption repair mechanism. Never run MyISAM utilities like `myisamchk` against InnoDB files.

Avoid repeated restarts if each boot worsens damage or no copy exists for testing. Before restarting, understand configs, logs, and the recovery plan.

## 6. Verifying Backups and Replicas Before Relying on Them

Backups are the preferred recovery path for corruption. Check:

- Backup timestamp and covered databases/tables.
- Whether the backup completed cleanly with valid checksums/manifests.
- Whether uninterrupted binary logs exist from the backup checkpoint to the recovery point.
- Whether that backup has ever been restore-tested.
- Whether MySQL version, encryption/keyring configs, and required plugins match.
- Whether you can restore onto a clean instance without overwriting the evidence instance.

A replica is not automatically a backup. If the failure was a mistaken `DELETE`/`UPDATE` or bad logical write, replication likely propagated it to replicas. If corruption is physical to a single node, another replica may still be healthy—yet you must verify its logs, readability, and business consistency before promoting or dumping.

In Group Replication / InnoDB Cluster topologies, an `ONLINE` member is not absolute proof all data is valid. Verify member status, error logs, replication apply state, checksum/logical comparisons, and independent backups.

When a clean backup exists, prefer restoring onto a clean instance and applying binary logs up to right before the incident via PITR. Switch traffic only after validating data and applications.

## 7. Inspecting Tables Cautiously

If the server runs steadily with no signs of severe corruption, inspect metadata, schema, and logical integrity first:

~~~sql
SHOW CREATE TABLE customers;
SHOW INDEX FROM customers;

SELECT COUNT(*) FROM customers;
SELECT MIN(id), MAX(id) FROM customers;
~~~

For InnoDB, `CHECK TABLE` can detect certain defects, yet it is not a repair tool and does not guarantee finding every form of corruption. On a badly damaged table, checking can add heavy load or crash the server when reading bad pages. Run it only after assessing impact, securing backups/copies, and scoping appropriately.

~~~sql
CHECK TABLE customers;
~~~

If the server is crashing, hitting I/O errors, or repeating page corruption, do not run mass `CHECK TABLE` in production as a first step. Prioritize logs, snapshots, and testing on copies.

### `innochecksum`

`innochecksum` checks page checksums in InnoDB tablespace files. It runs offline on files; never run checks or checksum rewrites against tablespaces actively opened by MySQL. Stop the server or operate on a consistent offline copy per procedure before running checks.

Example checking a copy file:

~~~bash
innochecksum --strict-check /recovery-copy/appdb/orders.ibd
~~~

The path is an example; flags vary by MySQL version. `innochecksum` checks file-level page checksums—it does not verify business rules, prove all indexes and logical relationships are valid, or replace restore tests. Never use rewrite-checksum flags to "fix" a page whose root cause is unknown.

## 8. What Is `innodb_force_recovery` Used For?

`innodb_force_recovery` is an InnoDB startup parameter allowing the server to boot under certain forms of damage so operators can read and export data. It is **not a repair tool**, does not rebuild damaged pages, and does not make the booted database safe for ongoing production use.

The default is `0` (normal recovery). Levels 1 through 6 progressively skip or disable normal InnoDB safeguards. Higher levels bypass more recovery steps and carry greater risk of inconsistent data.

Consider this parameter only when:

- MySQL cannot start normally due to confirmed InnoDB errors.
- Needed data cannot be obtained from a healthy backup or replica.
- The goal is booting temporarily to dump/export readable data.
- You have a plan to provision a clean instance and import salvaged data.

Never enable this setting merely because a query returns wrong results, a table has orphan rows, or an application hits timeouts.

## 9. The Six Levels of `innodb_force_recovery`

| Level | Common Source Name | Primary Effect | Risks / Limits |
|---:|---|---|---|
| 0 | Normal | InnoDB performs normal recovery | Standard operational mode |
| 1 | `IGNORE_CORRUPT` | Attempts to skip certain corrupt pages/index records so readable data remains accessible | Dumps may miss rows or skip damaged regions |
| 2 | `NO_BACKGROUND` | Prevents master thread and purge thread from running | Skips normal background maintenance; salvage use only |
| 3 | `NO_TRX_UNDO` | Skips post-crash transaction rollbacks | May expose uncommitted changes in visible data |
| 4 | `NO_IBUF_MERGE` | Prevents insert/change buffer merges and skips normal table statistics computation | Risks permanent data corruption; forces InnoDB read-only |
| 5 | `NO_UNDO_LOG_SCAN` | Skips scanning undo logs at startup; incomplete transactions appear committed | Data may be inconsistent; InnoDB read-only |
| 6 | `NO_LOG_REDO` | Skips redo log roll-forward | Pages may be stale or structurally incomplete; very high corruption risk; InnoDB read-only |

Levels 4, 5, and 6 put InnoDB in read-only mode. At lower levels, certain writes might still be permitted depending on version behavior, yet **you must never use that to continue running or editing data on the salvage instance**. The sole goal is extracting as much readable data as possible and rebuilding on a clean instance.

### How to Escalate Levels

Start at the lowest viable level—typically `1` when normal recovery fails to boot. Only if the server still fails to boot or cannot read needed data should you increment one level at a time, reviewing logs after each attempt.

Never jump straight to `6`. Higher levels skip undo or redo steps needed for consistency. Once using level 3 or above—especially 5/6—readable data no longer necessarily reflects a valid pre-crash transactional state.

`innodb_force_recovery` is a startup configuration variable; how you set it and restart depends on your MySQL deployment method. Operate on a copied `datadir` or isolated recovery environment whenever possible. Consult version-specific docs because limits and behaviors vary across branches.

## 10. Data Salvage Procedure with `innodb_force_recovery`

### Step 1 — Prioritize Clean Backups and Replicas

Verify backups, replicas, and snapshots first. If a valid backup exists, restore onto a clean instance and apply PITR if needed. Use force recovery only when normal recovery paths cannot supply needed data.

### Step 2 — Preserve the Original `datadir`

Stop MySQL cleanly per procedure if taking a physical copy. Use a consistent storage snapshot or proper backup tool; keep the original intact along with required metadata such as config files, keyrings, redo/undo, system tablespace, and `.ibd` files. Never copy a few isolated InnoDB files and try booting an inconsistent file mix.

### Step 3 — Boot the Copy at the Lowest Needed Level

Set `innodb_force_recovery=1` in the recovery config or startup flags. Watch the error log. Once the server boots, never connect production apps or permit write workloads on this instance.

If it fails to boot, read the log to see where recovery failed. Increment to 2, then 3, 4, 5, or 6 only when the previous level fails with a clear reason. Log every level tried, startup errors, and read outcomes.

### Step 4 — Dump Readable Tables

Prefer dumping database-by-database or table-by-table as needed. Example:

~~~bash
mysqldump --host=recovery-db --user=salvage_user \
  --quick --skip-lock-tables appdb customers > customers.sql
~~~

This command is illustrative; adjust privileges, socket/TLS, database/table names, and options for your environment. Use an account with minimal read privileges. Never pass passwords on the command line or shell history; use secure credential mechanisms.

If a full-table dump hits an error, try chunking reads by primary key ranges to isolate readable regions. Remember a single bad page can fail any query touching that page. Never silently skip failing rows without documenting missing ranges and business impact.

Do not use `--force` to hide errors. That flag can keep dumping after SQL errors, yielding an output file silently missing objects or rows. If used to rescue readable sections, log every error completely and inventory everything that failed to dump.

### Step 5 — Build a Clean Instance

Initialize a fresh `datadir` with a compatible MySQL version, standard config, and required keyring/encryption material. Never reuse the force-recovery `datadir` as a production instance. Create schemas using verified migrations or logical backups, then import the dumped data.

Verify charsets/collations, SQL modes, time zones, engines, indexes, constraints, users/roles, stored programs, and privileges. Never assume a logical dump contains every server setting or operational metadata required.

### Step 6 — Validate Before Switching Traffic

Reconcile row counts, min/max keys, aggregates, foreign key relationships, and business rules. Run application tests, verify critical query plans, check error logs, and confirm replication/backups on the clean instance. If some pages or rows could not be salvaged, document the exact missing ranges and obtain business sign-off before opening traffic.

## 11. Why Must You Never Keep Running Production Under Force Recovery?

Force recovery alters how InnoDB recovers transactions and pages. Skipping undo, purge, change buffer merges, or redo means visible state may no longer reflect a fully recovered database.

Risks include:

- Uncommitted data can appear committed under certain recovery levels.
- Unapplied redo can leave stale pages or incomplete internal structures.
- Writes are blocked at higher levels; at lower levels, writes can deepen corruption.
- Skipped indexes or pages can cause queries to silently omit rows.
- One successful dump does not prove every table and every row was salvaged.
- New mutations on a salvage instance have no trustworthy recovery path.

Treat a force-recovery instance strictly as a temporary read-only source for data extraction. Never return it to write traffic, run migrations on it, or promote it as a new primary.

## 12. Actions to Avoid

| Action | Why It Is Dangerous | Proper Path |
|---|---|---|
| Jumping straight to `innodb_force_recovery=6` | Skips redo, leaving stale pages and high risk | Start low and increment one step at a time on a copy |
| Writing data to a force-recovery instance | Can create inconsistent or unsupported state | Read/dump only; build a clean instance for writes |
| Deleting `ibdata1` or redo/undo files | Can destroy InnoDB structure and lose data | Keep `datadir` intact; restore from backup/snapshot |
| Running `REPAIR TABLE` on InnoDB | Not an InnoDB repair mechanism | Restore or salvage and rebuild |
| Running `myisamchk` on `.ibd` files | Wrong tool for the storage engine | Use InnoDB tools offline on copies only |
| Running mass `CHECK TABLE` on a failing server | Adds load and can trigger page-read crashes | Preserve logs/snapshots and test on a copy |
| Promoting an unverified replica | May promote logically or physically broken data | Verify logs, checksums, and business data first |
| Treating a partial dump as a complete backup | May silently miss tables/rows | Log all errors and reconcile dump completeness |

## 13. Verifying Data After Salvage

After importing into a clean instance, verify both structure and content.

### Check Row Counts and Key Ranges

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM orders;
~~~

Compare against backups, external sources, or pre-incident snapshots. Matching counts do not guarantee identical rows; where business keys exist, verify keys or batch checksums.

### Check Constraints

~~~sql
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

Check for orphan foreign keys, unique duplicates, and required columns. If constraints were deferred during salvage/import, validate data before re-enabling them.

### Check Business Aggregates

~~~sql
SELECT
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM orders
GROUP BY status
ORDER BY status;
~~~

Compare against pre-incident reports, backups, or authoritative business records. For monetary values, use `DECIMAL` and match the application's rounding rules. For timestamps, align time zones and snapshot windows.

### Check Application Behavior

Run smoke tests on the clean instance using production-like accounts and privileges. Verify reads/writes, transaction rollbacks, generated keys, stored procedures, triggers, events, and critical queries. Open traffic only after business owners confirm data meets acceptance criteria.

## 14. When Data Is Wrong While InnoDB Is Healthy

If the server runs stably, the error log shows no page corruption, and queries read cleanly, focus on data logic:

1. Pinpoint when records became wrong using audit logs, binlogs, or app history.
2. Locate the transaction or batch that wrote the bad data.
3. Compare a pre-incident backup against current state.
4. Use PITR to restore a copy right before the bad operation.
5. Extract the affected rows to restore from that copy.
6. Apply compensating updates in production inside verified transactions rather than overwriting whole tables if only a subset of rows is wrong.
7. Reconcile row counts and business totals afterward.

Never enable `innodb_force_recovery` for an accidental `DELETE` or bad migration while InnoDB itself is healthy. Force recovery understands nothing about business history and can disable writes without restoring prior values.

## 15. Decision Runbook Flowchart

~~~text
App reports wrong data or MySQL error
                 |
                 v
     Save error, timestamp, host,
     query, and blast radius
                 |
                 v
   Does direct SQL on the right
   instance reproduce the error?
          /             \
        No               Yes
         |                |
         v                v
  Check app, cache,    Does error log show
  routing, replica,    InnoDB page/tablespace
  transaction, ORM     or I/O corruption?
                          /       \
                        No         Yes
                         |          |
                         v          v
                 Check logic,     Preserve snapshot,
                 schema, DML,     backup, error log
                 constraint, PITR     |
                                      v
                            Does MySQL boot normally?
                                /             \
                              Yes              No
                               |                |
                               v                v
                       Restore/repair logic  Try clean backup/
                       from backup/PITR on   replica first
                       clean instance           |
                                                v
                                     No better option left?
                                                |
                                                v
                                 Force recovery on a copy,
                                 start low, dump only
                                                |
                                                v
                                     Rebuild clean instance,
                                     validate, then cut over
~~~

This diagram shows general decision flow. In practice, coordinate with DBAs, storage/platform teams, and app owners; never bypass incident processes or approval gates for destructive actions.

## 16. Incident Checklist

**Initial Classification**

- [ ] Recorded MySQL version, host, `server_uuid`, schema/table, and timestamp.
- [ ] Confirmed requests read from the intended instance and database.
- [ ] Reproduced via an independent read-only SQL query.
- [ ] Compared primary, replica, cache, and source data.
- [ ] Distinguished application bug, logical data error, and physical InnoDB fault.

**Preserving Evidence**

- [ ] Saved error log, `SHOW ENGINE INNODB STATUS`, and full SQL errors.
- [ ] Recorded page/space ID, tablespace, index, and involved files if present.
- [ ] Checked disk, filesystem, storage volume, and OS logs.
- [ ] Verified backups, binary logs, PITR, and replicas.
- [ ] Kept originals untouched and created a consistent snapshot/copy before testing.

**If `innodb_force_recovery` Is Required**

- [ ] Used only because normal recovery cannot boot or read needed data.
- [ ] Tested on a copy or isolated recovery environment.
- [ ] Started at the lowest level and incremented step by step.
- [ ] Kept the instance off production traffic and write workloads.
- [ ] Dumped table-by-table/range-by-range, logging all errors and missing data lists.
- [ ] Built a clean `datadir`/instance for importing salvaged data.

**Before Opening Traffic**

- [ ] Reconciled row counts, key ranges, aggregates, and batch checksums.
- [ ] Checked unique keys, foreign keys, `NOT NULL`, and business data rules.
- [ ] Verified schemas, indexes, routines, triggers, events, and privileges.
- [ ] Ran smoke tests and critical queries.
- [ ] Verified fresh backups and restore capability.
- [ ] Documented unrecoverable data ranges and business sign-off.

## 17. Key Takeaways

- Wrong query output does not equal InnoDB corruption; check applications, SQL, cache, replicas, and transactions first.
- Logically wrong writes require audits, backups, or PITR; force recovery cannot repair business rules.
- Page corruption, checksum mismatches, tablespace errors, and I/O failures signal physical investigation.
- Preserve error logs, InnoDB status, `datadir` snapshots, and backups before trying recovery steps.
- A replica is not automatically a backup; bad logical changes replicate just like valid ones.
- `innodb_force_recovery` is an emergency boot/salvage mode, not a repair tool.
- Escalate levels step by step from lowest to highest; levels 4–6 force InnoDB read-only.
- Levels 3+ can leave transaction state inconsistent; levels 5/6 bypass critical recovery phases.
- Never write data, run migrations, or send production traffic to a force-recovery instance.
- Build a clean instance, import salvaged data, validate business integrity, and take a backup before cutover.

By clearly separating application bugs, logical data errors, and physical corruption, operations teams choose the right tool every time. Reserve `innodb_force_recovery` strictly as a last resort to read and salvage data when InnoDB cannot operate normally; service restoration must finish on a verified clean instance.

## References

- [MySQL 8.0 Reference Manual: Forcing InnoDB Recovery](https://dev.mysql.com/doc/refman/8.0/en/forcing-innodb-recovery.html)
- [MySQL 8.0 Reference Manual: InnoDB Recovery](https://dev.mysql.com/doc/refman/8.0/en/innodb-recovery.html)
- [MySQL 8.0 Reference Manual: innochecksum — Offline InnoDB File Checksum Utility](https://dev.mysql.com/doc/refman/8.0/en/innochecksum.html)
- [MySQL 8.0 Reference Manual: CHECK TABLE Statement](https://dev.mysql.com/doc/refman/8.0/en/check-table.html)
- [MySQL 8.0 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)
- [MySQL 8.0 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.0/en/point-in-time-recovery.html)
