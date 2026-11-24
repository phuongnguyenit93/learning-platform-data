# Reading Class-Level Conditions Before Analyzing Individual @Bean Methods: A Spring Boot JDBC Example

## 1. How to read an auto-configuration from the outside in

A JDBC auto-configuration can provide multiple infrastructure beans, but only when the context meets the appropriate conditions. When reading source code, do not start straight inside the body of a `@Bean` method. Follow this order:

1. **Discovery source:** is the class imported by Spring Boot from `AutoConfiguration.imports`?
2. **Class-level metadata:** what do `@AutoConfiguration(before/after)`, `@Conditional...` annotations, `@EnableConfigurationProperties`, and `@Import` declare?
3. **Imported configurations:** what separate conditions does each nested/imported `@Configuration` have?
4. **Individual bean methods:** bean name, return type, method-level conditions, dependency parameters, and instantiation logic.
5. **Context outcome:** which beans were registered, which backed off, and why.

This reading order is useful for JDBC because `JdbcTemplateAutoConfiguration` is a coordinating class: it declares shared conditions and imports the nested configurations containing the factory methods for `JdbcTemplate` and `NamedParameterJdbcTemplate`.

**Scope of this practice:** analyze only the auto-configuration and bean registration mechanism. The examples use a mocked `DataSource`; no connections are opened, no SQL is executed, no tables are created, and no repositories or data-querying business logic are written.

## 2. Confirming the auto-configuration is discovered

An auto-configuration is a Spring configuration class annotated with `@AutoConfiguration`. For Spring Boot to discover the class in a JAR automatically, its fully qualified class name must be listed in:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Example:

~~~text
com.acme.jdbc.autoconfigure.AcmeJdbcAutoConfiguration
~~~

Each line is one candidate auto-configuration class. Having a class on the classpath or annotating it with `@AutoConfiguration` in source **does not automatically guarantee** the class will be imported. It can still be excluded or filtered out by conditions.

In Spring Boot 3.3, the public class `org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration` serves as the auto-configuration for `JdbcTemplate` and `NamedParameterJdbcTemplate`. It is a practical starting point for practicing how to read from class-level annotations down into imported configurations.

## 3. Reading class-level annotations of JdbcTemplateAutoConfiguration

Spring Boot 3.3 class-level metadata can be summarized as follows:

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

This represents the metadata layer; the imported configurations contain the concrete bean methods. Read each annotation before opening any method:

| Annotation | Question to answer | Meaning in the JDBC example |
| --- | --- | --- |
| `@AutoConfiguration(after = DataSourceAutoConfiguration.class)` | Which class must this be processed after? | Requires processing after `DataSourceAutoConfiguration` when both are candidates. This is **ordering** metadata, not a boolean condition. |
| `@ConditionalOnClass({DataSource.class, JdbcTemplate.class})` | Which types must be on the classpath? | Both JDBC `DataSource` and Spring `JdbcTemplate` must be present. Missing either type makes the auto-configuration ineligible. |
| `@ConditionalOnSingleCandidate(DataSource.class)` | Can the context select a single `DataSource` candidate? | Matches when one eligible candidate exists, or multiple candidates exist with one bean marked `@Primary`. |
| `@EnableConfigurationProperties(JdbcProperties.class)` | Which properties class is enabled? | Registers the JDBC configuration bean so the template can read options like fetch size, max rows, and query timeout. |
| `@Import(...)` | Which supporting configurations are brought in? | Imports the dependency configurer, the configuration creating `JdbcTemplate`, and the configuration creating `NamedParameterJdbcTemplate`. |

### Ordering does not mean an existence condition

`after = DataSourceAutoConfiguration.class` does **not** mean `DataSourceAutoConfiguration` is required to produce a bean. It only defines relative ordering when both auto-configurations participate.

If the application declares its own `DataSource` and the default datasource configuration backs off, `JdbcTemplateAutoConfiguration` can still find the user-provided bean as long as the other conditions match.

### Classpath does not mean BeanFactory

`@ConditionalOnClass(DataSource.class)` checks whether the type is on the classpath. It does not prove a `DataSource` bean exists.

`@ConditionalOnSingleCandidate(DataSource.class)` checks for a bean candidate in the context. Having the JDBC library on the classpath without a `DataSource` bean causes the candidate condition to fail.

These are two separate questions, even though both sit at the class level.

## 4. Reading the imported configurations

After understanding the coordinating class, inspect each configuration in `@Import`. For JDBC, the two key configurations are `JdbcTemplateConfiguration` and `NamedParameterJdbcTemplateConfiguration`.

### 4.1. Configuration creating JdbcTemplate

In Spring Boot 3.3, `JdbcTemplateConfiguration` is an imported nested configuration. Its core looks like:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(JdbcOperations.class)
class JdbcTemplateConfiguration {

    @Bean
    @Primary
    JdbcTemplate jdbcTemplate(
            DataSource dataSource,
            JdbcProperties properties) {

        // Configure fetch size, max rows, query timeout from properties.
        // Body simplified to focus on bean registration.
        return new JdbcTemplate(dataSource);
    }
}
~~~

The `@ConditionalOnMissingBean(JdbcOperations.class)` condition is placed on the **nested configuration class**. If the context already has a bean implementing `JdbcOperations`, this default configuration backs off. When the nested configuration applies, the `jdbcTemplate(...)` method provides the `JdbcTemplate` bean.

Read the method after understanding the condition:
- Return type is `JdbcTemplate`, a concrete type implementing `JdbcOperations`.
- The `DataSource` parameter must be resolved from the context.
- The `JdbcProperties` parameter supplies configuration options.
- `@Primary` marks this bean as the preferred candidate if multiple beans of the same type exist.
- The method body only constructs/configures the template object; the example does not call `query()` or `update()`.

### 4.2. Configuration creating NamedParameterJdbcTemplate

The second nested configuration can be summarized as:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnSingleCandidate(JdbcTemplate.class)
@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)
class NamedParameterJdbcTemplateConfiguration {

    @Bean
    @Primary
    NamedParameterJdbcTemplate namedParameterJdbcTemplate(
            JdbcTemplate jdbcTemplate) {

        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
~~~

There are two conditions at the **nested configuration** level:
- `@ConditionalOnSingleCandidate(JdbcTemplate.class)`: a single `JdbcTemplate` candidate must be selectable.
- `@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)`: no matching implementation provided by the application exists yet.

When the nested configuration applies, `namedParameterJdbcTemplate(...)` takes `JdbcTemplate` as a dependency and creates the `NamedParameterJdbcTemplate` wrapper. The example executes no SQL statements.

### 4.3. Overall condition flow

~~~mermaid
flowchart TD
    A["JdbcTemplateAutoConfiguration"] --> B{"DataSource and JdbcTemplate on classpath?"}
    B -->|"No"| X["Auto-configuration does not apply"]
    B -->|"Yes"| C{"Single DataSource candidate?"}
    C -->|"No"| X
    C -->|"Yes"| D["Import nested configurations"]
    D --> E{"Missing JdbcOperations?"}
    E -->|"Yes"| F["Register JdbcTemplate"]
    E -->|"No"| G["Use existing JdbcOperations bean"]
    F --> H{"Single JdbcTemplate and missing NamedParameterJdbcOperations?"}
    G --> H
    H -->|"Yes"| I["Register NamedParameterJdbcTemplate"]
    H -->|"No"| J["Do not create default NamedParameterJdbcTemplate"]
~~~

The diagram illustrates the primary condition gates. The real configuration also imports a dependency configurer and has additional metadata; the diagram does not replace reading the source of each configuration.

## 5. Distinguishing class-level and method-level conditions

A condition can appear on a configuration class or on a `@Bean` method. Before concluding which bean is affected, identify which element the annotation is attached to.

| Location | Scope to examine | Example |
| --- | --- | --- |
| `@AutoConfiguration` | Auto-configuration class | `@ConditionalOnClass`, `@ConditionalOnSingleCandidate(DataSource.class)` |
| Imported `@Configuration` | A group of beans in a nested configuration | `@ConditionalOnMissingBean(JdbcOperations.class)` |
| `@Bean` method | Bean definition provided by the method | `@ConditionalOnProperty` or `@ConditionalOnMissingBean` attached directly to the method |
| Method parameters | Dependencies needed to create the bean | `DataSource`, `JdbcProperties`, `JdbcTemplate` |

**Do not lump all conditions into one category.** `@ConditionalOnClass` is a classpath condition. `@ConditionalOnProperty` checks the `Environment`. `@ConditionalOnBean` and `@ConditionalOnMissingBean` check beans already processed in the context. They have different semantics and evaluation phases.

Spring Boot notes that `@ConditionalOnBean` and `@ConditionalOnMissingBean` do not simply stop a configuration class from being created. When placed at the class level, the condition affects registering the configuration class itself as a bean; when placed on a method, the condition attaches directly to the bean method. Therefore, always read the annotation's JavaDoc, attachment target, and actual outcome in the context.

For library auto-configurations:
- If only one default bean needs to back off, placing `@ConditionalOnMissingBean` on the corresponding method usually expresses intent clearly.
- If a group of nested configurations only makes sense when a prerequisite is present, organize them into a nested configuration and place conditions intentionally.
- To guard an optional library on the classpath, use a classpath condition on an appropriate enclosing configuration; do not rely solely on a method condition whose signature references optional types.

## 6. How to read each @Bean method

After understanding class-level metadata and nested configurations, read each method along five items:

1. **Bean name:** the method name is the default bean name unless another name is specified.
2. **Return type:** Spring uses this type metadata to identify the bean and evaluate certain bean conditions.
3. **Method annotations:** which conditions are attached directly to the method? Are `@Primary`, `@Qualifier`, or a scope present?
4. **Parameters:** which dependencies does the method require? Are those dependencies provided by configurations that already passed their conditions?
5. **Method body:** does the method merely assemble objects, or create side effects like opening connections, reading files, or making network calls?

Illustrative example:

~~~java
@Bean
@ConditionalOnMissingBean(ReportFormatter.class)
DefaultReportFormatter reportFormatter(JdbcProperties properties) {
    return new DefaultReportFormatter(properties.getTemplate());
}
~~~

This is an independent example, not an original Spring Boot method. The condition on the method requires that no `ReportFormatter` bean exists yet. The concrete return type `DefaultReportFormatter` supplies clear type metadata; the `JdbcProperties` parameter must be registered beforehand.

Avoid writing:

~~~java
@Bean
@ConditionalOnMissingBean
Object reportFormatter(JdbcProperties properties) {
    return new DefaultReportFormatter(properties.getTemplate());
}
~~~

In this form, the method only exposes the `Object` return type. When a default condition infers the target type from the method, overly broad metadata can prevent the condition from recognizing the real contract. Declare the most specific appropriate return type.

## 7. Outcome matrix for the JDBC example

Assume both `DataSource` and `JdbcTemplate` are on the classpath, and no user-declared `NamedParameterJdbcOperations` bean exists:

| DataSource beans in context | Class condition `@ConditionalOnSingleCandidate(DataSource.class)` | Outcome for default JdbcTemplate |
| --- | --- | --- |
| No `DataSource` | Does not match | No `JdbcTemplate` created by this configuration |
| One `DataSource` | Matches | Can create `JdbcTemplate` if no user `JdbcOperations` exists |
| Two `DataSource`s, no `@Primary` | Does not match | Does not pick a datasource arbitrarily; no template created via this branch |
| Two `DataSource`s, one `@Primary` bean | Matches | Can create template using the primary candidate |

After the class-level condition matches, nested configuration conditions further decide:
- If `JdbcOperations` already exists, the default template configuration backs off.
- If one `JdbcTemplate` candidate exists and no `NamedParameterJdbcOperations` exists yet, the named-parameter configuration can register its bean.
- If the user already provides `NamedParameterJdbcOperations`, the corresponding default bean backs off.
- Having JDBC classes on the classpath does not replace a `DataSource` bean; having a `DataSource` bean does not guarantee the default template is created if a custom bean makes the condition back off.

## 8. Spring Boot 3.3 test: verifying bean registration without running queries

Use `ApplicationContextRunner` to test configuration branches. `Mockito.mock(DataSource.class)` creates a mock datasource; the tests only verify bean registration and dependency injection. They do not call query methods, open connections, or require a real database.

Create file `src/test/java/com/example/demo/JdbcAutoConfigurationConditionsTest.java`. The project needs Java 17+, Spring Boot 3.3, `spring-boot-starter-jdbc`, and `spring-boot-starter-test`:

~~~java
package com.example.demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class JdbcAutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JdbcTemplateAutoConfiguration.class));

    @Test
    void noDataSourceMeansJdbcTemplateAutoConfigurationDoesNotMatch() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(JdbcTemplate.class);
            assertThat(context).doesNotHaveBean(
                    NamedParameterJdbcTemplate.class);
        });
    }

    @Test
    void oneDataSourceAllowsBothTemplateBeans() {
        runner.withUserConfiguration(OneDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Test
    void multipleDataSourcesWithoutPrimaryDoNotSelectOneAutomatically() {
        runner.withUserConfiguration(TwoDataSourcesConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("firstDataSource");
                    assertThat(context).hasBean("secondDataSource");
                    assertThat(context).doesNotHaveBean(JdbcTemplate.class);
                    assertThat(context).doesNotHaveBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Test
    void primaryDataSourceResolvesTheSingleCandidateCondition() {
        runner.withUserConfiguration(
                TwoDataSourcesWithPrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                    assertThat(context.getBean(DataSource.class))
                            .isSameAs(context.getBean("primaryDataSource"));
                });
    }

    @Test
    void userJdbcTemplateMakesDefaultJdbcOperationsBackOff() {
        runner.withUserConfiguration(UserJdbcTemplateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class))
                            .isSameAs(context.getBean("customJdbcTemplate"));
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class OneDataSourceConfiguration {

        @Bean
        DataSource dataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesConfiguration {

        @Bean
        DataSource firstDataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        DataSource secondDataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithPrimaryConfiguration {

        @Bean
        @Primary
        DataSource primaryDataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        DataSource secondaryDataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJdbcTemplateConfiguration {

        @Bean
        DataSource dataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        JdbcTemplate customJdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }
}
~~~

Run in a Gradle project with dependencies configured:

~~~bash
./gradlew test --tests "com.example.demo.JdbcAutoConfigurationConditionsTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.JdbcAutoConfigurationConditionsTest"
~~~

**Expected result:** 5 tests PASS:
- Test 1: missing `DataSource` so the class-level candidate condition does not match.
- Test 2: one `DataSource` satisfies the condition; both template beans are registered.
- Test 3: two datasources without a primary; no single candidate.
- Test 4: two datasources with one primary bean; the candidate condition matches.
- Test 5: the application supplies `JdbcTemplate`; default configuration does not create an extra template, while the named-parameter configuration can still use the existing candidate.

This is a test example designed to run when dependencies are properly set; the tests have not been executed in a concrete project in this pass.

## 9. Diagnosing with the Condition Evaluation Report

When the context does not contain expected beans, pass `--debug` when running the app or set `debug=true` to inspect the Condition Evaluation Report.

A JDBC report can have a structure like:

~~~text
JdbcTemplateAutoConfiguration:
  @ConditionalOnClass found required classes
  @ConditionalOnSingleCandidate found a single bean 'dataSource'

JdbcTemplateConfiguration:
  @ConditionalOnMissingBean found no beans of type JdbcOperations

NamedParameterJdbcTemplateConfiguration:
  @ConditionalOnSingleCandidate found a single bean 'jdbcTemplate'
  @ConditionalOnMissingBean found no beans of type NamedParameterJdbcOperations
~~~

This is an **illustrative example of report structure**, not fixed stdout. Bean names and match/no-match messages vary by context.

In tests, you can attach a listener:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // assertions for beans to verify
        });
~~~

When reading the report, check in order:
1. Was `JdbcTemplateAutoConfiguration` imported?
2. Did `@ConditionalOnClass` find both `DataSource` and `JdbcTemplate`?
3. How many candidates did `@ConditionalOnSingleCandidate(DataSource.class)` find? Is there a primary?
4. Did nested `JdbcTemplateConfiguration` back off because `JdbcOperations` already exists?
5. Does `NamedParameterJdbcTemplateConfiguration` have one `JdbcTemplate` candidate?
6. Is there already an application-provided `NamedParameterJdbcOperations`?

Do not conclude a bug is inside a method body before knowing whether the method was even registered.

## 10. Common misconceptions when reading JDBC auto-configuration

| Misconception | Accurate understanding |
| --- | --- |
| Having the Spring JDBC dependency means having a `JdbcTemplate` bean | The classpath condition is only one gate; a `DataSource` candidate and nested configuration conditions are also required. |
| `after = DataSourceAutoConfiguration.class` means you must use a Boot-created datasource | It is ordering metadata; a user-provided datasource can still satisfy the bean condition. |
| With multiple `DataSource`s, Spring picks any one automatically | `@ConditionalOnSingleCandidate` requires a single candidate or one explicit primary. |
| `@ConditionalOnMissingBean(JdbcOperations.class)` checks the classpath | It checks beans in the context matching the specified type. |
| Class-level and method-level conditions always have identical semantics | Evaluation scope and timing depend on the condition type; read the specific annotation and the exact element it is attached to. |
| Creating `JdbcTemplate` means the database is connected | Registering the bean does not mean opening a connection or executing a query. |
| Having a `JdbcTemplate` bean guarantees having `NamedParameterJdbcTemplate` | The named-parameter configuration's candidate condition and missing-bean condition must also pass. |
| A method taking a `DataSource` parameter creates the datasource itself | The parameter is a dependency to resolve; it does not register a bean itself. |
| Bean creation order always matches auto-configuration order | Ordering controls bean definition processing order; instances are created per dependencies and lifecycle. |
| Context starting up successfully proves all beans were registered | A bean can be skipped by conditions while the context still starts; tests must assert bean presence/absence. |

## 11. Checklist for reviewing an auto-configuration class

1. **Import source:** confirm the class is in `AutoConfiguration.imports` or explicitly imported in tests.
2. **Ordering:** `before`/`after` affects processing order, not bean existence conditions.
3. **Classpath conditions:** which optional types must be present? Do any method signatures reference types not always present on the runtime classpath?
4. **Class-level bean conditions:** which bean types/names are checked, and what are the class-level semantics of the annotation?
5. **Property/web/resource conditions:** does the whole configuration or only part of it depend on the environment?
6. **Nested/imported configurations:** open each nested class and repeat steps 2–5.
7. **Each `@Bean`:** note its name, return type, method conditions, parameters, and body.
8. **Back-off:** does a user-provided bean prevent the default bean from being created?
9. **Test matrix:** classpath present/absent, prerequisite bean present/absent, single/multiple candidates, primary, and user override.
10. **Condition report:** confirm match/no-match reasons rather than guessing from source code.

## Official references

- [Spring Boot 3.3.13 — `JdbcTemplateAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html): class-level annotations, classpath, `DataSource` candidate, properties, and imported configurations.
- [Spring Boot 3.3.13 — `DataSourceAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html): class-level conditions of datasource auto-configuration.
- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class conditions, bean conditions, class/method semantics, `ApplicationContextRunner`, and Condition Evaluation Report.
- [Spring Boot 3.3.13 — `@ConditionalOnSingleCandidate` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html): single candidate or single primary candidate condition.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): default registration based on bean absence.
