# includeFilters, excludeFilters, and useDefaultFilters in Spring Component Scan

## 1. Lesson Objectives

In the Spring Core Container, `@ComponentScan` does not have to register every class annotated with `@Component`. We can **add kinds of classes to be discovered**, **exclude kinds of classes we do not want registered**, or **completely disable the default stereotype filters**.

After this lesson, you will be able to:

- Explain the meaning of `includeFilters`, `excludeFilters`, and `useDefaultFilters` on `@ComponentScan`.
- Accurately predict whether a class will be scanned into a bean when multiple filters apply together.
- Use `FilterType.ANNOTATION`, `ASSIGNABLE_TYPE`, `REGEX`, `ASPECTJ`, and `CUSTOM` within their proper scope.
- Understand the difference between "filtering candidates discovered by the component scanner" and "preventing every way a bean can be registered."
- Write a runnable Java 17+ configuration where a class with a custom annotation is selected, another class is excluded, and a regular `@Service` is not registered because `useDefaultFilters=false`.
- Diagnose missing beans, overly broad scanning, incorrect fully-qualified regexes, buggy custom `TypeFilter`s, and duplicate beans.

**Scope:** this lesson only covers **component scanning** filters in the Spring IoC Container. It does not replace `@Profile`, `@Conditional`, Spring Data repository scanning, or JPA entity scanning.

## 2. What Is the Default Component Scan Filter?

When using:

```java
@Configuration
@ComponentScan(basePackages = "com.example.shop")
public class AppConfig {}
```

Spring searches classes in package `com.example.shop` and its subpackages, and applies the **default filter**. Under standard Spring Framework configuration, this filter recognizes `@Component` and annotations meta-annotated with `@Component`, typically:

- `@Service`;
- `@Repository`;
- `@Controller`;
- `@RestController` (via a meta-annotation chain);
- `@Configuration`;
- custom application annotations meta-annotated with `@Component`.

If the application has Jakarta Inject available, Spring can also support the `@Named` annotation through the corresponding default filter. In this lesson, we focus on the `@Component` model.

**Distinguish two steps:**

1. **Candidate discovery:** the scanner uses packages and filters to determine which classes qualify.
2. **Bean registration/creation:** the container processes bean definitions, scopes, configuration conditions, dependencies, and lifecycle. A class matching a filter still needs to be a valid candidate and registrable by the container.

A plain `interface` matching `ASSIGNABLE_TYPE` does not mean Spring automatically instantiates the interface as a component. Type filters must still pass valid-candidate checks.

## 3. Three Important Attributes of @ComponentScan

Suppose we have this configuration:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = org.springframework.context.annotation.FilterType.ANNOTATION,
        classes = SpecialModule.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = org.springframework.context.annotation.FilterType.ASSIGNABLE_TYPE,
        classes = LegacyAdapter.class
    )
)
public class AppConfig {}
```

This is a **structural** example: `SpecialModule` is a custom annotation and `LegacyAdapter` is an actual application class, neither declared here. Do not copy this snippet alone and expect it to compile without those two types.

Meaning:

- `basePackages`: bounds the **region to scan**. Filters do not look for classes outside this region.
- `useDefaultFilters=false`: stops automatically treating stereotypes `@Component`, `@Service`, `@Repository`, `@Controller`, etc., as sufficient for selection.
- `includeFilters`: adds criteria for classes to be **eligible for recognition**. In this example, classes carrying `@SpecialModule` can be added to the candidate set even if that annotation is not meta-annotated with `@Component`.
- `excludeFilters`: removes classes matching the condition; in this example, classes of type `LegacyAdapter` are excluded from that scan pass.
- Explicitly registered `@Configuration` and `@Bean` definitions can still create beans independently of whether the class is selected by the scanner.

### Key Behavior Table

| `useDefaultFilters` | `includeFilters` | `excludeFilters` | Baseline Result |
| --- | --- | --- | --- |
| `true` (default) | Not declared | Not declared | Accepts default components/stereotypes in scanned packages. |
| `true` | Present | Absent | Accepts **default candidates OR include-matching candidates**. |
| `true` | Present | Present | Accepts default/include candidates, **except** those matching exclude. |
| `false` | Absent | Absent | No default include criteria to find regular components. |
| `false` | Present | Absent | Only accepts include-matching candidates in scanned packages. |
| `false` | Present | Present | Only accepts candidates matching include **and not matching exclude**. |

A very common misconception is that `includeFilters` **turns scanning into a whitelist** while `useDefaultFilters` is still `true`. It **extends** what the default filter finds. If you want the list based strictly on criteria you declare, consider `useDefaultFilters=false`.

## 4. Candidate Selection Model

For each class within the scan scope inspected by the scanner, the filter logic can be pictured as:

```text
Start with a class in the base package
               |
               v
       Matches exclude?
         /           \
       Yes            No
       |                |
  Skip class            v
                   Matches include?
                    /        \
                  Yes         No
                  |             |
               Select*          v
                       useDefaultFilters=true
                       and matches default?
                         /         \
                        Yes         No
                        |              |
                      Select*        Skip

* Valid bean candidate conditions are still checked afterward.
```

The diagram shows the logical outcome: **exclude wins over include/default** within the same scan pass. In the implementation, the scanner may check excludes first and short-circuit. Do not read the diagram as the exact call order of matchers in code.

We can write the model formula:

```text
eligibleByFilters =
    inBasePackage
    AND NOT excluded
    AND (
        matchesAnyInclude
        OR (useDefaultFilters AND matchesDefault)
    )
```

This formula only describes filters; it does **not** yet include concrete/independent candidate checks, conditions such as `@Conditional`, bean name handling, or already-registered bean definitions.

### Multiple Includes and Excludes

Inside an `includeFilters` array, multiple filters typically combine with **OR**: a class only needs to match one include filter. Similarly, multiple exclusions remove a class if **any** exclude filter matches.

Therefore:

```java
includeFilters = {
    @ComponentScan.Filter(
        type = FilterType.ANNOTATION, classes = FeatureA.class),
    @ComponentScan.Filter(
        type = FilterType.ANNOTATION, classes = FeatureB.class)
}
```

means "FeatureA **or** FeatureB", not "must simultaneously carry both." This is an illustrative annotation snippet requiring imports for `ComponentScan`, `FilterType`, and declarations of the two business annotations.

If you need a composite condition "A **and** B", you can use `FilterType.CUSTOM` to inspect both pieces of metadata inside one `TypeFilter`, or structure your packages/annotations more clearly.

## 5. useDefaultFilters: true vs false

### 5.1. Default true: Stereotypes Are Still Scanned

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = Experimental.class
    )
)
class AppConfig {}
```

Assume `Experimental` is an application-defined annotation. With the default `useDefaultFilters=true`:

- `@Service StandardService` in the package is still a candidate;
- `@Repository StandardRepository` is still a candidate;
- class `@Experimental PreviewEngine` can be accepted if the filter matches, **even if `@Experimental` is not meta-annotated with `@Component`**;
- classes matching neither default nor include are skipped.

**Mistake:** "Adding `includeFilters = Experimental` makes Spring scan only Experimental classes." This is false unless defaults are turned off.

### 5.2. useDefaultFilters=false: Keeping Only Declared Criteria

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = Experimental.class
    )
)
class AppConfig {}
```

Now, classes carrying only `@Service` or `@Component` without `@Experimental` will not be selected by this scanner. Note that this does not necessarily remove **every bean** in the context: beans from `@Bean`, `@Import`, directly registered configuration classes, and other mechanisms can still exist.

### 5.3. Turning Off Defaults While Forgetting Includes

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false
)
```

With this setup, the scanner has no default stereotype filters and is given no include filters; as a result, **regular components in the scan region are not automatically discovered**. This configuration is rarely intentional. If the `@Configuration` class is passed directly to `AnnotationConfigApplicationContext`, it still exists itself; do not confuse that with the scanner finding services.

### 5.4. When Should You Keep the Default?

Most applications should leave `useDefaultFilters=true` because package structure and stereotypes already describe components clearly. Only use `false` when you want an active, specialized component selection mechanism—such as loading plugins via a dedicated annotation, isolating experimental adapters from regular components, or building a very narrow tooling context.

Do not use complex filters merely as a substitute for clean package organization.

## 6. Complete Java 17+ Example: include + exclude + Disabling Defaults

This program **does not need Spring Boot**. It uses Spring Framework 6.2.9, Java 17, and `AnnotationConfigApplicationContext`. All classes are placed in one Java file so it is easy to run and observe accurately.

Goals:

1. `PilotJob` carries `@Pilot` **without** `@Component` and is still brought into the context by an include filter.
2. `DirectJob` has **no stereotype annotation** and is still selected via `ASSIGNABLE_TYPE`.
3. `BlockedJob` carries `@Pilot` but is excluded, proving that exclude wins over include.
4. `RegularJob` has `@Service` but is skipped because `useDefaultFilters=false`.

### 6.1. Project Structure

```text
filter-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/FilterDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'filter-demo'
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
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.FilterDemo'
}
```

**`src/main/java/demo/FilterDemo.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.TreeSet;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.stereotype.Service;

public class FilterDemo {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext(ScanConfig.class)) {

            System.out.println("pilot=" + ctx.containsBean("pilotJob"));
            System.out.println("direct=" + ctx.containsBean("directJob"));
            System.out.println("blocked=" + ctx.containsBean("blockedJob"));
            System.out.println("regular=" + ctx.containsBean("regularJob"));

            var jobs = ctx.getBeansOfType(Job.class);
            System.out.println("selected=" +
                    String.join(",", new TreeSet<>(jobs.keySet())));

            System.out.println("run=" +
                    jobs.get("pilotJob").run() + "|" +
                    jobs.get("directJob").run());
        }
    }
}

interface Job {
    String run();
}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Pilot {
}

// Selected via ANNOTATION, even though @Pilot is not meta-annotated with @Component.
@Pilot
class PilotJob implements Job {
    @Override
    public String run() {
        return "pilot";
    }
}

// Selected via ASSIGNABLE_TYPE, no @Component needed.
class DirectJob implements Job {
    @Override
    public String run() {
        return "direct";
    }
}

// Matches @Pilot but is excluded by class.
@Pilot
class BlockedJob implements Job {
    @Override
    public String run() {
        return "blocked";
    }
}

// Has @Service, but default filters are turned off.
@Service
class RegularJob implements Job {
    @Override
    public String run() {
        return "regular";
    }
}

@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackageClasses = FilterDemo.class,
    useDefaultFilters = false,
    includeFilters = {
        @ComponentScan.Filter(
            type = FilterType.ANNOTATION,
            classes = Pilot.class
        ),
        @ComponentScan.Filter(
            type = FilterType.ASSIGNABLE_TYPE,
            classes = DirectJob.class
        )
    },
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = BlockedJob.class
    )
)
class ScanConfig {
}
```

`Job`, `PilotJob`, `DirectJob`, `BlockedJob`, `RegularJob`, and `ScanConfig` are non-`public` top-level types in the file; Java permits this. Only `FilterDemo` is `public`, matching the filename. Spring can discover independent top-level classes in package `demo`; omitting `public` does not turn them into inner classes.

`basePackageClasses=FilterDemo.class` only uses `FilterDemo`'s package as the scan root. The `FilterDemo` class itself is not selected because no filter matches it.

### 6.2. Running the Program

From the `filter-demo` directory, with Gradle and JDK 17+:

```bash
gradle run --quiet
```

If a Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. Standalone `javac FilterDemo.java` is insufficient because Spring JARs would be missing; Gradle resolves dependencies and compiles/runs `demo.FilterDemo`.

**Expected stdout printed by the program:**

```text
pilot=true
direct=true
blocked=false
regular=false
selected=directJob,pilotJob
run=pilot|direct
```

Dependency download or Gradle configuration logs, if any, are separate from the lines produced by `System.out.println`.

### 6.3. Analyzing Each Candidate

| Class | Matches default stereotype? | Matches include? | Matches exclude? | Outcome |
| --- | --- | --- | --- | --- |
| `PilotJob` | No; `@Pilot` is not `@Component` | Yes, `ANNOTATION Pilot` | No | **Selected** |
| `DirectJob` | No | Yes, `ASSIGNABLE_TYPE DirectJob` | No | **Selected** |
| `BlockedJob` | No | Yes, `ANNOTATION Pilot` | Yes, `ASSIGNABLE_TYPE BlockedJob` | **Excluded** |
| `RegularJob` | Yes, `@Service` | No | No | **Excluded** because default is off |
| `ScanConfig` | Yes, `@Configuration` | No | No | Not *additionally scanned*; registered directly when creating context |

The `getBeansOfType(Job.class)` map contains `directJob` and `pilotJob`. `TreeSet` is only used to **sort names for deterministic stdout printing**; it does not prove the order in which Spring discovers beans on the classpath. `run=pilot|direct` is written by looking up beans by key, so it does not depend on map iteration order.

### 6.4. Trying Meaningful Variations

**Change `useDefaultFilters = false` to `true`.** Then `RegularJob` becomes a candidate because it carries `@Service`; the includes remain valid. `ScanConfig` can also be seen by the scanner due to `@Configuration`, though having already been registered directly does not create an extra `Job`. Do not assume toggling the flag only adds one bean of *any arbitrary type*.

**Remove the exclude for `BlockedJob`.** `BlockedJob` will be added because it matches `@Pilot`. This proves the exclude was blocking a class that would otherwise be included.

**Remove the include for `DirectJob`.** With defaults still disabled, the `directJob` bean is not scanned. The demo's `jobs.get("directJob").run()` call will fail because the sample code still requests that key. When testing variations, adjust the print statements or check only `containsBean` for controlled observation.

**Put `@Component` on `RegularJob` while keeping `useDefaultFilters=false`.** The bean still does not appear unless it matches an include. Adding a stereotype does not override the switch that turned off default filters.

## 7. FilterType.ANNOTATION

`ANNOTATION` is the default filter type of `@ComponentScan.Filter`. It selects classes carrying a specified annotation or matching meta-annotation.

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = ExperimentalFeature.class
    )
)
```

This is an illustrative annotation snippet placed on a configuration class; `ExperimentalFeature` is an application-defined annotation. Spring can bring a class like the following into the container when scanning:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ExperimentalFeature {}

@ExperimentalFeature
public class PreviewDiscountPolicy {}
```

This snippet requires importing `ElementType`, `Target`, `Retention`, and `RetentionPolicy`. To run standalone, place each public top-level type in its correspondingly named file.

**Two cases to distinguish:**

- Custom annotation **without** `@Component`: the default scanner normally ignores it, whereas `includeFilters=ANNOTATION` can select it.
- Custom annotation **with** `@Component` as a meta-annotation: the default scanner can already select it, even without adding a filter.

Meta-stereotype example:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@org.springframework.stereotype.Component
public @interface BusinessComponent {}
```

This is a structural example; Java annotation types must be imported. With `@BusinessComponent`, many applications do not need a separate include filter. For highly specialized selection rules, an include filter remains useful combined with `useDefaultFilters=false`.

**Note:** `ANNOTATION` inspects metadata on the scanned **type**; it does not look for `@GetMapping` methods or other method-level annotations to automatically create beans for them. Method-level scanning is a separate topic.

## 8. FilterType.ASSIGNABLE_TYPE

`ASSIGNABLE_TYPE` selects classes assignable to a target type—meaning the class itself is that type, extends that superclass, or implements that interface.

```java
@ComponentScan(
    basePackages = "com.example.shop.handlers",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = CommandHandler.class
    )
)
```

Assuming `CommandHandler` is a business interface, the scanner can pick up implementations inside the scanned package even if they are not annotated with `@Component`:

```java
interface CommandHandler {
    void execute();
}

class CreateOrderHandler implements CommandHandler {
    public void execute() {}
}

class CancelOrderHandler implements CommandHandler {
    public void execute() {}
}
```

This is a two-part example that needs to reside in the same package or import the right types. The scanner still checks candidate validity; it does not instantiate the `CommandHandler` interface itself.

**Warning about cardinality:** filtering by a very broad base interface may scan multiple implementations and cause `NoUniqueBeanDefinitionException` during single-bean injection by interface. If you want multiple beans, injecting `List<CommandHandler>` is a clear option. If you want one, consider `@Qualifier`, `@Primary`, or narrowing the package/type scope appropriately.

Type filtering is a check on **class metadata**; it does not guarantee every assignable type has suitable constructors or dependencies for Spring to instantiate successfully.

## 9. FilterType.REGEX

`REGEX` selects classes by their **fully qualified class name**, including package and class name. It does not inspect business values of objects and does not apply the regex to bean names after creation.

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = "com\\.example\\.shop\\.adapter\\..*Adapter"
    )
)
```

Here:

- `com\\.example\\.shop\\.adapter\\.` in a Java string literal uses `\\.` so the regex receives literal dots.
- `.*Adapter` matches names ending with `Adapter` inside the described package.
- Regex checks the fully qualified class name; `basePackages` still governs where the scanner looks for classes to test.

For example, `com.example.shop.adapter.SqlAdapter` matches the pattern. `com.example.shop.service.StockService` does not match. `com.example.shop.adapter.SqlAdapterV2` also does not match because it does not end with `Adapter`.

**Common Java string mistake:** writing `pattern="com\.example\..*"` causes an invalid escape sequence error in Java source because `\.` is not a valid Java string escape. Write `"com\\.example\\..*"` in Java source so the regex engine receives `com\.example\..*`.

**Do not use regex when type/annotation suffices:** package and class names can change during refactoring, causing filters to stop matching the right classes with little warning from the IDE/compiler. If the system has capability-describing annotations, filtering by `ANNOTATION` usually expresses intent more clearly.

## 10. FilterType.ASPECTJ

`ASPECTJ` accepts an **AspectJ type pattern expression** to match types. Reference example following Spring documentation:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASPECTJ,
        pattern = "com.example..*Service+"
    )
)
```

This illustrative configuration snippet uses **AspectJ pattern syntax**, not Java regex. The `..` and `+` symbols follow AspectJ semantics; verify the actual types matched by AspectJ syntax and ensure AspectJ type-pattern support (typically `aspectjweaver`) is on the classpath when using this filter.

`ASPECTJ` here is **only used to select classes during scanning**; it does not automatically enable Spring AOP, create aspects, or intercept method calls. It should also not be confused with the `@Aspect` annotation. For most categorical component selection tasks, `ANNOTATION`, `ASSIGNABLE_TYPE`, or `REGEX` is easier to understand.

## 11. FilterType.CUSTOM and TypeFilter

When built-in filter types cannot express the desired criterion, you can implement `org.springframework.core.type.filter.TypeFilter` (the actual interface resides in package `org.springframework.core.type.filter`).

```java
package com.example.shop.config;

import java.io.IOException;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.MetadataReaderFactory;
import org.springframework.core.type.filter.TypeFilter;

public final class EndsWithGatewayFilter implements TypeFilter {
    @Override
    public boolean match(
            MetadataReader metadataReader,
            MetadataReaderFactory metadataReaderFactory) throws IOException {

        String className =
                metadataReader.getClassMetadata().getClassName();

        return className.endsWith("Gateway");
    }
}
```

This is a valid Java `TypeFilter` class when `spring-core` is on the classpath (brought in by Spring Context). It can be used in a configuration within the same project as follows:

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.CUSTOM,
        classes = EndsWithGatewayFilter.class
    )
)
```

This illustrative configuration snippet requires importing `ComponentScan`, `FilterType`, and `EndsWithGatewayFilter` on an appropriate class.

**Why use `MetadataReader`?** The scanner reads `.class` metadata via an appropriate mechanism, avoiding the need to instantiate or load every type just to decide whether to register it. Custom filters should be designed to be **fast, predictable, and side-effect free**. Do not connect to databases, make network requests, or load heavy classes just to decide include/exclude.

`MetadataReaderFactory` supports reading metadata of related classes, such as superclasses or interfaces when advanced criteria require it; avoid creating custom classloaders or doing arbitrary resource reads for every `.class` file.

If many matched classes cannot be instantiated as components, the system still enforces candidate validity; `TypeFilter` does not bypass bean creation rules.

## 12. Combining include and exclude in Real Scenarios

### 12.1. Keep Default Scanning While Excluding Legacy Classes

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = LegacyComponent.class
    )
)
class AppConfig {}
```

Assume `LegacyComponent` is a custom annotation. While `useDefaultFilters` stays `true`, Spring continues discovering regular stereotypes while excluding classes marked legacy. This works well when most of the architecture still follows `@Component`.

### 12.2. Selecting a Group of Plugins with a Custom Annotation

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.plugins",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = PluginComponent.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = DisabledPlugin.class
    )
)
class PluginConfig {}
```

This illustrative snippet requires the two business annotations. With these filters, classes annotated with `@PluginComponent` are selected unless they also carry `@DisabledPlugin`. **Runtime toggling** is not continuously re-evaluated: this is a bean registration decision made when Spring builds the context. For dynamic runtime toggling, use an appropriate separate mechanism.

### 12.3. Swapping Implementations in Tests

```java
@Configuration
@ComponentScan(
    basePackages = "com.example.shop.data",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = ".*Stub.*Repository"
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = org.springframework.stereotype.Repository.class
    )
)
class TestDataConfig {}
```

Idea: include classes named like `StubCustomerRepository` and exclude classes annotated with `@Repository` in this scan pass. If the **stub also carries `@Repository`**, it will be excluded too because exclude beats include; design markers/stubs cleanly.

Test configuration also depends on other imported or auto-configured configurations. Excluding in one scan pass **does not prove** the original bean cannot be registered via another scan pass, `@Bean`, `@Import`, or auto-configuration.

### 12.4. What Happens When Include and Exclude Match the Same Class?

```java
@ComponentScan(
    basePackages = "com.example.shop",
    useDefaultFilters = false,
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = OrderProcessor.class
    ),
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = ".*DeprecatedOrderProcessor"
    )
)
```

If `DeprecatedOrderProcessor implements OrderProcessor` and its fully qualified name ends with `DeprecatedOrderProcessor`, that bean is excluded. Other eligible `OrderProcessor` classes are added to the candidate set. This is the exclusion rule within a **scanner pass**.

## 13. Equivalent XML Configuration in Legacy Projects

Many legacy projects use `context:component-scan` instead of annotations. Same concept:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan
            base-package="com.example.shop"
            use-default-filters="false">
        <context:include-filter
                type="annotation"
                expression="com.example.shop.PluginComponent"/>
        <context:exclude-filter
                type="regex"
                expression="com\.example\.shop\..*Legacy.*"/>
    </context:component-scan>
</beans>
```

This is an XML example with a hypothetical business annotation `com.example.shop.PluginComponent`. In XML, regex uses `\.` directly without extra Java string literal escaping. Both Spring XML and `@ComponentScan` express the same type inclusion/exclusion filtering concept.

XML type values include `annotation`, `assignable`, `aspectj`, `regex`, and `custom`; in the Java API, these are constants on `FilterType`.

## 14. Distinguishing Scan Filters from Other Mechanisms

| Mechanism | Purpose | Relationship to Component Scan |
| --- | --- | --- |
| `basePackages` / `basePackageClasses` | Defines the **classpath region to scan** | Filters operate only inside that region. |
| `includeFilters` | Adds selectable classes | Can select classes without `@Component`. |
| `excludeFilters` | Removes classes from the **scan pass** | Does not block registration via other paths. |
| `useDefaultFilters` | Enables/disables default stereotype detection | Does not remove beans already registered by `@Bean` or `@Import`. |
| `@Profile` | Restricts registration by active profile | Configuration condition, not a `@ComponentScan` filter. |
| `@Conditional` | Restricts registration by specific condition | Can prevent bean registration even after scanner recognizes metadata. |
| `@Primary` | Prioritizes a candidate during single autowiring | Does not decide whether the scanner brings a type into the context. |
| `@Qualifier` | Narrows candidates at injection | Applied during dependency resolution, after scanning. |
| `@Bean` | Registers bean from factory method | Independent registration path, not removed by an exclude filter. |
| `@Import` | Imports configurations/selectors/registrars | Registration path distinct from scanner component selection. |

**Dangerous mistake:** treating `excludeFilters` as "banning this class from appearing anywhere in the `ApplicationContext`." If another `@Configuration` declares a bean of the same type via `@Bean`, an exclude filter does not suppress that bean. Inspect all registration paths when investigating unexpected beans.

## 15. Spring Boot and Scan Boundaries

In Spring Boot, `@SpringBootApplication` typically includes `@ComponentScan`. Attributes such as `scanBasePackages` and `scanBasePackageClasses` configure **component scanning**, but do not automatically replace other scan mechanisms such as JPA entities or Spring Data repositories.

Conceptual example:

```java
@SpringBootApplication(scanBasePackages = "com.example.shop")
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

This is a Spring Boot snippet requiring Spring Boot dependencies and classes in appropriate packages. For applications that add multiple `@ComponentScan` annotations manually, be careful because each scan configuration can contribute additional bean definitions. An exclude filter applied to one scan pass does not guarantee another scan pass will not register that type.

If you simply want to omit a bean based on a feature flag in Boot, conditional bean configuration (`@ConditionalOnProperty`, etc.) matches configuration sources better than filtering class names with regex. However, that is a design choice outside Spring Framework's basic filter mechanism.

## 16. Common Errors and How to Check Them

### Error 1 — "I added includeFilters, yet Spring still scans every @Service"

Cause: `useDefaultFilters` defaults to **true**, so `@Service` is still selected. To select only classes matching include filters, set `useDefaultFilters=false` and verify all required dependencies.

### Error 2 — "Setting useDefaultFilters=false made all services disappear"

Without an appropriate include filter, regular stereotypes are no longer found by this scan pass. Add include filters, or keep the default if using standard stereotype organization.

### Error 3 — "I excluded a class, yet the bean is still present"

Identify where the bean is registered from: a `@Bean`, `@Import`, another context, another `@ComponentScan`, or auto-configuration. `excludeFilters` only applies to the configured scanner. In this case, inspect bean definitions and configuration sources rather than adding redundant excludes.

### Error 4 — "REGEX does not match the expected class"

Verify the **fully qualified name** of the class (`package.ClassName`), not the bean name. In Java strings, remember `\\.` to represent literal regex `\.`. Test the pattern against actual class name strings and keep in mind the regex matcher matches according to the filter type's rules.

### Error 5 — "ASSIGNABLE_TYPE found an interface, but no bean was created"

Interfaces or abstract classes do not become instantiable components merely by matching a filter. Only valid concrete, independent classes are normally added as component candidates, aside from specialized support such as conditional lookup methods. Selecting concrete implementations and providing suitable constructors/dependencies resolves this.

### Error 6 — "Both exclude filter and include filter match; I expected include to win"

Within a single scan pass, a class matching **exclude** is rejected even if it also matches an include or default stereotype. Change your condition design or review business precedence before writing filters.

### Error 7 — "CUSTOM filter has side effects or loads classes arbitrarily"

Custom `TypeFilter`s run during scanning; expensive I/O or reflection slows startup and can cause unintended failures. Use `MetadataReader` whenever sufficient, and avoid service calls, connections, or global mutable state inside matchers.

### Error 8 — "Scanning too broad a package brought in unwanted beans"

Using `basePackages="com"` or an overly generic root package can make the scanner hit countless classes from unrelated modules. Narrow scan packages, separate business annotations cleanly, and check configuration imports from elsewhere.

### Error 9 — "Added a filter to one context and expected it to apply to all contexts"

An application may have a root `ApplicationContext`, child `WebApplicationContext`, test slices, or independent contexts. Which beans exist in a context depends on that context's scans and registrations; filters do not apply globally across context boundaries.

### Error 10 — "Selected bean via scanner, yet constructor still fails"

A filter can select a scan-eligible bean that still needs a missing dependency, has an unsuitable constructor, or hits a bean name conflict. `includeFilters` does not bypass dependency injection or bean creation errors. When needed, inspect `UnsatisfiedDependencyException`, `BeanCreationException`, and the candidate list.

### Error 11 — "Renamed a class without updating REGEX"

Regexes based on fully qualified class names are fragile under refactoring. Filtering by annotation or interface is a more resilient option when class names are not a business contract.

### Error 12 — "Thinking scan filters dynamically toggle beans after the context starts"

Filters decide at scan/registration time; they do not watch config files to add/remove beans at runtime. For dynamically toggleable features, design a dedicated abstraction or runtime strategy rather than relying on changing `includeFilters` while running.

## 17. Observing and Testing Filters

### 17.1. Checking Bean Names Directly

```java
try (AnnotationConfigApplicationContext ctx =
         new AnnotationConfigApplicationContext(ScanConfig.class)) {
    System.out.println(ctx.containsBean("pilotJob"));
    System.out.println(ctx.containsBean("blockedJob"));
}
```

This snippet reuses `ScanConfig` from `FilterDemo` and can be placed in package `demo` with appropriate context imports. Outputting `true` then `false` verifies **presence by bean name**, which alone does not prove all selection logic is right if bean names have been customized.

### 17.2. Checking by Type

```java
var names = ctx.getBeanNamesForType(Job.class);
java.util.Arrays.sort(names);
for (String name : names) {
    System.out.println(name);
}
```

This snippet belongs inside the live scope of `ctx` and uses `Job` from the demo. Sorting simply keeps the test deterministic. With the original demo configuration, the resulting names are `directJob` followed by `pilotJob`.

### 17.3. Inspecting the Origin of a Bean Definition

In diagnostic tests, you can use:

```java
var factory = ctx.getBeanFactory();
var definition = factory.getBeanDefinition("pilotJob");

System.out.println(definition.getBeanClassName());
System.out.println(definition.getResourceDescription());
```

This is an illustrative snippet in the same `AnnotationConfigApplicationContext` as the demo. `getResourceDescription()` may return a resource description or `null` depending on how the bean was registered, so do not assert fixed stdout text for it. For component-scanned beans, the resource description usually hints at the discovered file/class. This value is useful for tracing origin, not as a business output contract.

### 17.4. Testing with a Configuration Matrix

| Action | `PilotJob` | `DirectJob` | `BlockedJob` | `RegularJob` |
| --- | --- | --- | --- | --- |
| Original: default=false, 2 includes, 1 exclude | Yes | Yes | No | No |
| Remove exclude | Yes | Yes | Yes | No |
| Switch default=true, keep include/exclude | Yes | Yes | No | Yes |
| Remove `DirectJob` include, keep default=false | Yes | No | No | No |
| Remove all includes, keep default=false | No | No | No | No |

This matrix describes **discovery by the scan pass under test**. `ScanConfig` is still registered directly, and beans from other configurations (if added) can alter the actual list.

**Test at two levels:** unit tests for custom `TypeFilter`s (which metadata sets match), and integration tests with `AnnotationConfigApplicationContext` to verify real bean definitions and dependencies. When tests alter scan configuration, build a **fresh context** for each variant rather than expecting an already-refreshed context to re-scan automatically.

## 18. Self-Study Questions

**Question 1.** A configuration declares `includeFilters = @Filter(Experimental.class)` without setting `useDefaultFilters`. Why do `@Service` beans typically still appear?

**Answer:** Because the default is `true`. Include filters **augment** default stereotypes with additional candidates rather than narrowing them.

**Question 2.** You want to scan only classes annotated with `@Pilot`, even classes without `@Component`. Which configuration expresses that intent accurately?

**Answer:** `useDefaultFilters=false` and `includeFilters=@Filter(type=ANNOTATION,classes=Pilot.class)` with appropriate base packages. Classes must still qualify as component candidates and succeed registration.

**Question 3.** If a class matches both an include filter and an exclude filter, what happens?

**Answer:** The class is excluded from that scan pass because exclude takes precedence.

**Question 4.** Why does `excludeFilters` not guarantee there will never be a bean of that type in the container?

**Answer:** The bean may still be registered via `@Bean`, `@Import`, auto-configuration, or another scan pass. Excludes only constrain a single scan pass.

**Question 5.** Does `FilterType.REGEX` compare against `getBean("beanName")` or `package.ClassName`?

**Answer:** It compares against the **fully qualified class name** in metadata, not the bean name assigned by Spring.

**Question 6.** Does `ASSIGNABLE_TYPE` with an interface automatically instantiate the interface?

**Answer:** No. It can select eligible implementation classes in base packages; an interface itself cannot be constructor-instantiated as a concrete component.

**Question 7.** If you want the condition "the class has both annotation A and annotation B", is adding two include filters enough?

**Answer:** No, includes combine with OR. You can write a custom `TypeFilter` checking both A and B simultaneously or reorganize your marker annotations.

**Question 8.** In `FilterDemo`, why does `RegularJob` have `@Service` yet `containsBean("regularJob")` returns false?

**Answer:** `useDefaultFilters=false` turns off default stereotypes, and the two includes only select `Pilot` and `DirectJob`. `RegularJob` matches neither include.

**Question 9.** Does an `ASPECTJ` filter automatically turn a class into an aspect?

**Answer:** No. It uses type-pattern syntax to select classes during scanning; it does not enable Spring AOP or apply advice to methods.

**Question 10.** When a custom filter causes slow startup times, what should you inspect?

**Answer:** Check whether `TypeFilter.match()` performs I/O, network calls, class loading, expensive reflection, or repeated metadata processing; prefer fast, side-effect-free inspection of `MetadataReader`.

## 19. Official References

- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): filter types, include/exclude examples, `useDefaultFilters`, and XML configuration.
- [Spring Framework 6.2 — ComponentScan API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ComponentScan.html): `includeFilters`, `excludeFilters`, `useDefaultFilters`, scan scope, and defaults.
- [Spring Framework 6.2 — ComponentScan.Filter API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/ComponentScan.Filter.html): `classes`, `pattern`, `type`, and multi-type rules.
- [Spring Framework 6.2 — FilterType API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/annotation/FilterType.html): the five choices ANNOTATION, ASSIGNABLE_TYPE, ASPECTJ, REGEX, CUSTOM.
- [Spring Framework — TypeFilter API](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/type/filter/TypeFilter.html): implementation contract for custom matchers.

**Key takeaway:** With `@ComponentScan`, **packages define scope**, `includeFilters` adds recognition rules, `excludeFilters` removes candidates, and `useDefaultFilters=false` disables default component/stereotype discovery. To accurately predict whether a bean appears, look at **filters**, **candidate eligibility**, and **all other bean registration paths** in the context.
