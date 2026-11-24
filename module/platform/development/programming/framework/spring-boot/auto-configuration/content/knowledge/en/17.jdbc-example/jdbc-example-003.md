# Connection Properties and Default Data Source Selection

> **Goal:** Understand how Spring Boot uses `spring.datasource.*` properties to create a JDBC `DataSource`, how Boot chooses a pool or embedded database when no URL is declared, and when an application-provided `DataSource` causes auto-configuration to yield. After this lesson, you can identify which default data source is being selected, configure connections properly for your driver/pool, and intentionally switch to one or more custom `DataSource`s.

This lesson belongs to **Spring Boot Auto Configuration → JDBC Example**, using Spring Boot 3.3.x and Java 17+. The content focuses on JDBC `javax.sql.DataSource`; it is not equivalent to reactive R2DBC connections (`ConnectionFactory`).

## 1. What is a DataSource and what does Boot auto-configure?

JDBC provides the `javax.sql.DataSource` interface for applications to obtain connections to a database. A `DataSource` typically acts as a factory or connection pool, allowing components such as `JdbcTemplate`, Spring Data JDBC, and JPA to share a uniform way of obtaining connections.

In a typical Spring Boot application, you do not need to write `@Bean DataSource` yourself. When dependencies and conditions match, Boot applies `DataSourceAutoConfiguration`, registering a `DataSource` based on external configuration and the libraries present on the classpath.

Main parts of the process:

1. **Classpath:** Are the JDBC API, Spring JDBC, and an appropriate driver/pool present?
2. **Property binding:** Does `spring.datasource.*` provide a URL, username, password, driver, or JNDI name?
3. **Implementation selection:** Which pool is available? Is one explicitly specified via `spring.datasource.type`?
4. **Back-off:** Has the application already registered a `DataSource`? If so, Boot usually yields default `DataSource` creation.
5. **Usage:** Data-access beans receive `DataSource` via dependency injection; `JdbcTemplate` and several other JDBC components can be auto-configured based on this bean.

A created `DataSource` bean does not guarantee that every SQL statement will succeed. The driver may fail to reach the host, the account may lack permissions, the database may not exist yet, or the schema may not be initialized. Separate configuration creation errors, connection-opening errors, and SQL execution errors when diagnosing.

## 2. Standard connection properties: spring.datasource.*

Common configuration lives under the `spring.datasource` prefix. PostgreSQL example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
~~~

Important fields:

| Property | Meaning | Notes |
| --- | --- | --- |
| `spring.datasource.url` | Database JDBC URL | The most important piece of information when connecting to an external database. |
| `spring.datasource.username` | Connection account | Can be sourced from environment variables or a secret manager. |
| `spring.datasource.password` | Password | Do not commit real values to the repository. |
| `spring.datasource.driver-class-name` | Fully qualified JDBC driver class name | Usually inferred from the URL; if declared explicitly, the class must be on the runtime classpath. |
| `spring.datasource.type` | Desired `DataSource` implementation class | Used to specify a pool/implementation instead of automatic selection. |
| `spring.datasource.jndi-name` | JNDI name of an application-server-managed DataSource | A way to look up a DataSource from JNDI instead of creating a pool with URL/username/password. |
| `spring.datasource.name` | Datasource name, used in some cases like embedded databases | Not a bean name substitute for `@Qualifier`. |
| `spring.datasource.generate-unique-name` | Request a unique embedded database name | Useful in tests where each context needs its own database. |
| `spring.datasource.embedded-database-connection` | Select embedded database type or `none` | Used when multiple embedded databases exist on the classpath or to disable embedded selection. |

These common properties are bound into `DataSourceProperties`. In addition, each pool has its own namespace, such as `spring.datasource.hikari.*`, `spring.datasource.tomcat.*`, `spring.datasource.dbcp2.*`, or `spring.datasource.oracleucp.*`. Not every pool property applies to every implementation.

### 2.1. JDBC URL and driver

JDBC URLs follow vendor-specific formats. Common examples:

| Database | Sample URL | Commonly used driver class |
| --- | --- | --- |
| PostgreSQL | `jdbc:postgresql://localhost:5432/orders` | `org.postgresql.Driver` |
| MySQL | `jdbc:mysql://localhost:3306/orders` | `com.mysql.cj.jdbc.Driver` |
| H2 in-memory | `jdbc:h2:mem:orders` | `org.h2.Driver` |

Boot can infer the driver class from the URL for most databases. Therefore, in normal cases you only need to declare the URL and ensure the driver dependency is present at runtime:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

If you need to declare the driver explicitly:

~~~properties
spring.datasource.driver-class-name=org.postgresql.Driver
~~~

The driver name must exist and be loadable. If an outdated class name is used or the driver jar is not on the runtime classpath, pool creation can fail before any SQL query runs.

**Do not confuse the URL with the database name:** The URL typically contains host, port, and database/service name. A wrong port, wrong database name, or missing SSL parameter can cause connection refusal or authentication rejection by the database even when username/password are correct.

### 2.2. Managing credentials

In real environments, avoid putting passwords directly into committed YAML files. You can use environment variables:

~~~yaml
spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
~~~

Spring Boot also supports environment variables matching regular property names; for example `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD`. When using placeholders, the application must actually receive the corresponding variables from the process/container/IDE. Do not log passwords when debugging.

## 3. How does Boot choose the default DataSource?

The selection depends on the URL, embedded databases, drivers, and available pools. Distinguish two decisions: **which database is connected** and **which DataSource/pool implementation is used**.

### 3.1. External database connection URL present

When `spring.datasource.url` is provided, Boot uses the URL along with credentials/driver to configure a pooled datasource. The pool requires a valid, loadable JDBC driver.

Example:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/orders
spring.datasource.username=orders_app
spring.datasource.password=${DB_PASSWORD}
~~~

If the PostgreSQL driver is on the classpath and a suitable pool is available, Boot can create a pooled `DataSource`. The URL specifies the database; the classpath and pool configuration decide the implementation.

### 3.2. No URL: try an embedded database

If `spring.datasource.url` is absent, Boot tries to configure an embedded database when a suitable implementation is on the classpath. Supported embedded databases include:

- H2
- HSQL
- Apache Derby

They are suitable for demos, tests, or certain internal tools. An in-memory database normally does not persist data after the process exits. Do not accidentally leave a production application using embedded H2 just because the H2 dependency remained on the classpath.

If multiple embedded databases coexist, you can explicitly choose one via `spring.datasource.embedded-database-connection`. The value `none` disables embedded database selection. In tests, `spring.datasource.generate-unique-name=true` prevents application contexts from accidentally sharing a default-named embedded database.

Example H2 dependency for tests:

~~~groovy
dependencies {
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Example test configuration:

~~~properties
spring.datasource.generate-unique-name=true
~~~

### 3.3. Which pool is selected?

In Spring Boot 3.3, when Boot selects a pool automatically from the classpath, the priority order is:

1. **HikariCP** if present.
2. Tomcat JDBC connection pool if HikariCP is absent.
3. Commons DBCP2 if the two options above are absent.
4. Oracle UCP if the previous pools are absent and UCP is available.

`spring-boot-starter-jdbc` and `spring-boot-starter-data-jpa` pull in HikariCP by default. That is why many applications see Hikari even without declaring a separate Hikari dependency.

You can specify the pool via a property:

~~~properties
spring.datasource.type=com.zaxxer.hikari.HikariDataSource
~~~

The value must be the fully qualified class name of a `DataSource` on the classpath. When specifying `spring.datasource.type`, you explicitly decide the implementation instead of relying on the automatic selection algorithm.

**Summary of common cases:**

| URL | Embedded DB on classpath | Pool/driver | Expected result |
| --- | --- | --- | --- |
| External URL present | Embedded DB not needed | Valid driver and pool available | Pooled DataSource connecting to the declared URL |
| No URL | H2/HSQL/Derby and `spring-jdbc` present | Embedded database can be created | Boot can use the embedded database |
| No URL | No suitable embedded DB | No alternative connection source | Cannot determine default datasource; app may fail if a DataSource is required |
| User `DataSource` bean present | Irrelevant for default auto-config branch | Application chooses implementation itself | DataSource auto-configuration yields |

This table describes the common branches. Classpath conditions and other beans in the context can still affect the actual result.

## 4. Connection-pool-specific properties

Standard properties `spring.datasource.url`, `username`, and `password` are shared across implementations. Specific parameters such as pool limits and timeouts must be placed under the namespace of the pool in use.

HikariCP example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Common properties:

- `maximum-pool-size`: maximum number of connections the pool is allowed to hold.
- `minimum-idle`: minimum number of idle connections the pool tries to maintain.
- `connection-timeout`: maximum time to wait for a connection from the pool before throwing an error.
- `idle-timeout`: how long an idle connection can sit in the pool before being eligible for eviction.
- `max-lifetime`: maximum lifetime of a connection in the pool.

The numbers in the example are only to illustrate configuration syntax, not recommendations for every system. Pool size should be based on the number of application instances, concurrent threads, query duration, and database connection limits. If each instance opens a pool of 12 connections and you run 10 instances, total potential open connections can reach 120, not counting admin tools or other services.

### 4.1. Do not confuse spring.datasource.url with Hikari jdbc-url

Hikari has a Java property named `jdbcUrl`, whereas `DataSourceProperties` uses the common name `url`. When using Boot's standard `spring.datasource.*` configuration, Boot handles mapping the URL to the pool implementation.

However, if you create a `HikariDataSource` yourself and bind directly:

~~~java
@Bean
@ConfigurationProperties("app.datasource")
HikariDataSource customDataSource() {
    return DataSourceBuilder.create()
            .type(HikariDataSource.class)
            .build();
}
~~~

then Hikari has no `url` property; its direct property is `jdbc-url`. Configuration under the `app.datasource` prefix then needs `app.datasource.jdbc-url`.

A more flexible approach is to use `DataSourceProperties` and `initializeDataSourceBuilder()`; it preserves the common `url` property contract and maps it to `jdbcUrl` appropriately for Hikari. Section 7 has a complete example.

## 5. When does auto-configuration yield?

If the application declares a bean of type `DataSource`, Spring Boot normally does not create an additional default datasource. This is the back-off mechanism giving the user control over how connections are created.

Example of an application-created datasource:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDatabaseConfiguration {

    @Bean
    DataSource customDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:h2:mem:custom")
                .username("sa")
                .build();
    }
}
~~~

This is a short illustrative example; a real project needs the H2 driver dependency and should externalize values rather than hardcoding them. When this `DataSource` bean is present before auto-configuration evaluates conditions, Boot does not add a default datasource.

This has an important consequence: if you only add an extra secondary `DataSource` to the application and expect Boot to continue creating the default datasource for the primary database, declaring a custom bean may cause auto-configuration to back off. When you need multiple data sources, define and configure **both** datasources explicitly, and mark the default one with `@Primary`.

Do not use `@Primary` as a substitute for back-off. `@Primary` only helps Spring pick a preferred bean when multiple candidates of the same type exist; it does not prevent Boot from creating the default bean. Back-off and candidate selection are two separate mechanisms.

### 5.1. When to use JNDI?

In an application server capable of managing connection pools, an application can obtain a datasource via JNDI:

~~~properties
spring.datasource.jndi-name=java:jboss/datasources/orders
~~~

The application then references the DataSource registered by the server at that JNDI name. This is an alternative to declaring `spring.datasource.url`, `username`, and `password` to configure a datasource yourself. The JNDI name must exist in the runtime container; running the same configuration in an environment without that resource will fail.

## 6. Minimal JDBC example with Spring Boot

To visualize a standard setup, a Maven application can use:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

File `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 30000
~~~

A bean can receive `JdbcTemplate` without creating a datasource manually:

~~~java
package example.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HealthRepository {

    private final JdbcTemplate jdbcTemplate;

    public HealthRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Integer databaseVersion() {
        return jdbcTemplate.queryForObject(
                "select 1",
                Integer.class);
    }
}
~~~

`JdbcTemplate` is auto-configured by Boot when a suitable `DataSource` and related conditions are met. The repository above runs `select 1` to confirm a simple query; the exact validation SQL query may vary across databases. The example does not require creating a `JdbcTemplate` bean manually.

## 7. Configuring a custom DataSource using DataSourceProperties

When you need to explicitly choose Hikari or another pool, `DataSourceProperties` helps reuse standard connection properties:

**File:** `src/main/java/example/jdbc/CustomDataSourceConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomDataSourceConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource")
    public DataSourceProperties appDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    public HikariDataSource appDataSource(
            DataSourceProperties appDataSourceProperties) {

        return appDataSourceProperties
                .initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Configuration:

~~~yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    configuration:
      maximum-pool-size: 12
      connection-timeout: 30000
~~~

`DataSourceProperties.initializeDataSourceBuilder()` creates a builder from the bound URL, username, password, driver, and type. `.type(HikariDataSource.class)` explicitly selects Hikari; the `.configuration` namespace binds Hikari-specific properties after the builder creates the object.

Because this is a custom datasource, Boot no longer creates a default datasource via the auto-configuration branch. In a complete application, JDBC access beans will use this datasource when there is only one matching candidate.

If the bean is named `appDataSource` instead of `dataSource`, injection by type still works when there is only one bean; if there are multiple candidates, use `@Primary` and `@Qualifier` as shown in the next section.

## 8. Multiple DataSources: Primary and Qualifier

An application may connect to an operational database and a reporting database. Each datasource needs its own prefix, its own `DataSourceProperties`, and its own pool configuration.

**File:** `src/main/java/example/jdbc/MultiDataSourceConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class MultiDataSourceConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.primary")
    DataSourceProperties primaryDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.primary.configuration")
    HikariDataSource primaryDataSource(
            @Qualifier("primaryDataSourceProperties")
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting")
    DataSourceProperties reportingDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting.configuration")
    HikariDataSource reportingDataSource(
            @Qualifier("reportingDataSourceProperties")
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

YAML configuration example:

~~~yaml
app:
  datasource:
    primary:
      url: jdbc:postgresql://localhost:5432/orders
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 16

    reporting:
      url: jdbc:postgresql://localhost:5432/reports
      username: reports_app
      password: ${REPORTS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 6
~~~

How it works:

- `primaryDataSourceProperties` and `primaryDataSource` are both `@Primary`, so other auto-configurations needing a default datasource by type have a preferred candidate.
- `reportingDataSourceProperties` and `reportingDataSource` are retrieved separately using `@Qualifier`.
- Because the application declares DataSources itself, Boot's default datasource auto-configuration yields.
- DAOs/services needing the reporting database must explicitly inject `@Qualifier("reportingDataSource")`.

Injection example:

~~~java
package example.jdbc;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    public ReportingRepository(
            @Qualifier("reportingDataSource") DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }
}
~~~

If using JPA with multiple datasources, creating two `DataSource`s is only the first step. Usually you also need an `EntityManagerFactory`, transaction manager, and repository configuration for each database. Do not assume Boot will automatically infer all JPA mappings for every datasource just because multiple beans exist.

## 9. Testing DataSource selection with ApplicationContextRunner

`ApplicationContextRunner` lets you spin up a lightweight context, load `DataSourceAutoConfiguration`, and vary properties/beans to test auto-configuration branches without starting a full web server.

The example below is a complete Java test file for Java 17+, Spring Boot 3.3.x, JUnit Jupiter, AssertJ, `spring-boot-starter-jdbc`, and H2 at test runtime.

**File:** `src/test/java/example/jdbc/DataSourceAutoConfigurationTest.java`

~~~java
package example.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.zaxxer.hikari.HikariDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DataSourceAutoConfiguration.class));

    @Test
    void jdbcUrlCreatesHikariDataSourceAndInfersDriver() {
        runner.withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1",
                "spring.datasource.username=sa",
                "spring.datasource.password=",
                "spring.datasource.hikari.maximum-pool-size=4")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);

                    DataSource dataSource = context.getBean(DataSource.class);
                    assertThat(dataSource).isInstanceOf(HikariDataSource.class);
                    assertThat(((HikariDataSource) dataSource)
                            .getMaximumPoolSize()).isEqualTo(4);

                    try (var connection = dataSource.getConnection()) {
                        assertThat(connection.isValid(1)).isTrue();
                    }
                });
    }

    @Test
    void missingUrlUsesEmbeddedH2WhenAvailable() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context.getBean(DataSource.class))
                    .isInstanceOf(EmbeddedDatabase.class);
        });
    }

    @Test
    void userDataSourceMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("customDataSource");
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(EmbeddedDatabase.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource customDataSource() {
            return new EmbeddedDatabaseBuilder()
                    .setType(EmbeddedDatabaseType.H2)
                    .generateUniqueName(true)
                    .build();
        }
    }
}
~~~

**Required test dependencies:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Run:

~~~bash
mvn -Dtest=DataSourceAutoConfigurationTest test
# Or Gradle wrapper on Linux/macOS:
./gradlew test --tests example.jdbc.DataSourceAutoConfigurationTest
~~~

**Expected result:** 3 tests PASS when the dependencies above are configured properly:

1. H2 JDBC URL present: Boot creates HikariDataSource, driver is inferred from URL, and the pool receives `maximum-pool-size=4`; connection validity check returns `true`.
2. Missing URL: H2 is present in test runtime so Boot can choose the embedded database.
3. `customDataSource` bean present: auto-configuration does not create an additional default datasource.

There is no fixed stdout because the tests use assertions. The first test actually opens a connection to in-memory H2; the remaining two tests check bean types and back-off. To test real PostgreSQL/MySQL, use Testcontainers or a dedicated test database environment instead of assuming H2 fully replicates production server behavior.

## 10. Diagnosing common connection errors

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Failed to determine a suitable driver class` | No suitable URL/embedded database or driver could not be loaded | Verify `spring.datasource.url`, runtime driver dependency, and `spring.datasource.driver-class-name` |
| `No suitable driver` | Malformed JDBC URL or driver not on classpath | Cross-check URL against vendor format and runtime dependency tree |
| `Connection refused` | Wrong host/port, database not running, firewall, or network policy | Check DNS, TCP port, container/service, and network route |
| `Unknown database` or database not found | Database/service name in URL does not exist or access is not allowed | Check database name and server configuration |
| `Access denied` / authentication failure | Wrong username/password or user lacks privileges | Check the secret injected into the process and database permissions |
| Timeout acquiring connection | Pool exhausted, queries holding connections too long, slow or unreachable database | Distinguish pool acquisition timeout from network/connect timeout; inspect pool metrics and logs |
| Hikari ignores URL during custom binding | Binding `url` directly onto `HikariDataSource` | Use `jdbc-url` or `DataSourceProperties.initializeDataSourceBuilder()` |
| `NoUniqueBeanDefinitionException` | Multiple `DataSource`s of the same type with no clear candidate | Mark one bean `@Primary` and use `@Qualifier` where secondary datasources are needed |

### 10.1. Check in order

1. **Were properties actually loaded?** Identify active profiles, config imports, environment variables, and command-line args; higher-priority sources can override `application.yml`.
2. **Is the URL valid for vendor/host/port/database?** Try testing connectivity from the same environment/container where the application runs.
3. **Is the driver on the runtime classpath?** Dependencies only in compile/test scope may be absent from the executable artifact.
4. **Which pool implementation was selected?** Check `spring.datasource.type` and present pool libraries; do not guess from the IDE if the runtime artifact differs.
5. **Is a user DataSource bean causing auto-config to back off?** Inspect `@Configuration`, `@Bean`, profiles, and conditions of custom configurations.
6. **Is the failure at connection acquisition or SQL execution?** Open a minimal connection first, then check queries, schema, and permissions.

Actuator can help observe configuration and health when configured appropriately, though sensitive details or connection info should not be exposed publicly. Do not log passwords or URLs containing credentials.

## 11. Distinguishing JDBC DataSource and R2DBC ConnectionFactory

`DataSource` belongs to JDBC and uses a blocking database access model. R2DBC uses `io.r2dbc.spi.ConnectionFactory` for reactive access. The two types cannot directly substitute for one another:

| Aspect | JDBC | R2DBC |
| --- | --- | --- |
| Connection API | `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| Common property prefix | `spring.datasource.*` | `spring.r2dbc.*` |
| Access model | Blocking | Reactive |
| Commonly used template | `JdbcTemplate` / `JdbcClient` | `DatabaseClient` |
| Driver | JDBC driver | R2DBC driver |

If an application uses R2DBC, do not configure `spring.datasource.url` expecting it to create reactive connections. Likewise, adding the JDBC starter does not turn JDBC code into non-blocking code. Choose the stack based on actual concurrency, transaction, driver, and data-access library requirements.

## 12. Design mistakes to avoid

- **Leaving H2 on the production runtime classpath without declaring a URL:** Boot may pick the embedded database instead of the intended database.
- **Declaring an outdated `driver-class-name`:** The URL may be valid while the driver class no longer exists in the dependency version in use.
- **Using `spring.datasource.hikari.*` when the pool is not Hikari:** those properties do not configure another pool.
- **Binding `url` directly onto HikariDataSource:** Hikari uses `jdbc-url`; use `DataSourceProperties` to keep the common property name.
- **Adding a second DataSource and expecting Boot to keep the default DataSource:** a user DataSource causes auto-configuration to yield; define both datasources explicitly.
- **Forgetting `@Primary`:** many downstream auto-configurations require one datasource candidate by type and may fail if no preferred candidate is identified.
- **Using `@Primary` instead of `@Qualifier`:** `@Primary` only selects the default; code accessing a secondary database should specify a qualifier to avoid hitting the wrong database.
- **Tuning the pool by arbitrarily increasing connection counts:** total connections across all instances can exceed the database's limit.
- **Storing credentials in Git:** use a secret manager, environment variables, or an appropriate secret management system.
- **Using JDBC `DataSource` in reactive code expecting non-blocking behavior:** JDBC remains blocking, even when called from a WebFlux application.

## 13. Knowledge self-check

1. `spring.datasource.url` is not declared, but H2 is on the classpath. What can Boot do?  
   **Answer:** Attempt to auto-configure embedded H2; classpath conditions and embedded database selection determine the exact branch.

2. `spring-boot-starter-jdbc` is present and HikariCP is on the classpath. What is the default pool usually?  
   **Answer:** HikariCP, because Boot prioritizes Hikari in its pool selection algorithm.

3. Can `spring.datasource.driver-class-name` always be omitted?  
   **Answer:** Usually yes when the driver can be inferred from the JDBC URL and the driver jar is present. If inference fails or a specific class is needed, declare it explicitly.

4. Why is `DataSourceProperties` useful when creating a HikariDataSource yourself?  
   **Answer:** It handles common properties like `url` and maps them appropriately to Hikari's `jdbcUrl` via `initializeDataSourceBuilder()`.

5. The application declares its own `DataSource` bean. What happens to the default datasource?  
   **Answer:** DataSource auto-configuration yields; the bean declared by the application is used.

6. When there are two DataSources, how do `@Primary` and `@Qualifier` differ?  
   **Answer:** `@Primary` identifies the default candidate by type; `@Qualifier` selects the exact bean to use at an injection point.

7. Why is checking the `DataSource` bean not enough to prove a production database is usable?  
   **Answer:** You must open a connection and verify the network, credentials, database, permissions, and actual queries/schema.

## Official documentation

- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): embedded databases, `spring.datasource.*`, driver inference, pool priority, `spring.datasource.type`, JNDI, and JDBC templates.
- [Spring Boot 3.3 — Configure a Custom DataSource](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html#howto.data-access.configure-custom-datasource): `DataSourceBuilder`, Hikari `jdbc-url`, `DataSourceProperties`, and `initializeDataSourceBuilder()`.
- [Spring Boot 3.3 — Configure Two DataSources](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html#howto.data-access.configure-two-datasources): `@Primary`, `@Qualifier`, two sets of `DataSourceProperties`, and pool configuration.
- [Spring Boot 3.3 API — DataSourceProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html): standard connection properties and builder initialization.
- [Spring Boot 3.3 API — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html): datasource auto-configuration conditions and structure.

**Key takeaway:** Separate three decisions: **which database/URL is connected**, **which pool implementation is chosen**, and **which DataSource bean is the default candidate**. `spring.datasource.*` describes the connection, classpath/`spring.datasource.type` affects the pool, and an application-declared bean can make Boot back off; when multiple sources exist, use `@Primary` for the default and `@Qualifier` for each specific source.
