# Scaling the System

## MySQL Router, Connection Proxying, and Boundaries with Connection Pools

When an application needs to connect to a multi-node MySQL deployment, the primary can change after a failover and the number of connections grows with the number of application instances. Connecting directly to a single database address forces the application to track which node accepts writes, which nodes serve reads, and how to reconnect when the topology changes. MySQL Router provides a stable connection endpoint in front of MySQL Servers, tracks supported topologies, and routes connections to the appropriate node.

In the **DATABASE_MYSQL** module, you learn how to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and relational database operational troubleshooting. This lesson extends operational knowledge to the connection layer: placing Router in front of MySQL, coordinating with the application's connection pool, understanding connection sharing, splitting read/write traffic, and building failover reconnection workflows.

The key takeaway is that there are multiple layers of connection management. The connection pool inside the application manages the JDBC connections borrowed and returned by code. MySQL Router accepts connections from the application and routes them to servers; starting in Router 8.4, connection sharing can reuse server connections when sessions are eligible. These layers have different goals and limits, so they must be configured and measured separately.

### 1. Multi-Layer Connection Architecture

Typical flow when using Router and pools:

~~~mermaid
flowchart LR
    A[Application instances] --> B[Application connection pool]
    B --> C[Router service / load balancer]
    C --> D1[MySQL Router A]
    C --> D2[MySQL Router B]
    D1 --> E[Metadata cache and routing]
    D2 --> E
    E --> F[Primary]
    E --> G[Secondary 1]
    E --> H[Secondary 2]
~~~

Each layer has distinct responsibilities:

| Component | Responsibilities | What not to expect |
|---|---|---|
| JDBC/DataSource | Creates logical connections, caps borrowed connections, manages application-side lifecycle and timeouts | Automatically knowing the new primary if the URL points directly to a single node |
| Application connection pool | Reuses connections, caps concurrency, reclaims connections, and supports health checks | Automatically recovering a disconnected transaction or ensuring a replica has caught up |
| MySQL Router | Listens on endpoints, selects destinations, forwards MySQL protocol, tracks topology metadata, and supports certain sharing/routing modes | Replacing the application's transaction manager, business retries, or validation |
| MySQL Server | Executes SQL, transactions, locks, replication, and data storage | Silently migrating an in-flight connection from an old primary to a new primary without surfacing an error to the client |
| Load balancer/service discovery | Provides a stable address to one or more Routers | Understanding MySQL transaction semantics if operating strictly at the TCP layer |

For example, HikariCP holds a pool of JDBC connections to Router. Router accepts those connections and chooses a MySQL node via its routing service. When a server fails, existing connections may drop; the pool must evict broken connections and the application must open new connections through the same Router endpoint.

### 2. What Does MySQL Router Do?

MySQL Router is lightweight middleware sitting between the application and MySQL Server. It supports connection routing, integration with InnoDB Cluster and supported topologies, read/write splitting in applicable versions, TLS, and connection sharing.

Router can:

- Provide a stable endpoint for applications.
- Route connections to primary or secondary nodes based on the metadata cache.
- Select servers using routing strategies such as first-available or round-robin.
- Track InnoDB Cluster topology state to update destinations.
- Disconnect clients when a backend connection fails so the application can reconnect.
- With Router 8.4 and appropriate configuration, share/reuse eligible idle server connections.
- With read/write splitting, classify statements and direct traffic to read-write or read-only destinations.

Router is not a standalone MySQL Server storing data. The application connects to Router, while SQL statements still execute on MySQL backends. Router does not replace server privileges, constraints, transactions, replication, or backups.

### 3. Connection-Based Routing

Basic routing mode selects a backend when the client establishes a connection. Router forwards MySQL packets between client and server. In basic routing mode, Router does not inspect individual SQL statements to pick a destination; the chosen connection remains bound to that backend for the duration of the session.

A simple routing example:

~~~ini
[routing:primary_service]
bind_address = 127.0.0.1
bind_port = 7001
destinations = db-primary.example.net:3306
routing_strategy = first-available

[routing:read_service]
bind_address = 127.0.0.1
bind_port = 7002
destinations = db-replica-1.example.net:3306,db-replica-2.example.net:3306
routing_strategy = round-robin
~~~

This is an illustrative configuration for a static destination list. In an InnoDB Cluster environment, use metadata cache and bootstrap-generated configuration so Router understands primary/secondary roles and topology. Do not use a static IP list instead of metadata-aware routing if the goal is keeping up with cluster failovers.

Common routing strategies:

| Strategy | General behavior | Suitable use case |
|---|---|---|
| first-available | Selects the first available destination; on failure can try the next destination | Endpoints needing a preferred node |
| round-robin | Distributes new connections sequentially across available destinations | Spreading connection load across replicas |
| round-robin-with-fallback | Prefers a role-based destination group; can fall back as configured when the preferred group has no eligible nodes | Read-only routing with designed fallback |
| next-available | Moves to the next destination and can exclude nodes marked unreachable until Router restarts | Static destination lists needing skip-failed-node behavior |

Strategies apply to new connections. Do not mistake round-robin for Router splitting individual SELECT statements within one connection across multiple replicas. If you want statement-level read/write classification within a session, configure read/write splitting appropriately.

### 4. Metadata Cache and InnoDB Cluster

When using InnoDB Cluster, MySQL Router can be bootstrapped against a cluster member. Bootstrapping reads metadata, generates routing configuration, and sets up the account Router needs to access metadata. Router maintains a metadata cache to know which members are currently primary, secondary, or unavailable.

General workflow:

1. Create and verify the InnoDB Cluster with MySQL Shell AdminAPI.
2. Create a bootstrap/router account with the proper privileges per version documentation.
3. Run bootstrap on the host that will run Router.
4. Inspect the generated configuration file, runtime directory, logs, and keyring.
5. Start Router and verify the exposed endpoints.
6. Connect through Router and read hostname/port to confirm the actual backend.

Example bootstrap command on Linux:

~~~bash
mysqlrouter --bootstrap router_admin@db-seed.example.net:3306 \
  --directory /var/lib/mysqlrouter
~~~

The example command uses a placeholder account and host. Supply passwords via prompt or managed secret mechanisms; never write passwords directly into command history. Bootstrap privileges must match the Router documentation for your version and topology.

Do not arbitrarily edit bootstrap-generated configuration sections. When routing adjustments are needed, review the entire relevant section and preserve the metadata cache, dynamic state, keyring, and auto-generated paths.

### 5. Read-Write and Read-Only Endpoints

An InnoDB Cluster deployment typically exposes endpoints for:

- Read-write: connects to the current primary.
- Read-only: connects to an eligible secondary.

Ports 6446 and 6447 are commonly used as defaults in typical bootstrap configurations, though they can be changed. Applications should read ports from deployment configuration rather than hardcoding assumptions.

A bootstrap-generated configuration snippet typically looks like:

~~~ini
[routing:bootstrap_rw]
bind_address = 127.0.0.1
bind_port = 6446
destinations = metadata-cache://myCluster/?role=PRIMARY
routing_strategy = first-available
protocol = classic

[routing:bootstrap_ro]
bind_address = 127.0.0.1
bind_port = 6447
destinations = metadata-cache://myCluster/?role=SECONDARY
routing_strategy = round-robin-with-fallback
protocol = classic
~~~

This is an illustrative snippet, not a complete configuration file. Cluster name, metadata cache section, credentials, and other options must match the bootstrap-generated configuration.

Applications can use two DataSources:

- A write DataSource pointing to the read-write endpoint.
- A reporting read DataSource pointing to the read-only endpoint.

Split pools only when business requirements and consistency permit. Reading immediately after writing, reading payment status, checking inventory, or verifying a just-committed transaction typically requires the primary to avoid reading data not yet applied on a replica.

### 6. Read/Write Splitting in MySQL Router 8.4

MySQL Router 8.4 provides statement-level read/write splitting mode. This differs from selecting a read-only or read-write endpoint for an entire connection. Within a single session, Router can use a read-write destination for write statements and a read-only destination for read statements.

To enable read/write splitting, Router configuration requires these key conditions:

- `access_mode` set to `auto`.
- `connection_sharing` enabled.
- `protocol` set to `classic`.
- `destinations` using metadata cache with role `PRIMARY_AND_SECONDARY`.

Illustrative configuration snippet:

~~~ini
[routing:read_write_split]
bind_address = 127.0.0.1
bind_port = 6450
destinations = metadata-cache://myCluster/?role=PRIMARY_AND_SECONDARY
routing_strategy = round-robin
protocol = classic
access_mode = auto
connection_sharing = 1
~~~

These settings must be paired with the metadata cache section and appropriate connection pool settings. Check the installed Router version; do not apply an 8.4 snippet to older versions where the feature is unsupported.

Access mode can be set per session:

~~~sql
ROUTER SET access_mode = 'auto';
ROUTER SET wait_for_my_writes = 1;
~~~

`access_mode` values:

| Value | Meaning |
|---|---|
| read_write | All session traffic is sent to a read-write server |
| read_only | All session traffic is sent to a read-only server |
| auto | Router classifies statements and selects a read-only or read-write destination |

A single session can use both destinations. Therefore, do not assume a JDBC connection to the read/write split endpoint maps to only a single backend connection throughout its lifecycle.

### 7. How Does Router Classify Statements?

Router 8.4 maintains lists of statements treated as read-only or read-write. This is a classifier based on syntax and supported statement types, not a complete semantic analysis of every stored procedure or function.

Examples of read-only statements:

- SELECT.
- DO, VALUES, TABLE.
- WITH not followed by UPDATE or DELETE.
- EXPLAIN, DESCRIBE, DESC in supported cases.
- HELP, USE, CHECKSUM, and parenthesized query expressions.

A statement starting like a SELECT may still require a read-write server if it contains:

- GET_LOCK().
- FOR UPDATE or FOR SHARE.
- LOCK IN SHARE MODE.
- Functions or syntax capable of writing data.

Statements treated as read-write include:

- DDL and schema-modifying operations.
- INSERT, UPDATE, DELETE, REPLACE, CALL, and supported load/import forms.
- START TRANSACTION, COMMIT, ROLLBACK, SAVEPOINT, and XA.
- Certain administrative commands, account management, SET SESSION, and SHOW CREATE.

Statements outside the two classification sets may not be supported when `access_mode=auto`. Notably, CALL is routed read-write even if the procedure only reads. A SELECT invoking a function with side effects may also be routed read-write or fail if forced to read-only.

If a query must execute on the primary, set the session to `read_write` or use a dedicated read-write endpoint. Do not rely on the SELECT keyword alone to guarantee a statement performs no writes.

### 8. Read-After-Write and Replication Lag

A replica may not yet have applied a transaction just committed on the primary. If the application writes via the primary and immediately reads via a secondary, results can be stale.

There are three common ways to handle this:

1. Send both writes and consistency-sensitive reads to the read-write endpoint.
2. Keep a transaction/session in `read_write` mode for the entire business flow.
3. Use `wait_for_my_writes` in Router 8.4 when read/write splitting is configured and that behavior fits.

Example:

~~~sql
ROUTER SET access_mode = 'auto';
ROUTER SET wait_for_my_writes = 1;
ROUTER SET wait_for_my_writes_timeout = 2;
~~~

When `wait_for_my_writes` is enabled, Router can wait for the read-only destination to apply the last transaction written by the session. If the timeout expires, Router can fall back to the read-write destination according to configuration. In Router 8.4, `wait_for_my_writes_timeout` defaults to 1 second; maximum limits and behavior should be checked per version. Measure actual latency before changing the timeout.

This is not a guarantee of linearizable consistency for every read in all scenarios. Test with your replication mode, topology, node failures, and real load. For financial or inventory workflows, choose the primary if stale reads are unacceptable.

### 9. Application Connection Pool vs. Router Connection Sharing

These are two pools at two different boundaries.

| Attribute | Application pool | Router connection sharing |
|---|---|---|
| Location | Inside the application process or application server | Inside MySQL Router |
| Managed object | Logical/physical JDBC client connections to Router | Backend connections from Router to MySQL Server |
| Goal | Reduce connection open cost, cap app connections, reuse connections | Reduce idle server connections and allow server connections to be reused across eligible client sessions |
| Application-visible API | `DataSource.getConnection()`/`Connection.close()` | No separate JDBC API; configured at Router |
| State scope | Transaction and session state of the JDBC connection | Protocol/session state tracked by Router and backend shareability |
| Limiting conditions | Pool size, timeouts, validation, leak detection | Classic protocol, session state, transactions, prepared statements, and supported features |

In Router 8.4, connection sharing is disabled by default by configuration option. When enabled, Router can place idle backend connections into a pool for other client sessions to reuse. Router tracks statements and SQL state to preserve session state; if sharing is unsafe, the backend connection is not pooled.

Connection sharing does not mean any arbitrary SQL statement can run on just any server session. Router must preserve session state and has a list of features that prevent returning a connection to the pool. Test the statements your application uses before enabling it.

Options controlling connection sharing in Router 8.4:

| Option | Documented default | Role |
|---|---:|---|
| connection_sharing | 0 | Enables/disables backend connection sharing |
| connection_sharing_delay | 1 second | Wait duration before an eligible idle backend connection enters the pool |
| max_idle_server_connections | 0 | Maximum idle backend connections retained for reuse |
| idle_timeout | 5 seconds | Duration an idle backend connection stays in the pool before closing |

Values and configuration sections can vary by version; bootstrap may generate settings different from general defaults. For instance, a bootstrapped read/write split route may set `max_idle_server_connections` greater than 0. Inspect the actual configuration and measure backend connection counts before tuning.

With an application-side connection pool, the lifecycle may unfold as follows:

1. HikariCP provides a JDBC connection; a client-to-Router TCP connection is open.
2. Router binds the session to a MySQL backend and forwards statements.
3. Code calls `Connection.close()`; HikariCP reclaims the logical connection but typically keeps the TCP connection to Router open in an idle state.
4. If connection sharing is enabled, after `connection_sharing_delay` Router may place the idle backend connection into its pool if the session is not pinned by a transaction or unsupported feature.
5. When the application reuses the JDBC connection and sends statements, Router attaches the session to an eligible backend connection while preserving tracked state.

Thus, HikariCP `close()` does not mean the client TCP connection closed. Router sharing can reuse backends even while the application pool holds client connections open; however, state such as temporary tables or prepared statements can prevent backend sharing until the client resets or closes the session.

### 10. Limitations of Connection Sharing

In Router 8.4, connection sharing supports only the classic protocol. It is not supported in certain TLS configurations such as `PASSTHROUGH` or the combination `server-ssl-mode=AS_CLIENT` with `client-ssl-mode=PREFERRED`. Read the compatibility matrix for your running Router version.

The following statements/state items can prevent a backend connection from returning to the shared pool until the client closes or resets the connection:

- User variables.
- Temporary tables.
- Prepared statements.
- `GET_LOCK()` and related named locks.
- `SQL_CALC_FOUND_ROWS`.
- `LOCK TABLES`.
- An open transaction.

Certain statements such as `GET DIAGNOSTICS` and `LAST_INSERT_ID()` are not supported under connection sharing outside a transaction per documented limitations.

Operational implications:

- Do not assume a temporary table safely persists after a backend connection is shared.
- Do not rely on user variables to pass data across statements if sessions can be shared.
- Close/reset prepared statements per the JDBC lifecycle.
- Keep transactions short and commit/rollback before connections go idle.
- Use session state in ways supported by Router and test on the actual version.

If an application frequently uses temporary tables, user variables, or prepared statements in ways that pin connections, connection sharing may yield diminished benefits. Measure the actual backend connection reuse ratio instead of just enabling the option and assuming connection counts will drop.

### 11. Coordinating with HikariCP or JDBC Pools

Java applications should use a long-lived DataSource/pool. Illustrative configuration example:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:mysql://router.service.internal:6446/appdb");
config.setUsername("app_user");
config.setPassword(secret);
config.setMaximumPoolSize(20);
config.setConnectionTimeout(3000);
config.setValidationTimeout(1000);
config.setMaxLifetime(1500000);
config.setKeepaliveTime(120000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

These numbers are illustrative only. Choose `maxLifetime` shorter than connection age limits enforced by Router, load balancers, firewalls, or MySQL. `keepaliveTime` must suit `maxLifetime` and your pool version's requirements. Do not copy these values into production without measuring.

The application must close `ResultSet`, `Statement`, and `Connection` properly:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT order_id, total_amount FROM orders WHERE order_id = ?")) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
~~~

In a pool, `Connection.close()` usually returns the logical connection to the pool; the socket to Router may stay open. Hence, Router may still see an active client connection even after the request finishes. If Router connection sharing is enabled, it can manage idle backend connections according to its sharing rules.

Always finish transactions before returning a connection. Closing a connection with an uncommitted/unrolled-back transaction is not a cleanup strategy. The pool may issue a rollback when reclaiming it, but the application must own transaction boundaries.

### 12. Separating Read and Write Pools

If using separate endpoints, create two independently configured DataSources:

~~~java
HikariConfig writeConfig = new HikariConfig();
writeConfig.setJdbcUrl("jdbc:mysql://router.service.internal:6446/appdb");
writeConfig.setUsername("app_user");
writeConfig.setPassword(secret);
writeConfig.setMaximumPoolSize(20);

HikariConfig readConfig = new HikariConfig();
readConfig.setJdbcUrl("jdbc:mysql://router.service.internal:6447/appdb");
readConfig.setUsername("app_read_user");
readConfig.setPassword(readSecret);
readConfig.setMaximumPoolSize(30);
~~~

This example illustrates common read-write and read-only endpoints. Port names, credentials, and pool sizes depend on the deployment. The same account can be used if privileges are designed accordingly, though separating read/write users helps enforce least privilege.

Do not route read/write solely by repository method names such as `get`/`find`/`save` without controlling transactions. A method named `find` might invoke a stored function with side effects; an `update` method might need consistent reads on the primary. Build business-aware routing policies at the service/repository layer and test against real backends.

If using a single Router 8.4 read/write split endpoint, test how the driver, pool, and Router interact with session settings. `ROUTER SET` options are session state; when connections are reused, the application must know which state is reset and how to re-establish it per unit of work.

Router 8.4 resets Router session options to initial values when a client sends `change_user` or `reset_connection`. Do not assume every JDBC pool sends those commands on every connection return; inspect your pool/driver behavior and explicitly set `access_mode` per business flow.

### 13. Connection Budgeting Across Layers

Setting a maximum pool size per process without accounting for application replica counts can exceed MySQL's `max_connections`.

Estimate client connections to Router:

~~~text
Application client connections
  = sum(application instances x pool maximum size)
    + background workers
    + migration jobs
    + admin/monitoring clients
~~~

Estimate backend connections on each MySQL node:

~~~text
Backend connections on node
  = active Router backend sessions
    + idle Router server connections
    + direct application/admin connections
    + replication and system sessions
~~~

When connection sharing is effective, backend connections can be fewer than client connections. However, sessions in open transactions, or using temporary tables, user variables, or prepared statements, may not be shareable. Therefore, do not budget based on an assumed reduction ratio.

Limits to distinguish:

| Limit | Where it applies | Meaning |
|---|---|---|
| Pool `maximumPoolSize` | Per DataSource in each process | Maximum logical connections the application can borrow |
| Router `max_total_connections` | Entire Router instance | Total client connections Router accepts |
| Router `max_connections` | A configured routing destination/route | Connection cap assigned to that destination |
| Router `max_idle_server_connections` | Router's server-side connection pool | Idle backend connections retained for reuse |
| MySQL `max_connections` | Per MySQL Server | Total client connections the server permits |
| MySQL `max_user_connections` | Per MySQL account | Per-user connection cap if configured |

Keep headroom for DBAs, health checks, backups, migrations, replication, and incident response. A node should not operate near `max_connections` under normal conditions.

### 14. Router Is a Layer That Requires HA

If there is only one Router, Router becomes a single point of failure. Production deployments typically run multiple Router instances across distinct hosts/failure domains and expose a service address via load balancer, DNS/service discovery, or an appropriate networking mechanism.

The design should answer:

- How many Router instances are needed to survive a host failure?
- Does the load balancer check Router via TCP or a dedicated health endpoint?
- Does the application pool connect to one service address or a list of Routers?
- When a Router restarts, how are existing connections handled?
- How are configuration and metadata cache kept synchronized?
- Where are Router logs, REST API metrics, and alerts collected?

Do not let health checks merely verify that the process is alive. Router may be running while unable to reach metadata servers or lacking eligible backends. Health checks should reflect readiness for application traffic while avoiding heavy load from constantly opening new connections.

### 15. Failover and Reconnect

Router supports directing new connections to available servers. When an existing backend connection breaks, Router can return a connection error to the client. The application must retry creating a connection; Router will select the new backend according to topology and routing strategy.

Do not assume Router transparently migrates an active session to a new primary without surfacing an error to the application. An open connection is bound to the old backend; an in-flight transaction may roll back or have an indeterminate outcome if connectivity drops right at commit.

Application reconnection workflow:

1. Catch connection-fatal errors from the driver.
2. Mark the connection unusable and return/evict it per pool implementation.
3. Borrow a new connection from the pool through the Router endpoint.
4. If the operation is safe to retry, re-run the entire unit of work with backoff and a retry limit.
5. If failure occurred during `COMMIT`, reconcile the outcome using a business key/idempotency key before retrying.
6. Log the correlation ID, SQLState, vendor error code, and reconnect attempt count.

Do not retry indefinitely or retry every `SQLException`. Duplicate key, validation, or permission errors are not fixed by reconnecting. For write operations, idempotency keys prevent creating duplicate transactions when the client does not know whether commit succeeded.

### 16. TLS and Security Boundaries

With Router in place, the network path has at least two hops:

1. Application to Router.
2. Router to MySQL Server.

Enabling TLS on the client-to-Router hop does not automatically prove the router-to-server hop is encrypted with certificate verification. Configure `client_ssl_mode` and `server_ssl_mode` per security policy; use appropriate CAs/certificates and verify identities when required.

Do not use `PASSTHROUGH` if Router needs to decrypt/inspect traffic for features requiring protocol termination or connection sharing. Some TLS mode combinations are incompatible with connection sharing; check the matrix for your Router version.

Principles:

- Bind Router to internal network addresses or localhost when architecture permits.
- Open Router ports only to application subnets requiring access.
- Use least-privilege application accounts.
- Separate metadata/bootstrap accounts from application accounts.
- Protect keyrings, configuration files, logs, and secrets.
- Never include passwords in JDBC URLs or shell history.
- Test certificate expiration, hostname verification, and certificate rotation.

### 17. Observing Router and Backends

When the application connects through Router, query backend details to verify routing:

~~~sql
SELECT
  @@hostname AS backend_host,
  @@port AS backend_port,
  @@server_uuid AS server_uuid,
  @@read_only AS read_only,
  @@super_read_only AS super_read_only;
~~~

Compare results across read-write and read-only endpoints. If the topology changes, open a new connection and verify the backend again.

Signals to monitor:

| Layer | Metrics/logs | Signs requiring investigation |
|---|---|---|
| Application pool | active, idle, pending, acquisition latency, timeout, leak | Pool exhaustion, requests waiting for connections |
| Router | client connections, backend connections, route errors, connect retries, logs | Backend unavailable, metadata cache errors, connection limits hit |
| MySQL | `Threads_connected`, `Threads_running`, `max_used_connections`, connection errors | Abnormal connection growth or server hitting limits |
| Replication | applier status, lag, queue, transaction apply time | Slow read-after-write or replica falling behind |
| Network | TCP resets, timeouts, packet loss, TLS errors | Flaky connections between app, Router, and backend |

On MySQL, check:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW PROCESSLIST;
~~~

Combine Router logs and the REST API if enabled/configured. Secure Router's admin endpoint and never expose it to public networks. When debugging connection sharing, Router 8.4 offers `ROUTER SET TRACE`; this feature requires compatible configuration and can emit sensitive logs/traces, so enable it only temporarily in test environments or per runbook.

### 18. Comparing MySQL Router, ProxySQL, and TCP Load Balancers

Proxy tools have different scopes:

| Component | Strengths | What to verify |
|---|---|---|
| MySQL Router | InnoDB Cluster metadata integration, role-based routing, HA connection routing, connection sharing, and read/write splitting in Router 8.4 | Statement/session state limits, protocol, TLS modes, and version |
| ProxySQL | MySQL proxy with query rules, hostgroups, connection pooling/multiplexing, and rich traffic management features | Rule configuration, transaction/session pinning, compatibility, and separate operations |
| TCP load balancer | Provides virtual IP/service endpoint, TCP health checks, and connection distribution | Does not understand full SQL semantics or MySQL metadata if operating only at L4 |
| DNS round-robin | Simple endpoint distribution | DNS caching, failover delay, health awareness, and existing open connections |

Do not pick a proxy solely based on how many connections it can accept. Determine whether you need role-based routing, statement-based routing, multiplexing, query rules, caching, TLS termination, or InnoDB Cluster integration. Then test session state, transactions, prepared statements, and failover.

### 19. Testing the Deployment

A test plan should cover routing, pooling, and failures:

1. Connect via the read-write endpoint and verify the backend is the primary.
2. Connect via the read-only endpoint and verify the backend has appropriate `read_only`/`super_read_only`.
3. Run `SELECT`, DML, DDL, `CALL`, `SELECT FOR UPDATE`, and queries with side-effect functions to verify routing.
4. Test multi-statement transactions to confirm backends do not switch mid-transaction.
5. Write on primary then read via read-only; measure replication lag and test `wait_for_my_writes` if used.
6. Enable connection sharing in staging; test user variables, temporary tables, prepared statements, named locks, transactions, and connection resets.
7. Generate load with multiple application instances; measure client connections at Router and backend connections at MySQL.
8. Stop one secondary and verify Router removes the destination and continues serving new connections.
9. Perform a controlled switchover/failover; verify existing connections error as expected and new connections land on the new primary.
10. Disrupt a Router instance; verify the load balancer fails over to a healthy Router and the pool reconnects.
11. Test TLS, certificate rotation, and account privileges.
12. Re-run tests after upgrading MySQL Server, Router, Connector/J, or the connection pool.

Never kill the primary or induce network partitions in production just to test failover. Use a staging environment with a matching topology and a recovery procedure.

### 20. Troubleshooting by Symptom

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Application cannot connect to Router | Wrong bind address/port, firewall, or Router not running | Check service, listener, logs, and network path |
| Router cannot find primary | Metadata cache unreachable or cluster has no primary | Check cluster status, metadata account, and Router logs |
| New connections go to old primary | Router has not refreshed metadata or app still connects directly | Check topology, metadata cache, and JDBC URL |
| Existing connections fail after failover | Old backend session disconnected | Evict broken connections, reconnect via Router, and retry safely |
| Read queries return stale data | Replica lag or read/write splitting | Read from primary or use `wait_for_my_writes` per policy |
| `SELECT FOR UPDATE` fails on replica | Statement requires a read-write server | Use read-write endpoint/session |
| Connection count on MySQL stays high | App pool holds client connections, Router sharing disabled, or sessions pinned | Measure each layer and inspect sharing blockers |
| Router reports connection sharing inactive | Unsupported protocol/TLS mode or session state preventing sharing | Check classic protocol, TLS options, and executed statements |
| Router hits `max_total_connections` | Too many app pools/clients or application leak | Sum pool sizes, cap concurrency, and scale Router |
| MySQL hits `max_connections` | Backend sessions exceed budget | Measure Router backend/idle pool, reduce pool sizes appropriately, or increase capacity after evaluation |
| Requests wait long for pool | App pool exhausted due to slow queries or long transactions | Optimize queries, reduce hold times, and check pool metrics |
| TLS handshake error | Mismatched certificates, CA, hostname, or modes across the two hops | Check client-router and router-server TLS separately |
| Stored procedure not read/write split as expected | `CALL` is classified as read-write | Use the appropriate endpoint/mode and do not assume Router inspects procedure bodies |

### 21. Production Design Checklist

- [ ] Topology identified: standalone, InnoDB Cluster, or another replica topology.
- [ ] Router bootstrapped and compatible with the MySQL Server version.
- [ ] Multiple Router instances or a Router HA plan in place.
- [ ] Application connects to the Router service rather than a fixed primary IP.
- [ ] Read-write/read-only endpoints separated and tested.
- [ ] Read/write splitting enabled only when Router version, classic protocol, and connection sharing meet requirements.
- [ ] Session states that block connection sharing have been identified.
- [ ] Application pool sizes calculated across process/replica counts and DataSources.
- [ ] Router `max_total_connections`, route `max_connections`, and backend idle pool sized separately.
- [ ] MySQL `max_connections` retains headroom for replication, DBAs, backups, and operations.
- [ ] Transactions are short; `ResultSet`/`Statement`/`Connection` closed; session state reset.
- [ ] Retries are bounded with backoff and idempotency for writes.
- [ ] Read-after-write has a clear consistency policy.
- [ ] TLS configured separately for client-router and router-server hops.
- [ ] Router logs, REST API, pool metrics, and MySQL metrics monitored.
- [ ] Failover, Router restart, backend outage, and pool reconnect tested on staging.
- [ ] Runbook documents how to verify the actual backend and recover from failures.

### 22. Practice Exercise

A Java application has 8 replicas, each running two `HikariDataSource` pools: a write pool with max 20 connections and a read pool with max 30 connections. Both connect to two Router endpoints. The InnoDB Cluster has one primary and two secondaries. After enabling Router 8.4 connection sharing and read/write splitting, connection counts on the primary remain high; some requests reading immediately after writing receive stale data. During a primary failover, several in-flight requests fail with `Communications link failure`.

1. Calculate the maximum number of client connections the application pools can open to Router.
2. Explain why the number of backend connections does not necessarily equal the number of client connections.
3. List session features that can prevent Router from placing a backend connection into the connection pool.
4. Why can a request reading immediately after a write observe an out-of-date replica?
5. Design `read_write`, `read_only`, and `wait_for_my_writes` policies for different business flows.
6. Which error types can be retried, and why does a disconnected `COMMIT` require an idempotency key?
7. Which metrics in HikariCP, Router, and MySQL would you inspect to find the cause of high connection counts?
8. Outline a test plan for primary failover, Router outage, and TLS.

### 23. Operational Principles

Treat the application pool, MySQL Router, and MySQL Server as separate layers with their own connection budgets and states. The application pool reduces per-process connection creation cost; Router routes according to topology and can share backend connections when version/configuration/session allow; MySQL Server still bears the ultimate connection and concurrency limits. Choose read-write/read-only per consistency requirements, keep transactions short, control session state, configure TLS on both hops, and implement reconnection/idempotency in the application. Measure connections at every layer before changing pool sizes or enabling additional sharing mechanisms.

### References

- MySQL Router 8.4 — Connection Routing: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-features-connection-routing.html
- MySQL Router 8.4 — Connection Sharing and Reuse: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-features-connection-sharing.html
- MySQL Router 8.4 — Read/Write Splitting Configuration: https://dev.mysql.com/doc/mysql-router/8.4/en/router-read-write-splitting-configuration.html
- MySQL Router 8.4 — Read/Write Splitting Statements: https://dev.mysql.com/doc/mysql-router/8.4/en/router-read-write-splitting-statements.html
- MySQL Router 8.4 — Application Considerations: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-general-using-developing.html
- MySQL Router 8.4 — Configuration File Options: https://dev.mysql.com/doc/mysql-router/8.4/en/mysql-router-conf-options.html
