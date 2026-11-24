# Feature-Based Configuration and Restricting Overly Broad Component Scans

As a Spring Boot application grows, the number of controllers, services, repositories, configuration classes, and integration adapters increases rapidly. If all of them are placed inside a few large packages and Spring scans from an overly broad root package, the application may still start, yet boundaries between features become hard to understand: one module accidentally registers another module's beans, two classes with the same name cause bean conflicts, a test/dev-only configuration shows up unexpectedly at runtime, or a library module gets scanned as part of the application.

A manageable way to organize code is **placing configuration and components by feature (feature/module)** while restricting component scanning to packages the application genuinely owns. Each feature can group its controllers, services, repositories, domain logic, and related configuration; shared components are separated into shared modules/packages with explicit boundaries.

The goal is not to create as many packages as possible. The goal is to make the relationship between features and bean registration predictable:

- Looking at a package tells you which feature a component belongs to.
- An application module knows explicitly which modules are brought into its context.
- Configuration for one feature does not automatically affect the whole application unnecessarily.
- Tests can initialize an appropriate slice or module without scanning the entire system.
- Adding a new module does not accidentally pull in dozens of unrelated beans.

This lesson uses Spring Boot 3.x, Java, and Spring Framework annotation-based configuration. It focuses on choosing package boundaries, component scanning, feature-based configuration, explicit module integration, key limitations to watch out for, and debugging applications when the context initializes incorrectly.

## 1. Why Does an Overly Broad Component Scan Become Hard to Control?

Spring manages objects registered as beans in the ApplicationContext. A common way to register beans is component scanning: Spring searches for classes carrying stereotypes such as `@Component`, `@Service`, `@Repository`, `@Controller`, or `@Configuration` within a specified scope.

Example:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootApplication` includes component scanning starting from the package containing that class downward by default. If the class resides in an appropriate root package, Spring can discover the application's components without declaring individual packages.

However, if the main class sits in a package that is too broad—such as a parent root package shared by multiple applications, libraries, or modules not belonging to the current service—scanning can pull in unintended components.

Example:

~~~text
com.company
├── platform
│   ├── audit
│   │   └── AuditConfiguration.java
│   ├── identity
│   │   └── IdentityAdminController.java
│   └── shared
│       └── SharedCacheConfiguration.java
├── shop
│   ├── ShopApplication.java
│   └── order
│       └── OrderService.java
└── analytics
    └── AnalyticsBatchApplication.java
~~~

If `ShopApplication` were placed in `com.company`, default component scanning could pick up `platform`, `shop`, and `analytics`. While the Shop application might only need part of `platform`, it would accidentally register controllers or batch configurations belonging to another application.

### 1.1. Common Consequences

| Issue | Symptom |
| --- | --- |
| Unintended beans | Controllers, schedulers, or integration clients from another module appear in the context |
| Duplicate bean names | Two components with the same default name or explicit bean name collide |
| Out-of-scope dependencies pulled in | A service demands beans that the current application does not configure |
| Unexpected auto-configuration interactions | Beans registered by another app/module cause Boot auto-configuration to back off |
| Slower startup | Spring must inspect more candidates, configurations, and bean definitions |
| Hard-to-isolate tests | A module test must initialize many unrelated beans |
| Blurry boundaries | Unclear which module owns a bean/configuration |
| Broader security surface | Unexpected routes or management components get registered |

Not every broad component scan immediately breaks the application. Many bugs surface only when adding a new module or changing environments/profiles. That is why package boundaries should be designed early.

## 2. Where Does Component Scanning Start?

The `@SpringBootApplication` annotation is typically placed on the main application class:

~~~java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

By default, component scanning uses the package of `ShopApplication` as its base package and scans that package along with its subpackages.

If the class is in `com.example.shop`, the default scope includes:

~~~text
com.example.shop
com.example.shop.order
com.example.shop.payment
com.example.shop.inventory
com.example.shop.configuration
~~~

But it excludes sibling packages:

~~~text
com.example.identity
com.example.analytics
~~~

Diagram:

~~~text
com.example
├── shop                 <-- base package if ShopApplication is here
│   ├── ShopApplication
│   ├── order
│   └── payment
├── identity             <-- not under com.example.shop
└── analytics            <-- not under com.example.shop
~~~

### 2.1. Place the Main Class in the Application's Root Package

A common convention:

~~~text
com.example.shop
├── ShopApplication.java
├── order
├── payment
├── inventory
└── shared
~~~

Having the main class in the root package lets component scanning cover the application's own feature packages. You usually do not need to specify `scanBasePackages`.

### 2.2. Do Not Place the Main Class in the Default Package

Do not leave the application class in the default package (with no `package` declaration):

~~~java
@SpringBootApplication
public class ShopApplication {
}
~~~

Without an explicit package, the scan scope can become so broad that it covers huge portions of the classpath and becomes difficult to control. Always place the main class in a named package, typically the root package of the application module.

### 2.3. Main Class Placed Too Deep

If the main class is placed at:

~~~text
com.example.shop.order.bootstrap.ShopApplication
~~~

then default scanning starts from `com.example.shop.order.bootstrap` and its subpackages. Sibling packages like `com.example.shop.payment` or `com.example.shop.inventory` will not be scanned.

The application may start up missing beans from other features. Place the main class in the root package or configure scan boundaries deliberately.

## 3. Package by Layer vs. Package by Feature

Two common ways to organize packages:

**Package by layer:**

~~~text
com.example.shop
├── controller
│   ├── OrderController.java
│   └── PaymentController.java
├── service
│   ├── OrderService.java
│   └── PaymentService.java
├── repository
│   ├── OrderRepository.java
│   └── PaymentRepository.java
└── config
    └── SecurityConfiguration.java
~~~

**Package by feature:**

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   └── OrderConfiguration.java
├── payment
│   ├── PaymentController.java
│   ├── PaymentService.java
│   ├── PaymentGateway.java
│   └── PaymentConfiguration.java
└── inventory
    ├── InventoryController.java
    ├── InventoryService.java
    └── InventoryRepository.java
~~~

Packaging by layer highlights the technical role of a class. Packaging by feature highlights **the business capability the class serves**.

### 3.1. Why Does Package by Feature Scale Better in Larger Systems?

When adding a requirement like "cancel order," most changes live inside the `order` feature. Developers can find related controllers, services, repositories, and configurations in the same namespace.

When packaging by layer, files for one feature are scattered:

- Controllers in `controller`.
- Services in `service`.
- Repositories in `repository`.
- Configuration in `config`.

As features grow, understanding a full capability requires jumping across many packages.

Packaging by feature helps:

- Keep related changes close together by business capability.
- Reduce reliance on overly broad shared packages.
- Clarify ownership across teams.
- Make component scanning easier to scope per module.
- Make it easier to extract a module into its own artifact when needed.

### 3.2. Package by Feature Does Not Force Cramming Everything into One Package

A feature can have subpackages:

~~~text
com.example.shop.order
├── api
│   ├── OrderController.java
│   └── OrderRequest.java
├── application
│   ├── CreateOrderService.java
│   └── CancelOrderService.java
├── domain
│   ├── Order.java
│   └── OrderPolicy.java
├── persistence
│   └── JpaOrderRepository.java
└── configuration
    └── OrderConfiguration.java
~~~

This structure still organizes by feature while grouping internally by responsibility. Package depth should serve discoverability and boundaries, not aesthetics.

### 3.3. Shared Packages Need Clear Limits

A `shared` package easily turns into a dumping ground for anything without an obvious home. Over time it can accumulate:

- Helpers used by a single feature.
- Configuration for multiple modules.
- DTOs tied to one specific API.
- Repositories or clients with no clear owner.
- Components depending on multiple features.

Put into `shared` only abstractions that are genuinely shared and have stable contracts. Feature-specific business logic should stay inside the feature that owns it.

## 4. Keep Configuration Near the Feature That Owns It

A configuration class should sit near the components it configures if its scope is primarily one feature.

Example:

~~~text
com.example.shop
├── ShopApplication.java
├── payment
│   ├── PaymentService.java
│   ├── PaymentGatewayClient.java
│   └── configuration
│       ├── PaymentConfiguration.java
│       └── PaymentProperties.java
└── order
    ├── OrderService.java
    └── configuration
        └── OrderProperties.java
~~~

`PaymentConfiguration` can register the client, timeouts, retry policies, or converters serving only payments.

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties,
            RestClient.Builder builder) {

        RestClient client = builder
                .baseUrl(properties.baseUrl())
                .build();

        return new HttpPaymentGateway(client);
    }
}
~~~

Type-safe properties:

~~~java
package com.example.shop.payment.configuration;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

Configuration in application YAML:

~~~yaml
app:
  payment:
    base-url: https://payments.example.internal
    connect-timeout: 3s
    enabled: true
~~~

Here both configuration and properties reside in the `payment` namespace, immediately showing readers which feature owns these settings.

### 4.1. A Configuration Class Is Also a Component

`@Configuration` is a stereotype detected by component scanning. If a class lies outside the scan boundary, Spring will not register it automatically simply because the file exists on the classpath.

You can:

- Place the class inside a scanned package.
- Import the class with `@Import`.
- Register beans through the application module's configuration.
- Use auto-configuration/module configuration conventions as appropriate.

Do not widen component scanning across the entire project just so one configuration class gets picked up.

### 4.2. Use proxyBeanMethods=false Where Appropriate

For configuration classes that simply register beans and do not call `@Bean` methods across each other like plain Java calls, you can use:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {
}
~~~

This avoids CGLIB method interception on the configuration class. Note that in this mode, if one `@Bean` method calls another `@Bean` method directly, it may create a fresh object instead of fetching the singleton bean from the container. Therefore, inject dependencies as method parameters:

~~~java
@Bean
PaymentFacade paymentFacade(PaymentGateway paymentGateway) {
    return new PaymentFacade(paymentGateway);
}
~~~

This is explicit and compatible with lite configuration semantics.

## 5. @SpringBootApplication and scanBasePackages

`@SpringBootApplication` combines several annotations, including `@ComponentScan`. You can customize base packages:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.shop",
                "com.example.platform.audit"
        }
)
public class ShopApplication {
}
~~~

The application scans the `shop` package and a specific portion of the `audit` platform.

### 5.1. scanBasePackages Is an Alias for Component Scan Base Packages

On `@SpringBootApplication`, `scanBasePackages` serves as an alias to configure component scan packages. It does not automatically alter other scanning mechanisms such as JPA entity scanning or repository scanning.

This is an important point: **component scan, entity scan, and repository scan are separate mechanisms**.

### 5.2. Do Not Set scanBasePackages Too Broadly

A configuration like:

~~~java
@SpringBootApplication(scanBasePackages = "com.example")
~~~

may be reasonable if `com.example` contains only one application and modules permitted in its context. However, if that namespace contains multiple independent services, batch apps, or other libraries, the scope is too broad.

Do not pick a package merely because it is a common prefix across modules. Choose base packages based on **ownership and runtime boundaries**.

### 5.3. Use Type-Safe Marker Classes Instead of Strings When Needed

`@ComponentScan` supports `basePackageClasses`:

~~~java
@SpringBootApplication
@ComponentScan(basePackageClasses = {
        ShopApplication.class,
        AuditModuleMarker.class
})
public class ShopApplication {
}
~~~

A marker type can be an empty class or interface inside the module's package. This avoids string typos and makes package refactoring safer.

Note: `@SpringBootApplication` already includes `@ComponentScan`. When adding a separate `@ComponentScan`, verify carefully whether the configuration merges as intended or creates an unintended scan scope. Usually, you can configure scanning directly via attributes on `@SpringBootApplication` rather than stacking multiple annotations.

### 5.4. Base Packages Are Not a List of Bean Classes

Component scanning treats packages as search regions, not a list of classes to register. If you want to integrate a specific module without scanning an entire package, `@Import` or an explicit module configuration may be more suitable.

## 6. @Import for Intentional Module Wiring

A module can expose a configuration entry point:

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentProperties properties) {
        return new HttpPaymentGateway(properties);
    }

    @Bean
    PaymentService paymentService(PaymentGateway paymentGateway) {
        return new PaymentService(paymentGateway);
    }
}
~~~

The application imports the module:

~~~java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
~~~

Benefits:

- The application explicitly shows which modules are integrated.
- The module has a stable entry point.
- No need to scan every package inside a library.
- Easier to test module configuration independently.
- Internal package rearrangements affect consumers less.

### 6.1. Importing a Configuration Does Not Automatically Scan Every Component in Its Package

`@Import` registers the specified configuration class and components it declares or imports. It does not turn the package containing that class into a general component-scan zone.

If the configuration needs additional components, declare them via `@Bean` or explicitly import their configurations.

### 6.2. A Module Configuration Can Import Sub-Configurations

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
        PaymentClientConfiguration.class,
        PaymentMappingConfiguration.class
})
public class PaymentModuleConfiguration {
}
~~~

This creates a clean module entry point. Consumers only import the main module configuration; internal implementation details are managed by the module itself.

### 6.3. Avoid Circular Dependencies Between Configurations

If `PaymentConfiguration` imports `OrderConfiguration` and vice versa, module boundaries are no longer clear. Consider extracting shared abstractions into a smaller module or letting the application composition root connect both modules.

## 7. Application Composition Root

In a modular application, the main application class typically acts as the **composition root**: the place deciding which modules are assembled to form a runtime application.

Example:

~~~java
@SpringBootApplication
@Import({
        OrderModuleConfiguration.class,
        PaymentModuleConfiguration.class,
        InventoryModuleConfiguration.class
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Diagram:

~~~mermaid
flowchart TD
    A["ShopApplication / Composition root"] --> O["OrderModuleConfiguration"]
    A --> P["PaymentModuleConfiguration"]
    A --> I["InventoryModuleConfiguration"]
    O --> OS["Order beans"]
    P --> PS["Payment beans"]
    I --> IS["Inventory beans"]
~~~

This makes runtime composition clearly visible. A separate batch application can import only the modules it needs:

~~~java
@SpringBootApplication
@Import({
        InventoryModuleConfiguration.class,
        ImportJobConfiguration.class
})
public class InventoryImportApplication {
}
~~~

The same codebase can host multiple executable applications with distinct bean sets, provided module boundaries and dependencies are cleanly designed.

## 8. Conditional Bean Registration: @Conditional

A configuration can be activated only when a feature is enabled or a required dependency is present.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentProperties properties) {
        return new HttpPaymentGateway(properties);
    }
}
~~~

When:

~~~yaml
app:
  payment:
    enabled: false
~~~

this configuration is not applied according to the specified condition. If the property is missing, `havingValue` does not treat it as true by default; set `matchIfMissing` explicitly when needed.

### 8.1. ConditionalOnClass

An integration module can activate only if a library is present:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public class VendorIntegrationConfiguration {
}
~~~

Using a string class name can avoid resolving the type when the dependency is absent. In auto-configuration libraries, pay attention to classloading and nested configuration structure so conditions are evaluated properly before any bean method references optional types.

### 8.2. ConditionalOnMissingBean

You can supply a default implementation if the consumer has not declared one:

~~~@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new DisabledPaymentGateway();
}
~~~

This fits extensible modules, provided the contract and fallback conditions are well defined. Do not use conditionals to mask missing required beans due to scan issues: if the module is not imported at all, neither the service nor the default gateway will exist.

### 8.3. Conditionals Do Not Replace Module Boundaries

An overly broad package scan can still pick up unwanted components even when some configurations are conditional. Restrict scanning first; use conditions for genuine configuration choices and optional integrations.

## 9. Excluding Components from Scans

Sometimes a package is scanned generally, yet a specific component should not be registered. `@ComponentScan` supports include/exclude filters.

Example excluding a class:

~~~java
@SpringBootApplication
@ComponentScan(
        basePackageClasses = ShopApplication.class,
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = LegacyPaymentController.class
        )
)
public class ShopApplication {
}
~~~

Or excluding by annotation:

~~~java
@ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = InternalOnlyComponent.class
)
~~~

Other filter types such as regex or AspectJ patterns can be used depending on requirements.

### 9.1. Exclude Filters Are No Substitute for Package Structure

If you must add numerous exclusions to filter out components belonging to other applications, the base package is likely too broad. Splitting packages/modules cleanly reduces exclusion lists and prevents forgetting to exclude newly added components.

### 9.2. Do Not Accidentally Exclude Infrastructure Components

A broad annotation-based filter can unintentionally exclude essential components. After adding exclusions, verify context startup and the features that depend on those beans.

## 10. Component Scan Differs from Entity Scan and Repository Scan

This is one of the most frequent sources of bugs in modular applications.

- **Component scan** discovers Spring components such as services, controllers, and configurations.
- **Entity scan** discovers JPA entity classes.
- **Repository scan** discovers Spring Data repository interfaces.

Setting `scanBasePackages` does not guarantee that entities and repositories in another module are discovered.

### 10.1. EntityScan

Suppose:

~~~text
com.example.shop
└── ShopApplication.java

com.example.platform.persistence
└── customer
    └── CustomerEntity.java
~~~

If entities sit outside the application's default scan package, configure:

~~~java
@SpringBootApplication
@EntityScan(basePackageClasses = CustomerEntity.class)
public class ShopApplication {
}
~~~

`@EntityScan` configures packages used to locate entity classes for relevant data auto-configurations. It does not register services in those packages as Spring beans.

### 10.2. EnableJpaRepositories

Repository interface:

~~~java
package com.example.platform.persistence.customer;

public interface CustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
~~~

You can specify the repository package:

~~~java
@SpringBootApplication
@EnableJpaRepositories(
        basePackageClasses = CustomerRepository.class
)
@EntityScan(basePackageClasses = CustomerEntity.class)
public class ShopApplication {
}
~~~

`@EnableJpaRepositories` controls scanning for Spring Data JPA repository interfaces. This mechanism is separate from component scanning.

### 10.3. Specifying Marker Classes

Using `basePackageClasses` makes package refactoring safer than string names:

~~~java
@EntityScan(basePackageClasses = {
        CustomerEntity.class,
        OrderEntity.class
})
~~~

However, if the list of entities/repositories keeps growing, consider a dedicated persistence module configuration to group responsibilities and provide a clean entry point.

## 11. Feature-Based Configuration with @ConfigurationProperties

Configuration values should also be grouped by feature rather than dumped into one huge class with hundreds of fields.

Example:

~~~text
com.example.shop
├── order
│   └── configuration
│       └── OrderProperties.java
├── payment
│   └── configuration
│       └── PaymentProperties.java
└── inventory
    └── configuration
        └── InventoryProperties.java
~~~

Payment properties:

~~~java
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) @Max(5) int maxAttempts
) {
}
~~~

Registration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

YAML:

~~~yaml
app:
  payment:
    base-url: https://payments.example.internal
    timeout: 2s
    max-attempts: 3
~~~

### 11.1. Benefits of Type-Safe Configuration

- Properties are strongly typed rather than manually parsed strings scattered everywhere.
- Validation is centralized at the binding boundary.
- Prefixes show which feature owns the configuration.
- Tests can supply module-specific properties.
- Configuration documentation is easy to organize by feature.

Avoid creating a giant `ApplicationProperties` class merely because all properties belong to the same application. Configuration groups should reflect features and ownership.

### 11.2. Do Not Store Secrets in Source-Controlled Defaults

Internal URIs may live in config files, but passwords/API keys should come from a secret manager or protected environment/config sources. Organizing by feature does not secure data by itself; you still need a dedicated secrets-handling policy.

## 12. @ConfigurationPropertiesScan Has Its Own Scope

You can use:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
~~~

When no package is specified, `@ConfigurationPropertiesScan` starts scanning from the annotated class's package according to its rules.

You can narrow it explicitly:

~~~java
@ConfigurationPropertiesScan(basePackageClasses = {
        PaymentProperties.class,
        OrderProperties.class
})
~~~

Key distinctions:

- `@ComponentScan` finds component stereotypes.
- `@ConfigurationPropertiesScan` finds `@ConfigurationProperties`-annotated types.
- `@EntityScan` finds JPA entities.
- `@EnableJpaRepositories` finds repository interfaces.

Do not expect one scan annotation to perform the work of the others.

## 13. Modular Monolith: Each Feature Has a Module Configuration

A modular monolith is a single deployable application organized into feature modules with clear responsibilities and internal APIs.

Example:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── api
│   ├── application
│   ├── domain
│   └── configuration
├── payment
│   ├── api
│   ├── application
│   ├── domain
│   └── configuration
└── inventory
    ├── api
    ├── application
    ├── domain
    └── configuration
~~~

Each feature can provide:

~~~java
@Configuration(proxyBeanMethods = false)
public class OrderModuleConfiguration {
    // Declare order module beans if needed.
}
~~~

The application composition root imports the modules permitted to run.

### 13.1. Module APIs Differ from Implementation Packages

If another feature needs to invoke `order`, it should depend on a stable API/application contract such as `OrderQueryService` or an interface. Avoid letting the `payment` feature directly access `order`'s internal repositories.

A broad component scan can make every technical class injectable, yet **being registered as a bean does not mean it is permitted as a public module API**.

### 13.2. Package-Private to Restrict Implementations

Java package visibility can help encapsulate implementation details:

~~~java
class JpaOrderRepositoryAdapter {
}
~~~

Without a `public` modifier, the class is accessible only within its package (under standard Java visibility rules). Keep in mind that component scanning and proxying have specific visibility requirements; design bean boundaries so Spring can instantiate and invoke beans cleanly.

Do not apply package-private mechanically to every bean. Choose visibility based on module APIs and how the framework needs access.

## 14. Multi-Module Gradle/Maven Builds Do Not Automatically Control Component Scanning

A multi-module project might look like:

~~~text
shop/
├── shop-app/
├── order-module/
├── payment-module/
└── platform-contracts/
~~~

Declaring module dependencies in Gradle/Maven only places artifacts and classes on the classpath. **Component scanning still obeys package boundaries and scan configuration**.

For example, if the app depends on `payment-module`, yet `payment` packages live outside the app's root package:

~~~text
com.example.shop.app
com.example.shop.payment
~~~

the main class in `com.example.shop.app` will not scan the sibling `com.example.shop.payment` by default. You must import the module configuration or specify base packages intentionally.

### 14.1. Use a Module Entry Point Instead of Scanning an Entire Group

In the library module:

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentModuleConfiguration {
    // Module beans.
}
~~~

In the app:

~~~java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
~~~

This clarifies the integration contract. The library can reorganize internal packages without requiring the application to scan the entire namespace.

### 14.2. Dependency Graph and Bean Graph Are Two Separate Graphs

- Gradle/Maven's dependency graph decides which artifacts/classes are on the classpath.
- Spring's bean graph decides which objects are registered and injected into each other.

Having a dependency on the classpath does not automatically make every class a bean. Conversely, scanning a component whose required dependency is missing from the runtime classpath will still fail bean creation.

## 15. Auto-Configuration and Component Scan Are Different Mechanisms

Spring Boot auto-configuration relies on conditions, classpath presence, and configuration to supply beans/infrastructure by convention. Component scanning discovers components declared by the application or libraries.

For example, `spring-boot-starter-web` triggers Boot to configure MVC and an embedded server. However, your application's controllers still must be discovered by component scanning or registered appropriately.

### 15.1. @SpringBootApplication Includes @EnableAutoConfiguration

`@SpringBootApplication` includes `@EnableAutoConfiguration`. Auto-configuration is not simply "scan every dependency package." It uses metadata/import selectors and conditions to determine which configurations apply.

Consequently:

- Broad component scanning can pick up components in unintended packages.
- Auto-configuration can activate due to classpath presence and conditions.
- Both bean sources can interact, such as a custom bean causing auto-configuration to back off.

### 15.2. Do Not Use Component Scanning to Enable Boot Features

If a feature requires auto-configuration, ensure the right dependencies and settings are present. Adding packages to component scanning does not substitute for required dependencies or classpath conditions.

### 15.3. Checking the Condition Report

In development environments:

~~~bash
java -jar app.jar --debug
~~~

The condition evaluation report explains why an auto-configuration matched or did not match. It complements inspecting component scans rather than replacing it.

## 16. Bean Name Conflicts When Scanning Too Broadly

By default, Spring derives bean names from class names using its bean naming conventions. Two components in different packages with the same simple class name can collide:

~~~java
package com.example.shop.order;

@Service
public class DefaultValidator {
}
~~~

~~~java
package com.example.shop.payment;

@Service
public class DefaultValidator {
}
~~~

If both are scanned, both default to the bean name `defaultValidator`. Depending on bean registration settings and version/configuration, the context may fail with a bean definition conflict or disallow overriding.

### 16.1. Do Not Fix Every Conflict with Long Bean Names

You can specify explicit names:

~~~java
@Service("orderValidator")
public class DefaultValidator {
}
~~~

However, if the application does not even need beans from one of those features, the proper fix is narrowing module scans or importing only required modules. Explicit names only resolve name collisions; they do not fix registering unnecessary components.

### 16.2. @Primary and @Qualifier Resolve Injection Ambiguity

When multiple implementations of the same interface genuinely belong in the context:

~~~java
public interface PaymentGateway {
    void charge();
}
~~~

~~~java
@Component
@Qualifier("card")
class CardPaymentGateway implements PaymentGateway {
    public void charge() {}
}
~~~

~~~java
@Component
@Qualifier("bank")
class BankPaymentGateway implements PaymentGateway {
    public void charge() {}
}
~~~

Consumers can specify a qualifier:

~~~java
@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`@Primary` can designate a default implementation when injecting by type with multiple candidates. However, do not use `@Primary` to paper over blurry module boundaries; if one implementation belongs only to a batch application, it likely should not be registered in the web application at all.

## 17. Profiles and Conditional Beans Should Not Replace Package Ownership

Example:

~~~java
@Configuration
@Profile("dev")
public class LocalPaymentConfiguration {
    // Fake gateway for development.
}
~~~

This component applies only when the matching profile is active, yet it still must be discovered/registered via scanning or import.

A broad package scan may find both production adapters and dev adapters; profiles/conditions decide which beans are instantiated. If conditions are wrong or profiles are misconfigured, the application can load the wrong implementation.

### 17.1. Profiles Are Runtime Choices; Module Boundaries Are Structural

- Package/module boundaries state which features belong to the application.
- Profiles state which configuration/implementation is used in a given environment.
- Conditions state whether a bean is created when criteria are met.

Do not use profiles to solve package-structure problems. Do not use package scanning to model dev/test/prod environments.

## 18. Organizing Configuration Classes by Responsibility

An application may have configuration classes like:

~~~text
com.example.shop
├── ShopApplication.java
├── configuration
│   ├── WebConfiguration.java
│   ├── SecurityConfiguration.java
│   └── JacksonConfiguration.java
├── order
│   └── configuration
│       └── OrderConfiguration.java
├── payment
│   └── configuration
│       ├── PaymentConfiguration.java
│       └── PaymentProperties.java
└── inventory
    └── configuration
        └── InventoryConfiguration.java
~~~

Distinguish:

- **Application-wide configuration**: affects multiple features or the entire app, such as MVC converters, security filter chains, and serialization defaults.
- **Feature configuration**: serves a single module, such as payment clients, order policies, or inventory integration.
- **Infrastructure configuration**: connects databases, messaging, caches, or external platforms; should have a clear owner and API.

### 18.1. Avoid a Massive AppConfig

A single class holding dozens of `@Bean` methods for every module increases configuration coupling. Editing payment settings can inadvertently break order wiring or test setups.

Split configuration by feature and responsibility, without necessarily putting one bean per file. Group beans sharing a lifecycle and dependencies around a single concern.

### 18.2. Avoid Configuration Outside Its Ownership

If `PaymentConfiguration` creates beans for `order` and `inventory`, the class name no longer reflects its responsibility. Move shared pieces into a dedicated infrastructure/module or let the composition root connect the modules.

## 19. Testing Packages and Component Scans

Tests should reflect how the application is actually assembled.

### 19.1. @SpringBootTest Locating Application Configuration

A test:

~~~java
@SpringBootTest
class ShopApplicationTest {
}
~~~

typically searches upward from the test's package for `@SpringBootConfiguration` or an application configuration following test bootstrap rules. If the test sits outside the package tree or multiple application configurations exist, specify the class explicitly:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class ShopApplicationTest {
}
~~~

Specifying the application class ensures the test uses the intended composition root.

### 19.2. Slice Tests Limit Loaded Components

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Initializes only the MVC slice relevant to the test.
}
~~~

Slice tests do not run a full application component scan. Service dependencies may need to be mocked or imported via focused configuration.

### 19.3. Testing Module Configurations Independently

You can verify a module using a minimal context:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PaymentModuleConfiguration.class)
class PaymentModuleConfigurationTest {
    // Assert expected module beans/contracts.
}
~~~

If the module configuration relies on auto-configuration or properties, include the corresponding test configuration. The goal is verifying that the module's entry point registers the right beans without scanning every application package.

### 19.4. Verifying Unwanted Beans Are Absent

An integration test can assert that components from another application do not appear:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class ShopBeanBoundaryTest {

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotRegisterAnalyticsController() {
        assertThat(context.containsBean("analyticsController")).isFalse();
    }
}
~~~

The bean name in the example must match the actual component. If the component derives a different name or is registered differently, adjust the assertion to match your contract.

Boundary tests should prioritize checking **module behavior/APIs** rather than locking down internal bean names that are likely to be refactored.

## 20. Troubleshooting Missing or Extra Beans

### 20.1. NoSuchBeanDefinitionException

Example:

~~~text
No qualifying bean of type 'com.example.shop.payment.PaymentGateway' available
~~~

Possible causes:

- The `payment` package lies outside component scan scope.
- The module configuration has not been imported.
- The bean was excluded by a condition or profile.
- The implementation lacks a stereotype or `@Bean` declaration.
- The module is missing from runtime classpath dependencies.
- Tests use a different application configuration than production.

Resolution: verify the module entry point, bean registration conditions, and scan/import boundaries. Do not widen scanning to the highest root package just to make the error go away.

### 20.2. BeanDefinitionOverrideException or ConflictingBeanDefinitionException

Causes can include two components sharing a bean name or a configuration being imported/scanned multiple times in a conflicting way.

Check:

- Do two classes have the same component name?
- Are there overlapping component scan configurations?
- Is a package both scanned and manually imported?
- Are custom bean names colliding?
- Is a module present in the application context that does not belong there?

Assign explicit bean names if both truly belong. Otherwise, narrow the registration scope.

### 20.3. Beans Created Twice

This can happen when configuration registers the same class through multiple paths or creates a bean manually while component scanning also picks it up. Inspect context bean definitions and the configuration import graph.

Do not assume every duplicate object is caused by component scanning; some beans may be prototype-scoped or instantiated manually outside the container.

### 20.4. App Starts Yet Unexpected Routes Appear

A controller from another module may have been scanned into the context. Check component scan base packages and module ownership. For sensitive APIs, check security authorization too; keeping unwanted routes out of the context reduces attack surface better than relying solely on route protection.

## 21. Inspecting Bean Registrations

In development environments, you can inspect bean definitions via ApplicationContext:

~~~java
String[] names = context.getBeanDefinitionNames();

Arrays.stream(names)
        .sorted()
        .forEach(System.out::println);
~~~

This can produce lengthy output. Filter by prefix, package, or bean type under investigation.

The Spring Boot Actuator `beans` endpoint can also display the bean graph when added and exposed appropriately. This exposes internal structure and should not be broadly exposed in production.

### 21.1. Condition Reports and Bean Lists Answer Different Questions

- The bean list shows which beans are registered.
- The condition report shows which auto-configuration conditions matched or backed off.
- Component scan debug logs show which candidates were found or filtered out.
- The dependency tree shows which classes/libraries are on the classpath.

No single source answers every question. Pick the tool matching the question being investigated.

## 22. Broad Component Scanning and Startup Performance

Overly broad component scanning can increase the number of candidates inspected, bean definitions registered, and context initialization work. However, do not blame every slow startup on component scanning.

Other causes can include:

- Beans opening network or database connections synchronously.
- Migrations or schema initialization.
- A huge classpath with many auto-configurations.
- Bean factory post-processors.
- Configuration property validation.
- External service calls during initialization.
- Classpath scanning by ORMs or other frameworks.

Restricting scans keeps the context controllable and avoids unnecessary work, though actual startup measurements should confirm performance bottlenecks before optimizing.

### 22.1. Do Not Set All Components to Lazy to Hide Startup Issues

`spring.main.lazy-initialization=true` defers bean creation, yet missing dependencies or misconfigurations may surface only when a bean is first used. It does not fix module boundaries and can delay failure detection.

## 23. Complete Feature-Based Design Example

Structure:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── api
│   │   └── OrderController.java
│   ├── application
│   │   └── OrderService.java
│   ├── domain
│   │   └── Order.java
│   └── configuration
│       └── OrderModuleConfiguration.java
├── payment
│   ├── application
│   │   └── PaymentService.java
│   ├── infrastructure
│   │   └── HttpPaymentGateway.java
│   └── configuration
│       ├── PaymentProperties.java
│       └── PaymentModuleConfiguration.java
└── inventory
    ├── application
    │   └── InventoryService.java
    └── configuration
        └── InventoryModuleConfiguration.java
~~~

Main application:

~~~java
@SpringBootApplication
@Import({
        OrderModuleConfiguration.class,
        PaymentModuleConfiguration.class,
        InventoryModuleConfiguration.class
})
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Payment module:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties,
            RestClient.Builder builder) {

        RestClient client = builder
                .baseUrl(properties.baseUrl())
                .build();

        return new HttpPaymentGateway(client);
    }

    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

Properties:

~~~java
@ConfigurationProperties("app.payment")
public record PaymentProperties(URI baseUrl) {
}
~~~

This design shows the application root assembling features while each module registers its own implementations and configuration. If a module is small and all components already live under a clean root scan, you do not need a module configuration just to wrap a single component. Use an appropriate level of explicitness matching actual complexity and boundaries.

## 24. Design Choices to Avoid

### 24.1. Placing the Main Class in the Company-Wide Package

~~~text
com.company
├── service-a
├── service-b
├── batch
└── shared-platform
~~~

If each service is an independent application, placing the main class in `com.company` can scan everything. Place each application class in its own service package and import shared modules explicitly.

### 24.2. Scanning an Entire Namespace Just to "Let Spring Find Things"

A configuration like:

~~~java
@ComponentScan("com")
~~~

is almost always too broad for real applications. It can pick up components from dependencies, other applications, or packages not owned by the current service.

### 24.3. Having Every Module Scan Everything Under a Common Namespace

If every module uses `@ComponentScan("com.example")`, module boundaries become largely meaningless. Explicit module entry points or dedicated base packages make composition far clearer.

### 24.4. One Configuration Class Containing Every Feature

A massive `ApplicationConfig` couples features together and makes isolated testing difficult. Split by concern/feature and let the application composition root assemble them.

### 24.5. Using @Primary to Solve Every Bean Conflict

`@Primary` chooses a default candidate for type-based injection. It does not solve bean name conflicts and does not remove unwanted beans from the context.

### 24.6. Growing Exclude Filter Lists

If you have to exclude dozens of components from scans, re-evaluate the base package. An allowlist/import list or cleaner package structure is usually easier to maintain.

### 24.7. Treating Package-Private as a Security Boundary

Java package visibility supports code encapsulation, not security enforcement for HTTP routes, databases, or secrets. Use appropriate security controls for protected resources.

## 25. Design Checklist for a New Application

Before adding many components:

1. The main application class sits in the root package of its own application module.
2. Do not place the main class in the default package or a parent package shared by multiple applications.
3. Feature packages reflect business ownership.
4. Shared packages hold only genuinely shared abstractions.
5. Feature-specific configurations live near their feature.
6. `@ConfigurationProperties` use feature-scoped prefixes and appropriate validation.
7. Component scanning has explicit base packages that are not widened arbitrarily.
8. Modules outside the scan boundary are imported via explicit entry points.
9. Entity scanning and repository scanning are configured separately when needed.
10. Profiles/conditional beans do not accidentally select the wrong environment implementation.
11. Application context tests verify required modules are present.
12. Negative tests verify out-of-scope application components are absent.
13. Bean conflicts are resolved through ownership/names/qualifiers matching the root cause.
14. Actuator bean diagnostics are not broadly exposed in production.

The checklist guides architectural review; do not add unnecessary configuration complexity to a small application with a few components inside a clean root package.

## 26. Practice Exercises

### Exercise 1 — Observe Default Component Scanning

Create a main class in `com.example.shop` and two components in `com.example.shop.order` and `com.example.shop.payment`. Start the context and verify both beans are discovered.

### Exercise 2 — Main Class Placed Too Deep

Move the main class down to `com.example.shop.order.bootstrap`. Observe that the `payment` bean is no longer discovered by default scanning. Restore it by moving the main class back to the root package or configuring scan scope appropriately.

### Exercise 3 — Overly Broad Scan

Create a `com.example.analytics` package with a controller. Place the application class in `com.example` and observe the unintended route appearing. Narrow the scan so `analytics` is no longer part of the `shop` context.

### Exercise 4 — Package by Layer vs. Feature

Organize the same `order` feature under both layouts. Compare locating controllers, services, and repositories, and determine which layout clarifies team ownership in a simulated project.

### Exercise 5 — Import Module Configuration

Create `PaymentModuleConfiguration` registering a gateway and service. Place the `payment` package outside the scan boundary. Use `@Import` to integrate the module and write a test verifying the beans are created.

### Exercise 6 — Feature-Scoped ConfigurationProperties

Create `OrderProperties` and `PaymentProperties` with distinct prefixes. Omit a required value and observe binding validation. Identify which module owns each property.

### Exercise 7 — Conditional Module

Use `@ConditionalOnProperty` to toggle payment integration on/off. Test `true`, `false`, and missing property cases. Explain the effect of `matchIfMissing` if configured.

### Exercise 8 — Component Scan Filters

Create a legacy component and exclude it via an `ASSIGNABLE_TYPE` filter. Then narrow the base package to check whether the exclusion is still needed.

### Exercise 9 — Entity and Repository Scans

Place a JPA entity/repository in a package outside the application root. Configure `@EntityScan` and `@EnableJpaRepositories` separately. Verify why `scanBasePackages` does not cover those two scans automatically.

### Exercise 10 — Bean Name Conflicts

Create two `@Service` classes with the same name in two feature packages and scan both. Observe the conflict. Try setting distinct bean names, then evaluate whether both beans truly belong in the same application context.

### Exercise 11 — Application Composition Root

Create a web app and a batch app sharing contract modules. Have each main application import only the modules it needs. Verify the batch app does not register unrelated controllers.

### Exercise 12 — Boundary Tests

Write an integration test verifying the application context contains required features and lacks beans from out-of-scope modules. Specify the explicit application class on `@SpringBootTest` so test bootstrapping does not depend on the test's package location.

## 27. Key Takeaways

Spring Boot component scanning searches from the main application class's package downward by default. Placing the main class in the application's own root package lets feature packages be discovered without scanning an entire shared namespace. An overly broad package can accidentally pull controllers, services, configurations, or other modules into the ApplicationContext.

Organizing **by feature** keeps controllers, application services, domain types, repository adapters, and configuration close to the owning capability. Each module can expose a configuration entry point while the application class acts as the composition root using `@Import` to assemble the right modules. Use `@Conditional` for optional integrations and `@ConfigurationProperties` with feature prefixes for clear configuration.

Distinguish component scanning from entity scanning, repository scanning, and configuration-properties scanning. `scanBasePackages` governs only component scanning; JPA entities and Spring Data repositories have separate mechanisms. When encountering missing or extra beans, inspect base packages, the import graph, conditions/profiles, and runtime dependencies before widening scans or adding `@Primary`.

**A controllable ApplicationContext starts with clear module boundaries.** Let each application know which features it owns, which configurations it needs, and which beans are permitted to participate at runtime.
