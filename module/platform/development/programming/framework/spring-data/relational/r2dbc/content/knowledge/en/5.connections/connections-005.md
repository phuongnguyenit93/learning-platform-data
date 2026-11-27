# Driver Discovery and Creating a ConnectionFactory

For a Spring Data R2DBC application to access a database, it must first have a suitable **R2DBC driver** and a properly configured **ConnectionFactory**. The driver implements the R2DBC protocol for a specific database management system; ConnectionFactory is the entry point for creating connections under the R2DBC SPI standard. Spring R2DBC and Spring Data R2DBC use this ConnectionFactory to execute SQL and perform entity operations.

You can visualize the chain of components as follows:

~~~text
Spring Application
    ↓
Spring Data R2DBC / Spring R2DBC
    ↓
ConnectionFactory
    ↓
R2DBC Driver
    ↓
Database engine protocol
    ↓
Database
~~~

This lesson focuses on how to choose a driver, how the R2DBC SPI locates drivers, the ways to create a ConnectionFactory, configuring with Spring Boot, using a connection pool, and verifying connectivity in an application.

## 1. What Is an R2DBC Driver?

R2DBC (Reactive Relational Database Connectivity) is a specification for accessing relational databases using a reactive model. This specification defines an SPI (Service Provider Interface) so data access libraries can work with drivers for multiple database engines under a common contract.

An **R2DBC driver** is a library implementing that SPI for a specific database engine. The driver is responsible for translating API calls into communication the database understands, sending statements and parameters, receiving results, converting data into R2DBC types, and reporting errors.

For example, an application connecting to PostgreSQL needs an R2DBC driver for PostgreSQL. An application connecting to H2 needs an R2DBC driver for H2. Sharing the same SPI does not mean one driver can connect to every database engine.

### 1.1. R2DBC Drivers and JDBC Drivers Are Different

JDBC and R2DBC share a similar business-level purpose: enabling Java to work with relational databases. However, they are two separate APIs and driver ecosystems.

| Criterion | JDBC | R2DBC |
|---|---|---|
| Standard API | JDBC API | R2DBC SPI |
| Driver | JDBC driver | R2DBC driver |
| I/O model | Typically blocking | Reactive, non-blocking when properly implemented by the driver |
| Access results | Synchronous APIs like ResultSet | Reactive Streams Publishers |
| Connections | DataSource creates JDBC Connections | ConnectionFactory creates R2DBC Connections |
| Spring integration | Spring JDBC | Spring R2DBC and Spring Data R2DBC |

A JDBC URL looks like jdbc:postgresql://host:5432/database. An R2DBC URL has its own scheme, such as r2dbc:postgresql://host:5432/database. You cannot pass a JDBC URL or JDBC driver to ConnectionFactory and expect the application to operate reactively.

Nor should you conclude that simply wrapping JDBC calls in Mono or Flux converts them into R2DBC. JDBC calls remain blocking. To use R2DBC, the application needs a driver that implements the R2DBC SPI.

### 1.2. Choosing a Driver by Database Engine and Version

When choosing a driver, determine:

- The database management system and running version.
- The R2DBC SPI version supported by the driver.
- The Spring Boot / Spring Framework / Spring Data versions compatible with the driver.
- Support for data types, transactions, SSL/TLS, authentication, and SQL features needed by the application.
- Operational readiness in the deployment environment, including connection pooling, timeouts, and error observability.

Some commonly used drivers:

| Database engine | Commonly used R2DBC driver |
|---|---|
| PostgreSQL | r2dbc-postgresql |
| H2 | r2dbc-h2 |
| MySQL | r2dbc-mysql |
| MariaDB | r2dbc-mariadb |
| Microsoft SQL Server | r2dbc-mssql |
| Oracle Database | oracle-r2dbc |

Artifact names and detailed configuration may vary by publisher and version. Consult the documentation for the corresponding driver and let Spring Boot dependency management handle versions when the project uses Spring Boot.

## 2. R2DBC SPI and the Role of ConnectionFactory

The R2DBC SPI defines several abstractions so upper-level libraries do not have to depend directly on how a specific database creates connections.

Key components include:

- **ConnectionFactoryOptions**: a set of options describing the driver, host, port, database, user, password, and other connection properties.
- **ConnectionFactoryProvider**: a provider supplied by the driver, capable of recognizing the options the driver supports and creating the corresponding ConnectionFactory.
- **ConnectionFactories**: a utility that looks up registered providers and creates a ConnectionFactory.
- **ConnectionFactory**: the abstraction that creates R2DBC connections.
- **Connection**: a connection session used to create statements, execute SQL, manage transactions, and close the connection.
- **Result** and **Row**: representations of execution results and a single returned row of data.

### 2.1. A ConnectionFactory Is Not a Connection

Distinguish between the two objects:

- ConnectionFactory is the object that creates or allocates connections. An application usually keeps a single shared instance throughout its lifecycle.
- Connection is a specific connection allocated for an operation or unit of work. The connection must be released properly after completion.

The create() method on ConnectionFactory returns a Publisher containing a Connection. A connection is acquired when the publisher is subscribed to under the reactive model. Calling create() is not the same as holding one shared connection for the entire application.

~~~java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

ConnectionFactory connectionFactory = /* configured in later sections */;

Mono<Connection> connectionPublisher =
    Mono.from(connectionFactory.create());
~~~

The publisher above describes a request to obtain a connection. Once a connection is obtained, code calling the R2DBC SPI directly is responsible for releasing it after the operation finishes. When using Spring DatabaseClient or Spring Data R2DBC, the framework manages connection lifecycle for operations it executes.

### 2.2. ConnectionFactory Provides Metadata

ConnectionFactory also provides metadata about the driver:

~~~java
String driverName = connectionFactory.getMetadata().getName();
System.out.println("R2DBC driver: " + driverName);
~~~

Metadata is useful for startup logging or configuration diagnostics. It does not replace testing actual connectivity: being able to create a ConnectionFactory does not prove the database is reachable, credentials are valid, or networking is clear.

## 3. Driver Discovery: How Does R2DBC Find a Driver?

An R2DBC driver normally registers a provider through the Java Service Provider mechanism. When the application adds the driver artifact to the runtime classpath, the driver's provider is registered so the R2DBC SPI can find it.

General process:

1. The application supplies ConnectionFactoryOptions or an R2DBC URL.
2. The R2DBC SPI searches registered ConnectionFactoryProvider implementations.
3. Each provider checks whether it supports the given driver/protocol and options.
4. The matching provider creates the ConnectionFactory.
5. ConnectionFactory uses the driver to allocate connections when data access operations occur.

~~~mermaid
flowchart TB
    A["R2DBC URL / ConnectionFactoryOptions"]
    B["ConnectionFactories"]
    C["Service Provider discovery"]
    D["Driver's ConnectionFactoryProvider"]
    E["ConnectionFactory"]
    F["R2DBC Connection"]
    G[("Database")]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
~~~

If the driver is not on the runtime classpath, the SPI cannot locate a suitable provider. A common error is failing to find a driver matching the URL or options.

This is why the driver dependency must be present at runtime. Declaring only Spring Data R2DBC or Spring R2DBC is not sufficient to connect to a specific database.

## 4. Creating a ConnectionFactory Using an R2DBC URL

The most concise approach is using an R2DBC URL with the ConnectionFactories utility.

PostgreSQL URL example:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;

ConnectionFactory connectionFactory =
    ConnectionFactories.get("r2dbc:postgresql://localhost:5432/orders");
~~~

Common URL structure takes the form:

~~~text
r2dbc:<driver>://[user:password@]host[:port]/database
~~~

Where:

- r2dbc is the scheme indicating this is an R2DBC URL.
- driver identifies the driver/provider to use, such as postgresql.
- user and password are credentials if provided in the URL.
- host and port identify the server and port.
- database identifies the database to connect to.

URL syntax and supported options depend on the driver. Some drivers add query parameters to configure SSL, timeouts, schema, or proprietary properties. Consult the driver documentation before using those parameters.

Do not place real passwords inside URLs in source code, committed configuration files, or logs. URLs may be recorded in error logs or diagnostic output. In application environments, put credentials in environment variables or a secret manager and pass them through appropriate configuration.

## 5. Creating a ConnectionFactory Using ConnectionFactoryOptions

When you need per-property control or do not want to embed credentials in the URL, you can create ConnectionFactoryOptions using its builder.

PostgreSQL example:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactoryOptions;

import java.util.Objects;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

public class R2dbcConnectionFactoryConfig {

    public ConnectionFactory connectionFactory() {
        String username = Objects.requireNonNull(
            System.getenv("DB_USERNAME"),
            "DB_USERNAME is required"
        );

        String password = Objects.requireNonNull(
            System.getenv("DB_PASSWORD"),
            "DB_PASSWORD is required"
        );

        ConnectionFactoryOptions options =
            ConnectionFactoryOptions.builder()
                .option(DRIVER, "postgresql")
                .option(HOST, "localhost")
                .option(PORT, 5432)
                .option(USER, username)
                .option(PASSWORD, password)
                .option(DATABASE, "orders")
                .build();

        return ConnectionFactories.get(options);
    }
}
~~~

The options above are commonly used standard options. Drivers may support additional proprietary options. Not every driver supports the same set of properties or the same data type for an option.

### 5.1. DRIVER and Standard Options

| Option | Meaning |
|---|---|
| DRIVER | Name of the driver/provider to use |
| PROTOCOL | Protocol or connection variant if defined by the driver |
| HOST | Database server host |
| PORT | Service port |
| DATABASE | Database name |
| USER | Login username |
| PASSWORD | Password |
| SSL | SSL option if supported by the driver |

Not every connection needs all of these options. For example, some embedded databases do not need host or port; some drivers use protocol or proprietary properties to select the database or schema.

### 5.2. When to Use a URL vs. Options?

| Creation method | Suitable when |
|---|---|
| R2DBC URL | Concise configuration, well suited for environment config variables or Spring Boot |
| ConnectionFactoryOptions | Need to build options conditionally, read secrets separately, or add driver-specific options |
| Spring Boot properties | Spring Boot application wanting to leverage auto-configuration and bean lifecycle management |

All three ways can produce a ConnectionFactory. In a typical Spring Boot application, prefer Boot's standard configuration to avoid manually creating a parallel factory.

## 6. Declaring the Driver Dependency

The application needs the Spring Data R2DBC dependency and the corresponding driver.

Gradle example with Spring Boot and PostgreSQL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

If the project needs a connection pool and the active Spring Boot version does not pull in the pool dependency automatically, you can add:

~~~kotlin
runtimeOnly("io.r2dbc:r2dbc-pool")
~~~

When using Spring Boot dependency management, omit explicit versions from dependencies already managed by the BOM. Avoid picking an R2DBC SPI or driver version that is incompatible with the project's Spring Boot / Spring Data version set.

Distinguish the driver dependency from the JDBC dependency:

- The PostgreSQL JDBC driver is typically org.postgresql:postgresql.
- The PostgreSQL R2DBC driver is org.postgresql:r2dbc-postgresql.

The two artifacts serve two different APIs. Having the JDBC driver present does not mean the R2DBC driver is present.

## 7. Creating ConnectionFactory via Spring Boot Auto-Configuration

Spring Boot can create and register a ConnectionFactory from application configuration when a matching driver is on the classpath. Spring Data R2DBC, Spring R2DBC, and related components can then use this bean.

Example application.yml:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

In this configuration:

- url specifies the R2DBC driver and database address.
- username and password are read from environment variables.
- Spring Boot creates the ConnectionFactory based on the URL, credentials, and driver on the runtime classpath.

The application can inject ConnectionFactory or use higher-level abstractions such as DatabaseClient, R2dbcEntityTemplate, and reactive repositories.

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.stereotype.Component;

@Component
public class DatabaseConnectionInfo {

    private final ConnectionFactory connectionFactory;

    public DatabaseConnectionInfo(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String driverName() {
        return connectionFactory.getMetadata().getName();
    }
}
~~~

There is no need to call ConnectionFactories.get() manually in every service. A ConnectionFactory managed by the Spring container can be injected into components that need data access.

### 7.1. What Does Spring Boot Auto-Configuration Need?

Usually all of the following conditions are required:

1. A suitable Spring Boot R2DBC dependency is present.
2. An R2DBC driver for the database engine in use is on the runtime classpath.
3. A valid URL or connection properties are configured.
4. No conflicting custom configuration causes auto-configuration to back off.
5. The database is reachable from the application's runtime environment and credentials are valid.

When the application declares its own ConnectionFactory bean, auto-configuration may back off according to Spring Boot's conditions. Therefore, if you want Boot to create the factory automatically, avoid declaring an unnecessary extra factory.

### 7.2. Using Profiles for Different Environments

Connection details often differ across local, test, staging, and production. You can keep the same configuration structure while substituting values via environment variables:

~~~yaml
spring:
  r2dbc:
    url: ${R2DBC_URL}
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
~~~

Example:

~~~text
Local:
R2DBC_URL=r2dbc:postgresql://localhost:5432/orders

Production:
R2DBC_URL=r2dbc:postgresql://db.internal:5432/orders
~~~

Do not commit credentials to the repository. In production environments, use a secret manager or the deployment platform's secret-injection mechanism. Grant the application account only the database permissions the application needs.

## 8. Connection Pooling with r2dbc-pool

A ConnectionFactory can create a new connection whenever requested. In applications serving many requests, repeatedly opening and closing physical connections can consume resources and increase latency.

A **connection pool** manages a group of connections so operations can borrow and return connections. In the R2DBC ecosystem, the r2dbc-pool library provides a ConnectionFactory implementation capable of pooling.

~~~mermaid
flowchart TB
    A["Repository / DatabaseClient"]
    B["Pooled ConnectionFactory"]
    C["Connection pool"]
    D["Connection 1"]
    E["Connection 2"]
    F["Connection N"]
    G[("Database")]

    A --> B
    B --> C
    C --> D
    C --> E
    C --> F
    D --> G
    E --> G
    F --> G
~~~

The application still interacts with the ConnectionFactory abstraction. The factory wrapped by the pool manages allocating and reusing underlying connections.

### 8.1. Configuring the Pool in Spring Boot

When r2dbc-pool is on the classpath, Spring Boot supports configuring the pool via the spring.r2dbc.pool property group.

Example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 2h
      max-acquire-time: 5s
~~~

Meaning:

- enabled enables the pool.
- initial-size is the initial number of connections the pool attempts to initialize per configuration.
- max-size limits the maximum number of connections in the pool.
- max-idle-time limits how long a connection can stay idle.
- max-life-time limits a connection's lifetime.
- max-acquire-time limits how long to wait when acquiring a connection from the pool.

Property names and available options depend on the Spring Boot and r2dbc-pool versions. Cross-check the configuration for your project's versions before copying a template verbatim.

### 8.2. Creating a ConnectionPool Programmatically

When not using Spring Boot auto-configuration or when manual configuration is needed, you can wrap the driver's ConnectionFactory with a ConnectionPool:

~~~java
import io.r2dbc.pool.ConnectionPool;
import io.r2dbc.pool.ConnectionPoolConfiguration;
import io.r2dbc.spi.ConnectionFactory;

import java.time.Duration;

ConnectionFactory driverFactory = /* factory created from driver */;

ConnectionPoolConfiguration poolConfiguration =
    ConnectionPoolConfiguration.builder(driverFactory)
        .initialSize(5)
        .maxSize(20)
        .maxIdleTime(Duration.ofMinutes(30))
        .maxLifeTime(Duration.ofHours(2))
        .build();

ConnectionPool pooledFactory =
    new ConnectionPool(poolConfiguration);
~~~

ConnectionPool also implements ConnectionFactory, so Spring components can use pooledFactory like a normal factory.

If creating a pool manually in Spring, register it as a bean and let Spring manage its lifecycle, including disposing the pool when the application context closes. Do not create a new pool per request or per repository.

Do not configure two pooling layers simultaneously on the same connection path. If Boot already created a pooled ConnectionFactory, do not wrap it in another ConnectionPool unless there is a clear reason and you understand the impact.

### 8.3. Choosing Pool Size

Bigger max-size numbers are not always better. Every connection consumes resources on both the database and the application. Consider:

- Database connection limits.
- Number of application instances running concurrently.
- Number of workers or requests actually accessing the database concurrently.
- Average duration an operation holds a connection.
- Connections reserved for migrations, administration, batch jobs, and other services.

For example, if there are 4 application instances and each instance allows up to 20 connections, this application alone can create up to 80 connections to the database. That number must fit within the limit the database can serve alongside other clients.

Too small a pool can cause requests to wait for connections. Too large a pool can overload the database and increase contention. Monitor acquire time, active connection count, idle connection count, and timeouts before tuning.

## 9. Connection Lifecycle and Resource Release

When using the R2DBC SPI directly, a connection must be closed after the operation completes. In reactive code, release must happen on completion, error, or cancellation.

Spring provides abstractions such as DatabaseClient to manage most of the connection lifecycle for SQL operations. When working directly with the SPI, you can use reactive resource management such as Mono.usingWhen.

Illustrative example testing a simple query:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

Mono<Integer> ping(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(connection.createStatement("SELECT 1").execute())
            .flatMap(result ->
                Mono.from(result.map((row, metadata) ->
                    row.get(0, Integer.class)
                ))
            ),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

In this example, usingWhen manages closing the connection when the publisher completes normally, terminates with an error, or is cancelled. The return type of SELECT 1 in the example depends on the database/driver; with other database engines you may need to adjust the type extracted from Row.

If the connection was issued from a pool, close() normally returns the connection to the pool for reuse. If the connection is not pooled, close() releases the connection according to the driver implementation.

Do not store a shared Connection in a singleton service for multiple requests to operate on concurrently. A Connection is a stateful resource with its own transactions and lifecycle; let each operation or unit of work acquire and release connections through the framework's mechanism.

## 10. Verifying Connectivity and Diagnosing Errors

Being able to create a ConnectionFactory does not guarantee a successful connection. Actual connectivity also depends on DNS, network, firewall, host/port, database status, TLS, authentication, permissions, and connection limits.

Check layer by layer:

| Symptom | Possible cause | What to check |
|---|---|---|
| Provider/driver not found | Missing driver dependency or wrong DRIVER in options | Check runtime classpath and R2DBC URL |
| Cannot parse URL | Wrong scheme or URL syntax | Use the r2dbc scheme and driver syntax |
| Connection refused / timeout | Host, port, firewall, or database not running | Check DNS, route, port, and database status |
| Authentication failed | Wrong user/password or authentication mechanism | Check secrets and auth configuration |
| SSL handshake failed | Incompatible TLS/certificate/protocol | Check SSL mode, trust store, and certificates |
| Cannot acquire connection from pool | Pool exhausted, operations holding connections too long, or database limits | Monitor acquire timeout and pool metrics |
| Data type error | Driver does not support type or conversion is incorrect | Check driver codecs and Spring Data custom conversions |

### 10.1. Checking Configuration Before Checking the Database

You can log the driver name from metadata:

~~~java
System.out.println(connectionFactory.getMetadata().getName());
~~~

Do not log passwords, URLs containing passwords, or full options if they contain sensitive information. Logging host, port, database, and driver name in line with the application's security policy is sufficient for many diagnostic scenarios.

### 10.2. Checking Actual Connectivity

A health check should run a lightweight database operation over the connection path the application actually uses. For example, SELECT 1 can confirm the application can obtain a connection and the database can execute a query.

In a Spring Boot application, use the health indicator mechanism appropriate for the installed version and dependencies. If writing a custom health check, set a reasonable timeout and avoid generating excessive continuous probe queries.

A health check should distinguish application liveness from database availability. If the database is temporarily unavailable, the deployment platform may need to mark readiness as failing to stop routing new requests; exact behavior depends on operational policy.

## 11. Security and Operational Notes

- Do not hard-code username/password in source code.
- Do not commit configuration files containing real credentials.
- Use a secret manager or protected environment variables at runtime.
- Enable TLS/SSL when required by the environment and security policy; verify certificates instead of disabling certificate validation to bypass errors.
- Use a dedicated database account for the application with the minimum required privileges.
- Size pools according to total instance count and database connection limits.
- Set timeouts for connection acquisition and data access operations.
- Do not log passwords, tokens, or URLs containing credentials.
- Monitor connection leaks, pool exhaustion, timeouts, and driver errors.
- Close or dispose the pool on application shutdown if the application created the pool manually.

## 12. Which Configuration Approach Should Your Project Choose?

You can use the following criteria to choose how to create a ConnectionFactory:

| Context | Recommended approach |
|---|---|
| Typical Spring Boot application | Configure spring.r2dbc.url, username, password and let Boot auto-configure |
| Need to change database address per environment | Use environment variables or profiles for Spring Boot properties |
| Need driver-specific options | Use a URL with driver-supported parameters or ConnectionFactoryOptions |
| Non-Spring Boot application | Use ConnectionFactories.get(URL/options), then register the factory in your DI container |
| Need connection reuse | Use r2dbc-pool or Boot-configured pooling |
| Need SQL/entity access in Spring | Use ConnectionFactory as the foundation for DatabaseClient, R2dbcEntityTemplate, or repositories |

In most Spring Boot applications, configuring via application.yml is sufficient. Creating ConnectionFactory manually is helpful when an application needs dynamic configuration, integrates multiple databases, or runs outside Spring Boot. Pooling should be configured in a single place and managed throughout the application lifecycle.

## 13. Key Concepts to Remember

- **R2DBC driver** implements the R2DBC SPI for a specific database engine.
- **ConnectionFactoryOptions** describes information used to select a driver and configure connections.
- **ConnectionFactories** locates registered providers and creates a ConnectionFactory.
- **ConnectionFactory** creates/allocates Connections under the reactive model.
- **Connection** is a concrete resource that must be released properly.
- **Connection pool** reuses and limits concurrent connections.
- **Spring Boot auto-configuration** can create a ConnectionFactory from configuration and drivers on the classpath.
- **DatabaseClient / Spring Data R2DBC** uses ConnectionFactory to perform queries and mapping at a higher layer.

When configuring R2DBC, verify in order the driver artifact, URL/options, credentials, database reachability, and pooling. Distinguishing ConnectionFactory from Connection prevents holding connections with the wrong lifecycle; understanding driver discovery helps resolve missing provider errors; sizing the pool properly helps the application use database resources stably.
