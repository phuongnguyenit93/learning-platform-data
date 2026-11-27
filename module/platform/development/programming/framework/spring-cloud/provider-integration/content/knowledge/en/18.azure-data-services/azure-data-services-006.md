# Connecting to Azure Database for MySQL or PostgreSQL via JDBC

Spring Boot can connect to **Azure Database for PostgreSQL Flexible Server** or **Azure Database for MySQL Flexible Server** via JDBC just like any standard relational database. The extra Azure-specific configuration concerns the FQDN endpoint, networking/firewall, TLS, Microsoft Entra identity, database-level permissions, high availability, and connection limits. Spring Cloud Azure provides JDBC starters to integrate Microsoft Entra passwordless authentication into `DataSource`; Spring Boot continues to manage `JdbcTemplate`, transactions, and the connection pool.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson focuses on Azure's two relational database services and how to connect to them from Java applications via JDBC.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish Azure Database for PostgreSQL Flexible Server and Azure Database for MySQL Flexible Server.
- Add the JDBC driver and Spring Cloud Azure JDBC starter using a compatible BOM.
- Configure `DataSource`, `JdbcTemplate`, HikariCP, and `@Transactional`.
- Connect using database username/password or Microsoft Entra passwordless authentication.
- Use Managed Identity and grant database permissions following least privilege.
- Configure TLS, FQDN, firewalls, VNet/private access, and diagnose network paths.
- Manage schema migrations, connection pools, timeouts, failover, and safe retries.
- Test with Testcontainers/local databases and an Azure test server.

## 2. Choosing the Right Relational Database Service

Both services are managed database engines, yet each retains the distinct characteristics of MySQL and PostgreSQL:

| Topic | Azure Database for PostgreSQL Flexible Server | Azure Database for MySQL Flexible Server |
| --- | --- | --- |
| Engine | PostgreSQL | MySQL |
| JDBC driver | PostgreSQL JDBC Driver (`org.postgresql:postgresql`) | MySQL Connector/J (`com.mysql:mysql-connector-j`) |
| JDBC URL | `jdbc:postgresql://...` | `jdbc:mysql://...` |
| FQDN | `<server>.postgres.database.azure.com` | `<server>.mysql.database.azure.com` |
| Default port | `5432` | `3306` |
| TLS | Required for service connections | TLS enabled/enforced by default |
| Microsoft Entra | Supported | Supported |
| Data permissions | PostgreSQL roles/users, schema/table/sequence privileges | MySQL users, database/table privileges |
| HA | Primary + standby, configurable per zone | Primary + standby, configurable per zone |

Choose the engine based on schemas, SQL dialect, extensions, workload, and operational expertise. Do not assume changing a JDBC URL is enough to switch between MySQL and PostgreSQL. Differences in data types, generated keys, JSON, collations, transaction isolation, SQL syntax, and migrations must still be handled.

### 2.1. Connection Architecture

~~~mermaid
flowchart LR
    A[Spring Boot application] --> D[Hikari DataSource]
    D --> J[JDBC driver]
    J --> T[TLS connection]
    T --> N[Azure network / DNS]
    N --> P[PostgreSQL Flexible Server]
    N --> M[MySQL Flexible Server]
    I[Microsoft Entra / Managed Identity] -. token .-> D
    K[Key Vault / secret provider] -. password if used .-> D
~~~

At runtime, `JdbcTemplate` borrows a connection from `DataSource`, executes SQL through the JDBC driver, and returns the connection to the pool. Applications should never open a new `DriverManager.getConnection(...)` per HTTP request. With Spring Boot, `DataSource` and HikariCP reuse connections, bound concurrent connections, and manage connection lifecycles.

## 3. Dependencies and Version Management

Spring Cloud Azure provides separate starters for PostgreSQL and MySQL:

- `com.azure.spring:spring-cloud-azure-starter-jdbc-postgresql`
- `com.azure.spring:spring-cloud-azure-starter-jdbc-mysql`

Both starters integrate Microsoft Entra passwordless authentication into Spring Boot JDBC. Pick **one** starter matching the engine your application uses. Add Spring Boot's JDBC starter and the corresponding driver; use the BOM to align Spring Cloud Azure dependencies.

Maven example for PostgreSQL:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-jdbc-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
    </dependency>
</dependencies>
~~~

For MySQL, swap the starter and JDBC driver:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-jdbc-mysql</artifactId>
</dependency>
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
</dependency>
~~~

Versions of Spring Boot, Spring Cloud Azure, and the JDBC driver must be compatible. Never copy an older driver version from a quickstart and mix it with a different BOM. Use the [Spring Cloud Azure version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) to select the BOM for your Spring Boot line. Azure JDBC starters have supported passwordless since Spring Cloud Azure 4.5.0+; verify the exact version in the version mapping.

## 4. Configuring PostgreSQL with JDBC

### 4.1. JDBC URL and TLS

The JDBC URL for PostgreSQL Flexible Server takes the form:

~~~text
jdbc:postgresql://<server>.postgres.database.azure.com:5432/<database>?sslmode=require
~~~

Basic configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
~~~

`sslmode=require` ensures the connection is encrypted with TLS. In production, configure certificate and hostname verification via `sslmode=verify-full` with appropriate trusted root CAs. PostgreSQL JDBC by default does not fully verify server identity when only encryption is enabled; TLS encryption and TLS identity verification are two distinct things.

Always use the Azure-provided FQDN, never a hard-coded IP. During failover, DNS can update the endpoint to point to the new primary. An application using an old IP may fail to reconnect.

### 4.2. Password Authentication

If using a local PostgreSQL account:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

The database user should be an application account without server administration privileges. Store the password in Azure Key Vault or your deployment environment's secret provider; inject it securely via environment/configuration. Never commit passwords into `application.yml`, Docker images, or source control. Design rotation so the connection pool is recreated or refreshed via a tested procedure.

### 4.3. Microsoft Entra Passwordless with Spring Cloud Azure

The PostgreSQL starter acquires Microsoft Entra tokens and passes them as credentials to the JDBC driver. Configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

When running on Azure with Managed Identity:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Declare only when using a user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
  datasource:
    url: jdbc:postgresql://${DB_SERVER}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

`DB_ENTRA_USERNAME` is the database principal name configured for the Microsoft Entra identity. Managed Identity only enables the workload to obtain tokens; it does not automatically create users in PostgreSQL or grant SELECT/INSERT/UPDATE permissions. You must configure a Microsoft Entra administrator on the server, create a database principal for the application's identity, and grant database/schema/table permissions.

Example permission flow:

1. Enable Microsoft Entra authentication on PostgreSQL Flexible Server and set an Entra administrator.
2. Assign the application's Managed Identity under the appropriate identity setup.
3. Have the Entra administrator create the corresponding database principal (e.g., via `pgaadauth_create_principal` per Microsoft docs).
4. Create a dedicated runtime role/privileges; grant access only to necessary databases/schemas/tables.
5. Configure `passwordless-enabled: true`, the principal username, and the TLS URL in the application.
6. Verify tokens are acquired from the intended identity and queries succeed only within granted permissions.

Example least-privilege SQL to adapt to your schema:

~~~sql
GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT USAGE ON SCHEMA public TO app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO app_runtime;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO app_runtime;
~~~

To ensure future tables/sequences also receive proper permissions, manage default privileges via migrations or a schema-admin role. Never use the Entra administrator account for application runtime connections.

## 5. Configuring MySQL with JDBC

### 5.1. JDBC URL and TLS

The JDBC URL for MySQL Flexible Server takes the form:

~~~text
jdbc:mysql://<server>.mysql.database.azure.com:3306/<database>?sslMode=REQUIRED&serverTimezone=UTC
~~~

Password configuration example:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
~~~

`sslMode=REQUIRED` enforces TLS encryption. In production, configure `sslMode=VERIFY_IDENTITY` with a trust store containing all trusted root CAs to verify certificates and hostnames. Never use `DISABLED` or turn off TLS to work around connection errors. `serverTimezone=UTC` aligns how the driver interprets timestamps; the application must still handle time zones explicitly in domain logic and database columns.

Azure Database for MySQL Flexible Server uses TLS 1.2 by default and supports TLS 1.3 depending on server version/configuration. Check server parameters, JDBC driver, and trust stores when upgrading.

### 5.2. Microsoft Entra Passwordless with Spring Cloud Azure

The MySQL starter uses `AzureMysqlAuthenticationPlugin` through Spring Cloud Azure integration. Basic configuration:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

When the application uses Managed Identity, configure the credential chain:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Declare only when using a user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
  datasource:
    url: jdbc:mysql://${DB_SERVER}.mysql.database.azure.com:3306/${DB_NAME}?sslMode=REQUIRED&serverTimezone=UTC
    username: ${DB_ENTRA_USERNAME}
    azure:
      passwordless-enabled: true
~~~

Creating Entra users and granting database permissions differs from PostgreSQL:

- Configure a Microsoft Entra administrator for MySQL Flexible Server.
- Configure Managed Identity and any required directory permissions per MySQL documentation if the server needs an identity to look up principals/groups.
- Create the Entra database user via the appropriate `CREATE AADUSER` mechanism.
- Grant permissions on the target database/tables to the runtime principal.
- Set the registered Entra username in JDBC configuration and enable `passwordless-enabled`.

Do not copy MySQL's `CREATE AADUSER` syntax into PostgreSQL; PostgreSQL uses its own principal creation and grant mechanisms. Likewise, do not mistake Azure Resource Manager Contributor for SQL data read/write permission.

## 6. Choosing Password or Microsoft Entra Authentication?

| Criterion | Database Username/Password | Microsoft Entra Passwordless |
| --- | --- | --- |
| Credential | Secret stored on database user | Token from Entra identity |
| Rotation | Application/operations must manage passwords | Short-lived tokens refreshed by credential integration |
| Workloads on Azure | Must retrieve secret securely | Fits Managed Identity well |
| Local development | Easy with test user | Can use Azure CLI/IDE credentials if configured |
| Database user/permissions | Still must create user and grant permissions | Still must create Entra database principal and grant permissions |
| Primary risks | Secret leaks, broken rotation, overly broad grants | Identity mapping, token acquisition, ungranted Entra/database principal |

Passwordless does not mean the database needs no username or no database permissions. It only changes how credentials are authenticated. For production workloads on Azure, prefer Managed Identity and least-privilege roles/database grants. If passwords are required, store them in Key Vault or a secret manager with a rotation process.

## 7. Spring Boot `DataSource`, `JdbcTemplate`, and Transactions

### 7.1. Using `JdbcTemplate` Instead of Managing Connections Manually

Spring Boot auto-configures `DataSource` from `spring.datasource.*`. With the JDBC starter, HikariCP is typically the default connection pool when on the classpath. `JdbcTemplate` borrows a connection, executes statements, and returns the connection to the pool:

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

public record Customer(
    UUID id,
    String email,
    String displayName
) {}

@Repository
public class CustomerRepository {
    private final JdbcTemplate jdbc;

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Customer findById(UUID id) {
        return jdbc.queryForObject(
            """
            SELECT id, email, display_name
            FROM customers
            WHERE id = ?
            """,
            (rs, rowNum) -> new Customer(
                rs.getObject("id", UUID.class),
                rs.getString("email"),
                rs.getString("display_name")),
            id);
    }

    public List<Customer> findByEmailDomain(String domain) {
        return jdbc.query(
            """
            SELECT id, email, display_name
            FROM customers
            WHERE email LIKE ?
            ORDER BY email
            """,
            (rs, rowNum) -> new Customer(
                rs.getObject("id", UUID.class),
                rs.getString("email"),
                rs.getString("display_name")),
            "%@" + domain);
    }

    public int updateDisplayName(UUID id, String displayName) {
        return jdbc.update(
            "UPDATE customers SET display_name = ? WHERE id = ?",
            displayName,
            id);
    }
}
~~~

`?` placeholders are bound via `PreparedStatement`, avoiding string concatenation in SQL. Handle `EmptyResultDataAccessException` or return a list/`Optional` when missing rows are expected. This example uses `UUID`, which fits PostgreSQL natively; if supporting MySQL, verify the column type and JDBC mapping (e.g., `BINARY(16)` or `CHAR(36)`) per your chosen schema.

### 7.2. Transactions Within a Single Relational Database

Spring manages JDBC transactions through the transaction manager bound to `DataSource`. Example:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository customers;
    private final AuditRepository audit;

    public CustomerService(
            CustomerRepository customers,
            AuditRepository audit) {
        this.customers = customers;
        this.audit = audit;
    }

    @Transactional
    public void changeDisplayName(
            UUID customerId, String newName) {
        customers.updateDisplayName(customerId, newName);
        audit.record("CUSTOMER_NAME_CHANGED", customerId.toString());
    }
}
~~~

Minimal audit repository example sharing the same `JdbcTemplate`/`DataSource`:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void record(String eventType, String aggregateId) {
        jdbc.update(
            "INSERT INTO audit_events(event_type, aggregate_id) VALUES (?, ?)",
            eventType,
            aggregateId);
    }
}
~~~

If both repositories share the same `DataSource` and transaction manager, their SQL statements commit/roll back together in one database transaction. `@Transactional` does not include Azure Blob Storage, Service Bus, or another database; external side effects outside JDBC require outbox/sagas when delivery guarantees are needed.

Never open connections with `DriverManager` inside repositories or hold connections across requests. With `JdbcTemplate`, Spring manages borrowing and returning connections. When using raw JDBC APIs directly, always use try-with-resources for `Connection`, `PreparedStatement`, and `ResultSet`.

## 8. HikariCP Connection Pool

Every physical JDBC connection consumes resources on both the application and the database server. HikariCP keeps a pool of open connections to reduce TLS/authentication/handshake overhead, but an oversized pool can overload the database.

Example:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
      keepalive-time: 300000
~~~

These values are starting baselines to measure, not universal defaults for every server. Size the pool based on:

- Number of concurrently running instances/pods.
- Requests actually holding connections simultaneously and query/transaction duration.
- Database tier connection limits and slots reserved for migrations/monitoring/admin.
- Network/firewall idle timeouts and environment connection limits.
- Read/write load, query duration, and failover behavior.

For example, if 6 pods each configure `maximum-pool-size=10`, the application can open up to 60 connections, before counting workers or migrations. Never look at pool size on a single pod alone; sum across the entire deployment and leave headroom for administration/replicas.

### 8.1. Connection Timeouts and Query Timeouts Are Different

- **Connection timeout** limits how long a caller waits to borrow a connection from the pool.
- **Login/socket timeout** limits how long opening a connection or waiting on network I/O takes.
- **Statement/query timeout** limits SQL execution duration.
- **Transaction timeout** limits the entire transaction if configured on Spring/transaction manager.

Raising one timeout does not fix another. For example, pool exhaustion caused by long-running transactions holding connections will not be solved by increasing socket timeout.

### 8.2. Preventing Connection Leaks and Pool Exhaustion

Monitor Hikari metrics: active, idle, pending, acquisition time, usage time, and timeout counts. If active stays pinned at maximum and pending climbs, check:

- Are transactions holding connections while calling HTTP/Blob/Service Bus?
- Are there slow queries or missing indexes?
- Does manual JDBC code forget to close `ResultSet`/`Statement`/`Connection`?
- Are batch jobs running with unbounded parallelism?
- Does the total pool size across all pods exceed database capacity?

Keep transactions short; never perform unrelated network calls while holding a database connection or row locks.

## 9. Networking and DNS

Azure Database for PostgreSQL Flexible Server and MySQL Flexible Server offer public access and private networking options per each service's model.

| Configuration | Characteristics | Best Fit |
| --- | --- | --- |
| Public access + firewall | Has public FQDN; only allowlisted IPs can connect | Dev/test or workloads with fixed egress IPs and policy approval |
| Private access / VNet integration | Database integrated into a private VNet/subnet with no public endpoint | Production workloads requiring network isolation |
| Private endpoint / Private Link | Private connectivity via an endpoint inside the VNet per service support | Architectures needing explicit private connectivity control |

Some networking choices are decided at server creation time or have transition constraints; check the specific service documentation before provisioning. Never open the firewall to the entire Internet to fix connection errors.

### 9.1. Ports and FQDNs

| Database | Sample FQDN | Port |
| --- | --- | ---: |
| PostgreSQL | `pg-orders.postgres.database.azure.com` | 5432 |
| MySQL | `mysql-orders.mysql.database.azure.com` | 3306 |

Always use the official FQDN rather than a static IP. DNS targets can change during failover or infrastructure updates. When using custom DNS, VNet peering, or hybrid networks, verify private DNS zones/links and name resolution from the application's actual subnet.

### 9.2. Layered Diagnostics

When an application fails to connect, check in order:

1. **DNS:** Does the FQDN resolve to the expected address from the pod/VM?
2. **Routing/network:** Do the subnet, NSG, route tables, firewall, and private endpoint allow TCP 5432/3306?
3. **Server firewall:** Is the egress IP in the allowlist when using public access?
4. **TLS:** Does the driver support the TLS version, certificate chain, and hostname verification?
5. **Authentication:** Are the username, password/token, Managed Identity, and Entra principal correct?
6. **Authorization:** Does the database user have required `CONNECT`/`USAGE`/`SELECT`/`INSERT`... privileges?
7. **Pool/engine:** Are connection slots available, or is the server failing over/restarting/under maintenance?

Do not jump to "firewall issue" solely from a `connection refused` message; inspect DNS, routing, TLS, and server state.

## 10. TLS and Certificate Validation

TLS protects data in transit between the application and the database. Both services enforce encrypted connections by default; never disable TLS in production.

| Driver | Minimum for Encryption | Server Verification Setting to Evaluate |
| --- | --- | --- |
| PostgreSQL JDBC | `sslmode=require` | `sslmode=verify-full` with trusted CAs and hostname verification |
| MySQL Connector/J | `sslMode=REQUIRED` | `sslMode=VERIFY_IDENTITY` with trusted CAs/system trust store |

`require`/`REQUIRED` ensures TLS encryption is active but does not necessarily enforce full hostname verification. With `verify-full`/`VERIFY_IDENTITY`, the driver validates both the certificate chain and server identity. Use a trust store containing the root CAs published by Azure; avoid pinning intermediate or leaf server certificates that can rotate.

Never set `trustServerCertificate=true`, `sslmode=disable`, or `sslMode=DISABLED` as a quick production workaround. If a handshake fails, inspect driver versions, JVM trust store, root CAs, and hostnames.

## 11. Database Users, Roles, and Least Privilege

Azure Resource Manager roles and database privileges are two separate layers:

- Azure RBAC governs Azure resources such as creating servers, changing configuration, or managing networking.
- Database authentication verifies the connecting principal.
- Database authorization determines which schemas/tables/sequences the principal can read or write.

Never grant subscription Contributor/Owner to an application just to execute SQL queries. Use a dedicated Entra principal or runtime database user; separate migration users with DDL privileges from runtime users needing only DML when appropriate.

### 11.1. PostgreSQL

PostgreSQL uses roles and privileges. A runtime user typically needs `CONNECT` on the database, `USAGE` on the schema, `SELECT`/`INSERT`/`UPDATE`/`DELETE` on relevant tables, and sequence privileges if the schema uses sequences. Privileges to create/alter tables belong to a migration identity.

### 11.2. MySQL

MySQL uses users and database/table grants. A runtime account only needs DML privileges on the application's database/schema; never put root/admin credentials in the connection string. MySQL's user/host syntax and privilege model differ from PostgreSQL.

Example with an existing local database user:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
    ON appdb.* TO 'app_runtime'@'%';
~~~

For Microsoft Entra users, create the principal via `CREATE AADUSER` and grant privileges to the exact registered username. Avoid `GRANT ALL PRIVILEGES` for runtime accounts if the application does not need DDL or administrative capabilities.

### 11.3. Migration Identity vs. Runtime Identity

Flyway/Liquibase may require `CREATE`/`ALTER`/`DROP` or permission to manage a history table; the runtime application usually does not need those privileges. You can run migrations in the deployment pipeline with a dedicated identity, then run the service with a restricted runtime principal. This limits blast radius if runtime credentials are compromised.

## 12. Schema Migrations and SQL Dialect Differences

Use Flyway or Liquibase for versioned schema management. Avoid relying on `spring.jpa.hibernate.ddl-auto=update` in production relational databases; with JDBC/`JdbcTemplate`, manage schemas explicitly via migration scripts.

Key differences to watch:

| Topic | PostgreSQL | MySQL |
| --- | --- | --- |
| Auto-generated ID | `GENERATED ... AS IDENTITY`, sequences | `AUTO_INCREMENT` |
| UUID | Native `uuid` type | Commonly stored as `BINARY(16)` or `CHAR(36)` |
| JSON | `json`, `jsonb` | `JSON` |
| Time zones | `timestamp with time zone` (`timestamptz`) stores UTC instants | `TIMESTAMP` converts by session time zone; `DATETIME` carries no time zone |
| Identifiers | Unquoted identifiers fold to lower-case | Depends on configuration/case sensitivity and filesystem for db/table names |
| Upsert | `INSERT ... ON CONFLICT` | `INSERT ... ON DUPLICATE KEY UPDATE` |
| Sequences | Dedicated sequence objects | `AUTO_INCREMENT` typically bound to a table |

Do not reuse one raw SQL migration script across both engines when syntax diverges. Separate migrations per engine or use Liquibase abstractions only where genuinely appropriate. Test migrations on the exact major version of the target server.

## 13. High Availability, Failover, and Retries

Flexible Server supports HA with a standby replica and automatic failover. When failover occurs, the database server endpoint remains the same FQDN used by the application; DNS/traffic shifts to the new primary per the service's architecture. Even so, **open JDBC connections can drop**. The application must replace broken connections from the pool and handle in-flight requests.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot / Hikari
    participant P as Current primary
    participant S as Standby
    A->>P: JDBC query / transaction
    P--xA: Connection lost during failover
    P--xS: Primary failure detected
    S->>S: Recovery / promotion
    Note over P,S: DNS or service routing switches to new primary
    A->>A: Discard broken connection
    A->>S: Reconnect through the same FQDN
    S-->>A: New connection ready
~~~

Never treat failover as completely seamless. Applications should:

- Use FQDNs instead of IPs.
- Configure reasonable pool timeouts and connection lifetimes.
- Handle connection reset/broken pipe/corresponding `SQLState` errors.
- Only retry idempotent operations or after confirming a transaction did not commit.
- Reconcile state when a commit response is lost; never blindly replay a payment or duplicate write.
- Actively test failover on a test server and observe reconnection time.

HA does not replace backups/PITR and does not protect against application bugs. Standby replicas are generally not read replicas for arbitrary read queries; if read scaling is needed, provision dedicated read replicas and manage consistency/read-after-write lag.

## 14. Timeouts, Retries, and Transactions

Set timeouts aligned with each use case's SLA:

- Connection acquisition timeout: waiting to borrow a connection from Hikari.
- Connect/socket timeout: opening a connection and waiting on I/O.
- Statement timeout: query execution limit.
- Transaction timeout: total transaction limit.

Never configure infinite timeouts. When retrying, classify errors:

| Error | Remediation |
| --- | --- |
| DNS/firewall/TLS/authentication failure | Do not retry indefinitely; fix configuration/identity/networking |
| Connection reset during a read query | Bounded retries may be safe if the read is pure |
| Deadlock/serialization failure | May retry the entire transaction if the business operation is idempotent and started fresh |
| Constraint violation | Treat as data/conflict error; do not retry blindly |
| Timeout during commit | Outcome is ambiguous; reconcile state via operation/business key before resending |
| Failover/temporary unavailable | Backoff with jitter, bounded total deadline and attempt count |

Retrying just a single statement mid-transaction can corrupt business logic. If the database aborts a transaction, roll back and start a fresh transaction. Never invoke HTTP/Blob/Service Bus while holding a long JDBC transaction; use an outbox to coordinate external side effects.

## 15. Observability and Operations

Monitor both the application side and the Azure database side:

| Layer | Metrics / Diagnostics |
| --- | --- |
| HikariCP | Active/idle/pending connections, acquisition/usage time, timeout count |
| JDBC | Query duration, `SQLState`, connection errors, transaction rollbacks, deadlocks |
| PostgreSQL | Active sessions, locks, slow queries, CPU, memory, storage, IOPS, connection count |
| MySQL | Active connections, slow queries, lock waits, CPU, storage, IOPS, connection count |
| Azure | Server health, HA state, failover events, CPU/storage/IO, connection metrics, maintenance |

Never log passwords, access tokens, JDBC URLs containing secrets, sensitive bind parameters, or personal data. Use correlation IDs/trace IDs to link requests to query logs and operations; omit raw SQL parameter values if they carry PII.

Health checks should distinguish:

- **Liveness:** the JVM/app process is alive.
- **Readiness:** the application can serve traffic; may check `DataSource` depending on requirements.
- **Database health:** database connectivity succeeds with a short timeout and minimal load.

Do not tie liveness directly to the database if a transient database outage would cause the orchestrator to crash-loop every pod. Readiness can mark an instance unready when the database is unavailable, according to your deployment policy.

## 16. Testing JDBC with Local Databases and Real Azure

### 16.1. Unit Tests

Mock repositories/DAOs or use an appropriate test slice to verify business rules. Unit tests require no Azure credentials or network connectivity.

### 16.2. Testcontainers

Testcontainers can launch PostgreSQL or MySQL containers to verify:

- JDBC mapping and `PreparedStatement` binding.
- SQL dialect and Flyway/Liquibase migrations.
- Transaction commit/rollback, constraints, and locking.
- Hikari `DataSource` lifecycle and repository behavior.

Local containers verify engine compatibility, not Azure Entra authentication, Managed Identity, private DNS, firewalls, TLS certificate chains, HA failover, or Azure server parameters.

### 16.3. Azure Integration Tests

Provision a dedicated test Flexible Server with a test database/schema and least-privilege identity. Verify:

1. JDBC connects via FQDN on the right port with TLS verification.
2. Public firewall/private networking permits only the required workload.
3. Password authentication or Microsoft Entra Managed Identity works.
4. The runtime principal has only needed privileges; attempt a forbidden action to verify least privilege.
5. Migrations run cleanly and the app can read/write.
6. Hikari pool behaves properly under concurrent load.
7. HA failover drops connections and the pool recovers without mis-replaying transactions.
8. Metrics/diagnostics are traceable without leaking secrets.

Never use production data or administrative identities in integration tests. Clean up test resources systematically and prevent test jobs from provisioning unbounded servers/databases.

## 17. Spring Boot Deployment Flow Example

~~~text
Build:
  - Choose PostgreSQL or MySQL driver
  - Import compatible Spring Cloud Azure BOM
  - Add the matching JDBC starter

Provision:
  - Create Flexible Server and database
  - Choose public firewall or private networking
  - Enable TLS and HA as required
  - Create Entra admin/database principal or local runtime user
  - Grant least-privilege database permissions

Deploy:
  - Assign Managed Identity to workload
  - Configure FQDN/database/username
  - Enable passwordless-enabled or fetch password from Key Vault
  - Configure Hikari pool and timeouts
  - Run Flyway/Liquibase migrations
  - Readiness checks and metrics

Operate:
  - Monitor pool/database/HA
  - Run periodic failover drills
  - Rotate identities/secrets per policy
  - Backup/PITR and restore drills
~~~

## 18. Common Errors

| Error | Cause | Remediation |
| --- | --- | --- |
| `Connection timed out` | Firewall, route, NSG, private DNS, or wrong port | Verify FQDN resolution, TCP 5432/3306, and network path |
| TLS handshake failure | Incompatible driver/JVM trust store, missing root CA | Update driver, CA chain, and TLS config |
| PostgreSQL/MySQL authentication failed | Username does not match principal, invalid password/token, or Entra user not created | Verify identity and database principal |
| Entra token acquired but query fails permission denied | Authentication succeeded without database grants | Grant least-privilege schema/table permissions |
| Hikari pool timeout | Exhausted pool, long transactions, slow queries, or undersized pool | Check active/pending counts, query durations, and pool sizing |
| Application fails to recover after failover | Static IP, stale connections, DNS caching, or flawed retries | Use FQDN, discard broken connections, reconnect, and test failover |
| Queries fail after migration | SQL dialect or major version mismatch | Split migrations per engine and test on exact version |
| Duplicate data after retry | Commit response lost and command replayed | Use business keys/idempotency and reconcile before retrying |
| App starts up while DB is unavailable | Connections only opened on first request | Add appropriate readiness/connection validation |

## 19. Practice Exercises

**Exercise 1 — Connecting to PostgreSQL.** Create an Azure Database for PostgreSQL Flexible Server, an `orders` database, and a dedicated runtime user. Configure Spring Boot `spring.datasource.url`, TLS, and Hikari; write a DAO using `JdbcTemplate` to insert and read an order.

**Exercise 2 — Connecting to MySQL.** Use MySQL Flexible Server and Connector/J. Configure the URL with FQDN, port 3306, TLS, and UTC. Run a migration to create tables and insert/update/delete rows with `JdbcTemplate`.

**Exercise 3 — Passwordless.** Enable Microsoft Entra authentication, assign a Managed Identity to the workload, create the database principal, and grant privileges. Configure the Spring Cloud Azure starter with `passwordless-enabled: true`; verify the application connects without a static password.

**Exercise 4 — Least privilege.** Create a runtime principal with only `SELECT`/`INSERT`/`UPDATE` on application tables. Attempt `CREATE TABLE` or `DROP TABLE` from the app and verify rejection; run migrations using a separate identity with DDL privileges.

**Exercise 5 — Hikari pool.** Run 5 simulated pods with pool size 10. Compute maximum total connections and compare against database limits. Measure pending connections, acquisition time, query latency, and the impact of shrinking/growing the pool.

**Exercise 6 — TLS/networking.** Test connecting with missing firewall rules, wrong DNS, missing root CA, and TLS verification enabled. Distinguish network errors from handshake errors and database authentication errors.

**Exercise 7 — Failover.** Enable HA on a test server and trigger a planned failover. Observe dropped connections, Hikari creating new connections, in-flight transactions, and request retries. Propose idempotency for writes with ambiguous outcomes.

**Exercise 8 — Multi-engine migrations.** Support one business schema on both PostgreSQL and MySQL. Split migrations for UUIDs/generated keys/JSON/time zones; run Testcontainers on both engines and compare results.

## 20. Key Takeaways

- **Azure Database for PostgreSQL/MySQL Flexible Server are managed relational databases.** Spring Boot connects via their respective JDBC drivers, `DataSource`, HikariCP, and `JdbcTemplate`.
- Use `spring-cloud-azure-starter-jdbc-postgresql` or `spring-cloud-azure-starter-jdbc-mysql` with a compatible BOM to integrate Microsoft Entra passwordless authentication.
- **Managed Identity provides identity/tokens only.** You still must create the database principal and grant least-privilege SQL permissions; Azure control-plane roles do not replace database grants.
- Always use **FQDN and TLS**. Production should verify CA/hostname (`verify-full` for PostgreSQL, `VERIFY_IDENTITY` for MySQL) rather than encrypting without server verification.
- Size HikariCP across total running instances and database limits. Long transactions, slow queries, and oversized pools can all exhaust connections.
- `@Transactional` protects a single relational `DataSource` transaction; it does not cover Blob, Service Bus, or another database.
- HA failover can drop open connections. Use FQDNs, reconnect, and retry boundedly; never blindly replay transactions with side effects.
- Testcontainers validates engine/JDBC/migrations; an Azure test server is required to verify Entra, Managed Identity, networking, TLS, quotas, and HA failover.

## 21. References

- [Spring Cloud Azure — PostgreSQL support and passwordless JDBC](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/postgresql-support)
- [Spring Cloud Azure — MySQL support and passwordless JDBC](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/mysql-support)
- [Spring Cloud Azure developer guide and version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Java JDBC quickstart — Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/connectivity/connect-java)
- [Java JDBC quickstart — Azure Database for MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/connect-java)
- [Microsoft Entra authentication — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-entra-configure)
- [Microsoft Entra authentication — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-how-to-entra)
- [TLS configuration — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect)
- [TLS configuration — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/security-tls)
- [Networking — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-networking)
- [Networking — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-networking)
- [High availability — PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability)
- [High availability — MySQL Flexible Server](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-high-availability)
