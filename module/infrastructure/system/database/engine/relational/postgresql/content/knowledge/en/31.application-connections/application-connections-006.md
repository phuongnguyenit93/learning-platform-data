# Connection Pools, Connection Limits, and Load-Based Sizing

A Java API handles thousands of HTTP requests per minute yet needs SQL execution for only a tiny fraction of each request. If the application opens a fresh PostgreSQL connection for every request, authentication, session startup, TLS, and backend process creation overhead spike sharply. If it keeps **a dedicated connection per request**, the database can run out of connection slots and RAM when traffic rises. If the pool is too small, requests queue waiting for a connection and time out even while the database still has idle CPU. Conversely, an overly large pool lets too many queries contend for CPU, locks, and I/O, causing throughput to **drop** even as connection count rises.

**A connection pool** reuses established connections, caps concurrent work entering PostgreSQL, and forms a short queue at the application tier. **Sizing** is the process of choosing pool dimensions based on **workload, application replica count, connection hold time, database resources, slow queries, latency budgets, and recovery behavior**—not a fixed rule like "10/50/100 connections is always right".

This lesson uses PostgreSQL, Java/JDBC, HikariCP, and PgBouncer as examples. Parameter values and outputs are annotated illustrations, not substitutes for measurements on your specific server.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the PostgreSQL connection lifecycle and why many backend sessions consume resources.
2. Distinguish **client connection**, **server connection**, **physical JDBC connection**, **logical connection lease**, and **active SQL query**.
3. Understand `max_connections`, reserved connection slots, and limits enforced by the server, proxy, or managed service.
4. Build connection budgets across multiple services, replicas, background jobs, admin sessions, and other applications.
5. Estimate concurrency using `L = λ × W` (Little's Law) with consistent units.
6. Distinguish pool size, request concurrency, DB-active time, transaction duration, and connection hold time.
7. Configure basic HikariCP settings, close connections properly, and handle acquisition timeouts and connection leaks.
8. Distinguish PgBouncer **session pooling**, **transaction pooling**, and session-state limitations.
9. Align timeouts across application, JDBC, pooler, and PostgreSQL without conflicts.
10. Read `pg_stat_activity`, `pg_stat_database`, `pg_locks`, and pool metrics to pinpoint bottlenecks.
11. Design load tests and pick pool sizes via latency, throughput, and saturation rather than connection count alone.
12. Handle overload, connection storms, failover, autoscaling, long-running transactions, and slow SQL.
13. Design security, per-role/per-database limits, health checks, and readiness probes.
14. Apply a sizing workflow backed by metrics, formulas, experiments, and a deployment checklist.

> **Version note:** PostgreSQL has reserved-connection parameters added or adjusted across versions (such as `reserved_connections` in newer releases); some managed services reserve additional slots of their own. HikariCP and PgBouncer behaviors also vary by version and configuration. Always consult the documentation for the exact running versions before applying a specific value.

## 2. Why Opening a New Connection Is Expensive

For a typical PostgreSQL connection session:

```text
Client TCP/TLS
      │
      ▼
 PostgreSQL server
      │
      ├── authentication / access checks
      ├── backend process for the session
      ├── session state and memory contexts
      ├── transaction state
      ├── prepared statements / cursors / temp objects
      └── SQL statements and responses
```

PostgreSQL uses a **process-per-connection** model for regular client sessions. Each session carries setup overhead and dedicated memory/resources; adding more backend processes does not give the server more CPU cores.

If every request opens and closes a connection:

- TCP/TLS/authentication handshakes multiply.
- Process startup/teardown overhead climbs.
- Cold-path latency increases.
- Traffic spikes cause CPU and memory bursts.
- `max_connections` can be exhausted even when each request's SQL is brief.

A pool keeps a set of physical connections ready and **lends them sequentially to requests**. One connection cannot concurrently serve two independent transactions as two separate sessions at the same instant.

## 3. Precise Definitions of Connection Types

| Term | Meaning |
|---|---|
| HTTP request | An incoming API call; may not even need SQL |
| JDBC `Connection` | Client object representing a session/connection or pool-provided wrapper |
| Physical connection | Actual network connection to PostgreSQL or a pooler |
| Pool lease / borrowed connection | Duration the application holds a connection checked out from the pool |
| Idle pool connection | Connection sitting free in the app pool ready for reuse |
| Active pool connection | Currently borrowed by the app, **not necessarily executing SQL** |
| PostgreSQL backend | Server process/session corresponding to one physical server connection |
| Active SQL query | Backend currently executing a command, not every leased connection |
| Waiting query | SQL blocked on locks, I/O, client, or other resources |
| PgBouncer client connection | Connection from the app to PgBouncer |
| PgBouncer server connection | Connection from PgBouncer to PostgreSQL |

### A Key Point

**Pool active ≠ PostgreSQL query active.** A thread may borrow a connection, wait on another HTTP call, wait on a lock, or crunch data in Java. It still occupies a pool lease while the database may be doing no useful work.

## 4. Four Distinct Concurrency Quantities

For sizing, separate:

1. **Request concurrency**: how many HTTP requests are in flight concurrently.
2. **Connection checkout concurrency**: how many requests/tasks currently hold a connection lease.
3. **Database active query concurrency**: how many backends are executing SQL.
4. **PostgreSQL server connection count**: how many sessions are open, including idle ones.

Example:

```text
200 HTTP requests in flight
 ├── 150 doing CPU/HTTP/cache/JSON, not yet borrowing DB
 ├── 30 waiting in connection pool queue
 └── 20 holding a borrowed connection
       ├── 8 running SQL
       ├── 6 waiting on locks
       └── 6 processing in Java before commit
```

This is purely illustrative. You cannot deduce `maximumPoolSize=200` from request concurrency = 200.

## 5. An Ideal Request Model

```text
request
  │
  ├── validate input / authorize
  │
  ├── borrow DB connection
  │      ├── BEGIN
  │      ├── SQL 1
  │      ├── SQL 2
  │      └── COMMIT / ROLLBACK
  │
  ├── return connection to pool
  │
  └── serialize response / return HTTP
```

**Keep connection leases as short as possible** while preserving transaction correctness. Never borrow a connection prematurely or hold it across external HTTP calls, sleeps, or heavy CPU work that do not need an open DB transaction.

## 6. What Connection Pools Can and Cannot Do

A pool helps:

- Reuse connections.
- Cap total connections per process/instance.
- Bound concurrency hitting the database.
- Let requests wait up to a controlled timeout.
- Manage connection lifecycle, health, and retirement.
- Expose active/idle/pending metrics.

A pool **cannot** by itself:

- Add CPU or RAM to PostgreSQL.
- Fix SQL missing indexes or holding long locks.
- Guarantee transactions never leak.
- Enforce tenant permissions.
- Keep an in-flight transaction alive across a failover.
- Guarantee every server connection is doing useful work.
- Automatically know the optimal pool size across the entire cluster.

In fact, an oversized pool can worsen tail latency through lock contention, scheduler thrash, and I/O queueing.

## 7. PostgreSQL `max_connections`

Inspect:

```sql
SHOW max_connections;

SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name = 'max_connections';
```

`max_connections` caps the number of **concurrent connections** PostgreSQL accepts at the server level; it is not a target number of backends you should aim to saturate routinely.

### What Not to Do

Do not hit `too many connections` and immediately crank `max_connections` to 1000. If the server has only a few cores and limited RAM, a huge backend count causes:

- High memory and scheduler overhead.
- More queries fighting over shared resources.
- Less room reserved for operations/admin access.
- Higher risk of memory pressure under concurrent query execution.

Changing `max_connections` typically requires a **PostgreSQL restart** and must be coordinated with hardware/managed-service sizing.

## 8. Reserved Connection Slots

PostgreSQL reserves priority slots so privileged roles can still connect when regular clients nearly exhaust the limit.

Check available settings on your server:

```sql
SELECT name, setting, context
FROM pg_catalog.pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
```

`superuser_reserved_connections` sets aside priority connections for superusers per server configuration.

On versions with `reserved_connections`, an additional pool of slots is reserved for roles with appropriate privileges such as `pg_use_reserved_connections`, separate from superuser-only slots.

### Do Not Assume Availability Equals `100 - 3`

Managed providers, replication clients, monitoring sessions, and service roles can introduce extra limits. Even when `max_connections = 100`, assuming "the app can always use 97 connections" is dangerous.

Always leave **operational headroom** instead of pushing pools right up to the ceiling.

## 9. Per-Role and Per-Database Limits

PostgreSQL can enforce connection limits per role or database:

```sql
-- Run only with proper privileges on existing roles/databases.
-- ALTER ROLE app_user CONNECTION LIMIT 20;
-- ALTER DATABASE application_db CONNECTION LIMIT 80;
```

These limits are separate from `max_connections`, apply per role/database rules, and can reject clients **before global `max_connections` fills up**.

### Inspect Metadata

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_catalog.pg_roles
ORDER BY rolname;

SELECT
    datname,
    datconnlimit,
    datallowconn
FROM pg_catalog.pg_database
ORDER BY datname;
```

`-1` normally indicates no specific limit at that attribute level. Even then, global/server/provider constraints still apply.

## 10. The Connection Budget Covers More Than the Main App

One server may serve:

```text
                      PostgreSQL
                         ▲
        ┌────────────────┼────────────────┐
        │                │                │
    API service      Background jobs    BI / admin
      replicas        workers/pools      scripts
        │                │                │
     HikariCP          pool              psql
        │                │                │
        └────────────────┼────────────────┘
                         │
                monitoring / ops
```

Besides HTTP APIs, there are scheduled jobs, migration tools, ETL, BI, administrators, poolers, failover monitoring, and other clients.

If multiple applications share a server, compute **total physical server connections** under load and during autoscaling, not just one pod's `maximumPoolSize`.

## 11. Basic Budget Formula

Let:

- `Cmax`: `max_connections`.
- `Creserve`: slots reserved for priority/emergency roles per config.
- `Cother`: budget for connections outside the application being sized.
- `Cheadroom`: practical headroom for bursts, operations, and estimation error.

Preliminary budget for the application:

\[
C_{\mathrm{app,budget}}
= C_{\max} - C_{\mathrm{reserve}}
- C_{\mathrm{other}} - C_{\mathrm{headroom}}
\]

With `N` replicas, each having max pool size `P`, we need:

\[
N \times P \le C_{\mathrm{app,budget}}
\]

With multiple services:

\[
\sum_{i=1}^{k} N_iP_i
+ C_{\mathrm{jobs}}
\le C_{\mathrm{app,budget}}
\]

This is **upper-bound budgeting** for pools opening direct server connections, not a formula for **throughput-optimal** connection count. When using PgBouncer transaction pooling, account for PgBouncer's server pools plus any clients bypassing the pooler.

## 12. Multi-Replica Budget Example

Suppose PostgreSQL has the following design budget:

| Component | Connections |
|---|---:|
| `max_connections` | 120 |
| Reserved priority/emergency slots | 5 |
| Monitoring, BI, admin, and other clients | 20 |
| Headroom to stay clear of the ceiling | 20 |
| **Remaining budget for API** | **75** |

If the API runs **5 replicas**, the budget ceiling per pod pool is:

\[
P \le \left\lfloor \frac{75}{5} \right\rfloor = 15
\]

If you pick `maximumPoolSize = 12`:

\[
5 \times 12 = 60
\]

The application uses at most 60 server connections assuming **each pod has one pool connecting directly to the database**; 15 connections remain within the API budget alongside the separately reserved headroom.

### Why Not Automatically Pick 15?

15 is only the **budget ceiling** under one allocation. If benchmarks show peak throughput at 8–10 and queueing degrades at 12, pick the smaller pool.

### When Autoscaling to 8 Replicas

`8 × 12 = 96`, exceeding the 75 API budget. Pool size per pod must be calculated against **maximum allowed replicas**, or total budget must adapt when scaling—not only for today's 5 replicas.

## 13. Hidden Danger: Multiple Pools in One Process

A Spring Boot service may contain:

- One primary `DataSource`.
- One read-replica `DataSource`.
- One pool for background jobs.
- One pool created internally by a third-party library.
- Another pool in test/health tooling.

Saying "each pod has Hikari `maximumPoolSize = 10`" is misleading if there are actually three `HikariDataSource`s of max 10 each.

### Audit

List all datasource/pool instances by:

```text
service / deployment / pod
  ├── primary DB pool maximum
  ├── replica DB pool maximum
  ├── batch DB pool maximum
  └── external processes connecting same DB
```

Budget per **database endpoint**; if primary and replica are separate servers, do not lump all pools into one limit, yet budget each server individually.

## 14. Connection Count Is Not Active Work

Inspect:

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY state;
```

Common states:

- `active`: backend is executing a query, possibly also waiting on I/O or locks.
- `idle`: waiting for the next client command.
- `idle in transaction`: transaction is open, not currently running a query.
- `idle in transaction (aborted)`: failed transaction still open, awaiting rollback.
- `state IS NULL`: may occur due to privileges, backend type, version, or unavailable state.

### Do Not Assume "Idle Is Bad"

Idle sessions in a pool are normal: they are physical connections kept ready for reuse. What matters is excessive idle connections exhausting slots, or `idle in transaction` holding snapshots and locks and hurting vacuum.

## 15. How Much RAM Does Each Connection Use?

There is no single fixed MB figure valid across all versions, servers, and workloads.

Associated costs include:

- Backend process and memory contexts.
- Session/query state.
- Prepared statements, portals/cursors, and temporary data.
- Executor memory for sorts/hashes/aggregates while queries run.
- Backend-local caches and extension state.
- Shared memory is shared across backends; never multiply `shared_buffers` per backend.

### The `work_mem` Misconception

Do not naively calculate:

`total_RAM = max_connections × work_mem`

and assume that is total memory. `work_mem` is the budget **per operation** (such as sort or hash) inside a query, and one query plan can have multiple operations, plus parallel workers and other allocations. Real peak memory under concurrency must be measured for your workload.

### Yet Do Not Ignore `work_mem` Either

As concurrent running queries rise, total executor memory can climb steeply. A `work_mem` setting that is fine for 8 active queries can trigger memory pressure with 100 running concurrently.

## 16. Little's Law: The Foundational Formula

In a stable system:

\[
L = \lambda W
\]

where:

- `L`: average number of **in-flight work items inside the system**.
- `λ`: average arrival/completion throughput in items per second.
- `W`: average time an item spends within the **measured boundary**, in seconds.

When measuring specifically how long the application **holds a DB connection**:

\[
\text{avg leased connections}
\approx
\text{DB-using requests per second}
\times
\text{mean connection hold time}
\]

This holds accurately only when `λ` and `W` are measured over the **same work set and boundary**, and the system is reasonably steady. If one request borrows a connection multiple times, count **leases/second** or total hold time appropriately rather than multiplying requests/second blindly.

## 17. Little's Law Example

Suppose an API sees:

- 120 requests/second requiring the DB.
- Each request **borrows a connection exactly once**.
- Mean hold time = 50 ms = 0.05 s.

In steady state:

\[
L \approx 120 \times 0.05 = 6
\]

That means an average of about **6 leased connections** across the entire measured traffic scope.

### Do Not Immediately Set `pool = 6`

The number 6 **does not reflect**:

- Bursts and arrival variability.
- Tail latency (p95/p99 hold time).
- Locks and slow queries.
- Headroom for background jobs.
- Uneven traffic distribution across pods.
- Server behavior under higher concurrent query counts.

Sizing requires testing 8, 12, 16, etc. against realistic traffic distributions and benchmarks. Never derive a universal fixed safety multiplier from Little's Law alone.

## 18. What If Requests Hold Connections for 500 ms?

Still 120 requests/second, yet mean hold time rises from 50 ms to 500 ms:

\[
L = 120 \times 0.5 = 60
\]

Holding connections 10× longer increases average leased connection demand by 10× at the same throughput.

### A Better Fix Than Increasing the Pool

Ask **why is the connection held for half a second?**

- Slow SQL?
- Waiting on row locks?
- Returning too many rows with slow Java streaming?
- Application making HTTP calls inside a transaction?
- Framework opening transactions too early?
- `idle in transaction` gaps?

Cutting hold time from 500 ms to 100 ms often scales capacity far better than bumping a pool from 20 to 100.

## 19. Mean, p95, and Tail Latency

A workload where 99% of transactions hold a connection for 10 ms and 1% hold for 5 seconds may show a modest mean while exhibiting drastically different tail/queueing behavior.

Metrics to track:

- Mean/p50/p95/p99 **connection acquisition time**.
- Mean/p95/p99 **connection hold time**.
- SQL query duration and wait events.
- Pool active/idle/pending counts.
- Database CPU/I/O/lock waits.
- Error and timeout rates.

### Little's Law Does Not Pick p99 Pool Size Automatically

Little's Law uses **means**, not "multiply p99 hold time by throughput to guarantee p99 latency". Evaluating tail behavior requires load testing with realistic distributions, bursts, and service-time variability.

## 20. Queueing Is a Protective Mechanism, Not Just an Error

If a pool has 12 connections and 30 requests need a connection simultaneously:

```text
12 are granted connections
18 wait in the acquisition queue
  ├── a slot frees before deadline → proceed
  └── exceeds connectionTimeout → return error
```

Bounded waiting prevents slamming the database with all 30 queries simultaneously.

### Yet Unbounded Queues Signal Overload

Long wait queues tie up HTTP request threads, memory, and latency budgets. Configure:

- Pool acquisition timeout.
- HTTP request deadline.
- Queue / request concurrency limit.
- Retry and backpressure policy.

A pool must never act as an **infinite queue** masking a saturated database.

## 21. Pool Size vs. Throughput Is Non-Monotonic

Consider three regimes:

| Pool Size | Likely Outcome | What to Measure |
|---|---|---|
| Too small | Requests wait on the pool while DB has spare capacity | Pending, acquisition latency, DB CPU |
| Well-sized | DB stays busy, queues stay short, healthy throughput | Throughput, p95/p99, saturation |
| Too large | SQL contends for CPU/I/O/locks; tail latency spikes | CPU, wait events, lock waits, TPS |

**Never equate "more connections" with "faster".** If disk I/O or a row lock is the bottleneck, enlarging the pool only puts more workers in line behind the same bottleneck.

## 22. Which Layer Shows Overload?

| Layer | Symptom | First Line of Investigation |
|---|---|---|
| HTTP | Request queue, thread exhaustion | Concurrency limits, backpressure |
| Application pool | Pending rises, connection timeout | Hold time, pool size, and budget |
| PgBouncer | Client waiting, exhausted server slots | Server pool sizing, long transactions |
| PostgreSQL sessions | `too many connections` | Total pool budgets, reserved slots |
| CPU | 100% CPU, rising latency | SQL optimization, active concurrency |
| I/O | Read/write waits, temp spills | Indexes, memory/plan, disk capacity |
| Locks | Long waiting queries | Transaction scope, indexing, contention |
| WAL | Write/fsync pressure | Batch design, write workload tuning |

Raising `maximumPoolSize` helps only when it addresses the **actual bottleneck** without choking downstream layers.

## 23. HikariCP: Application-Side JDBC Pool

HikariCP is a widely used JDBC connection pool in Java/Spring.

Example creating a `HikariDataSource`:

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

HikariConfig config = new HikariConfig();
config.setPoolName("orders-primary");
config.setJdbcUrl(
    "jdbc:postgresql://db.internal:5432/ordersdb"
);
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(12);
config.setMinimumIdle(4);
config.setConnectionTimeout(2_000);
config.setIdleTimeout(600_000);
config.setMaxLifetime(1_800_000);

HikariDataSource dataSource = new HikariDataSource(config);

// In a real application, DataSource lifecycle is managed by DI/container.
// Call dataSource.close() on application shutdown.
```

These values are **illustrative only**. URL, credentials, and timings must be tuned for your deployment, TLS, proxy, network timeouts, and load tests. Never hardcode real passwords in source code or logs.

## 24. Key HikariCP Properties

| Property | Role | Common Mistake |
|---|---|---|
| `maximumPoolSize` | Ceiling of physical connections in the pool | Setting 100 per pod across many pods |
| `minimumIdle` | Target idle count the pool tries to maintain per config | Setting unnecessarily high, holding idle slots |
| `connectionTimeout` | Max time waiting to borrow a connection from pool | Confusing with SQL query timeout |
| `idleTimeout` | Controls retirement of idle connections when allowed | Expecting it to shrink a fixed-size pool immediately |
| `maxLifetime` | Max lifetime of a physical connection in the pool | Setting longer than network/server limits, causing stale connections |
| `keepaliveTime` | Optional check/keepalive for idle connections | Confusing with long-running query timeout |
| `validationTimeout` | Timeout for connection validation | Treating as an HTTP request deadline |
| `leakDetectionThreshold` | Logs warning when a connection is held past threshold | Treating the log as proof of a definite leak |

**Note:** HikariCP recommends a fixed-size pool in many scenarios; `minimumIdle` defaults can make the pool behave close to fixed-size depending on version and configuration. When tuning, understand the distinction between **max** and **min idle** rather than guessing from property names.

## 25. What Does `Connection.close()` Mean With a Pool?

With a connection leased from Hikari:

```java
try (Connection conn = dataSource.getConnection()) {
    // Use conn within required scope.
}
```

`conn.close()` on the pool's connection wrapper **normally returns the lease to the pool** rather than immediately closing the physical TCP socket. The pool decides when physical connections are recreated or retired.

### Dangerous Pattern

```java
Connection conn = dataSource.getConnection();
executeBusinessLogic(conn);
// Forgets close() on exception paths.
```

Without returning the connection, the pool drains its slots, pending rises, and subsequent requests time out.

### Right Pattern

Use `try-with-resources` or framework transaction management so close/rollback runs on every code path.

## 26. JDBC Transactions and Connection Lifecycle

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (PreparedStatement ps = conn.prepareStatement(
                "UPDATE orders SET status = ? WHERE order_id = ?"
        )) {
            ps.setString(1, "PAID");
            ps.setLong(2, 42L);
            ps.executeUpdate();
        }

        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        conn.rollback();
        throw ex;
    }
}
```

The `orders` table name assumes a real application schema; in a lab, substitute the qualified table name you created earlier. This snippet focuses on **borrow, transaction, commit/rollback, and return**.

### Transaction State Warning

If an application forgets to commit or roll back before returning a connection, reset behavior depends on pool/driver details and should never be relied upon as normal design. Frameworks/pools may clean up, yet business code must manage transaction boundaries explicitly.

Never wrap multi-second external API calls inside an open connection block if no transaction needs to span them.

## 27. Connection Acquisition Timeout Differs From Query Timeout

Example:

```text
Hikari connectionTimeout = 2s
PostgreSQL statement_timeout = 5s
HTTP request deadline = 8s
```

These timeouts apply to different phases:

- **Pool acquisition:** waiting to borrow a connection.
- **Statement/query:** SQL executing; PostgreSQL cancels the statement if exceeded.
- **Request:** total end-to-end processing including queueing, network, and DB.

Never assume an 8-second HTTP deadline is guaranteed just because `statement_timeout` is 5 seconds: a request might wait 2 seconds on the pool, run multiple statements, or suffer network/app processing delays.

### Design a Time Budget

Account for wait times plus non-DB steps. One request might execute three SQL statements taking 5 seconds each, so `statement_timeout=5s` does not bound the whole request to 5 seconds.

## 28. PostgreSQL `statement_timeout`

Inspect:

```sql
SHOW statement_timeout;

SELECT current_setting('statement_timeout');
```

In a practice transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';

SELECT pg_sleep(3);
-- Expected to cancel due to statement_timeout.

ROLLBACK;
```

### Meaning

`statement_timeout` bounds statement execution time per PostgreSQL and protocol rules; when canceled, the active transaction enters an error state and requires rollback.

Set timeouts **per workload/endpoint**, avoiding a tiny limit that breaks legitimate migrations/analytics or an overly huge limit on latency-sensitive APIs.

## 29. `lock_timeout` and `idle_in_transaction_session_timeout`

`lock_timeout` limits waiting to acquire **a lock**, not total query duration.

`idle_in_transaction_session_timeout` terminates sessions left in `idle in transaction` too long; it is a safety net when applications forget to finish transactions.

Example:

```sql
BEGIN;
SET LOCAL lock_timeout = '750ms';
SET LOCAL statement_timeout = '4s';

-- Subsequent SQL obeys both limits in this transaction.
SELECT 1;

COMMIT;
```

### Avoid Conflicting Settings

If `lock_timeout` is greater than or equal to `statement_timeout`, it may have no practical effect because `statement_timeout` fires first. Also, if `idle_in_transaction_session_timeout` kills a client-held session, the pool and application must handle the broken connection cleanly.

## 30. Connection Lifetime and Network Idle Timeouts

A physical connection can be closed by:

- PostgreSQL backend/server restart.
- Network device, load balancer, or firewall.
- Managed proxy or pooler idle/server lifetime limits.
- TLS or network disruptions.
- Pool retirement policies.

### Hikari `maxLifetime`

When configuring `maxLifetime`, set it **shorter than any known upstream lifetime limit**, with a safety margin, so the pool retires and recreates connections proactively.

Setting `maxLifetime` too low causes connection churn, extra TLS/authentication handshakes, and wasted CPU. Do not pick a tiny value out of a vague belief that "reconnecting constantly is safer".

### Keepalive

Keepalives and validation can detect dead idle connections, yet cannot rescue an in-flight transaction during failover. Depending on network and driver, TCP keepalives, pool keepalives, and server-side timeouts must be coordinated across layers.

## 31. PgBouncer: Database-Side Pooler

HikariCP manages connections inside the **Java process**. PgBouncer is a **connection pooler/proxy** commonly placed between clients and PostgreSQL:

```text
       API pod A           API pod B           Batch workers
         Hikari              Hikari               Hikari
            \                  |                    /
             \                 |                   /
              └───────────── PgBouncer ──────────┘
                               |
                       smaller server pool
                               |
                           PostgreSQL
```

If 200 client connections connect to PgBouncer while at most 30 concurrent server transactions run at once, **transaction pooling** can serve them using far fewer server connections, provided transactions are short and workloads are compatible.

### Important

PgBouncer itself must also be sized. If you deploy **multiple PgBouncer instances**, each instance maintains its own server connections. Never treat `default_pool_size=20` as "20 server connections across the whole cluster" when five pooler nodes and multiple database/user combinations exist.

## 32. Client Pools and Server Pools Differ

| Layer | Common Limit | What It Measures |
|---|---|---|
| HikariCP pod | `maximumPoolSize` | Physical connections from that pod to its target endpoint |
| PgBouncer | `max_client_conn` | Client connections accepted by PgBouncer |
| PgBouncer | `default_pool_size` and per-db/user limits | Server connections for a corresponding pool |
| PostgreSQL | `max_connections` and reserved slots | Total open server sessions |

**`max_client_conn` is not PostgreSQL `max_connections`.** PgBouncer can accept many client connections while multiplexing them over fewer server connections, depending on pooling mode.

### When Multiplexing Gives No Benefit

If applications open long transactions and hold server connections for tens of seconds, PgBouncer transaction pooling cannot release backends mid-transaction. Server connections stay pinned and client waits climb.

## 33. PgBouncer's Three Pooling Modes

| Pool Mode | When Is a Server Connection Bound to a Client? | Compatibility |
|---|---|---|
| `session` | For the entire client session | Compatible with more session features; poor multiplexing |
| `transaction` | For the duration of one transaction; released on transaction boundary | Good multiplexing for short transactions; restricts session state |
| `statement` | Per individual statement | Heavily restricted; unsuitable for multi-statement transactions |

### Session Pooling

Closely mirrors direct PostgreSQL connections. Features tied to session affinity—such as temporary tables, session settings, session-level advisory locks, and `LISTEN`/`NOTIFY`—may require this mode or a direct connection.

### Transaction Pooling

A client may run transaction 1 on server backend X and transaction 2 on backend Y. **Never assume session state survives** across transaction boundaries.

### Statement Pooling

Server connections are reassigned between statements. Because it does not hold a backend across arbitrary multi-statement transactions, this mode is very restrictive; never pick it by default just because it sounds "more optimal".

## 34. Example PgBouncer Configuration

Below is an **illustrative configuration**, not a complete production file:

```ini
[databases]
ordersdb = host=postgres.internal port=5432 dbname=ordersdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 500
default_pool_size = 30
reserve_pool_size = 5
reserve_pool_timeout = 5
server_idle_timeout = 600
```

### Configuration Warnings

- Values, auth sources, TLS, and file paths must be adapted to your infrastructure.
- `default_pool_size` typically applies per **pool key** (database/user depending on config), not total server connections across the entire PgBouncer instance.
- `reserve_pool_size` can open extra server connections when wait conditions trigger; **include it in your budget**.
- If running two PgBouncer instances, each can maintain its own server pools.
- `max_client_conn` also affects file descriptors and pooler memory.

Never copy this snippet into production without TLS, private networking, strict auth file permissions, and high-availability policies.

## 35. Calculating Total PgBouncer Server Connections

Suppose two PgBouncer instances each serve:

- Two database/user pools.
- Each pool has `default_pool_size = 20`.
- `reserve_pool_size = 5` can activate under load.

Preliminary design ceiling:

\[
2 \times 2 \times (20+5) = 100
\]

This is a **hypothetical ceiling** if both pool keys on both PgBouncer instances expand to maximum simultaneously. Per-database/user limits and other settings can cap effective usage.

### Very Common Mistake

Setting `default_pool_size = 20` on each pooler and claiming "PostgreSQL only ever sees 20 connections." When multiple user/database pools, pooler nodes, reserve slots, and direct clients coexist, total server sessions can be far higher.

## 36. Transaction Pooling and Prepared Statements

Many JDBC drivers use **server-side prepared statements** to cut parse/plan overhead after repeated runs. Under transaction pooling, the next transaction may execute on a **different PostgreSQL backend** where the earlier session's prepared statement does not exist.

### Distinguish Two Kinds

- **SQL-level `PREPARE name AS ...`**: session-bound backend state, normally incompatible with relying on cross-transaction persistence in PgBouncer transaction pooling.
- **Protocol-level named prepared statements**: newer PgBouncer versions can **track/map** them when configured appropriately (e.g. `max_prepared_statements`); verify exact version and feature support.

### Avoid Outdated Claims Like "Prepared Statements Never Work"

With modern PgBouncer, protocol-level prepared statements can work in transaction mode when tracking support is enabled. However, that **does not** make all session features compatible; SQL `PREPARE`, temporary tables, session locks, and `LISTEN` still have different semantics.

### Integration Testing

Verify your pgJDBC version, PgBouncer version, and preparation settings, and test:

1. One connection running repeated prepared queries.
2. Reconnects and failovers.
3. Switching backends between transactions.
4. Schema migrations invalidating plans.
5. Heavy concurrency and error/retry paths.

## 37. Transaction Pooling and Session State

Features requiring special attention:

| Feature | Issue Under Transaction Pooling |
|---|---|
| Session `SET` / session GUCs | Setting may be gone on the next transaction's backend |
| Temporary tables | Live in backend session; not guaranteed across transactions |
| Session-level advisory locks | Bound to backend; cannot safely span transactions |
| `LISTEN`/`NOTIFY` subscriptions | `LISTEN` is session state; requires session affinity |
| Open cursors held past commit | Cannot assume the same backend on the next transaction |
| SQL `PREPARE` | Statement name belongs to backend session |
| Session-level role/`search_path` | Requires clear policy to prevent inconsistent state |

### An Important Distinction

**Transaction-scoped state** such as `SET LOCAL` inside a single transaction works with transaction pooling when all related SQL executes inside that same transaction. **Session-scoped state** must never be assumed to persist between transactions.

## 38. `SET LOCAL` and Tenant Context

If an application uses a custom setting for RLS or auditing:

```sql
BEGIN;

SELECT set_config(
    'app.tenant_id',
    '10',
    true
);

SELECT *
FROM public.orders
WHERE tenant_id = 10;

COMMIT;
```

Passing `true` to `set_config` scopes it **local to the current transaction**.

### Why Is `BEGIN` Required?

If autocommit is enabled and `set_config(..., true)` runs as a standalone statement, its transaction finishes immediately; the local setting will not survive into the following `SELECT`. This breaks both under PgBouncer transaction pooling and on direct connections.

### Authorization

An `app.tenant_id` settable by untrusted code **does not prove an authenticated tenant**. RLS and authorization must rest on trusted authority. Custom GUCs are not anti-spoofing signatures.

## 39. `LISTEN`/`NOTIFY` and Pool Modes

A service receiving PostgreSQL notifications typically runs:

```sql
LISTEN order_events;
```

This registers the listener on **one backend session**. If PgBouncer transaction pooling swaps backends between transactions, the listener no longer sits on a stable session as expected.

### Recommendation

Use a **dedicated direct connection or session pooling** for long-lived listeners. Never lease a connection from the general request pool indefinitely just to `LISTEN` without budgeting capacity.

Listeners must also reconnect and resubscribe after failover and handle missed notifications; `LISTEN`/`NOTIFY` is not a durable message queue with guaranteed delivery.

## 40. Temporary Tables and Session Affinity

If a workflow:

```sql
CREATE TEMP TABLE tmp_ids (...);
COMMIT;

SELECT * FROM tmp_ids;
```

expects the temporary table to survive on the **same PostgreSQL backend** in a later transaction, it is incompatible with PgBouncer transaction mode.

### Alternatives

- Keep the entire workflow inside one transaction when semantics allow (mind `ON COMMIT` behavior).
- Use a regular staging table keyed by `request_id`/`batch_id` with explicit cleanup.
- Use session pooling or direct connections for workflows genuinely requiring session temp state.
- Refactor queries to use CTEs, arrays, `unnest`, or set-based SQL.

Do not hold transactions open for minutes just for a temp table if doing so starves the server pooler.

## 41. Advisory Locks and Pooling

PostgreSQL offers **session-level advisory locks** and **transaction-level advisory locks**.

Session-level locks belong to the backend session and are unsafe when clients can switch backends after each transaction.

Transaction-level advisory locks are bound to the transaction, fitting transaction pooling **when lock acquisition and protected work occur in the same transaction**.

### Caution

Advisory locks do not guarantee correctness if another write path modifies the same resource without taking the lock. Ensure consistent lock keys, sound transaction boundaries, and timeout/deadlock handling.

Never acquire a session-level `pg_advisory_lock` through a transaction pool assuming the client can reliably unlock it in a subsequent transaction.

## 42. HikariCP in Front of PgBouncer: Two Queues

An architecture may look like:

```text
HTTP requests
   ↓
Hikari pending queue
   ↓
Hikari connection to PgBouncer
   ↓
PgBouncer client wait queue
   ↓
PgBouncer server connection
   ↓
PostgreSQL locks / CPU / I/O queue
```

If pending rises in Hikari, the server is not automatically short on connections: all Hikari connections might be stalled in PgBouncer's client wait queue.

### Monitor All Layers Together

- Hikari `active / idle / pending`.
- Hikari acquisition latency.
- PgBouncer client waiters and available server connections.
- PostgreSQL active/idle/lock states.
- SQL latency and transaction hold times.

Queue growth at one layer is often a **symptom** of congestion deeper downstream, not the root cause.

## 43. Should You Remove Hikari When Using PgBouncer?

There is no single universal answer.

Keeping an application pool offers benefits:

- Caps per-pod concurrency.
- Reuses connections to PgBouncer.
- Integrates cleanly with JDBC `DataSource`/transactions.
- Exposes acquisition metrics.

Yet two pooling layers can also:

- Increase total idle client connections.
- Add extra timeout and queueing layers.
- Decouple app-side connections from PostgreSQL backend sessions.

### Key Distinction

With PgBouncer transaction pooling, **Hikari `maximumPoolSize`** limits connections **to PgBouncer**, not directly the number of PostgreSQL backends the system opens. The server connection budget is governed mainly by PgBouncer pool settings and any direct connections.

Still, Hikari `maximumPoolSize` bounds concurrent work from each pod and must be sized for the workload.

## 44. Inspecting PgBouncer via the Admin Console

On a connection to the PgBouncer administrative database (with proper privileges):

```sql
SHOW POOLS;
SHOW STATS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW CONFIG;
```

These commands belong to the **PgBouncer admin console**, not regular PostgreSQL database SQL.

### What to Check in `SHOW POOLS`

Depending on version, columns cover:

- Client active/waiting counts.
- Server active/idle/used counts.
- Pool database/user.
- Wait-time statistics.

Exact column names and metrics vary by PgBouncer version; check your version's output schema.

### Diagnostic Clue

If client waiting is high while PostgreSQL CPU is low, PgBouncer's server pool may be too small, server connections may be pinned by long transactions, or one pool key may be throttled.

## 45. Inspecting Connections in PostgreSQL

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY
    datname, usename, application_name, state
ORDER BY sessions DESC, datname, application_name;
```

### Why `application_name` Matters

It distinguishes:

- Primary API.
- Reporting service.
- Migration tool.
- BI/dashboards.
- PgBouncer backend connections.

With transaction pooling, PostgreSQL sees PgBouncer's server-side connections; how `application_name` propagates depends on configuration. Never assume every PostgreSQL session maps 1:1 to a specific HTTP pod.

## 46. Sessions Holding Transactions Too Long

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    now() - state_change AS time_in_state,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
  AND xact_start IS NOT NULL
ORDER BY transaction_age DESC NULLS LAST
LIMIT 30;
```

### Reading the Output

`idle in transaction` with a large `transaction_age` demands investigation. Open transactions hold locks and snapshots, hurting vacuum and resource availability, and extend connection hold times.

### Be Careful When Diagnosing

Never blindly `pg_terminate_backend` production sessions just because they top the list. Verify owner, job type, migrations/backups, business transaction, and rollback blast radius first.

A long-running `active` query may be blocked on a lock rather than burning CPU continuously.

## 47. Observing Wait Events

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

Common categories:

- `Lock`: waiting on locks; enlarging the pool often just increases waiters.
- `IO`: waiting on I/O events per server version.
- `Client`: waiting on client/network read or write.
- `LWLock`: waiting on internal lightweight locks.

### Do Not Equate `active` With Using CPU

A backend with `state='active'` can simultaneously have `wait_event_type='Lock'`. Never conclude from 50 active sessions that the database is utilizing 50 CPU cores.

## 48. `pg_stat_database`: Connections and Transaction Activity

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    deadlocks,
    temp_files,
    temp_bytes
FROM pg_catalog.pg_stat_database
WHERE datname = current_database();
```

`numbackends` shows the current backend count connected to that database per view stats; the other counters are typically cumulative since the last stats reset.

### Do Not Mistake Cumulative Counters for TPS

To compute transactions/second, measure the **delta between two timestamps** divided by the elapsed interval, checking whether stats were reset. Never quote raw `xact_commit` as "current TPS".

## 49. Connection Pool Metrics to Export

| Metric | Meaning |
|---|---|
| Pool active | Connections currently borrowed |
| Pool idle | Free connections available |
| Pool total | Active + idle at a given instant |
| Pool pending/waiting | Threads/requests waiting for a connection |
| Acquisition time p50/p95/p99 | Time spent waiting to borrow a connection |
| Connection usage/hold time p50/p95/p99 | Time from borrow to return |
| Acquisition timeout count | Requests failing to obtain a connection in time |
| Connection creation/error count | Churn, DB auth, or network issues |
| Pool capacity/max | Configured ceiling |
| JDBC transaction duration | Whether connections are held too long |

In Spring Boot/Micrometer, metric names follow instrumentation/version conventions, such as `hikaricp.connections.*`. Confirm exact metric names and labels in your deployment before hardcoding alert rules.

### Combining Metrics

**High pending + low DB CPU** can point to an undersized pool, connection leaks, or waiting in PgBouncer/locks.

**High pending + high DB CPU + slow SQL** points to database saturation; raising pool size is rarely the right first move.

## 50. Leak Detection: Proof or Signal?

HikariCP offers `leakDetectionThreshold` to log a warning when a connection is borrowed longer than the threshold, when enabled.

However, a legitimate long-running transaction can trigger a **false positive**. Conversely, a real leak shorter than the initial threshold may not log immediately.

### Investigation Workflow

1. Inspect the borrow stack trace and hold duration.
2. Find code paths missing `try-with-resources` or rollback.
3. Check for HTTP/network calls inside transactions.
4. Check streaming `ResultSet`s, cursors, and lazy ORM loading.
5. Cross-reference `pg_stat_activity`, `xact_start`, and lock waits.
6. Adjust the threshold only after understanding the workload.

**Leak detection logs do not replace resource management** such as `try-with-resources`.

## 51. Connection Leases Can Stretch Even When SQL Is Fast

An anti-pattern:

```java
try (Connection conn = dataSource.getConnection()) {
    beginTransaction(conn);
    updateRow(conn);
    callSlowPaymentGateway();  // e.g., 4-second external network call.
    commit(conn);
}
```

The `updateRow` SQL may take 10 ms, yet the connection stays pinned for 4 seconds waiting on the payment gateway while holding locks.

### Design Direction

- Shrink transaction scope.
- Move external calls out of DB transactions whenever business rules allow.
- Use sagas, outboxes, and idempotency for multi-system workflows.
- Open transactions only when actually needed.
- Avoid network calls inside lock-holding critical sections whenever possible.

Multi-system financial flows require deliberate consistency design; never split transactions carelessly in ways that break business atomicity without compensation.

## 52. ORMs and Transactions Opened Too Early

In Spring/Hibernate:

```java
@Transactional
public Response handle(Request req) {
    validate(req);
    callExternalService();
    repository.save(...);
    renderLargeResponse();
    return response;
}
```

Not every framework checks out a physical connection immediately upon entering the method; acquisition timing depends on transaction manager, ORM, and connection acquisition mode. Still, once acquired and held until transaction end, external calls and response rendering inflate hold time significantly.

### Better Approach

Place transaction boundaries **strictly around the DB work needing atomicity**, measure actual connection checkout durations, and verify whether lazy loading triggers late SQL during view rendering.

### Open Session in View

Some web ORM setups keep the persistence context open through rendering, which can fire unexpected DB queries outside intended boundaries. Measure and set explicit policies to prevent leaks and N+1 queries, without assuming every persistence session continuously holds a physical connection.

## 53. Should Long-Running Analytics Use a Separate Pool?

A multi-minute BI query has very different needs from a 50 ms OLTP API.

Sharing one pool risks:

- A few analytics tasks pinning all connections for minutes.
- Short OLTP API requests blocking on the pool.
- Tail latency (p99) surging dramatically.

### Possible Solutions

- Dedicated pool and role for reporting with low concurrency limits.
- Read replica for read-only workloads when replication lag is acceptable.
- Background queues for report generation.
- Dedicated `statement_timeout`.
- Materialized views or pre-aggregation per requirements.

### Not Free Capacity

Splitting into two pools creates no extra compute on the same PostgreSQL primary. Both still count toward the **server connection budget** and share CPU and I/O.

## 54. Connection Storms After Deploy or Restart

Suppose 30 pods start simultaneously, each trying to open 20 idle connections:

\[
30 \times 20 = 600
\]

If PostgreSQL only permits ~150 application sessions, many connections fail immediately during deployment warm-up.

### Countermeasures

- Budget against max replicas **plus rolling overlap** (old + new pods).
- Lower `minimumIdle` or warm-up concurrency where appropriate.
- Add jitter and backoff on reconnects; avoid synchronized retry waves.
- Configure startup/readiness probes not to trigger connection storms.
- Use PgBouncer server pooling when suitable.
- Reserve connection headroom for jobs/migrations running during deploys.

### Easy-to-Miss Detail

During a rolling deployment, **new pods boot before old pods terminate**. If your budget only fits 20 steady-state pods, rollout overlap will exceed the connection limit.

## 55. Autoscaling and Database Limits

An autoscaler triggered by CPU or HTTP queues adds pods as traffic grows. Yet if PostgreSQL is the bottleneck, adding pods:

1. Increases total pool max.
2. Increases concurrent queries hitting the DB.
3. Slows the DB down further.
4. Slows requests down further.
5. Causes the autoscaler to add even more pods.

This is a **destructive feedback loop**.

### Principles

- Budget against `maxReplicas`.
- Enforce global concurrency/admission controls.
- Scale pool size alongside replica scaling policy, or cap via a pooler's server pool.
- Monitor database saturation alongside HTTP service metrics.
- Never treat autoscaling as a substitute for SQL, index, and transaction tuning.

Adding application replicas adds Java CPU, not throughput on a saturated PostgreSQL primary.

## 56. Choosing Pool Size via Load Testing

A practical workflow:

1. **Characterize the workload:** read/write ratio, queries per request, transaction duration, payload size, tenant mix.
2. **Capture a baseline:** app metrics, pool metrics, `pg_stat_activity`, CPU, memory, I/O, lock waits.
3. **Establish the budget:** `max_connections`, reserved slots, other pools, max replicas, rollout overlap.
4. **Pick candidates:** e.g., `maximumPoolSize = 4, 8, 12, 16, 24`.
5. **Generate representative load:** warm-up, steady state, bursts, long-tail queries, and background jobs.
6. **Measure against SLOs:** successful throughput, p95/p99 latency, timeouts, errors, DB saturation.
7. **Select the balanced operating point:** avoid maxing out connections or CPU.
8. **Test failures:** DB restart, PgBouncer unavailability, network loss, concurrent deploys.
9. **Define alerts and rollback criteria:** if latency, timeouts, or DB load breach thresholds.

### Never Size Using `SELECT 1` Alone

`SELECT 1` tests connectivity; it does not represent real JOINs, index scans, writes, lock contention, or row volumes. Benchmarking pools with trivial SQL selects oversized pools that collapse under real production data.

## 57. Hypothetical Benchmark Result Table

Suppose an API has an SLO of p95 ≤ 150 ms. The table below contains **hypothetical numbers for practicing decision-making**, not a real PostgreSQL benchmark:

| Pool/Pod | Successful req/s | API p95 | DB CPU | Pool Pending |
|---:|---:|---:|---:|---|
| 4 | 400 | 180ms | 45% | High |
| 8 | 650 | 95ms | 75% | Low |
| 12 | 700 | 100ms | 90% | Low |
| 24 | 680 | 260ms | 100% | Medium |

### Analysis

- Pool 4 misses the SLO while DB utilization is modest: the app lacks sufficient concurrency.
- Pool 8 meets latency well with solid throughput and healthy DB headroom.
- Pool 12 nudges throughput slightly higher yet pushes DB CPU to 90%, requiring burst-safety evaluation.
- Pool 24 degrades both CPU and latency; adding connections hurts throughput.

If target peak traffic is 600 req/s, pool 8 is likely safer than pool 12. If sustained 700 req/s is required, evaluate burst/failover headroom and consider SQL tuning, DB scaling, or workload adjustments.

### Do Not Treat "90% DB CPU" as an Absolute Threshold

Acceptable CPU depends on SLOs, I/O, headroom, and contention. For systems needing burst and failover tolerance, 90% sustained CPU may be dangerously tight, yet no universal percentage fits every workload.

## 58. A Repeatable Sizing Methodology

Hold constant:

- Database instance CPU, RAM, storage, and configuration.
- Data volume and tenant skew.
- App replica count and HTTP worker settings.
- SQL and index definitions.
- Request mix and arrival pattern.
- Network path and PgBouncer settings.

Vary **only pool size** one step at a time and record:

```text
throughput, successful/failed requests
request p50/p95/p99
pool acquire p50/p95/p99
pool lease/hold p50/p95/p99
pool active/idle/pending
DB active sessions/CPU/IO/locks
timeouts, WAL, transaction rollbacks
```

### Warm-Up

Pool initialization, Java JIT, caches, query plan caches, and OS page cache skew initial intervals. Allow proper warm-up before comparing steady-state runs—while **also testing cold-start behavior** if services scale or restart frequently.

### Reproducibility

Run multiple trials and report variance. If two candidates differ by 2% in throughput while measurement noise is 10%, you cannot declare a winner yet.

## 59. Verify the Load Generator Is Not the Bottleneck

An underpowered load generator may fail to drive enough traffic to saturate the app or database. Pool sizes 8 and 24 will look identical simply because demand never exceeded 8 connections.

### Check

- Load generator CPU and network.
- Actual request arrivals vs. target rate.
- Client-side request timeouts/retries.
- HTTP client connection reuse.
- Load tool error handling and backpressure.

A benchmark throttled by the **load generator** proves nothing about pool or database capacity.

## 60. Open-Loop vs. Closed-Loop Load Generation

Two request generation models:

- **Closed-loop:** a fixed set of virtual clients sends the next request only after the prior one completes.
- **Open-loop:** requests arrive at a target arrival rate regardless of response latency (up to tool limits).

When the system slows down, closed-loop tools automatically throttle arrivals, making peak behavior look calmer than reality. Open-loop tests expose queueing and timeouts under true arrival pressure, though they require an adequately provisioned generator.

### Implications for Sizing

To size `maximumPoolSize` for bursty APIs, model realistic arrival patterns instead of only "100 concurrent users" with artificial think times.

## 61. Pool Exhaustion and Backlog

Suppose Hikari has 12 connections:

```text
pool active = 12
pool idle = 0
pool pending = 45
connection acquisition p99 = 1900ms
connectionTimeout = 2000ms
```

This shows the application is **waiting to acquire connections**, yet by itself does not tell you whether to enlarge the pool.

### Two Possibilities

**A. DB CPU is low, queries are fast, high request concurrency:** the pool may simply be undersized within server budget.

**B. DB CPU is high / heavy lock waits / long connection holds:** enlarging the pool lets even more queries pile into the DB and worsens latency.

Always pair pool metrics with `pg_stat_activity` and DB resource metrics before acting.

## 62. Measure Wait Time and Hold Time Separately

A request might break down as:

```text
200 ms waiting for connection
 50 ms executing SQL
 10 ms processing results inside transaction
---------------------------------------------
260 ms DB-related portion
```

If you only measure `SQL duration = 50 ms`, you miss the 200 ms pool wait, leaving API p95 terrible despite "fast queries".

### Measure Exact Boundaries

- Wait before `getConnection()` returns.
- Hold from borrow until `close()`/return.
- Query execution and lock wait times.
- Total request duration.

Never call `pool active time` "query time". Especially with ORMs, a connection can be leased while no SQL runs for part of the time.

## 63. Prioritize Reducing Connection Hold Time

Before enlarging the pool, consider:

- Checking out connections only right before SQL execution.
- Returning connections before DB-independent CPU or network work.
- Indexing and tuning slow SQL.
- Eliminating N+1 queries and extra round trips.
- Batching SQL where appropriate.
- Reducing lock contention and transaction duration.
- Avoiding long-running streaming on OLTP connections.
- Isolating long analytics onto separate pools.

### Quantitative Illustration

At 200 DB leases/s:

- Mean hold 100 ms → ~20 concurrent leases.
- Mean hold 40 ms → ~8 concurrent leases.

Cutting hold duration more than halves average connection demand **without raising `max_connections`**, assuming constant throughput and Little's Law conditions.

## 64. Query Optimization Before Scaling Connections

A query:

```sql
SELECT *
FROM orders
WHERE customer_id = $1
ORDER BY created_at DESC
LIMIT 50;
```

without a supporting index may scan and sort huge amounts of data.

For a real table/sort, consider an index:

```sql
-- Illustrative only, after verifying schema and workload:
-- CREATE INDEX ix_orders_customer_created
-- ON orders(customer_id, created_at DESC);
```

### Indirect Impact on the Pool

If the query drops from 400 ms to 40 ms, connection hold time and active DB demand fall, allowing a smaller pool to suffice.

Never add an index purely from an example SQL snippet: verify with `EXPLAIN (ANALYZE, BUFFERS)` and measure write overhead on real data. Infrequently run queries may not justify index maintenance costs.

## 65. Read Replicas and Pool Budgeting

Some applications split traffic:

```text
Write pool → PostgreSQL primary
Read pool  → PostgreSQL replica
```

Potential advantages:

- Offloads eligible read-only workloads from the primary.
- Isolates reporting from OLTP writes.
- Allows separate pool budgets per endpoint.

### Do Not Forget Consistency

Read replicas can have **replication lag**, so a request writing to the primary and immediately reading from a replica may miss the fresh write. Design routing, read-your-writes policies, and fallbacks properly.

### Connection Counts

Both primary and each replica have their own limits. An oversized read pool can still exhaust CPU and memory on a replica; replicas are not "free capacity".

## 66. Multi-Tenant Fairness

One heavy tenant sending bursts of requests can monopolize pool leases, causing smaller tenants to time out even when overall load could be shaped fairly.

Mitigations:

- Per-tenant request rate and concurrency limits.
- Fair queueing or admission control.
- Dedicated worker pools for unusually heavy workloads.
- Tiered query limits and timeouts by service class.
- Database or replica isolation when truly warranted.

### Crucial Point

Creating **one Hikari pool per tenant** destroys connection budgets once you have hundreds of tenants. Align pooling with your tenancy architecture and endpoint count; never spawn per-tenant pools as a default fairness mechanism.

## 67. Common PostgreSQL Errors Under Connection Overload

Distinguish these `SQLSTATE` codes:

| SQLSTATE | Condition |
|---|---|
| `53300` | `too_many_connections` |
| `08001` | `sqlclient_unable_to_establish_sqlconnection` |
| `08006` | `connection_failure` |
| `57P01` | `admin_shutdown` |
| `57014` | `query_canceled` (e.g., `statement_timeout`) |
| `40P01` | `deadlock_detected` |
| `40001` | `serialization_failure` |

### Do Not Retry Every Error Identically

- Connection failure before commit may allow retrying the **entire operation** per idempotency rules.
- Deadlock/serialization failure typically retries the full transaction with bounded backoff.
- Query cancellation due to timeout often indicates slow SQL; immediate blind retries worsen overload.
- `too_many_connections` should trigger backpressure and budget remediation, not a reconnect storm.

Never decide retries from `SQLSTATE` alone without knowing whether the operation might already have committed.

## 68. Unknown Commit Outcome on Connection Loss

A request:

```text
BEGIN
UPDATE account
COMMIT
connection drops before client receives COMMIT result
```

The client cannot conclude "the transaction rolled back" just because it missed the `COMMIT` acknowledgment. The server may have committed right before the socket dropped.

### Retry Implications

For operations such as "debit funds" or "create order", require:

- An idempotency key.
- A unique business constraint.
- A way to look up outcome by request ID.
- Bounded transaction retry policies.

A connection pool can replace a dead socket, **yet cannot resolve ambiguous commit outcomes**.

## 69. Failover: How Must the Pool Recover?

When the PostgreSQL primary switches nodes:

1. Existing physical connections may drop.
2. In-flight transactions fail and must roll back/retry per policy.
3. The connection pool must detect and evict stale connections.
4. DNS/proxy/endpoint routing shifts to the new node.
5. Many clients may reconnect simultaneously.
6. Application readiness should reflect dependency state where appropriate.

### Do Not Assume Hikari Replays SQL Safely

The pool manages connections; it **does not replay** an interrupted business transaction safely. Retries belong at the application layer with proper idempotency, authorization, and transaction semantics.

### Prevent Post-Failover Connection Storms

Backoff with jitter, controlled warm-up, and `maxReplicas` budgeting protect the newly promoted primary.

## 70. Readiness vs. Liveness

In containerized platforms:

- **Liveness**: whether the process is deadlocked/unrecoverable.
- **Readiness**: whether the instance can safely receive traffic right now.

If a readiness probe opens a brand-new PostgreSQL physical connection every second outside the pool or re-initializes the datasource, probes themselves add heavy load.

### Recommendations

- Keep probes cheap, bounded by timeouts, and avoid opening unnecessary new connections.
- Health checks should inspect the existing datasource/pool appropriately.
- Avoid flapping readiness across all pods simultaneously over brief transient DB blips.
- Distinguish a real DB outage from one slow reporting endpoint.

Never equate "PostgreSQL is reachable" with "the app has capacity for current traffic".

## 71. When PostgreSQL Returns `too many connections`

Runbook:

1. Record the timestamp, affected application/service, and `SQLSTATE`.
2. Check `max_connections`, reserved slots, and role/database limits.
3. Group sessions by `application_name` and `usename`.
4. Audit current replicas, rollout overlap, batch jobs, BI, and pool maxes.
5. Compare `idle`, `idle in transaction`, and `active` counts.
6. Inspect PgBouncer pool keys and server connections if present.
7. Look for newly deployed services or accidentally instantiated secondary pools.
8. Apply concurrency reduction, rollout throttling, or backpressure as needed.
9. Increase PostgreSQL limits only after evaluating CPU/RAM and restart impact.
10. Add alerts to catch budget creep before slots run dry.

### Never Terminate Sessions Blindly

`pg_terminate_backend(pid)` rolls back active business transactions, can trigger retry storms, and can interrupt migrations. Use it only after confirming target identity, authority, and blast radius.

## 72. When Pool Pending Is High Yet DB CPU Is Low

Possible causes:

- Pool max is too small for the workload.
- Application holds connections without running SQL.
- Pool leaks or overly long transactions.
- PgBouncer server pool is throttled even though DB CPU is low.
- Connections are failing to establish due to network/auth issues.
- Row-lock contention on hot rows while overall CPU stays idle.
- Client-side thread or queue bottleneck.

### How to Differentiate

Inspect Hikari hold times, leak stack traces, PgBouncer pools, `pg_stat_activity.state`/`wait_event`, lock-waiting transactions, and connection creation errors.

**Low DB CPU alone never proves that raising pool size is safe or helpful.**

## 73. When DB CPU Is High and the Pool Is Not Full

If Hikari shows:

```text
active 6 / max 20
pending 0
```

while PostgreSQL CPU hits 100%, just six concurrent queries are saturating the server.

### Investigation Steps

- Top queries and execution plans.
- Index scans vs. sequential scans.
- CPU-heavy operators: sorts, hashes, JSON processing.
- N+1 SQL call patterns.
- Autovacuum or maintenance contention if relevant.
- VM/container CPU quotas or throttling.

Bumping the pool from 20 to 40 will not solve this; it can make things worse if load grows.

## 74. When Hikari Reports a Connection Leak

Runbook:

1. Inspect logs for leak stack traces.
2. Check connection lease durations.
3. Audit code paths missing `try-with-resources`.
4. Check for transactions started before external calls.
5. Check for unclosed `ResultSet`/`Statement`/cursors.
6. Correlate with `pg_stat_activity` `idle in transaction` and locks.
7. Reproduce with integration tests and injected dependency failures.
8. Fix the resource lifecycle—do not merely raise `maximumPoolSize`.

### False-Positive Warning

A legitimate report holding a connection for 2 minutes while `leakDetectionThreshold` is 30 seconds will log a "leak" warning. Tune thresholds thoughtfully and separate job types.

## 75. Using Retry/Backoff When Pools Congest

Without retries, transient errors fail; yet unbounded or immediate retries **amplify** overload.

### Retry Design

- Retry **only eligible errors**; never retry validation or authorization errors.
- Enforce attempt limits and an overall deadline.
- Use exponential backoff with jitter.
- Use circuit breakers / open states during dependency outages.
- Require idempotency keys on writes to prevent double execution.
- Shed load / reduce request concurrency when the database is saturated.

### Dangerous Example

1000 requests hit a pool timeout and each retries 5 times immediately: the system receives 5000 extra attempts in seconds. The moment the DB recovers, the storm knocks it back over and prolongs the outage.

## 76. Circuit Breakers and Admission Control

A service can bound how many requests enter the database-using path:

```text
Incoming requests
        │
        ▼
  admission / bulkhead
     ├── admitted → pool → PostgreSQL
     └── rejected/queued briefly → controlled error
```

This applies **backpressure** before thousands of requests pile up behind the pool.

### Picking the Limit

Do not set admission concurrency vastly higher than what the DB tier can finish if your goal is protecting latency. Test:

- Short bursts.
- Sustained overload.
- DB failover.
- One noisy tenant.
- Long transactions and lock contention.

Returning a fast, controlled overload error is often far healthier than letting thousands of HTTP threads block until they all time out together.

## 77. Budgeting During Rolling Deployments

Suppose steady state is:

```text
12 pods × 8 connections = 96
```

A deployment with `maxSurge=25%` can temporarily add 3 pods:

```text
15 pods × 8 connections = 120
```

If the API budget is 100 server connections, steady state passes while a rollout exhausts slots.

### Solutions

- Tune `maxSurge`/`maxUnavailable` within connection capacity.
- Size per-pod pool max against surge replica count.
- Avoid warming up all connections too aggressively on boot.
- Use a PgBouncer server pool hard cap where architecturally appropriate.
- Implement graceful shutdown to drain requests and transactions.

Sizing for **steady replicas** while forgetting surge overlap is one of the most common mistakes in Kubernetes deployments.

## 78. Startup and Graceful Shutdown

When a pod shuts down:

1. Stop accepting new requests.
2. Allow in-flight requests to complete within a shutdown deadline.
3. Finish or roll back open transactions cleanly.
4. Close the datasource/pool.
5. Ensure server connections are released.

### On Abrupt Termination

PostgreSQL detects the dropped socket and rolls back uncommitted transactions. Still, clients may have been awaiting commit acknowledgments; business logic must handle unknown commit outcomes.

### Avoid Unmanaged Pool Lifecycles

Code that accidentally instantiates a new `HikariDataSource` on every method call leaks pools and opens runaway physical connections. A `DataSource` should normally be a **shared, lifecycle-managed** component, never created per request.

## 79. Spring Boot: Configuring HikariCP

Example `application.yml`:

```yaml
spring:
  datasource:
    hikari:
      pool-name: orders-primary
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 2000
      idle-timeout: 600000
      max-lifetime: 1800000
      validation-timeout: 1000
```

This covers **pool settings only**, omitting JDBC URL, TLS, username, and password. Inject secrets from your deployment's secret manager, environment, or credential provider rather than committing them to Git.

### Sizing Against Resource Budgets

With 5 replicas and one `DataSource` per pod, `maximum-pool-size = 12` yields an application-side ceiling of 60 connections. Against direct PostgreSQL, that is also the physical connection upper bound from those pools; behind PgBouncer transaction pooling, PostgreSQL backend count is governed by PgBouncer pool settings.

### Watch Out for Milliseconds

Hikari durations in code and Spring properties above are in **milliseconds**. `connection-timeout: 2000` means 2 seconds, not 2000 seconds.

## 80. `ApplicationName` for Per-Service Visibility

Configuring PostgreSQL JDBC:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://db.internal:5432/ordersdb");
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));
config.addDataSourceProperty("ApplicationName", "orders-api");
config.setMaximumPoolSize(12);
```

In PostgreSQL:

```sql
SELECT
    application_name,
    count(*) AS session_count
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name
ORDER BY session_count DESC;
```

### With PgBouncer

`ApplicationName` through a pooler follows the pooler's connection negotiation rules. When multiplexing transactions, **server connections do not necessarily map 1:1 to specific pods**. Pair PgBouncer client metrics with application tracing instead of trying to count pods from `pg_stat_activity.application_name`.

## 81. Securing Credentials and TLS

A pool reuses credentials across many sessions. If credentials leak, attackers can spin up connections, read data, or exhaust slots.

### Measures

- Least-privilege database roles.
- TLS with proper server identity verification, e.g. pgJDBC `sslmode=verify-full` and required trust configuration.
- Secret manager and rotation.
- Never place passwords in source code, logs, or plaintext diagnostics.
- Network policies restricting DB/PgBouncer access strictly to required services.
- Compatible authentication across PgBouncer and PostgreSQL.
- Never make an application role superuser or owner of every table unnecessarily.

### Credential Rotation

Already-authenticated connections can stay open in some situations even after a password changes; pools must retire and reconnect per rollout policy. Never assume rotating a password instantly kills existing sessions.

## 82. Read-Only Workloads and Read-Only Transactions

If a pool serves reporting only:

```sql
BEGIN READ ONLY;
SELECT count(*) FROM some_reporting_table;
COMMIT;
```

`READ ONLY` makes PostgreSQL reject many write operations within that transaction per its semantics, yet does not replace **`GRANT SELECT`** and proper role privileges.

### Why You Need Both

- Role privileges enforce long-term security boundaries.
- Read-only transactions catch accidental write bugs inside a transaction.
- Replica routing offloads the primary, provided lag is acceptable.

Never trust a Java `readOnly=true` flag as an unbypassable security control.

## 83. Role Connection Limits Are Guardrails, Not Capacity Plans

`ALTER ROLE ... CONNECTION LIMIT` helps prevent one role from monopolizing all server slots, yet can reject valid pods if total pool max across replicas exceeds the role limit.

### Example

If `app_user` has limit 30:

```text
4 pods × 12 pool max = 48 potential connections
role connection limit = 30
```

The pool budget and role limit conflict. Some pods acquire full pools while others fail unevenly.

### Alignment

Reconcile `max_connections`, role/database limits, poolers, replicas, surge, batch jobs, and operational headroom in a single coherent budget.

A role connection limit **does not distribute slots evenly across pods**; it is strictly a cumulative cap per role.

## 84. Global Admission Limits vs. Per-Pod Pools

Per-pod `maximumPoolSize` does not automatically enforce **cluster-wide fairness**. Under skewed load balancing, one pod can pile up pending requests while another sits idle.

### Options

- Effective load balancing.
- Horizontal pod sizing aligned with concurrency settings.
- Application-level bulkheads.
- Centralized rate limiting per workload/tenant.
- PgBouncer server pool caps protecting the primary.
- Per-pod distribution monitoring, not just service-wide averages.

### Why Average Metrics Mislead

If 9 of 10 pods have `pending = 0` and 1 pod has `pending = 100`, the average `pending = 10` hides a severe hotspot. Monitor per pod and track tail/max values.

## 85. Budget Example Including Rollout and Jobs

Suppose:

| Component | Value |
|---|---:|
| PostgreSQL `max_connections` | 140 |
| Reserved/priority budget | 5 |
| BI, monitoring, admin | 15 |
| Operational headroom | 20 |
| **Budget for app + batch** | **100** |
| API steady replicas | 8 |
| API max replicas during rollout overlap | 10 |
| Batch jobs max DB connections | 8 |

Therefore:

\[
10P + 8 \le 100
\]

\[
P \le \left\lfloor \frac{92}{10} \right\rfloor = 9
\]

`P = 9` permits up to 90 API connections during surge; plus 8 batch = 98, within the 100 budget.

### Still Not Automatically the Optimum

If PostgreSQL handles 40 active queries optimally, opening 98 server connections **does not let it execute 98 queries efficiently in parallel**. The budget merely prevents hitting slot limits; picking `P = 5`, `7`, or `9` depends on measured latency, throughput, and server behavior.

### Baseline Sanity Check

If the app connects through PgBouncer, update the server-pool budget to count **PgBouncer server connections**, not `10P` as direct PostgreSQL sessions. Still, `10P` remains the number of client connections Hikari opens to the pooler.

## 86. Sizing for Traffic Bursts

Suppose normal traffic is 100 requests/s, with 20-second bursts to 300 requests/s. Mean connection hold is 40 ms and each request takes one DB lease:

```text
Normal:
100 × 0.04 = 4 average leased connections

Burst:
300 × 0.04 = 12 average leased connections
```

### Why 12 Slots Are Not Automatically Enough

- Requests do not arrive uniformly spaced.
- Hold times vary.
- Other jobs/tenants share the system.
- If the DB slows down during the burst, hold time climbs and concurrency demand spikes.
- If the DB saturates, queueing/backpressure is needed rather than unbounded admission.

### Test Recommendation

Run realistic burst shapes; measure pool wait times, p99 latency, error rates, DB CPU/locks, and post-burst recovery time. Pick pool size and queueing policies that satisfy SLOs rather than matching the mean of 12 naively.

## 87. Query Fan-Out Within One Request

A single request might execute:

```text
Query A then Query B then Query C (sequentially)
```

or:

```text
Query A, B, C (in parallel across three connections)
```

With parallel fan-out, one request borrows **multiple connections concurrently**. Multiplying requests/s by one hold time underestimates demand if multi-lease fan-out is ignored.

### What to Measure

- Checkout operations per request.
- Peak concurrent checkouts per request.
- Total connection-seconds per request.
- Transaction boundaries.

Do not spawn unbounded asynchronous JDBC calls expecting the connection pool to sort out fairness automatically.

## 88. Reactive Applications and R2DBC

Reactive apps may use R2DBC or non-JDBC drivers. This **does not remove physical server connection limits**:

- Connections to PostgreSQL/pooler still exist.
- Concurrent DB operations still consume server resources.
- Backpressure and timeouts are still required.
- Transaction scopes must still be managed.

Never rewrite to reactive just to escape `too many connections` thinking database capacity constraints disappear.

### Comparison

Fewer threads can cut **application** memory/thread overhead, yet a single PostgreSQL primary's throughput remains bounded by CPU, I/O, locks, and SQL workload.

## 89. Local Pool Usage Inspection Tool

In HikariCP you can query the MXBean for connection counts:

```java
import com.zaxxer.hikari.HikariPoolMXBean;

HikariPoolMXBean metrics = dataSource.getHikariPoolMXBean();

int active = metrics.getActiveConnections();
int idle = metrics.getIdleConnections();
int total = metrics.getTotalConnections();
int waiting = metrics.getThreadsAwaitingConnection();

System.out.printf(
    "active=%d idle=%d total=%d waiting=%d%n",
    active, idle, total, waiting
);
```

### Does Not Replace Proper Monitoring

This is an in-process point-in-time snapshot, not a p95/p99 histogram or fleet-wide telemetry. Export metrics via Micrometer/Prometheus/OpenTelemetry and secure metrics endpoints appropriately.

## 90. Querying Sessions and Pool Budget From the Server

An administrative query:

```sql
WITH params AS (
    SELECT
        current_setting('max_connections')::integer
            AS max_connections
),
connections AS (
    SELECT
        count(*) FILTER (
            WHERE backend_type = 'client backend'
        ) AS client_backends
    FROM pg_catalog.pg_stat_activity
)
SELECT
    p.max_connections,
    c.client_backends,
    p.max_connections - c.client_backends
        AS arithmetic_difference
FROM params AS p
CROSS JOIN connections AS c;
```

### Reading Caution

`arithmetic_difference` **is not guaranteed free capacity for an application role**: reserved slots, role/database limits, and other client classes still apply. It is only a rough difference between one limit and observed `client backend` sessions.

Track all connection types and provider/pooler metrics when sizing seriously.

## 91. PgBouncer Is Not a Primary Database Replica

PgBouncer is a proxy/pooler—**not a data store**—and does not replicate tables or WAL.

### What PgBouncer Can Help With

- Reducing server connections via multiplexing.
- Queueing clients when server slots are scarce.
- Enforcing per-database/user pool caps.
- Managing connection lifecycles to PostgreSQL.

### What It Cannot Do on Its Own

- Increase PostgreSQL CPU capacity.
- Solve read-after-write replication lag.
- Make in-flight transactions survive HA failover seamlessly.
- Turn session-scoped features into transaction-scoped ones.
- Let cluster-wide connection counts exceed PostgreSQL capacity without consequence.

Multi-instance PgBouncer deployments need proper HA routing and separate server connection budgets; adding a proxy does not grant "unlimited connections".

## 92. Relationship Between Query Plans and Pool Size

A larger pool allows more concurrent queries, which can:

- Increase concurrent memory-consuming sorts and hashes.
- Increase temp-file spills.
- Increase lock contention.
- Increase buffer cache pressure.
- Increase CPU context switching.

**Query plans** are not directly chosen by pool size, yet concurrency alters the runtime environment of plans. A plan that runs fast in isolation can degrade sharply when 50 copies execute together.

### Benchmarks Need Concurrency

Never run `EXPLAIN ANALYZE` on one isolated SQL call and assume 100 concurrent executions keep the same latency. Load test under realistic concurrency alongside plan/statistics inspection and measure contention.

## 93. Case Study: 1 Pod vs. 10 Pods

A service starts with 1 pod, Hikari max = 20:

```text
1 × 20 = 20 potential DB connections
```

After scaling to 10 pods with unchanged config:

```text
10 × 20 = 200 potential DB connections
```

If PostgreSQL `max_connections = 150` with other clients sharing the server, this setup risks exhaustion once pools fill.

### Options

1. Lower per-pod max to stay within budget, then benchmark throughput.
2. Introduce PgBouncer transaction pooling if the workload is compatible.
3. Reduce connection hold time / SQL latency so less concurrency is needed.
4. Offload heavy read workloads to a replica or separate service.
5. Scale database capacity intentionally if resources are truly the bottleneck.

No single change fits all situations; evaluate both **budget and performance**.

## 94. Case Study: Large Pool With Many Idle Connections

Suppose 8 pods, each with pool max 30 and `minimumIdle` 25:

```text
8 × 25 = 200 idle connections potentially maintained
```

Overnight traffic needs only a few queries per second. If connected directly to PostgreSQL, 200 idle backends occupy slots and memory without delivering throughput.

### Remediation

- Re-evaluate `minimumIdle` and fixed-size strategies.
- Consider PgBouncer server pooling.
- Retain enough idle connections for cold-start latency while preserving server headroom.
- Do not set `idleTimeout` expecting a fixed-size pool (`minimumIdle = max`) to shrink automatically.

This does not mean always setting `minimumIdle = 0`. If bursty traffic requires warm connections and TLS/DB startup is expensive, modest idle capacity can be worthwhile.

## 95. Case Study: Connection Timeouts Caused by Locks

Suppose a transaction holds a row lock on `accounts.id = 1` for 45 seconds while many workers try to update the same row.

```text
DB: 15 sessions waiting for row lock
Hikari: active 15, idle 0, pending 30
API: connection acquisition timeout
```

Raising Hikari max from 15 to 40 simply lets 40 sessions wait on the lock without unlocking it any faster.

### Analysis

Check `pg_stat_activity.wait_event_type = 'Lock'`, transaction ages, blocking queries, and business transaction scope. Fix lock duration/ordering, add supporting indexes, and apply proper retry semantics.

**Pool saturation can stem from a lock bottleneck**, not a shortage of physical server connections.

## 96. Case Study: Holding Connections During External API Calls

```text
DB SQL = 20ms
Payment HTTP = 900ms
DB COMMIT = 10ms
Connection lease = 930ms
```

At 100 requests/s:

\[
L \approx 100 \times 0.93 = 93
\]

Needing 93 leased connections on average results from **transaction/lease scope**, not 100 SQL queries/s needing 93 active DB workers.

If architecture allows moving external HTTP outside the connection lease, average leases drop dramatically—provided business idempotency and atomicity are preserved via sagas/outboxes.

Never just bump the pool to 100 while ignoring why connections are held for nearly a second.

## 97. Minimal Sizing Worksheet

Capture these inputs for each environment:

| Input to Collect | Hypothetical Example |
|---|---:|
| PostgreSQL `max_connections` | 120 |
| Reserved/admin/other/headroom | 45 |
| App budget | 75 |
| Max API replicas, including surge | 5 |
| Number of direct-DB pools/pod | 1 |
| Hard upper bound/pod from budget | 15 |
| DB-using request arrival rate | 120/s service-wide |
| Mean DB lease duration | 50ms |
| Little's Law average leases | 6 service-wide |
| Candidate pool sizes | 6, 8, 12, 15 |
| SLO | API p95 under 150ms |
| Acceptance tests | Peak/burst/lock/rollback cases |

### How to Use It

**Step 1:** Budget establishes the hard ceiling so scaling never exceeds server limits.

**Step 2:** Little's Law estimates baseline average active leases.

**Step 3:** Load tests and metrics determine the pool size meeting SLOs without DB saturation.

**Step 4:** Test rollouts and failovers, because tidy steady-state numbers can still fail during transitions.

### Context Note

In the example, 6 average leases is service-wide and does not split evenly across 5 pods at every millisecond. Load balancing, per-pod bursts, and skew govern local pool sizing.

## 98. Commonly Misunderstood Principles

**"One request needs one connection for its whole duration."** False; borrow only when DB access is required.

**"Pool size should equal HTTP thread count."** False; many threads are not using the DB simultaneously.

**"Pool size can equal `max_connections`."** False; account for all services, replicas, and headroom.

**"With 10 pods and max 20 each, there are only 20 DB sessions."** False; direct connections can reach 200.

**"Higher PostgreSQL `max_connections` always yields higher TPS."** False; the server can thrash.

**"`work_mem` is the RAM limit per connection."** False; an executor can run multiple operations and parallel workers.

**"Pool active means queries are burning CPU."** False; connections may be waiting on locks or app logic.

**"Idle connections in a pool are always leaks."** False; idle connections are normal for reuse.

**"Rising pool pending always means raise `maximumPoolSize`."** False; inspect DB saturation, locks, and hold times.

**"Little's Law gives the exact p99 pool size."** False; it uses means in steady state.

**"Multiplying p99 query time by RPS is enough."** False; measure true connection lease durations and arrival variance.

**"Pool timeout is the same as `statement_timeout`."** False; one bounds waiting for a connection, the other cancels a running SQL statement.

**"`SET LOCAL` persists across multiple transactions."** False; it is scoped to the transaction.

**"Session state survives PgBouncer transaction pooling."** False.

**"PgBouncer `default_pool_size=20` means the cluster has exactly 20 server connections."** False; there may be multiple pool keys, pooler nodes, and reserve pools.

**"Raising PgBouncer `max_client_conn` increases PostgreSQL server capacity."** False.

**"Every prepared statement is incompatible with PgBouncer transaction mode."** False across all versions/configs; distinguish protocol-level from SQL `PREPARE`.

**"`LISTEN` works across any pooling mode."** False; it requires session affinity.

**"`Connection.close()` always closes the physical TCP socket."** False with pools and proxies.

**"Hikari leak detection proves code leaked a connection."** False; legitimate long transactions can trigger warnings.

**"On failover, the pool safely replays interrupted transactions."** False; application-level retries and idempotency are required.

**"Raising `max_connections` is the first fix for `53300`."** False; investigate budget and workload first.

**"Read replicas don't need connection budgets."** False; replicas have their own limits.

**"Autoscaling more pods always increases DB throughput."** False; it can trigger an overload feedback loop.

**"With TLS between app and PgBouncer, PgBouncer→PostgreSQL is automatically encrypted."** False; configure TLS per hop.

**"A single `SELECT 1` load test is enough for production sizing."** False; tests must match real workloads.

**"A query that is fast alone stays fast at 100 concurrent runs."** False; contention changes everything.

**"Request failure when `COMMIT` ACK drops means it rolled back."** False; the commit outcome may be unknown.

**"Pool max is the exact number of connections always open."** False; it depends on `minimumIdle`, demand, and lifecycle.

**"A role connection limit splits slots evenly across pods."** False; it is a total cap per role, not a fair scheduler.

## 99. Combined Runbook: Acting on Signals

| Signal | First Question | Investigation / Adjustment Direction |
|---|---|---|
| Pool active=max, pending high, DB CPU low | What are connections doing? | Hold times, locks, pooler waits, leaks |
| Pool active=max, pending high, DB CPU high | Is the DB saturated? | SQL, CPU/I/O, concurrency limits, slow transactions |
| Many `idle in transaction` | Who holds transactions open? | Framework scope, rollback/timeouts, external calls |
| Many `idle` near server limit | Who keeps idle sessions open? | `minimumIdle`, pools per pod, PgBouncer |
| PgBouncer `cl_waiting` high | Which server pool is blocked? | Pool key limits, long transactions, backend health |
| PostgreSQL `SQLSTATE 53300` | Where was budget exceeded? | Replicas, surge, jobs, roles, reserved headroom |
| High CPU/I/O while Hikari active is low | Are queries heavy enough on their own? | `EXPLAIN`, waits, write amplification |
| Timeouts after deploy | Connection storm? | Pool init, rollout overlap, jitter |
| Many JDBC failures after failover | Were old connections dropped? | Endpoint routing, pool eviction, transaction retries |
| Reports starve the whole pool | Are long workloads sharing OLTP pools? | Separate pool/replica/jobs |
| High p99 with low average | Long-tail SQL or hold times? | Histograms, lock waits, traffic skew |
| Hikari leak logs | Truly missing `close()`? | Stack traces, hold duration, ORM transaction scope |

### Decision Discipline

Never tweak `max_connections`, Hikari `maximumPoolSize`, PgBouncer `default_pool_size`, `work_mem`, and `statement_timeout` all at once, leaving yourself unsure what helped or hurt. Change one variable at a time, measure before and after, and keep a rollback path.

## 100. Workflow for Rolling Out a New Pool Configuration

1. Document current settings and sources (app properties, env, PgBouncer, PostgreSQL, managed service).
2. Calculate total connection budget across max replicas, surge, pools, and jobs.
3. Confirm role, database, server, and pooler limits do not conflict.
4. Load test with a representative traffic profile.
5. Select a candidate meeting SLOs with safety headroom.
6. Verify feature compatibility with PgBouncer `pool_mode`.
7. Align timeout ordering and retry budgets, including HTTP deadlines.
8. Verify permissions and TLS on every hop.
9. Deploy via canary with metrics and alerts.
10. Monitor pool pending/acquisition/hold, DB CPU/locks, and error rates.
11. Test restarts, failovers, rollout surge, and batch jobs.
12. If thresholds breach, roll back the configuration rather than raising connection limits blindly.

### A Good Configuration Has Evidence

Operational docs should record:

- `max_connections` and admin-reserved slots.
- Total pool budgets and replica count assumptions.
- Rationale for `maximumPoolSize` (benchmark results).
- SLOs and overload behavior.
- Timeout and retry policies.
- PgBouncer modes and compatibility findings.
- Metrics dashboards, runbooks, and owners.

Whenever the application or workload changes, revisit sizing numbers.

## 101. Practice Exercises

### Exercise 1 — Why Use a Pool?

Explain why opening a new PostgreSQL connection for every HTTP request is costly. Name at least three benefits and three limitations of a connection pool.

### Exercise 2 — Distinguishing Concurrency Types

A service has 150 HTTP requests in flight, Hikari active = 12, and PostgreSQL active queries = 6. Why are the three numbers different?

### Exercise 3 — Observing `max_connections`

Run `SHOW max_connections` and query `pg_settings`. Distinguish the server limit setting from the number of currently open connections.

### Exercise 4 — Reserved Slots

Query `superuser_reserved_connections` and `reserved_connections` (if supported by your version). Why should applications avoid consuming all remaining slots?

### Exercise 5 — Role/Database Limits

Read `rolconnlimit` and `datconnlimit`. Can a role limited to 20 open 30 sessions when the server still has 80 slots free? Explain.

### Exercise 6 — Single-Service Budget

`max_connections = 100`, priority reserve 3, other clients 17, headroom 15. Compute the remaining budget for the API.

### Exercise 7 — Multi-Replica Budget

From Exercise 6, the API has 5 replicas, one pool per pod. Compute the pool-per-pod upper bound under budget and explain why it is not automatically the optimum.

### Exercise 8 — Two-Service Budget

Server app budget is 90. Service A has 4 replicas max 12, Service B has 3 replicas max 10, batch jobs take 8 connections. Does the total exceed the budget?

### Exercise 9 — Rollout Surge

A service runs 8 pods × pool 10. A rolling deployment can temporarily reach 11 pods. Compute peak potential connections and adjust the plan if the budget is 100.

### Exercise 10 — Multiple `DataSource`s

Each pod has a primary pool max 12 and a reporting pool max 8, running 6 pods. Compute maximum direct connections to each endpoint and when both must share the same budget.

### Exercise 11 — Little's Law

120 DB leases/s, mean hold time 50 ms. Compute average leased connections, stating stability conditions and application boundaries.

### Exercise 12 — Reducing Hold Time

Holding 120 leases/s constant, cut mean hold time from 200 ms to 40 ms. Compare average leased connections before and after and the impact on the pool.

### Exercise 13 — Tail Latency

99% of transactions hold a connection for 10 ms and 1% hold for 5 s. Why is the mean alone insufficient to predict p99 acquisition wait?

### Exercise 14 — Undersized Pool

Hikari active = max, pending rising, PostgreSQL CPU low, no lock waits. List what to check before increasing `maximumPoolSize`.

### Exercise 15 — Oversized Pool

Raising Hikari max from 12 to 50 reduces throughput and pegs DB CPU at 100%. Explain the likely mechanism and how to measure it.

### Exercise 16 — Hikari Configuration

Create a `HikariDataSource` with max = 12, minIdle = 4, `connectionTimeout` = 2000 ms, and `maxLifetime` aligned with upstream policy. Ensure the datasource closes on shutdown.

### Exercise 17 — `try-with-resources`

Write a JDBC method that borrows a connection, runs a `SELECT`, and returns the connection on both success and exception paths.

### Exercise 18 — Transaction Lifecycle

Write a JDBC transaction executing two `UPDATE` statements; commit on success, roll back on error, and close the connection on every branch.

### Exercise 19 — Classifying Timeouts

Compare Hikari `connectionTimeout`, PostgreSQL `statement_timeout`, `lock_timeout`, and an HTTP deadline. For a request running three SQL statements, why does per-statement timeout not bound the entire request?

### Exercise 20 — Idle in Transaction

Run a `pg_stat_activity` query filtering for `idle in transaction` and old `xact_start`. List three causes and three operational risks.

### Exercise 21 — PgBouncer Modes

Compare session, transaction, and statement pooling. Which mode should an app with multi-statement transactions and cross-transaction temporary tables choose, or how must its architecture change?

### Exercise 22 — PgBouncer Budget

Three PgBouncer instances, each with two pool keys, `default_pool_size = 15` and `reserve_pool_size = 5`. Compute the total server connection ceiling assuming all pools expand fully.

### Exercise 23 — Prepared Statements

Explain the difference between SQL `PREPARE` and protocol-level prepared statements. Why does compatibility with PgBouncer transaction pooling depend on version and configuration?

### Exercise 24 — Transaction-Local Setting

Inside a transaction, set `app.tenant_id` using `set_config(..., true)` and run a `SELECT`. What happens if `set_config` runs as a standalone autocommit statement expecting the `SELECT` to inherit it?

### Exercise 25 — `LISTEN`/`NOTIFY`

A background listener must maintain `LISTEN` for hours. Why is a Hikari request pool behind PgBouncer transaction pooling not a suitable default design?

### Exercise 26 — Session Advisory Locks

Compare session-level and transaction-level advisory locks through PgBouncer transaction mode. What can happen if you try to unlock in a later transaction on a different backend?

### Exercise 27 — Observing Backends

Write SQL grouping `pg_stat_activity` by `application_name`/`state` and counting sessions. Why is `idle` not automatically a leak?

### Exercise 28 — Wait Events

Query `state`, `wait_event_type`, and `wait_event`. With 20 `active` sessions mostly waiting on `Lock`, will enlarging the pool help?

### Exercise 29 — Cumulative Metrics

Read `pg_stat_database.xact_commit` at two timestamps 60 s apart. Write the TPS calculation and note the risk if statistics reset in between.

### Exercise 30 — Leak Detection

Hikari warns that a connection was held for 90 s. Distinguish a missing-`close()` leak from a legitimate report holding a long cursor; which metrics do you need?

### Exercise 31 — Lock Bottleneck

One transaction holds a row lock for 30 s while 15 writers wait. Explain why Hikari pending grows even with low DB CPU and how to fix it at the SQL/transaction layer.

### Exercise 32 — Load Test

Plan an experiment testing pool sizes 4/8/12/16/24. Specify input workload, warm-up, successful req/s, API p95/p99, acquisition time, hold time, CPU, and lock waits.

### Exercise 33 — Reading a Benchmark Table

Hypothetical test: pool 8 achieves 650 req/s p95 = 95 ms, pool 12 achieves 700 req/s p95 = 100 ms, pool 24 achieves 680 req/s p95 = 260 ms. Given SLO p95 ≤ 150 ms and target 600 req/s, which choice fits best? State what must still be verified.

### Exercise 34 — Connection Storm

30 pods start simultaneously, each opening 20 idle sessions. Calculate how many connections can open and propose how to avoid exhausting slots.

### Exercise 35 — Failover

PostgreSQL primary fails over just as a transaction sends `COMMIT` and the connection drops. Why can't you assume it rolled back? Propose an idempotency design.

### Exercise 36 — Error `SQLSTATE`

Classify `53300`, `08006`, `57014`, `40001`, and `40P01`. Which normally require retrying the whole transaction, and when do retries cause overload?

### Exercise 37 — Read Replica

Design a two-datasource primary/replica setup for a read-heavy app. Budget each server separately and handle read-after-write consistency.

### Exercise 38 — Spring Transaction Scope

A `@Transactional` method calls an HTTP service for 2 s before an `UPDATE`. What should you measure to check whether a physical connection is held for those 2 s, and how do you reduce hold time safely?

### Exercise 39 — Multi-Tenant Fairness

One tenant consumes 80% of DB leases, starving smaller tenants into timeouts. Propose concurrency/rate limiting and explain why one pool per tenant can break connection budgets.

### Exercise 40 — Comprehensive Design

A PostgreSQL platform has:

- `max_connections = 160`, needing 8 special reserved/ops slots, 25 slots for monitoring/BI, and 20 slots headroom.
- API runs 6 pods steady, 9 pods during rollout surge.
- Background workers have a total max pool of 12.
- API receives 240 DB leases/s, mean hold time 45 ms.
- API p95 SLO under 200 ms.
- Some jobs use temp tables, a listener uses `LISTEN`, and OLTP uses prepared statements.
- Previously hit occasional `SQLSTATE 53300` during autoscaling.

Design and explain:

1. Remaining API budget after subtracting reserved/ops, BI, headroom, and background jobs.
2. Hikari pool/pod upper bound with 9-pod surge.
3. Little's Law service-wide average leased connections.
4. Why neither the upper bound nor the average is automatically the optimum.
5. Candidate pool sizes to benchmark and mandatory metrics.
6. When to use PgBouncer transaction pooling and how to size pool keys/server budgets.
7. Handling `LISTEN`, temporary tables, and prepared statements per compatibility.
8. Timeout, retry, idempotency, and network TLS policies.
9. Monitoring `pg_stat_activity`, PgBouncer, Hikari, and long transactions.
10. Canary, rollback, failover, and burst test plan to prevent `too many connections`.

## Conclusion

**A connection pool is a tool for bounding concurrency and reusing connections, not a way to create extra CPU for PostgreSQL.** Good sizing begins by measuring **connection lease time**, arrival rates, pool pending/acquisition latency, and active queries—never by equating pool size with HTTP thread count or online user count.

**`max_connections` is a technical ceiling** alongside reserved slots and role/database limits, not a target to max out. Across multiple replicas, service pools, batch jobs, and rolling deployments, calculate **total openable physical server connections**; autoscaling without budget discipline turns an API bottleneck into a database-wide outage.

**Little's Law `L = λW`** estimates average leased connections when boundaries are measured cleanly in steady state. Yet practical sizing requires measuring p95/p99 latency, lock waits, DB CPU/I/O, throughput, and burst variability. Too small a pool makes requests queue; too large a pool forces PostgreSQL to juggle more contending tasks and can hurt throughput.

**HikariCP** pools inside the Java application; **PgBouncer** can multiplex client sessions onto fewer server connections, especially under transaction pooling. In return, you must understand session state, prepared statements, temp tables, advisory locks, `LISTEN`, and per-pool-key/per-instance server budgets.

Finally, prioritize **shortening connection hold times, optimizing SQL, bounding concurrent queries, coordinating timeouts/retries, and operating by metrics**. A sound pool configuration is not a magic number copied off the internet; it is the product of **connection budgeting, realistic load testing, explicit transaction boundaries, overload protection, and failover/rollout testing**.
