# max_connections, Connection Pooling, and PostgreSQL Memory Pressure

The number of PostgreSQL connections directly affects concurrency capacity, memory consumption, and system stability. Increasing `max_connections` can help applications get past "too many connections" errors, but it also creates more backend processes, shared-memory requirements, and opportunities for multiple queries to allocate memory simultaneously. If the connection count grows faster than CPU, I/O, and RAM capacity, throughput can drop while latency climbs.

An effective design generally limits the number of backend connections PostgreSQL actually has to serve, uses a connection pool to reuse those connections, and throttles waiting requests at the application or pooler layer. The goal is not to achieve a huge connection count; the goal is to maintain enough concurrency to utilize database resources without creating contention and memory pressure.

This lesson, part of the **Resource Tuning** chapter, focuses on:

- Understanding `max_connections`, backend processes, and reserved connection slots.
- Distinguishing client connections, server connections, and pool connections.
- Estimating memory across backends, active queries, and memory-consuming operations.
- Using application pools and PgBouncer to reuse connections.
- Choosing session, transaction, or statement pooling according to application semantics.
- Calculating the total connection budget from replicas, workers, and pool sizes.
- Controlling concurrency, queueing, timeouts, and retry behavior.
- Monitoring connection states, pool wait time, memory, CPU, and I/O.
- Handling connection storms, leaks, idle transactions, and failover.
- Building a measurable sizing and rollout runbook.

> **Principle:** `max_connections` is a resource-protection limit for PostgreSQL. A connection pool determines how many clients share a set of server connections. Actual memory depends on both backend count and currently running operations; `work_mem` is not simply a fixed allocation per connection.

## 1. How Does PostgreSQL Handle Connections?

In PostgreSQL's traditional architecture, each client connection is served by a dedicated server backend process. The backend is responsible for handling protocol, session state, transactions, and queries for that client.

When an application opens a connection:

1. The client establishes a TCP/TLS connection to PostgreSQL.
2. PostgreSQL authenticates the user/database and checks the connection limit.
3. A backend process serves the session.
4. The backend processes statements and transactions within the session.
5. When the client disconnects, the backend exits and session resources are freed.

A session can be in `active`, `idle`, `idle in transaction`, or waiting on a resource. An `idle` backend still occupies a connection slot and holds some resources, even when not executing a query at that moment.

### 1.1. A Connection Does Not Equal a Running Query

An application can hold connections in a pool for reuse. At any instant:

- 500 client connections may exist.
- Only 20 clients may be executing queries.
- The remaining connections are idle or waiting in the pool.
- PostgreSQL still has to manage backends/sessions corresponding to open server connections.

This is why a pooler helps: hundreds or thousands of client connections can be multiplexed across a smaller number of server connections.

### 1.2. Connections and the Process Model

A backend process carries costs for:

- Process metadata and kernel resources.
- Private memory contexts.
- Stack and session state.
- Socket buffers and network state.
- Transaction state, locks, and snapshots when needed.
- Executor memory while queries run.

In addition to client backends, PostgreSQL runs background processes/workers such as checkpointer, background writer, WAL writer, autovacuum workers, logical replication workers, and parallel query workers. They have their own configuration/capacity and should not be confused with client connections opened by applications.

### 1.3. Why Too Many Connections Slow Down the System

As the number of backends grows:

- Context switching and scheduler overhead can increase.
- Many queries can contend for CPU simultaneously.
- Many backends can hit the same storage concurrently.
- Memory contexts and per-query memory can accumulate.
- Lock contention can increase.
- Connection establishment/authentication can create bursts.
- Monitoring and process management must track more sessions.

Adding connections only increases potential concurrency. It does not add CPU cores, RAM bandwidth, disk IOPS, or lock throughput to the database.

## 2. What Is max_connections?

`max_connections` is the parameter limiting the number of concurrent client connections accepted by PostgreSQL. It is configured at the server level.

Check the current value:

```sql
SHOW max_connections;
```

Or:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
```

### 2.1. Changing max_connections

Configuration example:

```conf
max_connections = 250
```

Changing `max_connections` requires restarting PostgreSQL. On managed databases, this is typically done through a parameter group and enters a pending reboot state.

Do not raise the parameter in production merely to clear an error temporarily. First identify which connections occupy slots, why they exist, and whether pools, leaks, or idle transactions are the root cause.

### 2.2. max_connections Is Not a Concurrency Target

Suppose a database is configured with:

```conf
max_connections = 300
```

That does not mean 300 heavy queries should run simultaneously. It only sets a connection ceiling. The appropriate number of active queries can be significantly smaller and must be determined via benchmarks, CPU, storage latency, lock waits, and workload mix.

### 2.3. Reserved Connection Slots

PostgreSQL provides reserved slots so administrators can still connect when connection capacity is nearly exhausted.

- `superuser_reserved_connections`: slots reserved for superusers.
- `reserved_connections`: in PostgreSQL 16 and later, slots reserved for roles granted `pg_use_reserved_connections`.
- Remaining slots are available for ordinary connections.

Check example:

```sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections'
)
ORDER BY name;
```

`reserved_connections` and the predefined role `pg_use_reserved_connections` depend on version; on older servers, this parameter/role may not exist.

Total usable ordinary slots is approximately:

```text
ordinary_slots =
    max_connections
    - superuser_reserved_connections
    - reserved_connections
```

This formula applies when the server supports `reserved_connections`. Reserving administrative slots has clear operational value: if applications consume every slot, a DBA may be unable to log in to diagnose the issue.

### 2.4. Granting Access to Reserved Slots

On supported versions:

```sql
GRANT pg_use_reserved_connections TO ops_role;
```

Grant this privilege only to trusted operational roles. This is an emergency mechanism, not a way to give extra routine capacity to application roles.

### 2.5. Connection Limits per Role and Database

Beyond the server-wide limit, PostgreSQL allows setting connection limits per role or database:

```sql
ALTER ROLE app_service CONNECTION LIMIT 80;
ALTER DATABASE appdb CONNECTION LIMIT 120;
```

`-1` means no separate limit is set. These limits are useful to prevent one role or database from consuming all capacity. They do not replace a pooler and must be counted alongside connections for jobs, migrations, monitoring, and administration.

Check role limits:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_roles
ORDER BY rolname;
```

Check database limits:

```sql
SELECT
    datname,
    datconnlimit
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;
```

## 3. Connection Budgeting Before Raising Limits

Before choosing `max_connections`, inventory every source opening connections to the database.

### 3.1. Common Connection Sources

| Source | Example | What to count |
| --- | --- | --- |
| Web/API replicas | Multiple instances of orders-api | Pool size per instance |
| Worker processes | Queue consumers, schedulers | Worker count × pool per worker |
| Batch/ETL | Import, export, analytics jobs | Peak concurrency and run duration |
| Admin tools | psql, IDEs, dashboards | Separate cap and reserve |
| Migration jobs | Schema deployment | Connections during rollout |
| Monitoring | Exporters, health checks | Persistent sessions vs. frequent reconnects |
| Poolers | PgBouncer server connections | Total pool connections to PostgreSQL |
| Replication clients | Logical subscribers/CDC | WAL sender/replication capacity and client connections |
| Other services | BI, reporting, integrations | Peak load and owner |

The connection budget must account for concurrent deployments, rolling updates, autoscaling, and failovers. If you normally run 10 replicas but a rollout temporarily runs 15 replicas, total pool demand can jump 50%.

### 3.2. Total Pool Connections Formula

If each process maintains an application pool:

```text
application_pool_total =
    app_replicas × processes_per_replica × pool_size_per_process
```

Example:

- 6 replicas.
- Each replica runs 2 worker processes.
- Each process has a max pool of 8 connections.

```text
6 × 2 × 8 = 96 application connections
```

If there are also 20 connections for background jobs, 10 for monitoring/admin, and 15 for deployment/batch peaks, total demand can reach roughly 141 server connections if connecting directly to PostgreSQL.

This is a capacity planning calculation, not a recommendation to open all 141 connections. If using PgBouncer, client connections and server connections are two distinct quantities.

### 3.3. Pool Size Multiplied by Replicas

A common mistake is configuring pool size for a single process while forgetting total process count.

Example:

```text
12 app replicas × 4 worker processes × pool_size 15
= 720 potential server connections
```

A pool size of 15 sounds small, yet multiplied across 48 processes it far exceeds the capacity of many databases.

### 3.4. Planning for Rollouts and Autoscaling

Include headroom for:

- Maximum replicas under autoscaling.
- Rolling deployment surge capacity.
- Scheduled jobs overlapping peak hours.
- Worker retries during broker/database disruptions.
- Failovers causing clients to reconnect simultaneously.
- Admin access needed during incidents.

Set pool limits and connection limits for the maximum topology that can occur, not just normal steady state.

## 4. Memory Pressure from Connections

Connection count affects memory across multiple layers. A sound model distinguishes shared memory, backend private memory, and memory allocated only when queries run operations.

### 4.1. Shared Memory

Shared structures can include:

- `shared_buffers`.
- WAL buffers.
- Lock tables and shared metadata.
- Shared statistics or extension structures.
- Internal structures depending on configuration.

Some shared-memory requirements scale with `max_connections`, `max_locks_per_transaction`, worker settings, and extension configuration. Increasing `max_connections` can increase shared-memory requirements and requires a restart.

### 4.2. Backend Private Memory

Each backend has its own process state and memory contexts. This memory varies by session and query:

- Parser/planner/executor state.
- Tuple and expression state.
- Memory contexts for protocol/session.
- Transaction management structures.
- Internal buffers and extension allocations.
- Memory for sort/hash operations.

An idle backend typically uses less memory than a backend running a complex query, yet it still carries a baseline cost.

### 4.3. work_mem Is Not Fixed Memory per Connection

`work_mem` is the base memory limit per sort or hash operation before the operation may spill to temporary files. A single query can execute multiple operations at once.

Example:

- A query has 2 sorts and 1 hash join.
- Multiple operations may need memory simultaneously.
- Parallel queries may have workers executing corresponding operations.
- Hash operations may use an allowance scaled by `hash_mem_multiplier` on supported versions.

Therefore, do not calculate memory simply as `max_connections × work_mem`, nor ignore the possibility of multiple operations allocating memory concurrently.

### 4.4. Example of Memory Pressure from work_mem

Suppose:

- `work_mem = 16MB`.
- 30 queries are active.
- On average, each query has 2 concurrent memory-intensive operations.

Rough estimate:

```text
30 × 2 × 16 MB = 960 MB
```

This is an illustrative envelope for sort-like operations. Hash operations can use `work_mem × hash_mem_multiplier`; parallel workers and other operations can push peaks higher. This is not an exact prediction of PostgreSQL RSS.

### 4.5. Other Memory Parameters

| Setting | Usage scope | Notes |
| --- | --- | --- |
| `shared_buffers` | Shared buffer cache | Allocated at instance level |
| `work_mem` | Per sort/hash operation | Multiple operations/query and concurrent queries possible |
| `hash_mem_multiplier` | Hash operations relative to work_mem | Available on supported versions |
| `maintenance_work_mem` | Maintenance operations like index builds and some DDL | Multiple maintenance tasks possible |
| `autovacuum_work_mem` | Memory per autovacuum worker when set | `-1` typically uses `maintenance_work_mem` |
| `temp_buffers` | Temporary tables in a session | Allocated when a session uses temp tables |
| `logical_decoding_work_mem` | Logical decoding buffering | Can affect decoding spill/streaming |
| `wal_buffers` | WAL write buffering | Shared memory |
| `effective_cache_size` | Planner estimate of usable cache | Allocates no memory |

### 4.6. temp_buffers

`temp_buffers` are local buffers for temporary tables per session, allocated when a session uses temporary tables. Many sessions using temp tables can expand the memory footprint.

Do not raise `temp_buffers` globally just because one query creates a large temp table. Inspect temp table lifecycle and query design.

### 4.7. Maintenance and Autovacuum Concurrency

A database can simultaneously run autovacuum workers, index builds, manual VACUUM/ANALYZE, and DDL. These operations can consume their own memory.

In particular, if `autovacuum_work_mem` is not set separately and inherits `maintenance_work_mem`, concurrent worker count must be included in the memory budget. Do not count `maintenance_work_mem` only once if multiple operations can run concurrently.

### 4.8. Shared Buffers and OS Page Cache

`shared_buffers` is not the database's entire cache. PostgreSQL also relies on the OS filesystem cache. On Linux, memory analysis must consider shared memory, process private memory, and page cache.

Summing the RSS of all backends can double-count shared pages. When analyzing process memory, prefer PSS/private memory or appropriate OS tools; do not determine memory demand by mechanically summing RSS.

### 4.9. Overall Memory Budget

A budgeting model:

```text
RAM budget =
    PostgreSQL shared memory
  + backend private memory
  + active query operation memory
  + autovacuum/maintenance memory
  + background worker memory
  + OS and filesystem cache
  + monitoring/sidecar/agent memory
  + safety headroom
```

Components can overlap or share pages; this formula is a classification framework to avoid missing consumption sources. Measure directly on a production-like server.

## 5. Why Increasing max_connections Can Reduce Throughput

A database usually has an optimal concurrency point. Before that point, adding active queries helps utilize CPU/I/O. Beyond that point, adding concurrency mainly increases contention and queueing.

### 5.1. CPU Contention

If many runnable backends compete for fewer CPU cores:

- The scheduler must time-slice many processes.
- Context switches increase.
- CPU cache locality degrades.
- Query latency rises.
- Total throughput can flatten or drop.

### 5.2. I/O Contention

Many concurrent reads/writes can:

- Push storage queue depth high.
- Increase disk latency.
- Generate excessive random reads.
- Increase temporary file I/O.
- Cause checkpoints and background writes to contend with query I/O.

### 5.3. Lock Contention

Many connections updating hot rows/keys wait on locks. Increasing backend count does not eliminate transaction conflicts; it increases the queue of waiting sessions.

### 5.4. Memory Pressure and Swapping

When total memory demand exceeds RAM:

- The kernel reclaims memory and evicts cache.
- Page faults rise.
- PostgreSQL processes may swap.
- Latency becomes erratic.
- The OOM killer may terminate processes on the host/container.

Swapping database backends usually signals that capacity has exceeded design limits. Swap should never be treated as normal memory reserve for database workloads.

### 5.5. Connection Storms

After a network outage or failover, hundreds of applications may reconnect at once. Each new connection requires TCP/TLS/authentication and backend setup. Retries without backoff can create a connection storm right as the database recovers.

## 6. What Is Connection Pooling?

A connection pool maintains a set of connections for reuse instead of opening and closing a connection per request.

Basic flow:

1. A request asks the pool for a connection.
2. If an idle connection is available, the pool hands it to the request.
3. If the pool is full, the request waits in a queue or times out.
4. When the transaction/session finishes, the connection is returned to the pool.
5. The next request reuses that connection.

### 6.1. Benefits

- Reduces connection establishment and authentication overhead.
- Caps the number of server connections.
- Reuses backend processes.
- Provides queueing/backpressure during traffic bursts.
- Helps manage connection lifetime and health.
- Reduces the risk of app replicas opening too many connections.

### 6.2. A Pool Does Not Fix Slow Queries

If a query takes 20 seconds, a pool simply makes other requests wait longer once slots are busy. Pooling regulates concurrency, yet slow queries, locks, and I/O bottlenecks must still be fixed separately.

### 6.3. Application Pool vs. External Pooler

Two common layers exist:

- **Application-side pool:** lives inside the application process, e.g., HikariCP, Npgsql pool, psycopg pool, or node-postgres pool.
- **External pooler:** a service sitting between the app and PostgreSQL, e.g., PgBouncer.

Both can be used together. However, you must calculate total pool sizes and understand which layer holds client vs. server connections.

## 7. Session, Transaction, and Statement Pooling

An external pooler can share server connections under different modes. The mode determines when a server connection is returned to the pool.

### 7.1. Session Pooling

Pros:

- Session state is preserved.
- Temporary tables can persist across multiple transactions.
- Session-level `SET`, prepared statements, `LISTEN/NOTIFY`, and advisory locks work with standard PostgreSQL semantics.
- Easy compatibility with legacy applications.

Cons:

- Idle clients still occupy a server connection.
- Reduces multiplexing ratio.
- Does not solve the problem of thousands of idle clients.

### 7.2. Transaction Pooling

A server connection is assigned to a client for a single transaction and returned to the pool after COMMIT/ROLLBACK.

Pros:

- Many client sessions share a small set of server connections.
- Clients idle outside transactions do not hold server connections.
- Useful for short web/API requests with independent transactions.

Limitations:

- Session state is not guaranteed across transactions.
- Session-level `SET`/`RESET`, temp tables spanning transactions, session advisory locks, `LISTEN`, session cursors, and certain prepared statement patterns may be incompatible.
- Connection affinity is not preserved across transactions.
- Applications must return connections promptly and avoid long transactions.

Recent PgBouncer versions support protocol-level prepared statements in transaction pooling when `max_prepared_statements` is configured appropriately. Do not extrapolate this to all SQL `PREPARE` patterns or session state; verify version and driver behavior.

### 7.3. Statement Pooling

The server connection is returned after every statement. This is the most restrictive mode.

- Multi-statement transactions do not work with standard semantics.
- Unsuitable for most ORMs/application workflows requiring transactions.
- Only consider for simple, independent, thoroughly tested workloads.

### 7.4. Comparison

| Behavior | Session | Transaction | Statement |
| --- | --- | --- | --- |
| Holds server connection between transactions | Yes | No | No |
| Supports multi-statement transactions | Yes | Yes | Not with standard semantics |
| Session-level settings | Yes | Not guaranteed | Not guaranteed |
| Temp tables across multiple transactions | Yes | Not guaranteed | Unsuitable |
| Session advisory locks | Yes | Not guaranteed | Unsuitable |
| Long-lived LISTEN/NOTIFY listener | Yes | Unsuitable | Unsuitable |
| Multiplexing many clients onto small server pool | Low | High | Highest |
| Suitable for stateless web apps | Yes | Usually good | Special cases only |

### 7.5. Using SET LOCAL in Transaction Pooling

If an application needs per-transaction settings, use `SET LOCAL` inside the transaction:

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SET LOCAL search_path = app, public;

SELECT * FROM app.orders WHERE order_id = 42;

COMMIT;
```

`SET LOCAL` expires when the transaction ends, making it compatible with transaction pooling. Verify that the application/ORM opens transactions properly and does not rely on session state afterward.

## 8. Configuring PgBouncer

PgBouncer is a widely used connection pooler for PostgreSQL. It accepts many client connections and multiplexes them onto a bounded number of server connections.

### 8.1. Basic Configuration Structure

Example `pgbouncer.ini`:

```ini
[databases]
appdb = host=127.0.0.1 port=5432 dbname=appdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432

pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
reserve_pool_size = 5
reserve_pool_timeout = 3

server_idle_timeout = 600
server_lifetime = 3600

auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
```

This is a conceptual configuration example. Authentication, TLS, file paths, user management, and service supervision must match your actual deployment environment.

### 8.2. max_client_conn

`max_client_conn` limits client connections to PgBouncer. It is not the number of backend connections to PostgreSQL.

For example, PgBouncer may accept 1,000 clients while maintaining a much smaller server connection pool, depending on pool size and database/user combinations.

Account for file descriptor limits, socket buffers, and PgBouncer memory when setting a large `max_client_conn`.

### 8.3. default_pool_size

`default_pool_size` is the maximum number of server connections per pool for each database/user pair, unless overridden. Therefore, do not multiply a single pool size while ignoring the number of active user/database pairs.

If 5 databases and 4 users each create pools, total server connections can be much larger than `default_pool_size`. Use `max_db_connections` and `max_user_connections` when you need to cap totals per database/user.

### 8.4. reserve_pool_size

`reserve_pool_size` allows opening extra server connections when clients wait longer than `reserve_pool_timeout`. This is emergency capacity for brief bursts, not normal pool capacity.

If the reserve pool is constantly in use, investigate query duration, pool sizing, or DB capacity.

### 8.5. Limits per Database/User

Options such as:

- `max_db_connections`.
- `max_user_connections`.
- `default_pool_size`.
- `reserve_pool_size`.

help control total connections by scope. Availability and exact semantics depend on PgBouncer version; check `SHOW CONFIG` or documentation for your exact version.

### 8.6. Server Connection Lifetime

`server_idle_timeout` closes server connections idle beyond the threshold. `server_lifetime` caps the maximum age of a server connection. Values set too low cause connection churn; values set too high keep connections longer than desired.

Do not set an ultra-short lifetime as a default workaround for connection leaks. Identify the cause and apply proper pool reset/health policies.

### 8.7. Inspecting PgBouncer

The PgBouncer admin console provides commands:

```sql
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
SHOW CONFIG;
SHOW DATABASES;
```

Field names and some commands can vary by version. `SHOW POOLS` typically shows active/waiting clients and active/idle servers; this is key data for identifying pool saturation.

## 9. Designing Application Connection Pools

Application pools are usually configured per process. If a service runs multiple processes, each process typically has its own pool.

### 9.1. One Pool per Process

Avoid creating a new pool per HTTP request. A pool's lifecycle should be tied to the application process:

- Created at service startup.
- Reused across requests.
- Configured with a maximum size.
- Configured with an acquisition timeout.
- Configured with appropriate health validation.
- Closed on process shutdown.

### 9.2. Pool Size Does Not Equal Concurrent Requests

If an app handles 1,000 concurrent HTTP requests yet only 20 requests access the database at once, a pool size of 1,000 can be harmful. Requests not currently querying the database should not hold connections.

Size concurrency around simultaneous database operations and connection hold time.

### 9.3. HikariCP Example

```properties
maximumPoolSize=12
minimumIdle=2
connectionTimeout=3000
idleTimeout=600000
maxLifetime=1800000
validationTimeout=1000
```

Values are examples. `maximumPoolSize` caps one HikariCP instance. With 10 application instances, total potential connections could be 120.

### 9.4. node-postgres Example

```javascript
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 12,
  min: 2,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 3000
});
```

Ensure `pool` is a process-level singleton, never created per request handler. Always release the client in `finally` when using `pool.connect()`.

### 9.5. psycopg Pool Example

```python
from psycopg_pool import ConnectionPool

pool = ConnectionPool(
    conninfo="postgresql://app_service@db/appdb",
    min_size=2,
    max_size=12,
    timeout=3
)
```

Real credentials should come from a secret manager/environment per policy. Close the pool in the application shutdown hook.

### 9.6. Pool Acquisition Timeout

If the pool is full, requests wait. Set a clear timeout so the queue cannot grow unbounded.

The pool timeout should be shorter than the remaining request deadline. If a request only has a 2-second budget yet waits 10 seconds for a connection, the system has already missed the deadline before the query even runs.

### 9.7. Idle Timeout and Max Lifetime

- Idle timeout closes connections unused for a period.
- Max lifetime recycles connections after a maximum age.
- Validation/keepalive detects stale connections.
- Connection lifetime should align with network/load balancer/database timeouts.

Recycling too aggressively increases authentication/TLS churn; recycling too rarely keeps stale sessions around longer.

## 10. Sizing Pools by Workload, Not Guesswork

There is no single right pool size for every PostgreSQL instance. Measure throughput and latency as concurrency changes.

### 10.1. Little's Law

Little's Law:

```text
L = λ × W
```

Where:

- `L`: average number of requests inside the system.
- `λ`: average throughput/arrival rate.
- `W`: average time a request spends in the system.

For example, if a database processes 300 operations/sec with an average service time of 20 ms:

```text
L = 300 × 0.020 = 6 concurrent operations
```

`6` is the steady-state average concurrency. Actual pool sizing must account for bursts, variance, tail latency, transaction duration, and headroom. Do not multiply p99 request time by QPS as if every request holds a connection for the entire p99 duration.

### 10.2. Finding the Saturation Point

Benchmark sequentially across server pool sizes, e.g., 8, 12, 16, 24, and 32. At each level, measure:

- Throughput (transactions/second).
- p50/p95/p99 latency.
- CPU utilization and run queue.
- Storage latency/queue depth.
- Active sessions and lock waits.
- Memory usage and temporary files.
- Pool wait time and timeout rate.

Choose the region near where throughput starts flattening while latency has not spiked sharply. Keep headroom for bursts and maintenance.

### 10.3. Do Not Use CPU Core Count as a Hard Rule

CPU core count is a useful reference point, but the query mix determines optimal concurrency. CPU-bound queries, I/O-bound queries, short OLTP, and analytical scans behave differently.

Benchmark your actual or representative workload rather than setting pool size to `CPU cores × 2` without measurement.

### 10.4. Separate Active Concurrency from Open Connections

You may have 200 server connections yet only 15 active queries. Pooling keeps open connections stable while execution concurrency is governed by busy server connections and transaction duration.

## 11. Transaction Duration and Connection Occupancy

A connection is held for the entire transaction. Long transactions reduce how often the pool can reuse server connections.

### 11.1. Keep Transactions Short

Never hold a transaction open while:

- Waiting for user input.
- Calling an external HTTP API.
- Waiting on a message broker.
- Uploading/downloading files.
- Processing large batches that do not need atomicity.
- Running long CPU tasks that do not interact with the database.

Anti-pattern:

```text
BEGIN
  UPDATE database
  call external payment service
  wait 8 seconds
  UPDATE database
COMMIT
```

A better pattern typically separates external calls from database transactions using a state machine/outbox/saga depending on business consistency requirements.

### 11.2. idle in transaction

An `idle in transaction` session holds an open transaction without executing a statement. It can hold locks, pin a snapshot, and prevent vacuum from cleaning up old dead tuples.

Check:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    now() - xact_start AS transaction_age,
    now() - state_change AS idle_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS last_query
FROM pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
```

### 11.3. idle_in_transaction_session_timeout

Can be configured to terminate sessions idle in a transaction for too long:

```conf
idle_in_transaction_session_timeout = '60s'
```

Choose the timeout according to workload and transaction design. Too short may terminate legitimate long-running application workflows; too long lets sessions hold snapshots/locks excessively.

### 11.4. idle_session_timeout

`idle_session_timeout` closes sessions idle outside a transaction on supported PostgreSQL versions. Be careful with poolers: a session closed unexpectedly by the server can force the pool to reconnect and cause churn.

### 11.5. statement_timeout and lock_timeout

You can configure:

```conf
statement_timeout = '30s'
lock_timeout = '3s'
```

- `statement_timeout` caps statement execution duration.
- `lock_timeout` caps lock wait duration before the statement fails.

Timeouts should coordinate with application deadlines and retry policies. A `lock_timeout` that is too low can cause repeated errors during normal workload contention.

## 12. Connection Leaks and Proper Connection Usage

A connection leak occurs when an application checks a connection out of the pool and fails to return it.

### 12.1. Safe Pattern

Pseudo-code:

```javascript
const client = await pool.connect();

try {
  await client.query('BEGIN');
  await client.query('UPDATE app.orders SET status = $1 WHERE order_id = $2', [
    'paid',
    1001
  ]);
  await client.query('COMMIT');
} catch (error) {
  await client.query('ROLLBACK');
  throw error;
} finally {
  client.release();
}
```

If a transaction fails, roll back before releasing the client so the connection does not return to the pool in an unexpected transaction state. Some libraries provide transaction wrapper APIs that manage lifecycle more safely.

### 12.2. Signs of a Leak

- Pool active connections grow steadily and never drop.
- Idle pool connections are abnormally scarce.
- Pool acquisition timeouts climb.
- PostgreSQL shows many `idle` sessions from one app.
- Connection count grows after each request/job.
- Restarting the app temporarily improves the situation.

### 12.3. Leak Detection

Some pools support a leak detection threshold or logging when a connection is held too long. Enable purposefully in staging or production canary; leak logging can create heavy log volume if the threshold is too low.

### 12.4. Do Not Open Connections Inside Loops

Never open a new connection per row or per item in a batch. Use an appropriate connection/transaction, batched statements, or `COPY` when high throughput is needed.

## 13. Connection Pooling and Transaction Pooling Caveats

Transaction pooling saves backend connections but requires applications not to rely on session affinity.

### 13.1. Session Variables

Session-level `SET search_path` or `SET timezone` may no longer apply in the next transaction if the client is assigned a different server connection.

Solutions:

- Use `SET LOCAL` inside transactions.
- Use fully qualified object names.
- Configure defaults per role/database where appropriate.
- Do not assume session state persists after COMMIT.

### 13.2. Temporary Tables

Temporary tables can be session-scoped. Under transaction pooling, the next transaction may get a different server connection where the temp table does not exist.

If temp tables are required, redesign or use session pooling. Some `ON COMMIT DROP` patterns can work with transaction pooling in supported scenarios; verify your exact PgBouncer version and behavior.

### 13.3. Prepared Statements

Prepared statements can depend on session state. Newer PgBouncer versions support protocol-level prepared statement tracking when `max_prepared_statements` is configured non-zero. SQL-level `PREPARE` and driver-specific behaviors must be tested separately.

### 13.4. Advisory Locks

Session-level advisory locks are tied to the server session; they are unsafe if transaction pooling switches the client to another backend on the next transaction. Transaction-level advisory locks are scoped to the transaction and fit this model better.

### 13.5. LISTEN/NOTIFY

A listener requires a persistent session connection to receive notifications. Use a dedicated session-pool connection or a separate listener service rather than running it over a standard transaction pool.

### 13.6. Cursors and Streaming Results

Some cursor/portal workflows require session affinity or long-running transactions. Check driver and pooler mode before using; long-running result streaming also holds connections and impacts pool capacity.

## 14. Queueing and Backpressure

The pool is where requests queue when clients wanting the database exceed available server connections.

### 14.1. Bounded Queues

A useful queue needs:

- Maximum wait duration.
- Maximum pending requests or a bounded queue.
- Timeout on overload.
- Cancellation when the request deadline expires.
- Metrics for queue depth and wait time.

An unbounded queue simply converts overload into escalating latency and memory consumption.

### 14.2. Pool Saturation

When the pool is full, clients wait. Raising pool size can reduce wait time briefly, yet if the database is already saturated it merely shifts the queue from the app into the database and worsens query latency.

### 14.3. Application-Level Backpressure

Options include:

- Limiting concurrency per endpoint/job.
- Using bounded worker queues.
- Returning 429/503 or degrading noncritical requests.
- Reducing batch concurrency.
- Pausing background jobs during incidents.
- Using deadline propagation and cancellation.

### 14.4. Retry Storms

If pool timeouts or connection refusals cause every client to retry immediately, the database gets hit by an even larger burst. Use exponential backoff with jitter, retry budgets, and circuit breakers. Do not retry non-transient SQL errors such as constraint violations.

### 14.5. Deadline Budget

A request deadline should be partitioned into:

```text
request_budget =
    queue_wait_budget
  + pool_acquire_budget
  + database_execution_budget
  + application_processing_budget
```

Budgets must be consistent. If the pool acquisition timeout exceeds the request deadline, requests sit queued even after the caller has given up.

## 15. Observing Connections in PostgreSQL

Distinguish total existing sessions, active queries, and waiting sessions.

### 15.1. Counting Connections by State

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

This query requires privileges to view the relevant sessions; users lacking privileges may see restricted query text/metadata.

### 15.2. Total Client Backends

```sql
SELECT
    count(*) AS total_sessions,
    count(*) FILTER (WHERE state = 'active') AS active_sessions,
    count(*) FILTER (WHERE state = 'idle') AS idle_sessions,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_transaction
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

`backend_type` exists on supported PostgreSQL versions. On older versions, remove the filter or use columns appropriate to the catalog/view.

### 15.3. max_connections Utilization

```sql
SELECT
    current_connections,
    max_connections,
    round(
        100.0 * current_connections / NULLIF(max_connections, 0),
        1
    ) AS connection_utilization_pct,
    max_connections - current_connections AS nominal_free_slots
FROM (
    SELECT
        count(*) AS current_connections,
        current_setting('max_connections')::int AS max_connections
    FROM pg_stat_activity
) AS s;
```

This is the ratio of total sessions to the configured maximum. It does not subtract reserved slots and does not replace checking other connection limits.

### 15.4. Connections by Application

```sql
SELECT
    application_name,
    count(*) AS connections,
    count(*) FILTER (WHERE state = 'active') AS active,
    count(*) FILTER (WHERE state = 'idle') AS idle,
    count(*) FILTER (
        WHERE state LIKE 'idle in transaction%'
    ) AS idle_in_tx
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name
ORDER BY connections DESC;
```

`application_name` should be set consistently for this query to be valuable. If all sessions share one generic name or an empty string, identifying service owners is difficult.

### 15.5. Connection Age

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    backend_start,
    now() - backend_start AS connection_age,
    state,
    now() - state_change AS state_age
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start;
```

An old connection is not automatically an error. Combine age with pool policy, state, and owner to spot abnormal sessions.

### 15.6. pg_stat_database

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    temp_files,
    temp_bytes
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY numbackends DESC;
```

`numbackends` is the number of backends currently connected to the database. Other counters are cumulative since stats reset or initialization; compute deltas over time to measure rates.

## 16. Observing Memory and Workload

Connection counts should be paired with memory metrics, never viewed in isolation.

### 16.1. Sources to Monitor

- Host/container total memory and available memory.
- PostgreSQL process private memory/PSS.
- Shared memory and shared buffers.
- Swap in/out and major page faults.
- OOM events and container memory limits.
- Active query count and query mix.
- Parallel workers.
- Autovacuum/maintenance concurrency.
- Temporary file bytes.
- Pool server/client connections.

### 16.2. Do Not Sum RSS Naively

Each backend maps shared memory. Summing RSS across many processes counts shared pages multiple times. Use PSS/private memory or appropriate OS metrics to avoid overestimating memory.

### 16.3. Inspecting shared_buffers

```sql
SHOW shared_buffers;
```

This is PostgreSQL's shared buffer cache configuration, not total memory PostgreSQL will consume.

### 16.4. Inspecting Memory Settings

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'hash_mem_multiplier',
    'maintenance_work_mem',
    'autovacuum_work_mem',
    'temp_buffers',
    'logical_decoding_work_mem',
    'max_connections'
)
ORDER BY name;
```

Not every parameter exists in every major version. Filter conditionally or omit nonexistent names in multi-version automation.

### 16.5. Querying Memory Contexts

Supported PostgreSQL versions provide a view/function to inspect the current backend's memory contexts or log a backend's memory contexts with appropriate privileges. These are helpful when investigating abnormal memory growth in a query/backend, though they do not replace host-level memory dashboards.

## 17. Sizing max_connections and Pools by Example

Suppose a PostgreSQL instance has 16 vCPUs and 64 GiB RAM, serving an OLTP application.

### 17.1. Determine Connection Demand

Peak topology:

| Component | Replicas/processes | Max pool per process | Potential connections |
| --- | ---: | ---: | ---: |
| Orders API | 6 × 2 processes | 8 | 96 |
| Billing API | 3 × 2 processes | 6 | 36 |
| Background workers | 10 processes | 2 | 20 |
| Reporting jobs | 3 jobs | 2 | 6 |
| Admin/monitoring reserve | — | — | 10 |
| **Total potential direct connections** | | | **168** |

If all app processes connect directly, the database needs capacity for a peak of 168 plus operational headroom and reserved slots. However, if PgBouncer multiplexes clients, server connections can be much smaller.

### 17.2. Determine Active Query Concurrency

Suppose peak workload has 400 DB operations/s and an average service time of 15 ms:

```text
L = 400 × 0.015 = 6 average active operations
```

This is theoretical steady-state average concurrency. Bursts, tail latency, and longer transactions can push peaks higher. Benchmarks may show a pool of 16–24 delivers full throughput, while a pool of 100 only increases contention.

### 17.3. Choose a Server Pool Budget

Example trial plan:

- Application client connections to PgBouncer: max 500.
- PgBouncer server pool to PostgreSQL for `appdb`: 24.
- Dedicated reporting pool: 4.
- Admin/monitoring/direct maintenance: 10.
- Reserved slots for incidents and reserved roles.

Numbers are illustrative only. You must sum server pools across all PgBouncer instances and all direct connections; if multiple PgBouncer nodes exist, each node can open its own pool.

### 17.4. Memory Envelope

Suppose 24 active server connections, an average of 2 memory-intensive operations per query, and `work_mem=16MB`:

```text
24 × 2 × 16 MB = 768 MB
```

If some operations are hashes, the memory allowance can be higher by `hash_mem_multiplier`. Parallel workers, maintenance, autovacuum, and backend baselines must be added separately.

### 17.5. Choose max_connections

`max_connections` must accommodate the planned total server connections, including pooler nodes and direct clients, plus reserved slots. It does not need to equal the number of client connections accepted by PgBouncer.

In this example, the database might only need several dozen or well under a hundred server slots depending on actual topology. Benchmarks and memory/latency checks determine the final number.

## 18. PgBouncer Metrics and Interpretation

PgBouncer exposes metrics showing whether clients are waiting or server connections are in use.

### 18.1. SHOW POOLS

Commonly useful fields:

- `cl_active`: clients attached to a server connection.
- `cl_waiting`: clients waiting for a server connection.
- `sv_active`: server connections currently in use.
- `sv_idle`: server connections idle in the pool.
- `maxwait`: longest wait time of a client in the pool, per version semantics.
- `pool_mode`: pooling mode if displayed.

Verify column names against your PgBouncer version.

### 18.2. SHOW STATS

Statistics can include transactions, queries, bytes received/sent, average query time, average transaction time, and wait time. Compute deltas between scrapes to obtain rates.

### 18.3. Pool Wait Time

If `cl_waiting` is frequently greater than 0 and `sv_active` hits the pool limit:

- Queries/transactions may be holding server connections too long.
- The pool size may be too small for the workload.
- The database may be slow due to CPU/I/O/locks.
- There may be a transaction leak or clients failing to return connections.

Only raise pool size when the database has headroom and benchmarks show throughput improves.

### 18.4. Server Connections Idle Yet Clients Waiting?

Check pool key (database/user), pool mode, per-database/user caps, paused/suspended databases, and global limits. Server connections may be idle in a different pool and unavailable to the waiting pool because pools are isolated by scope.

## 19. Connection Limits and Workload Isolation

Connection limits can protect the database from a single service consuming all capacity.

### 19.1. Role Connection Limits

```sql
ALTER ROLE reporting_user CONNECTION LIMIT 8;
ALTER ROLE batch_user CONNECTION LIMIT 4;
ALTER ROLE app_service CONNECTION LIMIT 40;
```

These limits must coordinate with your pooler. If PgBouncer uses a single shared user for server connections, PostgreSQL sees that server-side role rather than individual end-user client identities in many configurations.

### 19.2. Database Connection Limits

```sql
ALTER DATABASE analytics CONNECTION LIMIT 12;
```

You can limit a reporting/analytics database to protect an OLTP database, while accounting for maintenance, migrations, and monitoring.

### 19.3. Workload Isolation

Additional strategies:

- Use dedicated roles for batch/reporting.
- Use dedicated pools and caps.
- Route analytical workloads to replicas or a warehouse.
- Cap concurrency in the job scheduler.
- Apply appropriate statement/lock timeouts.
- Separate maintenance windows if needed.

### 19.4. Connection Limits Are Not Full Resource Governance

Role/database connection limits do not restrict CPU time, I/O, per-query memory, or query cost. A single connection can still run an extremely heavy query. Combine limits with query governance, timeouts, workload routing, and monitoring.

## 20. Connection Storms and Reconnect Behavior

Connection storms typically happen when many clients reconnect simultaneously after an outage.

### 20.1. Causes

- Database restart/failover.
- Network load balancer resetting connections.
- PgBouncer restart.
- Secret/certificate rotation.
- Rolling deployment restart.
- Connection lifetimes of all clients expiring near the same time.
- Autoscaler scaling replicas up rapidly.

### 20.2. Jitter and Exponential Backoff

Retry policies should include:

- Exponential backoff.
- Random jitter.
- Maximum retry interval.
- Retry budget.
- Deadline-aware cancellation.
- Circuit breakers or load shedding.

Never let thousands of clients retry every 100 ms indefinitely.

### 20.3. Controlled Warmup

At service startup, you do not need to open the full max pool size immediately. Start with a low minimum idle count and scale up on demand. This reduces connection bursts during multi-replica rollouts.

### 20.4. Health Checks

Health checks should avoid opening a new connection on every probe when an existing pool or appropriate health signal can be used. Avoid overly frequent health-check intervals that generate load themselves.

## 21. Pooler High Availability and Topology

PgBouncer itself is a service that must be operated reliably.

### 21.1. Multiple PgBouncer Instances

If you run N PgBouncer nodes, each node can maintain its own server pools. Total server connections are roughly:

```text
total_server_connections =
    sum(server_connections_from_each_pooler)
```

Do not configure every node with the full database connection budget. Divide the budget across pooler nodes while leaving margin for when a node fails.

### 21.2. Failover

When PostgreSQL fails over, old server connections may break. The pooler/app must detect this and reconnect. Verify DNS/service discovery, primary routing, and stale connection handling.

### 21.3. Transaction Retries

Do not blindly retry transactions with side effects if you do not know whether the transaction already committed. Design idempotency keys or transaction outcome reconciliation for critical business operations.

### 21.4. TLS and Authentication

Define TLS for both client→PgBouncer and PgBouncer→PostgreSQL. The two hops are separate connections. Manage credentials, certificate rotation, and auth files according to security policy.

## 22. Connection Pooling with ORMs and Drivers

ORMs/drivers typically have built-in defaults or pool configurations.

### 22.1. Avoid Multiple Pools When Frameworks Instantiate Multiple Clients

Some frameworks create a database client per module/worker. If each module creates a new ORM client, total pool connections multiply.

Use a singleton or framework-appropriate dependency lifecycle. Document how many pool instances exist per process.

### 22.2. Serverless and Short-Lived Workers

Serverless functions can scale to hundreds of instances in seconds. Each instance having its own pool creates a connection storm.

Options:

- External pooler/proxy.
- Small pool size or single connection per instance.
- Reuse execution environments where possible.
- Cap function concurrency.
- Use a suitable managed connection proxy.

### 22.3. Driver Timeout Settings

Check separately:

- Connection timeout.
- Pool acquisition timeout.
- Socket/read timeout.
- Query/statement timeout.
- Idle timeout.
- Max lifetime.
- Validation timeout.

Do not rely on a single timeout for all phases.

### 22.4. Pool Validation

Overly frequent validation queries add overhead. Use driver-supported connection validation or appropriate keepalives. If a connection is stale, evict it from the pool and reconnect instead of repeatedly failing requests.

## 23. Memory-Based Capacity Planning

Setting `max_connections` without budgeting memory can cause OOMs at peak load.

### 23.1. Memory Categories

| Category | How to estimate |
| --- | --- |
| OS reserve | Memory needed for kernel, agents, and host |
| PostgreSQL shared memory | `shared_buffers`, WAL buffers, lock/shared structures |
| Backend baseline | Measure private memory when backends are idle |
| Active query memory | Concurrent operations × `work_mem`/hash allowance |
| Maintenance | Autovacuum workers, index builds, VACUUM/DDL |
| Parallel workers | Worker memory and process overhead |
| Other services | PgBouncer, monitoring, backup agents |
| Headroom | Reserved for bursts, allocator fragmentation, and uncertainty |

### 23.2. Measuring Backend Baseline

Use process metrics in a representative environment to measure private memory of idle and active backends. Avoid copying a fixed number from another server because extensions, libc, builds, workloads, and OS differ.

### 23.3. Measuring Peak Query Memory

Test workloads featuring:

- Large sorts.
- Hash joins/aggregates.
- Parallel queries.
- Temp table usage.
- DML with triggers.
- Concurrent maintenance.

Monitor host/container memory, temp files, and latency during runs.

### 23.4. Do Not Overcommit Memory via Configuration

An illustrative envelope formula:

```text
estimated_peak =
    shared_memory
  + backend_baseline × server_connections
  + active_operations × operation_memory_budget
  + maintenance_peak
  + worker_peak
  + OS_and_other_services
```

This is a conservative estimate; shared pages and allocator behavior make reality more complex. Calibrate using benchmarks and memory telemetry.

## 24. Optimizing Connections Through Workload Design

Not every query needs its own long-lived connection.

### 24.1. Batch Statements

Instead of calling the database hundreds of times row by row, use batch inserts/updates or `COPY` where appropriate. This cuts round trips and connection occupancy.

### 24.2. Shorten Transaction Duration

Keep external calls outside transactions. Avoid waiting on users or queues inside a transaction.

### 24.3. Cache Appropriately

Caching read-heavy data reduces query rate, though it requires an invalidation/consistency strategy and protection against cache stampedes.

### 24.4. Read Replicas

Read replicas offload suitable read workloads from the primary. Account for replication lag and verify queries tolerate eventual consistency requirements.

### 24.5. Async Jobs

Offload work that does not require synchronous responses into bounded worker queues. Cap worker concurrency so they do not form another oversized pool.

## 25. Common Issues

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `too many clients already` | Server slots exhausted | Check `pg_stat_activity`, pool totals, and reserved slots |
| Pool acquisition timeout | Pool saturation or long-held connections | Check queue wait, query duration, transaction age |
| Many idle sessions | Oversized pool or app holding sessions | Shrink pool; use transaction pooling if compatible |
| Many idle in transaction | App forgot commit/rollback or long transactions | Fix lifecycle, timeouts, and tracing |
| Memory grows with connections | Backend baseline and active operation memory | Measure private memory, cap concurrency, check `work_mem` |
| High CPU after raising `max_connections` | Too many active backends / context switching | Lower server pool and benchmark |
| Swap/OOM | Memory overcommit or query bursts | Lower concurrency, query memory, and maintenance overlap |
| Clients wait while server pool is idle | Pool key/cap/mode mismatch | Check `SHOW POOLS`/`CONFIG`/`DATABASES` |
| Reconnect storm after failover | Simultaneous retries and pool warmup | Backoff with jitter, bounded warmup |
| Rising temp files | Sort/hash spills or large queries | Read plan, check `work_mem` and query design |
| Connection count climbs over time | Leak or multiple pool instances | Check pool lifecycle and release paths |
| Reporting slows down OLTP | Shared connection/resource budget | Separate pools, role caps, replica/warehouse |

## 26. Runbook: Investigating Connection Saturation

**Step 1 — Confirm impact.** Record timestamp, database, application, error rate, pool timeouts, and user impact.

**Step 2 — Count PostgreSQL sessions.** Use `pg_stat_activity` grouped by database, role, application name, and state.

**Step 3 — Classify sessions.** Separate active, idle, idle in transaction, waiting, and admin/monitoring sessions.

**Step 4 — Compare against `max_connections`.** Check reserved slots, role/database limits, and remaining capacity.

**Step 5 — Inspect the pooler.** Run `SHOW POOLS`, `SHOW CLIENTS`, `SHOW SERVERS`, and `SHOW STATS`; check client waiters and server saturation.

**Step 6 — Check query/transaction duration.** Inspect slow logs, `pg_stat_activity`, blocking PIDs, and transaction ages.

**Step 7 — Check system resources.** Correlate CPU, memory, swap, disk latency, temp files, and parallel workers.

**Step 8 — Shed load cleanly.** Pause batch/reporting jobs, lower app concurrency, or throttle non-essential endpoints. Avoid killing sessions en masse without identifying transaction owners.

**Step 9 — Recover pooling.** Fix leaks, long transactions, retry storms, or pool topology. Increase server pool size only if the database has headroom and benchmarks justify it.

**Step 10 — Post-incident verification.** Confirm pool waits, active sessions, latency, memory, and error rates return to baseline. Document root cause and capacity actions.

## 27. Pool Design Checklist

Before going to production, verify:

- How many application replicas run at peak?
- How many processes/workers does each replica run?
- How many pool instances exist per process?
- What are total client connections to the pooler?
- What are total server connections across all pooler nodes?
- Are there direct connections bypassing the pooler?
- Which pool mode is used, and which session features are relied upon?
- Does the pool acquisition timeout fit the request deadline?
- Are queues bounded with backpressure?
- Do retries use exponential backoff and jitter?
- Can connection leaks be detected?
- Are transactions reliably committed/rolled back and connections released?
- Does the memory budget include `work_mem` operations and maintenance?
- Are slots reserved for administration?
- Have failover and reconnect behavior been tested?
- Which metrics alert on pool saturation and memory pressure?

## 28. Practice Exercises

Perform these in a PostgreSQL lab and PgBouncer test instance. Do not raise `max_connections`, terminate sessions, or alter production pools just to experiment.

### Exercise 1 — Reading `max_connections`

Run `SHOW max_connections` and explain why it is a server limit rather than a target concurrency.

### Exercise 2 — Checking Reserved Slots

Check `superuser_reserved_connections` and, if supported by your version, `reserved_connections`. Calculate the remaining ordinary slots.

### Exercise 3 — Connection Limits

Set role/database connection limits in the lab. Open multiple sessions and observe the error when exceeding the limit.

### Exercise 4 — Counting Sessions

Use `pg_stat_activity` to count active, idle, and idle-in-transaction sessions. Group by `application_name`.

### Exercise 5 — Connection Age

Open sessions over varying intervals. Inspect `backend_start` and `state_change`.

### Exercise 6 — Pool Size Multiplication

Simulate 8 replicas × 3 processes × pool size 10. Calculate potential server connections and propose a budget.

### Exercise 7 — Application Pool Lifecycle

Create an application pool singleton. Send multiple requests and confirm server session count does not grow per request.

### Exercise 8 — Connection Leak

Intentionally fail to release a client in the lab. Observe pool active count and acquisition timeouts, then fix with `finally`/release.

### Exercise 9 — Pool Acquisition Timeout

Have a query hold a connection for a long time and send competing requests. Measure pool wait time.

### Exercise 10 — Transaction Duration

Open a transaction and wait. Observe the `idle in transaction` state and transaction age.

### Exercise 11 — `idle_in_transaction_session_timeout`

Configure this timeout in the lab. Verify an idle-in-transaction session is terminated and check how the application handles the disconnect.

### Exercise 12 — `statement_timeout` and `lock_timeout`

Create a lock-waiting query in the lab. Compare the behavior of both timeouts.

### Exercise 13 — PgBouncer Session Pooling

Configure session mode. Test session-level `SET` and temp tables across multiple transactions.

### Exercise 14 — PgBouncer Transaction Pooling

Switch to transaction mode. Test session-level settings and explain why backend affinity cannot be assumed.

### Exercise 15 — `SET LOCAL`

Use `SET LOCAL` inside a transaction. Verify the setting expires after COMMIT.

### Exercise 16 — Prepared Statements

Test driver prepared statements with PgBouncer transaction mode. Check `max_prepared_statements` and version compatibility.

### Exercise 17 — Advisory Locks

Compare session-level and transaction-level advisory locks under transaction pooling in the lab.

### Exercise 18 — `LISTEN/NOTIFY`

Create a long-lived listener. Explain why it requires a dedicated session connection.

### Exercise 19 — `max_client_conn`

Increase client connections to PgBouncer while keeping the server pool small. Inspect `SHOW CLIENTS` and `SHOW POOLS`.

### Exercise 20 — `default_pool_size`

Create multiple database/user pools. Observe total server connections and explain why pool size applies per pool key.

### Exercise 21 — Reserve Pool

Configure `reserve_pool_size` and `reserve_pool_timeout`. Create a burst of client waiters and observe when the reserve pool engages.

### Exercise 22 — `max_db_connections`

Set a database-level cap in PgBouncer. Test multiple user pools targeting the same database.

### Exercise 23 — Little's Law

Generate a workload with known throughput and mean service time. Estimate average concurrency and compare with active sessions.

### Exercise 24 — Throughput Saturation

Benchmark pool sizes 8, 16, 24, and 32. Compare throughput, p95 latency, CPU, and lock waits.

### Exercise 25 — `work_mem` Pressure

Run queries with multiple sort/hash operations. Test different `work_mem` levels and observe memory/temp files.

### Exercise 26 — Parallel Queries

Run parallel queries in the lab. Observe worker processes and their impact on concurrency/memory envelopes.

### Exercise 27 — Maintenance Overlap

Run an index build or VACUUM alongside a query workload. Monitor memory, CPU, and I/O.

### Exercise 28 — Connection Storms

Simulate many clients reconnecting at once. Compare immediate retries against exponential backoff with jitter.

### Exercise 29 — Pooler Failover

Restart a PgBouncer test node. Observe client reconnects, server pool warmup, and error rates.

### Exercise 30 — Connection Budget

Create an inventory table of app replicas, process counts, pool sizes, direct connections, and reserves. Compute peak capacity.

### Exercise 31 — Memory Budget

Estimate shared memory, backend baseline, active operations, maintenance, workers, and OS headroom. Compare with lab telemetry.

### Exercise 32 — Role Isolation

Set different connection limits for app, reporting, and batch roles. Verify reporting workloads cannot consume the entire budget.

### Exercise 33 — Monitoring Dashboard

Build a dashboard showing connections, pool waiters, active/idle states, idle-in-transaction age, memory, swap, and temp bytes.

### Exercise 34 — Saturation Incident

Create controlled pool saturation. Follow the runbook to locate the bottleneck and recover using concurrency limits.

### Exercise 35 — Production Pool Runbook

Write a runbook covering topology, `max_connections`/reserved slots, app pool sizing, PgBouncer mode, memory budget, timeout/retry policies, metrics, failover, and rollback.

## 29. Summary

Key takeaways when designing **`max_connections`, connection pooling, and memory pressure**:

1. `max_connections` caps server connections; it does not define optimal concurrency.
2. Every PostgreSQL client connection carries backend/session overhead even when idle.
3. Keep reserved slots so DBAs/operations can connect when connections are nearly exhausted.
4. Calculate the connection budget from replicas × processes × pool size plus all direct clients.
5. A pooler decouples client connections from server connections.
6. Session, transaction, and statement pooling have different semantics; transaction pooling requires applications to avoid relying on session state.
7. `work_mem` is allocated per sort/hash operation, not as a single fixed amount per connection.
8. Parallel queries, maintenance, and autovacuum can push memory peaks higher.
9. Excessive connections cause CPU contention, I/O queueing, lock waits, and swapping.
10. Size pools via throughput/latency benchmarks, using Little's Law as a concurrency estimation tool.
11. Keep transactions short, release connections reliably, and detect leaks.
12. Use bounded queues, acquisition timeouts, deadline propagation, and retry jitter to handle overload.
13. Monitor `pg_stat_activity`, PgBouncer pools, memory, temp files, CPU, I/O, and connection wait times.
14. Sum server connections across all pooler nodes; never give each node the entire database budget.
15. Raise `max_connections` only with evidence of capacity and memory headroom.

A stable PostgreSQL system keeps server connections within the range the database can serve efficiently. Pooling, queueing, and memory budgeting absorb traffic bursts without turning every incoming request into a new backend process and another slice of resource pressure.

## 30. Official References

- [PostgreSQL Connection Settings](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [PostgreSQL Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html)
- [PostgreSQL Memory Configuration](https://www.postgresql.org/docs/current/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-MEMORY)
- [PostgreSQL Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)
- [Role Attributes and Connection Limits](https://www.postgresql.org/docs/current/role-attributes.html)
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html)
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html)
- [Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [EXPLAIN and Query Memory](https://www.postgresql.org/docs/current/using-explain.html)
- [PgBouncer Documentation](https://www.pgbouncer.org/config.html)
- [PgBouncer Features and Pool Modes](https://www.pgbouncer.org/features.html)
- [PgBouncer Administration Console](https://www.pgbouncer.org/usage.html)
- [PgBouncer FAQ](https://www.pgbouncer.org/faq.html)

`current` links point to the latest PostgreSQL documentation. Reserved connections, memory settings, statistics views, and PgBouncer prepared-statement behavior depend on version. Before deploying, check `SHOW server_version`, `pg_settings`, PgBouncer `SHOW CONFIG`, and documentation matching your exact versions.
