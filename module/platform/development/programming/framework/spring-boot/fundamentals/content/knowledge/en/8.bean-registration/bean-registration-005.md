# `@ComponentScan` with Include Filters, Exclude Filters, and Scan Scope

In a Spring Boot application, classes can be annotated with `@Service`, `@Repository`, `@RestController`, or `@Component`, yet Spring only creates beans for them when **an appropriate bean registration mechanism** is present. One common mechanism is **component scanning**: Spring searches for candidate classes in specified packages and registers bean definitions for classes matching the rules.

The `@ComponentScan` annotation lets you control that search across three closely related aspects:

- **Scan scope**: Which packages does Spring search for components?
- **Include filters**: Beyond the default candidates, what additional class characteristics should Spring accept?
- **Exclude filters**: Which classes should be excluded from that scan?

This becomes an important problem as an application grows: a package contains multiple implementations, only certain adapters are allowed to run in a given environment, or the startup class was placed in the wrong package so beans go undiscovered. However, filters **only control a single component scan operation**; they do not automatically remove beans registered from other sources, nor do they replace Spring profiles, auto-configuration, or dependency management mechanisms.

## 1. Where Does Component Scanning Sit in Bean Registration?

Consider an application with the following components:

~~~text
HTTP request
     |
     v
OrderController
     |
     v
OrderService
     |
     v
OrderRepository
~~~

`OrderController` and `OrderService` must become Spring beans so the container can instantiate them and inject dependencies via constructors. One option is declaring every bean manually via `@Bean` methods, but for project-owned classes, Spring also supports component scanning.

Example:

~~~java
package com.example.store.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "READY";
    }
}
~~~

If a component scan covers `com.example.store.orders` and no exclusion rule applies, Spring can recognize `OrderService` as a candidate, register a bean definition, and instantiate it according to the container lifecycle.

Simplified flow:

~~~text
@ComponentScan configuration
          |
          v
Determine root packages to scan
          |
          v
Read metadata of discoverable classes
          |
          v
Apply default candidate rules,
include filters, and exclude filters
          |
          v
Register bean definitions
          |
          v
Spring container resolves dependencies
and creates beans per scope, conditions, lifecycle
~~~

Key distinction: **scanning and registering a bean definition** differs from **instantiating an object**. Spring generally registers definitions first, then creates instances according to scope and timing. A class passing a filter can still fail to instantiate if dependencies are missing or its constructor throws an error.

### Which Annotations Are Discovered by Default?

Spring component scanning detects classes with `@Component` or annotations based on `@Component` by default, including common stereotypes:

| Annotation | Common meaning |
|---|---|
| `@Component` | General Spring-managed component |
| `@Service` | Application or business logic component |
| `@Repository` | Data access component |
| `@Controller` | Spring MVC controller |
| `@RestController` | REST controller, combining controller semantics with response body writing |
| `@Configuration` | Configuration class containing bean definitions or Spring configuration |

For instance, `@RestController` is a specialization of `@Controller`; `@Controller` is a component stereotype. Therefore, controllers are normally discovered even without writing `@Component` directly on the class.

Discovery relies on class metadata and matching annotations. However, **having an annotation is not enough**: the class must lie inside the scan scope, not be excluded by filters, not be blocked by other registration conditions, and be valid for the container to process.

## 2. Where Does Spring Boot Scan Without an Explicit `@ComponentScan`?

A typical Spring Boot application:

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`@SpringBootApplication` is a composite annotation that includes convention-based component scanning and enables auto-configuration. With the layout above, default component scanning starts from package `com.example.store` and scans subpackages such as:

~~~text
com.example.store
├── StoreApplication.java
├── catalog/
│   ├── BookController.java
│   └── BookService.java
├── orders/
│   ├── OrderController.java
│   └── OrderService.java
└── payments/
    └── PaymentService.java
~~~

If classes in those subpackages carry appropriate stereotypes, they can be discovered without adding `@ComponentScan`.

Now consider a different layout:

~~~text
com.example.store
├── bootstrap/
│   └── StoreApplication.java
├── catalog/
│   └── BookService.java
└── orders/
    └── OrderService.java
~~~

Here `StoreApplication` belongs to `com.example.store.bootstrap`. By default convention, scanning starts from `bootstrap` and its subpackages; **it does not walk up to the parent package and scan sibling packages**. As a result, `BookService` and `OrderService` may not become beans.

There are two common solutions:

1. Place `StoreApplication` in the root package `com.example.store`.
2. Explicitly configure the component scan scope.

Unless there is a specific architectural reason, placing the startup class in a shared root package is usually simpler.

**Avoid placing the startup class in the default package** (without a `package` declaration). That can make the scan scope overly broad and produce hard-to-control behavior.

## 3. Specifying Scan Scope with `@ComponentScan`

The `@ComponentScan` annotation has several attributes. The two most important groups when designing scope are:

- `basePackages` or `value`: package names as strings.
- `basePackageClasses`: classes or interfaces used to specify root packages in a refactor-safe way.

### 3.1. Scanning by Package Name

For example, scanning components in two branches:

~~~java
package com.example.store;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@ComponentScan(basePackages = {
        "com.example.store.catalog",
        "com.example.store.orders"
})
public class StoreApplication {
    // main method as in the previous example
}
~~~

This component scan starts from the two declared packages and descends into their subpackages.

If `com.example.store.payments.PaymentService` exists outside those roots, it will not be discovered by this scan. However, a bean of the same type **can still come from elsewhere**, such as `@Bean`, `@Import`, or another scan configuration.

Using package name strings is easy to read, but when renaming or moving packages, IDEs may not update every string literal automatically. Be careful when refactoring.

### 3.2. Scanning with a Marker Class or Marker Interface

You can place an empty interface inside the package to scan:

~~~java
// com/example/store/catalog/CatalogPackage.java
package com.example.store.catalog;

public interface CatalogPackage {}
~~~

Then reference it via class literal:

~~~java
package com.example.store;

import com.example.store.catalog.CatalogPackage;
import com.example.store.orders.OrdersPackage;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@ComponentScan(basePackageClasses = {
        CatalogPackage.class,
        OrdersPackage.class
})
public class StoreApplication {
    // main method
}
~~~

`OrdersPackage` is likewise a marker defined in `com.example.store.orders`. A marker interface does not need to become a bean; it simply represents a **package location** so Spring knows where to scan.

This approach has two benefits: the compiler validates class references, and Java refactoring tools typically update imports and class references more reliably than package strings. Therefore, `basePackageClasses` is worth considering in projects with many business packages or modules.

### 3.3. Attributes on `@SpringBootApplication`

To change only the scan scope in a Spring Boot application, you can use its convenience attributes:

~~~java
package com.example.store.bootstrap;

import com.example.store.catalog.CatalogPackage;
import com.example.store.orders.OrdersPackage;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
        scanBasePackageClasses = {
                CatalogPackage.class,
                OrdersPackage.class
        }
)
public class StoreApplication {
    // ...
}
~~~

Or:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.store.catalog",
                "com.example.store.orders"
        }
)
public class StoreApplication {
    // ...
}
~~~

`scanBasePackages` and `scanBasePackageClasses` are convenience aliases for **component scan**. They do not automatically alter every other scanning mechanism in Spring Boot.

Specifically with JPA and Spring Data, **entity scanning** and **repository scanning** determine their packages through separate mechanisms. If an application moves entities or repositories outside the root package typically used by auto-configuration, `@EntityScan` or `@EnableJpaRepositories` may be needed. Do not assume that setting `scanBasePackages` covers all JPA scanning mechanisms.

### 3.4. Summary of Scan Scope Options

| Option | Meaning | When useful? |
|---|---|---|
| Omitted; use `@SpringBootApplication` default | Scans the application's package and subpackages | Projects with an appropriate root package |
| `@ComponentScan("...")` or `basePackages` | Scans packages by name | Explicitly defining multiple areas to scan |
| `basePackageClasses` | Scans packages containing the specified types | Avoiding hardcoded strings |
| `scanBasePackages` on `@SpringBootApplication` | Configures component scan from the startup annotation | Only needing to adjust Boot's scan scope |
| `@Import` or `@Bean` | Registers specific configurations or beans | Preferring explicit registration over scanning an entire package |

When neither `basePackages` nor `basePackageClasses` is specified, Spring normally uses the package of the class declaring `@ComponentScan` as the base.

**Note:** A `@ComponentScan` placed directly on the same class as `@SpringBootApplication` can override the component scan configuration inherited from its meta-annotation. Therefore, when adding `@ComponentScan` directly, specify the full scope and filters you intend. In addition, another configuration class may perform **its own separate scan**; this means filters configured on one scan do not necessarily exclude beans registered by another scan.

## 4. What Are Include Filters and Exclude Filters?

A component scan must decide which classes are **candidates**. By default, it already includes filters recognizing stereotypes such as `@Component` and `@Component`-based annotations.

Two attributes enable customization:

- `includeFilters`: adds or defines which kinds of classes are treated as candidates.
- `excludeFilters`: removes matching classes from that scan's results.

Alongside these two attributes, it is essential to understand `useDefaultFilters`:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        useDefaultFilters = true
)
~~~

`true` is the default value. With it, standard component stereotypes continue to be recognized. If you add an include filter while leaving `useDefaultFilters = true`, the result may be broader than expected: **`@Component`, `@Service`, `@Repository`, and `@Controller` classes are still scanned** even if they do not match your extra include filter.

Conversely:

~~~java
@ComponentScan(
        basePackages = "com.example.store.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

This scan disables the default component recognition filters; it accepts only classes matching the specified include filter (and not excluded by an exclude filter). `Extension` in this example is a project-defined annotation.

Remember to import `org.springframework.context.annotation.FilterType` when using `FilterType.ANNOTATION`, `FilterType.ASSIGNABLE_TYPE`, etc.

### Mental Model for Evaluating One Component Scan

You can visualize candidate evaluation as:

~~~text
Classes in the scanned packages
                  |
                  v
   Candidate via default filters
       or via include filter?
                  |
            Yes   |   No
                  |      └── Skip
                  v
       Matches exclude filter?
             |        |
            Yes       No
             |        |
           Skip       v
                Eligible to register bean definition
                (subject to conditions and further steps)
~~~

This is a mental model for reading configuration, not exact pseudocode of every internal scanner step. Two practical takeaways are crucial:

1. **Include filters are not an exclusive allowlist** unless you set `useDefaultFilters` appropriately.
2. **Exclude filters can drop a class from a scan even if it matches an include filter.**

## 5. Common `FilterType` Options

`@ComponentScan.Filter` has a `type` attribute specifying how candidates are matched.

| `FilterType` | How it matches | Use case |
|---|---|---|
| `ANNOTATION` | Class has the specified annotation per Spring's annotation matching | Finding only classes with a custom annotation or excluding by annotation |
| `ASSIGNABLE_TYPE` | Class is of the specified type or has a matching inheritance/implementation relationship | Finding implementations of an interface |
| `REGEX` | Fully qualified class name matches a regular expression | Excluding a class name family or classes following a naming convention |
| `ASPECTJ` | Name/type matches a pattern using AspectJ syntax | Complex selection rules, requiring appropriate supporting libraries |
| `CUSTOM` | Invokes an application-supplied `TypeFilter` | Needing to inspect metadata and apply custom logic |

Inside the annotation:

- For `ANNOTATION` and `ASSIGNABLE_TYPE`, typically use the `classes` attribute.
- For `REGEX` or `ASPECTJ`, use the `pattern` attribute.
- For `CUSTOM`, `classes` points to your `TypeFilter` implementation.

You can provide multiple filters in `includeFilters` or `excludeFilters`. They let you express multiple matching paths, but **filters do not create separate package boundaries**: the scanner still only inspects the configured base packages.

## 6. Include Filter Example: Selecting Only Components with a Custom Annotation

Suppose an application supports extensions for exporting reports. You do not want every class in the `extensions` package to become a bean; only classes marked `@ReportExtension` should be picked up.

Example structure:

~~~text
com.example.report
├── ReportApplication.java
└── extensions
    ├── ReportExtension.java
    ├── CsvExporter.java
    ├── PdfExporter.java
    └── ExperimentHelper.java
~~~

### 6.1. Define the Marker Annotation

File `ReportExtension.java`:

~~~java
package com.example.report.extensions;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ReportExtension {}
~~~

`@ReportExtension` **does not need `@Component`** in this example. It serves as a marker for the include filter to recognize. Only when a scan configuration with a matching filter runs are classes bearing this annotation selected in the example.

### 6.2. Write the Extension Classes

~~~java
package com.example.report.extensions;

@ReportExtension
public class CsvExporter {
    public String format() {
        return "csv";
    }
}
~~~

~~~java
package com.example.report.extensions;

@ReportExtension
public class PdfExporter {
    public String format() {
        return "pdf";
    }
}
~~~

~~~java
package com.example.report.extensions;

public class ExperimentHelper {
    // Not marked as an extension yet.
}
~~~

### 6.3. Configure the Scan to Accept Only `@ReportExtension`

Example placing `@ComponentScan` directly on the startup class to show the application's scanning choice clearly:

~~~java
package com.example.report;

import com.example.report.extensions.ReportExtension;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.report.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ReportExtension.class
        )
)
public class ReportApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportApplication.class, args);
    }
}
~~~

Within the area scanned by this configuration, `CsvExporter` and `PdfExporter` match the marker and become bean candidates; `ExperimentHelper` does not match and is not registered by this scan.

Important: this configuration intentionally **disabled default filters**. If you add an ordinary `@RestController` in the `extensions` package without `@ReportExtension`, that controller will not be picked up by this scan either. If main controllers and services live outside `extensions`, the application must register them through another mechanism. This example illustrates a **selective scan region**, not a general configuration to apply to every project.

To extend an application that already has default scanning while selectively scanning a separate plugin package, place the plugin package **outside the default scan scope**, then import a `@Configuration` class containing its own `@ComponentScan`. If the plugin sits under the default scope of another scan, that scan may already register beans you did not intend to include. Plan package placement and coordinating scans clearly.

### What Happens If You Forget `useDefaultFilters = false`?

Suppose `ExperimentHelper` is annotated with `@Component`, while the configuration still states:

~~~java
@ComponentScan(
        basePackages = "com.example.report.extensions",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ReportExtension.class
        )
)
~~~

Because `useDefaultFilters` defaults to `true`, `ExperimentHelper` carrying `@Component` still qualifies as a candidate, even though it lacks `@ReportExtension`.

Hence, **include filters add candidates** to the default configuration; if the requirement is "only register classes with the marker", configure `useDefaultFilters = false` accordingly.

## 7. Include Filter by Interface with `ASSIGNABLE_TYPE`

In a system with multiple plugins sharing a contract, you can discover implementations of an interface.

~~~java
package com.example.report.spi;

public interface ReportExporter {
    String format();
}
~~~

Implementation classes:

~~~java
package com.example.report.plugins;

import com.example.report.spi.ReportExporter;

public class CsvReportExporter implements ReportExporter {
    @Override
    public String format() {
        return "csv";
    }
}
~~~

~~~java
package com.example.report.plugins;

import com.example.report.spi.ReportExporter;

public class PdfReportExporter implements ReportExporter {
    @Override
    public String format() {
        return "pdf";
    }
}
~~~

Configuration:

~~~java
package com.example.report;

import com.example.report.spi.ReportExporter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;

@Configuration
@ComponentScan(
        basePackages = "com.example.report.plugins",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = ReportExporter.class
        )
)
public class ExporterScanConfiguration {}
~~~

If `ExporterScanConfiguration` is imported or registered appropriately by the application, this scan can pick up classes implementing `ReportExporter` in the `plugins` package. `@Component` on each exporter is no longer required for this example's filter.

Understand a limitation: type-based filters can collect **multiple implementations**. If a service injects a single `ReportExporter` and two beans exist, Spring may fail unable to choose one. When designing for multiple plugins, use `List<ReportExporter>`, `Map<String, ReportExporter>`, `@Qualifier`, or an appropriate selection mechanism.

Additionally, an interface or abstract class can satisfy a type relationship without necessarily being an instantiable bean. The scanner also applies valid-candidate rules; a filter does not turn an interface into a runnable instance.

## 8. Exclude Filter Example: Dropping a Class by Annotation

Another scenario: you want to scan almost an entire module while excluding components marked with `@LegacyComponent`.

Define the marker:

~~~java
package com.example.store.shared;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface LegacyComponent {}
~~~

Usage:

~~~java
package com.example.store.pricing;

import com.example.store.shared.LegacyComponent;
import org.springframework.stereotype.Service;

@LegacyComponent
@Service
public class OldDiscountCalculator {
    // Legacy algorithm not intended to be activated via component scan.
}
~~~

Scan configuration:

~~~java
package com.example.store;

import com.example.store.shared.LegacyComponent;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = LegacyComponent.class
        )
)
public class StoreApplication {
    // ...
}
~~~

In this scan, `OldDiscountCalculator` lies within the scan scope and has the `@Service` stereotype, yet it matches the exclude filter and is not registered by this component scan.

This can be helpful when migrating from an old implementation to a new one. However, if another service still injects `OldDiscountCalculator` directly or injects an interface only implemented by this class, excluding it can prevent the application from starting due to a missing bean. Filters change the **bean graph**, so account for existing dependencies.

### Exclude Filter by Specific Type

If you only want to exclude one class:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = OldDiscountCalculator.class
        )
)
~~~

`ASSIGNABLE_TYPE` can also match assignable subtypes/implementations, so it is not strictly a narrow single-class name match. If you need a very specific condition, evaluate the appropriate filter type and actual inheritance hierarchy.

### Excluding by Package Using `REGEX`

Because `@ComponentScan` has no dedicated attribute meaning "exclude this entire subpackage" by standalone package name, you can use a regex against the **fully qualified class name**:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com[.]example[.]store[.]legacy[.].*"
        )
)
~~~

This pattern targets classes whose fully qualified name starts with `com.example.store.legacy.`, such as `com.example.store.legacy.LegacyPricingService`.

Using `[.]` instead of an unescaped dot clearly represents a literal dot in regex. If using `\\.` inside a Java string, keep regex escaping distinct from Java string escaping.

Keep three points in mind:

- The regex applies to the **Java type name** inspected by the scanner, not URLs, file paths, or arbitrary package strings.
- Subpackages such as `legacy.extra` will also match the pattern.
- If a `@Configuration` inside an excluded package is imported directly, or a bean is created by `@Bean` in an already-registered configuration, a component scan filter does not guarantee those beans disappear from the context.

### When to Use `@Profile` Instead of an Exclude Filter?

If the goal is "only activate this bean when running in the dev environment", Spring profiles usually express that intent more clearly:

~~~java
@Service
@Profile("dev")
public class DebugOnlyService {
    // ...
}
~~~

Exclude filters are better suited when you want a **scanning rule** to omit a group of classes by type, annotation, or package naming convention. Both mechanisms can coexist, solving different problems:

- `@Profile`: conditional registration by environment.
- `@ComponentScan.excludeFilters`: omitting candidates from a single scan.

## 9. Custom `TypeFilter` When Rules Go Beyond Annotations or Regex

Spring allows custom filters by implementing `org.springframework.core.type.filter.TypeFilter`. This is useful when decisions rely on class metadata that built-in filters cannot easily express.

Illustrative example: exclude every class whose name ends with `InternalAdapter` in a scanned package.

~~~java
package com.example.store.scanning;

import java.io.IOException;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.MetadataReaderFactory;
import org.springframework.core.type.filter.TypeFilter;

public class InternalAdapterFilter implements TypeFilter {

    @Override
    public boolean match(
            MetadataReader metadataReader,
            MetadataReaderFactory metadataReaderFactory
    ) throws IOException {
        String className =
                metadataReader.getClassMetadata().getClassName();
        return className.endsWith("InternalAdapter");
    }
}
~~~

Using the filter:

~~~java
package com.example.store;

import com.example.store.scanning.InternalAdapterFilter;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.CUSTOM,
                classes = InternalAdapterFilter.class
        )
)
public class StoreApplication {
    // ...
}
~~~

`TypeFilter` receives metadata from `MetadataReader`, allowing decisions without instantiating candidate classes. This matters because component scanning is an analysis and registration phase, before all beans are instantiated.

Custom filters are powerful, yet they can easily become hard to read, hard to maintain, and add scanning overhead. If a marker annotation or clean package boundary solves the requirement, prefer the simpler mechanism.

## 10. Combining Include, Exclude, and Scan Scope

Suppose a project has a document export module:

~~~text
com.example.docs
├── DocsApplication.java
├── exports
│   ├── CsvExporter.java       @ExportPlugin
│   ├── PdfExporter.java       @ExportPlugin
│   ├── OldXmlExporter.java    @ExportPlugin @Deprecated
│   └── ExportMetrics.java     @Component
└── orders
    └── OrderService.java      @Service
~~~

You want one scan to find exporters marked `@ExportPlugin` in `exports`, ignore other components there, and exclude old exporters marked `@Deprecated`.

You can configure it conceptually as:

~~~java
@ComponentScan(
        basePackages = "com.example.docs.exports",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ExportPlugin.class
        ),
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Deprecated.class
        )
)
~~~

Assuming `@ExportPlugin` is a valid marker annotation and the classes are valid bean-creation candidates, the expected result of **this scan** is:

| Class | In scanned package? | Matches include? | Matches exclude? | Result |
|---|---|---|---|---|
| `CsvExporter` | Yes | Yes | No | Selected |
| `PdfExporter` | Yes | Yes | No | Selected |
| `OldXmlExporter` | Yes | Yes | Yes | Excluded |
| `ExportMetrics` | Yes | No | No | Excluded because default filters are off |
| `OrderService` | No | Not evaluated | Not evaluated | Outside scan scope |

This table describes only **a single component scan**. If `DocsApplication` simultaneously runs a default scan covering all of `com.example.docs` from another configuration, classes excluded from the selective scan may still be registered by the other scan. Therefore, it is important to control both **package boundaries** and **all bean registration sources** when designing a strict scanning policy.

### Why Can Combining Multiple Scans Be Surprising?

Distinguish between:

~~~text
Scan A: com.example.docs (default filters)
Scan B: com.example.docs.exports
        (include @ExportPlugin, exclude @Deprecated)
~~~

`OldXmlExporter` may be excluded by Scan B yet still discovered by Scan A if it carries `@Component` or a matching stereotype. Do not assume Scan B's exclude filter acts as an ApplicationContext-wide ban.

Conversely, if no other scan covers `exports` and Scan B is the sole registration source for that package, the filters cleanly govern the candidates in that area.

When `@ComponentScan` is declared directly on a class carrying `@SpringBootApplication`, the local configuration typically takes precedence over the component scan supplied by `@SpringBootApplication`'s meta-annotation. Still, `@Import` or other `@Configuration` classes can also participate in registering beans. Understand **the entire context configuration** rather than looking at a single annotation in isolation.

## 11. Distinguishing `@ComponentScan`'s `excludeFilters` from Spring Boot's `exclude`

Two syntaxes look similar yet serve different purposes.

**Excluding a component from a scan:**

~~~java
@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = OldOrderService.class
        )
)
public class StoreApplication {}
~~~

**Excluding an auto-configuration class from Spring Boot auto-configuration:**

~~~java
@SpringBootApplication(
        exclude = {
                SomeAutoConfiguration.class
        }
)
public class StoreApplication {}
~~~

`SomeAutoConfiguration` in the second example is merely an illustrative name for an actual auto-configuration class excluded under Spring Boot's mechanism, not an arbitrary application class.

| Mechanism | Primary effect |
|---|---|
| `@ComponentScan.excludeFilters` | Excludes candidates from packages being component-scanned |
| `@SpringBootApplication(exclude = ...)` | Excludes an auto-configuration belonging to Boot's mechanism |
| `@Profile`, `@Conditional...` | Conditions controlling whether a bean/configuration is applied |
| `@Import` | Registers configurations or components explicitly |
| `@Bean` | Registers beans via factory methods |

For instance, if Boot registers a `DataSource` via auto-configuration, an exclude filter targeting a repository's package name will not exclude the `DataSource`. Likewise, if a class has no `@Component` and is registered via `@Bean`, an exclude filter will not simply "delete" that bean.

## 12. Component Scan Scope and Bean Scope Are Two Different Meanings of "Scope"

In this lesson, **scan scope** refers to the package tree where the scanner looks for classes. Spring also has **bean scope**, such as `singleton`, `prototype`, and `request`.

They are not synonymous:

| Concept | Question | Example |
|---|---|---|
| Component scan scope | Which packages are inspected for bean registration? | `com.example.store.orders` |
| Bean scope | Under what lifecycle scope are bean instances created and reused? | `singleton` or `prototype` |

Example:

~~~java
package com.example.store.orders;

import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class OrderDraftBuilder {
    // ...
}
~~~

If `OrderDraftBuilder` lies outside the component scan scope or is dropped by an exclude filter, `@Scope("prototype")` **will not make it appear automatically**. Conversely, if the bean is registered, its scope affects how the container creates and supplies instances, without changing which packages Spring scans.

In special cases, `@ComponentScan` also offers `scopeResolver` and `scopedProxy` for determining scope/proxy behavior of scanned beans. That is a separate configuration group from `basePackages`, `includeFilters`, and `excludeFilters` covered here.

## 13. Component Scan in Multi-Module Projects

In a multi-module Maven/Gradle Spring Boot application, component scan can only see classes **present on the classpath**. Declaring a package to scan is not enough if the module containing that package is missing from the application's runtime dependencies.

Suppose:

~~~text
store-parent/
├── store-app/
│   └── src/main/java/com/example/store/StoreApplication.java
├── store-catalog/
│   └── src/main/java/com/example/catalog/CatalogService.java
└── store-orders/
    └── src/main/java/com/example/orders/OrderService.java
~~~

If `store-app` depends on `store-catalog` and `store-orders` at runtime, you can specify:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.store",
                "com.example.catalog",
                "com.example.orders"
        }
)
public class StoreApplication {
    // ...
}
~~~

Or reference marker classes in each module:

~~~java
@SpringBootApplication(
        scanBasePackageClasses = {
                StoreApplication.class,
                CatalogPackage.class,
                OrdersPackage.class
        }
)
public class StoreApplication {
    // ...
}
~~~

Using marker classes reduces reliance on package name strings and clarifies which modules are wired at the composition root.

Keep in mind:

- Component scan does not automatically load a module absent from the runtime classpath.
- Spring Data repositories and JPA entities may need separate scan scopes depending on package placement and configuration.
- If a module only intends to expose a few beans, consider `@Configuration` + `@Import`, conditional configuration, or an explicit registration model instead of scanning everything.
- Scanning many packages together can produce two implementations of the same type or unintended beans, causing injection or configuration errors.

When scaling to a plugin system, simple classpath scanning may not suffice. Plugins might be loaded dynamically via separate classloaders or have complex lifecycles; those mechanisms require dedicated design beyond basic `@ComponentScan`.

## 14. Common Problem: Bean Not Discovered

Example:

~~~text
com.acme.app
├── boot
│   └── Application.java
└── payment
    └── PaymentService.java  @Service
~~~

If `Application` sits in `com.acme.app.boot` without expanding scan scope, `PaymentService` may not be registered. The injection error typically looks like:

~~~text
No qualifying bean of type 'com.acme.app.payment.PaymentService'
available
~~~

This is a **no qualifying bean** error, with several potential causes:

1. The class lacks a stereotype annotation and is not registered via `@Bean`.
2. The class lies outside the effective component scan scope.
3. `useDefaultFilters = false` prevented standard annotations from being picked up.
4. An include or exclude filter prevented the class from becoming a candidate.
5. `@Profile`, `@Conditional`, or another configuration prevented registration.
6. The class or module is absent from the runtime classpath.
7. The bean was created, but the requested injection type is incompatible; or a test context differs from the full application context.

Do not fix this by immediately widening the scan to an overly broad package. Identify the class needing registration, its intended registration source, and the actual scope in effect.

### Another Example: Bean Registered Multiple Times

Suppose:

~~~java
@Service
public class RemoteCustomerService implements CustomerService {
    // ...
}
~~~

Alongside a configuration:

~~~java
@Configuration
public class CustomerConfiguration {

    @Bean
    public CustomerService customerService() {
        return new RemoteCustomerService();
    }
}
~~~

Component scan may find `RemoteCustomerService`; the `@Bean` method also registers a separate `CustomerService` bean. When injecting the `CustomerService` interface without clear selection rules, the container encounters multiple candidates.

This is not merely an include-filter bug: it results from **multiple bean registration sources**. Pick one registration mechanism, or use `@Qualifier`/`@Primary` when multiple implementations are genuinely intended.

## 15. Debugging Scan Scope and Filters

When seeing `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, or an "unexpected" bean appearing, diagnose in sequence.

### Step 1: Identify the Startup Class and Root Package

Locate `@SpringBootApplication`, its package, and any `scanBasePackages`/`scanBasePackageClasses` attributes. Check whether the project declares `@ComponentScan` directly or through imported configurations.

First question: **Was Spring instructed to look inside the package containing the needed bean?**

### Step 2: Identify All Potentially Active Scans

Look for `@ComponentScan` in registered `@Configuration` classes and watch for library-supplied configurations. A bean can arrive via another scan, so one scan's filters are not enough to guarantee a bean's absence.

### Step 3: Check `useDefaultFilters`

This is a common source of confusion:

~~~java
@ComponentScan(
        basePackages = "com.example.extensions",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

Since `useDefaultFilters` defaults to `true`, a `@Service` class in this package can still be scanned even without `@Extension`.

If the intent is selecting extensions only, consider:

~~~java
@ComponentScan(
        basePackages = "com.example.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

Disabling default filters alters the entire candidate set and can cause normally scanned configurations to disappear; plan the scan scope and dependent beans carefully.

### Step 4: Verify Exclude Filters and Conditions

Check annotation, assignable-type, regex, and custom type filters. Next, inspect profiles and bean conditions. In Spring Boot, the auto-configuration conditions report helps explain why certain configurations applied or were skipped, but it **does not replace checking component scan** for application classes.

### Step 5: Check Actual Beans in `ApplicationContext`

You can inspect beans by type or name, e.g., in diagnostic code:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentService.class);

for (String name : names) {
    System.out.println(name);
}
~~~

`applicationContext` is a reference to Spring's `ApplicationContext` obtained via constructor injection or another appropriate source. This illustrates how to query beans; in real applications, choose appropriate logging/observability mechanisms.

If Actuator is integrated and management endpoints are exposed according to your security policy, bean information can aid diagnostics. Do not publicly expose configuration or internal bean details just to debug in production.

### Step 6: Check Dependencies and Bean Validity

A class discovered by the scanner can still fail when the container tries to instantiate it. Errors then shift from "bean not found" to constructor, missing-dependency, classpath, factory-method, or database errors.

Distinguish among:

- **No bean definition**: the class was not registered (or a condition did not match).
- **Bean definition exists, but instantiation failed**: the container knows the bean, yet cannot build the object graph.
- **Multiple candidate beans**: the injection point is ambiguous and needs a selection rule.
- **Bean exists, wrong behavior**: the bug may lie in business logic or implementation selection, not just scanning.

## 16. Are Filters Always the Right Tool?

Not every need to include only part of a codebase requires include/exclude filters. Your choice should match the underlying cause.

| Goal | Usually appropriate tool |
|---|---|
| All components in business packages should be scanned | `@SpringBootApplication` default or `scanBasePackageClasses` |
| Accept only marker-annotated classes in an extension package | `includeFilters` with `useDefaultFilters = false` |
| Skip a group of components within the same scan | `excludeFilters` |
| Choose dev/prod implementation | `@Profile` or matching bean conditions |
| Create bean only when a property is enabled | `@ConditionalOnProperty` on configuration/bean |
| Provide an external library object | `@Bean` in `@Configuration` |
| Explicitly enable a module or configuration | `@Import` or modular configuration |
| Disable a Spring Boot auto-configuration | Auto-configuration exclusion, not a component scan filter |
| Bean has multiple implementations, need one | `@Qualifier`, `@Primary`, or suitable injection design |

Mechanisms can be combined, with each controlling a distinct layer: **finding candidates**, **conditional registration**, **selecting candidates on injection**, or **framework auto-configuration**.

For small apps with single implementations and clean root packages, relying on default Spring Boot component scanning is usually simplest. Filters shine when you genuinely need to pick a specific class group or omit a group from scanning.

## 17. Self-Practice Exercise: Scanning Adapters on Demand

Suppose an order-processing application has this layout:

~~~text
com.example.orders
├── OrdersApplication.java
├── api/
│   └── OrderController.java           @RestController
├── service/
│   └── OrderService.java              @Service
└── adapters/
    ├── EmailNotifier.java            @NotificationAdapter
    ├── SmsNotifier.java              @NotificationAdapter
    ├── OldFaxNotifier.java           @NotificationAdapter @Deprecated
    └── DebugHelper.java               @Component
~~~

Requirements:

1. The application's controller and service must still be registered normally.
2. Within `adapters`, only classes annotated with `@NotificationAdapter` should be scanned.
3. `OldFaxNotifier` must not be picked up by the adapter scan.
4. Do not create two beans sharing an interface and then inject a single one without a selection rule.

One possible design:

- Place the selectively scanned adapters in a package **not covered by another default scan**.
- Use a dedicated `@ComponentScan` configuration for the adapter package with `useDefaultFilters = false`, including `@NotificationAdapter` and excluding `@Deprecated`.
- Register the adapter scan configuration explicitly, e.g., via `@Import`.
- Keep default component scanning for regular application packages.
- If multiple notifiers are needed simultaneously, inject a collection; if only one is needed, define an explicit selection via configuration or qualifier.

This exercise shows why you must design **scope** before writing filters: if `adapters` already sits under a default scan covering all of `com.example.orders`, a separate filtered configuration will not automatically remove `DebugHelper` or `OldFaxNotifier` already picked up by the broader scan.

## 18. Principles to Remember

1. **`@ComponentScan` locates candidates in packages, then applies filtering rules.** Packages outside the scan scope do not become candidates just by having `@Component`.
2. **Stereotypes are scanned by default.** Regular include filters expand the candidate set; to accept only classes matching include filters, understand and set `useDefaultFilters = false`.
3. **Exclude filters only affect that specific component scan operation.** Beans can still be registered via `@Bean`, `@Import`, auto-configuration, or another scan.
4. **`basePackageClasses` avoids fragile package strings during refactoring.** Marker interfaces are a lightweight way to anchor scan boundaries.
5. **`@SpringBootApplication` provides package-based default component scanning.** Where you place the startup class directly affects what gets discovered.
6. **Component scan is distinct from JPA entity/repository scanning and bean scope.** Each mechanism has its own purpose and configuration.
7. **Filters can reshape the dependency graph.** Excluding a service or repository can prevent other beans from initializing; adding candidates can trigger `NoUniqueBeanDefinitionException`.
8. **Prefer simple configurations that express intent clearly.** When the real condition is dev/prod or feature toggles, profiles or conditionals are often clearer than regex or custom filters.

## Conclusion

`@ComponentScan` determines **where Spring searches and which classes are considered bean candidates**. Scope is defined via base packages; `includeFilters` expands—or, with default filters disabled, restricts—accepted candidates; `excludeFilters` drops matching classes from that scan. These filters work alongside Spring Boot's other registration and configuration mechanisms, so always trace each bean's registration source.

When a bean is missing or appears unexpectedly, start from the startup class's package, configured base packages, `useDefaultFilters`, active filters, and other bean registration sources. Mastering these factors helps you organize Spring Boot code into well-bounded modules, avoid accidental component registration, and explain changes in the `ApplicationContext` accurately.
