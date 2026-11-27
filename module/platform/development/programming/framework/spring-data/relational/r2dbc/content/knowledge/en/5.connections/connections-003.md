# Configuring Host, Port, Database Name, and Credentials

For Spring Data R2DBC to connect to a relational database, the application needs to know where the server is running, which port accepts connections, which database will be used, and which account has access permissions. In Spring Boot, this information is typically declared via `spring.r2dbc` configuration in `application.yml` or `application.properties`. Spring Boot uses that configuration to create a `ConnectionFactory`, the component representing the R2DBC connection source used by repositories, `R2dbcEntityTemplate`, and `DatabaseClient`.

Configuring these four pieces of information properly is the foundational step of connectivity. If the host or port is wrong, the application cannot reach the server. If the database name is wrong, the server may accept the connection but refuse to open the requested database. If the username or password is wrong, authentication fails. If a JDBC URL is used by mistake, the R2DBC driver is missing, or the wrong environment is configured, Spring Data R2DBC also cannot initialize connections as expected.

## 1. The Four Basic Pieces of Connection Information

| Component | Meaning | Example |
| --- | --- | --- |
| Host | DNS name or IP address of the database server reachable from the application's runtime environment | `localhost`, `db.internal.example`, `10.20.0.15` |
| Port | TCP port on which the database service listens | PostgreSQL commonly uses `5432`; MySQL commonly uses `3306` |
| Database (database name) | Database or catalog that the connection will use | `orders`, `customer_service` |
| Credentials | Account and password used by the server for authentication and authorization | username `orders_app`, password loaded from a secret |

The default port values in the table are only common conventions. Administrators can configure servers to listen on different ports. Always take values from the actual deployment configuration rather than guessing the port based solely on the database type.

Beyond these four pieces of information, real environments may need TLS/SSL, timeouts, schema, driver-specific parameters, and connection pool configuration. Those settings supplement basic connection configuration; they do not replace host, port, database, and credentials.

## 2. Distinguishing R2DBC URLs from JDBC URLs

R2DBC uses URLs with the `r2dbc:` scheme. PostgreSQL example:

```text
r2dbc:postgresql://db.example.internal:5432/orders
```

This URL specifies the PostgreSQL R2DBC driver, host `db.example.internal`, port `5432`, and database `orders`.

The corresponding JDBC URL typically looks like:

```text
jdbc:postgresql://db.example.internal:5432/orders
```

The two URLs cannot be used interchangeably. Spring Data R2DBC needs a driver implementing the R2DBC SPI and a suitable `r2dbc:` URL. `spring.datasource.url` configuration, JDBC drivers, or HikariCP pools belong to the traditional JDBC model and do not automatically configure a `ConnectionFactory` for R2DBC.

Some common R2DBC schemes:

| Database system | Example URL |
| --- | --- |
| PostgreSQL | `r2dbc:postgresql://localhost:5432/orders` |
| MySQL | `r2dbc:mysql://localhost:3306/orders` |
| MariaDB | `r2dbc:mariadb://localhost:3306/orders` |

The scheme and options after `?` depend on the specific driver. Use the right driver for your database engine and consult the driver documentation when additional parameters such as TLS, sockets, or authentication modes are needed.

## 3. Declaring Connections in `application.yml`

With Spring Boot, the common approach is to declare the URL, username, and password under `spring.r2dbc`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
```

In this example:

- `url` contains the driver scheme, host, port, and database name.
- `username` is the account used to authenticate with PostgreSQL.
- `password` is read from the `DB_PASSWORD` environment variable instead of writing the password directly into the configuration file.

Spring Boot reads these properties and auto-configures `ConnectionFactory` if a matching R2DBC driver is on the classpath. When the application uses Spring Data R2DBC, repositories and `R2dbcEntityTemplate` can use that auto-configured connection infrastructure.

You can parameterize host, port, and database as environment variables so a single configuration file can be shared across environments:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

Expressions like `${ENV_VAR:default_value}` instruct Spring to read the environment variable if present, or otherwise fall back to the default value after `:`. The example above is convenient for local development machines. For deployed environments, explicitly supply the required variables and avoid using default accounts or passwords with broad privileges.

If `DB_PASSWORD` is absent, a placeholder `${DB_PASSWORD}` without a default value can prevent the application from resolving configuration. This is usually the desired behavior in environments requiring mandatory secrets: the application fails fast and reports missing configuration rather than silently using an empty password.

## 4. Equivalent Configuration in `application.properties`

If the project uses properties files instead of YAML, the properties can be declared as follows:

```properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/orders
spring.r2dbc.username=orders_app
spring.r2dbc.password=${DB_PASSWORD}
```

Example with host, port, and database sourced from environment variables:

```properties
spring.r2dbc.url=r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
spring.r2dbc.username=${DB_USERNAME:orders_app}
spring.r2dbc.password=${DB_PASSWORD}
```

Choose YAML or properties according to project conventions. There is no need to declare the same configuration in both files, as that can cause confusion when verifying the final values used by the application.

## 5. Installing the R2DBC Driver Dependency

Declaring the URL alone is not enough. The application needs the R2DBC driver dependency for the database engine in use. Example with Maven and PostgreSQL:

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

Spring Boot versions usually manage dependency versions through dependency management/BOM. If a project uses Spring Boot, let the BOM manage compatible versions rather than picking an arbitrary driver version. With Gradle, declare the equivalent dependencies using `implementation` or an appropriate runtime configuration.

An R2DBC driver is not a JDBC driver. For example, `org.postgresql:postgresql` is the PostgreSQL JDBC driver; it does not replace `org.postgresql:r2dbc-postgresql` when the application needs an R2DBC connection.

If using an R2DBC connection pool, the corresponding pool library must be on the classpath. Spring Boot can auto-configure pooling when the pool dependency is present and pooling is enabled. Pool configuration is covered in a later section.

## 6. Configuration by Database Engine

### PostgreSQL

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

The commonly used driver is `org.postgresql:r2dbc-postgresql`. PostgreSQL's common default port is `5432`, though you must use the port published by your server or managed database service.

### MySQL

```yaml
spring:
  r2dbc:
    url: r2dbc:mysql://${DB_HOST:localhost}:${DB_PORT:3306}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

The commonly used driver is `io.asyncer:r2dbc-mysql` in projects using current MySQL R2DBC drivers. Check the documentation and dependency management of the driver version chosen by the project; do not substitute the MySQL JDBC driver.

### MariaDB

```yaml
spring:
  r2dbc:
    url: r2dbc:mariadb://${DB_HOST:localhost}:${DB_PORT:3306}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
```

MariaDB has its own R2DBC driver. Do not assume all MySQL URL options apply identically to MariaDB; connection parameters and TLS must follow the documentation of the driver in use.

## 7. Understanding the Right Host in Each Environment

The value `localhost` means the machine or network namespace where the application process is running. Therefore, the correct host depends on deployment topology:

| Environment | Commonly used host | Explanation |
| --- | --- | --- |
| Application runs directly on the dev machine, database also runs on that machine | `localhost` or `127.0.0.1` | Connects over the development machine's loopback |
| Application and database run in the same Docker Compose network | Database service name, e.g. `postgres` | Containers on the same network resolve each other by service name |
| Application runs in a container, database runs on the host machine | Platform-appropriate host gateway name, e.g. `host.docker.internal` on supported environments | `localhost` inside a container points to the application container itself |
| Application runs in Kubernetes | Service DNS, e.g. `postgres.database.svc.cluster.local` | Application Pods reach Services in the cluster via DNS |
| Application runs on a dedicated server and database is on another machine | Internal DNS or IP of the database | Must ensure routing, firewall rules, and network access permissions |

A common mistake is using `localhost` inside a container or Pod even though the database is in another container/Pod. In that case, the application looks for the database in its own environment and typically gets a connection refused error. Determine the actual location of the application process before choosing the host.

In Docker Compose, an example configuration might look like:

```yaml
services:
  app:
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: orders
      DB_USERNAME: orders_app
      DB_PASSWORD: ${DB_PASSWORD}
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: orders_app
      POSTGRES_PASSWORD: ${DB_PASSWORD}
```

This is a structural example illustrating DNS by service name. Plain `depends_on` only controls container startup order; it does not guarantee the database is ready to accept connections. The application still needs appropriate retry/health check mechanisms or orchestration settings that wait for service readiness.

## 8. Managing Username and Password Securely

Username and password are secret information. Do not write real passwords into Git, committed configuration files, startup logs, screenshots, or error messages. Some common ways to provide credentials:

- **Environment variables:** supply `DB_USERNAME` and `DB_PASSWORD` from the application runtime environment.
- **Deployment platform secrets:** use Kubernetes Secrets, a cloud secret manager, or your organization's secret management system.
- **Externalized configuration:** supply values through Spring Boot's externalized configuration mechanism.
- **Dedicated application account:** create a user with the minimum required privileges rather than using a database administrator account.

Example YAML file referencing secrets only:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

These variables must be declared in the environment before the application starts. Do not set a real password as the default value in a placeholder.

If credentials are embedded directly in the URL, special characters like `@`, `:`, `/`, `?`, `#`, or `%` may need to be URL-encoded so they are not mistaken for URL delimiters. Declaring username and password via separate properties is usually easier to read, easier to manage as secrets, and less prone to encoding errors.

Do not use the same admin-privileged account across all environments. The application's account should have only the permissions needed to read, write, or perform migrations as designed. A migration account can be kept separate from the runtime application account to limit runtime privileges.

## 9. Separating Configuration by Profile

Connection details often differ between development machines, testing, and production. Spring Profiles allow keeping appropriate configurations in separate files:

`application-dev.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders_dev
    username: orders_dev
    password: ${DB_PASSWORD:dev_only_password}
```

`application-prod.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Activate a profile via an environment variable or configuration parameter, for example:

```text
SPRING_PROFILES_ACTIVE=prod
```

The `prod` profile should only be used when the deployment environment supplies all required connection variables. Avoid committing development passwords that could be used in real systems; `dev_only_password` is only an illustrative value and should be replaced with an appropriate secret if used in a shared environment.

Spring Boot has multiple configuration sources. Environment variables, command-line arguments, and external configuration sources can override values in files. When an application connects to the wrong database, check the active profile and final resolved configuration source rather than reading only `application.yml`.

## 10. Configuring the R2DBC Connection Pool

Opening a new connection to a database incurs overhead. A connection pool retains a set of reusable connections so requests do not have to establish a new connection for every operation. An R2DBC pool is a database connection pool; it is not a thread pool and does not determine the number of WebFlux event-loop threads.

Example pool configuration in Spring Boot:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:orders}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 30m
      max-acquire-time: 10s
```

Meaning of typical properties:

| Property | Meaning |
| --- | --- |
| `enabled` | Enables connection pool configuration when a pool implementation is on the classpath and supported by the active Spring Boot version |
| `initial-size` | Initial number of connections the pool attempts to create |
| `max-size` | Maximum connection limit for the pool |
| `max-idle-time` | Duration a connection may remain idle before being evicted according to pool policy |
| `max-life-time` | Maximum lifetime of a connection in the pool |
| `max-acquire-time` | Maximum time to wait to acquire a connection from the pool |

Properties and default values may vary by Spring Boot and pool library version. A compatible R2DBC pool dependency, such as `io.r2dbc:r2dbc-pool`, must be present if pool configuration requires that library. Check the configuration metadata and documentation of the version in use.

Do not set `max-size` excessively large just to reduce wait times. Each application instance has its own pool, so the total number of open connections can approach `max-size × number of instances` under heavy load. For example, four instances with `max-size: 20` each can generate peak demand of around 80 connections, not counting admin tasks, migrations, and other services. This value must fit within database limits and match the server's processing capacity.

If `max-acquire-time` expires frequently, the cause may be a pool that is too small, overly slow queries, connections held too long, an overloaded database, or traffic spikes. Increasing the pool limit without investigating the cause can overload the database even further.

## 11. TLS and Driver-Specific Properties

In production environments, network connections to the database may require TLS encryption to protect data and credentials. How TLS is enabled, how server certificates are verified, how CA certificates are supplied, and how authentication modes are chosen depend on the driver and database engine.

There is no single TLS query parameter string that applies to all R2DBC URLs. For instance, PostgreSQL's option names and representation of certificate verification modes may differ from MySQL or MariaDB. Consult the documentation for the exact driver version, use trusted CA certificates, and prefer verifying server identity rather than disabling certificate checks.

Spring Boot allows passing additional connection properties via `spring.r2dbc.properties` in supported versions. The names and values of these properties are determined by the driver. Only add properties confirmed by the driver; invalid configuration may be ignored or cause connections to fail.

## 12. Creating `ConnectionFactory` in Java When Customization Is Needed

In typical Spring Boot applications, prefer externalized configuration so Boot creates the `ConnectionFactory` automatically. Some systems need to choose configuration at runtime, combine multiple data sources, or initialize connections with custom logic. In those cases, you can create a `ConnectionFactory` using the R2DBC SPI.

PostgreSQL example:

```java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class R2dbcConfiguration {

    @Bean
    ConnectionFactory connectionFactory(DatabaseSettings settings) {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
                .option(ConnectionFactoryOptions.DRIVER, "postgresql")
                .option(ConnectionFactoryOptions.HOST, settings.host())
                .option(ConnectionFactoryOptions.PORT, settings.port())
                .option(ConnectionFactoryOptions.DATABASE, settings.database())
                .option(ConnectionFactoryOptions.USER, settings.username())
                .option(ConnectionFactoryOptions.PASSWORD, settings.password())
                .build();

        return ConnectionFactories.get(options);
    }
}
```

Here `DatabaseSettings` is an application-defined configuration object that can be bound from environment variables or `@ConfigurationProperties`. The snippet illustrates passing host, port, database, and credentials via the R2DBC SPI; it is not a complete production configuration for every environment. Additional options such as TLS and pooling must be configured according to the driver and operational requirements.

When declaring a `ConnectionFactory` bean manually, Spring Boot auto-configuration may back off because the application has supplied the corresponding bean. In that case, proactively ensure pooling, the transaction manager, and related components are configured properly. Avoid manually creating a `ConnectionFactory` while expecting Boot to use a different URL without understanding configuration precedence.

## 13. Verifying the Application Connects to the Right Database

After declaring configuration, verify connectivity from the actual environment where the application runs. Pinging the database from a personal laptop does not prove an application container or Pod has the same network reachability.

You can run a simple check using `DatabaseClient`:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public Mono<Integer> checkDatabase(DatabaseClient databaseClient) {
    return databaseClient.sql("SELECT 1 AS result")
            .map((row, metadata) -> row.get("result", Integer.class))
            .one();
}
```

When the publisher emits `1`, the test query executed and returned a result. Subscribe via an appropriate health check endpoint, health indicator, or integration test. Do not call `block()` on an event loop just to test connectivity.

A deeper test should verify the exact database and user, such as querying metadata appropriate for the database system in use. `SELECT 1` only proves connectivity and simple query execution work; it does not prove the user has sufficient privileges on every table, schema, or business operation.

## 14. Diagnosing Common Connection Errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `Connection refused` | No service listening at that host/port, database not ready, or firewall rejecting | Check host, port, database status, port mapping, and network policy |
| `UnknownHostException` or DNS resolution error | Wrong hostname or application environment cannot resolve DNS | Check service name, internal DNS, namespace, and network configuration |
| Authentication error / password authentication failed | Wrong username or password, locked account, or incompatible auth method | Check secrets, profile, account, and server authentication policy |
| Database does not exist | Wrong database name in URL or database not yet created | Check URL path segment and database initialization status |
| Driver not found or `ConnectionFactory` not found | Missing R2DBC driver dependency or wrong URL scheme | Check runtime dependencies, BOM, and `r2dbc:` scheme |
| Timeout acquiring connection | Pool exhausted, overloaded database, long-running query holding connections, or slow network | Check pool metrics, queries, timeouts, instance count, and database limits |
| SSL/TLS or certificate error | Mismatched TLS mode, CA, certificate hostname, or driver properties | Check TLS configuration against the exact driver and server certificate |
| Connects successfully but query rejected | User lacks privileges on schema, table, or specific operation | Check database and schema permissions of the application account |

A practical troubleshooting flow should proceed from outside in:

1. Confirm which profile the application is running with and inspect the actual resolved configuration values.
2. Check whether the hostname resolves from inside the application container or Pod.
3. Check whether a TCP connection can be opened to the right host and port from the same runtime environment.
4. Confirm the database has started, is listening on the right interface, and allows the application's network source.
5. Verify database name, username, password, and account privileges.
6. Confirm the R2DBC driver matches the database engine, the URL uses the right scheme, and TLS properties are suitable.
7. If errors occur under increased load, check the connection pool, query durations, and database connection limits.

Do not put passwords, URLs containing credentials, or secrets into logs while investigating. Logs should record host, port, database, and error code at a level sufficient for diagnostics while masking credentials.

## 15. Pre-Run Configuration Checklist

- [ ] Selected the right R2DBC driver for the database management system.
- [ ] URL uses the `r2dbc:` scheme and the driver's correct protocol.
- [ ] Host is an address reachable from the environment actually running the application.
- [ ] Port matches the port on which the database is listening.
- [ ] Database name exists and is declared accurately in the URL.
- [ ] Username and password are supplied from an appropriate configuration source.
- [ ] Account has the minimum privileges required by the application.
- [ ] Active profile matches the deployment environment.
- [ ] TLS and driver-specific properties are configured when required by the environment.
- [ ] Connection pool has the proper dependency and limits if enabled.
- [ ] Application can execute a check query from the actual deployment environment.
- [ ] Logs and repositories contain no real passwords or secrets.

## 16. Practical Guidelines

- Use `spring.r2dbc.url`, `spring.r2dbc.username`, and `spring.r2dbc.password` to configure connections in Spring Boot.
- Put host, port, and database name in the URL using the driver's syntax; do not use JDBC URLs for R2DBC.
- Store credentials in environment variables or a secret manager; do not commit real passwords.
- Determine the host based on where the application process runs; `localhost` inside a container is not a database in another container.
- Use the right R2DBC driver dependency and a version compatible with Spring Boot.
- Separate configuration by profile or externalized configuration to avoid connecting to the wrong environment.
- Size the pool according to database connection limits and total application instance count.
- Configure TLS according to driver documentation and verify the server certificate.
- Test connectivity from the exact runtime environment of the application and verify required permissions as well.
- Do not log credentials or place secrets into source code.

## 17. Conclusion

R2DBC connection configuration revolves around four pieces of information: host identifies the server, port identifies the service port, database identifies where data is accessed, and credentials identify the application's identity and privileges. Spring Boot allows declaring these values under `spring.r2dbc`, then creates a `ConnectionFactory` for Spring Data R2DBC, repositories, and `R2dbcEntityTemplate` to use.

Reliable connectivity also depends on having the right driver for the database engine, deployment DNS and networking, secret management, TLS, and connection pooling. When configuration is separated from source code, verified from the actual runtime environment, and scoped with reasonable account privileges, the application becomes easier to deploy across environments and easier to diagnose when connection issues occur.
