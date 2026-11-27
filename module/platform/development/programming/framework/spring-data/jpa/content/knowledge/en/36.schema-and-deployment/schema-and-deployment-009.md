# Configuring Dialects, Timezones, Pools, and Timeouts per Environment

## 1. Why Must Database Configuration Be Environment-Specific?

Spring Data JPA runs on top of a Hibernate/JPA provider, a JDBC driver, and a database server. A request only accesses the database successfully when all of these layers agree on the vendor, data types, timezone, connections, and time limits.

Local, test, staging, and production environments typically differ in:

- JDBC URL, hostname, port, and database/schema.
- Database vendor and engine version.
- Accounts, privileges, secrets, and TLS.
- Timezones of the JVM, JDBC connection, and database session.
- Connection pool size and number of application instances.
- Timeouts for connecting, acquiring connections, SQL statements, locks, and transactions.
- Migration settings, schema validation, and resource limits.

If these values are hard-coded in source code, the application becomes difficult to deploy across environments and prone to errors such as wrong dialects, time skew, connection pool exhaustion, or hanging requests.

The deployment principle is to keep JPA logic uniform, move environment configuration into external configuration/profiles/secrets, select a database engine matching production, and verify the effective values at application startup.

## 2. Configuration Layers to Distinguish

| Component | Responsibility | Example |
|---|---|---|
| JDBC driver | Communicates with the database | PostgreSQL JDBC, MySQL Connector/J |
| JDBC URL | Identifies the database and connection options | \`jdbc:postgresql://db:5432/app\` |
| Dialect | Translates Hibernate queries into matching SQL | PostgreSQLDialect, MySQLDialect |
| JVM timezone | Default timezone of the Java process | UTC |
| Hibernate JDBC timezone | Timezone used when binding/reading certain JDBC values | \`hibernate.jdbc.time_zone=UTC\` |
| Database session timezone | Timezone of the session holding the connection | \`SHOW TimeZone\`, \`@@session.time_zone\` |
| Connection pool | Reuses and bounds JDBC connections | HikariCP |
| Connection timeout | Limits waiting for/opening a connection | Hikari acquisition, driver connect |
| Query timeout | Limits SQL execution time | JPA/JDBC/database |
| Transaction timeout | Limits transaction duration | \`@Transactional(timeout = 5)\` |

One setting does not replace another. For example, setting Hibernate's JDBC timezone to UTC does not automatically change the PostgreSQL session timezone. Likewise, Hikari's connectionTimeout is not a query timeout.

## 3. JDBC URL and Driver

### 3.1. PostgreSQL

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/customer_db
spring.datasource.username=customer_app
spring.datasource.password=${DB_PASSWORD}
```

The driver is \`org.postgresql:postgresql\`. Spring Boot normally infers the driver from the JDBC URL when the driver is on the classpath; you do not need to declare \`spring.datasource.driver-class-name\` without a specific reason.

### 3.2. MySQL

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db
spring.datasource.username=customer_app
spring.datasource.password=${DB_PASSWORD}
```

The driver is MySQL Connector/J; the current artifact is typically \`com.mysql:mysql-connector-j\`. Let Spring Boot infer the driver from the URL as well.

### 3.3. Keep URLs and credentials out of source code

Local setups may use containers or a database on the developer's machine; CI uses Testcontainers; staging and production use managed database endpoints. Put URLs in profiles or environment variables rather than editing code and building separate artifacts per environment.

Never commit passwords, tokens, or private keys to Git. Use the deployment platform's secret store, CI secrets, or protected environment variables. Never print full JDBC URLs containing credentials into logs.

Production typically requires TLS, CA certificates, and hostname verification per infrastructure policy. TLS configuration depends on the driver and certificates; never copy an SSL flag from one vendor to another.

Verify from the actual host/container running the application:
- Does DNS resolve the database hostname?
- Do firewalls/routes allow connections to the port?
- Is the TLS certificate valid and matching the hostname?
- Does the user have permission to connect to the database/schema?
- Do proxies/load balancers enforce idle timeouts or connection lifetime limits?

Connecting successfully from a laptop does not prove a production pod shares the same network path.

## 4. Hibernate Dialect

### 4.1. What is a dialect for?

A dialect describes SQL differences across databases, such as pagination syntax, data types, generated values, sequences/identities, SQL functions, locking, and DDL. Hibernate uses the dialect to generate SQL tailored to the database accessed by the JDBC connection.

### 4.2. Modern Hibernate usually auto-detects the dialect

From Hibernate 6 onward, Hibernate inspects JDBC metadata to determine the vendor/version and selects an appropriate dialect automatically. Typical Spring Boot applications do not need to declare a dialect manually.

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_db
    username: customer_app
    password: ${DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
```

If the URL connects to PostgreSQL, Hibernate picks the PostgreSQL dialect. If the URL points to MySQL, the matching dialect is detected from metadata.

Do not hard-code a PostgreSQL dialect into the artifact and deploy that artifact against MySQL. The wrong dialect can cause Hibernate to emit incompatible SQL or map data types incorrectly.

### 4.3. When must a dialect be explicitly declared?

Override only for a specific reason:
- Using a custom dialect provided by the application/library.
- Hibernate cannot read JDBC metadata during bootstrap.
- A special environment requires initializing metadata before opening a connection.
- A confirmed workaround exists for a specific provider/database version.

Spring Boot supports:

```yaml
spring:
  jpa:
    database-platform: com.example.persistence.CustomPostgreSQLDialect
```

Or the Hibernate property:

```properties
spring.jpa.properties.hibernate.dialect=com.example.persistence.CustomPostgreSQLDialect
```

Choose only one clear way to declare it. \`spring.jpa.database-platform\` is a Spring Boot property; \`hibernate.dialect\` is a Hibernate property forwarded via \`spring.jpa.properties.*\`.

With Hibernate 6+, do not use old dialect classes just because they appeared in Hibernate 5 guides. Several version-specific old dialects were merged or deprecated. Use a dialect compatible with the Hibernate major version in use.

### 4.4. Do not confuse dialect with driver

| Configuration | Example | Purpose |
|---|---|---|
| JDBC URL | \`jdbc:postgresql://...\` | Selects endpoint/database |
| JDBC driver | PostgreSQL JDBC | Opens connections using the protocol |
| Hibernate dialect | PostgreSQLDialect | Generates database-specific SQL |
| JPA provider | Hibernate | Executes mappings/persistence |

Changing the dialect does not turn a PostgreSQL driver into a MySQL driver. Switching vendors requires changing the URL, driver, schemas/migrations, and running compatibility tests.

## 5. Timezones: What Does the Data Represent?

Before configuring timezones, clarify whether a temporal column represents a calendar date, local wall-clock time, or an absolute instant on the timeline.

| Java Type | Meaning | When to Use |
|---|---|---|
| \`LocalDate\` | Calendar date without time/timezone | Birth dates, invoice dates |
| \`LocalTime\` | Time of day without date/timezone | Opening hours |
| \`LocalDateTime\` | Wall-clock date and time without offset/zone | Local appointment time when zone is tracked separately |
| \`Instant\` | An absolute point in time | Event timestamps, createdAt |
| \`OffsetDateTime\` | Date and time with a UTC offset | Instant paired with a known offset |
| \`ZonedDateTime\` | Date and time with ZoneId/region rules | Regional schedules like Asia/Ho_Chi_Minh |

Do not attach UTC to a \`LocalDateTime\` and treat it as an Instant unless the domain specifies that. An appointment at 09:00 in Hanoi is local wall-clock time; an event that occurred should be modeled with Instant or an equivalent type.

If future regional schedules must be reconstructed, store an IANA ZoneId such as \`Asia/Ho_Chi_Minh\` or \`Europe/Berlin\` per business needs. A fixed offset like \`+07:00\` does not capture a region's daylight saving rules.

## 6. Aligning Timezones Across JVM, Hibernate, and Database

### 6.1. UTC convention for instants

For fields representing absolute instants, common conventions are:
- Store/exchange instants in UTC.
- Convert to the user's timezone at the presentation layer.
- Do not rely on the host's default timezone.
- Test round-trips through JDBC and the real database.

You can set the JVM timezone in the runtime environment:

```bash
java -Duser.timezone=UTC -jar app.jar
```

This is a process-level setting. Never call \`TimeZone.setDefault()\` while the application is running because it affects all code using the default timezone.

### 6.2. Hibernate JDBC timezone

Hibernate provides the property:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

Or:

```properties
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
```

This property tells Hibernate which reference timezone to use when calling JDBC APIs that accept a Calendar, especially when binding/reading timestamp/time types. It does not set the database server or session timezone.

Setting both the JVM and Hibernate JDBC timezones to UTC reduces dependence on the host's default timezone. You must still verify the column type and database session timezone.

### 6.3. Hibernate storage for OffsetDateTime/ZonedDateTime

Hibernate offers timezone-aware storage strategies such as \`NORMALIZE\`, \`NATIVE\`, \`COLUMN\`, and \`AUTO\` depending on version/provider.

- \`NORMALIZE\`: normalizes the instant without preserving the original zone/offset in the timestamp column.
- \`NATIVE\`: uses the database's native timestamp with time zone type if supported by the dialect.
- \`COLUMN\`: stores the extra timezone component in a separate column.
- \`AUTO\`: provider picks a strategy based on database capabilities.

With Hibernate versions supporting this property, you can configure it explicitly:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        timezone:
          default_storage: NORMALIZE
```

Do not assume \`OffsetDateTime\` always preserves its original offset after saving and reading back. If you need to retain a ZoneId such as \`Asia/Ho_Chi_Minh\`, store the ZoneId in a separate property/column; a UTC timestamp stores only the instant, not the region name.

## 7. Timezone Differences Between PostgreSQL and MySQL

### 7.1. PostgreSQL

PostgreSQL has two common types:

- \`timestamp without time zone\`: wall-clock date and time without timezone. Passing a literal with a timezone into this type may strip the timezone portion.
- \`timestamp with time zone\` (\`timestamptz\`): PostgreSQL converts input to UTC for storage; on read/display, values convert to the session timezone. PostgreSQL does not retain the original zone name or offset.

Check the session timezone:

```sql
SHOW TimeZone;
SELECT CURRENT_TIMESTAMP;
```

You can set a default timezone for a role:

```sql
ALTER ROLE customer_app SET TimeZone TO 'UTC';
```

A new connection is required for the session to pick up the new default. \`SET LOCAL\` applies only to the current transaction; session \`SET\` affects that connection until changed again or closed. With pooling, never run \`SET\` and return the connection to the pool without resetting session state.

### 7.2. MySQL

MySQL distinguishes:
- \`TIMESTAMP\`: the server converts values from the session timezone to UTC on write and from UTC back to the session timezone on read.
- \`DATETIME\`: stores wall-clock date and time without automatic timezone conversion like TIMESTAMP.

Check timezone:

```sql
SELECT
    @@global.time_zone,
    @@session.time_zone,
    NOW(),
    UTC_TIMESTAMP();
```

MySQL Connector/J from 8.0.23 onward includes instant-related properties:
- \`connectionTimeZone\`: timezone used when the driver needs to convert.
- \`forceConnectionTimeZoneToSession\`: instructs the driver to set the session timezone to match connectionTimeZone.
- \`preserveInstants\`: instructs the driver to attempt preserving instants when reading/writing corresponding types.

Example URL when standardizing on a UTC session:

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true&preserveInstants=true
```

This configuration changes the session timezone; functions like \`NOW()\`, \`CURTIME()\`, and \`CURDATE()\` are affected. Apply it only when application semantics expect a UTC session and after checking driver/server versions. Do not treat this URL as a magic string for every schema.

### 7.3. Choosing the right column type

| Use Case | Usually Suitable Java Type | Database Type to Consider |
|---|---|---|
| Birth date | \`LocalDate\` | DATE |
| Opening hours | \`LocalTime\` | TIME |
| Local appointment schedule | \`LocalDateTime\` + separate ZoneId | timestamp without time zone / DATETIME |
| Order creation instant | \`Instant\` | PostgreSQL timestamptz; MySQL TIMESTAMP or UTC convention with DATETIME |
| Recurring regional schedule | LocalDateTime + IANA ZoneId | Local datetime and zone ID columns |

Do not choose columns based purely on the Java type name. Check Hibernate mappings, the JDBC driver, and exact database semantics.

## 8. Daylight Saving Time and Timestamp Precision

Some regions shift offsets seasonally. When clocks spring forward, a local time interval may not exist; when clocks fall back, a local time interval may occur twice.

Therefore:
- Use \`ZoneId\` with IANA region names when business rules depend on regional rules.
- Store Instant for past events.
- Store ZoneId if future regional schedules must be reconstructed.
- Never add/subtract a fixed hour offset to convert timezones.
- Test timestamps before and after DST transitions if the application serves DST-observing regions.

Beyond timezones, databases have precision limits. Java can hold nanoseconds in \`Instant\`, whereas the database/driver may store microseconds or another precision. For exact equality assertions, truncate to or compare within the precision supported by the schema.

A round-trip test should verify:
1. Java value before persisting.
2. Value after flush.
3. Value re-read in a fresh persistence context.
4. Behavior under different JVM/session timezones within supported settings.
5. Behavior across day boundaries and DST transitions.

## 9. Connection Pools and HikariCP

### 9.1. Why use a pool?

Opening a fresh JDBC connection incurs network, authentication, and session setup overhead. HikariCP maintains a pool of connections for multiple requests to borrow and return.

Basic flow:
1. Spring transaction/data access borrows a connection from the pool.
2. Hibernate/JDBC executes SQL.
3. Transaction commits/rolls back.
4. Connection is returned to the pool.
5. Another request reuses the connection.

A pool does not turn slow queries into fast queries. It reduces connection establishment overhead and bounds concurrent sessions hitting the database.

### 9.2. Common Hikari properties

| Property | Meaning |
|---|---|
| \`maximum-pool-size\` | Maximum total connections, including idle and in-use |
| \`minimum-idle\` | Minimum idle connections the pool tries to maintain |
| \`connection-timeout\` | Time spent waiting to borrow a connection from the pool |
| \`idle-timeout\` | Duration before idle connections may be retired when scaling down |
| \`max-lifetime\` | Maximum lifetime before retiring a connection |
| \`keepalive-time\` | Interval for keeping alive/testing idle connections |
| \`validation-timeout\` | Maximum duration for validating a connection |
| \`leak-detection-threshold\` | Threshold warning when a connection is held too long |

Duration values in Spring Boot YAML can use \`ms\`, \`s\`, \`m\`. Internally, Hikari configures durations in milliseconds.

### 9.3. Pool configuration example

```yaml
spring:
  datasource:
    hikari:
      pool-name: CustomerPool
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 3s
      validation-timeout: 1s
      idle-timeout: 10m
      max-lifetime: 25m
```

This is an illustrative configuration only. Do not copy numbers like 12, 2, or 3 seconds into production without measuring load and database limits.

Hikari has its own defaults for many properties. For instance, connectionTimeout is typically 30 seconds, maxLifetime is typically 30 minutes, and maximumPoolSize defaults to 10; check your actual HikariCP version rather than relying on memory or older defaults.

### 9.4. Choosing maximumPoolSize

Total connections an application can open is roughly:

\`number of application instances × maximumPoolSize per instance\`

For example, 5 pods with max pool size 12 each can open up to 60 connections from this service alone, excluding workers, migrations, admin tools, and other services.

When sizing the pool, know:
- Database \`max_connections\` limit.
- Maximum scaled replica/pod count.
- Connections reserved for other apps, monitoring, and DBAs.
- Database CPU/I/O concurrency capacity.
- Query and transaction durations.
- Number of threads that may concurrently need a connection.

Too small a pool makes requests wait for connections. Too large a pool overwhelms the database with sessions, increasing context switching, lock contention, and memory usage. Increasing the pool is not a default fix for latency.

### 9.5. minimumIdle and idleTimeout

If \`minimum-idle\` is smaller than \`maximum-pool-size\`, the pool can resize dynamically and \`idle-timeout\` can retire idle connections above the minimum.

If you want a fixed-size pool, omit minimumIdle so Hikari uses maximumPoolSize as the target pool size by default. When operating as a fixed pool, idleTimeout does not shrink the pool as it does in an elastic setup.

### 9.6. maxLifetime and keepalive

Set \`max-lifetime\` lower than any connection lifetime limit enforced by database proxies, load balancers, or firewalls if the infrastructure imposes one. Hikari will retire connections before external layers forcibly close them.

\`keepalive-time\` applies only to idle connections and must be shorter than maxLifetime per Hikari rules. Enable it only when there is evidence the network drops idle connections; overly frequent keepalives add extra traffic.

### 9.7. Leak detection

\`leak-detection-threshold\` helps spot connections borrowed for too long. A warning does not always mean code leaked a connection: legitimate long transactions or slow queries can also hold connections past the threshold.

Enable temporarily during investigations, inspect stack traces, and locate call sites. Avoid setting too low a threshold in production because it creates noisy warnings.

## 10. Timeouts: Each Layer Has a Distinct Purpose

Timeouts must be designed across the request chain. A request may wait for a connection, open a socket, run SQL, wait for locks, and call downstream services. A timeout at one layer does not automatically bound all other layers.

| Timeout | What It Limits | Where Configured |
|---|---|---|
| Pool acquisition | Waiting for a free connection in Hikari | \`spring.datasource.hikari.connection-timeout\` |
| Driver connect/login | Opening network socket and authenticating to DB | JDBC driver property |
| Socket read | Waiting to read data from socket | JDBC driver property |
| Query/statement | Execution time of a SQL statement | JPA/JDBC/provider/database |
| Lock wait | Waiting for a lock | Database |
| Transaction | Transaction duration per transaction manager | \`@Transactional(timeout=...)\` |
| HTTP/request deadline | Total time a request is allowed to run | Web server/gateway/client |

Do not set every timeout to the same number assuming the application gets a consistent deadline. Design timeout ordering around your request budget and rollback/retry behavior.

## 11. Pool Acquisition Timeout

Hikari \`connection-timeout\` is how long a thread waits for an idle connection when the pool is exhausted. It is neither the TCP connect timeout to the database nor a query timeout.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3s
```

If all 12 connections are held and none return within the wait window, Hikari throws a connection acquisition exception. Investigate:
- Transactions holding connections too long.
- Slow queries or lock waits.
- Connections not returned to the pool.
- Pool sized smaller than actual concurrency.
- N+1 queries keeping connections busy across many round-trips.
- An overloaded database.

Do not raise connection-timeout indefinitely to mask pool exhaustion; that only queues requests longer.

## 12. Driver Connect Timeout and Socket Timeout

Driver timeouts are vendor- and version-specific settings.

### 12.1. PostgreSQL JDBC

pgJDBC provides \`connectTimeout\` and \`socketTimeout\`, measured in seconds. \`connectTimeout\` limits opening the socket connection, while \`socketTimeout\` limits waiting to read data from the socket.

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/customer_db?connectTimeout=5&socketTimeout=30
```

\`socketTimeout\` is a socket-layer limit. When it expires, the driver may close the connection; it is not the same as a query timeout with controlled statement/transaction cancellation semantics. Choose values based on SLAs and verify connection recovery.

### 12.2. MySQL Connector/J

MySQL Connector/J provides \`connectTimeout\` and \`socketTimeout\`; these networking values are measured in milliseconds per Connector/J documentation.

```properties
spring.datasource.url=jdbc:mysql://db.internal:3306/customer_db?connectTimeout=5000&socketTimeout=30000
```

Do not copy PostgreSQL URL units into MySQL. For other drivers, read the official documentation for your exact version.

### 12.3. Do not confuse driver timeouts with Hikari timeouts

| Situation | Configuration to Inspect |
|---|---|
| No free connection left in pool | Hikari connectionTimeout |
| Network cannot open connection to DB | Driver connectTimeout/loginTimeout |
| Socket receives no data | Driver socketTimeout |
| SQL runs too long | Statement/query timeout |
| SQL waits on row/table lock | Database lock timeout |
| Transaction holds connection too long | Transaction boundary and transaction timeout |

## 13. Query Timeout in JPA and Spring Data JPA

### 13.1. Jakarta Persistence query timeout hint

Jakarta Persistence defines the \`jakarta.persistence.query.timeout\` hint. The unit is milliseconds.

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Query("select o from Order o where o.status = :status")
    @QueryHints(
        value = @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "3000"
        )
    )
    List<Order> findByStatusWithTimeout(
        @Param("status") OrderStatus status
    );
}
```

Imports:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;
```

This is a query hint; provider/driver/database support varies. Do not assume the hint always cancels SQL at exactly 3 seconds. Test on a production-like database and observe the actual exception raised.

### 13.2. Query timeout with EntityManager

```java
TypedQuery<Order> query = entityManager.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
);

query.setParameter("status", OrderStatus.PENDING);
query.setHint("jakarta.persistence.query.timeout", 3000);

List<Order> result = query.getResultList();
```

The value is in milliseconds. This is a per-query hint, not a timeout for the entire request.

### 13.3. Spring JdbcTemplate differs from JPA queries

Spring Boot has \`spring.jdbc.template.query-timeout\` for JdbcTemplate. This property does not apply globally to all Hibernate/JPA queries. When an application uses both JdbcTemplate and Spring Data JPA, configure timeouts on each data access path.

## 14. Transaction Timeout and Lock Timeout

### 14.1. Spring @Transactional timeout

```java
@Service
public class OrderService {

    @Transactional(timeout = 5)
    public void processOrder(Long orderId) {
        // Load, validate, and update data within the transaction.
    }
}
```

Spring's \`@Transactional\` timeout value is measured in seconds. Enforcement depends on the transaction manager and resource integration. It does not guarantee every driver cancels an in-flight SQL statement on time; query/statement timeouts and database-side limits are still needed where required.

Never hold a transaction open while calling slow external HTTP services, waiting on user input, or doing non-database work. Long transactions hold connections and locks longer.

### 14.2. PostgreSQL statement_timeout and lock_timeout

PostgreSQL has dedicated timeouts:
- \`statement_timeout\`: limits how long a single statement may run.
- \`lock_timeout\`: limits how long to wait for a lock.
- \`idle_in_transaction_session_timeout\`: terminates sessions idle inside a transaction for too long.

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';

-- Transaction SQL statements

COMMIT;
```

\`lock_timeout\` limits only lock wait time; if \`statement_timeout\` is smaller, statement timeout may trigger first. \`SET LOCAL\` applies only to the current transaction.

Avoid setting \`statement_timeout\` too low server-wide when mixed workloads exist. Configure per role/database or per transaction. With pooling, understand SET scope and session state resets.

### 14.3. MySQL execution and lock timeouts

MySQL has different limits:
- \`max_execution_time\` (milliseconds) can limit SELECT statements.
- Optimizer hint \`MAX_EXECUTION_TIME(N)\` can apply to a single SELECT.
- \`innodb_lock_wait_timeout\` limits InnoDB row lock waits, measured in seconds.

Check session settings:

```sql
SELECT
    @@session.max_execution_time,
    @@session.innodb_lock_wait_timeout;
```

Do not treat \`innodb_lock_wait_timeout\` as a general query timeout. It governs only InnoDB lock waiting. Syntax and scope vary by MySQL version; verify before production use.

## 15. Per-Request Timeout Budgets

Suppose an endpoint has an 8-second deadline. An illustrative design might allocate:
- Up to 0.5 seconds waiting for a pool connection.
- Up to 1 second opening a new connection if needed.
- Up to 4 seconds for queries/locks per database policy.
- The remainder for business logic, serialization, and response.

These numbers are illustrative only. Driver connect timeout does not occur on every request when the pool already holds connections.

Principles:
1. Lower-layer timeouts should not push a request past upper-layer deadlines.
2. Query timeouts should be low enough to free resources when queries misbehave.
3. Lock timeouts are typically shorter than statement timeouts when failing fast under contention is desired.
4. Transactions should not stay open merely because a client is waiting for a response.
5. Retries apply only to retryable errors and safe/idempotent operations.
6. On timeout, determine whether the statement rolled back or the transaction was marked rollback-only.

Timeouts do not replace end-to-end cancellation. If a client disconnects, SQL may keep running unless the driver/provider/database receives and executes cancellation.

## 16. Environment Configuration with Spring Profiles

### 16.1. Common configuration

The \`application.yml\` file contains shared properties:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC

  datasource:
    hikari:
      pool-name: CustomerPool
      validation-timeout: 1s
      max-lifetime: 25m
```

URL, username, password, and pool sizes belong in appropriate profiles/secrets. With Flyway/Liquibase-managed schemas, \`ddl-auto: validate\` verifies mappings instead of letting Hibernate create production schemas.

### 16.2. Local profile

The \`application-local.yml\` file:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/customer_local
    username: local_app
    password: ${LOCAL_DB_PASSWORD}
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
      connection-timeout: 5s
      idle-timeout: 5m
```

Local setups can use containers or a dedicated database. There is no need to mirror production connection counts on a laptop.

### 16.3. Production profile

The \`application-prod.yml\` file:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX}
      minimum-idle: ${DB_POOL_MIN}
      connection-timeout: 2s
      idle-timeout: 10m
      max-lifetime: 25m
      validation-timeout: 1s
```

Values for DB_URL, DB_USERNAME, DB_PASSWORD, DB_POOL_MAX, and DB_POOL_MIN are supplied by the deployment environment or secret manager. If required variables are missing, the application should fail fast with a clear configuration error instead of silently falling back to a default database.

Activate the profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or via environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Never place real passwords inside committed profile files. Use Kubernetes Secrets, Vault, a cloud secret manager, or your platform's secret mechanism.

### 16.4. Externalized configuration and precedence

Spring Boot can read configuration from:
- application.yml and application-{profile}.yml.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config server or config imports.
- Platform secret/config stores.

Effective values depend on property source precedence. When suspecting the application is using the wrong URL/pool size, inspect active profiles and effective property sources through secured diagnostics; never log credentials.

### 16.5. Avoid branching code by environment

Avoid writing \`if (isProduction)\` conditionals in code to select dialects or pools. Database configuration should flow through Spring Environment/ConfigurationProperties. Business logic should not depend on profile names.

If database vendors genuinely differ across deployments, configure the corresponding driver/dialect/schema at the configuration boundary and run integration tests for each vendor.

## 17. Typed Configuration with @ConfigurationProperties

When grouping multiple related parameters, bind them into a typed configuration object for validation:

```java
@ConfigurationProperties(prefix = "app.database")
@Validated
public record DatabaseRuntimeProperties(
    @Min(1) int expectedInstances,
    @Min(1) int poolMax,
    @NotBlank String referenceTimeZone
) {
}
```

Register properties:

```java
@Configuration
@EnableConfigurationProperties(DatabaseRuntimeProperties.class)
public class DatabaseConfiguration {
}
```

Example YAML:

```yaml
app:
  database:
    expected-instances: 4
    pool-max: 10
    reference-time-zone: UTC
```

This is application-specific configuration and does not replace \`spring.datasource.hikari.*\` or \`spring.jpa.properties.hibernate.*\`. It can be used to verify consistency, such as ensuring total pool connections across instances stay within the allocated connection budget.

## 18. Multiple DataSources or Multiple Database Vendors

If an application uses multiple databases, each DataSource needs its own configuration:
- Matching JDBC URL and driver.
- Dedicated connection pool.
- Dedicated EntityManagerFactory.
- Dedicated TransactionManager.
- Matching entity/repository package scanning.
- Dialect matching that persistence unit's database.

Never share a single Hikari pool across two databases of different vendors. Never bind the same EntityManagerFactory to two different DataSources.

```text
SalesDataSource   -> SalesEntityManagerFactory   -> SalesTransactionManager
BillingDataSource -> BillingEntityManagerFactory -> BillingTransactionManager
```

Repositories must bind to the right EntityManagerFactory/transaction manager. If a transaction must update two databases, local transactions on each DataSource do not automatically form a distributed atomic transaction; design a saga/outbox or JTA if appropriate.

## 19. Observing Pools, Queries, and Timeouts

Monitor:
- Hikari active, idle, pending, and maximum connections.
- Connection acquisition wait time p50/p95/p99.
- Count of connection acquisition timeouts.
- Query duration and slow query count.
- Transaction duration and rollbacks.
- Lock waits, deadlocks, and database session counts.
- Connection creation/close rates.
- Queued request counts and response times.

Spring Boot Actuator/Micrometer can export Hikari metrics when the datasource/pool is instrumented. Metric names usually start with \`hikaricp.connections\`; exact metric and tag names depend on version and registry.

| Observation | Likely Area to Investigate |
|---|---|
| Active stays at max, pending rises | Pool exhausted or transactions/queries holding connections too long |
| Many idle connections, yet requests remain slow | Bottleneck in query, network, or application |
| Connection timeouts spike | Database/network unresponsive or insufficient pool capacity |
| High query latency while pool is not full | SQL/indexes/locks/database workload |
| Connections closed periodically | maxLifetime misaligned with proxy/server timeouts |
| Timeouts occur in only one profile | URL, network, pool, or server settings differ across environments |

Metrics do not replace database slow query logs and execution plans. Combine application metrics with database telemetry to locate bottlenecks.

## 20. Testing Environment Database Configuration

### 20.1. Test against the real database vendor

Use Testcontainers or a matching database service to test real PostgreSQL/MySQL. Do not treat H2 as proof for dialects, native SQL, or vendor-specific types.

Tests should verify:
- ApplicationContext starts with the expected JDBC URL/profile.
- Hibernate chooses the appropriate dialect.
- Migrations execute cleanly.
- Repository queries and native SQL run.
- Timezone round-trips preserve instants/local times per semantics.
- Timestamp precision matches expectations.
- Pool borrows/returns connections properly.
- Query timeouts/lock timeouts take effect per provider/driver/database.
- Transaction rollbacks and isolation behave as expected.

### 20.2. Deliberate timezone testing

Write tests covering:
- Instant in UTC.
- OffsetDateTime with a non-UTC offset.
- LocalDateTime without timezone.
- Instants near day boundaries.
- Values with fractional seconds.
- DST-observing zones if supported by the application.
- A known session timezone.

After persisting, flushing, clearing, and re-reading in a new transaction, compare according to intended semantics—not formatted strings if the database shifts timestamps to the session timezone.

### 20.3. Isolated pool and timeout tests

To test pool timeouts, create controlled concurrency and hold connections inside a test transaction longer than the acquisition timeout. Do not run such tests in parallel with other tests sharing the same pool, as doing so causes flakiness.

To test query timeouts, use a query with a deterministic execution time on the target database or a controlled lock. Verify the exception and transaction state after timeout. Never rely on \`Thread.sleep()\` and assume a database query was cancelled.

## 21. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| Hibernate cannot determine dialect | Cannot fetch JDBC metadata, missing driver, or DB unavailable | Check URL, driver, network, and startup readiness |
| SQL fails only in production | Different dialect/native SQL or database version | Verify vendor/version and test on real engine |
| Timestamps shifted by hours | JVM, Hibernate, JDBC session, or DB timezone misaligned | Inspect all four layers and column type |
| LocalDateTime shifts hours | Local type treated as instant or mapping/column mismatch | Clarify domain semantics and pick right Java/SQL types |
| MySQL NOW() differs from expected | Session timezone altered by driver/config | Check \`@@session.time_zone\` and Connector/J options |
| Hikari connection timeout | Pool exhausted or connections held too long | Inspect active/pending, transaction duration, and queries |
| Connect timeout | DNS, routing, firewall, TLS, or DB not accepting connections | Check driver connect settings and network |
| Socket timeout | Database/network failed to return data within limit | Check slow queries, DB load, and driver socket settings |
| QueryTimeoutException | SQL or lock exceeded limit | Inspect query hint, DB statement/lock timeout, and plan |
| Lock wait timeout | Another transaction holds the lock | Inspect lock graph, transaction duration, and update order |
| Pool closes connections periodically | maxLifetime exceeds proxy/server limit or network idle timeout | Align lifetime/keepalive with infrastructure |
| Fails only when scaling many pods | Total pools exceed DB connection budget | Sum pool sizes across all replicas and other clients |

## 22. Common Configuration Mistakes

1. **Hard-coding the dialect:** declaring PostgreSQL dialect while passing a MySQL URL in another environment.
2. **Relying solely on JVM timezone:** failing to check session timezone or column semantics.
3. **Storing local schedules as instants:** converting local appointment times to UTC without tracking ZoneId.
4. **Enlarging the pool to fix slow queries:** the database gets more concurrency while SQL stays slow.
5. **Setting pool size equal to thread count:** not every thread needs a connection concurrently; the database has its own limits.
6. **Treating connectionTimeout as queryTimeout:** requests can still run slow SQL long after acquiring a connection.
7. **Setting socketTimeout too low:** the driver drops connections during normal queries or brief database slowdowns.
8. **Setting global database timeouts without analysis:** different workloads have different SLAs.
9. **Changing session timezone without resetting pooled connections:** connections returned to the pool can retain unexpected session state.
10. **Setting leak detection too low:** logs warn on valid connections running long queries.
11. **Not testing migrations on the production engine:** schemas might only work on H2.
12. **Committing credentials in YAML:** exposes database access details.

## 23. Pre-Deployment Checklist

### Dialect and driver
- [ ] JDBC URL points to the right vendor, host, port, and database.
- [ ] Correct JDBC driver version is on the runtime classpath.
- [ ] Hibernate auto-detects the dialect from metadata unless an override is justified.
- [ ] If overriding dialect, the class matches Hibernate's major version and real database.
- [ ] Migrations/schema validation run against the target database.

### Timezone
- [ ] Calendar dates, local times, and instants are clearly distinguished.
- [ ] Java types match data semantics.
- [ ] JVM/Hibernate JDBC timezone convention is clear.
- [ ] Database session timezone has been checked.
- [ ] PostgreSQL timestamptz/timestamp and MySQL TIMESTAMP/DATETIME are understood.
- [ ] ZoneId is stored separately if regional schedules must be reconstructed.
- [ ] Round-trip, precision, and DST tests exist if applicable.

### Pool
- [ ] maximumPoolSize fits the system-wide connection budget.
- [ ] Maximum replicas and other database clients have been accounted for.
- [ ] connectionTimeout does not mask pool exhaustion.
- [ ] maxLifetime fits proxy/server timeouts.
- [ ] idleTimeout/keepalive are configured according to pool mode.
- [ ] Active/idle/pending metrics and acquisition latency are tracked.
- [ ] Leak detection is enabled only with an intentional threshold.

### Timeouts
- [ ] Pool acquisition timeout is distinguished from driver connect timeout.
- [ ] Socket timeout is distinguished from SQL timeout.
- [ ] Query/statement timeouts are verified on the real provider and driver.
- [ ] Lock timeout and statement timeout serve distinct purposes.
- [ ] Transaction timeout aligns with the transaction manager.
- [ ] Layered timeouts fit request deadlines and retry policies.

### Environment
- [ ] Local/test/staging/prod have separate URL and pool configurations.
- [ ] Secrets are never stored in Git or logs.
- [ ] Active profile and property sources are verified on deployment.
- [ ] CI runs integration tests on the exact database vendor/version.
- [ ] Multiple DataSources have dedicated EntityManagerFactory and TransactionManager beans.

## 24. Official References

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): datasource, HikariCP, JPA database platform, and pool settings.
- [Hibernate ORM User Guide — Time zone handling](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): \`hibernate.jdbc.time_zone\` and timezone-aware storage strategies.
- [Hibernate ORM — Dialect configuration](https://github.com/hibernate/hibernate-orm/blob/main/documentation/src/main/asciidoc/introduction/Configuration.adoc): dialect auto-detection from JDBC metadata and when overrides are needed.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP/wiki/Configuration): connectionTimeout, idleTimeout, maxLifetime, pool size, and validation.
- [PostgreSQL — Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html): timestamp with/without time zone.
- [PostgreSQL — Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html): statement_timeout, lock_timeout, and idle transaction timeout.
- [MySQL Connector/J — Datetime types processing](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-datetime-types-processing.html): connectionTimeZone, preserveInstants, and forceConnectionTimeZoneToSession.
- [MySQL — Date and Time Functions](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-functions.html): session timezone and temporal functions.
- [Jakarta Persistence — Query API](https://jakartaee.github.io/persistence/latest-nightly/api/jakarta.persistence/jakarta/persistence/Query.html): query timeout hint in milliseconds.

## 25. Conclusion

Environment-specific database configuration requires consistency across the JDBC URL, driver, Hibernate dialect, timezone, connection pool, and timeouts. Modern Hibernate usually detects dialects from JDBC metadata; override only for a clear technical reason. Changing a dialect never replaces the driver or database vendor.

For temporal values, distinguish LocalDateTime for local wall-clock time from Instant for absolute points in time. UTC is a helpful convention for instants, provided JVM, Hibernate JDBC binding, and database sessions stay aligned. PostgreSQL timestamptz does not preserve the original timezone name; MySQL TIMESTAMP converts according to the session timezone whereas DATETIME stores wall-clock values. If ZoneId must be retained, store it separately.

HikariCP bounds and reuses connections. Size pools based on the system-wide budget and replica count; monitor active, idle, pending, and wait times. Timeouts must be layered: pool acquisition, connect, socket read, query execution, lock wait, transaction, and HTTP request. No single value replaces all other limits.

Finally, externalize URLs/credentials/pools/timezones/timeouts, manage secrets safely, and run migrations and integration tests against the real database vendor/version. Observe metrics alongside database logs to tune for real load rather than copying fixed settings across every environment.