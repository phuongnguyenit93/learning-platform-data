# Testing Migrations, Backup/Restore, Replication, and Failover

A MySQL system is only trustworthy when it has proven it can evolve its schema, restore data, synchronize replicas, and switch server roles under controlled conditions. A migration script running without error, a backup job reporting completion, or a replica showing Running status is not enough to conclude the system is safe.

This lesson establishes how to test four critical operational capabilities: **schema migrations**, **backup and restore**, **replication**, and **failover**. Each capability requires clear preconditions, test data, success criteria, timing measurements, and reviewable evidence. Run exercises in an isolated environment or production-equivalent staging; never run destructive tests directly against a system serving live users.

Within **DATABASE_MYSQL**, these tests connect back to table design, data types, keys, SQL queries, indexes, transactions, and concurrency control. They also verify execution plan analysis, query optimization, privilege management, backups, and relational database incident handling.

## 1. Objectives and Testing Model

After this lesson, you will be able to:

- Design a migration test suite across supported schema versions.
- Verify data correctness after DDL changes and backfills.
- Create backups, restore on an independent server, and perform point-in-time recovery using binary logs.
- Verify replicas receive and apply transactions in order and measure replication lag.
- Rehearse switchover/failover, prevent split-brain, and verify application reconnection.
- Measure actual RPO/RTO and archive test evidence.
- Build a reproducible, safe CI/CD pipeline closely aligned with production.

### 1.1. Four Capabilities to Verify

~~~mermaid
flowchart TD
    PLAN[Change plan] --> MIG[Migration test]
    PLAN --> BACKUP[Backup / Restore test]
    PLAN --> REPL[Replication test]
    PLAN --> FAIL[Failover test]
    MIG --> DATA[Verify structure and data]
    BACKUP --> PITR[Restore and PITR]
    REPL --> CONS[GTID, lag, and consistency]
    FAIL --> PROMOTE[Promote and reconnect]
    DATA --> EVIDENCE[Evidence and RPO/RTO]
    PITR --> EVIDENCE
    CONS --> EVIDENCE
    PROMOTE --> EVIDENCE
~~~

| Capability | Core question | Evidence of success |
|---|---|---|
| Migration | Can schemas upgrade from supported versions without corrupting data or breaking apps? | Valid schema, intact data invariants, old/new apps behave per plan |
| Backup/restore | Can data and service be restored within committed targets? | Restore completes, reconciliation passes, RPO/RTO measured |
| Replication | Do replicas receive and apply all transactions in the right order? | GTID/position catches up, data matches, zero applier errors |
| Failover | When the primary fails, can traffic shift to a new server without two writable primaries? | Old primary fenced, new primary accepts writes, clients recover, RPO/RTO recorded |

### 1.2. Distinguishing Logic Tests from Operational Tests

Unit tests are ideal for pure data-transformation logic, validation, or business rules. Integration tests must run against real MySQL to verify DDL, constraints, transactions, SQL mode, collations, locking, and JDBC behavior.

Operational testing requires a multi-server environment with production-like components: primary, replicas, binary log archives, proxies/routers, connection pools, backup storage, and monitoring tools. Mocking a replica or simulating a backup outcome cannot prove replication or restore actually works.

## 2. Designing the Test Environment

### 2.1. Environment Parity with Production

Before testing, document critical characteristics:

- Exact MySQL version, including patch release.
- Storage engine, charset, collation, SQL mode, and time zone.
- `server_id`, GTID, binary log, and replication settings.
- `max_connections`, InnoDB settings, and storage capacity.
- JDBC driver, Spring Boot, Hibernate, and migration tool versions.
- Backup configuration, keyring, TLS, users/roles, and privileges.
- Proxies, MySQL Router, load balancers, and network timeouts.
- Data size, table counts, indexes, and data distributions.

A small MySQL container is very useful for CI, yet it does not fully represent production with terabytes of data, constrained I/O, multiple replicas, and proxies. Use containers to test schema logic and integration; use staging or a similarly sized clone to measure DDL, backup/restore, replication throughput, and failover.

### 2.2. Using MySQL Testcontainers for Integration Tests

Example with Spring Boot, JUnit, and Testcontainers:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("appdb")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    OrderRepository orderRepository;

    @Test
    void persistsAndReadsOrder() {
        Order order = new Order("ORD-1001", new BigDecimal("125.50"));
        orderRepository.saveAndFlush(order);

        Order loaded = orderRepository.findByOrderCode("ORD-1001")
            .orElseThrow();

        assertEquals(new BigDecimal("125.50"), loaded.getTotalAmount());
    }
}
~~~

This is an illustrative example. Add the Testcontainers MySQL/JUnit dependencies matching your project versions. Pin the image to the patch release used in production instead of leaving a floating tag when reproducible results are required. Configure the container with matching charset, collation, SQL mode, and time zone.

Never substitute H2 for MySQL to conclude SQL migrations are compatible. H2 differs from MySQL in syntax, data types, transactions, indexes, locking, and optimizer behavior. H2 can still be useful for unit tests of database-independent logic.

### 2.3. Test Data

Build fixtures covering both ordinary and boundary cases:

- Empty tables and large tables.
- Auto-incrementing primary keys, UUIDs, or composite keys if used by the system.
- `NULL` values, empty strings, Unicode, and maximum-length strings.
- Negative numbers, very large numbers, scaled decimals, dates, and time zones.
- Records with foreign key relationships, referenced rows, and rejected cases.
- Duplicate values, duplicate keys, and legacy historical data.
- Skewed data distributions where certain tenants/tables are very large.
- Concurrent transactions updating the same record.

Version-control fixtures or seed scripts. Every test run should record the exact input data, migration version, and server configuration.

## 3. Testing Schema Migrations

### 3.1. Testing Every Supported Upgrade Path

A migration test suite must exercise multiple starting states:

1. Empty database: fresh installation of all migrations.
2. Latest prior schema version: upgrading to the new version.
3. Older still-supported versions: upgrading through the real migration chain.
4. Database with large data and boundary data: verifying backfills and conversions.
5. Database with dependent objects: views, triggers, routines, events, foreign keys, and indexes.

Do not test only the path from the newest developer schema. Production environments may skip multiple releases, so know whether the system supports direct upgrades from older versions or requires sequential upgrades through each version.

With Flyway or Liquibase, verify migration history, versions, checksums, and execution status. If a migration fails partway through, determine which DDL statements already completed and what state the database is in. Many MySQL DDL statements trigger implicit commits; never assume an entire migration rolls back atomically merely because the migration tool uses transactions.

### 3.2. Example Migration Adding a Column and Backfilling

Suppose the `orders` table needs `source_channel` to record order origin. A compatible rollout splits into stages:

**Expand:** add a nullable column:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN source_channel VARCHAR(24) NULL;
~~~

**Migrate:** backfill existing rows in small batches keyed by primary key:

~~~sql
UPDATE appdb.orders
SET source_channel = 'legacy'
WHERE order_id > 0
  AND order_id <= 10000
  AND source_channel IS NULL;
~~~

Repeat across subsequent key ranges. Monitor per-batch duration, lock waits, redo/undo, CPU, I/O, and replication lag. If primary keys have large gaps or skewed distribution, use an adaptive keyset pagination strategy instead of assuming every range contains the same row count.

**Validate:** check remaining unbackfilled rows and out-of-set values:

~~~sql
SELECT COUNT(*) AS missing_source
FROM appdb.orders
WHERE source_channel IS NULL;

SELECT source_channel, COUNT(*) AS row_count
FROM appdb.orders
GROUP BY source_channel;
~~~

**Contract:** only after all application instances write the new column and data is verified should you decide to set `NOT NULL` or drop legacy structures. If the new column requires `NOT NULL`, define defaults and rules for historical data before applying the constraint.

Never run a migration changing nullability or dropping columns before confirming every active application version is compatible.

### 3.3. Inspecting Structure After Migration

Use `SHOW CREATE TABLE` to inspect actual definitions:

~~~sql
SHOW CREATE TABLE appdb.orders;
~~~

Compare attributes:

- Column names, ordering, data types, and nullability.
- Defaults, unsigned flags, generated expressions, and comments.
- Primary keys, unique keys, foreign keys, and indexes.
- Storage engine, charset, collation, and partitions.
- Views, triggers, procedures, functions, and events.
- User/role privileges used by the application.

You can query Information Schema for automated checks:

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Do not check column names alone. Changing `DECIMAL(12,2)` to `DECIMAL(10,2)`, for example, can prevent large values from being stored even though the migration succeeded syntactically.

### 3.4. Verifying Data Invariants

Invariants are business conditions that must always hold before and after migration. Examples:

- Every order has a unique order code.
- Payment totals are non-negative.
- Order statuses belong to the allowed value set.
- Every order item references an existing order.
- Total quantities and monetary sums remain unchanged after conversion.
- New column values map accurately from legacy columns.

Check for duplicate keys:

~~~sql
SELECT order_code, COUNT(*) AS duplicate_count
FROM appdb.orders
GROUP BY order_code
HAVING COUNT(*) > 1;
~~~

Check for orphan records:

~~~sql
SELECT COUNT(*) AS orphan_items
FROM appdb.order_items i
LEFT JOIN appdb.orders o ON o.order_id = i.order_id
WHERE o.order_id IS NULL;
~~~

Check aggregate totals:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM appdb.orders;
~~~

Compare results before and after migration on the same dataset. If the migration intentionally transforms values, write explicit reconciliation rules instead of asserting equal sums.

### 3.5. Testing Compatibility Between Old and New Application Versions

During rolling deployments, multiple application versions run concurrently for a period. Test the matrix:

| Schema | Old application | New application |
|---|---|---|
| Pre-expand schema | Must work | Not deployed yet if requiring new column |
| Post-expand schema | Continues working | Can run if code supports new column |
| Post-migrate schema | Must stay compatible before contract | Reads/writes using new structure |
| Post-contract schema | No longer supported | Must work |

Test writers, readers, workers, batch jobs, reports, CDC consumers, and operational scripts. A working new API does not prove an old worker isn't still referencing a dropped column.

### 3.6. Testing DDL and Performance

Run migrations on a clone sized close to production. Measure:

- Metadata lock wait time and DDL execution duration.
- CPU, IOPS, temporary space, redo/undo, and binary log volume.
- Replication lag during DDL and backfills.
- Read/write query availability during migration.
- Execution plans of key queries before and after.

Use `EXPLAIN` or `EXPLAIN ANALYZE` to verify queries still use expected indexes with proper cardinality. `EXPLAIN ANALYZE` executes the query, so run it only with safe queries in an appropriate environment.

If DDL must not silently fall back to table copy, specify the algorithm supported by your version so the migration fails explicitly if requirements aren't met. Never assume every operation supports `ALGORITHM=INSTANT` or `LOCK=NONE`; check documentation and test on the exact version, engine, and table definition.

## 4. Testing Backup and Restore

### 4.1. Defining Targets and Scope

Before running backup tests, document:

- RPO: maximum acceptable data loss.
- RTO: maximum time to restore service operation.
- Scope: whole instance, schema, table, or business dataset.
- MySQL version and backup/restore tooling.
- Required keyring, certificates, plugins, users/roles, and config files.
- Storage locations for backups and binary log archives.
- Retention policies and access permissions.

A backup job exiting with code 0 only proves the tool finished from its own perspective. You must verify files, manifests, checksums, and perform an actual restore.

### 4.2. Backup Test Scenario

A complete backup test:

1. Create fixtures with required InnoDB tables, views, triggers, routines, and events.
2. Record timestamp, GTID set, or binary log coordinates.
3. Execute a full backup with the chosen tool.
4. Check exit code, logs, manifest, checksums, and file sizes.
5. Copy the backup to independent storage.
6. Confirm files can be read/decrypted with the proper keys.
7. Verify binary logs from the backup point are archived continuously.
8. Store server and tool version metadata alongside the backup.

Example logical dump with MySQL:

~~~bash
mysqldump --login-path=backup \
  --single-transaction --quick \
  --source-data=2 \
  --routines --events --triggers --hex-blob \
  --databases appdb \
  > appdb-backup.sql
~~~

`--single-transaction` provides a consistent snapshot for InnoDB tables. Concurrent DDL on tables being dumped can break snapshot consistency or cause errors; freeze schema changes during the backup window. For non-transactional tables, use appropriate locking or backup methods.

For large datasets, test MySQL Shell dump/load or compatible physical backups. Never extrapolate restore duration from dump speed; loading, index building, and preparing backups have different resource profiles.

### 4.3. Restoring on an Isolated Server

Provision a recovery instance with:

- A MySQL version compatible with the backup format.
- Sufficient space for data, temporary tablespaces, and binary logs.
- Required keyrings, plugins, and certificates.
- An isolated endpoint incapable of receiving production traffic.
- A dedicated restore account.
- Isolated networking and DNS so applications cannot connect accidentally.

General restore runbook:

1. Provision the recovery server.
2. Install the required MySQL version and tools.
3. Restore configuration, plugins, and required keys.
4. Restore the full backup.
5. For physical backups, run prepare/apply-log per tool documentation.
6. Start MySQL and inspect the error log and tablespaces.
7. Verify schemas, objects, and required users.
8. Run data reconciliation and application smoke tests.
9. Record timing and outcomes for each step.

With logical dumps, an SQL file may partially load before failing. Never re-run the file on a half-loaded database without verifying idempotency and statement states. Rebuild a clean target schema and restore again.

### 4.4. Testing Point-in-Time Recovery

PITR combines a full backup with binary logs from the backup checkpoint up to the target recovery point.

A test scenario can follow these steps:

1. Take a full backup.
2. Record the snapshot's GTID set or binlog file/position.
3. Execute a test transaction with a unique marker, e.g., inserting `TEST-BEFORE`.
4. Record the recovery coordinate or timestamp right after this transaction.
5. Execute a subsequent transaction `TEST-AFTER`.
6. Perform a controlled destructive action in the test environment, such as dropping a fixture table.
7. Restore the full backup onto an isolated server.
8. Replay binary logs up to the mark recorded in step 4, stopping before `TEST-AFTER` and the destructive action.
9. Verify `TEST-BEFORE` exists, `TEST-AFTER` does not exist, and the fixture table is recovered.

Use `mysqlbinlog` to inspect and bound logs by position or timestamp:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 14:34:59" \
  /backup/mysql-bin.000123 \
  /backup/mysql-bin.000124 \
  > /restore/replay.sql
~~~

These values are placeholders only. In real tests, use the actual positions, timestamps, time zone, and binary log file list from your backup. To stop accurately right before a specific transaction, prefer identifying exact event/transaction boundaries and inspecting the output; timestamps alone may lack precision when transactions occur close together.

Inspect the replay file contents before applying it. Never replay unverified binary logs onto production. DDL triggers implicit commits and cannot be undone via standard `ROLLBACK`.

### 4.5. Restore Test Acceptance Criteria

- MySQL starts cleanly and opens all tablespaces.
- Required schemas, tables, and objects match expected counts.
- Checksums or data reconciliation checks pass.
- Users, roles, grants, and TLS connections work.
- Critical business queries execute cleanly.
- PITR stops at the exact mark; pre-mark and post-mark data are cleanly separated.
- Measured RTO and RPO meet targets.
- Logs, manifests, versions, and restore results are archived.

## 5. Testing Replication

### 5.1. Checking Baseline Configuration

For GTID-based replication, verify compatible settings on source and replica. The source requires binary logging; `server_id` must be unique across the topology. Use row-based binary logging when required by architecture and tooling.

On the source:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_bin';
SHOW GLOBAL VARIABLES LIKE 'gtid_mode';
SHOW GLOBAL VARIABLES LIKE 'enforce_gtid_consistency';
SHOW GLOBAL VARIABLES LIKE 'binlog_format';
SHOW BINARY LOG STATUS;
~~~

On the replica:

~~~sql
SHOW REPLICA STATUS\G
~~~

Inspect receiver/applier threads, latest errors, received and executed GTIDs, relay/source log positions, and replication lag. Do not look only at `Seconds_Behind_Source`; it can be `NULL` or fail to reflect true lag in certain states.

### 5.2. Testing Transaction Flow from Source to Replica

A simple test:

1. Write a record with a unique ID on the source and commit.
2. Read `@@GLOBAL.gtid_executed` after commit to capture the GTID set to wait for.
3. On the replica, wait until that GTID set is executed.
4. Read the record on the replica and compare with the source.

On the source:

~~~sql
INSERT INTO appdb.replication_probe(probe_id, payload)
VALUES ('replica-test-001', 'committed-on-source');

SELECT @@GLOBAL.gtid_executed;
~~~

On the replica, pass the captured GTID set:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('SOURCE_GTID_SET', 60);
~~~

A result of `0` means the GTID set executed within the timeout; `1` means timeout. Then verify data:

~~~sql
SELECT probe_id, payload
FROM appdb.replication_probe
WHERE probe_id = 'replica-test-001';
~~~

Use a dedicated probe table or controlled fixtures. Never let test records pollute business data.

### 5.3. Testing Lag and Catch-Up Capacity

Generate controlled write load on the source and measure:

- Commit timestamp on the source.
- GTID execution timestamp on the replica.
- `Seconds_Behind_Source` and receiver/applier status.
- Transaction receive/apply rates.
- CPU, I/O, relay log, and binary log volume.
- Time required for the replica to catch up once workload slows or stops.

Never intentionally overload a live production system beyond capacity. Use staging or a resource-matched clone. Lag tests need acceptance thresholds, such as requiring the replica to catch up within a defined window after write load stops.

### 5.4. Testing Replication Failures

In staging, rehearse scenarios:

- Network disconnect between replica and source.
- Receiver stops while applier still drains existing relay logs.
- Applier hits an error from incompatible schema or data.
- Required binary logs are purged before the replica reads them.
- Replica restarts and resumes from persisted metadata.
- DDL is applied while consumers read the new schema.
- Transactions touch multiple schemas in filtered topologies.

For each failure, confirm alerts fire, runbooks pinpoint the error location, and the replica recovers cleanly. Never blindly skip transactions or use skip counters just to flip status back to Running; doing so hides missing data.

### 5.5. Verifying Data Consistency

Compare table/chunk checksums or statistics at a synchronized point. You can verify row counts, monetary totals, min/max values, duplicate keys, and foreign key integrity. If the source keeps writing during comparison, counts may differ due to read skew; synchronize on a shared GTID set or pause writes during the check window.

Test application replica-read behavior separately:

- Does read-after-write route back to the primary?
- Does the application tolerate eventual consistency?
- When replica lag exceeds thresholds, does the router redirect reads to the primary or reject queries?
- Can a transaction read data just written on a different replica?

Replication status showing Running does not mean a replica is always safe for read-after-write.

## 6. Testing Switchover and Failover

### 6.1. Distinguishing Switchover from Failover

**Switchover** is a planned primary transition while the source is healthy, allowing writes to pause, replicas to catch up, and roles to swap cleanly.

**Failover** is a role transition when the primary fails or becomes unreachable. You may not be able to retrieve the final position from the old primary; with asynchronous replication, some committed transactions may not have reached the promoted replica.

Both require testing fencing, data integrity, application reconnection, and recovery of the old node. Failover tests must verify split-brain prevention: never allowing two nodes to accept independent writes.

### 6.2. Controlled Switchover

A general runbook for primary/replica topologies:

1. Enable maintenance mode or block new writes.
2. Drain requests and wait for open transactions to finish.
3. Fence the old primary with `super_read_only` and infrastructure blocks preventing app writes.
4. Record the primary's final GTID set.
5. Wait for the replica to execute that full GTID set.
6. Confirm receiver/applier have no errors and expected data is present.
7. Stop the replication channel on the replica chosen as the new primary.
8. Enable writes on the new node per the runbook.
9. Switch Router/proxy/DNS/endpoints and verify new connections.
10. Re-open traffic gradually, verify reads/writes, and monitor errors.
11. Keep the old node fenced; rejoin it to the topology only after proper resynchronization.

Example fencing and GTID wait commands:

~~~sql
-- On the old primary after stopping all writers
SET GLOBAL super_read_only = ON;

SELECT @@GLOBAL.gtid_executed;
~~~

On the selected replica:

~~~sql
SELECT WAIT_FOR_EXECUTED_GTID_SET('FINAL_SOURCE_GTID_SET', 120);
~~~

Proceed only after the replica executes the entire final GTID set and all other checks pass. Enabling writes on the new node must follow your organization's topology and management procedures. On standalone MySQL replication, disable `super_read_only` and `read_only` in proper order after promotion. When using InnoDB Cluster/Group Replication, use that topology's management commands instead of manipulating it manually like an independent replica.

### 6.3. Unplanned Failover

Simulate primary disconnect or isolation in staging:

- Confirm monitoring/orchestration detects primary unavailability.
- Fence or verify the old primary cannot accept writes.
- Select an eligible replica based on received/executed GTIDs and data state.
- Identify transactions potentially lost due to asynchronous replication.
- Promote the replica per runbook.
- Switch endpoints and verify applications open fresh connections.
- Test new writes, reads, and transaction state.
- Record the last preserved GTID and any missing data window.
- When the old primary returns, keep it read-only and resync per procedure; never automatically let it accept writes.

Never promote a replica solely because it is Running. Evaluate data currency and transaction-loss risk. Under asynchronous replication, commits on the primary are not guaranteed to reach replicas before failure. Semisynchronous replication narrows the data-loss window yet should not be assumed to guarantee zero data loss in every case; verify timeout/fallback modes and actual acknowledgment states.

### 6.4. Checking Clients and Connection Pools After Failover

Database promotion may succeed while the application continues failing if connection pools hold sockets to the old node or DNS caches stay stale.

Test:

- Does the JDBC driver reconnect when physical connections drop?
- Does HikariCP evict broken connections and open fresh ones?
- Does MySQL Router/proxy route to the new primary?
- Do DNS TTLs and connection strings cause clients to keep hitting the old node?
- Are mid-flight interrupted transactions surfaced clearly as errors?
- Are retries idempotent and able to resolve ambiguous commit outcomes?
- Do workers, schedulers, batch jobs, and consumers reconnect to the right node?

Never blindly retry a write transaction after a network error. The client may lose connectivity after server commit but before receiving the response. Use idempotency keys, business transaction IDs, or state lookup queries before retrying.

## 7. Measuring RPO and RTO

### 7.1. RPO

RPO is the maximum tolerable data loss window. During failover, determine:

- The last GTID committed on the old primary, if obtainable.
- The last GTID executed on the promoted replica.
- Which transactions had been acknowledged to clients.
- Which transactions existed only on the old primary and never reached the replica.
- Which transactions were lost or need reconciliation post-switchover.

Never use `Seconds_Behind_Source` as the sole RPO measure. Comparing GTIDs and data at the test checkpoint reveals the true set of transactions present on the replica.

### 7.2. RTO

RTO is the elapsed time from service unavailability until the application operates normally again. Record milestones:

| Milestone | Description |
|---|---|
| `T0` | Primary or database unavailability detected |
| `T1` | Switchover/failover decided and fencing started |
| `T2` | New node selected and promoted |
| `T3` | Router/proxy/endpoint switched to new node |
| `T4` | Application opens new connections and smoke tests pass |
| `T5` | Traffic restored and error rates return to normal thresholds |

Actual RTO spans from `T0` to the moment the service meets the organization's operational recovery criteria. Do not stop the clock when the MySQL process starts or when the replica promotes.

### 7.3. Example Result Recording

| Metric | Example target | Drill result |
|---|---|---|
| RPO | ≤ 30 seconds | Record actual measurement |
| RTO | ≤ 5 minutes | Record actual measurement |
| Replica catch-up after test load | ≤ 2 minutes | Record actual measurement |
| Full backup restore | ≤ 45 minutes | Record actual measurement |
| PITR right before faulty transaction | Exact boundary | PASS/FAIL and GTID/position |

These numbers are examples illustrating target definitions. Choose targets based on business requirements, SLAs, and real architecture.

## 8. Integrating Tests into CI/CD

### 8.1. Pipeline Layers

A sensible pipeline includes:

1. **Static validation:** check migration files, naming, versions, checksums, and secrets.
2. **Unit tests:** test database-independent transformation and validation logic.
3. **MySQL integration tests:** run migrations on exact MySQL version, seed fixtures, and verify schema.
4. **Compatibility tests:** run old/new apps against expand/migrate schemas per support matrix.
5. **Performance tests:** run DDL/backfills and critical queries on representative datasets.
6. **Backup/restore drills:** run periodically or before major releases in an isolated environment.
7. **Replication/failover exercises:** run on schedule in staging or drill environments.
8. **Release gate:** allow deployment only when mandatory criteria pass with evidence.

Full restores and failovers do not need to run on every commit. Unit/integration tests run continuously; restore drills, performance tests, and failover exercises run on schedules, before infrastructure changes, or ahead of risky releases.

### 8.2. Release-Blocking Gates

Conditions suitable as release gates:

- Migration fails to upgrade from any still-supported schema version.
- Migration checksum mismatch or inconsistent history.
- Data invariants fail.
- DDL exceeds lock-time limits or drives replication lag over thresholds.
- Backups lack successful restore proof within policy windows.
- Binary log archives miss segments needed for RPO.
- Replica reports IO/SQL errors or fails to catch up within targets.
- Failover fails to fence old primary or clients fail to reconnect.
- Measured RPO/RTO exceeds targets.

Each gate needs an owner, evidence logs, and a remediation workflow on failure. Never mark PASS simply because a job exited 0 without verifying postconditions.

## 9. Common Testing Incidents

| Symptom | Possible cause | Resolution path |
|---|---|---|
| Migration passes in CI but fails in staging | Version, collation, SQL mode, data, or privilege differences | Align test config and add representative fixtures |
| Migration succeeds yet data is wrong | Incomplete backfill, bad mapping, or wrong `NULL` handling | Verify invariants, batch ranges, and data reconciliation |
| DDL spikes replica lag | Table rebuild, index build, or oversized batches | Measure DDL on a clone, tune batch sizes and maintenance windows |
| Backup files exist yet MySQL fails to start | Missing files, keyring, plugins, or improper prepare step | Check manifests, error logs, and tool documentation |
| PITR overshoots faulty transaction | Timestamp stop point lacks precision | Identify exact event/transaction boundaries and inspect replay SQL |
| Replica Running yet data diverges | Replication filters, missing transactions, or unsynchronized check time | Compare GTIDs, filters, and checksums at an identical checkpoint |
| Failover produces two primaries | Old node not fenced or inconsistent endpoint routing | Halt writes, isolate node, pick authoritative source, rebuild topology |
| App fails to connect after promotion | Pool holds stale sockets or DNS/proxy caches lag | Inspect routes, connection pools, DNS, and reconnect behavior |
| Retries create duplicate transactions | Missing idempotency or ambiguous commit outcomes | Use idempotency keys and verify state before retrying |
| RTO exceeds target | Slow restore, promotion, DNS propagation, or manual checks | Time each step, automate runbooks, and drill again |

Never massage test results by skipping replication errors or relaxing data checks. Preserve error state to pinpoint root causes.

## 10. Runbooks and Test Evidence

Every drill should archive an evidence bundle:

- Objectives, scope, owner, and execution timestamps.
- Versions of MySQL, backup tools, drivers, migration tools, and application.
- Seed/fixture versions and input datasets.
- GTID sets, binlog files/positions, and PITR boundaries.
- Migration history, checksums, and actual executed DDL.
- Backup manifests, checksums, and restore logs.
- Pre/post `SHOW REPLICA STATUS` and reconciliation outputs.
- `T0`–`T5` milestones, RPO/RTO, and encountered errors.
- PASS/FAIL verdict, open issues, and follow-up actions.

A concise report should answer: which tests ran, on which environment, with what data, which criteria passed/failed, exact measured numbers, and who signs off on residual risk.

## 11. Master Checklist

### Migration

- [ ] Tested from an empty database and every still-supported schema version.
- [ ] Tested boundary data, `NULL`s, Unicode, duplicates, and large datasets.
- [ ] Verified schema, indexes, constraints, and dependencies after DDL.
- [ ] Reconciled invariants before and after backfill.
- [ ] Tested compatibility of old and new application versions.
- [ ] Measured metadata locks, DDL duration, I/O, and replication lag.
- [ ] Tested failure recovery when migration stops mid-flight.

### Backup/Restore

- [ ] Tested full/logical/physical backups per scope.
- [ ] Verified checksums, manifests, and binary log archives.
- [ ] Restored onto an isolated server.
- [ ] Verified PITR up to a marked transaction boundary.
- [ ] Verified users, roles, grants, keyrings, and TLS.
- [ ] Reconciled structure, data, and business logic.
- [ ] Measured actual RPO/RTO.

### Replication

- [ ] Verified GTID, binlog, `server_id`, and replication accounts.
- [ ] Tested transaction propagation from source to replica.
- [ ] Tested catch-up and measured lag under load.
- [ ] Tested network interruptions, restarts, and applier errors.
- [ ] Checked DDL/filters and cross-schema transactions.
- [ ] Verified checksums at an identical data checkpoint.
- [ ] Confirmed the application handles replica lag per requirements.

### Failover

- [ ] Tested planned switchover.
- [ ] Tested unplanned primary loss in staging.
- [ ] Fenced old primary before enabling writes on new node.
- [ ] Selected replica based on actual GTID/data state.
- [ ] Switched Router/proxy/DNS and verified client reconnection.
- [ ] Tested retries/idempotency and ambiguous commit outcomes.
- [ ] Resynchronized old node before rejoining topology.
- [ ] Measured RPO/RTO and archived evidence.

## 12. Self-Check

**Scenario 1:** A column-adding and backfill migration succeeds on an empty database, while production upgrades from a legacy schema holding historical data. Why is the current test insufficient?

**Hint:** An empty database lacks `NULL`s, boundary values, duplicates, skewed distributions, and scale. Test upgrades from supported versions using representative fixtures and verify invariants.

**Scenario 2:** A backup job returns exit code 0 and produces a large file. Can the backup be marked verified?

**Hint:** Not yet. Verify manifests/checksums, restore in an isolated environment, open tablespaces, verify data, privileges, and application behavior.

**Scenario 3:** A replica reports `Replica_IO_Running=Yes` but `Replica_SQL_Running=No`. Can this replica become the new primary?

**Hint:** No. The receiver fetches logs, yet the applier cannot execute them. Investigate SQL errors, GTIDs, and missing data before deciding to promote.

**Scenario 4:** The primary fails and the replica has an older GTID set. Can failover lose transactions?

**Hint:** Yes. Under asynchronous replication, some transactions committed on the primary may not have reached the replica yet. Determine actual RPO and reconcile potentially lost transactions.

**Scenario 5:** After promotion, the application still writes to the old primary because some connection pools have not reconnected. What is the risk?

**Hint:** Split-brain can occur with two nodes accepting writes simultaneously. Fence the old primary at both database and network layers, switch endpoints, evict stale connections, and open traffic only after confirming a single primary.

**Scenario 6:** An application loses connectivity right after sending `COMMIT`. Can it immediately retry the `INSERT`?

**Hint:** Never retry blindly because the server may have committed while the client missed the response. Use an idempotency key or query authoritative state before resending.

## 13. Key Takeaways

- Migration tests must cover an empty database, every supported schema version, boundary data, and large datasets.
- Real MySQL is required for integration tests covering DDL, transactions, constraints, locking, and optimizer behavior.
- DDL causes implicit commits; never assume migrations roll back atomically.
- Backups are only verified after restoring and checking data, privileges, and applications.
- PITR requires a full backup, an unbroken binary log chain, and an accurate stop boundary.
- Replication Running does not prove data matches; verify GTIDs, applier state, lag, and invariants.
- Switchover/failover must fence the old primary before enabling writes on the new primary to prevent split-brain.
- Asynchronous replication can lose transactions not yet received by replicas; measure RPO instead of assuming zero data loss.
- Applications must reconnect and retry safely after failover; ambiguous commit outcomes must be reconciled.
- Record RPO/RTO, logs, checksums, GTIDs, migration versions, and test outcomes so runbooks remain repeatable.

## References

- [MySQL 8.4 Reference Manual: Testing](https://dev.mysql.com/doc/refman/8.4/en/testing.html) — details on testing MySQL.
- [MySQL 8.4 Reference Manual: Replication](https://dev.mysql.com/doc/refman/8.4/en/replication.html) — configuring, monitoring, and troubleshooting replication.
- [MySQL 8.4 Reference Manual: GTID Auto-Positioning](https://dev.mysql.com/doc/refman/8.4/en/replication-gtids-auto-positioning.html) — synchronizing transactions with GTIDs.
- [MySQL 8.4 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.4/en/point-in-time-recovery.html) — recovering to a specific point using binary logs.
- [MySQL 8.4 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html) — logical backups and snapshots.
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — DDL algorithms and locking levels.
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/) — running real MySQL in integration tests.
- [Flyway Documentation: Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations) — managing versions and migration history.
- [Liquibase Documentation: Change Types](https://docs.liquibase.com/change-types/home.html) — modeling schema changes.
