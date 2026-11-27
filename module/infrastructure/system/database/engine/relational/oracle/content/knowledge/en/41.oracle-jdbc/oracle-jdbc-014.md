# Statement Caching, Server-Side Cursors, and Handling ORA-01000

Oracle JDBC allows Java applications to send SQL to Oracle Database via Connection, Statement, PreparedStatement, CallableStatement, and ResultSet objects. Each SQL execution may cause Oracle to allocate or reuse a server-side cursor to parse, execute, and fetch data. If an application opens too many cursors in a session without closing them properly, the database may return ORA-01000: maximum open cursors exceeded.

Statement caching reduces the cost of repeatedly creating statements and parsing SQL. However, caching also retains statements/cursors for reuse. If the cache size is too large—combined with a large connection pool or code that fails to close ResultSets/Statements—the number of cursors used per session can climb significantly.

Four mechanisms must be clearly distinguished:

- **JDBC statement cache:** caches PreparedStatements/CallableStatements on the Oracle JDBC connection side for statement reuse.
- **Server-side cursor:** cursor state maintained by Oracle inside a session to execute SQL and return results.
- **SESSION_CACHED_CURSORS:** caches cursors on the Oracle session side to reduce soft parses when SQL is closed and reopened.
- **OPEN_CURSORS:** limits the number of cursor handles a single session can have open.

These mechanisms are related but do not replace each other. Statement caching does not allow skipping close(); SESSION_CACHED_CURSORS does not fix leaks; raising OPEN_CURSORS does not resolve root causes if the application continuously opens statements without closing them.

## 1. Statements and cursors in Oracle JDBC

When Java executes SQL, the application typically interacts with a JDBC Statement object. On the Oracle side, the SQL is parsed and bound to a cursor so the database can manage execution state.

A typical query flow:

~~~text
Java application
      |
      v
JDBC Connection
      |
      v
PreparedStatement
      |
      | executeQuery()
      v
Oracle JDBC driver
      |
      v
Oracle session
      |
      v
Server cursor
      |
      +---- parse
      +---- execute
      +---- fetch
      |
      v
ResultSet returned to Java
~~~

A JDBC Statement is a client/driver-side object. A server cursor is a database-side resource and execution state. A PreparedStatement is not merely a SQL string in Java; it can be associated with a server-side cursor and related state.

### 1.1 Parse, execute, and fetch

SQL execution typically involves these phases:

1. **Parse:** Oracle checks syntax, object names, privileges, bind variables, and finds or creates a matching cursor.
2. **Execute:** Oracle runs the statement, sets up execution state, and processes bind values.
3. **Fetch:** for queries, Oracle returns chunks of results back to the JDBC driver.
4. **Close:** the application closes ResultSet/Statement; driver and database release resources or place them into the appropriate cache.

Parsing can be a hard parse or a soft parse. A hard parse is more expensive because Oracle must analyze the SQL and build an execution plan when no matching cursor exists in the shared pool. A soft parse reuses existing information, yet still incurs parsing and session cursor management overhead.

Statement caching helps reuse statements on the JDBC side and can reduce parse round trips. It does not mean Oracle skips execute/fetch steps on subsequent runs.

### 1.2 Server cursors are not the same as SQL text in the shared pool

Oracle maintains a shared SQL area/library cache containing SQL information shared across sessions where possible. Each session still holds its own cursor handles and state to execute SQL.

Consequently:

- A SQL text can share an execution plan in the shared pool.
- Multiple sessions can execute that same SQL text simultaneously.
- Each session still keeps its own cursor handle.
- Closing a JDBC statement does not necessarily remove SQL from the shared pool.
- A cursor cached in the session may still appear in cursor monitoring views.

Do not look at row counts in V$SQL and conclude that is a session's open cursor count. To investigate ORA-01000, inspect the exact session and cursor state.

## 2. JDBC object lifecycle

JDBC objects have lifecycle relationships:

- Connection creates Statement/PreparedStatement/CallableStatement.
- Statement executes SQL and creates ResultSet.
- ResultSet holds result-reading state.
- CallableStatement can return ResultSets or REF CURSORs via OUT parameters.
- Closing objects in proper order lets the driver release resources.

Basic query example:

~~~java
String sql =
    "SELECT order_id, status FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Process current row.
        }
    }
}
~~~

Try-with-resources calls close even when exceptions occur. When ResultSet closes, the result cursor is released per driver mechanics. When PreparedStatement closes, the driver either destroys the statement or places it into the implicit statement cache if caching is enabled and the statement is eligible.

### 2.1 Why close both ResultSet and Statement?

Closing Connection should not be relied upon as the sole cleanup mechanism for all resources. In applications with a connection pool, Connection.close() normally only returns the logical connection to the pool; the physical database session may remain alive.

If code fails to close ResultSet/Statement:

- Cursors may remain open inside the session.
- Statements may retain references to ResultSets.
- The connection pool may reuse physical sessions with leftover resources.
- ORA-01000 can surface after some time even though individual requests appear to work normally.

Close ResultSet right after reading finishes, then close Statement, and only then return Connection to the pool.

### 2.2 Statement.close() and ResultSet.close()

Per JDBC, closing a Statement closes any current ResultSet created by that statement. However, code should explicitly close ResultSet inside try-with-resources to clarify ownership and ensure resources release immediately when the read loop finishes.

If a Statement returns multiple result sets or update counts, process all results and close them per the JDBC API. Never keep a ResultSet open longer than necessary.

### 2.3 CallableStatement and REF CURSOR

Stored procedures can return cursors via OUT parameters. Example with Oracle REF CURSOR:

~~~java
String call = "{ call order_api.get_orders(?, ?) }";

try (Connection connection = dataSource.getConnection();
     CallableStatement statement = connection.prepareCall(call)) {

    statement.setLong(1, customerId);
    statement.registerOutParameter(2, oracle.jdbc.OracleTypes.CURSOR);
    statement.execute();

    try (ResultSet resultSet =
             (ResultSet) statement.getObject(2)) {
        while (resultSet.next()) {
            // Read data.
        }
    }
}
~~~

The example uses the Oracle JDBC extension OracleTypes.CURSOR. With newer drivers and APIs, the registration type may differ; use the REF CURSOR type supported by your running version.

Closing the ResultSet returned from a REF CURSOR is critical. Closing the CallableStatement upon completion is also necessary. If a procedure opens multiple REF CURSORs and the application only reads one, remaining cursors can continue holding resources until closed.

## 3. What is a statement cache?

A statement cache stores prepared statements so subsequent prepareStatement calls can retrieve the cached statement instead of creating one from scratch.

Oracle JDBC supports statement caching on Oracle connections. Two main forms:

- **Implicit statement caching:** the driver automatically locates a matching statement based on SQL and statement attributes.
- **Explicit statement caching:** the application manages cache keys and requests statements by key via corresponding Oracle JDBC APIs.

For most applications, implicit statement caching is easier to use. The application still calls prepareStatement normally and closes the statement after use. With caching enabled, close returns the statement to the cache rather than destroying it completely.

### 3.1 Benefits

Statement caching can:

- Reduce the cost of repeatedly allocating PreparedStatements.
- Reduce parse overhead and prepare round trips.
- Reuse prepared cursors/statements.
- Increase throughput for workloads with a stable set of SQL statements.
- Reduce shared pool pressure by limiting repeated parses, depending on workload.

Caching helps when an application frequently executes the same SQL with different bind values:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = :status
~~~

Instead of generating different SQL text per customer, the application uses bind variables and reuses PreparedStatements.

### 3.2 Statement cache is not a query result cache

A statement cache stores prepared statements, not query results. Calling executeQuery with new bind values still executes the SQL on Oracle and returns current data.

Do not confuse statement caching with:

- Oracle Database Result Cache.
- Application-level JDBC caches holding domain objects/results.
- Shared pool/library cache.
- Session cursor cache.
- Connection pool.

Each mechanism addresses a different category of cost.

### 3.3 Statement cache is tied to the physical connection

The statement cache belongs to the corresponding Oracle JDBC connection/session. With a connection pool, multiple logical Connections take turns using the same physical connection.

For example, if a pool has 40 physical connections and each connection caches 30 statements, each session can hold its own set of cached statements. There is no single cache shared across the entire pool.

This impacts sizing: cache size is a per-connection limit, so the total number of statements retained across the pool can approach pool size multiplied by cache size. Actual usage also depends on SQL workload and driver behavior.

## 4. Implicit statement caching

Implicit caching is the most common option. When enabled, the application does not manage cache keys manually. The driver uses SQL text and statement attributes to determine whether a statement can be reused.

Illustrative Oracle JDBC configuration:

~~~java
import java.sql.Connection;
import oracle.jdbc.OracleConnection;

void configureStatementCache(Connection connection)
        throws java.sql.SQLException {

    OracleConnection oracleConnection =
        connection.unwrap(OracleConnection.class);

    oracleConnection.setStatementCacheSize(32);
    oracleConnection.setImplicitCachingEnabled(true);
}
~~~

This example illustrates the Oracle JDBC API. In production, configure it when physical connections are created or via pool configuration per your connection pool's guidelines. Never resize the cache per request.

### 4.1 How statements return to the cache

Simplified flow:

~~~text
prepareStatement(SQL)
       |
       v
Driver searches cache entry
       |
       +---- Hit ----> Retrieve cached statement
       |
       +---- Miss ---> Create/prepare statement
       |
       v
executeQuery / executeUpdate
       |
       v
Read results
       |
       v
statement.close()
       |
       v
Driver places eligible statement into cache
~~~

The application must still call close. Without closing the statement, the driver lacks the normal signal to return the statement to the cache. Failing to close can also leave cursors held in an active state.

### 4.2 Conditions for reuse

Statement caches generally require matching SQL text and compatible statement types. Factors like PreparedStatement vs. CallableStatement, ResultSet type, and statement attributes can affect cache hits.

Two SQL texts differing in structure or literal values create separate cache entries:

~~~sql
SELECT * FROM orders WHERE order_id = 1001
SELECT * FROM orders WHERE order_id = 1002
~~~

Use bind variables:

~~~sql
SELECT * FROM orders WHERE order_id = ?
~~~

and pass different bind values on each execution. This both enables statement reuse and helps Oracle share cursors better when other conditions align.

### 4.3 SQL text must be stable

Differences in whitespace, comments, predicate order, or literal formatting make SQL texts differ and reduce cache hits. You do not need to force rigid formatting across all SQL, but avoid generating thousands of distinct SQL strings just by concatenating values.

Avoid:

~~~java
String sql =
    "SELECT order_id FROM orders WHERE customer_id = " + customerId;
Statement statement = connection.createStatement();
~~~

Prefer:

~~~java
String sql =
    "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    // Execute and process.
}
~~~

Bind variables do more than help caching. They also prevent SQL injection on data values and reduce hard parses caused by varying literals.

## 5. Explicit statement caching

Explicit caching lets applications assign keys to statements and retrieve statements by key via Oracle JDBC APIs. This can be useful when an application wants explicit control over statement identity or has a custom statement-management layer.

However, explicit caching increases management responsibility:

- Keys must be stable and unique within the connection's cache scope.
- SQL tied to a key must remain consistent.
- Retrieved statements must be closed/returned via explicit cache APIs.
- Multiple callers must never use the same cached statement concurrently.
- Bind parameter state, ResultSet, and transaction state must be managed carefully.

Do not build a custom explicit cache using a global Map holding PreparedStatements. Statements belong to a specific connection and are unsafe to share across threads or different connections.

### 5.1 When to use implicit vs. explicit?

| Criterion | Implicit cache | Explicit cache |
|---|---|---|
| Usage | Driver matches automatically by SQL/statement attributes | Application manages keys |
| Complexity | Lower | Higher |
| Best fit | Most standard JDBC workloads | Frameworks or workloads requiring explicit keys/ownership |
| Risks | Cache size and lifecycle still require management | Wrong keys or improper statement sharing can cause bugs |
| Recommendation | Start here | Use only when justified by measurable reasons |

Do not enable both mechanisms simply thinking more caching is better. Pick one clear strategy and read the Oracle JDBC documentation for your driver version.

## 6. Statement caching and ResultSet

Statement caching does not mean ResultSets are kept to return the same data on the next query. A ResultSet is the output of a single execution and must be closed after use.

Points to remember:

- Close ResultSet before closing PreparedStatement.
- Never store ResultSet in static fields or long-lived objects.
- Never return a ResultSet out of the DAO layer without clear ownership of Connection/Statement.
- Never return a Connection to the pool while a ResultSet is open.
- If passing data to upper layers, map to DTOs or a stream with clear lifecycle management.
- Never use a ResultSet after its Statement is closed or its connection has returned to the pool.

### 6.1 Anti-pattern: returning ResultSet from a DAO

Avoid:

~~~java
public ResultSet findOrders(Connection connection, long customerId)
        throws SQLException {
    PreparedStatement statement =
        connection.prepareStatement(
            "SELECT order_id FROM orders WHERE customer_id = ?"
        );
    statement.setLong(1, customerId);
    return statement.executeQuery();
}
~~~

This method does not clearly transfer statement ownership to the caller. The caller only receives the ResultSet without knowing which statement to close; the statement can easily be leaked.

Map data within the method scope instead:

~~~java
public List<Long> findOrderIds(
        DataSource dataSource,
        long customerId) throws SQLException {

    String sql =
        "SELECT order_id FROM orders WHERE customer_id = ?";
    List<Long> ids = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                ids.add(resultSet.getLong(1));
            }
        }
    }

    return ids;
}
~~~

If streaming large datasets is needed, design a streaming API with clear ownership and ensure the caller can close the stream to release ResultSet, Statement, and Connection.

## 7. What is OPEN_CURSORS?

OPEN_CURSORS is an Oracle initialization parameter specifying the maximum number of cursor handles a single session can have open simultaneously. It is a per-session limit, not a single global limit across the entire database.

When a session exceeds this limit, Oracle may raise:

~~~text
ORA-01000: maximum open cursors exceeded
~~~

The error can appear during execute, parse, or another JDBC operation when the database needs to open another cursor and the session has hit its cap.

### 7.1 OPEN_CURSORS is not the count of distinct SQL statements

An application can run a single SQL text repeatedly across multiple PreparedStatements and still consume many cursor handles in a session. Conversely, one SQL text can be executed by many sessions with separate cursor handles.

Do not merely count SQL texts in source code. Measure per-session cursor counts at peak workload.

### 7.2 Open cursors vs. cached cursors

Cursors can exist in different states:

- Actively used by an executing statement.
- Open ResultSet currently fetching rows.
- Closed statement whose cursor is retained in the session cursor cache.
- Statement retained in the JDBC statement cache.
- Internal cursors opened by PL/SQL, recursive SQL, or metadata operations.

Different cache types and cursor states have distinct accounting in Oracle. When investigating, read V$OPEN_CURSOR alongside session statistics and remember the list can include cached cursors, not just ResultSets currently being read by the application.

### 7.3 Each session has its own limit

If a connection pool has 100 physical connections and OPEN_CURSORS is 500, each session has a limit of 500 cursor handles. It does not mean the entire pool can only open 500 cursors total.

However, total resource consumption on the database still grows with session count. An oversized pool paired with a large statement cache can drive total cursors/cache entries across the instance high, even before individual sessions hit OPEN_CURSORS.

## 8. ORA-01000: common causes

ORA-01000 signals that a session needs to open another cursor while no slots remain under OPEN_CURSORS. Common causes:

1. Failing to close PreparedStatement/Statement.
2. Failing to close ResultSet.
3. Failing to close CallableStatement or REF CURSOR.
4. Exceptions occurring before close runs.
5. DAOs returning ResultSet/Statement without managing ownership.
6. Connections returned to the pool while statements remain open.
7. Statement cache size too large relative to OPEN_CURSORS and workload.
8. SESSION_CACHED_CURSORS and statement cache configured without measuring total cursors.
9. Code generating too many distinct SQL texts.
10. Stored procedures or triggers opening cursors without closing them.
11. Batches/loops creating a new statement on every iteration.
12. Connection pools creating many sessions with poorly sized cache settings.

### 8.1 Leaks inside loops

Anti-pattern:

~~~java
for (Order order : orders) {
    PreparedStatement statement =
        connection.prepareStatement(
            "UPDATE orders SET status = ? WHERE order_id = ?"
        );

    statement.setString(1, order.status());
    statement.setLong(2, order.id());
    statement.executeUpdate();
}
~~~

Each iteration creates a new PreparedStatement without closing it. Over many iterations, the session accumulates cursors.

Create the statement once and reuse it:

~~~java
String sql =
    "UPDATE orders SET status = ? WHERE order_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {

    for (Order order : orders) {
        statement.setString(1, order.status());
        statement.setLong(2, order.id());
        statement.addBatch();
    }

    statement.executeBatch();
}
~~~

If the batch is too large, split it into smaller batches to control memory, transaction duration, and redo. Call executeBatch and clearBatch after each chunk per design.

### 8.2 Leaks when exceptions occur

Anti-pattern:

~~~java
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();

// If row processing throws an exception, close may never be called.
process(resultSet);

resultSet.close();
statement.close();
~~~

If process() throws an exception, the final two close calls are skipped.

Try-with-resources guarantees closing:

~~~java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    try (ResultSet resultSet = statement.executeQuery()) {
        process(resultSet);
    }
}
~~~

### 8.3 Leaks in stored procedures

PL/SQL can also open cursors. Example explicit cursor that must be closed:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id FROM orders WHERE status = 'PENDING';
    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;
        -- Process current row.
    END LOOP;

    CLOSE c_orders;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
~~~

A cursor FOR loop automatically manages OPEN/FETCH/CLOSE:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'PENDING'
    ) LOOP
        -- Process current row.
        NULL;
    END LOOP;
END;
/
~~~

If a procedure opens a SYS_REFCURSOR to return to a client, ownership transfers to the caller; the caller must close the ResultSet/REF CURSOR after reading.

## 9. Distinguishing OPEN_CURSORS, SESSION_CACHED_CURSORS, and statement cache

This is the most frequently confused area when troubleshooting ORA-01000.

| Mechanism | Where it operates | Purpose | Replaces close? |
|---|---|---|---|
| OPEN_CURSORS | Oracle session | Limits open cursor handles | No |
| SESSION_CACHED_CURSORS | Oracle session | Caches closed cursors to reduce soft parses | No |
| JDBC implicit statement cache | Oracle JDBC connection/driver | Reuses PreparedStatement/CallableStatement | No |
| JDBC explicit statement cache | Oracle JDBC connection/driver | Reuses statements by app-managed key | No |
| Shared pool/library cache | Oracle instance | Shares SQL areas, execution plans, and metadata | No |

### 9.1 SESSION_CACHED_CURSORS

SESSION_CACHED_CURSORS lets an Oracle session cache closed cursors to reduce soft-parse cost when the same SQL is parsed again.

It differs from the JDBC statement cache:

- Session cursor cache is managed by Oracle Database.
- JDBC statement cache is managed by the Oracle JDBC driver.
- Both mechanisms can operate simultaneously.
- Neither exempts code from closing ResultSet/Statement.
- Increasing SESSION_CACHED_CURSORS does not cure cursor leaks.

### 9.2 Statement cache and cursor count

The JDBC statement cache can keep statements/cursors that are closed at the API level yet retained in the cache for reuse. Therefore, increasing cache size can increase the number of cursors held inside a session.

When sizing, consider cache size alongside OPEN_CURSORS and cursors opened by the workload. Do not set cache size to 200 just because database OPEN_CURSORS is 300; a single request may open additional cursors from ResultSets, callable statements, metadata, and PL/SQL.

### 9.3 Shared pool is not the fix for ORA-01000

Flushing or enlarging the shared pool is not a standard cure for ORA-01000. The shared pool manages shared SQL areas; OPEN_CURSORS is a per-session cursor handle limit.

Never flush the shared pool in production just to experiment. Doing so can cause a spike in hard parses across the entire instance without fixing the session leak.

## 10. Configuring statement caching in Java applications

Configure caching once per physical connection or in the connection pool configuration. Never toggle caching repeatedly inside requests.

Direct configuration example on an Oracle JDBC connection:

~~~java
import oracle.jdbc.OracleConnection;
import java.sql.Connection;
import java.sql.SQLException;

public final class OracleJdbcSettings {
    private OracleJdbcSettings() {}

    public static void configure(Connection connection)
            throws SQLException {

        OracleConnection oracle =
            connection.unwrap(OracleConnection.class);

        oracle.setStatementCacheSize(32);
        oracle.setImplicitCachingEnabled(true);
    }
}
~~~

The number 32 is only an example. Actual sizing should be measured based on repeating SQL statements, other cursors in the session, and the OPEN_CURSORS limit.

### 10.1 Configuring in the connection pool

With a pool, physical connections are created and reused. Configure statement caching in the physical-connection creation hook or via Oracle JDBC properties per your pool's documentation.

Avoid configuring caching on every logical connection checkout if doing so mutates state repeatedly or adds overhead.

Some pools have their own statement cache or wrapper cache. Avoid enabling multiple cache layers simultaneously without understanding ownership and close semantics. Check your pool's documentation to see whether it caches statements itself or delegates to Oracle JDBC's cache.

### 10.2 Never share PreparedStatements across threads

PreparedStatement holds mutable bind values, ResultSet state, and is tied to a specific connection. Never store a PreparedStatement in a static field shared across threads.

Each operation should borrow a connection from the pool, obtain/create a statement on that connection, bind values, execute, and close. The driver cache handles safe reuse within that connection's scope per its API contract.

### 10.3 Start with a small cache size

A safe rollout approach:

1. Measure the most frequently repeated SQL texts on a physical connection.
2. Enable implicit caching with a small size.
3. Measure cache hits/misses if the driver/pool exposes metrics.
4. Measure cursor counts and parse rates.
5. Increase cache size gradually if throughput improves and cursor headroom remains sufficient.
6. Test with pool max size and peak workload.

Not every SQL statement needs caching. One-off statements, highly varied dynamic SQL, or statements with unusual lifecycles may yield no benefit.

## 11. Sizing OPEN_CURSORS and statement cache

There is no single right value for every application. Estimate concurrent cursors per session at peak load.

Components to account for:

- Currently executing Statements/PreparedStatements.
- Currently open ResultSets.
- CallableStatements and REF CURSORs.
- Retained JDBC statement cache entries.
- Session cursor cache.
- Cursors from PL/SQL, triggers, recursive SQL, and metadata operations.
- Internal cursors opened by frameworks or drivers.

Do not sum metrics mechanically, as Oracle accounting and cache views differ. Measure current cursor count and peak cursor count on representative sessions under realistic load.

### 11.1 Headroom

Maintain headroom for infrequent paths such as reports, batches, metadata queries, migrations, and admin tasks. If peak usage sits right against OPEN_CURSORS, a minor code change can trigger errors.

An initial estimation model:

~~~text
OPEN_CURSORS target
  >= peak active cursor demand
   + retained statement cache demand
   + operational headroom
~~~

This is a sizing model, not an exact accounting formula. Validate using session statistics and V$OPEN_CURSOR under load.

### 11.2 Impact of connection pools

Suppose:

- Pool max is 60 physical connections.
- Statement cache size is 40 per connection.
- Some requests open 20 extra uncached cursors.

A session can hold more cursors than expected when cache entries and active cursors coexist. OPEN_CURSORS applies per session; pool size does not directly multiply a single session's OPEN_CURSORS, yet total cursors across the database scale with session count.

An oversized pool also raises session count, PGA/session state, network connections, and aggregate cursor cache footprint. Size the pool and statement cache together.

### 11.3 When to increase OPEN_CURSORS?

Only increase when:

- Code already closes resources properly.
- There is no upward leak trend over time.
- Peak legitimate workload genuinely requires more concurrent cursors.
- Statement cache size is deliberately configured.
- Session cursor cache and PL/SQL workloads have been accounted for.
- Database memory and resources have sufficient headroom.
- The change has been tested in an equivalent environment.

Raising OPEN_CURSORS does not pre-allocate the entire limit as fixed memory, though sessions can consume more resources as more cursors open. Do not raise it without bound, and never use parameter changes to mask a leak.

## 12. Diagnosing ORA-01000 in Oracle

Start by identifying the offending session, timestamp, and workload. Determine whether the error comes from an application service, batch job, scheduler job, or stored procedure.

### 12.1 Checking configuration

~~~sql
SHOW PARAMETER open_cursors;
SHOW PARAMETER session_cached_cursors;
~~~

These values show the current limit and session cursor cache setting. Compare against pool configuration, statement cache, and observed cursor counts.

### 12.2 Getting the current session's SID

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

When investigating from a separate DBA session, locate application sessions in V$SESSION by username, machine, program, module, service_name, or client_identifier.

~~~sql
SELECT sid,
       serial#,
       username,
       machine,
       program,
       module,
       action,
       status,
       sql_id,
       logon_time
FROM v$session
WHERE username = 'APP_USER'
ORDER BY logon_time;
~~~

Replace APP_USER with the application schema. In RAC, use GV$SESSION and pay attention to INST_ID.

### 12.3 Checking a session's current cursor count

~~~sql
SELECT s.sid,
       s.value AS opened_cursors_current
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name = 'opened cursors current'
  AND s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

You can also view cumulative counts:

~~~sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE n.name IN (
    'opened cursors current',
    'opened cursors cumulative'
)
AND s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'));
~~~

opened cursors current shows how many cursors are currently held by the session per Oracle accounting. opened cursors cumulative is the lifetime total of cursors opened by the session, not the count open at query time.

### 12.4 Listing a session's cursors

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       COUNT(*) AS cursor_count
FROM v$open_cursor
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
GROUP BY sid, cursor_type, sql_id
ORDER BY cursor_count DESC, sql_id;
~~~

View details:

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       last_sql_active_time,
       sql_text
FROM v$open_cursor
WHERE sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
ORDER BY last_sql_active_time DESC;
~~~

V$OPEN_CURSOR can list open cursors, parsed cursors, or cached cursors depending on type. Therefore, do not treat every row as a ResultSet actively being read by the application. Combine cursor_type, current statistics, SQL_ID, and application behavior to draw conclusions.

### 12.5 Finding sessions with high cursor counts

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.machine,
       s.program,
       st.value AS opened_cursors_current
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
WHERE sn.name = 'opened cursors current'
  AND s.username IS NOT NULL
ORDER BY st.value DESC
FETCH FIRST 20 ROWS ONLY;
~~~

FETCH FIRST requires an Oracle version supporting the row limiting clause. On older releases, use an inline view with ROWNUM.

In RAC, replace V$ with GV$ and join on both INST_ID and SID.

### 12.6 Inspecting SQL and module

If a session has a SQL_ID:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       parse_calls,
       loads,
       invalidations,
       sql_text
FROM v$sql
WHERE sql_id = :sql_id;
~~~

SQL in V$SQL helps reveal the statement, parses, and executions. It does not prove a single SQL_ID caused the leak. A session may hold open cursors across many different SQL statements; correlate with module/action and application call stacks.

## 13. Tracking leaks over time

A single snapshot may not suffice. Leaks typically appear as cursor counts climbing steadily across requests or over time without dropping back after requests finish.

Sample periodically:

- SID and SERIAL#.
- MODULE/ACTION.
- OPENED_CURSORS_CURRENT.
- SQL_ID.
- Cursor type and count.
- Pool connection identity if logged by the application.
- Active request count and thread name.

Example querying current cursors per session:

~~~sql
SELECT s.sid,
       s.serial#,
       s.module,
       s.action,
       s.machine,
       st.value AS current_cursors
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
WHERE sn.name = 'opened cursors current'
  AND s.username = 'APP_USER'
ORDER BY st.value DESC;
~~~

Sample after the pool stabilizes, after normal load, and after high load. If cursor counts grow with request count without returning to baseline once requests finish, audit resource lifecycles.

### 13.1 Using MODULE and ACTION

Applications can tag module/action so DBAs can distinguish workloads:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try (var call = connection.prepareCall(
            "BEGIN DBMS_APPLICATION_INFO.SET_MODULE(?, ?); END;")) {
        call.setString(1, "order-service");
        call.setString(2, "find-orders");
        call.execute();
    }

    // Execute application SQL on this connection.
}
~~~

This example is illustrative only. Reset module/action or set appropriate values when returning connections to the pool so subsequent requests are not mislabeled. Application wrappers/interceptors can manage this cleanly.

### 13.2 Distinguishing leaks from workload peaks

A high cursor count is not always a leak. A report may intentionally hold multiple cursors open; a procedure may open multiple REF CURSORs; a single transaction may use many PreparedStatements.

Signs of a leak:

- Cursor count climbs over time without dropping.
- The same SQL text appears repeatedly in the cursor list.
- Errors occur after a fairly consistent number of requests.
- Restarting the connection pool drops cursor counts sharply, only for them to climb again.
- Heap/thread dumps reveal retained Statement/ResultSet objects.

Signs of a workload peak:

- Cursor count rises during a batch/report run and drops back after completion.
- Cursor counts correspond to intentionally opened queries/REF CURSORs.
- Errors occur only under high concurrency and do not drift upward over time.
- Resource cleanup works properly, but concurrency exceeds capacity.

## 14. Investigating from the Java side

Database views expose sessions and cursors; Java heap/thread diagnostics help locate unclosed objects.

Investigation angles:

- Enable connection pool logging or leak detection.
- Audit code paths calling prepareStatement/createStatement/prepareCall.
- Locate every opened ResultSet and its corresponding close.
- Check exception paths and early returns.
- Check methods returning Statements/ResultSets to callers.
- Check static fields, application caches, or collections holding JDBC objects.
- Check threads blocked while holding open ResultSets.
- Check unclosed streaming responses.
- Check ORM/native queries and cursor-based pagination.

### 14.1 Pool leak detection

Some connection pools provide a leak detection threshold to log when a Connection is held too long. This primarily catches checked-out connections that are never returned; it does not always catch Statement leaks if the logical connection still gets returned.

Some pools offer statement tracking or cleanup wrappers. Read your pool's documentation and test diagnostics in staging before enabling in production, as instrumentation adds overhead.

### 14.2 Java Flight Recorder and heap dumps

If you suspect Java is retaining JDBC objects:

- Use Java Flight Recorder to inspect allocations, threads, and resource hold times.
- Capture a heap dump in a controlled environment.
- Search for PreparedStatement, OraclePreparedStatement, ResultSet, and wrapper references.
- Trace GC roots to locate collections, singletons, or threads retaining those objects.
- Use thread dumps to identify code actively fetching or blocked on I/O.

Do not conclude a leak solely from high heap object counts; caches intentionally retain objects. Compare object counts over time against connection state.

### 14.3 Close instrumentation

In tests, you can wrap DataSource/Connection/Statement to record creation and close timestamps, SQL fingerprints, and request IDs. Never log sensitive bind values.

Instrumentation helps identify unclosed statements by call path. Disable or dial down logging once the root cause is found to avoid overhead and log volume.

## 15. Using statement caching properly

A solid usage workflow:

1. Create the statement within the connection scope.
2. Bind parameters.
3. Execute.
4. Read all needed results.
5. Close ResultSet.
6. Close Statement.
7. Return Connection to the pool.

With implicit caching, closing is the signal for the driver to place eligible statements into the cache.

### 15.1 Reusing within a single method

~~~java
String sql =
    "SELECT order_id, total_amount " +
    "FROM orders WHERE customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    for (long customerId : customerIds) {
        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long id = resultSet.getLong("order_id");
                BigDecimal amount =
                    resultSet.getBigDecimal("total_amount");
                // Map or process.
            }
        }
    }
}
~~~

The statement is reused on the same connection while the ResultSet closes after each execution. Closing PreparedStatement at the end lets the driver cache it.

### 15.2 Clearing parameters and batch state

When reusing a PreparedStatement, re-bind every required parameter on each execution. JDBC may retain previous bind values if code fails to overwrite all positions.

For batches, manage addBatch/executeBatch/clearBatch properly. Never let old batch commands get submitted accidentally. With statement caching, the driver resets state per the API contract, yet applications must still use statements properly.

### 15.3 ResultSet concurrency and holdability

ResultSet type, concurrency, and holdability affect statement behavior and cacheability. If an application requires scrollable/updatable ResultSets or cursors held across commits, verify whether the driver supports caching for that statement type and understand the cursor lifecycle impact.

Default FORWARD_ONLY and READ_ONLY suffice for most application queries. Only choose scrollable/updatable when business logic genuinely requires it.

## 16. Optimizing SQL to reduce statement/cursor churn

Statement caches work best when workloads have stable SQL text.

Practices:

- Use bind variables for data values.
- Avoid concatenating literals into SQL strings.
- Avoid generating distinct SQL solely because condition ordering changes.
- Generate dynamic SQL only when query structure genuinely changes.
- Bound the number of dynamic SQL shapes.
- Use PreparedStatement for repeated statements.
- Never allocate new statements inside loops when reuse is possible.
- Avoid caching one-off statements when there is no benefit.

### 16.1 Bind variables and cursor sharing

Example:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
~~~

SQL using bind variables can be reused across many values. Oracle can share cursors when SQL text, bind metadata, optimizer environment, and object metadata align.

Bind variables do not guarantee every execution uses a single child cursor. Bind peeking, adaptive cursor sharing, data type mismatches, and optimizer environments can spawn multiple child cursors. Even so, binding remains best practice to avoid literal SQL proliferation.

### 16.2 Data type consistency

Bind parameters should use data types compatible with columns. For example, NUMBER columns should bind with appropriate setLong/setBigDecimal rather than setString when conversion is unnecessary.

Data type mismatches can trigger implicit conversion, affecting index access and cursor sharing. Match JDBC setters to Oracle column types.

## 17. ResultSet fetching and cursor lifetime

A large query can hold a server cursor open for the entire time the application fetches results. This is not necessarily a leak if the application is actively reading data, though it occupies a cursor for a long time and keeps the connection checked out of the pool.

### 17.1 Fetch size

JDBC fetch size hints how many rows the driver fetches per round trip:

~~~java
statement.setFetchSize(200);
~~~

Fetch size reduces network round trips and affects client memory. It does not directly reduce open cursor count: the ResultSet remains tied to its cursor until closed.

Choose fetch size based on row width, network latency, memory, and workload. Too large increases memory; too small increases round trips.

### 17.2 Streaming and connection pools

If an API returns a stream to a caller, the connection may stay held until the caller finishes reading or closes the stream. A slow client can hold cursors and connections long enough to exhaust the pool.

Consider:

- Reading and mapping into small pages, then closing the connection.
- Using keyset pagination.
- Enforcing read timeouts.
- Ensuring streams implement AutoCloseable and are closed by callers.
- Avoiding keeping ResultSets open across multiple uncontrolled application layers.

### 17.3 Pagination

Offset pagination can force the database to read/skip many rows at deep pages. Keyset pagination is generally more efficient with a stable sort order:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE order_date < :last_order_date
   OR (order_date = :last_order_date
       AND order_id < :last_order_id)
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Pagination does not fix cursor leaks on its own, yet it shortens how long ResultSets and Connections stay held per request.

## 18. Views and metrics to know

| View/parameter | What it is used for |
|---|---|
| V$SESSION | Locate sessions, users, modules, SQL_IDs, and status |
| V$SESSTAT | View per-session statistics |
| V$STATNAME | Look up statistic names |
| V$OPEN_CURSOR | Inspect cursors recorded in a session |
| V$SQL | Inspect SQL text, executions, parse calls, and child cursors |
| V$PARAMETER | View parameter values in instance/session context |
| GV$SESSION / GV$OPEN_CURSOR | Investigate across instances in RAC |
| OPEN_CURSORS | Per-session open cursor handle limit |
| SESSION_CACHED_CURSORS | Session cursor cache size |

V$ views generally require catalog roles or specific SELECT privileges. Application accounts should not be granted broad privileges just to self-diagnose production. DBAs can expose restricted per-session views/reports.

### 18.1 Cursor types in V$OPEN_CURSOR

V$OPEN_CURSOR includes a CURSOR_TYPE column distinguishing tracked cursor kinds, such as open cursors, session-cached cursors, or PL/SQL-related cursors depending on release. Exact values and interpretation vary by Oracle version.

Do not rely on a single cursor type alone to draw conclusions. Compare against opened cursors current and test closing resources in a test session to understand driver behavior.

### 18.2 RAC

In RAC, sessions reside on specific instances. Use GV$ views and join on INST_ID, SID, and SERIAL# to avoid confusing sessions with matching SIDs on different instances.

When a connection pool connects through a RAC service, requests can distribute across multiple instances. Check both which instance hosts the failing session and its module/action.

## 19. Step-by-step workflow for resolving ORA-01000

When encountering ORA-01000:

### Step 1: Scope the issue

- Does the error occur in one service or multiple services?
- Only one endpoint/batch or system-wide?
- Does it happen after how many requests or how long?
- Did it coincide with a deployment or pool/cache change?
- Only one RAC instance or all instances?

### Step 2: Identify the session

Use V$SESSION/GV$SESSION to obtain SID, SERIAL#, USERNAME, MACHINE, PROGRAM, MODULE, ACTION, and SQL_ID.

### Step 3: Measure cursor counts

Fetch opened cursors current and the V$OPEN_CURSOR list for the session. Compare against OPEN_CURSORS.

### Step 4: Find repeating SQL and cursor types

Group by SQL_ID/CURSOR_TYPE. Check whether many duplicate cursors originate from the same code path or procedure.

### Step 5: Inspect Java resource lifecycle

Search for unclosed statements/result sets, especially in exception paths, loops, async callbacks, streaming, and REF CURSORs.

### Step 6: Check statement cache and pool settings

Record:

- Pool max/min size.
- Number of physical connections.
- Oracle JDBC driver version.
- Whether implicit/explicit caching is enabled.
- Statement cache size per physical connection.
- Whether the pool has its own statement cache.
- Session cursor cache size.

### Step 7: Fix code and test

Add try-with-resources, close REF CURSORs, fix ownership, and bound concurrency. Run sustained load tests long enough to verify cursor counts remain stable.

### Step 8: Tune parameters if needed

Once you confirm legitimate peak workloads require more concurrent cursors, the DBA can adjust OPEN_CURSORS and cache sizes per capacity plan. Record before/after values and monitor resources.

## 20. Investigation and resolution example

Suppose a Java application handles many order-lookup requests. After a few minutes, logs show:

~~~text
java.sql.SQLException: ORA-01000: maximum open cursors exceeded
~~~

The DBA sees APP_USER sessions have OPEN_CURSORS set to 300 while opened cursors current climbs steadily from 80 to 280.

V$OPEN_CURSOR shows many repeated SQL_IDs with statement/PLSQL-related cursor types. Java code inspection finds the following method:

~~~java
public Order findOrder(Connection connection, long orderId)
        throws SQLException {

    PreparedStatement statement =
        connection.prepareStatement(
            "SELECT order_id, status FROM orders WHERE order_id = ?"
        );

    statement.setLong(1, orderId);
    ResultSet resultSet = statement.executeQuery();

    if (resultSet.next()) {
        return new Order(
            resultSet.getLong("order_id"),
            resultSet.getString("status")
        );
    }

    return null;
}
~~~

The method never closes ResultSet or PreparedStatement. Fix:

~~~java
public Order findOrder(Connection connection, long orderId)
        throws SQLException {

    String sql =
        "SELECT order_id, status FROM orders WHERE order_id = ?";

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, orderId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (resultSet.next()) {
                return new Order(
                    resultSet.getLong("order_id"),
                    resultSet.getString("status")
                );
            }
        }
    }

    return null;
}
~~~

After deploying, re-measure opened cursors current per session. If cursor counts return to baseline after each request and stop climbing continuously, the leak is resolved. If counts remain high yet flat, check cache size and peak concurrency.

Never simply bump OPEN_CURSORS from 300 to 1000 and declare the bug fixed. If a leak remains, sessions will keep accumulating cursors and the error will simply appear later.

## 21. Testing statement cache and cursor lifecycle

Testing should measure both performance and resource consumption.

A test plan:

1. Run a baseline workload with statement caching disabled.
2. Record throughput, latency, parse calls, and opened cursors current.
3. Enable implicit caching with a small size.
4. Run the identical workload with the identical physical connection count.
5. Compare cache hits/parse reduction if metrics are available.
6. Measure peak and steady-state cursor counts.
7. Increase concurrency and run duration.
8. Test exceptions, timeouts, cancellations, and connection returns.
9. Test REF CURSORs, batches, and streaming queries.
10. Check cursor counts after the workload finishes.

### 21.1 Success criteria

- Zero ORA-01000 errors.
- Cursor count does not grow unboundedly with request count.
- After requests finish, active cursors drop back to an appropriate baseline.
- Caching does not consume most of OPEN_CURSORS headroom.
- Throughput/latency improves or at least does not degrade noticeably.
- Pool does not exhaust connections due to long-held queries/streams.
- No statement/result set is accessed after close.

### 21.2 Testing pool recycling

Test closing logical connections and re-borrowing connections from the pool. Confirm:

- Physical sessions are reused properly.
- Statement caching operates per configuration.
- Module/action is reset or re-tagged accurately.
- No ResultSet/Statement from an old request remains referenced by callers.
- Cursor counts stay stable across many checkout/return cycles.

## 22. Checklist for preventing ORA-01000

### In Java code

- [ ] Use try-with-resources for Connection, Statement, and ResultSet.
- [ ] Close CallableStatements and REF CURSORs.
- [ ] Never return ResultSets externally without clear ownership.
- [ ] Never store PreparedStatements in static fields.
- [ ] Never share Statements across threads.
- [ ] Reuse statements inside loops where appropriate.
- [ ] Use bind variables and stable SQL text.
- [ ] Close ResultSets before returning connections to the pool.
- [ ] Audit exception paths, cancellations, and early returns.
- [ ] Audit streaming APIs and ORM/native queries.

### Statement cache and pool

- [ ] Enable caching intentionally, starting with a small size.
- [ ] Configure on physical connections per pool guidance.
- [ ] Remember cache size applies per connection.
- [ ] Avoid enabling unnecessary multiple statement cache layers.
- [ ] Measure cache hits/misses if metrics exist.
- [ ] Size the pool together with statement cache and OPEN_CURSORS.
- [ ] Never change cache size per request.

### Oracle database

- [ ] Monitor OPEN_CURSORS and SESSION_CACHED_CURSORS.
- [ ] Measure opened cursors current per session.
- [ ] Use V$OPEN_CURSOR to inspect cursor types and SQL_IDs.
- [ ] Use GV$ views in RAC.
- [ ] Audit PL/SQL explicit cursors and REF CURSORs.
- [ ] Maintain headroom for peak workloads.
- [ ] Only raise OPEN_CURSORS after measuring and ruling out leaks.

### Operations

- [ ] Alert when cursor counts approach limits.
- [ ] Tag module/action to identify code paths.
- [ ] Enable appropriate pool leak detection logging.
- [ ] Run sustained load tests, not just short smoke tests.
- [ ] Have a procedure to capture session, SQL_ID, and cursor details during incidents.
- [ ] Document changes to drivers, pools, caches, and database parameters.

## 23. Conclusion

Oracle JDBC statement caching enables reuse of PreparedStatements/CallableStatements and lowers prepare/parse overhead for repeated SQL. Implicit caching is usually the simplest option: applications close statements normally, and the driver returns eligible statements to the cache. Caching is tied to physical connections, so cache size must be planned per session alongside overall connection pool scale.

Server-side cursors are per-session resources used to execute SQL and fetch results. OPEN_CURSORS bounds open cursor handles per session; SESSION_CACHED_CURSORS is Oracle's own session cursor cache. Neither replaces JDBC resource cleanup.

ORA-01000 usually stems from unclosed Statements/ResultSets/REF CURSORs, concurrent cursor demand exceeding capacity, or an oversized cache. Identify the session, measure opened cursors current, inspect V$OPEN_CURSOR, trace SQL/module back to Java code, fix lifecycles with try-with-resources, and run sustained load tests. Adjust OPEN_CURSORS only after understanding peak cursor demand and ruling out leaks.
