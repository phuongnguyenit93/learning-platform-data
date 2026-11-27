# Application Continuity, Replay, and Operations Unsafe to Repeat

## 1. Why Is Application Continuity Needed?

An application can lose its connection to Oracle Database while processing a request. Causes include an instance/node outage, network interruption, storage failure, service relocation, or planned database maintenance. From the application's perspective, a SQL statement may have been sent while no response ever came back.

The most dangerous scenario is **not knowing whether a transaction committed**. For example:

1. The application sends a command to record a payment.
2. The database executes `COMMIT` successfully.
3. The connection drops before the client receives the response.
4. The application sees only a connection error and does not know whether the transaction completed.
5. If the application blindly resubmits the entire operation, the customer could be charged twice.

**Application Continuity (AC)** masks many recoverable failures by recording database calls within a request, reconnecting to a valid database target, and replaying the necessary work. The goal is restoring the session and transaction to an equivalent state so the application continues as if the request merely experienced a brief delay.

Replay is not a mechanism that re-executes arbitrary application code from scratch. The Oracle driver, database service, and connection pool coordinate to capture, restore, and verify database calls. Middle-tier logic, external side effects outside the database, and non-recoverable states still demand careful design.

## 2. Core Concepts

### 2.1. Database Request

A database request is a unit of work submitted by an application to Oracle over a database connection. A request typically corresponds to the SQL, PL/SQL, and database calls serving one HTTP request or one business operation.

With a connection pool, request boundaries are commonly defined when:

- The application borrows a connection from the pool (checkout/borrow).
- The application performs database work.
- The application returns the connection to the pool (check-in/close).

Request boundaries matter because Oracle needs to know which call history belongs to one unit of work and when that history can be released.

### 2.2. Recoverable Error

Recoverable errors typically stem from infrastructure or connectivity outages independent of the business logic running—such as dropped connections, foreground/session errors, instance or node crashes, or network/storage outages.

Application Continuity handles only errors in the recoverable category and only while the request meets replay preconditions. Business errors such as invalid input, constraint violations, or application logic errors do not automatically become recoverable simply because AC is enabled on the driver.

### 2.3. Call History

While a request is protected, the replay driver records database calls and the results needed to reconstruct the session. Upon a recoverable error, the driver uses this history to rebuild state and replay calls in their original order.

Replay must ensure that results already observed by the application before the outage remain consistent. If the database returns different data or state from what the application already used to make decisions, Oracle rejects replay rather than proceeding with an inconsistent state.

### 2.4. Transaction Guard and Commit Outcome

Oracle may have durably written commit redo even though the client never received the response. Transaction Guard provides a post-outage queryable transaction outcome using a Logical Transaction ID (LTXID) to identify the transaction.

When `COMMIT_OUTCOME` is enabled on the service, commit outcomes are retained for the configured retention period. Application Continuity uses Transaction Guard to determine whether the last transaction committed, preventing re-execution of an already-completed transaction.

This is the key difference between controlled replay and an application naively retrying an `UPDATE`/`INSERT` after a connection error.

## 3. Stages of Application Continuity Operation

~~~text
Application sends database request
             |
             v
       NORMAL RUNTIME
       - identify request boundary
       - record database calls
       - track session/transaction state
             |
             v
       RECOVERABLE ERROR
       - session or connection lost
             |
             v
       RECONNECTION
       - driver detects recoverable error
       - find connection to valid service/target
       - Transaction Guard checks commit outcome
       - restore required session state
             |
             v
       REPLAY
       - replay call history in order
       - validate results and state
       - reject if cannot safely restore
             |
       +-----+------+
       |            |
       v            v
    SUCCESS       REJECT/FAIL
       |            |
       v            v
  Request resumes  Application receives
  from appropriate error and handles
  point            fallback
~~~

### 3.1. Normal Runtime

During normal execution, the driver identifies requests, captures call history, and tracks session state. With AC, request boundaries generally must be explicitly delineated. With Transparent Application Continuity, state tracking can detect implicit request boundaries under supported conditions.

### 3.2. Reconnection

When encountering a recoverable error, the driver seeks a fresh connection to a valid target for the service. The target must belong to a supported HA configuration and provide consistent data state.

If the last transaction may have issued `COMMIT`, Transaction Guard determines the outcome before replay to avoid re-executing a committed transaction.

### 3.3. Replay

The driver replays captured database calls in the required sequence. Oracle verifies session state and previously observed results. If replay succeeds, the application resumes the request. If replay cannot reproduce results the client already relied upon, replay is rejected and the application receives the error to handle.

### 3.4. AC Does Not Eliminate Error Handling

Applications must still handle:

- Non-recoverable errors, such as invalid input data.
- Requests rejected from replay because results or session state could not be restored.
- Timeouts exceeding the replay initiation timeout.
- Timeouts or lack of any eligible target.
- External side effects that occurred before the database transaction completed.
- Errors from external systems, message brokers, or payment providers.

Never design an application assuming that enabling AC means errors will never occur.

## 4. Application Continuity vs. Transparent Application Continuity

Oracle 19c distinguishes two primary modes:

- **Application Continuity (AC):** explicitly configured replay mode; the service typically sets `FAILOVER_TYPE = TRANSACTION`.
- **Transparent Application Continuity (TAC):** mode using state tracking to automatically identify and manage session state; the service sets `FAILOVER_TYPE = AUTO`.

| Criterion | Application Continuity | Transparent Application Continuity |
| --- | --- | --- |
| Service attribute | `TRANSACTION` | `AUTO` |
| State management | Relies on configuration, callbacks, and known application states | Automatically tracks and classifies session/transaction state |
| Request boundaries | Mandatory for AC | Recommended; can detect implicit boundaries under supported conditions |
| Application side effects | Calls replay from history; side effects must be evaluated and replay disabled where needed | State tracking detects certain application side effects and disables capture/replay for affected calls |
| Required application insight | Usually requires understanding session state and side-effecting calls | Reduces need for deep application knowledge via state tracking |
| Session state consistency | `DYNAMIC` or `STATIC` per manual AC design | `AUTO` is mandatory |
| Best suited for | Evaluated apps with clear request boundaries and replay behavior | Apps seeking automatic state tracking and minimal code changes |

TAC does not automatically make all side effects across external systems safe. Applications must still be tested for callouts, database links, autonomous transactions, and external integrations under your exact driver and service versions.

### 4.1. Configuring a Service for AC

Illustrative example with Oracle RAC:

~~~text
srvctl add service -db mydb -service app_ac
  -preferred inst1 -available inst2
  -failovertype TRANSACTION
  -failover_restore LEVEL1
  -commit_outcome TRUE
  -notification TRUE
  -drain_timeout 300
  -stopoption IMMEDIATE
~~~

### 4.2. Configuring a Service for TAC

~~~text
srvctl add service -db mydb -service app_tac
  -preferred inst1 -available inst2
  -failovertype AUTO
  -failover_restore AUTO
  -commit_outcome TRUE
  -notification TRUE
  -drain_timeout 300
  -stopoption IMMEDIATE
~~~

These are illustrative examples, not copy-paste commands for every database. Check whether your database is admin-managed or policy-managed, check PDBs, `PRIMARY`/`STANDBY` roles, existing services, and exact `SRVCTL` syntax for your Grid Infrastructure release.

### 4.3. Single-Instance Databases

For non-RAC databases, services can be managed via `DBMS_SERVICE`. Conceptual TAC configuration example:

~~~sql
DECLARE
    params DBMS_SERVICE.SVC_PARAMETER_ARRAY;
BEGIN
    params('FAILOVER_TYPE') := 'AUTO';
    params('FAILOVER_RESTORE') := 'AUTO';
    params('COMMIT_OUTCOME') := 'TRUE';
    params('AQ_HA_NOTIFICATIONS') := 'TRUE';
    params('REPLAY_INITIATION_TIMEOUT') := 600;
    params('RETENTION_TIMEOUT') := 86400;

    DBMS_SERVICE.MODIFY_SERVICE(
        service_name => 'APP_TIER_SERVICE',
        params       => params
    );
END;
/
~~~

The service name must exist and the caller must hold appropriate administrative privileges. Check `DBMS_SERVICE` documentation and service attributes for your exact release.

### 4.4. Key Service Attributes

| Attribute | Role |
| --- | --- |
| `FAILOVER_TYPE` | `TRANSACTION` for AC, `AUTO` for TAC |
| `FAILOVER_RESTORE` | Restores session state; `LEVEL1` typical for AC, `AUTO` for TAC |
| `COMMIT_OUTCOME` | Enables Transaction Guard commit outcome tracking |
| `RETENTION_TIMEOUT` | Duration to retain replay/commit outcome metadata per configuration |
| `REPLAY_INITIATION_TIMEOUT` | Time limit to initiate replay after a failure |
| `FAILOVER_DELAY` / `FAILOVER_RETRIES` | Controls retry/failover timing per service configuration |
| `AQ_HA_NOTIFICATIONS` / `notification` | Enables FAN/HA notifications for clients/pools |
| `DRAIN_TIMEOUT` / `STOP_OPTION` | Controls connection draining during service maintenance |

Choose values aligned with SLAs, expected outage durations, pool behavior, and request runtimes. Avoid timeouts too short that abort replay before the new target is ready, or excessively long timeouts that stall requests past SLAs.

## 5. Request Boundaries: Defining Replay Scope

### 5.1. Why Are Request Boundaries Needed?

Oracle needs to know where call history begins and ends. If one connection serves multiple requests without clear boundaries, history can grow unbounded or mix operations from unrelated units of work.

For AC, request boundaries are a strict requirement. When using Oracle connection pools such as UCP or OCI Session Pool, boundaries are typically integrated with connection checkout and check-in.

### 5.2. JDBC beginRequest and endRequest

Oracle JDBC provides explicit APIs:

~~~java
import java.sql.Connection;
import oracle.jdbc.OracleConnection;

Connection connection = dataSource.getConnection();
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

oracleConnection.beginRequest();

try {
    // JDBC calls belonging to the same database request.
    // Execute transaction and handle errors per application.
} finally {
    // Before endRequest, the transaction must finish:
    // COMMIT or ROLLBACK per business outcome.
    oracleConnection.endRequest();
    connection.close();
}
~~~

This snippet is an illustrative skeleton. In real applications, never place an unconditional `COMMIT` inside `finally`. Base `COMMIT`/`ROLLBACK` decisions on business state and Transaction Guard outcomes when required.

Oracle JDBC throws an error if `beginRequest` or `endRequest` is invoked while a local transaction remains open. Never call `endRequest` to mask an unresolved transaction.

### 5.3. Connection Pools

With UCP/WebLogic pools, a request normally starts on connection borrow and ends on connection return. Therefore:

- Borrow a connection at the start of the unit of work.
- Do not hold a connection across multiple independent requests without clear justification.
- Close/return the connection promptly.
- Never reuse a failed connection or one evicted by the pool.
- Let the pool reset/clean up session state as configured.

### 5.4. Implicit Request Boundaries in TAC

TAC can detect implicit boundaries whenever a session reaches a clean state, such as:

- No open objects/cursors outside supported conditions.
- Cursors returned to the statement cache.
- No active open transaction.
- Session state determined to be restorable.

Implicit boundaries reduce application code changes, yet they do not replace proper connection and session-state hygiene.

## 6. Operations Unsafe to Replay

A key aspect of replay is that database calls may be re-executed after a failure. A safe operation must preserve semantics when replayed, or else be detected and excluded from replay.

### 6.1. Calling External Systems: Email, HTTP, TCP, Files

Common examples:

- `UTL_SMTP`, `UTL_MAIL`: sending email.
- `UTL_HTTP`, `UTL_URL`: invoking endpoints or fetching URLs.
- `UTL_FILE`: writing files.
- `UTL_FILE_TRANSFER`: transferring files.
- `UTL_TCP`: sending data over TCP.
- `DBMS_PIPE`, `DBMS_ALERT`: inter-session messaging/notifications.
- `DBMS_FILE_TRANSFER`: copying files.
- Java callouts, `Process.exec`, or shell script invocations.
- Writing external tables or calling external services.

These actions produce durable side effects outside the database transaction. For example:

1. A procedure successfully sends an email.
2. The database transaction has not yet committed.
3. The session drops due to an outage.
4. Oracle replays the procedure.
5. The email is sent a second time.

A database `ROLLBACK` cannot unsend an email or un-transfer a file. Therefore, external side effects pose the highest risk during replay.

### 6.2. Autonomous Transactions

A procedure marked with `PRAGMA AUTONOMOUS_TRANSACTION` runs in an independent transaction from its caller. If the autonomous transaction commits an audit/log row and the main transaction then hits an outage and replays, the independent audit record may be inserted a second time.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit(p_message VARCHAR2) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

If this procedure executes inside a replayed request, audit rows may be written multiple times depending on replay mode and side-effect handling. Never assume an autonomous transaction rolls back with the parent transaction.

### 6.3. Writing Files or Sending Messages Outside the Database

A file written to a filesystem or a message published to an external broker persists even if the Oracle transaction rolls back.

When handling side effects:

- Attach a unique business event ID.
- Supply an idempotency key when the external API supports one.
- Check status before re-sending.
- Persist outbound intent in a transactional outbox.
- Use a separate worker to dispatch messages post-commit.
- Track delivery results and retry per receiver policy.

Never rely on the replay driver to magically turn email, HTTP calls, or file writes into exactly-once operations.

### 6.4. Synchronizing Multiple Sessions via Locks or Volatile Resources

Applications may use database locks, `DBMS_LOCK`, pipes, in-memory queues, semaphores, sockets, or volatile resources to coordinate across multiple sessions or data sources.

If session A holds a lock ensuring session B does not modify data, then A fails over and loses that lock, replaying A does not automatically know that session B already relied on the old lock. This can violate application exclusivity assumptions.

Do not enable replay for workloads whose correctness relies on multiple independent sessions holding volatile coordination state across an outage without a resynchronization mechanism.

### 6.5. Relying on Middle-Tier Wall Clocks

The driver replays database call history; it does not re-evaluate middle-tier timing logic.

Unsafe example:

~~~java
if (Instant.now().isBefore(deadline)) {
    updateOrder();
}
~~~

Suppose the request starts before the deadline, the outage outlasts the deadline, and the database call replays afterward. The `Instant.now()` check is not re-executed by the driver, while the database call may still replay. Behavior can violate application assumptions.

Solutions:

- Push time checks inside the database transaction/call when appropriate.
- Capture the decision timestamp as an immutable request input.
- Pass explicit timestamps/deadlines as bind variables.
- Never assume application server and database clocks stay perfectly synchronized.

### 6.6. Assuming ROWID Never Changes

Applications should not persist `ROWID` long-term as a business key. `ROWID` can change during table reorganization, partitioning, migration, rebuilds, export/import, flashback, or restore.

Replay is rejected if returned `ROWID` values differ from what the application observed before the outage.

Use stable primary keys or business keys instead of persisting `ROWID` as a durable identifier.

### 6.7. Assuming Instance, SID, or Host Never Changes

After failover, a session may land on a different instance or node. Physical values such as:

- `SYS_CONTEXT('USERENV','INSTANCE')`
- `SYS_CONTEXT('USERENV','SID')`
- `SYS_CONTEXT('USERENV','SESSIONID')`
- `HOST`, `IP_ADDRESS`, `TERMINAL`

can change. If business logic branches on these values, replay may be rejected or yield unexpected outcomes.

Logical identifiers such as `CLIENT_IDENTIFIER`, `MODULE`, `ACTION`, and NLS settings are far better suited for request classification. Use physical locators only for diagnostics or callbacks, not as business keys.

### 6.8. Mutable Functions: Timestamps, GUIDs, and Sequences

Certain functions can return different values on each invocation:

- `SYSDATE`, `SYSTIMESTAMP`.
- `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`.
- `SYS_GUID`.
- `sequence.NEXTVAL`.

If replay returns new values instead of the values the application already observed before the outage, primary keys, foreign key binds, or client logic can become inconsistent.

Oracle 19c supports preserving original mutable values in supported scenarios. Configure `KEEP` appropriately, especially for PL/SQL:

~~~sql
GRANT KEEP DATE TIME TO app_user;
GRANT KEEP SYSGUID TO app_user;
GRANT KEEP SEQUENCE ON sales.order_seq TO app_user;
~~~

The sequence owner can also configure:

~~~sql
CREATE SEQUENCE order_seq KEEP;
~~~

Or:

~~~sql
ALTER SEQUENCE order_seq KEEP;
~~~

Notes:

- Oracle 19c does not require granting `KEEP` for sequence mutables at the SQL level per documented mechanics.
- PL/SQL enforces separate `KEEP` rules; grant appropriate privileges or configure the sequence.
- `KEEP SEQUENCE` is an object privilege on a specific sequence.
- `KEEP DATE TIME` and `KEEP SYSGUID` are system privileges.
- `GRANT ALL ON object` does not implicitly include `KEEP` privileges.
- Grant `KEEP` only to application users that require it.
- `SYS_GUID` value preservation has limits, such as supporting serial processing plans only under documented conditions.

Do not grant `KEEP` broadly without identifying which values the application actually needs preserved.

### 6.9. DDL and Administrative Statements

Certain statements are restricted or disable replay, such as `ALTER SYSTEM` and `ALTER DATABASE`. Some `ALTER SESSION` statements are also restricted when they leave session state unable to be safely restored.

Keep DDL and administrative commands out of business requests expected to replay. Separate migrations, deployments, and admin tasks from OLTP requests.

### 6.10. XA Two-Phase Commit and Isolation Levels

Oracle 19c imposes restrictions by driver and transaction mode:

- Replay can support local transactions through an XA data source under supported conditions.
- When true XA two-phase commit is active, replay may be disabled.
- `SERIALIZABLE` isolation is unsupported for replay per documented restrictions.
- Verify exact drivers, transaction managers, and XA modes before enabling AC.

Never assume an XA application automatically replays simply because the service sets `FAILOVER_TYPE`.

## 7. How Side Effects Differ Between AC and TAC

With manual AC (`FAILOVER_TYPE = TRANSACTION`), recorded calls can replay from history. If a request invokes `UTL_SMTP` or a callout that must not repeat, the application must explicitly disable replay for that request or route to a non-AC service.

TAC (`FAILOVER_TYPE = AUTO`) uses state tracking to recognize certain application side effects and automatically turns off capture/replay for affected calls. This reduces manual coding, yet external integrations and custom side effects still require testing.

### 7.1. Disabling Replay in Java

With a JDBC replay connection:

~~~java
if (connection instanceof oracle.jdbc.replay.ReplayableConnection) {
    ((oracle.jdbc.replay.ReplayableConnection) connection).disableReplay();
}
~~~

`disableReplay` applies to the current request. Once replay is disabled, both recording and replay remain off until the request ends. There is no API to re-enable it mid-request because the driver cannot guarantee a continuous call history.

### 7.2. Disabling Replay in OCI

OCI provides the corresponding `OCIRequestDisableReplay` API for requests that must avoid replay. Check the OCI Developer's Guide for your client version for exact invocation details.

### 7.3. Using Separate Services

An application can split services:

- An AC/TAC service for OLTP requests safe to replay.
- A replay-disabled service for requests with uncontrollable side effects.

Separate services require aligned routing, monitoring, pools, and SLAs. Never switch services mid-transaction.

## 8. Design Patterns to Prevent Duplicate Side Effects

### 8.1. Transactional Outbox

If a database transaction needs to emit an event to a message broker or call an external API, do not send it directly inline before committing. Instead, write an outbox record within the same transaction.

~~~text
HTTP request
    |
    v
Oracle transaction
    |
    +---- UPDATE business tables
    |
    +---- INSERT OUTBOX(event_id, payload, status)
    |
    v
  COMMIT
    |
    v
Outbox worker
    |
    +---- send to external system using event_id
    |
    +---- mark delivered / retry
~~~

Example:

~~~sql
CREATE TABLE event_outbox (
    event_id       VARCHAR2(64) PRIMARY KEY,
    event_type     VARCHAR2(50) NOT NULL,
    payload        CLOB NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    delivered_at   TIMESTAMP,
    status         VARCHAR2(20) DEFAULT 'PENDING' NOT NULL
);
~~~

Inside the business transaction:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;

INSERT INTO event_outbox(event_id, event_type, payload)
VALUES (:event_id, 'ORDER_PAID', :payload);

COMMIT;
~~~

A worker reads the outbox after commit and dispatches the event. If the worker sends successfully but crashes before marking `DELIVERED`, it may resend. Thus, the downstream receiver should still support idempotency keys / `event_id`.

An outbox does not magically create exactly-once delivery; it establishes a durable checkpoint for controlled retries and deduplication.

### 8.2. Idempotency Keys for Payments/APIs

When calling payment providers or REST APIs, generate a stable business operation ID and pass it as an idempotency key. If the same operation is resent, the receiver returns the prior result instead of charging a second time.

Never generate a new idempotency key on each retry; the key must represent the same single business operation.

### 8.3. Isolating Audit Transactions

If audit records must survive independently of the main transaction, enforce deduplication rules. Use a unique event ID and a unique constraint so each event is recorded at most once.

Never assume an autonomous transaction always replays at most once.

## 9. Session State Consistency and COMMIT

Replay restores more than transactional data changes. It must also restore non-transactional session state such as NLS settings, optimizer settings, PL/SQL package state, temporary table contents, application contexts, and other session properties.

### 9.1. DYNAMIC

`DYNAMIC` fits most applications, especially when session state can change mid-request.

With manual AC, when session state consistency is `DYNAMIC` (the default), replay is disabled after a `COMMIT` until the next request starts. This is because non-transactional state may have changed during the transaction and cannot be safely reconstructed if the session is lost.

### 9.2. STATIC

`STATIC` applies only when session state is established during initialization and can be restored via `FAILOVER_RESTORE` or callbacks. Never choose `STATIC` if the application mutates package state, NLS, contexts, or temporary state between transactions inside a request.

### 9.3. AUTO

`AUTO` is the mandatory `session_state_consistency` setting for TAC. State tracking captures and verifies TAC-supported session states, restoring sessions without requiring the application to declare every mutation.

### 9.4. Comparison Table

| Mode | Used With | Behavior |
| --- | --- | --- |
| `DYNAMIC` | Manual AC | State can change mid-request; replay disables after COMMIT until next request |
| `STATIC` | Manual AC | Safe only when state is fixed at initialization and restorable |
| `AUTO` | TAC | Oracle tracks state automatically; mandatory mode for TAC |

If you do not fully understand your application's session state, never force `STATIC`. Oracle recommends `AUTO` with TAC; with manual AC, `DYNAMIC` fits the vast majority of applications.

## 10. Planned Maintenance vs. Unplanned Outages

### 10.1. Unplanned Outages

Examples:

- Instance crash.
- Node failure.
- Network interruption.
- Storage failure.
- Foreground process failure.
- Service/database outage.

FAN notifies connection pools promptly of UP/DOWN events. Drivers/pools evict dead connections, open new connections, and coordinate with AC/TAC to recover eligible requests.

### 10.2. Planned Maintenance

When patching, relocating services, or stopping an instance, prioritize draining active requests:

1. Notify that the service is entering maintenance.
2. Pool stops handing out new connections to the draining instance.
3. In-flight requests are given time to complete.
4. Eligible requests that fail to drain in time can fail over and replay.
5. Stop the instance/service per procedure.
6. Complete maintenance and restart the service.
7. Confirm the pool receives FAN UP events and traffic returns to normal.

### 10.3. Not Every Session Should Replay

If a DBA intentionally kills/disconnects a session and wants to prevent replay, Oracle supports `NOREPLAY` in administrative commands:

~~~sql
ALTER SYSTEM KILL SESSION 'sid, serial#, @inst' NOREPLAY;
~~~

Or:

~~~sql
ALTER SYSTEM DISCONNECT SESSION 'sid, serial#, @inst' NOREPLAY;
~~~

Use only when certain the session should not be recovered. For service maintenance, `SRVCTL`/`DBMS_SERVICE` provide corresponding options depending on environment.

## 11. Supported Drivers and Environments

Application Continuity depends on both database services and the client stack. You cannot simply flip a database parameter and assume every driver supports replay.

Key points to verify on Oracle 19c:

- Java uses an appropriate JDBC Thin Replay Driver/data source.
- UCP and WebLogic provide built-in Application Continuity integration per configuration.
- OCI/ODP.NET Unmanaged require verifying supported versions and APIs.
- JDBC OCI driver (type 2), ODP.NET Managed, OLE DB, ODBC, OCCI, and certain precompilers fall outside AC support in the documented 19c matrix.
- TAC has its own support matrix; OCI/ODP.NET Unmanaged and SQL*Plus 19.3+ are examples of supported clients.
- Never use `SID`/`instance_name` in replay connections; connect to a database service so the driver routes to valid targets.
- With RAC/Data Guard, configure FAN/ONS and appropriate service placement.

For JDBC, Oracle 19c uses replay data sources such as `oracle.jdbc.replay.OracleDataSourceImpl` or `OracleConnectionPoolDataSourceImpl` per documentation and pool configuration. Always verify exact driver versions, connection pools, services, and database releases.

## 12. Limitations to Know

Several scenarios are documented as excluded or restricted in Oracle 19c:

- `ALTER SYSTEM` or `ALTER DATABASE` statements disable replay.
- Certain `ALTER SESSION` statements unsafe for session reconstruction disable replay.
- XA two-phase commit has restrictions; replay may be disabled during active global transactions.
- `SERIALIZABLE` isolation is unsupported for replay.
- Certain deprecated JDBC concrete classes are unsupported.
- Application-server JDBC statement caches should be disabled during replay; use supported JDBC driver statement caching instead.
- Certain stream arguments/physical stream addresses replay best-effort only; certain JDBC stream setters disable replay.
- The replay target must belong to a supported database cluster/configuration; you cannot replay arbitrarily to an unrelated database.
- If the target database suffered data loss or opened at an earlier point in time (e.g., flashback/incomplete recovery), replay is rejected to protect transaction integrity.
- Certain statement-level parallel query errors do not trigger replay.
- DRCP for Java is unsupported per documented restrictions.
- Certain Active Data Guard configurations with read/write database links back to the primary are restricted.

This list does not replace the official compatibility matrix for your exact driver and Release Update. Consult Oracle documentation before onboarding production workloads.

## 13. Monitoring and Diagnosing Replay

### 13.1. Application Continuity Statistics

Oracle tracks request counts and protected calls. Inspect system statistics:

~~~sql
SELECT n.name,
       s.value
FROM v$sysstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE LOWER(n.name) LIKE '%request%'
   OR LOWER(n.name) LIKE '%replay%'
ORDER BY n.name;
~~~

Useful statistics, depending on release, include:

- `cumulative begin requests`.
- `cumulative end requests`.
- `cumulative user calls in requests`.
- `cumulative user calls protected by Application Continuity`.
- `successful replays by Application Continuity`.
- `failed replays`.

Verify exact statistic names and presence in your actual database.

### 13.2. Session Statistics

To inspect per session, join `V$SESSTAT` and `V$STATNAME`:

~~~sql
SELECT s.sid,
       n.name,
       ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname n
  ON n.statistic# = ss.statistic#
WHERE s.username = 'APP_USER'
  AND (
      LOWER(n.name) LIKE '%request%'
      OR LOWER(n.name) LIKE '%replay%'
  )
ORDER BY s.sid, n.name;
~~~

### 13.3. JDBC ReplayStatistics

The Oracle JDBC replay driver exposes `ReplayStatistics`, obtainable from `ReplayableConnection` or `OracleDataSource`. Metrics typically include:

- `TotalRequests`.
- `TotalCompletedRequests`.
- `TotalCalls`.
- `TotalProtectedCalls`.
- `TotalCallsAffectedByOutages`.
- `TotalCallsTriggeringReplay`.
- `SuccessfulReplayCount`.
- `FailedReplayCount`.
- `ReplayDisablingCount`.
- `TotalReplayAttempts`.

Read statistics at an appropriate point in the application, such as after completing a workload or via an administrative endpoint. Statistics can be cleared; subsequent counts reflect the period since the last clear.

### 13.4. AWR and ACCHK

Application Continuity statistics are captured in AWR and appear in AWR reports. Use the `ACCHK` utility from Oracle Autonomous Health Framework/ORAchk for your release to uncover factors reducing protection or blocking replay.

When protected calls drop, check:

1. Does the service have the right `FAILOVER_TYPE`?
2. Is the driver replay-capable?
3. Are request boundaries properly marked?
4. Are restricted calls or `disableReplay` disabling capture?
5. Can session state be restored?
6. Are unsupported concrete classes, stream APIs, or transaction modes in use?
7. Is `REPLAY_INITIATION_TIMEOUT` long enough?

## 14. Process for Evaluating Whether an Operation Is Safe to Replay

For each operation inside a request, ask:

1. Does the operation modify data strictly within an Oracle transaction?
2. Does it invoke external systems or create non-rollbackable side effects?
3. If executed twice, is the business outcome identical to executing once?
4. Is it guarded by an idempotency key or unique constraint?
5. Does it contain autonomous transactions or hidden `COMMIT`s?
6. Does it depend on middle-tier wall-clock time?
7. Does it depend on `SID`, `INSTANCE`, `HOST`, `ROWID`, or volatile resources?
8. Does it alter session state after `COMMIT`?
9. Do the driver and service support that operation?
10. If replay is rejected, how does the application handle the failure?

### 14.1. Assessment Matrix

| Operation | Replay Risk | Remediation |
| --- | --- | --- |
| `SELECT` business data | Typically low if results pass consistency checks | Use supported driver/service and test results |
| `INSERT`/`UPDATE` inside Oracle transaction | Replayable when request and session state are valid | Use clear transaction boundaries, business keys/unique constraints |
| `COMMIT` with lost response | Client may not know commit outcome | Use Transaction Guard/`COMMIT_OUTCOME`; never blindly retry |
| Sending email | High, email may be sent twice | TAC/`disableReplay`, outbox, idempotency |
| Calling payment API | Very high, may double-charge | Idempotency key at payment provider and outbox |
| Writing external files | High, file may be written twice | Write via outbox/worker or idempotent operation |
| Autonomous transaction | Can duplicate independent side effects | Review replay rules, deduplicate via event ID |
| Using middle-tier time | High if clock crosses deadline during outage | Freeze input timestamp or enforce inside DB |
| Branching on `SID`/`INSTANCE` | Unstable across failover | Use logical identity |
| Persisting `ROWID` long-term | `ROWID` can change | Use primary/business keys |
| DDL `ALTER SYSTEM`/`ALTER DATABASE` | Restricted/disables replay | Separate from business requests |
| Mutating session state then `COMMIT` | May fail to restore under `DYNAMIC` | Use `AUTO`/TAC or redesign state handling |
| XA two-phase commit | Restricted support | Verify driver/transaction mode; never assume replay |

## 15. Lab: Simulating Request and Replay Behavior

This lab focuses on design and observation without inducing outages in production. Run in a RAC/HA test environment with supported services and drivers.

### 15.1. Prepare the Service

DBAs create a dedicated AC or TAC service matching topology. TAC example:

~~~text
FAILOVER_TYPE = AUTO
FAILOVER_RESTORE = AUTO
COMMIT_OUTCOME = TRUE
AQ_HA_NOTIFICATIONS = TRUE
~~~

For manual AC, set `FAILOVER_TYPE = TRANSACTION` and configure `FAILOVER_RESTORE`/`SESSION_STATE_CONSISTENCY` per design.

### 15.2. Create a Test Transaction Table

~~~sql
CREATE TABLE ac_lab_orders (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20) NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    updated_at TIMESTAMP
);

INSERT INTO ac_lab_orders(order_id, status, amount, updated_at)
VALUES (1001, 'NEW', 250, SYSTIMESTAMP);

COMMIT;
~~~

### 15.3. Create an Outbox

~~~sql
CREATE TABLE ac_lab_outbox (
    event_id VARCHAR2(64) PRIMARY KEY,
    order_id NUMBER NOT NULL,
    event_type VARCHAR2(30) NOT NULL,
    status VARCHAR2(20) DEFAULT 'PENDING' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

### 15.4. Execute Business Logic in One Transaction

~~~sql
UPDATE ac_lab_orders
SET status = 'PAID',
    updated_at = SYSTIMESTAMP
WHERE order_id = 1001;

INSERT INTO ac_lab_outbox(event_id, order_id, event_type)
VALUES ('ORDER-1001-PAID', 1001, 'ORDER_PAID');

COMMIT;
~~~

The business update and outbox event commit or roll back atomically. A worker dispatches the event afterward using `ORDER-1001-PAID` as the idempotency key.

### 15.5. Verify Results

~~~sql
SELECT *
FROM ac_lab_orders
WHERE order_id = 1001;

SELECT *
FROM ac_lab_outbox
WHERE event_id = 'ORDER-1001-PAID';
~~~

Re-executing the outbox insert with the same `EVENT_ID` hits the unique constraint instead of creating a duplicate event. Applications should interpret duplicate keys as an already-recorded business operation.

### 15.6. Test Non-Idempotent Side Effects in an Isolated Lab

In an isolated lab, invoke a test endpoint or write a temporary file inside a request using manual AC. Simulate a failure after the side effect occurs but before the request completes. Observe whether the side effect repeats.

Never use live payment endpoints, real email addresses, production files, or external systems holding real data in this test.

### 15.7. Test disableReplay

On a Java replay connection, call `disableReplay` before invoking a module with non-repeatable side effects. Compare protected calls and replay count statistics against normal requests.

### 15.8. Test Transaction Guard

In an HA test environment:

1. Enable `COMMIT_OUTCOME` on the service.
2. Execute a transaction with a unique business identifier.
3. Simulate a connection drop right around `COMMIT` per an approved test script.
4. Check transaction outcome using the appropriate API/driver.
5. Confirm the application does not resubmit a committed transaction.

Never arbitrarily kill production instances to generate test failures.

## 16. Application Continuity Implementation Checklist

1. **Is the service right?** Application connects via a service, never hardcoded `SID`/instance.
2. **Is `FAILOVER_TYPE` right?** `TRANSACTION` for AC, `AUTO` for TAC.
3. **Is Transaction Guard enabled?** `COMMIT_OUTCOME = TRUE` with appropriate retention.
4. **Is `FAILOVER_RESTORE` appropriate?** `LEVEL1` for AC or `AUTO` for TAC per design.
5. **Does the driver support it?** Verify JDBC/OCI/ODP.NET and connection pool versions.
6. **Is FAN/notification configured?** Verify ONS, pool, and service.
7. **Are request boundaries sound?** Checkout/check-in or `beginRequest`/`endRequest`.
8. **Is session state restorable?** NLS, package state, contexts, temporary tables, optimizer settings.
9. **Have side effects been audited?** Email, HTTP, files, autonomous transactions, Java callouts.
10. **Are mutable functions handled?** Sequences, `SYSDATE`, `SYSTIMESTAMP`, `SYS_GUID`, and `KEEP`.
11. **Are `ROWID` or physical locators used?** Replace with logical keys wherever possible.
12. **Are multiple sessions synchronized via volatile locks?** Redesign or disable replay for that workload.
13. **Are restricted XA/Serializable/stream APIs present?** Check compatibility matrix.
14. **Is `disableReplay` scoped properly?** Prevent replay from staying disabled unintentionally.
15. **Do timeouts match SLAs?** Replay initiation, retry, retention, and pool timeouts.
16. **Have unplanned outages been tested?** Test both successful replay and replay rejection.
17. **Has planned maintenance been tested?** Drain, FAN, service relocation, and active requests.
18. **Are statistics monitored?** Protected calls, successful/failed replays, disabling counts.
19. **Has commit outcome been tested?** Avoid blind retries after lost `COMMIT` responses.
20. **Does the application have fallbacks?** Handle non-recoverable errors and replay rejections.

## 17. Self-Check Questions

**Question 1.** What problem does Application Continuity solve when a database session drops?

**Question 2.** What is a database request?

**Question 3.** How do recoverable errors differ from non-recoverable errors?

**Question 4.** Why might a client not know whether `COMMIT` succeeded?

**Question 5.** What problem do Transaction Guard and LTXID solve?

**Question 6.** How do `FAILOVER_TYPE = TRANSACTION` and `AUTO` differ?

**Question 7.** Why does AC require request boundaries?

**Question 8.** When are `beginRequest` and `endRequest` used?

**Question 9.** Why should `endRequest` not be called while a transaction remains open?

**Question 10.** What does TAC use state tracking for?

**Question 11.** Why can `UTL_SMTP` or `UTL_HTTP` produce duplicate side effects?

**Question 12.** How does an autonomous transaction differ from its calling transaction?

**Question 13.** Why can locks held across two sessions lose validity after replay?

**Question 14.** Why should middle-tier wall clocks not drive replay-sensitive decisions?

**Question 15.** Why is `ROWID` unsuitable as a long-term business key?

**Question 16.** Which `SYS_CONTEXT` location values can change after failover?

**Question 17.** What are `KEEP DATE TIME`, `KEEP SYSGUID`, and `KEEP SEQUENCE` used for?

**Question 18.** Why should DDL such as `ALTER SYSTEM` not appear inside replayable requests?

**Question 19.** How does a transactional outbox reduce side-effect risk?

**Question 20.** Why are idempotency keys still needed even with AC/TAC enabled?

<details>
<summary>Answer Hints</summary>

1. Restores sessions and in-flight work after recoverable outages so requests can continue safely.
2. A unit of database work on a connection, typically aligned with one application request.
3. Recoverable errors stem from infrastructure/connectivity failures; non-recoverable errors cannot be fixed by reconnect/replay, such as invalid input data.
4. `COMMIT` may have been durably persisted while the response never reached the client.
5. Determines whether the last transaction committed to avoid re-submitting completed transactions.
6. `TRANSACTION` enables manual AC; `AUTO` enables TAC with state tracking.
7. So the driver knows which call history belongs to a request and when it ends.
8. Explicitly mark request start/end on a JDBC connection when the pool/framework does not manage boundaries automatically.
9. Oracle requires local transactions to finish before closing a request boundary.
10. Tracks and validates session/transaction state, detects request boundaries, and identifies certain side effects.
11. Email/HTTP actions occur outside the database transaction; replay can re-invoke them after an outage.
12. Autonomous transactions commit/roll back independently, so side effects persist even if the parent transaction rolls back.
13. Failover can discard locks/volatile resources that another session relied upon.
14. The driver replays database calls without re-running middle-tier timing logic.
15. `ROWID` can change after reorganization, partitioning, migration, restore, or flashback; use primary/business keys.
16. `INSTANCE`, `SID`, `SESSIONID`, `HOST`, `IP_ADDRESS`, and `TERMINAL`.
17. Preserve original mutable values for timestamps, GUIDs, and sequences in supported replay scenarios.
18. Administrative statements are restricted and disable replay; separate them from business requests.
19. Writes events atomically in the same transaction as business data, then dispatches post-commit via a worker with controlled retries.
20. AC/TAC do not make external systems exactly-once; idempotency keys allow receivers to deduplicate resent requests.

</details>

## 18. Official Oracle Documentation

1. [Oracle Database 19c Real Application Clusters Administration and Deployment Guide — Ensuring Application Continuity](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html): AC, TAC, replay, side effects, restrictions, service configuration, and Transaction Guard.
2. [Oracle Database 19c JDBC Developer's Guide — Application Continuity for Java](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/application-continuity.html): JDBC Replay Driver, request boundaries, TAC, `disableReplay`, and `ReplayStatistics`.
3. [Oracle Database 19c High Availability Overview — Configuring Level 3](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/configuring-level-3-mask-unplanned-failovers-applications.html): configuring services for AC/TAC, commit outcomes, and side effects.
4. [Oracle Database 19c Concepts — Transactions and Application Continuity](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): requests, reconnection, replay, and Transaction Guard.
5. [Oracle Database 19c Reference — DBMS_SERVICE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SERVICE.html): managing services and service attributes.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APP_CONT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APP_CONT.html): PL/SQL replay APIs and rules where supported.
7. [Oracle Database 19c Real Application Clusters Administration and Deployment Guide — Fast Application Notification](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/ensuring-application-continuity.html): FAN events and connection pool coordination.

**Key Principle:** Application Continuity records database requests, reconnects, and replays database calls after recoverable outages. Transaction Guard determines commit outcomes to avoid re-submitting completed transactions. Replay is safe only when session state and previously observed results can be restored. Email, HTTP, file transfers, autonomous transactions, cross-session volatile lock synchronization, middle-tier wall clocks, `ROWID`, and physical locators require special scrutiny. Use TAC/state tracking, `disableReplay`, transactional outboxes, and idempotency keys appropriately; never assume enabling AC/TAC makes every operation automatically exactly-once.
