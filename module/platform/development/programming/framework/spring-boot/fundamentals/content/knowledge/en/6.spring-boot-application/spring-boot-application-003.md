# What Scope Does `@ComponentScan` Search for Bean Candidates?

In Spring Boot, you only need to write `@Service`, `@Repository`, or `@RestController` on a class and then use constructor injection to use that class. Yet this mechanism does not apply to every class in every package of a project. **Spring must know which package scope to scan**, identify the classes eligible to become beans, and register the appropriate bean definitions in the application context.

That is the role of `@ComponentScan`. In a typical Spring Boot application, `@SpringBootApplication` already includes `@ComponentScan` as a meta-annotation, so you rarely have to declare it manually. Understanding the default scan scope will help you organize packages cleanly and troubleshoot dependency injection errors such as "bean could not be found."

## 1. What Is `@ComponentScan`?

`@ComponentScan` is a Spring Framework annotation that enables Spring to **search for bean candidate classes** in one or more packages based on configured matching criteria. A class annotated with `@Component` or a stereotype built on `@Component` can be discovered during scanning.

Example:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String productName() {
        return "Notebook";
    }
}
```

When package `com.example.shop.service` falls within the component scan scope, Spring can typically detect `ProductService` and register the corresponding bean definition. The container then creates and manages the bean according to its configured scope, lifecycle, and dependencies.

Distinguishing closely related concepts:

| Concept | Meaning |
| --- | --- |
| **Component scanning** | Searching for and identifying bean candidate classes in the specified packages |
| **Bean definition** | Information Spring uses to create, configure, and manage a bean |
| **Bean** | An object managed by the Spring IoC container |
| **Dependency injection** | The container supplying dependent beans to another bean |
| **Auto-configuration** | Spring Boot automatically applying configurations based on classpath, properties, and relevant conditions |

**Note:** "being detected as a candidate" does not guarantee the bean will be created successfully. Bean definitions may be subject to conditions, profiles, filters, or configuration errors; actual instantiation also depends on lifecycle and scope.

## 2. How Does `@SpringBootApplication` Relate to Component Scanning?

A Spring Boot startup class typically looks like:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`@SpringBootApplication` combines the primary capabilities:

```text
@SpringBootApplication
    ├── @SpringBootConfiguration
    ├── @EnableAutoConfiguration
    └── @ComponentScan
```

Specifically:

- `@SpringBootConfiguration` identifies the application's primary configuration class.
- `@EnableAutoConfiguration` lets Spring Boot apply auto-configurations when their conditions are satisfied.
- `@ComponentScan` lets Spring find bean candidates starting from the appropriate root package.

In the example above, because `ShopApplication` is in package `com.example.shop`, **the default scan scope starts at `com.example.shop`**, covering that package and all of its subpackages.

Not every bean in an application comes from component scanning. Beans can also be created through `@Bean`, `@Import`, auto-configuration, or dedicated registration mechanisms from Spring Data and integrated libraries.

## 3. Default Scope: The Package Containing the Configuration Class and Its Subpackages

When `@ComponentScan` does not specify `basePackages` or `basePackageClasses`, Spring uses **the package of the class declaring `@ComponentScan`** as the root. In applications using `@SpringBootApplication` directly on the main class, that is typically the package containing the main class.

Example structure:

```text
src/main/java/
└── com/
    └── example/
        ├── shop/
        │   ├── ShopApplication.java       <-- @SpringBootApplication
        │   ├── controller/
        │   │   └── ProductController.java <-- scanned
        │   ├── service/
        │   │   └── ProductService.java    <-- scanned
        │   ├── repository/
        │   │   └── ProductCache.java      <-- scanned if it is a valid component
        │   └── config/
        │       └── TimeConfig.java        <-- scanned if it is a valid component
        └── shared/
            └── SharedFormatter.java       <-- outside the default scope
```

With `ShopApplication` located at `com.example.shop`, the following packages are within the default region:

```text
com.example.shop
com.example.shop.controller
com.example.shop.service
com.example.shop.repository
com.example.shop.config
com.example.shop.service.internal
```

These packages are **not** within the default scope:

```text
com.example
com.example.shared
com.example.billing
org.othercompany.common
```

This rule is based on **Java package names**, not on whether files live in the same repository, the same Gradle/Maven module, or the same `src` directory. A dependency JAR on the classpath is also not scanned in full by default if its packages fall outside the scan region.

### 3.1. Example of Three Classes in the Same Application

`ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

`ProductService.java`:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String findName() {
        return "Keyboard";
    }
}
```

`ProductController.java`:

```java
package com.example.shop.controller;

import com.example.shop.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/product-name")
    public String productName() {
        return productService.findName();
    }
}
```

In an application with Spring Web appropriately configured and running on the default port, the endpoint:

```text
GET http://localhost:8080/product-name
```

can return:

```text
Keyboard
```

Spring discovers `ProductService` and `ProductController` because both classes sit in subpackages of `com.example.shop`, then resolves the controller's constructor parameter to the `ProductService` bean.

### 3.2. Trying a Class in a Sibling Package

Suppose we change the package of `ProductService` to:

```java
package com.example.shared;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String findName() {
        return "Keyboard";
    }
}
```

After updating the controller's import so the program still compiles, the service class **no longer resides under `com.example.shop`**. Without another bean registration mechanism, Spring may fail when creating the controller:

```text
Parameter 0 of constructor in ...ProductController
required a bean of type '...ProductService' that could not be found.
```

The actual message varies by Spring Boot version and injection style. The point to check here is that **the service is on the classpath but outside the component scan region**. Being able to import a class in Java only proves the class can be referenced at compile time; an import does not cause Spring to register a bean automatically.

## 4. Which Bean Candidates Does Spring Recognize?

In standard component scanning, Spring recognizes classes annotated with `@Component` and specialized annotations built on `@Component` (*stereotype annotations*).

| Annotation | Common meaning | Can default component scan discover it? |
| --- | --- | --- |
| `@Component` | General application component | Yes |
| `@Service` | Business/service layer | Yes |
| `@Repository` | Data access layer as a Spring component | Yes |
| `@Controller` | Spring MVC controller | Yes |
| `@RestController` | REST controller (`@Controller` + `@ResponseBody`) | Yes |
| `@Configuration` | Spring configuration class (specialized `@Component`) | Yes |
| Custom annotation meta-annotated with `@Component` | Project-specific stereotype | Potentially, per Spring recognition rules |

Example of a regular component:

```java
package com.example.shop.util;

import org.springframework.stereotype.Component;

@Component
public class OrderCodeGenerator {
    public String generate(long orderId) {
        return "ORD-" + orderId;
    }
}
```

If the class is in a scanned package and not excluded by conditions or filters, Spring treats it as a bean candidate.

### 4.1. Meta-Annotations Count Too

`@Service` is meta-annotated with `@Component`. Therefore:

```java
@Service
public class PriceService {
}
```

can be recognized even though `@Component` is not written directly on the class. You can also declare custom stereotypes:

```java
package com.example.shop.stereotype;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface UseCase {
}
```

```java
package com.example.shop.application;

import com.example.shop.stereotype.UseCase;

@UseCase
public class CheckoutUseCase {
}
```

`CheckoutUseCase` is a bean candidate if it is within the scan range. The `@UseCase` annotation merely serves as a stereotype in this example; if custom bean naming or specialized logic is needed, that must be configured accordingly.

### 4.2. Not Every Annotation Causes a Class to Be Scanned

Several annotations are easily confused:

- `@Entity` describes a JPA entity; it **does not automatically turn the entity into a Spring component**. Entities are managed separately by the JPA mechanism.
- `@Embeddable` and `@MappedSuperclass` also belong to the JPA model, not component scan stereotypes.
- `@ControllerAdvice` is a specialized stereotype related to `@Component`, so it can be discovered by component scanning within the scan range.
- Interfaces extending `JpaRepository` are typically registered via Spring Data's repository scanning mechanism, which is **different** from regular component scanning.
- Methods annotated with `@Bean` are processed during Spring configuration processing; a method itself is not a class for component scanning to find.

Example:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CurrencyConfiguration {

    @Bean
    public CurrencyFormatter currencyFormatter() {
        return new CurrencyFormatter();
    }
}
```

In this case, component scanning can discover the **class** `CurrencyConfiguration` because `@Configuration` is a stereotype. Then Spring's configuration processing reads `@Bean` and registers the bean produced by the `currencyFormatter()` method. These two steps are related but distinct.

## 5. Changing the Scan Scope with `scanBasePackages`

When a project structure requires placing components outside the root package, `@SpringBootApplication` has a `scanBasePackages` attribute to specify which packages to component scan.

Example:

```text
com.example
├── shop
│   └── ShopApplication.java
├── shared
│   └── SharedFormatter.java
└── billing
    └── BillingService.java
```

The application wants to scan `com.example.shop` and `com.example.shared`, while not yet scanning `com.example.billing`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.shared"
    }
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

In this configuration:

```text
com.example.shop               scanned
com.example.shop.controller    scanned
com.example.shared             scanned
com.example.shared.formatter   scanned
com.example.billing            not included in this scan scope
```

You could also set `scanBasePackages = "com.example"` to cover all subpackages. However, an overly broad scan scope easily pulls unintended components, configurations, or beans into the context. Pick root packages tailored to the application's structure.

### 5.1. `scanBasePackages` and `@ComponentScan(basePackages = ...)`

The following two styles express configuring the component scan scope:

```java
@SpringBootApplication(
    scanBasePackages = {"com.example.shop", "com.example.shared"}
)
public class ShopApplication {
}
```

and a direct Spring configuration example:

```java
@Configuration
@ComponentScan(
    basePackages = {"com.example.shop", "com.example.shared"}
)
public class ComponentScanConfiguration {
}
```

`@SpringBootApplication`'s `scanBasePackages` is an alias for `@ComponentScan`'s `basePackages` attribute. In a typical Spring Boot application, prefer configuring it directly on `@SpringBootApplication` when you only want to change the scan roots; scenarios needing advanced filters can use `@ComponentScan` directly.

**Caution:** when placing `@ComponentScan` directly on the `@SpringBootApplication` class itself, the direct declaration may take precedence over the `@ComponentScan` provided via meta-annotation. Avoid layering multiple component scan configurations without understanding their interaction.

### 5.2. `scanBasePackageClasses` Avoids Hardcoding Package Names

Package names written as strings are prone to breaking when refactoring source code structure. Spring Boot also supports declaring packages via **a class located inside the package to scan**:

```java
package com.example.shared;

public final class SharedPackageMarker {
    private SharedPackageMarker() {
    }
}
```

In the main class:

```java
package com.example.shop;

import com.example.shared.SharedPackageMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        SharedPackageMarker.class
    }
)
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Spring uses **the package of each specified class**, not just scanning that single class alone:

- `ShopApplication.class` identifies the `com.example.shop` package.
- `SharedPackageMarker.class` identifies the `com.example.shared` package.
- Their respective subpackages are also included in the scan scope.

`SharedPackageMarker` does not need to be a Spring bean. It is purely a marker type so the compiler and refactoring tools can check references instead of relying on handwritten package strings.

## 6. The Location of the `@SpringBootApplication` Class Determines the Default Scope

An organization that minimizes extra configuration is placing the main class in the **common root package of the application's components**:

```text
com.example.shop
├── ShopApplication.java
├── api
│   └── ProductController.java
├── application
│   └── ProductService.java
├── domain
│   └── Product.java
└── infrastructure
    └── ProductAdapter.java
```

With this layout, `@SpringBootApplication` does not need `scanBasePackages` to discover application components in subpackages.

If main is placed too deep:

```text
com.example.shop
├── api
│   └── ProductController.java
└── bootstrap
    └── ShopApplication.java  <-- located at com.example.shop.bootstrap
```

then the default scan scope starts at `com.example.shop.bootstrap`; the controller in `com.example.shop.api` lies outside that region. Moving the main class up to `com.example.shop` or explicitly declaring the scan scope are the two ways to address this.

### 6.1. Avoid the Default Package

Java allows classes without a `package` declaration, but that is unsuitable for placing a Spring Boot application:

```java
// No package declaration: avoid this
@SpringBootApplication
public class Application {
}
```

A main class in the **default package** can cause component scanning to sweep a massive portion of the classpath, causing slowdowns or picking up unintended classes. Always use a named package, such as `com.example.shop`.

### 6.2. Multiple Modules Do Not Automatically Mean Multiple Scan Regions

Suppose a project has two modules:

```text
shop-app
  com.example.shop.ShopApplication

shared-library
  com.example.shared.EmailFormatter
```

Even when `shop-app` depends on `shared-library`, the `EmailFormatter` component is still not automatically scanned if its package lies outside the default scope. Having the library on the classpath is only a prerequisite for Spring to see the class; **component scanning still must cover the corresponding package**, or the bean must be registered via another mechanism.

In libraries reused across multiple applications, another design option is providing a configuration class and having applications `@Import` it, or using Spring Boot's auto-configuration mechanism when appropriate. Expanding the scan scope across every package of a library is not always necessary.

## 7. Component Scan Scope Differs from Entity and Repository Scope

This is a frequent source of confusion when starting with Spring Data JPA:

```java
@SpringBootApplication(scanBasePackages = "com.example")
```

The `scanBasePackages` (and `scanBasePackageClasses`) attributes on `@SpringBootApplication` **only adjust component scanning**. They do not automatically change all scopes that other separate mechanisms use to locate JPA entities or Spring Data repositories.

| Target to discover | Corresponding mechanism | Common scope configuration |
| --- | --- | --- |
| `@Service`, `@Controller`, `@Component` | Spring component scanning | `@ComponentScan`, `@SpringBootApplication(scanBasePackages = ...)` |
| JPA `@Entity` | JPA entity scanning/auto-configuration | Defaults to application package; `@EntityScan` can be used |
| `JpaRepository` interfaces | Spring Data repository scanning | Defaults to application configuration; `@EnableJpaRepositories` can be used |

Example layout with a JPA module outside the main package:

```text
com.example.shop
  ShopApplication
  service/ProductService

com.example.persistence
  entity/ProductEntity
  repository/ProductRepository
```

In the configuration, each search scope must be specified explicitly:

```java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.persistence"
    }
)
@EntityScan(basePackages = "com.example.persistence.entity")
@EnableJpaRepositories(basePackages = "com.example.persistence.repository")
public class ShopApplication {
}
```

The snippet illustrates how to configure each scope; a real application also needs a datasource, JPA provider, and corresponding dependencies. In many projects with a clean package layout, default auto-configuration is sufficient and the two extra annotations are unnecessary.

**Do not put `@Component` on an entity just to force it into component scanning.** JPA entities and Spring beans have different roles, lifecycles, and management models.

## 8. Expanding or Narrowing Scope with Filters

Beyond specifying packages, `@ComponentScan` lets you add or exclude candidates using `includeFilters` and `excludeFilters`.

Example excluding a specific component from scanning:

```java
package com.example.shop;

import com.example.shop.integration.LegacyGateway;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyGateway.class
    )
)
public class ShopApplication {
}
```

In this setup, the `LegacyGateway` class is not registered through the configured component scan path. However, if a `@Bean`, `@Import`, auto-configuration, or another mechanism registers the same bean type, **filters do not block those other registration paths**.

Common filter types:

| `FilterType` | Selection basis |
| --- | --- |
| `ANNOTATION` | Based on annotations on the candidate |
| `ASSIGNABLE_TYPE` | Based on class/interface type |
| `REGEX` | Based on a regular expression matching the class name |
| `ASPECTJ` | Based on an AspectJ type pattern expression |
| `CUSTOM` | Custom filtering logic you implement |

### 8.1. `useDefaultFilters = false`

By default, component scanning recognizes Spring stereotypes such as `@Component`. If you configure:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = MyFeature.class
    )
)
```

then you have **disabled the default filters**, and must explicitly specify the candidate types you want recognized in `includeFilters`. This example assumes `MyFeature` is an annotation type defined by the project. Depending on the filter, Spring can select classes without `@Component` based on the matching criteria, provided they are eligible to become bean definitions.

Changing filters on the main configuration class affects many parts of the application. For an initial project, the simplest solution is usually placing main in the right root package and sticking with default component scanning.

### 8.2. Profiles and Conditions Are Not Package Boundaries

Example:

```java
package com.example.shop.service;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;

@Service
@Profile("dev")
public class DevelopmentMailService {
}
```

The `DevelopmentMailService` class is inside the scanned region, yet the bean is only registered when the `dev` profile is active. Similarly, conditions like `@ConditionalOnProperty` can decide whether a bean is registered.

Thus there are two independent questions:

1. **Does Spring scan the package containing this class?**
2. **If the class is found, are the bean registration conditions satisfied?**

If a bean is missing at runtime, the cause could stem from either step.

## 9. Does Component Scanning Load and Instantiate Every Class?

No. Spring can use mechanisms that read metadata from `.class` files to identify candidates without having to load and instantiate every class immediately during scanning. After identification, the framework registers bean definitions, applies conditions, and instantiates beans according to their lifecycles and scopes.

Certain singleton beans are commonly instantiated during context startup; lazy or prototype beans may be created when actually needed. Scanning many packages increases the amount of class metadata that must be inspected, but does not mean every class in the scan range becomes a bean.

Furthermore, many essential beans from Spring Boot, Spring MVC, DataSource, or other modules may appear via auto-configuration or `@Bean` methods in configuration classes. Do not infer that every bean visible in `ApplicationContext` was directly discovered by `@ComponentScan`.

## 10. How to Check Whether Spring Registered a Bean

When dependency injection fails, first check the main class and the component's package location. Next, you can query `ApplicationContext` directly.

Example:

```java
package com.example.shop;

import com.example.shop.service.ProductService;
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    @Bean
    CommandLineRunner inspectBeans(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(ProductService.class);
            System.out.println("ProductService beans: " + Arrays.toString(names));
        };
    }
}
```

With `ProductService` registered under its default name, sample output:

```text
ProductService beans: [productService]
```

The example above illustrates checking when the application starts successfully; in real applications, if the context fails early due to a missing required bean, the `CommandLineRunner` will never get a chance to run. In that case, read the startup error and fix the bean declaration/registration issue first.

Another way to check for a specific bean is:

```java
boolean available = context.getBeansOfType(ProductService.class).size() > 0;
```

However, calling `getBeansOfType` can trigger bean instantiation in some cases. For simple diagnostics, `getBeanNamesForType` is usually preferable for inspecting bean names by type.

### 10.1. Distinguishing "Class Not Found" from "Bean Not Found"

| Symptom | Possible meaning |
| --- | --- |
| Compiler reports `cannot find symbol` or IDE cannot import class | Source code, dependency, or compile classpath issue |
| Runtime throws `ClassNotFoundException`/`NoClassDefFoundError` | Missing or incompatible class on runtime classpath |
| Spring throws `NoSuchBeanDefinitionException` / `No qualifying bean` | The class may exist, but the container has no matching bean |
| Spring throws `NoUniqueBeanDefinitionException` | Multiple matching beans exist; the container does not know which one to pick |
| Component is in the right package yet no bean exists | Could be blocked by annotations, conditions, profiles, filters, class type, or bean registration path |

Do not try to fix a "missing bean" error by adding a Java `import`. An `import` does not expand the component scan scope.

## 11. Common Package Design Mistakes

### 11.1. Main Class Placed Too Deep in a Package

```text
com.example.shop.bootstrap.ShopApplication
com.example.shop.api.ProductController
```

By default, scanning from `com.example.shop.bootstrap` does not find `com.example.shop.api`. You can move the main class up to `com.example.shop` or specify `scanBasePackages`.

### 11.2. Service in a Separate Library Outside the Root Package

```text
com.example.shop.ShopApplication
com.example.common.NotificationService
```

You must intentionally expand the scan scope or provide a bean-registration configuration in the library for the application to import. Simply adding a dependency to the `common` JAR is not enough for the service to be scanned automatically.

### 11.3. Class Missing a Stereotype or Excluded by a Filter

```java
package com.example.shop.service;

public class InvoiceService {
}
```

The class is in the right package, but has no `@Component`, `@Service`, matching meta-annotation, or other registration mechanism, so default component scanning does not register it. You can add `@Service` if you want the container to manage this class, or create the bean via `@Bean` in a configuration.

### 11.4. Misunderstanding Repository and Entity Scope

`@Entity` classes or `JpaRepository` interfaces located in packages outside JPA/Spring Data's own automatic discovery region may still go undetected even after you expand component scanning. Check `@EntityScan`, `@EnableJpaRepositories`, and the application's default package in multi-module structures.

### 11.5. Scanning Too Broadly

When scanning a parent package that contains multiple unrelated applications or libraries, Spring may pick up unwanted configurations or beans, causing bean name collisions, wiring conflicts, or slower startup times. Choose a scan range covering what you need without widening it arbitrarily.

## 12. Practice Exercise: Predicting Scan Scope

Given the structure:

```text
com.acme.store
├── StoreApplication.java        // @SpringBootApplication
├── web/OrderController.java     // @RestController
├── service/OrderService.java    // @Service
└── config/ClockConfig.java      // @Configuration

com.acme.shared
└── AuditService.java            // @Service

com.acme.billing
└── BillingService.java          // @Service
```

**Task 1 — Default.** When using only `@SpringBootApplication` without `scanBasePackages` on `StoreApplication` in `com.acme.store`, identify which classes lie within the scan region.

**Task 2 — Expanding.** To scan `AuditService` as well without scanning `BillingService`, modify the main class annotation using `scanBasePackages` or `scanBasePackageClasses`. Explain why choosing `"com.acme"` would be broader than required.

**Task 3 — Moving main.** If `StoreApplication` is moved into `com.acme.store.bootstrap` without changing any other configuration, what might happen to `OrderController` and `OrderService`?

**Task 4 — Not a component.** Add `@Entity` to an `OrderEntity` class without adding `@Component`. Does this class become a Spring bean just because it lies in the component scan region? Which mechanism manages JPA entities?

**Task 5 — Conditions.** Place `@Profile("dev")` on `OrderService`, then start the application when the `dev` profile is not active. Does the scan scope change, and why might injecting `OrderService` fail due to a missing bean?

Self-check hints:

- Task 1: components under `com.acme.store` are in the default scan region; `com.acme.shared` and `com.acme.billing` are outside.
- Task 2: select `com.acme.store` and `com.acme.shared`, or corresponding marker classes, to avoid scanning `com.acme.billing` as well.
- Task 3: the `bootstrap` package does not cover sibling packages `web` and `service`; default component scanning may miss them.
- Task 4: entities are managed by the JPA provider via entity scanning, and do not automatically become Spring beans solely due to `@Entity`.
- Task 5: the package location remains inside the scan region, yet the profile condition decides whether the bean is registered.

## 13. Key Takeaways When Building Spring Boot Applications

`@ComponentScan` determines **which packages are searched for bean candidates**. When `@SpringBootApplication` is attached to the main class, Spring Boot typically scans **the package containing the main class and all of its subpackages**, rather than scanning every package in the project automatically.

To expand or change the scan scope, you can use `scanBasePackages`, `scanBasePackageClasses`, or an appropriate `@ComponentScan` configuration. Stereotype annotations determine **which classes** are candidates; profiles, conditions, and filters further affect **which beans get registered**. For JPA entities and Spring Data repositories, remember that they have their own discovery mechanisms.

When you encounter a missing bean error, check the package of the `@SpringBootApplication` class, the package of the dependency to be injected, the annotations on that class, and the configuration conditions before changing code. Understanding component scan boundaries properly is the foundation for organizing project structure and using dependency injection intentionally.
