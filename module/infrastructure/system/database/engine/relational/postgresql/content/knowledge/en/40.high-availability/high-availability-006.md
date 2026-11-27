# Write and Read Connection Routing and Connection Pool Refresh

In a PostgreSQL system with a primary and one or more standbys, applications must send write operations to the primary while optionally distributing eligible read queries to standbys to increase serving capacity and offload work. This routing must coordinate with the connection pool: pools hold open connections for long periods, whereas server roles, endpoint addresses, failover state, and replication lag can change.

A well-functioning architecture must answer three questions:

1. **Which connections accept writes and which accept reads?** Classify by transaction semantics, not merely by looking at the `SELECT` keyword.
2. **When is a read allowed to run on a replica?** Consider replication lag, read-after-write consistency, and requirements for the freshest data.
3. **How does the pool drop old connections and open new ones?** There must be health checks, connection lifetimes, DNS refresh, eviction, controlled retries, and a drain procedure during failover.

This lesson covers routing patterns at the application, proxy, and driver layers; designing write/read endpoints; using PgBouncer and PostgreSQL connection parameters; pooling modes; refreshing pools after failover or endpoint changes; as well as monitoring, troubleshooting, and runbooks. The focus is PostgreSQL in a high-availability environment, where routing and connection lifecycle directly impact application correctness.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a primary endpoint, read endpoint, standby endpoint, and pooler endpoint.
2. Design write/read routing at the application or proxy layer.
3. Classify transactions by read-only/write semantics.
4. Handle read-after-write and stale reads caused by asynchronous replication.
5. Understand health checks for distinguishing a primary from a standby.
6. Use libpq connection parameters such as `target_session_attrs`.
7. Explain session, transaction, and statement pooling.
8. Choose appropriate pool sizes, connection lifetimes, and timeouts.
9. Refresh connection pools after failover, DNS changes, or certificate rotation.
10. Drain connections safely and prevent pools from continuing to use old endpoints.
11. Design retries/idempotency when connections drop mid-transaction.
12. Monitor pool saturation, replication lag, routing distribution, and connection errors.
13. Build runbooks and test routing/failover using realistic scenarios.

> **Version note:** Examples use common PostgreSQL and PgBouncer setups. Syntax, pooling features, and health-check commands depend on the version/tool. Java, .NET, Go, Python drivers, and frameworks have different APIs; always verify the documentation for your exact version before putting configurations into production.

## 2. Why Must Reads and Writes Be Routed?

In physical replication, the primary accepts writes and generates WAL; standbys receive and replay WAL. A standby can serve read-only queries when hot standby is active. If all queries go to the primary, standbys do not help offload reads. If writes are mistakenly sent to a standby, PostgreSQL rejects them because the standby is in recovery/read-only mode.

Basic model:

```text
                     Application
                          |
                    Routing layer
                     /         \
              WRITE endpoint   READ endpoint
                    |               |
                    v               v
               PostgreSQL        PostgreSQL
                PRIMARY           STANDBY
                    |               ^
                    +---- WAL ------+
```

### Benefits of Read Routing

- Offload part of the `SELECT` workload from the primary.
- Use multiple replicas to increase read throughput.
- Isolate analytics/reporting workloads from write transactions.
- Leverage a standby in another region for certain reads closer to users.

### Costs and Limitations

- Replicas can lag behind the primary.
- Read-after-write is not guaranteed automatically.
- Failover can change server roles.
- Each endpoint/pool has its own connection budget.
- Incorrect query routing can make transactions inconsistent.

Read scaling is a conditional optimization; not every read query is suitable for running on a replica.

## 3. Common Endpoints

| Endpoint | Purpose | Expected behavior |
|---|---|---|
| Primary/write endpoint | Write transactions and reads needing the latest data | Always points to the current primary |
| Read endpoint | Read queries that can tolerate lag | Distributes to healthy standbys |
| Per-replica endpoint | Targets a specific standby | Used for dedicated workloads/regions |
| Pooler endpoint | Accepts client connections and allocates server connections | Decouples client lifecycle from PostgreSQL sessions |
| Admin endpoint | Migrations, monitoring, failover operations | Restricted access, not shared with the app pool |

### An Endpoint Is Not Necessarily a Single Server

A DNS name, VIP, load balancer, or proxy can represent a group of PostgreSQL nodes. The endpoint is only a connection address; the component behind it must determine which node is currently primary or standby.

### Do Not Use a Single Read-Write Endpoint Without Role Awareness

If a load balancer distributes all TCP connections randomly across primary and standbys, applications can send writes to a standby or reads requiring the freshest data to a lagging replica. Routing must know the role and policy of each node.

## 4. Layers Where Routing Can Be Implemented

### Application-Side Routing

The application maintains two data sources/pools: a write pool pointing to the primary endpoint and a read pool pointing to the read endpoint. The application/service layer chooses the pool based on transaction intent.

Pros:

- Business logic knows whether a transaction requires read-after-write.
- Easy to bind consistency policies to each use case.
- Can pin a transaction to the same connection.

Cons:

- Every service must implement routing properly.
- Risk of inconsistent logic across applications.
- Requires operating multiple pools/endpoints.

### Proxy-Side Routing

A proxy accepts connections/queries and forwards them to PostgreSQL nodes. Some proxies can inspect node roles and route according to rules; SQL classification, transaction handling, and session-state support depend on the product.

Pros:

- Centralizes routing and health checks.
- Can provide stable endpoints for multiple applications.
- Can abstract away topology changes.

Cons:

- The proxy becomes a critical component requiring HA/monitoring.
- Query classification can misfire on stored procedures, functions, or multi-statement transactions.
- Session semantics and prepared statements may be restricted.

### Driver/Connection String Routing

Some drivers can try multiple hosts and pick a server based on target session attributes. This is useful for picking a node when opening a connection, but typically does not classify individual SQL statements after the connection is established.

## 5. Routing by Transaction Semantics

Do not classify a query solely by checking whether the SQL starts with `SELECT`. A `SELECT` can call a function with side effects, advance a sequence, or depend on session state. A transaction may read first and write later.

Practical classification:

| Workload type | Suitable endpoint |
|---|---|
| `INSERT`/`UPDATE`/`DELETE`/`MERGE` | Primary |
| DDL and migrations | Primary |
| `SELECT` that must see a just-committed write | Primary or a replica that has replayed up to the commit LSN |
| `SELECT` accepting eventual consistency | Standby |
| Reporting/analytics that can tolerate lag | Designated standby |
| Read-then-write transaction | Primary from the start of the transaction |
| Advisory locks/session state tied to writes | Typically primary with session affinity |

### Safety Rule

If a transaction has any chance of writing, choose the primary right from the beginning and keep the same transaction/connection. Never start on a replica and switch mid-transaction to the primary; transaction snapshots and locks do not migrate across connections.

### SELECT Is Not Always Read-Only

A `SELECT` can invoke a function that modifies data or sequences. Hot standby blocks many write operations, yet the routing layer should not rely on SQL prefixes to judge transaction safety. Use application intent, read-only transaction semantics, and function testing.

## 6. Separating Read Pool and Write Pool in Applications

An application can declare two data sources:

```text
WriteDataSource
  jdbc:postgresql://pg-primary.service:5432/appdb
  maxPoolSize: 20

ReadDataSource
  jdbc:postgresql://pg-read.service:5432/appdb
  maxPoolSize: 40
```

This is an illustrative example, not a default configuration. Pool sizes must be based on total application instances, workers, and the PostgreSQL/PgBouncer connection budget.

### Routing at the Service Layer

```java
public Order createOrder(CreateOrderCommand command) {
    return writeTransaction.execute(status -> {
        Order order = orderRepository.insert(command);
        auditRepository.insert(order.id(), "CREATED");
        return order;
    });
}

public OrderView getOrder(long orderId) {
    return readRepository.findViewById(orderId);
}
```

The service explicitly knows `createOrder` is a write transaction and `getOrder` is a read use case. If an endpoint needs to read immediately after creating an order, that use case needs primary routing or a consistency token rather than defaulting to the read pool.

### Do Not Let Repositories Choose Arbitrarily

A clear convention such as `ReadRepository`/`WriteRepository` or transaction annotations makes routing intent visible to reviewers. Avoid letting each method guess the endpoint from SQL names.

## 7. Transaction Pinning and Connection Affinity

A transaction must run on one connection from `BEGIN` to `COMMIT`/`ROLLBACK`. If a transaction starts on the primary, every statement within that transaction must stay on that same primary connection.

Example:

```sql
BEGIN;

UPDATE public.account
SET balance = balance - 100
WHERE account_id = 1;

SELECT balance
FROM public.account
WHERE account_id = 1;

COMMIT;
```

The `SELECT` in this transaction must read from the same primary transaction to see its own uncommitted change. Never route that `SELECT` to a standby.

### Autocommit and Multi-Statement Flows

In autocommit mode, each statement can be a separate transaction. However, a multi-statement business workflow requiring atomicity must be managed as a single transaction and pinned to a write connection.

## 8. Read-After-Write Consistency

An asynchronous standby may not yet have replayed a transaction just committed on the primary. Example:

1. The application executes `INSERT` for an order on the primary.
2. The transaction commits successfully.
3. The application immediately executes `SELECT` for the order from the read endpoint.
4. The replica has not yet replayed the corresponding WAL, so the query does not see the order.

This is a stale read due to replication lag, not necessarily data loss.

### Options

- Read from the primary for a window of time after a write.
- Keep the request/session sticky to the primary.
- Wait for the replica to replay up to an LSN token before reading.
- Use synchronous replication with appropriate acknowledgement if durability/visibility requirements justify it.
- Design UX/API to accept eventual consistency and return newly written data directly from the write result.

### Do Not Use Fixed Sleep

Waiting 500 ms or 2 seconds does not guarantee the replica has caught up. Lag fluctuates with workload, network, and replay capacity. If consistency is required, use primary routing or an LSN-based wait with an explicit timeout.

## 9. LSN-Based Read-After-Write

PostgreSQL can compare LSNs on the primary and standby. After a transaction commits on the primary, the application can capture an LSN token at or after the commit point, then wait for the standby to replay up to that token.

Conceptual example on the primary after `COMMIT`:

```sql
SELECT pg_current_wal_lsn() AS consistency_lsn;
```

On the standby:

```sql
SELECT
    pg_last_wal_replay_lsn() >= '0/16B6C50'::pg_lsn
    AS replayed_to_target;
```

In the application, poll with a deadline/backoff and only read from the replica when the condition is met. The example LSN must be replaced by the actual token from the primary.

### Limitations

- The token must belong to the relevant timeline/history.
- If failover occurs, the new timeline must be handled and the consistency boundary re-established.
- An LSN token fetched after commit may include WAL from other transactions; that is safe, though it may wait slightly longer.
- On timeout, fall back to the primary or return a response per the consistency contract.

Never compare LSNs across independent clusters or incompatible histories.

## 10. Synchronous Replication and Read Visibility

Synchronous replication has multiple acknowledgement levels. `synchronous_commit=on` typically waits for the synchronous standby to flush WAL; `remote_apply` waits for the standby to replay the transaction before the primary reports commit success, when the synchronous standby is properly configured.

Illustrative configuration example:

```ini
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

A transaction can select:

```sql
SET LOCAL synchronous_commit = 'remote_apply';
```

### Do Not Equate Synchronous With Routing

Synchronous replication defines the wait level on commit. It does not automatically route application `SELECT`s to the specific standby that acknowledged, nor does it replace endpoints/health checks. With multiple standbys, you must identify which node satisfies the synchronous policy and which nodes the read endpoint may pick.

### Trade-Off

`remote_apply` can increase commit latency. Use it only when consistency/durability requirements justify the cost and failover behavior has been tested.

## 11. How Replication Lag Affects Read Routing

The read endpoint should select replicas that satisfy policy, for example:

- Connected and in recovery mode.
- WAL receiver active if using streaming.
- Replay lag below threshold.
- Not overloaded on CPU/I/O.
- Not experiencing prolonged pause/recovery conflicts.

### Byte Lag vs. Time Lag

LSN distance reflects the volume of un-replayed WAL bytes; timestamp lag reflects when the latest transaction was replayed. On an idle primary, the timestamp can look stale even when the replica is not actually lagging. Use multiple metrics rather than a single number.

### Lag Thresholds

Thresholds depend on the use case. Dashboards/reporting may tolerate several minutes; transaction status screens may require the primary or very low lag. Set thresholds according to the product's consistency contract.

## 12. Health Checks for Primary and Standby

An open TCP port or successful `SELECT 1` only proves the server accepts connections and simple queries. It does not determine whether the node is a primary or a replica.

Check role:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    current_setting('transaction_read_only') AS transaction_read_only;
```

A primary candidate normally has `pg_is_in_recovery() = false`; a standby normally has `true`.

### Checking True Writability

A primary may be out of recovery yet still configured read-only, or the user may lack write permissions. A health check can combine:

- `pg_is_in_recovery()`.
- `transaction_read_only`.
- Authentication using a health-check role with appropriate permissions.
- A lightweight non-mutating check or a dedicated probe table in controlled environments.

Avoid running `INSERT`/`ROLLBACK` probes on every health check if frequency is high and unnecessary.

### Read Endpoint Health

Ensure the node is in recovery/hot standby and replay progress is within threshold. A replica in recovery that is hours behind should not receive default reads.

## 13. Routing With libpq target_session_attrs

`libpq` supports `target_session_attrs` to select a host from a multi-host list based on session attributes. Example:

```text
host=pg1.internal,pg2.internal
port=5432
dbname=appdb
user=app_user
target_session_attrs=read-write
```

`read-write` requires a connection to a server that accepts read-write transactions. For clients needing a standby/read-only server, `read-only` or `standby` can be used depending on the driver/version and supported semantics.

### primary and standby Attributes

Values supported by `libpq` may include `any`, `read-write`, `read-only`, `primary`, `standby`, and `prefer-standby`; the exact set and behavior depend on version. Check the `libpq` documentation for the PostgreSQL version in use.

### Limitations

`target_session_attrs` chooses a server when creating a connection. It does not inspect individual queries to auto-route `SELECT`/`UPDATE` differently over an existing connection. An open connection stays bound to that node until closed/reconnected.

## 14. Multiple Hosts in a Connection String

A connection string can list multiple hosts for the client to try sequentially:

```text
host=pg-a.internal,pg-b.internal
port=5432,5432
dbname=appdb
user=app_user
connect_timeout=3
target_session_attrs=read-write
```

The driver tries the hosts and applies the target session attribute. This configuration is useful for finding the primary in a node list.

### Not Query Load Balancing

Once a host is chosen, the connection remains pinned to that host. To distribute read connections across multiple replicas, you need a separate endpoint/proxy/load-balancing strategy or an appropriate driver feature.

## 15. DNS and Stable Endpoints

A DNS name can point to a VIP, proxy, or endpoint updated by the HA manager on failover. Applications should use stable hostnames rather than hardcoding the IP of the current primary.

### DNS Caching

DNS record TTL does not guarantee every process switches IPs on time. The JVM, OS resolver, driver, pooler, or service mesh may cache DNS longer than the TTL. Connection pools keep open TCP sockets, so DNS updates do not automatically move existing sockets to another node.

### Design

- Use DNS/VIP/HA endpoints managed by the control plane.
- Set appropriate TTLs while understanding caching at each layer.
- Configure resolver/client caches intentionally.
- Combine with health checks and connection eviction.
- Never treat a DNS change as the entire failover process.

## 16. Read Load Balancing

Reads can be distributed across multiple standbys via:

- Round-robin at a proxy/load balancer.
- Weighted routing by capacity.
- Least-connections or queue-aware routing.
- Region-aware routing.
- Application selecting a replica by workload.

### What to Avoid

- Routing to replicas whose lag exceeds threshold.
- Pushing long reporting queries onto a replica serving low-latency APIs.
- Using identical weights for nodes with very different capacities.
- Lacking a fallback when all replicas are unhealthy.

### Weighted Example

If replica A has twice the capacity of replica B, you can try a 2:1 weight ratio and then tune based on actual CPU, I/O, active sessions, and query latency. Weights do not replace circuit breakers/health checks.

## 17. Routing With PgBouncer

PgBouncer is a connection pooler for PostgreSQL. It reduces server connection count by multiplexing connections across many client connections.

A common architecture uses two PgBouncer pools/endpoints:

```text
Application
   |                         |
   v                         v
pgbouncer-write          pgbouncer-read
   |                         |
   v                         v
primary endpoint         standby/read endpoint
```

PgBouncer itself primarily pools connections by database/user/pool mode; by default it does not parse every SQL statement and route per statement to primary/standby. Separate write/read endpoints or pair it with a role-aware routing layer.

### Two Listeners

You can run two PgBouncer services/configurations or place a proxy in front to expose two ports/hostnames. Each pool must have an appropriate backend and a clear failover update process.

## 18. PgBouncer Pooling Modes

| Mode | Server connection held until | Characteristics |
|---|---|---|
| Session | Client disconnects | Better session-state compatibility, less multiplexing |
| Transaction | Transaction ends | Many clients share server connections efficiently |
| Statement | Statement ends | Heavily restricted; no multi-statement transactions |

### Session Pooling

The client holds one server connection for the entire client session. Suitable for applications relying on session state, though multiplexing is lower.

### Transaction Pooling

The server connection is returned to the pool after each transaction. Improves connection-sharing efficiency, but session state is not guaranteed to persist across transactions of the same client.

### Statement Pooling

The server connection is returned after every statement. Unsuitable for multi-statement transactions and most typical applications.

## 19. Transaction Pooling and Session Features

In transaction pooling, avoid relying on:

- Session-level `SET` persisting across transactions.
- Temporary tables surviving across multiple transactions.
- Session-level advisory locks.
- Long-lived `LISTEN`/`NOTIFY` listener sessions.
- Cursors/portals living beyond a transaction.
- Session variables or state retained by extensions.
- Prepared statements if the pooler/version/config does not support the required semantics.

### Solutions

- Use `SET LOCAL` inside a transaction instead of session-level `SET` where appropriate.
- Set `search_path`/role/timezone in connection startup config supported by the pooler.
- Use session pooling for workloads requiring session affinity.
- Isolate dedicated listener/worker processes from the transaction pool.
- Test prepared statements according to your PgBouncer version and `max_prepared_statements`.

Do not switch to transaction pooling solely to reduce connections if the application depends on session state without modifying application code.

## 20. Illustrative PgBouncer Configuration

Example for a write endpoint:

```ini
[databases]
appdb = host=pg-primary.internal port=5432 dbname=appdb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
reserve_pool_size = 5
server_idle_timeout = 600
server_lifetime = 3600
server_connect_timeout = 5
server_login_retry = 5
```

This is an illustrative example, not a complete production file. You must configure authentication, TLS, admin users, `userlist`/`auth_query`, logging, DNS behavior, and security policies for your environment.

The read endpoint can have its own configuration/backend pointing to the read service. If a proxy/HA manager changes the backend after failover, the pooler must reload/reconnect/drain following a tested procedure.

## 21. PgBouncer Admin Console

PgBouncer provides an admin database to inspect pools/servers/clients and execute maintenance commands. Common commands include:

```sql
SHOW POOLS;
SHOW SERVERS;
SHOW CLIENTS;
SHOW STATS;
SHOW CONFIG;
```

Maintenance commands such as `RELOAD`, `PAUSE`, `RESUME`, `RECONNECT`, and `WAIT_CLOSE` have specific semantics. Check the PgBouncer documentation for your exact version before running them in production.

### Observe Before Changing

Record:

- Active/waiting client count.
- Active/idle/used server connections.
- Pool database/user mapping.
- Query/transaction wait times.
- Server lifetime/idle timeout.
- Current backend host/port.

Do not run `PAUSE`/`SUSPEND` during peak hours without understanding the impact on waiting requests and in-flight transactions.

## 22. PgBouncer RECONNECT, PAUSE, and RESUME

When the backend host or credentials change, PgBouncer provides admin commands to act on server connections:

- `RECONNECT`: instructs server connections of a database to be closed and recreated as appropriate for their usage state.
- `WAIT_CLOSE`: waits for server connections marked for closing to actually finish.
- `PAUSE`: waits for current queries/transactions to finish, then closes server connections of the database.
- `RESUME`: resumes accepting/serving after `PAUSE` or `SUSPEND`.
- `RELOAD`: reloads configuration from file.

Detailed semantics and command scope depend on version. Before running, consult PgBouncer documentation and test in staging. In particular, `PAUSE` can cause new requests to wait and hurt availability if prolonged.

### Example Backend Change Workflow

1. Confirm the new endpoint points to the primary/standby with the right role.
2. Verify credentials/TLS to the new backend.
3. Reload PgBouncer configuration if the file changed.
4. Run `RECONNECT` on the appropriate database to replace old server connections.
5. Monitor `SHOW SERVERS` and `SHOW POOLS`.
6. Confirm new connections land on the right backend.

Do not treat `RECONNECT` as a failover manager; it only refreshes pooler connections against the current backend configuration.

## 23. Pool Sizing and Connection Budget

Every PostgreSQL backend has a connection limit. The total connection budget must account for all application instances, workers, poolers, monitoring, migrations, replication, and admin access.

Example:

| Component | Count |
|---|---:|
| 8 application instances × write pool 10 | 80 |
| 8 application instances × read pool 20 | 160 |
| 2 workers × pool 10 | 20 |
| Monitoring/admin/migrations reserve | 20 |
| Total client-side connections | 280 |

Without pooler multiplexing, this figure can become the server connection count. With PgBouncer transaction pooling, server connections can be substantially lower, though they must still be calculated across database/user pools and workload concurrency.

### Do Not Set Max Pool Equal to max_connections

PostgreSQL needs headroom for autovacuum workers, replication, superuser-reserved connections, monitoring, and incident access. Application pool exhaustion must never lock administrators out of the database during an incident.

### Oversized Pools

- Increase memory/backend process overhead.
- Increase context switching.
- Worsen CPU, lock, and I/O contention.
- Can reduce throughput instead of increasing it.

Measure query concurrency, queue time, CPU, and latency before increasing pool size.

## 24. Calculating Server Connections Across Multiple PgBouncer Pools

PgBouncer typically creates a pool per database/user pair. A configuration with multiple database aliases or multiple users can spawn many independent pools.

Example:

- 3 databases.
- 5 database users.
- `default_pool_size = 20`.

The theoretical ceiling can reach 3 × 5 × 20 server connections if all pools are active simultaneously, before counting reserve pools and other limits.

### Capping the Total

Set `max_db_connections`/`max_user_connections` as appropriate to bound total backend connections. Verify option availability and semantics for your PgBouncer version.

## 25. Connection Acquisition Timeout and Queueing

An application pool may wait for a connection when all connections are busy. If the queue grows too long, request latency rises and threads/request workers are held up.

Timeouts to distinguish:

| Timeout | Limit |
|---|---|
| Pool acquisition timeout | Wait time to borrow a connection from the application pool |
| Connect timeout | Time to establish a TCP/PostgreSQL connection |
| Server login timeout | Time the pooler waits for backend login |
| Query timeout | Duration a query is allowed to run |
| Transaction timeout/deadline | Duration of the entire transaction/request |
| Idle timeout | Duration a connection sits idle before closing |

### Timeout Hierarchy

Design inner timeouts to finish before the overall request timeout. If a request deadline expires while the query keeps running, the connection can remain pinned in the pool and grow the backlog. Use appropriate cancellation/statement timeouts while understanding transaction rollback behavior.

## 26. Connection Lifetime and maxLifetime

Connection pools usually hold connections long-term to avoid connect/authentication/TLS overhead. However, indefinitely lived connections can stick to an old backend after DNS/failover changes or hit network middlebox idle timeouts.

Pool libraries may support:

- Maximum connection lifetime.
- Idle timeout.
- Keepalive/validation.
- Soft eviction/recycle.
- Connection test on borrow or background validation.

### Choosing Lifetime

Lifetime should be shorter than infrastructure limits that must be respected (such as server-side connection lifetimes or proxy maintenance windows), with jitter if the pool supports it to prevent all connections from expiring together.

### Avoiding Connection Churn

An overly short lifetime forces the pool to constantly open/close connections, increasing TLS/auth load and connection storms. Set lifetime based on measured connection stability and failover objectives.

## 27. Keepalive and Stale TCP Connections

A TCP connection can be severed by a network path without the client immediately noticing. TCP keepalive, driver socket timeouts, and pool validation help detect stale connections.

### Keepalive

TCP keepalive sends probes after a connection is idle long enough. OS/driver defaults vary; configure it at the right layer. Keepalive is not a health check for PostgreSQL role.

### Validation

A pool can validate a connection before lending it to a request or run background validation. The validation query should be lightweight; checking role/lag requires a separate probe if routing policy demands it.

### Do Not Validate Every Connection With Heavy Queries

Excessively frequent health checks can generate load on their own. Use minimal connection validation and cache health state at the routing layer for a reasonably short duration.

## 28. HikariCP: Common Properties

In Java applications using HikariCP, commonly tuned properties include:

| Property | Meaning |
|---|---|
| `maximumPoolSize` | Maximum number of connections in the pool |
| `minimumIdle` | Target number of idle connections |
| `connectionTimeout` | Wait time to acquire a connection |
| `idleTimeout` | Idle duration before a connection can be retired |
| `maxLifetime` | Maximum lifetime of a connection |
| `keepaliveTime` | Keepalive interval for idle connections |
| `validationTimeout` | Maximum time to validate a connection |

Illustrative example:

```properties
maximumPoolSize=20
minimumIdle=2
connectionTimeout=3000
idleTimeout=300000
maxLifetime=1500000
keepaliveTime=120000
validationTimeout=2000
```

Time units and constraints must be confirmed for your HikariCP version. These values only illustrate configuration; do not copy verbatim without measuring your workload.

### Read/Write Pools

You can create two independent `HikariDataSource` instances, one for the write endpoint and one for the read endpoint. Close/recreate or soft-evict connections using the version's API/lifecycle when endpoints change.

## 29. What Is Pool Refresh?

Refreshing a connection pool is the process of making an application stop using old connections and open new connections matching current endpoints, credentials, TLS certificates, or server roles.

Refresh may be needed when:

- Primary fails over to a new node.
- DNS/VIP/backend mapping changes.
- A standby is promoted or removed from the read pool.
- Credentials/passwords are rotated.
- TLS certificates/CAs are replaced.
- PgBouncer/backend configuration changes.
- Connections become stale or network paths stop working.

### Pool Refresh Does Not Mean Restarting the Application

Many pool libraries support soft eviction or closing idle connections, then creating new connections from datasource configuration. If the endpoint resides in an immutable config object, swap the datasource/pool in a controlled manner and drain the old pool.

## 30. How Does Failover Affect Connection Pools?

Suppose primary A fails and standby B is promoted:

```text
Before:
  write pool ---> Primary A
  read pool  ---> Standby B

Failover:
  A fenced / unavailable
  B promoted to primary

After:
  write pool ---> New primary B
  read pool  ---> Another healthy standby C
```

Existing connections to A do not automatically move to B. They may error out, hang until timeout, or keep talking to A if A was not fenced and remains alive.

### Role of Fencing

Before redirecting writes to B, the HA control plane must guarantee A does not continue accepting writes. Changing DNS or evicting pools alone does not prevent split-brain if the old primary stays writable.

### Endpoint Update

After promotion, update the primary endpoint via the HA manager/proxy/DNS and confirm health checks select only B. Then refresh the write pool. The read pool must remove B from the replica pool if B is now primary and add another standby per policy.

## 31. Refresh Sequence After Failover

A reference sequence:

1. Detect primary failure.
2. Execute fencing/STONITH or a mechanism ensuring the old primary is not writable.
3. Promote standby per HA orchestration.
4. Verify the new node is writable and on the new timeline.
5. Update the primary/write endpoint.
6. Update read endpoint membership; remove the newly promoted node from the standby list.
7. Instruct the pooler to reconnect or drain old backend connections.
8. Evict stale connections in application pools.
9. Open new connections and confirm they hit the right role.
10. Run smoke tests and gradually open traffic.
11. Rejoin/reseed the old primary per procedure.

### Do Not Refresh Too Early

If the pool shifts writes to the new node before promotion finishes, new connections may hit read-only/recovery errors. Wait for role verification and the HA manager state to transition to primary.

## 32. Soft Eviction and Hard Shutdown

**Soft eviction** marks existing connections so they are not reused once returned to the pool; in-flight requests can finish. **Hard shutdown** closes connections immediately, which can fail running queries/transactions.

### When to Soft-Evict

- DNS/backend changed while the old server still serves normally.
- Rotating credentials/TLS with an overlap window.
- Recycling connections per `maxLifetime`.
- Non-urgent read endpoint configuration changes.

### When Hard Close Is Necessary

- Old primary was fenced or endpoint was revoked.
- Credentials were compromised.
- TLS identity is no longer trusted.
- Connections point to a node no longer allowed to receive traffic.

Hard close can leave transactions with an unknown outcome at the client. A retry/idempotency policy must be in place.

## 33. Draining Connections Before Maintenance

Draining reduces new traffic to the old endpoint/pool, waits for in-flight work to finish, and then closes connections.

Procedure:

1. Stop granting new connections from the routing layer to the old backend.
2. Wait for in-flight transactions to finish within a deadline.
3. Monitor active clients/transactions.
4. Soft-evict idle/returned connections.
5. Close remaining ones per maintenance policy.
6. Confirm no traffic remains on the old backend.

### Long-Running Transactions

A long transaction can hold a connection without returning it to the pool. Set appropriate deadlines/`statement_timeout`/`transaction_timeout` and notify applications of the drain window.

Do not terminate sessions en masse without knowing which transactions they are running and the rollback impact.

## 34. Coordinating DNS Refresh and Connection Lifetime

When DNS changes from A to B:

- New connections may resolve B after caches expire.
- Already-open connections stay attached to A.
- The pool may continue lending old connections from its idle list.
- Drivers/JVMs may cache DNS longer than the record TTL.

### Strategy

- Use stable endpoints with role-aware routing.
- Bound DNS caching per environment/driver.
- Set `maxLifetime` so old connections get recycled.
- After failover, actively evict instead of waiting for lifetime expiry.
- Observe the backend address of new connections.

A short DNS TTL does not replace eviction; eviction does not replace fencing.

## 35. Refreshing After Password Rotation

When an application role's password is changed:

1. Determine when the new credential takes effect.
2. Update the secret manager/config for the new pool.
3. Verify new connections authenticate successfully.
4. Soft-evict or drain old connections per the overlap policy.
5. Confirm no processes still use the old password.
6. Revoke the old credential once no dependencies remain.

If server policy allows overlap using two roles/credentials, staged rotation can avoid downtime. Rotating a PostgreSQL role password directly does not automatically drop existing sessions; new connections require the new password.

## 36. Refreshing After TLS Certificate Rotation

TLS certificate/CA rotation can cause new connections to fail if the client trust store has not been updated or hostname verification no longer matches.

### Overlap Procedure

1. Update the trust store to trust the new CA first.
2. Deploy the new certificate to PostgreSQL/proxy.
3. Test TLS handshake and hostname verification.
4. Create new pool connections.
5. Drain connections using the old certificate per policy.
6. Remove the old CA/certificate after the overlap period ends.

### Existing Sessions

An established TLS session does not switch certificates mid-stream. Pool refresh establishes new handshakes to validate the new certificate.

## 37. Retries When Connections Drop

Connection failures can occur:

- Before a transaction begins.
- Between statements.
- During `COMMIT`.
- After the server commits but before the client receives acknowledgement.

The last case produces an **ambiguous outcome**: the client does not know whether the transaction committed.

### Do Not Retry Blindly

Retrying `INSERT`/charge/payment/order creation can create duplicates if the previous transaction already committed. You need:

- Idempotency keys or unique request IDs.
- Unique constraints preventing duplicates.
- Outbox/inbox patterns when integrating external systems.
- Querying transaction status by business key before retrying.
- Distinguishing connect-before-send errors from connection loss during commit.

### Retry Policy

Use bounded retries, exponential backoff, and jitter. Do not retry infinitely or retry every SQLSTATE. Some errors are permanent (authentication/permission/schema); others may be transient (connection failure/failover).

## 38. Common SQLSTATEs During Connections and Failover

| SQLSTATE | General meaning | Handling direction |
|---|---|---|
| `08000` | Connection exception | Check network/driver/pool |
| `08003` | Connection does not exist | Remove connection from pool |
| `08006` | Connection failure | Reconnect with backoff |
| `57P01` | Admin shutdown | Wait for HA/pooler to switch endpoint |
| `57P02` | Crash shutdown | Check node/HA state |
| `57P03` | Cannot connect now | Node not ready yet |
| `25006` | Read-only SQL transaction | Write may have routed to standby or read-only tx |
| `28P01` | Invalid password | Check credential rotation/secret |

SQLSTATE is a diagnostic signal, not the sole retry decision. Inspect transaction state, request idempotency, and the HA control plane.

## 39. Circuit Breakers and Fallbacks

A circuit breaker stops sending requests to a failing endpoint after crossing a failure threshold, then retries in a controlled manner.

### For the Write Endpoint

Never fall back writes to an arbitrary replica. Switch only when the HA control plane confirms the new primary is promoted and the old primary is fenced.

### For the Read Endpoint

If a standby lags/overloads, remove it from the read pool. If no healthy standby remains:

- Route some reads to the primary if capacity permits.
- Throttle/queue analytics workloads.
- Return errors/retries for requests with explicit consistency contracts.

Do not dump all read traffic onto the primary without a capacity guard.

## 40. Read Routing by Workload Class

Read endpoints can be split by workload class:

| Class | Replica/policy | Example |
|---|---|---|
| Low-latency reads | Replica near app, low lag | Product detail, profile |
| Read-after-write | Primary or LSN-wait | Just created/updated record |
| Reporting | Dedicated replica, capped query concurrency | Dashboards, reports |
| Analytics/batch | Separate replica or warehouse | Large scans, exports |
| DR validation | Standby/isolated restore | Recovery checks |

### Why Separate Reporting?

A long scan query can cause I/O pressure, cache eviction, and replay conflicts. Separating workloads keeps API read latency steadier and reduces impact on the primary.

## 41. Session State and Read Routing

A read query can depend on session settings:

- `search_path`.
- `TimeZone`.
- role/`current_user`.
- temporary objects.
- prepared statements.
- advisory locks.
- transaction isolation.

If requests move across pools/endpoints, state does not travel automatically. Set state in connection startup or transaction-local scope per policy.

### SET LOCAL

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SET LOCAL TIME ZONE 'UTC';
SELECT * FROM public.product WHERE product_id = 10;
COMMIT;
```

`SET LOCAL` ends with the transaction, making it a much better fit for transaction pooling than persistent session-level `SET`.

## 42. Connection Pool Metrics

Collect metrics across the application pool, PgBouncer, and PostgreSQL:

### Application Pool

- Active, idle, and total connections.
- Threads/requests waiting for a connection.
- Acquisition latency and timeout count.
- Connection creation/close rate.
- Connection lifetime/eviction count.
- Validation failures.

### PgBouncer

- Active/waiting client connections.
- Active/idle/used server connections.
- Pool wait time.
- Query/transaction time.
- Login failures and server reconnects.

### PostgreSQL

- `numbackends`/active sessions.
- `pg_stat_activity` wait events.
- `pg_stat_replication` state/lag.
- `pg_stat_wal_receiver` status.
- Replication slot retained WAL.
- CPU, memory, disk I/O, and network.

### Routing Metrics

- Writes sent to primary.
- Reads sent to each standby.
- Reads pinned to primary for consistency.
- Fallback-to-primary count.
- Replicas removed due to lag/health.
- Requests failed during refresh/failover.

## 43. Verifying Routing Distribution

Do not measure only overall query latency. You need to know where the workload is actually going.

A log/trace record can capture:

- route class: write/read/reporting/read-after-write.
- logical endpoint/pool name.
- connected database node/host.
- transaction id/request id.
- query duration and pool acquisition duration.
- replica replay lag at routing time.
- fallback reason if the read endpoint was bypassed.

Do not log passwords, connection strings containing secrets, or sensitive data in SQL parameters.

### Verification From PostgreSQL

On each node:

```sql
SELECT
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_is_in_recovery() AS is_standby,
    current_database() AS database_name,
    current_user AS role_name;
```

Applications can set different `application_name` values for write/read/reporting pools to distinguish sessions in `pg_stat_activity`.

## 44. application_name and Connection Attribution

Set a clear `application_name` in the connection string:

```text
application_name=orders-api-write
```

Read pool example:

```text
application_name=orders-api-read
```

When inspecting:

```sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    count(*) AS connections
FROM pg_catalog.pg_stat_activity
GROUP BY
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event
ORDER BY application_name, state;
```

`application_name` helps distinguish pools/workers, but it is not a security identity. Never use it in place of authentication or authorization.

## 45. pg_is_in_recovery and Primary Detection

Primary detection commonly relies on:

```sql
SELECT pg_is_in_recovery();
```

- `false`: node is not in recovery at the time of the query.
- `true`: node is in recovery/standby.

### Why Are Multiple Signals Needed?

A node returning `false` could be an old primary after a network partition, or an independent cluster. The HA manager must confirm leader/term/lease/fencing state. Checking `pg_is_in_recovery` alone does not prove a node is the sole primary authorized to accept writes.

### Health Checks Can Cache Briefly

A proxy may poll role/health periodically and cache the result for a few seconds. A longer cache window slows detection; too short creates probe load and risks flapping. Choose based on failover objectives.

## 46. Role-Aware Load Balancers

A PostgreSQL load balancer must understand the protocol or use a health-check agent to add/remove nodes from backend pools. A simple TCP health check cannot distinguish primary from standby.

### Safe Design

- The write backend pool contains only the primary confirmed by the HA control plane.
- The read backend pool contains only standbys healthy within the lag threshold.
- On promotion, a node moves from read membership to write membership after role verification.
- When a node is unhealthy, stop sending new connections and drain old ones.
- Never allow two primaries in the write backend pool at the same time.

Some solutions use HAProxy with an external check script/agent; configuration depends on OS, HA manager, and version. Health-check scripts must have timeouts, least-privilege permissions, and explicit failure behavior.

## 47. Pgpool-II and Query Load Balancing

Pgpool-II can provide connection pooling, health checks, failover handling, and load balancing according to configuration. It can classify certain queries to route reads, though behavior depends on replication mode, query type, transaction state, and configuration.

### Must Be Tested

- Simple `SELECT` and `SELECT` inside a transaction.
- `SELECT` after `INSERT`/`UPDATE`.
- Functions with side effects.
- Temporary tables/session settings.
- Prepared statements.
- Explicit read-only transactions.
- Multi-statement transactions.
- Queries using advisory locks or sequences.

Do not assume every `SELECT` goes to a standby or that every failover error is handled automatically. Proxies must be tested with realistic workloads and failover drills.

## 48. Connection Poolers Do Not Replace Application Routing

PgBouncer optimizes reusing server connections. It does not inherently understand business semantics such as "reading an order right after creating it must see the new data." Applications still need to decide consistency policies and endpoints.

### Division of Responsibilities

- Application: decides write/read/consistency class.
- HA manager: determines the primary and failover state.
- Load balancer/proxy: exposes endpoints by role/health.
- Pooler: multiplexes and manages backend connections.
- PostgreSQL: executes transactions/recovery/replication.

Keeping responsibilities clear makes routing incidents easier to debug.

## 49. Pool Refresh When Changing Read Replica Membership

When adding/removing a standby:

1. Health-check the new node and verify its role.
2. Measure lag, CPU, disk, and connection capacity.
3. Add the node to the read backend pool with a low weight.
4. Observe traffic distribution and latency.
5. Increase weight gradually if stable.
6. When removing a node, stop granting new connections.
7. Drain/evict existing connections.
8. Confirm the node no longer receives read traffic.

### Do Not Add a Replica Just Because TCP Is Open

A replica may be in initial recovery, catching up, or lagging past threshold. Add it only when the application read policy is satisfied.

## 50. Pool Refresh When Changing Endpoint Config

If the datasource URL/host changes:

- Identify the configuration source of truth.
- Update the secret/config store.
- Ensure processes pick up the new config.
- Create a new pool or update the pool via supported APIs.
- Validate connections to the new backend.
- Shift traffic to the new pool.
- Drain and close the old pool.

### Blue/Green Pool Replacement

For applications requiring high availability, you can stand up a new pool alongside the old pool. Once the new pool is healthy, switch routing to the new pool and drain the old one. Cap total connections during the overlap window.

## 51. Pool Refresh When the Endpoint Stays the Same but Role Changes

A DNS name may stay the same during failover while the node behind it changes role. Existing open connections to the previous node remain bound to sessions on that server.

Therefore:

- Check the role on the new backend.
- Evict old connections on failover events.
- Reconnect to land on the new node.
- Verify `application_name`/host/role after reconnect.

Do not compare hostnames alone; the same hostname can represent different nodes over time.

## 52. Backoff and Jitter on Reconnect

After an outage, thousands of application instances may reconnect simultaneously. If all retry immediately, the primary/proxy can suffer a connection storm.

Use exponential backoff with jitter:

```text
attempt 1: short delay
attempt 2: longer delay
attempt 3: longer delay with random jitter
...
maximum delay: bounded
```

Retries must have an overall deadline and distinguish transient vs. permanent errors. Authentication failures should not retry infinitely; connection refused during failover can be retried in a controlled way.

## 53. Startup Storms and Pool Warm-Up

After deployment/restart, every instance may simultaneously open `maximumPoolSize` connections. This hits PostgreSQL with a burst of authentication/TLS handshakes.

Measures:

- Limit `minimumIdle`.
- Warm up gradually with a concurrency cap.
- Use jitter for startup/reconnect.
- Cap max pool size by service tier.
- Use PgBouncer to multiplex where appropriate.
- Prevent autoscaling from pushing total connection count past budget.

## 54. Pool Exhaustion and Backpressure

When all connections are busy, the pool queue grows. If the application continues accepting unbounded requests, memory/thread backlogs can grow.

### Backpressure

- Limit concurrent requests according to pool capacity.
- Separate pools for critical traffic and batch jobs.
- Set query/transaction deadlines.
- Use bounded queue capacity.
- Return overload responses early when unable to serve.
- Throttle reporting workloads when primary/replicas are overloaded.

### Do Not Increase Pool Size Unboundedly

Increasing max pool size can shift the bottleneck onto PostgreSQL and make things worse. Inspect slow queries, locks, CPU, I/O, and connection leaks first.

## 55. Connection Leaks and Long Transactions

A connection leak occurs when an application borrows a connection and fails to return it to the pool. Long transactions also hold connections for a long time even when code does not leak.

### Symptoms

- Active connections rise while throughput does not.
- Pool wait time increases.
- `idle in transaction` sessions linger.
- Transactions hold locks or old snapshots.
- Read replica replay is blocked by long-running queries.

### Remediation

- Use try-with-resources/context managers.
- Keep transaction boundaries short.
- Close result sets/statements/connections properly in their lifecycle.
- Enable appropriate leak detection.
- Monitor `idle_in_transaction_session_timeout` and statement/transaction deadlines.

Do not terminate sessions based solely on `idle in transaction` state; inspect the owner and business impact.

## 56. Read Replica Lag Caused by Query Workloads

A long read query on a standby can conflict with WAL replay. If the standby delays replay to wait for the query, lag increases; if replay takes priority, the query may be canceled due to conflict.

### Separate Workloads

- Short API reads on low-latency replicas.
- Reports on a dedicated replica.
- Large exports on a batch-dedicated replica/warehouse.
- Read-after-write on the primary or an LSN-aware path.

### Monitor Conflicts

```sql
SELECT *
FROM pg_catalog.pg_stat_database_conflicts
ORDER BY datname;
```

Combine conflict counters, replay lag, query duration, and `max_standby_streaming_delay`/`hot_standby_feedback` policy.

## 57. Troubleshooting: Write Request Receives Read-Only Error

SQLSTATE `25006` typically indicates the transaction is read-only. Investigate:

1. Identify the actual host/server of the connection.
2. Check `pg_is_in_recovery()` on that node.
3. Check the write endpoint/backend membership.
4. Check whether the pool is holding an old connection to a standby.
5. Check the transaction read-only setting.
6. Check failover/DNS/proxy state.
7. Evict connections to the wrong endpoint after routing is fixed.
8. Retry the request only when transaction outcome is known.

Never "fix" this by disabling read-only protections on a standby.

## 58. Troubleshooting: Read Request Does Not See Newly Written Data

Investigate:

- Did the write transaction actually commit?
- Is the read request hitting the primary or a standby?
- Is the replica's replay LSN/time keeping up?
- Is there stale cache/application-level data?
- Is an old transaction snapshot holding the query back?
- Is the read pool pinned to a replica lagging behind other replicas?

Fix with primary routing, LSN wait, or an appropriate consistency contract. Do not increase fixed sleeps as the primary fix.

## 59. Troubleshooting: Pool Holds Connections to the Old Primary

1. Confirm failover/promotion has completed.
2. Confirm the old primary is fenced.
3. Check current DNS/VIP/proxy backends.
4. Check the app pool and PgBouncer server connections.
5. Evict/reconnect according to pool lifecycle.
6. Verify new connections reach the new primary node.
7. Monitor that the old node no longer accepts writes.
8. Handle unknown transaction outcomes using idempotency/reconciliation.

## 60. Troubleshooting: Pool Timeouts Despite a Healthy Database

Possible causes:

- Pool size too small or queue too long.
- Connection leak.
- Overly long queries/transactions.
- Pooler server pool exhausted.
- Per-user/per-database limits too low.
- High authentication/connect latency.
- DNS/TLS/secret refresh causing connection creation failures.

Inspect application pool metrics, PgBouncer `SHOW POOLS`/`SERVERS`, `pg_stat_activity`, and query latency. Distinguish pool acquisition timeouts from PostgreSQL connect/query timeouts.

## 61. Runbook: Switching the Primary Endpoint After Failover

1. Confirm the failure and failover decision from the HA control plane.
2. Fence the old primary to prevent split-brain.
3. Promote the standby via orchestration.
4. Verify `pg_is_in_recovery() = false` on the new node.
5. Verify the HA manager has only one writable primary.
6. Update the write endpoint/VIP/DNS/proxy backend.
7. Wait for the routing layer to pick up the new configuration.
8. Run `RECONNECT`/drain pooler backend connections per runbook.
9. Soft-evict or replace the application write pool.
10. Run write/read smoke tests and verify host/role.
11. Rebuild read pool membership from remaining healthy standbys.
12. Monitor SQLSTATEs, pool timeouts, transaction outcomes, and replication lag.

## 62. Runbook: Draining a Standby From the Read Pool

1. Mark the standby unhealthy/maintenance in the routing layer.
2. Stop sending new connections to the node.
3. Identify long-running queries/transactions.
4. Wait for in-flight requests to complete within the deadline.
5. Soft-evict/close idle connections.
6. Confirm the pool has no remaining backend connections to the node.
7. Perform maintenance/restart.
8. Check recovery/streaming after the node comes back up.
9. Wait for lag to drop below threshold.
10. Add the node back with a low weight and observe.

## 63. Runbook: Rotating Credentials and Refreshing the Pool

1. Issue the new credential via the secret manager.
2. Confirm the PostgreSQL role/policy accepts the new credential.
3. Update application/pooler configuration.
4. Create a test connection from each service identity.
5. Reload/restart the pooler if necessary.
6. Soft-evict old application connections.
7. Monitor authentication failures.
8. Confirm no processes still use the old secret.
9. Revoke the old credential per rotation plan.
10. Save audit evidence and update the rollback procedure.

## 64. Runbook: Handling a Connection Storm After an Outage

1. Keep bounded retries and backoff/jitter active.
2. Check whether the primary/proxy is ready.
3. Temporarily cap autoscaling/worker concurrency if needed.
4. Check the server connection budget.
5. Warm up pools gradually.
6. Monitor authentication/TLS handshake rates.
7. Open traffic by service tier.
8. Monitor pool queues and DB CPU.
9. Increase concurrency only while the database has headroom.
10. Record the root cause of the storm and adjust startup policies.

## 65. Routing and Pool Lifecycle Checklist

### Routing

- Writes/DDL always go to the current primary.
- Transactions are pinned to a single connection.
- Read-after-write policy is defined.
- Read endpoint filters replicas by role and lag.
- `SELECT`s with side effects are not misrouted.
- Reporting/batch workloads have suitable endpoints.

### Pooling

- Pool sizes are calculated across total instances/users/databases.
- Pool mode is compatible with session features.
- Acquisition/connect/query timeouts have deadlines.
- `maxLifetime`/idle timeout/keepalive are configured.
- Connection leaks/long transactions are monitored.

### Failover/Refresh

- Old primary is fenced before shifting writes.
- DNS/endpoint updates have a clear control plane.
- Application pools support soft eviction/recreation.
- Pooler backend connections have a reconnect/drain procedure.
- Credential/TLS rotations have overlap and refresh.
- Retries use backoff, jitter, and idempotency.

### Observability

- Route distribution by endpoint/replica.
- Pool active/idle/waiting/acquisition latency.
- Backend host/role and health state.
- Replication lag/slot state.
- Failover/refresh events and SQLSTATE errors.
- RPO/RTO and read consistency failures.

## 66. Common Design Mistakes

**Using a TCP check as a primary health check.** TCP open does not prove a node is primary.

**Routing every SELECT to a standby.** Some `SELECT`s have side effects or require read-after-write.

**Changing DNS and assuming old connections move automatically.** TCP sockets and pooled connections remain bound to the old backend.

**Using one pool for both reads and writes without role awareness.** Connections may point to a standby after failover.

**Increasing pool size to fix every timeout.** Can overload PostgreSQL even further.

**Using transaction pooling while retaining session state.** State can be lost or bleed onto another connection.

**Retrying transactions when COMMIT disconnects without idempotency.** The transaction may have committed, leading to duplicate effects.

**Putting a promoted primary into both read and write pools without updating role membership.** Can cause misrouting or load skew.

**Not fencing the old primary.** Risks split-brain.

**Using only the replication lag timestamp.** On an idle primary, the timestamp can look stale even when the replica has caught up.

**Testing failover only at the database layer.** You must test application pools, DNS, proxies, retries, and transaction outcomes.

## 67. Hands-On Exercises

### Exercise 1 — Primary and Read Endpoints

Draw an architecture with a primary, two standbys, a write endpoint, a read endpoint, and application pools. Explain which node accepts writes.

### Exercise 2 — Routing Semantics

Classify `INSERT`, `UPDATE`, DDL, a simple `SELECT`, a `SELECT` calling a function with side effects, and a read-then-write transaction.

### Exercise 3 — Non-Read-Only SELECT

A `SELECT` statement invokes a function that performs a side effect. Why is an SQL prefix insufficient to decide read routing?

### Exercise 4 — Separate Pools

Design a write pool and a read pool for an API service. Describe how the service layer expresses routing intent.

### Exercise 5 — Transaction Pinning

A transaction `UPDATE`s a balance and then `SELECT`s the balance before `COMMIT`. Why must the `SELECT` stay on the same primary connection?

### Exercise 6 — Read-After-Write

An order is committed on the primary but does not yet appear on a standby. Give three ways to ensure the user sees the newly created order.

### Exercise 7 — LSN Token

Write SQL to fetch the current WAL LSN after commit and check `pg_last_wal_replay_lsn` on a standby. State the timeline condition.

### Exercise 8 — Synchronous Commit

Compare `synchronous_commit=on` and `remote_apply`. Why does `remote_apply` not automatically select the read endpoint?

### Exercise 9 — Replication Lag

Explain the difference between byte lag and timestamp lag. Why can the timestamp look stale when the primary is idle?

### Exercise 10 — Health Check

Write a query using `pg_is_in_recovery` and `transaction_read_only` to distinguish primary/standby. Why are an HA manager and fencing still required?

### Exercise 11 — target_session_attrs

Write a `libpq` connection string that tries multiple hosts and selects a read-write server. State its limitation after the connection is open.

### Exercise 12 — DNS

The primary endpoint changes IP after failover, yet the app keeps using old connections. Explain DNS TTL, resolver caching, and TCP sockets.

### Exercise 13 — Read Load Balancing

Design weighted read routing for two replicas with different capacities. Which metrics must be monitored?

### Exercise 14 — PgBouncer

Diagram two PgBouncer endpoints for write and read. Why does PgBouncer not parse SQL by default to route per statement?

### Exercise 15 — Pooling Modes

Compare session, transaction, and statement pooling. Choose a mode for an application using multi-statement transactions.

### Exercise 16 — Session State

An application uses temporary tables, `LISTEN`/`NOTIFY`, and session advisory locks. Which features can run into trouble with transaction pooling?

### Exercise 17 — SET LOCAL

Write a transaction using `SET LOCAL statement_timeout` and `TimeZone`. Why is it a better fit than session-level `SET` in transaction pooling?

### Exercise 18 — PgBouncer Commands

Explain the purpose of `RELOAD`, `RECONNECT`, `WAIT_CLOSE`, `PAUSE`, and `RESUME`. Why must you read version-specific semantics?

### Exercise 19 — Pool Sizing

A service has 10 instances, each with a write pool of 15 and a read pool of 25. Calculate the potential total connections before accounting for a pooler and admin reserve.

### Exercise 20 — Connection Budget

PostgreSQL has `max_connections=300`. Design a budget for apps, workers, monitoring, replication, migrations, and admin headroom.

### Exercise 21 — Pool Timeout

Distinguish acquisition timeout, connect timeout, and query timeout. A request waits 3 seconds on the pool and fails; which metrics should you inspect?

### Exercise 22 — maxLifetime

Why does a pool need `maxLifetime`? Why can an overly short lifetime cause connection churn?

### Exercise 23 — Keepalive

Explain TCP keepalive and connection validation. Why do they not replace a primary role health check?

### Exercise 24 — HikariCP

Explain `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `maxLifetime`, and `keepaliveTime`. Which values must be measured before choosing them?

### Exercise 25 — Pool Refresh

An endpoint changes backend after failover. Describe how to soft-evict/recreate the pool and confirm new connections reach the right node.

### Exercise 26 — Fencing

Why must you fence the old primary before switching the write endpoint? Does a DNS update alone prevent split-brain?

### Exercise 27 — Drain

Design how to drain a read replica before maintenance without terminating long-running queries immediately.

### Exercise 28 — Credential Rotation

A PostgreSQL password is rotated. Design the overlap, secret update, pool refresh, and old credential revocation.

### Exercise 29 — TLS Rotation

Design a CA/certificate rotation with overlap. Why must the pool create new TLS sessions?

### Exercise 30 — Ambiguous Commit

A client loses connection right after sending `COMMIT` without receiving acknowledgement. Why can it not know for sure whether the transaction committed?

### Exercise 31 — Idempotency

Design an idempotency key/unique constraint for a payment creation API so retries after failover do not create duplicate charges.

### Exercise 32 — SQLSTATE

Explain the general handling for SQLSTATEs `08006`, `57P01`, `57P03`, `25006`, and `28P01`.

### Exercise 33 — Circuit Breaker

Design a circuit breaker for the read endpoint. Why must the write endpoint only switch when the HA control plane confirms the new primary?

### Exercise 34 — Workload Classes

Split API reads, read-after-write, reporting, and analytics into endpoints/pools. State the rationale.

### Exercise 35 — Pool Metrics

List the application pool, PgBouncer, and PostgreSQL metrics needed to detect pool saturation.

### Exercise 36 — Read Replica Query Conflicts

A long report query causes replay lag to climb. Design how to isolate the reporting workload and monitor conflicts.

### Exercise 37 — Startup Storm

After an outage, 50 application instances simultaneously open their max pools. Design warm-up, backoff, jitter, and concurrency caps.

### Exercise 38 — Pool Timeout Despite a Healthy DB

An application hits pool timeouts while PostgreSQL CPU is low. Investigate connection leaks, pooler limits, acquisition queues, and authentication.

### Exercise 39 — Failover Runbook

Write the sequence from fencing, promotion, endpoint update, pool refresh, and smoke test to read pool membership rebuild.

### Exercise 40 — End-to-End Routing and Pool Lifecycle Design

An e-commerce system has:

- One PostgreSQL primary and three physical standbys.
- 12 instances of an API service.
- Peak write traffic of 2,000 transactions/second.
- Peak read traffic of 12,000 queries/second.
- One standby dedicated to reporting.
- Two standbys serving API reads.
- 10-second RPO and 60-second RTO.
- Failover may change the primary endpoint.
- Some APIs must see an order immediately after creation.
- The application uses PgBouncer transaction pooling.

Design:

1. Write/read/reporting endpoint topology.
2. Pool sizes and connection budget.
3. Routing rules by transaction semantics.
4. Read-after-write policy using primary or LSN wait.
5. Health checks for primary/standby and lag thresholds.
6. PgBouncer pool mode and session-feature constraints.
7. DNS/HA endpoint and failover fencing.
8. Pool refresh/drain sequence after promotion.
9. Retries/idempotency when connection drops during `COMMIT`.
10. Monitoring, alerts, runbooks, and chaos tests proving RPO/RTO.

## Conclusion

**Routing reads and writes must be based on transaction semantics and the current role of the PostgreSQL node.** Writes, DDL, and reads requiring just-committed data should go to the primary or use an explicit consistency mechanism. Only reads that can tolerate eventual consistency should be distributed to standbys, after checking health and replay lag. You cannot choose a backend solely by looking at the `SELECT` keyword or a TCP port.

Application-side routing lets business logic decide consistency; proxies/load balancers expose role-based endpoints; PgBouncer manages and multiplexes connections. The pool mode must be compatible with session features, and pool sizes must be calculated across total instances/users/databases along with admin/replication headroom.

**After failover, connection pools must be refreshed intentionally.** DNS updates do not move open TCP sockets. Fence the old primary, promote and verify the new node, update endpoints, reconnect/drain the pooler, soft-evict application connections, and verify the host/role of new connections. Credential and TLS rotations require a similar refresh workflow.

Finally, retries must account for transaction outcomes: losing a connection during `COMMIT` can leave an indeterminate result at the client. Bounded retries, exponential backoff, jitter, and idempotency protect applications from duplicate effects and connection storms. **Routing, health checks, pool lifecycle, replication lag, and failover orchestration must be tested together** to achieve real-world high availability.
