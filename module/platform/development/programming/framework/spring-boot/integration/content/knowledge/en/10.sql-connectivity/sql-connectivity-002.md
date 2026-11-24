# spring.datasource.* and Inferring the JDBC Driver from the URL

## Objectives and Context

In the **SQL Connectivity** chapter of the **SPRING_BOOT_INTEGRATION** module, a Spring Boot application may read data from PostgreSQL, MySQL, SQL Server, or another database to coordinate with HTTP clients, caches, message brokers, and Spring Integration adapters. Before writing repositories or transactions, the application must know **which database to connect to, where to obtain credentials, and which JDBC driver to use**.

Spring Boot handles most common configuration work through the `spring.datasource.*` property group, the `DataSource` bean, and its auto-configuration mechanism. In particular, if you declare a JDBC URL for a database type that Boot recognizes, you typically **do not need to configure `spring.datasource.driver-class-name`**: Boot infers the driver class name from the URL.

This lesson focuses on that exact mechanism in a real-world system integration context, covering environment-specific configuration, data contracts, connection pooling, transactions, errors, testing, and observability.

After this lesson, you will be able to:

- Explain the relationship between `spring.datasource.url`, the JDBC driver, `DataSource`, the connection pool, and SQL access code.
- Declare `spring.datasource.url`, `username`, `password`, and pool settings without putting secrets in source code.
- Know when Boot can infer the driver from the JDBC URL and when `driver-class-name` must be configured.
- Distinguish between **driver not found**, **invalid URL**, **connection failure**, **invalid credentials**, and **connection pool exhaustion** errors.
- Understand the impact of single or multiple `DataSource` instances on transactions, migrations, tests, and observability.
- Use SQL connectivity as an adapter with clear responsibilities within an integration flow.

## 1. Layers in a Spring Boot SQL Connection

A SQL call does not go directly from a service to the database. Typically, there are several layers:

~~~mermaid
flowchart TD
    A["application.yml + environment"] --> B["DataSourceProperties"]
    B --> C["DataSourceAutoConfiguration"]
    C --> D["DataSource / connection pool"]
    E["JDBC driver from classpath"] --> D
    F["JdbcTemplate / Spring Data JPA"] --> D
    G["Business service / SQL adapter"] --> F
    D --> H["Database server"]
    I["Transaction manager"] --> D
    J["Actuator / Micrometer"] -.-> D
~~~

| Component | Responsibility | Example |
| --- | --- | --- |
| `spring.datasource.*` | Connection configuration supplied by operators | URL, username, password |
| `DataSourceProperties` | Binds basic configuration and resolves connection details | Boot properties class |
| `DataSourceAutoConfiguration` | Registers an appropriate `DataSource` if conditions are met | Selects pooling implementation |
| JDBC driver | Understands the database-specific JDBC wire protocol | `org.postgresql.Driver` |
| `DataSource` | Supplies `Connection` objects to data access code | `HikariDataSource` |
| Connection pool | Retains and reuses connections to avoid opening a new one each time | HikariCP |
| `JdbcTemplate` / JPA | Executes SQL or maps objects | `JdbcTemplate.queryForObject(...)` |
| `PlatformTransactionManager` | Coordinates the appropriate local transaction | `JdbcTransactionManager` / `JpaTransactionManager` |

**Important distinction:** A JDBC URL is not an open connection. The URL describes where to connect and the protocol type; the driver performs the connection; the `DataSource`/pool manages connection lifecycles; and the repository or template uses that connection.

In a system that consumes broker events, writes to a database, and sends HTTP requests, `@Transactional` normally covers only the configured transaction-participating resources, and **does not automatically extend into a distributed transaction** across message brokers or external HTTP services.

## 2. Creating a DataSource with Spring Boot

### 2.1. Minimal Dependencies for JDBC

Gradle Groovy DSL example using PostgreSQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

`spring-boot-starter-jdbc` brings in the Spring JDBC infrastructure and a default connection pool (typically HikariCP). `org.postgresql:postgresql` is the **actual JDBC driver**, which must be present at runtime. When using Spring Boot's dependency-management plugin/BOM, you do not need to specify versions manually for BOM-managed dependencies.

If the application uses Spring Data JPA, the JPA starter typically already includes the JDBC/pooling infrastructure; there is no need to install duplicate starters just to get a `DataSource`. However, you **still need the specific driver** for your chosen database. For other databases, replace the PostgreSQL driver with the corresponding driver.

| Database type | Common driver dependency | Notes |
| --- | --- | --- |
| PostgreSQL | `org.postgresql:postgresql` | Runtime scope is usually sufficient |
| MySQL | `com.mysql:mysql-connector-j` | Do not use the legacy `com.mysql.jdbc.Driver` class name |
| MariaDB | `org.mariadb.jdbc:mariadb-java-client` | Distinct from the MySQL driver |
| Microsoft SQL Server | `com.microsoft.sqlserver:mssql-jdbc` | Check JDK requirements and compatible versions |
| Oracle Database | `com.oracle.database.jdbc:ojdbc11` or JDK-compatible artifact | Choose the driver matching your JDK/Boot version |
| H2 | `com.h2database:h2` | Commonly used for testing/dev |

**Do not add only the JDBC starter and expect Boot to download a driver from the Internet based on the URL.** Resolving the driver class name and having the driver JAR on the classpath are two separate steps.

### 2.2. When Does DataSourceAutoConfiguration Activate?

In typical cases, Spring Boot considers creating a `DataSource` when:

- Required JDBC/`DataSource` classes are on the classpath.
- No user-defined `DataSource` bean exists that causes default auto-configuration to back off.
- No auto-configuration exclusions apply; in particular, when the application provides an R2DBC `ConnectionFactory` bean, JDBC auto-configuration normally backs off under Boot's conditions.
- Enough information exists to build a `DataSource`: a valid URL/driver or a supported embedded database.

Spring Boot prefers available connection pools; when HikariCP is on the classpath alongside the JDBC starter, Hikari is usually chosen. Applications can specify an implementation via `spring.datasource.type` when special needs arise.

No manual bean is needed:

~~~java
// Usually NOT needed in a standard Boot JDBC application:
@Bean
DataSource dataSource() {
    // Manually read URL, credentials, and initialize connection pool...
    return ...;
}
~~~

Declaring a custom `DataSource` bean causes some default auto-configurations to **back off**; the application then takes responsibility for property binding, pooling, transactions, and effects on other beans.

## 3. Configuring spring.datasource.* via application.yml

Example of an order-processing application writing to PostgreSQL:

~~~yaml
# application.yml
spring:
  datasource:
    url: ${DB_JDBC_URL:jdbc:postgresql://localhost:5432/orders_db}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s
      validation-timeout: 1s
~~~

The `localhost` address, database name, and username are **development environment examples only**. The `DB_PASSWORD` variable must be supplied from the environment or a secret manager; never place real values in the repository or documentation examples.

| Property | Meaning | Notes |
| --- | --- | --- |
| `spring.datasource.url` | JDBC URL to the DB | Usually sufficient for Boot to identify the driver |
| `spring.datasource.username` | Connection username | Least-privilege permissions for the workload |
| `spring.datasource.password` | Connection password | Sourced from a secret/config provider |
| `spring.datasource.driver-class-name` | JDBC driver class name (optional) | Set only when needed or when the URL cannot be inferred |
| `spring.datasource.type` | `DataSource` implementation | Specify when not using the default choice |
| `spring.datasource.hikari.pool-name` | Hikari pool name | Use a stable name for observability |
| `spring.datasource.hikari.maximum-pool-size` | Maximum pool connections | Must match DB capacity and replica count |
| `spring.datasource.hikari.connection-timeout` | Maximum wait time to acquire a connection from the pool | Not the SQL query timeout |
| `spring.datasource.hikari.validation-timeout` | Time limit for validating connection liveness | Must be reasonable relative to connection timeout |

Boot binds configuration through **relaxed binding**. For example, the YAML key `spring.datasource.url` can also be supplied via the standard environment variable `SPRING_DATASOURCE_URL`; `spring.datasource.hikari.maximum-pool-size` corresponds to `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE`. Property sources follow Spring Boot's externalized configuration precedence rules, so verify the effective configuration actually applied at runtime.

### 3.1. Why Separate the datasource and hikari Groups?

- `spring.datasource.*` contains basic connection settings processed by Boot's `DataSourceProperties`.
- `spring.datasource.hikari.*` contains HikariCP-specific properties.
- If Boot selects a pool other than Hikari, `spring.datasource.hikari.*` keys are not universal settings across all implementations.
- Avoid arbitrarily setting `spring.datasource.hikari.jdbc-url` instead of `spring.datasource.url` in standard Boot configuration. `spring.datasource.url` is designed by Boot to bind via `DataSourceProperties` and handle differences in pool URL property names.

An alternative configuration example using environment variables:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db.internal:5432/orders_db
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=<value provided by secret manager>
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=12
~~~

The password line here is an illustrative placeholder, not a valid password. Never print password values into logs, traces, or configuration inspection outputs.

### 3.2. Environment and Profile-Based Configuration

Profile files can be used to set **non-secret** parameters per environment:

~~~yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_dev
  hikari:
    maximum-pool-size: 4
~~~

~~~yaml
# application-prod.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 2s
~~~

In the production example, the URL, username, and password should come from environment variables or a secret store. Profile values only apply when the corresponding profile is active and may be overridden by higher-precedence configuration sources.

Consider **total connections = max pool per instance × running instances**, plus connections for migrations, jobs, monitoring, and other workloads. A pool of 20 connections across 10 replicas can demand up to 200 connections, not 20.

## 4. How Does Boot Infer the JDBC Driver from the URL?

### 4.1. General Rules

A JDBC URL has the `jdbc:` prefix and a driver identifier, such as `jdbc:postgresql:` or `jdbc:mysql:`. When `spring.datasource.driver-class-name` is not declared, Spring Boot uses information from the URL to identify a recognized database type and look up the corresponding default driver class name.

Conceptually, the decision logic works like this:

~~~text
Is spring.datasource.driver-class-name set?
  |
  +-- Yes --> use configured driver name, check classpath
  |
  +-- No
        |
        +-- Recognized JDBC URL present?
        |      |
        |      +-- Yes --> infer driver class name from URL
        |      +-- No --> explicit driver or other config needed
        |
        +-- No URL, but supported embedded DB present?
               |
               +-- Yes --> Boot may create an embedded DataSource
               +-- No --> insufficient connection info
~~~

This is a **behavioral description**, not Boot's verbatim source code. `DataSourceProperties` is responsible for determining the driver/URL to use, relying on Boot's catalog of recognized JDBC URLs (such as `DatabaseDriver`). It only inspects the URL to **infer the class name**; it does not actively query the database server to ask what engine is running.

### 4.2. Table of Common URLs and Drivers

| Sample JDBC URL | Commonly inferred JDBC driver |
| --- | --- |
| `jdbc:postgresql://db.example:5432/orders_db` | `org.postgresql.Driver` |
| `jdbc:mysql://db.example:3306/orders_db` | `com.mysql.cj.jdbc.Driver` |
| `jdbc:mariadb://db.example:3306/orders_db` | `org.mariadb.jdbc.Driver` |
| `jdbc:sqlserver://db.example:1433;databaseName=orders_db` | `com.microsoft.sqlserver.jdbc.SQLServerDriver` |
| `jdbc:oracle:thin:@//db.example:1521/ORCLPDB1` | `oracle.jdbc.OracleDriver` |
| `jdbc:h2:mem:orders_test` | `org.h2.Driver` |
| `jdbc:hsqldb:mem:orders_test` | `org.hsqldb.jdbc.JDBCDriver` |

These class names are typical examples for modern JDBC drivers. Different Boot versions may add or adjust recognized URL catalogs; for specialized drivers, consult the vendor's documentation and configure the class explicitly when needed.

**Three conditions for a successful connection:**

1. The URL has valid syntax and points to the right database endpoint.
2. The appropriate JDBC driver JAR is on the runtime classpath.
3. Network, TLS, credentials, permissions, and the database server are all healthy and valid.

Boot correctly inferring `org.postgresql.Driver` **does not mean** the PostgreSQL JAR is included in your build. Conversely, having the right JAR with a wrong host/port or password will still fail to connect.

### 4.3. No Need to Declare driver-class-name in Common Cases

With:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_db
    username: orders_app
    password: ${DB_PASSWORD}
~~~

and dependency:

~~~groovy
runtimeOnly 'org.postgresql:postgresql'
~~~

Boot normally has enough information to choose `org.postgresql.Driver`. Also adding:

~~~yaml
spring:
  datasource:
    driver-class-name: org.postgresql.Driver
~~~

is valid, but usually **redundant**. Specifying it "just to be safe" can cause mistakes when switching from PostgreSQL to MySQL or when replacing a driver.

### 4.4. When Is driver-class-name Needed?

Some JDBC URLs use prefixes or driver classes that Boot's default catalog does not recognize:

- Less common or vendor-supplied databases/drivers.
- URLs for a proxy/wrapper such as specialized JDBC instrumentation.
- JDBC drivers using custom URL syntax not mapped by Boot.
- Cases where the application must explicitly choose a different driver among multiple drivers supporting the same URL.

In those cases, configure:

~~~yaml
spring:
  datasource:
    url: jdbc:vendorx://db.example:9999/orders_db
    driver-class-name: com.vendorx.jdbc.Driver
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

**This is a hypothetical example**, not a real driver or vendor. You must still add the proper JAR for `com.vendorx.jdbc.Driver` and verify that the driver accepts the URL.

If you set only `driver-class-name` **without a URL**, Boot cannot guess the hostname, port, and database name of an external DB. Exceptions include using an embedded database, a JNDI datasource, or a custom configuration mechanism.

### 4.5. Distinguishing Boot Inference from DriverManager

Standard JDBC provides a driver registration mechanism (SPI) so `DriverManager` can locate a driver capable of handling a URL. Spring Boot additionally provides **inference of a known driver class from the URL** to build a `DataSource`.

Therefore:

- Having the driver JAR on the classpath is a prerequisite for a given driver.
- Boot's URL catalog does not cover every JDBC driver in existence.
- If a URL is unrecognized by Boot, the driver may still be JDBC-compliant, but Boot configuration may require `driver-class-name` or a custom `DataSource` bean.
- Do not use JDBC `driver-class-name` to configure R2DBC connections. R2DBC uses `spring.r2dbc.url` and its own `ConnectionFactory`.

## 5. Practical Example: DataSource → JdbcTemplate → SQL Adapter

Suppose an adapter needs to retrieve order status when a message arrives from a broker. Using `spring-boot-starter-jdbc`, the PostgreSQL driver, and the YAML from section 3, Boot automatically creates the `DataSource` and configures `JdbcTemplate` in a standard setup.

Create the table (managed via Flyway/Liquibase migrations in real systems):

~~~sql
CREATE TABLE integration_orders (
    order_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    last_event_id VARCHAR(100) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

DTO representing the read result:

~~~java
// OrderStatus.java
public record OrderStatus(String orderId, String status) {
}
~~~

SQL adapter:

~~~java
// JdbcOrderStatusAdapter.java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStatusAdapter {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderStatusAdapter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public OrderStatus findById(String orderId) {
        return jdbcTemplate.queryForObject(
                """
                SELECT order_id, status
                FROM integration_orders
                WHERE order_id = ?
                """,
                (rs, rowNum) -> new OrderStatus(
                        rs.getString("order_id"),
                        rs.getString("status")),
                orderId);
    }
}
~~~

Here:

1. `JdbcOrderStatusAdapter` receives `JdbcTemplate` from the Spring container.
2. `JdbcTemplate` acquires a connection from the Boot-configured `DataSource`.
3. The connection pool uses the PostgreSQL JDBC driver matching the URL to talk to the DB.
4. The query uses a `?` placeholder instead of string concatenation, passing the parameter value safely.
5. `queryForObject(...)` expects exactly one row: if none is found, Spring may throw `EmptyResultDataAccessException`. The adapter should translate this into an appropriate domain result type.

In larger applications, define a **port** such as `OrderStatusPort` in the domain/application layer and have the JDBC adapter implement that port. That way, HTTP, cache, or broker handlers do not depend directly on `JdbcTemplate`.

### 5.1. Persisting Data and Using Proper Transaction Boundaries

An update operation can live inside a Spring-managed application service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderUpdateService {

    private final OrderStore orderStore;
    private final InboxStore inboxStore;

    public OrderUpdateService(
            OrderStore orderStore,
            InboxStore inboxStore) {
        this.orderStore = orderStore;
        this.inboxStore = inboxStore;
    }

    @Transactional
    public void apply(OrderEvent event) {
        boolean firstTime =
                inboxStore.insertIfAbsent(event.eventId());

        if (!firstTime) {
            return;
        }

        orderStore.applyBusinessChange(event);
    }
}
~~~

`OrderStore`, `InboxStore`, and `OrderEvent` here are illustrative contracts, not built-in Spring types. `insertIfAbsent` must be implemented as an **atomic** operation backed by a database unique constraint, such as `INSERT ... ON CONFLICT DO NOTHING` on PostgreSQL. Both DB operations must share the **same transaction** and resource manager so the inbox marker rolls back if the business update fails.

Key points to remember:

- A pool-allocated connection does not mean every repository creates its own transaction.
- `@Transactional` normally takes effect when calls go through a Spring proxy, not plain self-invocation.
- The transaction manager must point to the exact `DataSource` used by the adapter, especially in multi-DB systems.
- An outbound partner HTTP request or broker publish **does not** automatically roll back just because a local SQL transaction failed.
- When updating a DB and publishing events to a broker, consider a **transactional outbox** to avoid losing events after commit and an idempotent consumer to tolerate redelivery.

## 6. HikariCP: Configuring the Pool and Understanding Timeouts

When using the JDBC starter with HikariCP on the classpath, Boot typically selects `HikariDataSource`. The pool bounds how many physical connections are opened and reuses them.

Common parameters:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 3s
      idle-timeout: 10m
      max-lifetime: 30m
      validation-timeout: 1s
~~~

Values are illustrative; there is no single optimal configuration for every database or workload. Depending on topology, replica count, and query latency, a small stable pool can outperform a very large one.

| Property | Controls | Do not confuse with |
| --- | --- | --- |
| `maximum-pool-size` | Limit of connections held in the pool | Unlimited concurrent SQL statements |
| `minimum-idle` | Minimum idle connections Hikari tries to maintain | Minimum throughput guarantee |
| `connection-timeout` | Wait time for the pool to supply a connection | TCP open timeout or total query timeout |
| `idle-timeout` | How the pool shrinks idle connections under eligible conditions | Data TTL or transaction TTL |
| `max-lifetime` | Maximum lifetime of a physical connection in the pool | Timeout for an executing query |
| `validation-timeout` | Time limit for validating a connection | End-to-end business timeout |

Hikari manages the pool alongside the application lifecycle. If the database or a server/load balancer enforces a connection timeout, `max-lifetime` should be tuned to reduce reusing dead connections. Do not choose arbitrary numbers without measuring system latency and behavior.

**Three separate timeout types:**

1. **Borrowing a connection from the pool:** `spring.datasource.hikari.connection-timeout`.
2. **Network/driver connection:** e.g., connect/socket timeouts supported by the JDBC driver, typically configured via driver-specific properties.
3. **SQL/transaction execution:** query timeout, transaction timeout, or driver/database statement cancellation mechanisms.

Increasing `maximum-pool-size` will not fix a slow SQL query caused by a missing index. Conversely, pool exhaustion can be a symptom of long-running transactions, unclosed connections in manual JDBC code, or request volume exceeding DB capacity.

### 6.1. Driver-Specific Properties

When a driver needs fine-grained settings such as application name, socket timeout, or SSL, you can use the JDBC URL or forward properties to the driver:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        ApplicationName: order-integration
~~~

`ApplicationName` above is a PostgreSQL JDBC property; it is **not** universal across all drivers. Each vendor defines its own property names, value types, and time units. Always check the driver documentation before configuring. With SSL/TLS, never disable certificate verification just to bypass certificate errors in production.

## 7. What Happens When the URL Is Missing or an Embedded Database Is Present?

Spring Boot supports embedded databases such as H2, HSQLDB, or Derby when the appropriate dependencies and configuration are present. In some cases without `spring.datasource.url`, Boot can create an embedded `DataSource`:

~~~groovy
// Example for testing or demo
runtimeOnly 'com.h2database:h2'
~~~

This is convenient for learning and testing, but carries two risks:

1. If you forget to configure the PostgreSQL URL in an unintended environment, the application might start with an embedded DB when H2 is on the runtime classpath.
2. H2's SQL syntax, transaction isolation, data types, indexes, and constraints are **not identical** to PostgreSQL or MySQL.

Therefore, do not treat passing H2 tests as sufficient proof for PostgreSQL-specific queries, `ON CONFLICT` syntax, transaction isolation, or driver behavior. For critical flows, use Testcontainers or a real test database close to production.

If there is **no** URL and no eligible embedded DB, a typical configuration failure looks like:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.

Reason: Failed to determine a suitable driver class
~~~

The exact message varies by Boot version. This is a signal to check **URL configuration, driver, and classpath** before changing repository logic.

## 8. Driver Inference Errors and Diagnostics

Do not lump every connection error together as "database down."

| Symptom | Possible causes | How to check |
| --- | --- | --- |
| `Failed to determine a suitable driver class` | Missing URL, unrecognized URL, no embedded DB | Check `spring.datasource.url` and add `driver-class-name` if needed |
| `Cannot load driver class: org.postgresql.Driver` | Missing driver JAR at runtime or wrong class name | Inspect runtime classpath/dependencies |
| `No suitable driver` | Driver rejects URL, malformed URL syntax, or matching driver not registered | Match URL against the driver in use |
| `Connection refused` | Server port not listening, wrong host/port, or network blocked | Check DNS, routing, firewall, port, DB service |
| `Connection timed out` | Network/TLS/DB did not respond in time | Check timeouts at each layer and server logs |
| `password authentication failed` / `Access denied` | Wrong user, secret, or privileges | Check secret injection, DB auth policy, and user |
| `database does not exist` | Wrong DB name or DB not provisioned | Check DB/schema name and DB creation permissions |
| `Connection is not available, request timed out` | Pool exhausted, DB overloaded, or connection leak | Inspect active/idle/pending pool stats and slow queries |
| `Table ... does not exist` | Migrations not run or wrong schema | Check Flyway/Liquibase and default schema |
| `Unknown property hikari...` or settings ignored | Wrong prefix/property type or different pool active | Check property metadata and actual pool implementation |
| App has R2DBC but no JDBC DataSource created | `ConnectionFactory` causes JDBC auto-config to back off under Boot conditions | Configure explicitly if both stacks are needed |

**Reasonable diagnostic order:**

1. Confirm which profiles and property sources are actually active, displaying only **non-secret** values.
2. Verify the URL starts with `jdbc:` and follows the exact vendor format.
3. Verify the driver JAR is on the runtime classpath, not just the test classpath.
4. Verify the driver class name if `driver-class-name` is configured.
5. Test network reachability to the database host/port using permitted environment tools.
6. Check credentials, TLS, database name, and permissions.
7. If the pool initializes but queries fail, inspect schema, migrations, SQL, and transactions.

In production, never print `spring.datasource.password`, raw JDBC URLs containing secrets, or full connection properties in logs. Some drivers allow passwords in URL query parameters; avoid this to reduce secret leakage through logs and traces.

### 8.1. Common Mistakes

**Mistake 1: Driver URL does not match dependency.**

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://db.example:3306/orders_db
    driver-class-name: org.postgresql.Driver
~~~

A MySQL URL paired with the PostgreSQL driver is invalid. Remove the explicit driver if Boot recognizes the URL and add the MySQL driver, or fix both URL and dependency to match the target database.

**Mistake 2: Using a URL without the `jdbc:` prefix.**

~~~yaml
spring:
  datasource:
    url: postgresql://db.example:5432/orders_db
~~~

This is not a standard JDBC URL expected by the PostgreSQL `DataSource` driver. For PostgreSQL JDBC, `jdbc:postgresql://...` is required.

**Mistake 3: Using an R2DBC URL as a JDBC URL.**

~~~yaml
spring:
  datasource:
    url: r2dbc:postgresql://db.example:5432/orders_db
~~~

`r2dbc:` belongs to the R2DBC stack, not `spring.datasource.url` for JDBC. When using R2DBC, configure `spring.r2dbc.*` and the corresponding R2DBC driver dependency.

**Mistake 4: Setting `spring.datasource.hikari.jdbc-url` while omitting `spring.datasource.url`.**

In standard Boot configuration, set `spring.datasource.url` so Boot binds basic settings and infers the driver. Use Hikari's `jdbcUrl` directly only for clear reasons, notably when manually constructing a `HikariDataSource`, where different binding rules apply.

## 9. SQL Schema, Migrations, and Initialization Order

**Connecting successfully** does not mean the database already has the schema the application needs. These responsibilities are separate:

- Creating databases/users/permissions: infrastructure provisioning.
- Defining tables/indexes/constraints: migrations and schema management.
- Choosing DB URL + driver + pool: connection configuration.
- Executing business logic: repositories, JdbcTemplate, JPA, or adapters.
- Transactions/resilience: transaction manager, outbox/inbox, and retries.

Spring Boot can run `schema.sql` and `data.sql` scripts when configured appropriately. `spring.sql.init.mode` controls SQL initialization, with default behavior and limits tied to embedded databases and Boot conditions.

Demo-only example:

~~~yaml
spring:
  sql:
    init:
      mode: always
~~~

**Do not enable `always` in production just to auto-create schemas on every deploy.** For real systems, prefer Flyway or Liquibase for versioned migrations with controlled execution order and change history. Ensure migrations run before services begin reading or writing data.

If the application uses JPA, properties such as `spring.jpa.hibernate.ddl-auto` manage Hibernate's schema behavior, **not** as a substitute for `spring.datasource.*`. Avoid configuring multiple competing mechanisms that auto-create or alter tables.

## 10. Configuring Multiple DataSources: Limits of the Default Case

`spring.datasource.*` is designed as a convenience for the **default DataSource**. If an application reads from an accounting database and writes to an orders database, you must explicitly separate the two DataSources and transaction managers.

Example using custom application properties:

~~~yaml
app:
  datasource:
    orders:
      url: ${ORDERS_DB_URL}
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
    reporting:
      url: ${REPORTING_DB_URL}
      username: ${REPORTING_DB_USER}
      password: ${REPORTING_DB_PASSWORD}
~~~

`app.datasource.*` **is not automatically turned into two DataSources by Boot** just by appearing in YAML. You must define beans yourself with `@ConfigurationProperties` and `DataSourceProperties`/`DataSourceBuilder`, mark `@Primary` for the default when needed, and configure each source's `JdbcTemplate` and transaction manager consistently.

A common mistake is binding an `url` property directly onto a manually created `HikariDataSource`. Hikari uses the `jdbcUrl` property, whereas Boot's `DataSourceProperties` understands `url` and maps it properly via `initializeDataSourceBuilder()`. Reuse `DataSourceProperties` for each custom property group.

With multiple databases:

- Attach `@Qualifier` to each adapter's DataSource, JdbcTemplate, and transaction manager.
- When using `@Transactional`, specify the exact transaction manager for the target resource.
- Distinguish between "two DataSources on the same PostgreSQL server" and "two independent databases," because atomicity and commit boundaries differ.
- Transactions across two DBs or between a DB and a broker are not atomic by default; when cross-system reliability is needed, consider outbox, saga, or compensating mechanisms.
- Observe each pool separately, keep pool names low-cardinality, and never embed per-request tenant IDs into pool names.

When an application has both an R2DBC `ConnectionFactory` and a JDBC `DataSource`, you may need to explicitly define the JDBC components instead of relying on default auto-configuration; do not assume adding both starters automatically wires both stacks completely.

## 11. Reliability of the SQL Adapter in an Integration Flow

### 11.1. Receiving Potentially Redelivered Events

Brokers typically allow redelivery. A consumer may:

1. Receive `OrderPaid(eventId=E-100)`.
2. Write order state to SQL.
3. Crash before acknowledging the broker.
4. Receive the same message again after restarting.

Correct driver inference from the URL and a healthy connection pool **do not prevent duplicate effects**. To avoid duplicate writes, use a stable idempotency key in the data contract and a unique constraint in the database.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Within a transaction, the consumer attempts to insert `event_id`; if the event already exists, it skips re-applying business side effects. How unique constraint errors, retries, and transaction rollbacks behave depends on the database/driver. Never use an unguarded `SELECT exists` followed by `INSERT` in a multi-consumer system.

### 11.2. Ambiguous Outcomes on Errors

If a SQL write returns a network error after being sent, the client may **not know for sure whether the server committed or not**. This is especially critical when a transaction reaches the commit boundary. Retrying a create operation without idempotency can create duplicate rows or duplicate side effects.

Separate error categories:

| Error | Nature | Suggested handling |
| --- | --- | --- |
| Invalid SQL/schema | Non-transient error | Fix migration/SQL; do not continuously retry |
| Unique key violation | Likely business duplicate or invalid data | Inspect contract before deciding to ignore |
| Deadlock/serialization conflict | Transaction may be safely retried | Bounded retry, backoff, idempotency |
| Connection lost before operation | Safe to retry once confirmed no side effect occurred | Bound retries and observe |
| Error right at commit/timeout | Outcome may be unknown | Reconcile state using business key |
| Pool exhausted | Overload, connection leak, or slow query | Measure pool and limit concurrency |

Spring JDBC translates `SQLException` into `DataAccessException` subclasses for better classification. Still, never catch `DataAccessException` and blindly retry everything; base decisions on the actual error type, driver semantics, and operation idempotency.

### 11.3. Transactions, Cache, and Outbox

In an integration flow:

~~~mermaid
flowchart LR
    A["Consume Order event"] --> B["SQL transaction"]
    B --> C["Upsert business row"]
    B --> D["Insert inbox key"]
    B --> E["Insert outbox event"]
    E --> F["Outbox relay / CDC"]
    F --> G["Message broker"]
    G --> H["Downstream consumer"]
    B -.-> I["Cache eviction after commit"]
~~~

Writing the business row + inbox + outbox in the **same DB transaction** prevents the state of "business updated, but forgot to save the outbound message." The outbox relay can still publish duplicates if it crashes before marking the row sent, so downstream consumers must be idempotent.

Evicting a cache before the transaction commits can cause readers to reload stale data. Therefore, when consistency matters, run cache invalidation after commit or use a tested transaction-aware mechanism. This is an integration-layer policy, not something `spring.datasource.url` decides on its own.

## 12. Testing Driver Inference and SQL Connectivity

Good tests verify not only that the Spring context starts, but also that **the real DB is used, the right driver is active, and errors are classified accurately**.

### 12.1. Unit Tests for Business Logic

Message classification logic, idempotency key construction, or DTO mapping should be tested independently using fake ports. Unit tests do not need to start a database or create a `DataSource`.

### 12.2. JDBC Slice Tests

Spring Boot supports `@JdbcTest` for testing repositories/`JdbcTemplate` in a focused context slice. Depending on dependencies and settings, the test slice may replace the DataSource with an embedded database. Never assume a passing JDBC test on H2 proves your production PostgreSQL URL works.

Recommended tests:

| Scenario | Expectation |
| --- | --- |
| Valid PostgreSQL URL and driver JAR present | Context creates DataSource and queries succeed |
| Missing driver JAR | Startup/connection fails with a clear cause |
| Malformed JDBC URL | Error is caught and does not connect to the wrong database |
| Incorrect password | Connection is rejected; no secret is logged |
| Migrations not applied | Schema error is detected |
| SQL unique key violated | Adapter translates to appropriate business/duplicate handling |
| Pool saturated | Timeout/backpressure occurs with alert metrics |
| Transaction fails | Business update, inbox, and outbox all roll back together |
| Redelivery of same `eventId` | No duplicate business side effects created |

### 12.3. Integration Testing with Real PostgreSQL via Testcontainers

For driver inference and PostgreSQL syntax, prefer a containerized database in tests. Example skeleton using JUnit 5 and Testcontainers (corresponding test dependencies must be included):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class SqlConnectivityIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void applicationUsesTestDatabase() {
        // Real assertions should call the repository and verify the data.
    }
}
~~~

This example only illustrates **how to wire a container's URL, username, and password into Spring Boot**. For meaningful tests, prepare the schema via migrations and assert real repository/transaction behavior; this snippet is not a complete test on its own. Testcontainers requires Docker or a compatible container runtime. Artifact coordinates may vary across Testcontainers versions, so let your project's dependency management resolve versions.

Notice this test **does not declare `spring.datasource.driver-class-name`**: when the PostgreSQL driver is present, it directly verifies driver inference from `postgres.getJdbcUrl()`. You can assert a `SELECT 1` query or query a migrated table rather than only asserting that the `DataSource` bean is non-null.

## 13. Observing and Operating Connectivity

Adding Actuator enables inspection of supported metrics and health indicators:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

With HikariCP and Micrometer, Boot can expose metrics such as `hikaricp.connections.*` and `jdbc.connections.*` (exact names, tags, and presentation depend on versions and registries). Particularly useful metrics:

| Metric / signal | Operational question |
| --- | --- |
| Active connections | Is pool utilization nearing capacity? |
| Idle connections | Are idle connections ready for incoming requests? |
| Pending threads | Are callers waiting for connections? |
| Connection acquisition time | Is wait time for a connection rising? |
| Connection creation/timeout failures | Are the DB, network, or pool causing errors? |
| HTTP/broker backlog | Is a slow SQL adapter backing up upstream? |
| Query/transaction latency (separately instrumented) | If the pool is healthy, which SQL is slow? |

A `DataSourceHealthIndicator` can check database connectivity when Actuator health is supported and enabled. Still, a passing health check only proves the DB **can answer that probe**, not that every query, migration, or table privilege is valid.

To observe individual SQL statements, separate instrumentation may be needed; **pool metrics are not SQL tracing**. Never attach `orderId`, `eventId`, raw SQL containing user data, or URLs containing passwords to metric tags or trace attributes.

A quick diagnostic flowchart when latency spikes:

~~~mermaid
flowchart TD
    A["Latency increases"] --> B{"High pool pending?"}
    B -->|"Yes"| C["Measure active, pool size, connection hold time"]
    C --> D["Check slow queries, long transactions, capacity"]
    B -->|"No"| E{"Slow DB queries?"}
    E -->|"Yes"| F["Query plan / index / lock / IO"]
    E -->|"No"| G["Check HTTP, broker, cache, and processing overhead"]
~~~

Increasing pool size without checking DB capacity can make things worse. Account for instance count, connection hold time, traffic bursts, and database connection limits.

## 14. Security and Environment Operations

A reliable connection setup requires attention to:

- **Secrets:** source passwords from a secret manager or environment variables; avoid printing entire `DataSourceProperties` or JDBC URLs containing secrets.
- **Privileges:** create task-specific users. Runtime users generally do not need DDL/DBA privileges when migrations run under a separate account.
- **TLS:** verify server certificates according to driver documentation; do not disable SSL verification in production.
- **Network:** keep the DB on a private network; restrict firewall rules to authorized sources rather than exposing the database publicly.
- **Credential rotation:** verify how live pools react and when new connections are established.
- **Configuration:** verify active profiles, property overrides, and secret injection before deploying.
- **Capacity:** `replicas × pool max` must stay within DB limits.
- **Recovery:** bounded retries, backoff, idempotency, alerts, and circuit breakers when interacting with multiple downstream systems.
- **Backups/migrations:** do not confuse "able to connect" with "having valid or recoverable data."

In Kubernetes or containerized environments, `localhost` inside the application points to **that container/pod itself**. The database address must use a hostname or service name reachable from the container. A URL that works on a laptop is not automatically valid in a container environment.

## 15. Checklist Before Adding a SQL Adapter to an Integration Flow

- [ ] Added the right JDBC/JPA starter and JDBC driver on the **runtime classpath**.
- [ ] `spring.datasource.url` uses the proper `jdbc:<vendor>:...` format and targets the right database per environment.
- [ ] Configured `driver-class-name` only when necessary; understand Boot's URL-based inference.
- [ ] Sourced username/password securely; no secrets in source code, logs, or traces.
- [ ] Pool sized appropriately for DB capacity and instance count; distinguish pool timeout, network timeout, and SQL timeout.
- [ ] Migrations create the schema before adapters query it; do not rely on H2 to verify engine-specific SQL.
- [ ] Tested URL → driver → DataSource against a real database or Testcontainers.
- [ ] Defined the transaction manager and local transaction boundaries on the right resource.
- [ ] Implemented idempotency/inbox for redeliveries and outbox if reliable DB → broker synchronization is needed.
- [ ] Classified driver, connection, authentication, constraint, and timeout errors.
- [ ] Enabled needed pool/health metrics and secured management endpoints.
- [ ] If using multiple DataSources or both JDBC and R2DBC, configured explicit beans and qualifiers.

**Technical conclusion:** `spring.datasource.*` is Spring Boot's primary SQL connection configuration surface; in common cases, Boot **infers the JDBC driver class from the URL** and creates the `DataSource`/connection pool for adapters to use. This inference eliminates boilerplate configuration, but does not replace driver dependencies, proper database setup, security, pool sizing, transactions, idempotency, or integration flow testing.

## References

- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource` configuration, JDBC, `JdbcTemplate`, connection pooling, and SQL initialization.
- [Spring Boot 3.5 — SQL Databases](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): cross-reference properties and APIs for Boot 3.x.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, placeholders, profiles, and relaxed binding.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, SQL parameters, exception translation, and resource management.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction boundaries, and resource coordination.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): pool properties, timeouts, and lifecycle.
- [PostgreSQL JDBC — Connecting to the Database](https://jdbc.postgresql.org/documentation/use/): PostgreSQL JDBC URL syntax, driver, and connection properties.
