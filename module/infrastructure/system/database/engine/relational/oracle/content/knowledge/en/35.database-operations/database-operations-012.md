# DBMS_APPLICATION_INFO for Tagging Application Sessions with Module/Action

In a database shared by multiple applications, services, and connection pools, looking solely at SQL text or the database username is often insufficient to know which business function a session is serving. A single database user may be shared across multiple modules of the same application, and a single physical connection may sequentially process requests from many different end users. When diagnosing why a specific feature is slow, DBAs need to know which module is issuing the SQL and what action is currently executing.

Oracle provides the **DBMS_APPLICATION_INFO** package so applications can tag their sessions. Its two primary attributes are **MODULE** and **ACTION**. MODULE identifies the functional area or application component, while ACTION describes the current operation inside that module. Oracle records these attributes in dynamic performance views such as V$SESSION and V$SQLAREA, and uses them as criteria for statistics aggregation and SQL tracing via DBMS_MONITOR.

For example, an order management system might set MODULE = ORDER_API and sequentially set ACTION to VALIDATE_ORDER, RESERVE_STOCK, and CREATE_INVOICE. When a session slows down, DBAs can locate sessions or SQL belonging to that exact module/action instead of guessing from username, hostname, or SQL text.

This lesson belongs to the **Operations** track of Oracle Relational Database Engine. It covers DBMS_APPLICATION_INFO, setting and clearing MODULE/ACTION, distinguishing CLIENT_INFO from CLIENT_IDENTIFIER, reading metadata from dynamic performance views, integrating with connection pools, statistics and tracing by service/module/action via DBMS_MONITOR, tracking long operations, security, and operational workflows.

After this lesson, you will be able to:

- Explain what MODULE and ACTION represent in a database session.
- Use SET_MODULE, SET_ACTION, READ_MODULE, and READ_CLIENT_INFO.
- Clear stale tags so workload is not misattributed to subsequent requests.
- Understand module/action length limits and the LONG_MODULE_ACTION parameter.
- Distinguish MODULE/ACTION, CLIENT_INFO, and CLIENT_IDENTIFIER.
- Query V$SESSION, V$SQLAREA, V$SQL, and V$ACTIVE_SESSION_HISTORY for application observability.
- Integrate module/action into PL/SQL procedures and Java/JDBC applications.
- Properly reset session state when using connection pools.
- Enable statistics aggregation by service/module/action using DBMS_MONITOR.
- Enable narrowly scoped SQL tracing and disable tracing after investigation.
- Use SET_SESSION_LONGOPS to expose progress for long-running operations.
- Avoid using application metadata as an authentication or authorization mechanism.

> **Example Scope:** Examples primarily target Oracle Database 19c. Certain views require dynamic performance view privileges; DBMS_MONITOR APIs require appropriate administrative privileges. Verify your release/RU, RAC/PDB setup, and actual privileges before applying.

## 1. Why Tag Sessions with Module/Action?

An application typically has multiple business flows connecting to the same database:

- Order creation API.
- Order lookup API.
- Payment processing flow.
- Inventory sync batch job.
- Revenue reporting.
- Notification dispatch job.

If all connections log in as the same database user, a DBA inspecting V$SESSION sees many sessions with identical USERNAME. Looking at SQL text alone makes it very hard to tell which request is at which business step.

### 1.1. Beyond Database Username

Example:

| Database user | Application | Module | Action |
| --- | --- | --- | --- |
| APP_RUNTIME | Sales API | ORDER_API | CREATE_ORDER |
| APP_RUNTIME | Sales API | ORDER_API | GET_ORDER |
| APP_RUNTIME | Sales API | PAYMENT_API | AUTHORIZE_PAYMENT |
| APP_RUNTIME | Inventory batch | INVENTORY_JOB | SYNC_STOCK |
| APP_RUNTIME | Reporting | REPORT_API | MONTHLY_REVENUE |

All of them may connect as APP_RUNTIME, yet module/action clearly categorizes each workload.

### 1.2. Operational Benefits

- Locate sessions executing a specific business function.
- Analyze resource-intensive SQL grouped by module.
- Aggregate execution statistics by service/module/action.
- Enable SQL trace for a specific action experiencing performance issues.
- Correlate requests in application logs with database activity.
- Separate OLTP, batch, and reporting workloads sharing the same schema.

### 1.3. End-to-End Application Tracing

Oracle calls cross-tier observability end-to-end application tracing. Attributes that can be used include:

- Client identifier: identifies the end user or logical client.
- Service: groups workloads connected via a database service.
- Module: functional component within the application.
- Action: current operation executing inside the module.
- Session: specific database session.
- Instance: specific database instance.
- Container: PDB/container in multitenant environments.

MODULE/ACTION are application-supplied metadata. They help DBAs understand what a session is doing, but do not automatically prove user identity or data access rights.

## 2. What Is DBMS_APPLICATION_INFO?

DBMS_APPLICATION_INFO is an Oracle-supplied PL/SQL package for recording an application's module name, action name, and supplementary client info on its session.

### 2.1. Main Procedures

| Procedure | Purpose |
| --- | --- |
| SET_MODULE | Sets MODULE and ACTION simultaneously |
| SET_ACTION | Changes ACTION within the current MODULE |
| READ_MODULE | Reads the current MODULE and ACTION |
| SET_CLIENT_INFO | Writes supplementary info to CLIENT_INFO |
| READ_CLIENT_INFO | Reads the current CLIENT_INFO |
| SET_SESSION_LONGOPS | Records progress of long operations in V$SESSION_LONGOPS |

### 2.2. Execution Privileges

In a standard Oracle installation, DBMS_APPLICATION_INFO is pre-installed with a public synonym. Oracle 19c documentation notes that applications do not require additional privileges to call this package.

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Do not grant the DBA role to an application just to set module/action.

### 2.3. Not a Business Audit Log Table

DBMS_APPLICATION_INFO updates session/cursor metadata for observability and tracing. It does not automatically log every business step into an application audit table, store request payloads, or replace application logging.

## 3. MODULE and ACTION

### 3.1. MODULE Represents a Functional Component

MODULE should represent a relatively stable application component:

- ORDER_API
- PAYMENT_API
- INVENTORY_JOB
- CUSTOMER_PORTAL
- REPORTING_SERVICE

Do not set module to a unique per-request value if your goal is aggregated statistics. Too many distinct module values make grouped analysis ineffective.

### 3.2. ACTION Represents the Current Task

ACTION describes the step or transaction currently executing:

- CREATE_ORDER
- VALIDATE_ADDRESS
- RESERVE_STOCK
- AUTHORIZE_PAYMENT
- LOAD_MONTHLY_REPORT
- SEND_NOTIFICATION

One module can step through multiple actions sequentially. For example:

~~~text
MODULE = ORDER_API
    ACTION = VALIDATE_ORDER
    ACTION = RESERVE_STOCK
    ACTION = WRITE_ORDER
    ACTION = PUBLISH_EVENT
~~~

### 3.3. MODULE and ACTION Are Not SQL Operations

MODULE/ACTION are application-defined. Oracle does not restrict ACTION to SELECT, INSERT, or UPDATE. Name them in business terms so operators can easily understand them.

For example, ORDER_API / AUTHORIZE_CARD is far more useful than MODULE1 / STEP3.

### 3.4. Naming Conventions

Establish consistent conventions:

- Use uppercase and underscores for easy filtering.
- Keep module names stable across application releases.
- Use action names that describe clear business steps.
- Avoid embedding timestamps, UUIDs, or request IDs into module/action.
- Never include sensitive data such as emails, account numbers, tokens, or access keys.
- Use client identifier or application log correlation IDs for request/user identity.

### 3.5. Length Limits

Pay close attention here because package documentation and database configuration can expose different limits.

| Configuration/Version | MODULE | ACTION |
| --- | ---: | ---: |
| Prior to Oracle 12.2 | 48 bytes | 32 bytes |
| Oracle 12.2+, LONG_MODULE_ACTION = FALSE | 48 bytes | 32 bytes |
| Oracle 12.2+, LONG_MODULE_ACTION = TRUE | 64 bytes | 64 bytes |

In Oracle 19c, LONG_MODULE_ACTION defaults to TRUE. V$SESSION.MODULE and V$SESSION.ACTION are both VARCHAR2(64).

Verify:

~~~sql
SHOW PARAMETER long_module_action
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'long_module_action';
~~~

LONG_MODULE_ACTION can be altered with ALTER SYSTEM and adjusted per PDB. In Oracle RAC, the exact same value must be used across all instances.

Example:

~~~sql
ALTER SYSTEM SET long_module_action = TRUE;
~~~

Change this parameter only as part of a uniform environment configuration plan. Do not rely on long strings being silently truncated without checking; two distinct module/action names could truncate to the exact same prefix.

### 3.6. Lengths Are Measured in Bytes

Oracle specifies module/action limits in bytes. In UTF-8 strings, a single character can occupy multiple bytes. Consequently, non-ASCII names (such as accented Vietnamese characters) can hit the byte limit sooner than the expected character count.

To avoid subtle truncation and minimize differences across client/database character sets, prefer short, stable labels, typically ASCII.

## 4. SET_MODULE

SET_MODULE sets both the current module and current action in a single call.

### 4.1. Syntax

~~~sql
DBMS_APPLICATION_INFO.SET_MODULE(
    module_name IN VARCHAR2,
    action_name IN VARCHAR2
);
~~~

### 4.2. Setting Module and Action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Afterward, V$SESSION can show MODULE = ORDER_API and ACTION = CREATE_ORDER.

### 4.3. Switching to Another Module

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'PAYMENT_API',
        action_name => 'AUTHORIZE_PAYMENT'
    );
END;
/
~~~

SET_MODULE updates both attributes. If you want to keep the current module and change only the action, use SET_ACTION.

### 4.4. Clearing Module/Action

When the current module finishes:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Oracle recommends setting the new module/action when an application enters a new module, and setting them to NULL when the module finishes if no subsequent module follows.

### 4.5. SET_MODULE Does Not Commit Transactions

SET_MODULE modifies only session metadata. It does not COMMIT, ROLLBACK, or alter transaction data. It can be called before a transaction, mid-transaction, or when starting a business step.

## 5. SET_ACTION

SET_ACTION updates only the ACTION of the current module.

### 5.1. Syntax

~~~sql
DBMS_APPLICATION_INFO.SET_ACTION(
    action_name IN VARCHAR2
);
~~~

### 5.2. Switching Actions Within the Same Module

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        'ORDER_API',
        'VALIDATE_ORDER'
    );

    -- Validate input data.

    DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');

    -- Call stock reservation logic.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_ORDER');

    -- Write order record.

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

MODULE remains ORDER_API while ACTION transitions across each step.

### 5.3. Clearing Action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

Clear the action when the business step completes. Otherwise, the session can keep displaying the old action during subsequent calls.

### 5.4. Setting Action Before Transactions

Oracle recommends that applications set the action before starting a transaction. This ensures statistics aggregated by service/module/action align cleanly with the intended step.

### 5.5. New Actions May Reflect on the Next Call in Aggregated Statistics

When DBMS_MONITOR gathers statistics by module/action, changing module/action inside a user call takes effect on the following user call. Therefore, the call invoking SET_ACTION may still be accounted under the old action, while subsequent calls accrue under the new action.

Keep this detail in mind when reconciling per-step metrics closely.

## 6. READ_MODULE and READ_CLIENT_INFO

You can read back current metadata inside the same session.

### 6.1. READ_MODULE

~~~sql
DECLARE
    l_module VARCHAR2(64);
    l_action VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_MODULE(
        module_name => l_module,
        action_name => l_action
    );

    DBMS_OUTPUT.PUT_LINE('MODULE=' || NVL(l_module, '<NULL>'));
    DBMS_OUTPUT.PUT_LINE('ACTION=' || NVL(l_action, '<NULL>'));
END;
/
~~~

READ_MODULE returns the most recent values set via SET_MODULE/SET_ACTION in the current session.

### 6.2. READ_CLIENT_INFO

~~~sql
DECLARE
    l_client_info VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_CLIENT_INFO(
        client_info => l_client_info
    );

    DBMS_OUTPUT.PUT_LINE(
        'CLIENT_INFO=' || NVL(l_client_info, '<NULL>')
    );
END;
/
~~~

### 6.3. Checking Metadata with SYS_CONTEXT

You can read several session attributes via SYS_CONTEXT:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'MODULE') AS module_name,
    SYS_CONTEXT('USERENV', 'ACTION') AS action_name,
    SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier
FROM dual;
~~~

SYS_CONTEXT is convenient when PL/SQL or SQL needs to inspect session metadata inside a SQL expression.

## 7. CLIENT_INFO vs. CLIENT_IDENTIFIER

These two attributes sound similar, yet serve different purposes.

### 7.1. CLIENT_INFO

SET_CLIENT_INFO records supplementary client metadata:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(
        'web-node-03;release-2026.11'
    );
END;
/
~~~

The value is stored in V$SESSION.CLIENT_INFO. Oracle 19c limits CLIENT_INFO to 64 bytes; longer strings are truncated.

Read it back:

~~~sql
DECLARE
    l_info VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_CLIENT_INFO(l_info);
    DBMS_OUTPUT.PUT_LINE(l_info);
END;
/
~~~

CLIENT_INFO can be read and overwritten by any user in their session. Never use it to store secrets or treat it as authentication proof.

### 7.2. CLIENT_IDENTIFIER

CLIENT_IDENTIFIER identifies the end user or logical client in multi-tier architectures. Examples:

- USER-10027
- CUSTOMER-501
- API-REQUEST-8F3A

Set via DBMS_SESSION:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('CUSTOMER-501');
END;
/
~~~

The value is visible in V$SESSION.CLIENT_IDENTIFIER or via:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER')
FROM dual;
~~~

DBMS_SESSION.SET_IDENTIFIER supports up to 64 bytes. Client identifiers are case-sensitive.

### 7.3. Clearing Client Identifier

~~~sql
BEGIN
    DBMS_SESSION.CLEAR_IDENTIFIER;
END;
/
~~~

### 7.4. Comparison

| Attribute | Purpose | API | Common View |
| --- | --- | --- | --- |
| MODULE | Application component | DBMS_APPLICATION_INFO.SET_MODULE | V$SESSION.MODULE |
| ACTION | Current business step | DBMS_APPLICATION_INFO.SET_ACTION | V$SESSION.ACTION |
| CLIENT_INFO | Supplementary client metadata | DBMS_APPLICATION_INFO.SET_CLIENT_INFO | V$SESSION.CLIENT_INFO |
| CLIENT_IDENTIFIER | End user/logical client identity | DBMS_SESSION.SET_IDENTIFIER | V$SESSION.CLIENT_IDENTIFIER |
| SERVICE_NAME | Database service the session connected to | Client/service configuration | V$SESSION.SERVICE_NAME |

### 7.5. Do Not Substitute CLIENT_INFO for CLIENT_IDENTIFIER

CLIENT_IDENTIFIER is directly integrated by Oracle into end-to-end tracing, client statistics, and certain security/auditing features. CLIENT_INFO is merely a free-form supplementary field.

When propagating logical user identity from a middle tier, use SET_IDENTIFIER through trusted application-tier logic. If attributes must drive authorization, use a secure application context populated by a trusted package; never trust arbitrary client-supplied metadata.

### 7.6. Do Not Confuse Metadata with Authenticated Identity

These APIs are designed for session labeling by applications. Any database user can invoke them and set arbitrary values. Therefore:

- Never grant data access based solely on MODULE/ACTION.
- Never treat CLIENT_IDENTIFIER as proof of password/MFA authentication.
- Never place secrets, tokens, passwords, or sensitive data into metadata.
- Use secure application contexts, VPD/RLS, database privileges, and real authentication for security enforcement.

## 8. Observing MODULE/ACTION in V$SESSION

V$SESSION displays active and inactive sessions currently connected, including module, action, client info, and client identifier.

### 8.1. Finding Sessions by Module

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    client_info,
    status,
    sql_id,
    sql_exec_start,
    last_call_et
FROM v$session
WHERE module = 'ORDER_API'
ORDER BY logon_time;
~~~

### 8.2. Finding a Specific Action

~~~sql
SELECT
    sid,
    serial#,
    username,
    module,
    action,
    status,
    event,
    wait_class,
    sql_id
FROM v$session
WHERE module = 'ORDER_API'
  AND action = 'RESERVE_STOCK';
~~~

### 8.3. Finding Sessions for a Client Identifier

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    status,
    machine,
    program
FROM v$session
WHERE client_identifier = 'CUSTOMER-501';
~~~

### 8.4. V$SESSION Shows Current State Only

V$SESSION reflects current session metadata. Once an application resets module/action, old values disappear from that session row. For historical analysis, use SQL trace, aggregated statistics, or a configured historical repository.

### 8.5. ACTIVE vs. INACTIVE Status

- ACTIVE: the session is currently executing a database call.
- INACTIVE: the session has no call currently running.

MODULE/ACTION can retain their last-set values even while a session is INACTIVE. Thus, seeing ACTION = CREATE_ORDER does not mean a CREATE_ORDER query is executing at that exact instant; inspect STATUS, SQL_ID, and SQL_EXEC_START.

## 9. Observing SQL by Module/Action

Oracle records module/action alongside SQL cursor metadata in views such as V$SQLAREA and V$SQL.

### 9.1. V$SQLAREA

~~~sql
SELECT
    sql_id,
    module,
    action,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    rows_processed,
    sql_text
FROM v$sqlarea
WHERE module = 'ORDER_API'
ORDER BY elapsed_time DESC;
~~~

### 9.2. V$SQL

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    module,
    action,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads
FROM v$sql
WHERE module = 'ORDER_API'
  AND action = 'CREATE_ORDER'
ORDER BY elapsed_time DESC;
~~~

### 9.3. Cumulative Statistics

Metrics in V$SQL/V$SQLAREA are typically cumulative totals for cursors residing in the shared pool. Do not compare raw total elapsed_time across two modules if their execution counts and cursor lifetimes differ.

You can compute reference averages:

~~~sql
SELECT
    module,
    action,
    SUM(executions) AS executions,
    ROUND(
        SUM(elapsed_time) /
        NULLIF(SUM(executions), 0) / 1e6,
        4
    ) AS avg_elapsed_seconds,
    ROUND(
        SUM(cpu_time) /
        NULLIF(SUM(executions), 0) / 1e6,
        4
    ) AS avg_cpu_seconds,
    ROUND(
        SUM(buffer_gets) /
        NULLIF(SUM(executions), 0),
        2
    ) AS avg_buffer_gets
FROM v$sql
WHERE module = 'ORDER_API'
GROUP BY module, action
ORDER BY avg_elapsed_seconds DESC;
~~~

Averages conceal percentiles and latency distributions. Use application metrics or tracing when p95/p99 details are needed.

### 9.4. SQL Text Can Be Truncated

V$SQLAREA.SQL_TEXT has a display length limit. For long SQL statements, use SQL_FULLTEXT or look up by SQL_ID according to privileges and release.

## 10. Tagging Module/Action in PL/SQL

A stored procedure can set its own module/action upon entry.

### 10.1. Simple Procedure Example

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER
)
IS
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );

    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE_CUSTOMER');
    -- Validate customer.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_ORDER');
    -- Write order record.

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
        RAISE;
END;
/
~~~

This example demonstrates tagging metadata. In production code, ensure cleanup executes even when validation or DML raises an exception.

### 10.2. Separating Business Logic and Cleanup

You can wrap business logic in a nested block so cleanup runs on both success and failure paths:

~~~sql
CREATE OR REPLACE PROCEDURE process_order_lab (
    p_order_id IN NUMBER
)
IS
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        'ORDER_API',
        'PROCESS_ORDER'
    );

    BEGIN
        DBMS_APPLICATION_INFO.SET_ACTION('LOAD_ORDER');
        -- SELECT order details.

        DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');
        -- Call stock reservation logic.

        DBMS_APPLICATION_INFO.SET_ACTION('UPDATE_STATUS');
        -- Update status.

    EXCEPTION
        WHEN OTHERS THEN
            DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
            RAISE;
    END;

    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

In large systems, build a helper/wrapper to avoid repeating cleanup boilerplate. Never swallow exceptions merely to reset metadata.

### 10.3. Avoid Leaving Stale Actions Behind

If a procedure only calls SET_ACTION on the happy path, an exception leaves the stale action on the session. Handle cleanup in exception blocks or via an application-layer finally block.

### 10.4. Nested Procedures

If procedure A calls B, establish conventions on who owns module/action:

- Top-level module can represent the overall API.
- Action updates as sub-steps execute.
- Child procedures should not arbitrarily clear the caller's module.
- If a child procedure overrides module, it should restore the caller's prior values upon exit.

A clear convention prevents unpredictable metadata overwrites.

## 11. Integration in Java/JDBC Applications

Java applications can invoke DBMS_APPLICATION_INFO via an anonymous PL/SQL block or stored procedure.

### 11.1. Setting Module/Action and Client Identifier

Example using JDBC CallableStatement:

~~~java
String sql = """
    BEGIN
      DBMS_APPLICATION_INFO.SET_MODULE(?, ?);
      DBMS_SESSION.SET_IDENTIFIER(?);
    END;
    """;

try (CallableStatement call = connection.prepareCall(sql)) {
    call.setString(1, "ORDER_API");
    call.setString(2, "CREATE_ORDER");
    call.setString(3, "CUSTOMER-501");
    call.execute();
}
~~~

This is a conceptual example. Use the exact physical connection that will execute the subsequent business SQL; never open a separate connection just to set metadata.

### 11.2. Updating Action Between Steps

~~~java
try (CallableStatement call =
         connection.prepareCall(
             "BEGIN DBMS_APPLICATION_INFO.SET_ACTION(?); END;")) {
    call.setString(1, "RESERVE_STOCK");
    call.execute();
}
~~~

### 11.3. Resetting Before Returning the Connection to the Pool

~~~java
String resetSql = """
    BEGIN
      DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
      DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL);
      DBMS_SESSION.CLEAR_IDENTIFIER;
    END;
    """;

try (CallableStatement reset = connection.prepareCall(resetSql)) {
    reset.execute();
}
~~~

Place the reset logic in a finally block or the pool's connection cleanup hook. If the reset fails, evict the connection from the pool rather than returning it with stale request metadata.

### 11.4. Never Open a Separate Connection Just to Set Tags

Module/action is state attached to a specific database session. It must be set on the same session executing the business SQL. Calling SET_MODULE on connection A while running queries on connection B will not tag connection B's queries.

## 12. Connection Pools and Session State

This is where tagging mistakes happen most frequently.

### 12.1. Physical Sessions Are Reused

A connection pool might keep 20 database sessions open. Request 1 borrows session #1 and sets MODULE = ORDER_API and ACTION = CREATE_ORDER. When the request returns the connection to the pool, the database session stays alive.

If Request 2 borrows that same session without resetting metadata, it may continue displaying ORDER_API/CREATE_ORDER even while running a report or completely different feature.

### 12.2. Recommended Lifecycle

~~~text
Application request
        |
        v
Borrow connection from pool
        |
        v
Set CLIENT_IDENTIFIER
Set MODULE and ACTION
        |
        v
Execute business SQL
Update ACTION as work changes
        |
        v
Clear MODULE/ACTION and CLIENT_IDENTIFIER
        |
        v
Return clean connection to pool
~~~

### 12.3. Set Metadata on Every Checkout

Do not set module/action only when a connection is initially created. A physical session serves many requests and end users over its lifetime. Re-apply metadata on every checkout or at the appropriate request boundary.

### 12.4. Reset on Both Success and Exception

If application code resets metadata only after a query succeeds, timeouts or exceptions can leave stale metadata on the session. Use finally blocks, interceptors, or pool callbacks to guarantee cleanup.

### 12.5. Pool Reset and Transaction State

Resetting metadata does not replace proper transaction management:

- Commit or roll back strictly at transaction boundaries.
- Return connections to the pool only after transactions end.
- Never leave open transactions on idle pooled connections.
- Reset session attributes per pool policy.

### 12.6. Module/Action Persists While Sessions Are Idle

V$SESSION displays the last module/action set on a session. An INACTIVE session can still retain tags from the prior request. This is why resetting before returning connections to the pool is critical.

## 13. DBMS_MONITOR: Statistics by Service/Module/Action

DBMS_APPLICATION_INFO applies labels. DBMS_MONITOR uses those labels to enable statistics aggregation or SQL tracing for targeted workloads.

### 13.1. SERV_MOD_ACT_STAT_ENABLE

Syntax:

~~~sql
DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
    service_name IN VARCHAR2,
    module_name  IN VARCHAR2,
    action_name  IN VARCHAR2 DEFAULT ALL_ACTIONS
);
~~~

Example enabling statistics for order creation:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

If action_name is omitted or set to DBMS_MONITOR.ALL_ACTIONS, Oracle gathers statistics across all actions in that module.

### 13.2. ALL_ACTIONS Differs from NULL

Oracle provides the special constant DBMS_MONITOR.ALL_ACTIONS to match all actions in a module. NULL or an empty string matches an unset/empty action. Never replace ALL_ACTIONS with NULL when your goal is to capture every action.

### 13.3. Viewing Statistics

V$SERV_MOD_ACT_STATS shows metrics for service/module/action combinations with aggregation enabled:

~~~sql
SELECT
    service_name,
    module,
    action,
    stat_name,
    value
FROM v$serv_mod_act_stats
WHERE service_name = 'SALES_APP'
  AND module = 'ORDER_API'
ORDER BY action, stat_name;
~~~

This view provides timing and work metrics for business transactions. VALUE is a cumulative statistic counter; many timing statistics are reported in microseconds.

### 13.4. Viewing Enabled Aggregations

~~~sql
SELECT
    aggregation_type,
    primary_id AS service_name,
    qualifier_id1 AS module_name,
    qualifier_id2 AS action_name
FROM dba_enabled_aggregations
WHERE aggregation_type LIKE 'SERVICE_MODULE%';
~~~

DBA_ENABLED_AGGREGATIONS lists currently active aggregation rules.

### 13.5. Disabling Statistics

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Per Oracle documentation, disabling removes the corresponding cumulative data from V$SERV_MOD_ACT_STATS. If you need to preserve results for analysis, export/save the metrics before disabling.

### 13.6. Persistence

Statistics aggregation by service/module/action is configured at the database scope and persists across instance restarts. In RAC, the configuration applies across instances of the same database.

### 13.7. Action Changes Take Effect on the Next Call

When an application changes module/action inside a user call, statistics for the current call may still be recorded under the old value. The new value takes effect starting on the next user call. Account for this when reconciling exact transaction figures.

## 14. DBMS_MONITOR: SQL Trace by Module/Action

When a specific module/action misbehaves, enable scoped SQL tracing instead of tracing the entire database.

### 14.1. Enabling Trace

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER',
        waits        => TRUE,
        binds        => FALSE
    );
END;
/
~~~

Parameters:

- service_name: database service.
- module_name: target module to trace.
- action_name: target action to trace; wildcard constant supported per API.
- waits: whether to include wait event details in trace.
- binds: whether to capture bind values in trace.
- instance_name: optionally restricts tracing to a single instance.
- plan_stat: frequency for writing row source statistics per supported options.

### 14.2. Why Be Careful with Binds by Default?

Bind values can contain sensitive information such as customer IDs, account numbers, or business payloads. Enabling binds writes that data into trace files. Enable binds only when truly necessary, with controlled access permissions and retention limits.

### 14.3. Database-Wide Tracing Scope

SERV_MOD_ACT_TRACE_ENABLE enables tracing for the service/module/action combination database-wide unless restricted by instance_name. In RAC, trace output can appear across multiple instances and multiple trace files.

### 14.4. Disabling Trace

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Always log both enabling and disabling trace. Never leave broad tracing active after finishing an investigation.

### 14.5. Consolidating Trace Files

Traces for the same module/action can span multiple trace files, especially when multiple server processes handle the workload. Use TRCSESS to consolidate traces by matching criteria, then use TKPROF to format and analyze them.

### 14.6. SQL Tracing Has Overhead

Tracing writes to the filesystem and can impact performance. Target a specific module/action for a short window and disable it once enough data is captured. Avoid database-wide tracing simply because workloads have not been tagged yet.

## 15. CLIENT_IDENTIFIER and DBMS_MONITOR

When tracking a single end user across multiple database sessions, client identifier is often better suited than module/action.

### 15.1. Statistics by Client

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_STAT_ENABLE(
        client_id => 'CUSTOMER-501'
    );
END;
/
~~~

Statistics can be queried in V$CLIENT_STATS.

### 15.2. Trace by Client Identifier

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
        client_id => 'CUSTOMER-501',
        waits     => TRUE,
        binds     => FALSE
    );
END;
/
~~~

Disable:

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
        client_id => 'CUSTOMER-501'
    );
END;
/
~~~

### 15.3. When to Use Which Criterion?

| Objective | Suitable Criterion |
| --- | --- |
| Find all requests belonging to order creation | Service + MODULE + ACTION |
| Track all activity for one end user | CLIENT_IDENTIFIER |
| Inspect one specific database connection | SID + SERIAL# |
| Track workload for an application/service | SERVICE_NAME |
| Find SQL for one business step | MODULE + ACTION |

Multiple criteria can be combined within the same tracing strategy.

## 16. SET_SESSION_LONGOPS: Reporting Progress of Long Operations

DBMS_APPLICATION_INFO also provides SET_SESSION_LONGOPS so applications can report progress of long-running operations into V$SESSION_LONGOPS.

### 16.1. Purpose

Examples:

- Importing millions of rows.
- Synchronizing data across multiple tables.
- Processing large files in batches.
- Recomputing data partition by partition.
- Running a long business workflow with measurable units of work.

The application updates SOFAR and TOTALWORK so DBAs can see how far the operation has progressed.

### 16.2. Main Syntax

~~~sql
DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS(
    rindex      IN OUT BINARY_INTEGER,
    slno        IN OUT BINARY_INTEGER,
    op_name     IN VARCHAR2 DEFAULT NULL,
    target      IN BINARY_INTEGER DEFAULT 0,
    context     IN BINARY_INTEGER DEFAULT 0,
    sofar       IN NUMBER DEFAULT 0,
    totalwork   IN NUMBER DEFAULT 0,
    target_desc IN VARCHAR2 DEFAULT 'unknown target',
    units       IN VARCHAR2 DEFAULT NULL
);
~~~

### 16.3. Progress Update Example

~~~sql
DECLARE
    l_rindex   BINARY_INTEGER;
    l_slno     BINARY_INTEGER;
    l_total    PLS_INTEGER := 100;
BEGIN
    l_rindex := DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS_NOHINT;

    DBMS_APPLICATION_INFO.SET_MODULE(
        'INVENTORY_JOB',
        'SYNC_STOCK'
    );

    FOR i IN 1 .. l_total LOOP
        -- Process a batch or group of records.

        DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS(
            rindex      => l_rindex,
            slno        => l_slno,
            op_name     => 'SYNC_STOCK',
            sofar       => i,
            totalwork   => l_total,
            target_desc => 'inventory batches',
            units       => 'batches'
        );
    END LOOP;

    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

In real code, update progress per batch or at reasonable intervals. Avoid calling SET_SESSION_LONGOPS on every row inside a million-iteration loop unnecessarily.

### 16.4. Key Fields

| Field | Meaning |
| --- | --- |
| OPNAME | Operation name |
| TARGET_DESC | Description of target object being processed |
| SOFAR | Work completed so far |
| TOTALWORK | Estimated total work |
| UNITS | Units for sofar/totalwork |
| ELAPSED_SECONDS | Elapsed execution time |
| TIME_REMAINING | Estimated remaining time |

### 16.5. Querying V$SESSION_LONGOPS

~~~sql
SELECT
    sid,
    serial#,
    opname,
    target_desc,
    sofar,
    totalwork,
    units,
    elapsed_seconds,
    time_remaining,
    message
FROM v$session_longops
WHERE sofar < totalwork
ORDER BY start_time DESC;
~~~

Certain Oracle-managed internal operations also appear in this view, not only application-reported operations.

## 17. MODULE/ACTION in RAC and Multitenant

### 17.1. Oracle RAC

Each session resides on one instance at a time. To find sessions across the entire RAC cluster, use GV$SESSION:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    status,
    sql_id
FROM gv$session
WHERE module = 'ORDER_API'
ORDER BY inst_id, sid;
~~~

DBMS_MONITOR service/module/action tracing can apply across all database instances; restrict with instance_name if needed.

### 17.2. LONG_MODULE_ACTION in RAC

When configuring LONG_MODULE_ACTION, Oracle requires the same setting on all instances. Never leave one node on TRUE and another on FALSE, as module/action strings could truncate differently.

### 17.3. CDB/PDB

In a multitenant database, sessions operate within a container context. When analyzing workloads, include CON_ID or container name when supported by the view:

~~~sql
SELECT
    con_id,
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier
FROM v$session
WHERE module = 'ORDER_API';
~~~

Module/action is session metadata, while service and container identify which database service/PDB the session is running in.

### 17.4. Service Name Is Not Module

Services route and group workloads at the database service layer. Module/action describe functional components and operations inside the application. One service can serve many modules; one module can contain many actions.

## 18. Historical Analysis via ASH/AWR

V$ACTIVE_SESSION_HISTORY samples active sessions and captures module, action, and client identifier. This lets you inspect workload behavior over time rather than only at the current instant.

### 18.1. Viewing In-Memory ASH Samples

~~~sql
SELECT
    sample_time,
    session_id,
    session_serial#,
    sql_id,
    module,
    action,
    client_id,
    event,
    wait_class
FROM v$active_session_history
WHERE module = 'ORDER_API'
  AND sample_time >= SYSTIMESTAMP - INTERVAL '30' MINUTE
ORDER BY sample_time DESC;
~~~

### 18.2. ASH Only Samples Active Sessions

ASH does not record idle periods and is not a complete audit log of every request. Very brief operations may not appear in samples. Supplement with application logs and transaction metrics.

### 18.3. AWR Historical ASH

DBA_HIST_ACTIVE_SESS_HISTORY provides historical ASH persisted by AWR:

~~~sql
SELECT
    sample_time,
    sql_id,
    module,
    action,
    client_id,
    event,
    wait_class
FROM dba_hist_active_sess_history
WHERE module = 'ORDER_API'
ORDER BY sample_time DESC;
~~~

AWR/ASH historical views and related features may require the Oracle Diagnostics Pack license. Verify your organization's licensing before querying pack-licensed views/features. Without that license, use V$SESSION, V$SQL, SQL Trace/TKPROF, and application telemetry as permitted.

## 19. Naming Conventions and Correlation Design

A well-designed metadata convention gives queries and aggregated statistics lasting value.

### 19.1. Suggested Structure

| Attribute | Example | Characteristics |
| --- | --- | --- |
| SERVICE_NAME | SALES_APP | Workload group / connection endpoint |
| MODULE | ORDER_API | Stable functional component |
| ACTION | CREATE_ORDER | Current business step |
| CLIENT_IDENTIFIER | USER-10027 | End user / logical client |
| CLIENT_INFO | node-03;release-2026.11 | Non-sensitive supplementary metadata |

### 19.2. Avoid High Cardinality in Module/Action

Never embed request UUIDs, timestamps, or customer IDs into module/action. If every request generates a distinct action, action-level aggregation fragments and becomes useless.

Use CLIENT_IDENTIFIER for user/client identity, and correlation IDs in application logs or distributed tracing systems for individual request tracking.

### 19.3. Aligning with Application Logs

Application logs can emit:

- Request/correlation ID.
- Module and action.
- Client identifier.
- Database service.
- Connection checkout/return timestamps.
- SQL_ID if captured.

During investigations, DBAs can join database metadata with application logs by module/action/client identifier and timestamp.

### 19.4. Avoid Sensitive Data in Metadata

MODULE/ACTION/CLIENT_INFO/CLIENT_IDENTIFIER are visible to users with read access to relevant views and can surface in traces/monitoring. Store only essential operational labels; never store:

- Passwords or tokens.
- Payment card numbers.
- Full emails/addresses unless strictly necessary.
- Request/response bodies.
- Application secrets.

## 20. Common Issues and Troubleshooting

| Symptom | Possible Cause | Resolution Path |
| --- | --- | --- |
| MODULE/ACTION is NULL | Application never called SET_MODULE/SET_ACTION or already cleared them | Check request lifecycle and tagging points |
| Module/action truncated | Exceeded byte limit or mismatched LONG_MODULE_ACTION | Check parameter and byte lengths |
| Query shows previous request's module | Connection pool reused session without resetting | Set metadata on every checkout and clear before pool return |
| Action unchanged in current call stats | DBMS_MONITOR applies new value starting on next user call | Account for call boundaries when reconciling |
| V$SESSION has module but V$SQLAREA looks unexpected | SQL cursor was parsed under another context or cursor aged/changed | Inspect V$SQL, SQL_ID, child cursors, and parse time |
| SERV_MOD_ACT_STATS has no data | Aggregation not enabled or service/module/action mismatch | Check DBA_ENABLED_AGGREGATIONS and actual tags |
| Action trace captures nothing | Wrong service/module/action or trace already disabled | Verify V$SESSION, API parameters, and instance |
| Trace files scattered across locations | Multiple server processes/instances | Consolidate with TRCSESS |
| Client identifier is wrong | SET_IDENTIFIER not called or pool failed to clear | Set/clear at request boundaries |
| CLIENT_INFO treated as secure data | Field is user-readable and user-writable | Use secure application context for security attributes |
| Longops shows no progress | SET_SESSION_LONGOPS not called or progress update incorrect | Check rindex/slno/sofar/totalwork and view |
| GV$SESSION missing sessions | Insufficient privileges or wrong instance/container filter | Check privileges and instance/container filters |

## 21. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| MODULE is the database username | MODULE is an application-supplied label |
| ACTION only accepts SELECT/INSERT/UPDATE | ACTION is an arbitrary business step name chosen by the application |
| SET_ACTION changes MODULE | SET_ACTION changes only ACTION |
| SET_MODULE changes only MODULE | SET_MODULE sets both MODULE and ACTION |
| MODULE/ACTION reset automatically on COMMIT | They are session metadata and persist across commits |
| CLIENT_INFO and CLIENT_IDENTIFIER are identical | Their purposes and APIs are distinct |
| CLIENT_INFO is safe for tokens | CLIENT_INFO is user-readable/writable; never store secrets |
| CLIENT_IDENTIFIER is a database-authenticated identity | It is an application-supplied client label |
| All versions limit module to 48 / action to 32 | 12.2+ adds LONG_MODULE_ACTION, defaulting to TRUE for 64/64 |
| V$SESSION only shows module while ACTIVE | INACTIVE sessions can retain the last module/action |
| DBMS_APPLICATION_INFO enables SQL trace itself | It only sets tags; DBMS_MONITOR enables stats/tracing |
| DBMS_MONITOR traces only one session | Service/module/action tracing applies database-wide or instance-wide |
| ASH logs every single request | ASH samples active sessions only |
| SET_SESSION_LONGOPS executes background work | It merely publishes progress updated by the application |
| Resetting metadata replaces transaction rollback | They are completely independent operations |

## 22. DBMS_APPLICATION_INFO Implementation Checklist

**Tag Design**

- Does MODULE represent a stable functional component?
- Does ACTION describe the current business step?
- Are UUIDs, timestamps, and high cardinality avoided?
- Do names fit within the database byte limits?
- Is LONG_MODULE_ACTION consistent across RAC nodes?

**Application Integration**

- Are module/action set on the exact physical database connection?
- Is action updated when business steps transition?
- Is metadata reset on both success and exception paths?
- Does the connection pool clean up before returning sessions?
- Is client identifier set/cleared at request boundaries?

**Observability**

- Does V$SESSION display expected module/action values?
- Can V$SQL/V$SQLAREA analyze SQL by module/action?
- Is DBMS_MONITOR aggregation enabled for the right service/module/action?
- Is the team aware of how to disable aggregation/tracing?
- Are trace files governed by retention and access policies?

**Security and Operations**

- Are secrets and sensitive data kept out of metadata?
- Is module/action never used for authorization?
- Is bind tracing enabled only when needed and tightly controlled?
- Are privileges on dynamic performance views verified?
- Are RAC, PDB, and service routing accounted for?

## 23. Comprehensive Hands-On Lab

This lab creates a tagged session, inspects V$SESSION, and enables statistics aggregation by service/module/action. Run it in a lab schema with appropriate privileges.

### Step 1 — Set Module/Action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );

    DBMS_SESSION.SET_IDENTIFIER('LAB-USER-01');
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO('lab-node-01');
END;
/
~~~

### Step 2 — Check Session Metadata

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    client_info,
    status
FROM v$session
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

### Step 3 — Change Action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');
END;
/
~~~

Re-query V$SESSION and observe ACTION.

### Step 4 — Read with READ_MODULE

~~~sql
DECLARE
    l_module VARCHAR2(64);
    l_action VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_MODULE(l_module, l_action);
    DBMS_OUTPUT.PUT_LINE('MODULE=' || l_module);
    DBMS_OUTPUT.PUT_LINE('ACTION=' || l_action);
END;
/
~~~

### Step 5 — Enable Statistics Aggregation

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'RESERVE_STOCK'
    );
END;
/
~~~

Replace SALES_APP with your lab's actual service name.

### Step 6 — Run SQL Under the Tagged Action

~~~sql
SELECT COUNT(*)
FROM user_objects;
~~~

Run it a few times to generate session activity.

### Step 7 — View Module/Action Statistics

~~~sql
SELECT
    service_name,
    module,
    action,
    stat_name,
    value
FROM v$serv_mod_act_stats
WHERE service_name = 'SALES_APP'
  AND module = 'ORDER_API'
ORDER BY stat_name;
~~~

### Step 8 — Disable Aggregation

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'RESERVE_STOCK'
    );
END;
/
~~~

### Step 9 — Reset Session Metadata

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL);
    DBMS_SESSION.CLEAR_IDENTIFIER;
END;
/
~~~

### Step 10 — Verify Reset

~~~sql
SELECT
    module,
    action,
    client_info,
    client_identifier
FROM v$session
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

All values should return NULL after cleanup.

## 24. Self-Check Questions

1. What is DBMS_APPLICATION_INFO used for?
2. How do MODULE and ACTION differ?
3. Which attributes does SET_MODULE set?
4. Does SET_ACTION modify module?
5. What does READ_MODULE return?
6. When should ACTION be set?
7. Why must module/action be reset?
8. What are the default module/action length limits in Oracle 19c?
9. How does LONG_MODULE_ACTION = FALSE alter the limits?
10. Are module/action lengths measured in characters or bytes?
11. How does CLIENT_INFO differ from CLIENT_IDENTIFIER?
12. Which API sets CLIENT_IDENTIFIER?
13. Why should CLIENT_INFO never be used to store tokens?
14. What information does V$SESSION provide?
15. How does V$SQLAREA help analyze workload by module/action?
16. Why can an INACTIVE session still show an ACTION?
17. How can connection pools cause stale module/action tags?
18. Why should cleanup live inside a finally block?
19. What is DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE used for?
20. Which view displays statistics by service/module/action?
21. How does ALL_ACTIONS differ from NULL?
22. When changing an action, do current-call statistics switch immediately?
23. What effect does SERV_MOD_ACT_STAT_DISABLE have on cumulative metrics?
24. What is SERV_MOD_ACT_TRACE_ENABLE used for?
25. Why should you be cautious with binds in traces?
26. What roles do TRCSESS and TKPROF play?
27. Which view exposes progress from SET_SESSION_LONGOPS?
28. What do SOFAR and TOTALWORK represent?
29. Is ASH a complete log of every request?
30. Can MODULE/ACTION be used for authorization?

**Answer Hints:**

1. Tagging application/session metadata for observability, statistics aggregation, and tracing.
2. MODULE represents the functional component; ACTION represents the current task within that module.
3. Both MODULE and ACTION.
4. No, it changes only ACTION.
5. Current module and action.
6. Before each transaction or business step you want to observe.
7. To prevent subsequent requests from inheriting the previous request's labels.
8. LONG_MODULE_ACTION defaults to TRUE: 64 bytes per field.
9. Module 48 bytes, action 32 bytes.
10. Bytes.
11. CLIENT_INFO is supplementary metadata; CLIENT_IDENTIFIER identifies the end user/logical client.
12. DBMS_SESSION.SET_IDENTIFIER.
13. CLIENT_INFO can be read/written by the user and is not secure storage.
14. Active/inactive sessions, status, service, module/action, client details, SQL_ID, and many other attributes.
15. Lists SQL cursors tagged with module/action along with execution statistics.
16. Metadata retains its last-set value until changed or reset.
17. Physical sessions are reused and can carry tags from the prior request.
18. To guarantee cleanup even when exceptions occur.
19. Enables aggregated statistics collection by service/module/action.
20. V$SERV_MOD_ACT_STATS.
21. ALL_ACTIONS is a wildcard matching all actions; NULL represents an empty/unset action.
22. Usually starting from the next user call.
23. Disables aggregation and removes the corresponding cumulative metrics from the view.
24. Enables SQL trace by service/module/action.
25. Bind values may contain sensitive data and get written to trace files.
26. TRCSESS consolidates trace files; TKPROF formats and analyzes them.
27. V$SESSION_LONGOPS.
28. Work completed so far and estimated total work.
29. No, ASH samples active sessions only.
30. No; they are application-supplied metadata, not an authorization mechanism.

## Oracle Reference Documentation

- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html): SET_MODULE, SET_ACTION, READ_MODULE, CLIENT_INFO, and SESSION_LONGOPS.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_MONITOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html): statistics and SQL trace by client/service/module/action.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SESSION.html): SET_IDENTIFIER and CLEAR_IDENTIFIER.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): MODULE, ACTION, CLIENT_INFO, and CLIENT_IDENTIFIER.
- [Oracle Database 19c Database Reference — V$SERV_MOD_ACT_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SERV_MOD_ACT_STATS.html): statistics by service/module/action.
- [Oracle Database 19c Database Reference — LONG_MODULE_ACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/LONG_MODULE_ACTION.html): module/action length limits from 12.2 onward.
- [Oracle Database 19c SQL Tuning Guide — Performing Application Tracing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/performing-application-tracing.html): end-to-end tracing, DBMS_MONITOR, trace files, and TKPROF.
- [Oracle Database 19c Security Guide — Preserving User Identity in Multitiered Environments](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/preserving-user-identity-multitiered-environments.html): client identifiers in multi-tier architectures.

**Principle to remember:** DBMS_APPLICATION_INFO lets applications set MODULE to describe a functional component and ACTION to describe the current business step. Apply tags on the exact physical session, update actions as work progresses, and reset metadata when the request ends. CLIENT_IDENTIFIER identifies the end user/logical client; CLIENT_INFO is merely a supplementary field, never a place for sensitive secrets. Combine MODULE/ACTION with V$SESSION, V$SQLAREA, DBMS_MONITOR, and V$SERV_MOD_ACT_STATS to pinpoint workloads and enable targeted tracing. With connection pools, always clean up session state before returning connections so subsequent requests are never mislabeled.
