# Recovery Drills, Failover, and Business Requirement Verification

A PostgreSQL system is considered resilient only when the team can restore data and bring the application back into service within committed limits. Having backups or a standby is not enough to prove that. Teams must regularly rehearse restores, server failovers, post-incident data verification, and end-to-end confirmation that critical business flows still work properly.

Within the Testing chapter of Database Engine Relational PostgreSQL, this lesson focuses on planning and executing drills for backup/restore, point-in-time recovery (PITR), failover, and business requirement verification. The goal is to measure recovery time, potential data loss, data integrity, and the ability to keep serving users.

## 1. Recovery Concepts to Distinguish

### 1.1. Backup, restore, and PITR

**Backup** is a stored copy of data used to recover when data or servers are lost, corrupted, or unexpectedly modified. PostgreSQL supports several backup methods, including physical backups via `pg_basebackup`, continuous WAL archiving, and logical backups via `pg_dump`/`pg_dumpall`.

**Restore** is the process of using a backup to rebuild a database or cluster. A backup has operational value only once it has been successfully restored in an isolated environment and the restored data has been verified.

**Point-in-time recovery (PITR)** restores a PostgreSQL cluster to a specific timestamp or WAL position by combining a base backup with the required WAL stream. PITR is valuable when a transaction is valid SQL yet wrong for the business—such as an operator accidentally deleting data or a batch job overwriting wrong values. You can restore to the point right before the erroneous action, then extract or migrate the needed data.

Physical backups and WAL archives are typically used to restore an entire cluster to a point in time. Logical backups like `pg_dump` suit restoring a selected database, schema, or object, but do not directly replace cluster-level physical PITR.

### 1.2. Replication and failover

Replication maintains a copy of data on another server. With physical streaming replication, a standby receives and replays WAL from the primary. When the primary fails, an eligible standby can be promoted to become the new primary.

**Failover** shifts service to a backup server when the primary can no longer serve traffic. Failover is typically unplanned due to server, storage, network, or availability-zone failures.

**Switchover** is a planned primary/standby role swap, usually for maintenance, upgrades, or testing. Because the current primary is still healthy, writes can be paused and the standby synchronized cleanly before swapping roles.

Replication is not a backup. An accidental `DELETE`, a faulty batch update, or data encrypted by a malicious application is replicated to the standby. Independent backups and PITR capability remain essential to return to a state prior to a logical incident.

### 1.3. RPO and RTO

Two fundamental metrics describe recovery targets:

- **RPO (Recovery Point Objective)**: the maximum amount of data an organization tolerates losing, usually expressed in time. For example, an RPO of 5 minutes means that after an incident, acknowledged transactions lost prior to the failure must not span more than roughly 5 minutes.
- **RTO (Recovery Time Objective)**: the maximum acceptable time to restore service to the required operational level. For example, an RTO of 30 minutes means critical functions must be back online within 30 minutes of the agreed incident start timestamp.

RPO/RTO are business and operational requirements, not properties automatically guaranteed merely by enabling replication or taking backups. They must be measured in real drills.

```text
Time of last acknowledged transaction
                  |
                  v
           Incident occurs
                  |
                  |<------ potential data loss window ----->|
                  |                                         |
                  v                                         v
          Incident detected                          Recovery point
                  |                                         |
                  |<------------- RTO --------------------->|
                  v                                         v
         Response begins                           Application operational
```

When measuring RTO, agree on the start point. It can start when the incident actually occurred or when monitoring detected it. If the organization measures from detection, also record detection latency and estimated incident start time so outage duration is not underestimated.

## 2. Defining Recovery Requirements from Business Needs

Before choosing PostgreSQL techniques, define what the application must recover. A database can open its port and answer `SELECT 1` while still failing business requirements if users cannot log in, orders cannot be placed, or balances are inconsistent.

### 2.1. Inventory critical services and data

For each service, document:

| Item | Question to answer |
|---|---|
| Business workflow | Which user actions must complete? |
| Critical data | Which tables, schemas, sequences, large objects, or configuration data must recover? |
| Priority | Which features must return first, and which can wait? |
| RPO | How much acknowledged data can the organization tolerate losing at most? |
| RTO | How quickly must the service return to operation? |
| Dependencies | Are DNS, secrets, certificates, queues, object storage, external APIs, or auth services required? |
| Owner | Who signs off that data and workflows recovered accurately? |

For example, a retail system might require product lookup back within 15 minutes while historical reporting can wait several hours. Confirmed order data might have an RPO near zero, whereas cache data can be rebuilt.

### 2.2. Translating RPO/RTO into test criteria

Requirements need concrete measurement methods. For example:

| Requirement | Measurement criteria |
|---|---|
| RPO at most 5 minutes | Identify the last transaction acknowledged by the application before the incident and the last transaction present after recovery; compute the time gap and reconcile transaction IDs. |
| RTO at most 30 minutes | Measure from the agreed incident start timestamp until business transaction tests pass and the system meets minimum performance thresholds. |
| Zero lost confirmed orders | Reconcile order IDs from an independent confirmation log against post-recovery data. |
| No duplicate payments | Reconcile idempotency keys, payment gateway transaction IDs, and payment record counts. |
| Financial reports balance | Recompute total debits/credits or balances from restored data and compare against control totals. |

Record test transaction markers outside the database under drill—for instance in an external log store or test coordinator. Relying solely on data inside the failed database can leave the team unaware of which transactions the application already reported as successful before losing connectivity.

## 3. Preparing the PostgreSQL Recovery Foundation

### 3.1. Choosing the right backup mechanisms

Common mechanisms cover different scopes:

| Mechanism | Scope | Common purpose |
|---|---|---|
| `pg_dump` | Single database, logical format | Migrate or restore selected databases/schemas/objects. |
| `pg_dumpall` | All databases and cluster-wide objects in SQL | Logical backup of roles, cluster objects, and databases. |
| `pg_basebackup` | Physical cluster base backup | Rebuild a cluster or provision a standby. |
| WAL archiving | Continuous WAL stream | PITR and recovering changes after a base backup. |
| Storage snapshot | Volume or filesystem snapshot | Fast backups when coordinated consistently with PostgreSQL and storage. |

A complete strategy typically combines periodic base backups with continuous WAL archiving, off-site copies in an independent location, and logical backups for object-level recovery. Storage snapshots must follow PostgreSQL and storage platform consistency guidelines; never assume snapshotting an arbitrary running volume produces a valid backup.

### 3.2. Enabling WAL archiving

Example `postgresql.conf` settings for a primary requiring PITR:

```conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /srv/pg_wal_archive/%f && cp %p /srv/pg_wal_archive/%f'
```

This is an illustrative test-environment example. In production, use reliable secure storage with proper access control, capacity, encryption, retries, and alerting when archiving fails. Never store backups only in a directory on the same volume as the data directory.

`archive_command` must return a success exit code only after the WAL segment is safely persisted. If it reports success before data is durable, PostgreSQL may recycle WAL that the backup store never saved. If it fails continuously, `pg_wal` can grow and fill the disk.

Check archive status on the primary:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

An increasing `failed_count` is an immediate signal to investigate. Also monitor filesystem capacity, time since the last successful archive, and readability of WAL files from storage.

### 3.3. Creating a physical base backup

Example taking a backup to a target directory with `pg_basebackup`:

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replication_user \
  -D /backup/pg/base_2026_11_14 \
  -Fp \
  -Xs \
  -P
```

Key flags in the example:

- `-h`, `-p`, `-U`: host, port, and role used to stream the backup.
- `-D`: target directory prepared according to `pg_basebackup` requirements.
- `-Fp`: output in plain directory format.
- `-Xs`: stream required WAL during the backup.
- `-P`: display progress.

The backup role requires replication privileges and matching connection configuration. Manage authentication and TLS per security policy. The `-R` flag generates configuration so the backup directory starts up as a standby; when creating an isolated restore for testing, review generated config files carefully so the test server does not accidentally join replication or receive production traffic.

When a backup includes a manifest, `pg_verifybackup` can verify backup contents against the manifest:

```bash
pg_verifybackup /backup/pg/base_2026_11_14
```

This command checks backup file integrity within the tool's scope. It does not prove the application can start, query properly, or meet business requirements. An actual restore remains stronger evidence.

### 3.4. Monitoring standbys and replication lag

On a standby, inspect recovery status and the WAL receiver:

```sql
SELECT pg_is_in_recovery();

SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
```

On the primary, inspect connected standbys:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Lag columns can be `NULL`, especially when there is no recent WAL activity; interpret LSNs, timestamps, and test workloads together rather than reading a single field in isolation. Use `pg_wal_lsn_diff()` to calculate byte distances between LSN positions.

```sql
SELECT
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
```

LSN distance reflects unreplayed WAL volume at the moment of sampling, not directly minutes of data loss. To measure RPO, reconcile committed and acknowledged business transactions.

### 3.5. Protecting backups

Backups must survive even if the primary server or production accounts are compromised. Typical safeguards include:

- Store backups in a separate storage system or account isolated from the database server.
- Restrict delete and modify permissions; use immutable/object locks if supported by the platform.
- Encrypt in transit and at rest; manage encryption keys separately with a documented key recovery procedure.
- Record metadata covering PostgreSQL version, extensions, configuration, tablespaces, checksums, and backup timestamp.
- Monitor retention of base backups and WAL to ensure full recovery chains remain intact.
- Test restoring directly from the actual backup repository, not only from a temporary local copy on the backup host.

## 4. Rehearsing Restore and Point-in-Time Recovery

### 4.1. Planning before restoring

Before starting a restore, define:

1. Simulated incident and target recovery point.
2. Selected base backup and required WAL sequence.
3. Compatible PostgreSQL version and extensions.
4. Data directory, tablespace locations, filesystem permissions, and disk space.
5. How configuration, certificates, secrets, and roles are restored.
6. Network isolation so the restored database cannot receive production traffic or connect back to production systems accidentally.
7. Technical sign-off owner and business sign-off owner.

Run initial tests on an independent restore host or container. If the goal is testing a backup, never overwrite a live production data directory.

### 4.2. Restoring from a base backup and WAL archive

General physical restore procedure:

1. Provision a target host and volume with sufficient capacity.
2. Restore the base backup into the data directory per your PostgreSQL version's instructions.
3. Set file ownership and permissions.
4. Configure `restore_command` to fetch WAL segments from the archive store.
5. Create `recovery.signal` inside the data directory to instruct PostgreSQL to enter archive recovery.
6. Start PostgreSQL and monitor logs until recovery finishes or pauses at the recovery target.
7. Verify data, configuration, privileges, and application behavior before opening service.

In PostgreSQL 12 and later, recovery settings belong in `postgresql.conf` or an included config file; `recovery.signal` activates archive recovery. Older versions use different configuration mechanisms, so consult the manual for your exact major version.

Example recovery configuration from a WAL archive:

```conf
restore_command = 'cp /srv/pg_wal_archive/%f %p'
recovery_target_timeline = 'latest'
```

This `restore_command` assumes an archive on the restore host's local filesystem. In practice, dedicated backup tools or object-storage download commands are commonly used. The command must return a non-zero exit code when a requested file does not exist and write the target file safely.

### 4.3. Restoring to a specific point in time

PITR lets you target a moment just before an erroneous action. For example, suppose an accidental delete occurred at 10:42 UTC. Set the target just prior:

```conf
restore_command = 'cp /srv/pg_wal_archive/%f %p'
recovery_target_time = '2026-11-14 10:41:30+00'
recovery_target_inclusive = on
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
```

Then create the signal file:

```bash
touch /var/lib/postgresql/data/recovery.signal
```

When PostgreSQL pauses replay at the target with `recovery_target_action = 'pause'`, you can connect and inspect the data before deciding to proceed. Once confirmed to complete recovery and allow writes, run:

```sql
SELECT pg_wal_replay_resume();
```

Alternatively, set `recovery_target_action = 'promote'` so PostgreSQL promotes immediately upon reaching the target. `pause` is convenient in drills to inspect before finalizing the recovery point; `promote` fits when the procedure already knows the target and wants the server to become a new primary.

`recovery_target_time` refers to transaction commit timestamps recorded by PostgreSQL. `recovery_target_inclusive` determines whether a transaction matching the exact target timestamp is included. When recovering from an erroneous operation, choose a timestamp with a safe margin before the bad transaction, then verify using transaction IDs and business records. Do not rely solely on application server clocks if clocks across systems are not synchronized.

Other recovery targets include `recovery_target_lsn`, `recovery_target_xid`, and `recovery_target_name` (when a named restore point was created). These are valuable when procedures log exact WAL positions or restore point names. Consult the manual for your PostgreSQL version for exact syntax and behavior.

### 4.4. Post-restore verification

PostgreSQL-level checks:

```sql
SELECT version();
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
```

`pg_is_in_recovery()` shows whether the server is still in recovery or has promoted. `pg_last_wal_replay_lsn()` and `pg_last_xact_replay_timestamp()` track replay progress; the timestamp can be `NULL` if no qualifying transaction has been replayed yet and should not be used alone to prove RPO.

Next, verify:

- Required databases, schemas, tables, indexes, sequences, extensions, and tablespaces exist.
- Roles, memberships, grants, default privileges, and authentication settings are restored.
- Critical tables are readable and representative business queries execute properly.
- Constraints, foreign keys, and data rules hold.
- The application connects using the intended roles and secrets.
- Scheduled jobs, queue consumers, and external integrations do not fire accidentally inside the restore environment.

After restoring, running `ANALYZE` may be needed so the planner has up-to-date statistics. Do not run `VACUUM FULL` or heavy maintenance as a default step of every restore; perform them only with specific justification.

### 4.5. Logical restore for a database or subset of objects

When restoring a single database or schema from a logical backup, use `pg_restore` with an archive created by `pg_dump`:

```bash
createdb -h restore-db.example.net -U restore_admin sales_restore

pg_restore \
  -h restore-db.example.net \
  -U restore_admin \
  -d sales_restore \
  --verbose \
  /backup/pg/sales_2026_11_14.dump
```

If an archive spans multiple databases or cluster-level objects such as roles, prepare a matching restore plan. `pg_dump` does not automatically include server config files, certificates, OS cron jobs, or external dependencies. Back up those components via a separate procedure.

## 5. Rehearsing Switchover and Failover

### 5.1. Pre-promotion checks

Before promoting a standby, know:

- Whether the current primary is still running or has genuinely lost write capability.
- Whether the standby is an eligible candidate actively receiving WAL.
- How far received, flushed, and replayed LSNs have progressed on the standby.
- Whether replication is synchronous or asynchronous and whether any acknowledged transactions might not have reached the standby.
- Which endpoint the application uses and how connection pools refresh connections.
- Who holds authority to approve promotion and who isolates the old primary.

Never promote a standby while the old primary can still accept application writes unless the architecture has thoroughly tested fencing and leader coordination. If two nodes accept writes independently, the system can split-brain into divergent data histories.

### 5.2. Planned switchover

A general manual switchover sequence may include:

1. Announce the maintenance window and confirm the incident/change lead.
2. Pause or drain application write paths gracefully; finish or cancel in-flight transactions per policy.
3. Confirm the standby has received and replayed up to the primary's final WAL position. If needed, switch to synchronous mode during handoff or wait for catch-up.
4. Shut down the old primary cleanly so it cannot accept further writes.
5. Promote the chosen standby.
6. Point connection endpoints, VIPs, DNS, or service discovery to the new primary.
7. Refresh connection pools and gradually reopen write traffic.
8. Run business transaction tests, check logs, and monitor load.
9. Reconfigure the old primary as a standby of the new primary after verifying data and executing the proper rejoin procedure.

In some architectures, automated HA tooling handles stopping, promoting, and endpoint updates. Actual procedures must follow the deployed orchestration tool—never mix manual commands with automated HA control without understanding cluster state.

### 5.3. Unplanned failover when the primary is lost

Unplanned failover must strictly control split-brain risk. Conceptual sequence:

1. Detect and confirm the primary can no longer serve safely. Distinguish a dead database from a one-sided network partition.
2. Execute fencing to prevent the old primary from continuing writes—using power fencing, cloud instance isolation, network isolation, or equivalent infrastructure controls.
3. Evaluate surviving standbys and pick the candidate with the freshest data per RPO policy.
4. Promote exactly one standby.
5. Switch application endpoints to the new primary and verify only one writer exists.
6. Run technical and business tests, documenting any data loss relative to acknowledged transactions.
7. Investigate the old primary and reintroduce it only after resynchronizing via a safe procedure.

With PostgreSQL, a standby can be promoted via SQL:

```sql
SELECT pg_promote(wait => true, wait_seconds => 60);
```

Or via command line on the standby host:

```bash
pg_ctl promote -D /var/lib/postgresql/data
```

These commands only perform promotion. They do not verify the old primary is fenced, update DNS, pick the best standby, or coordinate applications. Those responsibilities belong to the HA layer and surrounding infrastructure.

### 5.4. How synchronous and asynchronous replication affect RPO

With asynchronous replication, the primary can acknowledge a commit before the standby receives and flushes the corresponding WAL. If the primary fails suddenly, recently acknowledged transactions may be absent from the promoted standby. Actual exposure depends on network latency, load, and standby health.

With synchronous replication, the primary waits for standby acknowledgment according to `synchronous_standby_names` and `synchronous_commit`. Acknowledgment level can correspond to WAL write, flush, or replay depending on mode. Synchronous settings reduce the risk of losing acknowledged transactions on failover under the configured standby assumptions, at the cost of higher commit latency and potential write blocking if no eligible synchronous standby remains.

Conceptual configuration example:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

Do not copy this snippet directly into production without evaluating topology, `application_name` settings, standby count, and disconnect policies. `synchronous_commit = remote_apply` waits until the standby replays the transaction before confirming commit, while other levels acknowledge at different stages. Choose based on RPO and latency budgets.

## 6. Rejoining the Old Primary After Failover

After promoting a standby, the old primary may contain WAL or transactions absent on the new primary. Never simply restart the old primary and let it accept writes again. Rejoin the topology using one of these approaches:

- Rebuild the old primary from a fresh base backup of the current primary.
- Use `pg_rewind` if both data directories meet the tool's prerequisites and all needed WAL remains available.
- Use the rebuild workflow provided by your HA platform or managed PostgreSQL service.

`pg_rewind` synchronizes an older data directory onto the new primary's timeline after two nodes diverge. Key prerequisites include having data checksums enabled at `initdb` or `wal_log_hints` enabled, plus retaining the required WAL. The target server must be stopped before running rewind. Always verify exact version documentation and take a safe backup before proceeding.

Illustrative example run from an admin host targeting the stopped old primary's data directory:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/old_primary \
  --source-server='host=new-primary.example.net port=5432 dbname=postgres user=rewind_user'
```

After rewinding, configure the old node to follow the new primary and start it as a standby. Check `pg_stat_wal_receiver`, recovery status, and lag before returning the node to the standby pool. If rewind prerequisites are unmet or WAL is missing, rebuild from a valid backup.

## 7. Verifying Business Requirements After Recovery

### 7.1. Multi-layer verification

Do not stop once PostgreSQL opens its port. Verify across layers:

| Layer | Example checks | What must be proven |
|---|---|---|
| Infrastructure | Volume mounts, capacity, network, DNS, TLS | Server has required resources and connectivity. |
| PostgreSQL | Processes, logs, recovery state, connections, roles | Database is running in the expected role. |
| Structure | Schemas, tables, indexes, constraints, sequences, extensions | Required objects exist and remain compatible. |
| Data | Row counts, keys, totals, statuses, transaction markers | Data satisfies business invariants. |
| Application | Login, read, create, update, commit | Application executes real workflows. |
| Integrations | Queues, payment gateways, email, object storage | Downstream systems work without duplicate processing. |
| Operations | Fresh backups, monitoring, alerts, job schedules | System can continue operating safely. |

### 7.2. Verifying data invariants

Each business domain should define queryable invariants. For example:

**Every order must reference a valid customer:**

```sql
SELECT COUNT(*) AS orders_without_customer
FROM sales.orders o
LEFT JOIN sales.customers c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

**Order line totals must match order totals within defined rounding tolerance:**

```sql
SELECT
    o.order_id,
    o.total_amount,
    SUM(oi.quantity * oi.unit_price) AS calculated_amount
FROM sales.orders o
JOIN sales.order_items oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - SUM(oi.quantity * oi.unit_price)
) > 0.01;
```

**Payment provider transaction IDs must not be recorded multiple times:**

```sql
SELECT provider_transaction_id, COUNT(*) AS occurrences
FROM payments.transactions
GROUP BY provider_transaction_id
HAVING COUNT(*) > 1;
```

These queries are examples only. Exact conditions must reflect your real data model, rounding rules, refunds, cancellations, and business logic. A query returning zero rows alone also does not prove all data is intact; select test datasets and reconcile against an independent control source.

### 7.3. Verifying acknowledged transactions

To measure RPO, a test driver can write monotonically increasing transaction IDs or UUIDs and record commit acknowledgments in an independent observer store. After failover or restore, reconcile:

- The last transaction for which the application received a success response.
- The last transaction surviving in the recovered database.
- Transactions sent by the application that received no response.
- Transactions requiring retries and potential duplicate submissions.

A transaction with no response has an indeterminate state: it may have committed before the connection dropped. Applications need idempotency keys or status lookup mechanisms to retry safely. A client timeout alone never proves a transaction failed to commit.

Example probe table:

```sql
CREATE TABLE ops.recovery_probe (
    probe_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probe_token uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    scenario text NOT NULL
);
```

An external process can send periodic probes, recording each token and when the application received commit confirmation. After the drill, compare tokens in the observer store against tokens present in the database. Restrict privileges on the probe table and never let it replace real business transaction logs.

### 7.4. Verifying sequences and identifiers

Replication mechanisms do not always synchronize sequence state the same way as table data. Logical replication, for example, does not automatically synchronize sequence values. After restores or role switches, inspect sequences relative to existing data to avoid issuing duplicate IDs.

Inspect sequence states via `pg_sequences`:

```sql
SELECT schemaname, sequencename, last_value
FROM pg_sequences
WHERE schemaname IN ('sales', 'payments')
ORDER BY schemaname, sequencename;
```

For a specific column, use `pg_get_serial_sequence()` to locate its attached sequence. Adjust sequences carefully respecting ID generation type, cache, increment, and write privileges; never run `setval()` indiscriminately without confirming safe values. For application-generated UUIDs, check the ID generator source and collision risks across nodes.

### 7.5. End-to-end application verification

A post-recovery smoke test suite can execute:

1. Log in with a test account.
2. Look up a record created before the incident.
3. Create a test transaction with a unique idempotency key.
4. Read the transaction back and verify status, totals, and relationships.
5. Resend a duplicate request with the same idempotency key and confirm no second transaction is created.
6. Verify an integration flow such as outbox event dispatch or queue processing.
7. Confirm logs, metrics, and traces are emitted once service resumes.

Smoke tests should exercise production-like endpoints and credentials, while isolating or tagging test records clearly so real customers are unaffected.

## 8. Designing a Drill Scenario Suite

A strong drill program includes multiple scenarios from simple to complex. Never rehearse only a clean restore from the latest backup.

| Scenario | Goal | Outcomes to record |
|---|---|---|
| Full backup restore | Prove a base backup can rebuild the cluster | Restore duration, errors, database state, and business verification results. |
| PITR before accidental delete | Prove recovery to a point before a logical incident | Chosen target, replayed WAL, recovered records, and post-target state. |
| Primary loss | Test failover to a standby | Detection time, fencing, promotion, endpoint switch, and actual RPO. |
| Lagging standby | Verify standby selection policy and RPO | LSNs, potential lost transactions, lag cause, and promotion decision. |
| Lost archive connectivity | Test alerting and backup continuity | Detection time, WAL growth, and archive recovery steps. |
| DNS or pool holding stale endpoint | Test application convergence | Connection convergence time, client errors, and pool refresh method. |
| Recovery to a new host/region | Test infrastructure dependencies and docs | Provisioning time for hosts, volumes, secrets, networking, TLS, and configs. |
| Business data reconciliation | Verify invariants and data-owner sign-off | Reconciliation results, missing/duplicate transactions, and business approval. |

### 8.1. Sample PITR drill sequence

A drill can follow this sequence:

1. Record the start timestamp and create several confirmed test transactions.
2. Inject a simulated fault, such as deleting a batch of records in the drill environment.
3. Note the timestamp or named restore point prior to the fault.
4. Isolate the source database and prepare the recovery host.
5. Select the base backup and WAL archive, and configure PITR.
6. Start recovery to the target and stop in the paused state.
7. Verify pre-target transactions exist and the erroneous change has not appeared.
8. Confirm data accuracy with the business owner.
9. Promote or finalize recovery per scenario, run smoke tests, and measure RTO.
10. Document findings, lessons learned, and remediation actions.

### 8.2. Sample failover drill sequence

1. Confirm primary/standby topology and replication health.
2. Record committed probe transactions and the primary's LSN.
3. Simulate primary loss using the approved method in the drill environment.
4. Perform fencing or prove fencing prevented the old primary from writing.
5. Select a standby per policy and promote exactly one node.
6. Switch endpoints and refresh application connections.
7. Run read/write smoke tests and verify business invariants.
8. Reconcile probes to measure RPO and calculate RTO from recovery timestamps.
9. Rejoin the old primary using the documented procedure.
10. Confirm stable topology, resumed backups, and restored alerts.

## 9. Measurement and Completion Criteria

### 9.1. Recording timestamps

Record these milestones for every scenario:

| Milestone | Meaning |
|---|---|
| `T0` | Incident occurs or agreed drill start timestamp. |
| `T_detect` | System or operator detects the incident. |
| `T_decide` | Decision to restore/failover is made. |
| `T_fence` | Old primary is confirmed unable to write. |
| `T_promote` | Standby promotes or restore finishes recovery. |
| `T_endpoint` | Endpoints and application connections switch to the new host. |
| `T_business` | First business smoke test succeeds. |
| `T_stable` | Performance and error metrics meet stability thresholds. |

RTO may be measured to `T_business` or `T_stable` depending on service commitments. Report both if restoring minimal functionality and reaching full operational stability occur at different times.

### 9.2. Pass/fail criteria

A drill passes only when evidence satisfies all predefined criteria. For example:

- Restore finishes without WAL errors or missing files.
- Databases are in the expected primary/standby roles.
- Actual RPO does not exceed the committed limit.
- Actual RTO does not exceed the committed limit.
- Key data invariants hold.
- Confirmed transactions lost do not exceed threshold; retried transactions are not duplicated.
- Application and critical integrations work via the new endpoint.
- No two writers are active simultaneously.
- Backups, WAL archiving, monitoring, and alerting resume after the drill.
- Logs, timestamps, reconciliation queries, and business-owner sign-off are archived.

If a criterion fails, document the impact and remediation—for instance increasing base backup frequency, fixing archiving, strengthening fencing, lowering DNS TTL, tuning connection pools, or optimizing data validation. Never relax RPO/RTO after a drill merely to make results look passing; any target change requires service-owner approval.

### 9.3. Post-drill report

A report should include:

```text
Scenario name:
Environment / PostgreSQL version:
Date and participants:
Target RPO / RTO:
Base backup / timeline / recovery target:
Incident start time:
Service recovery time:
Measured RTO:
Last confirmed transaction before incident:
Last transaction present after recovery:
Measured RPO:
Technical verification results:
Business verification results:
Incidents or discrepancies found:
Remediation actions / owner / due date:
Service owner sign-off:
```

Retain reports and sufficient evidence to compare across future drills. Never store passwords, private keys, or unnecessary personal data in reports.

## 10. Safety During Drills and Common Mistakes

Restore/failover drills can disrupt service if commands are run on production by mistake or if a recovered machine joins the live network. Define clear scope, environment, coordinators, and stop conditions. For production drills, follow an approved change process with a rollback plan.

| Common mistake | Consequence | Prevention |
|---|---|---|
| Checking backups only by confirming files exist | Backups may be corrupt or missing required WAL | Periodically test restores directly from the backup store. |
| Storing backups on the same disk as the primary | One storage failure destroys both data and backups | Store independent copies across separate failure domains and restrict delete rights. |
| Not monitoring archive failures | WAL is not archived and `pg_wal` can fill up | Monitor `pg_stat_archiver`, disk capacity, and time since last archive. |
| Promoting a standby while old primary still writes | Split-brain and divergent data histories | Fence before promoting; permit only one writer. |
| Picking a standby solely because it is online | May promote a standby with heavy replication lag | Compare WAL receive/flush/replay state against RPO policy. |
| Treating replication as a backup | Accidental deletes or logical corruption propagate to standbys | Maintain independent backups and rehearse PITR. |
| Skipping application checks once DB port opens | Users still cannot complete business flows | Run end-to-end smoke tests and verify invariants. |
| Skipping sequence checks after restore or logical replication | New IDs may collide or sequences lag behind data | Check and adjust sequences per table before enabling writes. |
| DNS changes while connection pools keep old sockets | Some app traffic keeps hitting the old primary | Verify TTLs, pool lifetimes, retries, and endpoint refresh behavior. |
| Retrying transactions after timeouts without idempotency | Can create duplicate orders or payments | Use idempotency keys and query indeterminate transaction status. |
| Rejoining old primary by simply starting it up | Node may continue on its old WAL history | Use `pg_rewind` when eligible or rebuild from a backup. |
| Measuring only the promote command duration | Ignores detection, endpoint switchover, and business verification | Record the full timeline from incident start to stable service. |
| Never drilling when archives or standbys fail | Runbooks work only under ideal conditions | Include network faults, lag, disk pressure, and missing-WAL scenarios. |

## 11. Drill Cadence and Continuous Improvement

Drill frequency depends on service criticality, rate of architectural change, and audit requirements. A reference schedule:

| Activity | Reference cadence | Evidence |
|---|---|---|
| Verify backup jobs and WAL archiving | Daily or continuous automation | Metrics, alerts, logs, and last archive timestamp. |
| Test-restore a backup into an isolated environment | Monthly or per policy | Restore report, duration, and query verification results. |
| PITR drill | Quarterly or after major changes | Recovery target, pre/post-target data verification. |
| Failover/switchover drill | Quarterly or per service commitments | Timeline, RPO/RTO, and smoke test results. |
| Region or infrastructure recovery drill | Risk-based, typically at least annually | Proof of provisioning, restore, DNS, secrets, and business checks. |
| Runbook review after PostgreSQL/extension/HA changes | After every significant change | Document version, approver, and test results. |

This is a reference cadence; organizations must tailor it to RPO/RTO, regulations, data scale, and operational capacity. Any major change—such as a major version upgrade, storage migration, HA tool change, region move, or backup workflow change—can invalidate old runbooks and requires a fresh drill.

## 12. Operational Checklist for a Drill

### Before the drill

- [ ] RPO/RTO targets and pass/fail criteria confirmed by the service owner.
- [ ] Scenario, scope, schedule, and owners documented.
- [ ] Backups, WAL archives, secrets, and required configs ready.
- [ ] Recovery host or standby has adequate resources and matching version.
- [ ] Network isolation prevents the test environment from accidentally connecting to production.
- [ ] Probe driver or independent data source ready for transaction reconciliation.

### During the drill

- [ ] Record timestamps and PostgreSQL state at every step.
- [ ] Verify exact backup, timeline, and recovery target.
- [ ] For failover, fence the old primary prior to promotion.
- [ ] Ensure only a single primary accepts writes.
- [ ] Monitor logs, WAL replay, connections, and application errors.
- [ ] Execute technical checks and predefined business transactions.

### After the drill

- [ ] Calculate actual RPO/RTO and compare against targets.
- [ ] Reconcile transactions, data invariants, and integration states.
- [ ] Rejoin nodes or tear down the test environment per runbook.
- [ ] Confirm backups/WAL archiving and alerts are healthy again.
- [ ] Log issues, remediation actions, owners, and due dates.
- [ ] Obtain business-owner sign-off on recovery results.

## 13. Conclusion

PostgreSQL recovery drills must prove three things: data can be rebuilt from backups/WAL, service can fail over to an eligible node without split-brain, and the application still satisfies business requirements after recovery. RPO/RTO must be measured using real transactions and timestamps; a database merely starting up is only part of the outcome.

A dependable process combines independent backups, WAL archiving, periodic restore/PITR drills, appropriate replication, fencing during failover, data invariant checks, and end-to-end smoke tests. Post-drill reports expose gaps between targets and current capabilities, driving continuous improvements to runbooks, architecture, and operational procedures.

## References

- [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [PostgreSQL — Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html)
- [PostgreSQL — pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html)
- [PostgreSQL — pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html)
- [PostgreSQL — Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET)
- [PostgreSQL — System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html)
