# Registering DataSource as a Bean and Providing Connection Configuration in Spring Framework

## 1. Lesson Objectives

`DataSource` is the starting point for many relational database access mechanisms in Java and Spring. An application can create JDBC connections directly, but with Spring Framework, the standard approach is to **register a `DataSource` as a bean, letting Spring manage its lifecycle and supply that bean to components that need data access**.

After completing this lesson, you should be able to do these specific things:

1. Explain how `javax.sql.DataSource` differs from `java.sql.Connection` and a connection pool.
2. Register a `DataSource` using `@Configuration` and `@Bean` in plain Spring Framework, without depending on Spring Boot.
3. Supply URL, username, password, and pool parameters from configuration external to source code; accurately determine the configuration source.
4. Inject the same `DataSource` into `JdbcTemplate`, repositories, and the transaction manager, rather than creating pools manually at each call site.
5. Know when Spring Boot creates the bean automatically and how to avoid unintentionally creating two `DataSource` beans.
6. Verify connectivity with a runnable program, understand when resources open/close, and diagnose common configuration errors.

**Scope:** the focus is on bean declaration, parameter binding, and connection lifecycle. Complex JDBC queries, transaction propagation, JPA, and SQL optimization belong to subsequent lessons.

## 2. Distinguishing DataSource, Connection, Pool, and Spring Bean

`javax.sql.DataSource` is a **standard Java interface**, whose primary method `getConnection()` provides a `java.sql.Connection`. It does not inherently mean a connection pool: an implementation may open a new connection on every call, or retrieve a connection from a pool.

| Object | Function | Who Should Manage It? |
| --- | --- | --- |
| `DataSource` | Configures and supplies JDBC connections | Spring IoC container holds it as a bean |
| `Connection` | JDBC communication session with the database; carries transaction state | JDBC code or Spring JDBC/transaction infrastructure borrows and returns/closes it properly |
| Connection pool | Reuses physical connections, limits concurrent connections | A `DataSource` implementation such as HikariCP |
| `JdbcTemplate` | Executes SQL, binds parameters, maps results, and releases resources | Created as a bean, injected with `DataSource` |
| Transaction manager | Coordinates one or more JDBC calls within the same transaction | Spring transaction infrastructure |

Typical flow:

```text
Spring ApplicationContext
  ├── bean "dataSource" ──► HikariDataSource (pool)
  ├── bean "jdbcTemplate" ─► uses the DataSource bean above
  └── bean "transactionManager" ─► uses the DataSource bean above
                                         │ getConnection()
                                         ▼
                                   JDBC Connection
                                         │ driver
                                         ▼
                                   Database server
```

A singleton `DataSource` is **not** a singleton `Connection`. Requests can use separate connections allocated by the pool while referencing the same `DataSource` bean. When the application returns/closes a connection borrowed from HikariCP, the pool typically takes the connection back for reuse; only when Spring closes the context is the pool itself closed.

These principles are especially important:

- Inject `DataSource` or `JdbcTemplate`; do not call `new HikariDataSource(...)` inside each controller, service, or repository.
- Do not store a JDBC `Connection` as a shared field across multiple requests/threads.
- With Spring JDBC, let `JdbcTemplate` acquire and return connections. If using plain JDBC outside a Spring-managed transaction, use `try-with-resources` for connections, statements, and result sets.
- When a Spring transaction is active, do not manually commit/rollback or close a connection managed by the transaction manager; prefer `JdbcTemplate` or Spring's transaction-aware APIs.

## 3. Process of Creating and Registering the Bean in Plain Spring Framework

For an application **not using Spring Boot**, you need to define the `DataSource` bean and configuration loading mechanism yourself. A common configuration looks like this:

```java
@Configuration
@PropertySource("classpath:db.properties")
class DatabaseConfig {
    @Bean(destroyMethod = "close")
    HikariDataSource dataSource(Environment environment) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(environment.getRequiredProperty("db.url"));
        config.setUsername(environment.getRequiredProperty("db.username"));
        config.setPassword(environment.getRequiredProperty("db.password"));
        config.setMaximumPoolSize(
                environment.getProperty("db.pool.max-size", Integer.class, 5));
        return new HikariDataSource(config);
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

**Note:** This is an illustrative snippet inside a configuration class, without imports, startup application, or configuration file; Section 4 provides a **complete, standalone runnable** project.

Step-by-step explanation:

1. `@Configuration` marks a class that declares beans for the container. `@Bean` on a method indicates the returned object is registered as a bean.
2. `@PropertySource("classpath:db.properties")` adds a `.properties` file from the classpath into `Environment`. Plain Spring Framework **does not automatically understand `application.yml` via Spring Boot's configuration mechanism**.
3. `Environment` is injected by Spring into the factory method. `getRequiredProperty` helps detect missing URL/username/password early; `getProperty` can intentionally provide a default for non-sensitive parameters.
4. `HikariConfig` receives the JDBC URL, credentials, and pool parameters. `new HikariDataSource(config)` creates the pool with that configuration.
5. `@Bean(destroyMethod = "close")` instructs Spring to call `close()` when destroying the bean, releasing pool connections when closing the context.
6. `jdbcTemplate(DataSource dataSource)` receives the same existing bean from the container. Spring resolves the dependency by type; the method does not create a second `DataSource`.

For closeable beans, Spring can sometimes infer the destroy method; here `close` is specified explicitly to make the intent clear. Destroying the pool is **different** from calling `connection.close()` on a borrowed connection.

### Choosing the Right Implementation

- `DriverManagerDataSource` (Spring JDBC) makes examples and tests simple, but **does not pool**: each `getConnection()` creates a new connection.
- `HikariDataSource` (HikariCP) is a popular pool choice in real applications; requires declaring the dependency and configuring appropriate limits.
- `JndiObjectFactoryBean`/JNDI lookup is suitable when an application server or container already provides a `DataSource`; in that case do not create a duplicate pool.
- `DataSource` can be created by framework auto-configuration; if the right bean already exists, inject and use that bean.

## 4. Standalone Practice: Registering DataSource with @Bean

The example uses **Java 17**, **Spring Framework 6.2.3**, **HikariCP 5.1.0**, and **H2 2.3.232**. Versions are pinned for reproducible illustration. This is a simple Java application using the Spring container, **needing no Spring Boot, HTTP server, or externally installed database**.

### 4.1. File Structure

```text
datasource-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/demo/DataSourceBeanDemo.java
        └── resources/db.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'datasource-bean-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.3'
    implementation 'org.springframework:spring-jdbc:6.2.3'
    implementation 'com.zaxxer:HikariCP:5.1.0'
    runtimeOnly 'com.h2database:h2:2.3.232'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}

application {
    mainClass = 'demo.DataSourceBeanDemo'
}
```

`src/main/resources/db.properties`:

```properties
# In-memory H2: learning example configuration only.
db.url=jdbc:h2:mem:bean_demo;DB_CLOSE_DELAY=-1
db.username=sa
db.password=
db.pool.max-size=4
db.pool.connection-timeout-ms=30000
```

`db.password` is empty only because the H2 demo allows it. **Do not** copy the pattern of storing passwords directly in repository files for production databases. In `.properties`, the H2 URL and string containing `;` are parsed as normal text values.

`src/main/java/demo/DataSourceBeanDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

public class DataSourceBeanDemo {

    @Configuration
    @PropertySource("classpath:db.properties")
    static class DatabaseConfig {

        @Bean(destroyMethod = "close")
        HikariDataSource dataSource(Environment env) {
            HikariConfig config = new HikariConfig();

            config.setJdbcUrl(env.getRequiredProperty("db.url"));
            config.setUsername(env.getRequiredProperty("db.username"));
            config.setPassword(env.getRequiredProperty("db.password"));

            config.setMaximumPoolSize(
                    env.getProperty("db.pool.max-size", Integer.class, 4));
            config.setConnectionTimeout(
                    env.getProperty("db.pool.connection-timeout-ms",
                            Long.class, 30_000L));

            return new HikariDataSource(config);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DatabaseConfig.class)) {

            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE projects (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL
                    )
                    """);

            int inserted = jdbc.update(
                    "INSERT INTO projects (id, name) VALUES (?, ?)",
                    7L, "DataSource bean");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM projects", Integer.class);
            String name = jdbc.queryForObject(
                    "SELECT name FROM projects WHERE id = ?",
                    String.class, 7L);

            System.out.println("bean=" +
                    dataSource.getClass().getSimpleName());
            System.out.println("inserted=" + inserted);
            System.out.println("count=" + count);
            System.out.println("name=" + name);
        }
    }
}
```

From the `datasource-bean-demo` directory with Gradle installed, run:

```bash
gradle run
```

If you add Gradle Wrapper to the project, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Below are the **four lines written by `System.out`**; startup/shutdown logs from HikariCP or Gradle may also appear:

```text
bean=HikariDataSource
inserted=1
count=1
name=DataSource bean
```

**Mechanism explanation:**

1. `AnnotationConfigApplicationContext` reads `DatabaseConfig`, processes `@PropertySource`, invokes the `dataSource` factory method, and registers the Hikari object in the container.
2. The `jdbcTemplate` bean receives the same `DataSource`. There is no need to pass URL/username/password to `JdbcTemplate`, because it only needs the `DataSource` interface.
3. When the first SQL runs, `JdbcTemplate` requests a connection, executes the statement, and returns the connection to the pool according to the proper lifecycle.
4. `db.url` specifies in-memory H2; `DB_CLOSE_DELAY=-1` allows the in-memory database to persist across connection closes between statements within the same JVM.
5. `jdbc.update` returns the number of affected rows, so `inserted=1`; two queries read back the data producing `count=1` and `name=DataSource bean`.
6. The `try-with-resources` block closes `ApplicationContext` upon completion, causing Spring to call `HikariDataSource.close()`. The pool is not recreated per SQL statement.

**Meaningful experiments:**

- Delete the `db.url=...` line: `getRequiredProperty("db.url")` cannot find the property, so the bean cannot initialize. This is a configuration error that must be resolved before the application serves requests.
- Change the H2 URL to a non-existent database URL: you may encounter an error acquiring a connection or initializing the pool. Inspect the root exception and SQLState; do not assume it is a `@Bean` error.
- Change `db.pool.max-size` from 4 to 2 and observe the pool configuration; this limits the number of connections **in the pool**, not the number of `DataSource` beans.
- Remove `@Bean` from the `dataSource` method: Spring will not register that object as a bean, so the `DataSource` dependency of `jdbcTemplate` will fail to resolve (if no replacement bean exists).

## 5. Configuration Sources and Avoiding Hard-Coded Connection Info

A `DataSource` bean requires at least the following depending on the DBMS:

- **JDBC URL:** driver/protocol type, host, port, database, connection parameters; for example PostgreSQL `jdbc:postgresql://db.example.internal:5432/orders`.
- **Username/password** or an equivalent authentication mechanism (identity/IAM, wallet, secret provider...).
- **JDBC driver** on the runtime classpath, compatible with the database and JDK.
- **Pool configuration:** maximum size, connection borrow wait time, appropriate timeout/idle/lifetime values.
- **Security options:** TLS and certificate verification, least-privilege database permissions, timeouts to avoid prolonged hangs.

Do not place real sensitive values in Java code, git repositories, shared learning examples, or logs. Separate configuration per environment and supply secrets via environment variables, a secret manager, or secure configuration management.

### Plain Spring Framework: Environment + PropertySource

In the example in Section 4, `@PropertySource("classpath:db.properties")` loads a file from the classpath; `Environment` aggregates property sources in priority order. System properties or environment variables may participate depending on the environment and key name; verify the **actual resolved property name**, rather than assuming Spring Boot's "relaxed binding" rules always exist in Spring Core.

You can define custom property sources for real environments without changing Java code, such as adding an external file source or configuring a bean loaded from a secret provider. `getRequiredProperty` is useful for catching missing parameters early. However, it only checks **presence** of the property; the application should still validate non-empty strings for required values other than demo passwords.

With `@Value("${db.url}")` (if choosing placeholder injection), you must understand that placeholder resolution has been enabled in the context. In a plain Spring Framework application, `Environment` is a clearer illustrative choice with fewer dependencies on additional infrastructure.

### Spring Boot: Declarative Configuration with Auto-Configuration

In a Spring Boot application with `spring-boot-starter-jdbc` and an appropriate JDBC driver, **if the auto-configuration conditions are met**, Boot typically creates the `DataSource` bean automatically and uses HikariCP when present on the classpath. In that case, an `application.yml` file may be all you need:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

An example `DB_URL` value in production could be `jdbc:postgresql://db.internal:5432/app`; the corresponding PostgreSQL driver must be added. The `${...}` values are Spring Boot placeholders, requiring the matching environment variables or properties to actually be present.

**Do not define an extra `@Bean DataSource` just because you are using Spring Boot.** If you provide a `DataSource` bean yourself, the default `DataSource` auto-configuration typically backs off per Boot's conditions; at that point, you become responsible for configuration, pooling, lifecycle, and the relationship with the transaction manager. Check the actual Boot version and auto-configuration report if behavior differs from expectations.

### When a Custom Bean Is Needed in Boot

If you have special requirements (multiple databases, custom driver/pool, authentication mechanisms), use Boot's strongly typed binding mechanism. A simplified pattern with `DataSourceProperties` and HikariCP:

```java
// Illustrative snippet specific to a Spring Boot application.
// Requires importing DataSourceProperties, ConfigurationProperties,
// HikariDataSource, and related Spring annotations.
@Bean
@ConfigurationProperties("app.datasource")
DataSourceProperties appDataSourceProperties() {
    return new DataSourceProperties();
}

@Bean(destroyMethod = "close")
@ConfigurationProperties("app.datasource.hikari")
HikariDataSource appDataSource(DataSourceProperties appDataSourceProperties) {
    return appDataSourceProperties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
}
```

With this example, `app.datasource.url/username/password` bind to `DataSourceProperties`; `app.datasource.hikari.*` configures the pool. This is an **illustrative snippet**, not a complete standalone runnable class; in an application with multiple data sources, set explicit bean names/`@Qualifier` and avoid ambiguous injection. For a single standard database, prefer standard Boot configuration before writing custom factory methods.

## 6. Supplying the Bean to Repositories, JdbcTemplate, and Transaction Manager

Registering the bean is only the first step; what matters is that **all components for the same database use the expected `DataSource`**.

A plain Spring JDBC configuration can add a transaction manager as follows:

```java
// Added to a @Configuration class that already has a DataSource bean.
// Illustrative snippet; requires corresponding imports.
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
JdbcTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

`JdbcTransactionManager` implements `PlatformTransactionManager` for JDBC on the same `DataSource`. To use `@Transactional` in plain Spring Framework in proxy mode, you need to enable transaction management (e.g., `@EnableTransactionManagement`), invoke services through Spring-managed beans, and understand self-invocation limits. Details on propagation and rollback belong to the transaction lessons; the key point here is that **the DataSource must match**.

A repository can be injected:

```java
@Repository
public class ProjectRepository {
    private final JdbcTemplate jdbcTemplate;

    public ProjectRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countProjects() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM projects", Integer.class);
        return count == null ? 0 : count;
    }
}
```

This is a separate snippet, not a class inside the demo program in Section 4; it needs proper package/imports and component scanning enabled or repository bean registration. Applications should inject dependencies via constructor for clarity and testability.

**Why does using the same DataSource matter?** When Spring manages a JDBC transaction, the connection resource is bound to the current transaction. `JdbcTemplate` can participate in that connection/transaction via Spring's infrastructure; manually creating another pool or calling `DriverManager.getConnection(...)` inside a DAO can put the operation outside the expected transaction.

If an application has **two `DataSource`s** (e.g., `ordersDataSource` and `reportingDataSource`), name them clearly, use `@Qualifier` to pick the right bean when injecting `JdbcTemplate` and the transaction manager, or designate a `@Primary` bean intentionally. A typical JDBC transaction manager is tied to one `DataSource`: do not assume a transaction on database A automatically rolls back operations on database B.

## 7. Pool Lifecycle and Configuration Values to Understand

**`maximumPoolSize`:** maximum number of physical connections the pool can manage simultaneously. If no free connection is available, callers must wait until a connection is returned or `connectionTimeout` expires; at that point HikariCP may throw `SQLException`. A limit of 10 is **per instance/pool**, not across the entire deployment cluster.

**`connectionTimeout`:** maximum time to wait when borrowing a connection from the pool, in milliseconds for the Hikari setter. It is **not identical** to an SQL execution timeout or the JDBC driver's socket/network timeout.

**`maxLifetime` / `idleTimeout` / `keepaliveTime`:** relate to connection lifecycle and the pool actively keeping connections alive; choose according to database/proxy/network timeout limits. Do not set arbitrarily low values that cause constant closing and reopening.

**`minimumIdle`:** number of idle connections the pool tries to maintain. Unless there is a specific need, you can start with the pool's defaults and measure actual load before tuning.

**Lifecycle:** in a normal Spring context, the `DataSource` bean should be a singleton and live for the duration of the application. Spring closes the pool on shutdown. Connections borrowed from the pool should be returned promptly; do not hold a connection while waiting on a network API or running long computations that do not need the database.

Connection capacity example: if there are 6 instances and each instance configures `maximumPoolSize=10`, peak total demand from those six pools can reach **60 connections** (excluding admin, migrations, monitoring, and other services). Balance the database connection limit against the number of instances/pools, transaction duration, and concurrency; "larger pool means faster" is usually wrong.

**A pool does not solve every problem:** long-running transactions, slow queries, deadlocks, lock contention, missing indexes, or connection leaks will still bottleneck the application. Observe active/idle/pending connections, connection borrow latency, query execution time, and timeouts; only tune the pool after identifying the root cause.

## 8. Comparing Configuration Styles by Environment

| Scenario | How Should DataSource Be Registered? | Configuration Source |
| --- | --- | --- |
| Console app / plain Spring Framework | `@Configuration` + `@Bean` or existing infrastructure | `Environment`, `@PropertySource`, external sources |
| Spring Boot with a single database | Let `DataSourceAutoConfiguration` create the bean when appropriate | `spring.datasource.*` and environment/secret manager |
| Spring Boot with multiple databases | Explicitly named beans, clear binding and qualifiers | Separate prefix per database |
| Running in an application server with JNDI | Look up the `DataSource` managed by the server | JNDI name and server configuration |
| Integration test | H2 test `DataSource` or real database container | Test profile, test properties, ephemeral database |
| Production | Controlled bounded pool and secure credentials | Secret manager/environment, environment-specific URL/TLS/driver |

**Do not use `DriverManagerDataSource` for workloads requiring pooling.** Let a stable pool implementation serve as the bean, avoiding a new pool per request.

## 9. Checklist for Verifying a Working DataSource Bean

Check in order to distinguish DI, configuration, driver, and database errors:

1. **Does the bean exist?** `ApplicationContext.getBean(DataSource.class)` or check bean names. If not found, verify `@Configuration` is imported/scanned, `@Bean` is processed, and Boot auto-configuration actually activated.
2. **Are there multiple beans of the same type?** When injecting by `DataSource.class` with two candidates, Spring may report `NoUniqueBeanDefinitionException`. Use explicit names, `@Qualifier`, or `@Primary` intentionally.
3. **Are parameters resolved?** Check property names and profiles, ensuring URL, username, and secret are present. You can log masked host/database IDs; **do not log passwords, full connection strings containing secrets, or tokens**.
4. **Is the driver present?** Missing the JDBC driver on the runtime classpath can prevent Hikari/DriverManager from initializing connections. Install the right driver for the JDBC URL and JDK/database version.
5. **Is the database reachable?** Check DNS, firewall, port, TLS, database name, and account/permissions; do not blame Spring for every `SQLException`.
6. **Is the pool issuing connections?** If startup succeeds but requests time out, check for connection leaks, long transactions, active/pending pool counts, and database limits.
7. **Where do JdbcTemplate and the transaction manager point?** Both must use the corresponding bean. Especially with multiple pools, explicitly assert dependencies instead of relying on variable names.
8. **Is a real flow tested?** Run at least one simple SQL statement and release the context; with a real database, verify required query/write privileges and TLS.

### Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: DataSource` | Config not registered or auto-configuration did not apply | Import/scan `@Configuration`; inspect Boot's condition report |
| `NoUniqueBeanDefinitionException` | Multiple `DataSource` beans but ambiguous injection | Use qualifier/primary and explicit transaction naming |
| `db.url` not found | Missing `@PropertySource`, wrong classpath, wrong property name | Verify resource file and `Environment` sources |
| "No suitable driver" / driver class not found | Driver missing from runtime dependencies | Add the appropriate JDBC driver and verify the URL |
| Login failed / authentication error | Wrong credentials, permissions, or auth method | Fix secret, account, and privileges; do not print secrets |
| Connection refused / timed out | Host, port, network, TLS, or DB not ready | Check network, service/database, certificates |
| Connection is not available / timeout from pool | Pool exhausted or connections held too long | Measure active/pending, transaction duration, leaks |
| Rollback does not behave as expected | Wrong `DataSource`/transaction manager or bypassing proxy | Check bean wiring and test rollback |
| H2 tests pass but production fails | Different dialect, types, privileges, TLS, and behavior | Run integration tests on a production-compatible DB |

## 10. Testing Proper Configuration by Behavior, Not Just Startup

The demo proved three things: Spring returns a `DataSource` bean, `JdbcTemplate` can use it, and H2 executes write/read operations. In real projects, also verify:

- **DI:** repositories receive the right `JdbcTemplate`/`DataSource` bean, especially with multiple connection pools.
- **Lifecycle:** Spring context closes the pool; do not manually create a pool on every repository call.
- **Connection validation:** test a `SELECT 1` query or real operation against a test database.
- **Configuration failure:** when a required property is missing, the application fails clearly at startup instead of running with a dangerous default connection.
- **Transaction consistency:** repositories belonging to the same business operation share the same transaction manager; verify rollback with a dedicated integration test.
- **Production parity:** test access with a database/driver close to production, because H2 does not fully simulate dialect, isolation, permissions, or TLS.

**Extended practice prompt:** replace the H2 demo with a test PostgreSQL database. Move the URL and credentials to environment variables, add the PostgreSQL JDBC driver, and keep `JdbcTemplate` and the insert/query logic unchanged. If the application has to change repository classes just because host or credentials changed, configuration separation and dependency injection are not yet right.

## 11. Self-Assessment Questions

1. Is `DataSource` always a connection pool? Give an example of a non-pooling implementation.
2. Why are `@Bean` methods usually placed inside `@Configuration`, and why should `DataSource` be injected instead of calling `new` inside a repository?
3. When calling `getBean(DataSource.class)`, what happens if no bean exists or two beans of the same type exist?
4. How do `@PropertySource` and `Environment` work together in plain Spring Framework? Is `application.yml` loaded automatically like in Boot?
5. Why does `@Bean(destroyMethod="close")` make sense for `HikariDataSource` without meaning the pool closes after every query?
6. With `maximumPoolSize=10` across eight application instances, what is the maximum connection pressure those eight pools can create?
7. An application has two databases and two transaction managers: how do you prevent repository A from accidentally receiving `DataSource` B?
8. Why does an application passing tests on in-memory H2 still need connection/driver/query tests against a real database?
9. When a pool times out, what should you observe before deciding to increase `maximumPoolSize`?
10. In Spring Boot, when do you need to declare a `@Bean DataSource`, and when is configuring `spring.datasource.*` sufficient?

**Completion criteria:** independently create and run the project in Section 4, change connection configuration without editing repository code, explain the lifecycle of `DataSource`/`Connection`/pool accurately, and identify why a data-access bean fails to inject or connect.

## 12. Further Reading

- Java SE 17 `DataSource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html
- Spring Framework JDBC Package and DataSource: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework Java-based container configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Boot Data SQL / DataSource Configuration: https://docs.spring.io/spring-boot/reference/data/sql.html
- HikariCP configuration: https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby

When referencing APIs and examples, verify against the exact version branch of Spring, Boot, driver, and database used in your active project.