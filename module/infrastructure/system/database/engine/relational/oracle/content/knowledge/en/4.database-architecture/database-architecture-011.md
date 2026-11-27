# Hard Parse, Soft Parse, Shared Cursors, and the Library Cache

When a Java application sends an SQL statement to **Oracle Database**, the database does not simply "read the statement and run it". Oracle must determine whether the SQL is valid, whether the user has access privileges, which objects are referenced, and which execution strategy is suitable. If the same SQL statement executes repeatedly, Oracle can **reuse the parsed information** instead of redoing all of that work.

That is why four closely linked concepts must be understood:

- **Hard parse**: Oracle must create or recreate execution structures for an SQL statement because no compatible shared cursor is available for reuse; this phase typically includes optimization and generating an execution plan.
- **Soft parse**: Oracle finds a usable shared cursor and skips most of the hard parse optimization work, though it still incurs cursor lookup and management overhead.
- **Shared cursor**: a shared Oracle-side structure storing parsed information of an SQL statement, reusable across multiple sessions when sharing conditions are met.
- **Library cache**: a cache area inside the **SGA's shared pool** holding shared objects such as SQL cursors and compiled PL/SQL objects.

Understanding these concepts accurately helps distinguish **slow due to parsing** from **slow due to SQL execution**, explains why bind variables can reduce server load, and clarifies cases where one SQL statement has multiple *child cursors*.

## 1. From SQL Text to Query Results

An SQL statement can go through the following stages:

\`\`\`text
Java application / SQL tool
        |
        | Send SQL text and bind values
        v
Oracle session
        |
        v
Check if a cursor is already ready to reuse in the session?
        |
        +-- Yes, still valid --> Can reuse session cursor
        |
        +-- No --> Look up shared cursor in library cache
                       |
                       +-- Compatible child cursor found
                       |      |
                       |      +--> SOFT PARSE --> EXECUTE --> FETCH (if any)
                       |
                       +-- No compatible child cursor found
                              |
                              +--> HARD PARSE
                                     - Syntax/semantic checks
                                     - Resolve privileges and objects
                                     - Optimize, build execution plan
                                     - Create shareable child cursor
                                                |
                                                v
                                          EXECUTE --> FETCH
\`\`\`

This diagram is a mental model, not a specification of every internal branch across all Oracle releases. In particular, **not every \`EXECUTE\` requires re-parsing**: an already open and prepared cursor can be executed many times with different bind values.

### Distinguishing Parse, Execute, and Fetch

| Stage | Role | Observation Example |
| --- | --- | --- |
| **Parse** | Validates and prepares the SQL/cursor | Resolves which tables/columns \`SELECT\` references, chooses or looks up a suitable plan |
| **Execute** | Runs the SQL statement against the database | Executes \`UPDATE\`, or initiates execution of a \`SELECT\` |
| **Fetch** | Retrieves query result rows | JDBC calls \`ResultSet.next()\` to read rows |

A \`SELECT\` can spend most of its time **fetching** many rows over the network even when parsing is very fast. Conversely, thousands of distinct SQL statements generated continuously can create substantial CPU load even if each returns only a single row. Therefore, track **parse frequency**, **parse time**, **execution count**, and **execution/data-retrieval time** separately.

## 2. Where Does the Library Cache Sit in Oracle Architecture?

Conceptually, Oracle uses shared memory (**SGA**) and process/session-private memory (commonly called **PGA**). Inside the SGA, the **shared pool** contains the **library cache** and other shared memory structures.

\`\`\`text
Oracle Database instance
|
+-- SGA (shared memory)
|   |
|   +-- Shared pool
|   |   |
|   |   +-- Library cache
|   |   |    +-- SQL shared cursors
|   |   |    +-- PL/SQL program units and related metadata
|   |   |
|   |   +-- Other shared memory structures
|   |
|   +-- Database buffer cache
|   |    +-- Cached data blocks
|   |
|   +-- Other SGA components
|
+-- Session/process state
    +-- Session-private execution and cursor state
\`\`\`

**The library cache is not the database buffer cache.** The library cache primarily enables reusing *execution structures, SQL/PLSQL info, and metadata*; the database buffer cache holds *data blocks*. An SQL statement with a shared cursor may still need to read millions of data blocks; reusing a parse does not turn an I/O-heavy query into an instantaneous one.

Nor is the library cache **permanent storage**. Cursors can be aged out under shared pool pressure, go unused, be invalidated by metadata changes, or require a new child cursor due to incompatible execution contexts. Thus "having run the SQL before" does not guarantee a soft parse forever.

## 3. Hard Parse: When Oracle Must Build Execution Structures

Suppose a session sends an SQL statement for the first time:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = 101;
\`\`\`

If no compatible shared cursor exists in the library cache, Oracle must perform a **hard parse**. Key steps can include:

1. **Syntax check**: whether keywords, expressions, and statement structure are valid.
2. **Semantic and object check**: whether tables, columns, schema, data types, and access privileges are valid.
3. **Optimization**: using object metadata, statistics, binds, and relevant settings to evaluate candidate access paths, joins, and processing orders.
4. **Execution plan / cursor creation**: storing required structures for execution that may be shared with eligible sessions later.

Hard parsing typically consumes more CPU, shared-structure manipulation, and synchronization resources than soft parsing. When multiple sessions concurrently try to build or load the same objects, library cache contention can rise.

However, **a hard parse is not always an error**. Genuinely new SQL, a schema change, refreshed statistics, or a necessary optimizer environment difference can all legitimately trigger hard parses. The goal is to avoid **unnecessary repeated** hard parses, especially on identical business SQL patterns.

### When Is the Execution Plan Chosen?

During hard parse, the Oracle Optimizer can select a plan such as index access, full table scan, nested loops, or hash join. The plan is stored in the child cursor and used for execution. Do not equate "plan chosen" with "plan executed": optimization belongs to preparation, while reading and transforming data belong to execution.

A single SQL text **is not guaranteed to keep one plan forever**. The same SQL can have multiple child cursors with different execution conditions or plans, and plans can also change on a subsequent parse when statistics, structures, or environments change.

## 4. Soft Parse: Finding and Reusing a Shared Cursor

Suppose the same SQL statement is sent again from another session:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = 101;
\`\`\`

If Oracle finds a valid and compatible child cursor, it can perform a **soft parse**: reusing existing execution information instead of optimizing from scratch. Oracle still performs steps such as cursor lookup and sharing eligibility checks, so a soft parse **is not completely free**.

To visualize:

| Scenario | Likely Outcome | Notes |
| --- | --- | --- |
| New SQL with no matching cursor | **Hard parse** | Must create execution structures |
| SQL already in library cache, sharing conditions match | **Soft parse** | Reuses child cursor |
| An open \`PreparedStatement\` executed repeatedly | **Not necessarily parsed every time** | Can reuse prepared cursor/session state |
| Previously run SQL that was invalidated or aged out | **May hard parse again** | Old cursor is no longer usable |
| Same SQL text but different environment requiring a separate child | **May hard parse a new child** | Sharing depends on more than SQL characters |

Soft parsing also differs from a **session cursor cache hit**. A session can retain references to recently used cursors to reduce repeated preparation and lookup overhead. That is a session-scoped optimization, whereas shared cursors in the library cache serve multiple compatible sessions. Both are helpful, yet they are not the same structure.

## 5. Parent Cursor and Child Cursor

When querying Oracle dynamic performance views, you may see one \`SQL_ID\` with multiple \`CHILD_NUMBER\` values. This reflects how Oracle manages **parent** and **child cursors**.

\`\`\`text
Library cache
  |
  +-- Parent cursor: SQL text / SQL identity
        SQL_ID = "example ID of an SQL text"
        |
        +-- Child cursor 0
        |      Environment and metadata A
        |      Execution plan X
        |
        +-- Child cursor 1
        |      Environment/bind characteristics B
        |      Execution plan X or Y
        |
        +-- Child cursor 2
               Environment/bind characteristics C
               Execution plan Y
\`\`\`

The **parent cursor** represents the SQL statement's identity in shared cursor management; a **child cursor** holds execution structures matching a specific sharing context. One parent can have one or many children, and **each child is not required to have a different plan**.

### Why Can Identical SQL Text Have Multiple Children?

Possible reasons include:

- Differences in **bind variable data types or metadata** sent by clients.
- Differences in **optimizer environment**, such as session settings affecting plan selection.
- Differences in **object resolution context, privileges, or dependency states** preventing reuse of an existing child.
- Statistics or metadata changes that **invalidate** an earlier cursor.
- **Adaptive Cursor Sharing** creating children suited to different bind value ranges when data skew makes plan choice sensitive to bind values.

Do not conclude "multiple child cursors = bug" from \`VERSION_COUNT\` alone. Inspect the growth rate, why children cannot be shared, memory consumption, parse time, and actual workload impact.

### \`SQL_ID\`, \`CHILD_NUMBER\`, and \`PLAN_HASH_VALUE\` Differ

| Field | Describes | What Can It Be Used For? |
| --- | --- | --- |
| \`SQL_ID\` | Identifier for an SQL text/statement in monitoring views | Locating execution details for the same SQL statement |
| \`CHILD_NUMBER\` | Sequence number of the child cursor under the parent | Distinguishing execution variants under the same parent |
| \`PLAN_HASH_VALUE\` | Hash value representing plan structure as provided by Oracle | Quick check for plan change signs; does not replace viewing the detailed plan |
| \`VERSION_COUNT\` | Number of child cursor versions for an SQL in aggregate views | Signals multiple children worth inspecting |

Two children can share the same \`PLAN_HASH_VALUE\`; two different SQLs can also produce plans that look similar. To diagnose accurately, examine **SQL text, child number, non-sharing reasons, and the actual execution plan**.

## 6. Bind Variables: The Key to Reducing SQL Text Fragmentation

Consider an application looking up customers by ID, but building SQL by concatenating values directly:

\`\`\`sql
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 101;
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 102;
SELECT ma_khach_hang, ho_ten FROM khach_hang WHERE ma_khach_hang = 103;
\`\`\`

These three statements contain **different literals**, so Oracle cannot simply treat them as the exact same SQL text under standard exact cursor sharing. This pattern easily spawns many parent cursors, drives extra parsing, and uses the shared pool inefficiently when applications generate thousands of variants.

Replace them with one SQL statement using a **bind variable**:

\`\`\`sql
SELECT ma_khach_hang, ho_ten
FROM khach_hang
WHERE ma_khach_hang = :ma_khach_hang;
\`\`\`

Executions pass values \`101\`, \`102\`, \`103\` separately at bind time. **The SQL text stays identical**, creating the opportunity for cursor sharing. Bind variables also help prevent **SQL injection** on input values because data is never concatenated into SQL syntax.

### Java JDBC: Using \`PreparedStatement\`

\`\`\`java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class KhachHangRepository {
    private final DataSource dataSource;

    public KhachHangRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void inTenKhachHang(long[] maKhachHang) throws SQLException {
        String sql = """
            SELECT ma_khach_hang, ho_ten
            FROM khach_hang
            WHERE ma_khach_hang = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            for (long id : maKhachHang) {
                statement.setLong(1, id);
                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        System.out.printf("%d: %s%n",
                                rs.getLong("MA_KHACH_HANG"),
                                rs.getString("HO_TEN"));
                    }
                }
            }
        }
    }
}
\`\`\`

Here:

1. **JDBC** uses \`?\` placeholders instead of Oracle SQL tools' \`:ma_khach_hang\` bind syntax.
2. The SQL is prepared once into a \`PreparedStatement\` on the borrowed connection, then **executed multiple times** with different bind values.
3. Oracle has the opportunity to reuse the cursor. In a multi-request application, reuse also depends on the **connection pool, statement cache, bind types, and cursor state**.
4. Using \`setLong\` keeps the value type consistent. Sending a numeric type on one call and a string type on another for the same bind position can cause implicit conversions and/or unnecessary extra child cursors.

This Java example uses text blocks, suitable for modern Java versions. Table and column names are assumed to exist in the schema, the Oracle JDBC driver is configured, and the account holds \`SELECT\` privilege.

**Never use string concatenation as a substitute for binds**:

\`\`\`java
// Avoid: generates distinct SQL texts and is unsafe with arbitrary input.
String sql = "SELECT * FROM khach_hang WHERE ma_khach_hang = " + userInput;
\`\`\`

Bind variables represent **data values**, not table names, column names, or keywords like \`ORDER BY\`. For dynamic identifiers, applications must validate against an allowlist of permitted names and assemble SQL from controlled templates.

## 7. Sharing a Cursor Does Not Mean "All Bind Values Share One Plan"

Binds prevent SQL text fragmentation, yet different values sometimes have **dramatically different selectivity**. For instance, an orders table has 99% of rows with status \`DONE\` and only 1% with status \`ERROR\`:

\`\`\`sql
SELECT *
FROM don_hang
WHERE trang_thai = :trang_thai;
\`\`\`

A plan suited for returning nearly the whole table can differ from a plan suited for fetching very few rows. Oracle has related mechanisms such as:

- **Bind peeking**: under certain conditions, the optimizer peeks at bind values during hard parse to estimate selectivity and choose a plan.
- **Adaptive Cursor Sharing (ACS)**: Oracle can detect that execution efficiency depends strongly on bind values and allow multiple child cursors corresponding to different value ranges.
- **Bind-sensitive / bind-aware**: states observable in certain releases and situations via \`IS_BIND_SENSITIVE\` and \`IS_BIND_AWARE\` in \`V$SQL\`.

Not every SQL with binds becomes bind-sensitive or bind-aware, nor does every bind value change spawn a new child. Behavior depends on Oracle version, statistics, predicate type, data volume, and optimizer environment. When seeing multiple children, distinguish **legitimate bind-driven children** from **unshareable children caused by mismatched settings or bind types**.

An important principle: **optimizing parse and optimizing the execution plan are two related yet distinct goals**. Reducing hard parses will not automatically speed up an SQL statement scanning far too much data. Conversely, forcing every query onto a single plan solely to minimize child cursors can make certain bind values run very slowly.

## 8. Hands-On Practice: Observing Parse and Shared Cursors

The examples below are intended for a **private Oracle practice schema** with privileges to create tables and run SQL. \`V$...\` views usually require access granted by a DBA; learners do not automatically hold these privileges merely by logging into a schema. Never grant broad administrative privileges just to run an observation exercise.

### 8.1. Preparing a Small Table

\`\`\`sql
CREATE TABLE cursor_demo (
    id       NUMBER(6) PRIMARY KEY,
    nhom     VARCHAR2(20 CHAR) NOT NULL,
    gia_tri  NUMBER(10, 2) NOT NULL
);

INSERT INTO cursor_demo VALUES (1, 'A', 100);
INSERT INTO cursor_demo VALUES (2, 'A', 200);
INSERT INTO cursor_demo VALUES (3, 'B', 300);
INSERT INTO cursor_demo VALUES (4, 'B', 400);
INSERT INTO cursor_demo VALUES (5, 'C', 500);
COMMIT;
\`\`\`

This small table helps distinguish SQL text, bind values, and execution. DDL can trigger invalidations/commits per Oracle mechanics; complete table setup **before** starting parse observation.

### 8.2. Sending Multiple SQL Texts Using Literals

\`\`\`sql
SELECT /* cursor_demo_literal_1 */ id, nhom
FROM cursor_demo
WHERE id = 1;

SELECT /* cursor_demo_literal_2 */ id, nhom
FROM cursor_demo
WHERE id = 2;

SELECT /* cursor_demo_literal_3 */ id, nhom
FROM cursor_demo
WHERE id = 3;
\`\`\`

Here not only do literal values differ, the marker comments differ as well. During observation, we expect to see **multiple distinct SQL texts**. Do not use these three queries to measure exact hard-parse ratios of a real application; they merely illustrate how distinct SQL texts cannot reuse the same parent under standard sharing.

### 8.3. Sending Identical SQL Text with Different Binds

In **SQL*Plus or SQLcl**, \`VARIABLE\` and \`EXEC\` are client tool commands, not standalone SQL statements usable verbatim in every JDBC API:

\`\`\`sql
VARIABLE p_id NUMBER

EXEC :p_id := 1
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;

EXEC :p_id := 2
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;

EXEC :p_id := 3
SELECT /* cursor_demo_bind */ id, nhom
FROM cursor_demo
WHERE id = :p_id;
\`\`\`

The comment and SQL text across the three \`SELECT\`s are **identical**; only the value of \`p_id\` changes. Depending on session and how the tool prepares/caches statements, Oracle can reuse the child cursor in the shared pool or even the session cursor.

### 8.4. Viewing Child Cursors with \`V$SQL\`

When authorized to read dynamic performance views:

\`\`\`sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_text LIKE 'SELECT /* cursor_demo_bind */%'
ORDER BY sql_id, child_number;
\`\`\`

Key column meanings:

| Column | How to Read |
| --- | --- |
| \`EXECUTIONS\` | Number of recorded executions for that child |
| \`PARSE_CALLS\` | Number of recorded parse calls; does not mean all were hard parses |
| \`LOADS\` | Number of times the cursor was loaded/reloaded per Oracle stats |
| \`INVALIDATIONS\` | Number of times the cursor was marked invalid |
| \`IS_BIND_SENSITIVE\`, \`IS_BIND_AWARE\` | Hints regarding bind sensitivity and adaptive cursor sharing state |
| \`PLAN_HASH_VALUE\` | Signal for comparing plans across children |

Do not automatically expect \`PARSE_CALLS = EXECUTIONS\` or \`PARSE_CALLS = 1\`. Results are affected by observation timing, cursor caching, session count, and driver/tool version.

View parent summary:

\`\`\`sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM v$sqlarea
WHERE sql_text LIKE 'SELECT /* cursor_demo_bind */%';
\`\`\`

If \`VERSION_COUNT\` exceeds 1, investigate the concrete reason rather than assuming every child is redundant.

### 8.5. Finding Why Child Cursors Are Not Shared

\`V$SQL_SHARED_CURSOR\` provides flag columns indicating cursor sharing eligibility. You can start with:

\`\`\`sql
SELECT *
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
\`\`\`

The \`:sql_id\` parameter is the SQL_ID found from \`V$SQL\` or \`V$SQLAREA\`. Reason columns, data types, and display format can vary by Oracle version. Pay attention to categories such as \`BIND_MISMATCH\`, \`OPTIMIZER_MISMATCH\`, or access-context mismatches, and cross-check with session settings and bind metadata.

A \`Y\` flag in one column does not replace analyzing when the child was created, execution counts, and performance impact. Nor should you try to eliminate every mismatch if Oracle legitimately created a child to serve a better plan.

### 8.6. Distinguishing Total Parses from Hard Parses via Session Statistics

Oracle tracks statistics such as \`parse count (total)\`, \`parse count (hard)\`, \`session cursor cache hits\`, and \`execute count\`. With privileges to inspect your own session's stats:

\`\`\`sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
  AND n.name IN (
      'parse count (total)',
      'parse count (hard)',
      'session cursor cache hits',
      'execute count'
  )
ORDER BY n.name;
\`\`\`

To evaluate, record values before and after a **controlled** workload and examine the **deltas**. The stats query itself and helper commands also contribute to counters, so do not interpret deltas as absolute exact counts when running only a few manual SQL statements. For a rigorous measurement, run repeated workloads with consistent observation methodology and avoid mixing in unrelated queries or tasks.

These statistics help answer:

- Is the total number of parse requests Oracle receives growing rapidly relative to application needs?
- Is the hard-parse ratio significant when the workload consists only of a few repeated SQL templates?
- Is the session cursor cache being utilized?
- Did changing binding and statement reuse reduce parse counts?

**Do not use a single fixed percentage as a "universal healthy standard for all systems".** An OLTP workload running the same SQL millions of times differs completely from a reporting system running thousands of unique ad-hoc queries per day.

## 9. Factors That Prevent Cursor Reuse

### 9.1. Constantly Changing SQL Text

Differences in whitespace, comments, schema prefixes, literals, or predicate construction can cause Oracle to treat statements as distinct SQL texts under exact cursor sharing. For example, code generating \`IN (1,2)\` and then \`IN (1,2,3)\` dynamically alters the SQL shape.

Solutions depend on requirements: use binds, keep SQL templates stable, and choose suitable query patterns for variable-length parameter lists—rather than replacing every case with one overly complex generic query just to reduce \`SQL_ID\` counts.

### 9.2. Incompatible Bind Types or Optimizer Environment

Even with the same SQL \`WHERE id = :id\`, a client passing a number sometimes and a string other times can trigger type conversion differences or separate children. Inconsistent session settings such as NLS or optimizer parameters can also impair sharing in certain situations.

**Keep bind data types explicit and consistent** across code paths and frameworks. Also inspect actual metadata before assuming the problem is simply "same SQL having many children".

### 9.3. Invalidation from Object or Statistics Changes

Table/index structural changes, certain administrative operations, dependent object changes, or statistics updates that invalidate dependent cursors can force cursors to be recompiled/re-optimized. Hard parsing after such invalidation can be completely normal.

Do not try to prevent every invalidation; perform DDL/migrations, statistics gathering, and application changes in a controlled manner, especially on high-traffic systems.

### 9.4. Shared Pool Memory Pressure

The library cache uses finite memory. When many distinct SQL texts and shared objects compete for space, older cursors can be evicted from cache; the next execution may then require a hard parse again.

Before increasing shared pool size, inspect **distinct SQL text counts**, bind usage, child cursors, invalidations, CPU impact, and related wait events. Adding memory cannot fix an application generating thousands of nearly identical SQL statements.

### 9.5. Contention in the Library Cache

Sessions must coordinate when accessing, modifying, or pinning shared structures. In some workloads, waits involving **library cache lock**, **library cache pin**, or **cursor mutex** mechanisms can appear. Causes include DDL affecting active objects, excessive parsing, many sessions contending on the same cursor, or version/compatibility issues.

Do not assume "library cache wait = not enough RAM" or "every shared cursor causes contention". Inspect the specific wait event, involved sessions, SQL_ID, timing of schema changes, and load profile before intervening.

## 10. Three Cache Layers Often Confused with One Another

In Java applications connecting to Oracle, distinguish:

| Layer | Scope | What Does It Hold? | Benefit |
| --- | --- | --- | --- |
| **JDBC statement cache / PreparedStatement reuse** | Application/driver side, per physical connection | Statement state kept by the driver, potentially linked to a server cursor | Reduces prepare/open calls and communication overhead |
| **Session cursor cache** | Oracle session | Recently used cursors reusable within the session | Reduces repeated cursor lookup/open work |
| **Library cache / shared cursor** | Shared pool, across multiple sessions | Shared SQL cursors, PL/SQL, and shared metadata | Reduces hard parses across compatible sessions |

For example, a Java application has a 10-connection pool. The same SQL template can be used across multiple connections; the **library cache** shares SQL structures instance-wide, while the **driver statement cache** and **session cursor cache** remain scoped per individual connection / Oracle session.

### \`SESSION_CACHED_CURSORS\` and \`OPEN_CURSORS\`

- \`SESSION_CACHED_CURSORS\` controls how many cursors a session can cache to reduce repeated parsing. Suitable values depend on workload and statement usage patterns.
- \`OPEN_CURSORS\` limits how many cursors a single session can have open simultaneously. **\`ORA-01000: maximum open cursors exceeded\`** usually requires reviewing how the application closes \`Statement\`/\`ResultSet\` objects, driver caching, and actual cursor counts; merely raising the parameter can mask resource leaks.

In JDBC, \`try-with-resources\` closes \`ResultSet\` and \`Statement\` and returns \`Connection\` to the \`DataSource\` pool. However, API-level closing **does not necessarily immediately wipe cursor structures across all three cache layers**; caches may intentionally retain entries for reuse within configured limits.

Do not blindly enable every form of statement caching with huge sizes without measuring. Choose mechanisms supported by your driver/framework, bound cursor consumption, and evaluate reuse against real application behavior.

## 11. \`CURSOR_SHARING\`: Not a Switch That Fixes Every Hard Parse

Oracle provides the \`CURSOR_SHARING\` parameter affecting how SQL texts containing literals can be shared. Two commonly discussed modes:

- **\`EXACT\`**: sharing based on identical SQL text and compatibility rules; applications should use bind variables themselves when repeating the same SQL pattern.
- **\`FORCE\`**: Oracle can replace certain literals with system-generated binds, increasing cursor sharing opportunities among structurally similar statements.

Do not treat \`FORCE\` as a permanent replacement for using \`PreparedStatement\` properly. It does not fix SQL injection in string-concatenated code, does not guarantee every SQL is shared, and can degrade cardinality/plan estimates for literal-sensitive queries. Syntax and semantic exceptions depend on Oracle version.

Changing system-level parameters can affect multiple applications. It is a decision requiring workload verification and rollout planning, not a default exercise-level optimization trick.

## 12. From Performance Symptoms to Action

When suspecting high parse overhead, proceed in order:

1. **Identify symptoms**: high CPU, dropping throughput, rising latency, or library cache/mutex wait events.
2. **Measure parse counts**: inspect \`parse count (hard)\`, \`parse count (total)\`, and \`execute count\` at the appropriate session/workload scope alongside specific SQL stats.
3. **Find fragmented SQL patterns**: are many statements differing only in literals, object names, or dynamic SQL fragments?
4. **Inspect child cursors**: if \`VERSION_COUNT\` is high, check \`V$SQL_SHARED_CURSOR\` and bind/optimizer metadata.
5. **Check invalidations and cache pressure**: were there recent DDLs, stats updates, session changes, or shared memory shortages?
6. **Fix the root cause at the source**: use binds, reuse statements, stabilize bind types, manage connections properly, and reduce unnecessary SQL variants.
7. **Re-measure under the same workload**: verify whether hard parses, CPU, response times, and execution plan quality improved.

Helpful observation views include \`V$SQL\`, \`V$SQLAREA\`, \`V$SQL_SHARED_CURSOR\`, \`V$SESSTAT\`, \`V$STATNAME\`, and \`V$LIBRARYCACHE\`. Deeper diagnostic tools may require corresponding access privileges and licensing; use only capabilities permitted in your environment.

### Three Diagnostic Examples

**Case A — many distinct SQL_IDs, each executed only a few times.** The application may be concatenating literal values into SQL text. Start in the SQL-building code, convert input values to bind variables, and re-measure.

**Case B — one SQL_ID with many child cursors.** Check \`V$SQL_SHARED_CURSOR\`, bind types, session setting differences, and potential adaptive cursor sharing. Do not force merging children at all costs if distinct plans are genuinely needed.

**Case C — hard parses spike after deployment or DDL.** This may stem from invalidation or cache warm-up after changes. Distinguish a temporary spike from sustained hard parsing throughout runtime.

## 13. Self-Practice Questions

1. How do \`SELECT ... WHERE id = 1\` and \`SELECT ... WHERE id = 2\` built via Java string concatenation differ from one \`PreparedStatement\` with \`WHERE id = ?\`?
2. An SQL statement has \`EXECUTIONS = 10_000\` and \`PARSE_CALLS = 50\`. Did it necessarily hard parse 50 times? Why?
3. If the same \`SQL_ID\` has two \`CHILD_NUMBER\` values, can you conclude both children have different execution plans?
4. Why do bind variables both reduce SQL text fragmentation and potentially lead to multiple child cursors on bind-sensitive queries?
5. Why does data residing in the database buffer cache not imply the SQL cursor is in the library cache, and vice versa?
6. When encountering \`ORA-01000\`, why should you inspect how the application closes JDBC statements and cursor caches before simply raising \`OPEN_CURSORS\`?
7. A new SQL statement appears after adding an index and requires a hard parse. Is that necessarily a performance problem? What additional info should you inspect?

## 14. Summary of Accurate Understanding

**Hard parse** is the necessary work to build execution structures when no usable child cursor exists; **soft parse** reuses an existing shared cursor and avoids most optimization cost while still consuming resources. The **library cache** resides in the shared pool and enables sessions to reuse SQL/PLSQL structures; **parent/child cursors** explain why identical SQL text can still maintain multiple execution versions compatible with different contexts.

For Java applications, the most important practical rule is to **keep SQL text stable for identical business logic, pass data via bind variables, manage statement/connection lifecycles properly, and inspect metrics before tuning caches**. The goal is not to drive every parse to zero, but to let Oracle dedicate resources to actual execution work with plans suited to live data.
