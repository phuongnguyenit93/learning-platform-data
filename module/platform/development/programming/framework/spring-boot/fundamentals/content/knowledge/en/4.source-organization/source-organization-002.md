# Main Class Location and Its Impact on Component Discovery Scope

In Spring Boot, which package you place the startup class (often called the **main class**) in can determine which controllers, services, repositories, configuration classes, and data entities are discovered by the framework. Two projects with the same business code and the same dependencies, but with different startup class locations, can produce different startup results: one project creates all beans, while the other reports missing beans or fails to register endpoints.

The reason lies in the **root package** used by scanning and auto-configuration mechanisms. Understanding that scope helps you organize source code for scalability and avoid adding manual configuration just to fix component discovery errors.

## 1. What Does "Main Class" Mean in Spring Boot?

A Spring Boot application usually starts from the following class:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

There are two concepts to distinguish:

1. **The `public static void main(String[] args)` method** is the Java program's entry point when running that class.
2. **The configuration class annotated with `@SpringBootApplication`** is the primary configuration source Spring Boot uses to build the application context.

Normally both roles reside in `ShopApplication`, so we refer to it collectively as the main class. However, **the default scan scope is tied to the package of the Spring configuration class**, rather than being based on the name `main`, the directory where the command is run, the JAR filename, or the location of the `main` method.

For example, if another launcher calls:

~~~java
SpringApplication.run(ShopApplication.class, args);
~~~

then the package containing `ShopApplication` remains the basis for related default mechanisms, even if the launcher is located in another package.

## 2. How Does `@SpringBootApplication` Initialize Component Discovery?

`@SpringBootApplication` is a composite annotation encompassing three main capabilities:

| Component Annotation | Role |
|---|---|
| `@SpringBootConfiguration` | Marks the class as a Spring Boot configuration source; based on `@Configuration`. |
| `@EnableAutoConfiguration` | Allows Boot to auto-configure based on existing dependencies, properties, beans, and conditions. |
| `@ComponentScan` | Searches for components within specified packages, or the default scope if none are specified. |

When no custom scope is declared, **component scan starts from the package containing the class annotated with `@SpringBootApplication` and traverses its subpackages**.

Suppose:

~~~text
com.example.shop
├── ShopApplication
├── api
│   └── OrderController
├── service
│   └── OrderService
├── repository
│   └── OrderRepository
└── config
    └── ShopConfiguration
~~~

`ShopApplication` is placed in `com.example.shop`. Default component scan examines eligible classes in:

~~~text
com.example.shop
com.example.shop.api
com.example.shop.service
com.example.shop.repository
com.example.shop.config
... and deeper subpackages
~~~

**Parent packages are not scanned upward**, and **sibling packages are not automatically scanned**:

~~~text
com.example
├── shop                 ← where ShopApplication is placed
│   ├── api              ← within scope
│   └── service          ← within scope
├── shared               ← outside default component scan scope
└── admin                ← outside default component scan scope
~~~

This is a **Java package** relationship, not merely how folders appear in an IDE. The directory structure under `src/main/java` should accurately reflect the `package` declaration in each file.

## 3. Which Classes Are Registered as Beans by Component Scan?

Component scanning searches for classes with appropriate annotations, such as:

| Annotation | Common Meaning | Discoverable by Component Scan? |
|---|---|---|
| `@Component` | General application bean | Yes |
| `@Service` | Business-processing component | Yes; essentially a stereotype of `@Component` |
| `@Repository` | Data-access component written as a class | Yes; also a stereotype of `@Component` |
| `@Controller` | Spring MVC/WebFlux controller | Yes |
| `@RestController` | Controller returning HTTP data, typically JSON | Yes |
| `@Configuration` | Class declaring configuration and `@Bean` methods | Yes |
| `@Entity` | Entity mapping JPA data | **No**; belongs to JPA's entity management mechanism |
| `@ConfigurationProperties` | Describes binding configuration to an object | Not automatically from this annotation alone; requires an appropriate registration mechanism |

Example:

~~~java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long discountedPrice(long originalPrice) {
        return originalPrice * 90 / 100;
    }
}
~~~

~~~java
package com.example.shop.api;

import com.example.shop.service.PriceService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    private final PriceService priceService;

    public PriceController(PriceService priceService) {
        this.priceService = priceService;
    }

    @GetMapping("/prices/discounted")
    public long discountedPrice() {
        return priceService.discountedPrice(100);
    }
}
~~~

Because both classes reside under `com.example.shop`, Spring can register `PriceService` and `PriceController`; constructor injection connects the two beans during context initialization.

Note: **being in the right package is not enough** for a regular Java class to become a Spring bean. The class must also be registered via `@Component`/stereotypes, `@Bean` methods, `@Import`, auto-configuration, or another appropriate bean registration mechanism.

## 4. Why Does Placing the Main Class Too Deeply Cause Errors?

Consider the following structure:

~~~text
src/main/java/
└── com/example/shop/
    ├── api/
    │   ├── ShopApplication.java  ← @SpringBootApplication
    │   └── OrderController.java
    ├── service/
    │   └── OrderService.java
    └── config/
        └── DatabaseConfiguration.java
~~~

If `ShopApplication` declares:

~~~java
package com.example.shop.api;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

then the default component scan scope starts at `com.example.shop.api`. `OrderController` can be discovered, while `OrderService` in `com.example.shop.service` and `DatabaseConfiguration` in `com.example.shop.config` fall outside the scope.

If the controller requires `OrderService` via its constructor, bean creation can fail with a message like:

~~~text
Parameter 0 of constructor in ...OrderController
required a bean of type '...OrderService'
that could not be found.
~~~

If there is no required dependency, the application might even **start successfully but lack endpoints or features**. For example, placing a controller outside the scan area prevents handlers from being registered; requests to the corresponding URL may receive HTTP 404.

### Simplest Fix

Move `ShopApplication` up to the common root package:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java        ← @SpringBootApplication
    ├── api/
    ├── service/
    ├── repository/
    └── config/
~~~

Now `com.example.shop` covers all subpackage groups. This is the preferred structure in typical applications because the scope is clear and does not require manually declaring `scanBasePackages`.

## 5. Main Location Also Relates to Entities and Spring Data Repositories, via Different Mechanisms

A common misconception is that "`@ComponentScan` finds everything, including JPA entities and Spring Data repository interfaces." In reality, there are **separate discovery systems**:

| Type | Primary Mechanism | Default Scope Relates To |
|---|---|---|
| Controllers, services, components, configurations | Spring component scan | Package of `@SpringBootApplication` (if not customized) |
| Spring Boot auto-configuration | Selects configurations based on classpath and conditions | Does not work like scanning every class; some auto-configurations use "auto-configuration packages" |
| JPA entities | Entity scanning / JPA persistence-unit configuration | Usually relies on auto-configuration packages if not explicitly configured |
| Spring Data JPA repository interfaces | Spring Data repository scanning | Usually relies on auto-configuration packages if not explicitly configured |
| `@ConfigurationProperties` classes | Configuration-properties scanning/registration | Depends on `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or another bean registration mechanism |

`@EnableAutoConfiguration` indirectly sets the **auto-configuration package** based on the location of the Boot configuration class. Many auto-configurations, including Spring Data/JPA integrations, use this package information to choose defaults. It is not identical to component scan.

Suppose we have:

~~~text
com.example.shop
├── ShopApplication           ← @SpringBootApplication
├── api                       ← controller
└── service                   ← service

com.example.storage
├── entity
│   └── OrderEntity           ← @Entity
└── repository
    └── OrderJpaRepository    ← extends JpaRepository
~~~

`OrderEntity` and `OrderJpaRepository` lie outside the application's default packages. Even if `com.example.storage` is added to **component scan**, Spring Data JPA may still fail to discover the entity/repository because these two constructs use different registration paths.

When it is genuinely necessary to keep packages separate, you can declare them explicitly:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.storage"
})
@EntityScan(basePackages = "com.example.storage.entity")
@EnableJpaRepositories(
        basePackages = "com.example.storage.repository"
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

In this example:

- `scanBasePackages` expands **component scan** for ordinary components and configurations.
- `@EntityScan` defines the scope for finding entities managed by JPA.
- `@EnableJpaRepositories` defines the scope for finding Spring Data JPA repository interfaces.

Not every project needs all three. Explicit configuration should only be added when the package structure or integration requirements make the defaults unsuitable. The example above assumes the application already has the Spring Data JPA starter, a database driver, and a valid connection configuration.

### Distinguishing Bean Errors from Entity Errors

The two cases can surface at different stages:

~~~text
No qualifying bean of type '...OrderService'
~~~

This error typically suggests checking bean registration: annotations, package location, bean creation conditions, profiles, and configuration.

~~~text
Not a managed type: class ...OrderEntity
~~~

This error points to the entity not being part of the persistence unit / not being mapped as expected. Adding `@ComponentScan` alone usually does not fix the root cause.

## 6. Intentional Ways to Adjust Scope

### 6.1. Placing `@SpringBootApplication` in the Common Root Package

This is the clearest default choice:

~~~text
com.example.inventory
├── InventoryApplication.java
├── product
│   ├── ProductController.java
│   ├── ProductService.java
│   └── ProductRepository.java
└── order
    ├── OrderController.java
    ├── OrderService.java
    └── OrderRepository.java
~~~

Organizing by **feature** (product/order) or by **layer** (controller/service/repository) can both work, as long as everything belongs to appropriate subpackages. It is not mandatory to place components directly next to the main class.

### 6.2. Specifying `scanBasePackages`

When components truly reside in multiple separate packages:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example.inventory",
        "com.example.shared.audit"
})
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

Only the specified packages and their subpackages are scanned by this configuration. Avoid broadening indiscriminately to `com` or `org`, as it may pick up unwanted beans, cause bean name collisions, or trigger configuration conflicts.

If you want to reduce errors from package renaming, you can use a **marker class**:

~~~java
// com.example.shared.audit.AuditPackageMarker
package com.example.shared.audit;

public interface AuditPackageMarker {
}
~~~

~~~java
// com.example.inventory.InventoryApplication
package com.example.inventory;

import com.example.shared.audit.AuditPackageMarker;

@SpringBootApplication(
        scanBasePackageClasses = {
                InventoryApplication.class,
                AuditPackageMarker.class
        }
)
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

`scanBasePackageClasses` uses the packages of the specified classes. The marker does not need to be a Spring bean and does not need to contain logic.

### 6.3. Importing a Specific Configuration with `@Import`

If you only need a single configuration outside the scan scope, you do not necessarily have to scan an entire package:

~~~java
package com.example.shop;

import com.example.shared.config.AuditConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(AuditConfiguration.class)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@Import` explicitly registers the selected configuration. For a `@Configuration` containing `@Bean` methods, this is often the right choice when reusing a piece of configuration from another module.

### 6.4. Customizing Data Configuration According to the Technology

If JPA repositories are placed outside auto-configuration packages, use `@EnableJpaRepositories` with an appropriate base package; if entities are placed outside, use `@EntityScan`. For MongoDB, Redis, R2DBC, or other technologies, use the **corresponding repository configuration mechanism**—do not assume `@EnableJpaRepositories` applies to every Spring Data module.

For configuration classes such as:

~~~java
@ConfigurationProperties(prefix = "app.billing")
public record BillingProperties(String currency, boolean enabled) {
}
~~~

they can be registered using `@EnableConfigurationProperties(BillingProperties.class)` or scanned via `@ConfigurationPropertiesScan` placed in an appropriate location. Expanding `scanBasePackages` does not automatically replace every configuration properties registration mechanism.

## 7. Multi-Module: Same Classpath Does Not Guarantee Same Scan Scope

In an application split into multiple Gradle/Maven modules, for example:

~~~text
shop-app/
  com.example.shop.ShopApplication
shop-core/
  com.example.shop.core.PricingService
shop-integration/
  com.example.integration.ExternalClient
~~~

If all three modules have valid dependency declarations, their classes can appear together on the **runtime classpath**. However, classpath and component scan are two different conditions:

1. Spring can only use classes that the runtime **can actually load** from dependencies/classpath.
2. Component scan only detects classes that **fall within the scanned package scope** and satisfy bean registration conditions.

Since `com.example.shop.core` is a subpackage of `com.example.shop`, `PricingService` can be scanned by default when the dependency is present. However, `com.example.integration.ExternalClient` is in a sibling package; if you want to use its bean, you must explicitly configure how it is registered.

You should not solve this situation by adding an entire third-party library to component scan. Reusable libraries can provide configuration via `@Import`, properly declared starters and auto-configuration, or specific bean registration APIs. Which option fits depends on the library's integration contract.

## 8. Misplacing the Main Class in the "Default Package" Is Even More Dangerous

Java allows writing a class without a `package` declaration:

~~~java
// Missing: package com.example.shop;
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

This is the **default package** (unnamed package). Spring Boot recommends avoiding this placement because package-based annotations like `@ComponentScan`, `@EntityScan`, or `@SpringBootApplication` can cause the system to inspect a very broad scope across the classpath. The consequences can include unintended class discovery, configuration conflicts, increased startup time, or hard-to-trace errors.

Instead, always place the startup class in a named package, such as `com.example.shop`, at a level encompassing the application's packages.

## 9. Impact on Testing and How Spring Boot Finds Test Configuration

The location of the `@SpringBootApplication` class also affects how certain Spring Boot tests locate the configuration class:

~~~text
src/main/java/com/example/shop/ShopApplication.java
src/main/java/com/example/shop/service/OrderService.java
src/test/java/com/example/shop/service/OrderServiceTest.java
~~~

In many Spring Boot tests, if classes are not specified, the framework can **search upward through the package hierarchy from the test class location** to find `@SpringBootConfiguration`. When `ShopApplication` is in `com.example.shop`, tests in `com.example.shop.service` usually find the configuration.

Conversely, if the main class is placed in `com.example.shop.api` while tests are in `com.example.shop.service`, searching parent packages may fail to find the required configuration class.

An explicit way to specify it when needed:

~~~java
package com.example.shop.service;

import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(classes = ShopApplication.class)
class OrderServiceIntegrationTest {
    @Test
    void contextLoads() {
        // Integration tests will add assertions as required.
    }
}
~~~

This test only illustrates the configuration-class selection mechanism; it does not by itself verify that business logic is correct. For slice tests like `@WebMvcTest` or `@DataJpaTest`, bean scope and bootstrap mechanics also depend on the slice annotation. Therefore, placing the main class in the root package still makes the test structure more predictable.

## 10. How to Diagnose When Spring Cannot Find a Component

When you add `@Service` or `@RestController` and the application does not recognize it, investigate in order:

1. **Identify the actual configuration class** passed to `SpringApplication.run(...)` and check the package containing `@SpringBootApplication`.
2. **Read the `package ...;` line** in the missing class. Compare the parent/child relationship of the two packages.
3. **Check bean registration annotations**: `@Component`, `@Service`, `@RestController`, `@Configuration`, `@Bean`, or framework-specific registration methods.
4. **Check classpath/runtime dependencies**, especially if the class lives in another Gradle/Maven module.
5. **Distinguish the type of missing component**: Spring components, Spring Data repositories, JPA entities, or configuration properties require different scanning/registration mechanisms.
6. **Check bean creation conditions**: `@Profile`, `@Conditional`, auto-configuration, beans excluded by filters, or duplicate configurations can prevent a bean from existing even when the package is right.

Some common symptoms:

| Symptom | What to Check |
|---|---|
| `NoSuchBeanDefinitionException` / missing constructor dependency error | Is the bean registered? Is its package within scan scope? Is it excluded by conditions/profiles? |
| Calling URL always returns 404 even though controller is written | Is the controller registered, is the mapping correct, and do path/context-path match? |
| `Not a managed type` when using a JPA repository | Does the entity have appropriate JPA annotations and fall within entity scanning scope? |
| Spring Data repository interface does not get a bean created | Do the Spring Data module and repository scanning config pick up the interface's package? |
| Error failing to find `@SpringBootConfiguration` in tests | Location of the test class relative to the main class and the `classes` attribute of the test annotation. |
| Same application yields different results when moving modules/packages | Recheck runtime classpath, package scan, and imported configurations. |

Spring Boot can provide an auto-configuration condition report when debug mode is enabled, for instance by setting `debug=true` in configuration or passing `--debug` at launch. That report helps explain why an auto-configuration was applied or excluded. However, **the condition report is not a complete list of every class examined by component scan**. When you need to inspect actual beans, you can observe the `ApplicationContext` or Actuator's `beans` endpoint if the project has it enabled and properly secured.

## 11. Principles for Maintainable Source Organization

**Principle 1 — Choose a clear root package.** For example `vn.example.orders` or `com.example.shop`; place `@SpringBootApplication` right inside that package, with features and layers in subpackages.

**Principle 2 — Distinguish scanning mechanisms.** Component scanning, entity scanning, Spring Data repository scanning, and configuration-properties scanning have different scopes and activation methods.

**Principle 3 — Expand scope only with good reason.** If sharing components across multiple applications, prefer declaring specific packages or importing specific configurations. Avoid scanning a massive namespace just to fix one missing bean.

**Principle 4 — When changing packages, verify both runtime and tests.** Moving the main class can change which beans are scanned, default entity/repository scopes, and tests' ability to auto-discover configuration.

**Principle 5 — Use directory structure to reflect architecture.** Organizing packages by feature or by layer both work; what matters is that the main class sits at the true root of the application and dependencies between modules are clear.

Example of a clean, convenient structure for a Spring Boot application:

~~~text
src/
├── main/java/
│   └── com/example/shop/
│       ├── ShopApplication.java
│       ├── order/
│       │   ├── OrderController.java
│       │   ├── OrderService.java
│       │   ├── OrderRepository.java
│       │   └── OrderEntity.java
│       ├── product/
│       │   ├── ProductController.java
│       │   ├── ProductService.java
│       │   └── ProductRepository.java
│       └── config/
│           └── ShopConfiguration.java
└── test/java/
    └── com/example/shop/
        ├── order/
        └── product/
~~~

In this structure, **the main class location creates a predictable default boundary**. Spring Boot takes responsibility for setting up the application context, component scan finds eligible beans, and other data or configuration mechanisms use their respective scopes. By establishing that boundary properly from the start, the project can add new controllers, services, and features without repeatedly running into "bean not found" errors caused by mislocated packages.
