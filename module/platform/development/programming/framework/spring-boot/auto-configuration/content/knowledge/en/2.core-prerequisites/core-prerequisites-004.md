# @ComponentScan and Package Boundaries for Application-Owned Configuration

> **Context:** Spring Boot — auto-configuration; foundational knowledge on where Spring looks for application components. The main topic is the `@ComponentScan` mechanism, package scope, and how to control **application-owned** configurations. This must be clearly distinguished from loading **auto-configuration** from Spring Boot and libraries.

## 1. Why does package placement affect beans?

Spring manages beans inside `ApplicationContext`. A bean can be declared with `@Bean` inside a `@Configuration` class, imported with `@Import`, registered programmatically via APIs, or discovered when Spring **scans the classpath** using `@ComponentScan`.

The scan mechanism traverses configured root packages and their subpackages, finds classes matching its filters, and registers them as **bean definitions**. When initializing the context, Spring creates appropriate instances from these definitions. Spring does not automatically scan every class across the entire classpath.

In a typical Spring Boot application:

```text
dev.example.shop
├── ShopApplication.java             <- @SpringBootApplication
├── catalog
│   ├── CatalogService.java          <- @Service
│   └── CatalogController.java       <- @RestController
└── order
    ├── OrderService.java            <- @Service
    └── OrderConfiguration.java      <- @Configuration

dev.example.integration
└── PartnerClient.java               <- @Component
```

If `ShopApplication` is in package `dev.example.shop` and the scan scope is left unchanged:

- Spring sees components in `dev.example.shop` and **all subpackages** such as `catalog` and `order`.
- `dev.example.integration.PartnerClient` is in a **sibling package**, not under the `dev.example.shop` tree; having `@Component` alone is not enough for it to be registered.
- There is no need to add `@ComponentScan` to every service or controller; scan scope is established from the startup configuration.
- Spring can load classes outside the scan tree by other means, such as `@Import` or auto-configuration; therefore "outside scan scope" only means **not discovered by the scan in question**, not "can never become a bean".

**Key concept:** Java packages are dot-separated hierarchical names, not class inheritance relationships. `dev.example.shop.order` lies beneath `dev.example.shop`; `dev.example.shopping` does not.

## 2. How does `@SpringBootApplication` set up component scanning?

`@SpringBootApplication` combines three primary capabilities:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    excludeFilters = {
        @ComponentScan.Filter(type = FilterType.CUSTOM,
                              classes = TypeExcludeFilter.class),
        @ComponentScan.Filter(type = FilterType.CUSTOM,
                              classes = AutoConfigurationExcludeFilter.class)
    }
)
```

This is a **conceptual breakdown** of the meta-annotation to explain the mechanism, not a standalone Java program. Spring Boot uses Boot-specific additional filters; syntax and internal details may vary by version.

- `@SpringBootConfiguration` marks the application's root configuration class (specialized from `@Configuration`).
- `@EnableAutoConfiguration` activates evaluation of auto-configuration candidates.
- `@ComponentScan` discovers application components within package scope.

When `basePackages` or `basePackageClasses` are omitted, the package containing the class annotated with `@ComponentScan` serves as the starting point. With `@SpringBootApplication`, that is usually the package containing the `main` class.

```java
package dev.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Because the class sits in `dev.example.shop`, the default component scan scope is `dev.example.shop` and its subpackages. This is why Spring Boot guides typically recommend placing the application entry class at the **root package of application code**.

### What does "application-owned configuration" mean?

Here it refers to the components and `@Configuration` classes that the application development team **deliberately writes, selects, and organizes** to implement business behavior: services, controllers, component-style repositories, adapters, mappers, `@Bean` configurations, and so on.

Package boundaries define **by default** which classes the application automatically picks up. An external module or library might contain `@Component` classes, yet you should not assume the application will scan the library's entire package tree to pick them up. Libraries publishing auto-configuration have their own registration mechanism, covered in section 6.

## 3. Which classes does Spring actually detect?

Annotations commonly discovered via `@Component` or its meta-annotations:

| Annotation | Primary role | Can be found by component scan? |
| --- | --- | --- |
| `@Component` | General-purpose component | Yes, within scan scope. |
| `@Service` | Business service | Yes; it is a specialization of `@Component`. |
| `@Repository` | Data-access component | Yes; beyond stereotype role, also supports data-access exception translation when configured. |
| `@Controller` | Spring MVC controller | Yes, if the package is scanned and the corresponding MVC ecosystem is configured. |
| `@RestController` | REST controller (combines `@Controller` and `@ResponseBody`) | Yes, within scan scope. |
| `@Configuration` | Spring configuration definition class | Yes, also a specialization of `@Component`. |
| `@Bean` | Bean-declaring method | The method itself is not "scanned like a class"; it is processed once its enclosing class is loaded as configuration. |

Example:

```java
package dev.example.shop.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

With `ShopApplication` in `dev.example.shop`, this class is found. Conversely, an ordinary Java class without a stereotype and not imported/registered will not automatically turn into a bean just by residing in a scanned package.

### Not every annotation is handled by `@ComponentScan`

- JPA `@Entity` marks an entity, **not a `@Component`**. Entity scanning scope is a separate mechanism, adjustable via `@EntityScan`.
- `JpaRepository` interfaces typically get proxies generated by Spring Data through repository scanning, not because the interface is a `@Component`. This can be adjusted with `@EnableJpaRepositories`; Boot also derives defaults from the application's package.
- `@ConfigurationProperties` describes strongly typed configuration, with multiple registration paths: `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan`, or a scanned component. Simply placing `@ConfigurationProperties` on a class **does not usually mean** `@ComponentScan` discovers it.
- Classes referenced in `@Import` or beans registered programmatically do not need to live inside the scanned packages.

Therefore, do not rely on a single `scanBasePackages` argument assuming entities, Spring Data repositories, and every other configuration type automatically change scope along with it.

## 4. Runnable example: one component inside the package tree and one outside

Create a Java 17, Spring Boot 3.5.7 Maven project with this structure:

```text
package-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── dev/example/
    │           ├── app/
    │           │   ├── BoundaryApplication.java
    │           │   └── order/OrderService.java
    │           └── integration/
    │               ├── BillingMarker.java
    │               ├── BillingClient.java
    │               └── BillingConfiguration.java
    └── test/
        └── java/
            └── dev/example/scan/ComponentScanBoundaryTest.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>package-boundary-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Do not add `spring-boot-starter-web` since the example only needs the context and component scan, not an HTTP server.

### 4.2. A bean **inside** the scan tree

File `src/main/java/dev/example/app/order/OrderService.java`:

```java
package dev.example.app.order;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "ready";
    }
}
```

### 4.3. A bean **outside** the scan tree

File `src/main/java/dev/example/integration/BillingClient.java`:

```java
package dev.example.integration;

import org.springframework.stereotype.Component;

@Component
public class BillingClient {
    public String provider() {
        return "partner";
    }
}
```

File `src/main/java/dev/example/integration/BillingMarker.java`:

```java
package dev.example.integration;

// Marker does not need @Component; used for refactoring-safe package reference.
public interface BillingMarker {
}
```

Both classes sit in `dev.example.integration`, which is a sibling package of `dev.example.app`.

### 4.4. Running the application with default scanning

File `src/main/java/dev/example/app/BoundaryApplication.java`:

```java
package dev.example.app;

import dev.example.app.order.OrderService;
import dev.example.integration.BillingClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class BoundaryApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(BoundaryApplication.class, args)) {
            System.out.println(
                "orderService=" + !context.getBeansOfType(OrderService.class).isEmpty()
            );
            System.out.println(
                "billingClient=" + !context.getBeansOfType(BillingClient.class).isEmpty()
            );
        }
    }
}
```

Run command from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The two lines printed by the program (ignoring Spring Boot startup logs):

```text
orderService=true
billingClient=false
```

This shows the scan boundary working as expected. Importing `BillingClient` in Java code only tells the compiler the class type; the statement `import dev.example.integration.BillingClient;` **does not** register that class as a Spring bean.

## 5. When you need to expand scan scope

There are three common approaches serving different goals. Choose based on package ownership and how broadly you need to load components.

### Approach A: place the startup class at a shared root package

If all code under `dev.example` belongs to the same application, you can place `BoundaryApplication` in `dev.example`. Default scanning will cover both `dev.example.app` and `dev.example.integration`.

This is simple for small applications or monoliths with a clear root package, yet **only makes sense when you intentionally want to scan all components under that root**. If the root is too high or spans multiple shared modules/libraries, the accidentally loaded scope can become large and hard to control.

### Approach B: explicitly configure the packages to scan

You can use the `scanBasePackages` or `scanBasePackageClasses` attribute on `@SpringBootApplication`. For example, modify **only the annotation** in `BoundaryApplication.java`:

```java
@SpringBootApplication(
    scanBasePackageClasses = {
        BoundaryApplication.class,
        dev.example.integration.BillingMarker.class
    }
)
```

This is a **replacement annotation snippet** in the class presented above, not a standalone Java file. Re-running `mvn -q spring-boot:run` will print:

```text
orderService=true
billingClient=true
```

Explanation: Spring scans the package containing `BoundaryApplication` (`dev.example.app`) and the package containing `BillingMarker` (`dev.example.integration`), including subpackages. The marker acts as a **package anchor**, and does not need to be a bean.

String literals can also be used:

```java
@SpringBootApplication(scanBasePackages = {
    "dev.example.app",
    "dev.example.integration"
})
```

Using a marker via `scanBasePackageClasses` is safer when IDEs refactor package names. Remember: **declaring custom scan values specifies the entire set of packages to scan**; do not forget to keep the application root if you still want existing components to appear.

In plain Spring configuration, you can write `@ComponentScan(basePackageClasses = {...})` on a loaded `@Configuration` class. However, in a Boot application, `scanBasePackageClasses` directly on `@SpringBootApplication` is usually clearer and preserves the special filters from Boot's meta-annotation.

### Approach C: `@Import` a specific configuration instead of scanning a whole package

Sometimes an application only needs a single configuration outside the root without picking up every `@Component` in that package. File `src/main/java/dev/example/integration/BillingConfiguration.java`:

```java
package dev.example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BillingConfiguration {

    @Bean
    BillingClient billingClient() {
        return new BillingClient();
    }
}
```

While **keeping default scanning unchanged**, update the annotation on `BoundaryApplication` to:

```java
@SpringBootApplication
@Import(dev.example.integration.BillingConfiguration.class)
public class BoundaryApplication {
    // Keep main(...) from the example unchanged.
}
```

You need to add `import org.springframework.context.annotation.Import;` to the file. With this approach, `BillingConfiguration` is imported directly, its `@Bean` method creates the `BillingClient` bean, and the `dev.example.integration` package is not scanned as a whole. Both check lines also yield `true` and `true`.

**Do not enable** Approach C and Approach B together unintentionally: if `dev.example.integration` is already scanned, `BillingClient` can be picked up via `@Component`, and then `@Bean` in `BillingConfiguration` creates a second bean of the same type. That easily causes injection ambiguity; when two definitions share the same name, registration can fail. For real libraries, choose **one clear registration mechanism**, or guard a default bean with `@ConditionalOnMissingBean`.

Depending on the need, `@Import(SomeComponent.class)` can also register a single specific class directly without scanning an entire package. Importing a configuration class is preferable when grouping multiple interrelated beans into a single configuration point.

## 6. Distinguishing component scan from auto-configuration

This is a central point of the "Spring Boot - auto-configuration" module:

| Aspect | Component scan | Spring Boot auto-configuration |
| --- | --- | --- |
| Purpose | Find application classes in specified packages | Propose default configurations/beans suited to the environment and dependencies |
| Entry point | `@ComponentScan`, defaulted by `@SpringBootApplication` | `@EnableAutoConfiguration`, defaulted by `@SpringBootApplication` |
| Candidate list | Classpath classes matching filters within the scanned package tree | Declared auto-configuration classes, typically in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Conditions | Package scope, include/exclude filters, and stereotypes | `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, ... |
| Typical owner | Application code and configurations explicitly chosen by the app | Spring Boot or a starter/library providing configuration |
| When a user-supplied bean exists | Scanning can still register another bean of the same type; does not automatically back off | Default bean can back off if guarded by the corresponding condition |

**Relationship in practice:**

1. `@SpringBootApplication` activates **both** mechanisms.
2. Component scan finds user beans/configurations within the defined package scope.
3. Auto-configurations are imported separately and generally evaluated after user configuration definitions so conditions like `@ConditionalOnMissingBean` see application-declared beans.
4. If the application declares its own bean, an auto-configuration with an appropriate `@ConditionalOnMissingBean` can refrain from creating the default bean.
5. Changing `scanBasePackages` is **not** how you enable/disable an auto-configuration library. To exclude an auto-configuration, you can use `exclude` on `@SpringBootApplication` or `spring.autoconfigure.exclude`, after understanding its impact.

In custom starters/libraries, avoid thinking "if I put `@Component` classes in the dependency's package, the application will automatically find them". To provide genuine auto-configuration, a library should declare an `@AutoConfiguration` class and list its exact class name in `AutoConfiguration.imports`. A typical auto-configuration uses `@Bean` with conditions rather than component-scanning arbitrary application packages.

**Keep the two scopes separate:** `scanBasePackages` configures component scanning; other default packages that Boot infers from the location of `@EnableAutoConfiguration` do not necessarily change along with this parameter. This is especially important for JPA entities and Spring Data repositories.

## 7. Filtering components when packages cannot yet be reorganized

Sometimes multiple components live in the same package yet the application only wants to detect a subset. `@ComponentScan` supports `includeFilters` and `excludeFilters`, with types such as `FilterType.ANNOTATION`, `ASSIGNABLE_TYPE`, `REGEX`, `ASPECTJ`, `CUSTOM`, and so on.

Example selecting a package while excluding one class:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackages = "dev.example.integration",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = LegacyBillingAdapter.class
    )
)
class IntegrationScanConfiguration {
}
```

This is an **illustrative snippet**; appropriate `import`s and a real `LegacyBillingAdapter` class are needed for it to compile. With `includeFilters`, if you only want classes matching your filter and wish to omit default stereotypes, you can set `useDefaultFilters = false` to avoid picking up every `@Component` class.

Notes when writing filters:

- Filters apply during **that scan pass**, not as a mechanism to remove beans registered through other means.
- `excludeFilters` on a `@ComponentScan` does not automatically remove beans declared via `@Bean` or `@Import`.
- Placing `@ComponentScan` directly on a class that already has `@SpringBootApplication` can prevent Boot's meta-annotation default exclude filters from applying as intended. Boot relies on `TypeExcludeFilter` in test slices and `AutoConfigurationExcludeFilter`; altering them carelessly can cause tests to load too many components. Prefer `scanBasePackageClasses` when you only need to adjust package boundaries.
- Complex filters often signal unclear package/module boundaries; reconsider the structure or use `@Import` for narrow configurations.

## 8. Standalone testing of scan boundaries

This test uses Spring Framework's `AnnotationConfigApplicationContext` to test **only component scanning**, without starting Boot or other auto-configurations. It tests two branches: scanning only the internal service, and then scanning integration as well.

File `src/test/java/dev/example/scan/ComponentScanBoundaryTest.java`:

```java
package dev.example.scan;

import dev.example.app.order.OrderService;
import dev.example.integration.BillingClient;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ComponentScanBoundaryTest {

    @Test
    void defaultOwnedPackageContainsOnlyOrderService() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(OrdersOnlyScan.class)) {
            assertThat(context.getBeansOfType(OrderService.class)).hasSize(1);
            assertThat(context.getBeansOfType(BillingClient.class)).isEmpty();
        }
    }

    @Test
    void explicitPackagesIncludeExternalBillingClient() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(ExpandedScan.class)) {
            assertThat(context.getBeansOfType(OrderService.class)).hasSize(1);
            assertThat(context.getBeansOfType(BillingClient.class)).hasSize(1);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = OrderService.class)
    static class OrdersOnlyScan {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = {
        OrderService.class, BillingClient.class
    })
    static class ExpandedScan {
    }
}
```

Run:

```bash
mvn -q test
```

With the file structure shown and no interfering components added, **both tests must pass**. They do not depend on whether the application is currently using variant A, B, or C on its annotations because they define dedicated `@ComponentScan` settings on the two test configuration classes; the test also confirms that specifying `basePackageClasses` via a marker/class operates on **the package containing the class**, not just that individual class alone.

If you also want to verify Spring Boot auto-configuration and real injection, add an integration test with `@SpringBootTest` for the application; in multi-dependency modules, this helps catch errors from unintended scanned beans affecting back-off conditions.

## 9. Issues and how to diagnose them

### 9.1. `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`

For example, `OrderService`'s constructor requires `BillingClient`, yet `BillingClient` sits outside the scanned package. Spring tries to create `OrderService` and cannot find a `BillingClient` bean.

Troubleshooting steps:

1. Identify the **actual package** (`package ...;` declaration) of the root `@SpringBootApplication` class.
2. Identify the package of the missing class; check whether it falls under the scan tree.
3. Confirm whether the class carries a stereotype or is registered via `@Bean`/`@Import`. Merely having the dependency on the classpath is not enough.
4. Check whether any profile/condition/filter prevents registration (such as `@Profile`, `@Conditional`).
5. Check bean names/qualifiers and the multiple-beans-of-same-type case; "no bean" and "multiple bean candidates" are two distinct issues.

To inspect actual beans present:

```java
String[] names = context.getBeanNamesForType(BillingClient.class);
System.out.println(java.util.Arrays.toString(names));
```

This is a **snippet added inside main where `context` is available**, not a standalone program. If it prints `[]`, there is currently no bean of that type in the context being queried. If the Actuator endpoint `/actuator/beans` is enabled, it can help inspect the bean list; make sure to add the dependency, configure exposure, and secure access appropriately.

### 9.2. A component is loaded unexpectedly

Check whether the root package is placed **too high**, such as `dev.example`, causing classes in unintended modules to fall beneath the root. Check `@Import`, scanned `@Configuration` classes, or dependencies bringing their own auto-configuration. Do not immediately assume component scan is at fault.

### 9.3. Multiple beans of the same type or duplicate names

If a class is already scanned via `@Component` and you also declare an `@Bean` of the same type, you may end up with two beans and trigger `NoUniqueBeanDefinitionException` when injecting by type. If they share the same name, behavior depends on bean definition overriding policy, which you generally should not rely on.

`@Primary` or `@Qualifier` helps select a bean in some cases, yet does not fix the root cause of scanning too broadly; it is best to clarify bean ownership and registration.

### 9.4. Production works, but test slices fail

Test slices like `@WebMvcTest` restrict which beans are loaded. If a custom `@ComponentScan` on the application class drops Boot's default exclude filters, tests may pick up unwanted services or repositories. Prefer a standard root application class and use `scanBasePackageClasses` when expanding packages; if you must place an explicit `@ComponentScan`, understand and configure the appropriate filters.

### 9.5. Changed component scan, yet JPA entities/repositories are still missing

Separate responsibilities: `@ComponentScan` does not govern `@EntityScan` and `@EnableJpaRepositories`. Inspect the placement of the `@SpringBootApplication` class, JPA/Spring Data default packages, and specialized scan configurations. Do not solve entity/repository issues by widening component scanning across the entire classpath.

## 10. Practices for organizing application configuration

A maintainable package layout:

```text
com.acme.sales
├── SalesApplication.java
├── orders
│   ├── OrderService.java
│   ├── OrderController.java
│   └── OrdersConfiguration.java
├── customers
│   ├── CustomerService.java
│   └── CustomersConfiguration.java
└── infrastructure
    └── SecurityConfiguration.java

com.acme.shared.logging
└── SharedLoggingAutoConfiguration.java
```

Design tips:

- Keep the `@SpringBootApplication` class at the **application root package** so default scanning covers all application-owned code.
- Organize by feature or module boundary; use packages as architectural documentation and as a way to express ownership scope.
- For configurations belonging to external libraries, prefer importing **specific configuration classes** or using the library's auto-configuration mechanism rather than scanning the dependency's entire package.
- Avoid `@ComponentScan("com")`, `@ComponentScan("org")`, or overly broad root packages: this reduces predictability and increases bean conflicts, scan time, and coupling between modules.
- If multiple contexts exist, such as parent/child contexts in a complex system, check which context each component actually belongs to; package scanning does not replace context boundaries.
- Separate optional configurations (profiles, properties, dependencies) and apply conditions where appropriate; a scanned class does not guarantee every `@Bean` inside it will be registered if conditions apply.

## 11. Self-check questions

1. `App` is in `com.demo.a`, and `@Service` is in `com.demo.ab`. Will default scanning find the service? **No**; the two packages are siblings, even though their string names share a prefix.
2. `App` is in `com.demo`, and the service is in `com.demo.orders.internal`. Will it be scanned? **Yes**, provided no filter/condition excludes it and the class is a component candidate.
3. A class in a dependency has `@Component` and sits outside the scanned package. Does adding the dependency alone create the bean? **No** via component scan; another registration mechanism such as auto-configuration or `@Import` may exist.
4. When declaring `@SpringBootApplication(scanBasePackageClasses = PartnerMarker.class)`, are services in `App`'s package guaranteed to still be scanned? **No**, unless that package falls within the scan tree rooted at `PartnerMarker`. You must also list the root you want to keep.
5. Are `@Entity` and `JpaRepository` automatically discovered by expanding `scanBasePackages`? **You cannot conclude that**; JPA and Spring Data have their own scanning mechanisms.
6. Will an auto-configuration with `@ConditionalOnMissingBean(X.class)` back off when component scanning has registered an application bean `X`? **Usually yes**, if the corresponding bean definition has already been processed and the condition checks the matching type/name/context.
7. You need a single configuration in a package outside the root; which explicit option avoids unnecessary scanning? **`@Import` the specific configuration**, provided you understand the beans it registers.
8. Why can test slices break after adding an explicit `@ComponentScan`? **Boot's meta-annotation exclude filters may be lost**, causing non-slice components to be loaded.

## References

- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): how `@ComponentScan` discovers components, stereotypes, filters, and packages.
- [Spring Boot Reference — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): placement of `@SpringBootApplication` and default packages.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): auto-configuration and back-off conditions.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): `AutoConfiguration.imports` registration and why to avoid component scanning inside auto-configuration.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): context scoping and test slices.
