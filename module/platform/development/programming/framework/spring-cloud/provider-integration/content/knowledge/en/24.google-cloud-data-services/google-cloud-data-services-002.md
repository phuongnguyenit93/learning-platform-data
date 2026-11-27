# Connection Pooling, Private IP, and IAM Database Authentication When Supported

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to access storage, messaging, data, and manage identity/permissions. On Google Cloud, **Cloud SQL** provides managed relational databases. A Spring Boot application can connect successfully via JDBC yet still experience issues under increased load, when multiple replicas open pools concurrently, when workloads move to a private network, or when using IAM database authentication.

This lesson focuses on three operational concerns:

1. **Connection pool:** configuring HikariCP and calculating total connections across all replicas, workers, migration jobs, and admin tools.
2. **Private IP:** placing the workload on the right VPC path and configuring Cloud SQL Connector to use the private address.
3. **IAM database authentication:** distinguishing Cloud SQL connection permissions from database login permissions and SQL privileges; enabling it only when supported by the engine/version.

After this lesson, you will be able to estimate a connection budget for Cloud SQL, tune pools for autoscaling, design private networking for Cloud Run/GKE, configure IAM DB auth for PostgreSQL/MySQL when appropriate, and test recovery capability.

> **Scope:** The main examples use Cloud SQL PostgreSQL, Spring Boot, HikariCP, and Cloud SQL Java Connector. Some similar options apply to MySQL; IAM database authentication support and database user naming rules depend on the engine/version. Do not assume every Cloud SQL engine supports the exact same mechanism.

## 1. Three Layers to Control When Connecting to Cloud SQL

A successful connection must simultaneously satisfy three layers:

| Layer | Question to answer | Example |
| --- | --- | --- |
| Network | Does the workload have a route to the selected Cloud SQL address? | VPC, Private IP, firewall, egress |
| Cloud IAM | Is the workload permitted to connect to the instance? | ADC, `roles/cloudsql.client` |
| Database authorization | Which identity logs in and which SQL statements may it run? | DB user, IAM DB auth, SQL grants |

HikariCP is a fourth layer on the application side: it manages the lifecycle and count of JDBC connections. HikariCP does not grant IAM permissions, create network routes, or replace the database user.

~~~mermaid
flowchart TD
    APP["Spring Boot replicas"] --> POOL["HikariCP pools"]
    POOL --> JDBC["JDBC driver + Cloud SQL Connector"]
    NET["VPC route / Private IP"] --> JDBC
    IAM["ADC + Cloud SQL IAM"] --> JDBC
    JDBC --> DB["Cloud SQL instance"]
    DB --> AUTH["DB user / IAM DB authentication"]
    AUTH --> SQL["SQL roles and grants"]
~~~

If the application reports timeouts, investigate the network and pool. If it reports `PERMISSION_DENIED` in the connector, check IAM. If it connects but `SELECT` statements are rejected, check database grants. Do not handle all three error types by increasing pool size or granting Owner to the service account.

## 2. How Does a Connection Pool Work?

### 2.1. Why Do We Need a Pool?

Establishing a database connection has overhead: opening a socket, authenticating, establishing TLS, creating a session, and initializing JDBC state. If every HTTP request creates and closes a new connection, the system wastes time and can cause connection storms when traffic spikes.

A **connection pool** keeps a group of JDBC connections for requests to borrow and return. Spring Boot defaults to HikariCP in typical JDBC/JPA configurations.

~~~mermaid
flowchart LR
    R1["HTTP request A"] --> POOL["HikariCP"]
    R2["HTTP request B"] --> POOL
    R3["HTTP request C"] --> POOL
    POOL --> C1["JDBC connection 1"]
    POOL --> C2["JDBC connection 2"]
    POOL --> C3["JDBC connection 3"]
    C1 --> DB["Cloud SQL"]
    C2 --> DB
    C3 --> DB
~~~

When a request calls a repository/JdbcTemplate, Spring borrows a connection from the pool. After the transaction finishes and the connection is closed at the JDBC layer, HikariCP takes the connection back for reuse; calling `close()` on a pooled connection typically returns it to the pool rather than immediately closing the physical socket.

### 2.2. Cloud SQL Connector Is Not a Pool

Cloud SQL Java Connector handles authentication and the protected connection path to the instance. It does not itself limit the number of JDBC sessions created by the application. HikariCP is responsible for that.

| Component | Responsibility |
| --- | --- |
| Cloud SQL Java Connector / Socket Factory | Authenticates the instance, establishes TLS, and creates connections |
| PostgreSQL/MySQL JDBC driver | Executes database protocol, statements, and transactions |
| HikariCP | Limits, allocates, reuses, and reclaims JDBC connections |
| Spring transaction manager | Manages transaction boundaries |
| Cloud SQL | Enforces resource and database connection limits per configuration/engine |

If you create multiple `DataSource` instances or multiple pools in the same process, each pool has its own budget. Avoid accidentally creating a new pool per service or per request.

## 3. Calculating the System-Wide Connection Budget

### 3.1. Pool Size Must Be Multiplied by Replica Count

Suppose the configuration is:

- 5 Spring Boot replicas.
- Each replica has `maximum-pool-size = 8`.
- 2 background workers have their own pools, each up to 3 connections.
- 1 migration job can open 2 connections.
- 3 connections reserved for administration/monitoring.

Estimated maximum total connections:

~~~text
API replicas       = 5 × 8 = 40
Background workers = 2 × 3 =  6
Migration job      =          2
Admin/monitoring   =          3
--------------------------------
Expected total     =         51 connections
~~~

Cloud SQL sees the total connections from all workloads, not just a single HikariCP instance. A pool of 8 connections may look small, but 20 replicas can open up to 160 connections for the API alone.

### 3.2. Connection Budget Formula

You can budget using the formula:

\[
C_{total} =
N_{api}P_{api}
+ N_{worker}P_{worker}
+ C_{jobs}
+ C_{admin}
\]

Where:

- `N_api`: maximum number of API replicas that can run concurrently.
- `P_api`: maximum pool size of each API replica.
- `N_worker`: maximum number of worker replicas.
- `P_worker`: pool size of each worker.
- `C_jobs`: maximum connections from migration, batch, and scheduled jobs.
- `C_admin`: headroom for operations, monitoring, and emergency connections.

Keep `C_total` lower than the instance's actual connection limit with headroom. The difference is headroom to absorb bursts, failovers, rolling deployments, or administrative actions. There is no single headroom percentage suitable for every instance; choose based on load, database limits, and operational requirements.

### 3.3. Autoscaling Can Push Pools Past Limits

Cloud Run or GKE can scale up replicas when requests increase. If the pool size per replica is fixed, total connections grow with the replica count.

Cloud Run example:

~~~text
max instances = 20
maximum-pool-size per instance = 10

Potential API connections = 20 × 10 = 200
~~~

If Cloud SQL only has a budget of 100 connections left for the API, this configuration can cause the database to reject connections when autoscaling peaks.

Coordinated solutions:

1. Choose an appropriate `max instances` or replica ceiling.
2. Cap the pool per replica according to the connection budget.
3. Set application concurrency sensibly; you do not need one connection for every queued request if requests do not access the DB simultaneously.
4. Use queues for batch/background workloads that can be throttled.
5. Monitor actual connection count and pool wait times.
6. Reserve connections for migrations and administration instead of spending the entire budget on the API.

### 3.4. Pool Size Does Not Equal HTTP Concurrency

A request may perform plenty of work that does not use the database: calling HTTP services, reading caches, or processing data in memory. Therefore, you do not necessarily configure the pool to match HTTP concurrency.

Conversely, if a request holds a transaction open while calling an external service, the connection can be held for a long time and exhaust the pool. Keep transactions short and avoid slow network calls inside transactions unless necessary.

## 4. Configuring HikariCP in Spring Boot

### 4.1. Starting Configuration

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-cloud-sql-pool
      maximum-pool-size: 6
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      leak-detection-threshold: 0
~~~

These values are an initial example. Tune them according to your Cloud SQL instance, replica count, query duration, and connection limits. `leak-detection-threshold: 0` disables leak warnings; enable it only temporarily while investigating, with a threshold matching normal processing time.

### 4.2. Meaning of Key Parameters

| Parameter | Effect | Considerations |
| --- | --- | --- |
| `maximum-pool-size` | Maximum connections in one pool | Calculate based on total replicas and DB budget |
| `minimum-idle` | Idle connections the pool tries to maintain | Set low for elastic/scale-to-zero workloads |
| `connection-timeout` | Time to wait when borrowing a connection | Long enough for brief waits, without hiding pool saturation |
| `validation-timeout` | Time limit to validate a connection | Smaller than connection timeout |
| `idle-timeout` | Time before retiring idle connections when pool can shrink | Only meaningful when min idle is lower than max |
| `max-lifetime` | Maximum age of a connection before replacement | Coordinate with database/network timeouts |
| `leak-detection-threshold` | Logs connections held longer than threshold | Diagnostic tool; does not fix leaks automatically |

HikariCP typically defaults `maximumPoolSize` to 10 if unconfigured. Do not rely on this default for production capacity planning.

### 4.3. Choosing Minimum Idle for Elastic Workloads

If `minimum-idle` equals `maximum-pool-size`, the pool tends to hold a nearly fixed number of connections. That suits some steady workloads but can keep many idle connections open during low traffic.

For Cloud Run or workers that can scale to 0, setting `minimum-idle` low (even 0 if appropriate) helps reduce idle connections. In return, when new requests arrive, the pool must create connections and the first requests may be slower. Measure cold-start and latency before deciding.

### 4.4. maxLifetime and Cloud SQL Connector

HikariCP can retire old connections after `max-lifetime` to avoid keeping sessions open too long. Choose a value lower than any timeout enforced by the database/network if applicable. Do not set it so low that the pool constantly closes/reopens connections and increases handshake overhead.

Cloud SQL Java Connector manages connector credentials/TLS via its own mechanism. Refreshing connector metadata/certificates does not mean every open JDBC session must be closed immediately. The pool still needs a session lifecycle policy and must handle connections dropped due to maintenance/failover.

### 4.5. Monitoring Pool Saturation

Hikari metrics to observe:

- Active connections: number of connections currently borrowed.
- Idle connections: number of connections ready for use.
- Pending threads: number of threads waiting for a connection.
- Total connections: total connections held by the pool.
- Connection acquire time: time spent waiting to borrow a connection.

Signs of pool saturation:

- Active consistently equals maximum pool size.
- Pending threads increase.
- Connection wait time increases.
- Request latency rises even though query latency is unchanged.

If queries are slow or transactions hold connections too long, increasing the pool may merely shift pressure from HikariCP to Cloud SQL. Check slow queries, locks, transaction durations, and external service call times before increasing the pool.

## 5. Transactions and Connection Lifecycle

### 5.1. Keep Transactions Short

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(String orderId) {
        jdbc.update(
                "update orders set status = ? where id = ?",
                "PAID", orderId);
        jdbc.update(
                "insert into order_audit(order_id, action) values (?, ?)",
                orderId, "PAYMENT_CONFIRMED");
    }
}
~~~

In this example, both SQL statements run inside one transaction. After commit/rollback, the connection is returned to the pool.

Avoid this pattern:

~~~java
@Transactional
public void processOrder(String orderId) {
    jdbc.update("update orders set status = 'PROCESSING' where id = ?", orderId);
    callSlowExternalApi(); // Holds transaction/connection while waiting on the network.
    jdbc.update("update orders set status = 'DONE' where id = ?", orderId);
}
~~~

If the external API takes 20 seconds, the transaction and connection can be held for 20 seconds. Split into steps with explicit states, commit before calling the external service when business logic permits, and update the result in another transaction.

### 5.2. Close Connections Properly

When using raw JDBC, always close `Connection`, `Statement`, and `ResultSet` with try-with-resources. When using JdbcTemplate/JPA, Spring manages borrowing/returning connections along transaction boundaries; do not manually close injected connections or connections managed by the transaction manager.

### 5.3. Leaks and Starvation

A connection leak occurs when code borrows a connection and fails to return it. The pool gradually drains and other requests wait until `connection-timeout`.

When encountering this error:

1. Inspect thread dumps and stack traces from leak detection if enabled.
2. Find code paths that fail to close resources or have long-running transactions.
3. Check whether exception paths skip cleanup.
4. Measure transaction duration and external calls.
5. Fix the lifecycle before increasing the pool.

## 6. Cloud SQL Connection Limits and Additional Pooling Models

### 6.1. Connection Limits Depend on Engine and Instance Configuration

Cloud SQL does not have a single maximum connection number across all instances. Limits depend on database engine, memory/tier, flags, and instance configuration. PostgreSQL and MySQL also manage sessions differently.

Do not use a fixed number from an example to conclude how many connections your instance can sustain. Check the configuration/metrics of the running instance and leave capacity for operational tasks.

### 6.2. When Is a Proxy or Pooler Needed?

HikariCP manages pools per application process. If there are many short-lived replicas, each replica opening even a small pool can still create many database sessions.

You may consider an additional pooling/proxy layer if supported by the engine, version, and architecture—for example, a PostgreSQL pooler or an appropriate proxy service. Before deploying, evaluate:

- Session pooling vs. transaction pooling mode.
- Compatibility with prepared statements, session variables, temporary tables, and advisory locks.
- Transaction behavior and connection pinning.
- How IAM/password authentication works through the proxy.
- Limits and observability of the pooler.
- Added latency and additional failure points.

Transaction pooling can change assumptions about session affinity. Applications relying on session state must be tested before enabling it. Do not add a proxy just because connection counts look high; first calculate the budget and optimize application-side pools.

## 7. Private IP: Network Architecture and Path

### 7.1. Private IP Is an Address, Not an Access Permission

Cloud SQL Private IP places the instance in a private address range reachable from connected networks. Java Connector can be configured to choose private IP, but **the connector does not automatically create VPC routes** and does not replace firewall/network configuration.

~~~mermaid
flowchart LR
    subgraph VPC["Google Cloud VPC"]
      APP["Cloud Run / GKE / Compute workload"]
      SQL["Cloud SQL Private IP"]
      APP -->|"Private network route"| SQL
    end
    IAM["ADC + IAM permissions"] --> APP
    APP --> CONN["Cloud SQL Java Connector"]
    CONN --> SQL
~~~

To connect, the workload must simultaneously have:

1. An instance with Private IP or a configured private connectivity endpoint.
2. A network path from the workload to that VPC/endpoint.
3. Firewall/egress policies allowing the required connection flow.
4. Java Connector selecting the appropriate IP type.
5. An ADC principal with permission to connect to Cloud SQL.

### 7.2. Private Service Access and Private Service Connect

These two models should not have their names used interchangeably:

- **Private Service Access (PSA):** connects private services via VPC peering with an IP range allocated for the service producer; this is the common model when provisioning Private IP for Cloud SQL.
- **Private Service Connect (PSC):** provides a private endpoint for consumers to access a service through a configured endpoint; deployment, DNS, and connectivity differ from PSA.

Choose the model according to the Cloud SQL instance architecture and your organization's networking guidelines. Do not assume enabling PSC automatically creates Private Service Access or vice versa.

### 7.3. Cloud Run

Cloud Run requires appropriate network connectivity configured before using Cloud SQL Private IP. Possible models include:

- **Direct VPC egress** when supported by the deployment configuration and region.
- **Serverless VPC Access connector** in architectures using a serverless network connector.

Once the network path exists, configure Cloud SQL Java Connector to select `PRIVATE`. Simply editing the JDBC URL without configuring egress/VPC will still result in request timeouts.

Account for egress firewalls and connection limits when Cloud Run scales out. Align `max instances`, request concurrency, and Hikari pool within a single connection budget.

### 7.4. GKE and Compute Engine

For GKE, verify cluster/node/pod networking and VPC routes to Cloud SQL. Workload Identity Federation for GKE provides workload identity; it does not automatically create network routes.

For Compute Engine, the VM must be in a VPC with a route to the instance and have an appropriate service account attached. Firewall/egress policies must allow the required traffic.

### 7.5. Selecting IP Type in JDBC Socket Factory

For PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
~~~

`ipTypes=PRIVATE` instructs the connector to choose the private address. `DB_NAME` and `INSTANCE_CONNECTION_NAME` are placeholders resolved by Spring from environment variables/properties. If the instance lacks a Private IP or the workload cannot route to that address, the connection will fail. When Public IP is required, choose the appropriate IP type per connector documentation and network policy.

Do not use `PUBLIC,PRIVATE` as a way to mask a broken private route if security requirements dictate private-network-only traffic. Explicitly choose the connection path the workload is authorized to use.

## 8. IAM Database Authentication When Engine Supported

### 8.1. Three Independent Permissions/Identities

IAM database authentication can be confusing because both Google Cloud IAM and database authorization participate:

| Component | Role |
| --- | --- |
| Workload IAM principal | Service account or principal running the application |
| `roles/cloudsql.client` | Permission to connect to the instance via connector/proxy |
| `roles/cloudsql.instanceUser` | Permission for IAM login to the database when using IAM DB auth |
| IAM database user | User created/mapped in Cloud SQL |
| SQL roles/grants | Permissions to access databases, schemas, tables, sequences, and statements |

A service account with `roles/cloudsql.client` can establish a connection to the instance but cannot necessarily log in via IAM DB authentication. When using IAM DB auth, the workload needs the corresponding login permission and a valid IAM database user.

After login, SELECT/INSERT/UPDATE/DELETE privileges are still determined by database roles/grants. An IAM role does not automatically grant table permissions.

### 8.2. Engine and Version Must Support It

IAM database authentication is not uniformly supported across every database engine, edition, and version. The hands-on examples in this lesson focus on PostgreSQL and MySQL with their corresponding connectors. Before enabling on a real instance, verify:

- Whether the Cloud SQL engine and version support IAM DB auth.
- Whether the instance has the required IAM database authentication flag/option enabled.
- Whether the appropriate IAM database user type (user or service account) has been created.
- Whether the Cloud SQL Java Connector/Socket Factory and JDBC driver in use support `enableIamAuth`.
- Whether the workload principal has `cloudsql.instances.login` through an appropriate IAM role.

Do not apply PostgreSQL syntax or assumptions to MySQL/SQL Server. In particular, do not assume SQL Server shares the same IAM DB authentication mechanism just because it is also Cloud SQL.

### 8.3. Password-Based vs. IAM DB Authentication

| Criterion | Password-based DB auth | IAM database authentication |
| --- | --- | --- |
| Instance connection identity | ADC/IAM via connector | ADC/IAM via connector |
| Database login | Database username + password | IAM principal/user and IAM token |
| Secret management | Must protect and rotate passwords | Reduces static passwords for login |
| IAM permissions | Cloud SQL Client | Cloud SQL Client + IAM login permission |
| SQL permissions | Database grants | Database grants |
| Best fit | Existing apps, supported engine/config | Workloads with IAM identity and supported engine |

IAM DB auth does not mean the application no longer needs secrets anywhere; other secrets such as API keys, encryption keys, and credentials for dependent services still must be managed.

### 8.4. Creating a Database IAM User

Creating an IAM database user is a Cloud SQL administrative operation, separate from creating a service account. User names are normalized according to the engine and principal type. For service accounts, the database username format may differ from the full display email; follow Cloud SQL's exact rules for the engine and inspect the user after creation.

Then grant the required SQL privileges using database statements. For example, in PostgreSQL, after the IAM user exists and can log in:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_app_iam;
GRANT USAGE ON SCHEMA public TO orders_app_iam;
GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA public TO orders_app_iam;
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public TO orders_app_iam;
~~~

The role name `orders_app_iam` is only an illustrative example; replace it with the actual database user name created by Cloud SQL. If new tables/sequences are created later, default privileges or corresponding migration grants are needed.

## 9. Configuring IAM DB Authentication in Spring Boot

### 9.1. PostgreSQL Socket Factory

With Cloud SQL PostgreSQL Socket Factory, example JDBC URL when enabling IAM DB auth:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
~~~

`enableIamAuth=true` instructs the connector to use IAM database authentication according to engine/connector capabilities. The username must be the IAM database user name created in Cloud SQL per PostgreSQL rules; do not guess or truncate the email without checking the user's format.

In this model, do not put a static database password in the datasource as in password-based auth. The connector retrieves a token via ADC to authenticate the database connection. When Hikari needs to open a new connection, the connector handles fetching credentials according to the library's mechanism.

### 9.2. MySQL Socket Factory

MySQL uses a different driver and Socket Factory from PostgreSQL. The configuration can use `enableIamAuth=true` if the Cloud SQL MySQL version and connector in use support it:

~~~properties
spring.datasource.url=jdbc:mysql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.mysql.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
~~~

Verify the IAM database user name by principal type and engine. Do not copy PostgreSQL's user naming rules over to MySQL.

### 9.3. Password-Based Still Requires Secret Manager

If not yet using IAM DB auth, the database password should be retrieved from a secret manager or deployment environment secret injection:

~~~yaml
spring:
  datasource:
    username: ${DB_USER}
    password: ${DB_PASS}
~~~

Do not commit real passwords into `application.yml`, Docker images, logs, or shared `.env` files. Separate runtime users from migration users; secret rotation must be coordinated with new connection creation in the pool.

### 9.4. IAM Tokens and the Connection Pool

IAM database authentication uses a token during database connection authentication. HikariCP keeps already-opened database sessions; it does not fetch a new token for every SQL statement. When the pool creates a new connection, the connector must obtain valid credentials via its automatic mechanism.

This leads to several operational points:

- Workload ADC must remain available when creating new connections.
- The IAM role/user must exist throughout the workload's lifecycle.
- If IAM permissions are revoked, already-open database connections may not be severed immediately; do not treat IAM revocation as an instant session-kill mechanism.
- When rotating or changing principals, plan a controlled connection/pool replacement.
- Do not manually cache IAM tokens in environment variables or long-lived configuration.

## 10. Combining HikariCP, Private IP, and IAM DB Auth

A conceptual configuration for PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
    username: ${IAM_DB_USER}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: orders-private-cloud-sql
      maximum-pool-size: 6
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

This configuration only works if all of the following conditions hold:

1. The PostgreSQL instance supports and has IAM database authentication enabled.
2. The instance has a Private IP.
3. The workload has a VPC route to the private address.
4. ADC points to the right service account/principal.
5. The principal has Cloud SQL Client and the required IAM DB login permission.
6. The IAM database user has been created in the correct format.
7. The database user has SQL grants for the business operations.
8. Socket Factory dependency, JDBC driver, and properties are compatible.
9. Pool size fits within the instance's connection budget.

When diagnosing, check each condition layer by layer. If the TCP/private route does not work, editing the IAM DB user will not help. If the connector authenticates but the database rejects login, increasing Hikari maximum pool size will not fix it either.

## 11. Rotation, Failover, and Pool Recovery

### 11.1. Old Connections Can Be Dropped

Cloud SQL maintenance, failover, network disruption, or database restarts can close active sessions. HikariCP must evict broken connections and create new ones.

The application needs to:

- Set reasonable connection timeouts.
- Classify transient connection exceptions.
- Allow the pool to recreate connections once the database is ready.
- Retry transactions at the business boundary with idempotency.
- Avoid blindly retrying every SQL statement.

### 11.2. Do Not Confuse Connection Retry with Transaction Retry

If a connection drops before a statement runs, retrying after the pool creates a new connection is safe. If it drops during commit, the client may not know whether the transaction committed.

For critical write operations:

1. Use an idempotency key or unique constraint.
2. Persist business state within the transaction.
3. After an ambiguous error, query the state by idempotency key.
4. Re-execute only when confirming the operation has not completed.
5. Record retry counts and causes.

### 11.3. Changing IAM or Secrets

When changing a service account, IAM role, or database password:

- Update workload identity/secrets in the deployment environment.
- Ensure new connections can be established with the new credentials.
- Monitor connection failures during rollout.
- Perform a rolling restart or controlled pool refresh if needed.
- Revoke old credentials after verifying the new workload operates properly.

Do not revoke old passwords/roles before knowing which replicas still hold old connections/credentials.

## 12. Monitoring Cloud SQL and HikariCP

### 12.1. Application-Layer Metrics

| Metric | Meaning | Signs needing investigation |
| --- | --- | --- |
| Hikari active | Connections currently borrowed | Constantly equals maximum pool size |
| Hikari idle | Ready connections | Constantly 0 while requests wait |
| Hikari pending | Threads waiting for a connection | Sustained increase |
| Hikari acquire time | Time to obtain a connection | P95/P99 rising |
| Transaction duration | Time a transaction stays open | Unusually long |
| SQL latency | Query execution time | Rises alongside locks/CPU |
| Connection creation failures | Errors opening new sessions | IAM, network, DB limits, or failover |

### 12.2. Cloud SQL Metrics

Monitor:

- Database connection count and engine limits.
- CPU, memory, storage utilization/latency.
- Query latency, slow queries, and locks.
- Restart/failover/maintenance events.
- Network throughput and connection errors.
- Authentication/permission errors.

Correlate application metrics with Cloud SQL metrics over the same time window to distinguish pool exhaustion, query saturation, network failure, and database capacity.

### 12.3. Useful Alerts

- Hikari pending threads remain non-zero for an extended period.
- Active connections repeatedly hit maximum.
- Cloud SQL connection count approaches the limit.
- Connection creation error rate rises.
- Query latency or transaction duration spikes abnormally.
- Private IP connection timeouts increase after VPC/egress changes.
- IAM authentication failures appear after rollout/rotation.

Do not alert solely on total connections; also monitor queued request age and database utilization.

## 13. Integration and Load Testing

### 13.1. Layer-by-Layer Testing

| Test | What to verify | How to isolate failures |
| --- | --- | --- |
| ADC/IAM | Actual principal and Cloud SQL permissions | Check role bindings without changing the pool |
| Private networking | Workload route to private IP | Test from the real runtime/VPC, not only a local machine |
| Database authentication | Password or IAM DB auth | Test user login independently |
| SQL authorization | Grants/schemas/tables | Run queries with the exact DB user |
| Hikari pool | Pool size, acquire time, leaks | Concurrent load and observe metrics |
| Failover/restart | Pool evicts broken connections and recreates | Test in sandbox with idempotency |
| Autoscaling | Total connections at max replicas | Scale replicas in a controlled way and measure DB sessions |

### 13.2. Integration Test Scenario

1. Create a Cloud SQL PostgreSQL sandbox and a dedicated database.
2. Enable Private IP and configure a VPC path for the test workload.
3. Grant Cloud SQL Client to the service account.
4. Create a password-based database user; verify private connectivity.
5. If supported by engine/instance, enable IAM DB authentication, create an IAM user, and grant login permission.
6. Configure Socket Factory with `ipTypes=PRIVATE` and `enableIamAuth=true`.
7. Run read, write, and transaction rollback/commit queries.
8. Generate concurrent load higher than pool size to observe pending threads and acquire timeouts.
9. Scale test replicas up to the defined limit, confirming total connections do not exceed the budget.
10. Stop/restart the database in the sandbox per permitted procedures; verify pool recovery.
11. Revoke the IAM login role in the test environment and observe the effect on new connections versus open sessions.
12. Verify logs contain no passwords, tokens, JSON keys, or connection strings with secrets.

### 13.3. Verifying Total Connections by Calculation

Suppose:

- Cloud Run max instances: 12.
- API pool: 5 connections per instance.
- Workers up to 3 replicas, 2 connections each.
- Migration job up to 2 connections.
- Admin/monitoring needs 5 connections.

~~~text
API       = 12 × 5 = 60
Workers   =  3 × 2 =  6
Migration =             2
Admin     =             5
--------------------------
Total     =            73
~~~

Compare 73 against Cloud SQL's actual connection capacity and required headroom. If the budget is 60, you must reduce pools, lower the replica ceiling, or split workloads; do not wait until production hits `too many connections`.

## 14. Common Errors and How to Handle Them

| Symptom | Likely failing layer | Where to check |
| --- | --- | --- |
| `Connection timed out` with Private IP | Network | VPC route, Cloud Run egress, firewall, IP type |
| `PERMISSION_DENIED` when connector initializes | Cloud IAM | ADC principal, Cloud SQL Client role, API |
| IAM login rejected | IAM DB auth | Instance flag, `cloudsql.instances.login`, IAM DB user, engine support |
| Password authentication failed | Database authentication | DB username/password, secret version, DB user status |
| `too many connections` | Connection budget | Total replicas × pool, workers, jobs, admin |
| Hikari `Connection is not available` | Pool saturation or DB unreachable | Pending, active, acquire time, query latency, connector errors |
| Stale broken connections after failover | Pool lifecycle | Pool eviction, connection validation, and retry |
| SQL permission denied | Database authorization | Schema/table grants, sequence privileges |
| Spike in connection creation during scale out | Autoscaling | Replica ceiling, min idle, pool max, and cold-start |
| Works locally but fails Private IP on Cloud Run | Different network identity | VPC egress and runtime service account |

Do not fix errors by disabling TLS, granting Owner, switching a private workload to public unintentionally, or increasing the pool indefinitely. Identify the failing layer before changing configuration.

## 15. Comparison with AWS and Azure

Other platforms also have connection pools and private networking, but identity provisioning and managed database connectivity differ:

| Aspect | Google Cloud SQL | AWS RDS/Aurora | Azure Database |
| --- | --- | --- | --- |
| Java pool | HikariCP | HikariCP | HikariCP |
| Managed connectivity | Cloud SQL Java Connector/Auth Proxy | TLS/CA, RDS Proxy depending on architecture | TLS, corresponding proxy/service |
| Workload identity | ADC/service account | IAM role | Managed identity/service principal |
| Private networking | VPC, Private IP, PSA/PSC | VPC/subnet/security group | VNet/private endpoint |
| DB IAM auth | Only on supported engines/versions | Depends on engine and IAM DB auth support | Depends on engine/service and Entra support |
| Multi-replica pooling | Sum of Hikari pools across workload | Sum of pools, optionally combined with RDS Proxy | Sum of pools, optionally combined with appropriate pooling solution |

Spring Data/JdbcTemplate, transaction abstractions, and most repository logic can be shared when the SQL engine is compatible. Identity, network, proxy, secret, and database IAM authentication configurations must be provider-specific.

## 16. Practical Exercises

### Exercise A — Calculate the Connection Budget

A service has 10 API replicas, each with max pool size 6; 4 worker replicas, each with pool size 2; a migration job needs 2 connections and admin needs 4 connections. Calculate the maximum total connections. Then reduce the API pool to 4 and compare headroom.

### Exercise B — Autoscaling Test

Deploy Spring Boot to Cloud Run with controlled max instances. Increase load in a sandbox, observe Hikari active/pending and Cloud SQL connection count. Identify the point where pools/replicas bring the database near its limit.

### Exercise C — Private IP

Configure Cloud SQL Private IP, VPC egress for the workload, and `ipTypes=PRIVATE`. Run the application from the actual runtime. Then intentionally remove the VPC route in a test environment to distinguish network timeouts from IAM errors.

### Exercise D — IAM Database Authentication

On a supported engine/version, enable IAM DB auth, create an IAM database user, and grant Cloud SQL Client and Instance User to the appropriate principal. Connect with `enableIamAuth=true`, run queries, and verify SQL grants. Revoke login permission in the sandbox and observe new connections.

### Exercise E — Pool Recovery

In a test environment, restart/fail over Cloud SQL following allowed procedures. Observe broken connections being evicted, new connections being created, and business retries. Use an idempotency key to prove no duplicate records are created.

### Exercise F — Investigating a Pool Leak

Create a test code branch that intentionally holds a connection longer than normal. Temporarily enable leak detection, read the stack trace, fix the lifecycle, and compare pending threads before/after.

### Self-Check Questions

1. Why doesn't `maximum-pool-size = 8` mean the entire application only uses 8 connections?
2. How do you calculate total connections from API replicas, workers, and migration jobs?
3. Why can Cloud Run autoscaling exhaust Cloud SQL connections even when each pool is small?
4. How does `minimum-idle` affect scale-to-zero workloads?
5. How does `connection-timeout` differ from `max-lifetime`?
6. Why can increasing pool size overload the database even more?
7. Does Cloud SQL Java Connector manage HikariCP automatically?
8. Does `ipTypes=PRIVATE` automatically create a VPC route?
9. How do Private Service Access and Private Service Connect differ?
10. Why does a workload need both a network path and a Cloud SQL IAM role?
11. Does `roles/cloudsql.client` grant table SELECT privileges?
12. At which step does IAM database authentication differ from password-based DB auth?
13. Why should you verify the engine/version before enabling IAM DB authentication?
14. What happens to already-open database sessions when an IAM role is revoked?
15. Why does retrying a transaction after a commit error require idempotency?
16. When should you consider a proxy/pooler outside HikariCP?
17. Which metrics help distinguish Hikari pool exhaustion from Cloud SQL query saturation?

**Expected outcome:** learners can design a connection budget for the entire Spring Boot workload, tune HikariCP around autoscaling and Cloud SQL limits, configure private network paths properly, use IAM database authentication when supported by the engine, and test and monitor pool recovery capabilities.
