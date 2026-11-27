# Authenticating RDS with IAM When Supported and Refreshing Connections

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, SDKs, and drivers. With **Amazon Relational Database Service (Amazon RDS)**, Java applications typically use JDBC to access PostgreSQL, MySQL, or MariaDB. In production, beyond configuring the JDBC URL and networking, you must choose a database authentication method suited to the workload identity and connection pool lifecycle.

RDS supports **IAM database authentication** for specific engines and versions, enabling workloads to use AWS Identity and Access Management (IAM) to authenticate when opening database connections instead of long-lived database passwords. The application generates a SigV4-signed **authentication token** and passes it as the password during the JDBC handshake. The token has a **15-minute** lifetime; already-authenticated connections continue operating even after the token expires.

The challenge lies in connection pooling: HikariCP keeps physical connections open for extended periods and opens new ones only as needed. If the application generates a token once at startup and stores it as a static password, new connections opened after the token expires will fail. You must mint a fresh token **whenever a physical connection is opened**, while keeping the pool stable and handling failovers and credential refreshes.

After this lesson, you will be able to:

1. Identify RDS engines and versions that support IAM database authentication and enable the feature properly.
2. Distinguish the IAM permission `rds-db:connect`, the database user, and SQL privileges.
3. Generate authentication tokens with AWS SDK for Java v2 using the exact Region, hostname, port, and username.
4. Secure connections with TLS and hostname verification; avoid placing tokens as static passwords in configuration.
5. Integrate a token provider with HikariCP so tokens refresh whenever a new physical connection is created.
6. Combine IAM database authentication with RDS Proxy where appropriate, and monitor pooling, failovers, and rotation.
7. Test token generation and live connectivity in an AWS staging environment.

> **Scope:** IAM database authentication is supported for specific engines and versions, not universally across every RDS database engine. This lesson uses PostgreSQL as the primary example; MySQL/MariaDB require different user and TLS setups. Always check AWS's engine/version support matrix and documentation before enabling it in production.

## 2. How Does IAM Database Authentication Work?

### 2.1. Authentication Flow

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant IAM as AWS SDK / IAM credentials
    participant RDS as RDS PostgreSQL
    App->>IAM: Obtain credentials from provider chain
    App->>IAM: Sign token with Region, endpoint, port, DB user
    IAM-->>App: IAM authentication token
    App->>RDS: Open TLS connection, send DB user + token
    RDS->>RDS: Verify signature and IAM permission
    RDS-->>App: Authenticated database session
    Note over App,RDS: Token is only used when authenticating a new connection
~~~

Step-by-step flow:

1. The workload obtains AWS credentials from an IAM role or the credential provider chain.
2. The application generates a token for the exact endpoint hostname, port, Region, and DB username.
3. The JDBC driver opens a TLS connection to RDS.
4. The driver sends the database username and token during the authentication handshake.
5. RDS validates the token/IAM permission and checks that the database user is configured for IAM authentication.
6. If valid, the server establishes a database session. Once authenticated, the session does not resend the token for every SQL query.

The token is a signed string rather than a traditional database password, and generating it does not make a remote RDS API call. However, because the token embeds time-limited authentication material, treat it as sensitive data—never write it to logs, traces, or exception messages.

### 2.2. A 15-Minute Token Is Not Connection Lifetime

This is the single most important point when pairing IAM auth with HikariCP:

- A token is valid for **15 minutes from creation** to initiate authentication.
- An already-authenticated connection can remain in use long after the token expires.
- Whenever Hikari opens a new physical connection (pool scale-up, retirement of an old connection, failover, idle eviction), the application must mint a fresh token.
- You do not need a new token for every SQL query or every logical connection borrow from the pool.
- Do not set `maxLifetime` to 15 minutes just because tokens live for 15 minutes. Those two durations mean completely different things.

~~~text
09:00  Generate token T1
09:01  Open physical connection C1 using T1
09:15  T1 expires
09:20  C1 continues executing SQL cleanly
09:22  Hikari needs to open connection C2 -> generate fresh token T2
~~~

If the application puts token T1 into `spring.datasource.password` as a static string, Hikari reuses the expired token when opening new physical connections and fails authentication. The right approach is to generate the token at the physical-connection creation layer.

## 3. RDS Engines, Database Users, and Support Conditions

### 3.1. Verify Engine Support Before Designing

IAM database authentication is supported on engine families such as:

- Amazon RDS for PostgreSQL.
- Amazon RDS for MySQL.
- Amazon RDS for MariaDB.
- Amazon Aurora PostgreSQL-Compatible Edition.
- Amazon Aurora MySQL-Compatible Edition.

Support still depends on engine version, Region, cluster/instance configuration, and topology. Do not assume this applies to RDS for Oracle or SQL Server. Before deploying, check the IAM database authentication support matrix for your **exact running engine and version**.

IAM DB authentication must be enabled on the DB instance or Aurora cluster per engine documentation. Some configuration changes may require a propagation window or reboot depending on the resource type; verify instance status afterward.

### 3.2. Operational Limits to Plan Ahead

- **Database memory:** IAM DB authentication uses compute resources on the DB; AWS recommends provisioning roughly **300–1,000 MiB of additional memory** for stable connections. Use Enhanced Monitoring to compare RDS process memory before and after enabling it, especially on burstable instances.
- **Token size:** tokens are typically at least **~1 KB** and can grow larger depending on IAM tags, policies, and ARN length. JDBC drivers, proxy clients, or middleware must not truncate the password/token.
- **Temporary credentials:** if a token is signed with temporary credentials, those credentials must still be valid when the client actually opens the connection. Generate tokens just before connecting and use a refreshable credential provider.
- **Hostname:** do not use a custom Route 53 DNS record instead of the DB instance/cluster endpoint when signing tokens. When connecting through RDS Proxy, use the proxy endpoint itself per proxy documentation.
- **Auditing:** CloudWatch and CloudTrail do not log individual IAM DB authentication attempts or token generation calls. You can audit IAM role/policy modifications separately, but do not rely on CloudTrail to count database logins.
- **IAM condition keys:** IAM DB authentication does not support every global condition context key; do not assume keys like `aws:SourceIp`, `aws:SourceVpc`, or `aws:SourceVpce` restrict `rds-db:connect`. Use resource ARN/user scoping together with VPC, subnet, and security group rules for their respective layers.
- **Platform constraints:** IAM DB authentication is not supported on RDS on Outposts. On PostgreSQL, a user cannot simultaneously use IAM (`rds_iam`) and Kerberos (`rds_ad`); `rds_iam` causes IAM auth to take precedence over password auth.

### 3.3. Creating a Database User on PostgreSQL

IAM permissions only authorize an AWS identity to connect as the named DB user. They **do not create the database user** or grant SQL privileges on schemas/tables.

Example on RDS PostgreSQL:

~~~sql
-- Connect as an admin/database user with management privileges.
CREATE USER reservation_app;

-- Allow the user to use IAM database authentication.
GRANT rds_iam TO reservation_app;

-- Grant SQL privileges separately following least privilege.
GRANT CONNECT ON DATABASE reservationdb TO reservation_app;
GRANT USAGE ON SCHEMA public TO reservation_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA public TO reservation_app;

-- If sequences are used by identity/serial columns:
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA public TO reservation_app;
~~~

For tables created in the future, configure `ALTER DEFAULT PRIVILEGES` for the role creating objects; `ON ALL TABLES` applies only to tables existing when the statement runs.

On RDS PostgreSQL and Aurora PostgreSQL, `rds_iam` is the built-in role that enables IAM authentication for a database user. A PostgreSQL user granted `rds_iam` authenticates via IAM instead of password authentication; never grant `rds_ad` to the same user simultaneously.

### 3.4. MySQL and MariaDB Have Distinct Syntax

Illustrative example for supported MySQL/MariaDB engines:

~~~sql
CREATE USER 'reservation_app' IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS';

GRANT SELECT, INSERT, UPDATE, DELETE
    ON reservationdb.* TO 'reservation_app';
~~~

Verify plugin syntax and grant statements against your exact engine and version. Do not run PostgreSQL's `GRANT rds_iam` on MySQL/MariaDB. On Aurora MySQL, a user configured for IAM authentication does not use password authentication; standardize on one authentication method per user.

### 3.5. Distinguishing the Three Permission Layers

| Layer | Mechanism | Question answered |
| --- | --- | --- |
| AWS workload identity | IAM role, OIDC/workload identity, credential provider | Which AWS identity is the application running as? |
| DB login permission | IAM policy action `rds-db:connect` scoped to DB resource/user | May this AWS identity authenticate as this DB user? |
| Inside-database privileges | SQL `GRANT`, engine roles, and privileges | Which objects may this DB user SELECT/INSERT/UPDATE/DELETE? |

Having `rds-db:connect` without SQL privileges lets connections succeed while queries fail with `permission denied`. Having SQL privileges with a wrong IAM policy causes the handshake to fail. Security groups and TLS are additional network/transport controls—they do not replace either permission layer.

## 4. Granting the `rds-db:connect` IAM Permission

### 4.1. Resource ARN Has a Dedicated Structure

IAM database authentication uses the **`rds-db:connect`** action, not `rds:Connect`. The resource ARN format is:

~~~text
arn:aws:rds-db:<region>:<account-id>:dbuser:<db-resource-id>/<db-username>
~~~

`<db-resource-id>` is the immutable resource ID of the DB instance or DB cluster depending on resource type, not the human-chosen DB identifier. For RDS Proxy, use the proxy resource ID in the ARN per the proxy IAM DB authentication docs.

Example policy for an RDS PostgreSQL instance:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "rds-db:connect",
      "Resource": "arn:aws:rds-db:ap-southeast-1:123456789012:dbuser:db-ABCDEFGHIJKLMNOP/reservation_app"
    }
  ]
}
~~~

Substitute your actual Region, account ID, resource ID, and DB username. This policy permits logging in only as `reservation_app` on that specific resource; avoid broad wildcards when the workload needs only one user/database.

For Aurora clusters, the ARN uses the **DB cluster resource ID**. For RDS Proxy, the resource ID and permission structure differ from direct instance endpoints; never substitute the DB identifier or proxy DNS hostname for the resource ID.

### 4.2. Attaching Roles to Workloads

Common ways to supply AWS credentials:

- **Amazon ECS:** task role attached to the application container.
- **Amazon EKS:** EKS Pod Identity or IAM Roles for Service Accounts (IRSA) per cluster setup.
- **Amazon EC2:** instance profile role.
- **Development environments:** AWS IAM Identity Center/profile or an organization-approved credential provider.

AWS SDK for Java v2 uses the default credentials provider chain to locate credentials. Prefer temporary role-based credentials; avoid long-lived access keys in `application.yml`, Docker images, pipeline-committed env vars, or source code.

You do not need `rds:DescribeDBInstances` just to sign tokens if the application already knows the endpoint, port, and username. Grant describe/admin actions only if features actually require them.

## 5. Generating Tokens with AWS SDK for Java v2

### 5.1. Dependencies

Add the AWS SDK v2 RDS module, with versions aligned by the AWS SDK BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>rds</artifactId>
</dependency>
~~~

The application still needs the database JDBC driver, such as PostgreSQL:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Spring Boot can use `spring-boot-starter-jdbc` for JDBC, HikariCP, and auto-configuration. AWSpring does not require a dedicated RDS JDBC starter; the AWS SDK generates the IAM token, and the JDBC driver passes it when opening a connection.

### 5.2. Generating Tokens for PostgreSQL

To test the DataSource without calling AWS, define a small token-supplier interface:

~~~java
@FunctionalInterface
public interface IamTokenSupplier {
    String getToken();
}
~~~

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;
import software.amazon.awssdk.services.rds.model.GenerateAuthenticationTokenRequest;

public final class RdsIamTokenProvider implements IamTokenSupplier, AutoCloseable {
    private final RdsUtilities utilities;
    private final DefaultCredentialsProvider credentialsProvider;
    private final String hostname;
    private final int port;
    private final String username;

    public RdsIamTokenProvider(
            Region region, String hostname, int port, String username) {
        this.credentialsProvider = DefaultCredentialsProvider.create();
        this.utilities = RdsUtilities.builder()
                .region(region)
                .credentialsProvider(credentialsProvider)
                .build();
        this.hostname = hostname;
        this.port = port;
        this.username = username;
    }

    @Override
    public String getToken() {
        return utilities.generateAuthenticationToken(
                GenerateAuthenticationTokenRequest.builder()
                        .hostname(hostname)
                        .port(port)
                        .username(username)
                        .build());
    }

    @Override
    public void close() {
        credentialsProvider.close();
    }
}
~~~

The token is signed with the active AWS credentials. The SDK credential provider resolves and refreshes temporary credentials from the workload role via the provider chain. `RdsUtilities` requires the exact Region and endpoint; never pass a resolved IP address instead of the DNS hostname.

You can generate a token via the AWS CLI for manual verification:

~~~bash
aws rds generate-db-auth-token \
  --hostname mydb.abcdefghijkl.ap-southeast-1.rds.amazonaws.com \
  --port 5432 \
  --region ap-southeast-1 \
  --username reservation_app
~~~

The CLI command requires AWS credentials holding `rds-db:connect`. The generated token is sensitive—never paste it into tickets, shared shell histories, CI logs, or public chats. This command verifies token generation, though it does not prove networking, TLS, DB user setup, or SQL grants are right.

### 5.3. Tokens Must Exactly Match the Target Endpoint

All parameters must match:

- `hostname`: the RDS endpoint or RDS Proxy endpoint the JDBC client actually connects to.
- `port`: the endpoint's database port.
- `region`: the Region hosting the DB/proxy.
- `username`: the database username configured for IAM authentication.

When using RDS Proxy, sign the token using the **proxy endpoint hostname** and use the proxy's IAM policy/resource ID per documentation. Never generate a token for the DB instance and send it to the proxy hostname. AWS does not support custom Route 53 DNS records in place of the DB instance/cluster endpoint for signing tokens; never substitute an alias or resolved IP.

## 6. TLS Is Mandatory for IAM Database Authentication

IAM DB authentication requires SSL/TLS-encrypted connections. For PostgreSQL JDBC, configure `sslmode=verify-full` and the matching CA bundle:

~~~yaml
app:
  rds:
    jdbc-url: jdbc:postgresql://db.example.ap-southeast-1.rds.amazonaws.com:5432/reservationdb
    host: db.example.ap-southeast-1.rds.amazonaws.com
    port: 5432
    username: reservation_app
    region: ap-southeast-1
    ca-file: /etc/ssl/certs/global-bundle.pem
~~~

When opening a connection, pass the driver properties:

~~~java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", token);
properties.setProperty("sslmode", "verify-full");
properties.setProperty("sslrootcert", caBundlePath);
~~~

`verify-full` checks both the CA chain and that the hostname matches the certificate. Rotate CA bundles on AWS's published schedule before old certificates expire. Never disable TLS as a "quick fix" for auth errors; IAM tokens do not replace transport encryption.

With MySQL Connector/J, TLS uses `sslMode=VERIFY_IDENTITY` and the driver's trust material settings. PostgreSQL and MySQL properties differ; always consult the exact JDBC driver docs.

## 7. Refreshing Tokens Properly with HikariCP

### 7.1. Why Static Passwords Fail Over Time

A simple setup like the following is unsuitable for IAM authentication:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example:5432/reservationdb
    username: reservation_app
    password: "<token-created-at-startup>"
~~~

Spring Boot initializes the DataSource once, and HikariCP reuses that same password whenever opening new physical connections minutes or hours later. The startup token expires after 15 minutes; existing authenticated connections keep working, yet as soon as the pool adds or replaces a connection, the driver sends the expired token and gets rejected.

You do not need to refresh the token on every application `getConnection()` call when it simply borrows a logical connection from the pool. You must refresh it **at physical JDBC connection creation time**.

### 7.2. DataSource Architecture Minting Tokens Per Physical Connection

Wrap the JDBC driver in a custom DataSource. HikariCP uses this DataSource as its physical connection source; whenever Hikari opens a new connection, the DataSource generates a fresh token and invokes the driver.

~~~mermaid
flowchart TD
    A["Spring JdbcTemplate"] --> B["HikariCP pool"]
    B -->|"Borrow logical connection"| C["Existing connection"]
    B -->|"Need new physical connection"| D["IAM-aware DataSource"]
    D --> E["RdsIamTokenProvider.getToken()"]
    E --> F["AWS SDK signs fresh token"]
    F --> G["JDBC Driver + TLS"]
    G --> H["RDS / RDS Proxy"]
    H --> B
~~~

PostgreSQL DataSource example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

import org.springframework.jdbc.datasource.AbstractDataSource;

public final class IamPostgresDataSource extends AbstractDataSource {
    private final String jdbcUrl;
    private final String username;
    private final String caBundlePath;
    private final IamTokenSupplier tokenProvider;

    public IamPostgresDataSource(
            String jdbcUrl,
            String username,
            String caBundlePath,
            IamTokenSupplier tokenProvider) {
        this.jdbcUrl = jdbcUrl;
        this.username = username;
        this.caBundlePath = caBundlePath;
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Connection getConnection() throws SQLException {
        final String token;
        try {
            token = tokenProvider.getToken();
        } catch (RuntimeException ex) {
            throw new SQLException("Unable to generate RDS IAM token", ex);
        }

        Properties properties = new Properties();
        properties.setProperty("user", username);
        properties.setProperty("password", token);
        properties.setProperty("sslmode", "verify-full");
        properties.setProperty("sslrootcert", caBundlePath);

        return DriverManager.getConnection(jdbcUrl, properties);
    }

    @Override
    public Connection getConnection(String requestedUser, String ignoredPassword)
            throws SQLException {
        if (!username.equals(requestedUser)) {
            throw new SQLException("Unexpected database username");
        }
        // Do not use any static password supplied by the caller.
        return getConnection();
    }
}
~~~

The DataSource generates a token **each time `DriverManager` opens a physical connection**. HikariCP pools that connection; when returned, Hikari resets and parks the logical handle in idle state without regenerating tokens per query.

In this example, `AbstractDataSource` is Spring JDBC's utility base class. The PostgreSQL JDBC driver must be on the runtime classpath so `DriverManager` locates it. For MySQL, implement a DataSource/driver adapter setting Connector/J's TLS properties rather than copying `sslmode`/`sslrootcert`.

### 7.3. Wiring HikariCP with the Custom DataSource

Create the `RdsIamTokenProvider` bean and custom DataSource, then pass the custom DataSource to Hikari:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.rds.RdsUtilities;

import javax.sql.DataSource;

@Configuration
public class RdsIamDataSourceConfiguration {

    @Bean(destroyMethod = "close")
    RdsIamTokenProvider rdsIamTokenProvider(
            @Value("${app.rds.region}") String region,
            @Value("${app.rds.host}") String host,
            @Value("${app.rds.port}") int port,
            @Value("${app.rds.username}") String username) {
        return new RdsIamTokenProvider(
                Region.of(region), host, port, username);
    }

    @Bean
    @Primary
    DataSource dataSource(
            RdsIamTokenProvider tokenProvider,
            @Value("${app.rds.jdbc-url}") String jdbcUrl,
            @Value("${app.rds.username}") String username,
            @Value("${app.rds.ca-file}") String caBundlePath) {

        IamPostgresDataSource physicalDataSource =
                new IamPostgresDataSource(
                        jdbcUrl, username, caBundlePath, tokenProvider);

        HikariConfig config = new HikariConfig();
        config.setPoolName("RdsIamPool");
        config.setDataSource(physicalDataSource);
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setMaxLifetime(1500000);

        // Do not call config.setUsername()/setPassword():
        // The IAM-aware DataSource mints a token for each physical connection.
        return new HikariDataSource(config);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

`@Primary` ensures Spring Boot/JdbcTemplate selects this DataSource. Defining your own `DataSource` bean backs off Boot's default DataSource auto-configuration. Avoid declaring another password-based DataSource bean alongside it and accidentally injecting the wrong one into repositories or transaction managers.

`DataSourceTransactionManager` fits single-DataSource JDBC transactions. If an application mixes JPA and `JdbcTemplate` over one DataSource, choose the matching Spring Boot transaction manager (e.g., `JpaTransactionManager` coordinates JDBC access on the same DataSource); avoid creating unintentional extra transaction managers.

Pool size and lifetime values are illustrative; size them for your DB connection budget, replica count, RDS Proxy, and query durations. Call the token provider on every physical connect—never cache a token in a field for reuse.

### 7.4. Why You Do Not Need to Refresh Every Connection Every 15 Minutes

Token expiration only prevents an old token from **authenticating a new connection**. It is not a database session timeout. If a pool holds 8 healthy connections, all 8 can keep serving queries well past minute 15.

Never tear down the entire pool on the token's 15-minute schedule. Doing so risks a connection storm where all instances reopen connections simultaneously, spiking authentication and handshake load. Simply let HikariCP retire connections according to `maxLifetime` and validation policies, minting a fresh token whenever a replacement connection is opened.

Coordinate `maxLifetime` with network, DB, proxy idle timeouts, and maintenance windows. Hikari never kills a currently borrowed connection; it marks it for retirement upon return. `keepaliveTime` can probe/maintain idle connections as configured, but does not replace failover checks or business retries.

## 8. Using IAM Database Authentication Through RDS Proxy

### 8.1. Two Authentication Hops to Distinguish

RDS Proxy sits between the application and the DB:

~~~text
Spring Boot -- IAM auth / TLS --> RDS Proxy -- backend auth --> RDS
~~~

RDS Proxy supports two distinct models:

| Model | Client → Proxy | Proxy → Database | Key credentials / permissions |
| --- | --- | --- | --- |
| **Standard IAM authentication** | App uses an IAM token signed for the proxy endpoint | Proxy uses database username/password from Secrets Manager | App role needs `rds-db:connect` on proxy resource ID `prx-...`; proxy role needs read access to the secret and KMS key. Backend DB user continues using password auth; do not configure that DB user as IAM-only. |
| **End-to-end IAM authentication** | App uses an IAM token signed for the proxy endpoint | Proxy uses IAM database authentication to the DB | App role needs `rds-db:connect` on the proxy resource ID; the proxy's IAM role needs `rds-db:connect` on the DB instance/cluster resource ID and DB user. The database user must be configured for IAM auth. No DB password secret is needed for the end-to-end flow. |

With end-to-end IAM, configure the proxy with `DefaultAuthScheme=IAM_AUTH`; verify your engine/version/Region appears on the active support list (AWS documents this for MySQL and PostgreSQL). Enable IAM DB authentication on the target DB first, create the matching DB user, and grant IAM permissions to both the client role and the proxy role on their respective resources. Standard IAM authentication remains useful when clients authenticate to the proxy via IAM while the backend database keeps password auth. On PostgreSQL, do not grant `rds_iam` to the DB user in standard mode if the proxy must log into the backend using a password.

In both models, the client token must be signed for the **RDS Proxy endpoint**, not the target DB endpoint. Never assume client IAM auth automatically causes the proxy to use IAM toward the DB: only end-to-end IAM applies IAM to both hops.

### 8.2. When Is the Proxy Worthwhile?

Consider RDS Proxy when:

- Workloads scale rapidly or many instances churn connections.
- Serverless/container workloads open many short-lived client sessions.
- You want centralized backend connection management to dampen connection churn.
- You want to decouple client credentials from target database credentials as supported by the proxy.

The proxy does not eliminate HikariCP, cannot speed up CPU/I/O-bound queries, and does not guarantee every session multiplexes. Long transactions or session state can cause connection pinning. Monitor client connections, database connections, borrow latency, and proxy target health.

## 9. IAM Credential Refresh, Password Rotation, and Failover

### 9.1. AWS Credential Refresh Differs from DB Token Refresh

There are two separate lifecycles:

1. **AWS credentials**: temporary credentials from ECS task roles, EC2 instance profiles, EKS Pod Identity/IRSA, or AssumeRole have their own expiration. The AWS SDK credential provider chain refreshes them automatically per provider.
2. **RDS IAM tokens**: signed with active AWS credentials at creation time, valid for 15 minutes, and used when opening a new DB connection.

Never cache AWS session credentials or DB tokens in static fields past their expiration. Rely on a refreshing SDK provider and mint a fresh token right before physical connect. If a role's permissions are revoked, new connections are rejected; existing authenticated sessions do not automatically terminate immediately on IAM policy edits.

### 9.2. IAM Auth Differs from Password Rotation

Secrets Manager rotation updates database passwords/secrets via a rotation workflow. IAM database authentication relies on short-lived tokens signed with IAM credentials—not a static password rotated monthly.

If an app uses **password-based JDBC** with Secrets Manager, refresh secrets and replace connections on reopen. If it uses **IAM DB auth**, refresh AWS credentials via the provider chain and mint a new token per physical connection. Both mechanisms can pair at RDS Proxy in supported setups, but never mix credential logic without clearly separating client-auth and target-auth.

### 9.3. RDS Failover and DNS Endpoints

During RDS failover or DB restart:

- Old physical connections may close or become invalid.
- Hikari detects broken connections during validation or query execution; in-flight requests may fail.
- The official DNS endpoint remains the address the app should connect to; never pin resolved IPs.
- When opening replacement connections, sign the IAM token with the active endpoint hostname and Region.
- Transactions interrupted during commit leave ambiguous outcomes for callers; reconcile via business keys/idempotency before retrying.

RDS Proxy can smooth connection-level failover recovery, though in-flight transactions can still fail. Test failovers in staging and measure pool recovery time, connection acquisition latency, and retry counts.

## 10. Security and Operations

### 10.1. Security Checklist

- Attach the right IAM role to each workload; scope `rds-db:connect` strictly to the required DB resource and user.
- Grant SQL privileges separately following least privilege; never run applications as the master/admin DB user.
- Enforce TLS and hostname verification; manage CA bundles and certificate expirations.
- Never log or trace tokens, AWS credentials, DB passwords, or connection strings containing secrets.
- Never pass tokens in URL query strings, message queues, or HTTP responses.
- Match hostname/Region/port exactly when signing tokens; proxy and DB instance endpoints use distinct resource ARNs.
- Restrict network access with VPCs/subnets/security groups; IAM authentication does not replace network firewalls.
- Separate dev/staging/prod IAM roles and audit policy/DB grant changes.
- Monitor connection counts, auth failures, pool timeouts, and failovers.

### 10.2. Metrics to Observe

| Source | Metric or Event | Meaning |
| --- | --- | --- |
| HikariCP | active, idle, pending, max, acquisition time, timeout count | Is the pool exhausted or are requests waiting too long? |
| Amazon RDS | `DatabaseConnections`, CPU, memory, IOPS, latency | Is the DB overloaded or near connection limits? |
| RDS Proxy | client connections, database connections, borrow latency, target health | Is the proxy supplying backend connections fast enough? |
| Spring application | connection creation failures, IAM token generation latency, auth exceptions | Are failures happening at token signing, TLS, or DB auth? |
| IAM/CloudTrail | role/policy changes | Were identity configs or permissions altered? CloudWatch/CloudTrail do not log individual IAM DB logins or token generation. |

Exact metric names depend on engine, RDS/Proxy type, CloudWatch namespace, and versions. Use correlated timelines to separate pool exhaustion, DB `max_connections`, IAM permission errors, TLS failures, and network timeouts. If per-session database auditing is required, enable engine-level database audit logging—never treat CloudTrail as an IAM DB login audit log.

## 11. Testing IAM Authentication and Connection Refresh

### 11.1. Unit Tests for Token Provider / DataSource

`IamTokenSupplier` from Section 5.2 lets tests inject a supplier that counts invocations or returns a distinct token per call. Verify that calling `IamPostgresDataSource.getConnection()` invokes the supplier once before the driver opens a connection. To avoid AWS calls in unit tests, inject a stub supplier and mock the JDBC driver/connection factory.

Tests should confirm:

1. Tokens are not cached and reused across two physical connection creations.
2. Username and token pass via JDBC properties—never concatenated into URLs or logs.
3. TLS properties (`verify-full`, CA bundle) are applied.
4. Hikari logical borrows from an existing connection do not generate a new token.
5. When Hikari creates a replacement physical connection, the supplier is invoked again.
6. Token-generation or driver-auth errors translate into appropriate `SQLException`s and are logged safely.

### 11.2. Integration Tests with a PostgreSQL Container

Testcontainers PostgreSQL verifies JDBC URLs, Hikari lifecycles, transactions, and DataSource wrappers with standard password auth. It **does not emulate the RDS IAM authentication plugin**, IAM policies, token validation, RDS Proxy, or VPC security groups.

Split testing into two layers:

- **Local/CI:** PostgreSQL Testcontainers verifying the DataSource wrapper with a stub token supplier, Hikari pool lifecycle, and transactions.
- **AWS staging:** RDS PostgreSQL with IAM DB auth enabled, a real workload role, `rds-db:connect` IAM policy, TLS CA bundle, and official endpoint. Let a token expire and then open a new connection; verify existing connections stay healthy while new connections authenticate with freshly minted tokens.

### 11.3. Concrete Staging Test Scenario

1. Create DB user `reservation_app`, grant `rds_iam`, and apply minimal SQL grants.
2. Attach the IAM role to ECS/EKS/EC2 in staging, granting `rds-db:connect` only for the target resource/user.
3. Connect via the RDS endpoint with TLS `verify-full`; run `SELECT current_user`.
4. Use a small Hikari pool and keep one connection open past the 15-minute mark; verify the authenticated session keeps working.
5. Force Hikari to open a new physical connection after the initial token expires; verify a new token is minted and the connection succeeds.
6. Revoke `rds-db:connect` in the test environment and verify new connections are rejected; existing sessions may keep running, so never rely on IAM edits as an instant session-kill switch.
7. Restore the policy and run a controlled failover/restart; measure pool recovery time and failed transactions.
8. If using RDS Proxy, test client IAM auth and target auth separately rather than extrapolating from direct DB connections.

Never run policy revocation or failover tests in production without an approved change plan and rollback path. The steps above are strictly for controlled staging environments.

## 12. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `FATAL: PAM authentication failed` or IAM auth rejected | User lacks IAM role/plugin, wrong token, or role lacks `rds-db:connect` | Verify DB user, policy ARN, Region, hostname, port, and token |
| `Access denied for user` on MySQL/MariaDB | User lacks proper auth plugin or SQL privileges | Verify engine-specific plugin and user grants |
| Token generates cleanly, but JDBC connect fails | Wrong security group, TLS, CA bundle, endpoint, or DB user | Test from the actual workload, enable TLS verify, and check hostname |
| Works at startup, new connections fail after 15 minutes | Token was generated once and configured as a static password | Mint a fresh token inside the DataSource per physical connect |
| Running pool keeps working past 15 minutes | Connections authenticated before token expiration | Expected behavior; tokens do not define session expiry |
| Hikari cannot open new connections | IAM credentials provider expired/not refreshing, policy changed, or wrong token endpoint | Check provider chain and mint fresh tokens per connect |
| Direct connect succeeds, Proxy fails | Token/ARN targets DB endpoint/resource instead of proxy, or proxy target auth misconfigured | Verify proxy client-auth and target-auth separately |
| Multiple errors after failover | Old physical connections dropped, pool not yet refreshed, or in-flight transactions aborted | Configure validation, sensible `maxLifetime`, idempotent retries, and staging drills |
| SQL `permission denied` after successful IAM login | IAM grants login only; DB user lacks SQL privileges | Grant schema/table/sequence privileges in SQL |
| `PKIX path building failed` or hostname mismatch | Missing/outdated CA bundle or URL uses alias/IP mismatching cert | Update CA bundle and use official DNS endpoint with `verify-full` |

## 13. Self-Practice Exercises

1. Author an `rds-db:connect` IAM policy allowing only DB user `reservation_app` on one RDS PostgreSQL instance; explain why the DB identifier cannot replace the resource ID in the ARN.
2. Create a PostgreSQL user, grant `rds_iam`, apply narrow SQL grants, and verify the user cannot access out-of-scope schemas.
3. Implement `RdsIamTokenProvider` using AWS SDK v2, generate two tokens at different times, and explain the hostname/port/Region/username parameters.
4. Wrap the token provider in a custom DataSource and configure HikariCP; prove tokens are generated only for new physical connections, not on every logical borrow.
5. Keep a connection alive past 15 minutes and then open a second connection; explain why the first keeps working while the old token fails on the second.
6. Switch from an RDS endpoint to an RDS Proxy endpoint; update the token hostname and IAM resource ARN; describe both client/proxy and proxy/database authentication hops.
7. Write tests simulating token generation failure, TLS error, and `AccessDenied`; determine which errors are retryable and which require config/permission fixes.
8. Run a staging test revoking and restoring IAM permissions; measure how long new connections and existing connections are affected.
9. Compare RDS IAM DB authentication with workload identity/connectors for Azure Database and Google Cloud SQL; identify portable application interfaces versus provider-specific token/driver/connection factory layers.

**Completion criteria:** learners can generate IAM tokens for the exact endpoint, explain `rds-db:connect` vs. SQL grants, configure TLS, wire a token provider into HikariCP, verify token refresh on new physical connections, and distinguish token expiration from connection lifetime.

## References

- [Amazon RDS — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html): supported engines, tokens, TLS, and limits.
- [Amazon RDS — Supported Regions and DB engines](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RDS_Fea_Regions_DB-eng.Feature.IamDatabaseAuthentication.html): engine/version/Region matrix for RDS.
- [Amazon Aurora — IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/UsingWithRDS.IAMDBAuth.html): Aurora engines, tokens, and specific limits.
- [Amazon RDS — Setting up IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.Connecting.html): DB user setup, IAM policies, and connecting.
- [Amazon RDS — IAM database authentication for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html): `rds_iam` role and SQL privileges.
- [Amazon RDS — IAM database authentication for MySQL and MariaDB](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.DBAccounts.html): authentication plugin and users.
- [AWS SDK for Java 2.x — Generate an IAM authentication token](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-rds.html): `RdsUtilities` and `GenerateAuthenticationTokenRequest`.
- [Amazon RDS Proxy — Setting up IAM authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html): client-to-proxy IAM auth and target config.
- [Amazon RDS Proxy — Connecting using IAM authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connecting.html): standard IAM vs. end-to-end IAM, resource ARNs, and endpoints.
- [Amazon RDS Proxy — Concepts and terminology](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html): both IAM auth models and backend connections.
- [Amazon RDS — SSL/TLS connections](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html): CA bundles and engine-specific TLS.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): pool sizing, connection lifecycle, and timeouts.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC, and HikariCP auto-configuration.
