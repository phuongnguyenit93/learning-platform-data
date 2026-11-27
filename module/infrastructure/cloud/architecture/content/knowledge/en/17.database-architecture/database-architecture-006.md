# Scaling Connections and Using Connection Pools or Proxies

## Learning Objectives

In cloud application architectures, adding application instances does not automatically make the database process work faster. Each instance can open multiple concurrent connections; when autoscaling, rolling deployments, or traffic bursts occur, total connections can spike and exceed the database's capacity. Even when the database still has CPU headroom, the overhead of creating connections, authentication, TLS, session memory, and resource contention can slow down the system or cause rejected requests.

**Connection pooling** reuses established connections to avoid setup overhead and cap concurrent connections. A **database proxy** introduces an intermediary layer that manages or distributes connections between applications and the database, potentially offering centralized pooling, failover handling, routing, or authentication depending on the product. The two techniques are related but not identical: a pool typically lives inside the application process, whereas a proxy sits on the network path and can manage connections across many clients.

This lesson belongs to the **Database Architecture** chapter and focuses on scaling connections and using connection pools or proxies. It integrates cloud application design from business requirements through networking, compute, data, and deployment models—focusing on Well-Architected trade-offs across reliability, security, scalability, cost, and operations.

After this lesson, you can:

- Explain why database connection count is a finite resource.
- Estimate connection demand from instance count, pool size, concurrency, and workload.
- Distinguish application-side pools, server-side pools, and database proxies.
- Choose pool size, timeouts, lifetimes, validation, and leak detection based on evidence.
- Design for autoscaling, rolling deployments, failovers, and connection storms.
- Identify the impact of transactions, session state, prepared statements, and pooling modes.
- Secure connections using TLS, IAM, secret rotation, network segmentation, and least privilege.
- Monitor pool saturation, wait times, database sessions, query latency, and connection errors.
- Compare TCO across direct connections, in-app pools, and managed proxies.
- Design test scenarios and architectural decisions suited to system scale.

## 1. Why Must Database Connections Be Managed?

A database connection is not merely a TCP socket. Depending on the database and protocol, each session may consume memory, transaction management structures, authentication state, buffers, a backend process or worker, metadata, and tracking resources. Opening a new connection also incurs DNS, TCP handshake, TLS handshake, authentication, and session initialization costs.

Suppose a booking platform runs 20 application instances. Each instance has a max pool size of 30 connections. If every pool reaches capacity simultaneously, the application can hold up to:

~~~text
20 instances × 30 connections = 600 connections
~~~

If the database allocates only 400 connections to application workloads, this configuration already exceeds the budget before accounting for schedulers, workers, admin tools, migrations, or other services. If autoscaling scales out to 40 instances, the combined pool maximum hits 1,200.

The database may reject new connections, causing requests to block on the pool, time out, or fail immediately when acquiring a connection. Scaling out more application instances in that situation can worsen the outage because each new instance spins up another pool.

### 1.1. Connection Count Is Not Throughput

Having more connections does not always mean processing more queries. When session counts grow too high:

- The database spends more memory and CPU managing sessions.
- Context switching, lock contention, and inter-transaction waits increase.
- Cache locality can degrade as working sets fragment.
- Once CPU or disk is saturated, adding connections only lengthens queues.
- Many long-open transactions hold locks or row versions, complicating cleanup depending on the engine.

The goal is keeping connection counts within the range the database processes efficiently while giving the application enough concurrency to meet SLOs.

### 1.2. Distinguishing Connection Types

| Connection Type | Used By | Purpose |
| --- | --- | --- |
| Client-to-application | Web/mobile to API | Receive user requests |
| Application-to-database | API/worker to DB or proxy | Read and write data |
| Proxy-to-database | Proxy to DB | Maintain backend sessions serving clients |
| Admin connections | DBAs, migrations, monitoring | Administration, schema changes, diagnostics |
| Replication connections | Primary DB to replicas/standbys | Data synchronization and failover |

When calculating a connection budget, do not look only at the primary API pool. Background workers, queue consumers, cron jobs, reporting services, and older deployments during rollouts can all connect to the database simultaneously.

## 2. What Is Connection Pooling?

A connection pool is a set of database connections pre-created or created on demand and reused across many operations. Instead of every HTTP request opening and closing a TCP/TLS/database session, the application borrows a connection from the pool, runs its query/transaction, and returns the connection to the pool.

~~~mermaid
flowchart TB
    R1["HTTP request 1"] --> A["Application"]
    R2["HTTP request 2"] --> A
    R3["Worker job"] --> A
    A --> POOL["Connection pool"]
    POOL --> C1["DB connection 1"]
    POOL --> C2["DB connection 2"]
    POOL --> C3["DB connection 3"]
    C1 --> DB[("Database")]
    C2 --> DB
    C3 --> DB
~~~

Pools commonly expose these concepts:

- **Maximum pool size:** maximum connections the pool retains.
- **Minimum idle:** minimum idle connections the pool tries to maintain.
- **Idle connection:** a free connection ready to be borrowed.
- **Active/borrowed connection:** a connection currently in use by an operation.
- **Connection acquisition timeout:** maximum time a caller waits to borrow a connection.
- **Idle timeout:** duration an idle connection waits before being closed.
- **Max lifetime:** maximum age before the pool replaces a connection.
- **Validation/keepalive:** mechanisms to verify or keep connections alive.
- **Leak detection:** alerts when a connection is held unusually long.

Exact configuration names and semantics depend on the library. Always read the documentation for your specific pool and driver.

### 2.1. Lifecycle of a Connection in a Pool

1. The pool initializes or creates connections on demand.
2. The application requests a connection.
3. If an idle connection is available, the pool lends it out.
4. If none is free and the pool is below its limit, it may create a new connection.
5. If at the limit, the caller waits until a connection is returned or times out.
6. When the application closes the logical connection, the pool typically returns it to the pool instead of closing the physical socket.
7. The pool may validate, reset session state, or discard broken connections before the next borrow.

In Java JDBC, calling `close` on a pooled connection proxy typically returns the connection to the pool. Always wrap resources in `try-with-resources`; never store connections in fields or hold them across requests.

### 2.2. A Pool Does Not Automatically Make Queries Faster

A pool lowers connection setup overhead and caps concurrency. It does not fix unindexed queries, long transactions, lock contention, or an under-provisioned CPU/I/O tier. Too small a pool causes long request waits; too large a pool overwhelms the database with sessions. Size pools using benchmarks and a system-wide connection budget.

## 3. Common Pooling Models

### 3.1. Application-Side Pooling

Each application or process runs its own pool—for example, every Spring Boot instance running HikariCP. This is popular because it is simple, adds no extra network hops, and coordinates directly with thread/application lifecycles.

Pros: fewer infrastructure components; applications control pool size and timeouts; full use of driver transaction/session semantics; no separate proxy needed.

Limitations: every instance holds its own pool so total connections scale with replica count; autoscaling swings connection counts sharply; multiple applications must coordinate their shared DB budget; serverless functions scaling per invocation can generate huge client connection bursts.

### 3.2. Proxy or Middleware Pooling

A proxy sits between applications and the database. Applications connect to the proxy; the proxy maintains backend connections to the database and can multiplex clients depending on its mechanics.

~~~mermaid
flowchart LR
    APP1["API instances"] --> P["Database proxy"]
    APP2["Worker instances"] --> P
    APP3["Serverless functions"] --> P
    P --> B1["Backend connection 1"]
    P --> B2["Backend connection 2"]
    P --> B3["Backend connection 3"]
    B1 --> DB[("Database")]
    B2 --> DB
    B3 --> DB
~~~

A proxy can centralize connection management, reduce backend sessions, assist with authentication or failover, and provide a stable endpoint. However, not every proxy can multiplex all sessions; restrictions may apply to transactions, prepared statements, temporary tables, session variables, or protocol features.

### 3.3. Application Pool Combined with a Proxy

A common architecture pairs HikariCP inside each application instance with a managed proxy in front of the database:

~~~mermaid
flowchart TB
    subgraph COMPUTE["Compute layer"]
      A1["API instance 1"] --> H1["Hikari pool 1"]
      A2["API instance 2"] --> H2["Hikari pool 2"]
      W["Worker"] --> HW["Worker pool"]
    end
    H1 --> PROXY["DB proxy / connection manager"]
    H2 --> PROXY
    HW --> PROXY
    PROXY --> DB[("Database cluster")]
~~~

Here there are two pooling layers. The application pool bounds connections from each process; the proxy manages backend sessions to the database. Avoid configuring two layers of timeouts and capacities without understanding their interaction, since callers may wait in the application pool and then wait again at the proxy.

### 3.4. Comparison

| Criterion | Application-Side Pool | Centralized Pool / Proxy |
| --- | --- | --- |
| Scope | Single process/instance | Multiple clients/applications |
| Connection management | Configured per application | Proxy can consolidate and distribute |
| Horizontal scaling | Total pool grows with instances | Proxy can reduce backend sessions |
| Network hop | Direct to DB | Adds one hop |
| Session semantics | Closer to database/driver | May be constrained by multiplexing |
| Operations | Relatively simple | Adds a service, HA, quotas, and cost |
| Useful when | Stable apps with controlled instance counts | Many clients, serverless, bursts, needing failover endpoints |

No option fits every workload. An app with a handful of instances may only need local pools; a platform with hundreds of short-lived functions may need a proxy or a different data model.

## 4. Estimating the Connection Budget

### 4.1. Calculating the Application Ceiling

~~~text
Application connection ceiling
  = Number of instances × Maximum pool size per instance
~~~

With multiple components:

~~~text
Total possible client connections
  = Σ(instances_i × maxPoolSize_i)
~~~

Example:

| Component | Max Instances | Max Pool per Instance | Max Connections |
| --- | ---: | ---: | ---: |
| Booking API | 12 | 18 | 216 |
| Admin API | 3 | 8 | 24 |
| Background workers | 8 | 5 | 40 |
| Reporting service | 2 | 6 | 12 |
| **Total** | | | **292** |

If the database permits 350 connections, do not allocate all 350 to applications. Reserve capacity for DBAs, migrations, monitoring, replication, maintenance, and other services.

### 4.2. System-Wide Connection Budget

Example budget:

| Group | Connection Budget |
| --- | ---: |
| Application workloads | 250 |
| Reporting/analytics jobs | 25 |
| Admin/migration/monitoring | 20 |
| Replication and internal services | 15 |
| Headroom for failover/scaling | 40 |
| **Total** | **350** |

The budget should have an owner and be updated whenever workloads are added. If the database enforces per-user, per-database, per-role, or per-tenant limits, calculate by each scope rather than only summing the global total.

### 4.3. Autoscaling and Deployment Overlap

Suppose an API scales up to 10 instances with a max pool of 20. During a rolling deployment, 10 old instances and 10 new instances can coexist. If all pools fill up, connections can temporarily spike to 400 instead of 200.

Account for max autoscale replicas, surge/unavailable settings, graceful shutdown, pool minimum idle, concurrent workers/crons, failover, and extra migration connections. Calculate the connection budget for **deployment and recovery peaks**, not just steady state.

## 5. Pool Sizes Should Never Be Chosen Arbitrarily

A practical starting point is setting a small pool, measuring throughput/latency, and increasing gradually until gains plateau. Idle connections still carry overhead, so max pool size should not blindly equal request-handling thread counts.

Principles:

- Sum pools across all replicas before setting max size.
- Start modestly and benchmark with realistic query mixes.
- Cap total concurrency hitting the database, not just per endpoint.
- Background workers can use smaller pools than APIs if jobs are heavy.
- Reserve separate connections for admin/maintenance per policy.
- Never enlarge a pool to mask slow queries or long-held transactions.
- Inspect CPU, IOPS, locks, buffer/cache hits, and throughput alongside connection counts.

### 5.1. Little's Law and Estimating Active Connections

Under steady-state load, Little's Law estimates average concurrency:

~~~text
Average concurrent operations
  ≈ Arrival rate × Average time in system
~~~

For example, if the database handles 120 queries/sec with an average connection hold time of 80 ms:

~~~text
120 queries/s × 0.08 s = 9.6 concurrent connections
~~~

This reflects average concurrency in a simplified model. Long transactions, tail query latency, bursts, or multi-query transactions require benchmarking and percentile analysis. You cannot take 9.6 and conclude a max pool of 10 is guaranteed sufficient.

### 5.2. Pool Utilization and Queueing

If max pool size is 20 and all 20 connections are consistently active, new callers must wait. Sustained high utilization causes acquisition latency to spike sharply whenever query durations fluctuate.

Monitor active, idle, and total connections, pending/waiting borrowers, acquisition time, usage duration, creation/close rates, and timeout counts.

A chronically full pool may indicate an undersized pool, slow queries, long transactions, blocked threads, or an under-capacitated database. Always examine DB metrics alongside pool metrics.

## 6. Configuring Connection Pools in Java / Spring Boot

### 6.1. HikariCP and JDBC

Spring Boot typically uses HikariCP as the default JDBC connection pool when the appropriate dependency is included. Configuration must align with instance counts and the DB budget.

Illustrative YAML example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-proxy.internal:5432/booking
    username: booking_app
    password: $DB_PASSWORD
    hikari:
      pool-name: booking-api
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 2000
      idle-timeout: 300000
      max-lifetime: 1500000
      validation-timeout: 1000
      keepalive-time: 120000
      leak-detection-threshold: 0
~~~

These values are illustrative, not verbatim production recommendations. Verify your HikariCP, driver, proxy, and database versions. In production, fetch secrets from a secret manager or approved identity mechanism rather than storing plaintext in config files.

### 6.2. Parameter Meanings

| Parameter | Meaning | Misconfiguration Risk |
| --- | --- | --- |
| `maximumPoolSize` | Maximum connections allowed in pool | Too large overloads DB; too small increases wait times |
| `minimumIdle` | Minimum idle connections maintained | Too high leaves idle sessions; too low increases connection open latency |
| `connectionTimeout` | Max wait to borrow a connection | Too long hangs requests; too short fails prematurely |
| `idleTimeout` | Closes idle connections beyond threshold | Can cause connection churn under fluctuating traffic |
| `maxLifetime` | Max lifetime of a connection | Too long hits server/proxy-closed sockets; too short causes constant handshakes |
| `validationTimeout` | Timeout for validating a connection | Too long slows borrows; too short causes false failures |
| `keepaliveTime` | Periodically validates/maintains idle connections where supported | Adds periodic traffic; does not replace health checks |
| `leakDetectionThreshold` | Warns when a connection is held too long | Too low triggers noisy false alerts |

Do not enable leak detection with an overly tight threshold in production without understanding your workload. Valid transactions lasting longer than the threshold will trigger false leak warnings.

### 6.3. Always Close Connections

Use `try-with-resources` to return connections, statements, and result sets to the pool:

~~~java
public Optional<Booking> findBooking(UUID bookingId) throws SQLException {
    String sql = """
        SELECT id, status, check_in, check_out
        FROM bookings
        WHERE id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, bookingId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return Optional.empty();
            }

            return Optional.of(new Booking(
                result.getObject("id", UUID.class),
                result.getString("status"),
                result.getDate("check_in").toLocalDate(),
                result.getDate("check_out").toLocalDate()
            ));
        }
    }
}
~~~

When the `try` block exits, `close` returns the logical connection to the pool. Never hold a connection across sending emails, calling HTTP APIs, or waiting on users. Execute short DB read/write transactions and release the connection before performing external I/O.

### 6.4. Transaction Boundaries

Long-open transactions hold connections longer. For example, a transaction that updates a booking and waits 5 seconds on a payment provider call holds the DB session throughout that network wait. Under high traffic, the pool drains quickly.

A cleaner design:

1. Short transaction creating a pending payment state and operation ID.
2. Commit and return the connection to the pool.
3. Call the payment provider outside any DB transaction.
4. Run a second short transaction updating the outcome using an idempotency key.
5. Reconcile if a timeout leaves the outcome uncertain.

Never acquire a DB connection before doing non-DB work if you do not yet need to read or write data.

## 7. Pooling and Session State: Limits to Understand

Connections are returned to the pool and reused by subsequent requests. Session state must therefore be handled carefully:

- Transactions must commit or roll back before returning the connection.
- Never leave session variables, roles, or `search_path` modified without resetting them.
- Temporary tables/session-level objects may persist into the next borrow depending on DB and pool behavior.
- Prepared statements have lifecycles tied to drivers/sessions; proxy pooling can interfere.
- Advisory/session locks can outlive a logical request if not explicitly released.
- Changed transaction isolation levels or timezones must be properly reset.
- `LISTEN`/`NOTIFY`, long-lived cursors, or streaming results may require session affinity.

Applications must never assume every borrowed connection is a brand-new session. The pool can hand back a previously used session.

### 7.1. Transaction Pooling vs. Session Pooling

Some proxies support multiple pooling modes:

- **Session pooling:** the client keeps a backend connection for the entire session. Broad compatibility with session state, but lower multiplexing.
- **Transaction pooling:** a backend connection is assigned to a client only for the duration of a transaction; after commit/rollback it returns to the pool for other clients. Increases backend sharing, but restricts session-dependent features.
- **Statement pooling:** a backend connection is assigned per statement in supporting systems; even more restrictive for multi-statement transactions and session state.

Not every proxy supports every mode. Transaction pooling can break session-level features, temporary tables, prepared statements, advisory locks, or multi-statement transaction patterns. Check your proxy's compatibility matrix and run integration tests.

### 7.2. Prepared Statements and Driver Behavior

Prepared statements can be managed by the driver, server, or proxy. Some proxies must track/route prepared statement state; certain transaction-pooling setups do not fully support named server-side prepared statements. When introducing a proxy, check whether the driver caches prepared statements, whether statements are named server-side, how the proxy supports protocol features in your mode, and whether statements remain valid after backend switches or failovers.

Do not disable prepared statements blindly. Measure performance and compatibility across your actual driver, server, and proxy.

## 8. Database Proxies: Capabilities and Choices

### 8.1. Where Does the Proxy Sit?

A proxy exposes an endpoint to applications, accepts client connections, and manages backend connections to the database. Depending on design, it can multiplex many client connections onto fewer backend connections, manage connection lifecycles/health, route to writer/reader endpoints, assist failover, integrate IAM/DB authentication, and enforce/observe connection limits.

Capabilities depend on the product. Never assume a proxy automatically load-balances queries, safely retries transactions, or provides zero-disruption failovers.

### 8.2. Managed Proxies vs. Self-Managed Proxies

| Criterion | Managed Database Proxy | Self-Managed Proxy |
| --- | --- | --- |
| Setup and patching | Provider manages most of the infrastructure | Team deploys, patches, and upgrades |
| HA | May include service-managed HA | Team designs replicas, health checks, and failover |
| Deep configuration | May be restricted | Greater control |
| IAM/DB integration | Typically integrated with cloud IAM | Team configures and manages |
| Observability | Provider-supplied metrics/logs | Depends on team instrumentation |
| Cost | Service/compute/connection fees | Compute, networking, licenses, and labor |
| Lock-in | Can be tied to cloud service | More portable, though config differences remain |

Examples include Amazon RDS Proxy, Cloud SQL connectors/proxy, or PgBouncer for PostgreSQL. They differ in capabilities and semantics; evaluate current documentation, engine/version support, networking, authentication, pooling modes, and pricing for the specific service.

### 8.3. A Proxy Does Not Replace an Application Pool

An application can still open hundreds of logical client connections to a proxy. While the proxy reduces backend DB sessions, it does not eliminate client connection overhead, blocked threads, or memory used for client sessions in the app. Cap connections at both layers and monitor wait times at each hop.

## 9. Serverless and Connection Scaling

Serverless functions scale concurrency rapidly with event/request volume. If every invocation opens a fresh database connection, the database suffers a connection storm.

~~~mermaid
flowchart TB
    E["Traffic burst"] --> S["Serverless platform"]
    S --> F1["Function invocation 1"]
    S --> F2["Function invocation 2"]
    S --> F3["Function invocation N"]
    F1 --> PROXY["Database proxy"]
    F2 --> PROXY
    F3 --> PROXY
    PROXY --> POOL["Bounded backend pool"]
    POOL --> DB[("Database")]
~~~

A proxy or connection manager can reduce backend sessions, yet you still need to:

- Cap function concurrency / reserved concurrency.
- Set timeouts and cap client connections to the proxy.
- Reuse clients across warm execution environments where platform semantics allow.
- Avoid holding connections while functions sit idle.
- Use queues to absorb bursts if business latency permits.
- Choose databases/proxies compatible with transaction semantics.
- Benchmark connection establishment rates during cold starts or scale-outs.
- Monitor quotas across the proxy, DB, and network.

For short-lived functions, transaction pooling can work well provided the application does not rely on session state across transactions.

## 10. Timeouts: Coordinating Across Layers

A request traverses the client, API gateway, application thread, application pool, proxy, database connection, query execution, and response. Each layer has its own timeout.

~~~mermaid
flowchart LR
    C["Client timeout"] --> G["Gateway timeout"]
    G --> A["App request timeout"]
    A --> P["Pool acquisition timeout"]
    P --> X["Proxy/backend timeout"]
    X --> D["DB statement/lock timeout"]
~~~

If pool acquisition timeout is 30 seconds while gateway timeout is 10 seconds, the client abandons the request long before the pool fails. If query timeout exceeds the HTTP deadline, the backend keeps burning resources after the caller gave up.

Design an explicit timeout budget:

- The request deadline is the overall cap.
- Pool acquisition timeout takes only a small slice of the budget.
- Proxy connect/borrow timeouts align with the application pool.
- Database statement timeouts prevent runaway queries.
- Lock timeouts bound lock waits.
- Network/socket timeouts align with retry policies.

Never set every timeout to the exact same value. When a request hits its deadline, cancel the statement or abort work via driver/database mechanisms, and verify queries actually stop instead of continuing to consume resources.

## 11. Failover, DNS, and Connection Lifecycles

When a database fails over to another node, existing TCP connections may reset or become stale. Pools and proxies must detect broken connections, evict them, and open fresh ones. Applications must handle exceptions and apply controlled retries.

Check DNS TTLs and how drivers/proxies resolve endpoints; connection max lifetimes relative to server/proxy limits; validation/keepalive settings; retries after ambiguous commits where the response was lost; proxy HA; and the risk of a connection storm hitting the new endpoint.

### 11.1. Retrying Transactions Is Not Always Safe

If a client sends `UPDATE`, the database commits, and the network drops before the response returns, the application does not know whether the transaction committed. Blindly retrying can apply the side effect twice.

Use idempotency keys, unique business keys, optimistic versioning, or post-uncertain-outcome reconciliation. Pools and proxies improve connectivity, not the business correctness of retries.

### 11.2. Post-Outage Connection Storms

When a database recovers, every instance may try to reconnect simultaneously. To flatten the spike:

- Limit pool growth rates and startup connections.
- Use exponential backoff with jitter for reconnects.
- Cap application concurrency while the DB is stabilizing.
- Use circuit breakers or retry budgets.
- Reserve admin/monitoring connections for diagnostics.
- Avoid restarting the entire fleet simultaneously unless required.
- Monitor connection creation rates and authentication latency.

## 12. Securing Connection Pools and Proxies

Connection pooling changes how connections are shared; it does not relax security requirements.

### 12.1. TLS and Network Paths

Use TLS for app-to-proxy and proxy-to-database links where supported; verify certificates and hostnames properly; deploy proxies in appropriate private networks/subnets; enforce firewall rules permitting only required sources, destinations, and ports; and verify DNS/private endpoints and bidirectional routes. Never expose database or proxy endpoints publicly without strict justification and controls.

### 12.2. Identity and Secret Rotation

- Use per-workload database users or service identities.
- Grant least privilege per schema, table, and operation.
- Separate credentials for APIs, workers, reporting, and migrations.
- Store secrets in a secret manager or appropriate identity provider.
- Design rotation so pools establish new connections using updated credentials.
- Revoke old credentials only after a tested overlap window.
- Never log passwords, tokens, or full connection strings.

If the proxy supports IAM authentication or short-lived tokens, verify where tokens are fetched/refreshed, how token lifetime compares to connection lifetime, and how the system behaves if the identity provider transiently fails.

### 12.3. Session Reuse and Tenant Isolation

When multiple tenants share a pool or proxy, never rely on unreset session variables to separate tenants. Enforce tenant authorization at application/query boundaries; if using RLS, ensure tenant context is set safely inside each transaction and reset before returning the connection to the pool.

Never allow a previous tenant's session state to leak to the next tenant. Test sequential connection reuse across multiple tenants, including error and rollback paths.

## 13. Observability: Watching Pool, Proxy, and Database Together

Looking only at DB connection counts is insufficient for diagnosis. The DB may have spare sessions while the app pool is exhausted; the app pool may look idle while the proxy cannot obtain backend connections.

### 13.1. Application Pool Metrics

| Metric | Meaning |
| --- | --- |
| Active connections | Connections currently borrowed |
| Idle connections | Connections available for borrow |
| Total connections | Total connections managed by the pool |
| Pending threads/waiters | Callers currently waiting for a connection |
| Acquisition latency | Time spent waiting to borrow a connection |
| Usage duration | Duration a connection is held |
| Creation/close rate | Rate of connection creation and destruction |
| Timeout count | Failures to acquire a connection within deadline |
| Leak warnings | Connections held unusually long |

### 13.2. Proxy and Database Metrics

Depending on the product, track proxy client connections, backend connections, pool utilization, borrow wait times, rejected connections, authentication failures, backend health, and failover events.

On the database, monitor session counts by user/application, active/idle sessions, transaction age, lock waits, deadlocks, query latency, CPU, memory, IOPS, cache hits, replication lag, and connection rejections.

### 13.3. Connecting Metrics into a Diagnostic Chain

Suppose app pool pending waiters and acquisition latency spike:

- If app `active = max`, `idle = 0`, and proxy/backend have spare capacity: queries/transactions are holding connections too long or the app pool is undersized.
- If the app still has client connections available but proxy borrow wait rises: the proxy backend pool may be saturated or the database is rejecting sessions.
- If DB CPU/IO/lock waits are high: enlarging the app pool or proxy capacity will likely worsen the incident.
- If connection creation rate spikes after a deploy: inspect `minimumIdle`, `maxLifetime`, rollout surge, and startup behavior.

Include dimensions for service, environment, deployment version, and database role on dashboards; avoid high-cardinality labels per individual connection or request.

## 14. SLOs and Quality Scenarios

The thresholds below are learning examples only. In practice, define exact workloads, measurement windows, deadlines, and load conditions.

| ID | Scenario | Expected Response | Illustrative Metric |
| --- | --- | --- | --- |
| QA-POOL-01 | Peak traffic triples | Pool keeps connections within budget; wait stays bounded | Pool acquisition p95 under 100 ms; within DB budget |
| QA-POOL-02 | Autoscale + rolling deployment overlap | Total connections stay within app allocation | Peak connections below approved limit |
| QA-POOL-03 | Worker holds connection too long | Leak/long transaction detected | Alert within 2 minutes; service pool does not exhaust |
| QA-PROXY-01 | Proxy backend pool saturates | Requests are throttled or time out by deadline | Rejections/timeouts alerted; DB stays under max sessions |
| QA-FAIL-01 | Database failover | Pool evicts stale connections and recovers with backoff | Connections recover within RTO; no reconnect storm |
| QA-SEC-01 | Old credentials rotated | New connections use new credentials; old revoked | Zero secrets in logs; connections succeed post-rotation |
| QA-SESSION-01 | Two tenants reuse same backend session | Zero leakage of session state or auth context | 100% of isolation test suite passes |
| QA-COST-01 | Direct pool vs. proxy comparison | End-to-end path cost stays within budget at same SLO | Cost per successful transaction measured per model |

Connection SLOs cannot rely solely on connection counts. Combine acquisition latency, query latency, transaction success, and user impact.

## 15. TCO: Direct Connections, Pools, and Proxies

### 15.1. Cost Components

**Direct connection with application pool:** application compute and connection management; database capacity/session overhead; monitoring, troubleshooting, and pool ops; reconnect/failover headroom; networking/TLS/authentication.

**With proxy:** proxy instance/compute/connection fees per service; network hop and data processing; potential DB backend capacity savings if multiplexing is effective; HA, scaling, monitoring, and support; setup, migration, and session-compatibility testing time; lock-in and operational overhead of a new component.

A proxy can lower total cost if it meaningfully cuts backend sessions or simplifies operations; it can raise total cost for small workloads or when clients still hold backend sessions for long durations.

### 15.2. Hypothetical Cost Example

Unit: million VND/month. The numbers below illustrate comparison methodology only and are not price quotes.

| Line Item | A: Direct App Pool | B: App Pool + Proxy |
| --- | ---: | ---: |
| Allocated application compute | 35 | 35 |
| Allocated database capacity | 80 | 68 |
| Proxy service | 0 | 22 |
| Network/processing | 5 | 8 |
| Observability/security | 8 | 10 |
| Allocated operations | 14 | 12 |
| **Total** | **142** | **155** |

In this example, the proxy lowers assumed DB capacity cost, yet total cost remains higher due to proxy and networking charges. If a serverless workload creates many short-lived connections and the proxy avoids scaling DB capacity or prevents incidents, TCO can flip. Always substitute real benchmarks and current pricing.

### 15.3. Cost per Successful Transaction

~~~text
Cost per successful transaction
  = Total monthly cost of the database access path
    / Number of successful business transactions
~~~

The denominator is successful business transactions—not query count or connection count. If pool timeouts fail requests, the compute/log/DB cost of those failed attempts still sits in the numerator.

## 16. Design and Implementation Process

1. **Gather load profiles:** request rates, query mix, transaction durations, peaks/bursts, service counts, and autoscaling ranges.
2. **Survey the DB:** max connections, session memory, CPU/I/O, locks, role/user limits, replica topology, and reserved capacity.
3. **Build the budget:** sum max pools across APIs, workers, reporting, migrations, and deployment overlap; leave headroom.
4. **Choose architecture:** direct pool, proxy, or pool + proxy; verify backend connection semantics.
5. **Configure pools:** max/min, acquisition timeout, idle timeout, max lifetime, keepalive, and validation.
6. **Design transactions:** keep transactions short; never hold connections across external network calls.
7. **Design failure handling:** timeout budgets, retries, idempotency, circuit breakers, reconnect backoff, and failover.
8. **Design security:** private networking, TLS, identities, secret rotation, and least privilege.
9. **Instrument observability:** app pools, proxy, database, query latency, and business SLOs.
10. **Test:** peaks, autoscaling, rolling deploys, connection storms, failover, credential rotation, and session reuse.
11. **Tune:** benchmark pool sizes with realistic query mixes; add capacity at the real bottleneck.
12. **Hand off:** assign connection budget owner, dashboards, alerts, runbooks, quotas, and ADR.

### 16.1. Sample Connection Budget

~~~yaml
database: booking-primary
max_database_connections: 500
reserved:
  admin_and_migration: 25
  replication_and_monitoring: 25
  operational_headroom: 50
application_budget: 400
workloads:
  booking_api:
    max_instances: 15
    pool_max_per_instance: 16
    calculated_max: 240
  admin_api:
    max_instances: 3
    pool_max_per_instance: 8
    calculated_max: 24
  background_worker:
    max_instances: 10
    pool_max_per_instance: 6
    calculated_max: 60
  reporting:
    max_instances: 2
    pool_max_per_instance: 10
    calculated_max: 20
calculated_application_total: 344
unallocated_application_headroom: 56
status: proposed
~~~

This is a planning template. Real connection counts also depend on `minimumIdle`, startup behavior, deployment surges, proxy multiplexing, health checks, and how the engine counts sessions. Templates never replace load testing.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting large pools per instance without summing fleet-wide | DB runs out of connections when scaling | Maintain a fleet-wide connection budget |
| Increasing pool size when queries slow down | Sessions and contention escalate | Measure DB bottlenecks and query/transaction duration |
| Holding connections across external API calls | Pool drains even when DB queries are fast | Close transactions before external I/O |
| Failing to close connections | Leaks and pool timeouts | `try-with-resources`, audit all code paths |
| Pool max exceeding DB concurrency capacity | DB overload | Benchmark and cap app concurrency |
| Rolling deploy running two pool generations at once | Connection spike | Account for surge, min idle, and graceful shutdown |
| Blind retries after failover | Duplicate business writes | Idempotency keys and reconciliation |
| Monitoring only DB sessions | Misses app pool waits or proxy saturation | Three-layer dashboard |
| Using transaction pooling while relying on session state | Semantic bugs or cross-request data leaks | Check compatibility and reset state |
| Misaligned timeouts across layers | Requests stall past deadlines | End-to-end timeout budget |
| Simultaneous fleet reconnects after outage | Connection storm | Backoff/jitter and startup ramp |
| Assuming proxy HA is infallible | Proxy/backend pool becomes SPOF | Multi-AZ/HA and failure drills |
| Skipping rotation tests | New connections fail to use rotated credentials | Test rotation while old connections remain open |

## 18. Case Study: Spring Boot in the Cloud with a Shared Database

### 18.1. Context

A booking platform runs 15 Booking API instances at peak, 3 Admin API instances, 10 workers for email/inventory/reconciliation, and 2 reporting instances. Its managed PostgreSQL database has a limit of 500 connections for workloads and administration per service configuration.

Initially, each Booking API instance had a max pool of 40. The API alone could open:

~~~text
15 × 40 = 600 connections
~~~

That was before counting any other services. During peak hours, a new deployment triggered widespread connection acquisition timeouts and the database rejected new sessions.

### 18.2. Assessment and Changes

The team created a connection budget, sized smaller pools per workload, shortened transaction durations, and offloaded heavy reports to an appropriate read replica/warehouse. After benchmarking, API used max pool 16, Admin 8, Worker 6, and Reporting 10:

~~~text
Booking API: 15 × 16 = 240
Admin:        3 × 8  =  24
Worker:      10 × 6  =  60
Reporting:    2 × 10 =  20
--------------------------------
Total application ceiling = 344
~~~

The database reserved 400 connections for the application budget and the rest for migrations, admin, monitoring, and headroom. Figures still had to be tested under rollout surges and failover.

The team also evaluated a proxy because short-lived workloads and serverless functions can spin up connections rapidly. The proxy was deployed to staging to verify session state, prepared statements, transactions, IAM/TLS, failover, and metrics before considering production.

### 18.3. Acceptance Tests

- Load test at peak traffic, measuring active/idle/pending counts and p95/p99 acquisition latency.
- Scale from baseline instances to max replicas; verify DB sessions stay within budget.
- Rolling deployment with surge to measure real peak connections.
- Terminate primary DB and observe stale connections, reconnect rates, and transaction outcomes.
- Intentionally slow a query to verify pool saturation and alert triggers.
- Intentionally hold a connection past threshold in a test to verify leak detection.
- Rotate credentials while existing pool connections are still active.
- Reuse sessions sequentially across two tenants to verify state reset and isolation.
- If using a proxy, compare backend connection counts, borrow latency, error rates, and cost.

### 18.4. Expected Architectural Outcome

The system operates with a governed connection budget, benchmarked pool sizes, timeouts aligned to request deadlines, and transactions that never hold connections across external network calls. A proxy is deployed only if it demonstrably improves specific metrics—such as backend session count, failover behavior, or serverless operations. Every change ships with dashboards and runbooks.

## 19. Practical Exercise

An e-commerce application runs Spring Boot on Kubernetes and serverless functions. It has 25 API pods, each currently configured with max pool 30; up to 40 functions can run concurrently during flash sales; and 5 workers process orders. The database caps application workloads at 600 sessions and requires reserving 100 sessions for admin, replication, monitoring, and operations.

Complete the following:

1. Calculate the connection ceiling of the 25 pods alone (excluding functions and workers) and explain why the current config is risky.
2. Propose a connection budget for APIs, functions/proxy, and workers while preserving headroom for autoscaling and rolling deploys.
3. Distinguish an application pool from a database proxy, noting when a proxy reduces backend connections.
4. Estimate average concurrency if the workload generates 200 queries/sec with an average connection usage duration of 50 ms.
5. Propose max pool, minimum idle, acquisition timeout, max lifetime, and a benchmarking plan, explaining why those numbers are initial assumptions.
6. Analyze why holding a JDBC connection while calling a payment API exhausts the pool.
7. Describe session limitations when a proxy runs in transaction pooling mode.
8. Design an end-to-end timeout budget across client, gateway, app pool, proxy, and database statements.
9. Plan failover handling and connection-storm prevention after database recovery.
10. Design a dashboard covering the application pool, proxy, and database, listing at least five actionable alerts.
11. Compare TCO between direct connections and pool + proxy for the same workload and SLO.
12. Write an ADR for the final decision and revisit conditions.

**Self-assessment hints:** A solid solution calculates fleet-wide connections including autoscaling and deployment overlap, distinguishes logical client connections from backend database sessions, and pairs measurements of acquisition wait, DB capacity, failover behavior, and business transaction success.

## 20. Pre-Production Checklist

- [ ] Real connection limits for database, roles, users, and proxy are known.
- [ ] Max pools across all APIs, workers, reporting, and functions are summed.
- [ ] Autoscaling maximums, deployment surges, and startup behavior are accounted for.
- [ ] Separate capacity is reserved for admin, migrations, monitoring, replication, and headroom.
- [ ] Pool sizes are based on benchmarks/query mixes, not arbitrary thread counts.
- [ ] Acquisition timeout, idle timeout, max lifetime, and validation are properly configured.
- [ ] Connections are returned via `try-with-resources` and never held across external I/O.
- [ ] Transactions are short and session state is reset.
- [ ] Compatibility of prepared statements, cursors, temp tables, and session features with proxy mode is verified.
- [ ] Timeouts are coordinated across client, gateway, pool, proxy, and database.
- [ ] Idempotency/reconciliation covers retries after timeouts or failovers.
- [ ] TLS, private networking, least privilege, and secret rotation are enforced.
- [ ] Dashboards monitor pool, proxy, and database simultaneously.
- [ ] Autoscaling, rolling deploys, failover, connection storms, and credential rotation have been tested.
- [ ] Runbooks, connection budget owner, and a cost model are established.

## 21. Well-Architected Evaluation

| Pillar | Questions When Reviewing Connection Pooling / Proxies |
| --- | --- |
| **Operational Excellence** | Do connection budgets, dashboards, alerts, runbooks, rotation, and failover drills have clear owners? |
| **Security** | Are TLS, identities, least privilege, private endpoints, secret rotation, and session isolation verified? |
| **Reliability** | Do pools/proxies recover cleanly from stale connections, DB failovers, deploy overlaps, and connection storms? |
| **Performance Efficiency** | Do pool sizes, acquisition latency, query latency, concurrency, and DB saturation match the workload? |
| **Cost Optimization** | Are proxy fees offset by reduced backend sessions, fewer incidents, and lower ops toil; what is the cost per transaction? |
| **Sustainability** | Are excessive idle connections, repeated reconnects, and over-provisioned DBs/proxies avoided? |

**Conclusion:** Connection pools and database proxies throttle connection bursts, reuse sessions, and shield the database from uncontrolled client growth. Effectiveness depends on a fleet-wide connection budget, benchmarked pool sizes, short transactions, compatible session semantics, coordinated timeouts, and tested failover behavior. Never treat increasing connections as the default way to raise throughput; find the real bottleneck, measure end-to-end from application through proxy to database, and balance reliability, security, scalability, cost, and operations under Well-Architected principles.
