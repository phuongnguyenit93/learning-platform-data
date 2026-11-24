# Multiple DataSources, Primary Candidates, and `JdbcTemplateAutoConfiguration` Conditions

## Learning Objectives

In a Spring Boot application using JDBC, having a single `DataSource` usually makes `JdbcTemplate` creation automatic. However, when an application has multiple databases — for example, a transactional database and a reporting database — Spring must know **which DataSource is the default candidate** so a dependency of type `DataSource` can be injected without ambiguity.

This lesson traces how `JdbcTemplateAutoConfiguration` decides whether to apply, focusing on `@ConditionalOnSingleCandidate(DataSource.class)`, `@Primary`, `@Import`ed configurations, and back-off conditions when users declare JDBC beans themselves.

After this lesson, you can:

- Explain why a single `DataSource` is usually enough to auto-configure `JdbcTemplate`.
- Predict the outcome when there are two `DataSource`s without `@Primary`, with exactly one `@Primary`, or with multiple beans marked `@Primary`.
- Distinguish `@Primary` from `@Qualifier` and understand the limits of each annotation.
- Read the conditions and nested configurations imported by `JdbcTemplateAutoConfiguration`.
- Know when default `JdbcTemplate` is created, when default configuration backs off, and how to declare templates explicitly per database.
- Verify the branches with `ApplicationContextRunner` without connecting to a real database.

## 1. From DataSource to JdbcTemplate

`DataSource` is the JDBC abstraction used to obtain database connections. Spring JDBC's `JdbcTemplate` takes a `DataSource` and provides an API for SQL operations, JDBC resource lifecycle management, and translating JDBC errors into Spring's exception hierarchy.

A simple application usually has just one `DataSource`:

~~~java
@Bean
DataSource dataSource() {
    // Application's pool/connection configuration
}
~~~

When JDBC libraries need a `DataSource`, type-based injection with a single candidate is unambiguous. Spring Boot can auto-configure `JdbcTemplate` based on that DataSource.

With two databases, however:

- `ordersDataSource`: transactional database.
- `reportingDataSource`: reporting database.

A method taking `DataSource` without a qualifier would not know which bean to pick. Spring Boot cannot guess which business database the application intends to use. That is why the **single candidate** condition exists.

## 2. What does JdbcTemplateAutoConfiguration check?

In Spring Boot 3.3, the `org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration` class has the following primary annotation structure:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass({
        DataSource.class,
        JdbcTemplate.class
})
@ConditionalOnSingleCandidate(DataSource.class)
@EnableConfigurationProperties(JdbcProperties.class)
@Import({
        DatabaseInitializationDependencyConfigurer.class,
        JdbcTemplateConfiguration.class,
        NamedParameterJdbcTemplateConfiguration.class
})
public class JdbcTemplateAutoConfiguration {
}
~~~

This is a **structural excerpt for reading the source**, not a class users need to declare themselves. The nested configuration classes are provided by Spring Boot in the auto-configuration package.

There are five key points to recognize:

1. **`@AutoConfiguration(after = DataSourceAutoConfiguration.class)`:** processed after the auto-configuration that creates/provides the default DataSource. The condition needs to see DataSource bean definitions that have already been processed.
2. **`@ConditionalOnClass`:** only considers the configuration if both `javax.sql.DataSource` and `org.springframework.jdbc.core.JdbcTemplate` are on the classpath.
3. **`@ConditionalOnSingleCandidate(DataSource.class)`:** there must be a single determinable DataSource candidate for injection by type. If multiple beans exist, a single primary candidate can satisfy the condition.
4. **`@EnableConfigurationProperties(JdbcProperties.class)`:** registers configuration properties related to JDBC templates.
5. **`@Import`:** brings supporting configurations into processing, including `JdbcTemplate`, `NamedParameterJdbcTemplate`, and dependencies related to database initialization.

The most important condition in this lesson is `@ConditionalOnSingleCandidate(DataSource.class)`. If the condition on the **main class** does not match, the nested configurations imported inside this class are also not applied through that auto-configuration path.

## 3. What does @ConditionalOnSingleCandidate mean?

The annotation belongs to package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

The condition matches when:

- A bean of the checked type exists in the `BeanFactory`.
- A **single candidate** can be determined for autowiring a single dependency of that type.

Common cases:

- Only one `DataSource`: the condition matches.
- Multiple `DataSource`s, with exactly one marked `@Primary`: the condition still matches.
- Multiple `DataSource`s, with no primary: no single candidate, the condition does not match.
- Multiple beans marked primary: cannot pick a single primary, the condition does not match.

### Decision table

| DataSource beans in context | Single candidate? | JdbcTemplateAutoConfiguration |
| --- | --- | --- |
| No DataSource | No | Does not apply |
| One DataSource | Yes | Can apply if other conditions match |
| Two DataSources, no `@Primary` | No | Does not apply |
| Two DataSources, exactly one `@Primary` | Yes | Can apply |
| Three DataSources, exactly one `@Primary` | Yes | Can apply |
| Two DataSources, both `@Primary` | No | Does not apply |

The table assumes all beans are eligible autowire candidates. Attributes such as `autowireCandidate=false`, non-default candidate bean definitions, and context hierarchies can affect candidate lookup; those are advanced cases and should not replace a clear DataSource design.

**Note:** `@ConditionalOnSingleCandidate` only sees bean definitions that have already been processed when the condition is evaluated. Therefore, if another auto-configuration creates a DataSource, auto-configuration ordering must allow the DataSource to be registered first. This is also why `JdbcTemplateAutoConfiguration` declares it runs after `DataSourceAutoConfiguration`.

## 4. @Primary and @Qualifier solve two different problems

### 4.1. @Primary: selecting the default candidate by type

`@Primary` marks a bean as the preferred choice when Spring needs to inject **a single value** among multiple beans of the same type.

~~~java
@Configuration(proxyBeanMethods = false)
class DataSourceConfiguration {

    @Bean
    @Primary
    DataSource ordersDataSource() {
        return createOrdersDataSource();
    }

    @Bean
    DataSource reportingDataSource() {
        return createReportingDataSource();
    }
}
~~~

In the example, when a method accepts `DataSource` without a qualifier, Spring picks `ordersDataSource`. For `@ConditionalOnSingleCandidate(DataSource.class)`, the primary candidate lets the condition resolve a single candidate even though the context has multiple DataSources.

`@Primary` **does not remove** the other beans. `reportingDataSource` still exists and can still be injected using a qualifier. When injecting `List<DataSource>` or `Map<String, DataSource>`, Spring still provides all matching candidates; `@Primary` does not filter a collection down to one bean.

### 4.2. @Qualifier: selecting a specific bean at the injection point

When the reporting database is needed, specify the bean by name/qualifier:

~~~java
@Service
class ReportRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportRepository(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

A qualifier narrows the candidate set at a **specific injection point**. It does not itself mark a DataSource as primary and does not change the class-level `@ConditionalOnSingleCandidate(DataSource.class)` condition.

Therefore, if there are two DataSources with no primary, another service using `@Qualifier("ordersDataSource")` does not automatically make `JdbcTemplateAutoConfiguration` match. The auto-configuration condition evaluates the DataSource type across the entire context; it does not know the qualifiers of every injection point in the application.

### 4.3. Using both in a multi-database application

A common design:

- Mark the default DataSource with `@Primary` so auto-configurations use a default candidate.
- Use `@Qualifier` for services or templates tied to secondary databases.
- If a `JdbcTemplate` is needed per DataSource, explicitly declare the respective templates and qualifiers.

## 5. Configuring two DataSources with one primary

Spring Boot recommends marking one DataSource as `@Primary` when configuring multiple DataSources, because downstream auto-configurations often need to inject one candidate by type.

The production example below uses `DataSourceProperties` to bind URL, username, and password, and uses HikariCP as the connection pool.

**File:** `src/main/java/example/jdbc/DataSourcesConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
class DataSourcesConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    HikariDataSource ordersDataSource(
            DataSourceProperties ordersDataSourceProperties) {
        return ordersDataSourceProperties.initializeDataSourceBuilder()
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
            DataSourceProperties reportingDataSourceProperties) {
        return reportingDataSourceProperties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Unused imports can be removed when placing the code into a project; the snippet above shows all relevant types. `@EnableConfigurationProperties` is not needed here because the two `DataSourceProperties` beans are registered directly with `@Bean`.

Corresponding YAML configuration:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: app
      password: change-me
      configuration:
        maximum-pool-size: 20

    reporting:
      url: jdbc:postgresql://localhost:5432/reporting
      username: report
      password: change-me
      configuration:
        maximum-pool-size: 5
~~~

Connection values are illustrative examples; provide credentials from appropriate secrets/configuration in real environments.

`DataSourceProperties.initializeDataSourceBuilder()` handles mapping `url` to the appropriate connection pool property such as Hikari `jdbcUrl`. This avoids writing conversion logic manually and gives the two DataSources separate namespaces.

### Why does the first DataSourceProperties also have @Primary?

In the example, both `ordersDataSourceProperties` and `ordersDataSource` are marked `@Primary`. The primary DataSource lets type-based `DataSource` injections resolve a candidate; the primary properties bean lets components such as database initialization select the right default properties set when needed.

### Does DataSourceAutoConfiguration still create a default DataSource?

When the application declares DataSources itself, DataSource auto-configuration backs off according to its conditions. Here, both DataSources are managed by the application, so you should not expect Boot to create a third DataSource from `spring.datasource.*`.

However, that **does not mean** `JdbcTemplateAutoConfiguration` must also back off. If the context has multiple DataSources but exactly one primary candidate, `@ConditionalOnSingleCandidate(DataSource.class)` can still match and Boot can create the default `JdbcTemplate` for the primary DataSource.

## 6. JdbcTemplateConfiguration: when is the default template created?

`JdbcTemplateAutoConfiguration` imports the nested configuration `JdbcTemplateConfiguration`. In Spring Boot 3.3, this configuration uses a missing-bean condition on `JdbcOperations`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(JdbcOperations.class)
static class JdbcTemplateConfiguration {

    @Bean
    @Primary
    JdbcTemplate jdbcTemplate(
            DataSource dataSource,
            JdbcProperties properties) {

        JdbcTemplate template = new JdbcTemplate(dataSource);

        JdbcProperties.Template settings = properties.getTemplate();
        template.setFetchSize(settings.getFetchSize());
        template.setMaxRows(settings.getMaxRows());

        if (settings.getQueryTimeout() != null) {
            template.setQueryTimeout(
                    (int) settings.getQueryTimeout().getSeconds());
        }

        return template;
    }
}
~~~

This is a **condensed source snippet to explain the mechanism**. Class/package access modifiers in the actual source may not allow external applications to call it directly.

Key points:

- The condition is checked against the **`JdbcOperations` interface**, which `JdbcTemplate` implements.
- If the context already has a matching `JdbcOperations` bean, this default configuration backs off.
- If no such bean exists, the `jdbcTemplate` method creates a `JdbcTemplate`.
- The default bean is marked `@Primary`.
- The `DataSource` parameter is injected by type; when there are multiple DataSources and one primary, the default template uses the primary DataSource.

**The missing-bean condition does not only count beans named `jdbcTemplate`.** Another `JdbcOperations` implementation can also prevent the default configuration from applying. The goal is to respect a JDBC operations implementation already provided by the application.

### When the user creates a JdbcTemplate themselves

~~~java
@Bean
JdbcTemplate customJdbcTemplate(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
~~~

Because `JdbcTemplate` implements `JdbcOperations`, this bean prevents `@ConditionalOnMissingBean(JdbcOperations.class)` from matching. Boot will not create an additional default `JdbcTemplate`.

If the application has two DataSources and only creates a custom template for the secondary database, do not expect Boot to still create a second template for the primary. The missing-bean condition applies to the default configuration overall, not per DataSource. If you want both templates, declare both explicitly.

## 7. NamedParameterJdbcTemplate has its own condition

`JdbcTemplateAutoConfiguration` also imports `NamedParameterJdbcTemplateConfiguration`. This configuration creates `NamedParameterJdbcTemplate` when:

- There is a single `JdbcTemplate` candidate (or multiple beans with one determinable primary candidate).
- No matching `NamedParameterJdbcOperations` bean exists yet.

It typically creates a `NamedParameterJdbcTemplate` bean using the primary `JdbcTemplate` candidate and marks the default bean `@Primary`.

This means:

1. Two DataSources with no primary prevent the main auto-configuration from matching; the template configurations imported through it also do not run.
2. One DataSource or multiple DataSources with one primary allow the main configuration to run.
3. If the user provides a `JdbcTemplate`, the default `JdbcTemplate` creation configuration backs off.
4. If there is exactly one `JdbcTemplate` candidate and no `NamedParameterJdbcOperations` yet, Boot can still create `NamedParameterJdbcTemplate`.
5. If the user provides `NamedParameterJdbcOperations` themselves, the default NamedParameter configuration also backs off.

Two distinct missing-bean conditions protect two distinct abstractions: `JdbcOperations` and `NamedParameterJdbcOperations`.

## 8. When you need one JdbcTemplate per DataSource

If the application needs to query both the orders and reporting databases, create two templates with distinct qualifiers:

~~~java
@Configuration(proxyBeanMethods = false)
class JdbcTemplatesConfiguration {

    @Bean
    @Primary
    JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    JdbcTemplate reportingJdbcTemplate(
            @Qualifier("reportingDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Once there are two `JdbcTemplate`s, type-based injection of `JdbcTemplate` also needs a primary candidate or explicit qualifier. In the example, `ordersJdbcTemplate` is primary for unqualified injections.

Usage:

~~~java
@Repository
class OrdersRepository {

    private final JdbcTemplate jdbcTemplate;

    OrdersRepository(
            @Qualifier("ordersJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}

@Repository
class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportingRepository(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

Because `JdbcTemplate` was declared manually, Boot's default configuration backs off. This is the desired behavior: the application explicitly controls which database each template uses.

If a named-parameter template is needed for both databases, declare each bean explicitly:

~~~java
@Bean
@Primary
NamedParameterJdbcTemplate ordersNamedParameterJdbcTemplate(
        @Qualifier("ordersJdbcTemplate") JdbcTemplate jdbcTemplate) {
    return new NamedParameterJdbcTemplate(jdbcTemplate);
}

@Bean
NamedParameterJdbcTemplate reportingNamedParameterJdbcTemplate(
        @Qualifier("reportingJdbcTemplate") JdbcTemplate jdbcTemplate) {
    return new NamedParameterJdbcTemplate(jdbcTemplate);
}
~~~

Do not rely on a single default `NamedParameterJdbcTemplate` bean to automatically generate one template per DataSource; auto-configuration provides one default bean under the single-candidate rule.

## 9. Verification example with ApplicationContextRunner

We can verify the conditions without connecting to a real database. `DriverManagerDataSource` only holds URL info; the tests below do not run queries or open connections.

**File:** `src/test/java/example/jdbc/JdbcTemplateAutoConfigurationConditionsTest.java`

~~~java
package example.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class JdbcTemplateAutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JdbcTemplateAutoConfiguration.class));

    @Test
    void oneDataSourceCreatesDefaultJdbcTemplate() {
        runner.withUserConfiguration(SingleDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class).getDataSource())
                            .isSameAs(context.getBean("mainDataSource"));
                });
    }

    @Test
    void twoDataSourcesWithoutPrimaryDoNotMatch() {
        runner.withUserConfiguration(TwoDataSourcesWithoutPrimary.class)
                .run(context -> {
                    assertThat(context).hasBean("ordersDataSource");
                    assertThat(context).hasBean("reportingDataSource");
                    assertThat(context).doesNotHaveBean(JdbcTemplate.class);
                });
    }

    @Test
    void twoDataSourcesWithOnePrimaryUseThePrimaryDataSource() {
        runner.withUserConfiguration(TwoDataSourcesWithPrimary.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class).getDataSource())
                            .isSameAs(context.getBean("ordersDataSource"));
                });
    }

    @Test
    void twoPrimaryDataSourcesAreStillAmbiguous() {
        runner.withUserConfiguration(TwoPrimaryDataSources.class)
                .run(context ->
                        assertThat(context).doesNotHaveBean(JdbcTemplate.class));
    }

    @Test
    void userJdbcTemplateMakesDefaultJdbcTemplateBackOff() {
        runner.withUserConfiguration(CustomJdbcTemplateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.containsBean("customJdbcTemplate")).isTrue();
                    assertThat(context.containsBean("jdbcTemplate")).isFalse();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleDataSourceConfiguration {

        @Bean
        DataSource mainDataSource() {
            return dataSource("jdbc:example:main");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithoutPrimary {

        @Bean
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithPrimary {

        @Bean
        @Primary
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoPrimaryDataSources {

        @Bean
        @Primary
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        @Primary
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomJdbcTemplateConfiguration {

        @Bean
        @Primary
        DataSource mainDataSource() {
            return dataSource("jdbc:example:main");
        }

        @Bean
        JdbcTemplate customJdbcTemplate(
                @Qualifier("mainDataSource") DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    private static DataSource dataSource(String url) {
        return new DriverManagerDataSource(url);
    }
}
~~~

### Meaning of the five tests

| Test | Expected result | What is verified |
| --- | --- | --- |
| `oneDataSourceCreatesDefaultJdbcTemplate` | One JdbcTemplate using main DataSource | One DataSource candidate satisfies the condition |
| `twoDataSourcesWithoutPrimaryDoNotMatch` | No default JdbcTemplate | Two DataSources without primary is ambiguous |
| `twoDataSourcesWithOnePrimaryUseThePrimaryDataSource` | JdbcTemplate uses orders DataSource | One primary resolves a single candidate |
| `twoPrimaryDataSourcesAreStillAmbiguous` | No default JdbcTemplate | Multiple primaries do not produce a single candidate |
| `userJdbcTemplateMakesDefaultJdbcTemplateBackOff` | Only customJdbcTemplate exists | Default configuration backs off when JdbcOperations exists |

`DriverManagerDataSource` does not connect to a database simply upon instantiation; the tests only verify configuration and bean wiring. If executing queries, a real corresponding driver and database are required.

### Dependencies and run commands

The project requires Java 17+ and Spring Boot 3.3.x. With Gradle Groovy DSL, assuming the Spring Boot plugin or BOM manages versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run in the module containing the test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.jdbc.JdbcTemplateAutoConfigurationConditionsTest"

# Windows
gradlew.bat test --tests "example.jdbc.JdbcTemplateAutoConfigurationConditionsTest"
~~~

**Expected result:** five tests PASS. The tests use AssertJ with no `System.out.println`, so there is no fixed application stdout; console output depends on Gradle/JUnit configuration. This is the expected result based on the code, not the log of an actual run.

## 10. Reading the Condition Evaluation Report when the template does not appear

When running the application, enable debug:

~~~bash
java -jar app.jar --debug
~~~

In the Condition Evaluation Report, search for `JdbcTemplateAutoConfiguration` and related conditions.

Messages that can help guide you:

- `@ConditionalOnClass`: missing `DataSource` or `JdbcTemplate` on the classpath.
- `@ConditionalOnSingleCandidate(DataSource.class)`: no matching DataSource or no single determinable primary candidate.
- `@ConditionalOnMissingBean(JdbcOperations.class)`: a JdbcOperations bean already exists, so the default template is not created.
- `@ConditionalOnSingleCandidate(JdbcTemplate.class)`: no single JdbcTemplate candidate yet to create NamedParameter template.
- `@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)`: the application already has its own named-parameter operations.

Distinguish the condition on the **auto-configuration class** from the condition on the **nested configuration**:
- If the main class does not match `@ConditionalOnSingleCandidate(DataSource.class)`, the template configurations imported through it are not applied.
- If the main class matches but `JdbcTemplateConfiguration` backs off due to an existing `JdbcOperations`, `NamedParameterJdbcTemplateConfiguration` can still be evaluated independently against its own conditions.

Do not conclude solely based on seeing DataSource beans in the Beans tab. Read the exact conditions and bean names/types recorded by the report.

## 11. Common mistakes

1. **Having two DataSources with no primary.** `JdbcTemplateAutoConfiguration` cannot determine a single candidate by type; mark exactly one DataSource `@Primary` if you want it as the default.
2. **Marking both DataSources as primary.** This remains ambiguous; only a single primary candidate satisfies the single-candidate condition.
3. **Thinking @Qualifier replaces @Primary for auto-configuration.** A qualifier resolves one specific injection point; the class-level condition does not know service qualifiers.
4. **Thinking @Primary makes the secondary DataSource disappear.** The secondary bean still exists; use a qualifier to access it.
5. **Creating only one custom JdbcTemplate for the secondary DataSource and expecting Boot to also create a default for the primary DataSource.** The custom bean implements `JdbcOperations`, causing the default configuration to back off; declare all needed templates explicitly.
6. **Creating two JdbcTemplates without picking a primary or qualifier.** Single-bean injection by JdbcTemplate type will be ambiguous; mark one default template and qualify the rest.
7. **Confusing JdbcTemplate with NamedParameterJdbcTemplate.** They implement two different operations interfaces and have separate back-off conditions.
8. **Assuming having one DataSource satisfies all conditions.** The classpath must have JDBC classes, the DataSource configuration must be registered, and other conditions must still match.
9. **Omitting auto-configuration ordering.** JdbcTemplate's condition must be evaluated after DataSource configuration; Spring Boot sets `after = DataSourceAutoConfiguration.class` for this purpose.
10. **Using the wrong URL property with a connection pool.** When binding HikariDataSource directly, the property is `jdbc-url`; use `DataSourceProperties.initializeDataSourceBuilder()` to handle `url` mapping consistently.
11. **Assuming DataSource auto-configuration and JdbcTemplate auto-configuration back off together.** They are separate classes/conditions. Declaring a DataSource yourself can make DataSource auto-config back off, while JdbcTemplate auto-config can still apply if there is a single candidate.
12. **Testing only with a single DataSource.** Test two DataSources without primary, one primary, multiple primaries, and custom JdbcOperations as well.

## 12. Checklist when designing multiple databases

Before releasing configuration:

- Each DataSource has a clear bean name, such as `ordersDataSource` and `reportingDataSource`.
- Only one DataSource is chosen as the primary default when type-based auto-configurations are needed.
- Every repository/service accessing a secondary database uses a specific `@Qualifier`.
- Each manual JdbcTemplate is wired to the right DataSource via qualifier.
- If multiple JdbcTemplates exist, one default template is marked primary or all injections use qualifiers.
- Understand clearly that a custom `JdbcOperations` causes JdbcTemplate auto-configuration to back off.
- Check `NamedParameterJdbcOperations` as well if the application configures named-parameter templates itself.
- Include tests for DataSource counts, primary candidates, and custom templates.
- Read the Condition Evaluation Report when a branch is not registered.

## 13. Self-check questions

**Question 1.** An application has two DataSources and no `@Primary`. Does `@ConditionalOnSingleCandidate(DataSource.class)` match?

**Answer:** No. A single candidate cannot be determined for a dependency of type DataSource.

**Question 2.** An application has three DataSources, with exactly one bean marked `@Primary`. Can the condition match?

**Answer:** Yes. One primary candidate lets Spring determine a single bean when autowiring by type.

**Question 3.** A service uses `@Qualifier("ordersDataSource")`. Does that make JdbcTemplateAutoConfiguration match when there are two non-primary DataSources?

**Answer:** No. The qualifier only selects the bean at the injection point; the class-level condition still cannot determine a single primary candidate.

**Question 4.** A user creates a custom `JdbcTemplate` bean. Why doesn't Boot create an additional default template?

**Answer:** `JdbcTemplate` implements `JdbcOperations`; the `@ConditionalOnMissingBean(JdbcOperations.class)` condition on the default template configuration no longer matches.

**Question 5.** There is one custom JdbcTemplate, and no NamedParameterJdbcTemplate yet. Can Boot create the NamedParameter template?

**Answer:** Yes, if there is a single JdbcTemplate candidate and no matching `NamedParameterJdbcOperations` exists yet. The two nested configurations have separate conditions.

## 14. Key takeaways when reading JdbcTemplateAutoConfiguration

`JdbcTemplateAutoConfiguration` does not merely check whether a DataSource exists. It requires **one determinable DataSource candidate**. A single bean satisfies the condition; multiple DataSources can still satisfy it if exactly one is `@Primary`. Then, the nested configurations create `JdbcTemplate` if no `JdbcOperations` exists, and create `NamedParameterJdbcTemplate` if there is one JdbcTemplate candidate and no named-parameter operations yet.

For multi-database applications:
- `@Primary` identifies the default DataSource/template.
- `@Qualifier` selects the right database at each usage site.
- Declaring `JdbcOperations` or `NamedParameterJdbcOperations` yourself causes the corresponding default configuration to back off.
- To have a template per database, declare each bean and wire the right DataSource using qualifiers.

### Official Spring Boot and Spring Framework documentation

- [Spring Boot 3.3 — JdbcTemplateAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html)
- [Spring Boot 3.3 — ConditionalOnSingleCandidate Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
- [Spring Boot 3.3 — Data Access: Configure Two DataSources](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html)
- [Spring Framework 6.1 — @Primary Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring Framework 6.1 — @Qualifier Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html)
