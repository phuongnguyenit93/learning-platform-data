# `@ComponentScan` Scope and Package Placement in Spring Core Container

## 1. Why Does a Class Annotated with `@Component` Still Not Produce a Bean?

Suppose an application has the following service:

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

A class annotated with `@Service` (which is a specialization of `@Component`) has **enough metadata to be discovered**, yet that does not guarantee an `OrderService` bean exists in the Spring IoC Container. For Spring to register the class as a bean via component scanning, the class's package must lie within the **scan scope** of an enabled configuration, the class must be a valid candidate, and it must not be excluded by filters or conditions.

For example, if the application only scans `com.example.billing`, Spring will not automatically traverse over to `com.example.shop.service`. The error usually surfaces when a constructor requires `OrderService` and no matching bean exists:

```text
No qualifying bean of type 'com.example.shop.service.OrderService' available
```

This is an example of the **error message content** you may encounter; the full stack trace varies depending on the injection point and Spring version.

The goals of this lesson are to accurately grasp:

1. how `@ComponentScan` selects root packages and subpackages;
2. the difference between the default package, `basePackages`, and `basePackageClasses`;
3. how the placement of a configuration class or `@SpringBootApplication` affects component discovery;
4. how to scan across multiple packages/modules in a controlled manner without widening scope arbitrarily;
5. how to diagnose missing beans and avoid mistakes involving packages, classpath, filters, and conditions.

## 2. What Does `@ComponentScan` Actually Scan?

`@ComponentScan` belongs to package `org.springframework.context.annotation`. When a configuration class is processed, this annotation instructs Spring to search for **component candidates** in one or more base packages. The scanner primarily reads metadata from `.class` files available on the classpath (or module path under appropriate conditions) and registers **bean definitions** for valid candidates.

By default, candidates are classes annotated with `@Component` or a stereotype meta-annotated with `@Component`, such as:

- `@Service` for the business layer;
- `@Repository` for the data access layer;
- `@Controller` for the web/controller layer;
- `@Configuration` for configuration classes;
- custom stereotypes meta-annotated with `@Component`.

Component scan does **not** automatically take every Java class in a package and turn all of them into beans. A normal class without a matching stereotype still does not become a bean merely because the classpath contains it. Furthermore, the candidate class must be instantiable by Spring and not excluded by filters or configuration conditions.

Overview of the process:

```text
Configuration is registered into ApplicationContext
                     |
                     v
        Read @ComponentScan metadata
                     |
                     v
   Select one or more specific base packages
                     |
                     v
   Traverse classes in packages and subpackages
                     |
                     v
  Evaluate stereotypes + include/exclude filters
                     |
                     v
     Register valid bean definitions
                     |
                     v
Spring creates beans, resolves dependencies, and manages lifecycle
```

**Two distinct phases:** the scanner registers *bean definitions*; *instance* creation depends on scope, lazy initialization, dependencies, and the context refresh progress. `@ComponentScan` does not define business method execution order and does not automatically start an HTTP server.

## 3. The Configuration Class's Package Is the Default Anchor

The following configuration **does not specify** `basePackages`:

```java
package com.example.shop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class ShopConfig {
}
```

With this configuration, Spring defaults to scanning from the **package of the class declaring `@ComponentScan`**, namely `com.example.shop`, and proceeds into **subpackages** such as `com.example.shop.service` and `com.example.shop.persistence`.

Example Java layout:

```text
com.example/
├── shop/
│   ├── ShopConfig.java                  <-- has @ComponentScan
│   ├── service/
│   │   └── OrderService.java            <-- scanned
│   └── persistence/
│       └── OrderRepository.java         <-- scanned
├── shared/
│   └── TextConverter.java               <-- NOT scanned
└── billing/
    └── InvoiceService.java              <-- NOT scanned
```

Packages `com.example.shared` and `com.example.billing` are **sibling packages** to `com.example.shop`. The scanner does not climb up to the parent package `com.example` to cross into sibling branches.

| Class/package | Relative to base package `com.example.shop` | Inspected by this scan pass? |
| --- | --- | --- |
| `com.example.shop.ShopConfig` | Same package | Yes |
| `com.example.shop.service.OrderService` | Subpackage | Yes |
| `com.example.shop.persistence.OrderRepository` | Subpackage | Yes |
| `com.example.shared.TextConverter` | Sibling branch | No |
| `com.example.billing.InvoiceService` | Sibling branch | No |
| `com.example.BaseHelper` | Parent package | No |

"Inspected by this scan pass" does not automatically mean "guaranteed to have a bean": the class must still satisfy stereotypes, filters, conditions, and registration rules. Moreover, a bean outside the scan region **can still be registered by another means**, such as `@Bean` or `@Import`.

### Java Packages Differ from Arbitrary File Paths on Disk

For source file `src/main/java/com/example/shop/service/OrderService.java`, the important part at the top of the file is:

```java
package com.example.shop.service;
```

The compiler produces the fully qualified name `com.example.shop.service.OrderService`. The component scanner relies on class and package metadata on the **runtime classpath/module path**, rather than searching every directory containing `.java` files in the workspace. Directory organization matching packages is very helpful, yet `src/main/java` is the build tool's source root, not the default base package of `@ComponentScan`.

**Placing a configuration class in the default package** (a Java file without a `package` declaration) is a structure to avoid. When there is no specific base package, scanning from the root can cause Spring to search too broadly across the classpath, causing poor performance and unintended configuration. Always use an explicitly named package.

## 4. Specifying Scope Explicitly with `basePackages`

A configuration class in `com.example.app` can still instruct Spring to scan other packages:

```java
@Configuration
@ComponentScan(basePackages = {"com.example.shop", "com.example.shared"})
class AppConfig { }
```

This is an illustrative configuration snippet assuming appropriate imports. The scanner inspects both packages and all subpackages. The `basePackages` values are **Java package names**, not `src/main/java` paths or fully qualified class names. The syntax `@ComponentScan("com.example.shop")` uses the `value` attribute, which is an alias for `basePackages`; avoid configuring both aliases with conflicting values. String-based package names can easily be missed during refactoring.

## 5. Specifying Scope Explicitly with `basePackageClasses`

`basePackageClasses` selects the **package containing a marker class or interface** and its subpackages:

```java
@Configuration
@ComponentScan(basePackageClasses = {ShopPackage.class, SharedPackage.class})
class AppConfig { }
```

Assume `ShopPackage` is in `com.example.shop` and `SharedPackage` is in `com.example.shared`. Markers do not need `@Component`, because they only identify the scan root. Place markers at the **feature root**; mistakenly using `OrderService.class` in `com.example.shop.service` would skip sibling `com.example.shop.persistence`. Declaring both `basePackages` and `basePackageClasses` simultaneously selects the **union of the listed regions**. Full examples and refactoring trade-offs are covered in the dedicated follow-up lesson.

## 6. Complete Java 17+ Example: One Scanned Package, One Missed Package

The application runs with **Spring Framework 6.2.x** via `spring-context`, without Spring Boot. Two `ApplicationContext` instances are created sequentially:

- `ShopOnlyConfig` scans only `demo.shop`. `OrderService` and `OrderRepository` beans are discovered, whereas `SharedEncoder` in `demo.shared` does not appear.
- `ExpandedConfig` uses `basePackageClasses` with two markers in `demo.shop` and `demo.shared`. All three beans are discovered.

The Java code in this example is a real program split into the corresponding files and packages; standalone snippets in other sections are illustrative only.

### 6.1. Directory Structure

```text
component-scan-packages/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── demo/
        ├── app/
        │   └── ScanPackagesDemo.java
        ├── shop/
        │   ├── ShopPackage.java
        │   ├── service/
        │   │   └── OrderService.java
        │   └── persistence/
        │       └── OrderRepository.java
        └── shared/
            ├── SharedPackage.java
            └── text/
                └── SharedEncoder.java
```

`settings.gradle`:

```groovy
rootProject.name = 'component-scan-packages'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.ScanPackagesDemo'
}
```

The project requires JDK 17+ and a Gradle version compatible with the JDK in use.

### 6.2. Application Class and Two Scan Configurations

File `src/main/java/demo/app/ScanPackagesDemo.java`:

```java
package demo.app;

import demo.shop.ShopPackage;
import demo.shop.service.OrderService;
import demo.shared.SharedPackage;
import demo.shared.text.SharedEncoder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

public class ScanPackagesDemo {

    public static void main(String[] args) {
        try (var shop =
                new AnnotationConfigApplicationContext(ShopOnlyConfig.class)) {
            System.out.println("shop.orderService = " +
                    shop.containsBean("orderService"));
            System.out.println("shop.sharedEncoder = " +
                    shop.containsBean("sharedEncoder"));
            System.out.println("shop.message = " +
                    shop.getBean(OrderService.class).message());
        }

        try (var expanded =
                new AnnotationConfigApplicationContext(ExpandedConfig.class)) {
            System.out.println("expanded.orderService = " +
                    expanded.containsBean("orderService"));
            System.out.println("expanded.sharedEncoder = " +
                    expanded.containsBean("sharedEncoder"));

            String message =
                    expanded.getBean(OrderService.class).message();
            String decorated =
                    expanded.getBean(SharedEncoder.class).encode(message);
            System.out.println("expanded.message = " + decorated);
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "demo.shop")
class ShopOnlyConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = {
        ShopPackage.class,
        SharedPackage.class
})
class ExpandedConfig {
}
```

Only `ScanPackagesDemo` is top-level `public` in the file; `ShopOnlyConfig` and `ExpandedConfig` are valid package-private classes in the same `demo.app` package. Registering the configuration classes directly with `AnnotationConfigApplicationContext` causes Spring to process their `@ComponentScan`, even though `demo.app` itself is not part of either scan region.

### 6.3. Markers at the Package Roots

File `src/main/java/demo/shop/ShopPackage.java`:

```java
package demo.shop;

public final class ShopPackage {
    private ShopPackage() {
    }
}
```

File `src/main/java/demo/shared/SharedPackage.java`:

```java
package demo.shared;

public final class SharedPackage {
    private SharedPackage() {
    }
}
```

These two classes **do not have `@Component`**. They only mark the package roots for `basePackageClasses`; Spring does not create `ShopPackage` or `SharedPackage` beans from default scanning.

### 6.4. Classes in `demo.shop`

File `src/main/java/demo/shop/persistence/OrderRepository.java`:

```java
package demo.shop.persistence;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {
    public String load() {
        return "ok";
    }
}
```

File `src/main/java/demo/shop/service/OrderService.java`:

```java
package demo.shop.service;

import demo.shop.persistence.OrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String message() {
        return "order:" + repository.load();
    }
}
```

These two components reside in **two sibling subpackages** (`demo.shop.service` and `demo.shop.persistence`). Scanning from root `demo.shop` picks up both. `OrderService`'s single constructor does not need `@Autowired`; Spring selects `OrderRepository` by type for injection.

### 6.5. Component in the `demo.shared` Branch

File `src/main/java/demo/shared/text/SharedEncoder.java`:

```java
package demo.shared.text;

import org.springframework.stereotype.Component;

@Component
public class SharedEncoder {
    public String encode(String value) {
        return "[" + value + "]";
    }
}
```

This bean lies **outside** `demo.shop`, so it is absent from `ShopOnlyConfig`. It only appears in the `ExpandedConfig` context because that configuration adds the `demo.shared` root.

### 6.6. Run and Verify stdout

In the directory containing `build.gradle`:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `.\gradlew.bat run --quiet` on Windows PowerShell. The lines printed by `System.out.println` are:

```text
shop.orderService = true
shop.sharedEncoder = false
shop.message = order:ok
expanded.orderService = true
expanded.sharedEncoder = true
expanded.message = [order:ok]
```

**Exact explanation of the output:**

1. `shop.orderService = true`: root package `demo.shop` contains `demo.shop.service`, so `OrderService` is discovered.
2. `shop.sharedEncoder = false`: `demo.shared.text` is a sibling branch, not under `demo.shop`.
3. `shop.message = order:ok`: `OrderService` receives `OrderRepository` via constructor; both lie under the scanned root.
4. `expanded.orderService = true`: marker `ShopPackage.class` places a root at `demo.shop`.
5. `expanded.sharedEncoder = true`: marker `SharedPackage.class` adds root `demo.shared`.
6. `expanded.message = [order:ok]`: both beans are retrieved directly from the context and Java methods are called; there is no HTTP or web controller.

Two independent contexts have separate bean registries. A bean registered in `expanded` cannot cause a corresponding bean to appear in `shop`.

## 7. Which Package Should `@SpringBootApplication` Be Placed In?

In Spring Boot, `@SpringBootApplication` includes the functionality of `@SpringBootConfiguration`, `@EnableAutoConfiguration`, and `@ComponentScan`. When no custom scan attributes are specified, component scanning uses the **package containing the `@SpringBootApplication` class** as the root and searches its subpackages.

Recommended layout for a typical project:

```text
com.acme.shop/
├── ShopApplication.java              <-- @SpringBootApplication
├── api/
│   └── OrderController.java          <-- @RestController
├── service/
│   └── OrderService.java             <-- @Service
└── persistence/
    └── OrderRepositoryImpl.java      <-- @Repository
```

Placing `ShopApplication` in `com.acme.shop` finds components across all three sub-branches without listing each branch's name. If `ShopApplication` is moved down into `com.acme.shop.api`, the default scanner will mainly search `com.acme.shop.api` and branches beneath it; services/repositories in sibling packages risk not being discovered.

Illustrative Boot class code:

```java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

This snippet requires appropriate Spring Boot dependencies and is a **separate illustration**, not part of the runnable Spring Context project in section 6.

### Adjusting Scan Packages in Boot

When components belong to multiple root packages, you can specify them explicitly:

```java
@SpringBootApplication(scanBasePackages = {
        "com.acme.shop",
        "com.acme.shared"
})
public class ShopApplication {
}
```

Or type-safely:

```java
@SpringBootApplication(scanBasePackageClasses = {
        ShopMarker.class,
        SharedMarker.class
})
public class ShopApplication {
}
```

Both Boot snippets are **standalone illustrative variants**, requiring the corresponding marker classes/packages. In Spring Boot, `scanBasePackages` and `scanBasePackageClasses` are aliases to the **`@ComponentScan`** mechanism.

**Important limitation:** the `scanBasePackages` attributes of `@SpringBootApplication` adjust **component scanning**, and do not automatically adjust the scan scope for **JPA entities** or **Spring Data repository interfaces**. Those mechanisms follow different configuration rules; when needed, use `@EntityScan` and `@EnableJpaRepositories` (or the equivalent mechanism for the Spring Data module). Widening component scan does not guarantee that entities/repository proxies in packages outside Boot's root will be automatically recognized.

## 8. Multiple Modules and Java Libraries: Classpath Conditions

A multi-module Gradle application might be organized as:

```text
shop-app
  └── package com.acme.shop
common-library
  └── package com.acme.common
```

Suppose `common-library` publishes a `@Component` in `com.acme.common`. For the application to receive the bean via component scanning, **all of the following** are simultaneously required:

1. The artifact/module containing the class must be on the runtime classpath (or visible from the corresponding module system).
2. The base package scan must cover `com.acme.common`.
3. The class must be a valid component candidate and not excluded by filters/conditions.
4. All dependencies required to instantiate the bean must be satisfied.

Example in `shop-app`'s `build.gradle`:

```groovy
dependencies {
    implementation project(':common-library')
}
```

This is an **illustration for a multi-project Gradle build** that has declared `:common-library`; the line above is not sufficient by itself to form a standalone project. It only resolves the presence of the library module on the classpath; the scanner must still scan the right package, or the library must provide its own registration mechanism.

**Do not set base packages solely by Gradle module name.** Spring scans Java packages on the classpath and does not directly interpret Gradle project names. One Gradle module can contain multiple packages, or multiple modules can share a single package prefix.

### Java Module System (JPMS)

If the application runs on the Java module path with `module-info.java`, Spring's metadata reading, constructor invocation, or reflection-based injection may require appropriate `exports`/`opens` configuration. A JPMS reflection access error does not mean the package was not scanned. Distinguish between "bean definition not found" and "bean found but cannot be instantiated or have members accessed."

## 9. Controlled Scanning with Filters

`includeFilters` and `excludeFilters` only select/exclude candidates **within the base packages**. Example excluding an implementation from a scan pass:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyOrderService.class))
class AppConfig { }
```

This snippet requires importing `FilterType` and defining `LegacyOrderService`. An exclude filter does not prevent a class from being registered via `@Bean` or another scanner. With `useDefaultFilters=false`, default stereotypes are not picked up unless an appropriate include filter is present; filters also do not expand the package scan region.

## 10. Combining `@ComponentScan` with `@Import` and `@Bean`

`@Import` brings supported classes/configurations into the registration process, while `@Bean` registers definitions from factory methods. They can introduce beans into the context even when the class lies outside the component scan root:

```java
@Configuration(proxyBeanMethods = false)
class UtilityConfig {
    @Bean
    JsonHelper jsonHelper() { return new JsonHelper(); }
}
```

`JsonHelper` is a hypothetical type in this snippet. Do not open up scanning across an entire library just to create one needed bean; however, ensure the configuration containing `@Bean` is actually registered/imported. Having a dependency JAR on the runtime classpath and having annotations scanned are two separate conditions.

## 11. Scan Scope Errors and How to Diagnose Them

| Symptom | Common Cause | How to Verify/Fix |
| --- | --- | --- |
| `@Service` is on the class but bean is missing | Class is in a package outside the scan root | Compare the class's `package` with `@ComponentScan`/Boot main class package |
| Scanning `com.acme.shop.service` misses repository | Repository in `com.acme.shop.persistence` is a sibling | Use a marker at `com.acme.shop` or add the persistence root |
| Empty `@ComponentScan` scans the wrong place | Configuration class sits in a narrow package | Place configuration at the proper root or specify `basePackageClasses` |
| `@SpringBootApplication` placed deep in web package | Default scan only covers the web branch | Move Boot class to root package or explicitly widen scan |
| Widened `scanBasePackages` but JPA repository still missing | Component scan differs from Spring Data repository scanning | Check `@EnableJpaRepositories`/Spring Data auto-config packages |
| `@Entity` is not managed | Entity scanning differs from component scanning | Check `@EntityScan`/JPA configuration |
| Library module has class but bean is still unseen | Missing runtime dependency or missing scan package root | Check dependency graph/runtime classpath and packages |
| Class outside scan still becomes a bean | `@Import`, `@Bean`, auto-configuration, or another registration exists | Check all bean definition sources rather than assuming scan is buggy |
| `@ComponentScan` has right root yet class disappears | Excluded by `excludeFilters`, `@Profile`/`@Conditional`, or not a candidate | Check metadata/filters/conditions |
| Used `useDefaultFilters=false` and `@Service` vanished | Default stereotype filters were disabled | Add proper include filters or remove the disabling setting |
| Bean definition exists but bean creation fails | Missing constructor dependency, circular dependency, factory error, JPMS reflection | Separate registration from instantiation; read exception chain |
| Two beans share a name after widening scan | Classes in different packages share default/explicit name | Choose intentional names or narrow scan boundaries |
| Overly broad scan causes unexpected beans/conflicts | Base package is too large a common root | Narrow package roots, use markers/filters/explicit registration |
| Typed `basePackages="...OrderService"` | Passed a class name instead of a package | Change to package name or use `basePackageClasses` |
| Component in source folder missing at runtime | Class not compiled or not on runtime classpath | Check build output, source sets, and dependencies |

### Evidence-Based Debugging Procedure

**Step 1 — Identify the error type.** If `getBeanNamesForType(OrderService.class)` is empty, check registration/candidates. If a name is present yet bean creation fails, investigate constructors, factories, scope, post-processors, or module accessibility. If multiple names appear, resolve ambiguity via appropriate injection/qualifier design.

**Step 2 — Compare actual packages.** Open the `package` declaration of the component class and the configuration/Boot main class. Draw a root -> subpackage diagram. Do not rely solely on how files appear in the IDE tree.

**Step 3 — Read the active scan configuration.** Verify whether `@ComponentScan` is on a class that has actually been registered/imported. If multiple configuration classes exist, check each scan pass rather than inferring everything from one annotation.

**Step 4 — Check conditions.** Inspect `@Profile`, `@Conditional`, and exclude/include filters; with Boot, auto-config conditions and active profiles also need checking if a bean depends on them.

**Step 5 — Use the context to inspect instead of guessing.** For example, in a test context:

```java
String[] names = context.getBeanNamesForType(OrderService.class);
System.out.println(java.util.Arrays.toString(names));
```

This is an **illustrative snippet** assuming a `context` variable and `OrderService` class are available. It helps identify registered/visible beans by type that the container can resolve. With Spring Boot, the condition evaluation report or `/actuator/beans` (when Actuator is added and the endpoint is enabled/authorized) can help, though it is not a prerequisite for debugging Spring Core Container.

## 12. Package Structure Pitfalls to Avoid

### Pitfall A: All Classes Under the Same Source Root Are Scanned Together

`src/main/java` is a build source directory; `com.example.shop` and `org.example.shared` are still two distinct Java packages. They are only discovered by Spring within **configured scan roots**, not because they share `src/main/java`.

### Pitfall B: `basePackageClasses` Scans "by the Class's Type"

`basePackageClasses = OrderService.class` **does not tell Spring to create only beans of type `OrderService`**. It tells Spring to scan the package containing `OrderService`. To target a specific bean by class, register it explicitly with `@Import` or `@Bean` when appropriate.

### Pitfall C: Scanning as High Up a Parent Package as Possible

Opening `@ComponentScan("com")` can traverse many unrelated dependencies or application packages. The result can be slow startup, unintended bean definitions, naming conflicts, or duplicate dependencies. Choosing **narrow yet sufficiently covering package roots** is a better design.

### Pitfall D: Widening Scan Means Every Framework Is Configured

JPA entity scanning, Spring Data repository scanning, MVC mapping, transaction management, and security configuration have separate mechanisms. A `@RestController` class scanned into a bean does not mean URL mappings run if the web context is not configured. Widening component scan also does not automatically enable repository proxies or entity scanning.

### Pitfall E: Annotations Always Create Beans Immediately

Component scanning can discover classes, but instances are only created according to lifecycle/scope and dependency resolution. `@Lazy`, prototype scope, profile conditions, and factory-method beans can change when an instance exists. When debugging, distinguish **missing bean definition** from **bean present but failing to instantiate**.

## 13. Practice Exercises with Answers

**Exercise 1 — Moving a marker into a subpackage.** In the section 6 example, replace `ShopPackage.class` in `ExpandedConfig` with `OrderService.class`, keeping `SharedPackage.class`. Predict the result.

*Answer:* Spring only scans `demo.shop.service` and `demo.shared`. `OrderRepository` in `demo.shop.persistence` is not scanned; creating `OrderService` will lack the `OrderRepository` dependency and context refresh typically fails with `UnsatisfiedDependencyException`. Execution cannot reach the `expanded` output lines without adding repository registration.

**Exercise 2 — Adding a package root.** Change `ShopOnlyConfig` to:

```java
@ComponentScan(basePackages = {"demo.shop", "demo.shared"})
```

*Answer:* `shop.sharedEncoder = true` and the `SharedEncoder` bean can be retrieved from the `shop` context. Other code remains unchanged; this demonstrates changing scan scope without moving classes.

**Exercise 3 — Moving the configuration class to another package.** Suppose `ShopOnlyConfig` moves from `demo.app` to `demo.config` while keeping `@ComponentScan(basePackages="demo.shop")`. Will it still scan `OrderService`?

*Answer:* **Yes**. Because `basePackages` explicitly states the scan root, the configuration class's new location does not change the declared root.

**Exercise 4 — Removing `basePackages`.** Keep `ShopOnlyConfig` in `demo.app` and change the annotation to `@ComponentScan` with no arguments. Will the `OrderService` bean be registered automatically?

*Answer:* **Not via this scan pass**. The default scanner starts from `demo.app` and its subpackages, whereas `demo.shop` is a sibling. Without another registration method, `getBean(OrderService.class)` will fail.

**Exercise 5 — Only adding a Gradle dependency.** The application depends on a module containing a `@Component` in `com.example.payments`, yet `@ComponentScan` only scans `com.example.orders`. Is the new dependency enough for Spring to create the payment bean?

*Answer:* **No**. The dependency ensures the class is available on the classpath; Spring also needs an appropriate base package or an independent registration mechanism.

**Exercise 6 — Entity/repository scanning in Boot.** Given `@SpringBootApplication(scanBasePackages={"com.example.app","com.example.data"})`, an `@Entity` under `com.example.data.model` is not recognized by JPA. Can you conclude `@ComponentScan` is broken?

*Answer:* **No**. `@Entity` is not a Spring component stereotype to be scanned like `@Service`. Check JPA entity scanning and `@EntityScan` or auto-configuration packages; similarly, repository interfaces belong to Spring Data's process.

**Exercise 7 — Debugging "bean exists but cannot be injected".** If `getBeanNamesForType(PaymentClient.class)` returns two names, is widening `@ComponentScan` further guaranteed to fix the error?

*Answer:* **No**. When multiple candidates already exist, inspect `@Qualifier`, `@Primary`, or dependency design; widening scanning can worsen ambiguity.

## 14. Design Checklist and Key Takeaways

Before declaring `@ComponentScan`:

1. Explicitly document **which package roots are scanned** and which subpackages contain required components.
2. Use argument-free `@ComponentScan` when the configuration class genuinely sits at the desired root; otherwise, declare `basePackages` or prefer `basePackageClasses` with markers placed at the exact roots.
3. Keep the Boot main class in an appropriate root package; only widen scanning when modules/packages lie outside the default boundary.
4. Verify the runtime classpath, stereotypes, profiles/conditions, and filters; scanning the right package alone does not guarantee bean instantiation.
5. Distinguish component scan from `@Bean`/`@Import`, Spring Data repository scanning, and JPA entity scanning.
6. Do not place the scan root overly high just to avoid package design; narrow, intentional scanning is easier to maintain and test.

Core rule: **`@ComponentScan` scans downward from one or more base packages into subpackages, and does not automatically traverse up to parent packages or across to sibling branches.** The location of the class declaring the annotation only determines the default root when no package is explicitly specified. `basePackageClasses` enables type-safe markers; `basePackages` uses string package names. Scanning the right classpath region is one prerequisite for bean registration, while stereotypes and other conditions determine whether a class is actually registered.

### Official Spring Documentation

- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework Javadoc — `@ComponentScan`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework Reference — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Boot Reference — Locating the Main Application Class](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html).
- [Spring Boot Javadoc — `@SpringBootApplication`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html).
