# Tracing @Import and Nested Configurations by Selection Branch

## Learning Objectives

When reading Spring Boot auto-configuration code, a bean often does not appear directly in the first configuration class you open. The root configuration may use `@Import` to bring in additional classes, an `ImportSelector` may choose classes based on metadata or environment, and nested `@Configuration` classes may only be processed when their corresponding conditions match.

This lesson shows how to **trace a configuration path from its entry point down to the final bean**. The focus is the relationship among `@Import`, `ImportSelector`, `DeferredImportSelector`, nested configurations, and the conditions on each branch.

After this lesson, you will be able to:

- Distinguish direct class imports from imports via a selector or registrar.
- Trace a configuration branch from `@EnableAutoConfiguration` or a root configuration class.
- Understand why a nested configuration may not be processed when conditions do not match.
- Distinguish configuration parsing time, bean definition registration, and bean instantiation.
- Use `ApplicationContextRunner` to verify individual branches without starting the whole application.
- Find the exact places in Spring Framework and Spring Boot source code when explaining why a bean appears or is skipped.

## 1. Starting from the Entry Point: Who Brings the Configuration into the Context?

A class annotated with `@Configuration` is not automatically present in every application context. It must be discovered by Spring through an appropriate mechanism, such as:

- Registered directly when creating the context.
- Found by component scanning.
- Brought in by another configuration class via `@Import`.
- Returned by an `ImportSelector` or `DeferredImportSelector`.
- Registered via an auto-configuration mechanism such as Spring Boot.

In a typical Spring Boot application, `@SpringBootApplication` includes `@EnableAutoConfiguration`. Boot's auto-configuration mechanism introduces a `DeferredImportSelector` into the configuration processing pipeline. This selector locates the list of auto-configuration candidates, applies exclusions and appropriate condition filters, and passes the selected classes into parsing.

Therefore, when tracing a bean, do not start by searching for the bean name across the entire repository and stopping at the `@Bean` method. Ask first: **by what path was the class containing that method brought into the context?**

### Overall Diagram

~~~text
@SpringBootApplication
        |
        +-- @EnableAutoConfiguration
        |       |
        |       +-- AutoConfigurationImportSelector
        |               |
        |               +-- reads AutoConfiguration.imports
        |               +-- filters/excludes/orders candidates
        |               +-- selects auto-configurations
        |
        +-- application-declared @Configuration classes
                |
                +-- direct @Import
                |       +-- Configuration class
                |       +-- ImportSelector
                |       +-- ImportBeanDefinitionRegistrar
                |
                +-- nested @Configuration
                        +-- evaluates conditions
                        +-- processes matching branch
~~~

This is a conceptual diagram. Actual flows may nest multiple levels of imports and conditions; not every application uses all branches above.

## 2. Four Forms of Import to Recognize

### 2.1. Directly Importing a Configuration Class

~~~java
@Configuration(proxyBeanMethods = false)
@Import(TransportConfiguration.class)
class ApplicationFeatureConfiguration {
}
~~~

Spring treats `TransportConfiguration` as a configuration source to process. If that class itself has `@Import`, Spring continues following the new imports. This is the easiest form to read when the set of classes to include is known at compile time.

Multiple classes can be imported:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
    HttpTransportConfiguration.class,
    RetryConfiguration.class
})
class ApplicationFeatureConfiguration {
}
~~~

Declaring a class in `@Import` does not mean every bean method inside it is guaranteed to be registered: the configuration class is still governed by its conditions and each bean method's own conditions.

### 2.2. Importing a Regular Class

`@Import` is not restricted to `@Configuration` classes. An imported class can be registered as a bean/component definition depending on its type and annotations. However, if the goal is to declare a group of `@Bean` methods and configuration conditions, use an explicit configuration class.

### 2.3. ImportSelector: Dynamically Selecting Classes

`ImportSelector` allows deciding which classes to import based on the `AnnotationMetadata` of the class importing the selector. The selector returns **fully qualified class names**, rather than directly creating beans.

~~~java
public class TransportImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[] {
            HttpTransportConfiguration.class.getName()
        };
    }
}
~~~

This is an illustrative snippet. You can read annotation metadata to choose classes based on attributes of an enabling annotation, or implement `Aware` interfaces to receive `Environment`, `ResourceLoader`, and other Spring-supported collaborators.

Usage:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(TransportImportSelector.class)
class TransportFeatureConfiguration {
}
~~~

When parsing `TransportFeatureConfiguration`, Spring invokes the selector to obtain the import list. The selector class is not an application business bean; its role is **to supply the list of imported configurations**.

### 2.4. DeferredImportSelector: Selecting After Regular Configurations

`DeferredImportSelector` extends `ImportSelector`, but is processed **after regular configurations have been parsed**. This is useful when selection depends on the overall configuration state that has already been read.

Spring Boot uses this mechanism in `AutoConfigurationImportSelector` to introduce auto-configurations after regular application configurations. Thanks to this, bean conditions in auto-configurations can be evaluated after user configurations have been processed according to the model Boot designed.

Do not use `DeferredImportSelector` just to make code look more flexible. Choose:
- `@Import(Config.class)` when the set of classes is fixed and known ahead of time.
- `ImportSelector` when the import list must be computed dynamically during the parse phase.
- `DeferredImportSelector` when import selection must happen after regular configurations, like the auto-configuration pipeline.
  
### 2.5. ImportBeanDefinitionRegistrar: Registering Definitions Programmatically

`ImportBeanDefinitionRegistrar` is an advanced mechanism for cases where you need to register `BeanDefinition` instances via container APIs instead of returning configuration class names. It receives a `BeanDefinitionRegistry` and can register definitions according to resolved metadata/conditions.

Do not use a registrar for every situation. If a `@Configuration` class with `@Bean` methods expresses the intent clearly, that approach is usually easier to read, test, and maintain.

## 3. Nested Configurations: Each Branch Has Its Own Conditions

A configuration class can declare static nested classes annotated with `@Configuration`. Spring can recognize these member configuration classes while processing the outer class. Each nested class can carry its own conditions so Spring only processes matching branches.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class TransportConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "http")
    static class HttpConfiguration {

        @Bean
        TransportClient httpTransportClient() {
            return () -> "http";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "queue")
    static class QueueConfiguration {

        @Bean
        TransportClient queueTransportClient() {
            return () -> "queue";
        }
    }
}
~~~

This is an illustrative snippet. `TransportClient` is an interface defined by the application/library. When `demo.transport.mode=http`, nested `HttpConfiguration` matches and registers the HTTP bean; the queue branch does not match. When the value is `queue`, the outcome is reversed.

**Nested configurations should be static.** A non-static inner class requires an enclosing class instance to be instantiated, which does not fit how Spring processes an independent configuration. Using `static` makes each branch an independent configuration that can be parsed and registered on its own.

### 3.1. Automatically Discovered Nested Configurations

When a nested class is a member configuration class of a `@Configuration` class, Spring can discover it while processing the outer class. Therefore, you do not always need to add `@Import(NestedClass.class)` for that nested member itself.

This matters when reading source: open the outer class, inspect the static nested classes annotated with `@Configuration`, and then check each class's conditions. A branch may be discovered yet skipped because its condition did not match.

### 3.2. Explicitly Imported Nested Configurations

Another approach is to keep nested classes inside a non-configuration holder class, then import individual branches:

~~~java
final class TransportBranches {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "http")
    static class HttpConfiguration {
        @Bean
        TransportClient httpTransportClient() {
            return () -> "http";
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.transport",
            name = "mode",
            havingValue = "queue")
    static class QueueConfiguration {
        @Bean
        TransportClient queueTransportClient() {
            return () -> "queue";
        }
    }
}

@Configuration(proxyBeanMethods = false)
@Import({
    TransportBranches.HttpConfiguration.class,
    TransportBranches.QueueConfiguration.class
})
class ImportedTransportConfiguration {
}
~~~

Here, the holder class `TransportBranches` only organizes source code; it is not a configuration itself. `ImportedTransportConfiguration` brings both branches into the context. Each branch decides for itself whether to be processed based on its conditions.

The two styles (auto-discovered member configurations and explicitly imported nested classes) serve different purposes. When reading code, check both **member class relationships** and `@Import` lists; do not conclude a nested class is unused just because it is absent from an imports array.

### 3.3. Class-Level Conditions and Method-Level Conditions

Class-level condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "demo.transport", name = "mode", havingValue = "http")
static class HttpConfiguration {
    @Bean
    TransportClient httpTransportClient() { ... }
    @Bean
    HttpMetrics httpMetrics() { ... }
}
~~~

If the class condition does not match, that configuration class is skipped, so the bean methods within that branch are not registered either.

Method-level condition:

~~~java
@Configuration(proxyBeanMethods = false)
static class HttpConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo.transport", name = "metrics", havingValue = "true")
    HttpMetrics httpMetrics() { ... }
}
~~~

Here, the configuration can still be processed and bean methods without their own condition can still be registered; only the `httpMetrics` bean is controlled by the condition.

When reading a branch, identify which conditions apply to the **entire class**, which apply to **a single bean method**, and whether conditions are inherited via outer/nested classes.

## 4. Tracing a Branch from @Import to Bean

Use a fixed sequence of questions:

1. **What is the entry point?** Who registers the root configuration: component scan, `@Import`, auto-configuration imports, or a test runner?
2. **Which form of import is used?** Direct class, selector, deferred selector, or registrar?
3. **Which classes are selected?** For a selector, read `selectImports(...)` and the conditions/metadata it uses.
4. **Are there nested branches?** Check static member `@Configuration` classes, nested imports, and transitively imported configurations.
5. **Which conditions are evaluated?** Read `@Conditional`, `@Profile`, `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean`.
6. **Which bean definitions are registered?** Locate the `@Bean` method, component, or registrar that created the definition.
7. **Is the bean actually instantiated?** Check the dependency graph, scope, lazy initialization, and creation errors.

Do not jump from step 1 to step 7. If a bean does not exist, the cause may lie in configuration selection or conditions long before reaching the constructor.

### Flow Map

~~~text
Root configuration
   |
   +-- @Import(Class)
   |       |
   |       +-- parse imported class
   |               |
   |               +-- further @Import / nested @Configuration
   |
   +-- @Import(ImportSelector)
   |       |
   |       +-- selectImports(metadata)
   |               |
   |               +-- parse returned class names
   |
   +-- @Import(DeferredImportSelector)
   |       |
   |       +-- processed after regular configurations
   |
   +-- class / nested branch condition
           |
           +-- condition does not match --> skip branch
           |
           +-- condition matches
                   |
                   +-- read @Bean methods / registrar
                           |
                           +-- register BeanDefinition
                                   |
                                   +-- dependency injection
                                           |
                                           +-- create instance
~~~

The diagram illustrates the logical steps; not every branch passes through every node.

## 5. Where to Read Spring Framework and Spring Boot Source Code

When you want to understand actual behavior rather than only reading annotations, open the exact implementation classes in order.

### 5.1. Spring Framework 6.1: Configuration Parsing

| Class / Method | Question to Answer |
| --- | --- |
| `ConfigurationClassPostProcessor#processConfigBeanDefinitions` | Who initiates processing of configuration bean definitions? |
| `ConfigurationClassParser#parse` | How are root configurations parsed? |
| `ConfigurationClassParser#processConfigurationClass` | How is a configuration class checked and processed? |
| `ConfigurationClassParser#doProcessConfigurationClass` | Where are annotations, imports, and member classes traversed? |
| `ConfigurationClassParser#processImports` | How are imported classes, selectors, and registrars branched? |
| `ConfigurationClassParser#processMemberClasses` | How are nested configuration classes discovered? |
| `ConditionEvaluator#shouldSkip` | In which phase are conditions evaluated, and when is a class skipped? |
| `ConfigurationClassBeanDefinitionReader#loadBeanDefinitions` | How are parsed configuration classes turned into bean definitions? |

Method names may vary across Framework versions; when reading code, open the tag/version matching your project's dependency. The names above are representative starting points for Spring Framework 6.1.

### 5.2. Spring Boot 3.3: Auto-Configuration Import

| Class / Component | Role |
| --- | --- |
| `@EnableAutoConfiguration` | Enables the auto-configuration mechanism in the application |
| `AutoConfigurationImportSelector` | Deferred selector feeding auto-configuration candidates into parsing |
| `AutoConfigurationImportSelector#getAutoConfigurationEntry` | Obtains candidates, exclusions, and filtering results |
| `AutoConfiguration.imports` | Resource listing the library's auto-configuration classes |
| `@AutoConfiguration` | Marks an auto-configuration class and declares ordering relationships |
| `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` | Filters classes/beans by condition |

When tracing a Boot auto-configuration, distinguish:
- **Candidate list:** is the class listed in the resource?
- **Selected list:** was the class excluded/filtered?
- **Configuration parsing:** was the class parsed, or did a condition skip it?
- **Bean registration:** was the class processed, yet a bean method had its own condition?
- **Bean creation:** does the definition exist, yet instance creation failed?

These are five distinct states. Looking at `AutoConfiguration.imports` alone is not enough to conclude a bean will exist.

## 6. Verification Example: @Import Nested Branches by Property

The complete test example below imports two nested configuration classes. Each branch is guarded by `@ConditionalOnProperty`. When HTTP is selected, only the HTTP bean is registered; when queue is selected, only the queue bean; for any other value, no branch is selected.

**File:** `src/test/java/example/trace/ImportBranchSelectionTest.java`

~~~java
package example.trace;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class ImportBranchSelectionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TransportConfiguration.class);

    @Test
    void selectsHttpBranch() {
        runner.withPropertyValues("demo.transport.mode=http")
                .run(context -> {
                    assertThat(context).hasSingleBean(TransportClient.class);
                    assertThat(context.getBean(TransportClient.class).mode())
                            .isEqualTo("http");
                    assertThat(context.containsBean("httpTransportClient")).isTrue();
                    assertThat(context.containsBean("queueTransportClient")).isFalse();
                });
    }

    @Test
    void selectsQueueBranch() {
        runner.withPropertyValues("demo.transport.mode=queue")
                .run(context -> {
                    assertThat(context).hasSingleBean(TransportClient.class);
                    assertThat(context.getBean(TransportClient.class).mode())
                            .isEqualTo("queue");
                    assertThat(context.containsBean("httpTransportClient")).isFalse();
                    assertThat(context.containsBean("queueTransportClient")).isTrue();
                });
    }

    @Test
    void selectsNoBranchForUnsupportedMode() {
        runner.withPropertyValues("demo.transport.mode=other")
                .run(context ->
                        assertThat(context).doesNotHaveBean(TransportClient.class));
    }

    @Test
    void selectsNoBranchWhenPropertyIsMissing() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean(TransportClient.class));
    }

    interface TransportClient {
        String mode();
    }

    static class TransportBranches {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.transport",
                name = "mode",
                havingValue = "http")
        static class HttpConfiguration {

            @Bean
            TransportClient httpTransportClient() {
                return () -> "http";
            }
        }

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.transport",
                name = "mode",
                havingValue = "queue")
        static class QueueConfiguration {

            @Bean
            TransportClient queueTransportClient() {
                return () -> "queue";
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
        TransportBranches.HttpConfiguration.class,
        TransportBranches.QueueConfiguration.class
    })
    static class TransportConfiguration {
    }
}
~~~

### Reading the Test Results

- `withUserConfiguration(TransportConfiguration.class)` brings the root configuration into the context.
- `@Import` passes both nested configuration classes into parsing.
- Conditions on `HttpConfiguration` and `QueueConfiguration` are evaluated separately.
- Only the matching configuration registers its bean method.
- If the property is absent or its value matches neither option, both branches are skipped; the context can still start because no required bean is injected.

**Run prerequisites:** Java 17+, Spring Boot 3.3.x, the `spring-boot-starter-test` test dependency, and a Gradle project managing versions with the Spring Boot plugin/BOM.

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Run in the module containing the test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.trace.ImportBranchSelectionTest"

# Windows
gradlew.bat test --tests "example.trace.ImportBranchSelectionTest"
~~~

**Expected result:** four tests PASS. The test verifies with AssertJ and has no `System.out.println`, so there is no fixed stdout output. Gradle output depends on test logging. The test code is presented to run in a matching project; execute the command against the actual dependency graph to confirm the build.

## 7. Verification Example of ImportSelector Using Environment

When the import list must be chosen dynamically, `ImportSelector` can be used. The example below uses `EnvironmentAware` to read the mode and return the corresponding configuration class name.

~~~java
public class ModeImportSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        String mode = environment.getProperty("demo.transport.mode", "none");

        return switch (mode) {
            case "http" -> new String[] {
                HttpTransportConfiguration.class.getName()
            };
            case "queue" -> new String[] {
                QueueTransportConfiguration.class.getName()
            };
            default -> new String[0];
        };
    }
}
~~~

This is an illustrative snippet; you need to import `ImportSelector`, `EnvironmentAware`, `Environment`, `AnnotationMetadata`, and the configuration classes. The selector is attached to the root class:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ModeImportSelector.class)
class SelectedTransportConfiguration {
}
~~~

Unlike importing two classes and letting conditions decide:
- `ImportSelector` returns only the selected branch.
- Conditions on nested configurations can still serve as an extra layer of protection.
- The selector does not create beans itself; returned classes continue to be parsed by Spring as configurations.

### When Should a Selector Read Annotation Metadata?

If the choice depends on a library-defined annotation, read the metadata of the importing class rather than forcing the selector to depend directly on a global property. For example, an annotation `@EnableTransport(mode = "http")` can be meta-annotated with `@Import(ModeImportSelector.class)`; the selector reads the `mode` attribute from `AnnotationMetadata`.

This is the appropriate direction for a library-provided `@Enable...` API. If you only need selection based on a Spring Boot property, a couple of nested configs with `@ConditionalOnProperty` may be easier to understand than a custom selector.

## 8. Multi-Level Nested Imports and Recursive Tracing

One import can lead to another configuration class, which in turn imports more:

~~~text
RootConfiguration
    |
    +-- @Import(FeatureConfiguration)
                |
                +-- @Import(TransportConfiguration)
                |           |
                |           +-- @Import(HttpConfiguration)
                |
                +-- @Import(RetryConfiguration)
~~~

When reading source, do not stop after the first import. For each imported class, continue checking:
- `@Import` on that class itself.
- Nested `@Configuration` classes.
- `ImportSelector` and `DeferredImportSelector`.
- Conditions at class and bean method levels.
- Which beans `@Bean` methods depend on.

Spring tracks already-parsed configuration classes to avoid infinite loops when circular imports exist or the same class is imported through multiple paths. Nevertheless, a design with import cycles is hard to read and should be simplified unless there is a clear reason.

### Import Cycles Are Not a Way to Organize Modules

If `A` imports `B` and `B` imports `A`, do not rely on deduplication to treat this as a good design. Bidirectional dependencies obscure responsibilities and make conditions/ordering difficult to reason about. Look for a composition configuration class to act as the connecting point, or extract shared APIs into a separate module.

## 9. Distinguishing Import, Component Scan, and Auto-Configuration Imports

| Mechanism | How Classes Are Found | When to Use |
| --- | --- | --- |
| `@Import(Config.class)` | Explicitly specified class | Fixed composition, easy to trace |
| `@Import(ImportSelector.class)` | Selector returns class names | Dynamic configuration list |
| `@ComponentScan` | Scans packages and subpackages | Finding components along package boundaries |
| `AutoConfiguration.imports` | Spring Boot reads the library's auto-configuration list | Publishing auto-configurations from a starter |
| `@ImportResource` | Loads bean definitions from a resource, e.g., XML | Integrating existing XML configuration |

Do not use broad component scanning solely to discover auto-configurations. For Spring Boot libraries, publish classes via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` so Boot manages the candidate list and exclusions.

Also do not confuse the `AutoConfiguration.imports` file with `@Import` in source code. Boot uses `AutoConfigurationImportSelector` (a deferred selector) to read that list, apply filtering and ordering, and pass the selected classes into the configuration parser.

## 10. At Which Layers Are Conditions Applied?

Conditions can appear at multiple layers:

| Location | Example | Scope of Effect |
| --- | --- | --- |
| Root configuration | `@ConditionalOnProperty` on root config | The entire root configuration branch and contents processed inside it |
| Nested configuration | `@ConditionalOnClass` on optional branch | All bean methods in that branch |
| Bean method | `@ConditionalOnMissingBean` on a `@Bean` | Only the bean declared by that method |
| Profile | `@Profile("dev")` | Class/bean carrying that profile |
| Selector | `selectImports(...)` returns different sets of classes | The set of configurations passed into parsing |

Class-level conditions eliminate an entire branch before processing bean methods. Method-level conditions affect only the corresponding bean method; other bean methods in the same configuration can still be registered.

When a parent config is skipped because its condition fails, nested configs inside that branch are not processed through the parent. When a nested config is imported separately via another path, it can still be evaluated through that separate import path. Therefore, when reading code with multiple import paths, trace **all paths** to the same class before concluding that a parent's condition excludes it.

## 11. Bean Definition Registration Differs from Bean Instantiation

A common analysis mistake is seeing `@Bean` in source code and concluding the bean has definitely been created. Distinguish:

1. The configuration class is discovered.
2. The configuration class passes its conditions.
3. The bean method is read and a `BeanDefinition` is registered.
4. The bean is requested by the context or dependency graph.
5. The instance is created, dependencies are injected, and initialization succeeds.

For instance, a `@Lazy` bean may have a definition without being instantiated until requested. Prototype-scoped beans are also not created in the same way as eager singletons. A bean may be registered, yet a constructor or dependency error causes instantiation to fail.

`@Import` controls bringing a configuration class into processing; it **is not an immediate constructor call for all beans**.

## 12. How to Debug in a Real Project

### 12.1. Enable the Condition Evaluation Report

Start the application with:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot will print the Condition Evaluation Report. Search for the relevant auto-configuration or condition name, then check:
- Is the class in the candidate list?
- Was the class excluded?
- Did `OnClassCondition`, `OnPropertyCondition`, or `OnBeanCondition` match?
- Does the bean method have its own conditions?

The report is useful for Spring Boot conditions; it does not replace reading `@Import` paths and selectors in source code.

### 12.2. Use Breakpoints in Order

When deep IDE debugging is needed, you can place breakpoints at:
- `ConfigurationClassParser#processImports`: see which class is importing which class.
- `ConfigurationClassParser#processMemberClasses`: see which nested configurations are discovered.
- `ConditionEvaluator#shouldSkip`: see which class or method is skipped due to a condition.
- `ConfigurationClassBeanDefinitionReader#loadBeanDefinitionsForBeanMethod`: see which bean method creates a definition.

Internal methods may change across versions; check out source matching the actual dependency. When you do not want to debug the framework, condition logs and small context tests are usually enough to narrow down the issue.

### 12.3. Build a Trace Table for Each Bean

When reviewing a bean, record one row per layer:

| Layer | Information to Record |
| --- | --- |
| Entry | Root configuration and registration mechanism |
| Import | Direct class / selector / deferred selector / registrar |
| Branch | Nested config or class returned by selector |
| Condition | Class-level and method-level conditions, expected result |
| Definition | Bean name, type, factory method |
| Dependency | Constructor/method dependencies |
| Creation | Eager/lazy, scope, initialization error if any |

This table helps distinguish "not imported", "skipped by condition", "bean definition not registered", and "registered but instance creation failed".

## 13. Common Mistakes When Tracing

1. **Searching only for the `@Bean` method without finding the configuration that holds it.** Trace back how the class was registered.
2. **Thinking `@Import` always creates beans immediately.** It brings the class into parsing; conditions and the bean lifecycle still apply.
3. **Ignoring the selector.** If `@Import` points to an `ImportSelector`, read `selectImports` and the metadata/environment it uses.
4. **Failing to distinguish `ImportSelector` from `DeferredImportSelector`.** Deferred selectors are processed after regular configurations; this is a key foundation of Boot auto-configuration.
5. **Overlooking nested configs.** A static member class with `@Configuration` can be discovered while parsing the outer class even if it is not in an imports array.
6. **Assuming a condition on a bean method protects optional types in its signature.** When a type might be missing, place the classpath condition on a separate configuration so the class holding that signature can be skipped.
7. **Confusing class-level and method-level conditions.** When a class is skipped, none of the branch's bean methods are registered; when a method is skipped, it does not automatically eliminate other methods.
8. **Confusing AutoConfiguration.imports with component scan.** These are two distinct class discovery mechanisms.
9. **Confusing registration order with instantiation order.** Bean definition parsing/registration order does not equal constructor execution order.
10. **Testing only the happy path.** Also test missing properties, unsupported values, alternative branches, and overridden beans.
11. **Ignoring multiple import paths.** A nested class may be directly imported elsewhere even if the initial parent branch was not selected.
12. **Reading source from a different version than the dependency.** Framework internals change; match the version of the sources JAR/tag.

## 14. Self-Check Questions

**Question 1.** A root class has `@Import(ModeSelector.class)`. Which file should you read to know which branch is chosen?

**Answer:** Read the `ModeSelector#selectImports` implementation, the metadata/Environment it uses, and the returned class names.

**Question 2.** Two nested `@Configuration` classes are imported at the same time, each with a different `@ConditionalOnProperty`. Do both necessarily register beans?

**Answer:** No. Each class condition is evaluated independently; only the branch whose condition matches is processed.

**Question 3.** Why does Spring Boot use `DeferredImportSelector` for auto-configuration?

**Answer:** To process auto-configurations after regular configurations, allowing auto-configuration selection/conditions to operate in the order Boot designed.

**Question 4.** Does `@Import(Config.class)` mean all beans in `Config` have finished instantiating?

**Answer:** No. Import brings the configuration into parsing; conditions then determine which definitions are registered, and the container creates beans according to lifecycle/dependencies.

**Question 5.** When a bean does not appear, in what order should you check?

**Answer:** Entry point → import/selector → nested branch → condition → bean definition → bean creation.

## 15. Takeaways When Reading Auto-Configuration Code

To trace accurately, follow the path from the root class:

- Identify the **entry point** and how the configuration is registered.
- Follow each `@Import`, reading any selector/registrar if present.
- Inspect nested configuration classes and conditions on each branch.
- Distinguish selected classes from classes that pass conditions.
- Confirm that the bean definition is registered before investigating bean instantiation.
- Use `ApplicationContextRunner` to reproduce each branch with small tests.

When reading code, a missing branch may have been eliminated during import selection, during condition checks, or during bean method registration. Pinpointing the exact stage helps fix the root cause and prevents adding `@Import` or changing conditions by guesswork.

### Official References

- [Spring Framework 6.1 — Java-based Container Configuration and @Import](https://docs.spring.io/spring-framework/reference/6.1/core/beans/java/composing-configuration-classes.html)
- [Spring Framework 6.1 — @Import Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Import.html)
- [Spring Framework 6.1 — ImportSelector Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html)
- [Spring Framework 6.1 — DeferredImportSelector Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
