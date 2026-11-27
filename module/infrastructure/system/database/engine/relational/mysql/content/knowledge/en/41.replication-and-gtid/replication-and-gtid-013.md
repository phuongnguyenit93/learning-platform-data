# read_only, super_read_only, and preventing accidental writes to a replica

In the **DATABASE_MYSQL** module, replication distributes data from a source server to one or more replicas. Replicas typically serve read queries, reporting, or standby failover when the primary fails. If an application or operator accidentally sends write statements to a replica, data can diverge from the source and complicate synchronization or failover.

MySQL provides two global variables—**read_only** and **super_read_only**—to restrict writes from clients. Understanding the exact difference between them, the exception for the replication stream, and how to switch primary/replica roles is essential for protecting the topology.

This lesson belongs to the **DATABASE_MYSQL** module, complementing skills in table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operations issues.

## 1. Objectives and architecture

After this lesson, you will be able to:

- Explain the purpose and differences between `read_only` and `super_read_only`.
- Enable read-only mode on a replica while still allowing the replication applier to update data.
- Identify accounts that can bypass `read_only` and why `super_read_only` should be enabled.
- Inspect server status, replication status, and application account privileges.
- Design a procedure to promote a replica to primary without creating two servers accepting writes simultaneously.
- Investigate rejected write errors and unexpected read-only configuration behaviors.

A common topology:

~~~text
                 Write application
                      |
                      v
                +-----------+
                |  Primary  |
                | read_only |
                |    OFF    |
                +-----------+
                      |
                Binary log
                      |
             +--------+--------+
             |                 |
             v                 v
       +-----------+     +-----------+
       | Replica A |     | Replica B |
       | read_only |     | read_only |
       |   ON      |     |   ON      |
       | super RO  |     | super RO  |
       +-----------+     +-----------+
          read/report      read/standby
~~~

The primary receives writes from the application and generates binary logs. Replicas receive logs, write relay logs, and let the replication applier apply changes. Read-only variables protect replicas against write operations from clients; their job is not to block the replication applier from updating data.

Distinguish three streams:

1. **Business clients:** applications, reporting tools, or administrators connecting via SQL and issuing statements.
2. **Replication receiver:** receives binary logs from the source and writes them to the relay log.
3. **Replication applier:** reads the relay log and applies changes onto the replica.

The goal is to block unintended write streams from clients while keeping the legitimate replication stream running.

## 2. How does read_only work?

`read_only` is a global system variable. When enabled, MySQL restricts data and structural modification operations on the server. Updates performed by the replication applier remain permitted.

Enable at runtime:

~~~sql
SET GLOBAL read_only = ON;
~~~

Check:

~~~sql
SELECT @@GLOBAL.read_only;
~~~

However, `read_only=ON` still allows clients holding the `SYSTEM_VARIABLES_ADMIN` privilege or the `SUPER` privilege (deprecated in newer MySQL releases) to perform updates. This is an exception intended for highly privileged administrative accounts.

Therefore, `read_only` is useful for preventing regular applications or non-administrative accounts from accidentally writing to a replica. It is not a strong enough barrier if application or operational accounts on the server still possess privileges that bypass this mode.

For example, a reporting account with only `SELECT` will be rejected if it tries to run:

~~~sql
INSERT INTO shop.orders(order_id, status)
VALUES (9001, 'NEW');
~~~

MySQL typically returns an error like:

~~~text
ERROR 1290 (HY000): The MySQL server is running with the --read-only option so it cannot execute this statement
~~~

The exact message may vary depending on version and enabled variables. Check both server state and the account's effective privileges before concluding an error is caused by replication.

## 3. super_read_only provides stronger protection

`super_read_only` adds another layer of protection: when enabled, MySQL forbids clients from performing updates even if the account holds `SYSTEM_VARIABLES_ADMIN` or `SUPER`. Updates performed by the replication applier remain permitted.

Enable this mode:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

When `super_read_only` is enabled, MySQL automatically enables `read_only`. Check both variables:

~~~sql
SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Expected result on a protected replica:

| Variable | Value |
|---|---|
| read_only | 1 |
| super_read_only | 1 |

Key differences:

| Behavior | read_only=ON | super_read_only=ON |
|---|---|---|
| Regular client writes data | Blocked | Blocked |
| Client with SYSTEM_VARIABLES_ADMIN or SUPER writes data | May be allowed | Blocked |
| Replication applier applies changes | Allowed | Allowed |
| Automatically enables read_only | No | Yes |
| Protects replica against accidental admin writes | Insufficient | Stronger |

When `super_read_only` is turned off, `read_only` may remain `ON` if it was previously enabled. Conversely, setting `read_only=OFF` also turns off `super_read_only`. Therefore, when changing states, re-read both variables rather than inferring their state solely from the command just run.

`super_read_only` can still be turned off by an administrator holding privileges to modify system variables. It protects against accidental write statements from clients—even privileged clients—but does not replace administrative access control, auditing, and configuration change workflows.

## 4. Exceptions for replication and temporary tables

### 4.1. Replication continues running

Enabling `read_only` or `super_read_only` on a replica does not stop replication.

The normal flow continues operating:

1. The receiver thread receives events from the primary.
2. Events are written to the relay log.
3. The applier thread reads the relay log.
4. The applier applies changes to tables on the replica.
5. Execution status is updated so the replica stays synchronized.

This is an intentional exception. If read-only variables blocked the replication applier as well, the replica could never keep up with the primary.

You can check replication:

~~~sql
SHOW REPLICA STATUS\G
~~~

On older versions, the corresponding statement may be `SHOW SLAVE STATUS`. Check at minimum:

- `Replica_IO_Running` and `Replica_SQL_Running` are in the expected state.
- No unhandled receiver or applier errors.
- Replication source matches the expected server.
- Retrieved and executed GTIDs are advancing properly.
- Replication lag is within operational thresholds.

Displayed column names and statuses depend on version and replication type. With multi-source replication, inspect each channel rather than relying on a single overall status line.

### 4.2. TEMPORARY tables are an exception

Read-only mode does not apply in the usual way to `TEMPORARY` tables. Clients can create, modify, and drop temporary tables within a session even when the server has read-only mode enabled.

Example:

~~~sql
CREATE TEMPORARY TABLE tmp_report (
  order_id BIGINT PRIMARY KEY,
  total_amount DECIMAL(12,2)
);

INSERT INTO tmp_report(order_id, total_amount)
VALUES (1001, 250000.00);

DROP TEMPORARY TABLE tmp_report;
~~~

These operations do not write persistent data into business tables on the replica. Therefore, an SQL session being able to create a temporary table does not prove that `read_only` or `super_read_only` is disabled.

If the goal is preventing business data from being modified, inspect actual target tables and variable states. If the goal is completely isolating a client from the server, enforce connection privileges, query privileges, and network controls; read-only mode is not a mode that blocks all SQL statements.

## 5. Safe replica configuration

### 5.1. Startup configuration

To ensure a replica always starts in read-only state, configure it in the MySQL configuration file:

~~~ini
[mysqld]
read_only=ON
super_read_only=ON
~~~

`super_read_only=ON` automatically enables `read_only`, though declaring both variables explicitly makes the configuration intent clear to operators.

For runtime changes, use:

~~~sql
SET GLOBAL super_read_only = ON;
~~~

Changes via `SET GLOBAL` take effect for the current run. Without startup configuration or an appropriate persistent configuration mechanism, the state may revert to another value after the server restarts.

Some environments use centrally managed configuration, managed database services, or Group Replication that manage this variable automatically. Use the configuration and failover mechanisms provided by the platform; avoid manually overriding state managed by automation.

### 5.2. Verification after configuration

After enabling, verify:

~~~sql
SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;

SHOW REPLICA STATUS\G
~~~

Also confirm:

- The server holds the intended replica role in the topology.
- The replica is receiving and applying logs from the expected source.
- Reporting applications connect only to read endpoints.
- Application accounts do not carry administrative privileges that bypass `read_only`.
- No jobs, crons, migrations, or admin tools are sending writes to the replica.
- Monitoring and alerts can detect if the variable is changed outside approved procedures.

### 5.3. Controlling account privileges

`super_read_only` is a server-level protection layer. SQL privileges must still be designed following the principle of least privilege.

For example, a reporting account needs only `SELECT` on the read schema:

~~~sql
CREATE USER 'report_reader'@'10.%'
IDENTIFIED BY 'use-a-secret-manager';

GRANT SELECT ON shop.* TO 'report_reader'@'10.%';
SHOW GRANTS FOR 'report_reader'@'10.%';
~~~

The password string in the example is only an illustrative placeholder. In deployment, generate and distribute secrets using your organization's secret management system; never commit real passwords to scripts, Git, or shared docs.

Avoid granting administrative privileges such as `SYSTEM_VARIABLES_ADMIN` or `SUPER` to application accounts unless business requirements demand them. Do not share a single account across applications, reporting, and operational administration. Role-based privilege separation reduces the pathways that could accidentally disable protection.

## 6. Procedure for enabling read-only on a replica

An operational procedure should include the following steps:

1. **Confirm role:** verify hostname, server UUID, `server_id`, replication source, and channels.
2. **Check replication health:** confirm receiver/applier are running, error-free, and GTIDs are advancing normally.
3. **Inspect workload:** identify applications, reports, migrations, and background jobs connected to the server.
4. **Enable protection:** set `super_read_only=ON`; `read_only` will be enabled along with it.
5. **Verify:** re-read both variables and check that replication continues applying events.
6. **Verify routing:** confirm write endpoints point to the primary; read endpoints point to the replica.
7. **Monitor:** watch for rejected write errors, replication lag, and configuration changes.

If a replica needs maintenance, enabling read-only before starting work reduces the risk of clients sending accidental writes. However, check whether backup tools, data verification tools, or migrations require writes; they may need to be redirected to an appropriate environment.

## 7. Promoting a replica to primary during failover

During failover, a replica may be promoted to primary. This is a particularly sensitive moment because changing `super_read_only` allows the server to accept writes from applications.

A safe role-transition procedure must guarantee that only one primary is allowed to accept writes.

### 7.1. Before opening write access

- Confirm the old primary has stopped writing or has been fenced off from applications.
- Confirm the chosen replica has sufficiently fresh data according to the RPO target.
- Inspect retrieved and executed GTIDs; identify any missing transactions if present.
- Confirm the new topology and which primary the remaining replicas will follow.
- Ensure routers, proxies, or application configurations will send writes to the right server.
- Capture pre-failover state so you can investigate if divergence arises.

**Fencing** is the act of preventing the old primary from continuing to accept writes—for example, stopping the service, blocking write connections at the network layer, or using a guaranteed orchestration mechanism. Simply changing DNS or switching a proxy may not stop existing clients connected directly to the previous primary.

### 7.2. Promoting the selected server

Only after confirming the selected server is the sole writer and the old primary is fenced should administrators disable read-only mode:

~~~sql
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;

SELECT
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

Expected result on the new primary:

| Variable | Value |
|---|---|
| read_only | 0 |
| super_read_only | 0 |

Next, complete replication configuration for the new topology according to your GTID or file/position plan. Verify that applications write only to the new primary and remaining replicas receive logs from the right source.

The exact sequence depends on your failover tooling, MySQL version, and GTID model. When using Orchestrator, Group Replication, InnoDB Cluster, or managed services, follow the platform's official promotion procedure. Never manually turn off `super_read_only` while the orchestrator still views the server as a replica.

### 7.3. Demoting the old primary to a replica

When bringing the old primary back into the topology, ensure it cannot continue accepting writes from applications:

- Fence or tear down old write endpoints.
- Inspect the old primary's data for divergence or out-of-band transactions.
- Resynchronize using your chosen procedure; rebuilding the replica from the new primary may be necessary if consistency between both sides cannot be proven.
- Configure the new replication source and verify GTIDs.
- Enable `super_read_only=ON`.
- Return the server to the read pool only after replication and read-only state are verified.

Never just enable `super_read_only` and assume old data is already synchronized. This variable blocks client writes; it does not resolve data conflicts or transactions created during a split-brain event.

## 8. Monitoring and alerting

Monitor both variable state and actual runtime behavior:

| Metric or signal | Meaning | Action when abnormal |
|---|---|---|
| `@@GLOBAL.read_only` | Basic write-restriction state | Check server role and configuration changes |
| `@@GLOBAL.super_read_only` | Stronger write-protection state | Alert if an intended replica has value `OFF` |
| Replica IO/applier status | Replication connection and apply | Investigate channel errors, relay logs, or source |
| GTID received/executed | Transaction receipt and apply progress | Identify missing gaps or lag |
| Replication lag | Lag behind the primary | Inspect load, network, long transactions, and applier |
| Client write errors | Application is sending writes to replica | Fix routing or connection pool configuration |
| System variable changes | Someone or automation changed state | Cross-check audit logs and failover events |

Quick check example:

~~~sql
SELECT
  @@hostname AS host_name,
  @@server_id AS server_id,
  @@GLOBAL.read_only AS read_only,
  @@GLOBAL.super_read_only AS super_read_only;
~~~

This result pairs variable states with server identity. In multi-replica systems, collect it periodically from every server and compare against the role recorded in your orchestration system.

A helpful alert rule: if a server is registered with the replica role yet `super_read_only=OFF`, fire an immediate alert. Also alert when a replica stops receiving or applying logs, because read-only state does not guarantee its data is fresh.

## 9. Troubleshooting common issues

| Symptom | Possible cause | What to check |
|---|---|---|
| Application writes to replica fail with error 1290 | `read_only` or `super_read_only` is enabled | Check connection endpoint, hostname, and both global variables |
| Admin account can still write when `read_only=ON` | Account holds `SYSTEM_VARIABLES_ADMIN` or `SUPER` | Check `SHOW GRANTS`; enable `super_read_only` if server must block client writes |
| Admin account write rejected when `super_read_only=ON` | Expected behavior of stronger protection mode | Perform changes on the primary or per approved maintenance procedure |
| Replica data stops updating despite read-only enabled | Replication receiver/applier hit an independent error | Check `SHOW REPLICA STATUS`, channel errors, and relay logs |
| Replica still allows creating `TEMPORARY` tables | Temporary tables are an exception to read-only mode | Ensure temporary tables are not confused with persistent business tables |
| Replica unexpectedly becomes writable after restart | Runtime state was not persisted in startup config or automation changed it | Check config files, persisted variables, and orchestration tools |
| After failover, two servers accept writes | Old primary was not fenced or routing is inconsistent | Stop writes, isolate one side, reconcile GTIDs, and restore topology |
| Cannot disable read-only mode during promotion | Missing variable-admin privilege or automation managing state | Check `SYSTEM_VARIABLES_ADMIN` privilege, logs, and failover orchestration |

When an application reports write errors, do not immediately disable `super_read_only`. First verify which server the application is connecting to, its intended role, and replication status. If it is a replica, fix the application's connection string or routing back to the primary. Only change a server's role inside a controlled failover or maintenance procedure.

## 10. Self-check

**Scenario 1:** A replica has `read_only=ON`. An account with `SYSTEM_VARIABLES_ADMIN` still succeeds in running an update statement. Why?

**Hint:** `read_only` has an exception for accounts holding system variable administration privileges or `SUPER`. Use `super_read_only=ON` to block updates even from clients holding those privileges.

**Scenario 2:** A replica has `super_read_only=ON`, yet its data continues growing with changes from the primary. Did the read-only configuration fail?

**Hint:** No. The replication applier is permitted to apply events from the relay log. Read-only mode primarily blocks client-initiated updates.

**Scenario 3:** A client can create and write to a `TEMPORARY` table on a replica. Does that prove the replica accepts writes to business tables?

**Hint:** No. `TEMPORARY` tables are an exception; inspect table type and the state of both global variables.

**Scenario 4:** During failover, the selected replica has caught up with the primary, but the old primary is still reachable from several application servers. Should you immediately disable `super_read_only` on the new replica?

**Hint:** Not yet. You must fence the old primary and ensure only one writer exists before opening write access on the new primary. Changing proxy or DNS alone may be insufficient if clients still hold direct connections.

**Scenario 5:** After disabling `super_read_only`, `read_only` remains `ON`. Is this an invalid state?

**Hint:** No. Disabling `super_read_only` does not automatically disable `read_only`. If the server has been promoted and must accept writes, verify and disable `read_only` as well per procedure.

## 11. Key takeaways

- `read_only=ON` blocks most client write operations but allows an exception for accounts holding `SYSTEM_VARIABLES_ADMIN` or `SUPER`.
- `super_read_only=ON` blocks client writes even from privileged admin accounts; it automatically enables `read_only`.
- Replication receiver and applier continue operating; the replica keeps receiving and applying changes from the primary.
- `TEMPORARY` tables are an exception, so successfully creating a temporary table does not prove read-only mode is off.
- Verify `read_only`, `super_read_only`, `hostname`, `server_id`, replication status, and account privileges together.
- During promotion, fence the old primary before enabling writes on the new primary to prevent split-brain.
- When returning the old primary as a replica, verify data and GTIDs before putting it into the read pool.
- Read-only mode is one protection layer; least-privilege permissions, monitoring, and failover procedures remain essential.
