# Splitting Configuration Along Functional Boundaries in Spring Core Container

## 1. Why Split Configuration?

A small Spring application can start with a single `@Configuration` class containing all `@Bean` methods. However, as the application grows, one large configuration file often mixes different responsibilities:

- Storage configuration: `DataSource`, repositories, transaction infrastructure, or data adapters.
- Pricing configuration: discount policies, tax calculators, and business rules.
- Payment configuration: payment gateway clients, retry policies, and credential providers.
- Checkout configuration: use cases combining dependencies.
- Communication configuration: HTTP clients, serialization, and event publishers.

If everything is placed inside one `ApplicationConfig` class hundreds or thousands of lines long, readers struggle to tell **which bean belongs to which capability, which module depends on which module, and which configuration is needed for tests or a specific deployment environment**.

The solution is **splitting configuration along functional boundaries**: each group of beans is declared close to the responsibility it serves, and a **composition root** assembles them into an application context. In Java configuration, `@Configuration`, `@Bean`, and especially `@Import` provide the direct mechanism for this approach. This lesson is about **configuration composition** in Spring Core Container—not a rule that every module must be a microservice or that every package must have its own container.

### Learning Objectives

After this lesson, you will be able to:

1. Identify configuration boundaries by **capability/use case**, rather than grouping arbitrarily by annotation type or utility.
2. Write multiple dedicated `@Configuration` classes and use `@Import` to compose them from a single startup point.
3. Wire dependencies **across configurations** using `@Bean` parameters so Spring resolves beans by type, qualifier, and scope.
4. Distinguish `@Import`, `@ComponentScan`, `@Bean`, `@Profile`, and `@Conditional`: each tool handles a different part of the job.
5. Choose proper bean ownership and avoid name collisions, type ambiguity, circular dependencies, and duplicate resource initialization.
6. Design modules whose implementations can be swapped easily and write integration tests scoped to specific capabilities.
7. Run a Java 17+ example with **Storage**, **Pricing**, and **Checkout** modules, composed **without component scanning**.

## 2. What Does “Functional Boundary” Mean?

A functional boundary is where a group of configurations and beans serves a **relatively independent responsibility** with a clear contract toward the rest of the system. For example:

| Boundary | Responsibility | Typical Beans | Required Public Dependencies |
| --- | --- | --- | --- |
| Storage | Persist and look up orders | `OrderStore`, JDBC/in-memory adapter | DataSource or storage settings |
| Pricing | Calculate prices and promotions | `DiscountPolicy` | Pricing policies, rate settings |
| Checkout | Orchestrate order placement | `CheckoutService` | `OrderStore` and `DiscountPolicy` |
| Integration | Connect to external services | SDK client, timeout/retry | Settings and credentials |
| Delivery/Web | Translate HTTP requests to use cases | Controller, message mapper | `CheckoutService` |

A sound boundary should have:

- **High cohesion:** beans in the same group serve closely related goals.
- **Clear dependency direction:** checkout may need pricing and storage; pricing usually does not need to know about the checkout controller.
- **Stable contract:** other modules rely on interfaces or public services rather than internal structure.
- **Consistent ownership:** whichever group creates a bean is responsible for configuring its appropriate scope/lifecycle.
- **Intentional toggleability/replaceability:** an adapter can be swapped in tests without modifying a whole series of unrelated configurations.

There is no rule saying “one class per configuration” or “exactly one configuration per module”. Split by real responsibility, avoiding both **God Configuration** and excessive files that add no extra meaning.

### Two Common Package Organization Approaches

**By technical layer:**

```text
com.example
├── config
│   ├── DataConfig.java
│   ├── ServiceConfig.java
│   └── WebConfig.java
├── controller
├── service
└── repository
```

This approach can work well for small projects, but when many different capabilities share the same layer, changing one feature may require edits across multiple places.

**By capability/feature:**

```text
com.example
├── checkout
│   ├── CheckoutService.java
│   └── CheckoutConfiguration.java
├── pricing
│   ├── DiscountPolicy.java
│   └── PricingConfiguration.java
├── storage
│   ├── OrderStore.java
│   └── StorageConfiguration.java
└── bootstrap
    ├── ApplicationConfiguration.java
    └── Application.java
```

This option gives clearer ownership when capabilities evolve independently. In larger systems, you can further separate **API contracts** from implementations/infrastructure within each capability. Do not be rigid: the choice depends on team size, dependency direction, testability, and real deployment boundaries.

## 3. Spring Mechanisms for Composing Multiple Configurations

### 3.1. @Configuration Describes a Group of Bean Definitions

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingConfiguration {

    @Bean
    DiscountPolicy discountPolicy() {
        return new TenPercentDiscountPolicy();
    }
}
```

This is an illustrative snippet; `DiscountPolicy` and `TenPercentDiscountPolicy` must be defined as in the complete example later. `@Configuration` tells Spring that the class holds configuration; the `@Bean` method registers a bean definition. When the context is built, Spring can create the `discountPolicy` bean to inject into other capabilities.

`proxyBeanMethods=false` fits here because the factory methods are independent and do not need to call another `@Bean` method directly. **It does not disable dependency injection**: factory method parameters are still resolved by Spring as usual.

### 3.2. @Import Composes Configurations from an Explicit List

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
public class ApplicationConfiguration {
}
```

The classes in the array must exist and be imported from the proper packages. This is the configuration layout that will appear in the runnable example.

When `ApplicationConfiguration` is registered with `AnnotationConfigApplicationContext`, Spring processes `@Import` and the imported configurations. Their `@Bean` methods become bean definitions in **the same ApplicationContext**, enabling dependency injection across boundaries.

**Key point:** `@Import` does not mean “embed Java source code”, is not `new StorageConfiguration()`, and does not automatically create a child context. It is metadata telling Spring to load additional configuration sources/types into the context.

Spring documentation also allows `@Import` to reference certain regular component classes, `ImportSelector`, or `ImportBeanDefinitionRegistrar` in advanced scenarios. In this lesson, using explicit `@Configuration` classes is the easiest approach to learn and control.

### 3.3. @Bean Parameters Wire Dependencies Across Configurations

```java
@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore orderStore,
            DiscountPolicy discountPolicy) {
        return new CheckoutService(orderStore, discountPolicy);
    }
}
```

`CheckoutService`, `OrderStore`, and `DiscountPolicy` are the types in the complete example. Spring resolves both parameters from the registered bean definitions, even though they are declared by **other configuration classes**.

This is the crux of configuration composition: **the checkout module knows the contracts it needs, without necessarily knowing which configuration class created the implementation**.

Do not replace this approach with:

```java
@Bean
CheckoutService checkoutService() {
    return new CheckoutService(
            new StorageConfiguration().orderStore(),
            new PricingConfiguration().discountPolicy()
    );
}
```

That counterexample assumes access to the factory methods is allowed in the respective package. Manually calling `new` on configuration classes and invoking factory methods directly can create objects outside the container, bypassing scopes, lifecycles, proxies, and bean replacement in tests. When using `@Configuration(proxyBeanMethods=false)`, cross-`@Bean` calls also carry direct Java semantics rather than container lookup.

## 4. Role of the Composition Root

The **composition root** is where the application decides **which configurations/modules are present together** in a deployment. Typically, it is one or a few classes near the entry point:

```text
                 ApplicationConfiguration
                       @Import
                      /   |   \
                     v    v    v
          StorageConfig PricingConfig CheckoutConfig
                |           |           |
                v           v           v
             OrderStore DiscountPolicy CheckoutService
                \           /
                 \         /
                  \       v
                    CheckoutService
```

The diagram shows imports in the upper layer and actual dependencies in the lower layer. `CheckoutService` receives the contracts provided by the other modules; the container does not create a dependency automatically just because two configurations are imported together.

### Why Is a Composition Root Useful?

- **One place to decide application assembly:** startup does not need to remember to manually register dozens of scattered configuration classes.
- **Supports different environment assemblies:** tests import in-memory storage; production imports JDBC storage.
- **Observable dependency graph:** the composition root reveals which modules make up the application.
- **Fewer unintended scans:** explicit imports allow selecting the exact set of configurations to load.
- **Clear responsibility boundaries:** pricing does not need to import checkout to work; bootstrap handles the assembly.

**Do not confuse:** `ApplicationContext` is still **one** container in the example. Multiple `@Configuration` classes do not mean multiple containers or separate singleton caches. Normal singleton scope applies within the shared context into which the definitions are composed.

## 5. Complete Java 17+ Example: Storage + Pricing + Checkout

The following example uses **Spring Framework 6.2.19**, **Java 17+**, **Gradle**, and `AnnotationConfigApplicationContext`. We intentionally omit `@ComponentScan` to clearly see **`@Import` + `@Bean` + parameter injection**.

The program stores simulated data in memory, calculates a 10% discount using integers, and prints deterministic output. No database, web server, Spring Boot, or network is needed.

### 5.1. Directory Structure

```text
modular-config-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    ├── App.java
    ├── config/
    │   ├── ApplicationConfiguration.java
    │   ├── StorageConfiguration.java
    │   ├── PricingConfiguration.java
    │   └── CheckoutConfiguration.java
    ├── storage/
    │   ├── OrderStore.java
    │   └── InMemoryOrderStore.java
    ├── pricing/
    │   ├── DiscountPolicy.java
    │   └── TenPercentDiscountPolicy.java
    └── checkout/
        └── CheckoutService.java
```

There are **10 Java files**: one entry point, four configuration classes, and five classes/interfaces implementing the contracts. Each public top-level type file has the exact corresponding name and package.

### 5.2. Gradle Configuration

**`settings.gradle`**

```groovy
rootProject.name = 'modular-config-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
```

Spring Framework 6.2.x supports Java 17+. The `spring-context` dependency brings in the necessary Spring Core/Beans libraries via Maven metadata. No `spring-boot-starter` is needed to run a pure IoC Container demo.

### 5.3. Storage Module: Contract and Implementation

**`src/main/java/demo/storage/OrderStore.java`**

```java
package demo.storage;

public interface OrderStore {
    String save(String orderId, long chargedTotal);
    int count();
}
```

`OrderStore` is the contract used by Checkout. Real applications may design a richer domain API, but the demo only needs to save a record and count the number of writes.

**`src/main/java/demo/storage/InMemoryOrderStore.java`**

```java
package demo.storage;

import java.util.concurrent.atomic.AtomicInteger;

public final class InMemoryOrderStore implements OrderStore {
    private final AtomicInteger writes = new AtomicInteger();

    @Override
    public String save(String orderId, long chargedTotal) {
        writes.incrementAndGet();
        return orderId + ":" + chargedTotal;
    }

    @Override
    public int count() {
        return writes.get();
    }
}
```

The implementation has no `@Component`. `StorageConfiguration` itself actively registers it. `AtomicInteger` makes the counter safe for concurrent increments, even though the demo runs on a single thread. This is an in-memory fake for learning configuration, **not durable persistence**.

### 5.4. Pricing Module: Pricing Rules

**`src/main/java/demo/pricing/DiscountPolicy.java`**

```java
package demo.pricing;

public interface DiscountPolicy {
    long discountedTotal(long baseTotal);
}
```

**`src/main/java/demo/pricing/TenPercentDiscountPolicy.java`**

```java
package demo.pricing;

public final class TenPercentDiscountPolicy implements DiscountPolicy {
    @Override
    public long discountedTotal(long baseTotal) {
        if (baseTotal < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return baseTotal - (baseTotal / 10);
    }
}
```

This is a demo policy calculated with `long`. For 100, the result is 90; for 50, the result is 45. Real monetary applications should define the smallest currency unit, rounding policy, and overflow handling, and use `BigDecimal` when the domain requires it, rather than treating integer division as a universal business standard.

### 5.5. Checkout Module: Depends Only on Interfaces

**`src/main/java/demo/checkout/CheckoutService.java`**

```java
package demo.checkout;

import demo.pricing.DiscountPolicy;
import demo.storage.OrderStore;

import java.util.Objects;

public final class CheckoutService {
    private final OrderStore store;
    private final DiscountPolicy discounts;

    public CheckoutService(OrderStore store, DiscountPolicy discounts) {
        this.store = Objects.requireNonNull(store);
        this.discounts = Objects.requireNonNull(discounts);
    }

    public String checkout(String orderId, long baseTotal) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("blank order id");
        }
        long charged = discounts.discountedTotal(baseTotal);
        return store.save(orderId, charged);
    }
}
```

Checkout does not import `StorageConfiguration`, `PricingConfiguration`, or concrete implementations; it only uses `OrderStore` and `DiscountPolicy`. As a result, business logic tests can pass fakes into the constructor **without needing Spring**.

### 5.6. Three Dedicated Configuration Classes

**`src/main/java/demo/config/StorageConfiguration.java`**

```java
package demo.config;

import demo.storage.InMemoryOrderStore;
import demo.storage.OrderStore;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {
    @Bean
    OrderStore orderStore() {
        return new InMemoryOrderStore();
    }
}
```

**`src/main/java/demo/config/PricingConfiguration.java`**

```java
package demo.config;

import demo.pricing.DiscountPolicy;
import demo.pricing.TenPercentDiscountPolicy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingConfiguration {
    @Bean
    DiscountPolicy discountPolicy() {
        return new TenPercentDiscountPolicy();
    }
}
```

**`src/main/java/demo/config/CheckoutConfiguration.java`**

```java
package demo.config;

import demo.checkout.CheckoutService;
import demo.pricing.DiscountPolicy;
import demo.storage.OrderStore;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore orderStore,
            DiscountPolicy discountPolicy) {
        return new CheckoutService(orderStore, discountPolicy);
    }
}
```

Notable point: the three configuration classes have distinct responsibilities. `CheckoutConfiguration` **does not instantiate a second repository or discount policy**. Spring resolves both parameters from the container.

In modules with multiple `OrderStore` or `DiscountPolicy` implementations, appropriate qualifiers or `@Primary` must be declared. The demo has only one bean per interface so the startup flow is easy to verify.

### 5.7. Composition Root Using @Import

**`src/main/java/demo/config/ApplicationConfiguration.java`**

```java
package demo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
public class ApplicationConfiguration {
}
```

This is the file that decides which three boundaries will be composed in the application. No `@ComponentScan` is needed. No `@Import` needs to be placed inside individual modules to import one another in a cycle.

Making the entry point depend only on `ApplicationConfiguration` is a clear way to express the composition root.

### 5.8. Entry Point

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.checkout.CheckoutService;
import demo.config.ApplicationConfiguration;
import demo.storage.OrderStore;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        ApplicationConfiguration.class)) {

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            OrderStore store =
                    context.getBean(OrderStore.class);

            System.out.println("store-bean="
                    + context.containsBean("orderStore"));
            System.out.println("discount-bean="
                    + context.containsBean("discountPolicy"));

            System.out.println("checkout1="
                    + checkout.checkout("ORDER-7", 100));
            System.out.println("checkout2="
                    + checkout.checkout("ORDER-8", 50));

            System.out.println("writes=" + store.count());
            System.out.println("store-count="
                    + context.getBeansOfType(OrderStore.class).size());

            System.out.println("service-singleton="
                    + (checkout == context.getBean(CheckoutService.class)));
        }
    }
}
```

### 5.9. Running

In the `modular-config-demo` directory, with Gradle and JDK 17+:

```bash
gradle run --quiet
```

If a Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. Running `javac App.java` alone is not enough because the project has multiple files/packages and requires Spring JARs on the classpath; Gradle handles compile and runtime dependencies.

**Lines printed by the application:**

```text
store-bean=true
discount-bean=true
checkout1=ORDER-7:90
checkout2=ORDER-8:45
writes=2
store-count=1
service-singleton=true
```

The output may include Gradle or runtime logs depending on the environment, but the seven lines above come from the program's `System.out.println` statements.

### 5.10. Why Is the Output Correct?

1. `ApplicationConfiguration` is registered directly. Spring parses `@Import` and registers definitions from the three imported `@Configuration` classes.
2. `@Bean OrderStore orderStore()` creates an `InMemoryOrderStore`; `containsBean("orderStore")` returns `true`.
3. `@Bean DiscountPolicy discountPolicy()` creates `TenPercentDiscountPolicy`; the bean named `discountPolicy` exists.
4. `CheckoutConfiguration` requests `OrderStore` and `DiscountPolicy` via factory method parameters. Each of these two interfaces has exactly one eligible bean, so Spring can inject them.
5. `checkout("ORDER-7", 100)` applies the 10% discount rule and saves `ORDER-7:90`. The second call saves `ORDER-8:45`.
6. `OrderStore` is a singleton by default. Checkout and the entry point both use the same managed store, so after two saves, `store.count()` equals 2.
7. `getBeansOfType(OrderStore.class).size()` equals 1 because there is only one bean of this type in the context.
8. `CheckoutService` is also a singleton by default, so two calls to `getBean(CheckoutService.class)` return the same instance.

**Verified core takeaway:** multiple configuration classes still contribute beans into **one shared IoC Container**, and dependencies can be wired across classes/packages by type. There is no `new StorageConfiguration()` in checkout or direct call to `orderStore()` from another configuration.

## 6. Why Avoid Configurations Importing Each Other?

Consider a poorly organized situation:

```text
PricingConfiguration -> @Import(CheckoutConfiguration)
CheckoutConfiguration -> @Import(StorageConfiguration)
StorageConfiguration -> @Import(PricingConfiguration)
```

Some mutual import combinations can be processed by Spring as metadata within specific limits, but **from a design perspective**, they blur the dependency direction: lower layers have to “know” higher application layers, and it becomes hard to identify the composition root.

A clearer structure:

```text
ApplicationConfiguration
    |
    +--> StorageConfiguration
    +--> PricingConfiguration
    +--> CheckoutConfiguration

CheckoutService
    |
    +--> OrderStore interface
    +--> DiscountPolicy interface
```

**Distinguish two kinds of graphs:**

- **Import graph** states which configurations are loaded into the application context.
- **Bean dependency graph** states which bean needs which bean when created/used.

Do not try to mirror the bean dependency graph by having each module `@Import` the configurations of the modules it uses. The composition root loads the set of modules, while bean dependencies are expressed through constructor/factory method parameters. This is how you reduce coupling between configuration classes.

## 7. @Import vs. @ComponentScan: When to Use Which?

| Criterion | `@Import` | `@ComponentScan` |
| --- | --- | --- |
| How classes are selected | Explicitly by referenced class/type | Automatically searches candidates in base packages by filters |
| Primary purpose | Compose configurations or register specified types | Discover `@Component` and stereotype classes |
| Affected by package scan? | Does not require package scanning of the imported type | Yes |
| Easy to see enabled modules from composition root? | Yes, by reading the `@Import` array | Must inspect packages/filters and classpath |
| Works with classes without `@Component`? | Yes, for types supported by `@Import` | Default scanner does not automatically pick types lacking markers |
| Best suited for | Well-defined sets of configurations/feature modules | Many application components following conventions |

You do not have to choose **only one**. A practical organization often does this:

1. The composition root uses `@Import` to assemble functional configurations.
2. Each configuration can use `@ComponentScan(basePackageClasses=FeatureMarker.class)` to find services/controllers for **that capability**, or use explicit `@Bean` methods.
3. Avoid scanning an overly broad root package if doing so could pull unintended test doubles, adapters, and configurations into the context.

Example structure for a feature with many components:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = PricingPackageMarker.class)
public class PricingConfiguration {
}
```

`PricingPackageMarker` is a marker class/interface located in the package to scan. `basePackageClasses` uses the **package** of the referenced class as the root; it does not scan only the marker class itself. Valid imports for `ComponentScan`, `Configuration`, and the marker are required.

**Note:** if the marker resides in a package that is too general, the scanner may also pick up configurations/beans from other modules. Placing a package inside a functional module expresses organizational intent, not automatic runtime “module isolation”: all scanned/imported beans still live in the current context.

## 8. Functional Boundaries Do Not Automatically Become DI Isolation

When importing three configurations into one context, all bean definitions participate together in dependency resolution within that context. Spring does not automatically prevent a Storage bean from depending back on Checkout just because they are in different packages.

**Example of a poor dependency direction:**

```text
Storage adapter ---> CheckoutService ---> OrderStore
        ^                                 |
        +---------------------------------+
```

The risk is a circular dependency and an architecture that is hard to replace. Conversely, if Checkout only knows the `OrderStore` interface, the implementation can be swapped for JDBC, an event store, or an in-memory fake without modifying CheckoutService.

To enforce boundaries, you can use:

- Code reviews and package conventions.
- Java/Gradle/Maven modules suited to the project size.
- Architecture tests that check import directions.
- Exporting only consumed contracts; keeping implementations internal where Java visibility/packages allow.
- Dependency graph reviews before adding a new constructor dependency.

**Splitting configuration is an organizational step; it does not automatically guarantee architectural isolation.**

## 9. Should You Split by Capability or by Technical Infrastructure?

Both approaches have their place.

### 9.1. Feature-First When Use Cases Have Clear Ownership

A checkout feature can own `CheckoutConfiguration`, services, and feature-specific adapters. Each feature module carries a configuration “entry point” and its public contracts.

Pros:

- The team owning the feature easily finds where to make changes.
- Tests only need to import the relevant configuration.
- Fewer edits to central config as the feature evolves internally.
- Modules can be toggled/replaced via the composition root.

Cons: if every feature creates its own `ObjectMapper` or connection pool even though they should be shared, the system may duplicate resources and struggle to manage lifecycles.

### 9.2. Infrastructure-First When Resources Have Shared Ownership

Resources such as a shared `DataSource`, Jackson mapper, HTTP connection pool, metrics, or clock can be defined in a **shared infrastructure configuration**. Other features inject their **contracts**, avoiding duplicate resource creation.

Example:

```text
ApplicationConfiguration
├── SharedInfrastructureConfiguration
├── CustomerFeatureConfiguration
├── OrderFeatureConfiguration
└── BillingFeatureConfiguration
```

However, a shared config can also become a “God Configuration” if every feature-specific decision is stuffed into it. The criterion should be **who owns the resource's lifecycle/policy** and **who genuinely needs to share it**, not merely the number of classes.

### 9.3. Hybrid Is Usually Most Practical

- Configuration by feature/use case: services, policies, feature adapters.
- Configuration by shared infrastructure: genuinely shared resources.
- Composition root: selects the set of modules for an application/deployment.
- Profiles/conditions: selects implementation variants by environment when needed.
- Interfaces: prevents feature services from depending directly on vendor SDKs.

## 10. Swapping Implementations Without Modifying Services

In the example, Checkout uses `OrderStore` without knowing `InMemoryOrderStore`. We can define another implementation:

```java
public final class JdbcOrderStore implements OrderStore {
    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public String save(String id, long total) {
        jdbc.update(
            "insert into orders(id, total) values (?, ?)",
            id, total
        );
        return id + ":" + total;
    }

    @Override
    public int count() {
        Integer value = jdbc.queryForObject(
            "select count(*) from orders",
            Integer.class
        );
        return java.util.Objects.requireNonNull(value);
    }
}
```

This is **non-standalone illustrative code**, as it requires importing `OrderStore`, `JdbcTemplate` (`spring-jdbc`), a database with an `orders` schema, `DataSource` configuration, and the corresponding types. Do not use this SQL snippet as a production migration/schema.

When production selects JDBC:

```java
@Configuration(proxyBeanMethods = false)
class JdbcStorageConfiguration {
    @Bean
    OrderStore orderStore(JdbcTemplate jdbc) {
        return new JdbcOrderStore(jdbc);
    }
}
```

The composition root can import `JdbcStorageConfiguration` instead of the in-memory `StorageConfiguration`, **and must not import both simultaneously if they both declare the bean name `orderStore` without a conflict policy**.

CheckoutService does not have to change. This is the main benefit of **configurable composition**.

### 10.1. Avoid Importing Two Implementations at the Same Time

If two configurations both contain:

```java
@Bean
OrderStore orderStore() { /*...*/ }
```

in the same context, they may collide on **the same bean name** `orderStore`. Depending on settings, duplicate definitions may fail or one definition may override another. Do not rely on import order to select an implementation.

If two methods have **different names** but the same return type `OrderStore`, single-bean injection by type can also be ambiguous: `NoUniqueBeanDefinitionException`.

A clearer approach:

- The composition root imports only **one** default implementation per deployment.
- If two valid implementations are needed, use names/`@Qualifier`/`@Primary` according to business requirements.
- With Spring Boot auto-configuration, conditions such as `@ConditionalOnMissingBean` typically resolve default beans, but that is a **Spring Boot API**, not automatically available in a pure Spring Framework project using only `spring-context`.

## 11. @Qualifier and @Primary in Configuration Modules

Suppose the system has two adapters of the same type:

```java
@Bean("fastStore")
OrderStore fastStore() {
    return new FastOrderStore();
}

@Bean("durableStore")
OrderStore durableStore() {
    return new DurableOrderStore();
}
```

`FastOrderStore` and `DurableOrderStore` are hypothetical types; the code only illustrates two bean registrations. When Checkout requires a specific bean:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("durableStore") OrderStore store,
        DiscountPolicy discounts) {
    return new CheckoutService(store, discounts);
}
```

`Qualifier` must be imported. Spring selects the matching candidate by qualifier. If there is a default bean that should be used when an injection point has no qualifier, you can mark an appropriate bean definition with `@Primary`.

**Convention:** qualifiers should express roles such as `durableStore`, `reportingStore`, or `paymentClient` rather than easily changed concrete implementation names. Although bean names are strings, custom qualifier annotations can be used to reduce reliance on string literals when the number of injection points is large.

## 12. Profiles and Conditions for Selecting Variants

In practice, many applications need in-memory storage for local/test and a database for production. Spring provides `@Profile` to restrict beans/configurations based on active profiles.

Example structure:

```java
@Configuration(proxyBeanMethods = false)
@Profile("local")
class LocalStorageConfiguration {
    @Bean
    OrderStore orderStore() {
        return new InMemoryOrderStore();
    }
}

@Configuration(proxyBeanMethods = false)
@Profile("prod")
class ProductionStorageConfiguration {
    @Bean
    OrderStore orderStore(DataSource dataSource) {
        return new ProductionOrderStore(dataSource);
    }
}
```

`ProductionOrderStore` is a hypothetical type; a `DataSource` and real persistence code are required. This is not part of the runnable main demo.

If the composition root imports both while only the corresponding profile is active, Spring can select bean definitions according to `@Profile`. However, you must clearly define behavior when **no profile is active**, **both are active**, or conditional registrations interact. If both profiles are active and both create the name `orderStore`, conflict risk remains.

Do not treat profiles as a complete mechanism for managing all feature toggles. Runtime feature flags may change while the application is running; `@Profile` primarily affects **bean registration when the context is built**.

### @Conditional in Spring Core

Spring supports `@Conditional` with a `Condition` implementation to control registration via configuration conditions. However, writing complex conditions just to avoid importing two configurations often makes debugging harder. With an explicit composition root, picking the right module upfront can be clearer.

`@ConditionalOnProperty` and `@ConditionalOnMissingBean` are common tools in **Spring Boot**, not basic `spring-context` annotations in the current demo.

## 13. Testing Individual Configuration Boundaries

Modular configuration makes it easy to create **small contexts** for individual tests.

### 13.1. Testing PricingConfiguration in Isolation

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
                 PricingConfiguration.class)) {

    DiscountPolicy policy =
            context.getBean(DiscountPolicy.class);

    if (policy.discountedTotal(100) != 90) {
        throw new AssertionError("unexpected discount");
    }
}
```

This code snippet relies on the demo's `PricingConfiguration` and `DiscountPolicy` files; both must be imported along with `AnnotationConfigApplicationContext`. The test only needs the Pricing module; storage and checkout are unnecessary.

### 13.2. Testing Checkout with a Fake Store and Policy

Because `CheckoutService` depends only on interfaces, it can be tested in plain Java:

```java
OrderStore fake = new InMemoryOrderStore();
DiscountPolicy fixed = baseTotal -> baseTotal - 5;

CheckoutService service = new CheckoutService(fake, fixed);

String result = service.checkout("TEST-1", 20);
if (!"TEST-1:15".equals(result)) {
    throw new AssertionError(result);
}
```

This snippet uses the types in the demo (imports required). No ApplicationContext is needed. This is a **business unit test**, not a verification of bean definition composition.

### 13.3. Testing the Composition Root with a Real Context

Build the context with `ApplicationConfiguration.class` and verify:

- `OrderStore` has exactly one candidate.
- `DiscountPolicy` has exactly one candidate.
- `CheckoutService` is created and behaves correctly.
- No unintended beans from unimported modules are present.
- Shared resources (if any) have the right scope and are created only once.

The demo `App.main()` itself is a simple integration smoke test with seven deterministic stdout lines. In a project with JUnit 5, assertions can be used instead of `System.out.println`.

### 13.4. Testing Alternative Configurations

A separate **test composition root** can import:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    FakeStorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
class CheckoutTestConfiguration {}
```

`FakeStorageConfiguration` is a hypothetical test class returning a fake `OrderStore`. This is a test-specific configuration, avoiding adding fake beans into the production root. Ensure there is **only one eligible candidate** for the injection point, rather than creating two `OrderStore` beans of the same type and relying on arbitrary ordering.

### 13.5. Do Not Spin Up the Entire Application Context to Test a Utility

Plain Java service logic tests can instantiate objects directly. Use a Spring context when testing **wiring/configuration**, scopes, qualifiers, bean lifecycle, or infrastructure integration. Proper configuration splitting lets you choose the smallest test scope that still proves what needs to be verified.

## 14. Keeping Modules Independent When Using @ComponentScan

A module with dozens of services may prefer package scanning instead of declaring `@Bean` for every class. You can let `FeatureConfiguration` scan **only that feature's package**:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = OrdersPackageMarker.class)
class OrdersFeatureConfiguration {}
```

`OrdersPackageMarker` is a marker type placed by the application inside the orders package, and related `@Service`/`@Repository` classes reside in that package or its subpackages. This is an illustrative snippet; real imports and marker are required.

Two important principles:

1. **The composition root can still use `@Import(OrdersFeatureConfiguration.class)`** to select the feature; scanning only operates inside the loaded feature.
2. If component scan is too broad, it can also discover `@Configuration` classes of other features because `@Configuration` is a specialization of `@Component`. In that case, “only importing feature A” could still indirectly pick up beans from feature B if the scan package is not carefully bounded.

`includeFilters`/`excludeFilters` and `useDefaultFilters=false` can fine-tune scanning, but they are not the primary tool to fix an unclear package structure.

### A Note on “Internal Configuration”

A `@Configuration` class in an internal package can still be discovered by Spring if another component scan covers that package. Do not rely on Java package names to guarantee a module will never be registered. Restrict scans and use an explicit import graph if controlled module activation is an important requirement.

## 15. Combining @Import with Configuration Classes Using @Bean Parameters

Suppose a feature wants to use `Clock`, `OrderStore`, and `DiscountPolicy`:

```java
@Configuration(proxyBeanMethods = false)
class CheckoutConfiguration {
    @Bean
    CheckoutService checkoutService(
            OrderStore store,
            DiscountPolicy policy) {
        return new CheckoutService(store, policy);
    }
}
```

The method only declares what it needs; the bean providers can come from `StorageConfiguration` and `PricingConfiguration`. Spring allows dependency resolution across imported classes **without direct `@Bean` method calls**.

There is no need to write:

```java
@Configuration
class CheckoutConfiguration {
    @Autowired
    private StorageConfiguration storageConfiguration;

    @Bean
    CheckoutService checkoutService() {
        return new CheckoutService(
                storageConfiguration.orderStore(),
                new TenPercentDiscountPolicy()
        );
    }
}
```

This is an **illustrative anti-pattern**; if `StorageConfiguration` uses `proxyBeanMethods=false`, a direct call can create another store outside the managed singleton. Even with full interception, the code still forces checkout to know the concrete configuration, increasing coupling. Injection via interfaces through method parameters is simpler.

Spring documentation also warns that `@Configuration` classes are processed early. Field/constructor injection on **the configuration class itself** can lead to unwanted early initialization, especially when the configuration contains a `BeanFactoryPostProcessor`/`BeanPostProcessor`. For processors that need to be created very early, `static @Bean` with an appropriate return type is typically used. When declaring regular business beans, parameter injection is the easiest way to control dependencies.

## 16. Module Boundaries and Resource Lifecycles

A functional configuration may create an expensive resource:

```java
@Configuration(proxyBeanMethods = false)
class MessagingConfiguration {
    @Bean(destroyMethod = "close")
    VendorMessageClient messageClient(MessagingSettings settings) {
        return VendorMessageClient.create(settings);
    }
}
```

`VendorMessageClient`/`MessagingSettings` are hypothetical SDK types; this code illustrates the ownership/lifecycle concept. If the library has a suitable `close()` method and the resource is owned by the application, the container will invoke the destroy callback as defined when closing the bean/context under appropriate conditions.

Functional boundaries do not just state which file a bean lives in, but also **who owns the resource**:

- A shared HTTP client may belong to `SharedIntegrationConfiguration`.
- A connection pool may belong to `PersistenceConfiguration`.
- A per-request builder may belong to a feature configuration with `prototype` or an appropriate scope.
- Feature services usually only inject the resource contract; **they do not create or close shared resources themselves**.

If every feature calls `new DataSource()` or creates an independent pool, splitting configuration can scatter ownership and increase resource leaks. Proper modularization should make ownership clearer, not more complicated.

## 17. When to Split into Separate Gradle/Maven Modules?

Splitting `@Configuration` by class/package is a **logical boundary within one codebase**. At larger scale, you can split into physical modules:

```text
checkout-api/
checkout-impl/
pricing-api/
pricing-impl/
storage-api/
storage-jdbc/
application/
```

However, this adds build overhead, dependency management, public API governance, and deployment complexity. Consider it when:

- Multiple teams make changes independently.
- You want the compiler/build to prevent implementation dependencies from reversing direction.
- Tests or artifacts need to be reused separately.
- You want to separate environment-specific adapters without pulling every dependency into one large package.

Even with multiple Gradle/Maven modules, Spring can still compose configuration classes into **one ApplicationContext** via `@Import`, appropriate scanning, or auto-configuration. Build-time modules and runtime bean containers are two different concepts.

**Avoid the false claim:** each Gradle module does not automatically get its own Spring context; nor does each `@Configuration` automatically get its own singleton cache.

## 18. Different Ways to Compose Configurations

### 18.1. Direct @Import

```java
@Configuration(proxyBeanMethods = false)
@Import({
    StorageConfiguration.class,
    PricingConfiguration.class,
    CheckoutConfiguration.class
})
class ApplicationConfiguration {}
```

Pros: explicit, easy to code review. Suits a moderate number of modules.

### 18.2. @Import at Feature-Level Configuration

If a feature has multiple internal parts:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    FeatureDomainConfiguration.class,
    FeatureAdaptersConfiguration.class
})
class FeatureConfiguration {}
```

`FeatureDomainConfiguration`/`FeatureAdaptersConfiguration` are hypothetical classes. The composition root imports `FeatureConfiguration`. This pattern is useful when a feature genuinely owns two sub-configurations, not so each feature can quietly import the entire application.

### 18.3. Context.register Multiple Configurations

```java
try (AnnotationConfigApplicationContext ctx =
         new AnnotationConfigApplicationContext()) {
    ctx.register(
        StorageConfiguration.class,
        PricingConfiguration.class,
        CheckoutConfiguration.class
    );
    ctx.refresh();
    CheckoutService service = ctx.getBean(CheckoutService.class);
}
```

This snippet can be used with the demo classes and appropriate imports. It composes multiple configs directly from bootstrap without `@Import`. It fits bootstraps that need to choose modules programmatically; however, an `ApplicationConfiguration` acting as the composition root usually makes the configuration set more visible and easier to reuse.

### 18.4. Spring Boot Auto-Configuration

Spring Boot has a mechanism that automatically configures beans based on classpath/properties and conditions. This is a higher-level composition mechanism suited for reusable libraries/starters, but **not required** to compose 3–10 capabilities in a simple Spring application. Do not apply Boot's `@ConditionalOnMissingBean` in a pure `spring-context` demo without adding the corresponding dependencies.

### 18.5. @ImportSelector and ImportBeanDefinitionRegistrar

These are advanced extension points for deciding imports/registering definitions programmatically using code and metadata. They are useful when building frameworks, starters, or plugin modules, but they increase the difficulty of tracing beans. For explicit module composition, they are usually unnecessary.

## 19. Common Mistakes

### Mistake 1 — Creating @Configuration Classes Without Loading Them into the Context

Bean definitions do not appear just because a file exists in source code. Check `@Import`, `context.register(...)`, component scans, and other registration mechanisms. If `ApplicationConfiguration` is not loaded, its import graph will not be processed either.

### Mistake 2 — Each Module Instantiating Another Module's Implementation

For example, Checkout creates `new InMemoryOrderStore()` instead of receiving the `OrderStore` bean. The consequence is two separate stores, lost shared state/lifecycle, and tests that are hard to substitute. Use interface injection via constructor/`@Bean` parameters.

### Mistake 3 — Placing @ComponentScan on an Overly Broad Root Package

The scanner can pick up `@Configuration` classes, test adapters, or implementations intended only for other environments. Scope scanning by feature or use explicit `@Import`.

### Mistake 4 — Registering the Same Bean Twice

If the same implementation has both `@Component` inside a scanned package and a `@Bean` method creating another object, Spring may end up with multiple beans of the same type or duplicate names. Audit all registration paths and keep only the intended registration.

### Mistake 5 — Two Modules Declaring the Same Bean Name

Two methods named `orderStore` in different configurations can cause definition conflicts. Do not assume BeanDefinition overriding is always allowed. Design every bean name to have a clear owner.

### Mistake 6 — Having Two Beans of the Same Interface Without Checkout Knowing Which to Pick

`CheckoutConfiguration.checkoutService(OrderStore store, ...)` can throw `NoUniqueBeanDefinitionException`. Use `@Qualifier`/`@Primary` when multiple candidates are intentional, or import only one implementation.

### Mistake 7 — Using @Profile and Forgetting a Default Profile

When both implementations only exist under `local`/`prod`, having no matching active profile leaves a missing bean. If both are active, name collisions or ambiguity can occur. Test each environment explicitly.

### Mistake 8 — Abusing Circular @Import Chains

If storage imports checkout and checkout imports storage, the architecture becomes unpredictable and can create circular bean dependencies. Keep the composition root as the place that selects modules; business code depends only on contracts.

### Mistake 9 — Relying on Declaration Order in @Import

Dependencies should be resolved by Spring via parameter injection. Do not assume modules are instantiated in the order listed in the `@Import` array as a business rule; Spring has its own dependency graph, scopes, lazy beans, and infrastructure lifecycle.

### Mistake 10 — Creating Heavy Resources in Multiple Configurations

Two modules each having their own `@Bean ObjectMapper`/client/pool can make sense when policies differ, but it is dangerous if it accidentally duplicates connection pools. Define scope and ownership, and reuse shared beans via injection when truly needed.

### Mistake 11 — Assembling All Configurations into Every Test

An oversized context slows down tests, pulls in unnecessary databases/networks, and makes root causes harder to isolate. Create small fixtures that import only the module under test plus any needed fake dependencies.

### Mistake 12 — Using @Configuration(proxyBeanMethods=false) While Calling @Bean Methods Directly

Calls inside a factory method body are direct Java calls, which can create new objects outside managed beans. Use parameter injection instead. Even though full mode can intercept inter-bean calls, explicit parameters remain easier to understand and less coupled.

### Mistake 13 — Confusing the Import Graph with Runtime Visibility Constraints

`@Import` only loads bean definitions; it does not forbid another class from calling `getBean(...)` or injecting a type that the architecture intended to keep private. You need module boundaries, code reviews, or architecture tests to control dependency direction.

### Mistake 14 — Thinking @Profile Replaces the Composition Root

`@Profile` selects registrations by environment, but it does not explain **which module owns a bean** or prevent profiles from being enabled simultaneously. Use profiles for intentional variants; the composition root should still represent the feature set.

## 20. Checklist When Designing Functional Configurations

Before creating a new configuration class, answer:

1. **Which capability is responsible?** Storage, pricing, checkout, billing, reporting, or shared infra?
2. **What is the public contract?** Which interfaces/services are other modules allowed to consume?
3. **Who registers the implementation bean?** There should be one place owning the bean definition and lifecycle.
4. **How is the configuration loaded?** `@Import`, direct registration, component scan, or Boot auto-configuration?
5. **Which module depends on which module?** Is the dependency direction consistent and cycle-free?
6. **Are there multiple implementations of the same type?** If so, is qualifier/primary/conditional selection clearly designed?
7. **Is automatic scanning needed?** If not, explicit `@Bean` is usually easier to trace.
8. **Are there shared resources?** Which beans should be singleton, prototype, lazy, have destroy callbacks, or have external ownership?
9. **What is the minimal set of modules needed for testing?** Can you spin up a context for just the feature or unit-test with plain objects?
10. **Can an adapter be swapped without modifying services?** If not, consider separating interfaces and composition logic.

## 21. Self-Check Questions and Answers

**Q1.** A context loads `ApplicationConfiguration` with `@Import(StorageConfiguration.class, PricingConfiguration.class)`. Is `@ComponentScan` needed to pick up the `@Bean` methods in these two configurations?

**A:** No. `@Import` loads the configurations and Spring processes their `@Bean` methods. Component scanning is a different class-discovery path.

**Q2.** CheckoutConfiguration has the method `checkoutService(OrderStore store, DiscountPolicy policy)`. The `OrderStore` bean comes from StorageConfiguration. How does Spring connect the two configuration classes?

**A:** When creating `checkoutService`, the container resolves both parameters based on bean definitions/types/qualifiers present in the same context. CheckoutConfiguration does not need to call StorageConfiguration directly.

**Q3.** Does each `@Configuration` create its own separate context?

**A:** No. In the example, one `AnnotationConfigApplicationContext` holds the definitions imported from the three configuration classes.

**Q4.** Why shouldn't PricingConfiguration import CheckoutConfiguration just because Checkout uses DiscountPolicy?

**A:** That reverses the composition/dependency direction. Pricing does not need to know the use case consuming it; the composition root selects both, while Checkout declares the `DiscountPolicy` parameter.

**Q5.** Can the JDBC implementation be swapped out from the in-memory one without modifying CheckoutService?

**A:** Yes. CheckoutService uses the `OrderStore` interface. The composition root selects one configuration providing the corresponding implementation; be careful not to let two undifferentiated beans appear together.

**Q6.** Why is `@Import` suitable when you need to clearly see which modules are enabled?

**A:** The import array is an explicit list of configuration sources. Component scan can pick up additional classes depending on packages/filters/classpath and requires inspecting its scope to know the real bean set.

**Q7.** If two beans both implement `OrderStore`, will injecting `OrderStore` into Checkout always work?

**A:** Not necessarily. When multiple candidates cannot be narrowed to a single unique match, Spring throws `NoUniqueBeanDefinitionException`. A qualifier, primary, or single implementation per deployment is required.

**Q8.** In the demo, what does `writes=2` prove?

**A:** Both checkouts used the same managed singleton `OrderStore` that the entry point retrieved from the context. Module composition keeps dependency identity consistent.

**Q9.** If using `@ComponentScan(basePackageClasses=Marker.class)`, does Spring scan only the single Marker class?

**A:** No. It uses the package containing Marker as the root to scan, including its subpackages.

**Q10.** If a bean is excluded from one component scan, is it guaranteed not to appear in the context?

**A:** No. The bean can still be registered via `@Bean`, `@Import`, or scanned from elsewhere. You must check all registration paths.

**Q11.** Should a shared HTTP pool be placed into both PricingConfiguration and CheckoutConfiguration?

**A:** Only if two pools with independent policies/lifecycles are genuinely needed. If it is a shared resource, there should be one owner configuration, and features inject the same managed bean.

**Q12.** When testing DiscountPolicy, do you also need to spin up the Storage and Checkout modules?

**A:** No. For a unit test, instantiate the policy directly; for a wiring test, import only PricingConfiguration. A minimal context makes tests faster and failure causes clearer.

## 22. Official References

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, composing configurations, injection across configuration classes, and early initialization notes.
- [Spring Framework 6.2 — Instantiating the Container with AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/instantiating-container.html): `register()`, `refresh()`, and `scan()`.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): the two core configuration annotations.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters, return types, scope, and lifecycle.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): configuration methods and inter-bean references.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): relationship between `@ComponentScan`, stereotypes, and metadata registration.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): lifecycle and scope when composing multiple bean definitions.

**Remember:** Splitting configuration along functional boundaries gives modules clear responsibilities and ownership. `@Import` assembles the needed configuration sources into **one Spring IoC Container**, while **`@Bean` parameters**/constructor injection wire beans through contracts rather than direct calls between configuration classes. The composition root decides *what gets assembled into the application*; each module decides *which beans it provides*; Spring resolves *how dependencies meet*.
