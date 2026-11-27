# Preserving Application Context When Correlating Logs with CONNECTION_ID

When an application request runs slowly or fails in MySQL, operators often need to stitch together multiple pieces of evidence: traces in application logs, the active connection session, the SQL statement, lock wait durations, and entries in the general or slow query log. The most useful join key on the MySQL side is the physical session's connection ID. The `CONNECTION_ID()` function returns the current connection's ID; this ID appears in Performance Schema's `PROCESSLIST_ID` column and in the general log's `thread_id` field.

A connection ID identifies only one session on a single MySQL server during a window of time. It is not a trace ID, request ID, or Performance Schema `THREAD_ID`. For reliable investigations, the application must log the connection ID alongside the instance identifier and request trace; MySQL must map that ID properly to threads and statements; and connection pools must manage context per connection checkout.

## 1. Learning Outcomes

After this lesson, you can:

- Explain what a connection ID represents and distinguish it from `THREAD_ID`, request ID, and trace ID.
- Retrieve `CONNECTION_ID()` on the exact connection used by a request and write it to application logs.
- Attach static application metadata to the connection handshake to identify service, version, and instance.
- Attach per-request context to sessions or individual SQL statements without leaking data across connection pool borrows.
- Use `performance_schema.threads`, `session_connect_attrs`, and statement event tables to inspect a connection's activity.
- Correlate connection IDs with the general log, slow query log, and error log within the data scope each log provides.
- Handle reconnects, proxies, replicas, connection pools, and Performance Schema history rollover.

The scope here covers MySQL Server and applications connecting directly or via a connection pool. If a proxy or SQL router sits in between, clarify whether an ID belongs to the client-facing connection or the backend connection to MySQL.

## 2. Which Session Does CONNECTION_ID() Identify?

Each client connection to MySQL is assigned a connection ID by the server. On that connection, run:

~~~sql
SELECT CONNECTION_ID() AS connection_id;
~~~

The result is the identifier of the current session. You can use this ID in diagnostic commands like `SHOW PROCESSLIST` or `KILL QUERY`, and correlate it with `PROCESSLIST_ID` in Performance Schema.

For example, an application handling a checkout request receives connection ID 18427. Opening an administrative connection to the same MySQL instance, an operator can look up session 18427 in the active thread list. The admin connection uses a different connection ID; that does not affect looking up the checkout session's ID.

### 2.1. Distinguishing Identifier Types

| Value | Meaning | Where Commonly Found |
|---|---|---|
| CONNECTION_ID() | Current client session ID on MySQL Server | SQL function, PROCESSLIST_ID, general log |
| PROCESSLIST_ID | Connection ID represented in Performance Schema thread rows | performance_schema.threads |
| THREAD_ID | Internal Performance Schema ID used to join event tables | performance_schema.threads and events_* tables |
| request_id | ID of a business request or job execution | Application logs, messages, or jobs |
| trace_id | ID linking spans across a distributed trace | Tracing systems |
| span_id | ID of a single processing segment inside a trace | Tracing systems |

Never compare `CONNECTION_ID()` directly against `THREAD_ID`. To find statement events for a connection, first map `PROCESSLIST_ID` to `THREAD_ID` via `performance_schema.threads`, then use `THREAD_ID` to query `events_statements_*` tables.

Nor is a connection ID a globally permanent key. It is scoped to one MySQL instance and one connection session. After reconnecting, the application receives a new ID. When investigating across restarts, failovers, or multiple servers, also record the instance identifier, endpoint or primary/replica role, and timestamp. Never use a raw connection ID alone to identify sessions across an entire cluster.

### 2.2. Physical Connections vs. Logical Requests

A connection pool holds a set of physical MySQL connections and lends them sequentially to many requests. Different requests can reuse the same connection ID at different times:

~~~text
Request A ── borrows physical connection 18427 ── returns connection
Request B ── re-borrows connection 18427 ────── returns connection
Request C ── borrows physical connection 18431 ── returns connection
~~~

Therefore, a connection ID tells you which session executed SQL, but not by itself which request sent that SQL. Applications must log `trace_id` or `request_id` in the same log entry alongside the connection ID. When a single request uses multiple connections, log each participating connection or emit a dedicated event per borrow.

## 3. Building a Correlation Chain from Application to MySQL

A correlation chain can be structured as follows:

~~~text
HTTP request / message / scheduled job
              |
              v
     trace_id, request_id
              |
              v
  application acquires pooled connection
              |
              +---- SELECT CONNECTION_ID()
              |
              v
  application log: trace + db instance + connection_id
              |
              v
         MySQL Server
              |
              +---- PROCESSLIST_ID -> THREAD_ID
              |                         |
              |                         +--> statement event history
              |
              +---- general log thread_id
              |
              +---- slow log connection Id (if format includes it)
              |
              +---- connection attributes
~~~

Each component answers a different question:

- Application logs show which business request ran, who triggered it, which trace tracks it, and which connection the app borrowed.
- The connection ID ties request activity to a specific MySQL session.
- Performance Schema shows which internal thread corresponds to that connection and which statement events remain in history buffers.
- The general log shows commands received by the server, including short statements absent from the slow query log.
- The slow query log focuses on statements exceeding configured thresholds; some formats include an Id field identifying the connection.
- The error log records server events. Not all error log messages include a connection ID, so it cannot serve as a universal join key for all errors.

Standardize field names in application logs, such as `db_instance`, `db_connection_id`, `db_user`, `db_schema`, `request_id`, and `trace_id`. Preserve the numeric type of the connection ID when logging; avoid conversions that could lose precision.

## 4. Fetching Connection ID on the Request's Own Connection

The most critical rule is querying `CONNECTION_ID()` on the exact connection object used to execute the business work. Calling it on an administrative connection or another connection drawn from the pool will not represent the session executing the SQL under investigation.

JDBC example:

~~~java
long readConnectionId(Connection connection) throws SQLException {
    String sql = "SELECT CONNECTION_ID()";
    try (Statement statement = connection.createStatement();
         ResultSet result = statement.executeQuery(sql)) {
        if (!result.next()) {
            throw new SQLException("MySQL did not return CONNECTION_ID()");
        }
        return result.getLong(1);
    }
}
~~~

After acquiring a connection, the application reads the ID and logs it with request context:

~~~java
try (Connection connection = dataSource.getConnection()) {
    long connectionId = readConnectionId(connection);

    logger.info(
        "mysql connection acquired",
        kv("trace_id", traceId),
        kv("request_id", requestId),
        kv("db_instance", dbInstance),
        kv("db_connection_id", connectionId)
    );

    // Execute business SQL statements on this exact connection.
}
~~~

This is an illustrative example; the `kv` helper depends on your application's logging library. If your pool provides a hook when creating physical connections, you can cache the connection ID in connection metadata after verifying the driver's reconnect behavior. Even with caching, you must still log that ID on each request checkout. If the driver auto-reconnects or a proxy switches backends, refresh the identifier appropriately.

A helpful structured log entry typically includes:

~~~json
{
  "timestamp": "2026-11-19T07:15:32.412Z",
  "level": "INFO",
  "event": "mysql_connection_acquired",
  "service": "orders-api",
  "service_instance": "orders-api-7f3a",
  "environment": "production",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-20261119-00421",
  "db_instance": "mysql-orders-primary-a",
  "db_connection_id": 18427,
  "db_schema": "orders"
}
~~~

Use UTC timestamps or a consistent time convention. Synchronize clocks across applications, MySQL Servers, and log collectors so events can be compared chronologically. If a request hits both a primary and a replica, log the instance and connection ID separately for each endpoint.

Do not place connection IDs into every metric label. High-cardinality IDs cause time-series counts to explode. Keep IDs in logs or traces; metrics should use bounded label sets such as service, instance, operation, and database role.

## 5. Attaching Static Attributes at Connection Handshake

MySQL accepts connection attributes sent by clients during the handshake. These attributes help identify the service, application version, runtime, or process instance. They describe the connection source and typically persist for the lifetime of the physical connection.

Performance Schema provides `performance_schema.session_connect_attrs`:

~~~sql
SELECT
    PROCESSLIST_ID AS connection_id,
    ATTR_NAME,
    ATTR_VALUE,
    ORDINAL_POSITION
FROM performance_schema.session_connect_attrs
WHERE PROCESSLIST_ID = 18427
ORDER BY ORDINAL_POSITION;
~~~

`PROCESSLIST_ID` in this table is the connection ID. A client may send multiple key/value pairs; order is tracked via `ORDINAL_POSITION`. Default attributes and specific attribute names depend on the client library or connector.

For example, MySQL Connector/J supports custom attributes via `connectionAttributes`. Illustrative configuration:

~~~text
jdbc:mysql://db.example:3306/orders?connectionAttributes=service:orders-api,service_instance:orders-api-7f3a,environment:production
~~~

Verify syntax and connector version in use, especially when values require URL encoding. Different connectors have their own attribute syntax; if the client does not send attributes, the server cannot infer the service name from requests.

Connection attributes fit relatively static metadata:

- Service or application name.
- Build or release version.
- Process instance identifier.
- Runtime, platform, or deployment environment.

Never use connection attributes to store per-request `request_id` or `trace_id`. When a pool reuses a connection, handshake attributes continue describing the process that opened the connection and do not update automatically per borrowing request.

If the table lacks expected data, check whether Performance Schema is enabled, whether the connector sends attributes, and the server's attribute buffer limit via `performance_schema_session_connect_attrs_size`. Overly long attributes or excess size may be truncated. Never raise limits arbitrarily without accounting for memory and metadata footprint.

## 6. Attaching Per-Request Context on Connection Pools

When server-side request context is needed while a request holds a connection, you can set user-defined session variables:

~~~sql
SET
    @app_service = 'orders-api',
    @app_request_id = 'req-20261119-00421',
    @app_trace_id = '4bf92f3577b34da6a3ce929d0e0e4736';

SELECT
    CONNECTION_ID() AS connection_id,
    @app_service AS app_service,
    @app_request_id AS request_id,
    @app_trace_id AS trace_id;
~~~

These variables belong to the current session. Code running on that connection can read them back; the `SET` statement also leaves a marker in logs if statement logging is active. On MySQL 8.0.22 and later, Performance Schema provides `performance_schema.user_variables_by_thread` to inspect user-defined variables by `THREAD_ID` from an admin session, if the table is available and the account has read privileges. To inspect another connection externally, first map `PROCESSLIST_ID` to `THREAD_ID`; running `SELECT @app_request_id` on an admin connection only reads the admin connection's own variable.

For example, after finding `THREAD_ID=731`:

~~~sql
SELECT THREAD_ID, VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.user_variables_by_thread
WHERE THREAD_ID = 731
  AND VARIABLE_NAME IN ('app_service', 'app_request_id', 'app_trace_id')
ORDER BY VARIABLE_NAME;
~~~

This table helps verify whether context is still attached to a session. Values disappear if unset, if the session resets, or when the thread exits. On versions lacking this table, rely on application logs, statement history, and in-session inspection. Because this table can expose user variables across threads, restrict read access and never store secrets in session variables.

### 6.1. Connection Pool Rules

One physical connection is borrowed by many requests sequentially. Therefore, on every checkout, reassign all context variables used by the application—even when the new value is NULL. Upon returning the connection, clear context in a cleanup block or use a verified connector/pool session-reset mechanism.

You can set values with a prepared statement:

~~~sql
SET
    @app_service = ?,
    @app_request_id = ?,
    @app_trace_id = ?;
~~~

Pass values via bind parameters. Never concatenate request data directly into SQL strings. If a field has no value, still bind NULL to overwrite stale data from the previous borrow.

At request end, clear them explicitly:

~~~sql
SET
    @app_service = NULL,
    @app_request_id = NULL,
    @app_trace_id = NULL;
~~~

Place cleanup inside a `finally` block or connection-return hook so it runs even if business SQL throws an exception. If cleanup fails, mark the connection dirty and evict it from the pool per pool policy; never return a session with indeterminate context to the next request.

### 6.2. Why ROLLBACK Does Not Clear User Variables

User-defined session variables belong to session state, not transactional data. `ROLLBACK` undoes data changes within a transaction, yet it does not clear `@app_request_id` or `@app_trace_id`. Therefore, never rely on rollback as a context cleanup mechanism.

Some connectors or pools reset sessions using `COM_RESET_CONNECTION` or an equivalent protocol command. That mechanism may clear session state, though you must verify driver version, pool configuration, and actual behavior. Even with session reset enabled, applications should explicitly assign full context on checkout rather than relying on residual state.

Never store passwords, access tokens, personal data, or sensitive content in session variables. Those values can appear in the general log, statement history, or diagnostic dumps. Pass only opaque, time-bounded, non-secret IDs.

## 7. Using SQL Comments to Tag Individual Statements

When the goal is tying a specific SQL statement to the request that issued it, prepend a comment to the statement:

~~~sql
/* service=orders-api request=req-20261119-00421 trace=4bf92f3577b34da6a3ce929d0e0e4736 */
SELECT order_id, status
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 20;
~~~

Comments let readers spot the request or operation directly inside recorded SQL text. This helps when one connection executes many statements or when a request runs only a few tracked queries.

Verify that comments survive intact through your driver, ORM, proxy, and logging pipeline. Some middleware layers strip or normalize comments. Performance Schema records both `SQL_TEXT` and `DIGEST_TEXT`: `SQL_TEXT` is better suited for inspecting original queries; `DIGEST_TEXT` is normalized for grouping and may strip comments rather than preserving them as trace tags. Never rely on digests to search for a specific request ID.

Keep comments concise, use safe characters, and interpolate only controlled values. Never concatenate arbitrary user input into comments. Do not confuse tracing comments with optimizer hints using `/*+ ... */` syntax. Adding request IDs to every statement also enlarges logs and can affect statement grouping; use it when diagnostic value outweighs storage cost.

Comments and session variables serve different roles. A comment attaches to a specific statement and travels with its SQL text. A session variable attaches to connection state and can be queried inside that session. Connection attributes attach to the handshake and describe the process that opened the connection. You can combine them, while still logging trace/request IDs in application logs.

## 8. Mapping Connection ID to Performance Schema THREAD_ID

`performance_schema.threads` tracks threads monitored by Performance Schema. `PROCESSLIST_ID` is the connection ID; `THREAD_ID` is the internal key for joining event tables.

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID AS connection_id,
    NAME,
    TYPE,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE PROCESSLIST_ID = 18427;
~~~

If the query returns a row, record `THREAD_ID` to query statement history. If no row appears, the connection may have closed, the ID may belong to another instance, or traffic passed through a proxy and your ID is client-side. MySQL background threads normally lack a client `PROCESSLIST_ID`.

Do not confuse `PROCESSLIST_INFO` with full history. That column reflects only the thread's current statement and is `NULL` while idle. To view recent statements, query `events_statements_*` tables.

### 8.1. Viewing Statement History for a Thread

Once you have `THREAD_ID`, query per-thread history:

~~~sql
SELECT
    EVENT_ID,
    EVENT_NAME,
    SQL_TEXT,
    DIGEST_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO,
    RETURNED_SQLSTATE,
    MESSAGE_TEXT
FROM performance_schema.events_statements_history
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 20;
~~~

Replace `731` with the `THREAD_ID` from the previous query. `TIMER_WAIT` is expressed in picoseconds; divide by 10^12 to convert to seconds. Error and row-count columns help distinguish failed statements, large result sets, and broad scans.

`events_statements_history` retains recent events per thread. `events_statements_history_long` holds a shared history buffer across threads. Both are bounded ring buffers; older events are overwritten when full. Neither is durable long-term storage for arbitrary querying days later.

You can query the shared history buffer:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO
FROM performance_schema.events_statements_history_long
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 50;
~~~

If the connection has already closed, its row in `performance_schema.threads` may no longer exist to map `PROCESSLIST_ID` to `THREAD_ID`. Historical events may remain in `history_long`, yet finding the right `THREAD_ID` after the thread vanishes requires having logged the mapping beforehand. That is why you should capture connection ID, instance, and statement/log context while the session is active.

### 8.2. Checking Consumers and Instruments

Performance Schema collects only enabled event classes. Check consumers:

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
)
ORDER BY NAME;
~~~

Check statement instruments:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
ORDER BY NAME
LIMIT 30;
~~~

If required statement consumers or instruments are disabled, history may be empty or missing timings. Enable only the instrumentation groups you need, weighing overhead and buffer capacity. You can enable history consumers during a controlled diagnostic window:

~~~sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);
~~~

Updating setup tables must be done by an authorized account per operational policy. `history_long` sizing is controlled by Performance Schema startup variables; resizing may require a restart. Never enable all instruments in production just to trace one request without evaluating impact.

## 9. Correlating with MySQL Log Types

### 9.1. General Query Log

The general query log records connections and commands received by the server. When logged to `TABLE`, query `mysql.general_log`:

~~~sql
SELECT
    event_time,
    user_host,
    thread_id,
    command_type,
    argument
FROM mysql.general_log
WHERE thread_id = 18427
ORDER BY event_time DESC
LIMIT 100;
~~~

In the general log, `thread_id` is the connection ID. It joins directly to `CONNECTION_ID()` or `PROCESSLIST_ID`. When logged to `FILE`, entries also include the thread ID to identify the connection.

The general log can generate massive data volumes and expose SQL text or sensitive values. Enable it only for a specific investigation goal, bounded duration, with restricted read access, and a plan to turn it off afterward. Querying `mysql.general_log` reflects only records written to `TABLE`; if `log_output` writes solely to `FILE`, the table will lack new events. Never assume the table is always populated.

### 9.2. Slow Query Log

The slow query log records only statements meeting configured criteria, such as exceeding `long_query_time` or related flags. Many slow log formats include a `User@Host` line with `Id`; this `Id` correlates with connection ID. Check the exact log format of your MySQL version and log collector before writing parsers.

The slow log helps identify slow queries, lock wait times, rows sent, and rows examined. It is not a complete record of every SQL statement on a connection. If a request fails quickly or statements fall below thresholds, they will not appear in the slow log.

### 9.3. Error Log

The error log focuses on server events such as startup errors, storage engine errors, warnings, connection failures, or subsystem messages. Structure and fields depend on version, log components, and sinks. Some messages carry thread/connection IDs; many do not.

Use connection ID to link error log entries only when an entry explicitly includes a meaningful ID. Otherwise correlate by timestamp, instance, host, user, server state, and related application events. Avoid assuming every server error came from the nearest connection ID appearing in the log.

## 10. Workflow for Investigating a Slow or Failed Request

Suppose application logs record `request_id=req-20261119-00421`, `trace_id=4bf92f...`, and `db_connection_id=18427`.

1. **Identify the exact MySQL instance.** Use `db_instance` or the logged endpoint. With multiple replicas, proxies, or clusters, confirm which node served the request at that timestamp.
2. **Locate the request in application logs.** Read events before and after acquiring the connection, query start/end times, retries, timeouts, and exceptions. Determine whether the request used one or multiple connections.
3. **Locate the active connection.** On the target instance, query `performance_schema.threads` where `PROCESSLIST_ID=18427`. Save `THREAD_ID` if present.
4. **Read statement events.** Use `THREAD_ID` to inspect `events_statements_current`, `events_statements_history`, or `events_statements_history_long`. Check `SQL_TEXT`, `TIMER_WAIT`, `ROWS_EXAMINED`, errors, and timestamps.
5. **Cross-check SQL logs.** Search `thread_id=18427` in the general log if logged to `TABLE`, or the matching `Id` in the slow query log if present in your format.
6. **Inspect connection attributes.** Use `session_connect_attrs` to confirm which service, version, and process instance opened the connection. This helps spot requests routed to the wrong service or deployment.
7. **Compare timing and context.** Normalize timestamps and inspect transactions, wait states, preceding statements, and retries. A request may stall on locks or wait in the connection pool before MySQL ever receives SQL.
8. **Conclude from evidence.** Separate pool wait time, connection establishment, SQL execution, lock wait, and application processing time. The connection ID links the session; it does not by itself prove why it was slow.

If the thread still exists while `PROCESSLIST_INFO` is NULL, the session may be idle or waiting for the application's next statement. Inspect statement history and application logs to see earlier commands. If the thread is gone, fall back to general/slow logs, traces, and previously collected telemetry; Performance Schema cannot reconstruct a lost session mapping retroactively.

## 11. Scenarios That Commonly Skew Results

### 11.1. Connection Pool Session Reuse

A single connection ID can appear in logs for many requests over time. Never lump every statement on a connection into one request. Use `request_id`/`trace_id` and timestamps to separate borrows. Reassign full session context on checkout and clear it on return.

### 11.2. Automatic Application Reconnects

When a connection drops and the driver opens a new session, the connection ID changes. If the application cached the ID only at pool creation, logs will misattribute SQL to the old ID. Refresh the ID after reconnects or on every checkout per driver design, and log connection-change events.

### 11.3. Proxies or SQL Routers

At least two sessions may exist: client-to-proxy and proxy-to-MySQL backend. The client-side ID does not necessarily match `PROCESSLIST_ID` on the backend. Proxies can multiplex or reuse backend connections under their own policies. When using a proxy, collect IDs on both sides if supported, along with proxy node, backend endpoint, and routing timestamps. Never assume the driver's ID is always the ID seen inside MySQL.

### 11.4. One Request Using Multiple Connections

A single request may read from a replica, write to a primary, or run parallel tasks. One `trace_id` then maps to multiple connection IDs. Log each `(db_instance, db_connection_id)` pair in its own span or event, tagged with the operation, to track which SQL ran on which node.

### 11.5. Treating Connection ID as a Long-Lived Key

Connection IDs are meaningful only within one instance and session lifetime. For multi-day investigations, also store a stable operational instance identifier, timestamp, endpoint, and role. After failover, the same numeric ID on another node does not represent the same session.

### 11.6. Overwritten Historical Data

`events_statements_history` and `events_statements_history_long` have bounded capacity. Investigating too late means events may have rolled over. General and slow query logs also depend on settings, rotation, and retention. If investigations occur hours or days later, ship needed logs to centralized storage with proper retention.

## 12. End-to-End Example: Tracing a Checkout Request

Suppose the `orders-api` service receives a checkout request. Trace middleware supplies `trace_id`; the business layer generates `request_id`. Upon borrowing a pooled connection, the application executes in order:

~~~sql
SELECT CONNECTION_ID();

SET
    @app_service = 'orders-api',
    @app_request_id = 'req-20261119-00421',
    @app_trace_id = '4bf92f3577b34da6a3ce929d0e0e4736';
~~~

The application logs connection ID, `db_instance`, `trace_id`, and `request_id`. Afterward, the business query can carry a comment:

~~~sql
/* service=orders-api request=req-20261119-00421 trace=4bf92f3577b34da6a3ce929d0e0e4736 */
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 20;
~~~

During an investigation, the operator uses the logged connection ID:

~~~sql
SELECT THREAD_ID, PROCESSLIST_ID, PROCESSLIST_USER,
       PROCESSLIST_HOST, PROCESSLIST_DB, PROCESSLIST_COMMAND,
       PROCESSLIST_TIME, PROCESSLIST_STATE
FROM performance_schema.threads
WHERE PROCESSLIST_ID = 18427;
~~~

Suppose it returns `THREAD_ID=731`. Query statement history:

~~~sql
SELECT EVENT_ID, SQL_TEXT, DIGEST_TEXT,
       ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
       ROWS_EXAMINED, ROWS_SENT, MYSQL_ERRNO, RETURNED_SQLSTATE
FROM performance_schema.events_statements_history
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 20;
~~~

Next, verify the service and process that opened the connection:

~~~sql
SELECT ATTR_NAME, ATTR_VALUE
FROM performance_schema.session_connect_attrs
WHERE PROCESSLIST_ID = 18427
ORDER BY ORDINAL_POSITION;
~~~

If the general log is writing to `TABLE`, inspect commands on the same session:

~~~sql
SELECT event_time, command_type, argument
FROM mysql.general_log
WHERE thread_id = 18427
ORDER BY event_time DESC
LIMIT 100;
~~~

When the request completes, the application clears session context before returning the connection:

~~~sql
SET
    @app_service = NULL,
    @app_request_id = NULL,
    @app_trace_id = NULL;
~~~

This workflow creates verifiable links: traces identify the request; application logs capture connection ID and instance; `PROCESSLIST_ID` maps to `THREAD_ID`; statement history reveals SQL; connection attributes confirm the opening process; and general/slow logs provide extra evidence when enabled and retained.

## 13. Security and Observability Overhead

Connection IDs and trace IDs are not secrets on their own, yet logs combining them with users, hosts, schemas, SQL text, and business data can expose sensitive details. Apply these safeguards:

- Never put passwords, tokens, session cookies, or personal data into connection attributes, session variables, or SQL comments.
- Restrict read permissions on `performance_schema`, `mysql.general_log`, and centralized logs by operational role.
- Avoid leaving the general log enabled for long periods on high-traffic systems; set time limits, monitor disk usage, and turn it off after investigations.
- Never turn request IDs or connection IDs into high-cardinality metric labels.
- Sanitize and bound metadata lengths; never accept arbitrary comments or attributes from external user input.
- Enforce retention, masking, and access controls on SQL text, as statements may contain sensitive literals or business logic.
- Evaluate the overhead of Performance Schema consumers/instruments before enabling them broadly in production.

## 14. Troubleshooting Table

| Symptom | Common Cause | How to Check |
|---|---|---|
| PROCESSLIST_ID not found | Session closed, wrong instance, or ID belongs to proxy/client | Verify db_instance, timestamp, reconnects, and backend endpoint |
| Thread exists but no statement history | Consumer/instrument off, thread ran no statements yet, or history overwritten | Check setup_consumers, setup_instruments, and collection timing |
| No connection attributes | Connector did not send them, Performance Schema off, or attribute buffer limit | Check connector config and performance_schema_session_connect_attrs_size |
| Different requests share same connection ID | Pool reuses physical connections | Separate by request_id, trace_id, and timestamp; reset context on checkout/return |
| Prior request's session context appears in next request | Failed to reassign or clean up user variables | Assign all variables on checkout, clean up in finally, check pool reset |
| Comment missing from SQL_TEXT/logs | Driver, ORM, or proxy normalized SQL | Inspect actual SQL at each layer and cross-check application logs |
| App ID does not match MySQL ID | Proxy created backend session or driver reconnected | Log IDs on the right side, backend node, and reconnect events |
| Query missing from slow log | Statement fell below threshold or log disabled | Use statement history/general log during an appropriate window |
| Cannot link error log to request | Entry lacks a connection ID | Correlate by instance, timestamp, subsystem, and app trace logs |
| Events missing after some time | Ring buffer overwritten or server restarted | Collect/export events early and use centralized logs with retention |

## 15. Hands-On Exercises

### Exercise 1: Distinguish PROCESSLIST_ID and THREAD_ID

1. Open a client connection and run `SELECT CONNECTION_ID()`.
2. From an admin connection, look up that ID in `performance_schema.threads`.
3. Record both `PROCESSLIST_ID` and `THREAD_ID`.
4. Use `THREAD_ID` to query `events_statements_history`.
5. Explain why `CONNECTION_ID()` must not be used directly as a `THREAD_ID`.

Expected outcome: you demonstrate mapping via `performance_schema.threads` without confusing the two ID spaces.

### Exercise 2: Track a Connection Through a Pool

1. Configure an application to borrow connections from a pool.
2. Log connection ID together with `request_id` on checkout.
3. Send two sequential requests so the pool has a chance to reuse the same connection.
4. Compare connection ID and request ID in the logs.
5. Set session variables on the first request, then verify the second request cannot read stale context.

Expected outcome: you observe that connection ID can repeat while request ID differs, and session context must be managed across the checkout/return lifecycle.

### Exercise 3: Compare Connection Attributes with Request Context

1. Send service, service instance, and environment via connection attributes.
2. Read the values from `performance_schema.session_connect_attrs`.
3. Set `@app_request_id` inside one request.
4. Re-borrow the connection and inspect the session variable value.
5. Explain why connection attributes describe the process that opened the connection whereas user variables describe current session state.

Expected outcome: you choose the right mechanism for static metadata versus per-request metadata.

### Exercise 4: Investigate a Slow SQL Query

1. Record connection ID and trace ID from application logs.
2. Locate the matching thread in `performance_schema.threads`.
3. Inspect statement history and record `SQL_TEXT`, `TIMER_WAIT`, and `ROWS_EXAMINED`.
4. If slow logs are available, locate the matching `Id`.
5. Determine whether the delay occurred in the pool, connection setup, SQL execution, or lock waits using timestamps.

Expected outcome: an investigation report containing instance, request, connection ID, `THREAD_ID`, SQL statement, and timing evidence.

## 16. Implementation Checklist

- [ ] Application fetches `CONNECTION_ID()` on the exact connection executing business work.
- [ ] Application logs record `trace_id`, `request_id`, `db_instance`, and `db_connection_id`.
- [ ] Connection attributes contain static metadata, never secrets or per-request context.
- [ ] Request context is fully assigned on checkout and cleared/reset on return.
- [ ] Cleanup still runs when statements fail or transactions roll back.
- [ ] Performance Schema queries distinguish `PROCESSLIST_ID` from `THREAD_ID`.
- [ ] Consumers/instruments are enabled purposefully with overhead evaluated.
- [ ] General/slow logs follow capacity, access control, and retention policies.
- [ ] Systems with proxies/reconnects record accurate backend instances and connection mappings.
- [ ] Timestamps are standardized and clocks across components are synchronized.
- [ ] Trace/request IDs stay in logs or traces, never becoming high-cardinality metric labels.
- [ ] Runbooks document how to proceed when a thread has closed or event history rolled over.

## 17. Reference Documentation

When deploying on a specific MySQL version, verify behavior and column names against the matching MySQL Reference Manual:

- Information Functions: `CONNECTION_ID()`.
- Performance Schema: `threads` table and `PROCESSLIST_ID`.
- Performance Schema: `session_connect_attrs` table.
- Performance Schema: `user_variables_by_thread` table (MySQL 8.0.22 and later).
- Performance Schema: statement event tables, `setup_consumers`, and `setup_instruments`.
- The General Query Log and The Slow Query Log.
- MySQL Connector/J: `connectionAttributes` property.

Always verify your actual MySQL Server, connector, pool, and proxy versions. Support for connection attributes, log formats, and Performance Schema configuration can differ across versions and deployments.
