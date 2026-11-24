# Using jakarta.inject.Provider and Controlling Bean Retrieval Timing in Spring Core Container

## 1. Objectives and Context

In the Spring IoC Container, **dependency injection** typically resolves dependencies as soon as the receiving bean is created. That is a sensible default for required, stable dependencies. However, sometimes the target object must be obtained **at the exact moment business logic executes**, for example:

- A singleton runs multiple jobs and each job needs a fresh `prototype` bean.
- A service touches a shorter-scoped bean only while an active request exists.
- A dependency is expensive or involved in a dependency cycle, so accessing it must be deferred until after the consumer is constructed.
- An interface has multiple implementations, and caller code specifies the intended one via a qualifier.

**`jakarta.inject.Provider<T>`** is a minimal contract from Jakarta Dependency Injection: the consumer receives `Provider<T>` via dependency injection, stores the provider, and calls `get()` when a `T` object is needed. Spring Framework supports this contract in the Core Container. The core idea is **deferring retrieval of the bean from the container**, not automatically creating new instances or making every bean in the application lazy.

After this lesson, you will be able to explain how `Provider<T>` works, integrate `jakarta.inject-api`, choose when to call `get()`, explain its relationship with scopes, and test missing/multiple-bean scenarios.

## 2. What Does the Provider<T> Interface Actually Provide?

`jakarta.inject.Provider<T>` has a minimal API:

```java
package jakarta.inject;

public interface Provider<T> {
    T get();
}
```

This is the core interface shown for learning the API. `T` is the object type supplied by the injector/container. Spring creates and injects a provider implementation tailored to the injection point. Consumer code never writes a `Provider<T>` implementation or directly receives `ApplicationContext`.

- `get()` **asks the container to supply a fully constructed and injected object** at call time.
- Which bean is returned and whether a new instance is created depend on **bean definition, scope, qualifiers, and candidate selection rules**.
- `get()` is a **required** lookup: if Spring cannot find a valid bean or encounters a creation error, the call can throw a runtime exception.
- The standard provider does **not** have `getIfAvailable()`, `getIfUnique()`, `stream()`, `orderedStream()`, or `getObject(args)`. Those capabilities belong to Spring's extended API, such as `ObjectProvider<T>`.

In Spring Framework 6+ and Spring Boot 3+ applications, the proper imports are:

```java
import jakarta.inject.Provider;
import jakarta.inject.Inject;
import jakarta.inject.Named;
```

Do not accidentally import `javax.inject.Provider` from legacy Java EE/older Spring ecosystems. The two package names are distinct Java types requiring different dependencies; this lesson uses the **`jakarta.inject`** namespace.

### Behavior Across Two Moments in Time

**At consumer creation:**

```text
Spring Container
    |
    +-- create WorkService
    |     |
    |     +-- inject Provider<Attempt> -- store provider
    |
    +-- WorkService ready to receive tasks
```

**During task execution:**

```text
WorkService.process()
    |
    +-- attemptProvider.get()
            |
            +-- Spring finds matching Attempt bean
            +-- applies Attempt's scope
            +-- creates or retrieves instance
            +-- returns instance for the current execution
```

These diagrams illustrate the lookup path. They do not claim that a target singleton bean is always created for the first time at `get()`: a non-`@Lazy` singleton may already have been initialized at container refresh.

## 3. Why Control Bean Retrieval Timing?

Suppose `TaskRunner` is a **singleton**, while `Attempt` is a **prototype**, each instance holding state for one execution.

### 3.1. Injecting a Prototype Directly into a Singleton

```java
// Structural example; Attempt and TaskRunner are illustrative domain types.
public final class TaskRunner {
    private final Attempt attempt;

    public TaskRunner(Attempt attempt) {
        this.attempt = attempt;
    }

    public void run() {
        attempt.execute();
    }
}
```

If `TaskRunner` is created once, Spring resolves `Attempt` for the constructor **once**. Because `TaskRunner` keeps the same reference, every call to `run()` uses the exact object injected initially. `@Scope("prototype")` on `Attempt` does not cause Spring to swap out the field on subsequent calls.

### 3.2. Injecting Provider and Calling get() Inside run()

```java
import jakarta.inject.Provider;

public final class TaskRunner {
    private final Provider<Attempt> attempts;

    public TaskRunner(Provider<Attempt> attempts) {
        this.attempts = attempts;
    }

    public void run() {
        Attempt current = attempts.get();
        current.execute();
    }
}
```

This is also a structural snippet, not a standalone program. With `Attempt` scoped as `prototype`, **each `get()` call resolves a new prototype bean** per Spring rules. If `Attempt` is a singleton, repeated `get()` calls normally return the same object within an `ApplicationContext`.

**Key decision:** store `Provider<Attempt>` in the consumer; store `Attempt` only in a local variable at the start of a unit of work. When all steps of one task must share the same attempt, call `get()` **once for that task** and pass the local object through the steps. Avoid calling `get()` repeatedly by accident assuming all calls return the same attempt.

## 4. Setting Up a Java 17+ Project with Spring Framework

Below is a complete program using Spring Framework **6.2.19**, `jakarta.inject-api` **2.0.0**, and Java **17+**. The example intentionally demonstrates four behaviors: prototypes are retrieved lazily per call, singleton scope still reuses its instance, `@Named` selects between two beans sharing an interface, and `get()` throws when no target bean exists.

Create this structure:

```text
provider-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ProviderTimingDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'provider-timing-demo'
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
    implementation 'jakarta.inject:jakarta.inject-api:2.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ProviderTimingDemo'
}
```

`spring-context` provides the Spring container and configuration annotations. `jakarta.inject-api` provides `Provider`, `Inject`, and `Named`. In a Spring Boot project using dependency management, framework versions are typically managed by a BOM; in that case, avoid pinning standalone Spring versions just to test providers.

**`src/main/java/ProviderTimingDemo.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.inject.Named;
import jakarta.inject.Provider;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class ProviderTimingDemo {

    record Attempt(int id) {}

    record Settings(String mode) {}

    interface Formatter {
        String format(String input);
    }

    interface OptionalMetrics {
        void record();
    }

    static final class WorkService {
        private final Provider<Attempt> attempts;
        private final Provider<Formatter> formatter;
        private final Provider<Settings> settings;
        private final Provider<OptionalMetrics> metrics;

        WorkService(
                Provider<Attempt> attempts,
                Provider<Formatter> formatter,
                Provider<Settings> settings,
                Provider<OptionalMetrics> metrics) {
            this.attempts = attempts;
            this.formatter = formatter;
            this.settings = settings;
            this.metrics = metrics;
        }

        void process(String label) {
            Attempt current = attempts.get();
            String output = formatter.get().format(label);
            System.out.println("process=" + output + "#" + current.id());
        }

        boolean sameSettings() {
            return settings.get() == settings.get();
        }

        void probeOptionalMetrics() {
            try {
                metrics.get();
                System.out.println("metrics=present");
            } catch (NoSuchBeanDefinitionException ex) {
                System.out.println("metrics=absent");
            }
        }
    }

    @Configuration
    public static class Config {
        private final AtomicInteger sequence = new AtomicInteger();

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        Attempt attempt() {
            int id = sequence.incrementAndGet();
            System.out.println("create-attempt-" + id);
            return new Attempt(id);
        }

        @Bean("mainFormatter")
        Formatter mainFormatter() {
            return input -> "main:" + input;
        }

        @Bean("backupFormatter")
        Formatter backupFormatter() {
            return input -> "backup:" + input;
        }

        @Bean
        Settings settings() {
            return new Settings("demo");
        }

        @Bean
        WorkService workService(
                Provider<Attempt> attempts,
                @Named("mainFormatter") Provider<Formatter> formatter,
                Provider<Settings> settings,
                Provider<OptionalMetrics> metrics) {
            return new WorkService(attempts, formatter, settings, metrics);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService work = context.getBean(WorkService.class);

            System.out.println("context-ready");
            System.out.println("before-first-get");
            work.process("A");
            work.process("B");
            System.out.println("singleton-same=" + work.sameSettings());
            work.probeOptionalMetrics();
        }
    }
}
```

Run in the `provider-timing-demo` directory with Gradle installed:

```bash
gradle run --quiet
```

If the project includes a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. The code needs Spring and Jakarta Inject on the classpath, so running `javac ProviderTimingDemo.java` standalone from the source folder is insufficient. The `gradle run` task compiles the code and supplies declared dependencies.

**Output printed by `main` to stdout:**

```text
context-ready
before-first-get
create-attempt-1
process=main:A#1
create-attempt-2
process=main:B#2
singleton-same=true
metrics=absent
```

### Interpreting the Results

1. `Config` and `WorkService` are constructed when the context starts; injecting `Provider<Attempt>` does not create `Attempt` yet because `Attempt` is a prototype not yet requested.
2. `context-ready` and `before-first-get` appear **before** `create-attempt-1`: this indicates retrieval timing is controlled by business code.
3. `process("A")` calls `attempts.get()` and creates attempt 1. `process("B")` calls `get()` again and creates attempt 2.
4. Two `Formatter` beans exist in the context. `@Named("mainFormatter")` on the provider parameter guides Spring to pick the named bean, yielding `main:A` and `main:B`. Without the qualifier and with no other candidate-selection rule, a single lookup on `Provider<Formatter>` could fail due to multiple candidates.
5. `Settings` has the default `singleton` scope; two `settings.get()` calls point to the same instance, so `singleton-same=true`.
6. No `OptionalMetrics` bean exists. Injecting `Provider<OptionalMetrics>` succeeds, yet when `get()` actually executes, Spring throws `NoSuchBeanDefinitionException`; the `catch` block turns this expected missing-bean case into `metrics=absent`.

Any extra lines printed by Gradle or the build environment sit outside `main`'s intentional stdout.

**Note on the optional example:** catching `NoSuchBeanDefinitionException` here merely illustrates `Provider.get()` semantics. In real code, if a dependency is optional by design and you are using Spring, `ObjectProvider<T>.getIfAvailable()` or `Optional<T>` expresses the optional contract more cleanly. Never catch every `RuntimeException` treating it as "bean does not exist," as that can hide bean creation or configuration bugs.

## 5. Choosing When to Call get(): Control Belongs to the Consumer

### 5.1. Retrieving at a Task Boundary

```java
void handle(Order order) {
    ProcessingSession session = sessionProvider.get();
    session.validate(order);
    session.reserve(order);
    session.finish();
}
```

`ProcessingSession` and `Order` are illustrative domain types, with the provider already injected. Call `get()` only when `handle` starts. All three steps share the same `session` object, which is vital if the prototype bean holds internal transaction state.

Replacing the three uses of `session` with three `sessionProvider.get()` calls could create three separate sessions for a prototype: this is usually wrong when one task needs shared state.

### 5.2. Looking Up Only on Branches That Need It

```java
void handle(Request request) {
    if (request.requiresExport()) {
        ExportWorker worker = exportWorkers.get();
        worker.export(request);
    }
}
```

Assuming `Request` and `ExportWorker` are domain types and `exportWorkers` is an injected `Provider<ExportWorker>`. Branches that do not export never call the provider. This is **deferred access on the consumer side**; it does not guarantee a singleton `ExportWorker` was not already initialized by Spring at startup.

### 5.3. Do Not Call get() Eagerly Inside the Constructor

```java
public ReportService(Provider<ReportBuilder> builders) {
    this.builder = builders.get();
}
```

The snippet above resolves the target bean while creating `ReportService`, defeating consumer-controlled timing. To get a fresh `ReportBuilder` per report, store the provider:

```java
public ReportService(Provider<ReportBuilder> builders) {
    this.builders = builders;
}

public Report build(Input input) {
    return builders.get().build(input);
}
```

Both snippets are partial examples; `ReportService`, `ReportBuilder`, `Report`, and `Input` represent domain types rather than a standalone runnable program. In real code, declare all fields, types, and methods properly.

### 5.4. Do Not Hold Onto Prototypes Too Long

A prototype object created for one task may hold mutable state and resources. Scope its lifetime to that task; do not accidentally store the retrieved object in a singleton field forever. Providers defer creation/lookup, **they do not automatically destroy prototypes after use**. If a prototype bean holds files/sockets/connections, design explicit resource closing, such as `try-with-resources` when the type implements `AutoCloseable`.

## 6. Scope Determines What get() Returns

| Target Bean Scope | Typical Outcome of Two `get()` Calls | Significance of Timing Choice |
| --- | --- | --- |
| `singleton` | Same instance within a container | Defers access from consumer; singleton may already exist since startup. |
| `prototype` | Two new instances across two resolutions | Each task can request an independent bean at the right time. |
| `request` | Same instance within the same HTTP request, different across requests | Must be called while request scope is active and bound to the right request. |
| `session` | Reused within the same HTTP session, isolated across sessions | Needs an active session context in a web application. |
| Custom scope | Depends on registered scope policy | Provider honors scope; it does not define lifetimes itself. |

A `Provider<T>` can be injected into a singleton even when bean `T` has a shorter scope. However, calling a request-scoped bean from a thread without an active request can fail because the **scope is inactive**. Notably, using `ExecutorService` or `@Async` does not automatically propagate request context to worker threads.

In Spring, beans declared with `@Component` or `@Named` still default to **singleton** unless another scope is specified. Do not carry over scope defaults from another DI framework into Spring. To define a prototype in Spring:

```java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class OneUseProcessor {
    public String run(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
```

This is a valid Java class when Spring dependencies are present, though it has no `main`. You can inject `Provider<OneUseProcessor>` into a consumer to get a processor each time one is needed. Scope selection belongs on the **target bean**, not by changing the provider declaration.

## 7. Combining @Inject, @Named, and Qualifiers

### 7.1. @Inject Can Be Used to Inject Providers

```java
import jakarta.inject.Inject;
import jakarta.inject.Provider;
import org.springframework.stereotype.Component;

@Component
public final class ExportService {
    private final Provider<OneUseProcessor> processors;

    @Inject
    public ExportService(Provider<OneUseProcessor> processors) {
        this.processors = processors;
    }

    public String convert(String source) {
        return processors.get().run(source);
    }
}
```

This example pairs with `OneUseProcessor` from the previous section as component-scannable beans. `@Inject` marks the constructor to inject; Spring's `@Autowired` can also be used. With a single constructor, Spring also supports constructor injection without any annotation, though `@Inject` helps make the Jakarta DI contract explicit.

### 7.2. Choosing an Implementation with @Named at the Injection Point

Suppose two beans share type `MessageTransport`:

```java
@Bean("smtpTransport")
MessageTransport smtpTransport() {
    return new SmtpTransport();
}

@Bean("localTransport")
MessageTransport localTransport() {
    return new LocalTransport();
}
```

`MessageTransport` and the two implementations above are illustrative types that must be declared in your application. To select a specific bean at `get()` time:

```java
public NotificationService(
        @Named("smtpTransport") Provider<MessageTransport> transports) {
    this.transports = transports;
}
```

In a complete class, `NotificationService` has a matching `Provider<MessageTransport> transports` field. `@Named("smtpTransport")` on the **provider parameter** configures name-based candidate selection in Spring. Without a qualifier, if multiple same-type beans remain tied, `transports.get()` can throw `NoUniqueBeanDefinitionException`.

If one bean is marked `@Primary`, Spring can choose it for typed dependencies when no specific qualifier is given. Still, prefer explicit qualifiers when business logic truly requires a specific implementation; do not rely on coincidental names or bean counts.

### 7.3. @Named on a Bean vs. @Named at an Injection Point Play Different Roles

```java
import jakarta.inject.Named;

@Named("csvExporter")
public final class CsvExporter implements Exporter {
    // Exporter methods are implemented here.
}
```

This is a class outline: `Exporter` is an undeclared domain interface. `@Named` on a class lets the bean be discovered via component scanning and gives it a name; `@Named` on a provider parameter narrows candidates when retrieving the bean. Do not confuse the two roles despite the identical annotation name.

## 8. Missing Beans, Multiple Beans, and When Errors Occur

Successfully injecting `Provider<T>` does not guarantee `get()` will succeed later. A provider is a **request gateway**; the container resolves the target object only when the gateway is called.

| State at Lookup Time | Common `Provider<T>.get()` Outcome in Spring |
| --- | --- |
| Exactly one valid candidate | Returns bean according to its scope. |
| Zero candidates | `NoSuchBeanDefinitionException`. |
| Multiple unresolvable candidates | `NoUniqueBeanDefinitionException` (a kind of `NoSuchBeanDefinitionException`). |
| Candidate exists but initialization fails | Bean creation exception, such as `BeanCreationException` or related runtime exception. |
| Scope inactive | Scope exception, such as `ScopeNotActiveException` for applicable scopes. |

**Very easy mistake:** `NoUniqueBeanDefinitionException` is a subclass of `NoSuchBeanDefinitionException` in Spring. Therefore, demo code catching `NoSuchBeanDefinitionException` can also catch **non-uniqueness**, not solely complete absence. In the demo, `OptionalMetrics` was unregistered so `metrics=absent` matched our known setup; **do not use that catch style in real apps to conclude a bean is absent** when multiple candidates could exist.

If you need to separate the two scenarios in Spring:

```java
try {
    TaskHandler handler = handlers.get();
    handler.handle();
} catch (org.springframework.beans.factory.NoUniqueBeanDefinitionException ex) {
    // Multiple beans configured without selecting a single candidate.
} catch (org.springframework.beans.factory.NoSuchBeanDefinitionException ex) {
    // No matching candidate remaining.
}
```

This illustrative snippet assumes `handlers` is an injected `Provider<TaskHandler>` and `TaskHandler` has `handle()`. Always catch the subclass **before** the superclass. In real systems, it is usually better to ensure valid configuration, fail clearly, and use optionality only when business requirements genuinely allow it.

### When a Dependency Is Optional

`Provider#get()` has no "return if present, otherwise null" method. In Spring, there are two clearer approaches:

```java
// Approach 1: optional lookup at usage time.
org.springframework.beans.factory.ObjectProvider<Feature> features =
        /* injected by Spring */;
Feature feature = features.getIfAvailable();

// Approach 2: optional when constructing the consumer.
java.util.Optional<Feature> featureAtInjection =
        /* injected by Spring */;
```

This snippet introduces API types rather than standalone initialization expressions. `ObjectProvider<T>` is Spring's extended API and suits repeated optional lookups. `Optional<T>` expresses presence/absence **at injection**, without providing fresh lookups later. Where a dependency is mandatory, keep `Provider.get()` so misconfiguration surfaces clearly.

**Do not use:** `provider.get() == null` as a general optionality strategy, because a missing bean in Spring can throw an exception before the comparison even runs.

## 9. Providers and Dependency Cycles

A legitimate reason to use a provider is decoupling **when a bean is built** from **when another bean is used**. Structural flow example:

```text
A created first
  └─ holds Provider<B> without calling get() yet
B created afterward
  └─ constructor needs already-created A
A.callB() at runtime
  └─ provider.get() -> B
```

If both `A` and `B` inject each other directly via constructors, the container cannot resolve the initialization cycle. Replacing one edge with `Provider<B>` allows both to be created provided **`A` does not call `get()` inside its constructor, `@PostConstruct`, or too early while the graph is still assembling**.

Illustrative snippet:

```java
@Component
class A {
    private final Provider<B> bs;

    @Inject
    A(Provider<B> bs) {
        this.bs = bs; // get() not called yet
    }

    String callB() {
        return bs.get().message();
    }
}

@Component
class B {
    private final A a;

    @Inject
    B(A a) {
        this.a = a;
    }

    String message() {
        return "ready";
    }
}
```

Import `jakarta.inject.Inject`, `jakarta.inject.Provider`, and `org.springframework.stereotype.Component` so this compiles in a package. Both classes must be within a scanned package. `B` takes `A` to demonstrate the cyclic edge; `message()` does not call back into `A.callB()`, avoiding runtime recursion.

**Limitation:** Providers do not cure every circular dependency. If `A` calls `bs.get()` in its constructor before `B` can be constructed, initialization cycles still fail. If `B.message()` immediately calls `A.callB()`, the program risks infinite recursion at runtime. Consider splitting responsibilities or introducing events or an intermediary service instead of preserving overly tangled cycles.

## 10. Provider Compared with Other APIs

| Dependency Form | Resolution Timing | Notable API | Best Suited For |
| --- | --- | --- | --- |
| Constructor injection `T` | At consumer creation | Use `T` directly | Mandatory dependency, stable scope. |
| `jakarta.inject.Provider<T>` | When consumer calls `get()` | `get()` | On-demand lookup with a simple Jakarta DI interface. |
| Spring `ObjectFactory<T>` | When consumer calls `getObject()` | `getObject()` | Similar to Provider, using a minimal Spring API. |
| Spring `ObjectProvider<T>` | When calling lookup/stream methods | `getObject()`, `getIfAvailable()`, `getIfUnique()`, `stream()` | Optional or multi-bean lookups needing Spring extensions. |
| `@Lazy T` at injection point | When target proxy is first used | Call `T` methods via proxy | Keeping type `T` while deferring target resolution; mind proxy semantics. |
| `Optional<T>` | At consumer injection | `isPresent()`, `orElse()` | Optionality decided when consumer is created. |
| `ApplicationContext.getBean(...)` | When calling context | Lookup via container API | Infrastructure genuinely needing container operations. |

**Do not confuse names:** `Provider<T>` is not `ObjectProvider<T>`; although Spring supports both, they are **two different interfaces**. Likewise, `jakarta.inject.Provider<T>` is not CDI's `jakarta.enterprise.inject.Instance<T>`: `Instance<T>` adds candidate discovery/filtering in CDI environments. Use the right API for your container.

### When to Choose Jakarta Provider

You can choose `Provider<T>` when you only need `get()` and want business code tied only to the **Jakarta DI standard**, especially when sharing libraries across environments supporting that standard. Keep in mind that different containers have different scope policies, bean selection rules, and exception types; the portable contract is `Provider.get()`, **not** Spring-specific exception details.

Choose `ObjectProvider<T>` if domain logic truly needs `null` on absence, fallbacks, uniqueness checks, or streaming via `stream()`/`orderedStream()`. Inject `T` directly if no deferral is needed, as that exposes missing-dependency errors at startup.

## 11. Common Misconceptions

### 11.1. "Every get() returns a new object"

False for singletons. A provider re-queries the container; the container applies scope. Singletons normally share one instance per context, whereas prototypes yield a new instance per resolution. Configure target bean scope properly.

### 11.2. "Having a Provider makes the bean completely lazy"

False. A provider only defers **the consumer's lookup**. If the target is an eager singleton, the container may already have instantiated it during `refresh()`. If the goal is deferring singleton creation as well, consider `@Lazy` on the bean definition or another suitable configuration, while checking whether other dependencies force eager creation.

### 11.3. "Provider lets any thread use a request bean"

False. Request/session scopes require an active context. Calling `get()` outside a valid scope fails. Do not rely on providers to carry thread-local request contexts across background executors.

### 11.4. "With Provider, startup cannot fail from a missing bean"

A provider can delay failure until `get()`. If a bean is mandatory yet only used when production traffic hits a branch, misconfiguration may stay hidden at startup. Add integration tests or configuration checks in appropriate places to catch issues early.

### 11.5. "Calling get() in the constructor is still lazy lookup"

Target retrieval already happened inside the constructor, meaning **eagerly**. Hold the provider until the processing method or appropriate operational boundary.

### 11.6. "Provider automatically cleans up prototypes"

False. Spring runs initialization callbacks for prototypes, yet does not manage full prototype destruction callbacks after handing out the bean. Objects holding resources must implement independent closing mechanisms.

### 11.7. "Catching NoSuchBeanDefinitionException guarantees zero beans"

False, because `NoUniqueBeanDefinitionException` inherits from `NoSuchBeanDefinitionException` in Spring. Catch and classify exceptions accurately, or better yet, use qualifiers and sound dependency contracts to prevent ambiguity.

### 11.8. "@Named on Provider automatically creates a bean by name"

False. Qualifiers **select among registered beans**. If no matching bean exists, `get()` still fails. For Spring to manage a bean, register it via `@Bean`, component scanning, or an equivalent mechanism.

### 11.9. "A thread-safe Provider means a thread-safe target"

The container handles lookup and scope; it does not make every returned bean thread-safe. A mutable singleton still needs proper concurrency design. A prototype merely gives each lookup a separate object, not thread safety if shared across threads.

## 12. Testing to Confirm Bean Retrieval Timing

In pure-Java consumer unit tests, you can pass a fake provider **without Spring**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.inject.Provider;

public final class ProviderUnitDemo {
    record Attempt(int id) {}

    static final class Runner {
        private final Provider<Attempt> attempts;

        Runner(Provider<Attempt> attempts) {
            this.attempts = attempts;
        }

        int runOnce() {
            return attempts.get().id();
        }
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        Provider<Attempt> fake = () -> new Attempt(creations.incrementAndGet());

        Runner runner = new Runner(fake);
        System.out.println("before=" + creations.get());
        System.out.println("run1=" + runner.runOnce());
        System.out.println("run2=" + runner.runOnce());
        System.out.println("after=" + creations.get());
    }
}
```

This example is standalone at the Java code level, though it still needs `jakarta.inject-api` on the compile/runtime classpath. If placed as `ProviderUnitDemo.java` inside the same Gradle project above, you can run it by temporarily changing `application.mainClass` to `ProviderUnitDemo` or adding another Gradle run task.

Output of `main` in `ProviderUnitDemo`:

```text
before=0
run1=1
run2=2
after=2
```

A fake lambda provider lets you verify **when the consumer invokes lookup** via a counter. It does not test Spring scopes or qualifiers because the lambda behavior is test-defined. To verify real Spring behavior, create an `AnnotationConfigApplicationContext` and test that prototypes yield two distinct objects, singletons yield the same object, `@Named` picks the right bean, and missing-dependency lookups throw at call time.

### Pre-Production Checklist

1. Confirm whether the dependency truly needs timed lookup or can be injected directly.
2. Choose the target's scope: `singleton`, `prototype`, request, or another appropriate scope.
3. Decide whether one task needs **one** or **multiple** lookups and retain the object for the proper lifetime.
4. If multiple implementations exist, configure `@Named`/qualifiers or `@Primary` explicitly.
5. Clarify whether the dependency is mandatory or optional; `Provider.get()` represents a mandatory contract.
6. Test behavior when context/scope is inactive, candidates are missing, and bean factories fail.
7. Manage cleanup for resource-holding prototypes and thread safety for shared beans.

## 13. Self-Practice Questions and Answers

**Question 1.** A singleton injects `Provider<Session>`; `Session` is a prototype. Why is calling `get()` inside each `handle()` better than calling `get()` in the constructor?

**Answer:** Each `handle()` gets a fresh prototype instance per task boundary. Calling it in the constructor resolves one instance early and, if stored in a field, reuses it.

**Question 2.** Two `provider.get()` calls return the same object. Is the provider broken?

**Answer:** No. The target bean may be a singleton or another scope reusing instances within an active boundary. Check the scope rather than guessing from the API name.

**Question 3.** Why can code injecting `Provider<Formatter>` start up fine yet fail with multiple beans when calling `get()`?

**Answer:** The provider can be injected before Spring needs to pick a specific `Formatter`. At lookup time, if multiple candidates cannot be disambiguated by qualifiers/primary/autowire rules, Spring reports non-uniqueness.

**Question 4.** Where can `@Named` be placed to pick the right implementation via a provider?

**Answer:** Place `@Named("beanName")` on the `Provider<Interface>` injection point, and ensure a matching bean is registered under that name.

**Question 5.** In the complete example, if `Attempt` is changed to singleton, what observations change?

**Answer:** The container may instantiate `attempt` during refresh before `context-ready`; both `get()` calls return the same instance, so `process("A")` and `process("B")` print the same ID. `get()` remains an on-demand lookup, without forcing the container to construct a new object.

**Question 6.** If an optional bean may be absent, should you always wrap `Provider.get()` in `try/catch RuntimeException`?

**Answer:** No. That masks unrelated failures. If using Spring and the dependency is optional by design, `ObjectProvider.getIfAvailable()` or `Optional<T>` is a better fit depending on timing needs; if mandatory, let configuration errors surface.

## 14. Official Reference Documentation

- [Spring Framework 6.2 — Using JSR 330 Standard Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html): support for `jakarta.inject.Provider`, `@Inject`, `@Named`, and relation to `ObjectFactory`.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and web scopes.
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): qualifiers, bean names, and candidate selection rules.
- [Jakarta Dependency Injection — Provider API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/inject/provider): `get()` contract and scoped lookup capabilities.
- [Jakarta Inject — Inject API](https://javadoc.io/static/jakarta.inject/jakarta.inject-api/2.0.1/jakarta/inject/Inject.html): injection points and `@Inject` semantics.

**Core takeaway:** `Provider<T>` lets **the consumer choose when to call `get()`**. Spring decides which bean is supplied and its lifetime based on IoC configuration. Using providers well requires cleanly separating *lookup timing*, *target scope*, and *required/optional contracts*.
