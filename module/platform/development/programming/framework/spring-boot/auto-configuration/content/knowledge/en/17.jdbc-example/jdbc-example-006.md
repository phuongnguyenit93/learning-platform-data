# Ordering Relationship Between Data Source Configuration and JDBC Utilities in Spring Boot

## 1. Problem to solve

A Spring Boot application can have multiple JDBC infrastructure layers:

- `DataSource` provides connections to the database.
- `JdbcTemplate` obtains connections from `DataSource` to execute SQL.
- `NamedParameterJdbcTemplate`, `JdbcClient`, or custom repositories/services may depend on `JdbcTemplate` or `DataSource`.

If a library provides its own JDBC utility, it should register beans only after the required dependencies have been configured. This is a problem of **auto-configuration application ordering** and **when bean conditions are evaluated**.

Two kinds of ordering must be distinguished:

1. **Auto-configuration application order:** the order in which Spring processes configuration classes and registers bean definitions. Uses `@AutoConfiguration(after = ...)`, `@AutoConfigureAfter`, `before`, or `@AutoConfigureBefore`.
2. **Bean instantiation order:** the order in which objects are actually created inside the ApplicationContext. Spring decides this based on dependency injection and `@DependsOn`.

`after` ensures bean conditions can see bean definitions configured earlier. It is **not** a directive to instantiate one object before another.

## 2. JDBC configuration chain in Spring Boot 3.3

Typical chain:

```text
DataSourceAutoConfiguration
          |
          | registers DataSource bean definition
          v
JdbcTemplateAutoConfiguration
          |
          | requires a suitable DataSource candidate
          | registers JdbcTemplate / NamedParameterJdbcTemplate
          v
CustomJdbcUtilityAutoConfiguration
          |
          | requires JdbcTemplate bean definition
          v
JdbcStatsRepository
```

Spring Boot 3.3 expresses this relationship in its built-in configurations:

- `DataSourceAutoConfiguration` is annotated with `@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)`. It checks required JDBC classes, the presence of an R2DBC `ConnectionFactory`, registers `DataSourceProperties`, and configures an appropriate data source.
- `JdbcTemplateAutoConfiguration` is annotated with `@AutoConfiguration(after = DataSourceAutoConfiguration.class)`. It checks for `DataSource` and `JdbcTemplate` on the classpath and uses `@ConditionalOnSingleCandidate(DataSource.class)` before registering template utilities.

Therefore, if a library's utility needs `JdbcTemplate`, place its auto-configuration after `JdbcTemplateAutoConfiguration`. If it only needs `DataSource` directly, it can be placed after `DataSourceAutoConfiguration`.

## 3. Declaring ordering with `@AutoConfiguration(after = ...)`

Example of a utility depending on `JdbcTemplate`:

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
public class JdbcUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(JdbcStatsRepository.class)
    JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        return new JdbcStatsRepository(jdbcTemplate);
    }
}
```

Meaning:

- `after = JdbcTemplateAutoConfiguration.class` requires the utility auto-configuration to be applied after Boot's template configuration.
- `@ConditionalOnClass(JdbcTemplate.class)` ensures the JDBC template API is on the classpath.
- `@ConditionalOnBean(JdbcTemplate.class)` allows this configuration to apply only when the template bean has been registered.
- `@ConditionalOnMissingBean(JdbcStatsRepository.class)` lets the application provide a replacement implementation.
- The `JdbcTemplate jdbcTemplate` parameter on the `@Bean` method creates the actual dependency. When Spring instantiates the repository, it must resolve the template first.

If the utility only uses `DataSource` directly, this pattern can be used:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(DataSource.class)
@ConditionalOnSingleCandidate(DataSource.class)
public class DirectDataSourceUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ConnectionInspector connectionInspector(DataSource dataSource) {
        return new ConnectionInspector(dataSource);
    }
}
```

`ConnectionInspector` is an illustrative type that must be defined separately. `@ConditionalOnSingleCandidate(DataSource.class)` fits when the utility needs a single datasource or one marked `@Primary`. If there are multiple datasources without a primary, this condition does not match.

| Needed utility | Should apply after | Commonly used bean condition |
|---|---|---|
| `DataSource` | `DataSourceAutoConfiguration` | `@ConditionalOnSingleCandidate(DataSource.class)` or `@ConditionalOnBean(DataSource.class)` |
| `JdbcTemplate` | `JdbcTemplateAutoConfiguration` | `@ConditionalOnBean(JdbcTemplate.class)` |
| `NamedParameterJdbcTemplate` | `JdbcTemplateAutoConfiguration` | `@ConditionalOnBean(NamedParameterJdbcTemplate.class)` |
| Bean provided by another auto-configuration | That auto-configuration | `@ConditionalOnBean(RepositoryType.class)` |

Only declare the direct ordering relationships that the utility genuinely needs.

## 4. `after`, `before`, `afterName`, and `@AutoConfigureOrder`

### `after` and `before`

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
class MyJdbcAutoConfiguration {
}

@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
class CustomSqlSetupAutoConfiguration {
}
```

`after` requests your configuration to be applied after the specified class. `before` requests it to be applied before the specified class.

### `afterName` and `beforeName`

When you do not want to reference the target class with a class literal, you can use its fully qualified name:

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration"
)
class MyJdbcAutoConfiguration {
}
```

This is useful when the target dependency is optional and the current module does not want to reference that class directly at compile time. The name must be the exact FQCN; the string is not checked by the compiler.

### `@AutoConfigureAfter` and `@AutoConfigureBefore`

Two dedicated annotations can still express the same relationship:

```java
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
class LegacyStyleJdbcConfiguration {
}
```

In newer Spring Boot 3.x code, `@AutoConfiguration(after = ...)` is generally preferred for auto-configuration classes.

### `@AutoConfigureOrder`

`@AutoConfigureOrder` sets a general relative order for auto-configurations, useful when configurations have no direct relationship or should not know each other's names. When a JDBC utility genuinely depends on `DataSourceAutoConfiguration` or `JdbcTemplateAutoConfiguration`, an `after` relationship is clearer than a generic order number.

`@Order` on a regular bean does not replace auto-configuration application ordering.

## 5. Bean definitions and object instantiation order are two different things

Suppose you have the method:

```java
@Bean
JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
    return new JdbcStatsRepository(jdbcTemplate);
}
```

When Spring creates `JdbcStatsRepository`, the `JdbcTemplate` parameter is a dependency. Spring resolves and creates the template before invoking this bean method if it has not been created yet. Dependency injection already expresses the necessary instantiation order.

`@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)` answers a different question: **when the utility's condition is evaluated, has the `JdbcTemplate` bean definition already been registered?**

`@ConditionalOnBean(JdbcTemplate.class)` relies on bean definitions that Spring has processed up to the moment of evaluation. If the utility is processed before the configuration creating the template, the condition may fail to match even though the template will be registered later. `after` resolves this evaluation-timing relationship.

| Mechanism | Effect |
|---|---|
| `@AutoConfiguration(after = ...)` | Configuration application order and bean definition registration |
| `@ConditionalOnBean(...)` | Registration decision based on already-known bean definitions |
| Parameters in a `@Bean` method | Dependency injection during bean instantiation |
| Constructor injection | Declares true dependencies between beans |
| `@DependsOn` | Forces one bean to initialize before another when side effects cannot be expressed via injection |

For `JdbcTemplate` and `DataSource`, prefer constructor or method-parameter injection. Do not use `@DependsOn` merely to replace existing dependency injection.

## 6. Why does `@ConditionalOnBean` need the right ordering?

`@ConditionalOnBean` and `@ConditionalOnMissingBean` are evaluated against bean definitions processed up to that point. Spring Boot recommends using these bean conditions in auto-configurations because auto-configurations are processed after user-declared bean definitions.

In the example:

```java
@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnBean(JdbcTemplate.class)
class JdbcUtilityAutoConfiguration {
    // Beans depending on JdbcTemplate
}
```

`after` ensures `JdbcTemplateAutoConfiguration` is applied first. If that configuration matches and registers the template, the utility's bean condition can see the corresponding bean definition.

Placing a condition at the class level prevents registering the configuration class if the condition does not match; placing it on an individual `@Bean` method controls only that bean method.

Do not use `@ConditionalOnBean` on a regular configuration expecting it to see every bean declared in configurations processed later. Put the logic in an auto-configuration and declare the appropriate ordering relationship.

## 7. Verification example with `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

The example below uses JUnit 5 and H2 to verify three cases:

1. Datasource present: Boot creates `JdbcTemplate`, then the custom auto-configuration creates the JDBC repository.
2. Datasource auto-configuration excluded: no `JdbcTemplate`, so the custom utility is not created.
3. User provides their own repository: default auto-configuration backs off.

Create file `src/test/java/demo/JdbcAutoConfigurationOrderTest.java`:

```java
package demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JdbcAutoConfigurationOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class,
                            JdbcTemplateAutoConfiguration.class,
                            JdbcUtilityAutoConfiguration.class
                    ))
                    .withPropertyValues(
                            "spring.datasource.url=jdbc:h2:mem:jdbc_order_test",
                            "spring.datasource.username=sa",
                            "spring.datasource.password="
                    );

    @Test
    void datasourceIsAvailableBeforeJdbcUtilityIsCreated() {
        runner.run(context -> {
            assertTrue(context.containsBean("dataSource"));
            assertNotNull(context.getBean(DataSource.class));
            assertNotNull(context.getBean(JdbcTemplate.class));

            JdbcStatsRepository repository =
                    context.getBean(JdbcStatsRepository.class);

            assertEquals(1, repository.selectOne());
        });
    }

    @Test
    void withoutDatasourceAutoConfigurationJdbcUtilityDoesNotExist() {
        runner.withPropertyValues(
                        "spring.autoconfigure.exclude="
                                + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
                )
                .run(context -> {
                    assertFalse(context.containsBean("jdbcTemplate"));
                    assertFalse(context.containsBean("jdbcStatsRepository"));
                    assertTrue(context.getBeansOfType(DataSource.class).isEmpty());
                });
    }

    @Test
    void userRepositoryOverridesTheDefault() {
        runner.withUserConfiguration(UserRepositoryConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("customJdbcStatsRepository"));
                    assertFalse(context.containsBean("jdbcStatsRepository"));

                    assertEquals(
                            1,
                            context.getBean(JdbcStatsRepository.class).selectOne()
                    );
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserRepositoryConfiguration {

        @Bean
        JdbcStatsRepository customJdbcStatsRepository(
                JdbcTemplate jdbcTemplate) {
            return new JdbcStatsRepository(jdbcTemplate);
        }
    }
}

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
class JdbcUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(JdbcStatsRepository.class)
    JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        return new JdbcStatsRepository(jdbcTemplate);
    }
}

final class JdbcStatsRepository {

    private final JdbcTemplate jdbcTemplate;

    JdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    int selectOne() {
        return jdbcTemplate.queryForObject("SELECT 1", Integer.class);
    }
}
```

### Test explanation

- `AutoConfigurations.of(...)` registers three auto-configurations. Spring Boot sorts them according to `before`/`after` metadata, independent of the listed class order.
- `DataSourceAutoConfiguration` creates a datasource from the H2 URL.
- `JdbcTemplateAutoConfiguration` is applied after datasource and matches only when a suitable `DataSource` candidate exists.
- `JdbcUtilityAutoConfiguration` is applied after `JdbcTemplateAutoConfiguration` and also checks that a `JdbcTemplate` bean already exists.
- The `jdbcStatsRepository(JdbcTemplate jdbcTemplate)` method expresses the true dependency between the repository and the template.
- The second test excludes datasource auto-configuration via a property. With no datasource, the condition to create `JdbcTemplate` is not met, and the custom utility is not registered either.
- The third test confirms the user bean replaces the default bean thanks to `@ConditionalOnMissingBean`.

### Dependencies and run commands

In a Gradle project with versions managed by Spring Boot 3.3.x:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run on Linux/macOS:

```bash
./gradlew test --tests demo.JdbcAutoConfigurationOrderTest
```

On Windows PowerShell:

```powershell
.\\gradlew.bat test --tests demo.JdbcAutoConfigurationOrderTest
```

**Expected result:** all 3 tests pass. The first test executes `SELECT 1` on in-memory H2; the second test does not create datasource/template/repository; the third test uses the user-provided repository. This is the expected result based on the code and dependency configuration, not the log of an actual run.

When packaging `JdbcUtilityAutoConfiguration` into a separate library, add the class name to `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.JdbcUtilityAutoConfiguration
```

Do not rely on component scan to discover auto-configurations. The test above registers classes directly via `AutoConfigurations.of(...)`, so no imports file is needed in the test.

## 8. When only DataSource is needed, not JdbcTemplate

Not every JDBC utility needs `JdbcTemplate`. A library may need `DataSource` directly to open connections, read metadata, or build another integration component.

Example:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(DataSource.class)
@ConditionalOnSingleCandidate(DataSource.class)
class ConnectionMetadataAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ConnectionMetadataReader connectionMetadataReader(
            DataSource dataSource) {
        return new ConnectionMetadataReader(dataSource);
    }
}
```

`ConnectionMetadataReader` is an illustrative class that must be defined in the application. `after = JdbcTemplateAutoConfiguration.class` is unnecessary because the configuration does not depend on the template. `@ConditionalOnSingleCandidate(DataSource.class)` fits if the utility only supports a single clear datasource candidate.

If the application has multiple datasources:

- With one datasource marked `@Primary`, Spring can determine a single candidate.
- With multiple datasources and no primary, `@ConditionalOnSingleCandidate` does not match.
- If the utility needs a specific datasource, use `@Qualifier` to inject the right bean; the condition must also express that requirement accurately.

## 9. Common ordering mistakes

1. **Placing the utility before the configuration that creates its dependency.** An auto-configuration using `@ConditionalOnBean(JdbcTemplate.class)` but processed before `JdbcTemplateAutoConfiguration` may fail to match. Declare `after` when there is a direct relationship.
2. **Using `@Order` instead of `after`.** `@Order` does not express dependencies between auto-configurations.
3. **Thinking `after` forces an object to be instantiated earlier.** It controls configuration application order and bean definition registration. To express instantiation-time dependencies, pass beans via constructors or `@Bean` parameters.
4. **Using `@DependsOn` to fix an unmatched condition.** `@DependsOn` controls bean initialization, not re-evaluation of `@ConditionalOnBean`.
5. **Forgetting `@ConditionalOnBean`.** If a utility needs `JdbcTemplate` yet still registers its bean method when the template is absent, the application can fail at startup.
6. **Checking the wrong abstraction.** Checking `DataSource.class` only proves a datasource is present, not that `JdbcTemplate` was registered.
7. **Returning too generic an interface from `@Bean`.** Bean conditions need sufficiently specific type metadata; provide a concrete return type.
8. **Assuming the class list in `AutoConfigurations.of` determines order.** Spring Boot uses ordering metadata to sort auto-configurations.
9. **Creating ordering cycles.** If A declares `after = B` and B declares `after = A`, redesign the dependency to be one-way.
10. **Forgetting the JDBC dependency is optional.** Isolate the configuration in a class with `@ConditionalOnClass` and avoid loading JDBC types when the dependency is absent.

## 10. Auto-configuration ordering does not replace dependency design

An application can have multiple configuration layers: datasource, transaction manager, JDBC template, SQL initialization, and custom query libraries. Each layer should declare its exact dependencies:

- `DataSourceAutoConfiguration` is responsible for configuring the data source.
- `JdbcTemplateAutoConfiguration` applies after datasource and checks for a single datasource candidate.
- A utility using only `JdbcTemplate` should apply after template and receive the template via injection.
- A utility using `DataSource` directly should depend on datasource, not template if unnecessary.
- Custom user beans should be respected using `@ConditionalOnMissingBean`.

Do not use a long chain of `after` attributes just to force everything into an imagined sequence. Put conditions on the right bean types, declare dependencies via injection, and only add ordering when a condition needs to see bean definitions from another auto-configuration.

## 11. Diagnosing when a JDBC utility is not created

1. **Check classpath:** Are `spring-jdbc`, the database driver, and the required pool implementation on the runtime classpath?
2. **Check datasource:** Is there a `DataSource` bean? Are there multiple datasources missing `@Primary` or `@Qualifier`?
3. **Check template:** Is there a `JdbcTemplate` or `NamedParameterJdbcTemplate` bean of the exact type the utility expects?
4. **Check ordering:** Does the utility auto-configuration specify `after` on the right class? Is that class actually imported in the application?
5. **Check conditions:** Enable `--debug` or view Actuator `/actuator/conditions` if configured to see whether `@ConditionalOnBean`, `@ConditionalOnClass`, or `@ConditionalOnSingleCandidate` failed to match.
6. **Check back-off:** Does the application already have a replacement repository/service bean preventing `@ConditionalOnMissingBean` from creating the default bean?
7. **Check instantiation:** Does the bean definition exist while the constructor or JDBC connection fails? That is an initialization error, not an ordering error.
8. **Test in isolation:** Use `ApplicationContextRunner` with each combination of classpath, properties, user beans, and auto-configurations to reproduce.

## 12. Key takeaways

- `DataSourceAutoConfiguration` is the data source configuration layer.
- In Spring Boot 3.3, `JdbcTemplateAutoConfiguration` is applied **after** `DataSourceAutoConfiguration`.
- Utilities needing `JdbcTemplate` should declare `after = JdbcTemplateAutoConfiguration.class`, check `@ConditionalOnBean(JdbcTemplate.class)`, and receive `JdbcTemplate` via injection.
- Utilities needing only `DataSource` can declare `after = DataSourceAutoConfiguration.class` and check for a suitable datasource.
- `after` controls **bean definition registration order**; constructor/method injection controls dependencies at instantiation time.
- `@DependsOn` is only for initialization ordering driven by side effects that cannot be expressed through injection.
- Test all cases: datasource present, datasource missing, and user override to confirm auto-configuration does not activate unexpectedly.

### Official documentation

- Spring Boot 3.3 Javadoc — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.3 Javadoc — `JdbcTemplateAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html
- Spring Boot 3.3 Javadoc — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Reference — Testing Applications / JDBC tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
