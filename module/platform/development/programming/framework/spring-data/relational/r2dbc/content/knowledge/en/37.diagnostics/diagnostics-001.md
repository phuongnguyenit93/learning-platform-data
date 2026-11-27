# Driver Not Found or ConnectionFactory Creation Failed

When starting a Spring Data R2DBC application, a common error is that Spring cannot find a suitable driver or fails to create the `ConnectionFactory` bean. Another group of errors appears after the application already has a `ConnectionFactory` but cannot open a connection to the database. These two groups of errors have similar symptoms in logs, but their root causes and resolutions are different.

**Diagnose in order: is the driver dependency on the runtime classpath, does the driver support the URL scheme, is the R2DBC configuration being read properly by Spring Boot, is the `ConnectionFactory` created, and only then check the actual connection and SQL query.** Do not start by changing the username/password or increasing the pool size when the application has not even found the driver.

Spring Data R2DBC requires an R2DBC implementation compatible with the database in use. A JDBC driver and JDBC URL cannot replace an R2DBC driver and R2DBC URL. `ConnectionFactory` is the abstraction for creating reactive connections; `DataSource` is the abstraction for JDBC. An application can use both technologies, but their configurations and beans are two separate paths.

## 1. Distinguishing Driver, ConnectionFactory, and Connection

These three components sit at different stages:

1. **R2DBC driver:** implementation of the R2DBC protocol for a specific database management system, such as PostgreSQL or MySQL.
2. **ConnectionFactory:** an object created by the driver from options/configuration; it is responsible for creating R2DBC `Connection` instances.
3. **Connection:** the actual connection session to the database, created when the application requests a connection from `ConnectionFactory`.

Overview of the initialization flow:

~~~text
Application configuration
        |
        v
R2DBC URL / ConnectionFactoryOptions
        |
        v
R2DBC ConnectionFactoryProvider discovery
        |
        v
Driver creates ConnectionFactory
        |
        v
ConnectionFactory.create()
        |
        v
Database connection
        |
        v
Execute SQL
~~~

Therefore, "driver not found" is usually a failure at the discovery or classpath step. "Cannot connect to database" usually happens after the factory exists, when the factory opens a connection. "Query error" happens later, when a statement is sent or results are read.

### 1.1. Common Error Messages

The exact exception name and wording depend on Spring Boot, Spring Framework, the R2DBC SPI, and the driver. Some indicators:

| Message or Symptom | Layer to Check First |
| --- | --- |
| No R2DBC ConnectionFactory available | Configuration or auto-configuration failed to create the factory |
| No ConnectionFactoryProvider found for driver ... | Missing driver or scheme not supported by the driver |
| Unable to create a ConnectionFactory from URL | Malformed URL, invalid scheme, or provider not found |
| Failed to determine a suitable driver class | Usually a JDBC auto-configuration message; check for mistaken DataSource/JDBC config |
| Connection refused | Database is not listening on host/port or network rejected the connection |
| UnknownHostException | DNS/hostname cannot be resolved |
| Authentication failed / password authentication failed | Connection reached the server, but authentication failed |
| Database does not exist | Server is reachable, but database name is wrong or has not been created |
| SSL handshake failed | Incompatible TLS mode, certificate, or trust configuration |
| Connection reset / connection closed | Network, server, proxy, pool, or driver closed the connection |

Do not classify an error from just the last line of a stack trace. Read the root cause and check whether the error occurs during bean creation, when calling create connection, or when executing SQL.

## 2. Adding the Right R2DBC Driver to the Runtime Classpath

Spring Data R2DBC does not include drivers for every database. The application must add the implementation corresponding to the database system being used.

Gradle example with PostgreSQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The examples are based on common dependency coordinates; you should use the version managed by Spring Boot dependency management/BOM if that driver is in the supported dependency set. Do not pick an old driver version manually or mix multiple R2DBC SPI versions without checking compatibility.

### 2.1. Some Common Drivers

| Database | Commonly Used R2DBC Artifact |
| --- | --- |
| PostgreSQL | org.postgresql:r2dbc-postgresql |
| MySQL | io.asyncer:r2dbc-mysql |
| MariaDB | org.mariadb:r2dbc-mariadb |
| H2 | io.r2dbc:r2dbc-h2 |
| Microsoft SQL Server | io.r2dbc:r2dbc-mssql |
| Oracle Database | com.oracle.database.r2dbc:oracle-r2dbc |

Artifacts and versions must be cross-checked against the official driver documentation, Spring Boot version, and R2DBC SPI compatibility. Some drivers have changed group/artifact coordinates or been replaced by newer maintained implementations.

### 2.2. The Driver Must Be Present at Runtime, Not Only Compile/Test

R2DBC looks up providers on the runtime classpath. If a driver is declared with a compile-only or test-only scope, the application may compile and pass some tests but fail to find the provider when running in production.

With Gradle, check:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

To see which specific dependency was selected:

~~~powershell
.\gradlew.bat dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
~~~

With Maven:

~~~powershell
mvn dependency:tree -Dincludes=org.postgresql:r2dbc-postgresql
~~~

Verify the output of the runtime classpath and the final packaged artifact. Do not just look at `build.gradle` and assume the dependency is inside the executable JAR/container.

### 2.3. Do Not Use a JDBC Driver Instead of an R2DBC Driver

The following two dependencies are not equivalent:

~~~kotlin
runtimeOnly("org.postgresql:postgresql")       // JDBC driver
runtimeOnly("org.postgresql:r2dbc-postgresql") // R2DBC driver
~~~

A JDBC driver implements the `java.sql` API and creates a JDBC `DataSource`/`Connection`. An R2DBC driver implements the R2DBC SPI and creates a reactive `ConnectionFactory`/`Connection`.

If the application uses both JDBC and R2DBC, both dependencies may be needed. However, adding the PostgreSQL JDBC driver does not automatically give Spring Data R2DBC a PostgreSQL `ConnectionFactory`.

### 2.4. Check for Excluded or Conflicting Dependencies

A driver can be omitted due to:

- exclusions in Gradle/Maven.
- dependency conflicts causing a different version to be selected.
- multi-module setups where the driver is only added to a test module.
- packaging/shading stripping service metadata.
- an image/container running a different artifact than the one tested.

Inspect the dependency tree and the contents of the deployed JAR. If using a custom classloader, plugin architecture, or native image, confirm that the provider discovery mechanism still works in that environment.

## 3. The R2DBC URL Must Use the Correct Scheme

An R2DBC URL contains a scheme so the provider knows which driver should handle it.

PostgreSQL example:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/appdb
spring.r2dbc.username=app_user
# Inject spring.r2dbc.password from a secret store
~~~

JDBC URL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/appdb
~~~

The two URLs serve different purposes. Putting `jdbc:postgresql` into `spring.r2dbc.url` will prevent the R2DBC provider from recognizing the scheme.

### 3.1. Parts of the URL

Example:

~~~text
r2dbc:postgresql://db.example.internal:5432/orders
~~~

It can be parsed into:

- R2DBC prefix: `r2dbc:`
- Driver protocol: `postgresql`
- Host: `db.example.internal`
- Port: `5432`
- Database: `orders`

The driver scheme must match a provider added to the classpath. For example, if the URL uses `postgresql` while runtime only has a MySQL driver, no matching provider will be found.

### 3.2. Do Not Add the `jdbc` Prefix Manually

Avoid:

~~~properties
spring.r2dbc.url=jdbc:postgresql://localhost:5432/appdb
~~~

Correct:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/appdb
~~~

Similarly, JDBC URLs for MySQL or SQL Server cannot be used directly for R2DBC either. Check the URL format for the specific driver.

### 3.3. Credentials Should Be Configured Separately

Spring Boot usually lets you set username/password via the `spring.r2dbc.username` and `spring.r2dbc.password` properties. Do not commit real passwords to source control. Use environment variables or a secret manager. If the URL also contains credentials, avoid logging the full URL because it can expose authentication details.

### 3.4. Driver-Specific Options

Some drivers support query parameters or driver-specific options for SSL, schema, socket, timezone, application name, and other features. Syntax and option names differ between drivers.

Do not copy parameters from a JDBC URL to an R2DBC URL without checking the driver documentation. If an option is unsupported, it may be rejected or fail to take effect as expected.

## 4. Spring Boot Configuration for R2DBC

In a Spring Boot application, the standard configuration usually uses the `spring.r2dbc` prefix:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    # Inject password from environment or secret manager
~~~

Spring Boot can auto-configure a `ConnectionFactory` when:

- R2DBC infrastructure is on the classpath.
- Appropriate URL/connection options are configured.
- A provider matching the driver protocol is present.
- No custom `ConnectionFactory` bean is already declared by the application, which would cause auto-configuration to back off.

Exact conditions and properties depend on the Spring Boot version.

### 4.1. Do Not Confuse `spring.datasource` with `spring.r2dbc`

JDBC properties:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/appdb
    username: app_user
~~~

do not auto-configure an R2DBC `ConnectionFactory`.

R2DBC properties:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
~~~

do not auto-configure a JDBC `DataSource`. If the application uses both, configure both appropriately for their respective purposes.

### 4.2. Profiles Can Override Configuration

An application may have `application.yml`, `application-local.yml`, `application-test.yml`, and environment variables. An active profile or environment variable may override the URL the developer is looking at.

Check:

- Which profile is active?
- Which ConfigMap/Secret is mounted in the container?
- Does an environment variable override `spring.r2dbc.url`?
- Is there a different URL configured in tests or deployment manifests?
- Do startup logs show the expected profile and configuration sources?

When debugging, only log host, port, database, and driver protocol after stripping credentials/secrets. Do not print the raw URL if it contains a username/password.

### 4.3. Environment Variables

Spring Boot relaxed binding typically maps environment variables as:

~~~text
SPRING_R2DBC_URL
SPRING_R2DBC_USERNAME
SPRING_R2DBC_PASSWORD
~~~

Check the variable names in the deployment environment and how the platform injects secrets. A typo in a variable name can cause the application to fall back to default settings or have no URL.

## 5. Understanding Spring Boot Auto-Configuration and the ConnectionFactory Bean

Spring Boot can create a `ConnectionFactory` from configuration if the application has not provided a suitable bean. If the project declares a `ConnectionFactory` manually, auto-configuration may back off and stop using the properties the developer expects.

### 5.1. Checking Whether a ConnectionFactory Bean Exists

One way to check inside the application context:

~~~java
@Component
public class ConnectionFactoryDiagnostics implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public ConnectionFactoryDiagnostics(
            ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("R2DBC ConnectionFactory metadata: {}",
                connectionFactory.getMetadata().getName());
    }
}
~~~

If the application fails to start because the bean is missing, constructor injection cannot run either. In that case, inspect the condition evaluation report or auto-configuration logs to see why the bean was not created.

Do not log the full options if they may contain a password.

### 5.2. Enabling the Condition Evaluation Report

When you need to diagnose auto-configuration, you can start with the debug report using Spring Boot's mechanism, for example:

~~~powershell
.\gradlew.bat bootRun --args="--debug"
~~~

Or enable the appropriate debug logging. The condition evaluation report shows which auto-configurations matched or did not match and why. Read the R2DBC/ConnectionFactory section instead of only looking for the last error line.

### 5.3. Checking Manually Defined Beans

Search the codebase for:

- `@Bean` returning `ConnectionFactory`.
- `@Bean` returning `ConnectionPool`.
- `AbstractR2dbcConfiguration`.
- Custom `R2dbcEntityOperations`/`DatabaseClient`.
- Multi-database configuration or a routing `ConnectionFactory`.

If there is a manual bean, confirm that it uses the right URL/options and is not being replaced by another bean. Avoid creating multiple unnecessary `ConnectionFactory` instances or nested pools.

### 5.4. When Using Multiple Databases

A multi-database application can have multiple `ConnectionFactory` and transaction manager beans. Bean names and qualifiers must be specified accurately for `DatabaseClient`, repositories, and transaction managers.

If a routing `ConnectionFactory` uses a tenant key, ensure the target map has valid providers/factories and that no default factory accidentally routes all tenants to the wrong database.

## 6. Creating a ConnectionFactory Manually to Isolate the Error

The R2DBC SPI provides a mechanism to parse options and look up a provider by driver protocol. Standalone test example:

~~~java
ConnectionFactoryOptions options =
        ConnectionFactoryOptions.parse(
                "r2dbc:postgresql://localhost:5432/appdb");

ConnectionFactory connectionFactory =
        ConnectionFactories.get(options);
~~~

If the error occurs right at `ConnectionFactories.get`, focus on the URL, provider discovery, and runtime classpath. If creating the factory succeeds but `factory.create()` fails, move on to checking the real connection.

You do not need to put this snippet into production; it is a way to isolate the cause while debugging.

### 6.1. Checking Metadata Without Opening a Connection

After creating the factory:

~~~java
String driverName = connectionFactory.getMetadata().getName();
~~~

Metadata helps confirm which driver the factory belongs to. It does not prove the database is running or the credentials are valid.

### 6.2. Smoke Test with ConnectionFactory

You can try creating and closing a connection:

~~~java
Mono<Void> verifyConnection(ConnectionFactory factory) {
    return Mono.from(factory.create())
            .flatMap(connection -> Mono.from(connection.close()));
}
~~~

In a reactive test:

~~~java
StepVerifier.create(verifyConnection(connectionFactory))
        .verifyComplete();
~~~

If the smoke test fails, inspect the root cause across driver, network, authentication, TLS, and database. Do not call `block` on the event loop or on production request-handling paths.

## 7. Distinguishing Factory Creation Errors from Connection Opening Errors

This is the most important distinction when reading logs.

### 7.1. Errors During ConnectionFactory Creation

Example causes:

- Missing driver dependency.
- Wrong driver protocol in the URL.
- Unparseable URL.
- Provider not registered properly.
- Driver version incompatible with the R2DBC SPI.
- Custom configuration passing an invalid option.
- Pool requested, but pool dependency is missing.

At this stage, no connection to the database has necessarily been attempted. Changing the username/password usually does not fix a missing-provider error.

### 7.2. Factory Created, but `create` Connection Fails

Example causes:

- Database is not running.
- Wrong host/port.
- DNS does not resolve.
- Firewall, security group, or container network blocks the connection.
- Database has not been created yet.
- Wrong username/password.
- User lacks `CONNECT` privilege or required schema privileges.
- Incorrect SSL/TLS mode or certificate.
- Server reached connection limit or rejected the session.

At this stage, the driver has been found and the factory has been created. Test connectivity from the actual application runtime environment, not just from the developer laptop.

### 7.3. Connection Opens, but SQL Fails

Examples:

- Table does not exist.
- Wrong schema/search path.
- User lacks `SELECT`/`INSERT`/`UPDATE` privileges.
- Incorrect SQL dialect or syntax.
- Bind parameter incompatible with column type.
- Constraint, transaction, or lock causing an error.

This is no longer a driver discovery error. Check migrations, schema, SQL, and database permissions.

## 8. Checking Network and Database from the Application Runtime Environment

If the factory is created but a connection cannot be opened, check along the network path:

1. Does the hostname resolve inside the container/pod?
2. Is the database port reachable from the workload?
3. Is the database listening on that interface?
4. Do the firewall/security group/network policy allow it?
5. Does the database accept more connections?
6. Are TLS/certificates configured correctly?
7. Are credentials and database permissions valid?

Do not use connectivity results from a developer machine to conclude that a production container can also connect. DNS, routes, secrets, and network policies may differ.

### 8.1. Host in Docker Compose

If the application and database run in the same Docker Compose network, the hostname is usually the service name, such as `postgres`, not `localhost`.

~~~yaml
services:
  app:
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://postgres:5432/appdb
  postgres:
    image: postgres:16
~~~

Inside the `app` container, `localhost` points to the `app` container itself. Only use `localhost` if the database actually runs in the same network namespace or the port is forwarded appropriately.

### 8.2. Kubernetes Service DNS

In Kubernetes, the host is usually the in-cluster Service DNS name, such as:

~~~text
postgres.database.svc.cluster.local
~~~

Check the namespace, Service, Endpoints/EndpointSlice, NetworkPolicy, and secret mounts. Do not hardcode pod IPs in configuration because pods can change.

### 8.3. The Database Container Might Not Be Ready Yet

In some Compose setups, container startup order does not always guarantee the database is ready to accept connections. Use health checks/readiness and a bounded startup retry mechanism. Do not retry indefinitely, which can cause application startup to hang without a clear status.

## 9. Checking Credentials, Database, and Permissions

After confirming that host/port are reachable:

- Is the username correct for the running environment?
- Is the password secret mounted and non-empty?
- Does the database name exist?
- Does the user have permission to connect to the database?
- Does the user have permissions on the required schemas/tables?
- Is SSL or a client certificate required?
- Does the password contain special characters that break the URL if embedded directly?

Put credentials in separate properties or a secret store instead of concatenating them into the URL. If the driver supports multiple authentication mechanisms, verify the exact mechanism configured.

### 9.1. Successful Authentication Does Not Mean Queries Have Privileges

A user may be able to connect to the database yet lack `SELECT` permission on a table or permission to use a schema. In that case, `ConnectionFactory` and `Connection` both work; errors only appear when running SQL.

### 9.2. Checking Database Name and Schema

Some drivers connect to the server and fail when the database name is wrong. Some database systems allow connecting to a default database, and then queries fail because the schema/search path is wrong. Distinguish handshake errors from errors when querying metadata or tables.

## 10. SSL/TLS and Certificates

In production environments, the database may enforce TLS. SSL configuration for an R2DBC driver can differ from a JDBC driver. Common issues:

- Driver is using the wrong SSL mode.
- CA certificate is not trusted yet.
- Hostname in the certificate does not match.
- Client certificate/key is in the wrong format or has wrong file permissions.
- Incompatible TLS protocol/cipher.
- Container is missing the required CA bundle.

Do not disable certificate verification as a long-term production fix. When diagnosing, verify the trust chain and hostname validation per the driver documentation, then configure the CA/certificate properly.

Do not log private keys, passwords, or secret contents when debug is enabled.

## 11. Pool Configuration and Pool Initialization Errors

If the application uses an R2DBC connection pool, distinguish between:

- The underlying driver factory.
- The pool factory wrapping the underlying factory.
- A connection acquired from the pool.

A pool creation error can result from a missing `r2dbc-pool` dependency, invalid min/max size configuration, or failure to create the target factory. An acquire timeout error, on the other hand, usually happens when the pool has no available connection within the allowed time.

### 11.1. Checking the Pool Dependency

If configuring `ConnectionPool` manually, confirm the pool dependency is on the runtime classpath. If relying on Spring Boot auto-configuration, check the Boot version and corresponding pool properties. Do not add a pool dependency just to fix a database driver provider error.

### 11.2. Checking Pool Size and Acquire Timeout

Settings such as initial size, max size, max acquire time, and max create connection time must be valid for the API/version in use.

A pool max size that is too small can cause acquire timeouts under load. A pool max size that is too large can exhaust database connections. Calculate total pooled connections across all replicas:

~~~text
potential database connections
    = application replicas x pool max size
      + workers + migration + monitoring + administration
~~~

Do not increase max size before checking connection hold time, query latency, and server limits.

### 11.3. Avoid Creating Nested Pools

Do not wrap an existing `ConnectionPool` in another `ConnectionPool` without a clear reason. Nested pools complicate lifecycle management, metrics, and timeouts; a connection in the outer pool can hold a connection from the inner pool for too long.

## 12. Version Compatibility and Dependency Alignment

R2DBC consists of the SPI and multiple implementations. If dependencies use incompatible versions, errors may occur when loading providers, creating factories, or running queries.

Check:

- Spring Boot version.
- Spring Framework/Spring Data versions managed by Boot.
- R2DBC SPI version.
- R2DBC driver version.
- R2DBC pool version if used.
- Java runtime version.

### 12.1. Prefer Spring Boot Dependency Management

If using the Spring Boot BOM/plugin, prefer letting Boot manage versions of supported dependencies. Avoid manually declaring versions for every artifact unnecessarily.

If you need to override a driver, verify the driver's compatibility matrix with the R2DBC SPI and database version. Document the reason for the override and test in a production-like runtime.

### 12.2. Do Not Mix Old and New R2DBC APIs Arbitrarily

Some online examples use packages or APIs from older versions. When copying code, check:

- Does the imported package exist in the project's version?
- Have interfaces/methods changed?
- Does the driver support the SPI version the application is using?
- Are two versions of the same artifact present on the classpath?

Compile errors and runtime provider discovery errors can both stem from mismatched dependency alignment.

## 13. Creating a ConnectionFactory Manually

In simple applications, Spring Boot auto-configuration is usually sufficient. When multiple databases, routing, or special driver options are needed, the factory can be created manually.

General example:

~~~java
@Configuration
public class R2dbcConfiguration {

    @Bean
    ConnectionFactory connectionFactory() {
        ConnectionFactoryOptions options =
                ConnectionFactoryOptions.builder()
                        .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                        .option(ConnectionFactoryOptions.HOST, "localhost")
                        .option(ConnectionFactoryOptions.PORT, 5432)
                        .option(ConnectionFactoryOptions.DATABASE, "appdb")
                        .option(ConnectionFactoryOptions.USER, "app_user")
                        .option(ConnectionFactoryOptions.PASSWORD, "secret")
                        .build();

        return ConnectionFactories.get(options);
    }
}
~~~

This is an illustrative configuration. In production, credentials must come from externalized configuration/secret stores, not hardcoded in source.

### 13.1. When Declaring the Bean Manually, Check Auto-Configuration Backoff

If the application defines a `ConnectionFactory` bean, Spring Boot may stop creating the automatic bean. This can cause changes to `spring.r2dbc.url` to have no effect even though the developer expects them to.

Inspect the actual injected bean, driver metadata, and option sources used. Do not look only at `application.yml`.

### 13.2. Do Not Create a ConnectionFactory per Request

`ConnectionFactory` is an infrastructure object with an application-level lifecycle. Do not create a new factory or pool per HTTP request. Doing so causes connection churn, resource leaks, and loses pooling benefits.

For multi-tenant database routing, manage factories via a tenant registry/lifecycle; do not create unbounded pools per tenant without eviction and a global cap.

## 14. Testing with DatabaseClient After the Factory Works

Once you have a `ConnectionFactory` and can open a connection, you can run a lightweight query to verify the database session:

~~~java
DatabaseClient databaseClient =
        DatabaseClient.create(connectionFactory);

Mono<Integer> ping = databaseClient
        .sql("SELECT 1")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one();
~~~

This query is only a smoke test; syntax and result type may need adjustment per database. It does not prove the entire schema, table permissions, or migrations are correct.

### 14.1. Checking Schema After Ping Succeeds

Next, check:

- Current database/schema.
- `SELECT` permissions on the required tables.
- Tables and columns created by migrations.
- Search path/schema mapping.
- Driver type mapping for key columns.

If `SELECT 1` succeeds but a repository query fails, the issue usually lies in schema, SQL, permissions, or mapping rather than driver discovery.

## 15. Diagnosing by Environment

### 15.1. Local Development

Check the database process/container, port mapping, local profile, URL scheme, and credentials. Use auto-configuration debug logs when there is no `ConnectionFactory` bean.

### 15.2. Automated Tests

Ensure the driver is on the test runtime classpath and Testcontainers has started before the application context creates the `ConnectionFactory`. If a test slice does not load production configuration, import the appropriate R2DBC configuration.

Do not use H2 R2DBC to emulate PostgreSQL if the test needs to verify the PostgreSQL driver, native types, or SQL dialect.

### 15.3. Docker/Kubernetes

Check DNS/service names, network policies, secret mounts, active profiles, ports, readiness, and database max connections from inside the workload.

Ensure the deployed artifact has the same runtime dependencies as the tested artifact.

### 15.4. Production

Do not enable logs containing credentials or full connection URLs. Collect the root cause, driver metadata, masked host/database, profile, connection pool metrics, and database health. Perform checks using least-privilege permissions.

## 16. Diagnostic Decision Tree

~~~text
Application has no ConnectionFactory?
|
+-- Yes
|   |
|   +-- Is the R2DBC driver on runtimeClasspath?
|   |      |
|   |      +-- No -> add the right driver dependency
|   |      |
|   |      +-- Yes
|   |           |
|   |           +-- Does URL use r2dbc:<driver>?
|   |           |      |
|   |           |      +-- No -> fix scheme/URL
|   |           |      |
|   |           |      +-- Yes -> check provider discovery,
|   |           |                versions, and auto-configuration
|   |
|   +-- Is there a manual ConnectionFactory bean?
|          |
|          +-- Yes -> inspect that bean and auto-config backoff
|          +-- No -> check condition evaluation report
|
+-- No, but opening connection fails
    |
    +-- Check host, port, DNS, and network
    +-- Check database name and server status
    +-- Check credentials, permissions, and SSL/TLS
    +-- Check connection limits and pool
    |
    +-- Connection opens, but SQL fails?
           |
           +-- Check schema, migrations, permissions,
               query, bind parameters, and type mapping
~~~

## 17. Common Errors and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No ConnectionFactoryProvider found | Missing R2DBC driver or wrong URL scheme | Check `runtimeClasspath` and protocol |
| Only PostgreSQL JDBC dependency present | Confused JDBC with R2DBC | Add PostgreSQL R2DBC driver |
| Compiles locally, but no provider in production | Driver only in test/compile scope or stripped during packaging | Inspect runtime artifact |
| URL starts with `jdbc:` | JDBC URL used in `spring.r2dbc.url` | Change to `r2dbc:<driver>` URL |
| Boot does not create ConnectionFactory | Missing URL, driver, or auto-config did not match | Check condition report and config profile |
| Changing URL has no effect | Manual `ConnectionFactory` bean caused auto-config backoff | Inspect injected bean and options |
| Connection refused | DB not running, wrong port, or network rejected | Check from inside container/pod |
| UnknownHostException | Wrong DNS/service name | Check DNS and network |
| Authentication failed | Wrong username/password or auth mode | Check secret and database user |
| Database not found | Wrong/uncreated database name | Create database or fix URL |
| SSL handshake failure | Wrong CA, certificate, hostname, or SSL mode | Configure TLS per driver docs |
| Acquire timeout | Pool out of connections or connections held too long | Check pending, hold time, and DB capacity |
| Factory created, but query fails | Schema, permissions, SQL, or type mapping | Run smoke query and inspect migrations |
| Works locally, fails on deploy | Different profile, secret, DNS, or artifact | Compare runtime config and dependencies |
| Passes with H2, fails on PostgreSQL | Different dialect, driver, or native type | Test with real PostgreSQL via Testcontainers |
| Fails after version upgrade | Incompatible driver/SPI/Spring dependency | Inspect dependency tree and BOM |

## 18. Testing Configuration and Connectivity

There should be multiple layers of testing:

### 18.1. Checking Dependency/Runtime Artifact

CI can inspect the dependency tree or boot the application context with the right runtime profile. The goal is to catch a missing driver before deployment.

### 18.2. Context Test

Boot the Spring context with the R2DBC configuration and verify that the `ConnectionFactory` bean exists and its driver metadata is correct. This context test does not necessarily prove the database is ready if connections are opened lazily.

### 18.3. Integration Test with the Same Database Type

Use Testcontainers or a test database of the same type as production. Verify:

1. Driver provider is discovered.
2. `ConnectionFactory` is created.
3. Connection opens successfully.
4. Smoke query succeeds.
5. Migrations/schema and table permissions are correct.
6. Repository save/find works.
7. Connection is closed/returned to the pool after the test.

### 18.4. Testing Intentional Configuration Errors

You can have tests for a wrong URL scheme or missing driver in a separate configuration module. Confirm that the error message is clear enough to distinguish provider discovery from connection failure. Do not break the main runtime classpath just to create a negative test.

### 18.5. Do Not Turn Readiness Probes into Heavy Queries

A readiness check can confirm the application is ready to receive traffic. If each probe runs a complex query or opens a new connection, probes can increase database load. Use a lightweight query at a reasonable frequency; distinguish liveness from readiness.

## 19. Checklist Before Reporting a Driver or ConnectionFactory Bug

- [ ] `spring-boot-starter-data-r2dbc` or corresponding Spring Data R2DBC configuration is present.
- [ ] Correct driver for the database in use is present.
- [ ] Driver is on the runtime classpath and in the executable artifact.
- [ ] JDBC driver is not confused with R2DBC driver.
- [ ] URL uses the correct `r2dbc:<driver>` scheme.
- [ ] Host, port, and database name are correct.
- [ ] Active profile and environment variables are confirmed.
- [ ] No custom `ConnectionFactory` bean is misconfigured or causing auto-config backoff.
- [ ] R2DBC SPI, driver, and Spring versions are compatible.
- [ ] If pooling is used, dependency and pool options are valid.
- [ ] Hostname/port are reachable from the application environment itself.
- [ ] Credentials, database permissions, and SSL/TLS are correct.
- [ ] Factory creation, connection creation, and SQL execution errors have been distinguished.
- [ ] Smoke test has been run against the real database/driver.
- [ ] Passwords, tokens, or URLs containing secrets are not logged.

## 20. Step-by-Step Troubleshooting Procedure

1. Read the root cause and determine whether the failure occurs at startup, factory creation, connection creation, or SQL.
2. Inspect the runtime dependency tree and confirm the driver matches the database.
3. Check the R2DBC URL scheme, host, port, and database name.
4. Check `spring.r2dbc.*` and the active profile/secrets.
5. Check whether there is a manual `ConnectionFactory` bean or routing factory.
6. Inspect the condition evaluation report if Spring Boot did not create the bean.
7. If the factory exists, check DNS, network, server, credentials, and TLS.
8. If a connection opens, run `SELECT 1`, then check schema/permissions/migrations.
9. If using a pool, check acquire/create timeouts and metrics.
10. Run integration tests against the same database/driver type as production.

Change one variable at a time and record the result. Do not change URL, driver version, pool size, and SSL mode simultaneously, as it will be difficult to tell which change resolved the root cause.

## 21. Conclusion

An R2DBC driver-not-found error and a database connection failure are two different stages. The driver must be on the runtime classpath and support the R2DBC URL scheme; Spring Boot must read `spring.r2dbc.*` properly or the application must build a valid `ConnectionFactory`. JDBC drivers, `DataSource`, and `jdbc:` URLs cannot replace R2DBC drivers, `ConnectionFactory`, and `r2dbc:` URLs.

Once the factory is created, move on to checking host, port, DNS, network, database name, credentials, permissions, and TLS. If a connection opens but SQL fails, check schema, migrations, query, and mapping. If pooling is used, distinguish pool creation/connection acquisition errors from driver discovery errors.

Finally, verify each layer with the dependency tree, condition evaluation report, `ConnectionFactory` metadata, a smoke query, and integration tests on a production-equivalent database. Stage-by-stage diagnosis helps fix the true cause, avoids unrelated changes to credentials or pools, and keeps secrets out of logs.
