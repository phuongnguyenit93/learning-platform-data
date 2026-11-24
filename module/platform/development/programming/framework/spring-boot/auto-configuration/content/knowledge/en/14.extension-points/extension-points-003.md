# Handling zero, one, or multiple extension components

## 1. Objective and problem statement

An **extension point** is a contract that allows an application or library to add behavior without modifying core code. In Spring Boot, an extension point is typically represented by an interface or callback; implementations are registered as beans in the `ApplicationContext`.

For example, a message-processing starter publishes a `MessageExtension` interface. An application using the starter might register no implementations, register one implementation, or install multiple implementations from different modules. The starter must handle **all three cases** properly:

- **Zero extensions (0):** choose a clear policy: keep the result unchanged (*no-op*), supply a default implementation (*fallback*), disable the feature, or report a configuration error if the extension is required.
- **Exactly one extension (1):** use that implementation without requiring extra user configuration, if the contract allows it.
- **Multiple extensions (N > 1):** choose an intentional policy: apply **all in order**, select one by qualifier/priority, merge results, or reject ambiguity. Do not arbitrarily pick "the first bean".

Objectives after this lesson: accurately distinguish "a bean exists" from "a unique bean"; use `ObjectProvider<T>`, `orderedStream()`, `@Order`, and Spring Boot conditions when appropriate; design explicit fallbacks and duplicate errors; and run a Java 17+ program to observe 0/1/N extensions.

**Scope limit:** we are designing extensions **managed as Spring beans** in the context of Spring Boot Auto-Configuration. Java `ServiceLoader`, dynamic plugins loaded outside the JVM, and runtime JAR loading are separate mechanisms and are not automatically activated simply by declaring an extension interface.

## 2. Define the contract before choosing annotations

Suppose the extension point is:

```java
public interface MessageExtension {
    String id();
    String apply(String input);
}
```

The snippet above illustrates the contract; in the full runnable program in section 6, the interface is placed inside the demo class. Meaning of the two methods:

- `id()`: logical identifier of the extension, used for configuration, error messages, and duplicate detection. This is **not necessarily** the Spring bean name.
- `apply(input)`: transforms the input and returns the output. The application decides whether it may alter content, return `null`, throw an exception, or produce side effects. In the example, the convention is to return a non-null string.

With such an interface, the most important design decision is the **semantics when multiple implementations exist**. Two common patterns are not interchangeable:

1. **Processing chain / list of handlers:** every extension contributes. Each extension processes the result from the previous one, so ordering is part of the contract.
2. **A single selected strategy:** multiple extensions are competing options. The application must specify a `@Qualifier`, name, identifier setting, or a unique selection policy.

Do not design an extension point assuming "I expect there to always be one bean" if the public API allows installing multiple plugins; once a second plugin appears, injecting a single `MessageExtension` can become ambiguous.

### Decision table by component count

| Situation | If the extension point is a handler list | If the extension point requires a single strategy |
| --- | --- | --- |
| **0 beans** | Return the input or use an explicitly documented fallback | Use a default if allowed, or fail with a "missing strategy" error |
| **1 bean** | Execute once | Select the single bean |
| **N beans** | Sort and run all of them; define error and duplicate rules | Select via explicit criteria or fail fast |
| **With `@Primary`** | Does not remove the remaining beans from the list | Can help Spring identify a candidate for single-value injection |
| **`@Order` ordering** | Crucial for defining pipeline sequence | Does not imply the lowest-order bean automatically becomes the "unique candidate" |

These policies are business decisions of the starter. Spring provides APIs to implement them rather than inferring intent from the interface alone.

## 3. Looking up 0/1/N beans in Spring: choosing the right tool

### 3.1. `ObjectProvider<MessageExtension>` and `orderedStream()`

In the bean managing the pipeline:

```java
@Bean
MessagePipeline messagePipeline(
    ObjectProvider<MessageExtension> extensionProvider
) {
    List<MessageExtension> ordered =
        extensionProvider.orderedStream().toList();
    return new MessagePipeline(ordered);
}
```

This is an **illustrative snippet** (assuming `MessagePipeline` exists). `ObjectProvider<T>` is Spring's API for flexible object lookup. `orderedStream()` produces a stream of beans compatible with `T` ordered by the BeanFactory's comparator, respecting `Ordered` and `@Order` in an appropriate Spring context.

- **0 extensions:** `orderedStream()` is empty; `toList()` returns an empty list. The pipeline bean is still created.
- **1 extension:** the list contains one object.
- **N extensions:** the list contains all matching beans returned by the provider, in the defined order; the pipeline decides how to combine them.

The advantage here is that the extension point genuinely supports **zero-or-more**, without needing a dummy bean just to make single-element injection succeed. `ObjectProvider` resolves beans when accessed; converting to a `List` and storing it in the pipeline constructor creates a **snapshot** of the list at pipeline construction time. If you need dynamic lookup on each invocation, you can retain the provider and call `orderedStream()` at runtime, after weighing cost and lifecycle.

Selected beans are still subject to Spring's candidate/qualifier rules. Applying `@Qualifier` to an injection point or having beans ineligible for autowiring can make the returned list differ from all bean definitions of that type.

### 3.2. Why not immediately use `getObject()` / `getIfAvailable()` / `getIfUnique()`?

Single-result APIs carry different semantics:

| Lookup method | No bean | One candidate | Multiple candidates without a single preferred candidate |
| --- | --- | --- | --- |
| `provider.getObject()` | Missing-bean error | Returns bean | Ambiguity error |
| `provider.getIfAvailable()` | Returns `null` | Returns bean | May throw `NoUniqueBeanDefinitionException` |
| `provider.getIfUnique()` | Returns `null` | Returns bean | Returns `null` if no unique candidate exists |
| `provider.orderedStream()` | Empty stream | Single-element stream | Stream of matching beans, sorted by ordering rules |

**Note on `@Primary`:** in Spring 6.1, `getIfUnique()` can return the `@Primary` bean when multiple beans exist and a single preferred candidate is identified. Therefore **`getIfUnique() != null` does not prove there is strictly one bean in the context**; to check cardinality, count candidates via a stream or inspect a list. `getIfAvailable()` can also resolve a single candidate when an appropriate primary/qualifier exists; do not assume it always fails whenever two or more beans are present.

Example:

```java
MessageExtension selected = provider.getIfUnique();
```

This is suitable when the contract truly is "use a candidate Spring considers unique; if none is selected, do not run", **not** when multiple extensions must all execute. It also risks silently treating 0 beans and N ambiguous beans as the same `null` state.

### 3.3. `Optional<T>`, `List<T>`, and `Map<String,T>`

Spring also supports these injection forms:

```java
// Illustrates constructor signatures, not a standalone program.
public ExampleService(Optional<MessageExtension> optional) { ... }
public ExampleService(List<MessageExtension> extensions) { ... }
public ExampleService(Map<String, MessageExtension> byBeanName) { ... }
```

- `Optional<T>` expresses an **optional** dependency, but only fits a **single choice**; if multiple unresolvable candidates exist, an ambiguity error can still occur. `Optional` is not a container holding all plugins.
- `List<T>` and `Map<String,T>` can retrieve multiple beans (the map keys are **bean names**). However, when no matching bean exists, injection behavior depends on the injection point and requiredness; in this lesson we choose `ObjectProvider<T>.orderedStream()` so the 0-bean case is always explicit and consistent.
- `Map<String,T>` helps diagnose bean names or select by bean name. Bean names are **different** from a plugin contract's `id()` unless the application actively keeps the two in sync.

If the pipeline always runs all implementations, use a **multi-result** API. If the pipeline only runs one implementation, design a **uniqueness** policy and test when two plugins are configured.

## 4. Ordering when multiple extensions exist

Suppose one extension adds a prefix and another adds a suffix. The two transformations may not commute:

```text
input = "hello"

prefix before suffix: [A:hello]|B
suffix before prefix: [A:hello|B]
```

If you leave this dependent on bean registration order or classpath scanning order, the result can change when another starter/module is added.

### 4.1. `@Order` and `Ordered`

`@Order` can be placed on a bean class or a `@Bean` method:

```java
@Bean
@Order(10)
MessageExtension prefixExtension() {
    return new PrefixExtension();
}

@Bean
@Order(20)
MessageExtension suffixExtension() {
    return new SuffixExtension();
}
```

This snippet is based on hypothetical types; the full version is in section 6. **Lower numbers have higher priority (run earlier)**: when the provider uses `orderedStream()`, the prefix with order 10 executes before the suffix with order 20. Implementations can also implement `Ordered`, returning the order via `getOrder()`.

**Do not confuse `@Order` with singleton initialization order.** List ordering for extension execution and the order in which Spring instantiates beans are two different concerns; Spring determines initialization dependencies from injection/`@DependsOn` and lifecycle.

If two extensions share the **same** order value, do not rely on their relative order for business logic. When deterministic ordering is important, add a secondary key such as `id()` and sort with a transparent comparator, or require plugins to declare non-duplicate order values.

### 4.2. Priority does not mean excluding other extensions

`@Order(10)` does **not** mean "pick one winning bean". With `orderedStream()`, both order 10 and order 20 beans participate. Conversely, `@Primary` targets **single-bean** dependency resolution; it cannot replace a multi-component pipeline design.

If business logic wants "only the highest-priority plugin runs", write a **single-selection** policy (including tie-breaking rules) or configure an explicit plugin ID. Do not accidentally use `orderedStream().findFirst()` as an implicit selector before deciding tie rules.

## 5. Policies when no extension exists and on duplicates

### 5.1. No extension: no-op or fallback?

Two valid models:

**Model A — no-op:** the pipeline is the core bean, and the extension list may be empty. When empty, it returns the input or performs core work without applying plugins. This model is convenient when extensions are optional. The example in section 6 uses Model A.

```java
String process(String input) {
    String result = input;
    for (MessageExtension extension : extensions) {
        result = extension.apply(result);
    }
    return result;
}
```

**Model B — fallback bean:** the starter registers a default implementation **only when no application implementation exists**:

```java
@AutoConfiguration
class ExtensionFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageExtension.class)
    MessageExtension defaultMessageExtension() {
        return new DefaultMessageExtension();
    }
}
```

This is an illustrative snippet; `DefaultMessageExtension` must be defined in a real project. In Spring Boot, `@ConditionalOnMissingBean(MessageExtension.class)` lets the starter **back off** when the application already supplies an extension. If one or more `MessageExtension` beans are known at evaluation time, this fallback bean is not registered.

**Distinguish the outcomes:** with Model A, 0 extensions means the pipeline runs 0 plugins. With Model B, when the user declares no plugin, the context still contains **one default extension** after auto-configuration. Do not describe a fallback as "the list stays empty".

Bean conditions like `@ConditionalOnMissingBean` evaluate bean definitions already processed **at evaluation time**. Spring Boot recommends placing them in auto-configurations so they run after user beans; with multiple related auto-configurations, declare `@AutoConfiguration(after = ...)` when needed. If a fallback must always run alongside other plugins, do **not** use `@ConditionalOnMissingBean(MessageExtension.class)`: define it as a separate processing step or an always-present bean and specify its ordering.

### 5.2. When an extension is required

If the feature cannot operate without a plugin, failing fast is better than silently skipping:

```java
List<MessageExtension> found =
    provider.orderedStream().toList();

if (found.isEmpty()) {
    throw new IllegalStateException(
        "At least one MessageExtension is required"
    );
}
```

The error should state the **required extension type, registration conditions, and remediation steps**, rather than reporting an unhelpful message like "unexpected null". Failing proactively should be driven by business requirements; do not apply it to optional extension points.

### 5.3. When multiple extensions exist but only one is allowed

An application might treat 0 as disabled, 1 as valid, and N > 1 as an error:

```java
List<MessageExtension> found =
    provider.orderedStream().toList();

if (found.size() > 1) {
    throw new IllegalStateException(
        "Expected at most one MessageExtension, found " + found.size()
    );
}

MessageExtension selected = found.isEmpty() ? null : found.get(0);
```

This is a **true cardinality check**; unlike `getIfUnique()`, because Spring can recognize a `@Primary` candidate among multiple beans. A contract that lets `@Primary` select one bean is also valid, but it must be documented and tested separately.

### 5.4. Detecting duplicate logical identifiers when running N plugins

Two beans can have different Spring bean names yet return the same `id()`. If `id()` is a unique key, check it:

```java
Set<String> seen = new HashSet<>();
for (MessageExtension extension : extensions) {
    if (!seen.add(extension.id())) {
        throw new IllegalStateException(
            "Duplicate MessageExtension id: " + extension.id()
        );
    }
}
```

This snippet requires `import java.util.Set;` and `import java.util.HashSet;` in a class that has an `extensions` variable. Checking **logical IDs** prevents running the same plugin type twice because two modules both registered it. Spring has its own rules for **duplicate bean names**, but those do not replace business ID checks.

A well-designed extension point should specify **plugin names/IDs**, **ordering**, **error handling**, **whether multiple implementations may run simultaneously**, and **whether a fallback is needed**.

## 6. Standalone Java 17+ example: 0, 1, and 2 extensions

This example uses **Spring Boot 3.3.13**, **Spring Framework 6.1.x**, JDK 17+, and Maven. It simulates a starter with an `@AutoConfiguration` creating a `MessagePipeline` bean. Extensions are beans declared by the "application" in separate `@Configuration` classes.

To keep three independent scenarios in one `main`, the program uses `AnnotationConfigApplicationContext` and **explicitly registers configuration classes**. As a result, the example accurately observes bean management, `ObjectProvider`, `@Order`, and `@ConditionalOnMissingBean` without starting a web server. In a real starter, `@AutoConfiguration` must be imported via `AutoConfiguration.imports` (covered in section 7), not relied upon through component scanning of the starter.

### 6.1. Structure

```text
extension-cases-demo/
├── pom.xml
└── src/main/java/demo/ExtensionCasesDemo.java
```

### 6.2. `pom.xml` file

```xml
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
    <groupId>demo</groupId>
    <artifactId>extension-cases-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. `src/main/java/demo/ExtensionCasesDemo.java` file

```java
package demo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public final class ExtensionCasesDemo {

    // Extension contract: has an ID and a text transformation.
    interface MessageExtension {
        String id();
        String apply(String input);
    }

    static final class PrefixExtension implements MessageExtension {
        @Override
        public String id() {
            return "prefix";
        }

        @Override
        public String apply(String input) {
            return "[A:" + input + "]";
        }
    }

    static final class SuffixExtension implements MessageExtension {
        @Override
        public String id() {
            return "suffix";
        }

        @Override
        public String apply(String input) {
            return input + "|B";
        }
    }

    static final class MessagePipeline {
        private final List<MessageExtension> extensions;

        MessagePipeline(List<MessageExtension> extensions) {
            this.extensions = List.copyOf(extensions);

            // Check uniqueness by business ID, not just bean name.
            Set<String> ids = new HashSet<>();
            for (MessageExtension extension : this.extensions) {
                if (!ids.add(extension.id())) {
                    throw new IllegalStateException(
                        "Duplicate extension id: " + extension.id()
                    );
                }
            }
        }

        int extensionCount() {
            return extensions.size();
        }

        String process(String input) {
            String result = input;
            for (MessageExtension extension : extensions) {
                result = extension.apply(result);
            }
            return result;
        }
    }

    // Simulates a starter's auto-configuration.
    @AutoConfiguration
    static class PipelineAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(MessagePipeline.class)
        MessagePipeline messagePipeline(
            ObjectProvider<MessageExtension> provider
        ) {
            return new MessagePipeline(
                provider.orderedStream().toList()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrefixConfiguration {
        @Bean("prefixExtension")
        @Order(10)
        MessageExtension prefixExtension() {
            return new PrefixExtension();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SuffixConfiguration {
        @Bean("suffixExtension")
        @Order(20)
        MessageExtension suffixExtension() {
            return new SuffixExtension();
        }
    }

    static void runCase(
        String label,
        Class<?>... extensionConfigurations
    ) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            // Register the auto-configuration class explicitly
            // so each example uses an isolated context.
            context.register(PipelineAutoConfiguration.class);

            if (extensionConfigurations.length > 0) {
                context.register(extensionConfigurations);
            }
            context.refresh();

            MessagePipeline pipeline =
                context.getBean(MessagePipeline.class);

            System.out.printf(
                "%s: extensions=%d, output=%s%n",
                label,
                pipeline.extensionCount(),
                pipeline.process("message")
            );
        }
    }

    public static void main(String[] args) {
        runCase("none");
        runCase("one", PrefixConfiguration.class);

        // Intentionally register Suffix before Prefix.
        // @Order + orderedStream ensures Prefix runs first.
        runCase(
            "many",
            SuffixConfiguration.class,
            PrefixConfiguration.class
        );
    }
}
```

### 6.4. Running and explaining the output

Requires JDK 17+, Maven 3.8+, and dependency resolution access. From the `extension-cases-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ExtensionCasesDemo
```

Three lines **printed by the program itself** (excluding Maven messages if your environment adds any):

```text
none: extensions=0, output=message
one: extensions=1, output=[A:message]
many: extensions=2, output=[A:message]|B
```

**Scenario none:** only `PipelineAutoConfiguration` is present. The `MessagePipeline` bean is registered; `ObjectProvider<MessageExtension>.orderedStream()` is empty; the loop does not execute, so `process("message")` leaves the input unchanged. This is a **valid no-op policy** when no extension exists.

**Scenario one:** adds the `prefixExtension` bean. The provider finds one `MessageExtension`; the pipeline runs `PrefixExtension` and returns `[A:message]`. There is no need to select a bean by name because the pipeline contract is "run all available extensions".

**Scenario many:** two beans are registered from two configuration classes. Although `runCase` passes `SuffixConfiguration.class` **before** `PrefixConfiguration.class`, the provider calls `orderedStream()` and the `@Bean` methods have `@Order(10)` and `@Order(20)`; the prefix extension runs first, and the suffix runs second. The result is `[A:message]|B`, not `[A:message|B]`.

**Duplicate error control:** the `MessagePipeline` constructor checks `id()`. If two extensions both return `"prefix"`, pipeline creation throws `IllegalStateException("Duplicate extension id: prefix")`, preventing the context from starting. That is an intentional fail-fast policy, unlike picking a plugin at random.

**Role of `@ConditionalOnMissingBean` in the example:** the annotation applies only to the **pipeline** bean, so users can declare a replacement pipeline themselves. It does **not** prevent users from declaring multiple `MessageExtension` beans; hence the zero/one/many flow works. Placing `@ConditionalOnBean(MessageExtension.class)` on the entire pipeline configuration would prevent the `none` scenario from creating a pipeline, violating the no-op requirement.

The program registers `PipelineAutoConfiguration` directly to isolate the three cases; in a real starter, Spring Boot loads auto-configurations automatically from the imports file. The extension ordering rules remain the same.

## 7. Applying in a real Spring Boot starter

A common layout:

```text
my-library-autoconfigure/
├── src/main/java/com/acme/lib/
│   ├── MessageExtension.java
│   ├── MessagePipeline.java
│   └── MessagePipelineAutoConfiguration.java
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports

my-application/
└── src/main/java/com/example/app/
    ├── MyExtensionConfiguration.java
    └── ...
```

In the autoconfigure module, the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file lists the FQCN:

```text
com.acme.lib.MessagePipelineAutoConfiguration
```

The auto-configuration provides the **pipeline bean**:

```java
@AutoConfiguration
public class MessagePipelineAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessagePipeline.class)
    MessagePipeline messagePipeline(
        ObjectProvider<MessageExtension> extensions
    ) {
        return new MessagePipeline(
            extensions.orderedStream().toList()
        );
    }
}
```

This is an **illustrative snippet**, assuming `MessagePipeline` and `MessageExtension` are already defined in the library module. Users supply extensions via application `@Bean`/`@Component` definitions:

```java
@Configuration(proxyBeanMethods = false)
class MyExtensionConfiguration {

    @Bean
    @Order(100)
    MessageExtension sanitizeExtension() {
        return new SanitizeExtension();
    }
}
```

`SanitizeExtension` is a hypothetical application type; the snippet is not a standalone Java file.

**Important point:** a starter should not use `@ComponentScan` to scan application packages, nor force applications to manually import the auto-configuration class. Spring Boot 3.3 requires declaring auto-configurations in the imports file. Application extensions are registered through normal bean configuration; the provider then retrieves the candidates.

### 7.1. Pipeline backoff and extension fallback are two different things

- `@ConditionalOnMissingBean(MessagePipeline.class)`: allows **replacing the entire pipeline** provided by the starter.
- `@ConditionalOnMissingBean(MessageExtension.class)`: allows **supplying a default implementation** when no extension exists yet.

Do not swap these two conditions because they target **two different bean types**. If an application wants to customize the *pipeline* itself while still using auto-registered extensions, let the application's pipeline bean replace the default under the first condition. If you want the default pipeline plus all extensions, keep the pipeline registered when missing and **do not require** extensions to exist.

### 7.2. Stability when modules change

Adding a new dependency can introduce another `MessageExtension` bean. If the default pipeline runs **all** extensions, the application's output will change in accordance with that contract. Therefore:

- Define clear plugin identifiers and enable/disable defaults.
- Specify priority ordering and tie-breaking behavior for equal orders.
- Define whether a plugin may run multiple times, have duplicate IDs, or replace another plugin.
- If an extension touches sensitive data or I/O, clearly document side effects and exception handling.
- In logs, include the extension name/ID and reason when skipped, and avoid logging sensitive payloads.
- Check compatibility when upgrading the starter, since new extensions can change output without modifying application config.

Do not use `@Primary` assuming the list will automatically shrink to a single element. If the library requires only one strategy, use qualified injection / an explicit selection policy and write tests for two or more beans.

## 8. Testing the three cases and error conditions

A baseline test suite for an extension point should cover **at least** three scenarios:

| Scenario | Setup | Result to verify |
| --- | --- | --- |
| **0** | No `MessageExtension` registered | Pipeline is still created under a no-op policy; output is unchanged, or fallback is created if fallback policy was chosen |
| **1** | One `PrefixExtension` bean | Extension runs exactly once; `@Primary` is not required |
| **2+** | Two beans of the same interface, registered in reverse priority order | Runs the exact number of times and **in the right order**; no bean is missed |
| **Duplicate ID** | Two differently named beans with the same `id()` | Context fails with duplicate details, if the contract requires unique IDs |
| **Pipeline replacement** | User provides `@Bean MessagePipeline` | `@ConditionalOnMissingBean(MessagePipeline.class)` makes the default pipeline back off; two pipelines are not created |
| **Failing plugin** | One extension throws an exception | Follows the policy: fail fast or isolate the error and continue; behavior must be verified |

Spring Boot provides `ApplicationContextRunner` for testing auto-configurations across different combinations of beans, properties, and classpath states. The example below is a **guiding snippet** for tests (requiring actual project classes, imports, and test dependencies):

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MessagePipelineAutoConfiguration.class)
    )
    .withUserConfiguration(MyExtensionConfiguration.class)
    .run(context -> {
        MessagePipeline pipeline = context.getBean(MessagePipeline.class);
        // assert plugin count, ordering, and output according to the contract.
    });
```

The template above assumes `ApplicationContextRunner`, `AutoConfigurations`, and actual project classes are imported; the test runner comes from `spring-boot-test` (typically via `spring-boot-starter-test`). Note: this snippet only illustrates setup and should not be presented as a complete test without assertions.

**Reverse-order testing:** intentionally register a bean with `@Order(20)` before a bean with `@Order(10)` (as in section 6), then require the output to match 10 → 20. Also test adding a third plugin or changing an order value to ensure the pipeline does not rely on source-code position.

**Testing user beans:** in auto-configuration, missing-bean conditions can be affected by the order in which bean definitions are processed. Spring Boot recommends using bean conditions only inside auto-configurations, and ordering with `@AutoConfiguration(after = ...)` when depending on another auto-configuration. Do not evaluate existence solely from a class being present on the classpath: a bean definition must actually be registered.

## 9. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Injecting a single `MessageExtension` while allowing multiple plugins | Can hit a dependency ambiguity error once a second plugin appears | Use `ObjectProvider<MessageExtension>.orderedStream()` if all should run |
| Using `Optional<MessageExtension>` to handle 0/1/N | `Optional` only represents one value or absence, not multiple implementations | If multiple plugins are valid, use a list/stream |
| Using `getIfUnique() == null` to conclude "no plugin exists" | Multiple ambiguous plugins can also return `null` | Count the stream if you need to distinguish 0 from N |
| Assuming `@Primary` makes other plugins disappear | `@Primary` only helps select a single dependency when appropriate | For multi-step pipelines, fetch all candidates via `orderedStream()` |
| Relying on declaration/scan order instead of `@Order` | Pipeline results can change after refactoring or adding modules | Declare ordering or a comparator with a clear contract |
| Putting `@ConditionalOnBean(MessageExtension.class)` on a no-op-capable pipeline | With 0 plugins, the pipeline disappears even though the feature should still exist | Create the pipeline independently, accepting an empty provider |
| Using `@ConditionalOnMissingBean(MessagePipeline.class)` thinking it creates a fallback plugin | It only checks the `MessagePipeline` bean | Use a condition targeting the extension type if a fallback is needed |
| Reusing bean names/IDs assuming Spring always merges validly | Can fail on duplicate bean names, or duplicate logical IDs across different names | Define a duplicate policy and check logical IDs explicitly |
| Ignoring plugin errors or swallowing exceptions without logging | Hard to detect missed processing and corrupt data | Choose fail-fast or controlled isolation with contextual error messages |
| Thinking `@Order` controls bean instantiation timing | It is a collection/extension sorting rule, not an initialization dependency relationship | Use injection/`@DependsOn` for lifecycle ordering |
| Confusing an interface on the classpath with a registered implementation bean | Class presence does not mean a bean is registered | Check bean candidates and the condition report |
| Observing different results across parent–child BeanFactories/contexts | Providers in different contexts/qualifiers see different candidate sets | Identify the context and qualifiers, and test in the right environment |

## 10. Self-check questions

**Question 1.** A starter provides `MessagePipeline`, but the application declares no `MessageExtension`. What does `provider.orderedStream().toList()` return?  
**Answer:** An empty list. If the pipeline chooses no-op, it returns the input unchanged; no dummy extension bean is needed for it to exist.

**Question 2.** There are two beans of the same interface, one `@Order(100)` and one `@Order(10)`. When using `orderedStream()`, are both still included?  
**Answer:** Yes, if both are eligible candidates. The order 10 bean is emitted before the order 100 bean; `@Order` does not filter beans out.

**Question 3.** Two extensions have bean names `firstPlugin` and `secondPlugin`, and both return `"pricing"` from `id()`. Is checking duplicate bean names enough?  
**Answer:** No. Two differently named beans still collide on the logical identifier `"pricing"`, so `id()` must be checked if the contract requires uniqueness.

**Question 4.** There are two implementations with one marked `@Primary`. If `provider.getIfUnique()` returns a bean, can you conclude there is strictly one extension?  
**Answer:** No. Spring can resolve a single primary candidate among multiple beans; to check cardinality, you must count them.

**Question 5.** A pipeline can run multiple plugins yet has `@ConditionalOnBean(MessageExtension.class)` directly on the pipeline configuration. What happens when there are no plugins?  
**Answer:** The condition does not match, so the pipeline may not be registered. If the contract wants zero-extension no-op behavior, remove that required condition.

**Question 6.** Does `@ConditionalOnMissingBean(MessageExtension.class)` on a fallback bean automatically register the fallback when the application already has another extension?  
**Answer:** No, if that bean is already known when the condition is evaluated, the fallback backs off. Place the condition in an auto-configuration and account for bean definition processing order.

**Question 7.** Plugin A adds `[A:...]`, plugin B adds `|B`. You need output `[A:message]|B` on every run. What design should you use?  
**Answer:** Require A to run before B, for example declaring `@Order(10)` on A and `@Order(20)` on B, and use `orderedStream()` instead of arbitrary registration order.

**Question 8.** If N plugins are valid in the context but business rules allow only one plugin to run, should you apply all of them via a stream?  
**Answer:** No. Define a selection rule such as plugin ID/`@Qualifier`/`@Primary` or fail on multiple candidates; the behavior must be clearly documented in the contract.

## 11. Takeaways and references

- **0 / 1 / N are three distinct cases:** choose the behavior **before** writing the auto-configuration.
- For list-style extensions, `ObjectProvider<T>.orderedStream()` handles **0, 1, and N** cleanly while preserving `@Order`/`Ordered` sequence when needed.
- For single-strategy extensions, do not equate `getIfUnique()` with "only one bean exists"; `@Primary` can select one candidate out of many.
- `@ConditionalOnMissingBean(Pipeline.class)` lets users replace the pipeline; `@ConditionalOnMissingBean(Extension.class)` registers a fallback when no extension exists. The two conditions serve different purposes.
- Use **logical ID** duplicate checks, ordering rules, and plugin error policies to avoid undefined behavior when extra modules are added.
- A real starter must declare its auto-configuration in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; extensions are registered by the application as Spring beans.

Official documentation references for **Spring Boot 3.3 / Spring Framework 6.1**:

1. [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), *Bean Conditions* and *Testing Your Auto-configuration* sections.
2. [Spring Framework 6.1 — ObjectProvider Javadoc](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/beans/factory/ObjectProvider.html), `getIfAvailable()`, `getIfUnique()`, and `orderedStream()` methods.
3. [Spring Framework 6.1 — @Order Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/core/annotation/Order.html), component ordering and relationship to injection.
4. [Spring Boot 3.3 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
5. [Spring Boot 3.3 — @ConditionalOnSingleCandidate Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html), when a single candidate is needed for injection (not equivalent to strictly one bean).
