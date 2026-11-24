# Providing a custom bean to conditionally replace a default

Spring Boot and starter libraries often automatically register default beans so applications can run with minimal configuration. For example, a starter may provide a default implementation for a notification service, a data converter, or an integration client. When an application needs custom behavior, developers can register another bean with the same contract.

Spring Boot supports this pattern with conditions, especially **`@ConditionalOnMissingBean`**. The default bean is registered only when the container does not yet have a matching bean. If the application has already provided its own bean, the default configuration automatically yields.

This approach differs from registering both beans and using `@Primary` to pick one during injection. With `@ConditionalOnMissingBean`, the default bean may not be registered in the first place; with `@Primary`, both beans still exist in the context and one is preferred for single-value injection.

This lesson explains how to provide replaceable default beans, how applications override defaults, when conditions are evaluated, how to match conditions by bean type or name, how this relates to other selection annotations, and how to test the configuration.

## 1. Why does Spring Boot need replaceable default beans?

A starter usually wants to provide out-of-the-box functionality. Suppose a library has a contract:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

Default implementation:

~~~java
package com.example.greeting;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

If the starter always registers this implementation without letting the application replace it, consumers will struggle to customize how greetings work. If the starter provides nothing, every application has to write repetitive configuration.

A useful pattern is:

- The starter provides a default implementation.
- The application can register its own implementation.
- When the application already has a matching bean, the default configuration stops registering its bean.
- Consuming services still depend on the `GreetingService` interface.

This is how Spring Boot balances **convention** and **customization**.

~~~mermaid
flowchart TD
    A["Spring Boot starts up"] --> B["Register application configurations"]
    B --> C["Process auto-configuration"]
    C --> D{"GreetingService already exists?"}
    D -->|Yes| E["Skip default bean"]
    D -->|No| F["Register DefaultGreetingService"]
    E --> G["Inject application-provided bean"]
    F --> H["Inject default bean"]
~~~

The application uses the same contract whether the bean comes from the starter or is registered by the application itself.

## 2. What is @ConditionalOnMissingBean?

`@ConditionalOnMissingBean` is a Spring Boot annotation in the package:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
~~~

It instructs Spring to apply the configuration or register the annotated bean only when **no matching bean is found** within the checked scope.

Simple example:

~~~java
@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Meaning:

- If the container already has a bean of type `GreetingService`, the `greetingService()` method is not used to register the default bean.
- If no matching bean exists yet, Spring invokes the factory method when creating the bean and manages the returned object.
- The default bean is registered like any normal bean when the condition matches.

`@ConditionalOnMissingBean` is commonly used in Spring Boot **auto-configuration**. Auto-configuration provides default configuration for the application, while user-declared beans can replace that configuration.

### 2.1. The condition decides bean registration, not implementation selection on method call

When the condition does not match, the bean definition from the annotated method is not registered. Therefore, Spring does not create a default bean and check on every service call whether there is another custom bean to switch to.

This is a decision made during configuration processing and bean definition registration.

### 2.2. Placing the condition on a method or class

Placed on a method:

~~~java
@Configuration(proxyBeanMethods = false)
public class GreetingConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    Clock greetingClock() {
        return Clock.systemUTC();
    }
}
~~~

In this example, the condition only controls the `greetingService` bean. The `greetingClock` bean is still declared independently.

Placed on a class:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(GreetingService.class)
public class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
~~~

If the class-level condition does not match, the entire configuration is skipped, including the `greetingFormatter` bean.

Choose placement based on the desired scope:

- **Method-level condition:** only that bean is conditional.
- **Class-level condition:** the entire configuration is applied only when the condition matches.

When multiple independent beans have different conditions, placing conditions on individual methods usually makes the configuration easier to understand.

## 3. Providing a custom bean from the application

Suppose the starter has an auto-configuration registering a default:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return new DefaultGreetingService();
    }
}
~~~

The application wants custom greeting behavior:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new VietnameseGreetingService();
    }
}
~~~

Custom implementation:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;

public class VietnameseGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Because the `customGreetingService` bean was already declared by the application's configuration before the default auto-configuration is evaluated, `@ConditionalOnMissingBean(GreetingService.class)` does not match. Spring skips the `defaultGreetingService()` factory method.

Result:

- The context has the custom bean.
- The starter's default bean is not registered.
- Consumers injecting `GreetingService` receive the implementation provided by the application.
- No changes are needed in the starter code or the services using the contract.

Different bean names are used in the example to make clear that replacement happens via a **type-based condition**, not by overriding a bean name.

## 4. Configuration processing order matters

`@ConditionalOnMissingBean` can only inspect bean definitions that the container already knows about at the moment the condition is evaluated. Thus, configuration processing order is significant.

In the standard Spring Boot model:

1. Configurations declared by the application are processed.
2. Auto-configurations are imported and processed according to Boot's auto-configuration mechanism.
3. Auto-configuration conditions can see matching bean definitions already registered by the application configuration.
4. If the application already provided a bean, the default auto-configuration backs off.

That is why `@ConditionalOnMissingBean` is designed and commonly used in auto-configuration.

### 4.1. Do not use this condition casually between user configurations

Suppose two regular configuration classes are both scanned:

~~~java
@Configuration
class DefaultConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService defaultGreetingService() {
        return new DefaultGreetingService();
    }
}

@Configuration
class CustomConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new VietnameseGreetingService();
    }
}
~~~

If processing order causes `DefaultConfiguration` to be evaluated before the custom bean is registered, the condition may see no bean yet and register the default. Then the custom bean is also registered, leading to two candidates.

Do not rely on component scan order or file order to build a default-override mechanism. In real applications, default configuration should live in auto-configuration and the application should provide its custom bean in user configuration.

If multiple auto-configurations depend on each other's order, use appropriate ordering metadata such as `before` or `after` in `@AutoConfiguration`, or the corresponding ordering annotations. Auto-configuration ordering must express real configuration relationships, not serve as a fix-all for bean conflicts.

### 4.2. Conditions do not wait for beans to finish instantiating

Conditions primarily work with bean definitions and metadata. They do not need to wait for all singletons to be instantiated before deciding whether to register a default bean.

Therefore, the return type of a custom factory method should declare the proper contract:

~~~java
@Bean
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Spring can identify the bean by type `GreetingService` from the method's metadata. If you declare an overly generic return type like `Object`, type prediction may fail to recognize that the bean satisfies the contract before auto-configuration evaluates the condition.

Do not write:

~~~java
@Bean
Object customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

if the intent is to provide a replacement bean for `GreetingService`. Declare the return type as the recognizable interface or concrete implementation.

## 5. Conditions by type, name, and other attributes

`@ConditionalOnMissingBean` has several attributes to define what counts as an "existing" bean.

### 5.1. Checking by type

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

This is the most common approach: if a bean matching `GreetingService` already exists, do not register the default.

You can use the explicit attribute:

~~~java
@Bean
@ConditionalOnMissingBean(value = GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

### 5.2. Checking by bean name

~~~java
@Bean
@ConditionalOnMissingBean(name = "customGreetingService")
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

In this example, the condition checks for the absence of a bean named `customGreetingService`. This is useful when a contract has multiple beans and the goal is to avoid registering a duplicate under a specific identifier.

However, if the goal is to let the application provide any implementation of the contract, checking by type is usually more appropriate than checking by name.

### 5.3. Checking by annotation

The condition can also match beans carrying a specific annotation:

~~~java
@Bean
@ConditionalOnMissingBean(annotation = CustomGreetingMarker.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

`CustomGreetingMarker` is a custom annotation defined by the application or library. This is useful when the contract alone is insufficient to represent the group of beans the configuration wants to recognize.

### 5.4. Ignoring certain types when evaluating candidates

In special cases, attributes like `ignored` or `ignoredType` can exclude certain types from condition evaluation. These options usually serve complex libraries or auto-configurations.

Do not add them unless there is a clear need. The condition's intent should remain readable: "if the user already provided a bean satisfying this contract, back off."

## 6. Distinguishing @ConditionalOnMissingBean from @Primary

These two annotations are often confused as equivalent ways to replace a default bean. In reality, they address two different stages.

### 6.1. @ConditionalOnMissingBean: do not register the default bean

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}
~~~

If the application has a matching `GreetingService` bean, the default method is not registered. The context only contains the application-provided bean for this contract, unless other beans are registered elsewhere.

### 6.2. @Primary: register both, prefer one bean

~~~java
@Bean
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
@Primary
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

Here both beans exist. When a consumer asks for a single `GreetingService`, the bean annotated with `@Primary` is preferred.

However, the default bean is still registered and can still appear when injecting collections or querying by name.

| Criterion | `@ConditionalOnMissingBean` | `@Primary` |
| --- | --- | --- |
| Primary decision | Should the default bean be registered? | Which bean should be chosen for single-value injection? |
| Default bean when app has custom bean | May not be registered | Still registered |
| Multiple beans in a collection | Only registered beans appear | Both still appear |
| Where commonly used | Auto-configuration | Application or library bean configuration |
| Purpose | Let users replace the default | Set a preferred choice |

If the goal is to completely replace the starter's default, `@ConditionalOnMissingBean` usually expresses it more accurately. If you want to keep multiple implementations while having a default choice for single injection, `@Primary` is more appropriate.

## 7. Distinguishing from @Qualifier and @Fallback

### 7.1. @Qualifier selects a candidate for a consumer

If there are two beans:

~~~java
@Bean
@Qualifier("default")
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
@Qualifier("vietnamese")
GreetingService vietnameseGreetingService() {
    return new VietnameseGreetingService();
}
~~~

The consumer can select specifically:

~~~java
@Service
public class WelcomeControllerService {
    private final GreetingService greetingService;

    public WelcomeControllerService(
            @Qualifier("vietnamese") GreetingService greetingService) {
        this.greetingService = greetingService;
    }
}
~~~

`@Qualifier` does not prevent the default bean from being registered. It helps an injection point select the right candidate.

### 7.2. @Fallback marks a fallback bean

Since Spring Framework 6.2, `@Fallback` can mark a bean as a fallback candidate when multiple matching beans exist for single-value injection.

~~~java
@Bean
@Fallback
GreetingService defaultGreetingService() {
    return new DefaultGreetingService();
}

@Bean
GreetingService customGreetingService() {
    return new VietnameseGreetingService();
}
~~~

In this case both beans are still registered. The regular bean is preferred when injecting a single `GreetingService`; the fallback bean still exists and still appears in collection injection.

### 7.3. Comparison table

| Annotation | Meaning |
| --- | --- |
| `@ConditionalOnMissingBean` | Only register the bean when no matching bean exists yet |
| `@Primary` | Prefer this bean for single-value injection |
| `@Qualifier` | Select a candidate by a specific qualifier |
| `@Fallback` | Mark a bean as having fallback priority |

`@Fallback` belongs to Spring Framework 6.2 and later. It is not a bean registration condition and does not replace `@ConditionalOnMissingBean` in auto-configuration.

## 8. Complete example of auto-configuration in a starter

Suppose you are building a library `greeting-spring-boot-starter`. The starter wants to provide a default `GreetingService`, which the consuming application can replace.

### 8.1. Contract and implementation

`GreetingService.java`:

~~~java
package com.example.greeting;

public interface GreetingService {
    String greet(String name);
}
~~~

`DefaultGreetingService.java`:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

### 8.2. Auto-configuration

`GreetingAutoConfiguration.java`:

~~~java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

When the auto-configuration is applied, Spring Boot registers the default bean if no matching bean exists yet.

### 8.3. Registering auto-configuration for Boot discovery

With Spring Boot 3.x, the auto-configuration library declares the class name in the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

This file tells Spring Boot which auto-configurations to consider when an application uses the starter.

In a real project, the auto-configuration module is often separated from the starter metadata module; the exact module layout depends on how the library is packaged. What matters is that the auto-configuration class is included in the imports mechanism used by Boot.

### 8.4. Application provides a custom bean

In the application consuming the starter:

~~~java
package com.example.application;

import com.example.greeting.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return new GreetingService() {
            @Override
            public String greet(String name) {
                return "Xin chào, " + name + "!";
            }
        };
    }
}
~~~

When Spring Boot processes `GreetingAutoConfiguration`, the `customGreetingService` bean is already registered. The condition on `greetingService()` does not match and the default bean is not created.

Consumer:

~~~java
@Service
public class WelcomeService {
    private final GreetingService greetingService;

    public WelcomeService(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    public String welcome(String name) {
        return greetingService.greet(name);
    }
}
~~~

`WelcomeService` does not need to know whether the implementation comes from the starter or the application.

## 9. Combining with other conditions

In auto-configuration, whether a bean of the same type exists is only part of the decision. You may need to check classes on the classpath, properties, or application type.

Example optional client integration configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(ExternalGreetingClient.class)
@ConditionalOnProperty(
        prefix = "greeting.external",
        name = "enabled",
        havingValue = "true"
)
public class ExternalGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService externalGreetingService(
            ExternalGreetingClient client) {
        return new ExternalGreetingService(client);
    }
}
~~~

Meaning of the conditions:

- `@ConditionalOnClass`: the library providing `ExternalGreetingClient` must be on the classpath.
- `@ConditionalOnProperty`: the application must enable the integration feature.
- `@ConditionalOnMissingBean`: only provide the default implementation if the application has not already provided `GreetingService`.

`ExternalGreetingClient` and `ExternalGreetingService` are illustrative types. The client needs to be configured or created by another appropriate bean.

Conditions placed on the same configuration/method typically combine with AND logic: all relevant conditions must match for the bean to be registered.

### 9.1. Ordering between auto-configurations

If an auto-configuration needs to check for a bean provided by another auto-configuration, declare the appropriate ordering.

For example:

~~~java
@AutoConfiguration(after = ClientAutoConfiguration.class)
public class ExternalGreetingAutoConfiguration {
    // ...
}
~~~

`ClientAutoConfiguration` is a hypothetical auto-configuration class. `after` helps Boot process this configuration after the stated client configuration, within auto-configuration ordering.

Ordering does not replace proper condition design. If a configuration depends on a bean registered by another auto-configuration, clearly define the relationship and ensure the condition is evaluated after the relevant definition has been processed.

Do not use ordering to hide a genuinely missing bean or to rely on singleton initialization order.

## 10. Providing custom beans for some common default configurations

The same pattern is used across many Spring Boot integrations.

### 10.1. Customizing ObjectMapper

Spring Boot can provide an `ObjectMapper` bean based on Jackson configuration. If the application declares its own `ObjectMapper` bean, some related default auto-configurations may yield due to missing-bean conditions.

For example:

~~~java
@Configuration(proxyBeanMethods = false)
public class JsonConfiguration {

    @Bean
    public ObjectMapper objectMapper() {
        return JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();
    }
}
~~~

This snippet requires appropriate Jackson dependencies and corresponding class imports.

However, if you only want to **customize a few behaviors** of the Boot-managed ObjectMapper, you should usually consider an extension point like `Jackson2ObjectMapperBuilderCustomizer` instead of replacing the entire `ObjectMapper`. Creating a complete bean yourself may make you responsible for modules, features, and conventions that Boot otherwise configures.

The takeaway here: providing a custom bean can replace a default, but choose the smallest customization level that meets the need.

### 10.2. Providing your own DataSource

When the application declares a suitable `DataSource` bean, the default datasource auto-configuration can back off.

~~~java
@Configuration(proxyBeanMethods = false)
public class DatabaseConfiguration {

    @Bean
    public DataSource dataSource() {
        HikariDataSource dataSource = new HikariDataSource();
        dataSource.setJdbcUrl("jdbc:postgresql://localhost:5432/shop");
        dataSource.setUsername("shop_user");
        dataSource.setPassword("read-from-secure-configuration");
        return dataSource;
    }
}
~~~

This example illustrates how to create the bean; in real applications, do not hard-code passwords in source code. You should bind properties from external configuration and manage secrets securely. Additionally, a custom DataSource must have the appropriate driver, pool, transaction manager, and related settings.

If you only need to change some datasource properties, Boot's property configuration is usually simpler than replacing the entire bean yourself.

### 10.3. Custom bean for an integration client

A starter may provide a default client if the application has not registered its own client. The application can provide an implementation tailored for its own proxy, timeout, authentication, or endpoint.

What matters is that the custom bean fulfills the contract required by other services, and the default auto-configuration checks the right type/identifier to yield.

## 11. Distinguishing bean replacement from customizing an existing bean

There are two approaches:

**Bean replacement:** the application registers a different bean and auto-configuration skips the default bean thanks to `@ConditionalOnMissingBean`.

**Bean customization:** the application keeps the default bean but provides an extension point such as a customizer, builder, converter, callback, or properties to adjust behavior.

For example with ObjectMapper, if you only want to add a module or toggle a feature, a customizer is usually less invasive than creating a new ObjectMapper yourself.

Ask yourself:

- Do you need to replace the entire implementation?
- Or do you only need to change a few parameters?
- Does the starter have a built-in extension point?
- Will creating the bean yourself lose other default configurations?

Replacing a bean is a broader decision than adjusting properties of an existing bean.

## 12. Testing auto-configuration that can yield

An auto-configuration should be tested in at least two cases:

1. No user-provided bean: the default bean is created.
2. User-provided bean present: the default bean is not registered and the custom bean is used.

Spring Boot provides `ApplicationContextRunner` to test auto-configuration in a small context.

Example test:

~~~java
import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class)
                    );

    @Test
    void createsDefaultWhenUserBeanIsMissing() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class))
                    .isInstanceOf(DefaultGreetingService.class);
        });
    }

    @Test
    void backsOffWhenUserBeanIsPresent() {
        contextRunner
                .withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class))
                            .isInstanceOf(CustomGreetingService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }
}
~~~

`DefaultGreetingService` and `CustomGreetingService` are the implementations in the example. The test requires the `spring-boot-test` dependency along with suitable test libraries, typically provided when using `spring-boot-starter-test`.

### 12.1. Checking bean count

`hasSingleBean(GreetingService.class)` verifies that the context has exactly one bean matching the contract in the two scenarios above.

If you only check `context.getBean(GreetingService.class)` without checking the count, a configuration could accidentally register both the default bean and the custom bean while the test still receives one bean due to primary or qualifier. For testing backoff, the bean count is also important.

### 12.2. Checking behavior, not just type

You can invoke the bean's method to confirm the chosen implementation performs the right behavior:

~~~java
assertThat(context.getBean(GreetingService.class).greet("Lan"))
        .isEqualTo("Xin chào, Lan!");
~~~

Testing both condition branches prevents the situation where a starter works without customization yet fails when an application registers its own bean.

## 13. Common mistakes

### 13.1. Default bean is still registered even though the application has a custom bean

Possible causes:

- Auto-configuration was processed before the configuration providing the custom bean.
- The custom bean was not registered due to package scan, profile, or another condition.
- The factory method's return type is too generic, preventing Spring from recognizing the contract before the condition is evaluated.
- The condition checks the wrong bean type or name.

How to fix:

1. Verify the custom bean is actually registered.
2. Declare a clear return type, such as `GreetingService`.
3. Place the default bean in an appropriate auto-configuration.
4. Check ordering if the condition depends on a bean from another auto-configuration.

### 13.2. Two beans of the same type exist and injection is ambiguous

Perhaps the default bean has no condition or the condition did not match as expected. Spring registers both beans, and a constructor requiring a single bean may fail with `NoUniqueBeanDefinitionException`.

Check the bean definition names, condition report, and registration configuration. Do not default to adding `@Primary` as a workaround instead of fixing the condition if the real goal is for the default bean to yield.

### 13.3. Custom bean is declared but not visible

A class with `@Configuration` or `@Component` is processed only if it is within the scan scope or properly imported. Check the package containing `@SpringBootApplication` and the configuration's location.

If the configuration belongs to another module, `@Import` or an appropriate configuration mechanism may be needed.

### 13.4. Using @ConditionalOnMissingBean in application configuration with unclear ordering

Conditions are evaluated against definitions already processed at that time. Putting the condition in regular user configuration can make the result depend on ordering.

If the goal is to provide a default for starter users, placing it in auto-configuration is a clearer pattern.

### 13.5. Consumer requests a concrete implementation instead of the contract

If auto-configuration registers a bean under the `GreetingService` interface but a consumer requests the `DefaultGreetingService` class, when the application replaces the default bean with another implementation, that consumer will no longer be satisfied.

Services should depend on the interface if they only need the contract. Injecting a concrete class reduces the ability to replace beans.

### 13.6. Using @ConditionalOnMissingBean expecting beans to swap after startup

Conditions are evaluated during context configuration processing. They do not watch for newly registered beans or automatically swap running beans when properties or files change.

If you need dynamic implementation switching, you must design a runtime routing or strategy mechanism rather than using startup conditions.

### 13.7. Replacing the entire default bean just to tweak a small property

Providing your own bean can stop auto-configuration from applying other related settings. Before replacing, check if there is a more suitable customizer or properties extension point.

## 14. Process for choosing and replacing a default bean

When you want to customize a bean provided by a starter, proceed in order:

1. **Identify the contract:** what type is the default bean, and which services depend on it?
2. **Look for official configuration options:** does the starter have properties or a customizer for your need?
3. **Decide the scope of change:** customize the existing bean or provide a replacement implementation?
4. **Register the bean with the right type:** use `@Bean` or component scan; declare a sufficiently specific return type.
5. **Check conditions:** does the auto-configuration use `@ConditionalOnMissingBean` on that contract?
6. **Check ordering:** is the application configuration registered before the auto-configuration that needs to yield?
7. **Test both cases:** without a custom bean and with a custom bean.
8. **Check consumers:** do services accept the appropriate interface/contract without depending on the default implementation?

If `@ConditionalOnMissingBean` is not present in the auto-configuration, check the starter's documentation and how it designs customization. Do not assume every bean Boot provides is meant to be replaced simply by registering a bean of the same type.

## 15. Practice exercises

### Exercise A: Provide a default bean

Create an interface:

~~~java
public interface CurrencyFormatter {
    String format(long amount);
}
~~~

Create a default implementation `DefaultCurrencyFormatter` and an auto-configuration:

~~~java
@Bean
@ConditionalOnMissingBean(CurrencyFormatter.class)
CurrencyFormatter currencyFormatter() {
    return new DefaultCurrencyFormatter();
}
~~~

Run the context without a custom bean and verify the default implementation is created.

### Exercise B: Replace the default from the application

Create `VietnameseCurrencyFormatter implements CurrencyFormatter` and register it with `@Bean` in the application configuration.

Start the context with the auto-configuration. Verify the default bean is not registered and the service receives the Vietnamese implementation.

### Exercise C: Distinguish from @Primary

Remove `@ConditionalOnMissingBean` from the default bean, then register both the default and custom formatters. Mark the custom bean with `@Primary`.

Observe that:

- Both beans still exist.
- Single `CurrencyFormatter` injection prefers the primary bean.
- Collection injection still contains both.

Explain why this is not backoff.

### Exercise D: Condition by bean name

Replace the type-based condition with a name-based condition. Rename the application's factory method and observe the difference.

Explain when checking by name is more appropriate than checking by contract.

### Exercise E: Test auto-configuration

Use `ApplicationContextRunner` to write two tests:

- Without a custom bean: only the default exists.
- With a custom bean: only the custom one exists.

Verify both the count and runtime type of the selected bean.

### Exercise F: Partial customization instead of bean replacement

Pick a default bean that has an extension point (such as a builder customizer). Try adjusting a property via the customizer, then compare with creating a new bean yourself.

Note which default settings are preserved and which ones you become responsible for.

## 16. Self-check questions

**1. What is `@ConditionalOnMissingBean` used for?**

It allows registering a default bean only when no matching bean exists within the scope checked by the condition.

**2. Why does this annotation commonly appear in auto-configuration?**

Because auto-configuration provides defaults after application configurations have been processed, enabling it to detect user-registered beans and yield.

**3. If the application has a bean of the same type, what happens?**

The condition does not match and the annotated default bean is not registered from that method.

**4. How does `@ConditionalOnMissingBean` differ from `@Primary`?**

The condition controls bean registration; primary only prioritizes one bean among already registered candidates for single-value injection.

**5. Does the return type of a custom `@Bean` matter?**

Yes. Spring needs sufficiently specific metadata to recognize that the bean fulfills the contract before the condition is evaluated.

**6. Can this condition be used on a regular user configuration?**

Yes, but processing order must be controlled. The clearest and most common pattern for providing replaceable defaults is placing the condition in auto-configuration.

**7. If the default bean is not registered, does the custom bean need the same name?**

No. When checking by type, the custom bean only needs to satisfy the matching contract. The bean name can differ.

**8. Does the condition automatically swap implementations while the application is running?**

No. It is evaluated during context configuration processing, not as a dynamic runtime bean replacement mechanism.

## 17. Conclusion

Providing a custom bean to conditionally replace a default is one of Spring Boot's core customization mechanisms. Auto-configuration can register a default implementation using `@Bean` combined with `@ConditionalOnMissingBean`. When the application has already provided a matching bean, the condition fails to match and the default configuration yields.

Distinguish this mechanism from `@Primary`, `@Qualifier`, and `@Fallback`: they control candidate selection in different scenarios, whereas `@ConditionalOnMissingBean` decides whether the default bean is registered at all. Configuration processing order and factory method return types also matter because conditions rely on bean definitions identified at evaluation time.

When writing a starter or customizing an application, provide a clear contract, register custom beans with the proper type, and test both branches with and without a custom bean. This keeps services independent of the default implementation, allows applications to swap behavior at configuration boundaries, and still leverages the conventions Spring Boot provides.
