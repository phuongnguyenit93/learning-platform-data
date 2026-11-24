# @ImportAutoConfiguration and intentional scope of usage

Spring Boot can automatically configure many components based on dependencies, classpath, and application properties. This mechanism is very convenient when starting a complete application, but in some situations you only want to apply **a specific set of auto-configurations**. For example, a test might only need Jackson configuration to verify JSON; a test slice might only need MVC components; or a module might want to create a custom annotation to share test configuration across multiple tests.

Spring Boot provides the **`@ImportAutoConfiguration`** annotation for that purpose. The annotation allows intentionally importing auto-configuration classes, specifying a list of classes, and excluding classes you do not want applied. It commonly appears in test slices and composed test annotations.

This lesson explains what `@ImportAutoConfiguration` does, how it differs from `@Import` and `@EnableAutoConfiguration`, how to declare class lists and exclusions, how to use it in tests and custom annotations, and the limitations to keep in mind when designing configuration scope.

## 1. Why import auto-configurations selectively?

In a complete Spring Boot application, `@SpringBootApplication` includes `@EnableAutoConfiguration`. Boot inspects the auto-configurations published by dependencies on the classpath, then applies configurations matching the current conditions.

For example, if the application has a web dependency, Boot can configure components related to the web server and Spring MVC. If the Jackson library is present, Boot can configure JSON serialization. If a JDBC driver and datasource properties are present, Boot can configure database connectivity.

But in a small test, you might only need a subset of these configurations:

- Serializer tests only need Jackson.
- Controller tests need MVC components and HTTP message converters.
- Repository tests need JPA configuration and an appropriate datasource.
- Library tests want to test solely the auto-configuration provided by the library.

If you start the entire application for every test, the context may load many unrelated beans and dependencies. That slows tests down, increases environment requirements, and makes failures harder to isolate.

`@ImportAutoConfiguration` helps explicitly declare which auto-configurations need to be applied in a specific context or configuration.

## 2. What is @ImportAutoConfiguration?

The annotation resides in the package:

~~~java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
~~~

It lets you import and apply specified auto-configuration classes.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
public class ApiSupportConfiguration {
}
~~~

In this example:

- `JacksonAutoConfiguration` provides Jackson-related configuration when required conditions are satisfied.
- `ValidationAutoConfiguration` provides Bean Validation-related configuration when the corresponding dependency is present.
- Both classes still must satisfy their internal conditions; importing them does not force every bean inside to be created regardless of conditions.

Several key points:

- You can specify auto-configuration classes via the `value` or `classes` attribute.
- You can use the `exclude` attribute to omit certain auto-configurations from the imported set.
- The annotation can be placed on a configuration class or used as a meta-annotation on another annotation.
- When classes are not explicitly specified, the import mechanism uses the candidate auto-configuration list published by Boot via imports metadata.
- Conditions on auto-configurations are still evaluated during bean registration.

`@ImportAutoConfiguration` is not a Java method call and does not directly instantiate objects. It brings configurations into Spring's processing pipeline; beans inside are registered and initialized via the container mechanism.

## 3. Specifying auto-configurations via value or classes

You can declare a single class:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public class JsonSupportConfiguration {
}
~~~

Or multiple classes:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(classes = {
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
public class ApiSupportConfiguration {
}
~~~

The two attributes `value` and `classes` are two ways of expressing the imported class list. Usually you only need to use one of them so the code stays readable.

Short example with `value`:

~~~java
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
~~~

Explicit example with `classes`:

~~~java
@ImportAutoConfiguration(classes = {
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
~~~

When there are multiple configurations, only import auto-configurations relevant to the context's goal. Importing a class does not mean all its dependencies magically appear; classpath, bean, and property conditions can still cause part of the configuration to be skipped.

### 3.1. Import the right kind of auto-configuration class

`@ImportAutoConfiguration` is designed for Spring Boot auto-configurations, such as classes annotated with `@AutoConfiguration` or auto-configurations provided by Boot.

Example:

~~~java
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
~~~

Do not use this annotation as a general replacement for `@Import` to bring arbitrary classes into the context. If you have a regular application configuration class, using `@Import` usually expresses the intent better.

## 4. Excluding auto-configurations with exclude

Sometimes you want to import a group of configurations while skipping one specific configuration.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(
        classes = {
                JacksonAutoConfiguration.class,
                ValidationAutoConfiguration.class
        },
        exclude = {
                ValidationAutoConfiguration.class
        }
)
public class JsonOnlyConfiguration {
}
~~~

In this case, `ValidationAutoConfiguration` is excluded from the imported set; Jackson configuration is still evaluated.

The `exclude` attribute accepts classes. It is useful when a group of configurations is shared yet one specific test or module needs to omit a part.

Do not use exclusion just to make a context start at all costs. If an excluded auto-configuration is an actual dependency of the bean under test, the context may lack beans or no longer simulate the environment you want to verify.

### 4.1. Distinguishing annotation-level exclusion from application-wide exclusion

`@ImportAutoConfiguration(exclude = ...)` controls the set of auto-configurations imported through that annotation.

In a full Spring Boot application, `@EnableAutoConfiguration` also has application-wide exclusion mechanisms, such as the `exclude`/`excludeName` attributes or the `spring.autoconfigure.exclude` property. These mechanisms have different scopes and purposes.

Do not confuse a local exclusion in a test configuration with disabling that auto-configuration across the entire production application.

## 5. Differences between @ImportAutoConfiguration, @Import, and @EnableAutoConfiguration

The three annotations all relate to bringing configurations into a context, but they express different intents.

### 5.1. @Import: brings specific configuration classes or components into the context

`@Import` is a Spring Framework annotation:

~~~java
import org.springframework.context.annotation.Import;
~~~

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
        LocalCacheConfiguration.class,
        AuditConfiguration.class
})
public class ApplicationModuleConfiguration {
}
~~~

It imports the specified classes, usually configuration classes or components controlled by the application.

Use `@Import` when you want to explicitly wire application configurations together.

### 5.2. @EnableAutoConfiguration: enables Boot's auto-configuration mechanism

`@EnableAutoConfiguration` allows Spring Boot to discover and evaluate auto-configurations published on the classpath.

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`@SpringBootApplication` already includes `@EnableAutoConfiguration` alongside component scanning and `@SpringBootConfiguration`.

This mechanism fits when starting a Spring Boot application and letting Boot decide which configurations apply based on classpath, properties, and existing beans.

### 5.3. @ImportAutoConfiguration: selectively imports auto-configurations

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public class JsonTestConfiguration {
}
~~~

This annotation fits when a context only needs a chosen set of auto-configurations. It is commonly used in test slices, test configurations, or composed annotations.

### 5.4. Comparison table

| Annotation | Source | Primary purpose |
| --- | --- | --- |
| `@Import` | Spring Framework | Import specific configuration classes/components |
| `@EnableAutoConfiguration` | Spring Boot | Enable Boot's auto-configuration discovery and application mechanism |
| `@ImportAutoConfiguration` | Spring Boot | Intentionally import a targeted set of auto-configurations |

A way to remember:

- Need to import an application configuration class: use `@Import`.
- Need to enable Boot's overall auto-configuration system: use `@EnableAutoConfiguration` or `@SpringBootApplication`.
- Need a specific set of auto-configurations for a context or test: use `@ImportAutoConfiguration`.

## 6. Auto-configurations remain subject to conditions

Importing an auto-configuration does not guarantee every bean inside it will appear.

For example, an auto-configuration may contain:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class ExampleJsonAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ExampleJsonService exampleJsonService() {
        return new ExampleJsonService();
    }
}
~~~

If the required class is not on the classpath, the configuration may not match. If the application already provides a matching bean, the default bean may yield.

Common conditions include:

- `@ConditionalOnClass` and `@ConditionalOnMissingClass`.
- `@ConditionalOnProperty`.
- `@ConditionalOnBean` and `@ConditionalOnMissingBean`.
- `@ConditionalOnResource`.
- Custom conditions implementing `Condition`.

`@ImportAutoConfiguration` selects which configurations enter processing. The internal conditions continue deciding which beans are actually registered.

This is why tests must supply classpath entries, properties, and bean dependencies matching the scenario being tested.
## 7. When no class is specified: auto-configuration imports metadata

Spring Boot has a mechanism to publish auto-configuration lists in metadata. For Spring Boot 2.7 and above, the standard imports format is:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

An auto-configuration library can declare:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

Boot uses this metadata to find candidate auto-configurations.

`@ImportAutoConfiguration` can use this candidate discovery mechanism when an explicit class list is not provided. That is useful when building a composed annotation or test context that wants to use the auto-configuration list published by a module.

However, when the goal is to import a small, stable set, declaring classes explicitly is usually easier to read and control.

### 7.1. The imports file is not a properties configuration file

`AutoConfiguration.imports` is a list of class names, one auto-configuration class per line. It does not contain key/value pairs like `application.properties`.

Example:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Do not write:

~~~properties
greeting.enabled=true
~~~

Feature-enabling properties belong in application configuration files; imports metadata only publishes auto-configuration classes.

### 7.2. Imports metadata and version compatibility

Spring Boot prior to 2.7 typically used the `EnableAutoConfiguration` key in `META-INF/spring.factories` to publish auto-configurations. Starting from Boot 2.7, the `AutoConfiguration.imports` format is supported and is the standard approach for modern Boot lines.

When developing a starter supporting multiple Boot generations, check migration docs and corresponding packaging rules. Do not copy metadata from a newer version into an older starter without verifying that version's discovery mechanism.

## 8. Using @ImportAutoConfiguration in testing

One of the most common uses of the annotation is bringing the right auto-configurations into a test context.

For example, a test needs Jackson to check JSON serialization without starting a web server or database.

Test configuration:

~~~java
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonTestConfiguration {
}
~~~

Test:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(JsonTestConfiguration.class)
class JsonSerializationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesAnObjectAsJson() throws Exception {
        String json = objectMapper.writeValueAsString(
                new Message("hello")
        );

        assertThat(json).contains("hello");
    }

    record Message(String value) {
    }
}
~~~

The test context is initialized from `JsonTestConfiguration`. That configuration imports `JacksonAutoConfiguration`; related conditions and dependencies are still processed.

The test snippet needs Spring and JUnit test dependencies along with Jackson. For Spring Boot projects, `spring-boot-starter-test` usually provides most of the test infrastructure; a corresponding web or JSON dependency is needed for Jackson auto-configuration to be supported.

### 8.1. Why not use @SpringBootTest for every test?

`@SpringBootTest` usually initializes a context based on the main application configuration and can apply a broader configuration scope.

If the goal is just to test Jackson auto-configuration, a small context with `@ImportAutoConfiguration` keeps the test focused and less dependent on databases, servers, or other integrations.

Even so, test slices do not replace full-application integration tests. Choose the test type according to the behavior you need to verify.

## 9. Using in custom test annotations

You can create a composed annotation so multiple tests share a common set of auto-configurations.

For example, a library wants all JSON tests to have Jackson support:

~~~java
package com.example.testing;

import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public @interface JsonSupportTest {
}
~~~

Tests can use:

~~~java
@JsonSupportTest
@SpringJUnitConfig
class InvoiceJsonTest {
    // Test can inject ObjectMapper from the imported auto-configuration.
}
~~~

This is an example of a meta-annotation. In real projects, a composed annotation often needs to be combined with an appropriate Spring Test bootstrap/context annotation to define the test configuration. `@ImportAutoConfiguration` supplies the import part; it does not replace the entire test context bootstrap by itself.

### 9.1. Benefits of composed annotations

- Reduces repetition of auto-configuration lists across many tests.
- Clearly expresses the type of infrastructure the test needs.
- Allows changing the shared configuration set in one place.
- Helps a group of tests follow the same convention.

Do not create a composed annotation containing too many unrelated auto-configurations. When the scope gets too broad, tests become harder to understand and harder to isolate.

## 10. Role of @ImportAutoConfiguration in test slices

Spring Boot provides several test slices, such as:

- `@WebMvcTest` focuses on Spring MVC and related web components.
- `@DataJpaTest` focuses on JPA and persistence.
- `@JsonTest` focuses on JSON mapping.
- `@RestClientTest` focuses on testing HTTP clients.
- `@JdbcTest` focuses on JDBC.

These test slices typically use a set of annotations and import mechanisms to bring auto-configurations relevant to that test type into the context. `@ImportAutoConfiguration` is one of the mechanisms Boot uses for that purpose.

For example, an MVC test:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {
    // Focuses solely on the MVC slice.
}
~~~

If the controller needs a business service, the test can provide a mock bean:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    InvoiceService invoiceService;
}
~~~

The mock bean annotation name may vary depending on the Spring Framework/Boot version and test suite in use; older Boot projects commonly use `@MockBean`, while newer lines have `@MockitoBean` from Spring Framework Test.

If you need to add a specific auto-configuration to the slice:

~~~java
@WebMvcTest(InvoiceController.class)
@ImportAutoConfiguration(CustomJsonAutoConfiguration.class)
class InvoiceControllerJsonTest {
}
~~~

Only add needed configurations. Importing an extra auto-configuration can pull in dependencies and beans outside the original test slice scope.

## 11. Distinguishing from @EnableAutoConfiguration and global exclusions in tests

A test using `@ImportAutoConfiguration` usually wants to explicitly specify a set of additional configurations for the context. This differs from enabling the application's entire auto-configuration.

For example:

~~~java
@SpringBootTest
class FullApplicationIntegrationTest {
}
~~~

This test typically starts an application context using the full application configuration.

Whereas:

~~~java
@SpringJUnitConfig(JsonTestConfiguration.class)
class JsonSerializationTest {
}
~~~

with `JsonTestConfiguration` importing only Jackson auto-configuration, builds a context focused on the JSON goal.

Do not add `@EnableAutoConfiguration` to a small test just to get one convenient bean when you can import the exact auto-configuration needed or create a simple test configuration.

Conversely, if you are testing interactions across multiple application auto-configurations under realistic conditions, a full integration test is still necessary.

## 12. Ordering and conditions when importing multiple auto-configurations

Auto-configurations can declare ordering relationships:

~~~java
@AutoConfiguration(before = CacheAutoConfiguration.class)
public class CustomCacheSupportAutoConfiguration {
    // ...
}
~~~

Or:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class JdbcAuditAutoConfiguration {
    // ...
}
~~~

When importing multiple auto-configurations, the order in an array should not be used as a dependency coordination mechanism. Auto-configurations can declare ordering metadata, and Boot processes them via auto-configuration sorting.

If a configuration needs a bean from another auto-configuration:

- Identify the actual bean dependency.
- Use parameter injection or constructor injection.
- Declare ordering metadata when a condition needs to be evaluated after the bean-providing configuration.
- Test the context with the right set of configurations.

Do not rely on singleton initialization order to solve ordering issues. Auto-configuration ordering and the dependency graph are two related but distinct concepts.

## 13. Importing auto-configurations from an application-developed library

Suppose you have an internal starter providing:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

A test in the starter module can import it directly:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingStarterTestConfiguration {
}
~~~

Then the test verifies the default bean is registered when no custom bean is present.

Another test can provide a custom bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomGreetingTestConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new TestGreetingService();
    }
}
~~~

The test context combines both configurations:

~~~java
@SpringJUnitConfig({
        GreetingStarterTestConfiguration.class,
        CustomGreetingTestConfiguration.class
})
class GreetingBackOffTest {
    // Verify the auto-configuration yields to the test bean.
}
~~~

In a real auto-configuration, ensure appropriate ordering and user configuration registration so conditions see the test bean. For Boot auto-configurations, you can use `ApplicationContextRunner` to clearly test both branches.

## 14. Testing auto-configuration with ApplicationContextRunner

`ApplicationContextRunner` is usually the right tool for testing a library's auto-configuration. It lets you spin up a small context, add auto-configurations, user configurations, and properties, and inspect the result.

Example:

~~~java
class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class
                            )
                    );

    @Test
    void registersDefaultWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class))
                    .isInstanceOf(DefaultGreetingService.class);
        });
    }

    @Test
    void usesUserBeanWhenProvided() {
        contextRunner
                .withUserConfiguration(CustomGreetingTestConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class))
                            .isInstanceOf(TestGreetingService.class);
                });
    }
}
~~~

The example needs these imports:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
~~~

The implementations `GreetingService`, `DefaultGreetingService`, `TestGreetingService`, and custom configuration are classes in the test project.

### 14.1. Why test both branches?

An auto-configuration may work properly when there is no custom bean yet fail to yield when the application provides its own implementation.

Testing both branches confirms:

- The default is registered when the bean is missing.
- The default backs off when a user bean is present.
- Consumers can inject the proper contract.
- Bean count does not grow unexpectedly.

### 14.2. Using the context runner to test properties and classpath

`ApplicationContextRunner` also lets you add properties:

~~~java
contextRunner
        .withPropertyValues("greeting.enabled=true")
        .run(context -> {
            // Verify configuration by property.
        });
~~~

You can combine it with `FilteredClassLoader` or appropriate helpers to test classpath conditions. This is especially useful when an auto-configuration has multiple conditions.
## 15. Common mistakes

### 15.1. Accidentally importing a regular configuration class

**Symptom:** Using `@ImportAutoConfiguration` for an application configuration class that is not an auto-configuration and getting unexpected results.

**Cause:** This annotation is designed for Boot's auto-configuration import mechanism. `@Import` is the more natural choice for regular configuration classes.

**How to fix:** Identify what type the class to import is. If it is a module configuration controlled by the application, use `@Import`; if it is a Boot/starter auto-configuration, use `@ImportAutoConfiguration`.

### 15.2. Class imported but bean does not appear

**Symptom:** The auto-configuration is specified, yet the required bean is missing from the context.

**Possible causes:**

- `@ConditionalOnClass` did not match due to a missing dependency.
- `@ConditionalOnProperty` did not match.
- `@ConditionalOnMissingBean` yielded to another bean.
- Another condition was not satisfied.
- The bean was registered under a different type or omitted by an exclusion.

**How to fix:** Check the condition evaluation report, classpath, and context properties. Importing a class does not bypass conditions.

### 15.3. Importing too many auto-configurations

**Symptom:** The test context pulls in a database, web server, or many unrelated beans.

**Cause:** The imported auto-configuration set is too broad or a composed annotation contains too many configurations.

**How to fix:** Only import classes serving the test's objective. If the goal is testing the full application, use an explicit integration test instead of trying to turn a small test into a full-application context.

### 15.4. Excluding the wrong scope

**Symptom:** An auto-configuration still runs in the real application even though it was excluded in a test.

**Cause:** An exclusion placed on `@ImportAutoConfiguration` only affects that annotation's import set; the application may still have another auto-configuration import mechanism.

**How to fix:** Identify where the test context is created and which auto-configurations are imported via `@EnableAutoConfiguration` or test slices. If you want to exclude at the application level, use the appropriate exclusion on `@EnableAutoConfiguration` or the corresponding property.

### 15.5. Thinking the annotation creates a test context by itself

`@ImportAutoConfiguration` only participates in importing configurations. It does not by itself supply a JUnit extension, test bootstrap, or the entire context infrastructure.

Combine it with `@SpringJUnitConfig`, `@ContextConfiguration`, a test slice, or a suitable test bootstrap.

### 15.6. Forgetting the auto-configuration's dependencies

Importing `JacksonAutoConfiguration` does not automatically add Jackson libraries to the build. If required classes are missing from the classpath, conditions may fail to match or the configuration may not provide beans as expected.

Add the appropriate dependencies and check conditions before concluding the annotation does not work.

### 15.7. Relying on class array order to resolve dependencies

The list of classes in the annotation should not be treated as a sequential list of bean-creation commands. Auto-configurations have their own ordering metadata and dependency graphs.

Use dependency injection, ordering metadata, and test contexts to describe relationships properly.

## 16. Process for choosing import scope

When you need to bring auto-configurations into a context, follow these steps:

1. **Identify the goal:** are you testing JSON, MVC, persistence, or a specific starter?
2. **Identify the auto-configuration class:** find the exact Boot/starter class providing the needed beans.
3. **Choose the import mechanism:** use `@ImportAutoConfiguration` for auto-configurations; use `@Import` for regular application configurations.
4. **Keep the list narrow:** only import relevant configurations.
5. **Check conditions:** ensure dependencies, properties, and bean prerequisites match.
6. **Use exclude intentionally:** exclude only unnecessary configurations and understand the exclusion scope.
7. **Test the context:** verify registered beans, skipped beans, and proper dependency resolution.
8. **Review test scope:** ensure the test slice stays focused on the behavior under test.

If a test genuinely needs the entire application context, use an appropriate integration test. Do not manually import a long list of auto-configurations to mimic a full application when `@SpringBootTest` expresses that intent more clearly.

## 17. Practice exercises

### Exercise A: Import only Jackson

Create a test configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonOnlyConfiguration {
}
~~~

Create a test context, inject `ObjectMapper`, and serialize a simple record.

Verify the test does not need to start a web server.

### Exercise B: Import two auto-configurations and exclude one class

Import Jackson and Validation, then use `exclude` to exclude Validation.

Observe that Jackson-related beans can still appear when conditions match, while Validation configuration is not imported from that annotation.

### Exercise C: Compare @Import and @ImportAutoConfiguration

Create a simple application configuration class with a `@Bean`. Import it using `@Import`.

Then import a Boot auto-configuration using `@ImportAutoConfiguration`. Note the differences in semantics, conditions, and intended usage.

### Exercise D: Create a custom test annotation

Create a `@JsonSupportTest` annotation meta-annotated with `@ImportAutoConfiguration(JacksonAutoConfiguration.class)`.

Use this annotation on two test classes and verify both can inject `ObjectMapper`.

### Exercise E: Verify conditions

Import an auto-configuration that has `@ConditionalOnProperty`. Run tests with the property missing, false, and true.

Verify that importing the class does not make the condition match automatically.

### Exercise F: Test your own starter

Create an auto-configuration registering a default `GreetingService` using `@ConditionalOnMissingBean`.

Use `ApplicationContextRunner` to test both with and without a custom bean. Then use `@ImportAutoConfiguration` in a small test context to import just that auto-configuration.

## 18. Self-check questions

**1. Which package does `@ImportAutoConfiguration` belong to?**

`org.springframework.boot.autoconfigure`.

**2. What is this annotation used for?**

Intentionally importing and applying a targeted set of auto-configurations for a configuration or context.

**3. How does `@ImportAutoConfiguration` differ from `@Import`?**

`@Import` typically brings specific configuration classes/components into the context; `@ImportAutoConfiguration` is meant for Spring Boot auto-configurations and the corresponding import mechanism.

**4. How does `@ImportAutoConfiguration` differ from `@EnableAutoConfiguration`?**

`@EnableAutoConfiguration` enables discovering and applying auto-configurations across the application; `@ImportAutoConfiguration` allows importing a selected set of auto-configurations.

**5. Does importing an auto-configuration guarantee every bean inside it is created?**

No. Conditions, dependencies, and bean registration rules still apply.

**6. Can you exclude an auto-configuration from the imported set?**

Yes. Use the `exclude` attribute of `@ImportAutoConfiguration`.

**7. Does the annotation start a JUnit test context by itself?**

No. It participates in importing configuration; it must be combined with a test bootstrap or Spring Test annotation.

**8. When should you use a composed annotation?**

When multiple tests or modules need the same set of auto-configurations and want to share a clear convention.

**9. Should you import every auto-configuration into a unit test?**

No. Unit tests should test isolated class logic; integration or slice tests are what need a context and relevant auto-configurations.

## 19. Conclusion

`@ImportAutoConfiguration` helps control **the scope of auto-configurations brought into a context**. It is particularly useful in test slices, starter configuration tests, and composed annotations that need to share a specific set of auto-configurations.

Use `value` or `classes` to specify classes to import, `exclude` to omit unneeded configurations, and remember that conditions inside auto-configurations are still evaluated. Distinguish `@Import`, `@EnableAutoConfiguration`, and `@ImportAutoConfiguration` clearly to pick the right mechanism for your goal.

A good test only brings in the configurations required for the behavior being checked. When the import scope is chosen intentionally, the context is leaner, tests are easier to read, and configuration failures are easier to isolate.
