# scanBasePackages and scanBasePackageClasses in @SpringBootApplication

When starting out with Spring Boot, you typically place your startup class, controllers, and services within the same package tree. Simply annotating the main class with **@SpringBootApplication** lets Spring automatically discover and create beans such as **@RestController**, **@Service**, **@Repository**, and **@Configuration**. This makes dependency injection work without manually registering every class.

However, what happens when a service lives in a **sibling package**, or you want to split your application across multiple Java modules? A familiar error is Spring reporting **no bean found** even though the class has **@Service**. That may be a **component scanning scope** issue.

**scanBasePackages** and **scanBasePackageClasses** are two attributes on **@SpringBootApplication** used to specify which packages Spring should scan for components. They serve the same purpose, yet express packages in two ways: **package name strings** and **class references**.

## 1. Starting from the Default Behavior of @SpringBootApplication

Consider the project layout:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── web/
    │   └── ProductController.java
    ├── service/
    │   └── ProductService.java
    └── config/
        └── ShopConfiguration.java
~~~

Startup class:

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

With this setup, the **default component scan** scope is:

~~~text
com.example.shop                 ← package containing ShopApplication
├── ShopApplication
├── web                          ← scanned
│   └── ProductController
├── service                      ← scanned
│   └── ProductService
└── config                       ← scanned
    └── ShopConfiguration
~~~

Spring scans **the package containing the class annotated with @SpringBootApplication and its subpackages**. When it finds classes matching the component scanning criteria, Spring registers bean definitions and creates beans according to the ApplicationContext lifecycle.

Typically, Spring recognizes the following types of components:

| Annotation | Common role |
|---|---|
| **@Component** | General Spring component |
| **@Service** | Business logic component |
| **@Repository** | Data access component |
| **@Controller** / **@RestController** | Web request handling component |
| **@Configuration** | Class declaring configurations, capable of producing beans via **@Bean** |

Specialized annotations like **@Service** or **@RestController** are tied to the component stereotype mechanism. Thus, when people say "scan services," they are really talking about **component scanning**, rather than a separate scanner dedicated only to services.

### What If a Class Sits Outside the Root Package?

Suppose the application grows into:

~~~text
com.example/
├── shop/
│   ├── ShopApplication.java          ← @SpringBootApplication
│   └── web/
│       └── ProductController.java
└── catalog/
    └── service/
        └── CatalogService.java       ← @Service
~~~

**com.example.catalog** is a **sibling** package to **com.example.shop**, not nested beneath it:

~~~text
Default scan:   com.example.shop.**
Included:       com.example.shop.web.ProductController
Not included:   com.example.catalog.service.CatalogService
~~~

If **ProductController** requires **CatalogService** to be injected and Spring has not registered a corresponding bean in another way, the application may fail to start with an error such as **No qualifying bean of type ... available**.

This is when you need to understand how to expand the scan scope.

## 2. How Does @SpringBootApplication Relate to @ComponentScan?

**@SpringBootApplication** is a composite annotation combining several key startup behaviors, commonly explained as uniting:

- **@SpringBootConfiguration**: marks the class as the application's primary configuration.
- **@EnableAutoConfiguration**: lets Spring Boot auto-configure based on conditions like dependencies, existing beans, and configuration properties.
- **@ComponentScan**: searches for Spring components in specified packages.

The two attributes in this lesson are **aliases** for the corresponding attributes on **@ComponentScan**:

| Attribute on @SpringBootApplication | Corresponding attribute on @ComponentScan | Value |
|---|---|---|
| **scanBasePackages** | **basePackages** | **String[]**: one or more package names |
| **scanBasePackageClasses** | **basePackageClasses** | **Class<?>[]**: one or more classes used as package anchors |

They change the **component scan scope of the @ComponentScan part** inside `@SpringBootApplication`. They are **not options that alter the entire auto-configuration mechanism**, nor do they automatically adjust other scanning types such as JPA entity scanning or repository scanning.

This distinction is critical:

~~~text
@SpringBootApplication
   ├── Spring application configuration
   ├── Auto-configuration
   └── Component scanning
          ├── scanBasePackages
          └── scanBasePackageClasses
~~~

Therefore, when encountering a missing bean error, determine whether that bean is created by **component scanning**, **@Bean**, **auto-configuration**, or another registration mechanism. Not every bean error is solved by widening package scanning.

## 3. scanBasePackages: Declaring Packages via Strings

**scanBasePackages** accepts a list of Java package names as **String[]**.

For example, to scan both the shop application and the catalog module:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

At startup, Spring searches for components in **both listed packages and their subpackages**.

~~~text
com.example/
├── shop/                           ← scanned
│   ├── ShopApplication.java
│   ├── web/ProductController.java  ← discovered if it is a component
│   └── service/CheckoutService.java
└── catalog/                        ← scanned
    ├── service/CatalogService.java ← discovered if it is a component
    └── config/CatalogConfiguration.java
~~~

With a single package, you can write it concisely:

~~~java
@SpringBootApplication(scanBasePackages = "com.example")
public class ShopApplication {
    // ...
}
~~~

**Caution:** the declaration above expands the scope to all subpackages under **com.example**, including parts outside shop and catalog if they are also present on the classpath. That might be intentional, yet overly broad scanning can easily register unwanted beans.

### Rules to Understand

**1. The declared list specifies root packages to scan.**

Each root package includes itself and its subpackages. If you want to scan **com.example.catalog**, you do not need to also list **com.example.catalog.service**.

**2. The attribute specifies exact packages to scan; it does not implicitly retain the old default.**

Once **scanBasePackages** is specified, you must explicitly include **com.example.shop** if you still want controllers, services, or configurations there to be scanned. For example:

~~~java
@SpringBootApplication(
    scanBasePackages = "com.example.catalog"
)
public class ShopApplication {
}
~~~

In the example above, **com.example.shop.web** is no longer among the specified root packages. The **ShopApplication** class itself remains the primary configuration class used by SpringApplication; that does not mean beans underneath its package are still scanned automatically.

**3. Package names are string literals.**

If **com.example.catalog** is later renamed to **com.example.inventory**, the old string value does not update automatically via a Java refactor alone. Remember to update the annotation.

**4. Classes must be on the runtime classpath.**

Typing a valid package name does not make Spring scan a module or JAR that has not been declared as an application dependency. Classes must be compiled and present on the classpath when the application runs.

**5. Scanning does not turn every Java class into a bean.**

A regular class with no stereotype annotation, not created via **@Bean** or another registration mechanism, will not become a bean merely because its package is scanned.

### When Is scanBasePackages Convenient?

- When you need to list a few packages explicitly by name.
- When working with an existing codebase and wanting to adjust scan scope quickly.
- When a package resides in part of the app that does not yet have a stable marker class to reference.

The trade-off is that package names written as strings **are not checked by the Java compiler like class references**, so typos or package renames might only surface at runtime.

## 4. scanBasePackageClasses: Declaring Packages via Classes

**scanBasePackageClasses** takes one or more **Class<?>** values. For each class passed in, Spring uses **the package containing that class** as a root package to scan.

Suppose you have:

~~~text
com.example/
├── shop/
│   ├── ShopApplication.java
│   └── web/ProductController.java
└── catalog/
    ├── CatalogModuleMarker.java
    └── service/CatalogService.java
~~~

Create a marker class in package **com.example.catalog**:

~~~java
package com.example.catalog;

public final class CatalogModuleMarker {

    private CatalogModuleMarker() {
        // Use this class solely as an anchor identifying the package.
    }
}
~~~

Then configure the startup class:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModuleMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModuleMarker.class
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Spring will use:

~~~text
ShopApplication.class
    └── package: com.example.shop
        └── scans com.example.shop and subpackages

CatalogModuleMarker.class
    └── package: com.example.catalog
        └── scans com.example.catalog and subpackages
~~~

**CatalogModuleMarker does not need @Component, @Configuration, or @Service.** It is merely a **package anchor**. Appearing in **scanBasePackageClasses** does not mean Spring creates a bean for the marker.

Instead of a marker class, you could also reference an existing class:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogService.class
    }
)
public class ShopApplication {
}
~~~

However, if **CatalogService** sits in **com.example.catalog.service**, Spring takes **com.example.catalog.service** as the root package; components in **com.example.catalog.config** or **com.example.catalog.repository** do not sit under that package. Thus, a **marker placed in the root package** usually expresses intent more clearly.

### Marker Interfaces Work Too

You can use an empty interface:

~~~java
package com.example.catalog;

public interface CatalogModule {
    // Marker representing the catalog package root.
}
~~~

And reference it:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
public class ShopApplication {
}
~~~

Spring only needs a **Class** object to resolve the package, so either a marker class or marker interface works. In many codebases, a clearly named marker placed in a stable package keeps configuration less coupled to a specific service name.

### Why Is This Approach More Type-Safe?

When writing **CatalogModule.class**, the Java compiler and IDE recognize it as an existing type. If the class is deleted or renamed without updating the configuration, the broken reference is typically caught at compile time. IDEs can also assist with renaming classes and updating imports.

However, **type-safe does not automatically guarantee the scan scope stays right forever**. If the marker is moved into a different package, the scan scope shifts accordingly. Keep the marker at the module's actual root package level.

## 5. Comparing the Two Attributes

| Criterion | scanBasePackages | scanBasePackageClasses |
|---|---|---|
| Value passed | Package name strings | Class literals, e.g., **CatalogModule.class** |
| How root is determined | Uses the declared package names | Extracts the package containing each class |
| Catches errors on class rename | Not applicable to strings | Class references can be checked by compiler/IDE |
| On package rename | String must be manually updated to match | Can preserve scope if the marker stays in the right package |
| Risk of picking too narrow a package | Yes, if string names a subpackage | Yes, if referencing a class inside a subpackage |
| Readability in code | Package names are visible directly | Shows classes representing packages |
| Best suited for | Small projects or package-name configuration | Multi-module projects wanting to anchor scan scope via Java types |

**Both are ways to specify base packages for component scanning.** Neither attribute causes Spring to scan entities, repositories, DTOs, or every other class under a single catch-all mechanism.

In multi-module codebases, **scanBasePackageClasses** with stable markers often reduces typos in package names. In a simple project with one root package, it is best to keep the default behavior of **@SpringBootApplication** if it already meets your needs.

## 6. Complete Example: Controller and Service in Two Package Trees

Let's build a small Spring Boot REST application with two parts:

- **shop** handles HTTP requests.
- **catalog** provides business logic returning product information.

If generating the project via Spring Initializr, select the **Spring Web** dependency, Java language, a suitable stable Spring Boot version, and matching JDK. The example below assumes **Java 21** and JAR packaging. In a real application, catalog might live in a separate module or JAR; in that case **shop must declare a build dependency on the catalog module/JAR**.

### 6.1. Package Tree

~~~text
src/main/java/
└── com/example/
    ├── shop/
    │   ├── ShopApplication.java
    │   └── web/
    │       └── ProductController.java
    └── catalog/
        ├── CatalogModule.java
        └── service/
            └── CatalogService.java
~~~

### 6.2. Business Service

File **com/example/catalog/service/CatalogService.java**:

~~~java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public String findProductName(long id) {
        if (id == 1L) {
            return "Spring Boot Handbook";
        }
        return "Unknown product";
    }
}
~~~

### 6.3. Marker at the Catalog Package Root

File **com/example/catalog/CatalogModule.java**:

~~~java
package com.example.catalog;

public interface CatalogModule {
}
~~~

The marker is only used to pinpoint the package root; it holds no business logic and does not need to be a Spring bean.

### 6.4. Web Controller

File **com/example/shop/web/ProductController.java**:

~~~java
package com.example.shop.web;

import java.util.Map;

import com.example.catalog.service.CatalogService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final CatalogService catalogService;

    public ProductController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/products/{id}")
    public Map<String, Object> getProduct(@PathVariable long id) {
        return Map.of(
                "id", id,
                "name", catalogService.findProductName(id));
    }
}
~~~

The controller uses **constructor injection**. It receives **CatalogService** as a dependency and simply translates HTTP requests into Java method calls.

### 6.5. Startup Class Using scanBasePackageClasses

File **com/example/shop/ShopApplication.java**:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModule;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

When Spring Boot starts:

1. **ShopApplication** is used as the primary configuration.
2. Component scanning searches for components in **com.example.shop** and **com.example.catalog**, including their subpackages.
3. Spring discovers **ProductController** and **CatalogService**.
4. Spring creates the **CatalogService** bean and injects it into **ProductController**'s constructor.
5. Spring Web registers the **GET /products/{id}** mapping to accept HTTP requests.

Run the application using the project's chosen build tool. With Gradle you can use **bootRun**; with Maven you can use **spring-boot:run**. While the server is running on default port 8080, try:

~~~bash
curl http://localhost:8080/products/1
~~~

Sample response:

~~~json
{
  "id": 1,
  "name": "Spring Boot Handbook"
}
~~~

In this example, if you left **@SpringBootApplication** at its default on **com.example.shop.ShopApplication**, the controller would be scanned, yet **CatalogService** in the sibling package **com.example.catalog** would not be discovered by component scanning. Because the controller depends on that service, bean creation would fail.

### 6.6. Equivalent Configuration Using scanBasePackages

You can replace the annotation above with:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
    // main(...) remains the same as the example above.
}
~~~

The component scan outcome in terms of root packages is equivalent. Choose **one of the two approaches** for a sample application to avoid redundant configuration and keep the scan scope clear to readers.

## 7. Does Being in a Scanned Package Guarantee a Class Becomes a Bean?

**No.** Package scanning defines where Spring **searches for component candidates**. Spring still needs to recognize or register the bean via a suitable mechanism.

Example:

~~~java
package com.example.catalog.service;

public class PriceCalculator {

    public long calculate(long basePrice) {
        return basePrice;
    }
}
~~~

This class has no **@Component**, **@Service**, or other stereotype annotation. Simply adding package **com.example.catalog** to `scanBasePackages` **does not automatically register PriceCalculator** as a bean.

You can fix this by adding a stereotype:

~~~java
@Service
public class PriceCalculator {
    // ...
}
~~~

Or registering it through a configuration class:

~~~java
package com.example.catalog.config;

import com.example.catalog.service.PriceCalculator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogConfiguration {

    @Bean
    PriceCalculator priceCalculator() {
        return new PriceCalculator();
    }
}
~~~

In the latter case, **CatalogConfiguration** must be processed by Spring via component scanning or an appropriate configuration import mechanism like **@Import**. Only then does the **@Bean** method register the **PriceCalculator** bean. Configuration via **@Bean** is especially helpful when instantiating objects from a third-party library whose source code you cannot edit to add annotations.

Similarly, if multiple beans implement the same interface, widening package scanning might cause Spring to find **too many** candidates. In that situation, use **@Qualifier**, **@Primary**, or explicit configuration to disambiguate the intended bean.

## 8. Distinguishing Component Scan from Entity Scan and Repository Scan

This is an easy area to misunderstand when adding a database access module.

Suppose the layout is:

~~~text
com.example/
├── shop/
│   └── ShopApplication.java
└── catalog/
    ├── service/CatalogService.java           ← @Service
    ├── persistence/ProductEntity.java        ← @Entity
    └── repository/ProductRepository.java     ← JpaRepository
~~~

You add:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
}
~~~

This lets component scanning find **CatalogService**. Yet you should not infer that it also fully configures finding **ProductEntity** and **ProductRepository**.

Spring Boot and Spring Data have additional discovery mechanisms:

| Target to discover | Mechanism typically applied | Explicit configuration when outside default root |
|---|---|---|
| **@Service**, **@Component**, **@RestController**, **@Configuration** | Component scanning | **scanBasePackages** / **scanBasePackageClasses** |
| JPA **@Entity** | Persistence provider / Spring Boot entity scanning | **@EntityScan** |
| **JpaRepository** interfaces | Spring Data JPA repository scanning | **@EnableJpaRepositories** |
| **@ConfigurationProperties** classes without stereotype | Configuration properties registration mechanism | **@EnableConfigurationProperties** / **@ConfigurationPropertiesScan** |

Illustrative configuration when entities and JPA repositories reside in the catalog package:

~~~java
package com.example.shop;

import com.example.catalog.CatalogModule;
import com.example.catalog.persistence.ProductEntity;
import com.example.catalog.repository.ProductRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class
    }
)
@EntityScan(basePackageClasses = ProductEntity.class)
@EnableJpaRepositories(basePackageClasses = ProductRepository.class)
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

In this example:

- **scanBasePackageClasses** lets Spring find components.
- **@EntityScan** tells Boot where to find entities.
- **@EnableJpaRepositories** tells Spring Data JPA where to find repository interfaces.

**ProductEntity** and **ProductRepository** are hypothetical classes/interfaces belonging to a JPA example; in a real application, define them alongside Spring Data JPA dependencies and a suitable datasource.

**You do not always need all three annotations.** If entities and repositories already live within the default scope used by Spring Boot/Spring Data, auto-configuration can find them without manual declarations. Dedicated annotations are useful when package layouts extend beyond the default scope. In particular, changing **scanBasePackages** does not automatically change the root package used by other auto-configuration mechanisms.

### Why Are There Multiple Kinds of Scans?

Because these elements carry different meanings:

- **@Component** and related stereotypes represent beans managed by Spring.
- **@Entity** is metadata describing a persistence data type, not a request to instantiate a regular singleton bean via component scanning.
- **JpaRepository** is a repository contract for which Spring Data generates a proxy through the repository registration mechanism.
- **@ConfigurationProperties** describes configuration data types, which need to be registered via an appropriate mechanism to bind values from the environment.

Understanding this boundary avoids a common mistaken fix: seeing an entity or repository error and adding a package string to **scanBasePackages** expecting everything to work.

## 9. Can scanBasePackages Replace @ComponentScan?

For the goal of **declaring root packages to search for components**, the two attributes on **@SpringBootApplication** are usually a concise, clear choice for Boot applications.

For example:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class ShopApplication {
}
~~~

corresponds in package-specifying intent to:

~~~java
@ComponentScan(
    basePackages = {
        "com.example.shop",
        "com.example.catalog"
    }
)
public class SomeConfiguration {
}
~~~

However, **@ComponentScan** is a richer annotation with options such as **includeFilters**, **excludeFilters**, **lazyInit**, and other fine-grained settings. **scanBasePackages** and **scanBasePackageClasses** do not mirror all of those options.

An application needing specialized component scan settings might need **@ComponentScan** or configuration classes imported via **@Import**. Still, avoid carelessly stacking an extra **@ComponentScan** directly on the main class merely to repeat attributes already declared, because local scan annotations and meta-annotations follow precedence rules you must understand; the configuration might stop behaving as readers expect.

For beginners, the simplest and most maintainable organization is usually:

1. Place the **@SpringBootApplication** class in a shared root package whenever possible.
2. Specify **scanBasePackages** or **scanBasePackageClasses** only when multiple root packages are truly needed.
3. Use specialized scan annotations when dealing with entities, repositories, or other specialized types.
4. Use **@Import** / **@Bean** for targeted configuration instead of scanning a massive package tree just to pick up one bean.

## 10. When Multiple Modules Participate in an Application

A Spring Boot project can be split into multiple build modules:

~~~text
project-root/
├── shop-app/
│   └── src/main/java/com/example/shop/ShopApplication.java
├── catalog-core/
│   └── src/main/java/com/example/catalog/
│       ├── CatalogModule.java
│       └── service/CatalogService.java
└── notification-adapter/
    └── src/main/java/com/example/notification/
        ├── NotificationModule.java
        └── EmailNotificationAdapter.java
~~~

When **shop-app** is the runnable application, it needs:

- **Build dependencies** on the modules it uses.
- Those classes present on the **runtime classpath**.
- Required beans registered via component scanning, configuration, or another mechanism.

The startup class can choose:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        ShopApplication.class,
        CatalogModule.class,
        NotificationModule.class
    }
)
public class ShopApplication {
}
~~~

Key distinction: **Gradle/Maven configuration** determines which modules/JARs are present at build time and runtime; **component scanning** only determines which components Spring looks for among the classes already on the classpath.

~~~text
Build dependencies ──► Classes available on classpath
                                    │
                                    ▼
                         Component scanning
                                    │
                                    ▼
                            Spring bean definitions
                                    │
                                    ▼
                        Dependency injection at runtime
~~~

If **shop-app** has not declared a dependency on **catalog-core**, listing the catalog package name in **scanBasePackages** will not make Spring "load that module" into the application.

On the other hand, not every library needs component scanning. Many Spring Boot starters and libraries supply beans through **auto-configuration**, **@Import**, or another registration mechanism. Do not add every package of a third-party library to your scan list if the library already provides an official integration path.

## 11. Common Mistakes and How to Understand Their Causes

### Mistake 1: Service in a Sibling Package

~~~text
com.example.shop.ShopApplication
com.example.catalog.CatalogService
~~~

**Symptom:** the controller injects CatalogService, yet no bean exists.

**Possible cause:** default scanning only scans **com.example.shop**. Fix by placing the startup class in an appropriate root package, adding **com.example.catalog**, or importing the configuration / registering the bean explicitly.

### Mistake 2: Scanning Only External Packages, Forgetting the App's Own Package

~~~java
@SpringBootApplication(
    scanBasePackages = "com.example.catalog"
)
public class ShopApplication {
}
~~~

**Symptom:** CatalogService exists, yet controllers in **com.example.shop.web** are not discovered by component scanning.

**Fix:** include **com.example.shop** as well if components there are still needed, or reference **ShopApplication.class** too when using **scanBasePackageClasses**.

### Mistake 3: Marker Placed Too Deep

~~~text
com.example.catalog.service.CatalogService
com.example.catalog.config.CatalogConfiguration
~~~

If you use **CatalogService.class** as a base-package class, Spring only picks up package **com.example.catalog.service**. Configuration in **com.example.catalog.config** falls outside the scope.

**Fix:** place a marker in **com.example.catalog**, or explicitly add multiple root classes/packages.

### Mistake 4: Class Not Registered as a Bean

The class exists in the right package, yet lacks **@Component**/**@Service**/**@Repository** (or was not created via **@Bean**). Component scanning does not register arbitrary Java classes automatically.

**Fix:** check the bean creation mechanism for that class type before widening the scan scope.

### Mistake 5: Class Sits in a Module Missing a Dependency

The application references another module's package, yet the classes are absent from the build/runtime classpath.

**Fix:** declare the corresponding Maven/Gradle dependency, ensuring the classes are packaged and present at runtime.

### Mistake 6: Bean Excluded by a Configuration Condition or Profile

A bean may lie in a scanned package yet still not be created because of **@Profile**, **@Conditional**, or configuration conditions.

**Fix:** inspect bean creation conditions, active profiles, and required dependencies. Changing `scanBasePackages` does not bypass those conditions.

### Mistake 7: Multiple Beans of the Same Type

Scanning additional packages causes Spring to find two implementations of the same interface, such as two **PaymentGateway** beans. If injection requests only the interface type, Spring may fail to choose a single candidate.

**Fix:** disambiguate using **@Qualifier**, **@Primary**, or redesign configurations so only the intended implementation is registered.

### Mistake 8: Entity or JPA Repository Not Found

**@Entity** or **JpaRepository** interfaces lie outside the default range of JPA/Spring Data mechanisms. Component scanning does not guarantee handling those two types.

**Fix:** check JPA dependencies, datasource, **@EntityScan**, **@EnableJpaRepositories**, and the packages Spring Boot/Spring Data use for auto-configuration.

### Mistake 9: Scanning Too Broadly

~~~java
@SpringBootApplication(scanBasePackages = "com")
public class ShopApplication {
}
~~~

Overly broad configuration can pull unrelated classes into component discovery, creating unwanted beans, bean name collisions, or inappropriate configurations.

**Fix:** limit root packages to the boundaries of the application or modules actually needed. Broad scanning is not a safe way to solve dependency injection errors.

## 12. How to Investigate When Spring Cannot Find a Bean

Suppose the startup log shows a message like:

~~~text
Parameter 0 of constructor in
com.example.shop.web.ProductController
required a bean of type
com.example.catalog.service.CatalogService
that could not be found.
~~~

You can trace it in order:

1. **Identify the missing bean.** Here it is CatalogService, not ProductController.
2. **Check whether the class is registered as a bean.** Does it have **@Service**, **@Component**, **@Bean**, or an equivalent registration mechanism?
3. **Check the class's package.** Is it inside the component-scanned packages?
4. **Check the startup class and base packages.** Is it using defaults, or were **scanBasePackages** or **scanBasePackageClasses** declared?
5. **Check the classpath.** If the service lives in another module/JAR, does the application depend on that module?
6. **Check bean creation conditions.** Did a profile or conditional annotation skip the bean?
7. **Check for multiple implementations.** Is the real error "no bean" or "multiple beans of the same type"?

You can enable detailed logging as needed to inspect the startup process. For applications with Actuator configured appropriately, information about existing beans or auto-configuration conditions can also aid investigation; protect those management endpoints properly.

**Do not immediately change `scanBasePackages` to a huge parent package whenever you see an injection error.** Doing so can mask missing dependencies, missing stereotypes, or failing bean conditions while pulling unwanted components into the application.

## 13. Practice: Comparing the Two Attributes

Starting from the shop and catalog example, you can observe the differences with four independent changes:

**Experiment A — Default only.** Keep **@SpringBootApplication** on **ShopApplication** in **com.example.shop** with no scan attributes. When the controller requests CatalogService in the sibling package, observe the missing bean error at startup.

**Experiment B — Using scanBasePackages.** Add the two strings **com.example.shop** and **com.example.catalog**. Restart and call **GET /products/1** to verify the bean is now recognized.

**Experiment C — Using scanBasePackageClasses.** Replace the string configuration with **ShopApplication.class** and **CatalogModule.class**. Keep the package structure and endpoint unchanged; observe the same behavior.

**Experiment D — Moving the marker.** Move the marker from **com.example.catalog** into **com.example.catalog.service**, update imports, and run again. Observe the effect of narrowing the root package, especially if another component sits in **com.example.catalog.config**.

Distinguish **scan results** from **business results**. If the endpoint does not exist, the bug may be that the controller was not registered. If the controller was registered yet the application context fails to build due to a missing service, the bug may be a service outside the scan scope. If JPA repositories or entities are missing, inspect the specialized scan mechanisms.

## 14. Rules of Choice in Real Projects

When starting a new Spring Boot application, place the **@SpringBootApplication** class in a root package encompassing the application's subpackages. This is the most concise and readable usage:

~~~text
com.example.myapp/
├── MyAppApplication.java
├── api/
├── application/
├── domain/
├── persistence/
└── config/
~~~

When dealing with multiple independent root packages or multiple modules:

- Use **scanBasePackages** if you prefer configuring directly by package name and that list rarely changes.
- Use **scanBasePackageClasses** if you want to reference stable classes/markers so the compiler and IDE assist when renaming classes or restructuring source code.
- Place markers at the **actual root package you want scanned**, not deep inside a service subpackage while expecting the entire module to be scanned.
- Include the main application's package if you specify a list of base packages and still need its components scanned.
- Configure separate mechanisms for **entities**, **repositories**, **configuration properties**, and other items registered through distinct mechanisms.
- Avoid unnecessary scan expansion; choose clear dependencies and registration mechanisms along module boundaries.

## Conclusion

**scanBasePackages** and **scanBasePackageClasses** are two ways to declare **component scanning** scope on **@SpringBootApplication**:

- **scanBasePackages** uses package names as strings.
- **scanBasePackageClasses** uses the packages containing referenced classes, typically marker classes or marker interfaces.

Both help Spring find controllers, services, repository stereotypes, configurations, and other components within the chosen package trees. When using them, remember that **component scanning does not automatically manage every registration type in Spring Boot**: JPA entities, Spring Data repositories, and configuration properties have their own corresponding mechanisms.

Understanding the default package scope, how to specify multiple packages, and the differences between **classpath**, **component scanning**, and **auto-configuration** will help you organize multi-package or multi-module applications while keeping dependency injection predictable and maintainable.
