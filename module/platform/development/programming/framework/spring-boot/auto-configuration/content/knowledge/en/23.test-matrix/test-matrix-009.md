# @ImportAutoConfiguration and Narrowing the Configuration Set in Spring Boot Testing

## 1. Problem: testing only the auto-configuration actually needed

A Spring Boot application can have dozens of auto-configurations for web, JSON, database, cache, messaging, metrics, and many other integrations. When testing a small feature, loading the entire application context often makes tests slow, pulls in many dependencies, and makes it harder to tell which configuration created the bean under test.

For example, a JDBC repository needs only:

- A `DataSource` for testing.
- A `JdbcTemplate`.
- The library's own auto-configuration that creates the query service.
- Possibly a specific test support configuration.

It does not need to start a web server, security configuration, messaging, or every other integration in the application.

Spring Boot provides several ways to narrow the loaded configuration:

- **Test slices** such as `@JdbcTest`, `@DataJpaTest`, `@WebMvcTest`, and `@JsonTest` automatically pick a small set of configurations suited to the layer under test.
- **`@ImportAutoConfiguration`** adds a specified set of auto-configurations to a test slice or test context.
- **`exclude` / `excludeAutoConfiguration`** removes configurations you do not want applied.
- **`ApplicationContextRunner`** creates a small context and lets you choose the exact set of auto-configurations in auto-configuration tests.
- **`@Import`** registers specific test configurations or components; it plays a different role from importing auto-configurations.

The goal is to build a context sufficient to verify the behavior of interest, where it is clear why every bean appears.

## 2. What does `@ImportAutoConfiguration` do?

`@ImportAutoConfiguration` resides in the package:

~~~java
org.springframework.boot.autoconfigure.ImportAutoConfiguration
~~~

This annotation imports and applies the specified auto-configurations. It follows the same `before` / `after` ordering rules as `@EnableAutoConfiguration`, yet limits itself to the specified set of classes instead of pulling all candidates from `ImportCandidates`.

Example:

~~~java
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
class JsonSupportTest {
}
~~~

In the example, the test requests applying the two selected auto-configurations. The auto-configurations must still satisfy their own conditions, such as classpath, property, or bean conditions. Listing a class does not force an auto-configuration to create beans when its conditions do not match.

`@ImportAutoConfiguration` is especially useful when writing tests or building annotations for test slices. In a regular application, `@EnableAutoConfiguration` or `@SpringBootApplication` is usually the better choice.

### 2.1. Annotation attributes

| Attribute | Type | Meaning |
|---|---|---|
| `value` | `Class<?>[]` | Auto-configurations to import |
| `classes` | `Class<?>[]` | Alias for `value`, with the same purpose |
| `exclude` | `Class<?>[]` | Auto-configurations to exclude from this import |

`value` and `classes` are two alternative names for the same attribute. Only one syntax is needed:

~~~java
@ImportAutoConfiguration(
        classes = {JacksonAutoConfiguration.class}
)
class JsonSupportTest {
}
~~~

Or the short form:

~~~java
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonSupportTest {
}
~~~

Classes to import and classes to exclude can be combined:

~~~java
@ImportAutoConfiguration(
        classes = {
                JacksonAutoConfiguration.class,
                ValidationAutoConfiguration.class
        },
        exclude = {
                SomeOptionalMetricsAutoConfiguration.class
        }
)
class JsonSupportTest {
}
~~~

Classes in `exclude` are not applied via this import. Use `exclude` to explicitly state which configurations to avoid, especially when a test annotation or meta-annotation already brings in multiple auto-configurations.

### 2.2. When `value` or `classes` is omitted

If the class list is left empty, Spring Boot reads auto-configuration names from a file in `META-INF/spring`. The file name is the fully-qualified name of the class annotated with `@ImportAutoConfiguration`, followed by the `.imports` suffix.

For example, test class:

~~~java
package com.example.audit;

@ImportAutoConfiguration
class AuditSliceTest {
}
~~~

Can use the resource:

~~~text
META-INF/spring/com.example.audit.AuditSliceTest.imports
~~~

Content:

~~~text
com.example.audit.autoconfigure.AuditClientAutoConfiguration
com.example.audit.autoconfigure.AuditMetricsAutoConfiguration
~~~

Each line is an FQCN. Comments starting with `#` can be added. A line can use the `optional:` prefix to indicate that the imported class may be absent from the classpath; Spring Boot then ignores the optional class if it is not found.

This file mechanism differs from the general auto-configuration registration file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The first file serves imports tied to a specific annotation; the second publishes a library's auto-configurations for Spring Boot's standard auto-configuration discovery mechanism.

## 3. Narrowing the configuration set in test slices

A test slice focuses on one part of the application. Spring Boot provides common annotations:

| Annotation | Primary feature set |
|---|---|
| `@WebMvcTest` | Spring MVC controllers and related MVC web infrastructure |
| `@WebFluxTest` | Spring WebFlux controllers and reactive web infrastructure |
| `@JdbcTest` | `DataSource`, `JdbcTemplate`, and JDBC infrastructure |
| `@DataJpaTest` | JPA entities, repositories, and related persistence configuration |
| `@JsonTest` | JSON serializers/deserializers and JSON test helpers |
| `@RestClientTest` | REST clients and mock server for client testing |
| `@DataMongoTest` | MongoDB mapping and repository slice |
| `@JooqTest` | jOOQ `DSLContext` and related configuration |

Slices typically load only a limited set of auto-configurations and restrict component scanning to appropriate component types. Therefore, `@JdbcTest` is not a full application with every `@Service`, `@Controller`, and `@ConfigurationProperties` scanned like `@SpringBootApplication`.

For example, `@JdbcTest` by default configures an embedded database if present on the classpath and creates a `JdbcTemplate`. It does not scan regular application components. `@EnableConfigurationProperties` can be used to bring required properties into the context.

This has two consequences:

1. Test slices run focused and with fewer dependencies.
2. If a test needs a component outside the slice's scope, that component must be imported or declared explicitly.

## 4. Adding an auto-configuration to a test slice

Suppose a library has `AuditQueryAutoConfiguration`, which creates a query service based on `JdbcTemplate`. `@JdbcTest` already provides the JDBC infrastructure; the test only needs to import the library's auto-configuration.

~~~java
package com.example.audit;

import com.example.audit.autoconfigure.AuditQueryAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQuerySliceTest {

    @Autowired
    private AuditQueryService auditQueryService;

    @Test
    void usesJdbcTemplateProvidedByTheSlice() {
        assertEquals(1, auditQueryService.selectOne());
    }
}
~~~

`@JdbcTest` provides the JDBC slice. `@ImportAutoConfiguration` adds the custom auto-configuration. The test does not need to re-import `DataSourceAutoConfiguration` or `JdbcTemplateAutoConfiguration` since the slice already provides them.

Illustrative auto-configuration:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditQueryService;
import com.example.audit.JdbcAuditQueryService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
public class AuditQueryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditQueryService.class)
    AuditQueryService auditQueryService(JdbcTemplate jdbcTemplate) {
        return new JdbcAuditQueryService(jdbcTemplate);
    }
}
~~~

Service:

~~~java
package com.example.audit;

public interface AuditQueryService {
    Integer selectOne();
}
~~~

Implementation:

~~~java
package com.example.audit;

import org.springframework.jdbc.core.JdbcTemplate;

public class JdbcAuditQueryService implements AuditQueryService {

    private final JdbcTemplate jdbcTemplate;

    public JdbcAuditQueryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Integer selectOne() {
        return jdbcTemplate.queryForObject("SELECT 1", Integer.class);
    }
}
~~~

Ordering with `after = JdbcTemplateAutoConfiguration.class` ensures the bean condition is evaluated after the configuration that creates `JdbcTemplate`. The `JdbcTemplate` parameter on the `@Bean` method expresses the actual dependency when Spring instantiates the service.

The test needs the JDBC starter and H2 on the test runtime, for example with Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

With Spring Boot 3.3 and JUnit 5, run the test with:

~~~bash
./gradlew test --tests com.example.audit.AuditQuerySliceTest
~~~

The expected result is that the test starts the JDBC slice context, creates the service, and executes `SELECT 1` against the embedded database. This is a test example; run it in an actual project to verify dependencies, packages, and auto-configuration imports.

## 5. Excluding unnecessary auto-configurations

There are two common places to exclude configurations.

### 5.1. Using the `exclude` attribute of `@ImportAutoConfiguration`

~~~java
@ImportAutoConfiguration(
        classes = {
                AuditQueryAutoConfiguration.class,
                AuditMetricsAutoConfiguration.class
        },
        exclude = {
                SomeOptionalMetricsAutoConfiguration.class
        }
)
class AuditQuerySliceTest {
}
~~~

This fits when the test or a composed annotation declares the import set itself.

### 5.2. Using `excludeAutoConfiguration` on a test slice

Many slices have an `excludeAutoConfiguration` attribute. Example:

~~~java
@JdbcTest(
        excludeAutoConfiguration = {
                FlywayAutoConfiguration.class
        }
)
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQueryWithoutFlywayTest {
}
~~~

This example is for projects that have Flyway on the classpath and want to disable Flyway in tests. If Flyway is not a project dependency, there is no need to add this class to test code.

Difference in meaning:

- `@ImportAutoConfiguration(exclude = ...)` removes the class from that auto-configuration import.
- `excludeAutoConfiguration` is a slice annotation attribute that excludes an auto-configuration from the slice configuration.
- `@SpringBootApplication(exclude = ...)` and the `spring.autoconfigure.exclude` property exclude configurations from broader application startup; do not alter production configuration just to shrink a single test slice.

### 5.3. Choosing the exact class to exclude

Before excluding, identify which auto-configuration is actually causing the unwanted bean or side effect. You can use the Condition Evaluation Report to inspect:

- Which configurations matched.
- Which configurations did not match and why.
- Which beans were created by auto-configuration.
- Which conditions depend on classpath, properties, or present beans.

Do not exclude a broad group of configurations if only one specific auto-configuration is causing noise. Excluding too much can prevent the test from simulating the required infrastructure accurately.

## 6. How does `@ImportAutoConfiguration` differ from `@Import`?

Both annotations bring configurations into the context, yet their meanings and processing mechanisms differ.

| Criterion | `@ImportAutoConfiguration` | `@Import` |
|---|---|---|
| Target | Spring Boot auto-configuration classes | Regular configurations or specific components |
| Ordering | Follows auto-configuration ordering | Follows standard Spring configuration import mechanics |
| Lists | Supports `value`/`classes` and `exclude` | Imports the specified classes directly |
| Imports file | Can use `.imports` files named after the annotated class FQCN | Does not use this annotation's `.imports` file mechanism |
| Common use case | Adding configurations to a test slice or testing auto-configurations | Adding test configs, mock bean configs, or support configs to the context |

Spring Boot processes auto-configurations through a dedicated mechanism, including ordering and conditions. Therefore, when importing an auto-configuration into a test slice, use `@ImportAutoConfiguration`. Do not use regular `@Import` as a substitute.

Conversely, if you want to bring a `@TestConfiguration` class containing mock beans or a specific test setup into the context, `@Import` is the right choice:

~~~java
@JdbcTest
@Import(AuditTestBeans.class)
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditQuerySliceTest {
}
~~~

In the example, `AuditTestBeans` is a test-owned configuration; `AuditQueryAutoConfiguration` is the library's auto-configuration. Each annotation has a clear responsibility.

## 7. Creating a custom annotation to reuse a test slice

If many tests share the same slice and an extra set of auto-configurations, you can create a composed annotation.

~~~java
package com.example.audit.test;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@JdbcTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
public @interface AuditJdbcTest {
}
~~~

Using that annotation in a test:

~~~java
@AuditJdbcTest
class AuditRepositoryTests {

    @Autowired
    AuditQueryService auditQueryService;

    @Test
    void canRunJdbcQuery() {
        assertEquals(1, auditQueryService.selectOne());
    }
}
~~~

This groups test conventions under a meaningful name. When the shared slice infrastructure or auto-configuration changes, update the composed annotation once instead of editing every test class.

Keep the composed annotation's scope small. Do not add unrelated configurations just because a single test needs them.

## 8. Using an imports file to extend all tests of a slice

If a test-support library wants to add an auto-configuration to **every** test using a specific slice, Spring Boot allows registering by the slice annotation's name using a resource in `META-INF/spring`.

For example, to add `com.example.IntegrationAutoConfiguration` to every `@JdbcTest`, create the file:

~~~text
META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
~~~

Content:

~~~text
com.example.IntegrationAutoConfiguration
~~~

Comments can be added with `#`. This file is read by slice annotations backed by `@ImportAutoConfiguration`; thus, it applies to every `@JdbcTest` on any classpath containing that resource.

This is a test-support-module-level decision, not a choice for a single test class. If only one test needs extra configuration, using `@ImportAutoConfiguration` directly on the test or on a composed annotation is clearer and causes fewer side effects.

### 8.1. Distinguishing the three imports files

| File name | Used by | Purpose |
|---|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | General auto-configuration mechanism | Publishes the library's auto-configurations |
| `META-INF/spring/<FQCN-of-test-or-annotation>.imports` | `@ImportAutoConfiguration` | Specifies auto-configurations for a specific annotation/test |
| `META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports` | `@JdbcTest` | Adds configuration to all JDBC slice tests |

Do not put a library's auto-configuration into a slice test imports file expecting production applications to auto-discover it. Conversely, the global `AutoConfiguration.imports` file is not a way to limit configuration for a single test.

## 9. Does `@SpringBootTest` automatically restrict itself to the import list?

`@SpringBootTest` normally looks up the main application configuration, such as the class annotated with `@SpringBootApplication`. That configuration typically enables `@EnableAutoConfiguration`, so the context can load all auto-configurations matching the classpath and properties.

Adding:

~~~java
@SpringBootTest
@ImportAutoConfiguration(AuditQueryAutoConfiguration.class)
class AuditIntegrationTest {
}
~~~

does not replace all of the main application's auto-configurations with a list containing only `AuditQueryAutoConfiguration`. This annotation imports the specified configuration additionally; auto-configurations enabled by the main application can still be applied.

If you want integration testing close to the real application, `@SpringBootTest` is the right choice. If your goal is to isolate a group of auto-configurations, use a test slice or a minimally declared test context.

Do not try to turn a full `@SpringBootTest` into a slice by adding `@ImportAutoConfiguration`. Choose the annotation that fits the test scope from the start.

## 10. Testing an exact set of auto-configurations with `ApplicationContextRunner`

When developing library auto-configurations, `ApplicationContextRunner` is usually the cleanest and clearest way to test each combination:

- Which auto-configurations are enabled.
- Which properties are present.
- Which user beans are declared.
- Which classes are excluded from the classpath.
- Which beans are created or skipped.

Example:

~~~java
package com.example.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuditQueryAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class,
                            JdbcTemplateAutoConfiguration.class,
                            AuditQueryAutoConfiguration.class
                    ))
                    .withPropertyValues(
                            "spring.datasource.url=jdbc:h2:mem:audit_test",
                            "spring.datasource.username=sa",
                            "spring.datasource.password="
                    );

    @Test
    void importsOnlyTheAutoConfigurationsUnderTest() {
        runner.run(context -> {
            assertTrue(context.containsBean("dataSource"));
            assertTrue(context.containsBean("jdbcTemplate"));
            assertEquals(
                    1,
                    context.getBean(AuditQueryService.class).selectOne()
            );
        });
    }
}
~~~

`AutoConfigurations.of(...)` represents the set of auto-configurations for the runner to apply. Spring Boot still sorts classes according to ordering metadata; do not rely on the order they appear in the array.

The test above requires the JDBC starter and H2 at test runtime. It does not boot the full application, needs no `@SpringBootApplication`, and brings only the auto-configurations related to JDBC and the service under test into the runner.

### 10.1. Testing conditions when the classpath lacks a library

`FilteredClassLoader` can be used to simulate a class or package being absent from the runtime classpath:

~~~java
@Test
void backsOffWhenJdbcTemplateIsNotOnTheClasspath() {
    runner.withClassLoader(
            new FilteredClassLoader(JdbcTemplate.class)
    ).run(context ->
            assertTrue(context.getBeansOfType(AuditQueryService.class).isEmpty())
    );
}
~~~

This test is useful when auto-configuration has `@ConditionalOnClass`. It verifies behavior when a dependency is absent, rather than testing only the case where all libraries are on the classpath.

Note: the `FilteredClassLoader` example must be compiled in tests with `spring-boot-test`, and the referenced types must be on the compile classpath. The filter affects the test context's classloader; it does not remove the dependency from the build.

### 10.2. Testing back-off when the application provides its own bean

A well-behaved auto-configuration yields to beans provided by the application:

~~~java
@Configuration(proxyBeanMethods = false)
static class CustomAuditConfiguration {

    @Bean
    AuditQueryService customAuditQueryService() {
        return () -> 42;
    }
}
~~~

Pass the user configuration to the runner:

~~~java
runner.withUserConfiguration(CustomAuditConfiguration.class)
        .run(context -> {
            assertEquals(
                    42,
                    context.getBean(AuditQueryService.class).selectOne()
            );
        });
~~~

This test verifies that `@ConditionalOnMissingBean` works as expected. In real tests, ensure the interface and return type of the custom bean match the API checked by the auto-configuration.

## 11. Choosing the tool by test scope

| Goal | Tool to use | Reason |
|---|---|---|
| Testing an MVC controller | `@WebMvcTest` + `@Import` for test collaborators + `@ImportAutoConfiguration` when extra auto-config is needed | Focuses on web MVC |
| Testing a JDBC repository/service | `@JdbcTest` + `@ImportAutoConfiguration` | Uses the built-in JDBC slice |
| Testing JSON | `@JsonTest` and required JSON configurations | No database or web layer needed |
| Testing library auto-configuration | `ApplicationContextRunner` + `AutoConfigurations.of(...)` | Selects exact classes, properties, and user beans |
| Testing full-application integration | `@SpringBootTest` | Verifies realistic application-like configuration |
| Multiple tests sharing a slice and auto-configs | Composed annotation or slice-specific `.imports` | Shares conventions intentionally |

Spring Boot does not support combining multiple different slice annotations on the same test class, such as placing both `@JdbcTest` and `@JsonTest` together to form a combined slice. If you need multiple capabilities, pick one primary slice and add the appropriate `@AutoConfigure...` annotations or `@ImportAutoConfiguration`.

## 12. Diagnosing when a bean does not appear in tests

When a test cannot find an expected bean, check in sequence:

1. **Did the test load the right slice?** Verify the test annotation and whether main configuration is discovered.
2. **Is the auto-configuration in the import set?** Check that the class is specified in `@ImportAutoConfiguration`, runner `AutoConfigurations.of(...)`, or an `.imports` file.
3. **Did any classpath condition fail?** Verify the dependency is actually in the test runtime.
4. **Did any property condition fail?** Check the exact prefix, property name, and required value.
5. **Did any bean condition fail?** Another bean may cause `@ConditionalOnMissingBean` to back off, or a required dependency may not be registered yet.
6. **Is ordering right?** If a condition depends on a bean from another auto-configuration, declare `after` / `before` appropriately on the auto-configuration class.
7. **Is the bean outside the slice's component scan?** Use `@Import` or `@EnableConfigurationProperties` to register the component the test needs.
8. **Is an exclusion taking effect?** Check `exclude`, `excludeAutoConfiguration`, and `spring.autoconfigure.exclude`.
9. **Was `@Import` used by mistake?** Switch to `@ImportAutoConfiguration` when the class to import is an auto-configuration.
10. **Are you expecting `@ImportAutoConfiguration` to restrict a full `@SpringBootTest`?** Use a test slice or `ApplicationContextRunner` if a narrow configuration set is required.

Enable the debug condition report when you need to see why an auto-configuration matched or failed to match. Avoid adding configurations blindly until tests turn green; find the first unmatched condition and fix its root cause.

## 13. Common mistakes

1. **Using `@Import` to import an auto-configuration.** Use `@ImportAutoConfiguration` so Spring Boot applies ordering and dedicated import handling.
2. **Assuming `@ImportAutoConfiguration` creates beans regardless of conditions.** It only feeds auto-configurations into processing; class and bean conditions still apply.
3. **Putting `@ImportAutoConfiguration` on `@SpringBootTest` and expecting all other auto-configs to vanish.** It does not replace `@EnableAutoConfiguration` from the main application.
4. **Using `@JdbcTest` and expecting every `@Service` to be scanned.** Slices restrict component scanning; import required components explicitly.
5. **Forgetting the `.imports` file named after the annotation's FQCN.** When no class list is passed, the file name must match the class annotated with `@ImportAutoConfiguration`.
6. **Confusing a test slice's imports file with the global auto-configuration file.** The two files have different names and scopes.
7. **Relying on class order in the `classes` array.** Use `@AutoConfiguration(after=...)` or `before=...` to express ordering relationships.
8. **Excluding too many configurations.** The test may lose required infrastructure or stop simulating the application accurately.
9. **Combining multiple slice annotations.** Choose one primary slice and add missing capabilities using supporting annotations.
10. **Not testing missing classpath dependencies.** Use `FilteredClassLoader` to verify optional auto-configurations back off cleanly.
11. **Testing auto-configuration only with a runner and concluding the starter is packaged properly.** A runner registering classes directly does not prove `.imports` resources exist in the JAR; add a consumer test to verify artifact discovery.
12. **Putting a single test's configuration into a shared slice imports file.** Every test using that slice will receive it; use a shared file only when it is an intentional test-support module convention.

## 14. Process for designing tests with an explicit configuration set

1. Identify the layer under test: MVC, JDBC, JPA, JSON, client, or custom auto-configuration.
2. Choose the matching test slice if it provides the required infrastructure.
3. List the minimal beans and auto-configurations the test needs.
4. Use `@ImportAutoConfiguration` to add missing auto-configurations.
5. Use `exclude` or `excludeAutoConfiguration` when a specific configuration causes side effects or falls outside the test's scope.
6. Use `@Import` for test configurations, mock beans, or specific components.
7. When testing library auto-configurations, use `ApplicationContextRunner` and `AutoConfigurations.of(...)` to isolate each combination.
8. Also test missing classpath dependencies, disabled properties, and user bean overrides.
9. If the test depends on resource discovery, inspect the JAR and run a consumer smoke test; do not only register classes directly in the runner.
10. When multiple tests need to share the same configuration, create a composed annotation or a slice-specific `.imports` file with clear scope.

## 15. Takeaways

- `@ImportAutoConfiguration` imports a specific set of auto-configurations and follows ordering like `@EnableAutoConfiguration`.
- `value` and `classes` are aliases; `exclude` removes classes from the import.
- When the class list is empty, Spring Boot reads `.imports` files in `META-INF/spring` named after the annotated class's FQCN.
- Test slices already have a restricted auto-configuration set; `@ImportAutoConfiguration` supplements missing configurations.
- Use `@Import` for test configs or specific components; use `@ImportAutoConfiguration` for auto-configurations.
- `@SpringBootTest` with the main application usually still loads all matching auto-configurations; adding `@ImportAutoConfiguration` does not turn it into a slice.
- `ApplicationContextRunner` with `AutoConfigurations.of(...)` is the way to test an exact set of auto-configurations.
- Order in a class list does not replace `before` / `after` ordering metadata.
- A focused test slice should verify one layer; if extra functionality is needed, import configurations deliberately.
- A consumer smoke test is needed to verify imports resources and dependencies of a published artifact.

### Official Spring Boot 3.3 Documentation

- Javadoc `@ImportAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Testing Spring Boot Applications — test slices, auto-configured tests, and extending slices: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Testing — test modules and testing utilities: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Creating Your Own Auto-configuration — testing auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
