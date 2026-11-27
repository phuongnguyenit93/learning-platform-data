# Minimal Connection Configuration in application.yml

## 1. What Does R2DBC Connection Configuration Include?

For a Spring Data R2DBC application to access a database, it needs the corresponding R2DBC driver and the connection details to create a `ConnectionFactory`. In Spring Boot, most connection configuration is typically declared in `application.yml` under the `spring.r2dbc` namespace.

A minimal configuration needs to specify:

- **R2DBC URL:** the driver type, host, port, and database to connect to.
- **Username:** the database account the application uses.
- **Password:** the corresponding password or credential.
- **Driver:** the R2DBC driver dependency must be present on the runtime classpath.

The example below uses PostgreSQL. The database name and account are examples; replace them with the values from your actual environment.

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

At startup, Spring Boot reads these properties and configures a `ConnectionFactory` based on the driver present in the application. Components such as Spring Data R2DBC, `R2dbcEntityTemplate`, and `DatabaseClient` can then use that `ConnectionFactory` to perform data operations.

`application.yml` only provides configuration values. It does not install the database server, create the database, create accounts, open network ports, or grant permissions to accounts. Those external prerequisites must be prepared separately.

## 2. Adding Spring Data R2DBC and Driver Dependencies

Before configuring the URL, the project must include Spring Data R2DBC and the driver for the database management system in use. Example with Gradle and PostgreSQL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

Maven example:

```xml
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
```

When using Spring Boot dependency management, let Spring Boot's BOM or plugin manage compatible versions instead of arbitrarily picking versions of Spring Data, Spring Framework, and Reactor yourself. The driver must also be compatible with the R2DBC SPI version used by the application.

A few common drivers:

| DBMS | Commonly used driver dependency | URL scheme |
| --- | --- | --- |
| PostgreSQL | `org.postgresql:r2dbc-postgresql` | `r2dbc:postgresql:` |
| H2 | `io.r2dbc:r2dbc-h2` | `r2dbc:h2:` |
| Microsoft SQL Server | `io.r2dbc:r2dbc-mssql` | `r2dbc:mssql:` |
| MySQL | Corresponding MySQL R2DBC driver, e.g., `io.asyncer:r2dbc-mysql` | `r2dbc:mysql:` |

Artifact names and URL options can vary by driver or version. Consult the documentation of the selected driver to verify the dependency, scheme, and driver-specific properties.

**Note:** A JDBC driver such as `org.postgresql:postgresql` does not substitute for an R2DBC driver. A JDBC URL such as `jdbc:postgresql://...` is not an R2DBC URL either. If the application accesses the database using Spring Data R2DBC, it needs a driver that implements the R2DBC SPI.

## 3. Understanding Properties Under `spring.r2dbc`

| Property | Meaning | Example |
| --- | --- | --- |
| `spring.r2dbc.url` | Connection URL formatted for the R2DBC driver | `r2dbc:postgresql://localhost:5432/customer_db` |
| `spring.r2dbc.username` | Database account username | `app_user` |
| `spring.r2dbc.password` | Password or credential | `${DB_PASSWORD}` |
| `spring.r2dbc.properties.*` | Additional driver-specific options | Driver-dependent |
| `spring.r2dbc.pool.*` | Connection pool configuration when using R2DBC Pool and a Boot version supporting these properties | `max-size: 10` |

In standard configuration, `url` is the most important property for Spring Boot to identify the driver and connection target. Username and password are supplied separately so credentials do not have to be embedded in the URL.

There is no need to declare `driver-class-name` as is commonly done with JDBC. The R2DBC driver is discovered from the runtime classpath and the URL scheme. If the driver is missing or the scheme is unsupported by the driver, Spring cannot create an appropriate connection factory.

### 3.1. PostgreSQL URL Structure

A basic PostgreSQL URL has the form:

```text
r2dbc:postgresql://<host>:<port>/<database>
```

Example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

Where:

- `r2dbc` indicates this is an R2DBC ecosystem URL.
- `postgresql` identifies the PostgreSQL driver.
- `localhost` is the database server in this local-machine example.
- `5432` is the default PostgreSQL port, though it can differ if the server is configured otherwise.
- `customer_db` is the name of the database already created on the server.

If the database runs in Docker Compose or on another server, `localhost` may not be the address to use. Inside a container, `localhost` points to that container itself. When containers share a Docker network, the application typically connects using the database service name and the service's internal port.

### 3.2. Example with H2

When using H2 over R2DBC, add the H2 R2DBC driver and choose a URL matching the desired database mode. An in-memory URL typically looks like:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///testdb
```

This is a configuration example for development or testing environments. The data lifecycle of an in-memory database depends on how the driver and connection are configured; when the application stops, the data may no longer exist. Do not use an in-memory database as a substitute for integration testing on the target DBMS if your application relies on SQL syntax, data types, or behavior specific to that DBMS.

## 4. Using Environment Variables to Manage Connection Credentials

Do not commit real passwords, tokens, or database credentials to Git. Spring Boot supports placeholders in YAML to read values from environment variables or external configuration sources.

Example `application.yml`:

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
```

The syntax `${VAR_NAME:default_value}` means use the environment variable if it is set; otherwise use the default value after `:`. In this example, the URL and username have convenient defaults for local development, while the password must be supplied via `R2DBC_PASSWORD`.

On PowerShell, you can set the variables for the current terminal session before running the application:

```powershell
$env:R2DBC_PASSWORD = "local-development-password"
$env:R2DBC_URL = "r2dbc:postgresql://localhost:5432/customer_db"
$env:R2DBC_USERNAME = "app_user"
./gradlew bootRun
```

On Linux or macOS:

```bash
export R2DBC_PASSWORD='local-development-password'
export R2DBC_URL='r2dbc:postgresql://localhost:5432/customer_db'
export R2DBC_USERNAME='app_user'
./gradlew bootRun
```

The example values above are only for a development machine. Staging and production environments should retrieve credentials from a secret manager or the deployment platform's secret management mechanism. Avoid writing passwords to logs, screenshots, committed configuration files, or command-line arguments that could be persisted.

Spring Boot also supports environment variables mapped directly from property names, such as `SPRING_R2DBC_URL`, `SPRING_R2DBC_USERNAME`, and `SPRING_R2DBC_PASSWORD`. This is useful when the deployment platform manages configuration directly via environment variables.

## 5. Separating Configuration by Environment

An application typically needs different configurations for local, test, staging, and production. You can use Spring Boot profiles to separate environment-specific settings.

Example `application.yml` keeping shared configuration and defaults for the local environment:

```yaml
spring:
  application:
    name: customer-service
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
```

An `application-test.yml` file can point to a test database:

```yaml
spring:
  r2dbc:
    url: r2dbc:h2:mem:///customer_test
```

Activate the `test` profile when running tests or starting the application:

```bash
SPRING_PROFILES_ACTIVE=test ./gradlew bootRun
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "test"
./gradlew bootRun
```

For production, you can keep the URL and username in deployment configuration while supplying the password through a secret store. Do not create a file containing production passwords inside the repository.

Spring Boot merges configuration from multiple sources according to precedence order. Environment variables and deployment arguments can override values in YAML. Therefore, when the application connects to the wrong database, check both the active profile and the environment variables passed to the process.

## 6. Configuring a Connection Pool When Needed

Each database access requires a connection. Repeatedly creating new connections can be costly in time and resources, so applications often use a connection pool to reuse connections.

R2DBC Pool is a separate component. If you want Spring Boot to create a pooled `ConnectionFactory`, you need a compatible `io.r2dbc:r2dbc-pool` dependency and pool configuration enabled as supported by the Spring Boot version in use.

Gradle example:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
    runtimeOnly("io.r2dbc:r2dbc-pool")
}
```

Example pool configuration:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-idle-time: 30m
      max-acquire-time: 5s
```

Meaning of commonly used properties:

| Property | Meaning |
| --- | --- |
| `enabled` | Enables pooled connection factory configuration if supported by the dependency and Boot version |
| `initial-size` | Number of initial connections created in the pool |
| `max-size` | Maximum number of connections the pool can allocate |
| `max-idle-time` | Duration a connection may remain idle before being evicted according to pool policy |
| `max-acquire-time` | Maximum time to wait for a connection before the acquire operation fails |

The values above are only examples to illustrate syntax. `max-size: 10` is not the right number for every application. When choosing pool size, consider the number of application instances, concurrent requests, connection hold duration, the database's connection limit, and the load from other services sharing the database.

For instance, if there are 4 application instances and each allows up to 20 connections, the maximum total connections from the application could reach 80. Account for connections from administrative tools, background jobs, and other applications to avoid exceeding the database limit.

Do not increase `max-size` solely because requests are slow. If queries hold connections for a long time due to missing SQL indexes or long-running transactions, enlarging the pool can put higher load on the database without fixing the root cause. Monitor acquire wait times, active connection counts, SQL execution times, and database-side limits before tuning.

If the application does not use a pool, you can omit the entire `pool` section and the `r2dbc-pool` dependency. There is no reason to declare pool properties when the project has no pooling component.

## 7. Driver-Specific Properties

Beyond URL, username, and password, each driver can support specific options such as SSL/TLS, application name, timeouts, or protocol parameters. Spring Boot lets you pass driver properties via `spring.r2dbc.properties` when supported by the driver and Boot version.

Illustrative example of where to declare them:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.example.internal:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
    properties:
      # Set properties according to the documentation of the driver you are using.
      # Specific names and values depend on the driver and version.
```

Do not guess and copy JDBC driver options into an R2DBC driver configuration. The two drivers may use different property names, value types, or SSL mechanisms. For connections over public networks or across infrastructure zones, consult the driver documentation and security policies to configure TLS, certificate verification, and hostname verification properly.

## 8. `application.yml` Does Not Generate Schema from Entities

Declaring `@Table`, `@Id`, and `@Column` tells Spring Data R2DBC how to map entities to tables and columns. Those annotations do not cause Spring Data R2DBC to automatically create or update table structures from entities like the automatic DDL generation commonly seen in some JPA/Hibernate setups.

Databases and schemas must be created using initialization scripts, migration tools, or database administration workflows. Spring Boot can run SQL scripts such as `schema.sql` and `data.sql` when SQL initialization is configured appropriately; exact capabilities and execution order depend on the Boot version and connection factory type.

For real-world applications, manage schema changes with versioned migrations so deployment environments share the same change history. Clearly determine whether your migration tool connects via JDBC or R2DBC, because many traditional migration tools require a separate JDBC driver and datasource. Adding JDBC for migrations does not turn a JDBC driver into an R2DBC driver.

## 9. Verifying That the Configuration Works

When the application starts successfully, Spring Boot typically creates a `ConnectionFactory` if the URL, driver, and basic configuration are valid. However, bean creation alone does not always prove the database is ready to accept queries; many errors only appear when an operation is actually subscribed to and executed.

You can test with a simple query via `DatabaseClient`:

```java
@Service
public class DatabaseHealthService {

    private final DatabaseClient databaseClient;

    public DatabaseHealthService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> ping() {
        return databaseClient.sql("SELECT 1 AS value")
                .map((row, metadata) -> row.get("value", Integer.class))
                .one();
    }
}
```

The `ping()` method returns `Mono<Integer>`. It describes the check operation; the query is only executed when the publisher is subscribed to. In a WebFlux application, the caller can return this publisher to the framework. In test code, you can subscribe or use a test-appropriate assertion utility to verify the returned value is `1`.

If the project includes Spring Boot Actuator and the corresponding R2DBC health indicator, the health endpoint can also provide a signal about connectivity. Configure endpoint exposure and protection appropriately for your deployment environment.

When testing connectivity, distinguish three things:

1. The application can read the YAML configuration.
2. Spring can create a `ConnectionFactory` from the driver and URL.
3. The application can actually acquire a connection, authenticate, and run a query on the database.

Only the third step verifies that the entire connection path is working at the time of the check.

## 10. Common Configuration Errors

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| Cannot create `ConnectionFactory` | Missing R2DBC driver, wrong URL scheme, or incompatible dependencies | Check runtime dependencies and the URL prefix `r2dbc:<driver>:` |
| Cannot connect to host | Wrong hostname, port, DNS, firewall, or database not running | Verify address from the application's actual runtime environment and check server status |
| Authentication failed | Wrong username/password, environment variable not provided, or locked account | Check variable names, profile, credentials, and login permissions |
| Database does not exist | URL points to a database that has not been created or has a typo | Check database name on the server and in the URL |
| Connection refused | Server not listening on the configured address/port or container not ready | Check port, bind address, container health, and startup order |
| Pool acquire timeout | Pool exhausted, connections held too long, or unresponsive database | Monitor active/idle/pending counts, query durations, and transactions |
| SQL works on this machine but fails on another | Different DBMS, dialect, schema, or driver version | Compare environments, actual SQL, schema, and driver |
| YAML not read as expected | Wrong indentation, inactive profile, or environment variable override | Check YAML structure, active profiles, and configuration source precedence |

### 10.1. Accidentally Using JDBC Configuration

A JDBC configuration typically looks like:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

That configuration is for `DataSource` and JDBC. For Spring Data R2DBC, connection properties must live under `spring.r2dbc` and the URL must use an R2DBC scheme:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/customer_db
    username: app_user
    password: ${DB_PASSWORD}
```

A project may intentionally use both JDBC and R2DBC—for instance, a migration component using JDBC while business flows use R2DBC. In that case, configure both stacks explicitly and understand they may use separate connection factories or pools. Do not set JDBC properties and expect reactive repositories to automatically use them.

### 10.2. Misusing `localhost` Inside Containers

If the application runs directly on the host machine and the database also runs on the host, `localhost` may work. However, if the application runs inside its own container, `localhost` points to the application container itself. When using Docker Compose, the URL typically uses the database service name, for example:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://postgres:5432/customer_db
```

Here `postgres` must be a service name or hostname resolvable from the application container. The container's internal port may differ from the port published to the host machine.

### 10.3. Passwords Containing Special Characters

When placing a password directly in YAML, characters such as `#`, `:`, `{`, or quotes can affect how YAML parses the value if not properly quoted. Using environment variables avoids encoding credentials inside YAML files. If you must declare a literal string containing special characters, wrap it in appropriate quotes and verify the loaded value after configuration binding.

## 11. Complete Configuration Example for Local Development

The following example combines the URL, credentials sourced from environment variables, and a connection pool. It requires the PostgreSQL R2DBC and `r2dbc-pool` dependencies as shown in earlier sections.

```yaml
spring:
  application:
    name: customer-service

  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/customer_db}
    username: ${R2DBC_USERNAME:app_user}
    password: ${R2DBC_PASSWORD}
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-idle-time: 30m
      max-acquire-time: 5s
```

Before running, ensure that:

- PostgreSQL is running and reachable from the machine running the application.
- The `customer_db` database already exists.
- The `app_user` account exists and has the required permissions on the database/schema.
- The `R2DBC_PASSWORD` variable has been set.
- The PostgreSQL R2DBC driver and R2DBC Pool dependencies are on the runtime classpath.
- Pool settings fit the connection limits and load of your environment.

## 12. Configuration Sequence for a New Project

When starting a Spring Data R2DBC application, you can follow this sequence:

1. Choose the database management system and corresponding R2DBC driver.
2. Add `spring-boot-starter-data-r2dbc` and the driver to the project dependencies.
3. Declare `spring.r2dbc.url`, `username`, and `password` in `application.yml` or an external configuration source.
4. Confirm the database exists, the account has access rights, and the network allows connections.
5. Add R2DBC Pool only if the project needs pooling; then configure limits based on load and database resources.
6. Create or apply the schema using appropriate scripts or migrations.
7. Run a probe query to verify the application actually connects and reads data.
8. Separate credentials and connection addresses by profile or environment variables for each deployment environment.

With Spring Data R2DBC, `application.yml` is where you declare how Spring Boot creates reactive connections to the database. Dependencies supply the driver that performs communication, the URL identifies the target and driver type, and username/password supply authentication credentials. When these parts align with the database environment, Spring Boot can create a `ConnectionFactory` for repositories, `R2dbcEntityTemplate`, and `DatabaseClient` to use in reactive pipelines.
