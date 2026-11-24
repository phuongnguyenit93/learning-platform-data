# Tracing the Conditions of `DataSourceAutoConfiguration`

Topic: Spring Boot Auto Configuration  
Context: JDBC Example  
Goal: Trace from dependencies and classpath to class-level conditions, the embedded database branch, the connection pool branch, the back-off mechanism, and the effective JDBC configuration. After this lesson, you can read the Condition Evaluation Report to explain why Spring Boot creates or skips a `DataSource`.

## 1. What is `DataSourceAutoConfiguration` responsible for?

`DataSourceAutoConfiguration` is Spring Boot's auto-configuration for a JDBC `DataSource`. `DataSource` is the standard Java abstraction (`javax.sql.DataSource`) used to obtain a JDBC `Connection`. A `DataSource` is usually created from a concrete implementation such as HikariCP, Tomcat JDBC Pool, Apache DBCP2, or an embedded database.

Applications typically only need to add the starter and declare connection settings:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
```

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: ${DB_PASSWORD}
```

When auto-configuration is enabled via `@SpringBootApplication` or `@EnableAutoConfiguration`, Spring Boot evaluates `DataSourceAutoConfiguration`. If the conditions match, it selects a configuration branch and registers a `DataSource` bean. Other JDBC configurations such as `JdbcTemplate`, the transaction manager, or SQL initialization can rely on this bean.

Key point: `DataSourceAutoConfiguration` is not a single method that always creates a pool. It is a configuration with multiple layers of conditions. You must trace each layer to understand why a `DataSource` is created, or why a branch is skipped.

## 2. Read the class-level conditions first

In Spring Boot 3.3.x, the main declaration of `DataSourceAutoConfiguration` has an equivalent structure:

```java
@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
@ConditionalOnClass({
        DataSource.class,
        EmbeddedDatabaseType.class
})
@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
@EnableConfigurationProperties(DataSourceProperties.class)
@Import({
        DataSourcePoolMetadataProvidersConfiguration.class,
        DataSourceCheckpointRestoreConfiguration.class
})
public class DataSourceAutoConfiguration {
    // The embedded and pooled configuration branches are located inside.
}
```

Each annotation answers a distinct question:

| Annotation | Question | Meaning |
| --- | --- | --- |
| `@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)` | Which configuration does this need to come before? | Orders auto-configuration so the JDBC DataSource can be registered before SQL initialization |
| `@ConditionalOnClass(...)` | Are the required APIs on the classpath? | Both `javax.sql.DataSource` and Spring JDBC's `EmbeddedDatabaseType` must be present |
| `@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")` | Is there an R2DBC `ConnectionFactory` bean? | If present, default JDBC auto-configuration yields |
| `@EnableConfigurationProperties(DataSourceProperties.class)` | Is there a JDBC configuration property group? | Registers and binds `spring.datasource` keys into `DataSourceProperties` |
| `@Import(...)` | Which supporting configurations are loaded alongside? | Loads metadata providers and checkpoint/restore support; does not directly imply creating a pool |

### 2.1. The classpath condition

`javax.sql.DataSource` belongs to the Java SQL API. `EmbeddedDatabaseType` belongs to Spring JDBC. If Spring JDBC is missing from the runtime classpath, the class condition is not satisfied and `DataSourceAutoConfiguration` is not applied.

That is why starters matter:

- `spring-boot-starter-jdbc` pulls in Spring JDBC and HikariCP.
- `spring-boot-starter-data-jpa` also brings the required JDBC components into the dependency graph.
- Adding only a JDBC driver while missing the Spring JDBC library may not be enough to enable auto-configuration.

If the report states that `EmbeddedDatabaseType` is missing, check the `spring-jdbc` dependency and the dependency graph before editing `application.yml`.

### 2.2. Why does an R2DBC `ConnectionFactory` make JDBC back off?

The class-level condition checks for the absence of a bean of type `io.r2dbc.spi.ConnectionFactory`. When an R2DBC `ConnectionFactory` is already registered, default JDBC `DataSourceAutoConfiguration` does not participate. This is how Spring Boot avoids automatically bringing blocking JDBC into a reactive application's configuration.

The two APIs are not the same:

| JDBC | R2DBC |
| --- | --- |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| Blocking API | Reactive/non-blocking API |
| Example: `JdbcTemplate` | Example: `DatabaseClient` |

If an application genuinely needs both JDBC and R2DBC, you can explicitly import `DataSourceAutoConfiguration` to enable JDBC. However, you must consider using a blocking API inside a reactive application and manage threads appropriately; do not import it just to force a condition match without understanding the impact.

### 2.3. At which layer is `DataSourceProperties` registered?

When the class-level conditions match, `@EnableConfigurationProperties(DataSourceProperties.class)` registers the configuration object. Common properties include:

- `spring.datasource.url`
- `spring.datasource.username`
- `spring.datasource.password`
- `spring.datasource.driver-class-name`
- `spring.datasource.type`
- `spring.datasource.jndi-name`
- Settings related to embedded databases and XA.

`DataSourceProperties` is responsible for inferring certain values such as URL, driver class, username, and password. For example, Spring Boot can infer the driver from the JDBC URL; if there is no URL but an embedded database is available, it can determine the URL for the embedded database.

The existence of `DataSourceProperties` does not prove that a `DataSource` has been created. That is only the input configuration. The two inner branches decide whether to register a data source bean.

## 3. Two main branches: embedded database and pooled DataSource

`DataSourceAutoConfiguration` has two important nested configurations:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(EmbeddedDatabaseCondition.class)
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
@Import(EmbeddedDataSourceConfiguration.class)
protected static class EmbeddedDatabaseConfiguration {
}

@Configuration(proxyBeanMethods = false)
@Conditional(PooledDataSourceCondition.class)
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
@Import({
        DataSourceConfiguration.Hikari.class,
        DataSourceConfiguration.Tomcat.class,
        DataSourceConfiguration.Dbcp2.class,
        DataSourceConfiguration.OracleUcp.class
})
protected static class PooledDataSourceConfiguration {
}
```

The code above illustrates the structure and key conditions of the Boot 3.3 line; the list of pool classes may vary by version and classpath. Read the API/source for your exact version if you want to rely on a specific implementation.

Both branches check that the application does not already have a `DataSource` or `XADataSource`. However, the conditions for choosing embedded versus pooled differ.

### 3.1. The embedded database branch

Spring Boot can automatically create an embedded database if the corresponding dependency is on the classpath, for example:

- H2.
- HSQLDB.
- Derby (deprecated in newer Spring Boot documentation).

The embedded branch is typically considered when:

1. `spring.datasource.url` is not set to a value with text.
2. There is no supported connection pool, or no explicit pool type configuration causing the pooled branch to take priority.
3. `EmbeddedDatabaseType` is on the classpath.
4. An embedded database is detected on the classpath.

Maven example:

```xml
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

When `spring.datasource.url` is not declared, Spring Boot can choose an in-memory URL for H2 and create an embedded `DataSource`. An in-memory database is suitable for demos/tests, but the data is not persistent after the JVM exits.

### 3.2. The pooled DataSource branch

The pooled branch is considered when a supported pool implementation is on the classpath or the user specifies `spring.datasource.type`.

Spring Boot 3.3 prioritizes common implementations in order:

1. HikariCP.
2. Tomcat JDBC Pool.
3. Apache Commons DBCP2.
4. Oracle UCP when the previous options are absent.

If you use `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa`, HikariCP is usually already included, so Hikari is typically chosen by default.

You can explicitly specify the pool:

```yaml
spring:
  datasource:
    type: com.zaxxer.hikari.HikariDataSource
```

Or use another implementation if the corresponding dependency is present. `spring.datasource.type` is the actual `DataSource` class name; it is not a short name like `hikari`.

### 3.3. Why can the embedded branch be a no-match while a DataSource is still created?

This is one of the most important points when reading the report.

Suppose both H2 and HikariCP are on the classpath, but `spring.datasource.url` is not declared. Spring Boot can:

1. Recognize Hikari as a supported pool.
2. Select the pooled branch because a pool is available.
3. Evaluate the embedded branch as no-match because the pool takes priority.
4. Use `DataSourceProperties` to determine the embedded H2 URL.
5. Create a `HikariDataSource` connecting to in-memory H2.

Therefore, the report may record `EmbeddedDatabaseConfiguration` as a negative match, and `PooledDataSourceConfiguration` as a positive match. That is completely normal; it does not mean Spring Boot failed to create a database.

Do not read a single negative match line in isolation and conclude that the entire `DataSourceAutoConfiguration` failed. You must check both branches and the final bean in the context.

## 4. Back-off condition: when the application declares its own DataSource

Both the embedded and pooled configurations have:

```java
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
```

If the application already defines a `DataSource` or `XADataSource` bean visible to the condition, the default data source creation branches yield.

Example:

```java
@Configuration(proxyBeanMethods = false)
class MyDatabaseConfiguration {

    @Bean
    DataSource dataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/orders")
                .username("app_user")
                .password("secret")
                .build();
    }
}
```

This is an illustrative configuration; in real applications, credentials should be managed via secrets/environment variables rather than hardcoding passwords.

When the user bean is processed before auto-configuration:

- `DataSourceAutoConfiguration` at the class level can still match.
- `DataSourceProperties` can still be registered.
- `EmbeddedDatabaseConfiguration` does not match because a `DataSource` already exists.
- `PooledDataSourceConfiguration` also does not match because a `DataSource` already exists.
- The `dataSource` bean provided by the application is used for subsequent JDBC components.

This differs from `@Primary`. `@Primary` only helps select a candidate when multiple beans exist; `@ConditionalOnMissingBean` is the condition that prevents the fallback bean from being registered.

### 4.1. Why does matching by interface matter?

If a starter checks for the presence of `DataSource.class`, any suitable implementation can cause the fallback to yield. The user does not have to provide specifically a `HikariDataSource`.

Conversely, if code checks for a specific implementation such as `HikariDataSource.class`, a `DriverManagerDataSource` or another pool might not satisfy that condition. When designing your own auto-configuration, choose the condition based on the contract to be replaced, typically the `DataSource` interface, rather than locking onto an implementation without a clear reason.

Also ensure the `@Bean` method declares a sufficiently specific return type so Spring can deduce the bean type when the condition is evaluated. A signature returning `Object` can obscure the necessary type information.

## 5. Tracing the process from dependency to bean

The entire flow can be read in the following order:

```text
@SpringBootApplication / @EnableAutoConfiguration
                   |
                   v
     DataSourceAutoConfiguration candidate?
                   |
          +--------+---------+
          |                  |
       No match      Class-level match
          |                  |
   No JDBC DS created        v
                 Enable DataSourceProperties
                 Import metadata/checkpoint support
                              |
                              v
                 R2DBC ConnectionFactory present?
                    (checked at class level)
                              |
                 if absent, continue
                              |
               DataSource/XADataSource already exists?
                    /                    \
                  Yes                    No
                  |                        |
              Back-off             Evaluate 2 branches
                                           |
                          +----------------+----------------+
                          |                                 |
                 EmbeddedDatabaseCondition        PooledDataSourceCondition
                          |                                 |
             Suitable embedded database?          Suitable pool/type?
                          |                                 |
                 Embedded branch                 Pooled branch
                          |                                 |
                          +----------------+----------------+
                                           |
                              DataSource bean registered
                                           |
                              Bean initialized when needed
                                           |
                              JDBC consumers use it
```

Note that the diagram is a conceptual flow, not the entire internal callback order of Spring. `@AutoConfiguration(before=...)` orders auto-configuration processing; actual bean initialization order also depends on the dependency graph, `@DependsOn`, and lifecycle.

## 6. Properties to know when tracing JDBC

| Property | Effect | Diagnostic question |
| --- | --- | --- |
| `spring.datasource.url` | JDBC URL | Is it a real URL or just an unresolved placeholder? |
| `spring.datasource.username` | Connection account | Is it overridden by another configuration source? |
| `spring.datasource.password` | Password | Is the secret value injected properly? |
| `spring.datasource.driver-class-name` | Specific JDBC driver | Is the driver class on the runtime classpath? |
| `spring.datasource.type` | Select DataSource implementation | Has the class dependency been added? |
| `spring.datasource.jndi-name` | Obtain DataSource from JNDI | Is the JNDI context/name valid and configured accordingly? |
| `spring.datasource.hikari.*` | Hikari-specific properties | Was Hikari actually selected? |
| `spring.datasource.embedded-database-connection` | Select suitable embedded database connection | Which embedded database is selected or disabled? |

### 6.1. URL and driver

PostgreSQL example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: ${DB_PASSWORD}
```

Spring Boot usually infers the driver from the JDBC URL if the corresponding driver is on the classpath. You can declare it explicitly:

```yaml
spring:
  datasource:
    driver-class-name: org.postgresql.Driver
```

If the URL has syntax errors, the driver does not exist, or credentials are wrong, distinguish which errors occur during bean creation and which only appear when obtaining a connection. A pool can be initialized while the actual connection to the database still fails later, depending on configuration and connection validation timing.

### 6.2. Hikari-specific properties

When Hikari is selected, pool-specific properties are bound under:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
```

General properties under `spring.datasource` and specific properties under `spring.datasource.hikari` serve different roles. Do not put `maximum-pool-size` at the `spring.datasource` level and expect Hikari to pick it up; use the correct prefix.

### 6.3. The `jdbc:` URL and the `jdbc-url` property

Hikari has a `jdbcUrl` property, not a `url` property in the same way `DataSourceProperties` exposes it. If you write `@Bean HikariDataSource` yourself and bind it directly with `@ConfigurationProperties`, pay attention to this difference.

When using `DataSourceProperties.initializeDataSourceBuilder()`, Spring Boot translates the common URL to the appropriate property of the implementation. That is one reason to use `DataSourceProperties` in custom DataSource configurations instead of binding a `HikariDataSource` directly to `spring.datasource.url`.

## 7. Condition Evaluation Report for DataSource

To know why Spring Boot selected or skipped a JDBC branch, enable:

```bash
java -jar app.jar --debug
```

Or configure `debug=true`. The Condition Evaluation Report will display positive/negative matches and the message for each source.

Sources worth looking for:

- `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`
- `DataSourceAutoConfiguration.EmbeddedDatabaseConfiguration`
- `DataSourceAutoConfiguration.PooledDataSourceConfiguration`
- Nested configurations of `DataSourceConfiguration` such as Hikari, Tomcat, DBCP2
- Downstream auto-configurations that use `DataSource`, such as transaction manager, `JdbcTemplate`, and SQL initialization.

An illustrative report by meaning:

| Source | Result | What the message may indicate |
| --- | --- | --- |
| `DataSourceAutoConfiguration` | Positive | Required classes are present, no R2DBC ConnectionFactory |
| `EmbeddedDatabaseConfiguration` | Negative | A URL or supported pool is present so the embedded branch is not selected |
| `PooledDataSourceConfiguration` | Positive | A supported pool is on the classpath or type is specified |
| `DataSourceConfiguration.Hikari` | Positive | Hikari is on the classpath and no other DataSource exists |
| `DataSourceConfiguration.Tomcat` | Negative | Hikari was already selected, or Tomcat pool is absent/not the selected type |

The table is an illustrative example; exact messages depend on classpath, properties, and version. In an application using a custom DataSource, both the nested embedded and pooled branches can be no-match due to back-off, while the root `DataSourceAutoConfiguration` remains positive.

### 7.1. Reading the report via API in a context test

Spring Boot provides `ConditionEvaluationReport`:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (source.contains("DataSourceAutoConfiguration")) {
        System.out.println(source + " => "
                + (outcomes.isFullMatch() ? "MATCH" : "NO MATCH"));

        outcomes.forEach(item -> {
            var outcome = item.getOutcome();
            System.out.println("  "
                    + item.getCondition().getClass().getSimpleName()
                    + " | "
                    + (outcome.isMatch() ? "matched" : "did not match")
                    + " | "
                    + outcome.getMessage());
        });
    }
});
```

This is a snippet placed inside a test or component with a `ConfigurableApplicationContext`; it is not a standalone program. The message content is provided by each condition, so you should not rely on exact log strings in production logic.

If Spring Boot Actuator is present and the appropriate endpoint is exposed, `/actuator/conditions` provides positive/negative match results in JSON format. Only expose this endpoint in diagnostic environments and protect access appropriately.

## 8. Runnable practice: Spring Boot 3.3.13 + Java 17 + H2

This practice uses `ApplicationContextRunner` to verify three cases:

1. No URL declared, but H2 is on the classpath: Boot creates a DataSource for the embedded database, typically using Hikari when Hikari is available.
2. Application provides its own DataSource: auto-configuration backs off.
3. URL and Hikari-specific property provided: Boot uses the specified URL and binds the pool configuration.

### 8.1. Project structure

```text
datasource-auto-config-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── DataSourceAutoConfigurationTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>datasource-auto-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-starter-jdbc` provides Spring JDBC and HikariCP; H2 is only needed in test scope because the example does not connect to an external database.

### 8.3. `DataSourceAutoConfigurationTest.java`

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DataSourceAutoConfiguration.class));

    @Test
    void embeddedH2IsUsedWhenNoUrlIsProvided() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DataSource.class);

            DataSource dataSource = context.getBean(DataSource.class);
            assertThat(dataSource).isInstanceOf(HikariDataSource.class);

            try (Connection connection = dataSource.getConnection()) {
                assertThat(connection.getMetaData().getURL())
                        .startsWith("jdbc:h2:mem:");
            }
            catch (SQLException ex) {
                throw new AssertionError("Could not open embedded H2 connection", ex);
            }

            ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(context.getBeanFactory());
            var outcomes = report.getConditionAndOutcomesBySource()
                    .get(DataSourceAutoConfiguration.class.getName());

            assertThat(outcomes).isNotNull();
            assertThat(outcomes.isFullMatch()).isTrue();
        });
    }

    @Test
    void userDefinedDataSourceMakesDefaultConfigurationBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("userDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");

                    DataSource dataSource = context.getBean(DataSource.class);
                    assertThat(dataSource)
                            .isInstanceOf(DriverManagerDataSource.class);
                });
    }

    @Test
    void explicitUrlAndHikariSettingsAreApplied() {
        runner.withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:configured;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.hikari.maximum-pool-size=4")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);

                    HikariDataSource dataSource =
                            context.getBean(HikariDataSource.class);

                    assertThat(dataSource.getJdbcUrl())
                            .startsWith("jdbc:h2:mem:configured");
                    assertThat(dataSource.getMaximumPoolSize()).isEqualTo(4);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource userDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:userdb;DB_CLOSE_DELAY=-1",
                    "sa",
                    "");
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

Expected output: all three tests pass; Maven Surefire typically prints:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

There is no custom stdout. The first test opens a real connection to in-memory H2 and checks the JDBC URL; the second test verifies back-off with a custom bean; the third test verifies the URL and Hikari maximum pool size.

`ApplicationContextRunner` does not boot a complete production application. It creates a lightweight context with a defined classpath, properties, and user configuration, suitable for isolating auto-configuration conditions.

## 9. Misleading report scenarios

### 9.1. `DataSourceAutoConfiguration` does not appear

If the source is missing from the report, check:

- Whether `spring-boot-starter-jdbc` or an equivalent starter is in the runtime dependency graph.
- Whether `spring-jdbc` is actually present.
- Whether `DataSourceAutoConfiguration` was excluded via `@SpringBootApplication(exclude=...)` or `spring.autoconfigure.exclude`.
- Whether a dependency version mismatch caused the artifact to contain different classes than expected.
- Whether the application enables `@EnableAutoConfiguration` or `@SpringBootApplication`.

Not seeing the source does not mean a negative match; the auto-configuration may not have been a candidate or may have been excluded from the list.

### 9.2. Embedded no-match, pooled positive

This is usually the case when a pool takes priority. Check `PooledDataSourceConfiguration` and the final bean type. If the actual `DataSource` is `HikariDataSource`, the embedded branch being no-match makes sense.

### 9.3. Both embedded and pooled are no-match

Several possibilities:

- An application-provided `DataSource` or `XADataSource` exists, causing both branches to back off.
- No suitable embedded database and no supported pool are present.
- `spring.datasource.url` is declared, but no suitable pool/type is on the classpath.
- There is a classpath-level error or another condition excluding the configuration branch.

Read the specific message of each nested configuration before editing properties.

### 9.4. `DataSource` bean is present, but getting a connection fails

This differs from a condition no-match. The bean may already be registered and initialized, yet a connection cannot be opened due to:

- Missing or incompatible driver.
- Wrong URL/port/hostname.
- Database not ready.
- Incorrect username/password.
- TLS, network policy, or firewall.
- Pool connection exhaustion or timeout.

At this point, inspect the `getConnection()` exception, pool logs, and network/database; stop modifying conditions if the report shows DataSource matched.

### 9.5. R2DBC is present, but JDBC is needed

If the report indicates JDBC configuration backed off because of `ConnectionFactory`, determine whether the application truly needs both stacks. You can explicitly import `DataSourceAutoConfiguration` to keep JDBC, but consider the blocking API and separate transaction configuration. Do not delete the R2DBC bean just to make the JDBC condition match if the application still needs reactive database access.

## 10. When to disable or replace DataSource auto-configuration?

If the application manages its DataSource entirely on its own, simply declaring the appropriate bean lets the default branch back off automatically. It is not always necessary to exclude `DataSourceAutoConfiguration` altogether.

When you want to disable this entire auto-configuration, you can use:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class Application {
}
```

Or configure:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Only exclude it once you understand which auto-configurations depending on `DataSource` will be affected. For instance, `JdbcTemplate`, the JDBC transaction manager, and SQL initialization may no longer be created by default. Excluding does not automatically provide a replacement DataSource.

## 11. Concise diagnostic workflow

When `DataSource` does not appear as expected:

1. Check candidate: Is `DataSourceAutoConfiguration` loaded? Is it excluded?
2. Check class condition: Are `DataSource` and `EmbeddedDatabaseType` on the classpath?
3. Check R2DBC: Is there a `ConnectionFactory` bean causing JDBC auto-configuration to back off?
4. Check user bean: Does a `DataSource`/`XADataSource` already exist causing the nested branches to yield?
5. Check embedded/pool branch: Is URL set, is an embedded DB on the classpath, which pools are supported, is `spring.datasource.type` valid?
6. Check driver and URL: Is the driver on the runtime classpath, is the URL valid, are credentials valid?
7. Check pool-specific settings: Does the `spring.datasource.hikari` prefix match the selected pool?
8. If the bean exists but connection fails: switch to diagnosing database/network/credentials/pool instead of conditions.

Always confirm the final result by listing the `DataSource` bean, checking the concrete implementation, opening a connection in an appropriate test environment, and reading the condition report.

## 12. Self-check questions

**Question 1.** Why does `DataSourceAutoConfiguration` have `@ConditionalOnClass(EmbeddedDatabaseType.class)`?  
**Answer:** Spring Boot needs the Spring JDBC embedded database API on the classpath for this configuration branch to function. Without the required class, the root configuration does not match.

**Question 2.** H2 and Hikari are on the classpath, and no URL is declared. Why can the report show the embedded branch as no-match?  
**Answer:** Boot prioritizes supported pools; Hikari is created and can use the embedded H2 URL inferred from `DataSourceProperties`.

**Question 3.** The application already has `@Bean DataSource`. Does the root `DataSourceAutoConfiguration` necessarily have to no-match?  
**Answer:** No. The root class-level condition checks the classpath and R2DBC `ConnectionFactory`; the nested DataSource-producing configurations check for missing `DataSource`/`XADataSource` and back off.

**Question 4.** When an R2DBC `ConnectionFactory` is already present, how does default JDBC auto-configuration behave?  
**Answer:** It backs off at the class-level condition. If both are intentionally needed, JDBC auto-configuration can be imported explicitly while evaluating the impact of blocking JDBC.

**Question 5.** A Hikari bean appears, but `getConnection()` fails. Can we conclude `DataSourceAutoConfiguration` is a no-match?  
**Answer:** No. The bean has been registered; the error may lie in the driver, URL, database, credentials, network, or pool.

**Question 6.** To check why Hikari was chosen over the embedded configuration, what should you inspect?  
**Answer:** The Condition Evaluation Report for `EmbeddedDatabaseConfiguration`, `PooledDataSourceConfiguration`, and nested `DataSourceConfiguration.Hikari`, then verify the actual bean.

## 13. Key takeaways

- `DataSourceAutoConfiguration` has class-level conditions and two main branches: embedded and pooled.
- `@ConditionalOnClass` checks required APIs; `@ConditionalOnMissingBean(type=ConnectionFactory)` makes default JDBC yield when R2DBC is present.
- `DataSourceProperties` provides input configuration; it does not by itself prove a DataSource bean was created.
- The embedded branch can be no-match while the pooled branch matches; a single negative match does not tell the whole story.
- Pool selection depends on `spring.datasource.type` and the pools on the classpath; Hikari is usually preferred when available.
- A user `DataSource` or `XADataSource` causes the default branches to back off.
- A bean existing but failing to connect is a runtime/driver/network/credential issue, distinct from an unmatched condition.
- Use `--debug`, `/actuator/conditions`, and `ApplicationContextRunner` to verify each branch rather than guessing from a single log line.

### Official references

- [Spring Boot 3.3 API — `DataSourceAutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html)
- [Spring Boot 3.3 — SQL Databases and DataSource Configuration](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)
- [Spring Boot 3.3 — Data Access How-to](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html)
- [Spring Boot 3.3 API — `DataSourceBuilder`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/jdbc/DataSourceBuilder.html)
- [Spring Boot 3.3 API — `DataSourceProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReport`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
