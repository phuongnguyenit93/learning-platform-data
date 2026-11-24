# AutoConfigurationImportSelector in the @Import Processing Chain

> **Context:** Spring Boot 3.3.x (Java 17+, Spring Framework 6.1). This lesson explains **how Spring Boot brings auto-configurations into `@Import` processing**, focusing on `AutoConfigurationImportSelector`, deferred import timing, candidate discovery, exclusions, filtering, and ordering. The goal is to read the activation mechanism and diagnose why an auto-configuration is or is not applied.

## 1. Prerequisite: Auto-Configuration Is a Branch of @Import

Spring Framework's `@Import` can declare:
- A `@Configuration` class or a class containing valid bean definitions;
- An `ImportSelector`, i.e., an object that **selects class names to import**;
- An `ImportBeanDefinitionRegistrar`, i.e., an object that directly participates in registering bean definitions.

These are Spring Framework mechanisms. Spring Boot builds its auto-configuration feature on the **`ImportSelector`** branch, specifically `AutoConfigurationImportSelector`.

When you write:

```java
@SpringBootApplication
public class DemoApplication {
}
```

`@SpringBootApplication` already includes `@EnableAutoConfiguration`; and `@EnableAutoConfiguration` uses:

```java
@Import(AutoConfigurationImportSelector.class)
```

These two snippets are **explanatory annotation excerpts**, not two standalone Java files. Meaning: the application activates a selector, and the selector returns auto-configuration classes to pass into configuration parsing. Spring Framework continues processing those classes and decides which bean definitions get registered.

Key point: `AutoConfigurationImportSelector` **is not a business bean**, nor is it **where all default beans are directly instantiated**. It selects **configuration classes**; afterward, Spring processes `@Bean`, `@Conditional...`, and the bean creation steps.

## 2. Flow Diagram from Application to Beans

```text
SpringApplication.run(...)
        |
        v
ApplicationContext.refresh()
        |
        v
ConfigurationClassPostProcessor
        |
        v
ConfigurationClassParser reads application configuration
        |
        +-- @SpringBootApplication
              |
              +-- @EnableAutoConfiguration
                    |
                    +-- @Import(AutoConfigurationImportSelector.class)
                          |
                          +-- DeferredImportSelector
                                 (processed after ordinary configurations)
                                   |
                                   +-- AutoConfigurationGroup
                                        |
                                        +-- find candidates from .imports
                                        +-- deduplicate, exclude, import filter
                                        +-- merge, order
                                        |
                                        v
                              list of configurations to import
                                        |
                                        v
                   Spring parses @Configuration / @Conditional
                                        |
                                        v
                        register matching bean definitions
                                        |
                                        v
                       instantiate beans by dependencies
```

This is a **conceptual diagram**, not claiming every step happens in a single sequential stack frame. Spring performs multiple passes of configuration parsing and import processing; in execution, deferred selectors are collected and processed via groups.

Distinguish three milestones:

1. **Candidate selection**: the class name is in the list of auto-configurations eligible for consideration.
2. **Import and condition evaluation**: Spring reads metadata, parses configurations, and registers only matching bean definitions.
3. **Bean instantiation**: Spring creates actual objects when their turn arrives, based on dependencies and context lifecycle.

Having a candidate **does not mean** the class is imported; a class being imported **does not mean** every `@Bean` in the class is registered; having a bean definition **does not mean** the object instantiated successfully.

## 3. Why Is AutoConfigurationImportSelector a DeferredImportSelector?

`AutoConfigurationImportSelector` implements `DeferredImportSelector`, a variant of `ImportSelector`. Under Spring Framework's contract, deferred selectors are processed **after ordinary `@Configuration` classes have been parsed**, which suits configurations whose conditions depend on configuration provided by the application.

Comparison:

| Import Type | Effect | Relative Timing |
| --- | --- | --- |
| `@Import(SomeConfiguration.class)` | Imports a named configuration | While Spring parses the configuration holding the import |
| Regular `ImportSelector` | Computes a set of classes to import | During regular import processing |
| `DeferredImportSelector` | Defers selection to the deferred import phase | After ordinary configurations are parsed; can group via `Group` |
| `AutoConfigurationImportSelector` | Selects and orders auto-configurations for Spring Boot | Goes through `DeferredImportSelector` and `AutoConfigurationGroup` |

This deferral has practical value: auto-configuration often uses `@ConditionalOnMissingBean` to **back off** when the application author declares a bean themselves. If default configurations were processed too early, condition results against bean definitions could differ from what is intended.

However, `DeferredImportSelector` does not mean **every bean has already been instantiated** before auto-configuration runs. This is primarily the order of **configuration parsing / bean definition registration**, not object instantiation order.

### 3.1. Position in Spring's Processing Layer

Spring Framework uses `ConfigurationClassPostProcessor` to recognize and process configurations. During that process, `ConfigurationClassParser` reads `@Import` and recognizes classes implementing `DeferredImportSelector`. Deferred selectors are held for processing in the appropriate phase, optionally using `DeferredImportSelector.Group` to coordinate results.

When `AutoConfigurationImportSelector` is detected, Spring can supply `BeanClassLoader`, `BeanFactory`, `Environment`, and `ResourceLoader` via the `Aware` interfaces the selector implements. The selector needs these to read candidate resources, exclusion properties, metadata, and Boot filters.

You do not manually call `new AutoConfigurationImportSelector()` or `selectImports()` in an ordinary application. It is infrastructure triggered by `@EnableAutoConfiguration` via `@Import`.

## 4. Key Methods of AutoConfigurationImportSelector

Read by **responsibility** rather than memorizing every line of source:

| API / Component | Responsibility |
| --- | --- |
| `selectImports(AnnotationMetadata)` | `ImportSelector` API shape, returns class names when not going through the group mechanism |
| `getImportGroup()` | Provides `AutoConfigurationGroup` so deferred selectors in the same group can merge results |
| `getAutoConfigurationEntry(AnnotationMetadata)` | Computes candidates and exclusions for one selection pass |
| `getCandidateConfigurations(...)` | Retrieves auto-configuration class names from imports metadata |
| `getExclusions(...)` | Retrieves configuration names to exclude from annotation and environment |
| `getAutoConfigurationImportFilters()` | Retrieves import filters that can reject candidates early |
| `AutoConfigurationGroup.process(...)` | Collects entries supplied by selectors in the group |
| `AutoConfigurationGroup.selectImports()` | Merges, removes exclusions, orders, and returns entries to import |

In Spring Boot's usual **group** path, do not imagine Spring simply calls `selectImports()` once and uses the result directly. `Group.process(...)` retrieves `AutoConfigurationEntry`; `Group.selectImports()` returns the final list after merging and ordering. This is easy to miss when reading the call graph by searching only for usages of `selectImports()`.

### 4.1. Meaning of AutoConfigurationEntry

`AutoConfigurationEntry` is an internal data structure of the selector containing:
- `configurations`: candidate classes remaining after entry-level filtering steps;
- `exclusions`: classes requested to be excluded.

When multiple selector passes occur in the same group, the group collects entries, removes all applicable exclusions, and orders the combined list. Applications do not create or modify `AutoConfigurationEntry` themselves; this is not a business configuration API.

## 5. From Metadata to the Candidate List

With Spring Boot 3.x, an auto-configuration library registers candidates using the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example content:

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.greeting.autoconfigure.GreetingMetricsAutoConfiguration
```

Each line is a **fully qualified name** of a configuration class. Spring Boot uses `ImportCandidates` to read matching files from JARs on the classpath; therefore **dependencies / runtime classpath and ClassLoader** determine which resources this mechanism sees.

Points to remember:
- `@AutoConfiguration` marks a class as auto-configuration, yet **by itself does not make Boot find the class** if the JAR lacks the appropriate imports file.
- The imports file **declares candidates**; it does not guarantee the class will ultimately be selected.
- Duplicate class names can appear across multiple resources; the selector deduplicates names.
- Spring Boot 3.x does not use the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `META-INF/spring.factories` as the **primary auto-configuration candidate** registration path like older versions. However, `spring.factories` can still serve other extension points, such as certain import filters/listeners.
- The imports file must exist inside the **actual artifact** the consuming application uses. Having it in source yet omitting it when packaging the JAR leaves no candidate.

### 5.1. "Dependency Present" Is Not Enough for a Bean to Exist

Adding a starter can put core libraries, adapters, and the imports file onto the runtime classpath, yet multiple layers of conditions remain:

```text
Is the JAR on the runtime classpath?
   | yes
   v
Does AutoConfiguration.imports contain the class name?
   | yes
   v
Is the candidate free of exclusions and early filters?
   | yes
   v
Does the configuration pass its @Conditional checks?
   | yes
   v
Does the @Bean method pass its @Conditional checks?
   | yes
   v
Bean definition is registered; bean is then created when needed
```

A non-matching `@ConditionalOnClass` may be rejected early by a metadata-backed filter, or when Spring evaluates configuration conditions. `@ConditionalOnMissingBean` is typically evaluated while processing the corresponding bean definitions. **Do not treat import filters, class conditions, and bean conditions as one identical operation.**

## 6. Candidate Selection Chain: Deduplicate, Exclude, Filter, Order

Consider the logical processing path of `getAutoConfigurationEntry(...)` in Spring Boot 3.3:

1. **Check whether auto-configuration is enabled**. `spring.boot.enableautoconfiguration=false` can disable Boot's default auto-configuration selection.
2. **Read `@EnableAutoConfiguration` attributes** from the annotation metadata of the importing class.
3. **Retrieve candidates** from available `AutoConfiguration.imports` files.
4. **Remove duplicate names** in the candidate list.
5. **Collect exclusions** from `exclude`, `excludeName`, and the `spring.autoconfigure.exclude` property.
6. **Check for invalid exclusions** according to selector rules. Excluding a class that is present yet not a valid auto-configuration candidate can cause startup failure.
7. **Remove excluded candidates** from the active list.
8. **Run `AutoConfigurationImportFilter`s** to weed out ineligible configurations based on metadata.
9. **Publish import events** to configured `AutoConfigurationImportListener`s.
10. **Return AutoConfigurationEntry**.

Afterward, in `AutoConfigurationGroup.selectImports()`, results from multiple entries are merged, exclusions are applied across the combined set, and auto-configurations are **ordered** according to metadata before actually being imported.

This is the **conceptually meaningful** order of the Spring Boot 3.3 branch; the source code includes helper classes, caches, and implementation details omitted here.

### 6.1. What Are the Sources of Exclusions?

In an application:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class ExampleApp {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApp.class, args);
    }
}
```

This is a **separate illustrative program**, requiring a dependency containing `DataSourceAutoConfiguration` and not part of the demo project in section 8. `@SpringBootApplication(exclude=...)` provides annotation-based exclusion.

An equivalent configuration option in intent:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

If the class cannot be referenced in source (e.g., an optional dependency), you can use `excludeName` with the fully qualified name. Exclude only when you understand the impact on related configurations, not as a random attempt to "fix startup".

**Distinction:** `spring.autoconfigure.exclude` removes only **the named auto-configurations**. `spring.boot.enableautoconfiguration=false` is a broader switch for the default auto-configuration selection mechanism. Neither replaces removing `@Configuration` classes directly imported by the application.

### 6.2. How Does AutoConfigurationImportFilter Differ from ConditionalOnClass?

`AutoConfigurationImportFilter` is a **candidate-list filtering** extension point. Boot can leverage pre-prepared metadata to quickly reject many candidates before parsing configuration classes in detail.

`@ConditionalOnClass` is a **conditional annotation** on a configuration or bean. Some classpath condition data can be optimized for early filtering, yet the final condition still relies on Spring's evaluation pipeline.

Do not infer that any arbitrary `@Conditional` annotation is understood and fully processed by the selector. For example, a condition based on application-defined beans requires bean definition context, so it is typically evaluated when Spring processes configurations/bean definitions, not when initially reading candidate names from imports.

## 7. AutoConfigurationGroup and Processing Order

Reasons Boot uses `DeferredImportSelector.Group`:
- Collect multiple deferred selector results in the same group;
- Merge candidates and exclusions;
- Order auto-configurations according to declared ordering relationships.

For example, given two auto-configurations:

```java
@AutoConfiguration(beforeName = "com.example.feature.FeatureAutoConfiguration")
class CoreAutoConfiguration {
}

@AutoConfiguration(afterName = "com.example.core.CoreAutoConfiguration")
class FeatureAutoConfiguration {
}
```

This is an **illustrative ordering snippet**, not standalone compilable source: the two classes belong to different packages and thus need separate files, imports entries, and corresponding dependencies. `beforeName` and `afterName` are useful when you want to avoid compile-time references to other classes.

There are also `before`, `after`, `@AutoConfigureBefore`, `@AutoConfigureAfter`, and `@AutoConfigureOrder`. This metadata affects **the order in which configurations are evaluated / bean definitions are registered**. It **does not guarantee bean instance creation order**. Instantiation depends on the dependency graph, lazy behavior, `@DependsOn`, and Spring's lifecycle.

The difference is especially important with `@ConditionalOnMissingBean`: the condition sees bean definitions already processed up to the moment of evaluation. If two independent auto-configurations both attempt to create a default bean of the same type, make ordering or precedence explicit; do not rely on arbitrary JAR ordering on the classpath.

## 8. Runnable Demo: Proving @EnableAutoConfiguration Goes Through Imports

This hands-on exercise uses **Spring Boot 3.3.13 / Java 17 / Maven**. A single Maven project holds both application code and the auto-configuration class to clearly observe discovery; when publishing a real library, separate library code from the consuming application.

### 8.1. File Structure

```text
selector-flow-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── greeting/
    │   │       ├── GreetingService.java
    │   │       └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/greeting/autoconfigure/
            └── GreetingAutoConfigurationTest.java
```

`com.example.app` and `com.example.greeting` are **two sibling package branches**. Because `DemoApplication` is in `com.example.app`, default component scan does not automatically scan `com.example.greeting.autoconfigure`. The auto-configuration appears solely through the imports mechanism.

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>selector-flow-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

The parent provides dependency management appropriate for the Spring Boot 3.3 line. If a real project uses a newer version, check the corresponding API before relying on internal selector details.

### 8.3. Neutral Business API

`src/main/java/com/example/greeting/GreetingService.java`

```java
package com.example.greeting;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
```

The greeting contract has no dependency on Spring. `@FunctionalInterface` simply lets the compiler verify there is one abstract method for lambda usage.

### 8.4. Auto-Configuration Conditionally Creating a Default Bean

`src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java`

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return name -> "Xin chào, " + name + "!";
    }
}
```

There are **two decision layers** here:
- The selector picks the **name** `GreetingAutoConfiguration` because it is in the imports resource and not excluded.
- Spring evaluates `@ConditionalOnClass`, `@ConditionalOnProperty`, and then `@ConditionalOnMissingBean` before registering the default bean.

`@ConditionalOnMissingBean` allows the app to supply its own bean; `matchIfMissing=true` means an absent `demo.greeting.enabled` property is treated as enabled, provided other conditions pass.

### 8.5. Candidate Discovery Resource

Create the exact file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
```

This is the link from `AutoConfigurationImportSelector` to the library's auto-configuration class. If you omit this resource, the app's main class still has `@EnableAutoConfiguration`, yet **the demo's own** auto-configuration will not be discovered. Other auto-configurations provided by Spring Boot can still load as normal.

### 8.6. ApplicationRunner Observing Whether the Bean Exists

`src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.example.greeting.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showGreeting(ObjectProvider<GreetingService> services) {
        return args -> {
            GreetingService service = services.getIfAvailable();
            System.out.println(service == null
                    ? "GREETING=ABSENT"
                    : service.greet("Lan"));
        };
    }
}
```

`ObjectProvider` lets the runner execute even when auto-configuration does not register a bean. There is no need to import `GreetingAutoConfiguration` directly into `DemoApplication`.

Run inside the project directory:

```bash
mvn test
mvn spring-boot:run
```

When the default is enabled, the program prints one line:

```text
Xin chào, Lan!
```

This is the line from `ApplicationRunner`, **not the entire stdout** (Maven and Spring Boot also print startup logs).

If run with the disable property:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.greeting.enabled=false
```

The line printed by the runner is:

```text
GREETING=ABSENT
```

Because the property condition fails to match, the configuration does not create `GreetingService`. This **does not mean** the selector failed to find the candidate; the selector still picks the class via imports, while Spring skips it in the condition phase.

### 8.7. Application Supplies Its Own Bean: Auto-Configuration Backs Off

Add the following method **inside `DemoApplication`** from section 8.6:

```java
@Bean
GreetingService customGreetingService() {
    return name -> "App chào " + name + "!";
}
```

This is an **addition to an existing class**, not a standalone Java file. Run without the disable property. When the app already registers a bean of the same type, the default bean from auto-configuration is not registered due to `@ConditionalOnMissingBean`; the runner's output line is:

```text
App chào Lan!
```

The key takeaway for understanding deferred imports: the application gets the chance to declare its own beans, and then default configuration evaluates conditions accordingly. **Bean definition registration order** is what matters here, rather than waiting for the app to instantiate objects first.

## 9. Testing Branches with ApplicationContextRunner

Create `src/test/java/com/example/greeting/autoconfigure/GreetingAutoConfigurationTest.java`:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void createsDefaultWhenAllowed() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("Lan"))
                    .isEqualTo("Xin chào, Lan!");
        });
    }

    @Test
    void doesNotCreateWhenDisabled() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(GreetingService.class));
    }

    @Test
    void backsOffToConsumerBean() {
        runner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("Lan"))
                            .isEqualTo("Consumer: Lan");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        GreetingService consumerGreetingService() {
            return name -> "Consumer: " + name;
        }
    }
}
```

Run `mvn test`; the three tests verify that the default bean can be registered, blocked by a property, or back off for a consumer bean.

**Test limitation:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` supplies the class directly and **does not by itself prove that `AutoConfigurationImportSelector` discovers the class via the imports resource**. To verify the full `@Import` path, run the real `DemoApplication` or add an integration test that boots the application and inspects the JAR contents.

### 9.1. Checking That the Resource Is Packaged

Using Maven:

```bash
mvn package
jar tf target/selector-flow-demo-0.0.1-SNAPSHOT.jar
```

The listing must include `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside `BOOT-INF/classes/` of the executable JAR. When packaged as a regular library JAR, the resource sits under the corresponding `META-INF/spring/...` path. For this demo project, `jar tf` can print many entries; what matters is the resource's presence and exact class name.

## 10. Diagnosing Accurately: Candidate Not Selected or Bean Not Created?

When "adding a starter yet not seeing a bean", divide into cases:

| Symptom | What to Check | Do Not Jump to Conclusion |
| --- | --- | --- |
| Auto-configuration missing from candidate list | JAR, runtime classpath, imports resource, ClassLoader | "`@ConditionalOnMissingBean` removed the candidate" |
| Candidate dropped via exclusion | `@SpringBootApplication(exclude=...)`, `excludeName`, `spring.autoconfigure.exclude` | "Missing dependency so I must add a starter" |
| Configuration class appears in negative matches | `@ConditionalOnClass`, `@ConditionalOnProperty`, web condition, resource condition | "Selector is broken" |
| Default bean missing even though configuration matched | `@ConditionalOnMissingBean`, bean method condition, app's own bean | "Auto-configuration failed to import" |
| Bean definition exists yet startup fails | Exception during bean creation, missing runtime class, config/credentials | "Condition did not match" |
| Auto-configurations run in an unexpected order | `before/after`, `@AutoConfigureOrder`, metadata, other dependencies | "JAR order on classpath decides everything" |

You can enable the condition evaluation report:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

When reading the report, distinguish:
- **Positive matches**: configurations/conditions that matched;
- **Negative matches**: conditions that did not match;
- **Exclusions**: excluded auto-configurations;
- **Unconditional classes**: auto-configurations without relevant report-level conditions.

Exact section headings and formatting depend on the patch version. `--debug` is for diagnostics only; output can be lengthy.

If Actuator is present and endpoints are properly secured, `/actuator/conditions` can provide the condition report. Do not expose configuration/condition details carelessly in production.

### 10.1. Reading Two Similar-Looking Scenarios

**Scenario A — missing imports resource:** the library contains `GreetingAutoConfiguration.class`, yet the published JAR lacks `AutoConfiguration.imports`. The selector does not have that class name to pick. Adding `@ConditionalOnClass` to the class will not fix a **candidate discovery** failure.

**Scenario B — imports present yet property disabled:** the selector has the candidate, yet `@ConditionalOnProperty(demo.greeting.enabled=true)` fails. Editing the imports file alone will not make the bean appear; fix the property or explicitly provide a bean.

Both scenarios end with `GreetingService` absent, yet their root causes lie in **two different phases**.

## 11. Common Misconceptions When Reading the Source

1. **"`@Import` only imports classes written directly in the annotation."** No. `@Import` can import an `ImportSelector`, and the selector returns a computed list of classes.
2. **"`selectImports()` is always where the final result is returned."** With `DeferredImportSelector.Group`, results can flow through `Group.process(...)` and `Group.selectImports()`; Spring Boot uses the group path to merge, exclude, and sort.
3. **"The imports resource is a list of beans."** Wrong. It is a list of **auto-configuration class names**. Beans are determined when Spring processes the configurations.
4. **"If a class is in imports, it is guaranteed to register."** No. Exclusions, filters, and conditions can drop the class or bean.
5. **"Deferred means the application has finished instantiating all beans."** No. It is a mechanism that defers **imports during the configuration parsing phase**.
6. **"`@AutoConfiguration(after=...)` forces beans to be instantiated later."** No. It governs the order in which configurations are applied; bean instantiation order depends on the dependency graph and lifecycle.
7. **"Just adding a dependency tells you the selector ran."** No. You must verify `@EnableAutoConfiguration`, the imports resource, and the condition report.
8. **"To make a library's configuration discoverable, you must `@ComponentScan` its package."** No. Library auto-configuration should sit outside application component scanning and be declared via the imports resource.
9. **"Excluding removes the dependency too."** No. Exclusion only drops the corresponding auto-configuration; classes/JARs may remain on the runtime classpath and the application can still use them directly.
10. **"All `@Conditional` annotations are processed in one pass inside the selector."** No. Import filters are candidate-level optimizations; many conditions are still evaluated by Spring when parsing configurations or registering bean definitions.

## 12. Post-Lesson Check Questions

**Question 1.** Why can `@SpringBootApplication` activate hundreds of auto-configurations even without hundreds of `@Import(SomeClass.class)` entries on the application class?

Because `@SpringBootApplication` includes `@EnableAutoConfiguration`; that annotation imports a **selector**. The selector discovers candidates from resources on the classpath and supplies the list of configuration classes.

**Question 2.** Why does `AutoConfigurationImportSelector` need deferred import?

Because auto-configurations are conditional defaults that often need to inspect bean definitions already declared by the application; deferring parsing lets the back-off mechanism work properly within standard Spring configuration processing.

**Question 3.** Do `AutoConfiguration.imports` and `@ConditionalOnMissingBean` decide the same thing?

No. Imports decides **which candidate configurations can be discovered**; the bean condition decides **whether a bean definition should be registered**.

**Question 4.** If `GreetingAutoConfiguration` is selected yet `demo.greeting.enabled=false`, why is no bean visible?

Because the class was discovered, yet the condition during configuration processing did not match. This is expected behavior, not a candidate discovery failure.

**Question 5.** Does `@AutoConfiguration(afterName=...)` guarantee that the bean's constructor runs after the other bean?

No. The metadata orders auto-configurations; object instantiation order is determined by Spring dependency resolution and lifecycle.

**Question 6.** Does a passing `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` test prove the imports file is correct?

No. The runner is given the auto-configuration class directly. You must inspect the JAR/resource and run a real consuming application to verify the selector discovery path.

## 13. Mental Model Summary

`AutoConfigurationImportSelector` sits at **the bridge between Spring Framework's `@Import` and Spring Boot's auto-configuration metadata**. It reads candidates, removes exclusions, runs filters, merges/sorts via the group, and hands eligible configuration classes back to Spring's processing pipeline. Only then does Spring evaluate conditions, register bean definitions, and instantiate beans according to actual dependencies.

Remember this debugging question order:

```text
Does the application have @EnableAutoConfiguration?
  -> Does the selector see AutoConfiguration.imports?
  -> Was the candidate excluded/filtered?
  -> Did the configuration pass @Conditional?
  -> Did the bean method pass @Conditional?
  -> Did the bean instantiate successfully?
```

### Official Resources

- Spring Boot 3.3 Javadoc — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Spring Framework 6.1 Javadoc — `DeferredImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Framework 6.1 Javadoc — `ImportSelector`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html
