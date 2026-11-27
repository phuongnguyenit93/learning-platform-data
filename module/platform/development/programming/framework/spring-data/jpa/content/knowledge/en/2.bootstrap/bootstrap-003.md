# Configuring DataSource, Connection Details, and Environment Profiles

## Objectives and Scope

In a Spring Data JPA application, `DataSource` supplies JDBC connections to the database. Spring Boot can automatically create a `DataSource` and configure Hibernate, `EntityManagerFactory`, and the transaction manager from dependencies and configuration properties. You need to declare the right connection details, select configuration per runtime environment, and manage secrets safely.

After this lesson, you will be able to:

- Explain the connection flow from a JPA repository to the database.
- Add a JDBC driver and configure the URL, username, and password.
- Understand basic HikariCP connection pool settings.
- Separate shared, development, and production configurations using Spring Profiles.
- Move sensitive information into environment variables and troubleshoot connection errors.

The examples use Spring Boot 3.x, Java 17+, and PostgreSQL. The same principles apply to MySQL, MariaDB, SQL Server, or H2 when substituting the corresponding JDBC driver and URL.

## 1. Where Does DataSource Fit in Spring Data JPA?

A typical data operation flow:

1. A controller or service calls a Spring Data repository, such as `CustomerRepository`.
2. The repository uses the JPA `EntityManager` to execute queries.
3. Hibernate (the default JPA provider typically configured by Spring Boot) translates JPA operations into SQL.
4. Hibernate obtains a JDBC connection from `DataSource`.
5. `DataSource` provides a connection from the connection pool; the statement is sent to the database.
6. The results are mapped back to entities and returned to the caller.

`DataSource` is a JDBC abstraction for obtaining connections. It is not a database server, nor does it create the database automatically. The database, user, and access permissions must be prepared on the database management system side.

When Spring Data JPA and a suitable JDBC driver are on the classpath and the application has not defined its own `DataSource`, Spring Boot typically auto-configures a `DataSource`. With a single data source, Boot can also auto-configure Hibernate, `EntityManagerFactory`, and the transaction manager. Therefore, applications usually do not need to create these beans manually.

## 2. Adding Dependencies and the JDBC Driver

Maven example using Spring Boot dependency management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-data-jpa` provides Spring Data JPA, the JPA API, and required JDBC components; Spring Boot typically uses HikariCP as the default connection pool when it is on the classpath. The `org.postgresql:postgresql` dependency provides the driver for JDBC to communicate with PostgreSQL. When using MySQL or another database system, add the corresponding driver.

If using the Spring Boot parent or BOM, do not set separate versions for the driver and starter unless there is a specific compatibility reason. Let the Spring Boot version manage dependencies that have been tested together.

Missing-driver errors typically appear when the application cannot locate the JDBC driver class or does not recognize the URL. Verify that the dependency has been downloaded and that the driver matches the database in use.

## 3. Configuring Connection Details

Spring Boot reads configuration from `application.properties` or `application.yml`. Either format can be used. The examples below use YAML.

### 3.1. Basic DataSource Properties

| Property | Meaning |
|---|---|
| `spring.datasource.url` | JDBC URL identifying the database type, host, port, and database to connect to |
| `spring.datasource.username` | The application's database account |
| `spring.datasource.password` | The account password |
| `spring.datasource.driver-class-name` | JDBC driver class name; Spring Boot can usually infer this from the URL and the driver on the classpath |
| `spring.datasource.hikari.*` | HikariCP connection pool settings when HikariCP is used |

PostgreSQL URL example:

```text
jdbc:postgresql://localhost:5432/app_db
```

In the URL above:

- `jdbc:postgresql` specifies the JDBC driver for PostgreSQL.
- `localhost` is the hostname of the database server.
- `5432` is the default PostgreSQL port.
- `app_db` is the name of a pre-created database.

If the database runs in Docker or on another host, the hostname must be an address reachable by the Spring Boot process. When the application also runs in Docker Compose, the hostname is usually the database service name on the Compose network, not necessarily `localhost`.

### 3.2. Shared Configuration in application.yml

Place shared properties in `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: spring-data-jpa-demo

  datasource:
    hikari:
      pool-name: app-db-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 30000

  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        jdbc:
          time_zone: UTC
```

Notable settings:

- `pool-name` names the pool for easier identification in logs and monitoring.
- `maximum-pool-size` caps the maximum number of connections in the pool for a single application instance.
- `minimum-idle` is the minimum number of idle connections the pool tries to maintain.
- `connection-timeout` is the maximum time (in milliseconds) to wait for a connection from the pool before failing.
- `show-sql` toggles printing Hibernate-generated SQL. Setting it to false in the shared configuration prevents unintended SQL logging.
- `format_sql` formats SQL in logs when SQL logging is enabled.
- `jdbc.time_zone` sets the JDBC time zone for Hibernate date/time operations; choose a convention consistent with your application and database.
- `open-in-view: false` disables Open EntityManager in View. Services should load needed data within a transaction and return appropriate DTOs; with this disabled, accessing lazy relationships after the transaction/session closes can cause errors.

In this example, the URL, username, and password are placed in profile-specific configuration files in the next section. Without valid connection configuration from an active profile or external configuration source, the application will fail to create a DataSource.

### 3.3. Environment-Specific Configuration

Create files alongside `application.yml`:

- `application-dev.yml`: configuration for local development on a personal machine.
- `application-test.yml`: configuration for testing if needed.
- `application-prod.yml`: configuration for production.

Example `application-dev.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/app_db
    username: app_user
    password: ${DB_PASSWORD:local-dev-only}

  jpa:
    hibernate:
      ddl-auto: update
    show-sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

The default password in the example is only to help run tests on a local machine. Replace it with your own local password if needed. Logging bind parameters at TRACE level can expose sensitive data, so only enable it temporarily in development and disable it when no longer needed for diagnostics.

Example `application-prod.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: ${DB_POOL_MAX:20}
      minimum-idle: ${DB_POOL_MIN:5}

  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false
```

In production, `DB_URL`, `DB_USERNAME`, and `DB_PASSWORD` must be supplied by the deployment environment or a secret management system. Do not put real production passwords in source code, committed YAML files, or logs.

The `dev` profile uses `ddl-auto: update` for convenient schema experimentation. Production uses `validate` so Hibernate checks that the existing schema matches the entity mappings. Schema management is explained in Section 6.

### 3.4. Selecting a Profile When Running the Application

Spring Profiles allow Spring Boot to load additional configuration suitable for the active runtime environment. Example:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

On PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DB_PASSWORD = "local-secret"
.mvnw.cmd spring-boot:run
```

When running a JAR, you can pass the profile via a command-line argument:

```bash
java -jar target/spring-data-jpa-demo.jar --spring.profiles.active=prod
```

Common ways to activate a profile:

- Environment variable `SPRING_PROFILES_ACTIVE=dev`.
- Command-line argument `--spring.profiles.active=dev`.
- Property `spring.profiles.active` in the shared configuration when you genuinely want to set a default profile for the application.

Spring Boot loads the shared configuration and then applies properties from the active profile. Values from environment variables and command-line arguments can override configuration packaged inside the application. Do not place `spring.profiles.active` inside an `application-{profile}.yml` file to activate that file itself; select the profile from shared configuration or the runtime environment.

Multiple profiles can be active simultaneously, though you must understand precedence when profiles declare the same property. For simple applications, choose one clear profile per run to avoid ambiguity in the final configuration.

## 4. Managing Environment Variables and Secrets

There are two common ways to supply configuration:

1. Use Spring Boot property names directly, such as `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD`.
2. Use placeholders in YAML, such as `${DB_URL}`; in that case the process must have the corresponding `DB_URL` environment variable set.

Example environment variables for production:

```text
SPRING_PROFILES_ACTIVE=prod
DB_URL=jdbc:postgresql://db.internal:5432/app_db
DB_USERNAME=app_runtime
DB_PASSWORD=<secret-from-deployment-platform>
DB_POOL_MAX=20
DB_POOL_MIN=5
```

Principles for protecting connection information:

- Create a dedicated application account with the minimum required privileges; do not use a database administrator account to run the application.
- Supply passwords from a secret store, Kubernetes Secret, deployment platform, or your organization's secret management mechanism.
- Do not commit real passwords to Git. If accidentally committed, rotate/revoke the secret; deleting it from the current file does not erase Git history.
- Do not print passwords, tokens, or full JDBC URLs containing credentials to logs.
- For networked databases, configure TLS/SSL as required by the system and verify certificates following the provider's instructions.
- Separate accounts and databases across dev, test, and production to avoid writing data to the wrong environment.

Placeholders like `${DB_URL}` do not create environment variables automatically. If a required variable is missing, Spring will fail on startup with an unresolved placeholder error; this is a signal to check deployment configuration.

## 5. HikariCP Connection Pool

Opening a new TCP/JDBC connection for each operation is expensive. A connection pool maintains a group of reusable connections. When a query is needed, the application borrows a connection from the pool and returns it after the transaction or operation completes.

Spring Boot typically selects HikariCP when the library is on the classpath. Common properties:

| Property | Effect |
|---|---|
| `maximum-pool-size` | Limits the total number of connections in the pool |
| `minimum-idle` | Target minimum number of idle connections |
| `connection-timeout` | Wait time to obtain a connection from the pool, in milliseconds |
| `idle-timeout` | Time an idle connection may stay in the pool before removal, in milliseconds |
| `max-lifetime` | Maximum lifetime of a connection in the pool, in milliseconds |
| `pool-name` | Identifying name of the pool |

Do not increase `maximum-pool-size` arbitrarily. Total open connections must be calculated across all application instances—for example, 4 instances with a max pool of 20 can require up to 80 connections, excluding admin tasks and other applications. Compare against the database's connection limit, instance count, actual load, and query duration.

`connection-timeout` only controls how long to wait when borrowing a connection from the pool; it is not a timeout for the entire SQL statement. Query, transaction, and network timeouts are separate settings. Only adjust `max-lifetime` or `idle-timeout` when dictated by database/proxy limits and monitoring data. Do not hold connections longer than necessary; avoid slow network calls inside transactions holding a connection.

If the pool is exhausted, the application typically waits until `connection-timeout` and then fails. Causes may include a pool that is too small, long-running transactions, slow queries, connection leaks from manual JDBC handling, or an unresponsive database. Increasing pool size without finding the root cause can overload the database further.

## 6. Configuring JPA and Schema Management

DataSource defines how to connect to the database; `spring.jpa.*` properties control JPA/Hibernate behavior. Frequently used properties:

- `spring.jpa.hibernate.ddl-auto`: action Hibernate performs on the schema.
- `spring.jpa.show-sql`: prints Hibernate-generated SQL.
- `spring.jpa.properties.hibernate.format_sql`: formats SQL in logs.
- `spring.jpa.open-in-view`: toggles keeping the EntityManager open throughout a web request.

Common `ddl-auto` values:

| Value | Behavior |
|---|---|
| `none` | Does not automatically alter the schema |
| `validate` | Checks whether the schema matches entity mappings |
| `update` | Attempts to adjust the schema to match entities; does not replace controlled migration tools |
| `create` | Creates the schema on startup; existing schema objects may be recreated |
| `create-drop` | Creates the schema on startup and drops it when EntityManagerFactory closes |

`update`, `create`, and `create-drop` are suitable for controlled experimentation and should not be used as a production schema deployment workflow. They can cause data loss or fail to express complex changes such as column renames, data transformations, and constraint changes.

For production, use a migration tool such as Flyway or Liquibase to manage schema changes with versioning. A common workflow is running migrations before or during a controlled startup phase, then letting Hibernate `validate` confirm entity mappings match the schema.

The database must exist before the application connects. Configuring a JDBC URL does not create the database or user. The runtime user needs appropriate permissions to read/write data; the migration account may need higher DDL privileges and should be managed separately.

## 7. Verifying the Configuration

Follow these steps in order after configuring:

1. Confirm the database server is running and reachable from the machine/container running the application.
2. Confirm the database has been created, and hostname and port are correct.
3. Confirm the JDBC driver is in runtime dependencies.
4. Confirm the right profile is active and environment variables are supplied.
5. Start the application and read logs to confirm DataSource/Hibernate initialized successfully.
6. Call a repository from a service or run an integration test to execute an actual query.
7. If using `ddl-auto: validate`, confirm migrations have run before startup.

You can check the active profile via startup logs or Actuator configuration if the project has added and secured the appropriate endpoints. Do not expose endpoints displaying the entire environment or sensitive configuration publicly.

Example command running the dev profile:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

When SQL inspection is needed, enable logging in dev:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Hibernate 6 uses the `org.hibernate.orm.jdbc.bind` logger to record bind parameters. These logs may contain user data; disable them after diagnostics and do not use them in production without evaluating security impact.

## 8. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| `Failed to determine a suitable driver class` | Missing JDBC driver or missing JDBC URL | Check runtime dependency, URL, and active profile |
| `Connection refused` | Database not running, wrong host/port, or network/firewall blocking | Check the service, listening port, and connectivity from the actual app environment |
| `password authentication failed` | Wrong username/password or user not allowed to log in from that host | Verify secrets, user, and database authentication policy |
| `database does not exist` | Database name in URL has not been created or is misspelled | Create the database and verify the name in the JDBC URL |
| Could not resolve placeholder | Missing environment variables such as `DB_URL` or `DB_PASSWORD` | Check variables supplied to the right process/container |
| `Connection is not available, request timed out` | Pool exhausted or database responding slowly | Check connection count, long transactions, slow queries, and pool limits |
| `Schema-validation: missing table/column` | Schema not yet migrated or does not match entity | Check migrations, table/column names, and active profile |
| Works in dev but fails in prod | Different URL, permissions, secrets, profile, SSL, or schema | Compare resolved configuration without printing secrets; check production permissions and network |
| Date/time mismatch | Inconsistent JVM, JDBC, database time zones, or data types | Choose UTC or a system convention and configure it consistently |

When diagnosing, read the root cause in the stack trace, usually found under `Caused by`. Hibernate errors such as failing to obtain a JDBC connection may just be wrappers; the actual cause typically lies in the driver, network, authentication, or database.

## 9. Notes When Scaling Configuration

- **Multiple DataSources:** When an application connects to multiple databases, declare each DataSource, designate a primary bean if appropriate, configure the corresponding EntityManagerFactory and transaction manager, and bind repositories to the right data source. Do not simply declare two URLs and expect Spring to infer which database each repository uses.
- **Custom DataSource:** When declaring your own `DataSource` bean, parts of default auto-configuration may step aside for custom configuration. Ensure required JPA/transaction beans remain properly configured.
- **Repository Testing:** `@DataJpaTest` focuses on the persistence layer and in some configurations may replace the DataSource with an embedded database. If you need to test against real PostgreSQL, configure tests appropriately or use Testcontainers.
- **Separating Runtime and Migration Privileges:** The runtime account should only have permissions needed for normal operations. Permissions to create tables and modify schemas should belong to the migration process.
- **Operational Observability:** Monitor active/idle connection counts, connection wait times, connection errors, and query durations. Tune the pool based on metrics rather than guesswork.

## 10. Completion Checklist

- [ ] Spring Data JPA starter and the right JDBC driver for the database are added.
- [ ] JDBC URL points to the right host, port, and database.
- [ ] Username/password are supplied from an appropriate configuration source.
- [ ] dev/test/prod profiles are clearly separated and the needed profile is active.
- [ ] Pool limits fit the instance count and database capacity.
- [ ] Schema is managed with migrations; production does not use risky automatic schema generation modes.
- [ ] Application starts, acquires a connection, and executes a repository query.
- [ ] Logs do not leak passwords or sensitive data.

## Conclusion

DataSource configuration is the bridge between Spring Data JPA and the database. Spring Boot auto-configures most JDBC/JPA components, while the application supplies the right driver, URL, credentials, and profile. Separating configuration by environment, managing secrets outside source code, bounding connection pools, and using controlled migrations help keep the application stable from development machines to production.
