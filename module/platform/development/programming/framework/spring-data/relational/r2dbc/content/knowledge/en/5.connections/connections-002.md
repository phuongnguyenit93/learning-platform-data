# Distinguishing R2DBC URLs from JDBC URLs

R2DBC connection URLs and JDBC connection URLs both describe how an application locates a database, but they belong to two different SPIs, two driver ecosystems, and two data access models. For the same PostgreSQL server, JDBC typically uses a URL starting with `jdbc:postgresql:`, whereas R2DBC uses a URL starting with `r2dbc:postgresql:`. Replacing the prefix in the string is not enough to migrate an application from JDBC to R2DBC: the application must also use the corresponding driver, dependencies, Spring configuration, and connection APIs.

## 1. What Is a Connection URL Used For?

An application needs at least the following information to connect to a database:

- The database management system or driver to use.
- The host and port, if the database runs over the network.
- The database or catalog to access.
- Credentials and connection options such as SSL, timeouts, or default schema.

A URL bundles some or all of that information into a single string. The driver parses the string and establishes a connection using the protocol it supports. However, JDBC and R2DBC have their own driver discovery mechanisms, connection types, configurations, and URL conventions.

A URL is not the connection itself. It is input used to create a connection object through the corresponding API:

| Ecosystem | Connection creation API | Connection object |
|---|---|---|
| JDBC | `DriverManager` or `DataSource` | `java.sql.Connection` |
| R2DBC | `ConnectionFactories` or Spring `ConnectionFactory` | `io.r2dbc.spi.Connection` |

Therefore, a JDBC URL cannot be treated as an R2DBC URL simply because both point to the same database server.

## 2. General Structure of a JDBC URL

A JDBC URL has the general form:

```text
jdbc:<subprotocol>:<subname>
```

Where:

- `jdbc:` is the prefix identifying the URL as belonging to JDBC.
- `<subprotocol>` usually identifies the database engine or driver type, such as `postgresql`, `mysql`, `oracle`, or `sqlserver`.
- `<subname>` contains connection details according to the driver's convention, such as host, port, database, and optional parameters.

PostgreSQL example:

```text
jdbc:postgresql://localhost:5432/orders
```

This URL can be read as follows:

| Component | Value | Meaning |
|---|---|---|
| Prefix | `jdbc:` | Use JDBC |
| Subprotocol | `postgresql` | PostgreSQL JDBC driver |
| Host | `localhost` | Database running on the current machine |
| Port | `5432` | Commonly used default PostgreSQL port |
| Database | `orders` | Database to access |

Some other examples:

```text
jdbc:mysql://localhost:3306/shop
jdbc:oracle:thin:@//localhost:1521/ORCLPDB1
jdbc:sqlserver://localhost:1433;databaseName=orders
jdbc:h2:mem:sample
```

There is no single `<subname>` structure that applies to all JDBC drivers. PostgreSQL, MySQL, Oracle, SQL Server, and H2 may use their own syntax. Some drivers use query parameters in `?key=value` form, while others use semicolons or specialized syntax.

A JDBC driver is usually selected via `DriverManager` or wrapped inside a `DataSource`/connection pool. Direct JDBC usage example:

```java
String url = "jdbc:postgresql://localhost:5432/orders";

try (Connection connection = DriverManager.getConnection(
        url, "app", password)) {
    // Perform JDBC work.
}
```

In a Spring application, `DataSource` is typically the configuration and connection-allocation point for `JdbcTemplate`, JPA, or other JDBC components.

## 3. General Structure of an R2DBC URL

An R2DBC URL typically has the form:

```text
r2dbc:<driver>:[//<host>[:<port>]][/<database>][?<options>]
```

Where:

- `r2dbc:` is the prefix identifying the URL as belonging to R2DBC.
- `<driver>` is the R2DBC driver/provider name, such as `postgresql`, `mysql`, `mariadb`, or `h2` depending on the installed driver.
- Host, port, and database specify the connection target if the driver uses network connectivity.
- The query options section may contain options supported by the driver.

This is the general form. Drivers may extend or specify their own details, especially for embedded databases and connection options. Do not assume every driver accepts the exact same set of parameters.

PostgreSQL example:

```text
r2dbc:postgresql://localhost:5432/orders
```

Corresponding components:

| Component | Value | Meaning |
|---|---|---|
| Prefix | `r2dbc:` | Use R2DBC SPI |
| Driver | `postgresql` | R2DBC PostgreSQL driver/provider |
| Host | `localhost` | Database server |
| Port | `5432` | PostgreSQL port |
| Database | `orders` | Database to access |

Examples for some other drivers:

```text
r2dbc:mysql://localhost:3306/shop
r2dbc:mariadb://localhost:3306/shop
r2dbc:h2:mem:///sample
```

The exact driver name and syntax depend on the R2DBC artifact used. Check the documentation for the exact driver and version present in the project rather than inferring the driver name from the JDBC connector name.

The R2DBC SPI can create a `ConnectionFactory` from a URL via `ConnectionFactories`:

```java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

ConnectionFactory connectionFactory = ConnectionFactories.get(
    "r2dbc:postgresql://localhost:5432/orders"
);
```

In a Spring application, `ConnectionFactory` is normally configured and managed by Spring Boot or custom Spring configuration. `DatabaseClient`, `R2dbcEntityTemplate`, and reactive repositories use this infrastructure to access the database.

## 4. Direct Comparison Against the Same Database

With PostgreSQL at `localhost:5432` and database `orders`, the two basic URLs are:

```text
JDBC:  jdbc:postgresql://localhost:5432/orders
R2DBC: r2dbc:postgresql://localhost:5432/orders
```

The host, port, and database parts look nearly identical, but the prefix determines the connection ecosystem. The two strings are handled by two different types of drivers.

| Criterion | JDBC | R2DBC |
|---|---|---|
| Prefix | `jdbc:` | `r2dbc:` |
| SPI | JDBC | R2DBC SPI |
| Driver | JDBC driver | R2DBC driver |
| Connection creation API | `DriverManager` / `DataSource` | `ConnectionFactories` / `ConnectionFactory` |
| Connection type | `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| Operation model | Typically synchronous and blocking | Reactive, supports non-blocking I/O |
| Common Spring configuration | `spring.datasource.*` | `spring.r2dbc.*` |
| Spring abstractions | `JdbcTemplate`, JPA/JDBC | `DatabaseClient`, `R2dbcEntityTemplate`, reactive repositories |
| Common pool | HikariCP via `DataSource` | R2DBC Pool or equivalent pooling mechanism |

Key point: having the same host and database in the URL does not make the drivers interchangeable. A JDBC driver implements the JDBC SPI; an R2DBC driver implements the R2DBC SPI. To use R2DBC, the application must have the corresponding R2DBC driver.

## 5. Dependencies Must Also Match the URL

A URL is only meaningful when the classpath contains a driver/provider that understands that URL.

Example with PostgreSQL and Gradle Kotlin DSL:

**Application using R2DBC:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
```

**Application using JDBC:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("org.postgresql:postgresql")
}
```

Spring Boot dependency management can manage compatible versions when the project uses the Spring Boot BOM or plugin. If the project uses standalone versions, you must declare driver versions compatible with Spring Framework, Spring Data, and the database.

The two PostgreSQL artifacts above serve different purposes:

- `org.postgresql:postgresql` is the PostgreSQL JDBC driver.
- `org.postgresql:r2dbc-postgresql` is the PostgreSQL R2DBC driver.

Adding only the JDBC driver does not produce an R2DBC `ConnectionFactory`. Likewise, adding only the R2DBC driver does not provide a `java.sql.Driver` for `DriverManager`.

An application may need both drivers if it genuinely uses both JDBC/JPA and R2DBC. In that case, configure two separate connection stacks and manage transactions, pools, and beans appropriately for each stack.

## 6. Configuring URLs in Spring Boot

Spring Boot uses different configuration namespaces for JDBC and R2DBC. This is one of the easiest places to get confused when migrating a project.

### 6.1. R2DBC Configuration

Example `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Basic properties:

- `spring.r2dbc.url`: URL of the R2DBC driver.
- `spring.r2dbc.username`: database account.
- `spring.r2dbc.password`: database password.

Spring Boot uses this configuration to create a `ConnectionFactory` when the appropriate starter and driver are present. Reactive beans such as `DatabaseClient` and R2DBC repositories can use the configured connection factory.

### 6.2. JDBC Configuration

Example `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Basic properties:

- `spring.datasource.url`: URL of the JDBC driver.
- `spring.datasource.username`: database account.
- `spring.datasource.password`: database password.

Spring Boot uses this configuration to create a `DataSource` for `JdbcTemplate`, JPA, and other JDBC components.

### 6.3. Mistakes to Avoid

| Wrong configuration | Why is it wrong? | Configuration to use |
|---|---|---|
| Putting `jdbc:postgresql:...` in `spring.r2dbc.url` | R2DBC provider does not accept JDBC URLs | Use `r2dbc:postgresql:...` |
| Putting `r2dbc:postgresql:...` in `spring.datasource.url` | JDBC driver does not handle R2DBC URLs | Use `jdbc:postgresql:...` |
| Adding only `org.postgresql:postgresql` while using `DatabaseClient` | Classpath is missing the R2DBC driver | Add `org.postgresql:r2dbc-postgresql` |
| Adding only `org.postgresql:r2dbc-postgresql` while using `JdbcTemplate` | Classpath is missing the JDBC driver | Add `org.postgresql:postgresql` |
| Using `spring.datasource.*` and expecting R2DBC repositories to connect | That is the JDBC configuration namespace | Configure `spring.r2dbc.*` |
| Using `spring.r2dbc.*` and expecting JPA to use that connection | JPA/Hibernate uses a JDBC `DataSource` | Configure JDBC separately for JPA |

If the application needs both technologies, both configurations can coexist in the same file:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
```

Declaring both configurations does not make the two connection types share a pool or a transaction. JDBC and R2DBC have separate connection factories, pools, and transaction managers. Check auto-configuration and declare beans explicitly if the application has multiple `DataSource`, `ConnectionFactory`, or transaction manager beans.

## 7. Credentials in the URL vs. Separate Configuration

Some drivers allow placing username and password in the URL. Format example:

```text
r2dbc:postgresql://app:secret@localhost:5432/orders
jdbc:postgresql://localhost:5432/orders
```

With JDBC, username/password are usually passed separately via `Properties`, `DriverManager`, or `DataSource` configuration. With Spring Boot, the easier approach to manage is using separate `username` and `password` properties as shown in the examples above.

Do not put real passwords into committed configuration files or URLs that appear in logs. URLs may be recorded in startup logs, error reports, configuration dashboards, or diagnostic output. Use environment variables, a secret manager, or the deployment platform's secret management mechanism.

If a driver allows credentials inside the URL, special characters such as `@`, `:`, `/`, `?`, and `#` may require percent-encoding according to the driver's parser rules. Separating username/password from the URL is generally safer and easier to maintain unless the driver or deployment environment requires otherwise.

## 8. Optional Parameters and Differences Between Drivers

URLs may contain parameters such as SSL, timeout, schema, application name, or authentication mode. However, parameter names, letter casing, valid values, and encoding depend on the driver.

For example, PostgreSQL JDBC and PostgreSQL R2DBC may use different option names or interpret an option differently. Do not copy the entire query string of a JDBC URL over to an R2DBC URL without checking the driver documentation.

When configuring SSL, determine:

1. Whether the driver supports SSL/TLS.
2. Option names and values accepted by the driver.
3. How the driver requires trust certificates, client certificates, or hostname verification.
4. Whether configuration is passed via URL, `ConnectionFactoryOptions`, or Spring Boot-specific properties.
5. How the configuration behaves in production and during certificate rotation.

Do not disable certificate or hostname verification just to make a connection work in production. If a TLS connection fails, fix the trust chain, hostname, or certificate configuration according to system requirements.

Additionally, an R2DBC URL can be extended by a wrapper or provider, such as R2DBC Pool. A configuration may take the form:

```text
r2dbc:pool:postgresql://localhost:5432/orders
```

The `r2dbc:pool:` prefix requires the corresponding pool provider and underlying driver to be present. Not every application needs to write a pool wrapper into the URL; Spring Boot can configure the pool via R2DBC properties when the dependency and version support it. Follow the documentation of the Spring Boot and R2DBC Pool versions in use.

## 9. Differences with Embedded Databases

Not all R2DBC URLs follow the `r2dbc:<driver>://host:port/database` form. For embedded or in-memory databases, drivers may use custom syntax.

H2 example:

```text
JDBC:  jdbc:h2:mem:sample
R2DBC: r2dbc:h2:mem:///sample
```

Both strings point to an in-memory database named `sample`, but the URL structures differ because the JDBC H2 driver and R2DBC H2 driver have their own conventions.

When migrating an embedded database from JDBC to R2DBC, review:

- URL syntax and how the database is named.
- How the in-memory database is shared across connections.
- When the database is created and closed.
- Options for keeping the database alive when the last connection closes.
- SQL compatibility and features of the H2 version.

Do not assume a JDBC in-memory URL can be used verbatim in R2DBC just because the database name is the same.

## 10. A URL Does Not Determine the Entire Programming Model

A URL starting with `r2dbc:` signals selecting an R2DBC provider. It does not automatically turn every part of the application into non-blocking code.

For example:

```java
// R2DBC: returns a reactive publisher.
Mono<Customer> customer = databaseClient.sql("""
        SELECT id, name, email
        FROM customer
        WHERE id = :id
        """)
    .bind("id", 10L)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("email", String.class)))
    .one();
```

Meanwhile, JDBC typically executes synchronously:

```java
// JDBC: runs the query and reads ResultSet in a blocking manner.
Customer customer = jdbcTemplate.queryForObject(
    "SELECT id, name, email FROM customer WHERE id = ?",
    (rs, rowNum) -> new Customer(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getString("email")),
    10L
);
```

If a WebFlux application uses JDBC directly on an event-loop thread, blocking operations can still block the thread even if the endpoint returns `Mono` or `Flux`. To use JDBC in a reactive application, blocking work must be isolated onto an appropriate scheduler and accept JDBC's resource model. If the goal is end-to-end reactive non-blocking database access, use an R2DBC driver with reactive APIs.

R2DBC is not renamed JDBC or a JDBC URL wrapped in a `Mono`. It is a different SPI with its own drivers and connection APIs.

## 11. Process for Migrating Configuration from JDBC to R2DBC

When migrating an application using JDBC to Spring Data R2DBC, you can proceed in the following order:

### Step 1: Identify the database and R2DBC driver

Check the database engine, database version, supported R2DBC driver, and features the application needs. Confirm that the driver supports your project's data types, SSL, authentication, transactions, and SQL dialect.

### Step 2: Swap in the appropriate dependencies

Add the R2DBC starter and the corresponding R2DBC driver. Keep JDBC dependencies only if the application still has components using JDBC/JPA or tooling that requires them.

### Step 3: Convert the URL and configuration namespace

For example:

```properties
# Before: JDBC
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}

# After: R2DBC
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/orders
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
```

Keep the JDBC lines only if another part of the application continues to use JDBC. Do not change the prefix while forgetting to change the namespace and driver dependency.

### Step 4: Review driver options

Cross-check the options present in the JDBC URL against the R2DBC driver documentation. Convert each option intentionally, especially SSL, timeouts, schema, authentication, and pooling.

### Step 5: Replace data access APIs

Replace `DataSource`, `JdbcTemplate`, or JDBC repositories with `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate`, or appropriate reactive repositories. Update return types and error handling to `Mono`/`Flux`.

### Step 6: Verify transactions and pooling

Check the transaction manager, connection limits, acquire timeout, and subscription lifecycle. A JDBC transaction manager does not manage R2DBC transactions; the two stacks need managers suited to their respective connection factories.

### Step 7: Test against the target database

Run integration tests against the actual database and driver that will be deployed. Verify queries, mapping, generated keys, transaction rollbacks, connection errors, timeouts, and behavior when a publisher is cancelled.

## 12. Diagnosing URL and Driver Errors

When the application cannot connect, categorize the error before changing the URL arbitrarily.

| Symptom | Possible cause | What to check |
|---|---|---|
| `No suitable driver` when using JDBC | Missing JDBC driver or URL has wrong prefix/subprotocol | Check JDBC dependency and `jdbc:` URL |
| R2DBC `ConnectionFactory` not found | Missing R2DBC driver or URL has no matching provider | Check R2DBC dependency, driver name, and `r2dbc:` prefix |
| URL parse error at startup | Syntax unsupported by driver or unencoded URL characters | Compare against documentation for the exact driver version |
| `Connection refused` | Wrong host/port, database not running, or firewall blocking | Check service, DNS, port, and network policy |
| Authentication failed | Incorrect username, password, or authentication mechanism | Check secrets and server authentication method |
| JDBC connects but R2DBC cannot connect | The two drivers have different options, SSL, or authentication | Check R2DBC driver configuration and capabilities |
| R2DBC repository cannot find connection factory | Only `spring.datasource.*` configured or missing R2DBC starter | Configure `spring.r2dbc.*` and corresponding dependency |
| JPA cannot find `DataSource` | Only R2DBC configured | Configure JDBC `spring.datasource.*` if the app needs JPA |
| Connection works but opens too many connections | Pool not configured or limits inappropriate | Check R2DBC pool and database connection budget |

A quick check is to confirm four components match each other:

```text
URL prefix
    |
    v
Driver dependency
    |
    v
Spring configuration namespace
    |
    v
Connection API / data-access abstraction
```

For example, a PostgreSQL R2DBC configuration requires an `r2dbc:postgresql:...` URL, the R2DBC PostgreSQL driver, `spring.r2dbc.*` configuration, and APIs using `ConnectionFactory`, `DatabaseClient`, or reactive repositories.

## 13. Pre-Run Configuration Checklist

Before starting or deploying, confirm:

- [ ] Determined whether the application uses JDBC, R2DBC, or both.
- [ ] URL prefix matches the SPI: `jdbc:` for JDBC, `r2dbc:` for R2DBC.
- [ ] Driver/provider name in the URL is supported by the installed driver.
- [ ] Correct dependency type is on the runtime classpath.
- [ ] Spring Boot configuration namespace matches the technology in use.
- [ ] Host, port, and database name point to the intended environment.
- [ ] Username/password are sourced from secrets or environment variables.
- [ ] SSL, timeout, schema, and pool options are verified against driver documentation.
- [ ] Connection pool and transaction manager belong to the right connection stack.
- [ ] Integration tests run against the actual database and driver.

## 14. Principles to Remember

- JDBC URLs start with `jdbc:` and are handled by a JDBC driver.
- R2DBC URLs start with `r2dbc:` and are handled by an R2DBC provider.
- Having the same host, port, and database does not mean the two URLs can be substituted for one another.
- A JDBC driver and an R2DBC driver are two separate dependencies implementing two different SPIs.
- Spring Boot typically uses `spring.datasource.*` for JDBC and `spring.r2dbc.*` for R2DBC.
- Option names and URL syntax depend on the driver; do not copy query strings verbatim between the two ecosystems.
- An R2DBC URL does not automatically turn JDBC code reactive; the application must use R2DBC APIs end-to-end if non-blocking execution is needed.

When URLs, drivers, dependencies, and configuration namespaces are properly distinguished, connecting Spring Data R2DBC becomes much clearer. Treat the URL as part of the contract between the application and the driver: choose the right prefix, the right provider, and the right options for the technology in use, then verify connectivity with integration tests against the target database.
