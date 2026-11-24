# User-Provided DataSource Beans and Spring Boot's Back-Off Behavior

## 1. Context: Why can a DataSource bean stop Boot from creating the default bean?

In a Spring Boot application using JDBC, `DataSource` is the standard entry point for obtaining database connections. Normally, an application only needs to declare:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=change-me
```

Spring Boot reads the configuration, selects a connection pool on the classpath (typically HikariCP), and registers a `DataSource` bean for JDBC components, transactions, SQL initialization, or JPA to use.

When full control is needed, the application can declare a `DataSource` bean itself. This is an extension point supported by Spring Boot. Auto-configuration will **back off** for the application-provided bean if that bean satisfies the type condition checked by auto-configuration.

Example:

```java
@Configuration(proxyBeanMethods = false)
class DatabaseConfiguration {

    @Bean
    DataSource customDataSource() {
        // Create an application-managed DataSource.
        // Concrete example in section 6.
    }
}
```

When this bean is recognized as a valid `DataSource`, Spring Boot does not create the default `DataSource` bean from the embedded/pooling branches. Subsequent JDBC configurations can still use the bean provided by the application.

**Two things must be distinguished:**

- **Back-off of the default DataSource bean:** Boot skips creating the default pooled/embedded datasource because the application already provided a datasource.
- **Other JDBC auto-configurations:** components such as `JdbcTemplate`, database initialization, or the transaction manager can still be configured based on the existing datasource, if their own conditions are satisfied.

Therefore, a user-provided `DataSource` bean does not mean the entire Spring Boot JDBC ecosystem is disabled.

## 2. How does the back-off mechanism work?

Spring Boot uses `@ConditionalOnMissingBean` to allow applications to replace a default bean. For datasources, the embedded and pooled datasource configurations are only applied when no matching datasource exists in the context yet.

You can picture it as:

```text
Classpath has JDBC + Spring JDBC
             |
             v
     DataSourceAutoConfiguration
             |
             +--> Register DataSourceProperties
             |
             v
  DataSource / XADataSource bean exists?
          /                 \
        Yes                  No
        |                     |
        v                     v
  Skip default          Check URL, embedded DB,
  DataSource creation   connection pool, and driver
        |                     |
        v                     v
  Use user-provided     Create default DataSource
  bean                         |
        |                     |
        +----------+----------+
                   |
                   v
     JdbcTemplate / SQL init / transaction
       can use the matching DataSource
```

This is a conceptual model. In practice, `DataSourceAutoConfiguration` also has classpath conditions, R2DBC-related conditions, the embedded branch, and the pooled branch. Each supporting auto-configuration such as `JdbcTemplateAutoConfiguration` also has its own conditions.

### 2.1. Conditions are evaluated on bean definitions

`@ConditionalOnMissingBean(DataSource.class)` inspects bean metadata that Spring already knows at the time the condition is evaluated. Spring Boot recommends placing bean conditions like `@ConditionalOnMissingBean` in **auto-configuration**, because auto-configuration is processed after user-declared bean definitions.

Accordingly, when writing your own starter:

- Use `@ConditionalOnMissingBean(DataSource.class)` on the `@Bean` method that creates the default datasource.
- Place the method in an `@AutoConfiguration` class registered according to Boot's mechanism.
- Declare a clear return type of `DataSource` or a concrete implementation.
- Do not place the condition too early in a regular configuration assuming all application beans have already been registered.

The return type matters greatly. For instance, `@Bean Object customDataSource()` can hide type information from condition evaluation before the method is invoked. Declare `@Bean DataSource customDataSource()` or `@Bean HikariDataSource customDataSource()`.

### 2.2. A bean with the same name is not always enough

The back-off mechanism primarily relies on the **bean type** required by the condition. Merely naming a bean `dataSource` while returning an object that does not implement `DataSource` does not create a replacement datasource.

Conversely, a bean named `customDataSource` can still make the default datasource back off if its bean type is `DataSource` and it is a candidate considered by the condition.

Do not enable `spring.main.allow-bean-definition-overriding=true` just to override the default bean by name. Use the type-based back-off contract and conditions designed for that purpose.

## 3. Spring Boot's default configuration when no replacement bean exists

If the application does not provide a `DataSource` itself, Spring Boot can create a datasource from `spring.datasource.*`.

Example:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
    username: sa
    password:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

Common values:

- `spring.datasource.url`: JDBC URL.
- `spring.datasource.username` and `spring.datasource.password`: login credentials.
- `spring.datasource.driver-class-name`: driver name if Boot cannot infer it from the URL or needs explicit specification.
- `spring.datasource.type`: force a specific datasource/pool class.
- `spring.datasource.hikari.*`: HikariCP-specific settings.
- `spring.datasource.tomcat.*`, `spring.datasource.dbcp2.*`, or corresponding prefixes: configuration for other pool implementations if dependencies are present.

Spring Boot prioritizes connection pools in the order described in documentation: HikariCP, Tomcat JDBC pool, Commons DBCP2, and Oracle UCP. When using `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa`, HikariCP is usually already on the classpath.

If there is no URL but a suitable embedded database is on the classpath, Boot can auto-configure the embedded database. If you need to disable the embedded branch, you can set `spring.datasource.embedded-database-connection=none`.

### 3.1. DataSourceProperties remains part of auto-configuration

`DataSourceAutoConfiguration` enables `DataSourceProperties` to hold standard settings. When the user provides a datasource and the default datasource creation branch backs off, you should not assume every supporting properties bean has disappeared.

However, **a custom datasource bean does not automatically receive every `spring.datasource.*` setting** merely because `DataSourceProperties` exists. If your factory does not read the properties or the datasource is not bound with `@ConfigurationProperties`, those values are not automatically applied to the object you create.

## 4. When the user defines a DataSource themselves

### 4.1. Creating a DataSource bean manually

The following example uses Spring Framework's `DriverManagerDataSource` to illustrate an application-provided datasource:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
class CustomDataSourceConfiguration {

    @Bean
    DataSource customDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:custom;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
```

`DriverManagerDataSource` is not a connection pool; every time a connection is requested, it opens a new JDBC connection. It is a simple implementation for tests or demos, not the default choice for production load.

When the context contains this bean:

- Boot's default datasource creation branch backs off.
- `JdbcTemplate` can be auto-configured and use the `customDataSource` bean.
- Components needing a datasource can receive this bean via dependency injection.
- `spring.datasource.url` settings do not automatically override the hardcoded URL in the method above.

### 4.2. Boot still reuses the user's datasource

Spring Boot documentation confirms that an application-provided datasource is reused wherever Boot needs one, including database initialization. This allows you to change how connections are created while still leveraging Boot's other JDBC components.

For example, if the application uses `JdbcTemplate`:

```java
@Repository
class ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Integer countProducts() {
        return jdbcTemplate.queryForObject(
                "select count(*) from products",
                Integer.class
        );
    }
}
```

`JdbcTemplate` receives the matching datasource from the context. The repository does not need to know whether the datasource is Hikari, a JNDI datasource, or a custom application-created datasource.

Note: the repository example assumes the `products` table already exists; the snippet only illustrates injecting and using `JdbcTemplate`, not schema creation.

### 4.3. Binding external configuration to a custom datasource

If you want your custom datasource to still be configured from a YAML file, you can use `@ConfigurationProperties` on the bean or use `DataSourceProperties` to build the pool.

With HikariCP, a clean configuration approach is:

```java
import com.zaxxer.hikari.HikariDataSource;

import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
class CustomPoolConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource")
    DataSourceProperties dataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    HikariDataSource customDataSource(
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
```

Corresponding configuration:

```yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/catalog
    username: catalog_app
    password: change-me
    configuration:
      maximum-pool-size: 20
      connection-timeout: 30000
```

`DataSourceProperties.initializeDataSourceBuilder()` transfers standard values into the builder. This is important because Hikari uses the `jdbcUrl` property, while general datasource configuration uses `url`. If binding directly onto `HikariDataSource`, you typically have to use `jdbc-url` instead of `url`.

This is an application-controlled datasource configuration; because a `DataSource` bean is already provided, Boot does not create an additional default datasource. `@Primary` on `DataSourceProperties` in the example keeps this properties bean as the default candidate when multiple beans of the same type exist.

## 5. Distinguishing a replacement DataSource from an additional DataSource

This is the easiest point to get confused about when an application needs multiple databases.

### 5.1. A user-provided datasource to replace the default

If the application defines a single regular `DataSource` bean, Boot recognizes that datasource and yields creating the default bean.

```java
@Bean
DataSource customDataSource() {
    // ...
}
```

Result: the application only has the user-created datasource (along with supporting beans if configured). This is the right behavior when you want to completely replace the default datasource.

### 5.2. Adding a second datasource while keeping the default datasource

If you need a Boot-configured primary database and want to add a reporting database, declaring a second regular `DataSource` bean can cause default datasource auto-configuration to back off. To mark the secondary datasource as **not a default candidate**, Spring Framework 6.2 provides the `defaultCandidate` attribute on `@Bean`.

Example based on Spring Boot 3.5:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.zaxxer.hikari.HikariDataSource;

@Configuration(proxyBeanMethods = false)
class ReportingDataSourceConfiguration {

    @Bean(defaultCandidate = false)
    @Qualifier("reporting")
    HikariDataSource reportingDataSource() {
        return DataSourceBuilder.create()
                .type(HikariDataSource.class)
                .url("jdbc:h2:mem:reporting;DB_CLOSE_DELAY=-1")
                .username("sa")
                .build();
    }
}
```

In this case:

- Boot's default datasource can still be created from `spring.datasource.*`.
- `reportingDataSource` still exists and can be injected when specifying `@Qualifier("reporting")`.
- The secondary bean does not intrude into injection points requesting only the default `DataSource` type.
- Services needing the reporting database must specify the qualifier explicitly.

Example:

```java
@Repository
class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportingRepository(
            @Qualifier("reporting") DataSource reportingDataSource) {
        this.jdbcTemplate = new JdbcTemplate(reportingDataSource);
    }
}
```

`defaultCandidate=false` is supported from Spring Framework 6.2 onward, and is therefore available in the Spring Boot 3.5 line. It differs from `autowireCandidate=false`:

| Attribute | Injection without qualifier | Injection with qualifier |
| --- | --- | --- |
| Default | Can be considered | Can be considered |
| `defaultCandidate=false` | Not a default candidate | Can still be injected when qualifier matches |
| `autowireCandidate=false` | Not considered | Also not injected by type |

This is why you should not mechanically substitute `autowireCandidate=false` for a secondary datasource: the datasource still needs to be injectable where a qualifier is present.

### 5.3. Roles of @Primary and @Qualifier

- `@Primary` selects the preferred bean when multiple matching candidates exist for an unqualified injection.
- `@Qualifier` specifies the exact bean to inject.
- `@ConditionalOnMissingBean` decides whether auto-configuration creates a default bean.
- `defaultCandidate=false` marks an additional bean as not participating as a default candidate; in the second-datasource case, it prevents Boot's default datasource from backing off.

`@Primary` **does not replace** `@ConditionalOnMissingBean`. If you declare two regular datasources, marking one bean primary does not mean Boot will ignore the second datasource when evaluating conditions. If you want to keep the auto-configured datasource and add a secondary datasource, use the `defaultCandidate=false` + `@Qualifier` pattern described in the documentation.

## 6. Runnable example: verifying back-off with Java 17 and Spring Boot 3.5

The following example tests three cases:

1. No user-provided DataSource bean: Boot creates a Hikari datasource.
2. One user-provided DataSource bean: Boot's default datasource backs off, and JdbcTemplate uses the user's datasource.
3. One additional datasource marked `defaultCandidate=false`: Boot's default datasource is still created and the secondary datasource can be injected by qualifier.

The example uses in-memory H2 so no external database is needed. The tests execute `SELECT 1` to confirm connections actually work.

### Directory structure

```text
datasource-backoff-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── DataSourceBackoffTest.java
```

### File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>datasource-backoff-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### File src/test/java/example/DataSourceBackoffTest.java

```java
package example;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceBackoffTest {

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource customDataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();

            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                    "jdbc:h2:mem:userdb;DB_CLOSE_DELAY=-1"
            );
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            return dataSource;
        }
    }

    record ReportingProbe(JdbcTemplate jdbcTemplate) {}

    @Configuration(proxyBeanMethods = false)
    static class AdditionalDataSourceConfiguration {

        @Bean(defaultCandidate = false)
        @Qualifier("reporting")
        DataSource reportingDataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();

            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                    "jdbc:h2:mem:reporting;DB_CLOSE_DELAY=-1"
            );
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            return dataSource;
        }

        @Bean
        ReportingProbe reportingProbe(
                @Qualifier("reporting") DataSource dataSource) {
            return new ReportingProbe(new JdbcTemplate(dataSource));
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class,
                                    JdbcTemplateAutoConfiguration.class
                            )
                    );

    @Test
    void bootCreatesDefaultPooledDataSourceWhenNoUserBeanExists() {
        runner.withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:bootdb;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(HikariDataSource.class);

                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    Integer result = context.getBean(JdbcTemplate.class)
                            .queryForObject("SELECT 1", Integer.class);

                    assertThat(result).isEqualTo(1);
                });
    }

    @Test
    void userDataSourceMakesBootDefaultBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:ignored;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("customDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");

                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(DriverManagerDataSource.class);

                    // Properties bean is still registered.
                    assertThat(context)
                            .hasSingleBean(DataSourceProperties.class);

                    // JdbcTemplate uses the user-provided DataSource.
                    Integer result = context.getBean(JdbcTemplate.class)
                            .queryForObject("SELECT 1", Integer.class);

                    assertThat(result).isEqualTo(1);
                });
    }

    @Test
    void additionalNonDefaultCandidateKeepsBootDataSource() {
        runner.withUserConfiguration(AdditionalDataSourceConfiguration.class)
                .withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:primarydb;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasBean("dataSource");
                    assertThat(context).hasBean("reportingDataSource");
                    assertThat(context.getBeansOfType(DataSource.class))
                            .hasSize(2);

                    // Boot's default DataSource remains the default candidate.
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(HikariDataSource.class);

                    Integer primaryResult =
                            context.getBean(JdbcTemplate.class)
                                    .queryForObject("SELECT 1", Integer.class);

                    Integer reportingResult =
                            context.getBean(ReportingProbe.class)
                                    .jdbcTemplate()
                                    .queryForObject("SELECT 1", Integer.class);

                    assertThat(primaryResult).isEqualTo(1);
                    assertThat(reportingResult).isEqualTo(1);
                });
    }
}
```

### Running the program

In the directory containing `pom.xml`, use JDK 17+ and Maven:

```bash
java -version
mvn -version
mvn test
```

**Expected result:** three JUnit tests pass, and Maven finishes with `BUILD SUCCESS` if dependencies download successfully. There is no fixed business stdout because the tests use assertions and do not call `System.out.println`. Surefire reports are placed in `target/surefire-reports`.

Explanation of each test:

- **`bootCreatesDefaultPooledDataSourceWhenNoUserBeanExists`:** with no user bean, Boot creates a Hikari datasource from `spring.datasource.url`; `JdbcTemplate` executes the query successfully.
- **`userDataSourceMakesBootDefaultBackOff`:** with `customDataSource` present, Boot does not create the default bean named `dataSource`. `DataSourceProperties` still exists; `JdbcTemplate` uses the user-provided datasource. Boot's URL property is ignored for the custom bean because the factory does not bind it.
- **`additionalNonDefaultCandidateKeepsBootDataSource`:** the reporting datasource is marked `defaultCandidate=false` with qualifier `reporting`. Boot still creates the default datasource; the secondary bean is used via `@Qualifier("reporting")`.

The third example requires Spring Framework 6.2 or newer; Spring Boot 3.5 manages the compatible Framework version. If your project is on Boot 3.3 or an older Framework, do not copy the `defaultCandidate` attribute without checking whether the API exists; upgrade the version or design multi-datasource according to the mechanism appropriate for that version.

## 7. Effects on JDBC, transactions, and database initialization

### 7.1. JdbcTemplate

`JdbcTemplateAutoConfiguration` can create a `JdbcTemplate` based on the matching datasource in the context. When there is only one datasource, replacing the bean usually requires no changes to repository code.

When there are multiple datasources, an injection point declaring only `DataSource` can become ambiguous. Use `@Primary` for the main datasource or `@Qualifier` at the injection point to pick the data source explicitly. For an additional datasource that should not alter default selection, consider `defaultCandidate=false`.

### 7.2. SQL initialization

Scripts such as `schema.sql` and `data.sql` can be used by Boot to initialize the database according to the `spring.sql.init.*` policy. Boot reuses the application-provided datasource for database initialization when SQL initialization conditions match.

If a custom datasource points to a different database than intended, scripts may run in the wrong place. Verify the actual URL, profile, and datasource ordering before enabling initialization in an environment holding data.

### 7.3. Transaction manager

Transaction auto-configurations can create a transaction manager based on the existing datasource if their conditions are met. When an application has multiple datasources, decide which transaction manager serves which repository/service and specify appropriate qualifiers when multiple managers exist.

A single datasource does not automatically solve distributed transactions across multiple databases. If a use case needs to write to multiple data sources within one transaction, choose an appropriate transaction architecture (such as XA/JTA when genuinely needed) instead of assuming a default `@Transactional` covers everything.

### 7.4. JPA and other integrations

JPA auto-configuration typically needs a matching datasource candidate to create an `EntityManagerFactory`. When there are multiple datasources, the application may need to explicitly configure `EntityManagerFactory`, transaction manager, and repository packages for each persistence unit. Do not simply add another `DataSource` bean and expect all repositories to pick the right database automatically.

## 8. Choosing when to provide a DataSource yourself

| Need | Option |
| --- | --- |
| Only change URL, username, password, pool size of standard datasource | Use `spring.datasource.*` |
| Choose supported Hikari/Tomcat/DBCP2 | Use `spring.datasource.type` and corresponding properties |
| Obtain datasource from JNDI or application server | Use `spring.datasource.jndi-name` or a suitable JNDI bean |
| Use a custom implementation, wrapper, or datasource proxy | Register a `DataSource` bean yourself |
| Need to configure a separate Hikari pool using a different prefix | `DataSourceProperties` + `initializeDataSourceBuilder()` |
| Need a second database while keeping Boot's datasource | `@Bean(defaultCandidate=false)` + `@Qualifier` |
| Want to completely replace the default datasource | Regular `DataSource` bean; let auto-configuration back off |

Prefer standard properties when you only need to change values. Provide a bean yourself when you need control over the implementation, lifecycle, routing, or how connections are obtained.

## 9. Common mistakes

1. **Declaring a bean with the same name but wrong type.** The condition checks the `DataSource` type, so merely naming a bean `dataSource` is not enough to replace the default datasource.
2. **Declaring too broad a return type.** `@Bean Object customDataSource()` makes it hard for the condition to detect the type before instantiation. Return `DataSource` or a concrete implementation.
3. **Assuming spring.datasource.* automatically configures a custom bean.** If the factory hardcodes the URL or does not bind properties, Boot does not automatically write standard settings onto that object.
4. **Creating two regular datasources and forgetting back-off.** An extra bean can stop Boot's default datasource from being created. If you need a second datasource, use the `defaultCandidate=false` pattern.
5. **Using @Primary to prevent auto-configuration.** `@Primary` only selects the injection candidate; it is not a back-off condition.
6. **Using autowireCandidate=false instead of defaultCandidate=false.** That flag excludes the bean even from qualifier-based injection; unsuitable if the secondary datasource still needs to be injected in some places.
7. **Injecting DataSource without a qualifier when multiple candidates exist.** This can fail with bean ambiguity; specify `@Primary` or `@Qualifier` by design.
8. **Using DriverManagerDataSource for high production load.** It does not pool connections; choose a suitable pool or infrastructure-managed datasource.
9. **Neglecting pool/lifecycle management.** When creating Hikari or another pool yourself, configure limits, timeouts, validation, shutdown, and pool observability per operational needs.
10. **Overlooking SQL initialization.** A custom bean can cause `schema.sql` or `data.sql` to run against an unintended database. Verify which datasource is used.
11. **Mistaking a custom bean for disabling all JDBC auto-configuration.** The default DataSource backs off, while JdbcTemplate, transactions, or database initialization can still operate on the existing datasource.
12. **Evaluating bean conditions too early.** `@ConditionalOnMissingBean` only sees bean definitions that have already been processed. Place replacement conditions inside auto-configuration as recommended by Spring Boot.

## 10. How to diagnose when the datasource behaves unexpectedly

1. Confirm dependencies: are `spring-jdbc`, the database driver, and the needed pool implementation present?
2. Check actual beans: bean names, class types, and number of datasources.
3. Check auto-configuration conditions with `--debug` or Actuator `/actuator/conditions` if the endpoint is enabled.
4. Check final property sources: `spring.datasource.url`, profiles, environment variables, and CLI args.
5. Verify the driver and JDBC URL with a test connection.
6. With multiple datasources, inspect which bean is a default candidate, which has a qualifier, and which is marked primary.
7. Check which datasource `JdbcTemplate`/transaction manager is using; do not infer solely from property names.
8. Inspect pool initialization and SQL initialization logs to confirm the target datasource.

Command to run the condition report:

```bash
java -jar app.jar --debug
```

With Actuator, the conditions endpoint must be exposed via proper configuration. Do not expose sensitive diagnostic endpoints to the public Internet.

## 11. Checklist before replacing the default datasource

- [ ] Bean method returns `DataSource` or a concrete implementation type.
- [ ] Understand clearly which auto-configurations will back off.
- [ ] Have explicit property binding if you do not want to hardcode connection info.
- [ ] Choose an appropriate implementation (pooled vs. simple datasource).
- [ ] Have proper pool limits, timeouts, validation, and shutdown settings.
- [ ] `JdbcTemplate` and transaction manager receive the right datasource.
- [ ] If multiple datasources exist, use `@Primary`/`@Qualifier` clearly.
- [ ] If only adding a secondary datasource while keeping Boot's datasource, use `defaultCandidate=false` and a qualifier per Spring Framework 6.2+.
- [ ] SQL initialization runs against the right database.
- [ ] Test the default branch, user replacement, and additional datasource.
- [ ] Check the condition report when auto-configuration does not match.

## 12. Self-check questions

**Question 1.** An application has a `DataSource customDataSource()` bean. Will Spring Boot also create the default Hikari datasource?  
**Answer:** No, the default datasource creation branch backs off when the user bean is recognized as a valid `DataSource`.

**Question 2.** Can a custom bean named `myDatabase` make the default datasource back off?  
**Answer:** Yes. The condition checks the `DataSource` type; the bean name is not required to be `dataSource`.

**Question 3.** When a custom datasource exists, can `JdbcTemplate` still be auto-configured?  
**Answer:** Yes. `JdbcTemplateAutoConfiguration` has its own conditions and can use the user-provided datasource when a suitable candidate exists.

**Question 4.** Does `@Primary` stop Boot from creating the default datasource?  
**Answer:** No. It resolves injection selection when multiple beans exist; back-off is handled by `@ConditionalOnMissingBean`.

**Question 5.** If you want to add a reporting datasource while keeping Boot's primary datasource, what should you use?  
**Answer:** On Spring Framework 6.2+/Boot 3.5, mark the secondary bean `@Bean(defaultCandidate=false)` and inject it with `@Qualifier`.

**Question 6.** Why does Hikari require `jdbc-url` when bound directly, whereas the `DataSourceProperties` example allows `url`?  
**Answer:** Hikari exposes the `jdbcUrl` property; `DataSourceProperties.initializeDataSourceBuilder()` handles mapping from the standard URL property to the implementation's builder.

**Question 7.** Is manually creating `DriverManagerDataSource` suitable as a production pool?  
**Answer:** No. It does not manage a connection pool; use a connection pool or an infrastructure-managed datasource.

## Official references

- Spring Boot 3.5 Reference — SQL Databases, datasource configuration, connection pools, and JDBC templates: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 How-to — Configure a Custom DataSource, DataSourceProperties, Hikari, and multiple datasources: https://docs.spring.io/spring-boot/3.5/how-to/data-access.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot Reference — Creating Your Own Auto-configuration, bean conditions, and `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Framework 6.2 Reference — Autowiring Collaborators, `defaultCandidate`, and `autowireCandidate`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html

**Key takeaway:** An application-provided `DataSource` bean tells Spring Boot that the application already manages database connections itself, so the default datasource yields. Boot can still use that datasource for JDBC and database initialization. If you need a second datasource while keeping the default datasource, clearly distinguish `@Primary`, `@Qualifier`, and `@Bean(defaultCandidate=false)`.
