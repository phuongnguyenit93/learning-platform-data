# JDBC Connectivity, Connection Pools, and Retries in Java Applications

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data. The goal is to know how to deploy, monitor, secure, and control costs for application architectures on Azure. In the **Relational Databases** chapter, this lesson goes deep into three foundational components when Java connects to **Azure SQL Database**, **Azure Database for PostgreSQL**, or **Azure Database for MySQL**: **JDBC**, **connection pooling**, and controlled **retries**.

Imagine a Java Spring Boot system deployed as 8 replicas on AKS. Each request needs to look up an order and then update its status. When an Azure database performs a failover, existing connections may become invalid; at the same time, each replica has a connection pool and will attempt to reconnect. If the application creates a connection per request, retries indefinitely, or configures an oversized pool, the initial incident can turn into a connection storm, connection limit exhaustion, prolonged timeouts, and even duplicate data writes.

After this lesson, you will be able to:

- Explain the **JDBC driver**, `DataSource`, `Connection`, `PreparedStatement`, transactions, and `SQLException`.
- Construct appropriate JDBC URLs for Azure SQL, Azure PostgreSQL, and Azure MySQL; enforce TLS, DNS, and network checks.
- Use **HikariCP** or a Spring Boot connection pool and distinguish between **pool timeout**, **query timeout**, and **socket timeout**.
- Estimate total connections when scaling across multiple replicas, avoiding pool exhaustion/leaks and database overload.
- Distinguish authentication with **Microsoft Entra ID/managed identity** from SQL username/password; design proper token refresh for the pool.
- Identify transient connection errors, serialization/deadlock errors, throttling, and errors that should not be retried.
- Retry at the **right transaction scope**, with exponential backoff + jitter, time bounds, idempotency, and handling of uncertain commit outcomes.
- Monitor pool metrics, DB metrics, tracing, and alerts, and design failover/chaos tests.

## 1. Why Is Database Connectivity an Operational Problem?

An application using an Azure managed relational database still involves network and runtime components:

```text
Mobile/Web client
       |
       v
API Gateway / Ingress
       |
       v
Java API (8 replicas)
       |
       +-- Replica 1: HikariCP [0..10 connections]
       +-- Replica 2: HikariCP [0..10 connections]
       +-- ...
       +-- Replica 8: HikariCP [0..10 connections]
       |
       v
VNet / Private DNS / TLS / Azure Firewall per design
       |
       v
Azure SQL Database or Azure Database for PostgreSQL/MySQL
       |
       +-- Max connections / compute / IOPS / locks
       +-- Failover / maintenance / scaling events
```

Each connection has **overhead on both the Java process and the database server**: sockets, session state, memory, and potential resource contention. A connection pool helps reuse active connections, but it does not give the backend infinite capacity.

### 1.1. Three Types of Failures to Distinguish

| Failure | Example | Handling approach |
|---|---|---|
| **Unable to establish connection** | Wrong password, DNS failure, firewall/private endpoint, connection limit | Identify auth/network/capacity; retry **only when transient** |
| **Connected, but query fails** | Deadlock, lock timeout, invalid SQL, unique constraint | Classify SQLState/vendor code; can retry **the entire transaction** when safe |
| **Commit outcome unknown (succeeded or failed)** | DB committed, but TCP was severed before client received ACK | Do not blind retry; use idempotency key/state reconciliation |

**Retries cannot fix a wrong password, invalid query syntax, or insufficient database permissions.** Such configuration errors must be detected clearly and reported rather than continuously opening new connections.

### 1.2. “Managed” Does Not Mean Connections Cannot Drop

Azure manages many operations such as OS updates, infrastructure patching, backups, and certain HA/failover mechanisms depending on the service/tier. However, a network connection is a stateful resource and can be reset during failover, maintenance, autoscale, or network incidents.

The application must be designed to **recover**: discard broken connections, create new connections, retry safe operations, and signal failure quickly when it can no longer serve requests.

## 2. JDBC and the Lifecycle of an SQL Operation

**Java Database Connectivity (JDBC)** is the standard Java API for accessing a database through a matching JDBC driver. An application can use JDBC directly, Spring JDBC, JPA/Hibernate, or another ORM framework; underneath, they still typically rely on drivers, connections, and transactions.

```text
Service method
      |
      v
DataSource (typically a pool)
      |
      v
JDBC Connection
      |
      +-- PreparedStatement / ResultSet
      |
      +-- Transaction: auto-commit or begin/commit/rollback
      |
      v
JDBC driver <---- TLS socket ----> Azure relational database
```

### 2.1. Key Interfaces

| Component | Role | Notes |
|---|---|---|
| `Driver` | Implements the wire protocol for SQL Server/PostgreSQL/MySQL | Each database type uses the appropriate driver |
| `DataSource` | Provides `Connection`, often implemented by a pool | Applications should inject/reuse a single DataSource |
| `Connection` | Session/transaction and connection state | **Do not** share a single Connection across multiple threads |
| `PreparedStatement` | Executes parameterized SQL | Protects against SQL injection when placeholders are used properly |
| `ResultSet` | Query result data | Close resources according to their lifecycle |
| `SQLException` | SQLState, vendor error code, cause information | Not every SQLException is transient |
| `commit` / `rollback` | Ends the transaction | Understand the unit-of-work scope and commit failures |

**`Connection.close()` on a connection pool usually returns the connection to the pool**, rather than destroying the TCP socket immediately. If code forgets to close, the pool is exhausted even while the database is idle.

### 2.2. JDBC Example Using PreparedStatement

The following example **only reads** a record and contains no hardcoded credentials; `DataSource` is configured separately:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class OrderReader {
    private final DataSource dataSource;

    public OrderReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findStatus(String orderId) throws SQLException {
        String sql = "SELECT status FROM orders WHERE order_id = ?";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, orderId);
            ps.setQueryTimeout(5); // example: seconds, subject to driver support
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next()
                        ? Optional.ofNullable(rs.getString("status"))
                        : Optional.empty();
            }
        }
    }
}
```

`try-with-resources` closes `ResultSet`/`PreparedStatement` and returns `Connection` to the pool even when an exception occurs. Only close resources **that you own**: if a framework `@Transactional` manages the Connection, avoid interfering with transaction/close boundaries improperly outside the framework's scope.

### 2.3. PreparedStatement Does Not Solve Everything on Its Own

Parameterized SQL prevents input data from being interpreted as SQL syntax in bindable positions. However, parts such as **table names/column names/sort direction** generally cannot be bound with `?`; if they must be chosen dynamically, use a safe allowlist. Input data like `orderId` still needs length/type validation and object-level authorization.

## 3. Choosing the JDBC Driver and URL by Azure Service

**There is no single shared JDBC driver** for SQL Server, PostgreSQL, and MySQL. Each driver uses its own protocol, connection URL syntax, auth mechanisms, and SQLState/vendor codes.

| Azure database | Common JDBC driver | URL prefix |
|---|---|---|
| **Azure SQL Database** (SQL Server engine) | Microsoft JDBC Driver for SQL Server, `com.microsoft.sqlserver:mssql-jdbc` | `jdbc:sqlserver://` |
| **Azure Database for PostgreSQL – Flexible Server** | PostgreSQL JDBC Driver, `org.postgresql:postgresql` | `jdbc:postgresql://` |
| **Azure Database for MySQL – Flexible Server** | MySQL Connector/J, `com.mysql:mysql-connector-j` | `jdbc:mysql://` |

Driver versions should be **pinned to a stable release tested against the project's JDK/engine**. Do not use an unsupported JDBC driver for the running Java version, and do not download random JARs from untrusted sources.

### 3.1. JDBC URL for Azure SQL

**Illustrative** example:

```text
jdbc:sqlserver://orders-sql.database.windows.net:1433;databaseName=ordersdb;encrypt=true;trustServerCertificate=false;loginTimeout=30;
```

Explanation:

- `orders-sql.database.windows.net` is an illustrative Azure SQL server hostname.
- `1433` is the standard port for SQL Server/TDS.
- `databaseName=ordersdb` selects the database.
- `encrypt=true` enables encryption.
- `trustServerCertificate=false` requires verifying the server certificate rather than skipping verification.
- `loginTimeout=30` affects driver login duration; **it does not replace** the deadline of the overall HTTP request.

In production, verify certificate hostname validation and the JDK/container trust store. Do not set `trustServerCertificate=true` to "fix" trust chain errors; fix the CA trust, hostname, route, or TLS configuration instead.

### 3.2. JDBC URL for Azure PostgreSQL Flexible Server

```text
jdbc:postgresql://orders-pg.postgres.database.azure.com:5432/ordersdb?sslmode=verify-full
```

`verify-full` requires TLS and hostname verification per the PostgreSQL JDBC driver mechanism. The container/JVM must trust the server's CA chain. If the driver reports a certificate error, check the CA/trust store and ensure DNS resolves to the right hostname; **do not switch to `sslmode=disable`** in production.

Port `5432` is the PostgreSQL default; this does not imply the server must be public. With private access/private DNS, the hostname must resolve to the private IP according to the deployed Azure topology.

### 3.3. JDBC URL for Azure MySQL Flexible Server

```text
jdbc:mysql://orders-mysql.mysql.database.azure.com:3306/ordersdb?sslMode=VERIFY_IDENTITY
```

`sslMode=VERIFY_IDENTITY` requires TLS and hostname identity verification in supported MySQL Connector/J versions. `3306` is the standard port. When changing drivers/JDKs, re-verify TLS parameter names and the trust store rather than copying options from PostgreSQL to MySQL.

### 3.4. Configuring URLs and Identity Separately

A JDBC URL can be stored in non-secret configuration, but **username/password, access tokens, or private keys must not be committed to Git**. Separate them:

```text
DB_JDBC_URL   -> URL to the database, including TLS options
DB_USERNAME   -> DB account according to the chosen model
DB_PASSWORD   -> secret from a secrets manager (when using password auth)
```

In Azure, you can use Microsoft Entra authentication/managed identity depending on service/driver support. When using identity-based auth, how tokens are acquired and refreshed for the JDBC pool requires dedicated design; this is covered in a later section.

## 4. Network, Private Endpoint, DNS, and TLS Before Debugging JDBC

A `Connection refused`, timeout, or TLS handshake error often originates from **networking/certificates**, not from a missing `SELECT` permission in SQL.

```text
AKS / Azure App Service / VM / Container Apps
                  |
                  | outbound route from runtime
                  v
               VNet
                  |
          DNS resolver / Private DNS
                  |
          Firewall / NSG / UDR / NAT
                  |
                  v
        Azure database endpoint
                  |
                  v
            TLS + DB login
```

To check systematically:

1. Does the runtime resolve the exact **FQDN**? Is the Private DNS link/resolver configured appropriately?
2. Is the required port (Azure SQL 1433, PostgreSQL 5432, MySQL 3306 per design) reachable?
3. Is Azure DB networking/firewall public or private? Is the source network allowed?
4. Is any proxy/route/NSG/firewall blocking the connection?
5. Does the TLS handshake trust the certificate and match the hostname?
6. Only after networking/TLS works should you diagnose **database authentication and authorization**.

**Do not enable public database access for the entire Internet, disable TLS, or use an admin account to "fix" an undiagnosed timeout.** A successful connection from a laptop does not prove a pod in AKS shares the same DNS/route/identity.

## 5. What Is a Connection Pool?

Opening a database connection each time incurs **DNS, TCP/TLS handshake, authentication, session creation**, and server resource costs. If every Java request creates a new connection and closes the physical connection immediately, the application can suffer high latency and connection churn. A **connection pool** manages a set of connections for reuse, limits concurrent connections, and provides mechanisms to validate and evict broken connections.

```text
Thread A ----\
Thread B -----+--> HikariCP DataSource
Thread C ----/         |
                       +-- Idle connection #1
                       +-- Busy connection #2
                       +-- Busy connection #3
                       +-- ... up to maximumPoolSize
                       |
                       +-- When all connections are busy:
                           requests wait up to connectionTimeout
```

When code calls `getConnection()`, the pool lends an available connection or creates a new one if below the limit. When code calls `close()`, the connection returns to the pool. If connections run out and the wait reaches the timeout, the pool throws an exception. This indicates a **pool acquisition failure**, not necessarily that the database is dead.

### 5.1. One Connection Is Not One Thread

Do not share the same `java.sql.Connection` across concurrent threads. A Connection holds transaction state and session properties; improper sharing easily causes cross-thread commits, race conditions, or data leaks. The pool ensures a connection is lent to one borrower at a time when the API is used correctly.

### 5.2. A Pool Does Not Replace Database Capacity

Increasing `maximumPoolSize` does not create database CPU or IOPS. Once a database is saturated, adding sessions can **increase query latency**, worsen lock contention, and reduce throughput.

Pool sizing should be based on:

- The number of concurrent queries **genuinely needed** per replica.
- Average/p95 connection hold time.
- Connection limits and compute tier of the Azure database.
- Maximum Java replicas, background jobs, and BI/admin/maintenance clients.
- Lock contention, SQL query plans, DB CPU, memory, and I/O.

Pool size **should not default to the number of HTTP threads**. HTTP requests often perform substantial work that does not require a database connection; connections should only be held for the duration of necessary SQL operations.

## 6. Configuring HikariCP in Java

**HikariCP** is a widely used JDBC connection pool and the default in Spring Boot across many standard JDBC/JPA configurations. The following example uses **Azure Database for PostgreSQL Flexible Server** for illustration; pool setup applies similarly to Azure SQL/MySQL after changing the driver, URL, and authentication parameters.

### 6.1. Maven Dependencies

```xml
<dependencies>
  <dependency>
    <groupId>com.zaxxer</groupId>
    <artifactId>HikariCP</artifactId>
    <version>REPLACE_WITH_TESTED_HIKARI_VERSION</version>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>REPLACE_WITH_TESTED_PGJDBC_VERSION</version>
  </dependency>
</dependencies>
```

The `REPLACE_WITH...` strings are **version placeholders** and must be replaced with versions tested against the project's JDK and database engine before building. With Spring Boot, use aligned BOM/dependency management instead of forcing conflicting versions manually.

### 6.2. Creating a Shared DataSource

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DatabasePools {
    private DatabasePools() {}

    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setPoolName("orders-write-pool");
        config.setJdbcUrl(require("DB_JDBC_URL"));
        config.setUsername(require("DB_USERNAME"));
        config.setPassword(require("DB_PASSWORD"));

        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3_000);       // ms: wait for pool borrow
        config.setValidationTimeout(1_000);       // ms: validate connection
        config.setIdleTimeout(300_000);           // ms: idle too long
        config.setMaxLifetime(1_500_000);         // ms: 25 minutes
        config.setKeepaliveTime(120_000);         // ms: 2 minutes
        config.setLeakDetectionThreshold(20_000); // ms: diagnostic, consider disabling

        return new HikariDataSource(config);
    }

    private static String require(String envName) {
        String value = System.getenv(envName);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + envName);
        }
        return value;
    }
}
```

**Note:** `setPassword` illustrates **password authentication** for a lab and does not imply it is always the preferred production approach. Retrieve passwords from a secret store or move to Entra/managed identity when supported by the service/driver; never write secrets to logs, images, Git, or public config maps. Token authentication integration with the pool is covered later.

For a `HikariDataSource` created once at application startup, the framework must **close the pool on shutdown**; never create and close a pool on every HTTP request. For a Java CLI/demo, use:

```java
try (HikariDataSource ds = DatabasePools.create()) {
    OrderReader reader = new OrderReader(ds);
    System.out.println(reader.findStatus("ORD-1042"));
}
```

Each request simply borrows and returns a `Connection` from `ds`. Pool initialization may open connections immediately or lazily depending on configuration and DB state.

### 6.3. Meaning of HikariCP Parameters

| HikariCP property | Meaning | Consequence if misconfigured |
|---|---|---|
| `maximumPoolSize` | Maximum physical connections in the pool | Too large causes session storms; too small causes waits |
| `minimumIdle` | Desired idle connections | Setting high increases footprint, especially across many replicas |
| `connectionTimeout` | Max wait to borrow a connection from the pool | Too long queues HTTP threads; too short fails during spikes |
| `validationTimeout` | Threshold to check whether a connection is alive | Too long slows acquisition; must align with connectionTimeout |
| `idleTimeout` | Idle duration before excess connections above minIdle may be retired | Less effective than expected with fixed-size pools |
| `maxLifetime` | Maximum lifetime of a connection in the pool | Should be shorter than known network/DB connection lifetime limits |
| `keepaliveTime` | Periodic health check for idle connections per Hikari rules | Not a keepalive for arbitrary queries or every failure |
| `leakDetectionThreshold` | Warning threshold for a connection held too long | May produce false positives for legitimate long transactions |
| `initializationFailTimeout` | Fail-fast behavior if pool creation/check fails at startup | Weigh against dependency availability and app lifecycle |

Values like 10 connections, 3 seconds, and 25 minutes in the example are **illustrative lab values**, not optimal defaults for every Azure database. `maxLifetime` does not act as a hard timeout that abruptly kills an in-flight query; Hikari primarily retires connections once they return to a reclaimable state.

### 6.4. HikariCP Is Not a Database Connection Proxy

The pool typically lives **inside the JVM** of each app instance. With 12 pods, there are **12 separate pools**, not a cluster-wide shared pool. Solutions like PgBouncer (PostgreSQL) or other connection proxies can be evaluated separately, but they come with constraints around session/transaction mode, prepared statements, and authentication that must be verified. Do not treat a proxy as a free fix for unindexed queries or transactions holding locks too long.

## 7. Calculating Total Connections Under Autoscale

A common design mistake: configuring `maximumPoolSize=30` because "each JVM can handle 30 threads," forgetting the replica count.

Upper-bound estimate:

\[
Connections_{potential}=Replicas_{max}\times PoolsPerReplica\times MaximumPoolSize
\]

Example:

```text
Max AKS replicas = 20
Write pools per pod = 1
Max pool size = 10

Maximum from Java API ≈ 20 × 1 × 10 = 200 connections
```

If the DB tier only allows roughly 120 effective connections and still needs 20 connections reserved for administration, ETL, migrations, health checks, and other jobs, 200 is a risky configuration. Not every connection is open at all times, but **during simultaneous scale-out and traffic spikes**—often when DB capacity is tightest—this ceiling can be reached.

### 7.1. A Budgeted Estimation Formula

With a hypothetical example:

```text
Effective DB limit               = 120
System/operations reserve        = 20
Other clients                    = 20
Max Java replicas                = 20

Pool budget per replica = floor((120 - 20 - 20) / 20) = 4
```

This is a **preliminary capacity planning calculation**, not a performance guarantee at 4 connections. Effective limits also depend on service tier, session overhead, DB parallelism, replication, and connection types. Always **load test** to choose pool size based on actual throughput and latency.

### 7.2. Three Sources That Exceed Estimates

- **Rolling deployments:** old and new pods run concurrently, pushing total connections above the target `replicas`; account for `maxSurge` or similar rollout mechanisms.
- **Multiple DataSources:** read pools, write pools, migration/admin pools, or multi-tenant pools multiply the total connection count.
- **Background workers:** scheduled jobs, outbox relays, ETL, BI tools, or serverless functions can add concurrent connections.

During rapid scale-out, control **startup burst**, `minimumIdle`, and max replicas. Do not create 100 idle connections per pod when the DB only needs a few concurrent queries.

### 7.3. Why Fewer Connections Are Sometimes Faster

If a query takes 50 ms of CPU/IO and the database only has capacity to process a limited number of requests efficiently at once, pushing too many concurrent clients into the DB causes contention; a bounded queue in front of the database often yields better p95 latency. That is why you should measure:

```text
request latency
pool acquisition wait
DB query duration
DB CPU/IO
lock wait / deadlocks
active connections
error / timeout rates
```

Increasing pool size only helps when **the pool itself is the genuine bottleneck** and the DB has headroom to absorb more work. If DB CPU is already 95% or lock waits are climbing, optimize SQL, indexes, and transactions first.

## 8. Timeouts You Must Not Confuse

A single request can encounter several distinct waiting periods:

```text
HTTP request deadline (e.g., 5s)
    |
    +-- Pool acquisition (connectionTimeout, e.g., 1s)
    |
    +-- TCP connect + TLS/login (driver timeouts)
    |
    +-- SQL execution (statement/query timeout)
    |
    +-- ResultSet streaming / socket read
    |
    +-- COMMIT / ROLLBACK
```

### 8.1. Distinguishing Each Timeout

| Timeout | Controls | Example consequence |
|---|---|---|
| **HTTP deadline** | Total time caller waits for API | Caller disconnects; server may keep running unless cancelled |
| **Hikari `connectionTimeout`** | Time waiting to borrow a connection from pool | Pool exhausted when threads occupy all slots |
| **Connect timeout** | Establishing TCP connection to database | DNS/route/firewall or server unreachable |
| **Login timeout** | DB authentication phase per driver | Slow or failing Entra token/password/DB login |
| **JDBC query/statement timeout** | Query execution time per driver | Query cancelled per driver/server semantics |
| **Socket/network timeout** | Network read/write at the driver layer | Can occur mid-query or during COMMIT |
| **Transaction timeout** | Unit-of-work limit per framework | Prevents holding connections/locks too long |

**Do not assume a query timeout always rolls back the entire transaction.** Depending on the database and driver, the connection/transaction may end up needing an explicit rollback or become unusable. In PostgreSQL, a failed statement inside a transaction marks the transaction as aborted until rollback; in SQL Server, the effect depends on the error and transaction settings. Always handle rollback and classify exceptions explicitly.

### 8.2. Choosing Deadlines Systematically

Example for an API with a 5-second deadline:

```text
HTTP deadline          5.0s
Pool acquisition       0.8s
SQL statement          2.0s
Application/parsing    0.3s
Retry/network margin   remainder
```

This is only an **illustrative budget**, not independent timeouts allowed to be spent in full on every retry. Retrying three times with a 2-second query timeout each exceeds a 5-second deadline unless total request time is tracked. Propagate and enforce a **time budget** across layers.

### 8.3. A Client Query Timeout Does Not Mean Work Was Not Committed

When a socket error occurs after sending `COMMIT`, the server may have already committed while the response never reached the client. **Never assert a transaction rolled back simply because the client saw a timeout.** For writes, payments, or order placement, use an idempotency key and outcome verification instead of blind repetition.

## 9. Spring Boot and Pool Configuration in application.yml

Spring Boot can auto-configure a `DataSource` based on the available JDBC driver and pool implementation. For a Spring Boot application using HikariCP, you can configure it as follows:

```yaml
spring:
  datasource:
    url: "${DB_JDBC_URL}"
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
    hikari:
      pool-name: orders-write-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 300000
      max-lifetime: 1500000
      keepalive-time: 120000

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
```

The `${...}` expressions in this template are **Spring property placeholders**; the application reads actual environment variables at startup. Never put real passwords into a committed `application.yml`. In production, secrets must come from a tightly scoped source; even putting secrets in environment variables requires controlling access to config inspection, pod inspection, and memory dumps.

### 9.1. An Application-Scoped DataSource

```java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class OrdersRepository {
    private final JdbcTemplate jdbc;

    public OrdersRepository(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public int updateStatus(String orderId, String newStatus) {
        return jdbc.update(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                newStatus, orderId);
    }
}
```

Spring manages the `DataSource` and connections according to the application context and transaction manager. Never construct `new HikariDataSource` inside each `updateStatus` call. `JdbcTemplate` simplifies closing JDBC resources, yet transaction boundaries and retry logic must still be designed carefully.

### 9.2. `@Transactional` Only Protects One Database Transaction

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrdersRepository orders;

    public OrderApplicationService(OrdersRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void markPaid(String orderId) {
        int updated = orders.updateStatus(orderId, "PAID");
        if (updated != 1) {
            throw new IllegalArgumentException("Order not found");
        }
    }
}
```

This example illustrates a transaction boundary in Spring when the transaction manager is properly configured. `@Transactional` **does not automatically guarantee atomicity** across SQL Database and external services such as Service Bus, a payment provider, or a REST API.

A common mistake is calling a `@Transactional` method via **self-invocation within the same object**, assuming the proxy still applies the transaction. Understand your framework version's transaction management, propagation, isolation, and method visibility rules.

### 9.3. Do Not Open a Transaction and Make a Slow HTTP Call

```text
BEGIN DB transaction
  SELECT order FOR UPDATE
  HTTP call Payment API (waits 30 seconds)
  UPDATE order
COMMIT
```

This is an anti-pattern: the connection—and possibly row locks—are held while waiting on the network. Break workflows into short steps using durable state, outbox/saga patterns, or idempotent external API calls. **The shorter the transaction, the lower the risk of pool exhaustion and lock contention.**

## 10. Authentication: Password or Microsoft Entra Managed Identity?

Azure relational databases can support different authentication methods depending on the service, tier, and configuration:

| Approach | Advantages | Considerations |
|---|---|---|
| **DB username/password** | Broad JDBC driver compatibility | Requires secret store, rotation, least privilege, and no hard-coding |
| **Microsoft Entra ID authentication** | Central principal and permission management via Entra where supported | Requires configuring DB principal/roles and driver/token setup |
| **Managed identity / AKS Workload Identity** | Workloads hold no long-lived client secrets | Entra access tokens expire; driver/pool must handle refresh properly |
| **Integrated workload credentials** | Uses Azure Identity/driver environment-based token issuance | Depends on JDK, JDBC driver version, and cloud/tenant |

**A managed identity with Azure RBAC Contributor on the database resource does not automatically have SELECT rights inside the database.** You must configure a database-level authentication principal and appropriate GRANT/roles according to Azure SQL, PostgreSQL, or MySQL mechanisms. Azure resource management RBAC and SQL data-plane permissions are two separate scopes.

### 10.1. Azure SQL JDBC and Entra Authentication

The Microsoft JDBC Driver for SQL Server supports Entra authentication modes depending on version, such as `ActiveDirectoryManagedIdentity`, `ActiveDirectoryDefault`, or token-based auth via the appropriate API. **Conceptual connection string** example using the runtime identity:

```text
jdbc:sqlserver://orders-sql.database.windows.net:1433;databaseName=ordersdb;encrypt=true;trustServerCertificate=false;authentication=ActiveDirectoryManagedIdentity;
```

Exact mode/property names for **user-assigned identity**, driver dependencies, and client ID selection vary across versions. Do not assume all `mssql-jdbc` versions accept the same `user`/`msiClientId` syntax or automatically enable AKS workload identity federation. **Verify the exact driver version and environment**, provision the DB principal for the identity, and test connectivity before rolling out to the Hikari pool.

### 10.2. PostgreSQL/MySQL with Entra Access Tokens

Microsoft Entra authentication on PostgreSQL/MySQL can use an **access token as the login credential** depending on enabled features. A token has an **expiration**; if you initialize HikariCP with a static password set to an access token fetched at startup, **new connections** opened after expiration will fail while older sessions remain alive.

A safe design requires:

1. Identifying the service/driver and supported Entra authentication flow.
2. Provisioning the appropriate database principal/permissions for the managed identity.
3. Acquiring tokens with the audience/scope matching **the exact Azure database service**.
4. Integrating **token refresh whenever opening a physical connection**, or using a driver/pool-supported plugin/callback mechanism.
5. Never logging access tokens, keeping them in JVM dumps or config files, or reusing an immutable token as a password for hours.
6. Load-testing token expiration, failover, pool recycling, and simultaneous multi-replica startup.

Do not copy a `dataSource.setPassword(token)` snippet that runs once at startup and conclude it is production-ready; verify renewal behavior when the pool opens new connections.

### 10.3. Database Permissions Checklist

- Entra admin and authentication options are configured per the Azure service.
- Managed identity/service principal actually has a corresponding DB user/role.
- Runtime accounts only hold `SELECT/INSERT/UPDATE` on required tables/schemas; restrict `ALTER`/`DROP` in runtime.
- Migration/schema admin user is separated from the runtime application.
- Network/DNS/TLS and the Entra token endpoint are reachable wherever workloads need tokens.
- Secret/token rotation, principal changes, and failover have been tested.

### 10.4. Separating Migration and Runtime Permissions

Running Flyway/Liquibase migrations usually requires `CREATE/ALTER`; an application that only reads and writes orders does not need those privileges. If both share an admin credential, a SQL injection or bug could alter the schema.

Use a dedicated **migration identity** operated through CI/CD with approvals, while the runtime DataSource uses a least-privilege principal, especially in production.

## 11. Classifying JDBC Errors Before Retrying

`SQLException` carries rich information:

- `getSQLState()`: SQL state code by error class.
- `getErrorCode()`: database/driver-specific vendor error code.
- `getNextException()`, `getCause()`: chained exceptions that may reveal the root cause.
- Subtypes such as `SQLTransientException`, `SQLNonTransientException`, and `SQLRecoverableException` when used by the driver.

**You cannot decide "every SQLException is retryable."** The same timeout symptom could happen when opening a connection before a transaction, mid-update, or after COMMIT was sent—and the safety of retrying differs in each case.

### 11.1. SQLState Is a Hint, Not a Complete Policy

| SQLState / code | Typical meaning | How to retry |
|---|---|---|
| Class **`08`** | Connection exception | Can retry *new connection*; if writes/commit already sent, assess uncertainty |
| **`40001`** | Serialization failure/transaction rollback in some engines | Retry **the entire new transaction** after rollback, bounded |
| **`40P01`** (PostgreSQL) | Deadlock detected | Retry the rolled-back transaction in full, with backoff |
| **1205** (SQL Server vendor error) | Deadlock victim | Retry a new transaction after confirming DB aborted the transaction |
| **1213** (MySQL vendor error) | Deadlock | Retry a new transaction when driver/engine signals appropriate rollback |
| **40501** (Azure SQL vendor error) | Context-dependent throttling/busy condition | Retry with backoff in safe scope, following service guidance |
| **40613 / 40197** (Azure SQL vendor errors) | Temporary DB unavailability/processing error depending on context | Can retry connection/idempotent operations, checking transaction phase |
| **23505** (PostgreSQL) | Unique constraint violation | Usually business/duplicate error; do not keep retrying blindly |
| **28xxx** | Invalid authorization/authentication in some engines | Fix credentials/DB principal/roles; do not blind retry |
| **42xxx** | Syntax/object/authorization-related SQL errors depending on engine | Usually fix schema/query/permissions; do not simply retry |

The codes in this table are **common examples, not a standardized list across all drivers**. MySQL, PostgreSQL, and SQL Server map errors differently. Always consult driver/engine documentation and real logs before finalizing a production retry allowlist.

### 11.2. Errors That Should Fail Fast

- Wrong username/password, Entra principal lacking database permissions.
- Non-existent DNS hostname from persistent misconfiguration.
- Connection string with wrong driver/port/DB name.
- TLS hostname/certificate verification failure.
- Missing table/column or invalid SQL syntax.
- Unique constraint/foreign key/check constraint violated by invalid data.
- Insufficient tenant permissions or query accessing out-of-scope data.

Blindly retrying these errors increases latency and floods logs with **zero chance of success**. Return the appropriate error, raise an alert, and fix the configuration, schema, or data.

### 11.3. Potentially Transient Errors

- Azure service primary switch/failover or maintenance resetting older connections.
- Brief network interruption.
- Database overload/throttling requiring deceleration and backoff.
- Transaction chosen as deadlock victim or hitting serialization failure.
- Idle connection closed by firewall/NAT/database requiring the pool to open a replacement.

Even for transient errors, retries must be bounded by **attempt count, time budget, idempotency guarantees, and capacity**. Not every transient error justifies retrying an entire business workflow.

### 11.4. Two Dimensions to Determine

Before retrying, always ask two questions:

1. **At which phase did the error occur?** Before opening a connection, before any writes, inside an already rolled-back transaction, or after COMMIT was sent?
2. **Can the operation be re-executed safely?** Read-only, insert with a unique request ID, idempotent state update, or did it already emit external side effects?

For example, `UPDATE accounts SET balance = balance - 100 WHERE account_id = ?` is **not idempotent** if re-run after an unknown commit outcome. Conversely, `UPDATE orders SET status='PAID' WHERE id=?` may be idempotent in terms of state, yet you must still account for triggers, timestamps, audit records, and downstream side effects.

## 12. Retry Policy: Backoff, Jitter, and Time Budget

A sound retry policy includes an **error allowlist**, **max attempts**, **increasing backoff**, **jitter**, a **request deadline**, and **bounded logs/metrics**.

### 12.1. Exponential Backoff with Jitter

Illustrative example:

```text
Attempt 1: execute immediately
Attempt 2: wait ~100–250 ms
Attempt 3: wait ~250–600 ms
Attempt 4: wait ~600–1200 ms
Out of attempts or past deadline: return error for caller to handle
```

Actual timings depend on SLOs and failover/throttling durations rather than fixed magic numbers for Azure. Across hundreds of replicas, **jitter** prevents all instances from retrying in lockstep as the database recovers.

A conceptual calculation:

\[
delay_n=\min(delay_{max},delay_{base}\times 2^{n-1}) + randomJitter
\]

If multiple layers retry independently (HTTP gateway, service, JDBC driver, and transaction handler), total attempts can **multiply**. For example, three layers each retrying up to three times can trigger 27 downstream attempts. Assign retry responsibility cleanly to prevent a **retry storm**.

### 12.2. Time-Budgeted Retries

If an HTTP endpoint has a 5-second deadline, a transaction cannot retry 10 times with a 3-second statement timeout each. One strategy:

- Cap at **2–4 attempts** for allowlisted errors, though do not treat this range as a rigid rule.
- Stop when the remaining deadline is too short for a meaningful attempt.
- Respect cancellation/interruption signals; never swallow `InterruptedException`.
- Optionally add a circuit breaker to block new requests during prolonged DB outages.
- Never hold a `Connection` while sleeping between retries.

### 12.3. Retrying at the Right Layer

| Layer | Sensible retry | What not to do |
|---|---|---|
| **HikariCP/driver** | Manages broken connections and supported reconnect behavior | Assume the pool replays SQL transactions |
| **Repository/read query** | Short, deterministic SELECT with no side effects | Loop queries indefinitely, piling load onto a throttled DB |
| **Transaction service** | Retry the **entire rolled-back transaction** on deadlock/serialization failure | Retry an individual statement mid-broken transaction |
| **HTTP/API boundary** | Retry request if contract supports idempotency | Replay a payment POST without an idempotency key |
| **Background worker** | Retry job with a stable event ID and durable data | Complete the message before DB commit or trigger duplicate side effects |

## 13. Java: Retry Rolled-Back Transactions, Never Blind-Retry COMMIT

Here is a conservative **plain Java** example: it only retries SQL transactions identified as deadlock/serialization-aborted after a successful rollback. It intentionally **does not auto-retry** errors during `commit()` because the commit may have succeeded without the client receiving the ACK.

### 13.1. Executor Pattern for Database Transactions

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class TransactionRetry {
    private static final int MAX_ATTEMPTS = 4;
    private final DataSource dataSource;

    @FunctionalInterface
    public interface Work<T> {
        T execute(Connection connection) throws SQLException;
    }

    public TransactionRetry(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public <T> T run(Work<T> work) throws SQLException, InterruptedException {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try (Connection conn = dataSource.getConnection()) {
                conn.setAutoCommit(false);
                boolean commitStarted = false;

                try {
                    T result = work.execute(conn);
                    commitStarted = true;
                    conn.commit();
                    return result;
                } catch (SQLException ex) {
                    if (commitStarted) {
                        // COMMIT was invoked, but response failed:
                        // Unknown whether the server committed.
                        throw new SQLException(
                                "Commit outcome unknown; reconcile by request ID",
                                ex);
                    }

                    // Do not retry if safe rollback fails.
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                        throw ex;
                    }

                    if (!retryableAbortedTransaction(ex)
                            || attempt == MAX_ATTEMPTS) {
                        throw ex;
                    }
                } catch (RuntimeException businessError) {
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackFailure) {
                        businessError.addSuppressed(rollbackFailure);
                    }
                    throw businessError;
                }
            }

            // After Connection has been returned to the pool.
            long baseMs = Math.min(800L, 100L << (attempt - 1));
            long jitterMs = ThreadLocalRandom.current().nextLong(20, 150);
            Thread.sleep(baseMs + jitterMs);
        }
        throw new IllegalStateException("Unreachable");
    }

    private static boolean retryableAbortedTransaction(SQLException ex) {
        String state = ex.getSQLState();
        int vendorCode = ex.getErrorCode();
        return "40001".equals(state)
                || "40P01".equals(state)  // PostgreSQL deadlock
                || vendorCode == 1205     // SQL Server deadlock victim
                || vendorCode == 1213;    // MySQL deadlock
    }
}
```

**Example scope:** intended strictly for code running **a single database transaction**, without calling payment APIs, publishing messages, sending emails, or writing files outside the transaction. To handle `SQLException` when **`getConnection()`** fails, you can add a **separate acquisition retry** with an error classifier and deadline; this example intentionally lets that error propagate to avoid accidentally retrying an uncertain operation state.

**Point of caution:** once `commit()` succeeds, even an error closing/returning the connection does not mean the transaction failed. For business commands needing at-most-once effect, the caller must not blind-retry solely because an exception surfaced near completion; it must verify the request ID in the database.

### 13.2. Using the Executor with PreparedStatement

```java
TransactionRetry retry = new TransactionRetry(dataSource);

String orderId = "ORD-1042";
retry.run(conn -> {
    try (var ps = conn.prepareStatement(
            "UPDATE orders SET status = ? WHERE order_id = ?")) {
        ps.setString(1, "PAID");
        ps.setString(2, orderId);
        int changed = ps.executeUpdate();
        if (changed != 1) {
            throw new SQLException("Unexpected order row count");
        }
    }
    return null;
});
```

This is a **snippet inside a method** holding `dataSource`. Production readiness also requires deadlines, metrics, driver-specific exception mapping, business invariant checks, idempotency keys, and safe logging. The example deliberately omits retrying connection errors after writes; those require different handling depending on the phase.

### 13.3. Why Not Retry Individual Statements?

Suppose a transaction has three steps:

```sql
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
INSERT INTO transfers(transfer_id, status) VALUES (?, 'COMPLETED');
```

If the second statement hits a deadlock and the transaction is rolled back, **retrying only the second statement** without replaying the entire transaction produces corrupt results; if the first statement was already rolled back unbeknownst to the code, the retry no longer matches the original business operation.

For transactions aborted by serialization/deadlock, retry **the entire unit of work in a new transaction**, carrying the same logical transfer ID and checking invariants. Never partially retry and continue using a connection left in a failed transaction state.

## 14. “Commit Outcome Unknown”: The Most Dangerous Case

Scenario:

```text
Java                             Azure database
 |                                   |
 | BEGIN                             |
 | INSERT orders(order_id='ORD-42')  |
 |---------------------------------->|
 | COMMIT                            |
 |---------------------------------->|
 |                       COMMIT succeeded
 |             X Network reset before COMMIT ACK
 |<----------------------- (response lost)
 |
 | SQLException: connection lost
 | COMMIT OUTCOME? UNCERTAIN
```

If Java retries with a different `order_id` and invokes payment again, it can create **two orders or two charges**. A connection error after COMMIT does not mean the server rolled back.

### 14.1. Business-Layer Idempotency Key

An order creation API can require an **idempotency key** deterministically tied to the logical request by the client/gateway/service:

```http
POST /orders HTTP/1.1
Idempotency-Key: req-20261120-1042
Content-Type: application/json

{"productId":"SKU-17","quantity":1}
```

In the database, a table stores the request ID and transaction outcome:

```sql
CREATE TABLE order_requests (
    request_id VARCHAR(120) PRIMARY KEY,
    order_id VARCHAR(120) NOT NULL,
    result_status VARCHAR(30) NOT NULL
);
```

When retrying, the system queries `request_id` first or relies on a **unique constraint** so a second order cannot be created. If a request uses the same key with a different payload, detect a conflict error and reject it instead of letting keys be arbitrarily reused.

### 14.2. A Unique Constraint Is the Final Safeguard

A pre-check like:

```text
SELECT request_id -> not found
INSERT order -> succeeds
```

does not prevent two concurrent requests from both checking and both inserting. You need a **unique constraint** and proper transaction isolation. On a unique violation, the application should retrieve and return the original result per contract if the logical request matches, rather than retrying the insert endlessly.

### 14.3. Do Not Combine DB Commit and Service Bus Send on Faith

If Java saves an order to SQL and then sends `OrderCreated` to Azure Service Bus, those two actions do not automatically form an atomic transaction. When events must not be lost after DB commit, use a **transactional outbox**:

```text
DB transaction:
  INSERT orders
  INSERT outbox_events(event_id, payload)
  COMMIT

Outbox relay:
  read unsent outbox rows
  publish event with stable event_id
  mark sent after broker acknowledgment

Consumer:
  inbox/idempotent processing to tolerate duplicate delivery
```

An outbox prevents losing committed events, though duplicates can still be published if the relay crashes after broker ACK before marking the row sent. Therefore, **consumers must still be idempotent**.

### 14.4. Integrating with a Payment Provider

For charging, transferring funds, or provisioning resources in external services, a DB transaction only protects data inside that database. You need **downstream-supported idempotency keys**, transaction status lookups, and saga/compensation flows where needed. Never treat JDBC retries as an exactly-once guarantee for an entire workflow.

## 15. Transaction Isolation and Concurrency Handling

JDBC allows setting the transaction isolation level, but **actual semantics depend on the database engine** and can interact with options such as optimistic concurrency, snapshot isolation, or server defaults.

| Isolation concept | Goal | Risks/trade-offs |
|---|---|---|
| **READ COMMITTED** | Avoids reading uncommitted data per engine definition | Does not automatically prevent non-repeatable reads/phantoms |
| **REPEATABLE READ** | Greater read stability within a transaction | Can increase contention or cause serialization conflicts depending on engine |
| **SERIALIZABLE** | Stronger guarantee of serial-equivalent behavior | Can increase blocking/serialization failures; requires proper retries |
| **Snapshot/MVCC variants** | Consistent reads via database-specific mechanisms | Carries its own trade-offs and conflict handling |

Do not pick `SERIALIZABLE` for every request merely because it sounds "safest." Weigh business invariants, performance, retry capability, and how Azure SQL/PostgreSQL/MySQL implement isolation levels.

### 15.1. Optimistic Concurrency with Versions

One way to avoid overwriting another request's changes:

```sql
UPDATE orders
SET status = ?, version = version + 1
WHERE order_id = ? AND version = ?;
```

Java checks the affected row count. If 0, the data already changed or the record does not exist; that may be a **business conflict**, not a transient connection error. Do not blind-retry until the UPDATE wins: re-read the state and apply business rules.

### 15.2. Keep Locks Short

Anti-pattern:

```text
BEGIN
  SELECT ... FOR UPDATE
  HTTP call external service (30 seconds)
  UPDATE ...
COMMIT
```

Holding row locks and a JDBC connection while waiting on HTTP increases pool occupancy and deadlock risk. For multi-step workflows, use durable state and asynchronous messaging rather than spanning a single transaction across external systems.

### 15.3. Do Not Depend on Leaked Session State

Connections from Hikari are reused. If code changes `autoCommit`, isolation, schema, timezone, or other session settings via raw SQL without resetting them properly, the next request may inherit unexpected state. Some connection properties are tracked and reset by the pool, but you cannot rely on the pool to reset every **server-side session setting** across databases.

Prefer the framework transaction manager, appropriate connection init settings, and clean connection state before returning to the pool. If using PostgreSQL advisory locks, temp tables, or session variables, design explicit cleanup.

## 16. Connection Leaks and Diagnosing Pool Exhaustion

A **connection leak** happens when code borrows a connection and fails to return it to the pool when done. If a pool has 10 connections and all are held, the 11th request waits up to `connectionTimeout` and then fails.

### 16.1. Bad Example

```java
public String loadStatusBad(DataSource ds, String orderId)
        throws SQLException {
    Connection conn = ds.getConnection();  // Not closed.
    PreparedStatement ps =
            conn.prepareStatement(
                    "SELECT status FROM orders WHERE order_id = ?");
    ps.setString(1, orderId);
    ResultSet rs = ps.executeQuery();
    return rs.next() ? rs.getString(1) : null;
}
```

Here there is no `finally` block or `try-with-resources`; every successful request can leave a connection held until the process ends or unreliable garbage collection/driver cleanup kicks in. **Never rely on GC to return connections.**

### 16.2. Good Example

```java
public String loadStatusGood(DataSource ds, String orderId)
        throws SQLException {
    try (Connection conn = ds.getConnection();
         PreparedStatement ps = conn.prepareStatement(
                 "SELECT status FROM orders WHERE order_id = ?")) {
        ps.setString(1, orderId);
        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString(1) : null;
        }
    }
}
```

### 16.3. A Leak Warning Is Not Always a True Leak

Hikari `leakDetectionThreshold` triggers warnings when a connection is held past the threshold. A query legitimately taking 25 seconds with a 20-second threshold emits a warning even though the connection is eventually returned. In that case, look for a **slow query/long transaction** rather than immediately blaming a missing close.

Analyze alongside these signals:

- `active connections` stays elevated and does not drop after traffic stops.
- `idle connections` approaches 0, `pending threads` climbs, and acquisition timeouts occur.
- Thread dumps/stack traces show threads waiting on SQL, calling HTTP, or missing close.
- DB-side sessions/transactions in active or `idle-in-transaction` states.
- Slow query logs and query execution plans.

### 16.4. Leaks from Framework Boundaries

In Spring/JPA:

- Opening a transaction in a controller and returning a streaming response can hold a connection for a long time.
- Triggering lazy loading outside a transaction boundary can fail or acquire unexpected extra connections.
- An `@Async` method does not automatically inherit another thread's transaction context seamlessly.
- Background jobs manually creating an `EntityManager`/`Session` without closing it properly can leak resources.

Measure **connection hold time**, not just concurrent request count. Inspect transaction boundaries as well as error and cancellation paths.

## 17. Failover Incidents and How the Connection Pool Should Recover

Suppose Azure SQL or Azure Database for PostgreSQL experiences a failover. Some TCP connections to the old primary may close; the pool retains objects representing those connections until they are detected as invalid.

```text
T0: primary active -> Java pool has 8 connections
T1: failover/maintenance -> some connections become invalid
T2: request receives stale connection -> SQLException/connection reset
T3: pool evicts broken connection, attempts to open a new connection
T4: new DNS/route/primary is ready, authentication succeeds
T5: queries resume, though some requests had to retry safely
```

### 17.1. Design Principles

- Use the **official Azure database service hostname**, never a hardcoded current primary IP.
- Check JVM and network DNS TTL/caching behavior if failover relies on DNS updates.
- Configure Hikari connection validation, `maxLifetime`/`keepaliveTime` appropriately; never force reuse of a connection marked broken.
- Allow bounded timeouts and retries during brief failovers, without queuing thousands of HTTP requests indefinitely.
- Correlate alerts from DB failover/connectivity/compute metrics to distinguish DB incidents from pool capacity issues.
- After recovery, verify **business outcomes** of interrupted transactions.

**Do not lower `maxLifetime` to a few seconds** to force every request to open fresh sockets constantly; that inflates authentication/TLS overhead and can trigger a connection storm while the DB is still recovering.

### 17.2. Read Replicas and Read/Write Splitting

When an architecture uses read replicas (where supported by service/tier), you may have separate **read DataSource** and **write DataSource** instances. This is not free:

- Read replicas can **lag** behind the primary; read-your-writes requirements need a deliberate strategy.
- Each DataSource maintains its own pool, multiplying total connections.
- Update transactions must go to the writer; do not automatically route reads inside a write transaction to a replica and break consistency.
- When a replica fails, the application must have controlled degrade/fallback behavior.

Do not treat replicas as a cure for deadlocks on the writer or unindexed write queries.

### 17.3. Starting Up During a Database Outage

An application can choose between:

- **Fail-fast startup** when the DB is a mandatory dependency and no requests can be served without it.
- **Start but not ready** when the runtime needs to stay alive to retry/recover, while `readiness` accurately reflects business API availability.
- Background workers may continue non-DB work or wait for reconnect according to policy.

Do not abuse Kubernetes **liveness probes** to restart entire pods merely because the DB is temporarily unavailable: that causes restart storms and connection storms. Liveness measures whether the process is healthy; readiness reflects ability to serve traffic per contract.

## 18. Monitoring: Watching Both the Java Pool and the Azure Database

When an API returns 503 because it cannot borrow a connection, you must know whether the cause is an **undersized pool**, a **connection leak**, **slow queries/locks**, or a **database/network outage**.

### 18.1. HikariCP Metrics

In Spring Boot + Micrometer/Actuator or a compatible metrics stack, track:

| Conceptual metric | Meaning | Abnormal signal |
|---|---|---|
| **Active connections** | Currently lent connections | Near max for too long |
| **Idle connections** | Connections ready to lend | Consistently 0 under light load |
| **Pending acquisition** | Threads waiting for a connection | Climbing steadily, request latency rising |
| **Total connections** | Active + idle | Unexpected spikes/drops during scaling/failover |
| **Acquire time** | Time to borrow a connection | p95/p99 climbing when pool is under pressure |
| **Connection creation time** | Opening a new physical connection | Climbing when network/login slows down |
| **Timeout count** | Failures to obtain a connection in time | Pool, DB, or code holding connections too long |

Actual metric names may look like `hikaricp.connections.active` or Prometheus-mapped underscore names depending on framework/registry. **Do not hard-code metric names before inspecting your actual endpoint/registry.**

### 18.2. Azure Database Metrics

Observe metrics appropriate for the service/tier:

- CPU, memory, and storage pressure; I/O throughput/latency per supported metrics.
- **Active connections/sessions** count and limits.
- Failed connections, failed logins, connection throttling.
- Deadlocks, lock waits, query duration, and expensive SQL.
- Failover/maintenance events or service health status.
- Network errors and private endpoint/DNS events in available logs.

Metric names differ across Azure SQL Database, PostgreSQL Flexible Server, and MySQL Flexible Server. Never assume a SQL Server DMV chart exists identically on PostgreSQL or vice versa.

### 18.3. A Minimal Dashboard

```text
AKS API replicas                  12
Hikari maximumPoolSize            8
Estimated app connection ceiling 96
Hikari active (aggregate)        74
Hikari pending threads            9
DB active sessions               110
DB CPU                           87%
HTTP p95 latency                 2.4 s
DB query p95 latency             1.8 s
Connection acquire timeout/min   24
```

These numbers are illustrative. If `Hikari active` and `pending` are both high while DB CPU is 87% and SQL latency is climbing, raising pool size from 8 to 20 can overload the DB further. Identify the **bottleneck** via tracing, slow queries, and SQL execution plans first.

### 18.4. How Does Distributed Tracing Help?

An HTTP request trace can break down into:

```text
HTTP POST /orders  1800ms
  |
  +-- Auth/JWT check   30ms
  +-- Pool acquire     650ms
  +-- SQL INSERT       920ms
  +-- Business logic    50ms
  +-- HTTP response    150ms
```

Looking only at 920ms SQL execution while ignoring 650ms pool acquisition misses a major share of latency. Instrument JDBC/client spans and HTTP spans with OpenTelemetry/Application Insights or compatible tooling; **never place sensitive SQL parameters or credentials into traces**.

### 18.5. Alerts with Runbooks

Useful alerts include:

- Sustained high Hikari pending connections + rising timeout count.
- DB connections approaching limits as replicas/scale increase.
- Rising login/authentication failures after credential rotation.
- Rising query p95 or deadlock/serialization failures.
- DB CPU/IO saturation, storage capacity warnings, or failover events.
- Pool acquisition p95 consuming a significant fraction of the HTTP request budget.
- High request failure rate paired with dropping retry success rate—indicating retries are no longer helping.

Alerts should have an **owner, evaluation window, severity, action group, and runbook**. Never create an alert for "active connections > 0," since that is normal behavior.

## 19. Securing Connections and Data

### 19.1. Secrets and Rotation

When using password authentication:

1. Store passwords in Azure Key Vault or an equivalent secret store with least-privilege access.
2. Access secrets via the workload's managed identity when supported.
3. Have a rotation workflow using alternate accounts/credentials or dual credentials where supported.
4. Ensure the app/pool opens new connections with the current credential; **existing live physical connections might not be forced to re-authenticate immediately**.
5. Never log a JDBC URL if it embeds a username/password or access token; mask sensitive fields.

Updating a password in Key Vault **does not mean** every JVM automatically picks up the new value. If the app reads secrets at startup, design a safe refresh/restart procedure.

### 19.2. Principle of Least Privilege in the Database

- Runtime accounts only hold permissions on needed schemas/tables.
- Separate read-only workloads where appropriate.
- Use parameterized SQL and enforce tenant/ownership checks.
- Separate database migration admin accounts from runtime.
- Evaluate row-level security if supported by engine/schema, without treating it as a substitute for full application authorization.
- Restrict queries able to read system tables or administrative metadata beyond what is required.

### 19.3. Private Networking and Encryption in Transit

Choose Private Endpoint/VNet integration/private access according to supported Azure database and network topologies. If public access must be enabled for external integration, apply firewall rules, source restrictions, TLS, and a matching threat model; never leave `0.0.0.0/0` as a default.

**TLS in JDBC requires hostname verification**, not merely "an encrypted socket." Use the appropriate Azure CA trust chain and rotate certificates cleanly. Never print certificate private keys, access tokens, or connection strings containing secrets to logs.

### 19.4. Accounts and Data in Logs

Log `operation`, SQLState, vendor code, retry attempt, query fingerprint, pool name, DB resource ID/region, and correlation ID as needed. Never log:

- Full SQL containing interpolated sensitive values.
- Usernames/passwords/access tokens or SAS keys.
- Full connection strings containing secrets.
- PII, payment data, or full query result sets.
- Stack traces in public HTTP responses.

Investigations need **error codes**, **operation phase**, **timestamps**, and **blast radius**, without exposing customer data.

## 20. Troubleshooting: Finding Root Cause Instead of Growing the Pool

### 20.1. Symptom – Cause – Action Table

| Symptom | Possible cause | What to check |
|---|---|---|
| `Connection is not available, request timed out` from Hikari | Pool ran out of connections or connections held too long | Active/idle/pending, long transactions, slow SQL, leaks |
| `Connection refused` | Wrong hostname/port, service unreachable, firewall | DNS, routes, ports, Azure DB networking |
| `Connection timed out` on connect | Network/DNS/private endpoint issue or DB unresponsive | VNet, NSG, firewall, private DNS, failover events |
| `SSLHandshakeException` / certificate validation error | Wrong CA trust, hostname, or TLS config | Driver/JDK trust store, FQDN, and certificate chain |
| Login failed / SQLState `28...` | Invalid credential/token, missing DB user/role | Entra principal, DB auth, credential rotation |
| Failures immediately after password rotation | App/pool still creating physical connections with old password | Secret refresh/restart, rotation order, and safe logs |
| SQLState class `08` mid-query | Network reset, failover, broken connection | Operation phase, pool eviction, idempotency |
| `40001` or deadlock vendor code | Serialization/deadlock | Retry whole new transaction, optimize lock order/queries |
| `23505` after retry | Unique constraint/duplicate logical request | Use request ID to look up prior outcome |
| Azure SQL `40501` | Database busy/throttled depending on context | Compute/capacity, retry-after/backoff if supported |
| Many slow JDBC queries | Missing indexes, DB CPU/IO/locks, plan regression | Query plans, waits, DB metrics before resizing pool |
| Only a few pods failing | Different DNS/identity/secret/pool config, node egress | Compare runtime config, pod/node, and role |
| Whole app times out after scale-out | Total pools exceed DB session/capacity limits | Max replicas × max pool size, rollout surge |
| API times out while DB keeps writing | Caller deadline/cancellation did not cancel transaction in time | Timeout layering, idempotency, connection lifecycle |
| Java OOM/CPU spike | Many waiting threads, oversized ResultSets, large buffers | Heap/thread dumps, pool metrics, fetchSize, and query patterns |

Do not treat this table as a guaranteed diagnosis. A `Connection timeout` message may originate from **pool acquisition** or **network connect**; cross-check the exception class, stack trace, metrics, and emission point.

### 20.2. 10-Step Investigation Workflow

1. **Determine scope:** single endpoint, single replica, or whole cluster? When did it start?
2. **Classify exception:** `SQLException` SQLState/vendor code, Hikari timeout, or TLS/transport exception?
3. **Identify operation phase:** acquiring connection, executing SQL, transaction commit, or close?
4. **Inspect pool:** active, idle, pending, acquisition latency, leak warnings, physical connection creations.
5. **Inspect DB:** sessions, CPU/IO, deadlocks/locks, slow queries, failover/maintenance.
6. **Inspect network:** DNS, port, private endpoint/firewall, TLS certificate, egress from the exact pod/VM.
7. **Inspect authentication:** SQL credentials, Entra identity, token refresh, and DB principal grants.
8. **Correlate changes:** rollout, pool size, replica count, DB scaling, password rotation, migrations.
9. **Apply minimal remediation:** fix leak/query/credential/route or throttle concurrency with bounded retries.
10. **Verify and record:** test valid requests, error rejections, latency/pool recovery, and business consistency.

Never apply sweeping simultaneous changes such as "increase pool, add replicas, disable TLS, and open the firewall"; that is both dangerous and obscures which change had what effect.

### 20.3. When Pool Pending Rises While Database Is Not Overloaded

The pool size might be slightly too small, or a few transactions are holding connections too long. Sequence:

- Check whether `active` reaches `maximumPoolSize`.
- Inspect slow SQL and transaction durations, avoiding confusing HTTP waiting with DB usage time.
- Check for code leaks or unclosed streaming ResultSets.
- If the DB has headroom and load tests confirm throughput improves with more connections, consider a **bounded** pool increase.
- Recalculate total across all replicas after changing pool size to stay within the DB budget.

### 20.4. When DB Connections Are High While CPU Is Low

Many sessions may be idle, waiting on locks, waiting on network, or holding transactions without burning much CPU. Inspect **session states and waits** rather than assuming low CPU means the DB is unsaturated.

In PostgreSQL, `idle in transaction` deserves special attention because a session can hold locks/snapshots without running a query. In SQL Server, inspect sessions/requests and waits via permitted views/tools. In MySQL, inspect sessions/processlist/performance schema where permissions and features allow. Do not grant admin privileges to runtime just to query performance metadata.

## 21. Spring Retry, Resilience4j, and Transaction Boundaries

Spring applications often use Spring Retry, Resilience4j, or another resilience library. These tools are valuable, yet they can **misbehave if decorators are placed at the wrong layer**.

### 21.1. Retries Must Start a New Transaction

A pattern to avoid:

```text
@Transactional opens transaction
      |
      v
@Retryable repeats an SQL statement inside the old aborted transaction
      |
      v
Subsequent attempts fail or leave unwanted state
```

For serialization failures/deadlocks that rolled back, **each retry must run in a fresh transaction**. Design a **retrying orchestration service** that invokes a separate transactional service through a Spring proxy, or use `TransactionTemplate` per attempt. Verify actual proxy ordering, transaction propagation, and self-invocation behavior.

```text
HTTP/API layer
    |
    v
Retrying orchestration boundary
    |
    +-- Attempt 1 -> new DB transaction -> rollback on 40001
    |
    +-- backoff (without holding connection)
    |
    +-- Attempt 2 -> new DB transaction -> commit
    |
    v
Return response
```

**Never** call `Thread.sleep` inside a `@Transactional` holding a DB connection/locks. If a transactional service triggers external side effects, do not automatically retry the whole method with a decorator.

### 21.2. Retry at the Right Business Scope

| Operation | Safe to retry? | Condition |
|---|---|---|
| Short read-only `SELECT` | Usually yes | Deterministic query, no external state held, deadline remains |
| `UPDATE ... SET status='PAID'` | Possible if genuinely idempotent | Account for triggers, audits, side effects, and request ID |
| `INSERT` with unique idempotency key | Safe to reconcile/replay | Verify already-written row if commit outcome is unknown |
| Deducting balance via direct arithmetic | Do not blind retry | Requires ledger/transaction ID and unique constraint |
| Calling payment API inside DB transaction | Do not auto-retry full workflow | Needs provider idempotency and saga |
| Publishing to Service Bus after DB commit | Not atomic by default | Use outbox |

### 21.3. Circuit Breakers During Database Outages

If the DB is unreachable for several minutes, retrying every incoming HTTP request puts pressure on the connection pool and network. A circuit breaker enables **conditional fail-fast** when failure rates cross a threshold, followed by controlled recovery probing.

Key considerations:

- Apply circuit breakers only to dependency calls with clear failure classification.
- Do not mask programming bugs or business validation failures as "database unavailable."
- Do not keep the circuit open so long that the app stops testing recovery.
- Monitor `OPEN`/`HALF_OPEN`/`CLOSED` state transitions and post-failover success rates.
- Separate read-only endpoints and health endpoints by actual DB dependency.

A circuit breaker also does not replace idempotency. An HTTP caller may retry after receiving a 503; the backend must still check prior results via request key if a write may have completed.

## 22. JDBC and Reactive Programming

JDBC is a **blocking** API in standard usage. If a Java application uses Spring WebFlux/Project Reactor or a reactive pipeline, calling JDBC directly on an event-loop thread can cause widespread latency spikes because threads block waiting on I/O.

Options:

- Use **Spring MVC/virtual threads or a bounded thread pool** with JDBC where appropriate for the architecture, keeping total concurrency and pool capacity controlled.
- If a reactive framework must call JDBC, offload blocking work to a dedicated blocking-I/O scheduler with bounds and backpressure.
- Consider **R2DBC** if drivers, engines, and features fit and the team genuinely needs reactive database access; R2DBC is **not JDBC** and uses different drivers, pools, and configuration.

**Virtual threads do not make a database execute more queries.** They reduce the overhead of waiting threads, yet increase the number of requests waiting for connections unless paired with a semaphore or bounded concurrency. With large numbers of virtual threads, the Hikari pool remains the database access choke point.

### 22.1. N+1 Queries and Connection Hold Time

An HTTP request loading 100 orders where each order issues 5 separate queries can generate hundreds of SQL round-trips:

```text
SELECT orders ...          -> 1 query
for each order:
  SELECT items ...         -> 100 queries
```

This is the classic ORM **N+1 query problem**. Increasing pool size does not fix the root cause; fix fetching/query batching, indexes, and data access patterns. Measure queries per request and DB time with tracing before tuning the pool.

### 22.2. Cursors, fetchSize, and Streaming Large Datasets

If a query returns millions of rows, loading everything into memory can cause OOM or hold a connection too long. JDBC provides `fetchSize`/streaming mechanisms that vary by driver, engine, and transaction settings. In PostgreSQL, cursor-based fetching has specific autocommit and fetch-size requirements; in MySQL and SQL Server, streaming behaves differently.

Do not blindly copy `setFetchSize(500)` and assume low memory usage; verify driver/transaction behavior and release `ResultSet`/`Connection` according to their lifecycle.

## 23. Testing Failures and Recovery Before Production

You cannot validate retry logic simply by running a happy-path query. You need tests covering **positive, negative, and failure injection** cases in authorized environments.

### 23.1. Unit Tests

Without Azure:

- SQLState/vendor error classifier only retries allowlisted codes.
- Increasing backoff, max attempts, and deadlines; interruption is propagated cleanly.
- Connection is returned to the pool across success, `SQLException`, and `RuntimeException` paths.
- Serialization/deadlock retries the **entire transaction**.
- Query syntax errors/unique violations fail immediately or map to business conflicts.
- Errors during commit return an **unknown** status and require reconciliation.
- Database passwords/access tokens are never logged.

When mocking JDBC `Connection` and `SQLException`, also test failed `rollback()` calls so the code does not assume rollback succeeded and proceed to retry.

### 23.2. Integration Tests

Against an appropriate test database:

| Test | Simulation method | Expected outcome |
|---|---|---|
| Connection success | TLS + valid DB credential | Read query works, connection returns to pool |
| Wrong password/DB role | Invalid credential | Fail-fast, no retry storm |
| Network unavailable | Block connectivity in test environment | Bounded timeout, clear metrics/alerts |
| Pool exhausted | Hold all connections in a controlled test | Subsequent requests wait up to timeout, never hang forever |
| Deadlock/serialization failure | Two transactions contending on locks | Rollback + bounded new-transaction retry |
| Duplicate request | Send same idempotency key twice | Single logical DB effect |
| Commit ACK lost | Drop connection right after server commit in test | No duplicate record/business effect when caller retries |
| Failover | Trigger failover supported by service/lab | Pool evicts stale connections and self-recovers |
| Secret rotation | Rotate password/token per procedure | New connections use valid credentials |
| Token expiration | Test identity-based JDBC token refresh | New connections still authenticate after expiry |
| Autoscale burst | Scale replicas concurrently | Stays within connection budget/DB capacity |

**Never run unapproved failover or network-blocking tests against a production database.** Such tests can impact other clients and cause service outages.

### 23.3. Focusing on Uncertain-Commit Tests

A critical test:

1. Client sends request `Idempotency-Key=req-1042`.
2. Database commits the order and request record.
3. Simulate lost ACK before the client learns the outcome.
4. Client retries with the **same key**.
5. API retrieves the prior outcome or catches the unique conflict and returns the right response.
6. No second order is created and no duplicate side-effect event is emitted.

If exact ACK loss cannot be reproduced in a lab, at least write integration tests for **two competing concurrent requests** and **post-commit retries**; document test limitations instead of claiming exactly-once is proven.

### 23.4. Load Testing Pool Size

Run stepped load:

```text
Concurrent users: 10 -> 50 -> 100 -> 200
Pool max:          4 -> 8 -> 12 (tested individually)
Replicas:          2 -> 4 -> 8 (tested individually)
```

Measure throughput, p50/p95/p99 request latency, pool acquire p95, active/pending connections, DB CPU/IO, locks, deadlocks, and error rates. Choose a configuration that stays **stable at target load** rather than chasing peak throughput with severe tail latency.

### 23.5. Testing Scale-Down

When KEDA/HPA/Container Apps scales in, a process may be terminated mid-transaction. Verify graceful shutdown, connection closure, rollback of unfinished work, and retries from other callers/workers. Never let an app complete a received Service Bus message **before the DB commit succeeds**.

## 24. Cost and Pool Operations on Azure

A connection pool is not a separately billed Azure service, yet pool settings affect your **database compute tier**, app scaling behavior, and performance—carrying indirect cost impact.

| Component | Cost/risk | Optimization approach |
|---|---|---|
| Azure SQL/PostgreSQL/MySQL compute | CPU/RAM/IO per tier/vCore or service model | Optimize queries/indexes/transactions before scaling tier up |
| Database connections | Memory/session overhead and contention | Cap pool sizes, manage replicas, close properly |
| App compute | Threads, heap, wait time, autoscaling | Bounded concurrency, backpressure |
| Network | Private endpoints, NAT/Firewall, egress | Review topology and DNS |
| Logging/monitoring | Tracing/log ingestion, retention, alert evaluations | Metric sampling, log hygiene |
| Retry storms | Extra SQL attempts, DB CPU/locks, log volume | Error allowlists, backoff/jitter, circuit breakers |
| Database HA/replicas | Extra tier/replica/storage | Size according to RTO/RPO and actual read workload |

**Do not slash `connectionTimeout` or pool size purely for a prettier cost sheet** if SLOs fail. Equally, do not buy more database compute to mask N+1 queries, full-table scans, or long-held transaction locks.

### 24.1. An Indirect Cost Scenario

Suppose:

```text
10 API replicas × pool max 20 = 200 potential connections
Effective DB limit/capacity only fits ~100 sessions
Simultaneous retries during failover = 10 replicas × many requests
```

The app can trigger a connection storm, overload the database, spike error rates, cause the autoscaler to add more replicas, and worsen the feedback loop. A smaller pool, bounded concurrency, and classified retries can reduce both **errors and costs** without upgrading the DB tier.

### 24.2. Recording Baselines

Maintain a baseline table per environment:

```text
DB service / tier / region
Connection limit and reserve
JDK, JDBC driver, HikariCP version
maximumPoolSize × max replicas
Pool acquire p50/p95
SQL p50/p95
Error rate / SQLState distribution
Deadlocks / retry rate
DB CPU/IO/session count
RTO/RPO target and failover test record
```

Whenever scale or DB tier changes, update the baseline and re-run appropriate load tests.

## 25. Architecture Case Study: Orders API on AKS and Azure PostgreSQL

### 25.1. Requirements

An order management system has:

```text
AKS (production)
  |
  +-- orders-api: 6 replicas, HikariCP per JVM
  +-- orders-worker: 4 replicas, HikariCP per JVM
  +-- outbox-relay: 2 replicas, HikariCP per JVM
  |
  v
Azure Database for PostgreSQL Flexible Server
  |
  +-- orders
  +-- order_requests (unique request_id)
  +-- outbox_events
  +-- processed_messages
```

The API writes orders, the worker processes status changes, and the relay publishes events to Service Bus. The platform team wants:

- TLS with hostname verification over a private network.
- Separate principals for runtime and migrations, with no hard-coded secrets.
- Pools configured not to exceed the database connection budget.
- Bounded retries for deadlocks/serialization failures.
- No duplicate orders if a COMMIT ACK is lost.
- Visibility into pool acquisition and database load.

### 25.2. Connection Budgeting

Suppose a proposed setup:

| Workload | Max replicas | Max pool size | Potential connections |
|---|---:|---:|---:|
| `orders-api` | 10 | 8 | 80 |
| `orders-worker` | 6 | 4 | 24 |
| `outbox-relay` | 3 | 3 | 9 |
| **Total across three workloads** | | | **113** |

If the database only supports **100 effective connections** and needs headroom for monitoring/migrations, this configuration **fails the check**. You must lower pool/replica ceilings, split workloads, upgrade tiers, or improve throughput—never assume "each pod has under 10 connections so it's probably fine."

An initial test configuration:

```text
orders-api:      10 replicas × pool 4 = 40
orders-worker:    6 replicas × pool 3 = 18
outbox-relay:     3 replicas × pool 2 =  6
                                      ---
                                      64 connections
```

The remaining budget acts as reserve for migrations, admin, monitoring, deployment surges, and other clients. **This is not a final pool size recommendation**—validate against load tests and the real capacity of the chosen tier.

### 25.3. Order Processing Sequence

1. Client sends `POST /orders` with a stable idempotency key.
2. API borrows a connection from Hikari and opens a short transaction.
3. API inserts `orders`, `order_requests`, and `outbox_events` in the same transaction.
4. If the transaction hits deadlock/serialization failure and rolls back cleanly, retry the **entire transaction** per policy.
5. If a failure happens after sending COMMIT, return a reconciliation-needed state; retries with the same request ID will not create a duplicate order.
6. Outbox relay publishes the event with a deterministic event ID.
7. Worker receives the event, uses inbox/idempotency logic to update state, and commits the DB before acknowledging the Service Bus message.

### 25.4. During PostgreSQL Failover

Example incident:

```text
09:00:00  DB primary loses connectivity; pool holds 5 stale connections
09:00:02  Some requests report SQLState 08...
09:00:05  Pool evicts broken connections; DNS/DB not yet fully settled
09:00:15  DB accepts new connections; API gradually recovers
09:00:20  Outbox relay resumes publishing pending events
```

This is an **illustrative timeline**, not an Azure failover SLA. Transactions with uncertain outcomes are reconciled by request ID. Logs and metrics distinguish acquisition failures, login errors, deadlocks, and commit uncertainty.

### 25.5. Desired Outcomes

- No duplicate orders or double payments.
- Pool active/pending counts drop back down after DB recovery.
- Outbox backlog drains cleanly while preserving idempotency.
- Dashboards provide enough evidence to see the spike started at failover, not SQL syntax.
- No need to disable TLS or open public database access to recover.

## 26. Hands-On Exercises

### Exercise A – Configuring HikariCP

You have a Spring Boot API on App Service and Azure SQL Database. Maximum replicas is 8; the database has an effective limit of 100 connections, and other clients require 28 sessions.

**Tasks:**

1. Calculate the theoretical max pool size considering only replicas and reserve.
2. Write a `spring.datasource.hikari` configuration with reasonable `maximum-pool-size`, `connection-timeout`, and `max-lifetime` values for testing.
3. Explain why setting `maximumPoolSize=50` per replica is a bad idea.
4. List three metrics to monitor during a load test.

**Solution approach:** remaining budget `100 - 28 = 72`; dividing by 8 replicas gives **9 connections/replica** under a simplified model. That is only a theoretical ceiling; accounting for surge reserve and DB overhead, start lower and measure active/pending, query duration, and DB CPU/locks before deciding.

### Exercise B – Fixing a Connection Leak

A repository calls `dataSource.getConnection()` and returns early when no row is found without closing the connection. After a few thousand requests, the entire pool is busy.

**Tasks:** replace the code with `try-with-resources` and ensure `ResultSet`/`PreparedStatement`/`Connection` are closed on every branch, including exceptions. Describe how Hikari leak detection and pool metrics expose the problem.

**Solution approach:** see `loadStatusGood` in section 16. Exiting the scope returns the connection to the pool; if active count stays high afterward, check for long transactions and slow queries.

### Exercise C – Deadlock/Serialization Retries

Two requests update two accounts in opposite order, and one transaction receives `40001` or a vendor deadlock code.

**Tasks:**

1. Identify which transaction the DB rolled back.
2. Retry using a **new transaction**, not by repeating only the failed UPDATE statement.
3. Configure max attempts, jitter, and a deadline.
4. Add a stable transfer ID, unique constraint, and balance-total business invariant check.

**Solution approach:** an aborted transaction is recreated cleanly on retry; if attempts exceed the limit, return an appropriate error and emit a metric. Do not invoke a payment service inside a retried transaction if its side effects are not idempotent.

### Exercise D – COMMIT Without an ACK

Order `ORD-42` is inserted and committed by the server, but the response is lost and the client retries the POST.

**Tasks:** design an idempotency table, unique constraint, and logic to return the already-recorded result. Explain why retrying with a newly generated random order ID can create duplicate orders.

**Solution approach:** the same logical request must reuse the same `Idempotency-Key`; look up the previous result or handle the unique conflict per schema. Never conclude from a `SQLException` at commit time that the transaction definitely rolled back.

### Exercise E – Managed Identity Token Expiration

A Java app connects to Azure PostgreSQL using an Entra token and initializes `HikariDataSource` with that startup token as the password. Once the token expires, new connections can no longer authenticate.

**Tasks:** point out the design flaw and propose a solution that **refreshes the token when opening physical connections** using a supported driver/plugin/connection factory mechanism. Verify the DB principal's roles and JWT audience; never log tokens.

**Solution approach:** pooled connections do not automatically refresh a token frozen inside a password string. Use a driver- and database-supported token acquisition/refresh mechanism; test pool recycling and failover past token expiry.

### Exercise F – High DB CPU After Autoscale

AKS scales from 4 to 16 pods. Each pod keeps a max pool size of 20, raising the total connection ceiling from 80 to 320. DB CPU spikes to 95%, query p95 climbs, and retries start firing.

**Tasks:** propose adjustments to pool/replica ceilings, bounded concurrency, slow SQL/index optimization, and a load test to confirm. Explain why enlarging the pool makes things worse.

**Solution approach:** cap total connections within budget, examine query plans/locks/CPU, apply retry backoff, and avoid amplifying load via excess workers. Pool size must emerge from capacity testing rather than blindly multiplying per pod.

### Exercise G – Works Locally, Fails TLS in AKS Production

A developer connects cleanly from a laptop, while AKS receives `SSLHandshakeException`.

**Tasks:** inspect FQDN resolution, private DNS, container/JDK CA trust stores, certificate hostname matching, and driver TLS mode. State what workarounds to avoid.

**Solution approach:** verify network paths and cert chains directly from the pod; never set `trustServerCertificate=true` or `sslmode=disable` just to bypass errors, and do not open public access or disable hostname verification.

### Exercise H – Writing a Runbook

The SRE team receives sustained `Hikari pending > 0` alerts and rising connection acquire p95. Draft a runbook covering:

- Verifying actual replica counts and `maximumPoolSize`.
- Checking active/idle/pending counts, leak warnings, and DB sessions/CPU/locks.
- Classifying exception SQLState/vendor codes and operation phases.
- Correlating deployments/config changes/DB failovers/credential rotations.
- Choosing actions to shed load, fix leaks/slow queries, or tune pools safely.
- Verifying recovery and ensuring retries did not create duplicate side effects.

## 27. Self-Check Questions

**1. What is JDBC?** The standard Java API for accessing databases through an appropriate driver; `DataSource` provides `Connection` objects.

**2. What does `Connection.close()` typically do in Hikari?** Returns the connection to the pool for reuse rather than necessarily closing the TCP socket immediately.

**3. Why should a single Connection singleton not be shared across HTTP threads?** A Connection carries session/transaction state and is unsafe for concurrent multi-thread usage in that manner.

**4. Does a connection pool increase DB CPU capacity?** No. It optimizes reuse and bounds concurrency, without making the database itself faster.

**5. With 20 pods at max pool 10 each, what is the maximum connection count?** Roughly 200 connections from those pools alone, excluding other clients and rollout overlap.

**6. What does Hikari `connectionTimeout` measure?** Maximum time waiting to borrow a connection from the pool, not SQL query execution time.

**7. What flaw does `PreparedStatement` help prevent?** Reduces SQL injection risk in bindable positions, though input validation and object authorization are still required.

**8. Should `trustServerCertificate=true` be used to fix TLS errors in production?** No. Fix certificate trust, hostname, and networking properly.

**9. What does SQLState `40001` typically suggest?** Serialization/transaction rollback depending on the engine; you can retry the **entire new transaction** when safely rolled back.

**10. Is every `SQLException` retryable?** No. Authentication, syntax, permissions, constraints, and uncertain commit outcomes require different handling.

**11. Why not call `Thread.sleep` while a transaction is still open?** It holds connections and locks for too long, driving pool exhaustion and lock contention.

**12. Does a connection error during COMMIT mean the DB rolled back?** No. The commit outcome may be uncertain; idempotency keys and reconciliation are needed.

**13. What role does a unique constraint play in idempotency?** Prevents two concurrent transactions from inserting the same logical request record; a pre-check alone has a race condition.

**14. What problem does a transactional outbox solve?** Writes business rows and durable events in the same transaction, preventing lost events between DB commit and broker publishing.

**15. Does a managed identity with Azure RBAC Contributor on the DB resource automatically get SELECT rights?** No. Engine-appropriate DB principals and data permissions are required.

**16. Why can using an Entra token as a JDBC password at startup fail later?** Tokens expire; physical connections opened after expiration need a fresh token.

**17. When Hikari active count is high, should you enlarge the pool immediately?** No. First check leaks, long transactions, slow SQL, DB capacity, and total replica count.

**18. Why can placing `@Retryable` inside `@Transactional` be wrong?** It may retry inside an already aborted transaction; each retry requires a new transaction by design.

**19. Do virtual threads solve DB connection limits?** No. They do not increase database connection limits or backend capacity.

**20. Why might a read replica not show updates just written?** Replicas can lag; read-your-writes consistency must be designed intentionally.

## 28. Production Readiness Checklist

- [ ] Correct Azure SQL/PostgreSQL/MySQL engine and JDK-compatible JDBC driver identified.
- [ ] JDBC URL uses the official FQDN, right database/port, and TLS hostname verification.
- [ ] Private/public networking, DNS, routing, firewalls, and private endpoints verified from the actual runtime.
- [ ] No DB passwords, access tokens, or connection strings with secrets in Git, images, or logs.
- [ ] If using Entra/managed identity, DB principals/permissions and pool token refresh verified.
- [ ] Runtime identity holds minimal data privileges; migration/admin identity is separate.
- [ ] Each application instance reuses a shared DataSource/pool rather than creating pools per request.
- [ ] JDBC Connections, PreparedStatements, and ResultSets are closed cleanly across all branches.
- [ ] `maximumPoolSize`, `minimumIdle`, `connectionTimeout`, `validationTimeout`, and `maxLifetime` tuned appropriately.
- [ ] Total `max replicas × pools × max size` plus rollout surge fits within DB budget with reserve.
- [ ] Pool active/idle/pending, acquisition latency, creation time, and timeout counts measured.
- [ ] DB CPU/IO/connections/locks/deadlocks and slow SQL/query plans monitored.
- [ ] Retries restricted to classified transient/aborted errors with max attempts, jitter, and deadlines.
- [ ] Every transaction retry executes in a fresh transaction, with no sleeping inside transactions.
- [ ] Acquisition failures, query failures, deadlocks, and unknown commit outcomes handled distinctly.
- [ ] Order/payment writes and side-effect workflows enforce idempotency keys and unique constraints.
- [ ] Transactional outbox implemented wherever DB commits must reliably emit messages.
- [ ] Long-running external HTTP/API calls avoided inside DB transactions via decoupled workflows.
- [ ] App readiness/liveness and graceful shutdown designed for DB outages and scale-in events.
- [ ] Wrong credentials, TLS/DNS failures, pool exhaustion, failover, deadlocks, and token rotation tested.
- [ ] Duplicate/concurrent requests and missing COMMIT ACK scenarios tested in lab where feasible.
- [ ] Alerts and runbooks exist, sensitive data is excluded from logs, and capacity baselines are recorded.
- [ ] DB tier, replica, networking, monitoring, and retry-load costs evaluated.

## 29. Conclusion

**JDBC** lets Java interact with relational databases on Azure via the right driver and connection; **HikariCP connection pooling** enables connection reuse and limits concurrency; and **retries** help applications recover from transient faults such as deadlocks, serialization failures, or dropped connections. Yet all three only operate safely when paired with **TLS, proper authentication, clear transaction boundaries, pool capacity planning, budgeted timeouts, and end-to-end observability**.

The most important principle is **never retry a write operation merely because a SQLException occurred**. Know which phase failed, whether the transaction rolled back, and whether COMMIT's outcome is certain. For critical workflows, **idempotency keys, unique constraints, transactional outboxes, and outcome reconciliation** prevent duplicate side effects. Only when a Java application manages Connection lifecycles cleanly, caps total sessions across replicas, and tests failover/recovery can the system truly leverage managed Azure databases while maintaining production performance, consistency, and reliability.
