# Bean Naming Rules and Customizing `BeanNameGenerator` in Spring Core Container

## 1. Why Do Bean Names Matter?

A Spring IoC Container manages **bean definitions** identified by name. When writing `@Component`, `@Service`, `@Repository`, or specialized stereotypes, we can provide an explicit name or let Spring generate one automatically. Bean names appear in many operations:

- `applicationContext.getBean("orderService")`: lookup by name;
- `@Qualifier("orderService")`: can use the bean name as a default qualifier value when resolving dependencies;
- `@Resource(name = "...")`: a way to select dependencies by name in contexts supporting that annotation;
- `Map<String, T>` collections autowired by Spring: keys are typically bean names;
- observability/diagnostic systems, configuration, or integrations referencing beans by name.

For example, suppose these two components are scanned together:

```java
@Component
class InvoiceFormatter {
}

@Service("checkoutWorkflow")
class CheckoutService {
}
```

With the default naming strategy, the first bean typically gets the name `invoiceFormatter`; the second gets the name **`checkoutWorkflow`** because it was declared explicitly. This is an **illustrative snippet**, not a standalone runnable Java file.

Why learn `BeanNameGenerator`? In a large codebase, multiple packages may contain classes sharing the same **short name**: `com.acme.sales.ReportService` and `com.acme.audit.ReportService`. If both are discovered by component scanning and both receive the default name `reportService`, Spring risks reporting a bean definition conflict. You can assign explicit names on the stereotypes or use a naming strategy based on the fully qualified class name.

Lesson objectives:

1. Understand default naming rules, explicit names, JavaBeans decapitalization, and uppercase exceptions;
2. Understand the `BeanNameGenerator` interface alongside `AnnotationBeanNameGenerator` and `FullyQualifiedAnnotationBeanNameGenerator`;
3. Know how to configure `@ComponentScan(nameGenerator = ...)`, when it applies, and refactoring impacts;
4. Write a safe custom generator that prioritizes preserving explicitly declared names;
5. Recognize how component scan naming differs from `@Bean` and imported configurations;
6. Verify behavior with a runnable Java 17+ and Spring Framework 6 project.

## 2. How Does Spring Name Scanned Components?

When Spring scans a base package with `@ComponentScan`, the scanner finds candidate classes and registers bean definitions. At registration time, it needs a name for each definition. The default strategy of the **component scanner** is `org.springframework.context.annotation.AnnotationBeanNameGenerator`.

The logic can be understood in order:

1. The scanner discovers a component candidate with annotation metadata.
2. `AnnotationBeanNameGenerator` attempts to read an **explicitly declared name** from the appropriate stereotype.
3. If no explicit name exists, it generates a default name from the **short class name** according to JavaBeans rules.
4. The bean definition is registered under that name; if the name is already used by another incompatible definition, scanning may fail due to a conflict.

Diagram:

```text
Class discovered by @ComponentScan
                  |
                  v
        BeanNameGenerator
                  |
       +----------+-----------+
       |                      |
 @Component("explicit")      No explicit name
 / @Service("explicit")                  |
       |                                 v
       v                      Generate from class name
 "explicit"                   (default short name)
       |                                 |
       +--------------+------------------+
                      v
         Register bean definition
                      |
           Duplicate name, conflict?
             /               \
           Yes               No
           |                  |
     Registration error    Bean ready to resolve
```

A bean name is an **identifier in the registry**, not synonymous with a Java class name, package name, arbitrary qualifier, or dependency type. A bean can have multiple aliases, yet it still has only one primary bean name used during registration.

### 2.1. Default Name: JavaBeans `decapitalize`

For a class `com.acme.billing.InvoiceService`, Spring typically generates the name `invoiceService`: taking the **simple class name** and applying JavaBeans decapitalization rules.

| Scanned Class | Default Name with `AnnotationBeanNameGenerator` |
| --- | --- |
| `com.acme.billing.InvoiceService` | `invoiceService` |
| `com.acme.billing.MyJdbcDao` | `myJdbcDao` |
| `com.acme.api.UserController` | `userController` |
| `com.acme.util.URLFormatter` | `URLFormatter` |
| `com.acme.util.XMLParser` | `XMLParser` |

**Exception to remember:** `java.beans.Introspector.decapitalize` leaves the string unchanged if **both of the first two characters are uppercase**. Thus `URLFormatter` does not become `uRLFormatter`. This is why you should not implement default naming yourself via `Character.toLowerCase(name.charAt(0))`.

The following standalone Java snippet verifies the decapitalization rule used by Spring:

```java
import java.beans.Introspector;

public class BeanNameRuleDemo {
    public static void main(String[] args) {
        System.out.println(Introspector.decapitalize("InvoiceService"));
        System.out.println(Introspector.decapitalize("URLFormatter"));
        System.out.println(Introspector.decapitalize("XMLParser"));
    }
}
```

Save to `BeanNameRuleDemo.java` and run with JDK 17+:

```bash
javac BeanNameRuleDemo.java
java BeanNameRuleDemo
```

Stdout:

```text
invoiceService
URLFormatter
XMLParser
```

In this example, JavaBeans `Introspector` only illustrates the naming rule. Real component scanning also handles annotations, the registry, bean definitions, and class discovery conditions.

### 2.2. Explicitly Declared Names

Spring stereotypes support developer-specified names:

```java
@Component("auditWriter")
class AuditWriter {
}

@Service("paymentGateway")
class CardGateway {
}

@Repository("orderStorage")
class JpaOrderRepository {
}
```

This is **illustrative code**; when the classes reside in scanned packages, the registered names are `auditWriter`, `paymentGateway`, and `orderStorage` respectively. A name provided by the annotation takes priority over the generator's default name.

`@Component(value = "auditWriter")` and `@Component("auditWriter")` are equivalent. Specialized stereotypes such as `@Service` have an appropriate `value` attribute to declare the name.

When a bean needs to be looked up by name from code or external configuration, **an explicit name is a more stable contract than a class-derived name**. If class `CardGateway` is renamed to `StripeGateway`, the bean declared as `@Service("paymentGateway")` keeps the name `paymentGateway`. Conversely, the default name automatically changes from `cardGateway` to `stripeGateway`.

### 2.3. A Bean Name Is Not Automatically a Unique Qualifier

Suppose two beans implement `PaymentGateway`: one named `cardGateway` and one named `bankGateway`. A constructor requiring `PaymentGateway` **without a qualifier** can hit `NoUniqueBeanDefinitionException` if no winner is chosen by another rule.

`@Qualifier("cardGateway")` can usually select the matching bean because Spring treats the bean name as a fallback qualifier value where appropriate. However, when a business group has multiple beans sharing a qualifier, qualifiers do not have to match bean names and are not necessarily unique.

Do not use `BeanNameGenerator` as a substitute for disambiguation when a single dependency has multiple implementations. The generator solves **registry identity**; `@Qualifier`, `@Primary`, and autowiring rules solve **bean selection**.

## 3. Core `BeanNameGenerator` APIs

`org.springframework.beans.factory.support.BeanNameGenerator` is the name-generation strategy interface. Its core method:

```java
String generateBeanName(
        BeanDefinition definition,
        BeanDefinitionRegistry registry
);
```

This is a simplified API signature, requiring imports `BeanDefinition` and `BeanDefinitionRegistry` from `org.springframework.beans.factory.config` / `org.springframework.beans.factory.support`. An implementation receives the bean's metadata and the registry, and returns the **bean name** for the caller to register.

Three related APIs:

| API | Role | Characteristics |
| --- | --- | --- |
| `BeanNameGenerator` | Strategy interface | Allows implementing custom logic |
| `AnnotationBeanNameGenerator` | Default strategy for component scanning | Reads explicit stereotype names; falls back to JavaBeans short class name |
| `FullyQualifiedAnnotationBeanNameGenerator` | Built-in strategy | Keeps explicit stereotype names; falls back to fully qualified class name including package |

`AnnotationBeanNameGenerator` provides the protected method `buildDefaultBeanName(BeanDefinition)` so subclasses can customize how the **default name** is generated. This is the right extension point if you want to keep how Spring reads explicit stereotype names while changing the fallback format.

### 3.1. `AnnotationBeanNameGenerator`

With `@Component class LocalProcessor` in package `demo.catalog`, the default name is `localProcessor`. The same class name in `demo.billing` also becomes `localProcessor`. If both are scanned into **the same `BeanDefinitionRegistry`**, a conflict occurs unless names are differentiated.

It fits small projects or architectures with conventions ensuring component class names do not collide within the scan scope.

### 3.2. `FullyQualifiedAnnotationBeanNameGenerator`

The class `org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator` extends `AnnotationBeanNameGenerator` and changes the fallback to the **fully qualified class name**:

| Component | Default generator | Fully-qualified generator |
| --- | --- | --- |
| `demo.catalog.LocalProcessor` | `localProcessor` | `demo.catalog.LocalProcessor` |
| `demo.billing.LocalProcessor` | `localProcessor` | `demo.billing.LocalProcessor` |
| `demo.catalog.URLFormatter` | `URLFormatter` | `demo.catalog.URLFormatter` |
| `@Service("invoiceWorkflow") demo.catalog.InvoiceService` | `invoiceWorkflow` | `invoiceWorkflow` |

Names containing dots `.` are completely valid bean names. This is not a Java expression, and `context.getBean("demo.catalog.LocalProcessor")` works as a string lookup once the bean is registered under that name.

**Note:** `FullyQualifiedAnnotationBeanNameGenerator` still **respects explicitly declared names**. `@Service("invoiceWorkflow")` is not changed to `demo.catalog.InvoiceService`. If two classes in two packages both carry the explicit name `"invoiceWorkflow"`, switching to the fully-qualified generator **does not resolve the explicit name conflict**; the naming configuration must be fixed.

According to Spring Framework 6.2 Javadoc, **component scanning** uses `AnnotationBeanNameGenerator` by default, whereas **configuration-level imports** may use `FullyQualifiedAnnotationBeanNameGenerator` by default. That does not mean every bean in a Spring context gets a fully-qualified name.

### 3.3. When Should You Implement Your Own Generator?

A custom generator is appropriate when a codebase has a clear naming convention: for example, adding a `site_` prefix, adding domain namespaces, or deriving identifiers from metadata. However, the rule must be stable, easy to test, and not break intentionally configured bean names.

If the goal is simply to avoid short class name collisions across packages, **prefer the built-in fully-qualified strategy** before writing a custom generator. That avoids unnecessary infrastructure code.

## 4. Configuring a Generator for the Component Scanner

`@ComponentScan` provides the `nameGenerator` attribute accepting a class implementing `BeanNameGenerator`:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

@Configuration
@ComponentScan(
        basePackages = {"com.example.sales", "com.example.audit"},
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
public class AppConfig {
}
```

This is an **illustrative snippet** with hypothetical packages. When `AppConfig` is registered into the context, the scanner uses the specified generator to name components discovered by this scan pass.

You can also use a custom class:

```java
@Configuration
@ComponentScan(
        basePackages = "com.example.sales",
        nameGenerator = PrefixBeanNameGenerator.class
)
class PrefixedConfig {
}
```

This snippet only illustrates syntax; it requires an actual `PrefixBeanNameGenerator` class implementing `BeanNameGenerator`, having a no-arg constructor, and instantiable by Spring when processing the scan. A generator declared via annotation is **scanner configuration infrastructure**, not a business bean that has to be scanned by the component scanner.

**Scope of effect:** `nameGenerator` on a `@ComponentScan` affects component definitions **registered through that scan pass**. It does not by default rename beans created by `@Bean` methods, `@Import`, auto-configuration, or direct registration APIs. If multiple scan passes use different strategies, understand that they may write into the same registry and still produce name conflicts.

### 4.1. Programmatic Configuration via API

If constructing `AnnotationConfigApplicationContext` programmatically, you can configure the naming strategy on the context before registering configuration classes:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
context.setBeanNameGenerator(
        new FullyQualifiedAnnotationBeanNameGenerator());
context.register(AppConfig.class);
context.refresh();
try {
    // Use context...
} finally {
    context.close();
}
```

This is **illustrative code**; it requires imports and a real `AppConfig`. Set the generator **before** `register`/`scan` and `refresh` so bean definition registration uses the right strategy. Depending on the registration API and configuration level, a specific `@ComponentScan(nameGenerator = ...)` can pick its own generator for that scan pass, so when strict control is needed, establish a consistent policy across scan points.

### 4.2. Spring Boot

A typical Spring Boot application gets component scanning via `@SpringBootApplication`. You can configure a generator for the scanner by explicitly declaring `@ComponentScan`, but be careful: placing `@ComponentScan` directly alongside `@SpringBootApplication` adds to or alters how scanning works, and you must verify the default exclude filters that Boot provides through the composed annotation.

A less ambiguous direction is configuring the naming strategy via the context API or unified application infrastructure configuration, and **testing the final bean registry**. Within the scope of this lesson, the runnable program in section 7 uses plain Spring Context to accurately demonstrate `@ComponentScan` behavior.

## 5. Custom `BeanNameGenerator`: Adding a Prefix While Respecting Explicit Names

A concise and safe way is to extend `AnnotationBeanNameGenerator`, overriding only the default name generation logic:

```java
package demo.app;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.AnnotationBeanNameGenerator;

public class PrefixBeanNameGenerator extends AnnotationBeanNameGenerator {

    public PrefixBeanNameGenerator() {
    }

    @Override
    protected String buildDefaultBeanName(BeanDefinition definition) {
        return "site_" + super.buildDefaultBeanName(definition);
    }
}
```

This is a **complete** class, used directly in the sample project in section 7. `buildDefaultBeanName(...)` is only called when the generator finds no explicit stereotype name; therefore:

- `@Component class LocalProcessor` -> `site_localProcessor`;
- `@Component class URLFormatter` -> `site_URLFormatter`;
- `@Service("invoiceWorkflow") class InvoiceService` -> **`invoiceWorkflow`**, keeping the explicit name.

A prefix like `site_` is not enough to resolve collisions between **two classes with the same short name** in two packages. Both would still receive `site_localProcessor`. If the goal is to support `demo.catalog.LocalProcessor` and `demo.billing.LocalProcessor` simultaneously, choose the fully-qualified generator or include a package identifier in your naming policy.

### 5.1. Implementing the Interface from Scratch

You can implement `BeanNameGenerator` directly and access `definition.getBeanClassName()`, then build a name from the class name. However, that requires handling stereotype metadata, bean definitions without a direct class name, naming collisions, and special rules yourself. If you only want to change the format of **default names**, subclassing `AnnotationBeanNameGenerator` is usually less error-prone.

If you still choose to implement from scratch, verify:

1. Are unique names generated for all beans registered in the target registry?
2. How are explicit stereotype names and custom composed annotations prioritized?
3. When a bean definition uses a factory method or has an unresolved class name, how does the policy handle it?
4. When renaming packages/classes, how does the bean name contract change?
5. Do you need to consult `registry.containsBeanDefinition(name)` or have an explicit uniqueness strategy?

Do not silently append incrementing suffixes `1`, `2` based on scan order if bean names are a stable contract. When logical conflicts arise, fixing the naming convention is healthier.

## 6. Common Types of Bean Name Conflicts

### 6.1. Two Components with the Same Simple Class Name

`com.acme.sales.ReportService` and `com.acme.audit.ReportService` both have unnamed `@Service`:

```java
// File: com/acme/sales/ReportService.java
package com.acme.sales;
@Service
public class ReportService { }

// File: com/acme/audit/ReportService.java
package com.acme.audit;
@Service
public class ReportService { }
```

These two snippets are illustrative and require imports. The default generator names both `reportService`. When scanning both into one registry, Spring typically detects two incompatible bean definitions sharing a name and reports a registration error, commonly `ConflictingBeanDefinitionException`. Depending on registration source, overriding configuration, and processing stage, the exact error type can vary; do not rely on matching a single exact exception message.

How to handle it:

- assign distinct explicit names (`@Service("salesReportService")` and `@Service("auditReportService")`);
- or use `FullyQualifiedAnnotationBeanNameGenerator`;
- or adjust package structure/registration intentionally so only the right bean is registered.

### 6.2. Duplicate Explicit Names

`@Service("sharedService")` on two different classes is a conflict even with the fully-qualified generator, because explicit names are preserved. The solution is to assign distinct role-based names or avoid registering two incompatible beans simultaneously.

### 6.3. Two Beans with Different Names but the Same Type

Renaming allows **registering** both beans, yet a dependency of type `ReportService` or a shared interface can still be ambiguous during single-bean injection. In that case, `@Qualifier`, `@Primary`, collection injection, or a design adjustment is needed. Avoid confusing "bean name conflict" with "multiple candidates of the same type."

### 6.4. Duplicate Scanning and Other Registration Configurations

A class both scanned via component scanning and additionally created via `@Bean` can lead to duplicate beans by type, duplicate names, or overrides depending on registry policy. `BeanNameGenerator` on a scanner only handles names for **what the scanner registers**; it does not synchronize naming with `@Bean`/`@Import`.

### 6.5. Aliases and Primary Names

A bean can have **aliases** to reference the same instance under other names, but an alias does not turn the object into a new bean. For example, `@Bean({"primaryWriter", "writerAlias"})` creates a bean with primary name `primaryWriter` and alias `writerAlias` (when processed by appropriate annotation configuration). When injecting `Map<String, Writer>`, keys are typically primary bean names, rather than adding each alias as a separate map entry.

## 7. Runnable Java 17+ Project: Default, Fully Qualified, and Prefix

The project below uses **Spring Framework 6.2.18**, without Spring Boot. Three independent `AnnotationConfigApplicationContext` instances demonstrate:

1. Default single-package scan: produces short name `localProcessor`, preserves uppercase `URLFormatter`, and keeps explicit `invoiceWorkflow`.
2. Fully-qualified two-package scan: both `LocalProcessor` classes with the same short name are registered with **different fully-qualified names**.
3. Prefix generator: changes fallback to `site_*` while preserving explicit names.

### 7.1. Structure

```text
bean-name-generator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── demo/
        ├── app/
        │   ├── BeanNamingDemo.java
        │   └── PrefixBeanNameGenerator.java
        ├── catalog/
        │   ├── CatalogPackage.java
        │   ├── LocalProcessor.java
        │   ├── URLFormatter.java
        │   └── InvoiceService.java
        └── billing/
            ├── BillingPackage.java
            └── LocalProcessor.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'bean-name-generator-demo'
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
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.app.BeanNamingDemo'
}
```

### 7.2. Main and Scanner Configurations

File `src/main/java/demo/app/BeanNamingDemo.java`:

```java
package demo.app;

import demo.billing.BillingPackage;
import demo.catalog.CatalogPackage;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

public class BeanNamingDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            System.out.println("== DEFAULT ==");
            System.out.println("localProcessor = " +
                    context.containsBean("localProcessor"));
            System.out.println("URLFormatter = " +
                    context.containsBean("URLFormatter"));
            System.out.println("invoiceWorkflow = " +
                    context.containsBean("invoiceWorkflow"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(QualifiedConfig.class)) {
            System.out.println("== QUALIFIED ==");
            System.out.println("catalog = " +
                    context.containsBean("demo.catalog.LocalProcessor"));
            System.out.println("billing = " +
                    context.containsBean("demo.billing.LocalProcessor"));
            System.out.println("explicit = " +
                    context.containsBean("invoiceWorkflow"));
            System.out.println("shortName = " +
                    context.containsBean("localProcessor"));
        }

        try (var context =
                     new AnnotationConfigApplicationContext(PrefixConfig.class)) {
            System.out.println("== PREFIX ==");
            System.out.println("prefixed = " +
                    context.containsBean("site_localProcessor"));
            System.out.println("acronym = " +
                    context.containsBean("site_URLFormatter"));
            System.out.println("explicit = " +
                    context.containsBean("invoiceWorkflow"));
        }
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackageClasses = CatalogPackage.class)
class DefaultConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackageClasses = {CatalogPackage.class, BillingPackage.class},
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
class QualifiedConfig {
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
        basePackageClasses = CatalogPackage.class,
        nameGenerator = PrefixBeanNameGenerator.class
)
class PrefixConfig {
}
```

`DefaultConfig` only scans `demo.catalog`, so it does not encounter the short-name collision with `demo.billing.LocalProcessor`. `QualifiedConfig` scans both packages and uses fully-qualified names. `PrefixConfig` scans one package to demonstrate prefix behavior. The three separate contexts do not share a bean registry.

File `src/main/java/demo/app/PrefixBeanNameGenerator.java`:

```java
package demo.app;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.AnnotationBeanNameGenerator;

public class PrefixBeanNameGenerator extends AnnotationBeanNameGenerator {

    public PrefixBeanNameGenerator() {
    }

    @Override
    protected String buildDefaultBeanName(BeanDefinition definition) {
        return "site_" + super.buildDefaultBeanName(definition);
    }
}
```

The public no-arg constructor ensures the generator can be instantiated by Spring when reading `@ComponentScan`. The subclass only customizes the fallback name, while explicit name metadata is still handled by `AnnotationBeanNameGenerator`.

### 7.3. Marker Classes

File `src/main/java/demo/catalog/CatalogPackage.java`:

```java
package demo.catalog;

public final class CatalogPackage {
    private CatalogPackage() {
    }
}
```

File `src/main/java/demo/billing/BillingPackage.java`:

```java
package demo.billing;

public final class BillingPackage {
    private BillingPackage() {
    }
}
```

The markers carry no `@Component`, only identifying package roots via `basePackageClasses`.

### 7.4. Components in the catalog Package

File `src/main/java/demo/catalog/LocalProcessor.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Component;

@Component
public class LocalProcessor {
    public String id() {
        return "catalog";
    }
}
```

File `src/main/java/demo/catalog/URLFormatter.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Component;

@Component
public class URLFormatter {
    public String format(String value) {
        return "[" + value + "]";
    }
}
```

File `src/main/java/demo/catalog/InvoiceService.java`:

```java
package demo.catalog;

import org.springframework.stereotype.Service;

@Service("invoiceWorkflow")
public class InvoiceService {
    public String name() {
        return "invoice";
    }
}
```

Class `URLFormatter` intentionally starts with two uppercase letters to demonstrate the JavaBeans exception. `InvoiceService` specifies an explicit name to verify the generator does not overwrite declared names.

### 7.5. Component Sharing the Short Name in the billing Package

File `src/main/java/demo/billing/LocalProcessor.java`:

```java
package demo.billing;

import org.springframework.stereotype.Component;

@Component
public class LocalProcessor {
    public String id() {
        return "billing";
    }
}
```

The two classes `demo.catalog.LocalProcessor` and `demo.billing.LocalProcessor` share the same short class name but are **different Java types** because they are in different packages. Java allows both to coexist on the classpath. Short-name default bean naming is what causes the conflict when scanned together.

### 7.6. Run and stdout

Use JDK 17+ and a Gradle version compatible with that JDK:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `.\gradlew.bat run --quiet` on Windows PowerShell. Lines printed by the program:

```text
== DEFAULT ==
localProcessor = true
URLFormatter = true
invoiceWorkflow = true
== QUALIFIED ==
catalog = true
billing = true
explicit = true
shortName = false
== PREFIX ==
prefixed = true
acronym = true
explicit = true
```

**Analysis:**

- Default: `LocalProcessor` becomes `localProcessor`; `URLFormatter` keeps the name `URLFormatter`; `@Service("invoiceWorkflow")` keeps its explicit name.
- Qualified: both `LocalProcessor` classes get generated names `demo.catalog.LocalProcessor` and `demo.billing.LocalProcessor`, no longer competing for `localProcessor`. The explicit name `invoiceWorkflow` stays unchanged.
- Prefix: `LocalProcessor` becomes `site_localProcessor` and `URLFormatter` becomes `site_URLFormatter`; `InvoiceService` gets no prefix because it has an explicitly declared stereotype name.
- `containsBean(...)` checks for the presence of a bean name/alias in the context. This example uses names without declared aliases, so the results also prove the registered names.

**Limitation of the example:** the classes have no complex dependencies, keeping bean naming behavior isolated from autowiring concerns. The program uses no XML, web server, database, or other repositories.

## 8. Custom Stereotypes and `@AliasFor` Affecting Bean Names

A team wants to replace `@Service` with a custom `@UseCase` stereotype to express the use case role. A custom annotation can meta-annotate `@Component`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface UseCase {
    @AliasFor(annotation = Component.class, attribute = "value")
    String name() default "";
}
```

This is **illustrative content for `UseCase.java`**, not part of the runnable project in section 7. Usage:

```java
@UseCase(name = "fulfillOrder")
public class FulfillOrderUseCase {
}
```

When scanned, the explicit name is `fulfillOrder`. If `name` is omitted, the chosen strategy generates a fallback name just like other components.

Since Spring Framework 6.1, custom stereotypes that implicitly relied on a `value` attribute by convention without an explicit alias declaration have been deprecated. Using `@AliasFor(annotation = Component.class, attribute = "value")` lets custom annotations publish name metadata explicitly.

When using a custom generator extending `AnnotationBeanNameGenerator` as in section 5, explicit names from custom stereotypes with valid aliases continue to be respected. If writing a `BeanNameGenerator` from scratch, do not assume inspecting `definition.getBeanClassName()` alone will recognize all composed stereotypes and aliases.

## 9. `@Bean`, `@Import`, and Component Scan Have Different Rules

Key point: no single naming rule applies uniformly to every bean definition.

### 9.1. `@Bean` Methods

The default name of a bean created by a `@Bean` method is usually the **method name**:

```java
@Configuration
class InfraConfig {

    @Bean
    Clock systemClock() {
        return Clock.systemUTC();
    }

    @Bean("utcClock")
    Clock configuredClock() {
        return Clock.systemUTC();
    }
}
```

This is an **illustrative snippet**, requiring imports for `java.time.Clock` along with `@Configuration` and `@Bean`. The bean from the first method defaults to `systemClock`; the second method has the explicit name `utcClock`. Adding `FullyQualifiedAnnotationBeanNameGenerator` to `@ComponentScan` **does not automatically change** `systemClock` to a fully-qualified name.

### 9.2. `@Import` of Configuration Classes

Spring Framework 6.2 has cases where `FullyQualifiedAnnotationBeanNameGenerator` is used as the default for **configuration-level imports**. Thus a class imported via `@Import` may carry a different name from the same class discovered by the default scanner. Verify the actual registration path whenever code depends on bean names.

Avoid turning an import-generated bean name into a string contract when the framework provides type-based lookup APIs or when there is no need to target a specific name. When a configuration combines both scanning and imports, use `containsBean`/`getBeanDefinitionNames` to verify actual names in the context.

### 9.3. Direct Registration

APIs like `GenericApplicationContext.registerBean(...)` have their own naming strategies and overloads. If the caller provides a name, that name may have nothing to do with the scanner's `AnnotationBeanNameGenerator`. Do not expect changing one `@ComponentScan(nameGenerator = ...)` to change all bean names created across every extension point.

## 10. Changing Naming Policy in a Running System: Impacts to Know

Changing the naming generator from short class names to fully-qualified names is a **configuration interface change** whenever the application references names via strings. The following points may be affected:

| Component Using the Name | Example Before | Example After Switching to Fully-Qualified |
| --- | --- | --- |
| `getBean("localProcessor")` | Lookup succeeds | May not exist; needs `getBean("demo.catalog.LocalProcessor")` |
| `@Qualifier("localProcessor")` | Resolves via default name | May need an explicit qualifier on the bean or updated name |
| `@Resource(name="localProcessor")` | Selects bean by name | May fail if no matching alias remains |
| `Map<String, Processor>` | Key `localProcessor` | Key `demo.catalog.LocalProcessor` |
| Logging/monitoring identifying beans | `localProcessor` | `demo.catalog.LocalProcessor` |
| Explicit name `@Service("invoiceWorkflow")` | `invoiceWorkflow` | Preserved if generator respects stereotype names |

Changing the generator **does not automatically create aliases** for old names. If backward compatibility matters, clearly define which names are contracts; consider assigning explicit names to referenced beans, or registering aliases in a controlled manner rather than hoping Spring supports both default names.

Similarly, a prefix generator changes the names of unnamed components. A readable prefix can help logs or namespaces, but it should not be treated as a replacement for type/qualifier-based dependency injection.

## 11. Common Errors and How to Handle Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Two components in two packages cause `ConflictingBeanDefinitionException` | Same simple class name generating the same short name | Assign distinct explicit names or use the fully-qualified generator |
| `@Component("foo")` is still named `foo` after using fully-qualified | Explicit names take priority | This is intended behavior; change the annotation if you want to rename |
| Custom prefix fails to separate two `LocalProcessor` classes | Prefix produces identical `site_localProcessor` | Use a package-qualified policy or built-in FQ generator |
| `URLFormatter` becomes `URLFormatter` instead of `uRLFormatter` | JavaBeans rule preserves two leading uppercase characters | Check `Introspector.decapitalize`; do not manually lowercase one char |
| `@Bean` method name unchanged despite `@ComponentScan(nameGenerator=...)` | Generator only participates in component scan flow | Use `@Bean(name=...)` or an appropriate registration policy |
| `context.getBean("localProcessor")` no longer found | Switched to fully-qualified or prefixed name | Print actual bean names; update string references/aliases |
| `@Qualifier` starts failing after renaming | Qualifier relied on previous bean name | Use explicit qualifier annotations or synchronize references |
| Custom stereotype cannot use explicit name | Missing `@AliasFor` in composed annotation | Declare alias to `@Component.value` |
| Custom generator fails during instantiation | No-arg constructor unavailable, class unloadable, or exception thrown | Provide a public no-arg constructor; check classpath |
| Two beans have the same type despite different names | Autowiring conflict, not registry naming | Use `@Qualifier`/`@Primary` or collection injection |
| Widening scan causes conflicts | Now picking up additional components with the same short name | Compare packages/classes and review naming strategy |
| Naming beans by scan order | Registry may be processed in a changing order | Use deterministic rules that are tested and refactor-stable |
| Strange Spring Boot configuration results | Adding `@ComponentScan` altered roots/filters or another scan exists | Check `@SpringBootApplication` composition and final registry |

**Distinguish errors:** duplicate bean names are a registration issue; missing beans are a scanning/registration/condition issue; multiple beans of a type are a dependency resolution issue. The three error types require different remedies.

## 12. Inspecting Bean Names in Code Instead of Guessing

A simple inspection snippet in an application with an `ApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(MyService.class);
java.util.Arrays.sort(names);
System.out.println(java.util.Arrays.toString(names));
```

This is an **illustrative snippet**, requiring an actual `MyService` class and `context` variable. Sorting the array keeps output stable for comparison. If you just want to check a known bean name:

```java
boolean present = context.containsBean("demo.catalog.LocalProcessor");
```

When you need to know what aliases a bean has:

```java
String[] aliases = context.getAliases("invoiceWorkflow");
```

Verification tips:

1. **Distinguish contexts**: A bean in a child context is not automatically in every parent context. Debug the exact context performing injection/lookup.
2. **Verify the config actually in use**: `@ComponentScan` with `nameGenerator` must sit on a registered/imported configuration.
3. **Observe the registration path**: Was the bean scanned, created via `@Bean`, or registered via another API?
4. **Check explicit names too**: Names declared on stereotypes or custom annotations with aliases override fallback names in built-in generators.
5. **Check package roots**: The fully-qualified generator does not make the scanner scan wider; it only names components already discovered.
6. **Check dependency consumers**: Are there hardcoded `@Qualifier("...")` or string lookups depending on the previous name?

A unit/integration test creating an `AnnotationConfigApplicationContext` with a minimal scan configuration like section 7 is an effective verification method. When changing generators in an existing application, write dedicated tests for bean names considered stable contracts.

## 13. Practice Exercises

### Exercise 1 — Predicting Default Names

Given classes in package `com.acme.sales` carrying `@Component` without explicit names: `TaxService`, `XMLClient`, `ApiGateway`. Under `AnnotationBeanNameGenerator`, what are their names?

**Answer:** `taxService`, `XMLClient`, `apiGateway`. `XMLClient` keeps its leading letters unchanged because the first two characters are both uppercase.

### Exercise 2 — Conflict When Scanning Two Branches

Both `com.acme.billing.ReportHandler` and `com.acme.audit.ReportHandler` have unnamed `@Component`. What risk arises if the default scanner scans both?

**Answer:** both get named `reportHandler`; Spring can report a conflict when registering two incompatible bean definitions. Use `@Component("billingReportHandler")`/`@Component("auditReportHandler")` or `FullyQualifiedAnnotationBeanNameGenerator`.

### Exercise 3 — Changing a Bean Name Without Changing the Generator

A project uses `@Service class InvoiceService`, and another file looks up `"invoiceService"`. If you want to rename the class to `BillingService` without changing the lookup, how do you do it?

**Answer:** place `@Service("invoiceService")` on `BillingService` (if the old name still reflects the right business contract) or proactively update all call sites. Renaming the class alone changes the default name.

### Exercise 4 — Two Identical Explicit Names

Two classes in different packages both declare `@Component("sharedProcessor")`. Does switching to the fully-qualified generator resolve the conflict?

**Answer:** **No**. Built-in generators prioritize explicit names; at least one explicit name must be changed, or only the intended beans should be registered.

### Exercise 5 — Prefix Generator and Composed Stereotypes

Class `@UseCase(name="fulfillOrder") FulfillOrderUseCase` uses a custom stereotype with `@AliasFor`, and the scanner configures `PrefixBeanNameGenerator`. Which bean name is chosen?

**Answer:** `fulfillOrder`, because the explicit name is read before calling fallback `buildDefaultBeanName`. If `name` were omitted, the generator would use `site_fulfillOrderUseCase`.

### Exercise 6 — FQ Names Yet Autowiring Remains Ambiguous

Two classes implementing `Notifier` have distinct fully-qualified bean names. A constructor injects `Notifier notifier` and the container still throws `NoUniqueBeanDefinitionException`. Why?

**Answer:** registration names are distinct, yet there are still two candidates of the same type for a **single dependency**. Choose via `@Qualifier`, `@Primary`, or clearer dependency design.

### Exercise 7 — Changing a `@Bean` Method

A `@Configuration` has `@Bean Clock systemClock()`. Does configuring `@ComponentScan(nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class)` automatically rename the `systemClock` bean?

**Answer:** **No**. Bean factory methods have their own naming rules; to rename it, use `@Bean("newName")` and review references.

## 14. Checklist for Designing a Naming Policy

Before changing the generator on a project:

- Identify which bean names are referenced in `@Qualifier`, `@Resource`, `getBean(String)`, map keys, configuration, or integrations.
- Inventory which names rely on implicit class names versus explicit declarations.
- Identify the problem: short-name collisions across packages, namespace needs, or simply readability.
- Consider `FullyQualifiedAnnotationBeanNameGenerator` before writing a custom generator to solve short-name collisions.
- If writing a custom generator, ensure a no-arg constructor, deterministic naming, and tested behavior with explicit stereotype names.
- Check registration paths outside component scan: `@Bean`, `@Import`, and API registration.
- Use context tests/inspection to verify primary names, aliases, types, and injection outcomes before changing policy in a running application.

## 15. Key Takeaways

- **Default component scan:** `AnnotationBeanNameGenerator` generates JavaBeans short names when no explicit stereotype name is present.
- **Explicit names:** `@Component("x")`, `@Service("x")`, and composed stereotypes with `@AliasFor` normally keep name `x` even if you switch built-in generators.
- **Acronym class names:** `URLFormatter` stays `URLFormatter` under the default strategy, not `uRLFormatter`.
- **Package collisions:** two `LocalProcessor` classes in two packages both become `localProcessor` under the default generator; use explicit names or `FullyQualifiedAnnotationBeanNameGenerator`.
- **Custom generator:** extend `AnnotationBeanNameGenerator` and override `buildDefaultBeanName` if you only want to customize fallbacks.
- **Proper scope:** `@ComponentScan(nameGenerator=...)` does not alter all bean registration sources and does not widen package scanning.
- **Bean name differs from bean selection:** naming solves bean registry identity; qualifiers/primary/selection policies solve injection.

### Official Documentation

- [Spring Framework Reference — Classpath Scanning: Naming Autodetected Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html).
- [Spring Framework 6.2 Javadoc — `BeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `AnnotationBeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationBeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `FullyQualifiedAnnotationBeanNameGenerator`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/FullyQualifiedAnnotationBeanNameGenerator.html).
- [Spring Framework 6.2 Javadoc — `@ComponentScan`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ComponentScan.html).
- [Spring Framework — Bean Naming Conventions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html).
