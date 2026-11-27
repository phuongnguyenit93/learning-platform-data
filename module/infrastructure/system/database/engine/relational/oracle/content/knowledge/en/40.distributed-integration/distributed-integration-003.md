# Distributed Transactions, Two-Phase Commit, and In-Doubt Transactions in Oracle

A distributed transaction is a business transaction that performs changes across multiple databases or multiple resource managers yet must be treated as a single consistent unit. For example, an order is recorded in the sales database while simultaneously deducting inventory in the warehouse database and posting a journal entry in the finance database. If only one site commits while another rolls back, business data becomes inconsistent.

Oracle supports distributed transactions through database links and the **two-phase commit (2PC)** mechanism. When a transaction modifies data across multiple databases, Oracle coordinates the participants to reach a unified commit or rollback decision. 2PC has two phases: prepare so each participant ensures it can commit, and then commit/rollback to finalize the agreed decision.

If the coordinator or a participant loses connection right as the commit decision is being propagated, a database may not know the final outcome. The transaction is then in an **in-doubt** state. Oracle retains transaction information and may hold related locks until the decision is recovered. The background process RECO (Recoverer) automatically attempts to resolve pending distributed transactions once connectivity between sites is restored.

In-doubt does not mean the transaction definitely committed or rolled back. A DBA must never arbitrarily run `FORCE COMMIT`/`FORCE ROLLBACK` just to clear an entry or release locks. You must determine the global decision from the coordinator/participants, transaction IDs, commit records, and business evidence before intervening manually.

This lesson belongs to the **Distributed Integration** topic of *Database Engine Relational Oracle*. The content focuses on:

- Distributed transactions and database links.
- Roles of coordinator, participant, and commit point site.
- The prepare and commit/rollback phases of 2PC.
- Read-only participant optimization and transaction consistency.
- In-doubt transactions, locks, and RECO.
- `DBA_2PC_PENDING`, `DBA_2PC_NEIGHBORS`, and monitoring views.
- `COMMIT FORCE`, `ROLLBACK FORCE`, and the risks of wrong decisions.
- Recovery procedures when networks/sites/databases fail.
- Multi-database lab, fault scenarios, and operational checklists.

## 1. What Is a Distributed Transaction?

A local transaction modifies data within only one database. A distributed transaction can modify data across multiple different databases while the application wants them to have an atomic outcome: either all commit or all roll back.

### Business Example

An application transferring stock between two branches:

1. Warehouse database A decreases stock quantity.
2. Warehouse database B increases stock quantity.
3. Accounting database records the transfer.

If steps 1 and 2 commit while step 3 rolls back, accounting figures mismatch. If database A commits while B rolls back, inventory disappears from total stock. A distributed transaction coordinates the decision to avoid partial states.

### Oracle Database Links

A database link allows a session in one database to access objects in another database:

~~~sql
SELECT *
FROM products@warehouse_link
WHERE product_id = 100;
~~~

A database link can be used for remote queries or executing DML:

~~~sql
UPDATE inventory@warehouse_link
SET quantity = quantity - 1
WHERE product_id = 100;
~~~

When a transaction only reads remote data, it is a distributed query. When a transaction performs DML on a remote database and has local/remote changes that must commit together consistently, Oracle can use the distributed transaction protocol.

### Example Modifying Local and Remote in the Same Transaction

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

UPDATE inventory@warehouse_link
SET reserved_qty = reserved_qty + 1
WHERE product_id = 100;

COMMIT;
~~~

The application issues a single `COMMIT`. Oracle coordinates the participating databases to reach a global commit decision. If the transaction rolls back before commit, Oracle instructs participating changes to roll back.

### A Distributed Query Is Not Always a Distributed Transaction

A `SELECT` over a database link may read multiple databases without necessarily creating a distributed transaction requiring a 2PC commit. The key factor is whether the transaction modifies data across multiple participants and requires an atomic commit. A remote DML statement still joins the session's transaction; when the transaction spans multiple databases, Oracle must coordinate the commit.

## 2. Components of a Distributed Transaction

### Global Coordinator

The coordinator orchestrates the distributed transaction. In Oracle, the site initiating the transaction typically takes the coordinating role and tracks participant states. The coordinator initiates prepare, collects votes, and decides commit or rollback according to the protocol.

### Participant

A participant is each database taking part in the transaction and performing a portion of the work. Each participant must ensure its changes can commit or roll back according to the global decision.

### Commit Point Site

In Oracle 2PC, one participant is selected as the commit point site. This site plays a special role during the commit phase and may commit before other participants after all have prepared. Remaining sites then complete according to the recorded decision.

Oracle selects the commit point site based on the `COMMIT_POINT_STRENGTH` parameter of participating databases; the site with the highest strength is chosen according to Oracle's rules. To understand tie-breaking/selection details, check the documentation for your exact release.

### RECO

RECO is the Recoverer background process. It monitors and automatically attempts to resolve in-doubt distributed transactions once communication between participating databases is restored. RECO uses stored transaction information and protocol state to determine the missing decision.

### Overview Diagram

~~~text
                 Application Session
                         |
                         v
                Coordinator Database
                   /            \
                  /              \
          Participant A       Participant B
          Remote DB link      Remote DB link
                  \              /
                   \            /
               Global transaction
                Prepare / Commit
~~~

A transaction can have many participants and multiple layers of database links. The more sites, network hops, and coordinator dependencies involved, the more complex error investigation becomes.

## 3. Two-Phase Commit (2PC)

2PC is the protocol that coordinates commits across multiple participants. Oracle uses this protocol to guarantee atomicity of a distributed transaction when databases must commit together.

### Phase 1: PREPARE

The coordinator asks participants to prepare to commit. Each participant:

- Completes necessary work to confirm the transaction can commit.
- Writes required information to redo/transaction metadata so the decision can be recovered.
- Holds necessary locks to protect changes while awaiting the outcome.
- Votes `YES` if it can commit, or `NO` if it cannot.

A `YES` vote means the participant is prepared and guarantees it can complete the commit when it receives the global decision. It does not mean the transaction has already committed.

### Phase 2: COMMIT or ROLLBACK

If all required participants vote `YES`, the coordinator decides `COMMIT`. The commit decision is durably recorded and sent to participants. If any participant votes `NO` or an error prevents continuing under the protocol, the coordinator decides `ROLLBACK`.

Participants receiving the decision complete the commit/rollback, release locks, and report status. The coordinator tracks progress until participants finish.

### Two-Phase Diagram

~~~text
Coordinator                    Participants
     |                               |
     |--------- PREPARE ------------>|
     |                               |
     |<--------- YES / NO ------------|
     |                               |
     |   All required votes YES?     |
     |          /       \            |
     |        YES        NO          |
     |         |          |          |
     |------ COMMIT ---- ROLLBACK -->|
     |                               |
     |<------ completion ------------|
~~~

Conceptual illustration; specific messages, log records, and internal states are managed by Oracle.

### Why Is PREPARE Necessary?

If the coordinator sent `COMMIT` directly to each site without preparing, one participant might encounter a constraint/space/transaction error after another site had already committed. Prepare lets each participant confirm upfront that it can commit, and then hold the required state while awaiting the decision.

### Durability of the Decision

2PC relies on logs/redo to recover decisions after a crash. A prepared participant may have to hold locks across restarts until the outcome is received. This is why an in-doubt transaction can block applications even after a database has restarted.

## 4. Transaction Lifecycle and States

Common conceptual states in a distributed transaction:

| State | Meaning |
| --- | --- |
| Active | The transaction is performing local/remote work. |
| Preparing | The coordinator requests participants to prepare. |
| Prepared | The participant has voted `YES` and is awaiting the final decision. |
| Committed | The participant has completed committing. |
| Aborted/Rolled back | The transaction has rolled back. |
| In-doubt | One or more sites cannot determine/complete the global decision due to communication loss or crash. |

In the Oracle data dictionary, `DBA_2PC_PENDING` displays pending/in-doubt transactions and state details. `STATE` in the view can show values such as `collecting`, `prepared`, `committed`, `forced commit`, or `forced rollback` depending on the situation/release. Do not infer state from conceptual names; inspect actual values and Oracle documentation.

### Prepared Participants Hold Locks

A participant that voted `YES` cannot unilaterally roll back just because the coordinator lost connection. It has promised it can commit if the global decision is commit. Consequently, the transaction can hold row/table locks and cause other transactions to wait.

### In-Doubt Does Not Necessarily Mean a Broken Database

A database can remain `OPEN` and serve other transactions while one distributed transaction is in-doubt. However, locks on affected rows can impact part of the workload. Investigate the specific transaction instead of repeatedly restarting the database.

## 5. Commit Point Site and Commit Point Strength

The commit point site is the participant chosen to commit first under Oracle 2PC rules. Selecting this site gives the protocol a durable decision point for remaining participants to follow.

### COMMIT_POINT_STRENGTH

The `COMMIT_POINT_STRENGTH` parameter determines a database's strength when Oracle selects the commit point site. Higher values have higher priority under Oracle's rules.

Check:

~~~sql
SHOW PARAMETER commit_point_strength;

SELECT name, value
FROM v$parameter
WHERE name = 'commit_point_strength';
~~~

### Do Not Change Strength Arbitrarily

`COMMIT_POINT_STRENGTH` is a setting affecting commit point selection in distributed transactions. Do not change it merely to "prioritize" a more important database without understanding the impact, participation scope, and recovery procedures. Specific values must be governed consistently by design.

### Commit Point Site Is Not the Application Coordinator

The site initiating a distributed transaction and the commit point site are two distinct roles. The coordinator orchestrates the protocol; the commit point site is the participant selected as the first commit point. Do not confuse the commit point site with the application server or the database receiving the initial request.

## 6. Read-Only Participant Optimization

A participant that only reads remote data and has no changes to commit can be treated as a read-only participant. Oracle can optimize the protocol so read-only participants do not need to go through full prepare/commit steps like participants performing DML.

### Example

~~~sql
SELECT customer_name
INTO l_customer_name
FROM customers@crm_link
WHERE customer_id = p_customer_id;

UPDATE orders
SET customer_name = l_customer_name
WHERE order_id = p_order_id;
~~~

The CRM participant only reads; the local database has modifications. Oracle can use read-only optimization depending on transaction structure. If a remote participant has DML, it must participate in 2PC.

### Read-Only Optimization Is Not General Distributed Read Consistency

Read-only participant optimization in 2PC does not mean every `SELECT` across multiple databases shares a single SCN snapshot or cannot see data changes across sites. Distributed query consistency has its own rules; if business logic requires a consistent snapshot, you must understand SCNs, transaction isolation, and release capabilities.

## 7. How Oracle Records Distributed Transactions

Oracle stores necessary information to track transaction branches in each database. When a transaction completes normally, transaction management records are cleaned up via internal mechanisms. When an error occurs during 2PC, metadata may be retained so RECO can continue recovery.

### Local Transaction ID and Global Transaction ID

- `LOCAL_TRAN_ID` identifies the transaction branch within the current database.
- `GLOBAL_TRAN_ID` links branches belonging to the same global distributed transaction.
- A single global transaction can have multiple local transaction IDs, one per participant.

Never use database A's local transaction ID to force a transaction on database B unless that ID is the exact corresponding branch on B. Collect IDs and neighbor information at each participant.

### DBA_2PC_PENDING

`DBA_2PC_PENDING` lists pending/in-doubt distributed transactions in the current database. Key columns:

| Column | Meaning |
| --- | --- |
| `LOCAL_TRAN_ID` | ID of the transaction branch in the current database. |
| `GLOBAL_TRAN_ID` | Global ID used to link branches. |
| `STATE` | State of the pending branch. |
| `MIXED` | Indicates potential for a mixed outcome. |
| `ADVICE` | Transaction advice if provided. |
| `TRAN_COMMENT` | Comment attached to the transaction if any. |
| `FAIL_TIME` | Time when failure/pending state was detected. |
| `FORCE_TIME` | Time when a force operation was performed, if any. |
| `RETRY_TIME` | Time of most recent retry per metadata. |
| `DB_USER` | Associated database user. |

Check:

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       tran_comment,
       fail_time,
       force_time,
       retry_time,
       db_user
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

Column names/structures can vary by release; run `DESC DBA_2PC_PENDING` to confirm before building monitoring scripts. This view only shows state in the current database; it cannot itself supply the global decision if the coordinator/other participants are unreachable.

### DBA_2PC_NEIGHBORS

`DBA_2PC_NEIGHBORS` describes neighbor databases participating in the branch, including connection direction and related site information.

~~~sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface,
       dbid,
       sess#,
       branch
FROM dba_2pc_neighbors
ORDER BY local_tran_id, in_out;
~~~

`IN_OUT` typically distinguishes inbound/outbound neighbors in the protocol relationship. `DATABASE` and `DBID` help identify the remote database; `INTERFACE` describes the connection/participant interface in metadata. Check `DESC` on your exact release to confirm available columns.

### Viewing Both Pending Transactions and Neighbors

~~~sql
SELECT p.local_tran_id,
       p.global_tran_id,
       p.state,
       p.mixed,
       n.in_out,
       n.database,
       n.dbid
FROM dba_2pc_pending p
LEFT JOIN dba_2pc_neighbors n
  ON n.local_tran_id = p.local_tran_id
ORDER BY p.local_tran_id, n.in_out;
~~~

This is the local perspective. To understand the full transaction, a DBA typically must connect to each involved database and correlate global ID, local branch IDs, states, and neighbor records.

## 8. RECO Automatically Resolving In-Doubt Transactions

RECO (Recoverer) is the Oracle background process responsible for automatically resolving in-doubt distributed transactions. When a database has a pending transaction branch, RECO periodically attempts to connect to the required participants/coordinator to obtain the final decision.

### What Does RECO Do?

- Detects transaction branches needing recovery.
- Attempts to connect to neighbor databases.
- Exchanges global transaction state/decision information.
- Completes committing or rolling back the branch according to the recorded decision.
- Cleans up pending metadata once the entire protocol resolves.

### What Does RECO Need to Work?

- Involved databases must be reachable via Oracle Net/database links as configured.
- TNS/service resolution must be valid.
- Listeners, network, firewalls, and credentials/remote authentication must work.
- Participant databases must be open in an appropriate state for recovery.
- Transaction metadata must not have been deleted or improperly forced at one site.

### Monitoring the Background Process

~~~sql
SELECT pname, description, tracefile
FROM v$process
WHERE pname LIKE 'RECO%';
~~~

Process naming/display depends on platform/version. You can inspect background processes via `V$BGPROCESS`:

~~~sql
SELECT name, description
FROM v$bgprocess
WHERE name = 'RECO';
~~~

If RECO fails to resolve a transaction, inspect alert logs and trace files for connection, authentication, or participant state errors.

### Do Not Try to Restart RECO Like an Application Process

RECO is a background process managed by Oracle. Do not kill the RECO OS process or manipulate internal transaction tables directly. Restore network/database connectivity and let Oracle retry. If intervention is needed, use Oracle-supported commands/documented packages.

### Retry Timing

RECO retries according to internal mechanisms and Oracle release parameters/configuration. Do not set a fixed SLA like "will auto-resolve in N seconds". Monitor `RETRY_TIME`, alert logs, networking, and remote site health.

## 9. Investigating In-Doubt Transactions in Order

When an in-doubt transaction is detected, the most important task is determining the global decision. Never force on one participant before gathering evidence from all sites.

### Step 1: Record the Transaction Branch

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time,
       db_user,
       tran_comment
FROM dba_2pc_pending;
~~~

Record `LOCAL_TRAN_ID`, `GLOBAL_TRAN_ID`, `STATE`, `MIXED`, timestamps, and user.

### Step 2: Identify Neighbors

~~~sql
SELECT local_tran_id,
       in_out,
       database,
       dbid,
       branch
FROM dba_2pc_neighbors
WHERE local_tran_id = :local_tran_id;
~~~

Identify the coordinator and remaining participants from neighbor details. If the view is insufficient, use transaction comments, application logs, database link names, alert logs, and application transaction data.

### Step 3: Check Connectivity to Each Site

Check TNS aliases/services, listeners, network routes, firewalls, DNS, credentials, and database availability. An in-doubt transaction often resolves automatically once sites can communicate again.

### Step 4: Check State on All Participants

Connect to every involved database and query `DBA_2PC_PENDING`/`NEIGHBORS`. Compare `GLOBAL_TRAN_ID`, local branches, states, commit numbers if available, and log records. Never rely on just one site.

### Step 5: Find the Coordinator's Decision

Identify the coordinator/commit point site and determine whether the transaction committed or rolled back. Check alert logs, traces, application logs, and branch states. If the coordinator completed commit, pending participants must be committed; if the decision was rollback, all branches must roll back.

### Step 6: Restore Connectivity

Fix database links/TNS/services/network/authentication. Then allow RECO to retry and monitor `DBA_2PC_PENDING` until the transaction resolves.

### Step 7: Consider FORCE Only with Evidence

If connectivity cannot be restored or the coordinator no longer exists, the DBA needs a manual decision process grounded in authoritative logs/evidence. Only when commit or rollback is confirmed with certainty should you run `FORCE COMMIT`/`FORCE ROLLBACK` for the corresponding branch.

### Document the Incident Record

- Global transaction ID and all local transaction IDs.
- List of participant databases and commit point site.
- State of each branch.
- Evidence of commit/rollback decision.
- Timestamps of network/database outage and recovery.
- Force commands (if any), operator, and approvals.
- Business data reconciliation after completion.

## 10. COMMIT FORCE and ROLLBACK FORCE

Oracle provides force commands for DBAs to resolve an in-doubt transaction branch when RECO cannot complete automatically and the global decision has been confirmed via reliable evidence.

### COMMIT FORCE

If evidence shows the global transaction committed and the current branch is merely pending, you can force this branch to commit:

~~~sql
COMMIT FORCE 'local_tran_id';
~~~

Syntax example:

~~~sql
COMMIT FORCE '12.34.567';
~~~

The string in the example illustrates only the local transaction ID format; replace it with the actual `LOCAL_TRAN_ID` from `DBA_2PC_PENDING` on the current database.

### ROLLBACK FORCE

If evidence shows the global decision was rollback, you can force the current branch to roll back:

~~~sql
ROLLBACK FORCE 'local_tran_id';
~~~

Do not use `COMMIT FORCE` simply to release locks, nor `ROLLBACK FORCE` simply because a transaction has been pending a long time. Force commands can push a branch opposite to the decision recorded at another site.

### FORCE Resolves the Local Branch

`FORCE COMMIT`/`ROLLBACK` applies to the transaction branch with that `LOCAL_TRAN_ID` in the current database. A single global transaction can have multiple branches. The DBA must identify and resolve pending branches across all participants following the same global decision.

### Before Forcing

You must have:

- Cross-checked global transaction ID and local branch IDs.
- Evidence of the commit/rollback decision from the coordinator or commit point site.
- States of remaining participants.
- Supporting alert/trace/application log records.
- Incident/change approval from an authorized person.
- A data reconciliation plan after forcing.

If the decision cannot be determined, do not force. Restore the coordinator/network or escalate the incident to senior DBAs/Oracle Support.

### After Forcing

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       force_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

Log the command, operator, and timestamp. RECO may still need to finish resolving neighbors; monitor the view until the transaction is cleaned up by Oracle's mechanisms. Never delete rows directly from `SYS` transaction tables.

## 11. Mixed Outcomes and Inconsistency Risks

`MIXED='YES'` in `DBA_2PC_PENDING` is a critical signal indicating branches of a global transaction may have ended with different outcomes—for instance, one participant committed while another rolled back or was forced in the opposite direction.

### Why Are Mixed Outcomes Dangerous?

Distributed transactions are designed to be atomic. If some branches commit and others roll back, the application can end up with mismatched business data:

- An order is confirmed while inventory is not deducted.
- Funds are debited in one database but not credited in another.
- A coordination record exists while a participant was never updated.

### How to Handle

1. Do not continue forcing other branches by guesswork.
2. Collect all local/global IDs across every participant.
3. Determine which branches committed and which rolled back.
4. Cross-check decision records, audits, redo/transaction states, and business data.
5. Build an approved compensation/reconciliation plan.
6. Only use Oracle-supported cleanup procedures after data state has been reconciled.

### Never Modify Internal Dictionary Tables

Never directly `DELETE`/`UPDATE` `SYS` tables related to transactions, pending transactions, or two-phase commit. Internal tables are not administrative APIs. Direct edits can corrupt metadata and prevent recovery from completing.

### PURGE_LOST_DB_ENTRY and PURGE_MIXED

`DBMS_TRANSACTION` provides procedures to manage certain pending/mixed entries in special recovery situations. These are consequential cleanup operations and must only be used per Oracle guidance after the transaction is identified, data is reconciled, and necessary branches are handled.

Do not use `PURGE_LOST_DB_ENTRY` to delete an in-doubt transaction still awaiting a decision. Do not use `PURGE_MIXED` to hide a mixed outcome before reconciling data. Check documentation for your exact release and consult Oracle Support before calling these procedures.

## 12. Distributed Locks and Application Impact

A prepared participant typically holds relevant locks until it receives the final decision. Other sessions may wait when accessing the same rows/tables or locked resources.

### Signs of Lock Contention

- `UPDATE`/`DELETE` hangs despite a simple SQL plan.
- Sessions wait for another transaction to end.
- Applications report timeouts or `ORA-02049`.
- `DBA_2PC_PENDING` has transactions in `prepared`/in-doubt state.
- Blocking sessions belong to a distributed transaction.

### Finding Blocking Sessions

~~~sql
SELECT sid,
       serial#,
       username,
       blocking_session,
       event,
       wait_class,
       seconds_in_wait,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

To view locks:

~~~sql
SELECT lo.session_id AS sid,
       lo.oracle_username,
       lo.locked_mode,
       ob.owner,
       ob.object_name,
       ob.object_type
FROM v$locked_object lo
JOIN dba_objects ob
  ON ob.object_id = lo.object_id
ORDER BY lo.session_id, ob.owner, ob.object_name;
~~~

These views help locate locked sessions/objects, though they do not alone prove the lock comes from an in-doubt transaction. Correlate `SID`, transaction IDs, `DBA_2PC_PENDING`, `V$TRANSACTION`, and the alert log.

### V$TRANSACTION and Transaction Metadata

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       t.xidusn,
       t.xidslot,
       t.xidsqn,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr;
~~~

`V$TRANSACTION` shows active transactions in the instance. An in-doubt branch may not appear as a normal active transaction after a restart; use `DBA_2PC_PENDING` to investigate pending branches.

### DISTRIBUTED_LOCK_TIMEOUT

`DISTRIBUTED_LOCK_TIMEOUT` specifies how long to wait for locks in certain distributed transaction operations before returning a timeout error (typically `ORA-02049`). Check:

~~~sql
SHOW PARAMETER distributed_lock_timeout;
~~~

This parameter is not RECO's retry interval and does not decide whether an in-doubt transaction commits or rolls back. Increasing the timeout only makes sessions wait longer; it does not fix a disconnected coordinator/participant or a branch holding locks.

### Do Not Kill Blockers as a First Resort

Killing a session does not guarantee resolving a prepared/in-doubt branch. Some actions only cause cleanup/rollback to take time or leave transaction metadata behind. Before killing, verify the session/transaction, coordinator role, participant state, and business impact.

## 13. Common Failure Scenarios Creating In-Doubt Transactions

### Coordinator Loses Connection After PREPARE

The participant voted `YES` and holds the `prepared` state, but never received the final decision. The branch can then become in-doubt and hold locks. Once the coordinator returns, RECO can exchange the decision and finish.

### Participant Loses Connection

The coordinator may have recorded the commit/rollback decision but cannot reach the participant. The participant can remain pending until network/database recovery allows RECO to obtain the decision.

### Database Restart During 2PC

After restart, Oracle reads transaction metadata from redo/transaction tables and resumes recovery. Prepared branches may remain in-doubt; do not arbitrarily roll back just because the instance restarted.

### Network Partition

Coordinator and participants may all be running yet unable to communicate. 2PC prioritizes atomicity, so prepared participants wait for the decision rather than deciding independently. This is the trade-off between consistency and availability during communication loss.

### Commit Point Site Failure

If the commit point site fails right as the commit decision is being recorded/propagated, participants may have to wait until that site recovers or the decision can be verified from logs/recovery. Never guess commit/rollback from the fact that an application received a timeout.

### Database Link or Authentication Changes

Changes to TNS aliases, service names, passwords, wallets, database link credentials, or `remote_listener` can prevent RECO from connecting. Fix the connection path and verify from the participant database, not just from a client machine.

## 14. Application Design to Reduce Distributed Transaction Risk

2PC provides atomic commits but carries costs in networking, logging, lock retention, and coordinator dependencies. Application design should minimize participant counts and transaction duration.

### Keep Transactions Short

- Open a distributed transaction only when executing the relevant DMLs.
- Never wait for user input, HTTP APIs, or long processing while holding a transaction.
- Avoid unnecessary reads/writes across multiple remote databases.
- Complete validation before starting the transaction when data permits.
- Explicitly commit/roll back; never leave open transactions in a connection pool.

### Reduce the Number of Participants

If a workflow updates 5 databases, each site adds a failure point and network dependency. Consider consolidating data sharing the same consistency boundary into one database, using appropriate service boundaries, or handling steps asynchronously when immediate atomicity is not required.

### Use Local Transactions Whenever Possible

If data can be managed within the same database/schema, local transactions are simpler and have fewer failure modes. Database links should not be the default way to tie every service/database together.

### Outbox Pattern

When a local change must emit an event to another system without requiring simultaneous commit across all databases, use a transactional outbox:

1. Within one local transaction, update business data and write an event to an outbox table.
2. Commit the local transaction.
3. A worker reads the outbox and sends the event to the target system.
4. The target system processes idempotently and acknowledges.
5. The worker marks the event sent or retries.

Outbox does not provide instantaneous cross-database atomic commit; it provides retryable eventual delivery, which is easier to operate in many integration scenarios.

### Sagas and Compensating Transactions

For long workflows spanning multiple services/databases, a Saga breaks the process into local transactions and defines compensating actions when a downstream step fails. For example, place order -> reserve inventory -> capture payment; if payment fails, release inventory via a compensating transaction.

Compensation is not a physical rollback of a committed transaction. It is a new business action to return the system to an acceptable state. Design explicit idempotency, retries, timeouts, deduplication, and workflow state.

### When Should You Still Use 2PC?

2PC fits when:

- Participating databases support distributed transactions and genuine atomicity is required.
- Transactions are short with a limited number of participants.
- Network/database infrastructure is reliable and well monitored.
- The organization has operational capability for RECO, in-doubt recovery, and incident response.
- Eventual consistency/compensation cannot satisfy business requirements.

### Retries Must Be Safe

A client timeout after `COMMIT` does not prove the transaction rolled back. Before retrying a financial/order operation, the application must check transaction status or use a business request ID/idempotency key to avoid duplicate execution.

## 15. Monitoring Distributed Transactions

Monitoring should cover pending transaction count, transaction age, state, `MIXED` flag, retry time, neighbor reachability, and lock impact.

### Counting Pending Transactions

~~~sql
SELECT state,
       mixed,
       COUNT(*) AS transaction_count,
       MIN(fail_time) AS oldest_fail_time,
       MAX(fail_time) AS newest_fail_time
FROM dba_2pc_pending
GROUP BY state, mixed
ORDER BY state, mixed;
~~~

### Finding the Oldest Pending Transactions

~~~sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       fail_time,
       retry_time,
       ROUND((SYSDATE - fail_time) * 24 * 60, 1) AS pending_minutes
FROM dba_2pc_pending
ORDER BY fail_time;
~~~

The time expression assumes `FAIL_TIME` is `DATE`; verify datatype with `DESC`. If `FAIL_TIME` is a timestamp in a specific release, use appropriate interval arithmetic.

### Viewing Neighbors of Pending Transactions

~~~sql
SELECT p.local_tran_id,
       p.global_tran_id,
       p.state,
       n.in_out,
       n.database,
       n.dbid
FROM dba_2pc_pending p
LEFT JOIN dba_2pc_neighbors n
  ON n.local_tran_id = p.local_tran_id
ORDER BY p.fail_time, p.local_tran_id;
~~~

### Monitoring RECO and Alert Logs

Inspect the alert log for RECO retry messages, connection errors, unreachable participants, or transaction resolution. Use ADRCI or `V$DIAG_ALERT_EXT` if privileged:

~~~sql
SELECT originating_timestamp,
       message_text
FROM v$diag_alert_ext
WHERE UPPER(message_text) LIKE '%RECO%'
   OR UPPER(message_text) LIKE '%IN-DOUBT%'
ORDER BY originating_timestamp DESC;
~~~

`V$DIAG_ALERT_EXT` is a diagnostic view; access privileges and columns may vary by release.

### Alert Thresholds

Alert on:

- Any transaction with `MIXED='YES'`.
- Pending transactions exceeding target age.
- Steadily increasing pending count.
- Unsuccessful RECO retries.
- Unreachable neighbor/database link.
- Rising lock waits and application timeouts.

Age thresholds should align with SLAs and workload; never automatically force-resolve a transaction after a fixed number of minutes.

## 16. Common Errors and Handling

| Error | Common Meaning | Handling Direction |
| --- | --- | --- |
| `ORA-02050` | Distributed transaction rolled back; some remote databases may remain in-doubt | Check `DBA_2PC_PENDING`/`NEIGHBORS` across all participants and let RECO resolve. |
| `ORA-02054` | Transaction in-doubt | Identify global/local transaction IDs, restore coordinator/network, do not force by guesswork. |
| `ORA-02055` | Distributed update operation failed; transaction must roll back | Roll back per transaction state and inspect remote branch. |
| `ORA-02049` | Timeout while distributed transaction waited for lock | Identify blocker, lock duration, transaction scope, and `DISTRIBUTED_LOCK_TIMEOUT`. |
| `ORA-02068` | Subsequent severe error from remote database | Read following errors and `ORA-02063`, inspect remote alert log. |
| `ORA-02063` | Preceding line originated from specified database link | Investigate root error on remote database; this is usually supplementary context. |
| `ORA-02019` | Connection description for remote database not found | Check database link, TNS alias, `tnsnames.ora`, and naming method. |
| `ORA-02085` | Database link connects to a different database name than expected | Check `GLOBAL_NAMES` and database link/remote database names. |
| `ORA-12154` | Could not resolve connect identifier | Check `TNS_ADMIN`, `tnsnames.ora`, LDAP/EZCONNECT, and service alias. |
| `ORA-12514` | Listener does not know requested service | Check service registration, listener, and connect descriptor. |
| `ORA-03113`/`ORA-03135` | Connection disconnected/timed out | Check network, processes, alert log, and remote database availability. |
| Long-pending transaction | Coordinator/participant unreachable or decision not yet exchanged | Check neighbors, RECO, network, and transaction states across sites. |
| Prolonged row lock | Prepared/in-doubt participant may be holding locks | Correlate session/transaction with `DBA_2PC_PENDING`; avoid arbitrary kill/force. |
| `MIXED='YES'` | Possible inconsistent outcomes across branches | Stop forcing, cross-check all sites, reconcile, and contact Oracle Support if needed. |

### Distinguishing Application Errors from In-Doubt

An application receiving an exception or timeout is not enough to conclude a global transaction is in-doubt. Query `DBA_2PC_PENDING`, check remote alert logs, and identify transaction branches. A network error can happen before `PREPARE`, during `PREPARE`, or after `COMMIT`; the consequences differ.

## 17. Operational Runbook When In-Doubt Is Detected

The runbook must prioritize automatic protocol recovery. `FORCE` is an exceptional step taken only after confirming the decision, never the first step.

### Phase A: Preserve and Triage

1. Record timestamp, application, request ID, and client error.
2. Identify the coordinator database, participants, and commit point site if known.
3. Query `DBA_2PC_PENDING` and `DBA_2PC_NEIGHBORS` on the database where the issue was spotted.
4. Record `LOCAL_TRAN_ID`, `GLOBAL_TRAN_ID`, `STATE`, `MIXED`, and `FAIL_TIME`.
5. Inspect alert logs/traces on involved databases.
6. Do not drop database links, users, or transaction metadata during investigation.

### Phase B: Restore Connectivity

1. Confirm database instances are up and running.
2. Verify listeners and service names.
3. Verify database links and remote authentication.
4. Check network routes, firewalls, DNS, and TLS/wallets if used.
5. Test connectivity from the proper database host/context.
6. Restore communication paths without altering transaction decisions.

### Phase C: Let RECO Complete

1. Monitor alert logs/RECO retries.
2. Query `DBA_2PC_PENDING` at reasonable intervals.
3. Confirm pending rows clear and locks release.
4. Verify state across participants.
5. Reconcile business outcome using the global transaction ID/request ID.

### Phase D: Manual Decision If Auto-Recovery Is Impossible

1. Confirm the coordinator/commit point site or decision evidence with certainty.
2. Verify pending local branches on each participant.
3. If decision is `COMMIT`, force commit required branches by each local transaction ID.
4. If decision is `ROLLBACK`, force roll back required branches by each local transaction ID.
5. Log all force commands and approvals.
6. Monitor RECO and check the `MIXED` flag.
7. If `MIXED='YES'` or the decision is unclear, stop and escalate to Oracle Support/specialist DBAs; create a reconciliation plan.

### Phase E: Verify Data and Close Incident

- Check row counts, statuses, balances, and business invariants across all databases.
- Reconcile the application request against the global transaction ID.
- Confirm no related pending branches remain.
- Check blocking sessions and locks.
- Document root cause, recovery time, and preventive actions.

## 18. Hands-On Lab: Distributed Transaction Over a Database Link

This lab requires two independent Oracle databases (`LOCALDB` and `REMOTEDB`), two lab schemas, and a private database link. Perform only in a learning environment. Never create public links or use production credentials.

### Step 1: Create Table in Remote Database

Connect directly to `REMOTEDB` using the lab schema:

~~~sql
CREATE TABLE lab_inventory (
    product_id NUMBER PRIMARY KEY,
    quantity NUMBER NOT NULL,
    CONSTRAINT ck_lab_inventory_qty CHECK (quantity >= 0)
);

INSERT INTO lab_inventory(product_id, quantity)
VALUES (100, 20);

COMMIT;
~~~

### Step 2: Create Table in Local Database

Connect to `LOCALDB` using the lab schema:

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    product_id NUMBER NOT NULL,
    order_qty NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL
);

INSERT INTO lab_orders(order_id, product_id, order_qty, status)
VALUES (9001, 100, 1, 'NEW');

COMMIT;
~~~

### Step 3: Create Private Database Link

In the local schema:

~~~sql
CREATE DATABASE LINK remote_lab_link
CONNECT TO remote_lab IDENTIFIED BY "<lab-secret>"
USING 'REMOTEDB_SERVICE';
~~~

Replace remote user, secret, and connect identifier with your lab configuration. Never store real passwords in source control or lesson files. The remote user needs privileges on specific objects; never grant `DBA`/`SYSDBA` to a database link account.

Verify:

~~~sql
SELECT * FROM dual@remote_lab_link;

SELECT product_id, quantity
FROM lab_inventory@remote_lab_link
WHERE product_id = 100;
~~~

### Step 4: Execute Distributed DML

~~~sql
UPDATE lab_orders
SET status = 'CONFIRMED'
WHERE order_id = 9001;

UPDATE lab_inventory@remote_lab_link
SET quantity = quantity - 1
WHERE product_id = 100
  AND quantity >= 1;

COMMIT;
~~~

In a real application, check `SQL%ROWCOUNT` of the remote DML to ensure exactly one row was updated; if the condition is not met, roll back the transaction. This lab focuses on demonstrating a single `COMMIT` encompassing both local and remote changes.

### Step 5: Verify Both Databases

`LOCALDB`:

~~~sql
SELECT order_id, status
FROM lab_orders
WHERE order_id = 9001;
~~~

`REMOTEDB` (query directly or via link):

~~~sql
SELECT product_id, quantity
FROM lab_inventory
WHERE product_id = 100;
~~~

Results should show the order `CONFIRMED` and quantity decremented by exactly one unit.

### Step 6: Test Rollback

In `LOCALDB`:

~~~sql
UPDATE lab_orders
SET status = 'CANCELLED'
WHERE order_id = 9001;

UPDATE lab_inventory@remote_lab_link
SET quantity = quantity + 1
WHERE product_id = 100;

ROLLBACK;
~~~

Verify both databases retain the state prior to the rolled-back transaction. This is a normal rollback check, not yet an in-doubt simulation.

### Step 7: Observe Metadata During Normal Transactions

While a transaction is running, a second session with DBA privileges can observe transactions/locks. `DBA_2PC_PENDING` primarily shows pending/in-doubt branches, so a transaction that completes normally may leave no rows in the view after commit.

~~~sql
SELECT local_tran_id, global_tran_id, state, mixed
FROM dba_2pc_pending;
~~~

Seeing no rows after a normal commit is the expected result.

### Step 8: Drill In-Doubt Recovery in an Isolated Environment

Create a separate clone/lab and coordinate with the DBA managing both databases:

1. Enable logging/monitoring and record DBIDs, services, database links, and alert log locations.
2. Prepare a way to isolate the network between `LOCALDB` and `REMOTEDB` that can be toggled quickly, solely for the lab.
3. Execute distributed DML and coordinate fault injection right as 2PC `PREPARE`/decision is occurring.
4. Record client errors and check `DBA_2PC_PENDING`/`NEIGHBORS` on both sites.
5. Restore the network path.
6. Observe RECO retrying and the transaction resolving automatically.
7. Confirm data across both sites is consistent.

The exact timing to induce an in-doubt state cannot be guaranteed by an ordinary SQL statement; controlled fault injection or a scenario guided by a DBA/Oracle Support is required. Never kill processes or sever networks on a shared database to try creating this state.

### Step 9: Clean Up the Lab

`LOCALDB`:

~~~sql
DROP DATABASE LINK remote_lab_link;
DROP TABLE lab_orders PURGE;
~~~

`REMOTEDB`:

~~~sql
DROP TABLE lab_inventory PURGE;
~~~

Only drop objects created by the lab. If any pending transactions exist, resolve them before dropping links/users or cleaning up schemas.

## 19. Design and Operations Checklist

### Before Using Distributed Transactions

- Confirm the business process genuinely requires cross-database atomic commit.
- Minimize participant count and transaction duration.
- Verify database links, network, services, and authentication.
- Confirm participating databases support the appropriate distributed transaction protocol.
- Identify coordinator/participants/commit point site.
- Check backups, redo, alert logs, and monitoring.
- Define idempotency and retry behavior in the application.

### During Operations

- Monitor `DBA_2PC_PENDING` and `DBA_2PC_NEIGHBORS`.
- Alert on pending age and `MIXED='YES'`.
- Monitor RECO retries and network health.
- Monitor blocking sessions/locks.
- Ensure TNS/service/password rotations do not break recovery paths.
- Never kill sessions or force transactions without decision evidence.

### During Incidents

- Collect global/local IDs and all participant states.
- Restore connectivity first.
- Let RECO resolve automatically.
- Force only according to a verified decision.
- Reconcile business data in the event of a mixed outcome.
- Document the incident and re-drill the scenario.

## 20. Self-Check Questions

1. **What is a distributed transaction?** A transaction that modifies multiple databases/resource managers yet requires a single atomic outcome.
2. **What is a database link used for?** Allows a session to access objects in a remote database.
3. **What are the two phases of 2PC?** `PREPARE` and `COMMIT`/`ROLLBACK`.
4. **What does a participant voting YES mean?** The branch is prepared and can commit upon receiving the decision; it is not yet committed.
5. **What does the coordinator do?** Orchestrates prepare, collects votes, and propagates the global decision.
6. **What is the commit point site?** The participant selected to commit first under Oracle 2PC rules.
7. **What is `COMMIT_POINT_STRENGTH` used for?** Assists in selecting the commit point site.
8. **What is RECO?** The background process that automatically recovers in-doubt distributed transactions.
9. **Can an in-doubt transaction hold locks?** Yes, a prepared participant can hold locks until the final decision is received.
10. **What does `DBA_2PC_PENDING` display?** Pending/in-doubt distributed transaction branches in the current database.
11. **What does `DBA_2PC_NEIGHBORS` show?** Details on participant/neighbor databases associated with a branch.
12. **How do `LOCAL_TRAN_ID` and `GLOBAL_TRAN_ID` differ?** The local ID identifies the branch in one database; the global ID links the transaction across multiple sites.
13. **What does `MIXED='YES'` signal?** Possible inconsistent commit/rollback outcomes across branches; urgent reconciliation is needed.
14. **When is `COMMIT FORCE` used?** When the global decision is verified as commit yet the local branch remains in-doubt.
15. **When is `ROLLBACK FORCE` used?** When the global decision is verified as rollback and the local branch must be force-rolled back.
16. **Can you force based solely on a transaction pending for a long time?** No.
17. **What does `DISTRIBUTED_LOCK_TIMEOUT` control?** Lock wait timeout in certain distributed operations, not the RECO retry interval.
18. **Why shouldn't you delete directly from `SYS` transaction tables?** It can corrupt protocol metadata and leave recovery inconsistent.
19. **What is read-only participant optimization?** An optimization for participants that only read and have no changes to commit.
20. **Can 2PC cause blocking during a network partition?** Yes; prepared participants may wait for the decision to preserve atomicity.
21. **How does the outbox pattern differ from 2PC?** Outbox commits locally and emits events asynchronously, supporting eventual consistency instead of cross-database atomic commit.
22. **What does a Saga use when a step fails?** Compensating transactions to return the workflow to an acceptable business state.
23. **Does a client timeout after `COMMIT` prove rollback?** No; the transaction may have committed while the response was lost.
24. **Why do retries require an idempotency key?** To prevent duplicate business execution when the previous attempt's outcome is unknown.
25. **What is the first step when an in-doubt transaction appears?** Collect IDs/states/neighbors and restore connectivity—do not force immediately.

Distributed transactions over database links use two-phase commit to coordinate participating databases. Prepared participants hold state and locks until receiving the commit/rollback decision; if the coordinator or network fails, branches can become in-doubt. `DBA_2PC_PENDING` and `DBA_2PC_NEIGHBORS` provide investigation details, while RECO automatically attempts resolution once connectivity returns. `COMMIT FORCE`/`ROLLBACK FORCE` are only used after confirming the global decision; a `MIXED` outcome requires reconciliation and specialist support. For long-running or multi-service workflows, consider outbox/Sagas to reduce 2PC dependency. Good design requires short transactions, minimal participants, idempotent retries, monitoring of pending branches/locks, and periodic fault recovery drills.
