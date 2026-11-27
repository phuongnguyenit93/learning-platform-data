# ORA-01000, ORA-04030, ORA-04031, and Cursor/Memory Resources

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Troubleshooting  
> **Objective:** Distinguish three common Oracle resource errors; diagnose per-session open cursor limits, private process memory, and SGA memory pools; locate cursor leaks in PL/SQL, JDBC, connection pools, and ORMs; analyze PGA/SGA pressure; tune parameters and workloads based on evidence; and build an incident handling and recurrence-prevention runbook.

## 1. Distinguishing the Three Errors Before Taking Action

ORA-01000, ORA-04030, and ORA-04031 can all surface under rising load, yet they report three distinct resource limits:

| Error | Exhausted/Limited Resource | Typical Scope | Primary Investigation Focus |
|---|---|---|---|
| ORA-01000: maximum open cursors exceeded | Open cursors exceed `OPEN_CURSORS` | Single database session | Cursor leaks, unclosed statements/result sets, concurrent cursor count |
| ORA-04030: out of process memory | Process cannot allocate private memory | Single Oracle process | PGA/process memory, workareas, PL/SQL collections, OS memory |
| ORA-04031: unable to allocate bytes of shared memory | Cannot allocate memory in an SGA pool | SGA pool/instance | Shared pool/large pool, fragmentation, hard parses, pool sizing |

The three errors can interact. For example, an application opening excessive cursors increases private session/process memory as well as shared SQL cursor usage. However, raising `OPEN_CURSORS` will not fix ORA-04030 caused by runaway PGA, and raising `PGA_AGGREGATE_TARGET` will not fix ORA-04031 caused by shared pool allocation failures.

**Always identify the exact resource and process/session before changing parameters.**

## 2. What Is a Cursor in Oracle?

A cursor is the handle and execution state a session uses to work with a SQL or PL/SQL statement. A SQL statement is parsed and executed through cursor structures; JDBC applications typically create corresponding cursors when opening `Statement`, `PreparedStatement`, or `CallableStatement` objects.

Distinguish:

- **SQL cursor / shared cursor:** parsed SQL representation shareable in the SGA library cache.
- **Session cursor:** cursor state used by a specific session, including its handle and private execution state.
- **Open cursor:** a cursor currently kept open by a session.
- **Cached cursor:** a cursor closed on the application side yet retained in the session cursor cache for reuse as configured.
- **REF CURSOR:** a cursor variable returned by PL/SQL to a client or caller; the caller must consume and close the result set within the proper lifecycle.

Identical SQL statements can share a shared SQL area, yet each session maintains its own cursor state. Multiple sessions executing the same SQL do not share a single open cursor handle.

### 2.1. SQL/JDBC Cursor Lifecycle

A simplified flow:

~~~text
Connection / Session
       |
       v
Prepare SQL
       |
       v
Parse / cursor handle
       |
       v
Execute
       |
       v
Fetch rows
       |
       v
Close ResultSet
       |
       v
Close Statement
       |
       v
Cursor resources released or cached
~~~

When an application fails to close `ResultSet`/`Statement` objects, the session retains cursors longer than intended. Across thousands of requests or loop iterations, it gradually hits `OPEN_CURSORS`.

## 3. ORA-01000: maximum open cursors exceeded

ORA-01000 occurs when a single session opens more cursors than the `OPEN_CURSORS` limit configured for the instance/database. The limit is enforced per session, not database-wide.

### 3.1. OPEN_CURSORS

Check the current setting:

~~~sql
SHOW PARAMETER open_cursors;
~~~

Or:

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
~~~

`OPEN_CURSORS` defines how many cursors one session can keep open simultaneously. The setting must cover real workload needs, including application statements, PL/SQL, framework queries, and concurrently active cursors.

There is no single optimal number for every system. Setting it too low causes ORA-01000; setting it arbitrarily high without fixing leaks masks resource management bugs and inflates memory footprint.

### 3.2. SESSION_CACHED_CURSORS vs. OPEN_CURSORS

Check:

~~~sql
SHOW PARAMETER session_cached_cursors;
~~~

`SESSION_CACHED_CURSORS` controls how many closed cursors a session may keep in its session cursor cache for reuse to reduce parse overhead. It is not an open cursor limit and does not replace `OPEN_CURSORS`.

A cursor cached after closing may still appear in certain cursor views. Therefore, never simply count rows in `V$OPEN_CURSOR` and conclude they are all genuinely open cursors.

### 3.3. Measuring Current Open Cursors per Session

`V$SESSTAT` exposes the `opened cursors current` statistic:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       st.value AS opened_cursors_current
FROM v$sesstat st
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE sn.name = 'opened cursors current'
ORDER BY st.value DESC;
~~~

This metric is helpful for spotting which session currently holds the most open cursors.

To view cumulative cursors opened during the session:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       st.value AS opened_cursors_cumulative
FROM v$sesstat st
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE sn.name = 'opened cursors cumulative'
ORDER BY st.value DESC;
~~~

The cumulative metric grows across the session's lifetime; it is not the count of currently open cursors.

### 3.4. Viewing Cursors by Session

~~~sql
SELECT sid,
       user_name,
       cursor_type,
       COUNT(*) AS cursor_count
FROM v$open_cursor
GROUP BY sid, user_name, cursor_type
ORDER BY cursor_count DESC;
~~~

Inspect specific SQL statements for a session:

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       sql_text
FROM v$open_cursor
WHERE sid = :sid
ORDER BY cursor_type, sql_id;
~~~

`V$OPEN_CURSOR` can show both open cursors and certain cached cursors. Read `CURSOR_TYPE` alongside `opened cursors current`; do not assume every row in the view represents a resource leak.

### 3.5. Finding Repeated SQL in the Cursor List

~~~sql
SELECT sid,
       sql_id,
       cursor_type,
       COUNT(*) AS copies
FROM v$open_cursor
WHERE sid = :sid
GROUP BY sid, sql_id, cursor_type
ORDER BY copies DESC;
~~~

A SQL statement appearing multiple times can result from child cursors, cursor caching, or how the application allocates statements. Inspect `SQL_ID`, child cursors, and session statistics before drawing conclusions.

## 4. Causes of ORA-01000

Common causes:

1. Failing to close `PreparedStatement` or `Statement` after use.
2. Failing to close `ResultSet`.
3. Creating new statements inside loops instead of reusing appropriately.
4. Opening multiple `REF CURSOR`s without closing client-side result sets.
5. PL/SQL opening explicit cursors without closing them on exception paths.
6. `DBMS_SQL` cursors missing `DBMS_SQL.CLOSE_CURSOR`.
7. ORMs or frameworks holding result streams/scrollable results open too long.
8. Connection pools keeping sessions alive long-term, letting leaks accumulate across requests.
9. Application legitimately holding many concurrent statements while `OPEN_CURSORS` is too low.
10. Dynamic SQL creating unnecessary cursors or literal SQL increasing parse pressure.

### 4.1. JDBC Failing to Close Statements

Unsafe example:

~~~java
for (Order order : orders) {
    PreparedStatement ps = connection.prepareStatement(
        "update orders set status = ? where order_id = ?"
    );

    ps.setString(1, "DONE");
    ps.setLong(2, order.getId());
    ps.executeUpdate();

    // Statement is never closed.
}
~~~

Each iteration allocates a new statement/cursor. Without closing, the session accumulates cursors until hitting the limit.

Proper management:

~~~java
String sql =
    "update orders set status = ? where order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Order order : orders) {
        ps.setString(1, "DONE");
        ps.setLong(2, order.getId());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

Depending on workload, batching reduces round trips. Even if executing statements individually, always close statements via try-with-resources.

### 4.2. Failing to Close ResultSets

A `ResultSet` is bound to its `Statement`. Close both when finished. While closing a `Statement` closes its current `ResultSet` per the JDBC contract, declaring both in try-with-resources makes ownership explicit.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "select order_id, status from orders where status = ?")) {

    ps.setString(1, "OPEN");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process row.
        }
    }
}
~~~

### 4.3. Connection Pools Extend Leak Lifetimes

In a pool, `Connection.close()` usually returns the logical connection to the pool rather than closing the physical Oracle session. If `Statement`/`ResultSet` objects remain unclosed, resources stay attached to the reused session.

Closing `Connection` does not replace closing `Statement`/`ResultSet`. Close every resource per its ownership scope before returning the connection.

### 4.4. PL/SQL Explicit Cursors

Example closing the cursor on both success and exception paths:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN';

    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;

        -- Process row.
        NULL;
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

A PL/SQL cursor `FOR` loop manages `OPEN`/`FETCH`/`CLOSE` automatically:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN'
    ) LOOP
        -- Process row.
        NULL;
    END LOOP;
END;
/
~~~

Cursor `FOR` loops are safer and more concise when explicit lifecycle control is unnecessary.

### 4.5. DBMS_SQL and REF CURSOR

When using `DBMS_SQL`, always close the cursor number with `DBMS_SQL.CLOSE_CURSOR` in exception-safe cleanup.

When a procedure returns `SYS_REFCURSOR`, JDBC must consume and close the `ResultSet` and `CallableStatement` in the proper order. Closing the outer call while keeping the `ResultSet` open can break fetching or leak resources.

## 5. Handling ORA-01000 Properly

Investigation order:

1. Record `SID`, `SERIAL#`, username, service, module/action, and error timestamp.
2. Read `opened cursors current` by session.
3. Inspect `V$OPEN_CURSOR` and `CURSOR_TYPE`.
4. Identify the SQL/PLSQL call paths allocating cursors.
5. Verify the application closes `ResultSet`/`Statement` objects.
6. Check `REF CURSOR`, `DBMS_SQL`, and dynamic SQL.
7. Review pool/session lifetimes and cursor growth over time.
8. Evaluate raising `OPEN_CURSORS` only after ruling out leaks.

### 5.1. Tracking Current Cursors Over Time

Sample `opened cursors current` by `SID` repeatedly alongside request/load metrics. If a session's count climbs steadily and never drops after work finishes, there is a leak or code holding cursors open too long.

If cursor counts rise under load and fall once requests finish, that is normal concurrency. Compare against baseline and `OPEN_CURSORS`.

### 5.2. When to Increase OPEN_CURSORS

Increase `OPEN_CURSORS` when:

- The application properly closes all resources.
- The workload legitimately requires many concurrent cursors.
- `opened cursors current` approaches the cap during peak load.
- Memory and session capacity are sufficient.
- The change is tested and monitored.

Never raise the parameter to mask an active leak. Raising the cap will only delay the failure.

## 6. ORA-04030: out of process memory

ORA-04030 reports that an Oracle process could not allocate required private memory. Process memory typically involves the PGA (Program Global Area) and other process-private memory regions.

Unlike the SGA shared across processes, the PGA is private to a server process. Under dedicated server, session workareas and private state reside in the PGA. Under shared server, UGA may reside in the SGA large pool or shared pool depending on configuration.

### 6.1. What Is PGA Used For?

The PGA can contain:

- Sort workareas.
- Hash join workareas.
- Bitmap merge workareas.
- Session/private SQL state.
- PL/SQL runtime memory.
- Collections, arrays, and package state.
- Private cursor state.
- Process buffers and internal memory structures.

Large sorts/hashes, growing PL/SQL collections, or loading massive data into process structures can cause PGA usage to spike.

### 6.2. PGA_AGGREGATE_TARGET and PGA_AGGREGATE_LIMIT

Check settings:

~~~sql
SHOW PARAMETER pga_aggregate_target;
SHOW PARAMETER pga_aggregate_limit;
~~~

- `PGA_AGGREGATE_TARGET` is the target for managing total PGA; Oracle uses it to size workarea allocations where applicable.
- `PGA_AGGREGATE_LIMIT` is the hard aggregate PGA limit enforced by Oracle; when exceeded, Oracle terminates calls/sessions to bring usage below the limit, raising related errors such as ORA-04036.

ORA-04030 is a private process allocation failure. It does not automatically mean `PGA_AGGREGATE_LIMIT` was exceeded. A single process can fail allocation due to OS/container limits, address space limits, fragmentation, or a single huge allocation even while total PGA remains below the aggregate limit.

Do not address ORA-04030 solely by increasing `PGA_AGGREGATE_TARGET`. Identify the exact process and allocation first.

### 6.3. Viewing Overall PGA Statistics

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Key statistics:

- `aggregate PGA target parameter`.
- `aggregate PGA auto target`.
- `total PGA allocated`.
- `maximum PGA allocated`.
- `total PGA inuse`.
- `over allocation count`.
- `extra bytes read/written`.
- `global memory bound`.

Statistic names may vary slightly across releases; querying all of `V$PGASTAT` verifies your exact environment.

### 6.4. Finding Processes with High PGA

~~~sql
SELECT p.spid,
       s.sid,
       s.serial#,
       s.username,
       s.program,
       s.module,
       p.pga_used_mem,
       p.pga_alloc_mem,
       p.pga_freeable_mem,
       p.pga_max_mem
FROM v$process p
LEFT JOIN v$session s
  ON s.paddr = p.addr
ORDER BY p.pga_alloc_mem DESC;
~~~

Columns:

- `PGA_USED_MEM`: PGA memory actively used by the process.
- `PGA_ALLOC_MEM`: PGA memory currently allocated to the process.
- `PGA_FREEABLE_MEM`: portion releasable under Oracle mechanisms.
- `PGA_MAX_MEM`: peak PGA memory ever used by the process.

`PGA_ALLOC_MEM` and `PGA_USED_MEM` are not identical. A process may retain allocated memory for reuse even when active usage drops.

### 6.5. Viewing PGA by Category

~~~sql
SELECT pid,
       serial#,
       category,
       allocated,
       used,
       max_allocated
FROM v$process_memory
ORDER BY allocated DESC;
~~~

Categories include `SQL`, `PL/SQL`, `OLAP`, `JAVA`, `Freeable`, and `Other` depending on workload and release. Categories help isolate the type of memory, though they do not directly identify the offending SQL statement.

### 6.6. Correlating Processes with Sessions and SQL

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       s.prev_sql_id,
       s.module,
       s.action,
       p.spid,
       p.pga_used_mem,
       p.pga_alloc_mem,
       p.pga_max_mem
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY p.pga_alloc_mem DESC;
~~~

The current `SQL_ID` may not be the statement that caused the peak allocation if the failure happened after an earlier operation or inside PL/SQL. Use trace/incident data and session history to investigate.

## 7. Causes of ORA-04030

Common causes:

### 7.1. Large Sorts or Hash Joins

Queries sorting huge row sets or hash-joining large inputs require substantial workarea memory. When memory is insufficient, Oracle spills to `TEMP`; if a process requests a large allocation that cannot be satisfied, it can fail.

Inspect the SQL plan, cardinality estimates, workareas, `TEMP`, and input data.

### 7.2. Large PL/SQL Collections

For example, `BULK COLLECT` loading an entire table into a collection:

~~~sql
SELECT *
BULK COLLECT INTO l_rows
FROM very_large_table;
~~~

This can cause process memory to balloon. Use `BULK COLLECT ... LIMIT` to process in bounded batches:

~~~sql
LOOP
    FETCH c_rows
    BULK COLLECT INTO l_rows
    LIMIT 1000;

    EXIT WHEN l_rows.COUNT = 0;

    -- Process a bounded batch.
END LOOP;
~~~

Choose `LIMIT` based on row size and memory budget, not just row count.

### 7.3. Fetching Too Much Data in the Application

An application may pull millions of rows into a `List` or `Map` before processing. Even though those objects live in the JVM heap rather than PGA, large fetches and concurrency increase sessions, cursors, and database memory usage. Distinguish Oracle-side process memory errors from JVM `OutOfMemoryError`.

### 7.4. Many Sessions Running Heavy Queries Concurrently

One query may run fine alone, yet hundreds of concurrent sessions sorting or hashing drive aggregate PGA sky-high. Inspect peak concurrency, Resource Manager, batch overlap, and job schedules.

### 7.5. OS or Container Memory Limits

Oracle processes require real memory from the OS. Limits can come from:

- Physical RAM/swap.
- Linux `ulimit`.
- cgroup/container memory limits.
- HugePages/address space configuration.
- Process count and OS resource caps.
- Memory fragmentation or allocation patterns.

Coordinate with OS administrators. Do not inspect only total host free memory; inspect per-process/container limits and memory pressure at failure time.

### 7.6. PL/SQL Package State and Session Lifetime

Package global variables, large collections, and session state can retain memory indefinitely in pooled sessions. If sessions live long, memory accumulates or fails to release as expected.

Review package state, use `DBMS_SESSION.RESET_PACKAGE` where appropriate for the lifecycle, and verify how pools reset sessions. Never reset package state arbitrarily if the application depends on persistent state.

## 8. Workareas and TEMP: Distinguishing Spills from Process Memory Errors

Oracle uses PGA for sort/hash workareas. When memory is tight, operations spill to `TEMP`.

Inspect active workareas:

~~~sql
SELECT sid,
       operation_type,
       operation_id,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       number_passes,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY last_memory_used DESC;
~~~

Names/columns may vary by release. Query `V$SQL_WORKAREA` to analyze historical workarea sizing and execution modes.

Spilling to `TEMP` slows queries down but does not automatically produce ORA-04030. Conversely, raising PGA reduces spills while increasing overall memory pressure. Balance both according to workload and host capacity.

### 8.1. Tune Queries Before Adding Memory

- Check cardinality estimates and execution plans.
- Filter rows earlier before sorts/joins where logic permits.
- Add appropriate indexes for predicates/joins/order-by after measuring.
- Avoid `SELECT *` when unnecessary.
- Check for stale statistics.
- Eliminate Cartesian joins or faulty join conditions.
- Batch large data-processing jobs.
- Cap concurrency of heavy batches and reports.

Never add indexes or hints blindly based solely on ORA-04030; inspect plans and workloads first.

## 9. ORA-04031: unable to allocate bytes of shared memory

ORA-04031 occurs when Oracle cannot allocate a requested chunk of memory inside an SGA pool. The error message typically states the requested byte count and the pool/heap/subheap involved.

Affected areas can include:

- Shared pool.
- Large pool.
- Java pool.
- Streams pool.
- Other SGA memory areas depending on release/configuration.

ORA-04031 does not automatically mean the entire SGA is out of RAM. The SGA may show overall free memory while the specific pool/heap lacks a large enough contiguous chunk or suffers fragmentation/pressure.

### 9.1. What Is the Shared Pool Used For?

The shared pool holds shared structures including:

- Library cache: parsed SQL, PL/SQL code, and related metadata.
- Data dictionary cache / row cache.
- Shared SQL areas.
- Control structures and other allocations.

Heavy hard parsing, varying SQL text, growing child cursor counts, invalidations, or shared pool contention drive shared pool consumption up.

### 9.2. What Is the Large Pool Used For?

The large pool provides dedicated SGA memory for large allocations to avoid contending with the shared pool in applicable workloads, such as:

- Shared server UGA.
- Parallel execution message buffers.
- Certain RMAN I/O buffers.
- Backup/restore or execution buffers per configuration.

If ORA-04031 names the large pool, investigate shared server, parallel execution, RMAN, and large pool sizing; do not blindly increase the shared pool.

### 9.3. Inspect SGA Memory by Pool

~~~sql
SELECT pool,
       name,
       bytes
FROM v$sgastat
ORDER BY pool, bytes DESC;
~~~

Aggregate:

~~~sql
SELECT pool,
       SUM(bytes) AS bytes
FROM v$sgastat
GROUP BY pool
ORDER BY bytes DESC;
~~~

`V$SGASTAT` shows allocations by pool and component name. A single snapshot does not prove fragmentation; capture multiple snapshots under load and correlate with alert/trace logs.

### 9.4. Inspect the Shared Pool Reserved Area

~~~sql
SELECT free_space,
       avg_free_size,
       used_space,
       avg_used_size,
       requests,
       request_misses,
       last_miss_size,
       max_miss_size
FROM v$shared_pool_reserved;
~~~

`request_misses` and `last_miss_size` help assess large allocation failures in the reserved pool. Exact semantics and columns vary by release.

Do not raise `SHARED_POOL_RESERVED_SIZE` simply because `request_misses` is non-zero; analyze alongside workload, reserved list behavior, and error traces.

### 9.5. Inspect the Library Cache

~~~sql
SELECT namespace,
       gets,
       gethits,
       pins,
       pinhits,
       reloads,
       invalidations
FROM v$librarycache
ORDER BY namespace;
~~~

Rising reloads/invalidations indicate library cache churn or object invalidation. Compare deltas over time and workload rather than judging from a single cumulative total.

### 9.6. Inspect SQL Parsing and Child Cursors

~~~sql
SELECT sql_id,
       version_count,
       parse_calls,
       executions,
       loads,
       invalidations,
       sql_text
FROM v$sqlarea
ORDER BY version_count DESC
FETCH FIRST 30 ROWS ONLY;
~~~

SQL generating distinct literals proliferates parent/child cursors. Use bind variables where appropriate and inspect child cursor mismatch reasons:

~~~sql
SELECT sql_id,
       child_number,
       unbound_cursor,
       optimizer_mismatch,
       bind_mismatch,
       language_mismatch,
       auth_check_mismatch
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

`V$SQL_SHARED_CURSOR` has many reason columns depending on release. Pick columns suited to your version or inspect the full row. Never assume bind mismatch is the sole cause of ORA-04031.

## 10. Causes of ORA-04031

### 10.1. Shared Pool Pressure

- Shared pool undersized for workload.
- Heavy hard parsing.
- Literal SQL creating excessive cursors.
- High child cursor counts for the same `SQL_ID`.
- Frequent PL/SQL/package loading and invalidations.
- Dictionary cache pressure.
- Large allocations or fragmentation.
- Shared pool impacted by unstable workloads.

### 10.2. Large Pool Pressure

- Excessive parallel queries or high DOP.
- Surge in shared server sessions.
- Many RMAN channels/buffers.
- Sudden spike in large-pool-consuming workloads.
- Insufficient large pool under manual sizing.

### 10.3. Fragmentation

Total free bytes may look sizable while no single contiguous chunk fits the request. The shared pool uses complex heap/subheap allocation lifecycles; fragmentation is possible, but requires evidence from traces and pool statistics.

Never diagnose fragmentation solely because `V$SGASTAT` shows free memory rows.

### 10.4. SQL Churn and Hard Parsing

Application generating distinct SQL text per literal:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM orders
WHERE customer_id = 1002;
~~~

Use bind variables where appropriate:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
~~~

Binds enable cursor reuse in many workloads and reduce parse overhead. Note that bind peeking, adaptive cursor sharing, and data skew can still produce child cursors; binds are not a cure-all for every plan issue.

### 10.5. Cursor Leaks Are Related Yet Distinct

An open cursor retains private session/process state and links to a shared SQL area. However, ORA-04031 is an SGA pool allocation failure, whereas ORA-01000 is exceeding the per-session open cursor limit.

When seeing both, investigate cursor lifecycles, shared pool pressure, and PGA/session memory independently. Never just raise both `OPEN_CURSORS` and `SHARED_POOL_SIZE` together.

## 11. Distinguishing SGA, PGA, UGA, and Cursor Memory

| Area | Shared? | Purpose | Related Error |
|---|---|---|---|
| SGA | Shared within instance | Buffer cache, shared pool, large pool, redo buffer, instance structures | ORA-04031 |
| PGA | Process-private | Workareas, private state, sorts/hashes, PL/SQL memory | ORA-04030 |
| UGA | Session state | Session memory, package state, cursor state | Location depends on server mode |
| Session cursor state | Per session | Open cursor handles and execution state | ORA-01000 |

In dedicated server mode, UGA typically lives inside the server process's PGA. In shared server mode, UGA can live inside the SGA—typically in the large pool when properly configured.

A single cursor uses a shared SQL area in the SGA and private/session state in PGA/UGA. Thus cursor workloads pressure multiple memory regions, yet each ORA error pinpoints a specific failure mode.

## 12. Connecting ORA-01000 to JDBC, Spring, and ORMs

Java applications typically rely on connection pools. A physical Oracle session is reused across many requests; a cursor leak in one request accumulates across subsequent borrows if statements/result sets are left unclosed.

### 12.1. Try-with-resources

~~~java
String sql =
    "select order_id, status from orders where customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Process row.
        }
    }
}
~~~

In Spring transaction-managed code, do not close connections owned by the transaction manager outside its contract; use `JdbcTemplate` or let the framework manage connections. Still ensure any `Statement` and `ResultSet` you allocate directly are properly released.

### 12.2. Spring JdbcTemplate

`JdbcTemplate` automatically manages `Statement` and `ResultSet` inside callbacks:

~~~java
List<OrderRow> rows = jdbcTemplate.query(
    "select order_id, status from orders where customer_id = ?",
    (rs, rowNum) -> new OrderRow(
        rs.getLong("order_id"),
        rs.getString("status")
    ),
    customerId
);
~~~

Never return a JDBC `ResultSet` or stream outside the callback after `JdbcTemplate` closes resources. For streaming large results, use callback-based streaming APIs with explicit lifecycles and close the stream before the connection returns to the pool.

### 12.3. JPA Streams / Scrollable Results

JPA `Stream` or Hibernate scrollable results keep JDBC cursors and connections open while the caller consumes rows. Always use try-with-resources:

~~~java
try (Stream<OrderEntity> stream = repository.streamByStatus("OPEN")) {
    stream.forEach(this::process);
}
~~~

The repository method requires an active transaction, and provider-specific behavior must be verified. Never pass a stream outside its transaction and attempt to consume it after the transaction closes.

### 12.4. Statement Caching Does Not Replace Closing

Oracle JDBC implicit statement caching retains closed statements for reuse. Calling `close()` is still mandatory; the driver/pool moves the statement into cache instead of immediately destroying the physical cursor.

Distinguish intentional cursor caching from leaks. Inspect cursor types and session statistics before disabling statement caches or changing pool settings.

## 13. Runbook for Handling ORA-04030

### Step 1 — Capture Process/Session Details

Record:

- Instance and host.
- `SID`/`SERIAL#`.
- Username, service, module/action.
- `SPID`/process ID.
- `SQL_ID`/`PREV_SQL_ID`.
- `PGA_USED_MEM`, `PGA_ALLOC_MEM`, `PGA_MAX_MEM`.
- Timestamp and active workload.

### Step 2 — Check Process Memory Categories

Query `V$PROCESS_MEMORY` and `V$PGASTAT`. Identify rapidly growing categories and overall PGA trends.

### Step 3 — Check Execution Plans/Workareas

Inspect running SQL, `V$SQL_WORKAREA_ACTIVE`, `TEMP` usage, row counts, and execution plans.

### Step 4 — Check PL/SQL and Applications

Look for unbounded `BULK COLLECT`, unconstrained collections, package state, Java stored procedures, huge fetches, and high concurrency.

### Step 5 — Check the OS

Collect process RSS/virtual memory, `ulimit`, cgroup/container memory limits, swap, kernel logs, and memory pressure at the exact timestamp. Coordinate with the OS team.

### Step 6 — Recover and Reduce Load

Depending on root cause:

- Reduce batch/query concurrency.
- Chunk batches using `LIMIT`.
- Reduce intermediate data volume.
- Tune joins/sorts.
- Adjust workarea/PGA sizing within capacity.
- Fix memory leaks in code.
- Restore OS/container memory headroom.
- Apply Resource Manager limits if needed.

Never kill a process solely for high PGA before evaluating its transaction and business impact. Aborting a process triggers rollback and forces applications to handle retries.

## 14. Runbook for Handling ORA-04031

### Step 1 — Read Full Error Message and Trace

Record requested byte count, pool/heap/subheap name, process/session, `SQL_ID`, and incident trace. The pool name in the error stack is a critical clue.

### Step 2 — Identify the Pool

- Shared pool: library cache, dictionary cache, SQL/PLSQL allocations.
- Large pool: shared server, parallel execution, RMAN buffers.
- Java pool / Streams pool: respective workloads.
- Other pools: verify per release and trace.

### Step 3 — Capture SGA Snapshots

Query `V$SGASTAT`, `V$SHARED_POOL_RESERVED`, and related views. Capture multiple snapshots under load to compare deltas and free chunks.

### Step 4 — Check SQL/Library Cache

Inspect hard parses, `version_count`, child cursors, invalidations, literal SQL, bind mismatches, and object churn. Identify recent changes such as deployments, stats gathering, DDL, or batch spikes.

### Step 5 — Check SGA Configuration

~~~sql
SHOW PARAMETER sga_target;
SHOW PARAMETER sga_max_size;
SHOW PARAMETER shared_pool_size;
SHOW PARAMETER large_pool_size;
SHOW PARAMETER memory_target;
~~~

Under ASMM/AMM, Oracle manages dynamic component sizing according to the selected mode. Manual sizing and minimum component sizes affect allocation behavior. Never alter one parameter without reviewing the overall memory management mode.

### Step 6 — Recover

- Reduce hard parsing and SQL churn.
- Reduce concurrency or DOP if large pool pressure exists.
- Resize shared/large pools per workload and SGA capacity.
- Address invalidation/deployment churn.
- Investigate patches/known bugs when traces show a specific allocation failure pattern.
- Restart only with a plan and evidence showing it is necessary.

Never run `ALTER SYSTEM FLUSH SHARED_POOL` as a reflex. Flushing evicts cached SQL/PLSQL, triggers a hard parse storm, and worsens contention.

## 15. Evidence-Based Memory Tuning

### 15.1. Do Not Raise Parameters Blindly

| Parameter | Impact | Check First |
|---|---|---|
| `OPEN_CURSORS` | Raises allowed open cursors per session | Leaks, peak current cursors, PGA/session count |
| `SESSION_CACHED_CURSORS` | Increases per-session cursor cache | Parse workload, session count, memory |
| `PGA_AGGREGATE_TARGET` | Target total PGA/workarea | Total PGA, concurrency, `TEMP` spills, OS RAM |
| `PGA_AGGREGATE_LIMIT` | Hard aggregate PGA limit enforced by Oracle | Peak workload and available host memory |
| `SGA_TARGET` | Auto-managed SGA target | `SGA_MAX_SIZE`, host memory, component sizing |
| `SHARED_POOL_SIZE` | Size or floor for shared pool depending on mode | Parse rate, library cache, SGA mode |
| `LARGE_POOL_SIZE` | Size or floor for large pool depending on mode | PX, shared server, RMAN demand |

### 15.2. SGA/PGA and OS Headroom

SGA and PGA compete for the host's physical RAM. Raising SGA reduces headroom available for PGA and the OS. Raising PGA limits allows concurrent processes to consume more memory.

Capacity planning must account for:

- SGA.
- Peak aggregate PGA.
- OS/kernel memory.
- Agents/monitoring processes.
- Filesystem cache and co-located workloads.
- Container/cgroup limits.
- RAC node failure/degraded capacity if applicable.

### 15.3. RAC and Multiple Instances

`V$` views reflect only the current instance. In RAC, use `GV$` views to aggregate across instances and preserve `INST_ID`:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       status
FROM gv$session
WHERE type = 'USER'
ORDER BY inst_id, sid;
~~~

`OPEN_CURSORS` applies per instance/session configuration; investigate failing sessions on the exact instance. Analyze PGA and SGA pressure per node as well.

## 16. Monitoring and Early Alerting

Establish baselines for:

- `opened cursors current` per session.
- Ratio of sessions approaching `OPEN_CURSORS`.
- PGA allocated/used/max per process.
- Total PGA allocated and over-allocations.
- SGA pool usage and free memory.
- Shared pool reserved request misses.
- Library cache reloads and invalidations.
- SQL `version_count` and hard parses.
- `TEMP` usage and active workareas.
- Connection pool active/idle/wait counts.
- Batch concurrency and execution duration.

### 16.1. Alert Thresholds

Do not apply one static threshold to every database. Alert on ratios and trends:

- Session open cursors reaching a high percentage of `OPEN_CURSORS`.
- Process PGA growing rapidly or exceeding baseline.
- Aggregate PGA approaching `PGA_AGGREGATE_LIMIT`.
- Rising shared/large pool allocation misses.
- Simultaneous increases in connection pool waits and active connections.

Use rolling windows, deltas, and alert durations to suppress false positives. Alerts should identify `SID`/`INST_ID`/module/action and link to the matching runbook.

### 16.2. AWR/ASH and Diagnostic Licensing

AWR/ASH are helpful for reviewing historical workload, SQL, waits, and memory behavior, though Diagnostic/Tuning Pack features require licensing per your Oracle contract. Verify entitlement before using them. Dynamic performance views and current traces can always be used within standard permissions.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| ORA-01000 means the shared pool is full | It is a per-session open cursor limit |
| `V$OPEN_CURSOR` counts only genuinely open cursors | It can include cached cursors; check `CURSOR_TYPE` and session stats |
| `SESSION_CACHED_CURSORS` increases `OPEN_CURSORS` | The two parameters serve distinct purposes |
| Closing `Connection` in a pool is enough | `Statement`/`ResultSet` still require proper lifecycle closing |
| Raising `OPEN_CURSORS` always fixes the issue | It may merely delay a cursor leak |
| ORA-04030 means `PGA_AGGREGATE_LIMIT` was exceeded | Process allocation errors have multiple possible causes |
| Raising `PGA_AGGREGATE_TARGET` always fixes ORA-04030 | Must inspect processes, OS limits, and workload |
| ORA-04031 means the entire host is out of RAM | It is an SGA pool allocation error; may stem from pool sizing/heap/fragmentation |
| Shared pool and large pool are the same | Both serve different purposes and workloads |
| Flushing the shared pool cures fragmentation | It can trigger a hard parse storm |
| Every cursor leak causes ORA-04031 | ORA-01000, PGA, and SGA are distinct failure modes |
| `TEMP` spill equals ORA-04030 | Spills slow queries down; always read the exact error code |
| Raising memory needs no OS checks | SGA/PGA remain bounded by host/container limits |
| Restarting the database is the first fix | Restarts hide symptoms and cause downtime; do RCA first |

## 18. Hands-On Labs

Perform these in a lab database; never intentionally exhaust production resources.

### Lab 1 — Observing OPEN_CURSORS

Check `OPEN_CURSORS`, `SESSION_CACHED_CURSORS`, and session `opened cursors current`. Execute several queries/statements and observe how values change.

### Lab 2 — Cursor Lifecycle in JDBC

Write a program creating `PreparedStatement` in a loop. Compare unclosed statements against `try-with-resources`. Observe via session statistics.

### Lab 3 — Statement Caching

Enable Oracle JDBC/pool statement caching in the lab. Confirm statements are still closed at the API level and distinguish cached cursors from leaks.

### Lab 4 — PL/SQL Cursors

Write an explicit cursor with an exception path checking `%ISOPEN` and `CLOSE`. Compare with a cursor `FOR` loop.

### Lab 5 — REF CURSOR

Return a `SYS_REFCURSOR` from a procedure, fetch via JDBC `ResultSet`, and close both `ResultSet` and `CallableStatement`. Observe open cursor counts.

### Lab 6 — PGA Baseline

Capture `V$PGASTAT` and `V$PROCESS` before and after a sort/hash query in the lab. Record process PGA and the execution plan.

### Lab 7 — BULK COLLECT

Test unbounded `BULK COLLECT` on a small dataset, then switch to `LIMIT`. Compare memory and runtime; avoid exhausting host RAM.

### Lab 8 — Workareas and TEMP

Run sort/hash queries on test data and monitor `V$SQL_WORKAREA_ACTIVE` and `TEMP` usage. Distinguish one-pass/multipass execution from process memory errors.

### Lab 9 — Shared Pool Observation

Monitor `V$SGASTAT`, `V$SHARED_POOL_RESERVED`, and `V$LIBRARYCACHE` during a controlled parse-heavy workload. Do not flush the shared pool to create tests.

### Lab 10 — Bind Variables

Compare distinct literal SQL against bind-variable SQL in the lab. Observe `parse_calls`, `version_count`, and child cursors.

### Lab 11 — Connection Pools

Run a bounded load test tracking pool active/idle/wait counts and `opened cursors current` per session. Confirm all resources close cleanly after each request.

### Lab 12 — Runbook Simulation

Use captured traces, test harnesses, or snapshots to practice classifying ORA-01000, ORA-04030, and ORA-04031. Document root cause, evidence, actions, and post-checks.

## 19. Incident Handling Checklists

### ORA-01000

- [ ] Record `SID`/`SERIAL#`, `INST_ID`, service, module/action.
- [ ] Check `OPEN_CURSORS`.
- [ ] Read `opened cursors current` and `cumulative`.
- [ ] Inspect `V$OPEN_CURSOR` along with `CURSOR_TYPE`.
- [ ] Audit JDBC `Statement`/`PreparedStatement`/`ResultSet` closing.
- [ ] Audit PL/SQL explicit cursors, `REF CURSOR`, and `DBMS_SQL`.
- [ ] Check pool/session lifetimes.
- [ ] Distinguish cursor caching from leaks.
- [ ] Raise `OPEN_CURSORS` only after proving workload validity and memory headroom.

### ORA-04030

- [ ] Save error stack/trace and process ID.
- [ ] Correlate `SPID` with `SID`/`SERIAL#`/`SQL_ID`.
- [ ] Check `PGA_USED`/`ALLOC`/`MAX`.
- [ ] Check `V$PROCESS_MEMORY` categories.
- [ ] Check `V$PGASTAT` and PGA limits.
- [ ] Check workareas, `TEMP`, and execution plans.
- [ ] Check PL/SQL collections/`BULK COLLECT`/package state.
- [ ] Check concurrency and Resource Manager.
- [ ] Check OS/cgroup/`ulimit`/RAM/swap.
- [ ] Decide remediation before raising memory or killing processes.

### ORA-04031

- [ ] Record exact pool/heap/bytes in the error.
- [ ] Identify involved instance and session/process.
- [ ] Check `V$SGASTAT` by pool.
- [ ] Check `V$SHARED_POOL_RESERVED`.
- [ ] Check `V$LIBRARYCACHE` reloads/invalidations.
- [ ] Check SQL parsing, `version_count`, and child cursors.
- [ ] Check large pool consumers such as PX/RMAN/shared server.
- [ ] Check `SGA_TARGET`, `SGA_MAX_SIZE`, and memory mode.
- [ ] Capture snapshots over time rather than a single point.
- [ ] Avoid flushing shared pool or restarting without RCA.

## 20. Core Takeaways

- ORA-01000 is a per-session open cursor limit; inspect `OPEN_CURSORS` and `opened cursors current`.
- ORA-04030 is a process private memory allocation failure, typically involving PGA and OS allocation.
- ORA-04031 is an allocation failure inside an SGA pool; read the exact pool/heap in the error stack.
- Shared SQL cursors live in the library cache/SGA while session cursor state and private memory are separate; one workload can pressure multiple areas.
- `OPEN_CURSORS` differs from `SESSION_CACHED_CURSORS`; cursor caching is not a cursor leak.
- `V$OPEN_CURSOR` can show cached cursors; cross-check `CURSOR_TYPE` and `V$SESSTAT`.
- JDBC must close `ResultSet`, `Statement`, and `PreparedStatement`; connection pools do not remove cleanup responsibility.
- PL/SQL explicit cursors, `REF CURSOR`, and `DBMS_SQL` must be closed on both success and exception paths.
- Raise `OPEN_CURSORS` only when legitimate concurrent cursors require it and leaks have been ruled out.
- `PGA_AGGREGATE_TARGET` is a PGA management target; `PGA_AGGREGATE_LIMIT` is Oracle's aggregate cap; ORA-04030 does not necessarily mean the aggregate limit was exceeded.
- Unbounded `BULK COLLECT`, large collections, sorts/hashes, and concurrency drive process PGA up.
- `TEMP` spills slow queries down without automatically causing ORA-04030.
- The large pool serves workloads like shared server, parallel execution, and RMAN; do not confuse it with the shared pool.
- ORA-04031 can stem from pool pressure, fragmentation, hard parses, child cursors, or allocation patterns; never conclude from total free memory alone.
- Bind variables reduce SQL text churn and parse overhead, though child cursors and plan behavior still require review.
- Never flush the shared pool as a default cure because it can trigger a hard parse storm.
- SGA and PGA both consume host RAM; every memory change must account for OS/container headroom.
- In RAC, use `GV$` views and `INST_ID` to pinpoint the exact instance.
- Check AWR/ASH and Diagnostic/Tuning Pack licensing before using them.
- True root-cause fixes come from proper resource lifecycles, SQL/workload tuning, capacity planning, and monitoring; parameter changes are only one part of remediation.

### Recommended Oracle References

- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/) — ORA-01000, ORA-04030, ORA-04031 and related diagnostics.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$SESSTAT, V$STATNAME, V$OPEN_CURSOR, V$PROCESS, V$PROCESS_MEMORY, V$PGASTAT, V$SGASTAT, V$SHARED_POOL_RESERVED and V$LIBRARYCACHE.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Cursor management, PGA/workarea, SGA and shared pool tuning.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Memory architecture, initialization parameters and instance management.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — Explicit cursors, cursor FOR loops, REF CURSOR and DBMS_SQL.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC statement, result set and statement caching behavior.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostic and Tuning Pack feature licensing.

View columns, memory management behavior and available parameters vary by Oracle release and deployment mode. Capture the complete error stack and trace, verify the exact database version/RU and use a representative non-production workload before changing cursor limits, PGA/SGA sizing or pool configuration.
