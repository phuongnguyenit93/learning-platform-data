# Configuring MySQL DataSource in Spring Boot by Environment

## Objectives

Spring Boot can automatically create a `DataSource` from `spring.datasource.*` configuration and a JDBC driver on the classpath. When an application runs on a developer machine, a test environment, and production, each environment typically has a different endpoint, database, account, TLS certificate, and connection pool limit. Mixing these values into source code or sharing a single configuration across all environments makes it easy for the application to connect to the wrong database, expose credentials, or overload MySQL.

This lesson belongs to the **DATABASE_MYSQL** module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, and relational database operations. This lesson guides you through configuring a MySQL DataSource in Spring Boot using profiles, environment variables, and secrets; setting up Connector/J, HikariCP, and JPA; and then verifying the live connection.

After this lesson, you will be able to:

- Explain how Spring Boot auto-configures a `DataSource` from `spring.datasource.*`.
- Separate shared configuration from environment-specific configuration for `dev`, `test`, and `prod` using profiles.
- Override URL, username, password, and pool settings using environment variables.
- Configure MySQL Connector/J, TLS, timezone, and HikariCP appropriately.
- Choose how to configure JPA schema validation and verify the connection before deployment.

## 1. DataSource in Spring Boot

`DataSource` is the JDBC abstraction used to provide connections to a database. Instead of manually opening sockets or calling `DriverManager` in every repository, the application obtains connections from a `DataSource`. In a typical Spring Boot application, Spring Boot auto-configuration creates a `DataSource` if a JDBC/JPA dependency and a compatible driver are on the classpath, and the application has not declared another `DataSource` bean.

For a MySQL database, the basic configuration includes:

- JDBC URL: server address, port, and database name.
- Username/password: an application account with least-privilege permissions.
- JDBC driver: MySQL Connector/J.
- Connection pool: manages physical connections for reuse.

Spring Boot typically selects HikariCP when that library is on the classpath. Common starters such as `spring-boot-starter-jdbc` and `spring-boot-starter-data-jpa` generally pull in an appropriate pool via Spring Boot dependency management. If the project declares dependencies manually, inspect the dependency tree rather than adding multiple pools at once.

## 2. Adding MySQL Connector/J

With Maven, declare the driver at runtime:

```xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
```

If the project uses the Spring Boot parent or Spring Boot dependency management, let the BOM manage the compatible Connector/J version. Only pin a specific version when there is a clear compatibility reason or upgrade policy.

The modern driver class is `com.mysql.cj.jdbc.Driver`. Connector/J registers itself via the JDBC service provider mechanism, so declaring `spring.datasource.driver-class-name` is usually unnecessary. If the project has a special classloader or configuration, you can declare it explicitly:

```yaml
spring:
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
```

Do not use the legacy driver name `com.mysql.jdbc.Driver` in new projects.

## 3. Shared Default Configuration

Place shared settings in `src/main/resources/application.yml`. The following example uses environment variables to pass connection details while providing a localhost URL intended only for development:

```yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:mysql://localhost:3306/shop_dev}
    username: ${DB_USERNAME:shop_app}
    password: ${DB_PASSWORD:}
    hikari:
      pool-name: shop-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1740000

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

The HikariCP numbers above are starting examples, not an optimal configuration for every workload. `connection-timeout` is the maximum wait time to acquire a connection from the pool; `max-lifetime` sets the maximum lifetime of a physical connection; `idle-timeout` applies to idle connections when the pool can shrink. `max-lifetime` should be lower than the connection lifetime limit enforced by a proxy or database infrastructure.

`minimum-idle` and `maximum-pool-size` determine the pool size. If maintaining a fixed number of idle connections is unnecessary, choose a pool policy suited to the workload and application scaling behavior. Setting a large `maximum-pool-size` does not automatically make queries faster.

`ddl-auto: validate` tells Hibernate to validate the schema at startup without automatically creating or modifying tables. Production should typically use Flyway or Liquibase for versioned schema migrations, and then let Hibernate validate. Avoid `ddl-auto: update` as a production schema deployment mechanism.

## 4. Separating Configuration by Profile

Spring profiles allow loading environment-specific configuration. A manageable approach is to keep shared properties in `application.yml`, then create:

- `application-dev.yml` for developer machines.
- `application-test.yml` for integration testing.
- `application-prod.yml` for production.

Example `application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop_dev?connectionTimeZone=UTC
    username: shop_dev
    password: dev-only-password
```

Example `application-test.yml` can point to a dedicated test database or be overridden by Testcontainers during test execution:

```yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:mysql://localhost:3306/shop_test}
    username: ${DB_USERNAME:shop_test}
    password: ${DB_PASSWORD:}
```

Example `application-prod.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
```

In production, placeholders without default values cause the application to fail with a configuration error when required variables are missing. This helps detect missing secrets or endpoints immediately at startup instead of accidentally connecting to a default database.

Activate a profile via environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Or when running the JAR:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Do not put `spring.profiles.active` inside a profile-specific configuration file. Select the profile from the runtime environment, command line, or deployment configuration to avoid dependency cycles when Spring Boot loads files.

## 5. Overriding Configuration with Environment Variables

Spring Boot supports relaxed binding: configuration property names can be represented in uppercase with underscores in environment variables. Commonly used variables:

| Spring Property | Environment Variable |
|---|---|
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `spring.datasource.hikari.maximum-pool-size` | `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` |
| `spring.datasource.hikari.connection-timeout` | `SPRING_DATASOURCE_HIKARI_CONNECTION_TIMEOUT` |

Example when running in a container or deployment environment:

```bash
SPRING_PROFILES_ACTIVE=prod
SPRING_DATASOURCE_URL='jdbc:mysql://mysql-prod.internal:3306/shop?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC'
SPRING_DATASOURCE_USERNAME='shop_runtime'
SPRING_DATASOURCE_PASSWORD='injected-at-runtime'
SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE=20
```

This illustrates how variables are passed; password values must be injected by a secret manager or the platform's secret management system—never hardcoded in Dockerfiles, committed compose files, public manifests, logs, or shared shell history.

Do not set a production endpoint as a default in `application.yml`. If `DB_URL` or a secret is missing in production, the application should fail to start and report a configuration error.

## 6. Configuring the JDBC URL and Connector/J

A MySQL JDBC URL has the form:

```text
jdbc:mysql://host:port/database?property=value
```

Production example using TLS server identity verification and UTC timezone:

```text
jdbc:mysql://mysql-prod.internal:3306/shop?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC
```

`sslMode=VERIFY_IDENTITY` requires TLS and verifies that the server certificate matches the hostname. The system needs the trusted CA installed and a certificate with a SAN matching the hostname in the URL. If the environment uses a private CA, configure the trust store according to the Connector/J documentation and your Java deployment setup.

Do not use `sslMode=DISABLED` in production. `PREFERRED` may allow unencrypted connections if the server does not support TLS; for environments requiring security, choose an explicit mode and test certificate verification.

`connectionTimeZone=UTC` instructs Connector/J to use the specified timezone for time conversions. You must also align the MySQL session timezone, `DATETIME`/`TIMESTAMP` column types, and application storage rules. Do not treat setting the timezone in the URL as a substitute for proper temporal data design.

Avoid adding JDBC parameters you do not understand or copying URLs blindly from other environments. Some properties can alter semantics, security, batching, or data types. Check the Connector/J documentation for your exact version and verify with integration tests.

## 7. Designing the HikariCP Connection Pool

HikariCP manages physical connections and hands out logical connections to JDBC/JPA code. Key settings:

| Property | Meaning | Notes |
|---|---|---|
| `maximum-pool-size` | Maximum total connections in the pool | Account for the total across all application instances and other services |
| `minimum-idle` | Target number of idle connections | Can keep connections ready to reduce connection establishment latency |
| `connection-timeout` | Wait time to borrow a connection from the pool | Timeouts usually indicate pool exhaustion or an unresponsive database |
| `validation-timeout` | Maximum time to validate a connection | Must be smaller than `connection-timeout` |
| `idle-timeout` | Duration before an idle connection may be evicted when shrinking | Applies when the pool allows idle connections below maximum |
| `max-lifetime` | Maximum lifetime of a physical connection | Set lower than limits on MySQL, proxies, or network |
| `leak-detection-threshold` | Threshold to log connections held too long | Use for controlled diagnostics; may cause false alarms for legitimately long tasks |

### Calculating Total Connections

Pool size must be calculated across the entire system, not just a single JVM. For example, 4 application replicas with `maximum-pool-size=20` can open up to 80 connections, excluding migration jobs, batch workers, monitoring, DBAs, and other services.

```text
Potential application connections
  = application replicas x maximumPoolSize per replica
```

Ensure total maximum connections stay within the `max_connections` budget and leave headroom for administration, failover, and traffic spikes. An oversized pool can increase context switching, lock contention, and database load without increasing throughput.

### Investigating Connection Timeouts

If requests frequently block on `getConnection()`, inspect active/idle connection counts, connection hold times, slow queries, and database errors. Increasing `connection-timeout` only makes requests wait longer; it does not fix connection leaks or an overloaded database.

Do not hold a connection while making HTTP service calls, processing files, or performing long CPU-bound work. Acquire the connection close to when the query is needed and return it to the pool immediately afterward.

## 8. Dedicated MySQL Account for the Application

Do not configure the application to use `root` or a DBA account. Create a dedicated runtime account, restrict the source host, and grant only the privileges the application actually needs:

```sql
CREATE USER 'shop_runtime'@'10.20.30.40'
  IDENTIFIED BY '<secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON shop.*
  TO 'shop_runtime'@'10.20.30.40';
```

Replace the host address in the example with the actual host or network of your application. If the application is read-only, grant only `SELECT`; if it needs to call stored procedures, grant `EXECUTE` on the specific routines. DDL privileges such as `CREATE`, `ALTER`, and `DROP` should belong to a separate migration account, not the runtime account.

Store the username/password using a secret manager, Kubernetes Secret, cloud secret service, or a mechanism approved by your organization. Secret rotation requires a process to update configuration and recycle the connection pool; changing the password in MySQL while the pool retains old connections does not automatically update credentials for new connections.

## 9. Configuring JPA and Hibernate

If the application uses `spring-boot-starter-data-jpa`, Spring Boot usually auto-configures `EntityManagerFactory` and the transaction manager based on the `DataSource`. With a single MySQL database, manually specifying the dialect is normally unnecessary; Hibernate can detect the dialect from JDBC metadata.

Common configuration:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

`open-in-view: false` closes the persistence context at the service/transaction boundary instead of keeping it open throughout web response rendering. The application must load needed data within the transaction or use explicit DTOs/fetch plans to avoid lazy-loading outside a transaction.

`ddl-auto: validate` validates entity mappings against the existing schema. Use a migration tool such as Flyway or Liquibase to create and evolve the schema in a versioned manner. In development, you may use schema-generation modes for disposable databases, but never carry that configuration into production.

Setting `hibernate.jdbc.time_zone=UTC` helps Hibernate standardize how supported temporal values are bound and extracted according to that setting. You still need to choose appropriate SQL types and consistent timezone rules in the domain model.

## 10. Verifying the DataSource at Application Startup

Before serving traffic, verify that the application can connect and is using the right database. You can check via JDBC in an integration test or a health indicator.

Example verification query:

```sql
SELECT DATABASE() AS current_database,
       CURRENT_USER() AS authenticated_account,
       @@hostname AS mysql_host,
       @@time_zone AS session_time_zone;
```

In Spring Boot Actuator, the health endpoint can report database status when the appropriate health indicator is enabled. Do not expose detailed health endpoints or internal information to unauthorized users; restrict access to management endpoints.

For integration tests, prefer real MySQL in Testcontainers over using only H2 when you need to verify MySQL-specific features such as collations, JSON, locking, SQL modes, generated columns, or Connector/J behavior.

Example using `@DynamicPropertySource` to inject the container URL into the Spring context:

```java
@DynamicPropertySource
static void mysqlProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", mysql::getJdbcUrl);
    registry.add("spring.datasource.username", mysql::getUsername);
    registry.add("spring.datasource.password", mysql::getPassword);
}
```

This example assumes the test has declared and started a MySQL Testcontainer named `mysql`. Add the Testcontainers MySQL dependency compatible with your project version.

## 11. Multiple DataSources in One Application

Most applications only need a single MySQL `DataSource`. If an application uses multiple databases, each `DataSource` needs its own configuration and lifecycle. When you manually declare a `DataSource` bean, Spring Boot may no longer apply default auto-configuration as before; you must explicitly configure the primary bean, pools, transaction managers, and persistence units.

With multiple JPA databases, mark the default DataSource with `@Primary` where appropriate, use `@Qualifier` to inject the right bean, and configure the corresponding `EntityManagerFactory` and `PlatformTransactionManager`. Each repository must be bound to the proper persistence unit. Do not use a single default transaction manager across multiple databases and assume transactions will be atomic across them; distributed transactions require a dedicated architecture.

## 12. Environment-Based Configuration: Complete Example

A resource structure may look like this:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-prod.yml
```

Conventions:

- `application.yml`: shared configuration, pool baseline, and JPA settings.
- `application-dev.yml`: local database for developers.
- `application-test.yml`: test database endpoint or values overridden by Testcontainers.
- `application-prod.yml`: required placeholders for URL and secrets; pool sizing based on actual replica count.

The profile is selected by the deployment environment. Never commit production passwords to any profile file. If you need to verify bound configuration, log the active profile and a sanitized host/database; never log passwords or full URLs that may contain credentials.

## 13. Common Errors and Troubleshooting

- **`Communications link failure`:** check DNS, routing, firewall, port 3306, TLS, and MySQL status; verify the endpoint from the exact application container/host.
- **`Access denied for user`:** check the `user`/`host` account, injected password, authentication plugin, privileges, and TLS requirements.
- **JDBC driver not found:** check the `mysql-connector-j` dependency, runtime scope, and packaged classpath.
- **Connected to the wrong database:** check the active profile, configuration precedence, and `SELECT DATABASE()`.
- **Pool exhaustion:** investigate connection leaks, long-running transactions, slow queries, and application replica count; do not merely increase pool size.
- **TLS certificate error:** check CA trust, SAN/hostname, certificate expiration, and `sslMode`; do not downgrade to an unverified connection to bypass production errors.
- **Incorrect timestamps:** align application, JDBC URL, Hibernate, and MySQL session timezones; distinguish `DATETIME` from `TIMESTAMP`.
- **Schema validation failure:** run migrations before application startup and compare column types, nullability, precision, indexes, and constraint names.
- **Secret rotated but new connections fail:** update the secret in runtime and recycle the pool according to your credential rotation procedure.

## 14. Hands-On Exercise

Build a Spring Boot application using Spring Data JPA and MySQL:

1. Add `spring-boot-starter-data-jpa` and `mysql-connector-j` using Spring Boot dependency management.
2. Create `application.yml` with shared configuration, placeholders for `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, and a baseline pool configuration.
3. Create `application-dev.yml` pointing to a local database; create `application-prod.yml` requiring production connection variables.
4. Run the application with `SPRING_PROFILES_ACTIVE=dev`, and verify the profile and database using `SELECT DATABASE(), CURRENT_USER()`.
5. Create a dedicated runtime account in MySQL, grant the required DML privileges, and verify the account has no DDL privileges.
6. Enable hostname-verifying TLS in a test environment with an appropriate CA; confirm the connection fails when the certificate is invalid.
7. Tune HikariCP maximum pool size, run concurrent load, and monitor active/idle connections alongside `max_connections`.
8. Use Flyway or Liquibase to create the schema, set Hibernate `ddl-auto=validate`, and verify the application starts cleanly.
9. Write an integration test with MySQL Testcontainers to verify repositories and transactions against a real database.

**Completion criteria:** each environment uses the correct database and credentials, production contains no secrets in source code, the pool stays within MySQL's connection budget, TLS is verified, the schema is managed by migrations, and the application verifies the DataSource at startup.

## Conclusion

Configuring a MySQL DataSource in Spring Boot requires separating endpoints and secrets by environment, letting Spring Boot manage the DataSource/pool with explicit configuration, and budgeting total connections across the entire application fleet. Use a compatible Connector/J version, an appropriately sized HikariCP pool, a least-privilege runtime account, TLS with server identity verification, and a migration tool for schema changes. Finally, test against real MySQL and monitor the pool to ensure the configuration behaves properly in the deployment environment.
