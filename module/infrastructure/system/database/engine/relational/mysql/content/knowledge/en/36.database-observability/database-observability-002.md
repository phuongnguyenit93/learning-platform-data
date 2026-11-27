# SHOW PROCESSLIST and Distinguishing Waiting Connections from Running Queries

When MySQL slows down or runs out of capacity to accept connections, investigation usually starts with the process list. SHOW PROCESSLIST shows the currently connected client threads, their active commands, states, and how long they have been in those states. However, a Sleep connection does not mean a transaction has finished; conversely, a Query row does not prove the server is burning CPU executing it, because the query might be waiting on a lock, I/O, or metadata lock.

In the DATABASE_MYSQL module, this lesson explains how to accurately read process list columns, distinguish idle connections from running or waiting statements, use SHOW FULL PROCESSLIST, query Performance Schema, and cross-reference InnoDB transactions to find sleeping connections that still hold open transactions.

## 1. What Does the Process List Show?

The process list is a snapshot of client thread states at the moment the query runs. Each row typically corresponds to a client connection and indicates:

- Who is connected and which host the connection comes from.
- Whether the connection is waiting for a new command or processing a command.
- The current SQL statement, if any.
- How long the thread has been in its current state.

The process list is not a query history and not a CPU graph. A very short statement may finish before you capture the process list. A statement appearing in the list for a long time may be waiting for a resource rather than continuously consuming CPU.

To diagnose issues properly, combine the process list with Performance Schema, transaction metadata, lock information, and host metrics.

## 2. Viewing the List with SHOW PROCESSLIST

Basic command:

~~~sql
SHOW PROCESSLIST;
~~~

To view the full contents of the Info column:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Standard SHOW PROCESSLIST truncates SQL text in the Info column (typically limited to 100 characters). SHOW FULL PROCESSLIST displays more complete text, within the server's SQL metadata limits.

The output is a point-in-time snapshot when the statement executes. If a query lasts only a few milliseconds, a snapshot may miss it. For short queries or recent history, use statement instrumentation in Performance Schema rather than simply repeating SHOW PROCESSLIST.

## 3. The PROCESS Privilege and Visibility Scope

An account with the PROCESS privilege can see threads belonging to all users. Without this privilege, a regular account only sees its own threads.

This means:

- A DBA with PROCESS can observe all client connections.
- An application account without PROCESS typically sees only its own connections.
- An empty list or missing connections does not necessarily prove the server has no workload; check privileges and visibility scope.

PROCESS is a broad privilege because process list output can expose usernames, hosts, database names, and SQL text from other connections. Grant it only to operations teams that need server-wide visibility; avoid granting it to ordinary application accounts.

Check current privileges:

~~~sql
SHOW GRANTS FOR CURRENT_USER();
~~~

## 4. Meaning of Columns in the Process List

| Column | Meaning | How to Read During Investigation |
|---|---|---|
| Id | Client connection ID | Used to cross-reference PROCESSLIST_ID and KILL commands |
| User | MySQL account for the connection | Identifies the application or user group |
| Host | Client host, usually with port | Finds the application node or connection source |
| db | Session default database | Can be NULL if the session has not selected a database |
| Command | Type of command the thread is processing | Sleep usually means waiting for the client to send the next command |
| Time | Seconds the thread has been in the current state | Duration in the current state, not total connection age |
| State | Description of current processing state | May indicate waiting for locks, sorting, sending data, or other work |
| Info | Current statement if any | Usually NULL during Sleep; may be truncated without FULL |

Time must be interpreted alongside Command and State. For Sleep, it usually reflects how long the connection has been waiting. For an active query, it shows how long the thread has been in its current state; the state can change throughout a statement's lifecycle.

## 5. Distinguishing Sleep and Query

Two common cases:

| Indicator | Sleep Connection | Connection Processing Query |
|---|---|---|
| Command | Sleep | Usually Query |
| Info | Usually NULL | Contains current SQL |
| Meaning | Server is waiting for client to send a new command | Thread is processing an SQL command |
| Can hold an open transaction? | Yes | Yes |
| Necessarily using CPU? | Negligible when genuinely idle | No; may be waiting on resources |

Sleep means the server has not received a new command from the client on that connection. It does not mean the connection holds no transaction, holds no session state, or consumes no connection resources.

A pooled connection can normally Sleep while waiting for reuse. A connection that sleeps for a long time while still holding an open transaction can retain snapshots, hold locks, or grow undo history. Check transaction metadata before concluding such a connection is harmless.

## 6. Example of Reading a Process List

Run:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Suppose the illustrative rows appear:

| Id | User | Command | Time | State | Info |
|---:|---|---|---:|---|---|
| 101 | app_user | Sleep | 12 | NULL | NULL |
| 102 | app_user | Query | 3 | Sending data | SELECT ... |
| 103 | report_user | Query | 48 | Waiting for table metadata lock | ALTER/SELECT ... |
| 104 | app_user | Sleep | 420 | NULL | NULL |

Preliminary interpretation:

- ID 101 is waiting for the client to send a new command; 12 seconds of Sleep is not an incident by itself.
- ID 102 is executing a query; Sending data may include reading and processing rows, not just sending bytes over the network.
- ID 103 is blocked by a metadata lock; the long duration does not mean the statement is continuously burning CPU.
- ID 104 has been in Sleep for a long time; check whether an open InnoDB transaction exists before closing the connection.

The table above contains illustrative data only. Specific states vary by statement, engine, and MySQL version.

## 7. SHOW FULL PROCESSLIST Is Not a Query Timer

Do not interpret Time as the exact total SQL execution duration in all cases:

- A thread can transition through multiple states within a single statement.
- A statement may wait on a lock for a long time before executing its work.
- Time reflects duration in the current state as reported by the process list.
- A query that finishes before the snapshot is taken will no longer appear.
- A connection sleeping for a long time may have no active SQL statement.

To measure statement duration and rows examined, inspect events_statements_current or history in Performance Schema if the corresponding instrumentation and consumers are enabled.

## 8. Common States

| State | Practical Interpretation |
|---|---|
| Sending data | Thread is reading, processing, or sending results; not solely network transfer |
| Creating sort index | Building structures for sorting or ordering |
| Sorting result | Sorting query results |
| statistics | Gathering/evaluating information for plan selection |
| Waiting for table metadata lock | Waiting for a metadata lock on an object |
| Waiting for ... lock | Waiting for the lock or resource type named in the state |
| Creating tmp table | Creating a temporary table for query processing |
| Copying to tmp table | Writing data into a temporary table |
| Sleep | Connection waiting for a new command from the client |

The list of states is not fixed and can change across MySQL versions. Do not diagnose solely from a state name; inspect the associated SQL, transaction, lock metadata, and statement history.

### Sending data Does Not Mean Only Sending Results

The state name is misleading. During this phase, MySQL may read rows from the storage engine, evaluate conditions, perform joins, compute expressions, and produce output. A query stuck in Sending data for a long time may be scanning many rows or executing expensive joins, not necessarily experiencing slow networking.

### Waiting for table metadata lock

This state typically appears when a statement needs a metadata lock while another transaction or statement holds a conflicting lock. For example, DDL such as ALTER TABLE may wait for an active transaction using the table to finish. Inspect pending metadata locks and holders before deciding on remediation.

## 9. Filtering the Process List with Performance Schema

Starting in MySQL 8.0.22, Performance Schema provides the performance_schema.processlist table as a process list interface. This table is suitable for filtering, sorting, and joining with other metadata using SQL.

INFORMATION_SCHEMA.PROCESSLIST was deprecated in MySQL 8.0.22. For structured queries, prefer performance_schema.processlist or performance_schema.threads instead of building new tooling on the legacy INFORMATION_SCHEMA table.

Example: viewing only non-Sleep connections:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM performance_schema.processlist
WHERE COMMAND <> 'Sleep'
ORDER BY TIME DESC;
~~~

Viewing long-sleeping connections:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    TIME AS sleep_seconds
FROM performance_schema.processlist
WHERE COMMAND = 'Sleep'
ORDER BY TIME DESC;
~~~

These queries only filter the current snapshot. What constitutes a long Sleep threshold must be defined according to connection pools, timeouts, and application characteristics; no single threshold fits every system.

## 10. Using performance_schema.threads

performance_schema.threads holds MySQL thread metadata. For client threads, the PROCESSLIST_* columns provide information similar to the process list:

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
ORDER BY PROCESSLIST_TIME DESC;
~~~

Distinction:

- THREAD_ID is the internal Performance Schema identifier.
- PROCESSLIST_ID is the connection ID visible to clients and used in the process list.

When joining statement events, use THREAD_ID. When correlating with SHOW PROCESSLIST or transaction metadata, typically use PROCESSLIST_ID.

Do not confuse internal InnoDB background threads with client connections. Filter on TYPE = 'FOREGROUND' and PROCESSLIST_ID IS NOT NULL to focus on client connections.

## 11. Getting the Current Statement and Execution Metrics

performance_schema.events_statements_current records a thread's current statement event if the relevant instrumentation/consumer is enabled:

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_COMMAND AS command_name,
    t.PROCESSLIST_TIME AS processlist_seconds,
    t.PROCESSLIST_STATE AS processlist_state,
    esc.SQL_TEXT,
    esc.ROWS_EXAMINED,
    esc.ROWS_SENT,
    esc.ROWS_AFFECTED,
    esc.LOCK_TIME
FROM performance_schema.threads AS t
LEFT JOIN performance_schema.events_statements_current AS esc
    ON esc.THREAD_ID = t.THREAD_ID
WHERE t.TYPE = 'FOREGROUND'
  AND t.PROCESSLIST_ID IS NOT NULL
  AND t.PROCESSLIST_COMMAND <> 'Sleep'
ORDER BY t.PROCESSLIST_TIME DESC;
~~~

For an active event, TIMER_END and TIMER_WAIT may not yet have final values; therefore, current-event queries focus on SQL and row counters rather than using TIMER_WAIT to claim final completion duration. In completed statement history, TIMER_WAIT is expressed in picoseconds; divide by 10^12 to convert to seconds. PROCESSLIST_TIME and TIMER_WAIT measure two different things with different semantics and are not interchangeable.

Some columns may be NULL if statement events are not captured or instrumentation is disabled. SQL_TEXT may also be truncated by the configured SQL text length limit. Check consumers and instruments before concluding no statements exist.

## 12. Viewing Recent Statement History

events_statements_current reflects only the current event. To inspect recently completed statements, query events_statements_history or events_statements_history_long if the corresponding consumers are enabled:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 3) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    ROWS_AFFECTED
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
  AND TIMER_WAIT IS NOT NULL
ORDER BY TIMER_END DESC
LIMIT 50;
~~~

History is a bounded buffer, not long-term storage. Older entries are overwritten as workload continues. If you need history for auditing or long-term analysis, design a dedicated collection pipeline and control sensitive data in SQL text.

## 13. Sleep Connections with Open Transactions

This is a case requiring close attention. An application may:

1. Open a transaction with START TRANSACTION.
2. Read or update some rows.
3. Return the connection to the pool while forgetting COMMIT/ROLLBACK.
4. The connection transitions to Sleep because the client has not sent a new statement.

An InnoDB transaction can still exist even when the process list shows Command = Sleep. Long-running open transactions can hold row locks, retain read views, delay purge, and increase the amount of undo that must be maintained.

Cross-reference the process list with information_schema.innodb_trx:

~~~sql
SELECT
    p.ID AS connection_id,
    p.USER,
    p.HOST,
    p.COMMAND,
    p.TIME AS processlist_seconds,
    p.STATE,
    trx.trx_id,
    trx.trx_state,
    trx.trx_started,
    TIMESTAMPDIFF(SECOND, trx.trx_started, NOW()) AS transaction_age_seconds,
    trx.trx_rows_locked,
    trx.trx_rows_modified,
    trx.trx_query
FROM performance_schema.processlist AS p
JOIN information_schema.innodb_trx AS trx
    ON trx.trx_mysql_thread_id = p.ID
ORDER BY trx.trx_started;
~~~

If COMMAND is Sleep yet the join still returns a transaction, the connection is idle in the process list while its transaction remains open. Check the owner, transaction age, and lock impact before intervening.

## 14. Distinguishing Running Queries from Lock-Waiting Queries

A thread with Command = Query means the connection is processing an SQL command. It might be:

- Reading and processing rows.
- Sorting or building a temporary table.
- Waiting on an InnoDB row lock.
- Waiting on a metadata lock.
- Waiting on I/O or another resource.

Therefore, Query does not equate to active CPU execution. Check State, statement events, and lock metadata.

### Checking Pending Metadata Locks

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_STATE AS processlist_state,
    ml.OBJECT_TYPE,
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS
FROM performance_schema.metadata_locks AS ml
JOIN performance_schema.threads AS t
    ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.LOCK_STATUS = 'PENDING'
ORDER BY t.PROCESSLIST_ID;
~~~

PENDING is a lock request not yet granted. To identify the blocker, inspect GRANTED locks on the same object and the transactions/statements holding them. Do not conclude from a single PENDING row that the thread is blocked by an InnoDB row lock; metadata locks are a different lock type.

### Checking InnoDB Lock Waits

MySQL 8.0 provides performance_schema.data_lock_waits and performance_schema.data_locks to observe InnoDB lock waits. data_lock_waits links waiting locks to blocking locks:

~~~sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx_id,
    req.THREAD_ID AS waiting_thread_id,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx_id,
    blk.THREAD_ID AS blocking_thread_id,
    blk.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Then join THREAD_ID with performance_schema.threads to get the connection ID and user. This describes InnoDB data locks; metadata locks are inspected through performance_schema.metadata_locks.

## 15. Why the Process List May Not Be Enough

The process list has several limitations:

- It is only a point-in-time snapshot when read.
- It does not store full statement history.
- TIME is not CPU time.
- INFO may be NULL or truncated in length.
- A Query row may be waiting on a lock or I/O.
- A Sleep connection may still hold an open transaction.
- It does not fully report rows examined, wait events, or execution stages.

For deeper analysis, combine:

| Source | Question Answered |
|---|---|
| SHOW FULL PROCESSLIST | Which connections are in what state right now? |
| performance_schema.processlist | How can the process list be filtered/sorted? |
| performance_schema.threads | How do internal threads map to connection IDs? |
| events_statements_current | How many rows is the current statement reading, and how long has it run? |
| events_statements_history_long | Which statements ran recently? |
| information_schema.innodb_trx | Which transactions are open, and when did they start? |
| metadata_locks | Which threads are waiting on metadata locks? |
| data_lock_waits | Which transaction is waiting and which transaction is blocking it? |
| SHOW ENGINE INNODB STATUS | What lock waits/deadlocks and internal state does InnoDB currently have? |

## 16. SHOW ENGINE INNODB STATUS for InnoDB Context

When suspecting a lock wait or deadlock, the following command provides a snapshot of InnoDB status:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

In clients supporting vertical output, you can use:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Focus on the TRANSACTIONS, LATEST DETECTED DEADLOCK, and lock wait sections. This is a summary report and does not replace structured queries against Performance Schema. The deadlock report typically retains only the most recently recorded deadlock.

## 17. KILL QUERY and KILL CONNECTION

After identifying the right thread and its impact, MySQL provides two distinct operations:

~~~sql
KILL QUERY 12345;
KILL CONNECTION 12345;
~~~

- KILL QUERY stops the connection's current statement while keeping the connection alive.
- KILL CONNECTION terminates the connection; any uncommitted transaction may have to roll back.

Do not KILL simply because a row shows a high Time value. First check the user, host, SQL, transaction age, held locks, and owning application. Rolling back a large transaction can take time and generate significant extra I/O.

Especially for a Sleep connection holding an open transaction, KILL QUERY usually does not resolve the problem because no statement is actively running. If you decide to terminate the connection, understand the rollback cost and application impact.

## 18. Workflow for Investigating a Slow Query

1. Capture SHOW FULL PROCESSLIST to record connection ID, user, host, command, time, state, and SQL.
2. Determine whether the thread is in Sleep or processing a command.
3. If it is Query, read State to distinguish data processing from waiting on locks/resources.
4. Query performance_schema.processlist and threads to filter relevant threads.
5. Read events_statements_current to inspect SQL text, rows examined, rows sent, and statement duration if available.
6. Check innodb_trx to detect long-open transactions, including on Sleep connections.
7. If lock waits exist, check metadata_locks or data_lock_waits according to the lock type.
8. If needed, inspect SHOW ENGINE INNODB STATUS for InnoDB context.
9. Identify the blocker and owning application before intervening.
10. Record before/after results and verify whether workload recovers.

## 19. Common Misinterpretations

| Misconception | Why It Is Wrong | Proper Verification |
|---|---|---|
| Long Sleep always means a leaked connection | Connection pools may intentionally keep idle connections | Check pool settings, timeouts, and open transactions |
| Sleep means the transaction is closed | A session can be idle while a transaction remains open | Join innodb_trx |
| Query means CPU is running | The thread may be waiting on locks or I/O | Read State and Performance Schema waits |
| Sending data means only network transfer | State can include reading and processing rows | Check rows examined, plan, and stages |
| Time is total SQL duration | Time is duration in the current state | Cross-check statement timers/history |
| No SQL visible means no workload | Snapshots can miss short queries or Info is NULL/truncated | Use statement history and instrumentation |
| KILL QUERY always releases the transaction | Statement stops but connection/transaction may remain | Check transactions after KILL |
| One process list is enough to find blockers | Process list does not fully describe lock relationships | Use metadata_locks/data_lock_waits |

## 20. Security and Observation Overhead

The process list and statement history can contain literals, emails, account numbers, or sensitive information embedded in SQL. Therefore:

- Restrict the PROCESS privilege.
- Restrict Performance Schema read privileges following least privilege.
- Do not expose SQL text to public logs or dashboards without redacting sensitive data.
- Limit polling frequency; continuously querying the process list at high frequency adds load.
- Prefer filtered queries selecting only needed columns rather than scanning/displaying all metadata.
- Protect observability dashboards and logs as sensitive operational data.

Observation must be detailed enough to diagnose issues without exposing query contents or connection details to unauthorized personnel.

## 21. Hands-On Exercises

1. Run SHOW PROCESSLIST and SHOW FULL PROCESSLIST; compare the length of the Info column.
2. Identify Sleep and Query rows; explain the meaning of Command, Time, State, and Info.
3. Open two sessions; leave one in Sleep and observe the process list from the other.
4. In a test environment, open an InnoDB transaction and leave the connection idle; confirm the process list shows Sleep while innodb_trx still lists the transaction.
5. Query performance_schema.processlist to filter non-Sleep connections and sort by TIME.
6. Join performance_schema.threads with events_statements_current to retrieve SQL_TEXT, ROWS_EXAMINED, and ROWS_SENT.
7. Create a query waiting on a metadata lock in a test environment; verify the state and confirm metadata_locks has a PENDING request.
8. Observe an InnoDB lock wait and correlate data_lock_waits with the process list.
9. Compare KILL QUERY and KILL CONNECTION on a test connection; observe transaction rollback.
10. Write a slow-query investigation runbook covering snapshot, statement metrics, transactions, locks, and recovery verification.

You have completed this lesson when you can read the process list, distinguish Sleep connections from active statements, recognize when a statement is waiting rather than consuming CPU, and detect long-running open transactions on idle connections. The process list is the starting point for observation; reliable conclusions require cross-referencing statement, transaction, and lock metadata.
