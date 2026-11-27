# Health Checks, Readiness, and Verifying Actual Serviceability

A PostgreSQL server may be running while the application is still unable to serve requests. The process might have an open TCP port yet reject connections during recovery; the database might accept connections while the application role lacks privileges; a `SELECT 1` query might succeed while a table or schema the application requires has not been migrated; the primary might be healthy while a replica has lagged past acceptable limits; or the connection pool might be exhausted even though PostgreSQL itself is healthy.

Therefore, health checks must answer the right question for each system layer. **Liveness** indicates whether a process is still alive or needs restarting. **Readiness** indicates whether an instance can accept specific types of traffic right now. **PostgreSQL health checks** observe server state, database state, and the capabilities the application actually depends on. A good check must be lightweight, bounded by timeouts, executed with an appropriate identity, and reflect failures that impact users.

## 1. Distinguishing Liveness, Readiness, and Startup

These three concepts are commonly used in container orchestrators, load balancers, and monitoring systems.

| Check Type | Question | Action on Failure | Examples |
|---|---|---|---|
| Liveness | Is the process alive and capable of continuing to run? | May restart the process after consecutive failures | Process exists, event loop is not hung |
| Readiness | Can the instance accept new requests? | Temporarily stop routing traffic to the instance | DB connection, schema, and mandatory dependencies ready |
| Startup | Has the application finished initial startup? | Wait longer before applying liveness/readiness | Migrations, cache warm-up, or initial connection setup |

Do not use a single endpoint for all three purposes when their behaviors differ. For example, PostgreSQL undergoing recovery after a restart may not yet accept connections. Repeatedly restarting a database container because readiness fails will not help recovery finish; it can trap the database in a startup loop.

For applications connecting to PostgreSQL, liveness should generally focus on the application process itself. Readiness can check connectivity via the pool, schema access, and mandatory dependencies. Startup probes give applications sufficient initialization time before other probes begin evaluating.

## 2. Defining the Scope of a Health Check

A health check must have a clear scope. A TCP-level check, a PostgreSQL protocol check, and a business query can yield different results.

1. **Process:** is the PostgreSQL or application process alive?
2. **Network:** do host, port, DNS, routes, and firewalls permit connections?
3. **Protocol:** does the server respond to PostgreSQL startup packets and report connection status?
4. **Authentication:** can the client authenticate with the expected role and method?
5. **Database:** does the target database exist and accept connections?
6. **SQL capability:** can the role execute required queries?
7. **Schema contract:** are required tables, views, functions, and migration versions present?
8. **Read/write capability:** is the read or write path required by the workload working?
9. **Replication/failover:** does the instance hold the expected primary/standby role and stay fresh enough to serve?
10. **Service capacity:** are connection pools, locks, I/O, and latency within serviceable limits?

Not every readiness endpoint needs all ten steps. Choose the mandatory conditions for the type of traffic the instance receives. For instance, a reporting read replica may accept read-only traffic within a lag bound; a write primary needs commit capability; an ETL worker may need read access to the source and write access to the target database.

## 3. Using `pg_isready` to Check Whether PostgreSQL Accepts Connections

`pg_isready` is a utility bundled with PostgreSQL clients. It checks the connection status of a PostgreSQL server on a specified host/port/database. It is a fast server-level check, usually suited for infrastructure-level probes.

Example:

```bash
pg_isready -h db.internal -p 5432 -d appdb -U app_health -t 3
```

Common options:

- `-h`: hostname or server address.
- `-p`: PostgreSQL port.
- `-d`: database name to check.
- `-U`: username supplied in the startup packet.
- `-t`: response timeout in seconds.

### Exit Codes

`pg_isready` returns exit codes for script handling:

| Exit Code | Meaning |
|---:|---|
| `0` | Server is accepting connections |
| `1` | Server is rejecting connections, e.g., during startup or shutdown |
| `2` | No response from server |
| `3` | No connection attempt made, usually due to invalid parameters |

Shell example:

```bash
if pg_isready -h db.internal -p 5432 -d appdb -t 3; then
  echo "PostgreSQL accepts connections"
else
  status=$?
  echo "PostgreSQL is not ready; pg_isready exit=$status"
  exit 1
fi
```

### Limitations of `pg_isready`

`pg_isready` does not prove that a role can log in successfully or execute queries. The server can report accepting connections even if the supplied username, database, or password is wrong; failed attempts may appear in server logs as authentication errors. This tool does not replace a SQL query executed under the application account.

Thus, `pg_isready` can be used for quick server and network checks, while application readiness needs deeper verification via the driver or `psql` with actual secrets and roles.

## 4. Testing Connections and SQL with the Actual Role

To confirm an application can work with PostgreSQL, execute a lightweight query over the same connection path, database, role, and TLS configuration that the application uses.

Example with `psql`:

```bash
psql "$DATABASE_URL" \
  -X \
  -v ON_ERROR_STOP=1 \
  -c 'SELECT 1;'
```

`-X` ignores the user's `psqlrc` file, making script results less environment-dependent. `ON_ERROR_STOP` makes `psql` fail on statement errors. The `DATABASE_URL` variable should come from a secrets manager or protected runtime environment; never print connection strings containing passwords to logs.

A query providing additional diagnostic details:

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    pg_is_in_recovery() AS is_standby,
    current_setting('transaction_read_only') AS transaction_read_only,
    now() AS checked_at;
```

This query confirms the database, role, and recovery role of the server the client connected to. `pg_is_in_recovery() = true` generally indicates the instance is in standby/recovery mode. `transaction_read_only` shows the read-only state of the current transaction; do not infer from this single field alone that the entire system is writable.

### Checking from the Application

If the application uses JDBC, Npgsql, psycopg, or another driver, the readiness probe should go through that exact connection pool and driver. A `psql` command succeeding from a monitoring container does not prove the application can resolve DNS, fetch secrets, open connections, or borrow connections from its pool.

A readiness handler can borrow a connection from the pool, set a short timeout, run `SELECT 1`, verify the result, and return the connection to the pool. The handler should not open a brand-new connection on every call if the application already manages a pool.

## 5. Checking Required Privileges and Schemas

`SELECT 1` does not touch business tables or check privileges on the application schema. If the application needs to read `app.orders`, readiness can perform a lightweight query on that object:

```sql
SELECT id
FROM app.orders
ORDER BY id
LIMIT 1;
```

This query confirms the role can read the object and the object exists. If the table is empty, the query still succeeds with zero rows; that is usually sufficient for an accessibility check, though it does not confirm business data is present.

To check privileges explicitly, privilege functions can be used:

```sql
SELECT
    has_schema_privilege(current_user, 'app', 'USAGE') AS can_use_schema,
    has_table_privilege(current_user, 'app.orders', 'SELECT') AS can_read_orders;
```

For functions or sequences, use the corresponding privilege functions. Still, the best check remains an actual query through the driver because it tests privileges, schema resolution, data types, and the connection path simultaneously.

### Avoid Heavy Probes

Never run `COUNT(*)` on large tables, multi-table joins, or heavy reporting queries on every readiness check. Probes are called frequently and from many instances; a heavy health check can create load itself when the system is already overloaded. Prefer `SELECT 1`, metadata checks, or single-row indexed queries.

## 6. Checking Schema and Migration Versions

An application may connect successfully yet not be ready to serve because migrations have not run or the schema is at an incompatible version. Store migration versions in a management table, such as one managed by Flyway or Liquibase, or an application-controlled version table.

Simple version table example:

```sql
CREATE TABLE app.schema_version (
    component text PRIMARY KEY,
    version text NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT now()
);
```

Readiness can verify the minimum version required by the current application:

```sql
SELECT version
FROM app.schema_version
WHERE component = 'orders-service';
```

The application should compare versions according to defined rules rather than naive string comparisons if formats include multi-digit numbers or release branches. When using migration tools, read the tool's history table via its API or stable conventions rather than depending on internal structures that may change.

### Migrations When Multiple Application Replicas Start

Do not let every application replica run migrations independently at startup if the migration tool is not configured for locking/coordination. A typical deployment workflow runs migrations as a separate step, waits for completion, and only then routes traffic to the application version requiring the new schema.

For rolling deployments, favor backward-compatible changes: add columns or tables first, deploy applications capable of reading/writing both old and new schemas, backfill, shift traffic, and remove old structures afterward. Readiness must reflect the schema actually required by the running application version.

## 7. Checking Actual Read and Write Capabilities

Readiness must match the instance's role. A read-only API can be ready when read queries work; an order-creation API needs to confirm the write path works. Do not test writes on a read-only replica and mark the service unhealthy if that replica is meant strictly for reads.

### Read Probe

A read probe can query a key table using an indexed predicate:

```sql
SELECT id
FROM app.orders
WHERE id = $1;
```

In periodic health checks, avoid using an arbitrary ID if returning zero rows is treated as an error. A metadata query or a managed canary row can be used instead. If the goal is simply verifying `SELECT` privileges, an empty result can still count as success.

### Write Probe with Commit

To verify real commit capability, a dedicated canary table with a fixed key can be used. For example:

```sql
CREATE TABLE app.health_write_probe (
    probe_name text PRIMARY KEY,
    checked_at timestamptz NOT NULL,
    sequence_no bigint NOT NULL
);
```

A probing worker can execute an upsert:

```sql
INSERT INTO app.health_write_probe (
    probe_name,
    checked_at,
    sequence_no
)
VALUES ('orders-api', clock_timestamp(), 1)
ON CONFLICT (probe_name) DO UPDATE
SET checked_at = EXCLUDED.checked_at,
    sequence_no = app.health_write_probe.sequence_no + 1;
```

To verify commit capability, the statement must commit successfully. If the transaction is rolled back, the probe only confirms the statement can execute within a transaction, not that it can commit. Write probes must run using the role and connection path matching the write application.

Do not run write probes too frequently from every replica. They generate WAL, update tuples and indexes, and may fire triggers or replicate. Use a centralized probe writer or longer intervals, and separate them from readiness endpoints called continuously by load balancers.

### Why Rollback Does Not Prove Commit Capability

Rolling back a transaction confirms permissions and part of the execution path, but does not verify transaction commit success, WAL flushes, or required synchronous commit policies. When verifying commit capability is required, use a committed canary write with controlled data and frequency.

## 8. Checking Primary and Standby Roles

In streaming replication architectures, applications need to know whether an endpoint points to the primary or a standby. The primary accepts writes; hot standbys serve read-only queries.

```sql
SELECT pg_is_in_recovery() AS is_standby;
```

If a write endpoint accidentally points to a standby, the application will receive errors on writes. If a read endpoint is designed strictly for replicas, `is_standby = true` is the expected state. Therefore, compare the result against the endpoint's intended role.

Do not hard-code a rule like "`is_standby` must be false everywhere." In systems with a primary and multiple replicas, readiness must know whether the checked service is a writer, reader, or backup node.

### Checking Read-Only Transactions

```sql
SHOW transaction_read_only;
```

A value of `on` indicates the current transaction is read-only. On standbys, transactions are normally read-only. On a primary, a session or transaction can still be set read-only via configuration, connection options, or `SET TRANSACTION READ ONLY`. Check the exact session the application uses.

## 9. Checking Replication Lag

A replica may accept connections and run queries while its data has lagged past acceptable business thresholds. Reader readiness may need a lag ceiling, such as a few seconds for near-real-time dashboards or a few minutes for less freshness-sensitive reports.

### On the Standby

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_transaction_at,
    now() - pg_last_xact_replay_timestamp() AS time_since_last_replay;
```

`pg_last_xact_replay_timestamp()` reports when the last transaction was replayed. `now() - timestamp` is not always exact replication lag: if the primary has no new transactions, the value grows even when the replica is caught up; if no transaction has replayed yet, the timestamp may be `NULL`. Combine with LSNs or a system-emitted heartbeat when accurate lag measurement is needed.

### On the Primary

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Lag columns in this view reflect recent delays across WAL send/write/flush/replay stages; they may become `NULL` when the system is idle or lacks recent samples. Do not naively interpret a `NULL` value as a broken replica.

### Heartbeats for Measuring Freshness

A more reliable method for business requirements is writing a periodic heartbeat on the primary:

```sql
CREATE TABLE ops.replication_heartbeat (
    heartbeat_name text PRIMARY KEY,
    updated_at timestamptz NOT NULL
);

INSERT INTO ops.replication_heartbeat (heartbeat_name, updated_at)
VALUES ('primary', clock_timestamp())
ON CONFLICT (heartbeat_name) DO UPDATE
SET updated_at = EXCLUDED.updated_at;
```

Readers read the timestamp on the replica and compute lag against current time. Heartbeats must be written frequently enough, use synchronized clocks, and replicate through the same mechanism being monitored. If the publisher stops writing heartbeats, results can no longer distinguish replica lag from an idle primary; the monitor must track source heartbeat health.

Replica readiness can return `not ready` if lag exceeds a configured threshold. However, be careful not to pull all replicas out of the load balancer simultaneously during a traffic spike. Separate warning thresholds and traffic-drain thresholds can be used.

## 10. Checking Connection Pools and Connection Limits

PostgreSQL enforces connection limits. A server may accept new connections while the application still cannot obtain one because its pool is exhausted or the pooler cannot allocate a backend session. Application readiness should verify borrowing a connection from the pool, not merely opening a fresh socket.

### Observing Connections on PostgreSQL

```sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS connections
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, application_name, state
ORDER BY connections DESC;
```

Compare current sessions against `max_connections`:

```sql
SELECT
    current_setting('max_connections')::integer AS max_connections,
    count(*) FILTER (
        WHERE backend_type = 'client backend'
    ) AS client_connections
FROM pg_stat_activity;
```

This is a point-in-time snapshot; connection counts can change immediately afterward. Certain connections are reserved for administrative roles or replication depending on version and settings. Do not set readiness thresholds solely by checking `count = max_connections`; track trends, per-role connections, and application-side pool waits.

### Checking at the Pool Side

Metrics to track:

- Total connections in the pool and connections currently in use.
- Idle connections immediately available.
- Requests waiting to borrow a connection.
- Average and p95/p99 wait times to acquire a connection.
- Timeouts when acquiring connections.
- New connection creations, resets, or broken connection evictions.

If the pool is exhausted, readiness should reflect that the instance cannot safely take more work. However, do not return `not ready` simply because one brief request waited a few milliseconds for the pool; use thresholds and hysteresis to prevent flapping.

### PgBouncer and Connection Proxies

If the application connects through PgBouncer or a similar proxy, check both the pooler and the PostgreSQL backend. The pooler may be up yet have no server connections available; PostgreSQL may be healthy yet the pooler cannot serve clients. Under transaction pooling, session-dependent features like temporary tables, session-level `SET`, session advisory locks, or prepared statements must be evaluated per pooler version and configuration.

## 11. Checking Locks and Blocked Queries

A database may accept queries while most sessions are blocked on locks. A readiness probe running `SELECT 1` can return quickly while business transactions pile up behind a hot table lock.

Check waiting sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 250) AS query_sample
FROM pg_stat_activity
WHERE wait_event_type = 'Lock'
ORDER BY query_start;
```

To identify blockers, use `pg_blocking_pids(pid)`:

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_application,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_application,
    now() - waiting.query_start AS waiting_for,
    left(waiting.query, 200) AS waiting_query,
    left(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(pg_blocking_pids(waiting.pid)) AS blocked_by(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = blocked_by.pid;
```

Health checks should not scan and analyze the full lock graph on every request. These are monitoring queries to run periodically or when latency spikes are detected. Readiness can use aggregate metrics such as sessions waiting on locks beyond a threshold rather than running deep lock queries continuously.

## 12. Checking Real Query Serviceability

`SELECT 1` tests only a tiny slice of the execution path. A service may depend on queries across multiple tables, functions, views, or extensions. Pick one or two representative queries with tightly bounded cost.

Readiness example for an order service:

```sql
SELECT o.id
FROM app.orders AS o
WHERE o.status = 'open'
ORDER BY o.created_at DESC
LIMIT 1;
```

If this query uses an appropriate index, it exercises the schema, privileges, and an access path close to the application. Ensure predicates and indexes prevent the probe from becoming expensive as data grows.

For APIs with many routes, readiness does not need to test every endpoint. Select the mandatory dependencies needed for most requests. A failure in a secondary reporting subsystem should probably not pull the order-writing API out of traffic if reporting is not on the transaction path.

### Checking Functions or Extensions

If the application depends on a function or extension, run a corresponding lightweight call. For example:

```sql
SELECT app.normalize_order_code('health-probe');
```

Use only side-effect-free functions. If a function writes data, makes network calls, or locks tables, do not run it in frequent readiness checks. Verify function existence, `EXECUTE` privileges, and extension versions per application requirements.

## 13. Checking Transactions and Durability

A successful read query does not guarantee all transaction types can commit. For write workloads, serviceability can depend on WAL, synchronous commit, disk space, write permissions, and storage health.

### Verifying Commits with a Canary

A canary write like the `health_write_probe` table earlier confirms a small transaction can commit through the write path. To be meaningful, it must use the same endpoint, role, pool, and synchronous configuration as the application. Never write into real business tables for health checks.

### Do Not Test Durability with Rolled-Back Transactions

A `BEGIN; INSERT; ROLLBACK;` transaction does not test commit or durability of committed data. It may help test privileges or transactional triggers, but does not replace a committed canary transaction.

### Monitoring WAL and Storage

Conditions like full filesystems, inability to write WAL, prolonged `archive_command` failures, or replication slots retaining WAL can degrade serviceability. Health monitoring must track filesystem space for the data directory and `pg_wal`, WAL growth rate, checkpoint/archive errors, and backup status. Do not run queries reading OS files from the database as routine checks; use host-level monitoring agents to observe capacity and I/O.

## 14. Timeouts and Low-Overhead Probe Design

Every probe needs a timeout shorter than the timeout of the system calling it. If the load balancer waits 10 seconds while the SQL probe has no timeout, a stall can tie up many health check requests and exhaust workers.

Practical design typically includes:

- Short connection timeout, e.g., 1–3 seconds depending on network.
- Dedicated `statement_timeout` for probes, e.g., 1 second.
- Few retries with backoff.
- A failure-persistence window before removing an instance to prevent flapping.
- Very short caching of probe results if multiple systems call the same endpoint.
- Concurrency caps on monitoring queries.

You can set timeouts for the check session:

```sql
SET statement_timeout = '1s';
SET lock_timeout = '250ms';
SELECT 1;
```

`statement_timeout` bounds total statement duration. `lock_timeout` bounds lock wait time. Routine probes should not need application locks; if blocked on a lock, a timeout is a useful signal that the system is not serving well.

Set timeouts in the connection string or driver configuration when needed from connection establishment. When using pools, reset session state or configure at the role/database level to avoid affecting other requests sharing the connection.

## 15. Designing Health Endpoints in Applications

A service can expose separate endpoints:

| Endpoint | Contents | Caller |
|---|---|---|
| `/live` | Checks process and processing loop | Orchestrator |
| `/startup` | Checks whether app init, config, and migrations finished | Orchestrator |
| `/ready` | Checks whether new requests can be served via pool and required dependencies | Load balancer/orchestrator |
| `/health/details` | Detailed metrics and status with access control | Monitoring/operators |

Public endpoints should return high-level status without exposing internal hostnames, database names, SQL, usernames, or stack traces. Detailed endpoints must be protected by authentication and administrative networks.

### JSON Response Example

```json
{
  "status": "ready",
  "checks": {
    "postgres_connection": "ok",
    "schema_version": "ok",
    "connection_pool": "ok"
  },
  "checked_at": "2026-11-14T08:00:00Z"
}
```

Include only necessary details in responses. Never return connection strings, secrets, user data, or full SQL errors on public endpoints.

### Readiness Logic Example

```text
function readiness():
    if application_is_shutting_down:
        return NOT_READY

    connection = pool.acquire(timeout = 1 second)
    if acquisition_failed:
        return NOT_READY

    try:
        set_local_statement_timeout(connection, 1 second)
        row = execute(connection, "SELECT 1")
        if row != 1:
            return NOT_READY

        schema = execute(connection, "SELECT required_schema_version()")
        if schema is incompatible:
            return NOT_READY

        if this service requires a writer:
            if execute(connection, "SELECT pg_is_in_recovery()") is true:
                return NOT_READY

        return READY
    catch timeout_or_database_error:
        return NOT_READY
    finally:
        release(connection)
```

This is pseudocode. `required_schema_version()` is an illustrative name; in real applications, use your existing version table or migration API. Do not create a new database function just for a health check example if unnecessary.

## 16. Configuring Probes in Kubernetes

Kubernetes distinguishes startup, liveness, and readiness probes. For PostgreSQL running in a StatefulSet, `pg_isready` can check container-level connection acceptance, while SQL and replication/role checks should be added at the appropriate monitoring layer.

Illustrative example for a PostgreSQL container:

```yaml
startupProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 60

livenessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3

readinessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432 -d postgres
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

This is only a baseline configuration illustrating the mechanism. Using the exact same `pg_isready` for all three probes does not fully evaluate application serviceability. For database clusters with failover, readiness must understand node roles and never cause restart loops while the server is recovering. Combine operators/cluster managers with architecture-appropriate probes.

For applications connecting to PostgreSQL, readiness should call an application endpoint that checks through its connection pool. Startup probes can wait for migrations or warm-up. Liveness should not fail simply because PostgreSQL temporarily lost connectivity, if restarting the application cannot fix the root cause and will only add reconnection pressure.

## 17. Readiness During Failover and Primary Switchover

In clusters with failover, the old node may become a standby and a new node is promoted to primary. Applications must switch to the writer endpoint or service discovery pointing to the new primary.

A readiness workflow for a writer can check:

1. Connect through the current writer endpoint.
2. `pg_is_in_recovery()` returns `false`.
3. Application role can execute required write queries.
4. Schema is compatible with the application version.
5. Connection pool has evicted old connections and established fresh ones.

Do not rely on a fixed IP if the cluster manager uses virtual IPs, DNS, or proxies to switch primaries. DNS caches and connection pools can retain stale addresses; configure TTLs, reconnection, and transaction error handling during failover.

In-flight transactions may be severed during failover. Applications must distinguish transient connection errors from business errors, and retry transactions only safely. A write may have committed on the old primary before the client received a response; blind retries can create duplicate data. Use idempotency keys or business constraints to protect operations.

## 18. Readiness for Read Replicas

Replicas serving reads require specific checks:

- `pg_is_in_recovery()` must return `true` if the endpoint is designed for standbys.
- The replica must be receiving and replaying WAL.
- Lag must not exceed the workload's threshold.
- Queries must not suffer prolonged recovery conflicts or frequent cancellations.
- Schema on the replica must be compatible with the reading application.
- Connection pools and read resources must retain sufficient capacity.

Readiness should not demand the replica match the primary at every instant if the architecture accepts eventual consistency. Traffic sensitive to freshness can be routed to the primary, while reporting accepts replicas within lag limits. A replica lagging past threshold can be drained from the reader pool while other replicas continue serving.

If using logical replication instead of physical streaming replication, check subscription status, workers, and apply lag per table/stream. A subscription may be active while a specific table has not finished initial synchronization.

## 19. Readiness for ETL, CDC, and Background Workers

ETL workers do not necessarily serve HTTP traffic, yet still require health status. Key conditions may include:

- Connecting to source and destination via runtime credentials.
- Reading required source schemas/tables.
- Writing to staging or destination targets.
- Valid watermarks/offsets capable of advancing.
- Replication slot/CDC stream still exists and does not retain WAL beyond limits.
- Most recent run completed within SLA.
- No backlog or dead-letter queue exceeding thresholds.

A worker processing a long batch should not be marked unhealthy merely because it has not finished in a few seconds. Health checks should distinguish process heartbeats from progress heartbeats. A worker that is alive yet makes no progress for a long time may need alerting or marking as degraded.

For CDC, checking that a slot is `active` does not prove the consumer is processing properly. Track LSN/offsets, latest event timestamps, ingest/apply rates, schema errors, and WAL retention. For batch jobs, track watermarks and processed row counts.

## 20. Classifying Failures and Appropriate Responses

Not every health check failure should trigger a restart. Responses must match the root cause.

| Condition | Potentially Failing Layer | Appropriate Typical Response |
|---|---|---|
| Application process hung | Application liveness | Restart application after confirmation threshold |
| PostgreSQL recovering | Database startup/readiness | Wait for recovery; do not restart repeatedly |
| Temporary DNS or network error | Network | Retry with backoff; alert if prolonged |
| Expired/wrong password | Authentication | Fix secret/rotation; avoid aggressive retries |
| Role lacks table privileges | Authorization/schema | Fix migration or grants; deploy in proper order |
| Pool exhausted | Application capacity | Shed load, fix connection leaks, or scale pool carefully |
| High replica lag | Replication | Drain replica from freshness-sensitive traffic; investigate WAL/replay |
| Rising lock waits | Database workload | Find blockers and long transactions; do not restart DB arbitrarily |
| Disk nearly full | Host/storage | Free or expand capacity per runbook |
| Incompatible migration | Deployment | Keep traffic on compatible version; complete migration |

A readiness endpoint should return only general status and reason. Internal monitoring systems should record details so operators can diagnose root causes.

## 21. Preventing Cascading Effects from Health Checks

When a database experiences an incident, all application replicas may simultaneously open new connections and run probes. If health checks run too frequently, they create a connection storm and worsen the outage.

Load-reduction principles:

- Use the existing pool for application probes instead of opening a new connection each time.
- Set timeouts and cap retry attempts.
- Add jitter so replicas do not run probes at the exact same instant.
- Avoid full scans, heavy aggregates, or heavy joins.
- Do not run write probes from every instance at high frequency.
- Do not call detailed endpoints continuously from public load balancers.
- Use circuit breakers to limit requests to failing dependencies.
- Distinguish transient errors from configuration errors needing intervention.

If all application instances mark themselves not-ready at once, the load balancer may have zero backends left. Design rollouts and failovers to maintain sufficient capacity, and alert before all instances are pulled from traffic.

## 22. Securing Health Endpoints and Health Data

Health checks are often called by orchestrators or load balancers. Public endpoints should avoid leaking details that expose infrastructure structure.

Do not expose:

- Passwords, tokens, connection strings, or secret contents.
- Internal hostnames, management IPs, and detailed topology unnecessarily.
- Full SQL statements that may contain sensitive input values.
- Usernames, emails, or customer data.
- Stack traces and detailed error messages to untrusted callers.

Internal logs may record error codes, correlation IDs, database roles, and probe durations, with data masking and access control. Detailed endpoints should be restricted to management networks or require authentication.

## 23. Periodic SQL Health Check Templates

The following queries can be used in internal monitoring dashboards. Run them with a role granted required statistics privileges and adapt to your PostgreSQL version.

### Instance Overview

```sql
SELECT
    version() AS server_version,
    current_database() AS database_name,
    current_user AS checked_as,
    pg_is_in_recovery() AS is_standby,
    current_setting('max_connections') AS max_connections,
    now() AS checked_at;
```

### Database Health

```sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

Counters are cumulative since the last statistics reset. To measure rates of change, take two samples over time and compute deltas; never treat cumulative totals as instantaneous rates.

### Sessions and Wait States

```sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
```

### Replication Slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Combine these queries with host-level metrics for `pg_wal` capacity, CPU, memory, and I/O. SQL probes alone cannot fully observe filesystem or storage device health.

## 24. Two-Layer Shell Health Check Script Example

The script below illustrates a fast server check via `pg_isready`, followed by a SQL query via `psql`. It assumes `DATABASE_URL` is supplied securely in the runtime environment.

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be configured}"

if ! pg_isready -d "$DATABASE_URL" -t 2 >/dev/null; then
  echo "database server is not accepting connections" >&2
  exit 1
fi

psql "$DATABASE_URL" \
  -X \
  -v ON_ERROR_STOP=1 \
  -c "SET statement_timeout = '1s'; SELECT 1;" \
  >/dev/null

echo "database SQL probe succeeded"
```

The script does not print credentials. If `DATABASE_URL` contains a password, protect the process environment and avoid enabling shell tracing (`set -x`). In production, prefer `PGPASSFILE` with strict file permissions or the platform's secret integration; never hard-code passwords into scripts.

`pg_isready` and `psql` are two distinct checks. The first checks whether the server accepts connections; the second verifies authentication and SQL execution. The application still needs readiness through its own driver/pool to validate the final serving path.

## 25. Testing Health Checks Before Deployment

Health checks must be tested both when the system is healthy and under controlled faults in staging.

1. **Database ready:** `pg_isready` and SQL probe succeed.
2. **Server starting up:** probes distinguish rejecting connections from no response.
3. **Wrong password:** SQL probe fails; logs do not leak secrets.
4. **Missing SELECT privilege:** query on application table fails and returns an appropriate reason.
5. **Old schema:** readiness refuses traffic if schema version is incompatible.
6. **Pool exhausted:** readiness reflects connection acquisition capability and honors timeouts.
7. **Primary becomes standby:** writer readiness detects `pg_is_in_recovery()` and stops accepting writes.
8. **Replica lag:** reader readiness enforces freshness thresholds accurately.
9. **Lock contention:** monitoring detects long waits without probes creating excessive load.
10. **Database recovers:** service returns to ready automatically after the dependency recovers, without a restart loop.
11. **Failover:** pool drops stale connections, connects to the new endpoint, and safely retries eligible operations.
12. **Controlled shutdown:** readiness flips to not-ready before the process stops so new requests stop arriving.

Also measure probe execution time and call frequency to verify health checks do not become a noticeable workload.

## 26. Operations Checklist

- [ ] Defined liveness, startup, and readiness separately for each component.
- [ ] Used `pg_isready` appropriately and handled its exit codes.
- [ ] Executed SQL probes using actual roles, databases, TLS, and connection paths.
- [ ] Verified minimum privileges and schemas required by the application.
- [ ] Checked migration versions against compatibility contracts.
- [ ] Checked writers and readers according to expected roles.
- [ ] Defined clear thresholds and actions for replica lag.
- [ ] Instrumented connection pools with acquire wait, timeout, and connection metrics.
- [ ] Tested write capability only with controlled canary writes when truly necessary.
- [ ] Configured probe timeouts, bounded retries, and avoided heavy queries.
- [ ] Ensured public endpoints do not leak secrets or internal details.
- [ ] Rehearsed startup, outages, failover, recovery, and shutdown.
- [ ] Attached alerts to runbooks and designated owners.

## 27. PostgreSQL References

- PostgreSQL Documentation — `pg_isready`: https://www.postgresql.org/docs/current/app-pg-isready.html
- PostgreSQL Documentation — Server Administration: https://www.postgresql.org/docs/current/admin.html
- PostgreSQL Documentation — System Information Functions: https://www.postgresql.org/docs/current/functions-info.html
- PostgreSQL Documentation — Monitoring Database Activity: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — Warm Standby and Streaming Replication: https://www.postgresql.org/docs/current/warm-standby.html
- PostgreSQL Documentation — Hot Standby: https://www.postgresql.org/docs/current/hot-standby.html
- PostgreSQL Documentation — Connection Settings: https://www.postgresql.org/docs/current/runtime-config-connection.html
- PostgreSQL Documentation — Client Authentication: https://www.postgresql.org/docs/current/client-authentication.html
- PostgreSQL Documentation — `pg_stat_activity` and Statistics Views: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL Documentation — `pg_stat_replication` and Replication Slots: https://www.postgresql.org/docs/current/view-pg-stat-replication.html

Health checks are valuable when they accurately reflect the capabilities a service needs to serve users. Combine server, SQL, privilege, schema, pool, primary/standby role, and data-freshness checks tailored to each workload; bound probes with timeouts and low cost; and use deep monitoring to detect lock, WAL, storage, and latency issues. This approach separates a merely running process from a PostgreSQL instance truly ready to serve.
