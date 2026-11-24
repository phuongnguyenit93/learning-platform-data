# Importing Configuration Classes with `@Import` in Spring Core Container

## 1. The Problem: An Application Needs Multiple Java Configuration Classes

A small Spring application can place all factory methods inside a single `@Configuration` class. As the system grows, code is usually separated by responsibility: repositories, business logic, infrastructure, and optional features. When initializing `ApplicationContext`, how do you compose these configurations without manually registering every class at every startup point?

Spring supports the `org.springframework.context.annotation.Import` annotation. For example:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {
    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {
    @Bean
    CustomerService customerService(CustomerRepository repository) {
        return new CustomerService(repository);
    }
}
```

This is an **illustrative snippet**, not a standalone runnable Java file: `CustomerRepository`, `InMemoryCustomerRepository`, and `CustomerService` are application types that must be defined. When `ServiceConfig` is registered with the Spring container, `@Import(RepositoryConfig.class)` causes Spring to **also process `RepositoryConfig`**, including the bean definition of `customerRepository()`. The factory method parameter `CustomerRepository repository` is resolved by the container according to dependency injection rules.

Key point: `@Import` **composes configuration sources explicitly**. It does not mean “call a class's constructor immediately”, nor does it mean “scan every class in the imported package”.

This lesson focuses on:

1. `@Import` syntax with one or more configuration classes and creating a single entry point.
2. Bean definitions, dependency relationships, and transitive imports.
3. Importing **regular component classes**, not only `@Configuration`.
4. Differences between `@Import`, `@ComponentScan`, `@Bean`, `@ImportResource`, and `@Enable...`.
5. Extending imports with `ImportSelector`, `DeferredImportSelector`, and `ImportBeanDefinitionRegistrar`.
6. Usage in modular applications, conditional features, testing, and troubleshooting.
7. A runnable Java 17+ project on Spring Framework 6.2 with Gradle structure and expected stdout.

## 2. What Is `@Import`?

`@Import` is an annotation declared at the **type level**. It accepts a `Class<?>` array, which can specify one class or multiple classes:

```java
@Import(DatabaseConfig.class)
```

```java
@Import({DatabaseConfig.class, ServiceConfig.class, MetricsConfig.class})
```

When a configuration annotated with `@Import` is processed by Spring, the import candidates are added to configuration class processing and bean definition registration. In Spring Framework 6.2, `@Import` supports four common groups:

| Object Passed to `@Import` | What Spring Does | Purpose |
| --- | --- | --- |
| `@Configuration` class | Processes the configuration class, registering `@Bean` methods and related metadata | Compose statically declared configurations |
| Regular component class | Registers the class as an appropriate component/bean definition without component scanning | Explicitly select application classes to bring into the container |
| `ImportSelector` implementation | Invokes the selector to determine which classes to import based on metadata/configuration | Select configurations conditionally or by annotation attributes |
| `ImportBeanDefinitionRegistrar` implementation | Allows programmatic bean definition registration against `BeanDefinitionRegistry` | Infrastructure extension point requiring registry-level control |

Since Spring Framework 4.2, `@Import` can import **regular component classes**, similar in spirit to registering a class via `AnnotationConfigApplicationContext.register(...)`. Thus, the imported target does not always have to be `@Configuration`.

**What is not a direct function of `@Import`:** importing XML resources as bean definitions. For XML or other supported bean definition resources, the related mechanism is `@ImportResource`. Nor can you pass a package string to `@Import`: this annotation requires concrete `Class<?>` tokens.

### 2.1. `@Import` Is Configuration Composition, Not a Java `import` Statement

Both syntaxes contain the word “import”, but their roles are different:

```java
import com.example.storage.StorageConfig;  // Java compiler: use class name.

@Import(StorageConfig.class)               // Spring: add config to container.
```

The Java `import` statement at the top of a source file only helps the compiler resolve type names; it **does not register beans**. Spring `@Import` actually participates in the container's bean definition parsing phase.

### 2.2. When Does the Import Process Occur?

A high-level flow:

```text
new AnnotationConfigApplicationContext(AppConfig.class)
                         |
                         v
           Register AppConfig as entry point
                         |
                         v
        Process @Configuration and @Import
                         |
          +--------------+--------------+
          |                             |
          v                             v
     @Bean of AppConfig           Import classes
                                        |
                     +------------------+--------------------+
                     |                  |                    |
                     v                  v                    v
                @Configuration     ImportSelector    Regular component
                     |                  |                    |
                     v                  v                    v
                  @Bean defs      Config candidates      Bean definition
                     |
                     +------------------+--------------------+
                                        |
                                        v
                           BeanFactory/registry
                                        |
                                        v
                        DI, instantiation, lifecycle
```

Spring resolves imports and creates **bean definitions** during configuration processing. Afterward, bean instances are created according to scope/lazy rules and the dependency graph. Do not conclude that the order of classes in the `@Import` array is the bean initialization order, or that every imported class constructor is invoked immediately when reading the annotation.

## 3. Composing Two Configuration Classes and Declaring Cross-Config Dependencies

Consider two configuration classes:

```java
@Configuration(proxyBeanMethods = false)
class PersistenceConfig {

    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(PersistenceConfig.class)
class ApplicationConfig {

    @Bean
    InventoryService inventoryService(InventoryRepository repository) {
        return new InventoryService(repository);
    }
}
```

The domain types in the snippet are defined in the real application. You only need to pass `ApplicationConfig` to `AnnotationConfigApplicationContext`; `PersistenceConfig` will be processed thanks to `@Import`.

**The dependency relationship is resolved by Spring via the factory-method parameter**, not by a Java call to `inventoryRepository()` from another config. `InventoryService` can use a Spring-managed singleton repository; there is no need to inject `PersistenceConfig` itself into `ApplicationConfig`.

This approach works cleanly with `@Configuration(proxyBeanMethods = false)`. In lite mode, a direct Java call to a `@Bean` method has no CGLIB inter-bean interception mechanism; whereas a dependency parameter is still resolved by the BeanFactory with proper container semantics.

### 3.1. Each Bean Has Its Own Name and Scope

`@Import` does not merge all factory methods of different classes into “one bean”. Each `@Bean` method is processed into a separate bean definition with its own bean name/qualifier/scope depending on configuration. The default name of a bean created by a `@Bean` method is typically **the method name**, for example `inventoryRepository`.

Once the context exists:

```java
InventoryRepository repository = context.getBean(InventoryRepository.class);
InventoryService service = context.getBean(InventoryService.class);
```

This is an illustrative snippet assuming `context` has already been created. With the default singleton scope, Spring typically returns the same instance each time it resolves by bean name/type within the same BeanFactory.

### 3.2. Transitive Imports

An imported class can itself carry `@Import`:

```java
@Configuration
@Import(PersistenceConfig.class)
class ServiceConfig {
}

@Configuration
@Import(ServiceConfig.class)
class MainConfig {
}
```

This is illustrative code. Registering `MainConfig` causes Spring to process the import structure passing through `ServiceConfig` to `PersistenceConfig`. That helps organize **intentional configuration sets**, rather than forcing application main to know every granular config.

Do not create an import cycle A → B → A. Spring's configuration processor detects invalid import cycles and can report an error; cyclic import complexity also blurs module ownership. If two modules need each other, prefer extracting shared parts or adjusting the dependency direction.

### 3.3. Importing a Configuration Class Multiple Times

A config can be referenced from multiple points in the import graph. Spring's configuration processing handles duplicate candidates to avoid pointlessly re-registering the same configuration in normal cases. **Do not rely on repeated imports expecting to create two singleton instances.** If you want two differently configured beans from the same implementation, declare two intentional bean definitions with different names/parameters.

Also avoid `@Bean` name collisions between incompatible configuration classes. Even across two different classes, two `@Bean service()` methods default to the same bean name `service`; the bean overriding policy may cause one definition to replace the other or raise an error. Use distinct names when responsibilities differ and test the registry.

## 4. `@Import` vs. `@ComponentScan`: Choosing by Boundary

Both annotations can result in Spring adding bean definitions, but they solve two different problems.

| Criterion | `@Import` | `@ComponentScan` |
| --- | --- | --- |
| Input declaration | Specific classes, selectors, or registrars | One or more base packages plus filters |
| Need to know each class? | With static imports, yes | No need to list every component |
| Opens up an entire package? | No | Yes, including subpackages |
| Fits libraries/integration points | Yes, public configuration entry point | Yes, if the app intentionally manages an entire package |
| Effect of adding a new `@Component` class in package | No automatic new bean unless registered via another source | The new class may be scanned and registered |
| Dynamic conditions/selectors | `ImportSelector` / conditional metadata | Filters/conditions and other mechanisms |
| Can be combined | Yes | Yes |

Example selecting **a specific** component:

```java
@Configuration
@Import(EmailGateway.class)
class MessagingConfig {
}
```

If `EmailGateway` is a regular class with an appropriate constructor, Spring can register it via `@Import` without scanning the whole package containing the gateway. `EmailGateway` does not need to be annotated with `@Component`; see the runnable example in section 8.

With package scanning:

```java
@Configuration
@ComponentScan(basePackages = "com.example.messaging")
class MessagingConfig {
}
```

The scanner looks at component candidates in `com.example.messaging` and subpackages, not just `EmailGateway`.

### 4.1. In Multi-Module Applications

A clean structure:

```text
app/
  AppConfig.java               -> @Import({StorageModuleConfig, OrderModuleConfig})
storage/
  StorageModuleConfig.java     -> exposes storage beans
  internal/...
orders/
  OrderModuleConfig.java       -> exposes orders beans
  internal/...
```

`@Import` supports an architecture where **each module provides a configuration entry point** and the application chooses which modules join the container. This avoids accidentally scanning an entire library package just because its JAR is on the classpath.

However, importing a configuration class that contains `@ComponentScan` inside **can still trigger that scan**. Therefore, `@Import` does not automatically restrict which beans the imported config registers. You need to inspect the imported configuration to know its actual scope.

### 4.2. Component Scan Does Not Replace Explicit Module Imports

In Spring Boot, placing `@SpringBootApplication` in the root package can scan components underneath. However, not every library wants users scanning its internal packages. A library can provide a configuration for the app to `@Import`, or provide Spring Boot auto-configuration by its own convention.

**Do not equate component scanning with Spring Data repository scanning or JPA entity scanning.** Those systems have different extension points and scan regions. `@Import`ing a configuration class can activate `@EnableJpaRepositories`, but `@Import` itself does not automatically turn every `Repository` interface in the project into a repository proxy.

## 5. Importing Regular Component Classes

Spring Framework 6.2's `@Import` Javadoc allows importing regular component classes, not necessarily `@Configuration`. This provides an explicit registration path:

```java
class HealthProbe {
    String status() {
        return "ok";
    }
}

@Configuration
@Import(HealthProbe.class)
class AppConfig {
}
```

This is an illustrative snippet. When registering `AppConfig`, Spring can create a `HealthProbe` bean even without `@ComponentScan` and without `HealthProbe` carrying a stereotype. As long as the class can be instantiated and its dependencies are valid, a caller can do:

```java
HealthProbe probe = context.getBean(HealthProbe.class);
```

The bean name of an imported class follows the registration type and the configuration processor's `BeanNameGenerator`; do not assume the exact name is always `healthProbe` like the default component scanner. If you do not need an explicit name, **lookup by type** is usually less brittle.

### 5.1. An Interface Does Not Automatically Become an Implementation

`@Import(MyPort.class)` where `MyPort` is a plain interface does not create a usable implementation. You must import a concrete implementation or a configuration/factory/registrar that creates a suitable object. An abstract class also cannot be instantiated normally by the container just because it appears in `@Import`.

### 5.2. Importing a Class with Constructor Dependencies

Spring can resolve constructor injection for an imported regular component class according to the container's bean creation capabilities. For example:

```java
public class AuditReporter {
    private final AuditStorage storage;

    public AuditReporter(AuditStorage storage) {
        this.storage = storage;
    }
}
```

If `@Import(AuditReporter.class)` is used and an eligible `AuditStorage` bean exists, the container can inject the parameter. If the dependency is missing, you still get a bean creation failure; `@Import` does not automatically supply unregistered types.

### 5.3. Importing Does Not Include the Whole Package

Suppose `EmailGateway` and `SmsGateway` are in the same package. `@Import(EmailGateway.class)` does not automatically register `SmsGateway`. If an imported `@Configuration` enables `@ComponentScan` on that package, then discovering extra beans is the result of **component scanning inside the configuration**, not because `@Import` scans packages itself.

## 6. `ImportSelector`: Dynamic Configuration Selection

For a selector class implementing `org.springframework.context.annotation.ImportSelector`, Spring invokes:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

The selector receives metadata of the class declaring `@Import` and returns **an array of fully qualified class names** to import. It helps create feature-enabling annotations and choose configurations based on attributes/environment or infrastructure rules.

Example:

```java
public class StorageSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { InMemoryStorageConfig.class.getName() };
    }
}
```

This is an illustrative snippet; `ImportSelector`, `AnnotationMetadata`, and `InMemoryStorageConfig` must be imported/present. When used:

```java
@Configuration
@Import(StorageSelector.class)
class AppConfig {
}
```

Spring processes the selector and imports the configuration returned by the selector. In the program in section 8, `PromotionSelector` imports `PromotionConfig` in the same way.

### 6.1. Metadata Enables High-Level Configuration Annotations

A custom annotation can use `@Import` as a **meta-annotation**:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(StorageSelector.class)
public @interface EnableStorage {
}
```

This is an illustrative snippet: imports from `java.lang.annotation.*` along with `@Import` are required. Elsewhere:

```java
@Configuration
@EnableStorage
class AppConfig {
}
```

The selector can then read information from the importing configuration/annotation to decide which classes to import. This is the foundation for writing `@Enable...` annotations whose behavior is managed through configuration imports.

Distinguish **enabling a module via annotation** from **component scanning**; the `@EnableStorage` annotation in the example only imports the selector/config it declares, and does not automatically scan packages beyond whatever further steps are configured.

### 6.2. `DeferredImportSelector`

`DeferredImportSelector` extends `ImportSelector` and allows deferring import selection until after regular configuration classes have been processed. This is an advanced extension point useful for scenarios that choose configurations based on broader context, notably in how auto-configuration is organized.

You do not need `DeferredImportSelector` just to compose two fixed configuration classes. Direct `@Import({AConfig.class, BConfig.class})` is easier to understand and avoids configuration-processing lifecycle complexity.

### 6.3. A Selector Is Not a Regular Business Bean

`ImportSelector` is configuration-processing infrastructure. Do not assume it is registered under a normal bean name to inject into services like a `@Component`. Its purpose is **choosing which classes to import**, not producing business objects via methods on the selector.

## 7. `ImportBeanDefinitionRegistrar`: Registering Bean Definitions Programmatically

If you want to operate at a lower level than `@Bean`, Spring allows classes to implement `org.springframework.context.annotation.ImportBeanDefinitionRegistrar`. A relevant method:

```java
void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry
);
```

An implementation can inspect annotation metadata, create a `BeanDefinition`, and register it into the registry. Example:

```java
public class DiagnosticsRegistrar implements ImportBeanDefinitionRegistrar {
    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(DiagnosticsClient.class);
        registry.registerBeanDefinition("diagnosticsClient", definition);
    }
}
```

This is an illustrative snippet requiring the following imports:

```java
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;
```

And a `DiagnosticsClient` class with a valid constructor/metadata is needed. In the application:

```java
@Configuration
@Import(DiagnosticsRegistrar.class)
class AppConfig {
}
```

Spring can register the `diagnosticsClient` bean definition. A registrar lets you declare beans based on metadata without writing fixed factory methods in source code for each one.

**Important lifecycle limitation:** according to the Spring 6.2 Javadoc, do not register `BeanDefinitionRegistryPostProcessor` types arbitrarily through `ImportBeanDefinitionRegistrar` because of configuration class processing lifecycle constraints. When an infrastructure post-processor is needed, choose the framework-recommended infrastructure registration mechanism.

### When Should You Use a Registrar?

- A framework/library building a configuration abstraction with custom annotations.
- Needing to register a variable number of bean definitions driven by metadata.
- Wanting programmatic control over bean names, implementation types, constructor/factory metadata, or registry-level conditions.

**Do not prefer a registrar for two concrete objects.** If you only need `Repository` and `Service`, `@Configuration` with clear `@Bean` methods is usually easier to read, debug, and test.

### 7.1. Difference from Selector

| Mechanism | Primary Output |
| --- | --- |
| `@Import(SomeConfig.class)` | Imports the configuration class directly |
| `ImportSelector` | Returns class names for Spring to continue processing imports |
| `DeferredImportSelector` | Selects imports at a deferred phase |
| `ImportBeanDefinitionRegistrar` | Registers bean definitions directly in the registry |

A selector returns **class names to import**; a registrar works with **bean definitions**. Avoid writing a selector that tries to return a bean name instead of a class name; Spring requires valid class names to process.

## 8. Runnable Example: Java 17+, Spring 6.2, and a Single Entry-Point `@Import`

The complete project below registers only **one** configuration class into `AnnotationConfigApplicationContext`. Spring will process:

- `@Import` bringing in two configuration classes: `RepositoryConfig` and `BusinessConfig`.
- `@Import` bringing in a regular class `HealthProbe` even though it has no `@Component`.
- `PromotionSelector` implementing `ImportSelector` and selecting `PromotionConfig`.
- `BusinessConfig` creating `CheckoutService` from beans provided by the other configurations.
- An `UnscannedHelper` class annotated with `@Component` that is **neither imported nor covered by any scan**, so it does not appear in the context.

The example requires no Spring Boot, web server, XML, or database.

### 8.1. File Structure

```text
spring-import-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ImportCompositionDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-import-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ImportCompositionDemo'
}
```

Use JDK 17 or higher and a Gradle version compatible with that JDK. `spring-context` pulls in the required Spring Beans/Core modules; there is no need to add `spring-boot` to use `@Import`.

### 8.2. Full Java Code

Save to `src/main/java/ImportCompositionDemo.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;
import org.springframework.stereotype.Component;

public class ImportCompositionDemo {

    public record CatalogRepository(String source) {
        String find() {
            return source;
        }
    }

    public record DiscountPolicy(int percent) {
    }

    public record CheckoutService(
            CatalogRepository repository,
            DiscountPolicy discountPolicy) {

        int total(int price) {
            return price - price * discountPolicy.percent() / 100;
        }

        String summary() {
            return repository.find() + ":" +
                    discountPolicy.percent() + "%";
        }
    }

    public record AppTag(String text) {
    }

    // Regular class, without @Component.
    public static class HealthProbe {
        public HealthProbe() {
        }

        String status() {
            return "ok";
        }
    }

    // Has @Component, but neither scanned nor imported.
    @Component
    public static class UnscannedHelper {
    }

    @Configuration(proxyBeanMethods = false)
    public static class RepositoryConfig {
        @Bean
        CatalogRepository catalogRepository() {
            return new CatalogRepository("catalog");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PromotionConfig {
        @Bean
        DiscountPolicy discountPolicy() {
            return new DiscountPolicy(10);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BusinessConfig {
        @Bean
        CheckoutService checkoutService(
                CatalogRepository repository,
                DiscountPolicy discountPolicy) {
            return new CheckoutService(repository, discountPolicy);
        }
    }

    public static class PromotionSelector implements ImportSelector {
        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {
            return new String[] { PromotionConfig.class.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
            RepositoryConfig.class,
            BusinessConfig.class,
            HealthProbe.class,
            PromotionSelector.class
    })
    public static class AppConfig {
        @Bean
        AppTag appTag() {
            return new AppTag("imported-composition");
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            AppTag tag = context.getBean(AppTag.class);
            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);
            DiscountPolicy policy =
                    context.getBean(DiscountPolicy.class);
            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            HealthProbe probe = context.getBean(HealthProbe.class);

            System.out.println("tag = " + tag.text());
            System.out.println("repository = " + repository.find());
            System.out.println("discount = " + policy.percent() + "%");
            System.out.println("total200 = " + checkout.total(200));
            System.out.println("summary = " + checkout.summary());
            System.out.println("probe = " + probe.status());
            System.out.println("unscannedCandidates = " +
                    context.getBeanNamesForType(UnscannedHelper.class).length);
            System.out.println("sameRepository = " +
                    (repository == checkout.repository()));
        }
    }
}
```

This is a complete Java program: there is only one top-level public class `ImportCompositionDemo`; domain types use Java records, while configurations/selectors/probes are static nested classes. `AppConfig` serves as the composition root.

### 8.3. Run Command and stdout

In the `spring-import-demo` directory:

```bash
gradle run --quiet
```

If using Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Lines produced by `System.out.println` in the program:

```text
tag = imported-composition
repository = catalog
discount = 10%
total200 = 180
summary = catalog:10%
probe = ok
unscannedCandidates = 0
sameRepository = true
```

Note: the example specifies the lines printed by **the program**; Gradle or the logging system may print extra messages not originating from `System.out.println`.

### 8.4. Explaining Each Result

**`tag = imported-composition`**: `AppConfig` is registered directly. Its `@Bean appTag()` method creates the `AppTag` bean.

**`repository = catalog`**: `RepositoryConfig` is statically imported, so the `catalogRepository` bean exists; no `@ComponentScan` is needed.

**`discount = 10%`**: `PromotionSelector` is imported and returns the class name `PromotionConfig`. The `discountPolicy` bean from the selector-chosen configuration can be resolved.

**`total200 = 180`**: `BusinessConfig` is imported; Spring injects `CatalogRepository` and `DiscountPolicy` into the factory method. A price of 200 discounted by 10% becomes 180. `BusinessConfig` does not need to directly call methods on `RepositoryConfig` or `PromotionConfig`.

**`summary = catalog:10%`**: the `CheckoutService` instance holds the exact two dependencies selected by BeanFactory; the record method returns the combined string from the repository and discount policy.

**`probe = ok`**: `HealthProbe` is a regular class without `@Component`. It exists because it is **explicitly listed in `@Import`**, not because of package scanning.

**`unscannedCandidates = 0`**: although `UnscannedHelper` has `@Component`, it is neither scanned nor imported. Adding a stereotype on source code does not automatically turn a class into a bean.

**`sameRepository = true`**: the repository has the default singleton scope in the context, so the bean retrieved directly and the reference received by `CheckoutService` are the same managed instance.

### 8.5. Four Small Exercises for Practice

**Try A:** Remove `RepositoryConfig.class` from `@Import`. Without another registration source, `BusinessConfig.checkoutService(...)` cannot resolve `CatalogRepository`. The context will typically fail on refresh due to a missing required dependency; it cannot proceed to normal stdout.

**Try B:** Remove `PromotionSelector.class` from `@Import` without directly importing `PromotionConfig`. `DiscountPolicy` has no bean left; creating `CheckoutService` will fail.

**Try C:** Replace the selector with `PromotionConfig.class` in the `@Import` list. The output stays the same because the `DiscountPolicy` bean is registered directly from a configuration instead of through a selector.

**Try D:** Add `UnscannedHelper.class` to `@Import`. In the new context, the count of bean names of type `UnscannedHelper` becomes 1 (assuming no other registration path creates another). This proves `@Import` lets you register a specific regular component without enabling component scanning.

## 9. `@Import` in Multi-Module Configuration and Access Levels

In a multi-module Gradle/Maven project, a module can expose a configuration class as a **public entry point**:

```text
order-app
  -> @Import({OrdersModuleConfig.class, PaymentsModuleConfig.class})

orders-module
  -> OrdersModuleConfig (exposes needed @Bean definitions)
  -> internal package (no need to scan everything)

payments-module
  -> PaymentsModuleConfig (exposes payment beans)
  -> internal package (no need to scan everything)
```

### 9.1. The Module Must Be on the Runtime Classpath

`@Import(PaymentsModuleConfig.class)` is a Java `Class<?>` reference. The project build must have a dependency on the module containing this type. If the class cannot be compiled or the module is absent from the runtime classpath, Spring cannot “find the module somewhere” merely from an annotation name.

Gradle multi-project example:

```groovy
dependencies {
    implementation project(':orders-module')
    implementation project(':payments-module')
}
```

This is an illustrative snippet for a build with two declared subprojects. The dependency ensures the proper classpath; `@Import`/other mechanisms decide which bean definitions join the container.

### 9.2. Do Not Expose Too Many Internal Beans

A library module can expose a `@Configuration` containing `@Bean` methods for public services, while private/internal implementation classes carry no stereotypes or are not broadly scanned. That way, the application knows the configuration entry point without needing to know every implementation type.

If an imported config itself scans internal packages using `@ComponentScan`, the effective scope can still be wide. Inspect the composition root, import graph, and filters to avoid accidentally pulling unwanted beans, test helpers/profiles, or alternate adapters into the application.

### 9.3. Scope and Lifecycle Are Still Decided by BeanFactory

Importing does not change the singleton default of `@Bean` methods, does not automatically enable lazy initialization, and does not automatically create AOP proxies or enable transactions. If imported bean `A` needs bean `B`, the relationship must be satisfied by DI resolution just like any bean in the container. Configuration fails if a required dependency is missing or if multiple candidates exist without a clear selection.

### 9.4. Java Platform Module System (JPMS)

If running with `module-info.java` instead of a regular classpath, reflection, constructor access, or CGLIB configuration enhancement may require appropriate `exports`/`opens`. An `InaccessibleObjectException` when instantiating an imported bean is **different** from a bean definition not being imported. Distinguish a successful import from a bean creation failure.

## 10. Conditional Imports and Profiles

An imported configuration class can carry `@Profile` or `@Conditional`:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevStorageConfig {

    @Bean
    Storage storage() {
        return new InMemoryStorage();
    }
}
```

This is an illustrative snippet requiring `Storage`, `InMemoryStorage`, and importing `@Profile`. If the class is imported while the `dev` profile is not active, Spring can skip the class's bean definitions according to profile rules. `@Import` **does not force** every bean inside to appear regardless of conditions.

For a fixed set of configurations, placing conditions directly on imported configurations is usually simpler than writing an `ImportSelector`. A selector makes sense when you need to read custom annotation metadata, select among many module implementations, or build a reusable library/framework.

### 10.1. `@Import` Does Not Establish Initialization Order

`@Import({AConfig.class, BConfig.class})` does not mean “instantiate all beans of A first, then B”. BeanFactory still creates beans based on the dependency graph, scopes, lazy flags, and lifecycle rules. If a service in B needs a repository from A, declare the dependency via `@Bean` parameters or constructors; if there is only a side-effect ordering requirement, look at `@DependsOn` in suitable situations.

### 10.2. Do Not Confuse `@Conditional` with Exception Handling

If an imported bean does not satisfy `@Conditional`, it may not be registered. If another bean unconditionally requires injecting it, the container will still fail with a missing dependency error. `@Import` does not supply a fallback automatically; for an optional module, you must design `Optional<T>`, `ObjectProvider<T>`, conditional consumer beans, or an appropriate fallback configuration.

## 11. `@ImportResource`, XML, and `@Enable...` Annotations

### 11.1. Importing Bean Definitions from XML

`@ImportResource` supports declaring paths to XML or compatible bean definition sources via the corresponding mechanism:

```java
@Configuration
@ImportResource("classpath:/legacy-services.xml")
class LegacyBridgeConfig {
}
```

This is an illustrative snippet; a valid `legacy-services.xml` file and importing `org.springframework.context.annotation.ImportResource` are required. **Do not write `@Import("classpath:/legacy-services.xml")`**, because `@Import` accepts class tokens, not string resource paths.

### 11.2. `@Enable...` Annotations Commonly Use `@Import`

In many Spring extensions, a high-level annotation enables behavior via one or more imported configurations/selectors/registrars. For example, `@EnableTransactionManagement`, `@EnableCaching`, and `@EnableAsync` involve different infrastructure configurations. When you see an `@EnableXxx` annotation, you can inspect its `@Import` metadata or extension implementation to understand which infrastructure bean definitions are activated.

**This does not mean** `@Import` itself turns on transactions or caching. The `@Enable...` annotations, corresponding beans/aspects, proxies, and conditions coordinate to produce the behavior.

### 11.3. `@Import` on Custom Annotations

`@Import` is also supported as a meta-annotation. You can define:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(PaymentsModuleConfig.class)
public @interface EnablePayments {
}
```

This is an illustrative snippet: imports from `java.lang.annotation`, `@Import`, and an existing `PaymentsModuleConfig` are needed. Consumers simply write:

```java
@Configuration
@EnablePayments
class AppConfig {
}
```

This creates an **annotation-based public API** for a module. If there is only a single internal usage site, direct `@Import(PaymentsModuleConfig.class)` may involve less ceremony.

## 12. Common Errors and How to Diagnose Them

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for a bean thought to be imported | Imported config was not processed, skipped by `@Profile`/`@Conditional`, or has no matching `@Bean` | Check context entry point, import graph, profiles, and conditions |
| `ClassNotFoundException`/compile error for an imported config | Wrong module dependency/classpath | Check build/runtime dependencies and class/package names |
| Imported config is present but service creation fails | Factory method needs a dependency missing from the context | Inspect `@Bean` signature, qualifiers, and bean definition sources |
| Two `@Bean` methods in two configs share the name `service` | Bean names collide or get overridden | Give distinct explicit names and review module ownership |
| Multiple beans of the same type after importing a second module | Single injection cannot choose a unique candidate | Use `@Qualifier`/`@Primary` or design collection injection |
| `@Import(SomeClass.class)` does not pull in the whole package | `@Import` registers the specific class; it does not scan packages | Use `@ComponentScan` if you actually want to scan a group of classes |
| `@Component` does not appear without scanning | Component was neither imported nor scanned | Import the specific class, or enable component scanning on the right root |
| `@Import("config.xml")` fails to compile | `@Import` requires `Class<?>` | Use `@ImportResource` for XML |
| Selector fails to import the class | `selectImports` returned a bean name instead of an FQ class name | Return the fully qualified class name (`SomeConfig.class.getName()`) |
| Conditional imported config is skipped | Profile/condition does not match | Check active profiles and `@Conditional` |
| Using `@Import` and expecting A to be created before B by array order | Confusing import order with dependency order | Use factory/constructor parameters, or `@DependsOn` when appropriate |
| Registrar creates duplicate bean names | Registrations are competing for one registry key | Check registry names, generation policy, and duplication |
| Registry post-processor registered at the wrong phase | Misusing `ImportBeanDefinitionRegistrar` for `BeanDefinitionRegistryPostProcessor` | Use the proper lifecycle extension point per Spring documentation |
| Calling `otherConfig.bean()` creates an unmanaged instance | Direct Java method call, especially in lite `@Configuration` | Pass dependencies via factory-method parameters |
| Module is on classpath but bean is absent | JAR presence does not mean beans are imported/scanned | Import the configuration entry point, scan the right package, or use auto-config |
| Module A test passes, real app lacks bean A | Two contexts have different entry points/import graphs | Inspect each context and the exact configuration the test uses |

### 12.1. Practical Debugging Workflow

**Step 1 — Check the configuration entry point.** A `@Configuration` class with `@Import` must actually be registered, scanned, or imported by another configuration. An annotation on a class that Spring never learns about has no effect.

**Step 2 — Map out the import graph.** Write down which configuration classes `AppConfig` leads to, which classes selectors return, and which definitions registrars create. Distinguish direct imports from transitive imports.

**Step 3 — Check bean types/names.** If the context starts up:

```java
String[] names = context.getBeanNamesForType(CheckoutService.class);
System.out.println(java.util.Arrays.toString(names));
```

This is an illustrative snippet when `context` and `CheckoutService` are available. Avoid guessing the bean name of an imported configuration class: bean names are generated by the configuration registration mechanism, which can differ from component scan naming.

**Step 4 — Check conditions and lifecycle.** A bean may be excluded by profile/condition before registration, or registered and then fail during creation. Read the root cause of `BeanCreationException`/`UnsatisfiedDependencyException` to pinpoint the phase.

**Step 5 — Check for conflicts.** If adding a module breaks the context, look for duplicate bean names or interface injection points that previously had one bean and now have two. Do not enable bean definition overriding globally just to mask an unexamined conflict.

**Step 6 — Use a small test context.** As in section 8, register only `AppConfig.class` and verify each bean by type. Apply conditions/profiles matching the target environment when behavior depends on them.

## 13. Practice Exercises with Answers

### Exercise 1 — One or Two Configuration Classes at Startup?

Given `@Configuration @Import(StorageConfig.class) class AppConfig` and `@Configuration class StorageConfig` containing `@Bean Storage storage()`. When creating a context with `new AnnotationConfigApplicationContext(AppConfig.class)`, do you also need to pass `StorageConfig.class`?

**Answer:** No. `AppConfig` already imports `StorageConfig`. Spring processes the bean definitions provided by `StorageConfig`.

### Exercise 2 — Importing a Regular Class

A class `HealthCheck` has no `@Component` and has a public no-arg constructor. `@Configuration @Import(HealthCheck.class) class AppConfig` is registered. Can you look up `HealthCheck` by type?

**Answer:** Yes, provided the import and bean creation succeed. Spring 6.2 supports importing regular component classes without requiring a component scanner.

### Exercise 3 — Sibling Component Next to an Imported Class

`EmailGateway` and `SmsGateway` are in the same package; only `@Import(EmailGateway.class)` is present, with no scanner. Does `SmsGateway` become a bean because it sits in the same package?

**Answer:** Not via that import. `@Import` registers the explicitly listed classes/configurations and does not scan sibling classes.

### Exercise 4 — Cross-Config Dependency

`ServiceConfig` has `@Bean OrderService orderService(OrderRepository repository)`, and `RepositoryConfig` has `@Bean OrderRepository orderRepository()`. Do you need to call `repositoryConfig.orderRepository()` directly?

**Answer:** No. Import/register both configs in the same context and let Spring resolve the `OrderRepository` parameter through the BeanFactory.

### Exercise 5 — What Does ImportSelector Return?

`ImportSelector.selectImports(...)` returns `new String[]{"paymentService"}`, where `paymentService` is only a bean name, not a class FQCN. Is this correct?

**Answer:** No. A selector must return valid import candidate class names; for example, `new String[]{PaymentsConfig.class.getName()}`.

### Exercise 6 — Duplicate `@Bean` Names

Modules A and B both declare `@Bean PaymentClient client()`, and both are imported. What is the concern?

**Answer:** Two bean definitions default to the same name `client`. Depending on registry policy, they may collide/override or instantiate unexpectedly. Use intentional names and avoid overlapping registrations.

### Exercise 7 — Inactive Profile

`@Import(DevMailConfig.class)` is present, `DevMailConfig` has `@Profile("dev")`, and the current environment only activates profile `prod`. Are the `@Bean`s of that config guaranteed to exist?

**Answer:** No. `@Profile` can cause the config to be skipped. Importing does not disable profile conditions.

### Exercise 8 — XML Config

A legacy application still has a `services.xml` file. Should you use `@Import(services.xml)` or `@ImportResource("classpath:/services.xml")`?

**Answer:** Use `@ImportResource` for XML resources. `@Import` is for Java class candidates/selectors/registrars.

### Exercise 9 — Duplicate Imports to Create Two Beans

Two configurations both import a `StorageConfig` containing singleton `StorageClient`. Can you use that to create two independent `StorageClient`s?

**Answer:** You should not and cannot rely on that. Spring deduplicates configuration candidates in the registry; to get two clients you need two distinct bean definitions (for example, two `@Bean` methods with different names/parameters).

### Exercise 10 — Replacing the Selector in the Demo

In section 8, remove `PromotionSelector.class` and add `PromotionConfig.class` to `@Import`. Do the outputs `discount = 10%` and `total200 = 180` change?

**Answer:** No in the demo configuration, because both paths import `PromotionConfig`. The selector only adds selection logic; it does not alter the bean contract of `DiscountPolicy`.

### Exercise 11 — Registrar or `@Bean`?

An application needs exactly two beans `Clock` and `ReceiptFormatter` with fixed implementations. Is it necessary to write an `ImportBeanDefinitionRegistrar`?

**Answer:** No. A `@Configuration` with two clear `@Bean` methods is simpler and more transparent. A registrar should be reserved for infrastructure creating definitions from dynamic metadata/rules.

### Exercise 12 — Replacing Component Scanning with a Module API

A library has 50 implementation classes, and the app only needs 3 public beans exposed by the library's config. Should you widen `@ComponentScan` to the entire internal package or import the public configuration?

**Answer:** When the library has designed a proper entry point, importing the public configuration provides a cleaner boundary. Still, verify whether that configuration scans internal packages or imports other auto-configs.

## 14. Checklist for Designing Safe `@Import` Usage

- Has the root/entry-point configuration **actually been registered with the context**?
- Can you explicitly list the module configurations that need to participate? If so, `@Import({AConfig.class, BConfig.class})` is usually enough.
- Is the imported class a `@Configuration`, regular component, selector, or registrar? Do not mix up each mechanism.
- Do `@Bean` methods across configurations **collide on bean names or types**?
- Are cross-config dependencies expressed via factory-method parameters or constructors?
- Does the imported configuration contain `@ComponentScan`, transitive `@Import`, `@Profile`, `@Conditional`, or notable lifecycle extensions?
- If using a selector, did it return **fully qualified class names** and validate conditions/annotation attributes properly?
- If using a registrar, have bean names been controlled and `BeanDefinitionRegistryPostProcessor` lifecycle constraints respected?
- Is XML needed? If so, use `@ImportResource` instead of forcing resources into `@Import`.
- Is the module actually on the runtime classpath? With JPMS, has reflection/access been handled where needed?
- Does an integration test building the context from **one composition root** verify both the imported beans and the beans intentionally left unregistered?

## 15. Summary

`@Import` is a key tool for **composing Java-based configurations explicitly** in Spring Core Container. You can import one or more `@Configuration` classes, regular component classes, or the `ImportSelector` and `ImportBeanDefinitionRegistrar` extension points. Spring processes the metadata/import graph to register bean definitions; BeanFactory still governs dependency injection, scopes, and lifecycles.

Use `@Import` when you want a clear composition root, modularization, and activation of only the needed configurations. For many application components that should be discovered by package, `@ComponentScan` may fit better. For XML configuration, choose `@ImportResource`. When bean A needs bean B from another config, prefer **method-parameter injection** over calling `@Bean` methods directly and relying on proxy mode.

**Rule to remember:** imports select *sources of bean definitions*; they do not scan packages automatically, do not guarantee bean creation order, and do not bypass profile/conditional/dependency rules. A clean, tested import graph is easier to maintain than scanning broadly and dealing with unintended beans afterward.

### Official References

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework 6.2 — `@ImportResource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportResource.html).
- [Spring Framework — Creating an ApplicationContext with Annotation-based Config](https://docs.spring.io/spring-framework/reference/core/beans/java/instantiating-container.html).
