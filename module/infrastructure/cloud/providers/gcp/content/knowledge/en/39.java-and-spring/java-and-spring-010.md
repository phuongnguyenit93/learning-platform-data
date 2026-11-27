# JDBC, R2DBC, and the Cloud SQL Java Connector

Java and Spring applications frequently store business data in PostgreSQL or MySQL. When deployed on Google Cloud, Cloud SQL provides managed relational databases, while the application must choose an appropriate access model: **JDBC** for synchronous workflows, **R2DBC** for reactive pipelines, and the **Cloud SQL Java Connector** to establish connections to Cloud SQL with Google Cloud authentication and secure encryption.

This lesson belongs to the **Java and Spring on GCP** chapter of the **CLOUD_PROVIDERS_GCP** module. Within the module scope—spanning projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases—understanding Cloud SQL connectivity helps teams select services, secure resources, deploy with control, and monitor reliability and cost.

After this lesson, you will be able to:

- Distinguish JDBC, R2DBC, database drivers, connection pools, and the Cloud SQL Java Connector.
- Choose synchronous or reactive models based on actual Spring processing flows.
- Connect to Cloud SQL for PostgreSQL via JDBC/HikariCP or R2DBC/ConnectionPool.
- Configure Application Default Credentials (ADC), Cloud SQL IAM, and IAM database authentication.
- Understand why the connector does not automatically create network paths to private IPs.
- Size connection pools properly when Cloud Run or GKE scales instance counts.
- Diagnose connection errors, permission errors, pool exhaustion, and query latency.

## 1. JDBC, R2DBC, and the Connector Solve Three Different Problems

These three components often appear side by side, yet they do not replace each other's roles:

| Component | Question it answers | How it works |
|---|---|---|
| JDBC | How does Java execute SQL? | Blocking API for connecting and running queries |
| R2DBC | How does Java process SQL in reactive streams? | Asynchronous, non-blocking database API interacting with Publishers |
| Cloud SQL Java Connector | How does the app authenticate and build a secure path to Cloud SQL? | Fetches metadata, authenticates via Google Cloud IAM, manages TLS, and supports IAM database authentication |
| JDBC/R2DBC database driver | How does Java speak the PostgreSQL, MySQL, or SQL Server protocol? | Implements the wire protocol and maps Java APIs to the database |
| Connection pool | How are connections reused, capped, and shielded from reopen overhead? | Keeps open connections ready and hands them out to requests |

~~~mermaid
flowchart LR
    APP["Spring service"]
    APP --> J["JDBC<br/>JdbcTemplate / JPA"]
    APP --> R["R2DBC<br/>DatabaseClient / repositories"]
    J --> H["HikariCP / JDBC DataSource"]
    R --> RP["R2DBC ConnectionPool"]
    H --> JC["Cloud SQL Java Connector<br/>JDBC socket factory"]
    RP --> RC["Cloud SQL Java Connector<br/>R2DBC provider"]
    JC --> NET["Existing network path<br/>public / private / PSC"]
    RC --> NET
    NET --> SQL["Cloud SQL PostgreSQL / MySQL"]
~~~

JDBC and R2DBC govern how the application handles database I/O. The connector handles Cloud SQL-specific connectivity and authentication. You can use JDBC/R2DBC without the connector when connecting directly via IP/host using alternative auth and TLS mechanisms. Conversely, adding the connector does not magically turn JDBC into non-blocking I/O or turn R2DBC into JPA.

### When to Choose JDBC?

Choose JDBC when the application uses Spring MVC, `JdbcTemplate`, Spring Data JDBC, or Hibernate/JPA; business logic relies on traditional transactions; and mature ecosystem libraries are used. Blocking JDBC is not automatically a problem in every app: with a well-sized connection pool and bounded requests/threads, it is often the simplest, most observable choice.

### When to Choose R2DBC?

Choose R2DBC when the entire application pipeline is genuinely reactive: Spring WebFlux, Project Reactor, non-blocking downstreams, and high I/O concurrency demands without tying up one thread per waiting operation. R2DBC does not make SQL execute faster by itself; if queries are slow due to locking or missing indexes, changing the driver API will not fix them.

Never call blocking JDBC directly on the WebFlux event loop; doing so can stall the event loop. If JDBC is required inside a reactive system, isolate it onto an appropriate scheduler or reconsider architectural consistency. R2DBC is not a drop-in replacement for JPA/Hibernate: entity lifecycles, lazy loading, and transaction semantics must be redesigned.

## 2. JDBC: Synchronous API and Usage Principles

JDBC comprises `DriverManager`/`DataSource`, `Connection`, `PreparedStatement`, and `ResultSet`. Database operations normally block the calling thread until results return or a timeout triggers. Spring Boot typically pairs `DataSource` with HikariCP and uses `JdbcTemplate` or JPA in the repository layer.

Java example reading an order's status with `PreparedStatement`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderStatusRepository {
    private final DataSource dataSource;

    public OrderStatusRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findStatus(long orderId) throws SQLException {
        String sql = "SELECT status FROM orders WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);

            try (ResultSet rs = statement.executeQuery()) {
                return rs.next() ? rs.getString("status") : null;
            }
        }
    }
}
~~~

Key principles:

- Always use `PreparedStatement` with parameter binding; never concatenate input strings into SQL.
- Use `try-with-resources` to return `Connection` objects to the pool promptly.
- Never store a `Connection` in a singleton or HTTP session.
- Multi-statement transactions must commit or roll back properly; in Spring, prefer `@Transactional` with the matching transaction manager.
- Configure wait timeouts so a database outage cannot hang request threads indefinitely.

## 3. R2DBC: Database Access via Reactive Streams

R2DBC (Reactive Relational Database Connectivity) defines `ConnectionFactory`, `Connection`, `Statement`, and `Result` following Reactive Streams. Instead of returning a value immediately or blocking a thread, APIs return a `Publisher`; applications typically work with Project Reactor's `Mono` and `Flux`.

Example repository using Spring `DatabaseClient`:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public final class ReactiveOrderRepository {
    private final DatabaseClient client;

    public ReactiveOrderRepository(DatabaseClient client) {
        this.client = client;
    }

    public Mono<String> findStatus(long orderId) {
        return client.sql("SELECT status FROM orders WHERE id = :id")
                .bind("id", orderId)
                .map((row, metadata) -> row.get("status", String.class))
                .one();
    }
}
~~~

From a caller's perspective, `Mono` represents an async result of zero or one element; `Flux` represents multiple elements. Execution only runs when subscribed to properly.

Important constraints:

- Avoid calling `block()`, `Thread.sleep`, or blocking JDBC on reactive paths.
- R2DBC transactions use `ReactiveTransactionManager` and `@Transactional` in reactive contexts; never use a JDBC transaction manager to manage an R2DBC `Connection`.
- Do not trigger manual subscriptions inside controllers just to "force execution"; return `Mono`/`Flux` so the framework manages the request lifecycle.
- Backpressure regulates data streams, yet it does not remove Cloud SQL connection limits or query execution capacity limits.
- If business logic requires JPA, JDBC is usually cleaner than a cobbled-together reactive workaround.

## 4. How Does the Cloud SQL Java Connector Work?

The Cloud SQL Java Connector is a connection library for Cloud SQL instances. It uses Google Cloud Application Default Credentials to call the Cloud SQL Admin API, fetch instance metadata and ephemeral certificates, and establish encrypted connections to Cloud SQL. It provides both a JDBC socket factory and an R2DBC provider.

~~~mermaid
sequenceDiagram
    participant APP as Java / Spring
    participant CON as Cloud SQL Java Connector
    participant IAM as ADC / Google Cloud IAM
    participant API as Cloud SQL Admin API
    participant DB as Cloud SQL Database

    APP->>CON: Request connection to PROJECT:REGION:INSTANCE
    CON->>IAM: Obtain credentials from ADC
    CON->>API: Verify instance and fetch metadata/certificates
    API-->>CON: Verified connection metadata
    CON->>DB: Encrypted connection over existing network
    DB-->>CON: Database session
    CON-->>APP: JDBC Connection or R2DBC Connection
~~~

**The connector does not provision a new network path to the database.** If using private IP, the application must already have a valid route to the VPC hosting Cloud SQL—such as Compute Engine/GKE inside the VPC, Cloud Run with Direct VPC egress, or Serverless VPC Access. If using public IP, the Cloud SQL instance must have a public IP and appropriate egress. For Private Service Connect (PSC), configure PSC first and select the matching IP type.

The connector handles transport and IAM authentication; the application must still authenticate at the database layer via one of two modes:

1. **Built-in database authentication:** PostgreSQL or MySQL username/password.
2. **IAM database authentication:** a Google Cloud user or service account configured as a database user; the connector automatically fetches and refreshes short-lived tokens.

The `Cloud SQL Client` IAM role only lets the principal connect through the connector; it does not implicitly grant `SELECT`/`INSERT`/`UPDATE` in PostgreSQL. Database `GRANT` statements are still required.

## 5. Prerequisites on Google Cloud

### 5.1. Required Resources

Examples in this lesson use Cloud SQL for PostgreSQL:

- Project ID: `demo-gcp-prod`.
- Region: `asia-southeast1`.
- Instance: `orders-db`.
- **Instance connection name**: `demo-gcp-prod:asia-southeast1:orders-db`.
- Database: `orders`.
- Workload runtime: service account `orders-api@demo-gcp-prod.iam.gserviceaccount.com`.
- Network path: `PRIVATE` for VPC routing; `PUBLIC` or `PSC` depending on design.

The instance connection name has the format **project:region:instance**, which differs from IPs, DNS hosts, and database names. Never confuse the instance name with the database name in a JDBC URL.

Enable the Cloud SQL Admin API:

~~~bash
gcloud services enable sqladmin.googleapis.com --project=demo-gcp-prod
~~~

Provision the Cloud SQL instance, database, and database users using your existing governance workflow. Manage instances, networking, storage, and backups via IaC rather than creating them manually per app deploy. For production, verify HA, PITR, backups, maintenance windows, and alerting before connecting workloads.

### 5.2. Granting IAM Permissions to the Runtime

Grant `Cloud SQL Client` on the project hosting the Cloud SQL instance:

~~~bash
gcloud projects add-iam-policy-binding demo-gcp-prod \
  --member="serviceAccount:orders-api@demo-gcp-prod.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
~~~

If using automatic IAM database authentication, also grant `Cloud SQL Instance User`:

~~~bash
gcloud projects add-iam-policy-binding demo-gcp-prod \
  --member="serviceAccount:orders-api@demo-gcp-prod.iam.gserviceaccount.com" \
  --role="roles/cloudsql.instanceUser"
~~~

In multi-project setups, if the workload service account lives in another project, enable the Cloud SQL Admin API in the relevant projects and grant IAM on the project owning the Cloud SQL instance.

During local development, use ADC:

~~~bash
gcloud auth application-default login
~~~

On Cloud Run, Compute Engine, or GKE, attach the appropriate runtime service account to the workload. On GKE, prefer Workload Identity Federation for GKE; avoid mounting long-lived service account JSON keys.

### 5.3. Checking Networking and Firewalls

Cloud SQL Connectors require:

| Flow | Port | Why it is needed |
|---|---:|---|
| Workload → Cloud SQL Admin API over HTTPS | TCP 443 | Fetch metadata, IAM/certificates, and refresh credentials |
| Workload → Cloud SQL instance | TCP 3307 | Establish the Cloud SQL Connector tunnel |
| Workload → Internet or private endpoints | Per configuration | Required only if other dependencies need them |

The domain `sqladmin.googleapis.com` does not have a single fixed IP address. When enforcing egress policies, allow HTTPS to Google Cloud APIs rather than pinning a static IP.

When using private IP, routing and DNS to Google APIs, Cloud NAT/Private Google Access, or Private Service Connect for APIs can affect connectivity. Design networking around where the workload runs. Never open broad public ingress as a "quick fix" for a private connectivity error.

## 6. JDBC + HikariCP + Spring Boot Connecting to Cloud SQL

### 6.1. Dependencies

For PostgreSQL, you need Spring JDBC, the PostgreSQL JDBC driver, and the Cloud SQL PostgreSQL socket factory.

Gradle Groovy DSL example (pick a socket factory version matching a tested connector release):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'com.google.cloud.sql:postgres-socket-factory:1.31.0'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Spring Boot manages starter and driver versions through dependency management; the socket factory library needs explicit version control. Version `1.31.0` reflects the upstream artifact documented at the time; before production use, verify the latest release and compatibility matrix.

By default, the Spring Boot JDBC starter provides HikariCP. Never instantiate a new `DataSource` per request.

### 6.2. Configuring DataSource as a Java Bean

This example uses a built-in database user and password read from platform-provided environment variables. In production, load `DB_PASSWORD` from Secret Manager or an equivalent secrets manager.

~~~java
package example.orders.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import javax.sql.DataSource;

@Configuration
public class JdbcCloudSqlConfig {

    @Bean(destroyMethod = "close")
    DataSource dataSource() {
        HikariConfig config = new HikariConfig();

        String db = requireEnv("DB_NAME");
        config.setJdbcUrl("jdbc:postgresql:///" + db);
        config.setUsername(requireEnv("DB_USER"));
        config.setPassword(requireEnv("DB_PASSWORD"));

        config.addDataSourceProperty(
                "socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        config.addDataSourceProperty(
                "cloudSqlInstance", requireEnv("INSTANCE_CONNECTION_NAME"));
        config.addDataSourceProperty("ipTypes", "PRIVATE");
        config.addDataSourceProperty("cloudSqlRefreshStrategy", "lazy");

        // TLS is handled by the Cloud SQL Java Connector.
        config.addDataSourceProperty("sslmode", "disable");

        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(10000); // 10 seconds
        config.setIdleTimeout(300000);      // 5 minutes
        config.setMaxLifetime(1800000);     // 30 minutes

        return new HikariDataSource(config);
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required configuration: " + name);
        }
        return value;
    }
}
~~~

Parameter explanations:

| Parameter | Meaning |
|---|---|
| `socketFactory` | Configures the Cloud SQL Connector for PostgreSQL JDBC |
| `cloudSqlInstance` | Instance connection name in `project:region:instance` format |
| `ipTypes=PRIVATE` | Selects private IP; requires VPC connectivity to the instance |
| `cloudSqlRefreshStrategy=lazy` | Refreshes metadata/certs only when needed, suited for serverless with CPU throttling |
| `sslmode=disable` | Disables pgJDBC's own SSL layer because the connector manages TLS |
| `maximumPoolSize` | Maximum physical connections per application instance |
| `connectionTimeout` | Maximum wait time for a connection from the pool |

Note: `sslmode=disable` in a **JDBC config using the Cloud SQL Connector** does not send plaintext between the app and Cloud SQL. The connector handles TLS. Never copy that setting to a direct-IP JDBC connection unless driver-level TLS is otherwise configured.

### 6.3. Spring Repository with JdbcTemplate

Once Spring has a `DataSource` bean, you can use `JdbcTemplate`:

~~~java
package example.orders.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {
    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String statusOf(long id) {
        return jdbc.query(
            "SELECT status FROM orders WHERE id = ?",
            rs -> rs.next() ? rs.getString("status") : null,
            id
        );
    }
}
~~~

With Spring Data JPA, keep this datasource underneath Hibernate, while carefully reviewing entity mappings, transaction boundaries, and lazy loading. Never put database passwords in source code or logged URLs.

## 7. Automatic IAM Database Authentication with JDBC

If your organization wants to avoid managing `DB_USER`/`DB_PASSWORD` secrets, Cloud SQL supports automatic IAM database authentication for PostgreSQL and MySQL. The connector mints and refreshes OAuth tokens instead of using a static database password.

Prerequisites:

1. Enable IAM database authentication on the Cloud SQL instance (PostgreSQL uses database flag `cloudsql.iam_authentication`).
2. Create an IAM database user/service account in Cloud SQL.
3. Grant `roles/cloudsql.client` and `roles/cloudsql.instanceUser` to the runtime principal.
4. Run PostgreSQL `GRANT` statements so the user has privileges on the required schemas and tables.
5. Use the **same IAM identity** to run the connector and log into the database.

Create the IAM database user for the service account:

~~~bash
gcloud sql users create orders-api@demo-gcp-prod.iam.gserviceaccount.com \
  --instance=orders-db \
  --type=CLOUD_IAM_SERVICE_ACCOUNT \
  --project=demo-gcp-prod
~~~

PostgreSQL represents IAM service account names without the `.gserviceaccount.com` suffix. For our example service account, the database username becomes:

~~~text
orders-api@demo-gcp-prod.iam
~~~

Grant data privileges in PostgreSQL to that username per actual requirements, for example:

~~~sql
GRANT CONNECT ON DATABASE orders
  TO "orders-api@demo-gcp-prod.iam";
GRANT USAGE ON SCHEMA public
  TO "orders-api@demo-gcp-prod.iam";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public
  TO "orders-api@demo-gcp-prod.iam";
~~~

These `GRANT` statements are examples to be applied by an authorized database administrator. Privileges on future tables require configuring default privileges or appropriate role ownership.

With Hikari, update username/password and add `enableIamAuth`:

~~~java
config.setUsername("orders-api@demo-gcp-prod.iam");
config.setPassword("unused-nonempty"); // Driver validation requires a non-empty value
config.addDataSourceProperty("enableIamAuth", "true");
~~~

When `enableIamAuth=true`, the connector uses an IAM token to authenticate; the placeholder password satisfies driver input validation and is not used as an actual database credential. In production code, document the placeholder clearly so operators do not mistake it for a real password.

**Distinguish the two permission layers:** `Cloud SQL Client` allows connecting via the connector; `Cloud SQL Instance User` allows IAM-based database login. PostgreSQL `GRANT` determines what data the user can access after logging in.

For Cloud SQL for SQL Server, IAM database authentication in this pattern is not supported by the Java connector. Use username/password authentication and the appropriate driver instead.

## 8. R2DBC + Cloud SQL Java Connector + Spring WebFlux

### 8.1. Dependencies

When choosing Spring WebFlux and R2DBC PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    implementation 'com.google.cloud.sql:cloud-sql-connector-r2dbc-postgres:1.31.0'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
    implementation 'io.r2dbc:r2dbc-pool'
}
~~~

The Spring Boot BOM manages supported Spring/R2DBC dependencies; the Cloud SQL connector is an independent dependency. Verify compatibility with Spring Boot, the Java runtime, Netty, and the driver before upgrading.

Do not add the JPA starter just to access the same database in an R2DBC application; JPA is blocking. If a system must combine both, strictly separate execution threads and transaction boundaries.

### 8.2. Creating the ConnectionFactory

For PostgreSQL, the Cloud SQL R2DBC provider uses `DRIVER=gcp` and `PROTOCOL=postgresql`. `HOST` takes the instance connection name. Other values such as `USER`, `DATABASE`, and `PASSWORD` come from configuration.

~~~java
package example.orders.config;

import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.Option;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

import static io.r2dbc.spi.ConnectionFactoryOptions.*;

@Configuration
public class ReactiveCloudSqlConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionPool connectionFactory() {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
            .option(DRIVER, "gcp")
            .option(PROTOCOL, "postgresql")
            .option(HOST, requireEnv("INSTANCE_CONNECTION_NAME"))
            .option(DATABASE, requireEnv("DB_NAME"))
            .option(USER, requireEnv("DB_USER"))
            .option(PASSWORD, requireEnv("DB_PASSWORD"))
            .option(Option.valueOf("ipTypes"), "PRIVATE")
            .build();

        ConnectionFactory delegate = ConnectionFactories.get(options);

        ConnectionPoolConfiguration poolConfig =
            ConnectionPoolConfiguration.builder(delegate)
                .initialSize(0)
                .maxSize(5)
                .maxIdleTime(Duration.ofMinutes(5))
                .maxAcquireTime(Duration.ofSeconds(10))
                .build();

        return new ConnectionPool(poolConfig);
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required configuration: " + name);
        }
        return value;
    }
}
~~~

This is an R2DBC `ConnectionPool`, distinct from HikariCP. Spring can use this bean for `DatabaseClient` and Spring Data R2DBC repositories. Tune pool settings against database instance sizing and application replica counts; never expand the pool indefinitely when seeing timeouts.

R2DBC also supports URL format:

~~~text
r2dbc:gcp:postgres://DB_USER:DB_PASS@PROJECT:REGION:INSTANCE/DB_NAME
~~~

In production, avoid placing secrets directly in URLs because URLs can show up in config logs, exceptions, and diagnostics. Use `ConnectionFactoryOptions` or Spring's secret management mechanisms.

### 8.3. Automatic IAM Auth for R2DBC

The Cloud SQL R2DBC provider supports IAM database auth for PostgreSQL and MySQL on the same principles as JDBC. Replace the password with a non-empty placeholder string, set the truncated database username, and add the `enableIamAuth` option:

~~~java
.option(USER, "orders-api@demo-gcp-prod.iam")
.option(PASSWORD, "unused-nonempty")
.option(Option.valueOf("enableIamAuth"), true)
~~~

These are replacement lines inside the `ConnectionFactoryOptions` builder, not standalone calls after `build()`. The IAM database user, roles, and PostgreSQL `GRANT`s must be configured beforehand. Do not enable this feature without evaluating your organization's IAM/database requirements.

### 8.4. Reactive Repositories and Transactions

Spring Data R2DBC supports querying via `Mono`/`Flux`. Transactions require `ReactiveTransactionManager` instead of `JpaTransactionManager`/`DataSourceTransactionManager`.

Example controller returning `Mono` without blocking:

~~~java
package example.orders.api;

import example.orders.repository.ReactiveOrderRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final ReactiveOrderRepository repository;

    public OrderController(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/{id}/status")
    public Mono<String> status(@PathVariable long id) {
        return repository.findStatus(id)
                .defaultIfEmpty("NOT_FOUND");
    }
}
~~~

The controller and repository in this section must coexist in the same project; `ReactiveOrderRepository` in Section 3 is an architectural sample you can build into a complete implementation.

## 9. Connecting via Public IP, Private IP, and PSC

The connector does not provision VPC peering, VPC routes, or Private Service Connect itself. Pick the IP type matching your topology:

| IP type | When suitable | Network prerequisites |
|---|---|---|
| `PUBLIC` | Workload has egress to Cloud SQL's public IP | Cloud SQL has public IP, egress TCP 3307/443; connector handles auth/TLS |
| `PRIVATE` | Workload sits in or routes to the VPC hosting Cloud SQL | Cloud SQL has private IP; VPC/Direct VPC egress/peering and routes configured |
| `PSC` | Cloud SQL is exposed via Private Service Connect | PSC endpoint/network/DNS properly configured |

In JDBC, use the `ipTypes` property (`PRIVATE`, `PUBLIC`, or `PSC`); in R2DBC, use the `ipTypes` option. If omitted, the default typically prefers `PUBLIC` then `PRIVATE`. Always specify the IP type explicitly in production to prevent traffic from taking an unintended network path.

### Cloud Run

If a Cloud Run service uses the Cloud SQL connector with private IP, configure Direct VPC egress to a VPC that routes to Cloud SQL, select the subnet, and verify firewalls/egress. While Cloud Run also offers a built-in Cloud SQL integration over sockets, when using the Java Connector directly inside the app, the built-in socket mount is not required.

### GKE

GKE workloads can use Workload Identity Federation for GKE to supply ADC for a Google Cloud service account. Ensure pod/network policies and VPC/firewalls allow egress on 443/3307, then configure the connector with the instance connection name.

### Compute Engine

The VM runs with a service account holding `Cloud SQL Client`; OAuth access scopes must suffice to call APIs. For private IP, the VM must sit in the VPC or have valid routing to Cloud SQL. Never place service account keys on VM disks.

## 10. Pooling, Concurrency, and Connection Limits

Opening a database connection incurs authentication, network handshake, and PostgreSQL resource overhead. Pools reuse connections and cap total counts.

Total connections scale according to:

\[
\text{Expected max connections}
\approx \text{Application instance count} \times \text{Pool size per instance}
\]

For example, 20 Cloud Run instances with HikariCP `maximumPoolSize=5` can require roughly **100 physical connections**—before counting jobs, migration tools, consoles, or other applications. If autoscaling ramps up quickly, the database can exhaust connections before Cloud Run CPU hits its threshold.

### Pool Design Recommendations

| Setting | JDBC/HikariCP | R2DBC pool | Effect |
|---|---|---|---|
| Maximum pool size | `maximumPoolSize` | `maxSize` | Caps connections per app instance |
| Minimum/initial size | `minimumIdle` | `initialSize` | Avoids opening too many connections immediately on scale-out |
| Acquire timeout | `connectionTimeout` | `maxAcquireTime` | Stops requests from waiting forever on the pool |
| Max idle time | `idleTimeout` | `maxIdleTime` | Releases unused connections |
| Connection lifetime | `maxLifetime` | `maxLifeTime` if supported by driver/pool | Periodically rotates connections |

Start with small pools and monitor Cloud SQL active connections, DB CPU, lock waits, query latency, connection acquire wait times, and 5xx/timeout rates. Increase pool size only when metrics prove a pooling bottleneck, because a larger pool cannot fix slow queries or missing indexes.

On Cloud Run, use lazy refresh to avoid unnecessary background metadata refreshes while CPU is throttled. During Cloud SQL maintenance or failovers, existing connections drop; applications need bounded retries with backoff and idempotency on appropriate operations.

## 11. Transactions, Timeouts, and Retries

Database connectivity incidents often stem from missing transaction/timeout discipline:

- Set timeouts on pool acquisition, queries, and HTTP requests aligned with SLAs.
- Keep transactions short; avoid awaiting third-party network calls inside an open database transaction.
- Never blindly retry `INSERT`/`UPDATE` statements, as a commit may have succeeded before the response failed, creating duplicate data.
- For idempotent operations or operations carrying idempotency keys, apply bounded exponential backoff retries.
- Distinguish transient connection errors from SQL syntax errors, constraint violations, or permission failures: the latter require code or privilege fixes.
- During Cloud SQL failovers, capture logs and metrics to track connection loss, recovery duration, and failed request counts.

In Spring JDBC, `@Transactional` manages transactions over `DataSource`. In Spring R2DBC, `@Transactional` with `ReactiveTransactionManager` relies on Reactor Context; never mix a thread-local JDBC transaction manager into a reactive pipeline.

## 12. Securing Credentials and IAM

### 12.1. Choosing IAM Database Auth or Passwords?

| Criterion | Built-in user/password | IAM database authentication |
|---|---|---|
| DB-layer credentials | Username + password | IAM user/service account + short-lived token |
| Rotation | Self-managed, optionally stored in Secret Manager | Connector refreshes tokens automatically |
| Cloud SQL connect permission | `roles/cloudsql.client` when using connector | `roles/cloudsql.client` and `roles/cloudsql.instanceUser` |
| Data read/write privileges | Database `GRANT` | Database `GRANT` |
| Best fit | Legacy apps, engines/tools requiring passwords | Google Cloud workloads with IAM wanting fewer static passwords |
| Constraints | Must manage and rotate secrets | Must configure IAM DB user, instance flag, and consistent principal |

Google Cloud recommends IAM database authentication when applications support it. When using passwords, Secret Manager helps store and rotate secrets securely. Never place `DB_PASSWORD` in source code, Dockerfiles, Git, error logs, or CI pipeline output.

### 12.2. Applying Least Privilege

The runtime service account needs only Cloud SQL connectivity and the API roles it genuinely uses. Inside PostgreSQL, create read-only or read-write roles scoped to needed schemas. Never run business applications as `postgres` or a superuser.

For CI/CD schema migrations, use a separate identity holding DDL permissions distinct from the runtime identity. Do not grant `CREATE`/`ALTER`/`DROP` to request-serving services unnecessarily.

## 13. Observability and Cost Control

Java applications and Cloud SQL must be monitored together. Useful signals:

- **From the application:** API latency, query duration, Hikari active/idle/pending connections, R2DBC pool acquire duration, exception rates, and timeout rates.
- **From Cloud SQL:** CPU, memory, disk, connection count, transaction throughput, lock waits, deadlocks, and Query Insights for slow queries.
- **From the connector:** IAM/API errors, refresh/certificate errors, network timeouts, and total connection creation counts.

Micrometer + Spring Boot Actuator can export HikariCP metrics. For R2DBC, metrics and tracing depend on the specific connector/pool and instrumentation; verify real metric emission before building dashboards.

When optimizing costs, consider connection counts, Cloud SQL instance sizing, HA, storage growth, cross-region network egress, and Cloud Run/GKE compute usage. Oversized pools increase database memory and CPU overhead even when request throughput stays flat.

## 14. Deployment Scenario: Orders API on Cloud Run

Suppose Orders API uses Spring Boot and Cloud SQL for PostgreSQL in the same region. The team wants private networking, no long-lived passwords, and autoscaling capability.

Recommended workflow:

1. Provision a Cloud SQL instance with private IP, database `orders`, and IAM database authentication enabled.
2. Create the `orders-api` service account and grant `Cloud SQL Client` + `Cloud SQL Instance User`.
3. Add the service account as an IAM database user and execute SQL `GRANT` statements on the business tables.
4. Deploy the Cloud Run service with that service account; enable Direct VPC egress to a network reaching Cloud SQL.
5. If using Spring MVC/JPA, add pgJDBC + JDBC socket factory + HikariCP; if using WebFlux/R2DBC, add the R2DBC provider + connection pool.
6. Configure the instance connection name, `ipTypes=PRIVATE`, and IAM auth; omit real `DB_PASSWORD` values from configuration.
7. Start with max pool size 5 per instance and reconcile Cloud Run max instances against the Cloud SQL connection budget.
8. Run migrations under a dedicated migration identity, then verify API `SELECT`/`INSERT` queries under the runtime identity.
9. Monitor API p95 latency, pool wait times, Cloud SQL active connections, CPU, lock waits, and 5xx errors.
10. Test DB failover/restarts in staging; tune connection timeouts, retries, and graceful shutdown.

If 403 errors appear after deployment, check the Cloud Run principal and IAM roles on the project owning Cloud SQL. If you see `"permission denied for table"`, connectivity and IAM succeeded, yet PostgreSQL `GRANT` privileges are missing. If timeouts occur reaching private IP, inspect routes and Direct VPC egress before changing credentials.

## 15. Common Errors and Troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| `403 PERMISSION_DENIED` from Cloud SQL Admin API | Missing `Cloud SQL Client`, wrong ADC, or API disabled | Verify runtime service account, `sqladmin.googleapis.com`, and role in the right project |
| Timeout calling Cloud SQL Admin API | Cannot reach `sqladmin.googleapis.com` over HTTPS | Check DNS, TCP 443 egress, proxy/Private Google Access/PSC |
| Timeout reaching Cloud SQL | Private IP missing network route or TCP 3307 egress blocked | Check VPC, Direct VPC egress, firewalls, and `ipTypes` |
| Instance not found | Wrong `project:region:instance` or instance lives in another project | Verify instance connection name in Cloud SQL Console |
| Password authentication failed | Wrong built-in password or username | Check Secret Manager, version, and actual DB user |
| IAM login failed | Flag disabled, IAM DB user not added, or missing `Instance User` | Check Cloud SQL IAM auth setting, IAM roles, and truncated username |
| Permission denied for table/schema | Missing PostgreSQL `GRANT` | Check `CONNECT`, `USAGE`, `SELECT`/`INSERT`/`UPDATE`, and default privileges |
| Hikari connection timeout | Pool exhausted, queries hold connections too long, or DB slow | Check active/pending pool counts, slow queries, transactions, and max connections |
| R2DBC provider not found | Missing connector or incompatible R2DBC driver | Check classpath, Spring Boot version, `gcp` provider, and PostgreSQL driver |
| Reactive endpoints stall together | Blocking JDBC or blocking work running on the event loop | Check for `block()`, CPU profiling, and tracing; use non-blocking drivers or a dedicated scheduler |
| Brief errors right after failover | Existing connections dropped during primary switchover | Retry idempotent ops with backoff, bound pool waits, and monitor recovery |
| Database connections spike on live service | Autoscaling multiplies pools too high | Calculate `instances × maxPool`, cap scale, and measure connection counts |

Never log raw database passwords, IAM access tokens, connection URLs containing credentials, or SQL containing sensitive data while debugging. When investigating, log the principal, instance connection name, error code, and an appropriate trace ID.

## 16. Production Checklist

- [ ] Database instance and engine/version are compatible with Java drivers.
- [ ] Cloud SQL Admin API is enabled and the runtime service account holds `Cloud SQL Client`.
- [ ] If using IAM auth, `Cloud SQL Instance User` and the IAM database user are configured.
- [ ] PostgreSQL `GRANT` restricts privileges to only required schemas/tables.
- [ ] Workload has valid ADC without storing long-lived service account JSON keys.
- [ ] Network path to the instance matches `PUBLIC`/`PRIVATE`/`PSC` and ports 443/3307.
- [ ] JDBC uses HikariCP/`DataSource`; R2DBC uses reactive `ConnectionFactory`/`ConnectionPool`.
- [ ] Blocking JDBC is never executed on the WebFlux event loop.
- [ ] Timeouts, pool sizes, and retries align with SLAs.
- [ ] Projected total pool connections stay within the Cloud SQL connection budget.
- [ ] Secrets are managed via Secret Manager or automatic IAM DB authentication.
- [ ] Schema migrations use a separate identity from runtime.
- [ ] Failover, timeouts, and graceful shutdown have been tested.
- [ ] Dashboards monitor both the application and Cloud SQL (connections, query latency, CPU, errors).
- [ ] Database authentication and privileges were verified in staging before release.

## 17. Self-Check Questions

**1. How do JDBC and R2DBC differ?**

JDBC is a blocking database access API commonly paired with Spring MVC, `JdbcTemplate`, and JPA. R2DBC uses Reactive Streams for non-blocking communication, fitting Spring WebFlux and end-to-end reactive pipelines.

**2. Does the Cloud SQL Java Connector create a VPC route for private IP?**

No. The connector handles IAM, metadata, and TLS. Workloads still require a valid network route to Cloud SQL's private IP via VPC networking or an equivalent connector path.

**3. Why is `Cloud SQL Client` not enough to read the Orders table?**

`Cloud SQL Client` permits connecting through the connector. Database-layer login and `SELECT`/`INSERT`/`UPDATE` privileges are governed by database users and PostgreSQL `GRANT` statements.

**4. What prerequisites does IAM database authentication require?**

Enable IAM auth on the instance, add the IAM database user/service account, grant `Cloud SQL Client` and `Cloud SQL Instance User`, grant DB privileges via `GRANT`, and use the same principal for both ADC and the database user.

**5. Why pay attention to pools when Cloud Run autoscales?**

Each Cloud Run instance maintains its own pool. Total connections can reach instance count multiplied by pool size; exceeding Cloud SQL limits causes new connections to be rejected or requests to time out.

**6. Why can JDBC using the Cloud SQL Connector set `sslmode=disable`?**

Because TLS between the application and Cloud SQL is already managed by the Java Connector. This setting is appropriate only when routing through the connector's socket factory.

**7. Does switching to R2DBC make slow SQL queries run faster?**

No. Non-blocking I/O improves how threads handle I/O waits; it does not fix missing indexes, lock contention, poor query plans, or an overloaded database.

## 18. References

- [Cloud SQL: Connect using Cloud SQL language connectors](https://cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL Java Connector: repository and general guide](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory)
- [Cloud SQL Java Connector: JDBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md)
- [Cloud SQL Java Connector: R2DBC](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/r2dbc.md)
- [Cloud SQL Java Connector: configuration reference](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/configuration.md)
- [Cloud SQL for PostgreSQL: IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL for PostgreSQL: Log in with IAM database authentication](https://cloud.google.com/sql/docs/postgres/iam-logins)
- [Cloud SQL for PostgreSQL: Connection options](https://cloud.google.com/sql/docs/postgres/connection-options)
- [Cloud SQL for PostgreSQL: Manage connections](https://cloud.google.com/sql/docs/postgres/manage-connections)
- [Cloud SQL for PostgreSQL: Connect from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run)
- [Spring Framework: R2DBC DatabaseClient](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [R2DBC Specification](https://r2dbc.io/spec/1.0.0.RELEASE/spec/html/)
