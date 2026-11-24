# Declaring basePackages and basePackageClasses in Spring Component Scan

## Objectives

The Spring Core Container can discover classes marked with `@Component`, `@Service`, `@Repository`, `@Controller`, or compatible stereotypes, and create corresponding bean definitions without writing a `@Bean` method for each class. This mechanism is called **component scanning**. However, Spring needs to know **which packages to start searching in**.

The `org.springframework.context.annotation.ComponentScan` annotation provides two commonly used attributes to define scope:

- `basePackages`: specifies **package names as strings** (for example, `"com.example.orders"`).
- `basePackageClasses`: specifies **anchor classes/interfaces**; Spring takes the **packages containing those types** as scanning starting points.

This lesson helps you choose the right attribute, combine multiple packages, understand recursive subpackage scanning, use marker interfaces safely during refactoring, troubleshoot missing beans, and verify results with a runnable Java 17 + Spring Framework example.

**Scope:** This covers configuring `@ComponentScan` in **Spring Core Container**. JPA entity scanning, Spring Data repositories, or manual bean registration have their own rules; they are mentioned only briefly where confusion is common.

## 1. What Problem Does Component Scanning Solve?

Consider the package structure:

```text
com.example.shop
├── app
│   └── AppConfig.java
├── orders
│   ├── OrderService.java
│   └── internal
│       └── OrderValidator.java
└── shipping
    ├── ShippingService.java
    └── ShippingPackage.java
```

Suppose `AppConfig` carries `@Configuration` and `@ComponentScan`. Without configuring additional packages, Spring starts scanning at the **package of the class declaring `@ComponentScan`**, namely `com.example.shop.app`, including its subpackages. Because `orders` and `shipping` are **sibling** packages, they are not found by default scanning from `app`.

A common cause of `NoSuchBeanDefinitionException` or `UnsatisfiedDependencyException` is **a component that exists but lies outside the scan region**.

You can solve this in either of two ways:

```java
// Declared using package name strings:
@ComponentScan(basePackages = {
    "com.example.shop.orders",
    "com.example.shop.shipping"
})
```

or:

```java
// Using two marker types placed in the two target packages:
@ComponentScan(basePackageClasses = {
    OrdersPackage.class,
    ShippingPackage.class
})
```

These are **illustrative annotation snippets**. To use them, `@Configuration` is needed on the configuration class, along with importing `org.springframework.context.annotation.ComponentScan` and the corresponding markers.

Both approaches instruct Spring to scan **two package regions**; they do not mean listing a fixed set of two beans to create.

## 2. Exact Meaning of `basePackages`

Attribute signature in `@ComponentScan`:

```java
String[] basePackages() default {};
```

Some valid ways to write it:

```java
@Configuration
@ComponentScan(basePackages = "com.example.shop")
class ShopConfig {
}
```

```java
@Configuration
@ComponentScan(basePackages = {
    "com.example.shop.orders",
    "com.example.shop.shipping"
})
class ShopConfig {
}
```

In both snippets, the required imports are `org.springframework.context.annotation.Configuration` and `org.springframework.context.annotation.ComponentScan`. These snippets only illustrate configuration; a standalone runnable example is in section 6.

### A Package Is a Java Name, Not a File Path

Use `"com.example.shop.orders"`, not `"src/main/java/com/example/shop/orders"` or `"com/example/shop/orders"`. The package in the annotation is the logical name declared by classes and present on the classpath, independent of the IDE's source root directory.

Package names are **case-sensitive**. If the code declares `package com.example.shop.orders;`, then `"com.example.shop.Orders"` does not point to that package.

### Recursive Scanning Through Subpackages

When specifying `"com.example.shop.orders"`, Spring inspects candidates under:

```text
com.example.shop.orders
com.example.shop.orders.internal
com.example.shop.orders.api
com.example.shop.orders.impl
```

Therefore, a sufficiently narrow parent package typically covers subpackages belonging to the same feature. **Sibling packages** such as `com.example.shop.shipping` are not covered if only `com.example.shop.orders` is scanned.

Scanning `"com.example.shop"` also includes `orders`, `shipping`, and `app`. This is convenient for small applications, but in large systems it may register unwanted components if all modules live under that package.

### `value` Is an Alias for `basePackages`

`@ComponentScan` also has the `value()` attribute, which is an alias for `basePackages()`. When writing a single unnamed argument:

```java
@ComponentScan("com.example.shop.orders")
```

it has the exact same meaning as:

```java
@ComponentScan(basePackages = "com.example.shop.orders")
```

Because `value` and `basePackages` are **two names for the same attribute**, do not set them to two independent or differing lists on the same annotation. If you want multiple packages, pass an array to **one** of the two names.

### When to Use `basePackages`?

Suitable when:

- The packages to scan are specified by configuration contract or a stable structure.
- You want to spell out each package name explicitly in the annotation.
- Configuring integration with package regions where the project has no convenient marker interface.

Main limitation: package names are **strings**, so package refactoring/renaming tools do not always update string literals. If a class moves from `com.example.shop.orders` to `com.example.shop.sales.orders` while the annotation keeps the old string, Spring may fail to find the expected bean.

## 3. Exact Meaning of `basePackageClasses`

Attribute signature in `@ComponentScan`:

```java
Class<?>[] basePackageClasses() default {};
```

With:

```java
@ComponentScan(basePackageClasses = ShippingPackage.class)
```

Spring resolves **the package of `ShippingPackage`** and scans that package along with its subpackages. If the marker class resides at:

```java
package com.example.shop.shipping;

public interface ShippingPackage {
}
```

then the mechanism has the same effect as specifying `"com.example.shop.shipping"`, provided those types exist on the classpath. The marker interface **does not need** `@Component`, because its sole purpose is to serve as a package anchor.

Crucial point: `basePackageClasses = ShippingService.class` **does not say Spring will only register `ShippingService`**. It instructs Spring to scan **the entire package containing `ShippingService` and its subpackages**, subject to scanner conditions.

### Why Are Marker Interfaces Useful?

The Spring Javadoc suggests using a dedicated no-behavior class or interface solely as a marker:

```java
package com.example.shop.orders;

/** Package anchor for component scanning. */
public interface OrdersPackage {
}
```

If there are two separate feature modules:

```java
@Configuration
@ComponentScan(basePackageClasses = {
    OrdersPackage.class,
    ShippingPackage.class
})
class ApplicationConfig {
}
```

With full imports for `OrdersPackage` and `ShippingPackage`, the compiler verifies that the marker types exist. When refactoring packages and moving the marker using IDE tools, class references have the opportunity to be updated or caught by the compiler, instead of leaving a package string silently pointing to the wrong place.

Place the marker at the **root of the package you want to scan**, such as `com.example.shop.shipping.ShippingPackage`. If the marker accidentally sits inside `com.example.shop.shipping.internal`, the scanner starts from `internal` and may miss components in `com.example.shop.shipping.api`.

### Is a Dedicated Marker Required?

No. You can specify any class or interface located in the target package:

```java
@ComponentScan(basePackageClasses = {
    OrderService.class,
    ShippingService.class
})
```

This is valid if both classes exist and are imported; the scanner uses their packages as anchors. However, if `OrderService` moves down into `orders.impl`, the scan region can accidentally shrink. A marker placed stably at the root package usually communicates more clearly that **this is a feature boundary**, not a random class.

### What `basePackageClasses` Does Not Do

- Does not automatically create a bean for a stereotype-less marker interface.
- Does not automatically add `@Component` to every class in the package.
- Does not "inject" the listed classes into a service; dependency injection is a separate step.
- Does not restrict the scanner solely to the classes listed in the array.
- Does not require the marker to be a concrete implementation; an empty interface is valid.

Multiple markers in the same package only add redundant declarations; usually one marker per package root to scan is enough.

## 4. Which Attribute to Choose? Can Both Be Used Together?

Both attributes **can appear together** on a single `@ComponentScan`:

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.legacy",
    basePackageClasses = { OrdersPackage.class, ShippingPackage.class }
)
class ApplicationConfig {
}
```

Spring builds the list of source packages from **both attributes**, and scans the corresponding regions. Understand this as a **union of root packages**, not an intersection condition ("package must both match the string and contain the marker").

| Criterion | `basePackages` | `basePackageClasses` |
| --- | --- | --- |
| Value type | `String[]` | `Class<?>[]` |
| Example | `"com.example.orders"` | `OrdersPackage.class` |
| How scan region is chosen | Specified package names | Packages containing the anchor types |
| Subpackages | Yes | Yes |
| Type safety on source restructuring | Depends on updating strings | Compiler/type references help catch changes |
| Readability when listing independent packages | Direct clear names | Clearer when markers already exist |
| Can be combined with the other attribute | Yes | Yes |

**Selection tip:** For packages in a codebase you control, `basePackageClasses` with marker interfaces is often preferable because it relies less on package name strings. For stable, simple, explicit package roots, `basePackages` is also completely suitable. Avoid turning this choice into an end in itself: what matters is that the scan region is **sufficient**, **accurate**, **easy to test**, and **not overly broad**.

### Multi-Package Example: Three Equivalent Ways for Scan Region

Suppose `OrdersPackage` is in `com.example.orders` and `ShippingPackage` is in `com.example.shipping`:

```java
// Option 1: all strings.
@ComponentScan(basePackages = {
    "com.example.orders", "com.example.shipping"
})

// Option 2: all markers.
@ComponentScan(basePackageClasses = {
    OrdersPackage.class, ShippingPackage.class
})

// Option 3: combined.
@ComponentScan(
    basePackages = "com.example.orders",
    basePackageClasses = ShippingPackage.class
)
```

The three snippets above are **separate annotation alternatives**, not three annotations to stack on one class. Whichever option is used, the chosen root packages determine which classes the scanner inspects, after which stereotypes/filters and other bean registration conditions are evaluated.

## 5. Default Behavior When No Root Package Is Declared

When a configuration class in `com.example.shop.app` has `@ComponentScan` with no arguments, Spring scans from **`com.example.shop.app` and its subpackages**. It does not automatically find sibling `com.example.shop.orders`. `@ComponentScan(basePackages={})` also uses the default package when no other root is present. For projects with multiple features, place configuration at an appropriate root or specify roots explicitly via strings/markers. Avoid placing configuration classes in Java's default package because scanning can become overly broad.

## 6. Runnable Java 17 Example: Combining Both Attributes

This example uses Spring Framework 6.2 without Spring Boot. We deliberately place the configuration in `demo.app.config`, while two `@Service` classes sit in two sibling packages. The configuration uses:

- `basePackages = "demo.orders"` to find `OrderService`;
- `basePackageClasses = ShippingPackage.class` to find `ShippingService` in `demo.shipping`.

### 6.1. Project Structure

```text
component-scan-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        ├── app/
        │   ├── Main.java
        │   └── config/
        │       └── AppConfig.java
        ├── orders/
        │   └── OrderService.java
        └── shipping/
            ├── ShippingPackage.java
            └── ShippingService.java
```

### 6.2. Maven POM

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>component-scan-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. Configuration Class

File `src/main/java/demo/app/config/AppConfig.java`:

```java
package demo.app.config;

import demo.shipping.ShippingPackage;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackages = "demo.orders",
        basePackageClasses = ShippingPackage.class
)
public class AppConfig {
}
```

The `AppConfig` class is not a service in either scanned package. It is **explicitly registered** when creating the context in `Main`. The `@ComponentScan` annotation then specifies the regions where the remaining components are found.

### 6.4. First Service Found via `basePackages`

File `src/main/java/demo/orders/OrderService.java`:

```java
package demo.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String label() {
        return "orders";
    }
}
```

Because `demo.orders` is a root package specified as a string, the scanner finds `OrderService` annotated with `@Service`. `@Service` is a Spring stereotype recognized by component scan under default settings.

### 6.5. Marker and Second Service Found via `basePackageClasses`

File `src/main/java/demo/shipping/ShippingPackage.java`:

```java
package demo.shipping;

/** Marker identifying the shipping package root for @ComponentScan. */
public interface ShippingPackage {
}
```

File `src/main/java/demo/shipping/ShippingService.java`:

```java
package demo.shipping;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {
    public String label() {
        return "shipping";
    }
}
```

`ShippingPackage` is an empty interface, carries no `@Component`, and does not become a service bean just because it is used in `basePackageClasses`. What matters is that this interface resides in `demo.shipping`; from there Spring finds `ShippingService`, which carries the `@Service` stereotype.

### 6.6. Main Class and Output

File `src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.app.config.AppConfig;
import demo.orders.OrderService;
import demo.shipping.ShippingService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService orders = context.getBean(OrderService.class);
            ShippingService shipping = context.getBean(ShippingService.class);

            System.out.println("orders=" + orders.label());
            System.out.println("shipping=" + shipping.label());
            System.out.println("markerBean=" +
                    context.containsBean("shippingPackage"));
        }
    }
}
```

From the directory containing `pom.xml`, run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.app.Main
```

Lines printed by the program (excluding Maven/Spring environment logging):

```text
orders=orders
shipping=shipping
markerBean=false
```

**Why is the output exact?**

1. `AppConfig` is passed to `AnnotationConfigApplicationContext`, so the scanner does not need to discover it.
2. `@ComponentScan(basePackages = "demo.orders")` covers `OrderService`.
3. `@ComponentScan(basePackageClasses = ShippingPackage.class)` uses package `demo.shipping` as root, thus covering `ShippingService`.
4. `context.getBean(OrderService.class)` and `context.getBean(ShippingService.class)` both succeed because beans of the right types exist.
5. The marker interface has no stereotype and no explicit bean definition, so `containsBean("shippingPackage")` is `false`.

You can replace `AppConfig` completely with the marker approach for both packages by adding `OrdersPackage` in `demo.orders`:

```java
// Illustrative option; requires declaring interface OrdersPackage
// inside demo.orders, and importing both markers.
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = {
        OrdersPackage.class, ShippingPackage.class
})
public class AppConfig {
}
```

Or replace it with a string array:

```java
// Another illustrative option, replacing AppConfig in the example:
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = {
        "demo.orders", "demo.shipping"
})
public class AppConfig {
}
```

These alternatives share the same intent of selecting **two package roots**; do not place multiple `AppConfig` classes with the same name in one project simultaneously.

## 7. What Happens If One Attribute Is Removed?

Try editing `AppConfig` to keep only:

```java
@ComponentScan(basePackages = "demo.orders")
```

Then the scanner does not look for `ShippingService` in `demo.shipping`, unless you register it through another mechanism. If you still run `Main` as before, the call:

```java
context.getBean(ShippingService.class);
```

will not find a matching bean and will throw `NoSuchBeanDefinitionException`. This is expected behavior: the component lies outside the scan region. It does not mean Spring failed to understand `@Service` or that the Java class does not exist.

Conversely, if only this is present:

```java
@ComponentScan(basePackageClasses = ShippingPackage.class)
```

`OrderService` lies outside the `demo.shipping` root; therefore `getBean(OrderService.class)` fails unless the bean is registered by another path.

This experiment shows that the two attributes **augment the scan region**. When both appear together, both sets of packages are inspected; when one side is removed, the corresponding scan region disappears.

### Inspecting Using Only BeanFactory

If you want to observe registered beans without letting `getBean` throw an exception:

```java
// Illustrative snippet in main/already-created context:
boolean hasOrders = context.containsBean("orderService");
boolean hasShipping = context.containsBean("shippingService");
```

With `@Service` and no explicit name, Spring typically uses a default bean name from the simple class name with the first character lowercased: `orderService` and `shippingService`. However, the name can differ when using `@Service("customName")` or a custom `BeanNameGenerator`. Thus when checking candidates by type, `getBeanNamesForType` or `getBeansOfType` usually reflects the goal more accurately:

```java
// Illustrative snippet: use while context is still open.
String[] shippingNames =
        context.getBeanNamesForType(ShippingService.class);
```

When no bean is found, the array may be empty. **Do not rely on names alone** if the goal is to verify that a class of the right type has been registered.

## 8. Which Classes Does the Scanner Detect?

`basePackages` and `basePackageClasses` only decide **where to search**; they do not force every class to become a bean. With `useDefaultFilters=true`, Spring inspects `@Component`, `@Service`, `@Repository`, `@Controller`, and composed stereotypes on concrete, independent classes. A marker interface without a stereotype is strictly a package anchor.

When a bean is missing, check the runtime classpath, filters, `@Profile`/`@Conditional`, dependencies, bean name errors, and which context is in use. Beans outside the scan region can still appear via `@Bean`/`@Import`. Disabling `useDefaultFilters` requires adding explicit include filters; simply annotating with `@Service` is no longer enough for the scanner to pick it up.

## 9. Scanning Just Enough: Avoiding Too Narrow or Too Broad

If the checkout module has branches `com.company.checkout.api`, `application`, `domain`, and `infrastructure`, a marker in `com.company.checkout` covers the whole feature. A marker placed deep under `...checkout.application.internal` misses sibling packages; scanning from `com.company` can pull in many unrelated modules.

Choose **package roots broad enough for valid dependencies and narrow enough for the module's exact boundary**. In multi-project Gradle/JAR setups, the scanner still reads Java packages on the runtime classpath, not Gradle module names, to establish boundaries. When a library exposes one adapter among many internal components, explicit `@Import`/`@Bean` can express that choice more clearly than a broad package scan.

## 10. Important Details About Refactoring and Modules

### When Renaming Packages in the IDE

With strings:

```java
@ComponentScan(basePackages = "com.company.oldname")
```

if the package is renamed to `com.company.newname` and the annotation is not updated, the code still **compiles** because any string literal is syntactically valid Java. The problem only surfaces when the context runs and the expected bean is missing.

With a marker:

```java
@ComponentScan(basePackageClasses = NewModulePackage.class)
```

the compiler checks the `NewModulePackage` reference. If the marker moves and imports are not fixed, compilation fails. If the marker moves along with the package and imports are updated, the scanner follows the new package. This is the "type-safe" advantage of this declaration style—even though it does **not** automatically guarantee that every needed bean resides in the new region.

### Splitting Packages Across Multiple Modules/JARs

If `OrdersPackage` lives in a dependent module, `basePackageClasses = OrdersPackage.class` can only serve as an anchor when that type **is present on the application's classpath**. Package scanning finds candidates on the classpath via Spring's mechanism; it **does not automatically add a Maven/Gradle dependency** to the module containing the class or download JARs over the network.

Therefore, for multi-module projects, all of the following are needed:

1. Proper runtime/build dependencies so classes are on the classpath.
2. Scan configuration targeting the right packages.
3. Conditions ensuring classes are actually valid component candidates.

If the marker is already importable while an implementation resides in a module not yet placed on the runtime classpath, scanning still cannot discover that implementation.

### Where to Place the Marker?

A simple convention:

```text
com.company.module.orders
├── OrdersPackage.java       <-- marker, no @Component
├── api/...
├── application/...
└── infrastructure/...
```

The marker rarely changes, sits in the common parent package, and has an intent-revealing name. Do not put the marker inside `impl` merely because a service currently lives there, unless you only want to scan that specific package.

## 11. Notes When Using Spring Boot

Spring Boot already integrates component scanning into `@SpringBootApplication`. To customize roots, use its dedicated attribute names:

| `@ComponentScan` | `@SpringBootApplication` | Selection Anchor |
| --- | --- | --- |
| `basePackages` | `scanBasePackages` | Package strings |
| `basePackageClasses` | `scanBasePackageClasses` | Marker types |

```java
@SpringBootApplication(scanBasePackageClasses = {
    OrdersPackage.class, ShippingPackage.class
})
public class ShopApplication { }
```

This snippet requires imports, marker types, and Boot dependencies. Without customization, Spring Boot typically scans the package containing the application class and its subpackages. **`scanBasePackages` does not change the scope of JPA entity scanning or Spring Data repository scanning**: check `@EntityScan`, `@EnableJpaRepositories`, or the corresponding mechanism when using those technologies. Adding `@ComponentScan` directly onto a Boot class can alter default composed scan filters; for simple root adjustments, use the attributes provided on `@SpringBootApplication`.

## 12. Common Errors and How to Fix Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for a `@Service` | Service lies outside the root package | Verify packages and deliberately expand `basePackages`/`basePackageClasses` |
| Context startup fails with `UnsatisfiedDependencyException` | A bean depends on an unregistered service, or an internal dependency of the service is missing | Read the exception chain to identify **which bean** is actually missing |
| Only `shipping` package scanned, `orders` missing | Marker only declared in `shipping` | Add the `orders` root via string or corresponding marker |
| Used `basePackageClasses = SomeService.class` but sibling classes in same feature missing | `SomeService` sits in a narrow subpackage | Place the marker at the feature root |
| Used `"src/main/java/..."` | Used a file path instead of a Java package name | Change to `"com.example...."` |
| Bean lost after package refactor despite compiling | Stale `basePackages` string | Update the string or switch to a marker type |
| Marker does not become a bean | Marker interface has no stereotype | This is intentional; a marker specifies the scan package, not a component itself |
| More beans for an interface than expected | Scan root too broad, pulling in out-of-scope modules | Narrow roots and adjust structure/qualifiers appropriately |
| Bean name conflict | Two components share the same bean name after widening scan | Assign explicit names or fix config/modules rather than ignoring the error |
| JPA entities/repositories not found in Boot | Confusing component scan with entity/repository scan | Configure the separate scan mechanism appropriate to each technology |
| Bean missing despite correct package | Missing runtime JAR, missing stereotype, exclude filter, or condition | Inspect classpath and component metadata |
| Scan changes when moving configuration class | Relying on default scan root | Place `@ComponentScan` in a stable root package or specify roots explicitly |

### Short Debugging Workflow

1. Determine the **actual package name** from the `package ...;` line in the Java file.
2. Verify **whether the class declaring `@ComponentScan` was passed into `ApplicationContext`**.
3. Compute the scan roots: from `basePackages`, the package of each type in `basePackageClasses`, or the config's package by default if unspecified.
4. Check whether the service falls under any of those roots/subpackages.
5. Check whether the class has a stereotype and is on the runtime classpath.
6. If it still fails, read the root exception and inspect filters, conditions, bean dependencies, and name conflicts.

For deeper diagnosis, you can enable DEBUG-level logging for Spring context/scanner packages in development. Avoid reading a "bean not found" message as sole proof that package scanning is wrong: dependencies inside the class or registration conditions can also be the cause.

## 13. Practice and Self-Check

### Exercise 1 — Where Does It Scan by Default?

`AppConfig` sits in `com.example.shop.app` and has:

```java
@Configuration
@ComponentScan
class AppConfig { }
```

`OrderService` is in `com.example.shop.orders`. Will it be discovered solely via this `@ComponentScan`?

**Answer:** No, because `orders` is a sibling package to `app`. The default root is `com.example.shop.app` and its subpackages. To scan `orders`, move the scan root appropriately or declare this package explicitly.

### Exercise 2 — Does the Marker Become a Bean?

`ShippingPackage` is an empty interface in `demo.shipping` with no stereotype. Does `@ComponentScan(basePackageClasses = ShippingPackage.class)` create a bean named `shippingPackage`?

**Answer:** No. The annotation takes **the marker's package** as a scan anchor; the marker does not become a component merely by being referenced in that attribute.

### Exercise 3 — Combining Both Attributes

Which regions does `@ComponentScan(basePackages = "demo.orders", basePackageClasses = ShippingPackage.class)` scan if `ShippingPackage` resides in `demo.shipping`?

**Answer:** `demo.orders`, `demo.shipping`, and the subpackages of each region. A service does not need to reside in **both** packages.

### Exercise 4 — Replacing Marker with a Subpackage Implementation

If you change `basePackageClasses = ShippingPackage.class` to `basePackageClasses = InternalShippingService.class`, where `InternalShippingService` belongs to `demo.shipping.internal`, will the scan region still find `demo.shipping.ShippingService`?

**Answer:** Not from this configuration alone, because the new root has narrowed down to `demo.shipping.internal`. If another scan root covers `demo.shipping`, the bean may still be seen. For stability, place the marker at the exact root package.

### Exercise 5 — Boot and JPA Repositories

With `@SpringBootApplication(scanBasePackages = "com.example.orders")`, an entity or Spring Data repository in another region is still not discovered. Can you simply add the package to `scanBasePackages` to ensure entities and repositories are scanned?

**Answer:** No. That attribute maps to `@ComponentScan`; entity and Spring Data repository scan scopes have separate mechanisms. Check the corresponding configurations such as `@EntityScan` and `@Enable...Repositories`.

### Exercise 6 — Choosing an Easy-to-Refactor Approach

A project has a `com.company.checkout` module containing multiple subpackages and you own all the source. Should you use `@ComponentScan(basePackages = "com.company.checkout")` or a `CheckoutPackage.class` marker?

**Answer:** Both are valid. A marker at the module root is helpful during refactoring because class references are compiler-checked and IDEs usually support package moves. If using strings, ensure tests verify scope updates when packages are renamed.

## 14. Practical Configuration Checklist

Before finalizing a `@ComponentScan` change, check:

- Have you identified the exact **root packages** corresponding to the modules/features to scan?
- Are `basePackages` valid Java package names for the project, rather than filesystem paths?
- Do `basePackageClasses` markers sit in the **intended parent packages**?
- When multiple packages are needed, have all roots or an appropriate parent root been declared?
- Are you avoiding accidentally scanning non-application modules/test components?
- Do the required classes have stereotypes and appear on the runtime classpath?
- Is the `@Configuration` class registered/imported into the container?
- If this is a Boot application, are you using the corresponding attributes and not confusing component scan with JPA/repository scan?
- Is there an integration test or an `AnnotationConfigApplicationContext` startup verifying that core beans are actually present?

## Key Takeaways

**`basePackages` selects by string; `basePackageClasses` selects by anchor type.** Both configure package regions for `@ComponentScan` and can be used together. `basePackageClasses` resolves the **package containing the class/interface**—it does not scan only that class and does not automatically turn the marker into a bean. If no root is declared, Spring uses the package of the class annotated with `@ComponentScan` as the root.

A good configuration targets the right modules, covers needed subpackages, avoids overly broad roots, and verifies that beans are actually registered. When source code is refactored frequently, a marker interface placed at the feature root is well worth considering.

## Official Documentation

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): how to enable component scanning and which stereotypes are recognized.
- [Spring Framework 6.2 — `@ComponentScan` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/ComponentScan.html): `basePackages`, `basePackageClasses`, `value` alias, and package defaults.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): `@Configuration`, `@Bean`, and `AnnotationConfigApplicationContext`.
- [Spring Boot — `@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html): `scanBasePackages`/`scanBasePackageClasses` and their scope of applicability.
