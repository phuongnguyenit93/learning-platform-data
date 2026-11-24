# DeferredImportSelector Processing Timing in Spring Core Container

## 1. Overview

When using Java configuration, Spring can compose configuration classes via `@Import`. You can import classes directly, let an `ImportSelector` choose which classes to import, or use `DeferredImportSelector` to **defer the import selection step** until after regular configuration classes have been parsed by Spring.

The word **deferred** is easy to misunderstand. Here, it means **processed later during the configuration metadata parsing phase**—not **creating beans after the application finishes starting**, not **running on a background thread**, and not **enabling lazy initialization**.

According to Spring's Javadoc contract, `DeferredImportSelector` is a specialized `ImportSelector` processed after `@Configuration` classes during configuration processing. This serves as a useful foundation for imports that depend on conditions, selection groups, or auto-configuration strategies.

### Objectives

After this lesson, you will:

1. Clearly understand the difference between `ImportSelector` and `DeferredImportSelector`.
2. Read the timeline accurately: parser → deferred imports → bean definitions → bean instances.
3. Understand `AnnotationMetadata`, `getImportGroup()`, `Group.process()`, `Group.selectImports()`, and `Group.Entry`.
4. Know the effect and limits of `Ordered`/`@Order` on deferred selectors.
5. Avoid relying on runtime bean state or an incomplete bean-definition registry while selectors run.
6. Run a Java 17+ example with a normal selector, nested normal selector, and deferred group, measuring callback order.
7. Understand why Spring Boot uses `AutoConfigurationImportSelector`, without confusing Boot APIs with Spring Core.
8. Diagnose issues when a configuration selected by a deferred selector still fails to appear as a bean.

## 2. What `@Import` Can Accept

`@Import` supports multiple ways to add configuration sources. The most explicit case:

```java
@Configuration
@Import({StorageConfiguration.class, PricingConfiguration.class})
public class ApplicationConfiguration {
}
```

This is an illustrative configuration snippet, assuming `StorageConfiguration` and `PricingConfiguration` actually exist on the classpath and `Configuration` and `Import` are imported. When `ApplicationConfiguration` is loaded, Spring parses `@Import` and brings the referenced configurations into the same ApplicationContext.

Beyond importing classes directly, `@Import` can work with:

| Type | Meaning |
| --- | --- |
| `ImportSelector` | Selects class/configuration names to import during normal processing. |
| `DeferredImportSelector` | Selects class/configuration names during the parser's deferred phase. |
| `ImportBeanDefinitionRegistrar` | Interacts with the registry to register bean definitions programmatically. |
| Configuration or component class | Added directly into the configuration processing pipeline. |

`DeferredImportSelector` **extends `ImportSelector`**, so it still uses:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

The return value is **an array of fully qualified class names**, such as `com.example.feature.FeatureConfiguration`, not bean names or object instances. If the class is a Java nested class, `SomeNestedConfig.class.getName()` returns a valid binary name; use that API rather than assembling strings manually.

## 3. Normal Selector vs. Deferred Selector

A normal selector:

```java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class NormalFeatureSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
            NormalFeatureConfiguration.class.getName()
        };
    }
}
```

This is an illustrative class requiring a concrete `NormalFeatureConfiguration`. When the parser encounters it in `@Import`, Spring processes the selector in the regular import-parsing flow and can immediately continue parsing the returned configuration.

A deferred selector:

```java
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class DeferredFeatureSelector
        implements DeferredImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {
            DeferredFeatureConfiguration.class.getName()
        };
    }
}
```

This is also an illustrative class requiring `DeferredFeatureConfiguration`. The difference lies not in the method signature, but in **when `ConfigurationClassParser` invokes and coordinates it**.

| Property | ImportSelector | DeferredImportSelector |
| --- | --- | --- |
| Inheritance | Base interface | Extends ImportSelector |
| Basic output | `String[]` class names | `String[]` class names |
| Processing timing | When parser processes normal imports | After parsing regular configurations |
| Group API | No corresponding Group interface | `DeferredImportSelector.Group` |
| Controls singleton creation | No | No |
| Supports conditional imports | Possible | Possible; often more useful when late processing is needed |
| Used for Spring Boot auto-configuration | Not the main Boot auto-configuration mechanism | Yes: `AutoConfigurationImportSelector` implements DeferredImportSelector |

Regardless of which selector is used, **Spring still has to create bean definitions and manage bean lifecycles afterward**.

## 4. Where Exactly Does Deferred Execution Happen in refresh()?

An `AnnotationConfigApplicationContext` follows the `refresh()` lifecycle. During `BeanFactoryPostProcessor` execution, `ConfigurationClassPostProcessor` parses configuration classes and coordinates `ConfigurationClassParser` with metadata registration.

Conceptual diagram:

```text
new AnnotationConfigApplicationContext(RootConfig.class)
                         |
                         v
                      refresh()
                         |
            ConfigurationClassPostProcessor
                         |
                         v
               ConfigurationClassParser
                         |
           +-------------+-------------+
           |                           |
   @Import(Config.class)       @Import(ImportSelector.class)
           |                           |
           +---------- normal processing
                         |
                @Import(DeferredImportSelector.class)
                         |
                    collect selector
                         |
                 finish parsing regular configs
                         |
                   deferred handler
                         |
                 group/order/filter imports
                         |
                 parse deferred imports
                         |
                         v
                bean-definition reader
                         |
                 registry has bean definitions
                         |
          register BeanPostProcessors / create singletons
                         |
                    refresh complete
```

**Important point:** the API phrase “after all `@Configuration` classes have been processed” refers to **configuration parsing**, not that Spring has already invoked every constructor or `@Bean` factory method.

You can divide the flow into four moments:

1. **Parse source metadata:** discover configs, annotations, and import candidates.
2. **Choose imports:** normal selectors run during parsing; deferred selectors choose during the deferred phase.
3. **Register bean definitions:** feed the final bean metadata into BeanFactory/registry.
4. **Instantiate beans:** invoke constructors/factory methods per scope and dependencies, and run post-processors/lifecycles.

It is the **second** phase that `DeferredImportSelector` defers.

### Why Cannot Deferred Be Treated as Lazy?

`@Lazy` affects when a singleton bean is instantiated (unless another dependency forces early creation). `DeferredImportSelector` affects when Spring **decides which configuration classes are imported**. A deferred-imported configuration can still declare eager singletons that are instantiated before `refresh()` completes.

For example, suppose a deferred selector picks a configuration containing an `HttpClient` bean. If that bean is non-lazy and a normal singleton, Spring will still instantiate the HTTP client during startup. Never use a deferred selector expecting a client to connect only on the first request.

## 5. How Does the Parser Collect Deferred Imports?

In implementation terms, when `ConfigurationClassParser` encounters a `DeferredImportSelector` implementation, it **stores it along with the metadata of the class that imported the selector**, instead of running it immediately like a normal `ImportSelector`.

At the end of the parse pass, collected deferred selectors are processed—potentially sorted by `Ordered` and organized into groups. Imports returned by a Group are then fed back into the parser as configuration candidates.

This process can uncover new imports, including nested imports. Therefore, a single-pass diagram is a learning model, **not a guarantee that the parser runs strictly one pass**.

### Do Not Over-Infer About BeanFactory

Even inside `DeferredImportSelector.selectImports`, the fact that `ConfigurationClassParser` has seen a `@Bean` method does not necessarily mean that method's bean definition has already been registered in the registry by `BeanDefinitionReader`.

Consequently, writing a selector like this is error-prone by design:

```java
// Conceptual counterexample:
// Inside selectImports(), do not call beanFactory.getBean("appService")
// to check whether a business bean already exists.
```

Especially avoid calling `getBean()` to force business bean creation during parsing; doing so can push bean creation into an early phase before processors/lifecycles are ready.

Instead, prefer importer metadata, `Environment`, or condition mechanisms with well-defined phase contracts.

## 6. Whose Class Does AnnotationMetadata Belong To?

The method:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata)
```

receives metadata for **the class performing the import**, not automatically the metadata of the class to be imported.

Consider:

```java
@Configuration
@Import(DeferredFeatureSelector.class)
class PaymentApplicationConfiguration {
}
```

When the selector runs, the metadata it receives corresponds to `PaymentApplicationConfiguration`. The selector can inspect annotations or meta-annotations declared on that configuration.

If you create an `@EnableFeature` annotation with attributes and meta-annotate it with `@Import`, the selector can read attributes from the metadata of the configuration class carrying that annotation. When meta-annotations and attribute aliases need to be supported, use Spring's metadata/`MergedAnnotations` API rather than reflecting directly on uninstantiated bean instances.

This ties closely to `Group.Entry`: an entry carries not only the target class name, but also the importer's metadata.

## 7. What Is DeferredImportSelector.Group?

A deferred selector can override:

```java
Class<? extends DeferredImportSelector.Group> getImportGroup();
```

By default, no custom group class is provided (the default return value may be `null`). If a selector returns a Group class, Spring uses that group to **collect multiple imports and determine the final result**.

The `Group` interface defines:

```java
void process(
        AnnotationMetadata metadata,
        DeferredImportSelector selector);

Iterable<DeferredImportSelector.Group.Entry> selectImports();
```

**`Group.process`** receives the importing metadata and corresponding selector. The Group itself can call `selector.selectImports(metadata)`, record candidates, deduplicate, or apply policies.

**`Group.selectImports`** returns the `Entry` items for the parser to continue importing. Each `Entry` holds the importing configuration's metadata and the imported class name.

Diagram:

```text
Selector A --> Group.process(metadataA, selectorA) --+
                                                       |
Selector B --> Group.process(metadataB, selectorB) --+--> Group state
                                                       |
Selector C --> Group.process(metadataC, selectorC) --+
                                                       |
                                                      v
                                              Group.selectImports()
                                                      |
                                                      v
                                             Iterable<Group.Entry>
                                                      |
                                                      v
                                            Parser processes config imports
```

**A common pitfall:** when using a Group, Spring does not necessarily call the selector's `selectImports` in a separate step beforehand. The `Group.process` implementation itself decides whether to call that method. If a custom group skips calling the selector, any side effects placed in `selector.selectImports` will not execute. Business side effects should not live in any selector callback anyway.

### Why Is Group Valuable?

When multiple modules contribute imports together, a Group can:

- Gather imports from many selectors.
- Deduplicate class names according to defined rules.
- Apply exclusions.
- Sort the processing order of imported classes.
- Decide precedence across multiple candidate sets.

However, **deduplicating imported class names does not deduplicate bean definitions across two *different* configs**. Bean name collisions, multiple type candidates, bean definition overriding policies, and injection ambiguity still apply at the registry/DI layer.

## 8. Ordered and @Order

`DeferredImportSelector` can implement `Ordered` or use `@Order` to establish relative precedence among deferred selectors. With `Ordered`, smaller numeric values generally carry higher priority.

However, **do not equate**:

- A selector with a lower order value with its target bean being created first.
- An import parsed first with its bean guaranteed to enter the singleton cache first.
- Selector ordering with bean `@DependsOn`.
- Ordering inside Spring Boot auto-configuration with global ordering across arbitrary custom selectors.

Ordering here serves the **selection phase**. When a Group is used, the Group's policy and group/import ordering also affect how final entries are handed to the parser. When an application requires dependency ordering, express dependencies through constructor/method parameters, `@DependsOn` where truly appropriate, or proper lifecycle mechanisms.

## 9. Complete Java 17+ Example: Measuring Callback Order

We use Spring Framework **6.2.19** and `AnnotationConfigApplicationContext`, without Boot. The exercise includes:

- `ImmediateSelector` — a normal `ImportSelector`.
- `ImmediateConfig` — the class selected by the normal selector.
- `NestedSelector` — a normal selector imported **inside** `ImmediateConfig`.
- `DeferredSelector` — a `DeferredImportSelector`.
- `DeferredGroup` — a Group receiving the selector, invoking `selectImports`, and returning `Entry`.
- `DeferredConfig` — the class selected during the deferred phase.
- An event list recording callbacks. After the context refreshes, the program verifies **selector callback order** rather than using bean instantiation order as a proxy.

### 9.1. Project Structure

```text
deferred-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DeferredDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'deferred-demo'
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
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.DeferredDemo'
}
```

### 9.2. Java Source

**`src/main/java/demo/DeferredDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public final class DeferredDemo {
    private static final List<String> EVENTS = new ArrayList<>();

    @Configuration(proxyBeanMethods = false)
    @Import({ImmediateSelector.class, DeferredSelector.class})
    public static class RootConfig {
    }

    public static class ImmediateSelector implements ImportSelector {
        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("immediate");
            return new String[] { ImmediateConfig.class.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(NestedSelector.class)
    public static class ImmediateConfig {
        @Bean
        String immediateMessage() {
            return "immediate";
        }
    }

    public static class NestedSelector implements ImportSelector {
        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("nested");
            return new String[0];
        }
    }

    public static class DeferredSelector implements DeferredImportSelector {
        @Override
        public Class<? extends Group> getImportGroup() {
            return DeferredGroup.class;
        }

        @Override
        public String[] selectImports(AnnotationMetadata metadata) {
            EVENTS.add("deferred.select");
            return new String[] { DeferredConfig.class.getName() };
        }
    }

    public static class DeferredGroup
            implements DeferredImportSelector.Group {

        private final List<Entry> entries = new ArrayList<>();

        @Override
        public void process(
                AnnotationMetadata metadata,
                DeferredImportSelector selector) {
            EVENTS.add("deferred.process");
            for (String name : selector.selectImports(metadata)) {
                entries.add(new Entry(metadata, name));
            }
        }

        @Override
        public Iterable<Entry> selectImports() {
            EVENTS.add("deferred.group.result");
            return List.copyOf(entries);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DeferredConfig {
        @Bean
        String deferredMessage() {
            return "deferred";
        }
    }

    public static void main(String[] args) {
        EVENTS.clear();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(RootConfig.class)) {

            int immediate = EVENTS.indexOf("immediate");
            int nested = EVENTS.indexOf("nested");
            int process = EVENTS.indexOf("deferred.process");
            int select = EVENTS.indexOf("deferred.select");
            int result = EVENTS.indexOf("deferred.group.result");

            System.out.println("immediate-before-deferred="
                    + (immediate >= 0 && immediate < process));

            System.out.println("nested-before-deferred="
                    + (nested >= 0 && nested < process));

            System.out.println("group-calls-selector="
                    + (process >= 0 && process < select));

            System.out.println("selector-before-group-result="
                    + (select >= 0 && select < result));

            System.out.println("immediate-bean="
                    + context.getBean("immediateMessage", String.class));

            System.out.println("deferred-bean="
                    + context.getBean("deferredMessage", String.class));

            System.out.println("event-count=" + EVENTS.size());
        }
    }
}
```

All classes live in a single source file, so you can copy the contents into place and run. `RootConfig`, `ImmediateConfig`, and `DeferredConfig` are public static nested classes; Spring can import them via the real class names obtained from `Class.getName()`. Do not create separate files for the nested classes.

### 9.3. Running

```bash
gradle run --quiet
```

If Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. Running `javac DeferredDemo.java` alone is not enough unless Spring JARs are provided on the classpath.

**Expected stdout from the println statements:**

```text
immediate-before-deferred=true
nested-before-deferred=true
group-calls-selector=true
selector-before-group-result=true
immediate-bean=immediate
deferred-bean=deferred
event-count=5
```

Any Gradle/runtime logs that appear are not part of the `System.out.println` lines.

### 9.4. Explaining the Output

1. Spring loads `RootConfig` and encounters `@Import` containing one normal selector and one deferred selector.
2. `ImmediateSelector` runs in the normal import stream, records `immediate`, and picks `ImmediateConfig`.
3. `ImmediateConfig` carries `@Import(NestedSelector.class)`; the nested normal selector records `nested`.
4. `DeferredSelector` is collected; after normal parsing finishes, the framework routes it to `DeferredGroup`.
5. `Group.process` records `deferred.process` and then **the Group itself** invokes `DeferredSelector.selectImports`, producing `deferred.select`.
6. `Group.selectImports` records `deferred.group.result` and returns an `Entry` pointing to `DeferredConfig`.
7. The parser feeds `DeferredConfig` into configuration metadata, and the `deferredMessage` bean is created under normal lifecycle rules.
8. Each selector callback in the fixture runs exactly once, resulting in five events.

The booleans observe **the ordering relationship between callbacks**. Meanwhile, `immediate-bean` and `deferred-bean` prove both imports ultimately produce beans in the same context. **Do not** infer which bean is instantiated first from import selection order.

## 10. Example: Group Deduplicating Imports

When multiple deferred selectors share a Group, you may want config class names to appear only once in the list returned by the Group:

```java
public final class UniqueImportsGroup
        implements DeferredImportSelector.Group {

    private final java.util.Map<String, Entry> selected =
            new java.util.LinkedHashMap<>();

    @Override
    public void process(
            AnnotationMetadata metadata,
            DeferredImportSelector selector) {

        for (String className : selector.selectImports(metadata)) {
            selected.putIfAbsent(
                    className,
                    new Entry(metadata, className)
            );
        }
    }

    @Override
    public Iterable<Entry> selectImports() {
        return selected.values();
    }
}
```

This is a separate demo class requiring imports for `DeferredImportSelector` and `AnnotationMetadata`. `LinkedHashMap` keeps the first entry per class name. In applications where differing annotation metadata from multiple importers matters, keeping the first entry **may not be the right policy**: decide based on the business contract.

### An Important Trap

A Group deduplicating config class names **cannot prevent** two *different* configs from both defining `@Bean("httpClient")`. Bean name collisions, duplicate type candidates, bean definition overriding policies, and injection ambiguity still occur in the registry/DI phase.

## 11. Relationship to @Conditional

Some imports only make sense when the configuration satisfies conditions. `DeferredImportSelector` is helpful because regular configurations have already been parsed, giving more context to certain import selection strategies.

However, do not equate “`@Configuration` metadata has been parsed” with “all beans already exist in BeanFactory”. Conditions and registration belong to different phases. A condition reading `Environment`/classpath can be safe; a condition relying on `getBean()` or incomplete BeanFactory state is error-prone.

### Environment-Driven Selector

```java
import org.springframework.context.EnvironmentAware;
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotationMetadata;

public final class AuditFeatureSelector
        implements DeferredImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        boolean enabled = environment.getProperty(
                "feature.audit.enabled", Boolean.class, false);

        return enabled
                ? new String[] { AuditConfiguration.class.getName() }
                : new String[0];
    }
}
```

This is a standalone snippet requiring an `AuditConfiguration` class in the application. Spring supplies `Environment` via `EnvironmentAware` while preparing the selector. A property-reading condition does not need to instantiate business services.

Even so, merely checking a property **does not require** deferred processing. Without needing a Group or late timing, a normal `ImportSelector` or `@Conditional` directly on the configuration is usually simpler.

## 12. Role in Spring Boot Auto-Configuration

A well-known real-world case is **Spring Boot**'s `AutoConfigurationImportSelector`: it implements `DeferredImportSelector` to drive auto-configuration.

Boot's idea is that application configuration is processed first, and then Boot picks appropriate defaults/auto-configurations based on classpath, properties, exclusions, and metadata ordering. Mechanisms like `@ConditionalOnMissingBean` can let default beans step aside when the application declares its own bean under valid conditions.

Three distinctions are essential:

1. `AutoConfigurationImportSelector` belongs to **Spring Boot**, not the plain `spring-context` dependency of this demo.
2. `@ConditionalOnMissingBean` is a **Spring Boot** annotation, not Spring Core's `@Conditional`.
3. Boot provides its own candidate discovery, ordering, filtering, and condition evaluation logic; `DeferredImportSelector` itself **does not implement those policies**.

**Never assume** a custom deferred selector automatically knows every registered bean definition or can “wait until the end” and avoid all conflicts.

## 13. How DeferredImportSelector Differs from Other Timing Mechanisms

| Tool | Primary Timing or Responsibility |
| --- | --- |
| `ImportSelector` | Selects imports during normal parsing |
| `DeferredImportSelector` | Selects imports later during configuration parsing |
| `DeferredImportSelector.Group` | Aggregates/filters/sorts selector imports |
| `ImportBeanDefinitionRegistrar` | Registers `BeanDefinition`s via API |
| `BeanFactoryPostProcessor` | Modifies metadata/definitions before regular beans are created |
| `BeanPostProcessor` | Processes bean instances during their lifecycle |
| `@Lazy` | Defers singleton bean instantiation when applicable |
| `ObjectProvider<T>` | Deferred dependency lookup when requested by caller |
| `@DependsOn` | Constrains initialization order at the bean-definition level |
| `@Async` | Runs method calls via async infrastructure |
| `ContextRefreshedEvent` | Event fired after context refresh |
| Boot auto-configuration | Selects/registers defaults under Boot conditions |

**A deferred selector is not a scheduler, async executor, or post-startup lifecycle callback.**

## 14. Common Mistakes and How to Diagnose Them

### Mistake 1 — Assuming Deferred-Imported Beans Are Only Created After Refresh

Deferred imports are still processed during configuration processing inside `refresh()`. Eager singleton beans can still be instantiated before `refresh()` finishes.

### Mistake 2 — Calling getBean Inside a Selector

`getBean()` can trigger premature object creation before infrastructure is ready, or observe an incomplete state. Prefer metadata/`Environment` and the right extension point.

### Mistake 3 — Assuming BeanFactory Holds All Final Definitions

When a deferred selector runs, the parser may have discovered `@Bean` methods while the reader has not finished registering them yet. `containsBeanDefinition(...)` at that point cannot be assumed to represent the final registry.

### Mistake 4 — selectImports Returning Bean Names Instead of Class Names

`selectImports` returns fully qualified **class names**. Use `TargetConfig.class.getName()`. For Java nested classes, this avoids binary-name bugs.

### Mistake 5 — Group Forgetting to Call selector.selectImports

A custom `Group.process` is responsible for collecting results per its contract. If the group neither calls the selector nor produces entries itself, imports end up empty even when the selector has logic in `selectImports`.

### Mistake 6 — Returning String[] from Group.selectImports

A Group must return `Iterable<Group.Entry>`, not `String[]`. Each Entry holds importer metadata and target class name.

### Mistake 7 — Using @Order to Force Bean Instantiation Order

`Ordered`/`@Order` on a selector controls selection precedence, not constructor/factory-method order of singletons. Use dependency injection or intentional lifecycle mechanisms.

### Mistake 8 — Failing to Load the Root Configuration

If the class carrying `@Import(MySelector.class)` is never registered/imported/scanned into the context, the selector never runs. Check the composition root and annotations.

### Mistake 9 — Thinking Group Deduplication Prevents Duplicate Bean Types

Two different configuration classes can still create duplicate bean names or return the same interface. Check bean overriding, `@Primary`, and `@Qualifier`.

### Mistake 10 — Confusing Boot Conditionals with Core Conditionals

`@ConditionalOnMissingBean` is a Boot API. A project with only Spring Framework dependencies does not have that annotation. Conditions depending on beans must be evaluated in the right phase.

### Mistake 11 — Using DeferredImportSelector for Hot Plugin Loading

Deferred imports are decided when the context is built; they do not dynamically add plugins into the registry after the application is running.

### Mistake 12 — Writing Selectors with Heavy Side Effects

Making network or DB calls, opening connection pools, or writing data inside `selectImports` slows startup and makes contexts hard to test. Selectors should be as pure and metadata-driven as possible.

### Mistake 13 — Testing Selector Timing via Constructor Order

If you want to measure selector timing, record events directly in `selectImports` or the Group. Constructors/`@PostConstruct` run in a different phase governed by the bean graph.

### Mistake 14 — Believing Deferred Runs Strictly in One Pass

Imported configurations can contain nested imports that yield new candidates. Treat deferred as a parser phase capable of processing further metadata, not an immutable list executed once in every case.

## 15. Effective Testing Practices

Tests should be split into two layers:

**Testing the selection phase:** create a minimal context containing only the configuration and selectors under study, record events in callbacks, and assert normal selectors run before the deferred group where the fixture applies. With multiple Groups or `Ordered`, verify the exact ordering relationship required by policy.

**Testing registration results:** after `refresh()`, use `containsBean`, `getBean`, or `getBeanNamesForType` to verify the expected bean was selected. If a class was selected by the selector yet filtered out by `@Conditional`, inspect the condition rather than concluding the selector failed to run.

A snippet retrieving a bean from the demo:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
                 DeferredDemo.RootConfig.class)) {

    System.out.println(
            context.containsBean("deferredMessage"));
}
```

This compiles using the demo package and importing `AnnotationConfigApplicationContext`, printing `true`. However, it **only** checks bean presence after refresh; recorded events are the evidence of timing.

### Useful Variations to Experiment With

- Change `DeferredSelector` to a normal `ImportSelector`: the group callbacks will no longer be called.
- Keep the deferred selector but remove the `getImportGroup()` override: Spring still processes it deferred, just without a custom group.
- Create two deferred selectors returning the same Group class: verify `Group.process` receives metadata from both importers.
- Use `Ordered` with different precedences: record callback order in a separate test without inferring bean creation order.
- Add `@Lazy` to a bean in deferred config: bean instantiation timing changes, yet **the selector still runs during parsing**.
- Add an Environment-based `@Conditional` on the imported configuration: observe both callbacks and final bean registration.

## 16. Self-Check Questions

**Q1.** What is the most important difference between `ImportSelector` and `DeferredImportSelector`?

**A:** When the parser selects imports: a deferred selector is collected and processed after regular configuration parsing in that pass.

**Q2.** Does a deferred import guarantee its bean is instantiated only after the context finishes starting up?

**A:** No. Eager singletons can still be instantiated during the same `refresh()`.

**Q3.** Whose class annotation metadata does `selectImports` receive?

**A:** The configuration class that imported the selector.

**Q4.** Is a selector returning `"paymentClient"` instead of a fully qualified configuration class name valid?

**A:** No. `selectImports` must return valid class names.

**Q5.** If a Group does not call `selector.selectImports(...)`, does Spring automatically call it beforehand prior to `Group.process`?

**A:** Do not assume that. The Group coordinates processing; it must produce the final `Entry` items according to its designed logic.

**Q6.** What is `Group.Entry` used for?

**A:** Holding the importer's annotation metadata together with the selected class name so the parser processes it with the right context.

**Q7.** Does `@Order` on a deferred selector force that selector's beans to be instantiated first?

**A:** No. Ordering belongs to the selection phase and does not guarantee constructor ordering.

**Q8.** Why does Spring Boot use `AutoConfigurationImportSelector`?

**A:** To select auto-configurations during the deferred phase, combined with Boot's filtering, ordering, and conditional mechanisms.

**Q9.** How can you verify a selector truly runs late?

**A:** Record events in both a normal selector and the deferred selector/Group, then compare callback positions in an integration test.

**Q10.** If you want to delay a client from connecting until it is actually used, what should you do?

**A:** Use `@Lazy` or an appropriate lookup mechanism, and design the client's lifecycle and connection policy; do not use `DeferredImportSelector` as a substitute.

## 17. Official Documentation

- [Spring Framework DeferredImportSelector API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html): deferred execution contract, ordering, and Group.
- [Spring Framework DeferredImportSelector.Group API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.Group.html): `process`, `selectImports`, `Entry`.
- [Spring Framework ImportSelector API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html): selector return type, metadata, and exclusion filter.
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import` mechanics when composing configurations.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): distinguishing metadata post-processing from bean instance post-processing.
- [Spring Boot AutoConfigurationImportSelector API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html): application of deferred selection in Boot.

**Conclusion:** `DeferredImportSelector` defers **import selection during the configuration parsing phase**, not **bean initialization** to runtime. `DeferredImportSelector.Group` allows coordinating multiple import results under a shared policy. Measure timing via **parser/selector callbacks**, and always keep metadata-processing timing separate from bean instantiation timing.
