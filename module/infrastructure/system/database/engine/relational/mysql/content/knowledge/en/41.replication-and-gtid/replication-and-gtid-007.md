# GTID auto-position and replica replacement conditions

In MySQL replication, a replica must know which transactions to fetch from the source to catch up on data. With traditional replication, the operator configures a binary log file name and byte position. When using **GTID auto-position**, during the connection handshake the replica sends a GTID set representing the transactions it has received, committed, or both; the source identifies the missing transactions and sends whatever portion it can provide. This makes switching sources or replacing a replica easier to manage because you do not have to recalculate file/position coordinates manually.

GTID auto-position does not fix corrupted data on its own, cannot recover transactions already purged from all available sources, and does not decide which replica is safe to promote. To replace a replica or switch the primary role, you must inspect transaction history, retained binary logs, data consistency, and split-brain risks.

This lesson uses the `SOURCE` and `REPLICA` terminology from MySQL 8.0.23 and later. On older versions, some statements still use `MASTER` and `SLAVE`, such as `CHANGE MASTER TO` and `SHOW SLAVE STATUS`.

## Learning objectives

After this lesson, you will be able to:

- Explain GTID, GTID sets, and the auto-position mechanism.
- Identify the prerequisites needed to enable GTID replication.
- Use `gtid_executed`, `gtid_purged`, `GTID_SUBSET()`, and `GTID_SUBTRACT()` to compare transaction history.
- Recognize scenarios where the source has purged transactions a replica needs or where a replica has errant transactions.
- Repoint a replica to a new source and evaluate safety conditions when replacing or promoting a replica.

## 1. GTID and GTID sets

A GTID (Global Transaction Identifier) is the identifier of a transaction written to the binary log. The common format is:

```text
source_uuid:transaction_id
```

Example:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:125
```

The UUID portion identifies the server that generated the transaction; the sequence number identifies the transaction within that UUID's history. A single GTID identifies a single transaction. A **GTID set** is a collection of one or more GTIDs, typically represented by UUIDs alongside intervals of sequence numbers:

```text
3E11FA47-71CA-11E1-9E33-C80AA9429562:1-125,
24BC7850-2C16-11E8-A6A5-FA163E3D9B3B:1-48:52-60
```

The range `1-125` represents GTIDs 1 through 125 for the corresponding UUID. The second example has two intervals, where numbers 49 through 51 are absent from the set. A GTID set is not a list of byte offsets in a binlog and cannot be compared via simple string sorting.

### 1.1. Important GTID sets

| Variable | Meaning |
|---|---|
| `gtid_executed` | Set of GTIDs for transactions executed on the server, including history that may no longer reside in current binary logs |
| `gtid_purged` | Set of GTIDs for transactions that have been purged from the binary logs on the server |
| `Retrieved_Gtid_Set` | In replication status, the set of GTIDs the receiver has fetched from the source and stored in the relay log, awaiting or currently being processed by the applier |
| `Executed_Gtid_Set` | In replication status, the set of GTIDs executed by the server; this is also the history reflected by `gtid_executed` |

Checking GTID sets on a server:

```sql
SELECT
  @@GLOBAL.server_uuid,
  @@GLOBAL.gtid_mode,
  @@GLOBAL.enforce_gtid_consistency,
  @@GLOBAL.gtid_executed,
  @@GLOBAL.gtid_purged;
```

`gtid_executed` indicates which transactions the server has ever executed. `gtid_purged` identifies the portion of history already deleted from the server's binary logs. A transaction being present in `gtid_executed` does not mean the server still has the log files to transmit that transaction to a replica.

## 2. How does GTID auto-position work?

When a replica connects with `SOURCE_AUTO_POSITION=1`, the replica sends a GTID set representing the transactions it has received, committed, or both. The source compares this set against the transactions currently in its binary logs and sends the transactions not yet recorded by the replica. Thus, a transaction already received into the relay log but not yet committed is not resent as if the replica had never received it.

High-level flow:

```text
Replica connects to source
          |
          v
Sends received/committed GTID set
          |
          v
Source compares GTID sets
          |
          v
Identifies missing transactions
          |
          v
Sends transactions from binary log
          |
          v
Replica writes relay log
          |
          v
Applier executes transactions
          |
          v
Updates executed GTIDs
```

For example: the source has executed GTIDs `uuid-A:1-120`, while the replica has executed `uuid-A:1-100`. If the source still retains binary logs containing GTIDs 101-120, the source can send the missing portion. The replica does not need to know which file or byte offset transaction 101 starts at.

To use this mechanism, both source and replica must be configured for GTID replication. The source needs binary logging and must retain the binary logs containing transactions the replica lacks. The replica must be able to connect, have replication privileges, and hold a GTID set accurately reflecting the data history loaded onto it. In multi-source or diamond topologies, GTID auto-skip helps avoid applying the same transaction multiple times when it arrives at a replica via another path.

## 3. Prerequisites for configuring GTID replication

### 3.1. Enabling GTID mode and enforcing consistency

For a stable GTID topology, participating servers need:

- `gtid_mode=ON` so transactions are managed using GTIDs.
- `enforce_gtid_consistency=ON` so MySQL prevents operations incompatible with GTID consistency.
- Binary logging enabled on the source (`log_bin=ON`).
- Non-zero `server_id` unique across the topology.
- Unique `server_uuid` on each instance.

During migration phases, MySQL allows a replica to be at `gtid_mode=ON_PERMISSIVE` or `OFF_PERMISSIVE` while the source is at `gtid_mode=ON`. These are transitional states in the GTID upgrade/migration workflow; for a completed topology, set `gtid_mode=ON` across participating servers.

Verify configuration:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'gtid_mode',
  'enforce_gtid_consistency',
  'log_bin',
  'server_id',
  'server_uuid',
  'log_replica_updates'
);
```

Migrating a running system from GTID OFF to ON must follow the multi-stage transition procedure supported by MySQL. Do not arbitrarily change `gtid_mode` on a single node in a live topology. Before enabling GTID, audit the application and statements that might violate GTID consistency, then roll out synchronously according to plan.

`server_uuid` is typically stored in the `auto.cnf` file generated by MySQL. When creating a replica by copying a server's filesystem, ensure the new instance gets its own UUID; two servers sharing the same UUID render GTID history untrustworthy.

### 3.2. Binary log and log_replica_updates

The source must enable binary logging and retain logs long enough for replicas to fetch missing transactions. If an intermediate replica will serve downstream replicas, enable `log_replica_updates=ON` so transactions it receives from upstream are also written to its local binary log. Otherwise, the intermediate node may lack complete logs for downstream replicas to pull transactions via GTID auto-position.

`log_replica_updates` does not regenerate missing data and does not replace binary log retention. Check purge policy, disk capacity, binlog backups, and how long a replica might remain disconnected.

### 3.3. Connection privileges and protecting the replica

The replication account needs appropriate replication privileges on the source, must be host-restricted, and should use TLS per security policy. Example account creation on the source:

```sql
CREATE USER 'repl'@'10.20.0.12'
  IDENTIFIED BY '<password-from-secret-manager>'
  REQUIRE SSL;

GRANT REPLICATION SLAVE
  ON *.*
  TO 'repl'@'10.20.0.12';
```

The privilege name in the statement above is commonly used in MySQL 8.0; verify the exact privilege requirements and compatible names for your running version. Never place real passwords in scripts committed to source control.

On the replica, `read_only=ON` and `super_read_only=ON` are typically enabled to reduce the risk of accidental writes to the replica. The replication applier can still apply changes via MySQL's internal mechanisms. This protection must be combined with account privilege separation, monitoring, and operational change controls.

## 4. Configuring auto-position

Suppose the replica has been seeded with data from a consistent backup, has an appropriate GTID set, and needs to connect to source `db-source.example`:

```sql
STOP REPLICA;

CHANGE REPLICATION SOURCE TO
  SOURCE_HOST = 'db-source.example',
  SOURCE_PORT = 3306,
  SOURCE_USER = 'repl',
  SOURCE_PASSWORD = '<password-from-secret-manager>',
  SOURCE_AUTO_POSITION = 1;

START REPLICA;
```

`CHANGE REPLICATION SOURCE TO` with `SOURCE_AUTO_POSITION=1` can only be run when both the receiver thread and applier thread are stopped; `STOP REPLICA` at the top of the example stops both. When using auto-position, do not configure `SOURCE_LOG_FILE`, `SOURCE_LOG_POS`, `RELAY_LOG_FILE`, or `RELAY_LOG_POS` in the same connection configuration. MySQL automatically determines which transactions to fetch based on GTID sets. Perform endpoint and credential changes through your system's security process; the example above illustrates syntax only.

Check status:

```sql
SHOW REPLICA STATUS\G
```

Fields to inspect include:

- `Source_Host`: the source the replica is connected to.
- `Auto_Position`: confirms auto-position is enabled.
- `Replica_IO_Running` and `Replica_SQL_Running`: whether receiver and applier are running.
- `Last_IO_Error` and `Last_SQL_Error`: most recent errors on the two threads.
- `Retrieved_Gtid_Set`: GTIDs received into the relay log.
- `Executed_Gtid_Set`: GTIDs executed on the replica.

Field names may vary slightly across versions. Both threads running does not mean the replica has completely caught up; compare GTID sets, inspect errors, and measure actual lag.

## 5. Comparing GTID sets before replacing a replica

GTID sets help inspect transaction history, but the comparison must be framed accurately for the goal. There are two different questions:

1. **Can this replica attach to this source?** The source must contain every GTID the replica has executed, and must still hold binary logs for the GTIDs the replica lacks.
2. **Can this replica replace the old primary?** The candidate must contain every GTID committed on the old primary that the organization needs to preserve. This is the freshness condition prior to promotion.

### 5.1. Checking whether a replica has errant GTIDs

In a simple single-source topology, when preparing to attach a candidate to a source, the candidate's executed GTID set should be a subset of the source's executed GTID set. On the source, replace placeholders with the GTID sets read from the candidate and source:

```sql
SELECT GTID_SUBSET(
  '<candidate_gtid_executed>',
  '<source_gtid_executed>'
) AS candidate_history_is_known_by_source;
```

A result of `1` means every GTID on the candidate also exists in the source's executed history. A result of `0` indicates the candidate has at least one GTID that the source does not have. In a single-source topology, this is a sign requiring investigation because it may represent **errant transactions**: transactions written directly on the replica or originating from an incompatible history. In a multi-source/diamond topology, GTIDs coming from another source may be valid; compare against the history of the entire expected topology rather than concluding every GTID outside one source is errant.

To see the exact extra GTIDs:

```sql
SELECT GTID_SUBTRACT(
  '<candidate_gtid_executed>',
  '<source_gtid_executed>'
) AS errant_gtids;
```

An empty result is a necessary condition for the candidate's history to fit within a single source's history. If there are GTIDs outside this set, identify the transactions that produced them and cross-check against other sources in the topology. In particular, if a replica holds GTIDs belonging to the source's UUID that the source itself lacks, auto-position may stop with error `ER_REPLICA_HAS_MORE_GTIDS_THAN_SOURCE`. This situation can also indicate the tail of the source's binary log was lost or truncated after a crash; check error logs, crash recovery status, and binlog sync settings. Never arbitrarily delete GTIDs from `gtid_executed` or inject an empty transaction just to make the comparison look clean.

### 5.2. Checking that the source still retains transactions the candidate needs

Compute the set of transactions the source has executed that the candidate lacks:

```sql
SELECT GTID_SUBTRACT(
  '<source_gtid_executed>',
  '<candidate_gtid_executed>'
) AS transactions_candidate_needs;
```

If this set is non-empty, the candidate must fetch those GTIDs from the source. Next, check whether any needed GTIDs have already been purged from the source's binary logs:

```sql
SET @candidate_missing = GTID_SUBTRACT(
  '<source_gtid_executed>',
  '<candidate_gtid_executed>'
);

SELECT @candidate_missing AS transactions_candidate_needs,
       GTID_SUBTRACT(
         @candidate_missing,
         @@GLOBAL.gtid_purged
       ) AS needed_gtids_not_purged,
       GTID_SUBTRACT(
         @candidate_missing,
         GTID_SUBTRACT(@candidate_missing, @@GLOBAL.gtid_purged)
       ) AS needed_gtids_already_purged;
```

`needed_gtids_not_purged` is the portion of GTIDs the candidate needs that the source has not recorded as purged; `needed_gtids_already_purged` is the portion the candidate needs that is already in `gtid_purged`. If the needed set is non-empty and `needed_gtids_already_purged` is also non-empty, the source has purged at least one transaction the candidate requires. Auto-position cannot request the source to resend transactions already deleted from the binary logs the source still holds. Even if needed GTIDs are not marked purged, still verify the source actually has the corresponding binary logs—especially when the source is an intermediate replica and `log_replica_updates` was not enabled.

Another way to check is to inspect the intersection between the needed GTID set and `gtid_purged`. This result only reflects history on the inspected source; another source or binlog backup may still hold the required data.

### 5.3. Example of two replicas with different freshness levels

Suppose the old primary committed GTIDs `uuid-P:1-500`. Replica A has executed `uuid-P:1-500`, while replica B has only executed `uuid-P:1-470`.

- A can be a candidate to replace the old primary from a GTID standpoint because A has executed the entire `uuid-P:1-500` history.
- B is missing 30 transactions. B can catch up from the old primary only if the primary's binary logs still contain GTIDs 471-500, or from another source that holds all of those transactions.
- If the old primary already purged `uuid-P:471-500` and no other log/backup source exists, B cannot catch up automatically via auto-position alone.

This is a GTID history comparison. Before promoting A, you must still verify data, application state, unreplicated transactions, and that the old primary has been fenced to prevent two primaries from accepting writes.

## 6. Conditions for replacing a replica

Replacing a replica means provisioning or selecting a new server to assume the replica role for the current source. The goal is for the new server to share the same baseline data and be able to fetch the entire missing portion of transactions.

### 6.1. Baseline data must be consistent

The candidate should be created from a consistent backup, MySQL Clone Plugin, or a validated provisioning workflow. The GTID set accompanying the backup must accurately reflect the captured data state. Copying data files while a server is mutating without a consistency mechanism can leave a GTID set that does not represent the actual data.

When preparing a candidate, verify:

- MySQL version, storage engine, schema, and configuration are compatible with the source.
- Data is seeded from a consistent snapshot with a recorded checkpoint/GTID set.
- `server_id` and `server_uuid` are unique.
- GTID mode and consistency settings match the topology.
- Binary logging and `log_replica_updates` are enabled if the candidate will act as an intermediate source for other replicas.
- Sufficient disk space exists for relay logs, binary logs, temporary files, and normal operation.

### 6.2. The source must be able to supply missing transactions

After loading the backup, retrieve `gtid_executed` on both the candidate and the source. Use `GTID_SUBTRACT(source_set, candidate_set)` to determine what the candidate is missing. Verify those GTIDs have not been purged from the source's binary logs.

If the source has already purged required GTIDs, there are three options:

1. Locate another replica or source that still retains enough binary logs for the candidate to fetch the missing portion.
2. Use a newer backup with an appropriate GTID checkpoint, then reload the candidate.
3. If no suitable log source exists, rebuild the candidate from a fresh consistent snapshot and configure replication from that snapshot.

Never skip GTIDs just to make replication continue. Skipping transactions can create data divergence that GTID status will no longer easily detect.

### 6.3. Connecting the candidate using auto-position

After verifying GTID history and baseline data, configure the new source endpoint with `SOURCE_AUTO_POSITION=1`, start the replica, and monitor receiver/applier. Put the candidate into workload service only after confirming it has caught up, has no replication errors, and key data is reconciled.

If using named replication channels or multi-source replication, explicitly specify the right channel when stopping, changing the source, and checking status. Do not alter the configuration of other channels on the same instance.

## 7. Conditions for promoting a replica to primary

Promoting a replica means turning a replica into a write-accepting source. This is a failover operation carrying higher risk than replacing an ordinary replica, because you must determine what data was committed on the old primary and prevent the old primary from continuing to accept writes.

### 7.1. Selecting the candidate with the most complete history

If the old primary is still reachable, obtain the committed GTID set on the primary and compare it with the candidate:

```sql
SELECT GTID_SUBSET(
  '<old_primary_gtid_executed>',
  '<candidate_gtid_executed>'
) AS candidate_contains_old_primary_history;
```

A result of `1` indicates the candidate has executed every GTID in the old primary's set. A result of `0` means the candidate is missing transactions. If the old primary went down suddenly and its final GTID set cannot be read, use information from replicas, archived binlogs, application logs, and RPO policy to determine which transactions may have been lost.

This check only proves the candidate contains the old primary's history. You must also check for extra GTIDs on the candidate:

```sql
SELECT GTID_SUBTRACT(
  '<candidate_gtid_executed>',
  '<old_primary_gtid_executed>'
) AS candidate_extra_gtids;
```

If `candidate_extra_gtids` is non-empty, investigate every transaction before promoting. In a single-source topology, these may be transactions written directly on the candidate; in a multi-source topology, some GTIDs outside the old primary may originate from another valid source. Do not treat a candidate as a consistent replacement merely because it holds all of the old primary's GTIDs; classify any extra GTIDs and reconcile the data.

In asynchronous replication, a transaction confirmed to the client on the primary might not yet have reached the replica before the primary crashed. Therefore, promoting a replica that has not caught up can lose committed transactions. GTID helps measure received history, but it cannot recover transactions that no remaining replica or backup holds.

### 7.2. Fencing the old primary to prevent split-brain

Before allowing the candidate to accept writes, ensure the old primary can no longer accept writes from applications or other nodes. Depending on infrastructure, fencing may include stopping the MySQL service, blocking write connections at the network/proxy, revoking write privileges, or HA orchestration mechanisms. Simply setting `read_only` is not always sufficient if accounts with bypass privileges remain or another failover mechanism could bring the old node back.

Once the old primary is fenced, inspect the candidate, configure read-only flags per the promotion runbook, update application write endpoints, and repoint remaining replicas to the new primary using GTID auto-position. Never allow writes on two nodes at the same time.

### 7.3. Evaluating candidates when the old primary is gone

When the final GTID set cannot be retrieved from the old primary, compare `gtid_executed` across all accessible replicas. The candidate with the largest GTID set often holds the most transactions, but the comparison must account for all UUIDs and any extra GTIDs. Two sets may not have a subset relationship; a larger GTID count does not automatically prove a candidate holds the complete valid history.

If replicas have differing GTIDs, trace the origin of each set and determine whether transactions were written directly on a replica. Do not merge histories mechanically. Select the candidate based on transaction completeness, data consistency, and acceptable RPO; then explicitly document any transactions that may be lost.

## 8. Common errors with auto-position

| Scenario | Common cause | Remediation |
|---|---|---|
| Source purged GTIDs needed by replica (`ER_SOURCE_HAS_PURGED_REQUIRED_GTIDS`) | Required binary logs no longer exist on the source | Use another source that still retains logs or reseed from a newer backup |
| Replica has GTIDs from source's UUID that source lacks | May result from out-of-band writes or tail of source binary log lost/truncated after a crash | Check error logs and crash recovery, identify which GTIDs truly committed, and reconcile data before modifying topology |
| Receiver cannot connect | Wrong host, port, account, TLS, firewall, or replication privileges | Check `Last_IO_Error`, connection details, and privileges on the source |
| Applier stops | Data, schema, transaction, or replication configuration error | Check `Last_SQL_Error`, identify the failing transaction, and handle per recovery procedure |
| Replica cannot keep up | Insufficient resources, large transactions, slow I/O, or heavy source load | Monitor receiver/applier, disk, CPU, transaction apply rate, and replica lag |
| Duplicate UUID | Cloned/copied instance did not generate a new `server_uuid` | Stop the affected topology and fix identity per supported MySQL procedure |

When the source reports it cannot send required GTIDs because they were purged, do not use transaction skipping to hide the error. When a replica has extra GTIDs, do not wipe GTID metadata to force a connection. Both scenarios require investigating history and data before proceeding.

## 9. Replica replacement checklist

Before switching roles, perform these steps in order:

1. Define the objective: replacing a failed replica, reparenting a replica to another source, or promoting a replica to primary.
2. Record the MySQL version, `server_id`, `server_uuid`, `gtid_mode`, `enforce_gtid_consistency`, `gtid_executed`, and `gtid_purged` of the involved nodes.
3. Verify the backup or clone used to seed the candidate is consistent and its GTID checkpoint matches the data.
4. Compare GTID sets to detect missing transactions and errant GTIDs.
5. Verify the source still retains all GTIDs the candidate needs, or that another source/backup can supply them.
6. Verify replication user, host, TLS, privileges, and `SOURCE_AUTO_POSITION`.
7. Start replication, monitor receiver/applier, errors, and GTID sets until the candidate catches up.
8. If promoting, fence the old primary before enabling writes on the candidate; assess unreplicated transactions against RPO.
9. Repoint remaining replicas to the new source using GTID auto-position and monitor the entire topology.
10. Verify application data, backups, binlog retention, and PITR capability after the change.

This checklist is a technical verification framework. Each environment must integrate it with HA orchestration, change approval workflows, and a concrete rollback plan.

## 10. Hands-on exercise

A topology has primary `db-a` and two replicas `db-b`, `db-c`. All three servers have GTID mode enabled. `db-a` crashes; `db-b` has executed GTIDs `uuid-a:1-900`, while `db-c` has executed `uuid-a:1-875` and also has `uuid-c:1-3` from a direct write outside replication.

Address the following tasks:

1. Write queries using `GTID_SUBSET()` and `GTID_SUBTRACT()` to determine whether `db-c` has errant GTIDs relative to `db-a`, assuming you have `db-a`'s final GTID set.
2. If `db-a` still has binary logs containing `uuid-a:876-900`, what conditions allow `db-c` to catch up via auto-position after resolving the errant GTIDs?
3. If the binary logs containing GTIDs 876-900 were already purged and there is no binlog backup, which approach would you choose to replace `db-c`?
4. If `db-a` cannot be recovered, `db-b` is the promotion candidate. What must you verify regarding committed transactions, RPO, and fencing `db-a`?
5. After promoting `db-b`, what must be checked and changed on `db-c` for it to become a replica of the new primary?
6. Why does `db-b` having more GTIDs not automatically prove it is a safe candidate if its GTID set contains extra transactions?

A sound plan must clearly distinguish missing GTIDs, errant GTIDs, retained binary logs, and actual data state. Document all verification results before modifying the topology.

## Conclusion

GTID auto-position enables MySQL to locate transactions a replica is missing based on GTID history, simplifying reconnection and reparenting. Essential prerequisites are compatible GTID configuration across servers, unique identities, consistent seed data, and the source retaining required binary logs. When replacing a replica, detect errant GTIDs and purged GTIDs; when promoting, verify the candidate contains all transactions to be preserved and fence the old primary to avoid split-brain. GTID sets serve as evidence of the transaction history recorded by a server, while final correctness must still be verified against actual data and operational procedures.
