# Connecting to RDS via JDBC and Managing Connection Pools

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services on AWS, Azure, and Google Cloud using the corresponding Spring Cloud libraries or SDKs. For relational data on AWS, **Amazon Relational Database Service (Amazon RDS)** handles most database engine administration such as PostgreSQL and MySQL; the Java application still communicates over **JDBC** just as with a standard relational database server.

A successful connection depends on more than a JDBC URL. The application must also configure VPC/security group networking, TLS, identity and secrets, connection lifecycles, transactions, and **connection pooling**. A pool that is too small makes requests wait; a pool that is too large can exhaust the database's `max_connections`, especially across multiple pods/instances. AWS offers **RDS Proxy** to manage and multiplex backend connections, though the proxy must still be sized alongside the application-side pool.

The running example is a reservation service:

- Table `reservation` stores bookings and their statuses.
- Table `property_inventory` tracks remaining available slots.
- When booking, the application updates inventory and inserts a reservation in a single SQL transaction.
- Spring Boot uses `JdbcTemplate` and a HikariCP-managed `DataSource` connecting to RDS PostgreSQL via an endpoint inside the VPC.

After this lesson, you will be able to:

1. Select the proper RDS endpoint, port, database name, JDBC driver, and network configuration.
2. Configure `spring-boot-starter-jdbc`, `JdbcTemplate`, and HikariCP in Spring Boot.
3. Calculate total potential connections across multiple application instances and size pools rationally.
4. Distinguish `connectionTimeout`, `maxLifetime`, `idleTimeout`, query timeout, and TCP connection establishment time.
5. Secure connections with TLS, Secrets Manager, or IAM database authentication; understand credential lifecycles inside a pool.
6. Use RDS Proxy, handle failovers and connection resets, monitor metrics, and write integration tests.

> **Scope:** RDS is an AWS-managed relational database service; JDBC and HikariCP live inside the Java application. Spring Cloud AWS can integrate with AWS services like Secrets Manager and Parameter Store, but JDBC connectivity to RDS primarily relies on the database driver, Spring Boot JDBC, and DataSource configuration. No separate "RDS JDBC starter" is required to use JDBC.

## 2. Connection Architecture from Spring Boot to RDS

### 2.1. Connection Flow

~~~mermaid
flowchart LR
    A["Spring Boot Service"] --> B["JdbcTemplate / JDBC"]
    B --> C["HikariCP DataSource<br/>application-side pool"]
    C --> D["RDS Proxy (optional)"]
    D --> E["Amazon RDS PostgreSQL/MySQL"]
    C -. "direct connection without Proxy" .-> E
    F["Secrets Manager / IAM DB Auth"] --> C
    G["VPC + Route + Security Group + TLS"] --- C
    G --- D
    G --- E
~~~

Each layer has a clear responsibility:

- **JDBC driver** translates JDBC calls into the wire protocol for PostgreSQL/MySQL.
- **HikariCP** retains and reuses physical connections, avoiding TCP/database session setup per request.
- **RDS Proxy** (if used) accepts client connections and manages/multiplexes connections to the database when workload patterns allow.
- **RDS** stores data and executes SQL/transactions.
- **IAM, Secrets Manager, and TLS** enforce identity, credentials, and transport security.
- **VPC/security groups** determine whether workloads can reach the RDS endpoint/port.

HikariCP and RDS Proxy sit on opposite ends of the connection path. HikariCP pools connections inside each JVM; RDS Proxy manages backend connections on the database side. Even with both, you must account for total client connections, pool sizing, transaction duration, and backend limits.

### 2.2. Choosing the Right Endpoint

RDS provides a DNS endpoint and engine-specific port. PostgreSQL defaults to port `5432`, MySQL to `3306`. JDBC URLs look like:

~~~text
jdbc:postgresql://<rds-endpoint>:5432/<database-name>
jdbc:mysql://<rds-endpoint>:3306/<database-name>
~~~

Never hardcode an IP address resolved from the endpoint. DNS endpoints let applications reconnect to the right target after infrastructure changes or failovers; instance IPs can change.

Distinguish endpoint types:

| Endpoint | Purpose | Things to note |
| --- | --- | --- |
| RDS DB instance endpoint | Connects to a DB instance | Use the instance/primary endpoint matching your topology |
| Read replica endpoint | Reads from a specific replica | Exhibits replication lag; not suited by default for read-after-write |
| Aurora cluster writer endpoint | Connects to the current writer | Use for writes and transactions requiring the writer |
| Aurora reader endpoint | Distributes read connections across readers | Does not replace the writer endpoint; may return lagged reads |
| RDS Proxy endpoint | Connects to the proxy | App still uses the engine's JDBC driver/SQL; proxy manages backend connections |

An RDS Multi-AZ DB instance standby and a read replica serve different purposes: a Multi-AZ standby provides availability/failover, not a default read-scaling endpoint. In Aurora, writer/reader endpoints belong to the cluster model. Always choose the endpoint matching your deployed RDS/Aurora topology.

## 3. Preparing JDBC Dependencies in Spring Boot

### 3.1. Maven for PostgreSQL

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot manages compatible versions through your project's dependency management/BOM. For MySQL, swap the driver to `com.mysql:mysql-connector-j` in `runtime` scope. Do not pull both drivers if the application uses only one engine.

`spring-boot-starter-jdbc` brings in Spring JDBC and HikariCP via Spring Boot defaults. Given a JDBC driver and `spring.datasource.*` properties, Boot auto-configures a `DataSource`, and `JdbcTemplate` is auto-configured on top of it.

To run the integration tests in Section 12, projects typically add `spring-boot-starter-test`, `org.testcontainers:postgresql`, and `org.testcontainers:junit-jupiter` in `test` scope. Align Testcontainers versions via your project's BOM or dependency management.

### 3.2. Configuring DataSource via Environment Variables

PostgreSQL RDS example:

~~~yaml
# application.yml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST}:${DB_PORT:5432}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: ReservationPool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 120000
~~~

The pool values above are **only a learning starting point**, not universal production sizing for every RDS instance. Replace them with measured values based on replica count, `max_connections`, query duration, and SLOs.

Never commit real passwords into configuration files in Git. `DB_HOST`, `DB_NAME`, `DB_USERNAME`, and `DB_PASSWORD` should come from deployment configuration or secret injection; Section 8 covers Secrets Manager and IAM database authentication.

### 3.3. Enabling TLS and Verifying the Server Certificate

Production connections should enforce TLS encryption and verify the server certificate. For PostgreSQL JDBC, configure a URL like:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST}:5432/${DB_NAME}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/global-bundle.pem
~~~

The CA bundle path is illustrative; ship the AWS-published CA bundle in your image/runtime with a certificate-rotation process. `verify-full` checks both the trust chain and that the hostname matches the certificate. Avoid `sslmode=disable` in production, and avoid encryption-only modes without server identity verification when security policies require full verification.

With MySQL Connector/J, the typical parameter is `sslMode=VERIFY_IDENTITY`; verify trust store/CA settings for your driver and engine version. PostgreSQL and MySQL URL parameters differ—never copy driver-specific parameters verbatim across engines.

## 4. AWS Networking: VPC, Subnets, and Security Groups

### 4.1. Ensure Network Connectivity Before Debugging JDBC

A private RDS connection typically requires:

1. RDS placed in a DB subnet group spanning your chosen subnets/VPC.
2. EC2/ECS/EKS or Spring Boot workload having routes to the RDS subnets, typically within the same VPC or via configured network peering/routing.
3. The RDS security group allowing **inbound** TCP from the application's security group on the database port (e.g., `5432`).
4. The application security group permitting appropriate egress, with no NACL, route table, or DNS rules blocking traffic.
5. The application resolving the DNS endpoint and connecting to the right hostname/port.
6. Valid TLS trust chain and hostname verification.

Never open the database port to `0.0.0.0/0` just to fix a connectivity error. Use private subnets and reference the **workload's source security group** in RDS inbound rules. Enable `Publicly accessible` only with explicit architectural justification and strict network controls.

### 4.2. Distinguishing Network Errors from Authentication Errors

| Symptom | Root cause category | What to check |
| --- | --- | --- |
| DNS lookup failed | Wrong endpoint, DNS/VPC resolver, or hostname config | Resolve the endpoint from the actual container/pod/EC2 instance |
| Connection timeout | Route, SG, NACL, port, endpoint, or RDS not ready | Test TCP reachability from a workload in the same network context |
| Connection refused | Wrong port, listener/instance not ready, or wrong proxy endpoint | Engine, port, and DB/proxy state |
| TLS handshake/certificate error | CA bundle, hostname, TLS version, or driver | CA bundle, `sslmode`, server cert, and driver version |
| Authentication failed | Username/password, secret rotation, or IAM DB auth | DB user, active credentials, and IAM auth config |
| Permission denied on SQL execution | DB user lacks schema/table/sequence grants | Database grants; IAM permissions do not grant SQL privileges |
| Hikari pool timeout | Pool exhausted, connections held too long, or DB refusing new sessions | Hikari active/idle/pending metrics and query/transaction durations |

Always test from the **actual workload environment**, because a developer laptop may reach RDS via VPN/bastion while a production pod lacks the proper route or security group. Never expose passwords on command lines or in logs while testing.

## 5. HikariCP: Application-Side Connection Pooling

### 5.1. Why Do We Need a Connection Pool?

Opening a new JDBC connection per HTTP request incurs TCP handshakes, TLS handshakes, authentication, and database session setup. HikariCP maintains a pool of open connections that requests borrow and return:

~~~mermaid
sequenceDiagram
    participant R1 as HTTP Request A
    participant R2 as HTTP Request B
    participant H as HikariCP
    participant DB as RDS PostgreSQL
    R1->>H: borrow connection
    H->>DB: reuse existing connection
    R2->>H: borrow another connection / wait
    H-->>R1: return connection
    R2->>H: receive newly freed connection
    H-->>R2: return connection
~~~

`DataSource` is the JDBC abstraction; HikariCP implements pooling for it. `JdbcTemplate` borrows a connection from `DataSource`, executes SQL, and closes the logical handle when done; HikariCP returns the physical connection to the pool instead of closing the socket immediately.

The pool is bounded: if every connection is busy running queries/transactions, incoming requests wait up to `connectionTimeout`. If waiting exceeds that limit, Hikari throws a connection acquisition error; growing the pool only helps when the database has spare capacity and the workload genuinely benefits from higher DB concurrency.

### 5.2. Key Configuration Parameters

| HikariCP property | Unit | Effect | Common mistake |
| --- | --- | --- | --- |
| `maximum-pool-size` | connections | Max total connections in pool (idle + in-use) | Raising it high without counting replicas and DB limits |
| `minimum-idle` | connections | Target idle connections the pool tries to maintain | Setting equal to max everywhere, holding excessive idle connections |
| `connection-timeout` | ms | Time caller waits to borrow a connection from pool | Confusing with query timeout or socket connect timeout |
| `validation-timeout` | ms | Max time to validate a connection's liveness | Setting >= `connectionTimeout` |
| `idle-timeout` | ms | Evicts idle connections when the pool can shrink | Has no shrinking effect when `minimumIdle == maximumPoolSize` |
| `max-lifetime` | ms | Max lifetime of a connection in the pool | Setting longer than DB/proxy/network connection lifetimes |
| `keepalive-time` | ms | Periodically tests/keeps idle connections alive | Setting too short, causing unnecessary traffic; must be < `maxLifetime` |
| `leak-detection-threshold` | ms | Logs warnings when a connection is held unusually long | Assuming Hikari automatically reclaims leaked connections |

Key rules:

- `connectionTimeout` bounds waiting for **an available pooled connection**, not how long SQL may run.
- `maxLifetime` should be shorter than any infrastructure/database/network idle or lifetime timeout so the pool retires connections proactively before the server/network drops them. Hikari never forcibly kills a connection currently borrowed by application code; retirement happens upon return.
- `idleTimeout` applies only when the pool can shrink below `maximumPoolSize`, i.e., when `minimumIdle` is lower than max.
- `keepaliveTime` applies to idle connections and does not replace query timeouts or OS TCP keepalives.
- With JDBC4 drivers implementing `Connection.isValid()`, manually setting `connectionTestQuery` is usually unnecessary.
- `leakDetectionThreshold` is a diagnostic warning tool, not a mechanism that closes held connections.

### 5.3. Do Not Confuse Timeout Types

| Timeout | Layer | Meaning |
| --- | --- | --- |
| Hikari `connectionTimeout` | Pool | Wait to acquire a connection from the pool |
| JDBC driver `connectTimeout` | Driver/network | Wait to establish the TCP/DB session |
| JDBC `socketTimeout` / network timeout | Driver/network | Wait for socket data; expiration may break the connection |
| JDBC `Statement.setQueryTimeout()` / Spring query timeout | SQL execution | Bounds statement execution duration per API/driver |
| Spring transaction timeout | Transaction | Bounds overall transaction duration per Spring/transaction manager |
| HTTP request timeout | API | Bounds total request duration from the caller's perspective |

Avoid setting every timeout to the same number. Layer them logically: the HTTP deadline should accommodate business steps, pool acquisition timeout should be smaller than the remaining deadline, query/transaction timeouts should bound SQL work, and driver connect/socket timeouts should prevent indefinite network hangs. A timeout at one layer does not automatically cancel work across all other layers.

## 6. Sizing Pools from Total Load, Not a Single JVM

### 6.1. Calculating Potential Total Connections

Each Spring Boot instance runs **its own pool**. With multiple pods/replicas, total connections scale linearly:

~~~text
Max total application connections
  = replica count × maximumPoolSize
    + worker/background pools
    + migration/admin/monitoring connections
~~~

Example:

| Component | Instances | Max pool per instance | Max connections |
| --- | ---: | ---: | ---: |
| Spring Boot API | 4 | 12 | 48 |
| Worker | 2 | 4 | 8 |
| Migration/admin/monitoring (reserve) | — | — | 10 |
| **Estimated total** | | | **66** |

If the engine only leaves 60 connections for application workloads after subtracting reserved/system connections, this setup is unsafe. You must shrink pools, scale database capacity appropriately, introduce a proxy, or adjust concurrency. Never treat `max_connections` as 100% available to the app, because the DB reserves slots for admin, monitoring, and failover tasks.

### 6.2. Larger Pools Do Not Equal Higher Throughput

A DB instance has finite CPU, memory, I/O, locks, and concurrent query capacity. Increasing a pool from 12 to 100 can:

- Increase DB session count and memory consumption.
- Cause more queries to contend simultaneously for CPU/I/O/locks.
- Increase queueing, context switching, and tail latency.
- Allow short traffic bursts to trigger unmanageable connection storms.

Choose pool sizes by benchmarking realistic workloads while observing query latency, active/idle/pending connections, and DB CPU/memory/IOPS. A small pool running fast, well-indexed queries often achieves higher throughput than a huge pool running long transactions.

### 6.3. Return Connections Promptly

Common causes of pool exhaustion:

- Forgetting to close `Connection`, `Statement`, or `ResultSet` when bypassing Spring abstractions.
- Opening a transaction and then calling HTTP/S3/SQS APIs or waiting on external I/O while holding a DB connection idle.
- Slow queries, missing indexes, or prolonged lock waits.
- Slowly streaming/consuming a `ResultSet` in the web layer while keeping the connection open.
- Spawning `@Async` tasks or new threads that mishandle transactions/contexts.
- Exception paths failing to close resources properly.

`JdbcTemplate` and `@Transactional` manage connection lifecycles automatically, provided transactions remain short. Never pass a raw JDBC `Connection` outside the repository or store it in shared fields.

## 7. RDS Proxy and Multi-Replica Applications

### 7.1. What Does the Proxy Solve?

Amazon RDS Proxy sits between your applications and RDS/Aurora. It maintains backend database connections and can **multiplex** many client sessions onto fewer backend connections when session state permits. This reduces connection-creation overhead, improves resilience during certain failovers, and centralizes backend connection lifecycle management.

RDS Proxy helps when:

- Serverless apps or rapidly scaling workloads open many concurrent connections.
- Many replicas maintain separate client pools against a database with tight connection limits.
- You want centralized auth/secret management and smoother connection recovery.

The proxy is not magic:

- Applications still need sensible client pools; never set Hikari max to unbounded.
- It does not eliminate DB CPU, I/O, lock contention, or slow queries.
- Active transactions typically hold a backend connection for the transaction's duration.
- Certain session states or stateful features trigger **connection pinning**, reducing multiplexing efficiency. Check RDS Proxy docs for your specific engine/driver.
- The proxy has its own cost and client/backend connection limits to monitor.

### 7.2. Connecting HikariCP Through RDS Proxy

Replace the host in the JDBC URL with the **RDS Proxy endpoint**; keep the engine's driver and database name:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${RDS_PROXY_ENDPOINT}:5432/${DB_NAME}?sslmode=verify-full&sslrootcert=/etc/ssl/certs/global-bundle.pem
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: ReservationViaProxy
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000
      max-lifetime: 1500000
~~~

These numbers are examples; base sizing on replica count and proxy/database metrics. Even with a proxy, `maximum-pool-size` still limits connections from **each JVM** to the proxy. The proxy manages backend connections—it does not replace HikariCP inside the application.

### 7.3. Session Pinning and Transactions

RDS Proxy may pin a client session to a backend connection when it detects session state or operations unsafe to multiplex. Long transactions, session-level parameter changes, temporary objects, or certain engine-specific features can prevent backend connection reuse. Exact behavior depends on the engine, driver, and features used; check proxy docs and metrics rather than assuming every SQL statement multiplexes.

Keep transactions short, avoid external service calls inside transactions, and minimize unnecessary session state. Monitor `DatabaseConnections`, `ClientConnections`, `DatabaseConnectionsBorrowLatency`, and other engine-specific proxy metrics.

## 8. Identity, Password Rotation, and IAM Database Authentication

### 8.1. Secrets Manager for Database Credentials

Database usernames/passwords can be stored in **AWS Secrets Manager** and delivered to the application at runtime via secret injection or SDK integration. Common patterns include:

- ECS task definitions referencing secrets to inject environment variables into containers.
- Kubernetes External Secrets/CSI or an organization-approved secret sync mechanism.
- AWSpring Secrets Manager/Parameter Store integration matching your version and supported properties.
- Application code fetching secrets via the AWS SDK using an IAM role, with caching/refresh and lifecycle controls.

Never write secrets into Git, Docker images, logs, or exception messages. Grant roles access only to the specific secrets needed, isolating secrets by environment and DB users by least privilege.

**Rotation affects pools:** HikariCP does not automatically notice when a password rotates in Secrets Manager. Existing authenticated connections can keep working, but newly opened connections must use the new credentials. If the app keeps supplying the old password, the pool can gradually drain as connections retire and fail to reopen. Implement credential refresh plus safe connection replacement/eviction, or use RDS Proxy with an appropriately configured secret model.

### 8.2. IAM Database Authentication

Certain RDS and Aurora engines/versions support IAM database authentication. Instead of storing a long-lived DB password on the client, the application generates a short-lived **authentication token** (**15-minute** lifetime) via the AWS SDK and passes it as the JDBC password. The token is signed for a specific Region, hostname, port, and database user, and requires TLS.

IAM DB authentication requires setup on both sides:

1. Enable IAM database authentication on the DB instance/cluster if supported by the engine.
2. Create the DB user and grant database privileges; for example, PostgreSQL requires configuring the role for IAM auth per engine docs.
3. Grant IAM permission `rds-db:connect` on the exact DB resource ID and DB username ARN.
4. Ensure the application has AWS credentials via an IAM role/provider chain to sign tokens.
5. Configure the JDBC connection to supply the token when opening physical connections and verify TLS per AWS guidelines.

Conceptual token generation example with AWS SDK v2:

Corresponding AWS SDK v2 dependency (version managed by the AWS SDK BOM):

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>rds</artifactId>
</dependency>
~~~

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;
import software.amazon.awssdk.services.rds.model.GenerateAuthenticationTokenRequest;

RdsUtilities utilities = RdsUtilities.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

String token = utilities.generateAuthenticationToken(
        GenerateAuthenticationTokenRequest.builder()
                .hostname(rdsEndpoint)
                .port(5432)
                .username(databaseUser)
                .build());
~~~

This snippet illustrates the token-generation API; add the AWS SDK v2 RDS dependency and load the endpoint/user from secure configuration. The token is used strictly for **authentication when opening a connection**; already-authenticated connections do not drop just because the token expires. However, new physical connections opened later by Hikari require a fresh token.

Because HikariCP normally reads a static password from configuration, never generate an IAM token once into `spring.datasource.password` and expect the pool to run forever. Use a DataSource/credential provider that mints a fresh token whenever a new physical connection opens, or use RDS Proxy with properly configured IAM/Secrets Manager authentication. Review engine and driver guidance before deploying.

### 8.3. Distinguishing IAM Permissions from SQL Privileges

IAM `rds-db:connect` allows an AWS identity to **authenticate** via IAM database authentication as the target DB user. It does not automatically grant `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on schemas/tables. SQL privileges must still be granted inside PostgreSQL/MySQL. Conversely, valid DB passwords do not bypass security groups, VPC routing, or TLS verification.

## 9. JDBC Transactions in Spring Boot

### 9.1. `JdbcTemplate` and `@Transactional`

`JdbcTemplate` borrows connections from `DataSource`, and Spring's transaction manager binds the connection to the active transaction scope. Repository example:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReservationJdbcRepository {
    private final JdbcTemplate jdbc;

    public ReservationJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int reserveInventory(
            String tenantId, String propertyId, int quantity) {
        return jdbc.update("""
                UPDATE property_inventory
                   SET available = available - ?
                 WHERE tenant_id = ?
                   AND property_id = ?
                   AND available >= ?
                """,
                quantity, tenantId, propertyId, quantity);
    }

    public int insertReservation(
            String tenantId, String reservationId,
            String propertyId, int quantity) {
        return jdbc.update("""
                INSERT INTO reservation
                    (tenant_id, reservation_id, property_id, guest_count, state)
                VALUES (?, ?, ?, ?, 'CONFIRMED')
                """,
                tenantId, reservationId, propertyId, quantity);
    }

    public int countByReservationId(String tenantId, String reservationId) {
        return jdbc.queryForObject("""
                SELECT COUNT(*)
                  FROM reservation
                 WHERE tenant_id = ? AND reservation_id = ?
                """,
                Integer.class, tenantId, reservationId);
    }

    public int availableForProperty(String tenantId, String propertyId) {
        return jdbc.queryForObject("""
                SELECT available
                  FROM property_inventory
                 WHERE tenant_id = ? AND property_id = ?
                """,
                Integer.class, tenantId, propertyId);
    }
}
~~~

Service example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {
    private final ReservationJdbcRepository repository;

    public ReservationService(ReservationJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void book(
            String tenantId, String reservationId,
            String propertyId, int guestCount) {
        int changed = repository.reserveInventory(
                tenantId, propertyId, guestCount);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Insufficient availability or inventory not found");
        }

        repository.insertReservation(
                tenantId, reservationId, propertyId, guestCount);
    }
}
~~~

If the insert fails (for instance, due to a unique constraint on reservation ID), the runtime exception causes Spring to roll back the transaction by default. Both SQL statements must run against **the same DataSource/transaction manager** and database to share the transaction. Always use `?` parameter placeholders—never concatenate user input into SQL strings.

This is a true relational database transaction, unlike DynamoDB transactions. If the service also calls S3, SQS, or HTTP APIs inside this method, external systems do not roll back alongside the JDBC transaction. Use an outbox/saga/compensation or explicit workflow instead.

### 9.2. Never Hold Connections While Calling External Systems

Avoid:

~~~text
@Transactional
  UPDATE inventory
  HTTP call to payment provider (waits 3 seconds)
  INSERT reservation
commit
~~~

While waiting on payment, the DB connection and transaction remain open, holding row locks and draining the Hikari pool. Instead, use a short transaction to record intent/pending state, call external systems after commit via workflow/outbox, and update final status idempotently based on the outcome.

By default, `@Transactional` rolls back on unchecked exceptions; if rollback is required for checked exceptions, declare `rollbackFor` explicitly. Also understand Spring proxy/self-invocation semantics: calling another `@Transactional` method on `this` bypasses the Spring proxy.

## 10. Read Replicas, Failover, and Connection Lifecycles

### 10.1. Read/Write Routing

With RDS read replicas or Aurora reader endpoints, workloads can split reads and writes:

- **Writes:** writer/primary endpoint.
- **Lag-tolerant read-only queries:** reader endpoint/replica.
- **Read-after-write or transactional reads:** read from the writer within the transaction or according to consistency requirements.

`@Transactional(readOnly = true)` does not automatically route JDBC connections to a read replica. Routing requires explicit DataSource/transaction routing configuration, ensuring the target datasource is chosen before the transaction starts and writes never hit a replica.

Replication lag means replica reads may miss recent writes on the writer. Never use a replica for immediate checks of recently mutated inventory or ownership when fresh state is required.

### 10.2. RDS Failover and Stale Connections

During RDS failover, restart, or maintenance:

- Existing TCP connections can drop or become stale.
- In-flight queries/transactions can fail; uncommitted transactions must be handled safely with idempotent business logic.
- DNS endpoints update to point to the new primary, yet JVM/driver/network caches and pools may retain stale connections briefly.
- Hikari evicts broken connections once detected; `maxLifetime`, validation, and application-level retries help the pool re-establish fresh connections.
- RDS Proxy can improve connection recovery time, though in-flight transactions can still abort.

Never cache endpoint IPs long-term and never assume failovers are completely transparent to every request. AWS Advanced JDBC Wrapper/failover-aware drivers can be an option for supported engines/topologies; verify compatibility, features, and versions before adopting.

### 10.3. Safe JDBC Transaction Retries

If a connection drops during commit, the client may not know whether the transaction committed. Retrying the entire operation with a fresh reservation ID can create duplicate bookings or double-decrement inventory. Use unique constraints/idempotency keys, reconcile by business key, and retry transactions only when outcome verification is in place. Do not retry every `SQLException` identically; distinguish deadlocks, serialization failures, connection resets, constraint violations, and bad data.

## 11. Monitoring the Pool and RDS

### 11.1. HikariCP Metrics

Spring Boot Actuator/Micrometer can expose Hikari metrics depending on dependencies and configuration:

| Metric (exact name varies by registry) | Meaning | Signal to investigate |
| --- | --- | --- |
| `hikaricp.connections.active` | Currently borrowed connections | Sustained near `max` |
| `hikaricp.connections.idle` | Idle connections | Persistently 0 while `pending` is high |
| `hikaricp.connections.pending` | Threads waiting for a connection | Rising steadily or exceeding thresholds |
| `hikaricp.connections.max` | Pool capacity | Compare against replica count and DB budget |
| `hikaricp.connections.acquire` / acquisition time | Connection borrow latency | Spiking p95/p99 |
| `hikaricp.connections.timeout` | Pool acquisition timeouts | Look for slow queries, leaks, or undersized pools |

Exact metric names depend on Spring Boot, Micrometer, and your metrics registry. Never expose URLs/passwords/secrets on dashboards. You may enable Actuator health/readiness checks for the DataSource, but avoid turning frequent liveness probes into heavy DB queries.

### 11.2. Amazon RDS and RDS Proxy Metrics

Monitor relevant CloudWatch metrics:

- `DatabaseConnections`, `CPUUtilization`, `FreeableMemory`, `FreeStorageSpace`, read/write latency, and IOPS.
- Deadlocks/locks, query performance, slow query logs/Performance Insights, or engine-specific observability tools.
- RDS Proxy: client connections, database connections, borrow latency, rejected connections, and pinning/target-health metrics where published.
- RDS maintenance, failover, reboot events, and DB/Proxy health statuses.

A pool timeout does not automatically mean the DB lacks connection slots. It could stem from slow queries holding connections, lock contention, transactions waiting on external APIs, or network drops. Correlate Hikari and RDS metrics on the same timeline.

## 12. Testing Connectivity and Pooling

### 12.1. Testing with PostgreSQL Testcontainers

An integration test with a PostgreSQL container validates the JDBC driver, schema, transactions, and repository SQL:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class ReservationJdbcIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("reservationdb")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired ReservationService service;
    @Autowired ReservationJdbcRepository repository;

    @Test
    void bookingUpdatesInventoryAndCreatesReservation() {
        // Schema/fixture data must be initialized via migrations or test SQL;
        // seed inventory for tenant-it/house-it with available = 3.
        service.book("tenant-it", "res-it-1", "house-it", 1);

        assertEquals(1, repository.countByReservationId("tenant-it", "res-it-1"));
        assertEquals(2, repository.availableForProperty("tenant-it", "house-it"));
    }
}
~~~

This example requires schemas/fixtures created via Flyway/Liquibase or test SQL, seeding inventory to `available = 3` before invoking the service. This is an illustrative test structure, not an already-executed project class. For transaction tests, verify **both reservation and inventory**, and add a failing-insert case to verify inventory rollback.

### 12.2. Testing the Hikari Pool

Scenarios to verify:

1. Pool respects configured max/min sizes and stays within the DB connection budget across scaled replicas.
2. Slow queries/transactions holding connections raise `pending` and trigger acquisition timeouts within API bounds.
3. Exceptions inside transactions roll back changes and return connections cleanly to the pool.
4. DB restart/failover breaks existing connections, and the pool opens fresh connections once the endpoint recovers.
5. Password rotation: new connections authenticate with updated credentials while old ones retire cleanly.
6. Misconfigured TLS hostname/CA verification fails fast rather than silently falling back to plaintext.
7. Lagged read-replica data is handled per contract and never used for mandatory read-after-write flows.

### 12.3. Limitations of Local Container Tests

PostgreSQL Testcontainers validates JDBC/PostgreSQL logic, **but does not fully simulate** RDS IAM authentication, Secrets Manager rotation, VPC security groups, RDS Proxy multiplexing, Multi-AZ failover, or CloudWatch. AWS-specific capabilities require integration testing on **staging RDS** within controlled quotas and budgets.

## 13. Common Errors and Diagnostics

| Symptom | Cause | Remediation |
| --- | --- | --- |
| `Connection timed out` | VPC route, security group, NACL, port, DNS | Test from the actual pod/EC2, check RDS SG inbound rules and endpoint |
| `password authentication failed` | Stale secret, wrong username/DB, unrefreshed rotation | Check secret version/current user and refresh mechanism |
| `PKIX path building failed` / SSL error | Wrong CA bundle or trust store | Update RDS CA bundle and verify hostname checking |
| `Connection is not available, request timed out` | Hikari pool exhausted or leaked connections | Inspect active/idle/pending metrics, query/tx duration, and leaks |
| `too many connections` | Sum of replica pools exceeds DB budget or other clients exist | Recalculate total connections, consider RDS Proxy, shrink pools/replicas |
| Slow queries while pool still has idle slots | SQL/index/lock/I/O bottleneck | Analyze query plans, locks, Performance Insights, and RDS metrics |
| Requests fail after failover | Old TCP connections dropped, in-flight transactions aborted | Let pool replace connections, apply idempotent retries, check DNS |
| Rising Proxy borrow latency | Backend connection shortage, session pinning, or DB overload | Monitor proxy metrics, shorten transactions, audit session state |
| App starts cleanly but queries fail | Wrong JDBC URL/driver/DB/schema/SQL privileges | Test real connection target and SQL user grants |

## 14. Self-Practice Exercises

1. Configure Spring Boot to connect to RDS PostgreSQL using a JDBC URL, environment variables, and TLS `verify-full`; verify connectivity from a workload inside the VPC.
2. Run four replicas, each with Hikari `maximum-pool-size=20`. Compute maximum potential connections and propose a pool size fitting your DB's actual `max_connections` while reserving headroom for migrations/admin.
3. Build a `@Transactional` booking endpoint: update inventory with `available >= quantity`, then insert the reservation; induce a unique constraint failure and verify rollback.
4. Lower `maximum-pool-size`, apply concurrent load, and observe `pending`, acquisition latency, and timeouts. Vary query duration to observe pool impact.
5. Switch the JDBC URL from the RDS endpoint to an RDS Proxy endpoint; compare `ClientConnections`, `DatabaseConnections`, and borrow latency.
6. Perform password rotation in Secrets Manager in a test environment; verify the application opens new connections and the pool retires old ones.
7. Explore IAM DB authentication for PostgreSQL or MySQL: enable the feature, configure the DB user, `rds-db:connect` policy, 15-minute tokens, and token refresh for new connections.
8. Simulate failover/restart on staging RDS; observe failed connections, aborted transactions, and idempotent retry behavior using a fixed reservation ID.
9. Compare RDS JDBC pooling against connecting to Azure Database for PostgreSQL/MySQL and Google Cloud SQL; identify which Spring `DataSource` concepts remain shared and which endpoint/auth/proxy details are provider-specific.

**Completion criteria:** learners can trace the JDBC path from Spring Boot to RDS, size HikariCP pools rationally, calculate total connections across replicas, secure credentials/TLS, handle failovers, and prove atomic rollback via integration tests.

## References

- [Amazon RDS — Connecting to a DB instance](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.Connect.html): endpoints, ports, networking, and client connections.
- [Amazon RDS — Security with VPC](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.RDSSecurityGroups.html): security groups and network access.
- [Amazon RDS — SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html): CA bundles and engine-specific TLS.
- [Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html): connection pooling, multiplexing, authentication, and failover.
- [Amazon RDS — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html): IAM tokens, DB users, and policies.
- [Amazon RDS — Managing credentials with Secrets Manager](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html): storing and rotating database credentials.
- [Amazon RDS — Working with parameter groups](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithParamGroups.html): engine parameters such as `max_connections`.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC, pooling, and auto-configuration.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): meaning of pool properties.
- [AWS SDK for Java 2.x — Generate an IAM authentication token](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-rds.html): generating IAM tokens with the SDK.
