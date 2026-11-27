# Source/replica model and its role in read scaling or recovery

Replication in MySQL maintains one or more replica servers by transferring changes written to the source server's binary log to the remaining servers. This model helps distribute read queries, create standby servers, and support service recovery when the source fails. To use it properly, you need to understand the data flow, replication lag, and consistency boundaries of each replica.

In modern MySQL, new documentation and statements use the terms **source** and **replica**. Some older versions still display the names **master** and **slave** in statements or status fields. This lesson uses source/replica; during operations, cross-check the syntax against the MySQL version you are running.

## 1. Source/replica architecture

In a one-source and one-replica model, the application sends write operations to the source. The source executes transactions and records the changes in the binary log. The replica connects to the source, receives the binary log events, stores them in the relay log, and applies them to its local data.

~~~mermaid
flowchart LR
    AppW["Write application"] --> Source["MySQL source"]
    Source --> Binlog[("Binary log")]
    Binlog --> Receiver["Receiver thread"]
    Receiver --> Relay[("Relay log")]
    Relay --> Applier["Applier thread"]
    Applier --> Replica["MySQL replica"]
    AppR["Read application"] --> Replica
    AppR2["Other read queries"] --> Source
~~~

The basic flow consists of the following components:

| Component | Role |
|---|---|
| Source | Accepts writes, executes transactions, and emits change events via the binary log |
| Binary log (binlog) | Stores events to be replicated; also a key input for point-in-time recovery |
| Receiver thread (I/O thread) | On the replica, connects to the source and reads binlog events |
| Relay log | Temporarily stores received events so the replica can apply them |
| Applier thread (SQL thread or worker) | Reads the relay log and executes changes on the replica |
| Replica | Maintains a copy of the data, serves read queries, or waits to be selected as the new source |

Standard MySQL replication is **asynchronous replication**. The source does not have to wait for the replica to finish applying a transaction before continuing to process writes. Therefore, the source can operate quickly and independently, while the replica may lag behind the source by some amount of time.

Once the receiver has received an event, the event is written to the relay log. The applier may apply it immediately or process it later if load is high, a transaction runs for a long time, or an error occurs. Therefore, you must distinguish between data **received** and data **applied**. A replica with an active receiver but a stopped applier can still accumulate relay logs while its data fails to keep up with the source.

Every server in the topology must have a **unique server_id**. The source must have binary logging enabled; the replica must be able to connect to the source and have the corresponding replication configuration. If a replica also needs to re-emit its changes to downstream replicas or may be promoted to source in a chained topology, you need to plan binary log writing on the replica as well, typically through the **log_replica_updates** option in versions that support the new naming.

## 2. What roles do the source and replica fulfill?

The **source** is the primary write point in a single-source topology. It accepts **INSERT**, **UPDATE**, **DELETE** statements, schema changes, and application transactions. Changes to be replicated are written to the binary log. The source also typically holds the freshest data and is the right place for operations that need to immediately read the result just written.

The **replica** receives and applies changes from the source. One replica may serve reports, dashboards, lookup queries, or read-heavy workloads. Another replica may be kept nearly free of application traffic so it is ready to replace the source during an outage. Multiple replicas can be deployed with different hardware specifications or purposes.

| Replica role | How it is used | Things to watch out for |
|---|---|---|
| Read replica | Offloads eligible read queries from the source | Results may be older than the source due to replication lag |
| Reporting replica | Runs reports or analytical queries with minimal impact on the transactional application | Heavy queries still consume CPU, I/O, and memory on the replica |
| Standby replica | Waits to be promoted when the source fails | Must monitor lag, capacity, and the role-switching procedure |
| Backup replica | Assists in taking backups to reduce load on the source | Must ensure a consistent snapshot; a replica does not replace an independent backup |

A common topology has one source and multiple replicas:

~~~mermaid
flowchart TB
    App["Application"]
    Source["Source"]
    R1["Application read replica"]
    R2["Reporting replica"]
    R3["Standby replica"]
    App -->|"Writes"| Source
    App -->|"Eligible reads"| R1
    Source --> R1
    Source --> R2
    Source --> R3
~~~

This model helps distribute read load by purpose. However, all write operations remain centralized at the source. Adding replicas does not automatically increase the write capacity of a single source, nor does it replace optimizing schemas, indexes, transactions, or queries.

You can build multi-tier topologies, where one replica forwards binlogs to another replica, or configure multi-source replication so one replica receives data from multiple sources. These topologies introduce additional constraints on data flow, conflicts, transaction ordering, and operations. Deploy them only when you have clearly defined which data belongs to which source and how conflicts are handled; a single-source topology with multiple replicas is usually easier to control.

## 3. How does replication help scale reads?

When an application has many read queries, a portion of those queries can be routed to read replicas. The source continues processing write transactions; replicas process read queries against the replicated copy of the data. Routing is typically handled at the application layer, connection pool, proxy, or data access layer.

Example classification of query flows:

| Operation type | Where to send | Reason |
|---|---|---|
| Creating orders, updating balances, writing transactions | Source | Writes must be executed on the primary write point |
| Immediately reading a newly created order or recently updated data | Source, or a mechanism that waits for the replica to apply the transaction | Avoid reading data that has not yet been replicated |
| Looking up catalogs, content, or infrequently changing data | Read replica | Can tolerate a small delay if the business logic allows |
| Aggregate reports, dashboards, heavy read queries | Dedicated reporting replica | Reduces resource contention with the transactional workload on the source |
| Schema changes or replication administration operations | Per runbook on the source or designated server | Avoid running ad-hoc changes on a replica serving reads |

Do not send every **SELECT** statement to a replica mechanically. Some queries require reading the exact latest state right after a write. If the application writes an order to the source and immediately reads that order from a replica, the replica might not have applied the transaction yet and may return stale results or not find the record.

This is the **read-after-write consistency** problem. There are three common ways to handle it:

1. After a write operation, continue reading from the source for a period of time or within the same business flow.
2. Route queries that require the freshest data to the source; only send queries that can tolerate lagged data to a replica.
3. For systems using GTID, the application or middleware can wait for the replica to apply up to the GTID of the transaction to be read before sending the query. The wait mechanism must have a timeout and a fallback plan when the replica cannot keep up.

Replication lag can vary with write load, large transactions, long-running queries on the replica, network speed, I/O capacity, and applier configuration. Therefore, set a lag threshold appropriate for the business and have a plan when the threshold is exceeded, such as temporarily stopping routing certain queries to a lagging replica.

Replication only distributes read load at the server level. If a reporting query scans too much data or lacks an index, it can still overload the replica. You still need to measure performance, read EXPLAIN plans, design indexes, and constrain heavy queries just as on the source.

## 4. Replication lag and consistency

**Replication lag** is the delay between a change on the source and the time that change is applied on the replica. Lag can be short under normal conditions but increase sharply when the source writes heavily, executes large transactions, or the replica lacks resources.

Several misleading situations to watch out for:

- Receiver is running but applier is stopped: relay logs keep growing while data on the replica does not advance.
- Receiver is stopped or disconnected: the replica stops receiving new events from the source.
- A single large transaction: the replica may take considerable time to apply that transaction.
- Long-running read queries: can compete for resources with the applier and slow down data updates.
- **Seconds_Behind_Source** equal to **0** is not absolute proof that every query will always see the newest data; this metric is a monitoring signal and should be read together with receiver status, applier status, and replication errors.

For workloads requiring high freshness, monitor at least:

- Receiver and applier status.
- Estimated lag time and lag trends over time.
- I/O errors, transaction apply errors, and relay log size.
- Binlog write rate on the source and apply rate on the replica.
- Network connectivity, disk space, and CPU/I/O resources on both sides.

If the topology uses GTID, the received and executed GTID sets help identify where a replica stands in the transaction stream. The **Retrieved GTID set** reflects transactions received; the **Executed GTID set** reflects transactions executed on the server. These two sets are useful when checking lag and choosing a replica to promote, though you must understand the relationship between GTID sets and check for transactions originating outside the replication stream before switching roles.

MySQL also provides semi-synchronous replication when the appropriate plugin is configured. In this mode, the source can wait for at least one replica to acknowledge that it has received and written the event to its relay log before completing the commit according to the semi-sync policy. Acknowledging receipt of an event does not mean the replica has applied the transaction. Semi-sync can narrow the window of data loss if the source fails, but it does not automatically guarantee zero data loss in all situations; you must check timeouts, fallback states, and failover policies.

## 5. Using a replica as a standby server and for service recovery

A healthy, well-maintained replica can become the new source when the current source fails. This process is commonly called **failover**. A standby replica helps reduce service recovery time, but its effectiveness depends on replication lag, failure detection capability, and the role-switching procedure.

Two key metrics when designing recovery:

- **RPO (Recovery Point Objective):** the acceptable level of data loss, usually measured in time or number of transactions.
- **RTO (Recovery Time Objective):** the maximum acceptable time to restore the service.

With asynchronous replication, the source may have confirmed a transaction to the application, yet that transaction had not reached the replica when the source suddenly crashed. When promoting a replica, unreplicated transactions may be lost. The actual RPO therefore depends on the lag at the time of the incident. If the business requires a very low RPO, consider semi-sync, an appropriate HA architecture, and failover testing; never assume RPO equals 0 just because a replica exists.

A manual failover procedure requires controlled steps:

1. **Confirm the incident:** verify that the source is genuinely unable to serve and rule out transient network or application errors.
2. **Prevent the old source from accepting further writes:** isolate or fence the old server to avoid having two sources accept writes when the network recovers.
3. **Evaluate the replicas:** check receiver/applier status, replication errors, lag, and executed GTID sets. Choose the replica with the most complete data based on verified transaction state.
4. **Promote a replica:** stop replication per the runbook, verify that required data has been applied, and transition the selected server to the write role.
5. **Switch routing:** update the proxy, DNS, or application configuration so write connections go to the new source; verify both read and write flows.
6. **Reconfigure the topology:** point remaining replicas to the new source and handle the old source before allowing it to rejoin.
7. **Verify and document:** check data, errors, lag, backups, and the time of role switch; record any transactions or data intervals that may have been lost.

On a replica protected by **super_read_only**, transitioning it into the new source must be performed intentionally after the old source has been isolated and data evaluation is complete. For example, the following statements remove server-level read-only mode:

~~~sql
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;
~~~

This is a role-change operation, not a lag-remediation command. Execute it only on the exact server chosen for promotion according to the operational procedure. If the old source can still accept writes, enabling writes on the new replica can create two independent data branches and cause conflicts that are difficult to reconcile.

When the old source recovers, do not automatically allow it to accept writes again. You must determine which transactions were committed on the old source, which transactions were executed on the new source, and how to resynchronize. Depending on the situation, you may need to rebuild the old server from a backup or a copy of the new source before adding it back to the topology.

## 6. Can a replica replace a backup?

A replica **is not an independent backup**. Replication copies valid changes along the binlog stream. If a user accidentally runs **DELETE** or **DROP TABLE** on the source, that change can also be applied to the replica. If data is logically corrupted or an account is compromised, the replica can receive the same harmful changes.

A replica can help offload the source when taking backups, but the backup process must still ensure data consistency and store an independent copy. A data protection strategy should combine:

- Full backups or incremental backups according to the retention policy.
- Binary logs retained long enough to support point-in-time recovery.
- Backups stored in a location with separate access permissions and fault domain from the database servers.
- Regular integrity checks and restore drills.
- Monitoring replication lag and the status of the replica used as the backup source.

If backing up from a replica, you must determine which point in time the snapshot represents, how it coordinates with the applier, and how the corresponding binlog position or GTID is recorded. If the replica is lagging or the applier has not yet applied all necessary transactions, the backup may not represent the latest state required by the business. The backup must also include the information needed to continue point-in-time recovery from the binlog.

## 7. Baseline configuration and status checks

Minimal configuration example for a source:

~~~ini
[mysqld]
server_id = 101
log_bin = mysql-bin
binlog_format = ROW
~~~

Baseline configuration example for a replica:

~~~ini
[mysqld]
server_id = 201
relay_log = relay-bin
read_only = ON
super_read_only = ON
relay_log_recovery = ON
~~~

The **server_id** values must be unique within the topology. Configuration file names and service management depend on the operating system and MySQL installation method. These are directional examples; before applying them, check your version, GTID policy, TLS, replication accounts, binlog retention, and topology requirements.

On a replica, use the following statement to check replication in modern MySQL versions:

~~~sql
SHOW REPLICA STATUS\G
~~~

In older versions, the statement may still be **SHOW SLAVE STATUS\G**. In the output, inspect the fields corresponding to your version, especially:

| Status field | Meaning |
|---|---|
| **Replica_IO_Running** | Whether the receiver thread is currently receiving binlog events |
| **Replica_SQL_Running** | Whether the applier is currently applying the relay log |
| **Seconds_Behind_Source** | Estimated lag; must be interpreted alongside other metrics |
| **Last_IO_Error** | Most recent error when connecting or receiving binlog events |
| **Last_SQL_Error** | Most recent error when applying events |
| **Retrieved_Gtid_Set** | GTIDs received by the replica, when using GTID |
| **Executed_Gtid_Set** | GTIDs executed on the server |

Both the receiver and applier statuses typically need to be **Yes** in a healthy topology. If either status is **No**, read the corresponding error message and server log before mechanically restarting the thread. A data error or incompatible schema may continue to recur after a restart.

You can check a server's role and read-only mode with:

~~~sql
SELECT
  @@hostname AS hostname,
  @@server_id AS server_id,
  @@read_only AS read_only,
  @@super_read_only AS super_read_only;
~~~

The result helps confirm which server you are connected to and whether it is in read-only mode. Do not use a single check query to conclude that the entire topology is healthy; cross-check the status on the source and each replica, logs, lag, and network health.

Binary logs on the source must be retained long enough for replicas to have time to recover after an interruption. If the source purges binlogs that a replica has not yet received, the replica may no longer be able to fetch the missing events and will need to be resynchronized or rebuilt from a backup. The **binlog_expire_logs_seconds** variable governs binlog retention duration; its value should be based on the maximum expected outage duration, binlog generation rate, and an operational safety margin.

## 8. Common errors and troubleshooting

| Symptom | Possible cause | What to check |
|---|---|---|
| Receiver not running | Network loss, wrong hostname/port, incorrect replication credentials, or source no longer retains required binlogs | Check **Last_IO_Error**, TCP connectivity, account privileges, and binlogs on the source |
| Applier not running | Event cannot be applied, data/schema error, or conflict | Check **Last_SQL_Error**, failing transaction, and schema differences |
| Lag growing continuously | Source write rate exceeds apply rate, large transaction, or replica lacks resources | Measure load, I/O, CPU, transactions, and number of applier workers |
| Replica receives events but data does not update | Receiver is running, but applier is slow or stopped | Compare relay logs, applier status, and executed GTIDs |
| Application reads stale data | Reading from a replica before the transaction is applied | Route read-after-write to the source or use a GTID wait with timeout |
| Replica cannot be used for recovery | Heavy replica lag, missing binlogs, or inconsistent data copy | Check GTIDs, binlog retention, backups, and rebuild plan |
| After failover, two servers accept writes | Old source was not fenced or routing still points to the old server | Isolate the old source, audit all write endpoints, and maintain only one valid source |

Do not skip a failing transaction just to get replication running again. Skipping an event can cause the replica's data to silently diverge from the source. If you are forced to handle a failing transaction, assess the data impact, document the decision, and re-verify consistency afterward.

## 9. Design scenario

An e-commerce system has one MySQL source and two replicas:

- The source handles order creation, payment updates, and inventory management.
- Replica A serves order lookups and product information for the application.
- Replica B serves end-of-day reporting and is kept ready for recovery if the source fails.

Design how to use this topology:

1. Direct order creation, payment, and inventory update operations to the source.
2. Direct lookup queries that can tolerate lag to replica A; right after a customer places an order, read the fresh state from the source or wait for the replica to apply the necessary transaction.
3. Restrict heavy reporting queries to replica B and monitor to ensure reports do not push replication lag past the threshold.
4. Set alerts when receiver/applier stops, lag increases, or binlogs are nearing expiration.
5. Build a failover runbook: isolate the old source, evaluate GTIDs and lag, promote a replica, update routing, and verify data.
6. Maintain independent backups and test restores; do not treat the two replicas as two backups.

When evaluating the design, make sure you can answer these questions: which queries require the newest data, what is the maximum acceptable lag, if the source is lost right after a transaction has that transaction reached the replica yet, who is authorized to promote, and how do you prevent the old source from continuing to accept writes?

## 10. Self-check questions

1. How do the roles of the binary log and the relay log differ in replication?
2. Why does a running receiver thread with a stopped applier thread still cause a replica to become stale?
3. Which part of system load does a read replica help scale? What limits does it not solve?
4. Why can a read query executed immediately after a write return stale data when read from a replica?
5. How does asynchronous replication affect RPO in the event of a source failure?
6. Why must the old source be fenced before promoting a replica?
7. Can a replica replace a backup? Give an example scenario where bad data gets replicated to all replicas.
8. When checking a replica, why must you inspect receiver status, applier status, errors, and executed GTIDs together?

A well-designed source/replica topology must have a clear purpose for each replica, read/write routing rules, replication lag thresholds, a binlog retention policy, and a rehearsed failover procedure. Only when these elements are combined with independent backups and access controls can replication support both read scaling and operational recovery.
