# Connecting to Cloud SQL with JDBC and Cloud SQL Connector

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to access storage, messaging, data, identity, and permissions. On Google Cloud, **Cloud SQL** provides managed relational databases for PostgreSQL, MySQL, and SQL Server. Java applications still use familiar JDBC and connection pools, but need to configure how workloads authenticate, network routing, and connection protection to the instance.

This lesson focuses on **JDBC + Cloud SQL Java Connector**. After this lesson, you will be able to:

1. Distinguish between Cloud SQL project, instance, database, database user, and instance connection name.
2. Connect Spring Boot using a JDBC URL and JDBC Socket Factory for PostgreSQL/MySQL.
3. Configure Application Default Credentials (ADC), IAM roles, and IAM database authentication.
4. Distinguish between Public IP, Private IP, and VPC networking requirements.
5. Compare Java Connector with Cloud SQL Auth Proxy.
6. Configure HikariCP, pool size, timeouts, transactions, and safe retries.
7. Test connectivity, permissions, HA/failover, and observe errors on Google Cloud.

> **Scope:** The main examples use PostgreSQL. Dependency/property names should be aligned with the Cloud SQL Java Connector version compatible with Spring Boot. The project ID, instance connection name, and database in this lesson are illustrative data.

## 1. Cloud SQL in Spring Boot Architecture

Cloud SQL is a managed relational database service. Google manages instance infrastructure, backups, patching, monitoring, and HA options; applications connect through familiar database protocols.

An instance can contain multiple databases, and each database has its own users/roles. It is important to distinguish:

| Component | Example | Meaning |
| --- | --- | --- |
| Google Cloud project | `rental-platform-dev` | Scope for resource management and IAM |
| Region | `asia-southeast1` | Region where the instance is located |
| Instance | `orders-db` | Cloud SQL resource |
| Instance connection name | `rental-platform-dev:asia-southeast1:orders-db` | Instance identifier used by connector/proxy |
| Database | `orders` | Database the application connects to |
| Database user | `orders_app` | Identity at the database layer |
| Workload identity | Service account of Cloud Run/GKE/Compute | Google Cloud identity of the application |

**The workload's IAM principal and the database user are two different identity layers.** A service account with permission to connect to Cloud SQL is not implicitly allowed to query every table; the database still checks the user, password or IAM database authentication, and SQL privileges.

~~~mermaid
flowchart LR
    APP["Spring Boot"] --> HIKARI["HikariCP / JDBC"]
    HIKARI --> CONN["Cloud SQL Java Connector"]
    CONN -->|"IAM + TLS"| SQL["Cloud SQL instance"]
    ID["Workload service account"] -->|"ADC"| CONN
    SQL --> DB["Database + DB roles"]
~~~

Java Connector helps authenticate the instance and establish an encrypted connection. The JDBC driver handles database communication; HikariCP manages the connection pool. The connector **does not replace the JDBC driver, database user, or transaction manager**.

## 2. Preparing the Instance and IAM

### 2.1. Required Information

Before configuring Spring Boot, identify:

- Database engine: PostgreSQL, MySQL, or SQL Server.
- Region and instance connection name.
- Database name and database user.
- Public IP, Private IP, or Private Service Connect according to the architecture.
- HA, backup, maintenance window, and connection limits.
- Database authentication mechanism: username/password or IAM database authentication.

Example instance connection name:

~~~text
rental-platform-dev:asia-southeast1:orders-db
└──── project ID ────┘└── region ──┘└instance┘
~~~

This is the **connection name**, not a JDBC hostname or database name.

### 2.2. Enabling the API and Granting Permissions

The project needs the Cloud SQL Admin API (`sqladmin.googleapis.com`) enabled.

The workload service account typically needs:

- **Cloud SQL Client** (`roles/cloudsql.client`): permission to establish connections to Cloud SQL.
- **Cloud SQL Instance User** (`roles/cloudsql.instanceUser`): required when using IAM database authentication to log in to the database as an IAM principal, in addition to Cloud SQL Client permission.

Grant only the necessary roles to the service account running the application. Do not assign project-wide Owner/Editor to fix connection errors.

For local development, developers can use ADC from a logged-in account granted appropriate permissions. For production, prefer a service account attached directly to Cloud Run, GKE Workload Identity, or Compute Engine; avoid placing service account JSON keys into containers or source code.

### 2.3. Database User vs. IAM Principal

With password-based database authentication:

- The application has a Google Cloud identity for the connector to verify connection permission.
- The application still provides a database username/password.
- The database user must be created in Cloud SQL and granted the necessary schema/table privileges.

With **IAM database authentication**, Cloud SQL allows an IAM identity to log in to the database according to the engine and instance configuration. You need to enable IAM database authentication, create an appropriate IAM user, and grant SQL privileges. Java Connector supports automatic token refresh when `enableIamAuth=true` is configured on supported drivers.

IAM database authentication **does not replace SQL privileges**. After authentication, the user can still only access the databases/schemas/tables permitted by database grants.

## 3. Cloud SQL Java Connector and JDBC Socket Factory

### 3.1. What Does the Connector Do?

Cloud SQL Java Connector is a library running inside the Java application that helps:

- Authenticate the workload with Google Cloud using ADC.
- Verify permission to connect to the instance.
- Establish a managed TLS connection.
- Refresh connection/metadata information according to the connector lifecycle.
- Select the appropriate IP type matching the instance configuration.

The connector is neither a database engine nor a connection pool.

| Component | Responsibility |
| --- | --- |
| PostgreSQL JDBC driver | Communicates via the PostgreSQL protocol and executes SQL statements |
| Cloud SQL Java Connector / Socket Factory | Authenticates the instance, handles TLS, and creates the connection path |
| HikariCP | Holds, allocates, and reclaims JDBC connections |
| Spring Data JPA/JdbcTemplate | Interacts with the database at the application layer |
| Google Cloud IAM | Authenticates and authorizes the workload to Cloud SQL |

### 3.2. PostgreSQL Dependencies

Maven example with PostgreSQL JDBC driver and Cloud SQL PostgreSQL Socket Factory:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.google.cloud.sql</groupId>
        <artifactId>postgres-socket-factory</artifactId>
        <version>${cloud-sql-java-connector.version}</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

`cloud-sql-java-connector.version` is a project property that needs to be declared according to a supported connector version. The Spring Boot BOM usually manages the PostgreSQL JDBC driver version; avoid overriding the driver/connector with incompatible versions.

If using JPA instead of JdbcTemplate, you can replace `spring-boot-starter-jdbc` with `spring-boot-starter-data-jpa`; the JDBC URL and connector principles remain the same.

### 3.3. PostgreSQL JDBC URL

Cloud SQL PostgreSQL Socket Factory is configured via the JDBC URL:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
~~~

Parameters:

- `jdbc:postgresql:///` uses a URL form without specifying a normal host; the socket factory identifies the instance via `cloudSqlInstance`.
- `cloudSqlInstance` has the format `project:region:instance`.
- `socketFactory` points to the PostgreSQL Socket Factory class in the dependency.
- `ipTypes=PRIVATE` instructs the connector to use the private connection path if the instance has a Private IP and the workload has a network route to the corresponding VPC.
- `DB_NAME`, `DB_USER`, `DB_PASS` are database credentials; they are not a Google Cloud service account.

If Public IP is needed, you can select `ipTypes=PUBLIC` or configure according to the IP types supported by the provider. Do not switch to PRIVATE merely by changing the JDBC URL if the workload does not yet have network connectivity to the VPC containing the instance.

### 3.4. Spring Boot Configuration with HikariCP

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&ipTypes=PRIVATE
    username: ${DB_USER}
    password: ${DB_PASS}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: orders-cloud-sql-pool
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

This is a starting configuration, not an optimal value for every instance. You must calculate the total connections across **all replicas**:

~~~text
Total maximum connections
  = number of application replicas × maximum-pool-size
    + migration jobs
    + worker/background jobs
    + admin/monitoring connections
~~~

For example, 6 replicas × 8 connections = 48 connections from the API, not counting jobs and operations. A pool that is too large can exceed Cloud SQL limits or overload the database; a pool that is too small causes requests to queue for a long time. Measure connection usage, query latency, and throughput under realistic load.

### 3.5. Using MySQL

For Cloud SQL MySQL, you need the MySQL JDBC driver and MySQL Socket Factory:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>com.google.cloud.sql</groupId>
    <artifactId>mysql-socket-factory</artifactId>
    <version>${cloud-sql-java-connector.version}</version>
</dependency>
~~~

Example URL:

~~~properties
spring.datasource.url=jdbc:mysql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.mysql.SocketFactory&ipTypes=PRIVATE
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
~~~

The Socket Factory names for PostgreSQL and MySQL are **different**. Do not copy the class name verbatim from one engine to the other. SQL Server has its own driver/socket factory and parameters; follow the corresponding instructions for the connector version.

## 4. Application Default Credentials and Workload Identity

### 4.1. How Does ADC Work?

Cloud SQL Java Connector obtains Google credentials through **Application Default Credentials (ADC)**. ADC discovers identity based on the execution environment:

- Local development: credentials generated via the Google Cloud CLI.
- Cloud Run: service account attached to the service.
- Compute Engine: service account attached to the VM.
- GKE: Workload Identity Federation for GKE binds the Kubernetes service account to a Google service account or appropriate principal.
- Environments outside Google Cloud: workload identity federation or an organization-approved credentials mechanism.

Do not put a service account JSON key into `application.yml`. Avoid storing key files in Docker images, Git, or temporary directories where they can easily be exposed.

### 4.2. Local Development with ADC

Developers can log in to ADC using the Google Cloud CLI:

~~~bash
gcloud auth application-default login
gcloud config set project rental-platform-dev
~~~

The first command creates credentials for local applications. The account needs appropriate IAM permissions on the project/instance. Setting the project in the gcloud CLI does not automatically grant permissions and does not guarantee ADC always uses that project in every configuration; verify the actual project and principal.

When running local integration tests, do not use a personal account with overly broad permissions if a test service account or dedicated principal can be used.

### 4.3. Workload Identity in Production

A good deployment configuration:

1. Create a dedicated service account for the `orders-api` service.
2. Grant `roles/cloudsql.client` on the project or instance within the allowed administrative scope.
3. If using IAM DB authentication, also grant the appropriate instance user permission and create the database IAM user.
4. Attach the service account to the Cloud Run/GKE/Compute workload.
5. Let ADC automatically retrieve credentials from the environment; do not mount a JSON key.
6. The database user is still granted only the required SQL privileges.

The IAM role grants permission to connect to Cloud SQL; SQL privileges determine which tables the application can SELECT/INSERT/UPDATE. Separating these two layers reduces the blast radius if the service account or application is compromised.

## 5. IAM Database Authentication

### 5.1. Distinguishing the Two Authentication Methods

| Method | Instance connection authentication | Database login |
| --- | --- | --- |
| Password-based DB auth | Connector uses ADC/IAM to authenticate to Cloud SQL | DB username + password |
| IAM DB authentication | Connector uses ADC/IAM; IAM auth mode enabled | IAM principal is mapped to a database user and tokens are issued automatically |

With IAM DB authentication, the instance needs the corresponding feature enabled and the IAM user must be created in Cloud SQL. Database user naming rules differ between PostgreSQL and MySQL; use the exact format specified by Cloud SQL for the engine.

### 5.2. Configuring Automatic IAM Auth

With PostgreSQL Socket Factory, you can add the parameter:

~~~properties
spring.datasource.url=jdbc:postgresql:///${DB_NAME}?cloudSqlInstance=${INSTANCE_CONNECTION_NAME}&socketFactory=com.google.cloud.sql.postgres.SocketFactory&enableIamAuth=true&ipTypes=PRIVATE
spring.datasource.username=${IAM_DB_USER}
~~~

When using `enableIamAuth=true`, the connector manages the IAM authentication token for the database using the supported mechanism. Do not configure a static database password in the same way as password-based authentication if the engine/connector is using IAM DB auth.

To work properly:

- The Cloud SQL instance must have IAM database authentication enabled.
- The workload principal needs permission to connect to Cloud SQL and the corresponding IAM DB authentication permission.
- The IAM database user must be created on the instance.
- The database user must have SQL privileges in the database.
- The connector, JDBC driver, and engine version must support the configuration in use.

**Do not confuse `roles/cloudsql.client` with IAM database login permission.** The two roles serve two different purposes.

### 5.3. When to Use Password vs. IAM DB Auth?

Password-based authentication is easy to integrate with existing applications, but requires storing secrets in Secret Manager or an approved secret management system, with rotation and no logging. IAM DB auth reduces the need to manage static passwords and fits workloads with clear IAM identities, but requires compatible instance, IAM principal, database user, and connector configuration.

Whichever approach you choose, the database still needs minimal roles/grants. Do not use a database owner/superuser account for the API runtime.

## 6. Public IP, Private IP, and VPC Networking

### 6.1. The Connector Protects Connections but Does Not Create Network Routes

Cloud SQL Java Connector supports authentication and TLS, but **does not automatically create network routes** from the application to the Private IP. If `ipTypes=PRIVATE` is selected, the workload must be able to reach the instance's private address through VPC/network configuration.

~~~mermaid
flowchart TD
    APP["Cloud Run / GKE / Compute"] --> CHOICE{"Select IP type"}
    CHOICE -->|"PUBLIC"| PUB["Cloud SQL Public IP"]
    CHOICE -->|"PRIVATE"| VPC["VPC network route"]
    VPC --> SQL["Cloud SQL Private IP"]
    PUB --> SQL
    IAM["ADC + Cloud SQL IAM"] --> CONN["Java Connector"]
    CONN --> SQL
~~~

### 6.2. Public IP

With Public IP, the connector can authenticate and establish TLS without manually managing SSL certificates. The connector does not require configuring authorized networks in the traditional direct-IP connection manner. However:

- The workload must still have outbound network access to the Cloud SQL endpoint.
- Environment egress/firewall/proxy rules may block the connection.
- Check organization policies, network zones, and compliance requirements.
- Do not turn the database into a public endpoint open to everyone; IAM and instance configuration still control access.

### 6.3. Private IP

Private IP is suitable when the database must only be accessed within a private network:

- The Cloud SQL instance is configured with a Private IP.
- The workload must have a network path to the corresponding VPC.
- Cloud Run needs Direct VPC egress or Serverless VPC Access configured according to the supported deployment model.
- GKE/Compute must reside in a network with appropriate routes and firewalls.
- Java Connector selects the private IP via the IP type configuration.

**Merely setting `ipTypes=PRIVATE` does not make Cloud Run automatically connect to the VPC.** If the route does not exist yet, the application will encounter timeouts or fail to connect even when the IAM role is correct.

### 6.4. Private Service Connect

Some architectures may use Private Service Connect to access Cloud SQL using a private endpoint model. PSC has its own DNS/network setup and instance connectivity model. The connector must be configured to match the IP/network choice; do not assume PSC is equivalent to Private Service Access. Follow the Cloud SQL deployment documentation for the specific environment.

## 7. Cloud SQL Java Connector vs. Cloud SQL Auth Proxy

Both help workloads connect to Cloud SQL without manually managing certificates/authorized networks in the legacy way, but their deployment models differ.

| Criterion | Java Connector | Cloud SQL Auth Proxy |
| --- | --- | --- |
| Execution location | Inside the Java process | Separate process/sidecar/container |
| Integration | JDBC Socket Factory | Exposes a local TCP or Unix socket |
| JDBC URL | Specifies `cloudSqlInstance` and `socketFactory` | Connects to `localhost:port` or socket |
| Credentials | ADC inside the application | ADC of the proxy process |
| TLS/auth | Managed by the connector | Managed by the proxy |
| Language dependency | Java/JDBC integration | Can be used across many application types |
| Operations | Dependency and configuration inside the app | Separate process/sidecar, health, and lifecycle management |

### 7.1. When to Choose Java Connector?

- A Java/Spring Boot application needs clean integration in the JDBC URL.
- You want to manage the connector alongside the application lifecycle.
- You want to use HikariCP/JPA/JdbcTemplate directly.
- The workload has ADC and a network path to the chosen IP type.

### 7.2. When to Choose Auth Proxy?

- Multiple languages or applications connect to Cloud SQL together.
- You want to decouple Cloud SQL connectivity from the application process.
- The deployment platform clearly supports sidecar/companion processes.
- You want the application to continue using a localhost JDBC URL while the proxy handles authentication/TLS.

There is no need to run **Java Connector and Auth Proxy stacked on top of each other** for the same connection. Choose one model, configure appropriate credentials/networking, and test the actual path.

### 7.3. JDBC Example When Using Auth Proxy

Suppose the proxy is running and listening on local TCP port `5432`:

~~~properties
spring.datasource.url=jdbc:postgresql://127.0.0.1:5432/${DB_NAME}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASS}
~~~

Here the JDBC driver connects to the proxy on localhost; the proxy forwards the connection to Cloud SQL. The application still needs a database username/password or IAM DB auth as supported by the proxy and engine. **Do not also configure the Java Connector Socket Factory in this URL** if the proxy is already acting as the connection layer.

## 8. HikariCP, Connection Pool, and Performance

### 8.1. The Connector Is Not a Connection Pool

Cloud SQL Java Connector creates a secure connection path, while each JDBC connection is still a database connection. HikariCP reuses connections to avoid creating a new connection for every HTTP request.

Let Spring manage the singleton datasource and pool according to the application lifecycle. Avoid manually opening connections without closing them, as that holds database slots until the pool is exhausted.

### 8.2. Estimating Pool Size

Suppose:

- 4 Spring Boot replicas.
- Each replica has `maximum-pool-size = 6`.
- 1 migration job can use at most 2 connections.
- A few connections are reserved for administration/monitoring.

~~~text
API pool = 4 × 6 = 24
Migration job = max 2
Expected application total = 26 + admin/monitoring
~~~

This number must be smaller than the instance's actual connection limit with headroom. Scaling replicas from 4 to 10 can multiply total connections by 2.5x even though each pod's configuration stays unchanged.

### 8.3. Timeouts and Lifetime

Hikari parameters commonly requiring consideration:

- `connection-timeout`: time to wait when borrowing a connection from the pool.
- `validation-timeout`: time to validate a connection.
- `idle-timeout`: duration after which an idle connection may be retired.
- `max-lifetime`: maximum lifetime of a connection before the pool replaces it.
- `keepalive-time`: can be used in some environments to keep idle connections from being closed by the network.

Do not set `max-lifetime` too low causing constant churn, or too high if the network/database has a shorter timeout. Check HikariCP documentation, Cloud SQL limits, and actual infrastructure configuration.

### 8.4. Query Latency and Pool Saturation

If requests are slow, do not assume Cloud SQL Connector is at fault. Check:

1. Time spent waiting to acquire a connection from HikariCP.
2. Time to establish a new connection.
3. Query execution time and lock waits.
4. Number of active/idle/pending connections.
5. Cloud SQL CPU, memory, storage IOPS, and connection count.
6. Network latency between the workload and the instance.

A full pool can be a symptom of slow queries or transactions holding connections too long, not necessarily a pool that is too small. Increasing the pool when the database is already overloaded can make the situation worse.

## 9. Transactions, Retries, and HA/Failover

### 9.1. Transaction Boundary

Spring Boot uses the JDBC/JPA transaction manager as normal:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderRepositoryService {
    private final JdbcTemplate jdbc;

    public OrderRepositoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(String orderId, long amount) {
        jdbc.update(
                "insert into orders(id, amount, status) values (?, ?, ?)",
                orderId, amount, "PENDING");

        jdbc.update(
                "insert into order_audit(order_id, action) values (?, ?)",
                orderId, "CREATED");
    }
}
~~~

The connector does not alter PostgreSQL/MySQL transaction semantics. Statements within the same transaction still adhere to the database engine's isolation level, locking, and commit/rollback behavior.

### 9.2. Retries Must Account for Idempotency

Network errors can occur while:

- Acquiring a connection from the pool.
- Executing a query.
- Committing a transaction.
- Cloud SQL failover or maintenance.
- Connector refreshing metadata/credentials.

If an error occurs **after the server has committed but before the client receives the response**, the client does not know whether the transaction succeeded. Blindly retrying an INSERT/charge/payment statement can create duplicates.

Safe design:

- Use idempotency keys/unique constraints for business operations.
- Retry at the transaction boundary with a bounded policy and backoff.
- Only retry clearly classified transient errors.
- Do not retry infinitely or retry every SQL exception.
- For money/order write operations, query the status by idempotency key before re-executing.

### 9.3. High Availability and Failover

Cloud SQL HA can fail over to a standby during an outage depending on instance configuration. The instance connection name typically remains the logical connection identifier, but open connections can be dropped during failover.

The application needs to:

- Let Hikari evict broken connections and create new ones.
- Have reasonable timeouts so requests do not wait indefinitely.
- Safely retry operations at the business layer.
- Monitor connection errors and recovery duration.
- Test failover in a test environment/appropriate maintenance window, without intentionally causing production outages.

Cloud SQL HA reduces downtime but **does not guarantee that every in-flight transaction will continue** or that clients will never receive an exception.

## 10. Schema Migration and Database Permissions

Use Flyway/Liquibase for versioned schema management. Do not run heavy DDL migrations on every replica at application startup if the deployment has multiple concurrent instances; use a dedicated migration job or deployment pipeline.

Separate database principals:

- `orders_migrator`: DDL privileges needed for migrations.
- `orders_app`: minimal DML privileges for runtime.
- `orders_readonly`: read-only if there are reporting use cases.

Basic PostgreSQL privilege grant example (adjust schema/role per environment):

~~~sql
CREATE ROLE orders_app LOGIN;
GRANT CONNECT ON DATABASE orders TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public TO orders_app;
GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA public TO orders_app;
~~~

This example does not configure passwords or default privileges for future tables; credentials must be managed via a secret manager and appropriate privileges granted for new objects. Do not use a superuser as the runtime account.

## 11. Testing Cloud SQL Connections

### 11.1. Unit Tests and Integration Tests

| Level | Objective | Limitations |
| --- | --- | --- |
| Unit test | Test service/repository logic with mocks or a local Testcontainers DB | Does not verify IAM, Connector, or Cloud SQL network |
| Local integration | Test JDBC driver, SQL schema, and transactions with local PostgreSQL/MySQL | Does not check Google Cloud permissions |
| Cloud integration | Test ADC, IAM, Java Connector, IP type, TLS, and DB user on a sandbox instance | Requires a test project/instance and cleanup |
| Resilience test | Test connection reset, controlled restart/failover, pool recovery | Do not run destructive tests on production |

### 11.2. Hands-on Scenario

1. Create a Cloud SQL PostgreSQL instance in a sandbox project.
2. Enable the Cloud SQL Admin API and note the instance connection name.
3. Create database `orders` and user `orders_app`.
4. Grant `roles/cloudsql.client` to the service account running the application.
5. If choosing Private IP, configure VPC connectivity for the workload before setting `ipTypes=PRIVATE`.
6. Add the PostgreSQL JDBC driver and PostgreSQL Socket Factory dependencies.
7. Configure the JDBC URL, ADC, database username/password, and a small Hikari pool.
8. Start Spring Boot, run a simple query, and execute a sample transaction.
9. Inspect logs/metrics for wrong instance name, missing IAM role, wrong DB password, missing network route, or missing SQL privileges.
10. Try IAM DB authentication in the sandbox if the engine/instance has it enabled and the IAM user is properly created.
11. Test the connection pool under concurrent load and compare active/idle/pending counts.
12. Perform an instance restart or failover in an allowed environment, verifying that the app recovers and write operations have idempotency.

### 11.3. Connection Check Example Using JdbcTemplate

~~~java
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class DatabaseHealthService {
    private final JdbcTemplate jdbc;

    public DatabaseHealthService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Map<String, Object> check() {
        return jdbc.queryForMap(
                "select current_database() as database_name, current_user as database_user");
    }
}
~~~

Health checks should not execute heavy queries or be called continuously at high frequency. You can distinguish between liveness and readiness: liveness checks whether the process is still alive; readiness checks whether it can serve requests requiring the database according to application policy.

## 12. Diagnosing Common Errors

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| `403 PERMISSION_DENIED` or connector not permitted to connect | Missing Cloud SQL Client role, API not enabled, ADC wrong principal | Check project, API, IAM bindings, and ADC credentials |
| `could not connect` / timeout with Private IP | Workload lacks VPC route or firewall blocks it | Check VPC egress, Direct VPC egress/connector, IP type, and route |
| Database authentication failed | Wrong DB user/password or IAM DB auth not configured | Check database user, secret, and `enableIamAuth` |
| `ClassNotFoundException` Socket Factory | Missing dependency or wrong class name for engine | Check `postgres-socket-factory`/`mysql-socket-factory` and URL |
| `No suitable driver` | Missing JDBC driver or wrong URL prefix | Check `org.postgresql.Driver`/MySQL driver and JDBC URL |
| Instance connection name invalid | Wrong project/region/instance or typo | Check identifier `project:region:instance` |
| Intermittent connection drops after idle | Network timeout, pool lifetime, or instance maintenance | Check Hikari lifetime/keepalive and connector logs |
| Hikari pool timeout | Pool exhausted, slow queries, transactions holding connections too long | Check active/pending, query latency, locks, and pool size |
| SQL query denied after successful connection | Missing database grants/schema privileges | Check SQL privileges; connection IAM does not grant table access |
| Errors after failover | Old connections dropped, incomplete transaction | Let pool evict broken connections, retry safely, and check state |

When investigating, log SQLState, error code, instance alias, request/correlation ID, and timestamp; do not log passwords, service account keys, tokens, or the full connection string containing secrets.

## 13. Comparison with RDS/Azure Database and Multi-Cloud Architecture

All cloud providers offer managed relational databases, though connection mechanisms and identities differ:

| Aspect | Google Cloud SQL | AWS RDS/Aurora | Azure Database |
| --- | --- | --- | --- |
| JDBC driver | PostgreSQL/MySQL/SQL Server JDBC | Engine-specific driver | Engine-specific driver |
| Managed connectivity | Cloud SQL Java Connector/Auth Proxy | RDS CA/TLS, IAM DB auth per engine, RDS Proxy | TLS, Azure identity/auth per service/engine |
| Workload identity | Google service account/ADC | IAM role | Managed identity/service principal |
| Private networking | VPC, Private IP, PSC per architecture | VPC/subnet/security group | VNet/private endpoint |
| Connection pooling | HikariCP or equivalent pool | HikariCP/RDS Proxy | HikariCP or equivalent proxy/service |
| Database authorization | DB user/roles or IAM DB auth | DB user/roles or IAM DB auth when supported | DB user/roles or Entra authentication when supported |

The business repository/service layer can share JDBC, Spring Data JPA, JdbcTemplate, and transaction abstractions. **Connection bootstrap, identity, network, secrets, failover, and proxy** parts require provider-specific adapters/configuration.

You should not build a multi-cloud JDBC URL by concatenating AWS, Google, and Azure parameters into the same string. Separate profiles/secrets/configurations by provider and use migrations/SQL queries compatible with the actual engine.

## 14. Practical Exercises

### Exercise A — Connect to Cloud SQL with Password Authentication

Create a sandbox Cloud SQL PostgreSQL instance, database `orders`, and a dedicated DB user. Add the JDBC driver and Cloud SQL PostgreSQL Socket Factory, configure ADC with `roles/cloudsql.client`, then run Spring Boot and query `select current_database()`.

### Exercise B — Choose Private IP

Configure Cloud SQL Private IP and a workload with VPC connectivity. Set `ipTypes=PRIVATE`, run the application, and verify the route. Try removing the VPC configuration in a test environment to observe the network error, then explain why the connector does not automatically create routes.

### Exercise C — IAM Database Authentication

Enable IAM database authentication on a test instance, create an IAM database user, and grant the appropriate role to the service account. Enable `enableIamAuth=true`, verify connectivity and SQL privileges. Distinguish between a connection IAM error and a database grant error.

### Exercise D — Compare Java Connector and Auth Proxy

Run the same application under two configurations: in-process JDBC Socket Factory and JDBC to localhost via Auth Proxy. Compare how credentials are provided, ports, logs, health checks, and sidecar operations.

### Exercise E — Calculate Connection Pool Size

With 8 replicas, up to 10 connections per replica, 2 workers, and 1 migration job, calculate the total maximum connections. Compare with the Cloud SQL limit and propose a pool size with headroom.

### Exercise F — Test Safe Retries

Create a write operation with an idempotency key. Simulate a connection drop around commit time and verify that retrying does not create duplicate records. Explain why you cannot blindly retry every exception.

### Self-Check Questions

1. What is the structure of an instance connection name and how does it differ from a database name?
2. Does Cloud SQL Java Connector replace the JDBC driver or HikariCP?
3. What does `roles/cloudsql.client` allow? Does it grant SELECT permission on tables?
4. Why are an IAM principal and a database user two different identities?
5. Which parameters does a PostgreSQL JDBC URL need to use Socket Factory?
6. Does `ipTypes=PRIVATE` automatically create a VPC network route for Cloud Run?
7. How do Java Connector and Cloud SQL Auth Proxy differ in execution location and how the application connects?
8. When are `roles/cloudsql.instanceUser` and `enableIamAuth=true` needed?
9. Why must connection pool size be calculated across the total number of replicas?
10. What can happen if a connection drops right after the database commits?
11. Why shouldn't every write operation be retried after a network error?
12. How should SQL privileges be granted to the runtime database user?
13. During Cloud SQL HA failover, are open connections guaranteed to be uninterrupted?
14. Which Spring Boot components can be shared across Cloud SQL, RDS, and Azure Database, and which components require separate configuration?

**Expected outcome:** learners can configure Spring Boot to connect to Cloud SQL using JDBC and Cloud SQL Java Connector, distinguish workload IAM from database privileges, choose Public/Private IP appropriately for the architecture, operate HikariCP sensibly, handle retries/failover safely, and evaluate how to integrate managed relational databases across cloud providers.
