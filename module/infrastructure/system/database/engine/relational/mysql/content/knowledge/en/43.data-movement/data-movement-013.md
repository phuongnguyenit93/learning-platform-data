# Cutover Planning, Write Freeze, and Rollback When Checks Fail

A database migration is complete only when applications use the right target server, data is verified, and operations knows how to respond if post-cutover checks fail. Cutover is the moment read/write traffic shifts from the source system to the target system. A write freeze establishes a stable data checkpoint for synchronizing final changes. Rollback returns the service to a predefined state if acceptance criteria are not met.

A solid plan defines the authoritative data source at every stage, how to prevent both sides from accepting writes simultaneously, go/no-go criteria, and how to handle new data created after the target begins accepting transactions. This guidance applies to MySQL migrations across servers, clusters, cloud environments, or deployment versions.

## 1. Defining Scope and Cutover Objectives

Before choosing tools, identify what will change and what must remain unchanged:

| Item | Questions to Answer |
|---|---|
| Source and target | Which servers, versions, topologies, and endpoints are source and target? |
| Data | Moving the full instance, selected databases, or a set of tables? |
| Schema | Are data types, collations, indexes, partitions, or table structures changing? |
| Workload | Which apps read, write, run batches, report, or use scheduled events? |
| Integrations | Are there ETL jobs, CDC consumers, queue workers, BI tools, backup agents, or external services connecting directly? |
| Downtime | What maximum downtime can the business tolerate? |
| RPO | What maximum data loss is acceptable if a rollback is required? |
| RTO | Within what maximum duration must the service recover? |
| Governance | Who signs off go/no-go and who has authority to halt cutover? |

Inventory connection endpoints, accounts, secrets, DNS, proxies, MySQL Router, connection pools, and background tasks. An application might not be the sole writer: cron jobs, Event Scheduler events, operational scripts, or integration pipelines might keep writing to the source even after APIs are switched.

Define measurable success criteria upfront, for example:

- All required schemas and objects exist on the target.
- Data at the cutover checkpoint is reconciled within agreed tolerances.
- Target caught up to the source's final transaction before write freeze ends.
- Read/write traffic routes to the intended endpoints.
- Critical business queries and background jobs execute successfully.
- Zero data errors, connection failures, or latency breaches occur during the monitoring window.

Never let vague criteria like "the app looks fine" replace quantitative checks.

## 2. Selecting Migration and Change-Sync Method

There are two common deployment patterns:

**Downtime cutover:** stop writes on the source, take a dump or consistent snapshot, restore to the target, verify, and switch applications. This is simpler when data volume is moderate and the outage window is acceptable.

**Low-downtime cutover:** load baseline data into the target while the source keeps serving, then use MySQL replication, binary-log CDC, or a migration tool to stream ongoing changes. At cutover, close write streams, wait for the target to catch up, and shift traffic. This shortens the write freeze at the cost of operating a sync pipeline and managing lag.

| Method | Best Suited When | Control Points |
|---|---|---|
| Logical dump/restore | Small datasets or selective database/table migration | Dump/restore duration, consistent snapshot, routines, triggers, events, and privileges |
| Physical backup/restore | Large datasets in compatible environments | Version, backup format, GTID/binlog metadata, and file permissions |
| MySQL replication/CDC | Changes must sync while the source stays live | Binlog retention, GTID or file/position, schema compatibility, lag, and apply errors |
| Dedicated migration tools | Platform shifts or complex automation requirements | Change capture mechanism, data-type limits, consistency checks, and operational overhead |

Do not start loading data before confirming the target has adequate storage, schema support, and compatible configuration. For migrations involving schema transformations, design mappings and transformation order explicitly; do not assume replication can automatically translate arbitrary structural changes.

## 3. Preparing Source and Target

### 3.1. Compatibility Verification

Compare configuration and objects across both environments:

- MySQL versions and SQL features in use.
- Storage engines, character sets, collations, and index key lengths.
- SQL mode, time zone, transaction isolation, and date/time settings.
- Data types, generated columns, expression indexes, partitions, and constraints.
- Triggers, views, stored procedures, functions, events, and `DEFINER`.
- Accounts, roles, grants, authentication plugins, and TLS policies.
- Auto-increment, foreign keys, unique constraints, and case sensitivity of object names.

Variables like `lower_case_table_names` affect how table names are stored and compared across operating systems. Verify before restoring or running applications on the target. In particular, never alter this variable arbitrarily on an instance that already holds data.

Ensure the target has sufficient CPU, RAM, IOPS, storage capacity, network throughput, and connection limits. Size storage for data, indexes, temporary files, relay/binlogs, backups, and growth headroom during cutover.

### 3.2. Security and Privilege Checks

Create or verify application accounts on the target with least-privilege access. Check dedicated replication/CDC accounts, operational privileges, TLS certificates, and secret delivery. Never copy overly broad admin accounts just to make an application connect.

Test firewalls, security groups, internal DNS, routing, proxies, and connectivity from every application subnet. A target may work on a private test network yet be unreachable from production subnets; test from the exact hosts that will run applications after cutover.

### 3.3. Recovery Readiness

Take a restorable backup of the source before making changes. Validate the backup via a test restore or equivalent verification procedure. Record timestamps, GTID set or binary log coordinates, configuration, and versions. Store backups in a fault domain and access boundary isolated from the source.

The target should also have a pre-cutover snapshot if state preservation is needed for investigation. Size binlog retention long enough to complete the migration and recover from an extended interruption.

## 4. Rehearsing Before Cutover Day

A rehearsal measures real timings and uncovers missing steps. Use data matching production volume and distribution; if using anonymized data, preserve key characteristics such as row counts, indexes, string lengths, and key distributions.

During rehearsal:

1. Provision the target from scratch using the exact planned configuration.
2. Run initial data load and measure elapsed time.
3. Enable the CDC/replication stream and generate representative write load on the source.
4. Measure change generation rate versus target apply rate.
5. Execute a simulated write freeze, capture the GTID or binlog position, and wait for target catch-up.
6. Run schema checks, checksums, business queries, and smoke tests.
7. Test switching application endpoints, draining connection pools, and reverting to old endpoints.
8. Time every step, identify failure points, and update the runbook.

If the source's change generation rate exceeds the target's apply rate over sustained periods, the target will never catch up. Improve target capacity, network, applier tuning, or throttle load before picking a cutover date.

## 5. Write Freeze Plan

The write freeze is the single most critical control point of cutover. Its goal is to guarantee zero new business transactions are written to the source while the final delta is applied to the target.

A complete write freeze must cover:

1. Pausing write APIs or write features per plan; returning maintenance responses or placing the app in read-only mode.
2. Pausing workers, queue consumers, cron jobs, ETL jobs, Event Scheduler events, and scripts that can write to the source.
3. Stopping or draining running batches; confirming unprocessed messages stay safely queued for replay.
4. Waiting for open transactions to complete or handling them per approved procedure.
5. Blocking application and integration accounts from opening new write streams to the source.
6. Recording the freeze timestamp and obtaining confirmation from every system owner.

Inspect remaining open InnoDB transactions on the source:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  trx_mysql_thread_id
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Correlate results with the process list and running jobs. Never conclude writes are frozen just because a single query returned no open transactions; an app or job could open a new transaction moments later.

After stopping write streams at the application tier, enable read-only mode on the source as an extra safeguard:

~~~sql
SET GLOBAL super_read_only = ON;

SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

This mode does not replace stopping applications, workers, and out-of-band writers. Highly privileged admin accounts can still change settings or lift protections; therefore control privileges and network endpoints throughout the cutover window. Replication still needs to read binlogs from the source so the target catches up.

Capture a final checkpoint only after the write freeze is truly in effect. With GTID, fetch the executed set on the source:

~~~sql
SELECT @@GLOBAL.gtid_executed;
~~~

With file/position replication, capture binary log status using your version's syntax, such as `SHOW BINARY LOG STATUS` or `SHOW MASTER STATUS` on older versions. Record filename, position, and collection timestamp. Never capture the checkpoint before the last transactions complete.

## 6. Waiting for Target Catch-Up and Verifying the Checkpoint

When using GTID, tell the target to wait until it executes the GTID set captured from the source:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET(
  'GTID_SET_CAPTURED_FROM_SOURCE',
  60
);
~~~

Replace the placeholder string with the exact captured GTID set. A return value of `0` means the target executed that GTID set; `1` means the timeout expired; `NULL` indicates an error. If it times out or errors, do not shift write traffic. Inspect receiver/applier status, SQL errors, I/O errors, connectivity, and binlog retention.

With file/position replication, compare received and applied positions in replica status. Use `SHOW REPLICA STATUS` on newer versions or the corresponding command on older versions. The target has caught up only when the applier has applied up to the final checkpoint, not merely when the receiver has read it.

If the source already purged binary logs needed by the target, replication cannot proceed. Never skip events or manually advance positions to jump over a gap. Restore from a consistent backup and re-establish sync coordinates.

## 7. Pre-Cutover Traffic-Switch Checks

Proceed only when all predefined checks pass. Structure checks across layers to catch every class of discrepancy.

### 7.1. Schema and Database Objects

Compare:

- Databases, tables, columns, data types, nullability, and defaults.
- Primary keys, unique keys, foreign keys, indexes, and partitions.
- Triggers, views, procedures, functions, and events.
- `DEFINER`, roles, users, grants, and execution privileges.
- Character sets, collations, SQL modes, and variables affecting query behavior.

For migrations with schema transformations, verify per-column mappings and handling of incompatible values. For instance, converting a string column to numeric requires reporting unparseable values; never let failures surface only when live apps write data.

### 7.2. Data Reconciliation

Verify across multiple levels:

| Scope | Verification Check |
|---|---|
| Database/table | Object inventory and table counts |
| Table | Row counts, min/max primary keys, and aggregate totals |
| Chunk | Key-range checksums to isolate discrepancies |
| Row | Missing, extra, or differing row values by key |
| Business | Order totals, payment totals, inventory, balances, or other key KPIs |

Equal row counts do not prove identical contents. For large tables, use chunked checksums or tools like `pt-table-checksum`, run against equivalent snapshots while evaluating I/O impact. Once the source is frozen, reconciliation is much clearer because data is no longer shifting during comparison.

### 7.3. Smoke Tests on the Target

Test connectivity with actual application accounts and TLS. Execute critical read queries, joins, paginated queries, reporting queries, and flows relying on stored procedures or views.

Do not create real production data in the target prior to cutover approval unless a plan exists to handle those test writes. If write tests are needed, use a dedicated test schema/tenant or identifiable test transactions cleaned up per procedure.

### 7.4. Confirming Go/No-Go Criteria

Maintain a sign-off table:

| Criterion | GO Condition |
|---|---|
| Final sync | Target applied up to final GTID or binlog checkpoint |
| Schema | Zero unapproved discrepancies |
| Data | Checksums and business metrics meet agreed thresholds |
| Connectivity | Required apps and jobs connect cleanly to target |
| Security | Accounts, grants, TLS, and network policies verified |
| Performance | Target latency and load within thresholds |
| Recovery | Backups and rollback plan ready |

If any mandatory criterion fails, keep the application frozen or restore the source per the prepared plan. Never push traffic over due to time pressure without knowing whether data is missing or wrong.

## 8. Shifting Traffic to the Target

Once a GO decision is issued:

1. Confirm the source remains write-locked and the target holds the verified dataset.
2. Switch write endpoints to the target via proxy, MySQL Router, service discovery, or application config.
3. Update read endpoints per plan; never route read-after-write queries to a lagging replica.
4. Rotate secrets or connection credentials if the target uses separate authentication details.
5. Drain and recycle connection pools so stale connections do not keep hitting the source.
6. Restart workers and scheduled jobs in the agreed order.
7. Run controlled read/write smoke tests on the target.
8. Monitor logs and metrics closely during the hypercare window.

DNS may be cached by the JVM, client libraries, proxies, or operating systems. Updating DNS alone does not guarantee connection pools immediately switch to the target. Verify live endpoints from every service and check active connection counts on both source and target.

Once the target begins accepting production writes, the target becomes the new system of record. Keep the old source fenced so legacy apps, old jobs, or operators cannot accidentally write to it.

## 9. Post-Cutover Monitoring

During hypercare, monitor:

- Connection error rates, authentication errors, timeouts, and deadlocks.
- Query latency, slow queries, CPU, memory, IOPS, and storage usage.
- Connection counts, connection pools, and write throughput.
- Business metrics such as orders, payments, inventory, and balances.
- Queue backlogs, job retries, Event Scheduler events, and integration flows.
- Binlogs, backups, and remaining replication or CDC consumers.

Compare against pre-cutover baselines and agreed thresholds. A service may return HTTP 200 yet drop data because a background job failed to restart; monitor both synchronous APIs and asynchronous tasks.

Keep the old source recoverable without accepting writes. Maintain backups and binlogs per policy. Do not decommission the old source or snapshots right after apps come up; retention must align with storage policy and stability sign-off.

## 10. Designing Rollback and the Point of No Simple Return

Rollback must be defined by phase. Feasibility depends on whether the target has already accepted production writes.

### 10.1. Before the Target Accepts Writes

If the target has not accepted any production transactions, rolling back is much simpler:

1. Halt the traffic switch.
2. Keep the target barred from accepting writes.
3. Point application endpoints back to the source.
4. Confirm connection pools reconnected to the source.
5. Lift the write freeze on the source in proper order, and only after confirming zero target-only writes.
6. Restart workers/jobs and run smoke tests.

Because the source remains the canonical dataset and the target generated no new business data, you can revert without reconciling two divergent write branches.

### 10.2. After the Target Has Accepted Writes

Once the target has accepted production transactions, the old source is stale. Switching applications straight back to the source can lose transactions committed on the target.

If rapid rollback is required after the target accepts writes, design and rehearse a supported reverse-sync path before cutover. That path must specify:

- How binlogs are written and retained on the target.
- How the old source receives changes from the target.
- Schema and topology compatibility.
- How unplanned bidirectional writes are prevented.
- Handling conflicting transactions and primary keys/auto-increment.
- GTID prerequisites and replication re-establishment.
- How data is verified after reverse sync.

Never enable bidirectional replication casually. Two servers taking writes simultaneously can create conflicting transactions, replication loops, or two data branches that cannot be merged automatically.

Without tested reverse replication, the safer choice is usually keeping the target as the writer and applying a forward-fix. If rollback is unavoidable, freeze writes on the target, capture the final GTID/binlog, analyze new transactions, and execute a verified merge plan before reopening the old source.

### 10.3. Rollback Decision Table

| When Failure Is Detected | Data State | Action |
|---|---|---|
| Before write freeze | Source is still the sole writer | Abort migration or reschedule |
| During write freeze, pre-traffic-switch | Source frozen, target has zero writes | If target checks fail, lift source freeze and restart services per runbook |
| After endpoint switch, zero production writes | Target has no new business data | Point endpoints back to source, verify pools, then reopen writes |
| After target accepted production writes | Target holds new transactions | Do not switch blindly to old source; forward-fix or reverse-sync and reconcile first |
| Corrupt data detected on target | Scope of bad transactions and authoritative copy unclear | Freeze writes, preserve logs/backups, analyze, and execute verified recovery |

## 11. Sample Cutover Runbook

### Before the Cutover Window

- [ ] Lock source, target, data scope, and GO/NO-GO decision owner.
- [ ] Complete at least one rehearsal with representative data and workload.
- [ ] Verify source backup is restorable.
- [ ] Verify schemas, versions, configs, privileges, TLS, and networking.
- [ ] Load initial baseline data and start CDC/replication if used.
- [ ] Confirm target keeps pace with transaction generation rate.
- [ ] Prepare endpoint changes, connection pools, and rollback procedures.
- [ ] Notify relevant system owners of the maintenance window.

### During the Cutover Window

- [ ] Pause write APIs, workers, queue consumers, cron jobs, and write-producing events.
- [ ] Drain active transactions and confirm zero remaining write sources.
- [ ] Enable write protection on the source after application write streams stop.
- [ ] Capture the final GTID set or binary log file/position.
- [ ] Wait for target to apply all changes up to the final checkpoint.
- [ ] Verify schema, checksums, business metrics, and critical queries.
- [ ] Make GO/NO-GO decision against agreed criteria.
- [ ] If GO, switch endpoints, recycle connection pools, and run smoke tests.
- [ ] Start workers/jobs and monitor integration flows.

### After Cutover

- [ ] Monitor errors, latency, load, deadlocks, and business metrics.
- [ ] Confirm all applications hit the intended target.
- [ ] Keep old source blocked from writes during the validation period.
- [ ] Take a target backup and verify restore procedures.
- [ ] Archive GTID/binlog markers, checksum results, timestamps, and approvers.
- [ ] End old source retention only after meeting archival and operational criteria.

## 12. Practical Scenario

An online store migrates its database from an aging MySQL server to a new target. The initial dump has been restored and replication is syncing. During the cutover window, operations pauses the write APIs yet discovers a queue consumer is still updating payment statuses on the source.

Handle it in order:

1. Do not declare the write freeze complete while the queue consumer is still writing.
2. Pause the consumer, confirm unprocessed messages remain safely in the queue, and check open transactions.
3. Wait for the final transaction to complete, enable write protection on the source, and capture the final GTID set.
4. Wait for the target to execute that GTID set, then reconcile order counts, payments, and checksums across affected tables.
5. If the target meets criteria, switch endpoints and restart the consumer to resume processing messages against the target.
6. If the target fails criteria before accepting production writes, roll back to the source per the runbook.
7. If an error is detected only after the target processed new payments, freeze the target and analyze new transactions before deciding between a forward-fix or reverse sync.

This scenario shows that a write freeze must encompass every write source, not just user-facing APIs. Likewise, rolling back after the target accepts writes must account for new data rather than simply flipping DNS back to the old server.

## 13. Self-Check Questions

1. Which components beyond application APIs must a write freeze stop?
2. Why must GTID or binary log position be captured only after the final transaction completes?
3. Does the receiver reaching the final checkpoint mean the applier has applied up to that checkpoint?
4. Why are matching row counts insufficient to prove datasets are identical?
5. How does rollback before the target accepts production writes differ from rollback after the target accepts writes?
6. Why should you not casually enable bidirectional replication to preserve rollback capability?
7. Which conditions must be satisfied before making a GO decision?
8. After cutover, why should the old source be kept blocked from writes during the validation window?

A MySQL cutover stays under control when every phase has clear checkpoints, owners, verification criteria, and failure playbooks. The write freeze establishes the final sync checkpoint; reconciliation proves the target is accurate; traffic switching promotes the target to the new writer; and rollback plans must account for every transaction committed after that point.
