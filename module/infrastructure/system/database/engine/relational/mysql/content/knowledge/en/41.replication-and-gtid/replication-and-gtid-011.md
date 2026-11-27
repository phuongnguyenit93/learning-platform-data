# Parallel applier, dependency tracking, and version-specific commit ordering

Parallel replication allows a replica to apply multiple transactions concurrently, reducing lag when write load on the source increases. To do this safely, MySQL needs to know which transactions are independent, how many applier workers to run, and whether commit order must match the source. Dependency tracking generates dependency metadata in the binary log; the logical clock uses that metadata to schedule transactions; commit-order preservation governs the order in which changes become visible on the replica.

This lesson belongs to the **Replication and GTID** chapter of the `DATABASE_MYSQL` module. On the path to mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, learners also practice reading execution plans, query tuning, privilege management, backups, and handling relational database operations issues. Parallel replication helps scale read capacity and keep replicas up to date; this section focuses on parallel appliers, dependency tracking, and variable/statement name changes across MySQL versions.

## 1. Parallel replication flow

In binary-log-based replication, the source writes transactions to the binlog. The replica runs a log-receiving stream and a log-applying stream:

- **Receiver thread** connects to the source and fetches binlog events.
- **Relay log** stores received events on the replica.
- **Coordinator thread** reads the relay log, analyzes dependencies, and dispatches transactions to workers.
- **Applier worker** executes transactions on the replica.

High-level model:

~~~text
Source
  |
  | Binary log + dependency metadata
  v
Replica receiver
  |
  v
Relay log
  |
  v
Coordinator
  |             |              |
  v             v              v
Worker 1      Worker 2       Worker 3
  |             |              |
  +-------------+--------------+
                |
                v
       Commit per
       preserve_commit_order policy
~~~

The coordinator cannot arbitrarily run every transaction simultaneously. If two transactions update the same row or share a dependency, the replica must preserve that relationship so the final data matches the source. Independent transactions can be applied concurrently.

A large worker count does not automatically make replication faster. Effectiveness depends on transaction independence, dependency metadata written by the source into the binlog, CPU, I/O, relay log capacity, and storage engine throughput.

## 2. Logical clock and dependency metadata

When using logical-clock scheduling, MySQL relies on metadata inside transaction events to determine which transactions can run in parallel. Two key fields are:

- **sequence_number:** the sequence number of the transaction in the binlog stream.
- **last_committed:** the sequence number of the most recent transaction identified as conflicting with the current transaction.

Transactions whose dependencies have been satisfied can be dispatched to workers to run concurrently. A transaction that depends on an earlier one must wait until its dependency completes according to applier rules.

This metadata does not alter the logical order established by the source. It helps the replica identify work that can run in parallel while preserving dependency relationships. Logical clock is the scheduling mechanism; accuracy and achievable parallelism depend on how the source computes dependencies.

## 3. Three dependency tracking modes on the source

Starting in MySQL 8.0.1, the `binlog_transaction_dependency_tracking` configuration variable lets the source record dependency metadata in the following modes.

### COMMIT_ORDER

COMMIT_ORDER examines the commit window of two transactions on the source. If the commit window of the earlier transaction overlaps with the subsequent transaction, MySQL can treat them as independent because they did not hold conflicting row locks simultaneously. Group commit information therefore creates opportunities for the replica to apply multiple transactions in parallel.

Its advantage is being relatively conservative and not requiring per-row key analysis. Its limitation is that parallelism can be low if the workload commits small individual transactions with little group commit overlap.

### WRITESET

WRITESET uses a transaction's write set to identify the row keys it modified. If two transactions write to disjoint rows and have no known dependency, the source can mark them independent even if they were not in the same group commit.

The write set is built from InnoDB row unique keys, including primary keys and eligible unique keys. Designing tables with stable PRIMARY KEY or UNIQUE KEY definitions improves conflict detection. When write sets are empty or partial, tables lack a primary/unique key, or operations affect parent tables in foreign key relationships, the source can fall back to COMMIT_ORDER calculation to preserve dependencies.

### WRITESET_SESSION

WRITESET_SESSION combines write-set conflict detection with preserving transaction ordering within the same source session. This mechanism is useful when an application relies on sequential transactions in a single connection, such as a subsequent transaction reading results written by the preceding one.

### Comparison

| Mode | How dependencies are determined | Characteristics |
|---|---|---|
| COMMIT_ORDER | Based on commit order / group commit | Conservative, less dependent on key design |
| WRITESET | Compares transaction write sets | Can discover more independent transactions |
| WRITESET_SESSION | Write sets plus ordering within the same session | Additionally preserves per-session ordering |

WRITESET does not mean every transaction will run in parallel. If multiple transactions update the same key, they remain dependent. Data constraints, DDL operations, long transactions, and resource limits can also reduce parallelism.

## 4. Conditions for WRITESET to work effectively

Write-set dependency tracking is configured on the **source**, where transactions are written to the binary log. The example below uses variable names from MySQL 8.0.26–8.0.28; starting in 8.0.29, `replica_parallel_type` is deprecated and `LOGICAL_CLOCK` is the default, so do not add that variable to new configurations:

~~~ini
[mysqld]
binlog_format=ROW
replica_parallel_type=LOGICAL_CLOCK
binlog_transaction_dependency_tracking=WRITESET
binlog_transaction_dependency_history_size=25000
~~~

- **binlog_transaction_dependency_tracking:** selects COMMIT_ORDER, WRITESET, or WRITESET_SESSION.
- **binlog_transaction_dependency_history_size:** limits the write-set history the source keeps for dependency comparisons. A larger history can detect conflicts across a wider transaction window at the cost of extra memory.

In MySQL 8.0, `transaction_write_set_extraction` defaults to XXHASH64; this value suffices for WRITESET to operate and must not be set to OFF. `transaction_write_set_extraction` was deprecated in MySQL 8.0.26 and removed in MySQL 8.3.0, so omit it from new configurations. In MySQL 8.4, write-set extraction is managed internally.

Variables and default values may differ by version. Check the documentation for your exact MySQL release and runtime values before making changes:

~~~sql
SHOW VARIABLES LIKE 'binlog_transaction_dependency_tracking';
SHOW VARIABLES LIKE 'transaction_write_set_extraction';
SHOW VARIABLES LIKE 'binlog_transaction_dependency_history_size';
~~~

The dependency variable inspection queries above apply to versions that still expose those variables. MySQL 8.3 and later no longer have `transaction_write_set_extraction`; MySQL 8.4 and later also no longer have `binlog_transaction_dependency_tracking`.

If WRITESET is used without good key metadata, parallel gains will be limited. Audit schemas, especially primary keys and unique keys on write-heavy tables. Never add a unique key solely to boost parallelism if it does not reflect the application's actual data rules.

Row-based binary logging is the standard choice for modern replication and clearly captures row changes. Check `binlog_format` on the source; if running STATEMENT or MIXED, consult version-specific documentation to verify whether dependency tracking uses write sets as expected.

Starting in MySQL 8.3.0, write sets are used for conflict checking only when `binlog_format=ROW`; MIXED is no longer supported for write-set dependency checking. Ensuring ROW format is therefore a key check when relying on WRITESET on newer releases.

MySQL 8.4 removed `binlog_transaction_dependency_tracking`. When a source has replicas running a parallel applier, MySQL 8.4 automatically uses write sets to generate dependency metadata, matching WRITESET behavior in earlier versions.

## 5. Configuring the parallel applier on the replica

On the replica, newer variable names use the `replica` prefix starting in MySQL 8.0.26. The example below shows explicit settings for MySQL 8.0.26–8.0.28; starting in 8.0.29, `replica_parallel_type` is deprecated and `LOGICAL_CLOCK` is the default:

~~~ini
[mysqld]
replica_parallel_workers=8
replica_parallel_type=LOGICAL_CLOCK
replica_preserve_commit_order=ON
~~~

- **replica_parallel_workers:** number of applier workers. A value of 0 disables the multi-threaded applier and uses a single sequential thread; starting in MySQL 8.0.30, setting 0 is deprecated—use 1 when sequential apply is needed. Values greater than 1 allow independent transactions to be processed concurrently.
- **replica_parallel_type=LOGICAL_CLOCK:** uses dependency metadata in the binlog to schedule transactions.
- **replica_preserve_commit_order=ON:** preserves commit order on the replica matching the source's commit order while still letting workers execute in parallel.

An older scheduling option is **DATABASE**. This mode can apply transactions belonging to different databases concurrently, but it is suitable only when databases are updated independently with no cross-database constraints. `LOGICAL_CLOCK` relies on dependency metadata and fits workloads needing parallel apply within the same database. Starting in MySQL 8.0.29, `replica_parallel_type` and `DATABASE` scheduling are deprecated; `LOGICAL_CLOCK` is the retained path.

Choose the worker count based on CPU, I/O, transaction size, and actual parallelism. Start with a moderate worker count, measure lag and resource usage, then tune. Setting workers too high can increase context switching, lock contention, I/O pressure, and memory usage without improving apply speed.

Different versions have different default values for worker count and parallel applier type. Do not rely on defaults from another version or an old blog post; inspect the running values:

~~~sql
SHOW VARIABLES LIKE 'replica_parallel_workers';
SHOW VARIABLES LIKE 'replica_parallel_type';
SHOW VARIABLES LIKE 'replica_preserve_commit_order';
~~~

Variable names in configuration must match the server version. On older MySQL releases, the corresponding variables use the `slave` prefix, such as `slave_parallel_workers`, `slave_parallel_type`, and `slave_preserve_commit_order`.

## 6. Preserving commit order with replica_preserve_commit_order

Workers can start and execute transactions on a parallel schedule. However, if a later transaction commits before an earlier one, a read query on the replica could observe an intermediate state that differs from the source's commit order.

When `replica_preserve_commit_order=ON`, MySQL coordinates commits so transactions take effect in the exact commit order of the source. Transactions still execute concurrently; a worker that finishes early may have to wait for its turn to commit. Therefore, commit-order preservation improves observable consistency at the possible cost of lower throughput when an earlier transaction runs long.

This setting is appropriate when applications read from the replica and must observe change order matching the source, or when the replica acts as a source for a downstream replica. In exchange, you must accept potential worker commit-wait delays and lower effective parallelism.

To use commit-order preservation, configure the applier with `LOGICAL_CLOCK`. If turning off commit-order preservation, carefully evaluate replica read behavior and downstream topology impact; do not treat disabling it as an unconditional performance optimization.

## 7. Syntax differences across MySQL versions

MySQL renamed several identifiers from `slave`/`master` to `replica`/`source`. New names were introduced incrementally across releases, so operational scripts must match the server and client versions.

| Version | Commands/variables to note |
|---|---|
| MySQL 5.7 | Uses `slave_parallel_workers`, `slave_parallel_type`, and `slave_preserve_commit_order`. Does not have MySQL 8.0-style write-set dependency tracking. |
| MySQL 8.0.1 and later | Provides `binlog_transaction_dependency_tracking` with `COMMIT_ORDER`, `WRITESET`, and `WRITESET_SESSION` up until MySQL 8.4. |
| MySQL 8.0.22 and later | Introduces new replica command names such as `SHOW REPLICA STATUS`, `START REPLICA`, and `STOP REPLICA`; legacy names remain compatible during transition depending on version. |
| MySQL 8.0.23 and later | Uses `CHANGE REPLICATION SOURCE TO` instead of `CHANGE MASTER TO` in new syntax. |
| MySQL 8.0.26 and later | Applier variables use the `replica` prefix instead of `slave`, e.g., `replica_parallel_workers`. |
| MySQL 8.0.27 and later | Defaults to `replica_parallel_workers=4`, `replica_parallel_type=LOGICAL_CLOCK`, and `replica_preserve_commit_order=ON`. Before 8.0.27, defaults were `0`, `DATABASE`, and `OFF` respectively. |
| MySQL 8.0.29 and later | `replica_parallel_type` is deprecated; do not choose `DATABASE` for new configurations. |
| MySQL 8.0.30 and later | Setting `replica_parallel_workers=0` is deprecated; use `1` for single-worker sequential apply. |
| MySQL 8.0.35 / 8.2 | `binlog_transaction_dependency_tracking` is deprecated. |
| MySQL 8.3 and later | `transaction_write_set_extraction` is removed; write sets are used for conflict checking only when `binlog_format=ROW`. |
| MySQL 8.4 and later | `binlog_transaction_dependency_tracking` is removed; source automatically uses WRITESET when replicas run a parallel applier. |

Example checking status with the new syntax:

~~~sql
SHOW REPLICA STATUS\G
~~~

On older versions, use `SHOW SLAVE STATUS\G`. Similarly, newer control statements use `START REPLICA` and `STOP REPLICA`; older versions use `START SLAVE` and `STOP SLAVE`.

Never mechanically swap variable names in configuration files without checking the server version. In multi-version environments, maintain version-grouped configs or use automation that detects the version and selects matching syntax.

## 8. GTID and parallel apply solve two different problems

GTID identifies transactions; dependency tracking identifies execution relationships between transactions. The two mechanisms complement each other but do not replace each other.

- **GTID:** tracks which transactions have executed, supporting replication auto-positioning and comparing transaction sets.
- **Dependency metadata:** indicates which transactions can be applied in parallel.
- **Parallel applier:** uses metadata to dispatch transactions to workers.
- **Commit-order preservation:** coordinates commit timing on the replica to match source order.

In MySQL 8.0.23 and later, configuring a source with GTID auto-position looks like:

~~~sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'db-source.example.internal',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl_user',
  SOURCE_PASSWORD = 'replace-with-secret',
  SOURCE_AUTO_POSITION = 1;
~~~

This is a syntax example; credentials must be managed securely and real passwords never stored in documentation or shell history. GTID mode must be enabled and configured consistently across participating servers. On older versions, the corresponding syntax is `CHANGE MASTER TO` with `MASTER_AUTO_POSITION=1`.

Baseline settings commonly used on both source and replica:

~~~ini
[mysqld]
gtid_mode=ON
enforce_gtid_consistency=ON
~~~

On a running topology, enabling GTID must follow an appropriate transition path, verifying that all transactions and applications are compatible. Do not turn both variables on directly on a live server and assume the entire topology is ready.

Checking GTID status:

~~~sql
SELECT @@GLOBAL.gtid_mode;
SELECT @@GLOBAL.gtid_executed;
SELECT @@GLOBAL.gtid_purged;
~~~

GTID helps a replica identify missing transactions, but it does not decide which transactions are independent. To increase parallelism, the source still needs to write proper dependency metadata and the replica needs a logical-clock applier configured.

## 9. Inspecting worker activity

On the replica, view replication status:

~~~sql
SHOW REPLICA STATUS\G
~~~

Fields to observe depending on version include receiver/applier state, SQL errors, relay log files, retrieved and executed GTIDs, and `Seconds_Behind_Source`. The lag field is a useful indicator but should not be used alone to conclude a replica is healthy or caught up; cross-check workers, relay logs, errors, and log growth rate.

Performance Schema provides per-worker details:

~~~sql
SELECT
  CHANNEL_NAME,
  WORKER_ID,
  THREAD_ID,
  SERVICE_STATE,
  LAST_APPLIED_TRANSACTION
FROM performance_schema.replication_applier_status_by_worker
ORDER BY CHANNEL_NAME, WORKER_ID;
~~~

Check the coordinator:

~~~sql
SELECT
  CHANNEL_NAME,
  THREAD_ID,
  SERVICE_STATE,
  LAST_ERROR_NUMBER,
  LAST_ERROR_MESSAGE
FROM performance_schema.replication_applier_status_by_coordinator;
~~~

Column names may vary across versions. Use `DESCRIBE performance_schema.replication_applier_status_by_worker` if you need to verify the schema on your running server.

Signals to watch for:

- Multiple workers simultaneously holding active transactions indicates parallel execution, though it does not by itself prove good throughput.
- Workers frequently waiting to commit can result from commit-order preservation or a slow preceding transaction.
- Relay logs growing continuously while the source is steady indicates the replica is not keeping up with transaction generation.
- A single worker hitting an error can cause the coordinator to halt apply progress and create lag across the entire channel.
- High CPU with low throughput can stem from lock contention, large transactions, or strongly dependent workloads.

## 10. Experimenting with dependencies and commit ordering

You can test in a lab environment using two groups of transactions:

**Group A – independent:** two transactions updating two rows with different primary keys and touching no shared business resource. With WRITESET, the source can recognize non-conflicting write sets and allow the replica to run them in parallel.

**Group B – conflicting:** two transactions updating the same row or the same unique key. Dependency tracking must preserve the required relationship; the replica must not apply them in a way that corrupts the outcome.

Experiment procedure:

1. Use one test source and one test replica with compatible configurations.
2. Create an InnoDB table with a PRIMARY KEY and sample data.
3. Enable GTID, binary logging, and dependency tracking on the source according to your version.
4. Configure the replica with multiple workers, LOGICAL_CLOCK, and preserve commit order.
5. Generate a workload containing both independent and conflicting transactions.
6. Observe workers, relay logs, GTID status, and lag.
7. Compare final results on source and replica; check commit ordering when reading related changes.
8. Repeat with COMMIT_ORDER to compare parallelism and resource utilization.

Do not benchmark using a single run. Repeat the workload with sufficient data and duration, keep hardware conditions equivalent, and monitor both throughput and lag.

## 11. Common errors and remediation

| Symptom | Possible cause | What to inspect |
|---|---|---|
| Increasing workers does not reduce lag | High transaction dependency, or I/O or CPU bottleneck | Inspect workers, transaction duration, and system resources |
| WRITESET does not increase parallelism | Tables lack suitable keys, workload writes to same keys, or short dependency history | Check PRIMARY KEY/UNIQUE KEY and writeset configuration |
| Workers wait long before committing | Earlier transaction has not finished or preserve commit order enforces waiting | Check worker status and slow transactions |
| Replica stops applying | SQL error, data drift, or incompatible event | Read coordinator/worker errors and compare against source |
| `replica_*` variables unrecognized | Older server version uses `slave_*` | Check version and use matching variable names |
| `SHOW REPLICA STATUS` fails | Older server only supports `SHOW SLAVE STATUS` | Use version-compatible syntax |
| GTID reports transaction already exists or missing | Baseline GTID state and log chain do not match | Compare GTID sets, backup metadata, and logs; do not skip transactions blindly |

When investigating errors, preserve relay logs and related logs before purging or resetting. Never run `RESET REPLICA` or delete relay logs to hide an error before understanding GTID state and applied data.

## 12. Operational principles

- Configure dependency tracking on the source and the parallel applier on the replica; do not confuse the two roles.
- Use LOGICAL_CLOCK when you want the replica to leverage dependency metadata in the binlog.
- Choose COMMIT_ORDER when conservative scheduling is needed; consider WRITESET or WRITESET_SESSION when workload and schema permit.
- Maintain appropriate PRIMARY KEY or UNIQUE KEY constraints on write-heavy tables so writeset conflict detection works well.
- Start with a moderate worker count and measure performance before increasing.
- Enable preserve commit order when observable commit order must match the source; evaluate commit-wait overhead.
- GTID handles transaction identification and positioning; dependency tracking describes parallel execution relationships.
- Use variable names and statements matching your MySQL version; check runtime values instead of assuming defaults.
- Monitor workers, coordinator, relay logs, errors, and lag together.

Parallel replication is safe only when dependencies are accurately described and the replica honors those relationships. By combining proper write-set tracking, logical clock scheduling, a sensible worker count, and a clear commit-order policy, a replica can accelerate apply speed while keeping data identical to the source.

## References

- [MySQL 8.0: Binary Logging Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-binary-log.html)
- [MySQL 8.0: Replica Server Options and Variables](https://dev.mysql.com/doc/refman/8.0/en/replication-options-replica.html)
- [MySQL 8.4: What Is New in MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/mysql-nutshell.html)
- [MySQL 8.4: Options and Variables Added, Deprecated, or Removed](https://dev.mysql.com/doc/refman/8.4/en/added-deprecated-removed.html)
- [MySQL 8.3 Release Notes: Restriction on writeset conflict checking for row-based logging](https://dev.mysql.com/doc/relnotes/mysql/8.4/en/news-8-3-0.html)
