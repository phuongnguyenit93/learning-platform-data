# @Import and Splitting Configuration by Responsibility

As a Spring Boot application grows, a single configuration class can accumulate too many things: shared utility bean declarations, database integration, HTTP client configuration, security, message processing, and module-specific features. Such a class becomes hard to read, hard to test in isolation, and prone to unintended changes when adding a feature.

Spring Framework provides the **`@Import`** annotation to compose configuration classes into a single application context. You can split configuration by responsibility into small classes, then explicitly declare which class needs to load which other classes. This organization preserves the explicitness of Java configuration while avoiding cramming every bean into one file.

Core idea:

~~~text
                 ApplicationConfiguration
                           |
                 @Import configurations
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   DataConfiguration  WebConfiguration  SecurityConfiguration
          |                |                |
       DataSource       Web client       Security rules
       Repositories     MVC/WebFlux      Filter chains
          |
          v
   Beans registered in the same ApplicationContext
~~~

`@Import` does not create a separate container per configuration class. Imported configurations participate in building **the same application context**, so beans in one configuration can be injected into beans in another configuration when registration conditions allow.

## 1. The Problem with Piling All Configuration into One Class

A configuration class may start out simple:

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    RestClient externalRestClient() {
        return RestClient.builder().build();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }
}
~~~

As the number of beans grows, this class knows too many details across unrelated areas. A change to external integration configuration forces readers to scan past security and order business rules as well. Beans also become harder to group under separate conditions or profiles.

We can split by responsibility:

~~~text
config/
├── ApplicationConfiguration.java
├── TimeConfiguration.java
├── SecurityConfiguration.java
├── ExternalClientConfiguration.java
└── OrderConfiguration.java
~~~

Each class describes a cohesive group of configuration. The root class is simply responsible for assembling the needed groups:

~~~java
@Configuration
@Import({
    TimeConfiguration.class,
    SecurityConfiguration.class,
    ExternalClientConfiguration.class,
    OrderConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

As a result, each configuration group can be read and tested with focus. However, do not split every single bean into its own class just to shrink line counts; a configuration class should represent **a meaningful responsibility or configuration boundary**.

## 2. Basic Syntax of @Import

`@Import` belongs to the `org.springframework.context.annotation` package:

~~~java
import org.springframework.context.annotation.Import;
~~~

The annotation accepts one or more classes:

~~~java
@Configuration
@Import({
    DatabaseConfiguration.class,
    MessagingConfiguration.class
})
public class ApplicationConfiguration {
}
~~~

When Spring processes `ApplicationConfiguration`, it also processes the configurations specified in `@Import`. Those configuration classes can in turn import other configurations, forming a configuration graph:

~~~text
ApplicationConfiguration
  ├── DatabaseConfiguration
  │     └── JpaConfiguration
  └── MessagingConfiguration
        └── RetryConfiguration
~~~

You do not need to place imported classes in the same package as the root class. They just need to be on the classpath and specified by class. Importing is **explicit by class**, not an automatic scan of all subpackages.

### 2.1. Using @Import Directly on the Spring Boot Startup Class

Because `@SpringBootApplication` is already a configuration source, you can place `@Import` directly on the main class:

~~~java
package com.example.orders;

import com.example.orders.config.PersistenceConfiguration;
import com.example.orders.config.SecurityConfiguration;
import com.example.orders.config.TimeConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import({
    PersistenceConfiguration.class,
    SecurityConfiguration.class,
    TimeConfiguration.class
})
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

This works well when the list of additional configurations is small and the main class stays readable. If the import list grows long, you can create an aggregate class like `OrdersModuleConfiguration` to keep the main class concise.

### 2.2. How Should Imported Classes Declare Configuration?

Typically, an imported class is a `@Configuration` class:

~~~java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

`@Configuration` marks the class as a Spring configuration source. The `@Bean` methods inside are processed to register bean definitions.

`@Import` can also import regular components and supports extension points such as `ImportSelector` or `ImportBeanDefinitionRegistrar`. For ordinary application configuration, prefer importing a `@Configuration` class so intent remains clear and easy to follow.

## 3. Example of Splitting Configuration by Responsibility

Suppose an order management application has three infrastructure areas: system time, HTTP client, and order policy.

### 3.1. Time Configuration

~~~java
package com.example.orders.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Services needing time can inject `Clock`. Using a bean makes it easy to test with a fixed clock instead of depending directly on `Instant.now()` inside business logic.

### 3.2. HTTP Client Configuration

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient() {
        return RestClient.builder()
                .baseUrl("https://partner.example")
                .build();
    }
}
~~~

In a real project, the base URL should come from externalized configuration such as `@ConfigurationProperties`, rather than hardcoding an environment address. The example focuses purely on illustrating where beans are declared.

### 3.3. Order Policy Configuration

~~~java
package com.example.orders.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    OrderPolicy orderPolicy(Clock applicationClock) {
        return new OrderPolicy(applicationClock);
    }
}
~~~

The `applicationClock` parameter is resolved by Spring from the bean provided by `TimeConfiguration`. This is the clean way to express dependencies across configurations and beans: no need to call factory methods on another configuration class directly.

### 3.4. Combining Configuration Groups

~~~java
package com.example.orders.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    TimeConfiguration.class,
    PartnerClientConfiguration.class,
    OrderConfiguration.class
})
public class OrdersModuleConfiguration {
}
~~~

And the main class:

~~~java
package com.example.orders;

import com.example.orders.config.OrdersModuleConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(OrdersModuleConfiguration.class)
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

On startup, the imported configurations are processed within the application context. The `applicationClock`, `partnerRestClient`, and `orderPolicy` beans can be injected by other beans unless conditions or exclusions prevent them.

In this example, `OrderPolicy` and related types are assumed to be application-defined classes. The illustrative configuration snippets can be placed in separate files matching their packages.

## 4. How Does @Import Differ from @ComponentScan?

Both annotations can cause beans to appear in the context, yet how they select classes differs.

| Criterion | `@ComponentScan` | `@Import` |
|---|---|---|
| How components are chosen | Searches for stereotyped classes in packages and subpackages within scan scope | Directly specifies classes or a class-selection mechanism |
| Scope | By package, filters, and scan configuration | By explicit list of classes/selectors |
| Best suited for | Auto-discovering controllers, services, repositories, and components | Composing known configuration modules |
| Scans subpackages? | Yes, from base packages | No; importing a class does not scan that class's package |
| Explicitness | Package scope determines many discovered classes | Import list explicitly shows which configuration modules are assembled |

Example:

~~~java
@Configuration
@ComponentScan("com.example.orders.feature")
public class FeatureScanConfiguration {
}
~~~

Spring scans `com.example.orders.feature` and its subpackages for matching components.

Meanwhile:

~~~java
@Configuration
@Import(FeatureConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Spring processes the specified `FeatureConfiguration` class. It does not automatically scan every `@Service` or `@Component` sitting next to that class.

The two mechanisms can be combined: a configuration imports a module configuration, and that module configuration declares a scoped component scan if that fits the module's design. Define boundaries clearly to avoid duplicate scanning or accidentally registering unintended components.

## 5. @Import Is Not @ImportResource

Spring supports multiple ways to assemble configuration:

- `@Import`: composes Java configurations or imports components via selectors/registrars.
- `@ImportResource`: loads bean definitions from XML configuration resources.
- `@ComponentScan`: automatically discovers components by package.

Example of importing XML:

~~~java
@Configuration
@ImportResource("classpath:/legacy/legacy-beans.xml")
public class LegacyIntegrationConfiguration {
}
~~~

`@ImportResource` is useful when integrating a legacy system that still has XML bean definitions. For new Java configurations, `@Import` is usually more direct and refactoring-friendly.

Do not use `@ImportResource` just because its name starts with "Import"; it handles a different kind of resource than `@Import`.

## 6. Splitting Configuration by Responsibility and Module Boundaries

Splitting configuration should reflect meaningful technical or business boundaries. Example:

~~~text
com.example.orders
├── OrdersApplication.java
├── config
│   ├── OrdersModuleConfiguration.java
│   ├── PersistenceConfiguration.java
│   ├── PartnerClientConfiguration.java
│   └── SecurityConfiguration.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   └── OrderRepository.java
└── customer
    ├── CustomerController.java
    ├── CustomerService.java
    └── CustomerRepository.java
~~~

Some boundaries to consider:

| Configuration group | Typical contents |
|---|---|
| Persistence | Data source, entity manager, repository scanning, transaction manager when custom setup is needed |
| External clients | HTTP clients, messaging clients, timeout/retry policies |
| Security | Filter chains, authentication providers, method security |
| Serialization | JSON mappers, message converters, or specialized serializers |
| Scheduling | Schedulers, task executors, and schedule configuration |
| Feature/module | Beans serving a specific feature or business module only |

Not every group needs its own configuration class. If Spring Boot already auto-configures something properly and the application needs no customization, do not create a configuration class just to repeat defaults.

### 6.1. A Module Self-Describes Its Needed Configuration

A module can expose a composite configuration class:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    OrderDomainConfiguration.class,
    OrderPersistenceConfiguration.class,
    OrderIntegrationConfiguration.class
})
public class OrderModuleConfiguration {
}
~~~

The host application can import this module:

~~~java
@SpringBootApplication
@Import(OrderModuleConfiguration.class)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

This gives the application a clear entry point to enable the module. The module can also split internal details into smaller configuration classes without forcing the host application to import every class individually.

If a module is a library reused across multiple applications, define its public configuration API clearly. Do not force host applications to import internal classes that the module may change at will.

## 7. @Import and @Bean: Avoiding Accidental Direct Factory Method Calls

One point to understand when splitting configuration is how Spring handles calls between `@Bean` methods.

### 7.1. Full @Configuration Mode

By default, `@Configuration` has `proxyBeanMethods = true`. Spring creates a proxy/subclass mechanism so that when one `@Bean` method in the same configuration class calls another `@Bean` method, the call is routed through the container to return the managed bean rather than creating an unmanaged object.

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(applicationClock());
    }
}
~~~

In full configuration mode, calling `applicationClock()` from `orderPolicy()` is handled by the proxy as a bean request, so it receives the registered `Clock` bean. This is special behavior of proxied configuration, not normal Java call semantics.

### 7.2. Lite Mode with proxyBeanMethods = false

If configured with:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy(applicationClock());
    }
}
~~~

then calling `applicationClock()` inside `orderPolicy()` is a **regular Java call**. It may create a different `Clock` instead of retrieving the registered bean from the context. This can violate expectations around identity, scope, or lifecycle.

A safer and clearer way to write it:

~~~java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    OrderPolicy orderPolicy(Clock applicationClock) {
        return new OrderPolicy(applicationClock);
    }
}
~~~

Spring resolves the `Clock applicationClock` parameter automatically and passes the matching bean into the factory method. This works cleanly in both full and lite configuration modes while exposing dependencies in the method signature.

When splitting configuration into multiple classes and importing them, **prefer method parameter injection** between beans rather than calling `@Bean` methods directly on another configuration class.

## 8. Combining @Import with Profiles and Conditions

Not every configuration module should load in every environment. You can attach conditions to imported configuration classes.

### 8.1. @Profile

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("development")
public class DevelopmentToolsConfiguration {

    @Bean
    DemoDataLoader demoDataLoader() {
        return new DemoDataLoader();
    }
}
~~~

The application can import this class:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(DevelopmentToolsConfiguration.class)
public class ApplicationConfiguration {
}
~~~

If the `development` profile is not active, that configuration does not contribute its beans to the context. If it is active, the corresponding beans are registered.

### 8.2. Spring Boot Conditions

In Boot applications, `@ConditionalOnProperty` can enable a module based on configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

In `application.yml`:

~~~yaml
feature:
  audit:
    enabled: true
~~~

The condition is evaluated while building the context. If the property does not match, the `auditPublisher` bean is not registered from that configuration.

### 8.3. Conditionals Do Not Replace Import Boundaries

`@Import` decides which configurations enter processing; `@Profile` or `@Conditional...` decides whether the configuration/bean meets the criteria to be registered. The two mechanisms complement each other:

~~~text
ApplicationConfiguration
       |
       +-- @Import(AuditConfiguration)
                     |
                     v
          Evaluate @ConditionalOnProperty
                /             \
              True            False
               |                |
               v                v
         Register bean     Skip bean
~~~

Do not expect explicit importing to bypass configuration conditions; conditions still apply during processing.

## 9. ImportSelector and DeferredImportSelector

When the list of configurations to import depends on metadata or a programmatic decision, Spring provides `ImportSelector`:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class StorageImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
                "com.example.storage.JpaStorageConfiguration"
        };
    }
}
~~~

Using the selector:

~~~java
@Configuration
@Import(StorageImportSelector.class)
public class StorageModuleConfiguration {
}
~~~

The selector returns the class names to import. In this example, it always chooses the JPA configuration; a real implementation might read annotation metadata from the importing class or decide via an appropriate rule.

`DeferredImportSelector` is a variant that defers import selection until a later stage of configuration analysis. It is used in Spring Boot's auto-configuration mechanisms, where processing order and conditions across configurations matter.

Do not write a custom selector merely to replace a fixed import list. For a few known configurations, `@Import({A.class, B.class})` is simpler and easier to read.

## 10. When Is ImportBeanDefinitionRegistrar Used?

`ImportBeanDefinitionRegistrar` is a lower-level extension point that lets you register bean definitions directly into the registry during configuration processing:

~~~java
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class ClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(GeneratedClient.class);

        registry.registerBeanDefinition("generatedClient", definition);
    }
}
~~~

Registering the registrar:

~~~java
@Configuration
@Import(ClientRegistrar.class)
public class ClientModuleConfiguration {
}
~~~

This example illustrates registering a bean definition by name. In practice, registrars are typically used when libraries need to generate multiple beans from metadata, annotations, interfaces, or custom conventions. You must check for existing bean names and registry constraints to avoid conflicts.

`ImportBeanDefinitionRegistrar` is more powerful than ordinary `@Bean` declarations, but it also makes configuration more complex. Only use it when dynamic bean-definition-level registration is genuinely needed; for application configuration, `@Configuration` + `@Bean` + `@Import` is usually sufficient.

## 11. @Import and Spring Boot Auto-Configuration

Spring Boot uses an import mechanism to assemble auto-configurations. Libraries can publish a list of auto-configuration classes in the resource file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

When `@EnableAutoConfiguration` (included in `@SpringBootApplication`) is active, Boot locates configurations registered via its mechanism, then evaluates conditions such as:

- `@ConditionalOnClass`: required classes are on the classpath.
- `@ConditionalOnMissingBean`: the application has not already provided a matching bean.
- `@ConditionalOnProperty`: matching property value.
- `@ConditionalOnWebApplication`: matching web application type.

This is how starters and integration libraries supply conditional defaults. **Do not equate importing application configuration with `@Import` and Boot's auto-configuration discovery mechanism**: the two share underlying configuration-class processing foundations, yet their goals and registration conventions differ.

If you merely want to compose an application-written `SecurityConfiguration`, `@Import(SecurityConfiguration.class)` is enough. There is no need to create an `AutoConfiguration.imports` file for an internal configuration used only by a single application.

## 12. Managing Order and Dependencies Across Configurations

The order of classes listed in `@Import` should not be used as a mechanism to orchestrate bean lifecycles. Spring processes configurations by parsing and registering bean definitions; actual instance creation timing still depends on dependencies, lazy/eager initialization, and lifecycle rules.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    DatabaseConfiguration.class,
    OrderConfiguration.class
})
class ApplicationConfiguration {
}
~~~

Do not assume that just because `DatabaseConfiguration.class` is listed first, every database bean will initialize before all beans in `OrderConfiguration`. If `OrderPolicy` needs a `DataSource` or repository, express that dependency in the `@Bean` method or bean constructor.

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

Spring resolves dependencies and ensures required beans are supplied according to the dependency graph. If there truly is a special initialization order requirement that cannot be expressed as a dependency, consider a lifecycle mechanism like `@DependsOn`, but never use it to replace dependency injection.

### Avoiding Circular Imports Between Configurations

If `AConfiguration` imports `BConfiguration` and `BConfiguration` imports `AConfiguration`, the structure becomes confusing and can cause issues during configuration analysis. It is better to define a higher-level configuration as the composition root:

~~~text
ApplicationConfiguration
  ├── AConfiguration
  └── BConfiguration
~~~

If two modules genuinely need to share a bean, move that bean into a foundational configuration or shared module with clear boundaries, and have both modules depend on the shared abstraction.

## 13. Testing Imported Configurations

Because imported configurations are processed in the same context, you can test the composition root with Spring Test or a small context.

Example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class OrdersModuleConfigurationTest {

    @Test
    void importsModuleBeans() {
        try (var context = new AnnotationConfigApplicationContext(
                OrdersModuleConfiguration.class)) {

            assertThat(context.getBean(Clock.class)).isNotNull();
            assertThat(context.getBean(OrderPolicy.class)).isNotNull();
        }
    }
}
~~~

This test assumes the configurations properly declare the beans and all required dependencies can be created. `AnnotationConfigApplicationContext` lets you test Java configuration without starting an entire web server.

For a Boot application, `@SpringBootTest` can verify that the composition root integrates with auto-configuration and other components:

~~~java
@SpringBootTest
class OrdersApplicationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void moduleConfigurationIsLoaded() {
        assertThat(context.getBean(Clock.class)).isNotNull();
    }
}
~~~

In real tests, use appropriate assertions and ensure database, security, and external client configurations do not depend on external environments unintentionally. Never spin up production connections just to test that a configuration class was imported.

### Testing Conditional Configurations

If a configuration uses `@Profile` or `@ConditionalOnProperty`, write tests for both enabled and disabled branches:

| Scenario | What to verify |
|---|---|
| Profile enabled | Beans belonging to the configuration are registered |
| Profile disabled | Optional beans do not appear |
| Property enabled | The feature is activated |
| Property disabled/missing | The feature is skipped according to declared semantics |
| Custom bean already exists | Auto-configuration or default configuration backs off as designed |

## 14. Common Mistakes When Using @Import

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Bean in configuration class does not appear | Class was not imported, is not a suitable configuration candidate, or condition did not match | Check imports, annotations, and conditions/profiles |
| Imported class reported not found | Class is not on compile/runtime classpath or wrong package | Check dependencies and fully qualified class name |
| Duplicate bean names | Two configurations register beans with the same name | Name explicitly, remove duplicate config, or use appropriate conditions |
| Calling a `@Bean` method creates an unexpected new object | Configuration uses lite mode or cross-class calls bypass the proxy | Inject beans via method/constructor parameters |
| Changing `@Import` order does not yield expected initialization order | Confusing import order with dependency/lifecycle order | Declare dependencies explicitly; use `@DependsOn` only when truly needed |
| Configurations import each other circularly | Unclear module boundaries, bidirectional dependency | Introduce a composition root or shared module |
| Expecting `@Import` to scan an entire package | Confused with `@ComponentScan` | Import specific classes or declare a component scan with an explicit base package |
| XML is not loaded | Used `@Import` for XML resources | Use `@ImportResource` |

When you need to know why a Boot auto-configuration was enabled or skipped, enable the condition evaluation report with `debug=true` or `--debug`. When you need to see which beans actually exist in the context, inspect `ApplicationContext` or the Actuator `beans` endpoint if enabled and properly secured. These tools help distinguish import, component scan, condition, and dependency issues.

## 15. Principles for Maintainable Configuration Splitting

**Split by responsibility, not by bean count.** A database configuration may hold many tightly related beans; a single bean may still warrant its own class if it represents an optional module with clear boundaries.

**Keep the composition root readable.** A top-level class like `OrdersModuleConfiguration` shows which configuration groups the application assembles. When the import list gets long, create module-level configuration groups.

**Prefer dependency injection between beans.** Use constructor parameters or `@Bean` method parameters instead of calling factory methods on other configuration classes directly.

**Limit component scanning.** Use `@Import` for known module configurations; use `@ComponentScan` when you genuinely want package-based stereotype discovery. Do not widen scan scope to an overly broad namespace just to make one bean appear.

**Keep conditions close to the feature.** `@Profile` or `@ConditionalOnProperty` should clearly state when a module/configuration is enabled. Avoid forcing the composition root to contain detailed conditional branches for every module.

**Do not rely on import order to control initialization.** Express required relationships using Spring's dependency graph.

**Only use advanced extension points when needed.** `ImportSelector` fits dynamic configuration selection; `DeferredImportSelector` fits deferred selection; `ImportBeanDefinitionRegistrar` fits low-level bean definition registration. For a fixed list, the plain `@Import` annotation is enough.

`@Import` helps build Java configuration through composition: each class owns a group of beans, while a higher-level class combines the needed groups into the same application context. When combined properly with component scanning, conditional configuration, and dependency injection, a Spring Boot application can scale across multiple modules while keeping configuration clear, testable, and easy to evolve.
