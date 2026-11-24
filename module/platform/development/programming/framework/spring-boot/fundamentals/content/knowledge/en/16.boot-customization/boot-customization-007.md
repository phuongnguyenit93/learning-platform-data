# Writing a small auto-configuration with clear back-off

Spring Boot auto-configuration helps a library automatically register sensible beans based on dependencies, properties, and beans the application has already provided. A good auto-configuration creates a "drop in the starter and it works" experience while still leaving the application in control to replace default behavior.

The key when writing auto-configuration is **back-off**: when the user has already declared a matching bean, the auto-configuration should yield instead of creating an extra competing bean. The most common mechanism is **@ConditionalOnMissingBean**.

This lesson builds a small auto-configuration for a greeting service. We will register a default service, let the application replace that service, toggle the feature with a property, and test the branches using ApplicationContextRunner.

## 1. What problem does auto-configuration solve?

Suppose many applications need to send notifications. A library can provide a default implementation:

~~~java
public interface GreetingService {
    String greet(String name);
}
~~~

~~~java
public class DefaultGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

If every application had to manually declare a `@Bean` for DefaultGreetingService, configuration would be repetitive. An auto-configuration can automatically register the default service when an application uses the library.

However, application A might want a custom greeting, application B might fetch greetings from an API, and application C might not want this feature enabled. So auto-configuration needs clear rules:

- Automatically create the default bean when no application-provided GreetingService bean exists yet.
- Yield when the application registers its own GreetingService.
- Only enable the feature when the property permits.
- Only activate integration parts when required libraries are on the classpath.
- Avoid creating multiple beans with the same role that make injection ambiguous.

An auto-configuration should not force applications to accept every default choice. It should provide a **replaceable default path**.

## 2. Distinguishing auto-configuration from component scanning

**Component scanning** finds classes annotated with `@Component`, `@Service`, or `@Repository` within scanned packages.

**Auto-configuration** is configuration discovered and applied by Spring Boot via a separate registration mechanism, typically located in a starter library or autoconfigure module.

Example component:

~~~java
@Service
public class GreetingServiceImpl implements GreetingService {
    // ...
}
~~~

This class is discovered only if its package is inside component scan or registered through another mechanism.

Conversely, auto-configuration can live outside the main class's package and be loaded by Boot via metadata:

~~~text
my-greeting-starter
├── API classes
├── auto-configuration classes
└── META-INF
    └── spring
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Users add the starter to their dependency graph; Spring Boot reads the imports file to locate configuration classes. Conditions on classes and bean methods decide which parts get applied.

## 3. Designing the example before writing code

We will build a library named Greeting:

| Component | Responsibility |
|---|---|
| GreetingService | Interface that the application uses. |
| DefaultGreetingService | Default implementation from the library. |
| GreetingProperties | Receives configuration from application.yml. |
| GreetingAutoConfiguration | Registers properties and the default bean. |
| Consuming application | Can use the default bean or provide a custom bean. |

Properties:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Hello"
~~~

Expected outcomes:

| Scenario | GreetingService in context |
|---|---|
| Feature enabled, application declares no custom bean | DefaultGreetingService is present. |
| Feature enabled, application declares custom bean | Only the application-provided bean is used. |
| Feature disabled | No default bean from auto-configuration. |

This is the basic back-off contract. We will test all three cases rather than only checking that the application starts successfully.

## 4. Declaring the API and default implementation

The interface is the contract consumers depend on:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

The default implementation accepts a prefix from its constructor:

~~~java
package com.example.greeting;

public class DefaultGreetingService implements GreetingService {
    private final GreetingProperties properties;

    public DefaultGreetingService(GreetingProperties properties) {
        this.properties = properties;
    }

    @Override
    public String greet(String name) {
        return properties.getPrefix() + ", " + name + "!";
    }
}
~~~

We do not need to annotate the implementation with `@Component`. Auto-configuration will register it via a `@Bean` method. This lets the library clearly control which bean is created and which conditions govern its creation.

Avoiding `@Component` also prevents the situation where the implementation gets picked up by the application's component scan while auto-configuration also declares a similar bean.

## 5. Creating a configuration class with @ConfigurationProperties

A properties class groups a feature's configuration in one place:

~~~java
package com.example.greeting;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {
    private boolean enabled = true;
    private String prefix = "Hello";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

With configuration:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Hi there"
~~~

Spring Boot binds the values into GreetingProperties.

### 5.1. Why have a dedicated properties class?

A properties class helps:

- Group properties under a prefix.
- Provide clear default values.
- Easily check and validate configuration.
- Reuse properties across multiple beans.
- Generate metadata supporting IDE autocomplete if the module has the right annotation processor.

Do not scatter property strings across many factory methods if they belong to the same feature.

### 5.2. Enabling properties registration in auto-configuration

Auto-configuration can use:

~~~java
@EnableConfigurationProperties(GreetingProperties.class)
~~~

This annotation tells Spring Boot to register and bind GreetingProperties. Consumers do not need to add `@EnableConfigurationProperties` to their application class.

## 6. Writing an auto-configuration with back-off

This is the core part:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.DefaultGreetingService;
import com.example.greeting.GreetingProperties;
import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingProperties properties) {
        return new DefaultGreetingService(properties);
    }
}
~~~

This auto-configuration has three responsibilities:

1. Be registered as an auto-configuration via `@AutoConfiguration`.
2. Enable properties and apply only when `demo.greeting.enabled` is true or the property is missing.
3. Create a default GreetingService if the context does not yet have a matching GreetingService bean.

The **@ConditionalOnMissingBean(GreetingService.class)** condition is the back-off. If the application has already registered a GreetingService bean, the `greetingService()` method is not used to register the default bean.

### 6.1. Why is the @Bean return type the interface?

The method declares:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService(GreetingProperties properties) {
    return new DefaultGreetingService(properties);
}
~~~

The return type expresses the contract consumers need. For bean-based conditions, Spring Boot uses the bean method's type metadata to evaluate candidates. Declaring a return type sufficiently specific and aligned with the bean's role helps conditions process accurately.

If the condition checks GreetingService while the method only declares an overly generic return type like Object, some type information may not be available when the condition is evaluated. Declare the return type according to the abstraction the bean actually provides.

### 6.2. What does matchIfMissing mean?

In the example:

~~~java
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

- Property is true: condition matches.
- Property is false: condition does not match.
- Property is absent: condition matches because `matchIfMissing = true`.

This allows the starter to work immediately when added without forcing consumers to explicitly declare an enabling property.

If you want the feature enabled only when users actively configure it, set **matchIfMissing = false** or choose a default value matching product requirements.

## 7. Registering auto-configuration so Spring Boot finds it

With Spring Boot 3, create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file content is the fully qualified name of the auto-configuration class, one class per line:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Do not put annotations or Java syntax in this file. This is resource metadata for Boot to discover auto-configurations.

If the imports file is missing or the class name has the wrong package, the auto-configuration may not be discovered even though the class compiles cleanly.

### 7.1. Do not use the old Spring Boot 2 registration mechanism for Boot 3 projects

Older Spring Boot projects might use the file:

~~~text
META-INF/spring.factories
~~~

with the key `EnableAutoConfiguration`. With Spring Boot 3, auto-configuration registration is standardized via **AutoConfiguration.imports**. When developing a library for Boot 3, use this exact resource.

If a library must support multiple Boot generations, design compatible artifacts/metadata per version rather than assuming one registration mechanism applies to all versions.

## 8. How does back-off happen?

Suppose the consumer has:

~~~java
@Configuration(proxyBeanMethods = false)
class ApplicationConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Nice to meet you, " + name;
    }
}
~~~

The context has two configuration sources:

~~~text
Application configuration
└── customGreetingService : GreetingService

GreetingAutoConfiguration
└── greetingService()
    @ConditionalOnMissingBean(GreetingService.class)
~~~

During configuration processing, the application-declared bean is recognized. When Spring Boot evaluates the default bean's condition, GreetingService already exists, so the condition does not match. The default bean is not registered.

Result:

~~~text
GreetingService
└── customGreetingService
~~~

Consumers injecting GreetingService receive the application's implementation.

### 8.1. Back-off does not delete application-declared beans

`@ConditionalOnMissingBean` does not replace, modify, or delete existing beans. It only decides whether to register the default bean.

If the application has `customGreetingService`, that bean remains in the context. Auto-configuration simply yields.

### 8.2. Back-off is not bean overriding

Distinguish:

| Mechanism | Meaning |
|---|---|
| **@ConditionalOnMissingBean** | Do not register the default bean when a matching bean already exists. |
| **Bean definition overriding** | Allow another definition to overwrite a definition with the same name, depending on container settings. |
| **@Primary** | Prefer one bean when multiple candidates exist for a single dependency. |
| **@Qualifier** | Filter candidates by metadata at the injection point. |

Auto-configuration should favor explicit back-off instead of relying on overwriting beans with duplicate names. This is easier to reason about and prevents an application from accidentally changing behavior due to registration order.

## 9. Class-level and method-level conditions in auto-configuration

The example above places `@ConditionalOnProperty` at the class level and `@ConditionalOnMissingBean` at the method level.

This is an intentional choice:

- If the greeting feature is disabled, the entire GreetingAutoConfiguration is not applied.
- If the feature is enabled yet the application already has GreetingService, only the default bean is skipped.

If `@ConditionalOnMissingBean(GreetingService.class)` were placed at the class level:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingAutoConfiguration {
    // Other beans...
}
~~~

then when the application provides its own GreetingService, the entire configuration is dropped. If the class also provides GreetingFormatter, GreetingMetrics, or other independent beans, they also vanish unexpectedly.

Design rule:

- Put class-level conditions for foundational prerequisites applying to every bean in the configuration.
- Put `@ConditionalOnMissingBean` on individual methods if each bean should be independently overridable.
- Use nested configurations when a group of beans shares a dedicated condition.

## 10. When is @ConditionalOnClass needed?

If an auto-configuration depends on an optional library, protect the integration with a classpath condition.

For example, a module provides an adapter only when a partner SDK is present:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.greeting.VendorGreetingClient")
    static class VendorGreetingConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        GreetingService greetingService(VendorGreetingClient client) {
            return new VendorGreetingService(client);
        }
    }
}
~~~

A nested configuration helps isolate optional types. If the SDK is missing, Spring Boot can skip this branch without having to load methods whose signatures reference VendorGreetingClient in an outer configuration that is always loaded.

Do not place only a method-level `@ConditionalOnClass` while letting an optional class appear in the outer class's superclass, fields, or method signatures that are always loaded. A class-level condition on a nested configuration is a safe, readable pattern for optional integrations.

## 11. Organizing starter and autoconfigure modules

For a small library, API and auto-configuration can reside in the same module. As the library grows, consider separating:

~~~text
greeting/
├── greeting-spring-boot-autoconfigure/
│   ├── API
│   ├── GreetingProperties
│   ├── GreetingAutoConfiguration
│   └── AutoConfiguration.imports
│
└── greeting-spring-boot-starter/
    └── dependency on autoconfigure and required dependencies
~~~

### 11.1. The autoconfigure module

This module contains:

- Auto-configuration classes.
- Properties classes.
- Default implementations.
- Condition metadata.
- The `AutoConfiguration.imports` resource.

This module should declare dependencies needed to compile and run the configuration. Optional SDKs should be handled separately rather than forcing every consumer to pull them in unnecessarily.

### 11.2. The starter module

A starter is primarily a convenience artifact aggregating dependencies consumers typically need. It can depend on the autoconfigure module and common runtime libraries.

Consumers add the starter to their build file:

~~~groovy
dependencies {
    implementation 'com.example:greeting-spring-boot-starter:1.0.0'
}
~~~

They can then use GreetingService without writing default bean configuration themselves.

### 11.3. Do not confuse the starter with auto-configuration

A starter is usually a dependency aggregator. Conditional logic and bean registration live in the autoconfigure module. Separating these two responsibilities lets consumers pick the right artifact and helps the library manage optional dependencies better.

## 12. Testing auto-configuration with ApplicationContextRunner

Do not only test whether a large application starts up. Auto-configurations need to be tested across each condition branch.

**ApplicationContextRunner** lets you create a small context, add configurations, properties, or test beans, and verify the results.

In the test module, an appropriate test dependency is needed, such as:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 12.1. Creating tests for auto-configuration

~~~java
package com.example.greeting.autoconfigure;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class
                            )
                    );
}
~~~

This runner loads only the specified auto-configuration. That keeps tests focused on the library's behavior without starting an entire consumer application's web server or database.

### 12.2. Case with no custom bean

~~~java
@Test
void createsDefaultGreetingServiceWhenUserBeanIsMissing() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(DefaultGreetingService.class);
            });
}
~~~

The test confirms that when the feature is enabled and no custom bean exists yet, the default implementation is registered.

### 12.3. Case where the application provides a custom bean

Create an implementation in the test:

~~~java
class CustomGreetingService implements GreetingService {
    @Override
    public String greet(String name) {
        return "Welcome, " + name;
    }
}
~~~

Test:

~~~java
@Test
void backsOffWhenUserProvidesGreetingService() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=true")
            .withBean(
                    GreetingService.class,
                    CustomGreetingService::new
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class))
                        .isInstanceOf(CustomGreetingService.class);
                assertThat(context.getBean(GreetingService.class)
                        .greet("Lan"))
                        .isEqualTo("Welcome, Lan");
            });
}
~~~

This is the most important test for back-off. It verifies:

- The context does not have two competing GreetingService beans.
- The default bean is not created.
- The application-provided bean is still used.

### 12.4. Case where the feature is disabled

~~~java
@Test
void doesNotCreateDefaultBeanWhenFeatureIsDisabled() {
    contextRunner
            .withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
}
~~~

This test verifies the class-level condition works. When the property is false, the configuration does not register a default GreetingService bean.

### 12.5. Case where the property is missing

Since the example uses `matchIfMissing = true`, you can test:

~~~java
@Test
void enablesFeatureWhenPropertyIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(GreetingService.class);
    });
}
~~~

The test verifies the designed default behavior. If you change `matchIfMissing` to false, update the assertion accordingly.

## 13. Testing property binding

Besides checking that beans appear, verify that properties bind properly:

~~~java
@Test
void bindsGreetingPrefix() {
    contextRunner
            .withPropertyValues(
                    "demo.greeting.enabled=true",
                    "demo.greeting.prefix=Good morning"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                GreetingService service =
                        context.getBean(GreetingService.class);
                assertThat(service.greet("Minh"))
                        .isEqualTo("Good morning, Minh!");
            });
}
~~~

This test verifies the full flow: the property is bound, auto-configuration creates the default service, and the service uses the configured value.

If there is validation such as `@Validated` or constraints on properties, add tests for valid and invalid properties.

## 14. Testing when the default bean has dependencies

An auto-configuration can register multiple beans, where the default bean depends on another bean.

For example:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    GreetingFormatter greetingFormatter() {
        return new DefaultGreetingFormatter();
    }

    @Bean
    @ConditionalOnMissingBean
    GreetingService greetingService(
            GreetingProperties properties,
            GreetingFormatter formatter) {
        return new DefaultGreetingService(properties, formatter);
    }
}
~~~

In this case, if the application provides its own GreetingFormatter, the default GreetingService can still be created and use the custom formatter.

If the application provides its own GreetingService without providing GreetingFormatter, only the default service yields; the default formatter can still be registered. That is why `@ConditionalOnMissingBean` should be placed on each bean that needs independent overriding.

Tests should cover the combinations:

- Neither bean present: both default formatter and service are created.
- Custom formatter present: default service uses the custom formatter.
- Custom service present: default service is not created, default formatter can still exist.

## 15. Auto-configuration ordering and application-provided beans

Spring Boot auto-configurations are processed via a mechanism designed so application configuration can provide custom beans before default configuration decides whether to back off.

That is why `@ConditionalOnMissingBean` usually works well in auto-configuration: the condition can recognize application-declared beans and refrain from registering the default bean.

### 15.1. No need to enable bean overriding yourself

With proper back-off design:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new DefaultGreetingService(...);
}
~~~

consumers can register their own GreetingService without two definitions sharing a name and without enabling overriding.

### 15.2. When multiple auto-configurations depend on each other

If an auto-configuration needs a bean provided by another auto-configuration, you can declare relative order:

~~~java
@AutoConfiguration(after = GreetingCoreAutoConfiguration.class)
public class GreetingMetricsAutoConfiguration {
    // ...
}
~~~

The before/after attributes control ordering among auto-configurations. They are not tools for sorting every bean in the application.

Do not rely on arbitrary classpath or component scan order to decide whether `@ConditionalOnMissingBean` sees another bean.

### 15.3. Keep bean conditions on methods when possible

For auto-configuration, method-level `@ConditionalOnMissingBean` is usually the clearest choice because each default bean can back off independently. Class-level `@ConditionalOnMissingBean` should only be used when the entire configuration group truly needs to yield together.

## 16. Customizing auto-configuration with properties

A useful auto-configuration usually lets users adjust behavior without replacing beans.

Example:

~~~yaml
demo:
  greeting:
    enabled: true
    prefix: "Hi"
~~~

Properties should have:

- A stable prefix with the library's own namespace.
- Names reflecting business meaning.
- Reasonable default values.
- Clear documentation on the effect when missing or invalid.

Do not use a generic property like **enabled** at the root of the entire application. Using a prefix like `demo.greeting` avoids colliding with properties from other libraries.

### 16.1. Feature toggle property and bean override are two different decisions

Suppose `demo.greeting.enabled=false` yet the consumer still declares a custom GreetingService. If `@ConditionalOnProperty` is placed at the class level as in the example, the entire auto-configuration is skipped; the application-declared custom bean still exists.

This property controls **the library's auto-configuration**, and has no authority to delete beans the consumer registered itself.

If the business requirement is to turn off the entire feature including custom implementations, the consumer must control bean or service registration at the application level; auto-configuration should not unilaterally strip out user-managed beans.

## 17. Diagnosing when auto-configuration does not work

If the default bean does not appear, check in sequence:

### Step 1: Verify auto-configuration is registered

Check the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ensure the class name is fully qualified and the file is packaged in the artifact.

### Step 2: Check the classpath

If the configuration class or nested configuration has `@ConditionalOnClass`, verify the dependency is on the runtime classpath. The test classpath can differ from production runtime.

### Step 3: Check properties

Confirm the property has the exact prefix, name, and value. With `@ConditionalOnProperty`, pay attention to `havingValue` and `matchIfMissing`.

### Step 4: Check back-off

If `@ConditionalOnMissingBean` does not match, the application may already provide a matching bean. Query ApplicationContext or Actuator to identify bean names and types.

### Step 5: Read the Condition Evaluation Report

Run the application with:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot can print the Condition Evaluation Report, showing which auto-configurations matched or did not match and why.

### Step 6: Distinguish non-registration from bean creation failure

If conditions match yet the constructor or factory method fails, read `BeanCreationException` and the cause chain. A matching condition does not guarantee bean initialization succeeds.

## 18. Principles for designing auto-configuration

1. **Provide replaceable defaults.** Consumers should be able to use it immediately while still being able to register custom beans.
2. **Use @ConditionalOnMissingBean on each default bean.** This keeps beans independent when another bean is customized.
3. **Place conditions at the right scope.** Put shared baseline prerequisites on the class or nested configuration; put per-bean conditions on methods.
4. **Declare clear properties.** Use a dedicated prefix, intentional defaults, and intuitive semantics.
5. **Protect optional dependencies.** Use `@ConditionalOnClass` and nested configurations for code referencing optional libraries.
6. **Keep the API stable.** Consumers depend on interfaces; default implementations can evolve inside the library.
7. **Avoid duplicate bean names.** Back off by type or name instead of relying on overriding.
8. **Pay attention to auto-configuration order.** Use before/after when one configuration genuinely depends on another.
9. **Test condition branches.** Test defaults, user overrides, disabled properties, and optional classes.
10. **Keep auto-configurations focused.** Split independent feature groups into nested configurations or separate auto-configurations.

## 19. Common misconceptions

**"Adding @AutoConfiguration makes Boot automatically find the class in any package."**  
No. Auto-configuration must be registered via metadata, which in Spring Boot 3 is the `AutoConfiguration.imports` file.

**"@ConditionalOnMissingBean creates a bean if there is no bean with the same name."**  
Normally the condition checks for matching beans by type or specified criteria; it does not simply compare names. Use the `name` attribute if the intent is to check a specific bean name.

**"Back-off deletes the default bean or replaces the custom bean."**  
No. Back-off only prevents the default factory method from registering a bean when a matching bean already exists.

**"@Primary replaces @ConditionalOnMissingBean."**  
No. `@Primary` selects one candidate when injecting a single dependency; `@ConditionalOnMissingBean` decides whether to create the default bean at all.

**"Placing @ConditionalOnMissingBean at the class level is always cleaner."**  
No. It can eliminate other beans the application still needs. Use method-level conditions when beans can be overridden independently.

**"A custom bean must use the same name as the default bean."**  
No. Type-based back-off can recognize a matching bean even with a different name.

**"Property enabled=false deletes all beans of the feature."**  
No. It only controls the conditionally annotated configuration; beans declared by the application are not automatically removed.

**"Condition match means the bean will definitely initialize successfully."**  
No. Constructors, factory methods, dependencies, or external configuration can still cause failures.

**"Auto-configuration needs to be added to component scan."**  
No. A dedicated auto-configuration registration mechanism lets Boot discover configurations from metadata.

**"Testing only the default case is enough."**  
No. Back-off is proven only when testing with a custom bean and confirming the default bean yields.

## Core takeaway

A small auto-configuration should provide default beans when conditions match and **back off** when the application already provides a custom bean. With Spring Boot 3, register the class via **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**, use **@AutoConfiguration** to declare the configuration, **@EnableConfigurationProperties** to bind properties, and **@ConditionalOnMissingBean** on each default factory method to allow clean overrides.

Place class-level conditions for shared baseline prerequisites of the entire configuration, method-level conditions for each optional bean, and nested configurations for groups depending on optional libraries. Test at least the default-bean case, the custom-bean case that makes auto-configuration yield, and the disabled-property case. When back-off is cleanly designed and verified, a starter can offer a convenient default experience while keeping customization control in the application's hands.
