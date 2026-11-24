# SmartInitializingSingleton After Creating Regular Singletons in Spring Framework

## 1. The Problem: Some Tasks Must Wait for the Entire Singleton Creation Phase

In the Spring IoC Container, a bean is created, dependencies are injected, callbacks such as `@PostConstruct` and `InitializingBean.afterPropertiesSet()` run, and only then is it considered initialized. Those callbacks belong to **each individual bean**. They do not mean all other singletons have finished being created.

Some tasks must wait until **the end of the pre-instantiation phase of regular (non-lazy) singletons**, for example:

- Validating configuration involving multiple components once default eager singletons have been initialized.
- Aggregating metadata from beans sharing an interface after they have completed normal initialization.
- Building an index of strategies/handlers registered in the container without accidentally forcing Spring to create other beans too early.
- Validating cross-bean constraints, such as requiring at least one handler for an event type.
- Finalizing an internal registry before the `ApplicationContext` publishes its context-refreshed event.

Spring provides the **`org.springframework.beans.factory.SmartInitializingSingleton`** callback for this purpose. The interface was introduced in Spring Framework 4.1 and continues to be used in Spring Framework 6.x/7.x.

```java
package org.springframework.beans.factory;

public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
```

This is an illustrative API signature from Spring, **not** source code you redeclare in your project. A singleton bean can `implements SmartInitializingSingleton`; when the `BeanFactory` finishes its regular singleton creation phase, Spring invokes `afterSingletonsInstantiated()` on eligible instances.

**What is guaranteed:** at the time the callback is invoked, **regular singleton beans** have been created and initialized according to the standard singleton creation algorithm. **What is not guaranteed:** that all lazy, prototype, or request/session-scoped beans already have instances; that all external services are ready; or that all application-level startup logic has completed.

## 2. Callback Position in the Spring Container Lifecycle

A typical path when refreshing a Spring `ApplicationContext`:

```text
ApplicationContext.refresh()
   |
   +-- read/process bean definitions
   +-- register BeanFactoryPostProcessors / BeanPostProcessors
   +-- prepare infrastructure (event multicaster, etc.)
   |
   +-- finishBeanFactoryInitialization(...)
   |     |
   |     +-- preInstantiateSingletons()
   |           |
   |           +-- create regular non-lazy singletons
   |           |     +-- constructor / @Bean factory
   |           |     +-- dependency injection
   |           |     +-- @PostConstruct
   |           |     +-- InitializingBean.afterPropertiesSet()
   |           |     +-- custom init method
   |           |     +-- BeanPostProcessor after initialization
   |           |
   |           +-- SmartInitializingSingleton.afterSingletonsInstantiated()
   |
   +-- finishRefresh()
         |
         +-- start lifecycle processor / SmartLifecycle per configuration
         +-- publish ContextRefreshedEvent
```

This diagram is a useful overview for a typical `AbstractApplicationContext`/`DefaultListableBeanFactory`. Certain special mechanisms such as background initialization, circular references, factory beans, and custom contexts can differ in detail. Do not treat the diagram as an absolute guarantee of order **between independent singletons**.

### Milestones to distinguish

| Milestone | When? | Does it know all regular singletons are created? |
| --- | --- | --- |
| Constructor | Creating that specific bean | No |
| Field/setter injection | Populating bean dependencies | No |
| `@PostConstruct` | Initialization of each target after injection | No |
| `InitializingBean.afterPropertiesSet()` | End of the bean's local initialization phase | No |
| `@Bean(initMethod=...)` | Custom initialization method for the bean | No |
| `BeanPostProcessor.postProcessAfterInitialization` | After each bean's init; may create proxy | No |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | End of the singleton pre-instantiation phase | **Yes**, within the scope of regular singletons |
| `ContextRefreshedEvent` | `ApplicationContext` refresh completes | Context has refreshed; context-level hook |
| `ApplicationRunner`/`CommandLineRunner` (Spring Boot) | After Boot context initialization completes | Boot startup logic, not a per-bean hook |

Normally, bean A's `@PostConstruct` runs **before** bean B's `afterSingletonsInstantiated()`. All regular beans have finished initialization when B's callback starts, yet **other beans'** `afterSingletonsInstantiated()` callbacks may not have run yet.

That is an important limit: do **not** treat bean A's callback as proof that bean B's callback has completed. If A truly depends on a specific result from B's callback, design a coordination mechanism or organize a single orchestration bean rather than relying on bean registration order.

## 3. How Spring Invokes This Interface

In Spring's common implementation, `DefaultListableBeanFactory.preInstantiateSingletons()` conceptually has two steps:

1. Iterate through the bean definitions and initialize singletons that require eager instantiation. Dependent beans are created as required by the dependency graph.
2. After that step finishes, find created singletons implementing `SmartInitializingSingleton` and invoke `afterSingletonsInstantiated()`.

```text
Bean definitions:
   alpha       -> eager singleton
   beta        -> eager singleton
   inspector   -> eager singleton, implements SmartInitializingSingleton
   lazyCache   -> @Lazy singleton
   factory     -> prototype

During pre-instantiation:
   alpha, beta, inspector are initialized per Spring rules
   (exact order depends on dependencies/definitions).

After regular singletons have been created:
   inspector.afterSingletonsInstantiated()

If getBean("lazyCache") is called later:
   lazyCache is created on demand;
   the past callback is not automatically re-invoked for lazyCache.
```

Difference from `InitializingBean`: `afterPropertiesSet()` runs at **the end of creating one specific bean**, so if it looks up all beans by type with `getBeansOfType()`, it risks initializing beans whose turn hasn't come yet. `afterSingletonsInstantiated()` is meant for this because regular singletons have already finished eager initialization.

However, `getBeansOfType(SomeType.class)` can still touch **lazy beans** or `FactoryBean`s depending on the API and declarations. Thus, "not accidentally initializing regular singletons too early" does not mean "every lookup creates zero extra objects". In environments with lazy beans, consider `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` to discover names without triggering eager initialization of `FactoryBean`s; even with names in hand, only call `getBean()` when you actually intend to instantiate.

## 4. Complete Runnable Spring Core Example with Java 17+

The example uses Spring Framework **6.2.18**, Java 17+, and Maven 3.9+; no Spring Boot, web server, or database is required. We declare two `Module` singletons and one `ModuleInspector`. Each module sets an `initialized` flag in `InitializingBean.afterPropertiesSet()`. At the end of singleton creation, the inspector finds both modules, verifies both are initialized, and prints the result. Output does not depend on the creation order of the two modules.

**Project structure:**

```text
smart-singletons/
├── pom.xml
└── src/main/java/edu/example/smart/
    ├── AppConfig.java
    ├── Module.java
    ├── ModuleInspector.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>smart-singletons</artifactId>
    <version>1.0.0</version>
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
                <configuration>
                    <mainClass>edu.example.smart.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/smart/Module.java**

```java
package edu.example.smart;

import org.springframework.beans.factory.InitializingBean;

public final class Module implements InitializingBean {
    private final String name;
    private boolean initialized;

    public Module(String name) {
        this.name = name;
    }

    @Override
    public void afterPropertiesSet() {
        // Called by Spring during this module's own initialization.
        initialized = true;
    }

    public String name() {
        return name;
    }

    public boolean initialized() {
        return initialized;
    }
}
```

**src/main/java/edu/example/smart/ModuleInspector.java**

```java
package edu.example.smart;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.ApplicationContext;

public final class ModuleInspector implements SmartInitializingSingleton {
    private final ApplicationContext context;
    private boolean checked;

    public ModuleInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void afterSingletonsInstantiated() {
        // Right moment: other regular singletons have finished init.
        List<Module> modules =
                new ArrayList<>(context.getBeansOfType(Module.class).values());
        modules.sort(Comparator.comparing(Module::name));

        if (modules.size() != 2 ||
                modules.stream().anyMatch(m -> !m.initialized())) {
            throw new IllegalStateException("Modules are not fully initialized");
        }

        String names = String.join(",",
                modules.stream().map(Module::name).toList());
        checked = true;
        System.out.println("callback: " + names + " initialized");
    }

    public boolean checked() {
        return checked;
    }
}
```

**src/main/java/edu/example/smart/AppConfig.java**

```java
package edu.example.smart;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public Module alpha() {
        return new Module("alpha");
    }

    @Bean
    public Module beta() {
        return new Module("beta");
    }

    @Bean
    public ModuleInspector inspector(ApplicationContext context) {
        return new ModuleInspector(context);
    }
}
```

**src/main/java/edu/example/smart/Main.java**

```java
package edu.example.smart;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ModuleInspector inspector = context.getBean(ModuleInspector.class);
            System.out.println("main: checked=" + inspector.checked());
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Lines printed by the program to `System.out` (in order):**

```text
callback: alpha,beta initialized
main: checked=true
```

Maven/Spring may produce separate logs; the two lines above are application output. `AnnotationConfigApplicationContext(AppConfig.class)` calls `refresh()` inside its constructor, so the callback is invoked **before** `context.getBean(ModuleInspector.class)` in `Main` executes. The module names are sorted before printing, so the result is independent of whether Spring chooses to create `alpha` or `beta` first. This is a single-context program with no lazy beans or other interfering lifecycle callbacks.

**Why does this example prove the learning point?** When `afterSingletonsInstantiated()` is called, both `alpha` and `beta` already exist and have completed `InitializingBean.afterPropertiesSet()`; the `initialized()` check passes. If `ModuleInspector` were changed to do the same lookup inside its constructor or `@PostConstruct`, the lookup could trigger creating modules that had not yet been created. That is the side effect that the end-of-singleton-phase callback helps avoid for regular singletons.

### Marker interface version

This mechanism does not require a bean to declare a special annotation. Any eligible singleton can implement the interface:

```java
@Component
public class StartupRegistry implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Validate or aggregate a registry from created regular singletons.
    }
}
```

This snippet is illustrative; when using it, import `org.springframework.stereotype.Component` and `org.springframework.beans.factory.SmartInitializingSingleton`, and place it in a component-scanned context. If the class is not registered as a Spring singleton bean, no callback will occur even though it implements the interface.

## 5. The Concept of "All Singletons" Has Exact Boundaries

You must read the phrase "all regular singleton beans" in its proper context. It refers to standard singletons processed during the pre-instantiation phase, **not** "every object in every scope across every container".

| Case | Included in the end-of-pre-instantiation guarantee? | Conclusion about callback |
| --- | --- | --- |
| Default eager Spring-managed singleton | Yes, standard case | If implementing the interface, the callback is invoked |
| `@Lazy` singleton not yet created during bootstrap | No | Late on-demand creation does not re-trigger the callback |
| Prototype | No | `afterSingletonsInstantiated()` is not invoked per scope contract |
| HTTP request/session/application scoped target | Not part of regular singleton pre-instantiation | Do not expect this callback per request/session |
| WebSocket scoped target | No | Use a lifecycle mechanism suitable for WebSocket sessions |
| Bean newly registered/created after context refresh | Not retroactive | Bootstrap callback is not a dynamic listener for new beans |
| Singleton in **another ApplicationContext** | Not in the same BeanFactory | Each container handles its own bootstrap phase |

**Lazy singletons:** If a bean is defined as `@Lazy` and `getBean()` is only called after context refresh, even if it implements `SmartInitializingSingleton`, the callback **does not run automatically** for a singleton created on demand after bootstrap. Therefore, do not put essential setup of a lazy service into this callback. For lazy beans, work required on creation should live in the bean's own constructor, `@PostConstruct`, or `InitializingBean`.

Anti-pattern example (illustrative snippet):

```java
@Lazy
@Component
class LazyIndexer implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Do not expect this to run if LazyIndexer is created after bootstrap.
    }
}
```

The snippet above requires importing `Lazy`, `Component`, and `SmartInitializingSingleton`; it is not standalone runnable source. If a lazy bean happens to be forced into creation **before** the bootstrap phase finishes by another dependency or lookup, observed behavior can differ; the safe rule is **never rely** on this callback for lazy-on-demand singletons.

**Factory-created beans:** `FactoryBean` and `SmartFactoryBean` have their own type detection and eager initialization rules, distinct from an ordinary singleton object. Do not infer from a `FactoryBean` name/type that all factory products have been created when the callback runs; if your design requires it, check flags and guarantee specific instances via explicit dependencies.

**Background bootstrap:** Spring Framework 6.2 introduces the `@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)` option for certain configurations. Background singletons normally must complete during the standard startup completion phase; a bean that is both `@Lazy` and background can finish later. When a specific happens-before relationship is needed, declare an explicit dependency instead of relying on thread ordering assumptions.

## 6. Comparison with @PostConstruct, InitializingBean, and ContextRefreshedEvent

### @PostConstruct: initialization of *the bean itself*

```java
@Component
class SchemaLoader {
    @PostConstruct
    void loadOwnSchema() {
        // Dependencies have been injected for this bean.
    }
}
```

Requires importing `Component` and `jakarta.annotation.PostConstruct`; this is an illustrative fragment. The callback runs during instance creation without waiting for all unrelated singletons. Good for validating properties, creating parsers, and preparing immutable maps. With Spring 6+/Java 17, use `jakarta.annotation.PostConstruct`, not the legacy `javax.annotation.PostConstruct`.

### InitializingBean.afterPropertiesSet(): also per-bean

```java
public class LocalIndex implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // After populating LocalIndex properties,
        // yet possibly before other singletons are created.
    }
}
```

This is a fragment requiring importing `org.springframework.beans.factory.InitializingBean`. `InitializingBean` couples directly to the Spring API, and differs from `SmartInitializingSingleton` in time scope: this callback runs right after local initialization; the "smart" callback runs after **the entire pre-instantiation phase**.

### ContextRefreshedEvent: context-level event

```java
@Component
class ContextObserver {
    @EventListener(ContextRefreshedEvent.class)
    public void refreshed() {
        // ApplicationContext has just refreshed successfully.
    }
}
```

This snippet requires importing `Component`, `EventListener`, and `ContextRefreshedEvent`. The event has `ApplicationContext`-level semantics, so in a parent/child context hierarchy, a listener may observe events from different contexts depending on event propagation and listener registration. If you only need the end of one BeanFactory's singleton creation phase, `SmartInitializingSingleton` avoids having to filter event sources.

In addition, `SmartInitializingSingleton` belongs to the `spring-beans` module and works even with an eligible `ListableBeanFactory`, without requiring `ApplicationContext`'s full event system. Conversely, `ContextRefreshedEvent` requires a context with event support.

### When to use ApplicationRunner / CommandLineRunner?

In Spring Boot, runners fit application-level startup work after the container has been refreshed, such as reading CLI arguments or running conditional bootstrap logic. Do not use `SmartInitializingSingleton` merely to run a job "once across the whole cluster": if there are 3 replicas, each instance/container still runs its own bootstrap phase.

### When to use Lifecycle / SmartLifecycle?

If you need to **start/stop a connection, polling loop, consumer, or scheduled task**, use `Lifecycle`/`SmartLifecycle` or Spring-managed infrastructure. They support start/stop, and `SmartLifecycle` provides phases and auto-startup. `SmartInitializingSingleton` only has a single init callback and does not manage shutdown, task cancellation, readiness, or lifecycle restarts.

| Requirement | Usually appropriate choice |
| --- | --- |
| Initializing a bean from its own dependencies | Constructor / `@PostConstruct` / `InitializingBean` |
| Aggregating multiple regular singletons after bootstrap | `SmartInitializingSingleton` |
| Reacting when ApplicationContext refreshes | `ContextRefreshedEvent` |
| Spring Boot-level startup logic | `ApplicationRunner`/`CommandLineRunner` |
| Managing start, stop, phase, cleanup for long-lived tasks | `SmartLifecycle` / `Lifecycle` |
| Ensuring bean X is created before bean Y | Constructor dependency or `@DependsOn` |
| Task that must run only once across the entire cluster | External coordination/leader election/lock outside the JVM, per domain needs |

## 7. Using getBeansOfType and Registries Properly

A sound pattern is registering strategy singletons with Spring and building a registry at the end of startup:

```java
public interface Exporter {
    String format();
    byte[] export(byte[] input);
}
```

```java
@Component
class ExportRegistry implements SmartInitializingSingleton {
    private final ListableBeanFactory factory;
    private Map<String, Exporter> byFormat = Map.of();

    ExportRegistry(ListableBeanFactory factory) {
        this.factory = factory;
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, Exporter> collected = new HashMap<>();

        for (Exporter exporter : factory.getBeansOfType(Exporter.class).values()) {
            Exporter previous = collected.putIfAbsent(exporter.format(), exporter);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate exporter format: " + exporter.format());
            }
        }
        byFormat = Map.copyOf(collected);
    }

    public Exporter require(String format) {
        Exporter exporter = byFormat.get(format);
        if (exporter == null) {
            throw new IllegalArgumentException("Unknown format: " + format);
        }
        return exporter;
    }
}
```

The registry snippets illustrate one application pattern, not a standalone runnable project. They need imports for `Component`, `ListableBeanFactory`, `SmartInitializingSingleton`, `Map`, and `HashMap`; concrete `Exporter` implementations must exist in the application. The registry uses `putIfAbsent` to detect duplicate keys and `Map.copyOf` to produce an immutable map once done. This design assumes the registry is used **after** the callback finishes. Do not have another bean call `registry.require(...)` inside its `@PostConstruct`, because the registry callback may not have run yet.

If the registry must be updated dynamically at runtime, a bootstrap callback is not enough. In that case you need an update mechanism with proper synchronization/publication: immutable snapshots via `AtomicReference<Map<...>>`, application events per your problem, or an explicit registration model.

**Be cautious when looking up by type:**
- `getBeansOfType(Exporter.class)` returns beans matching the type the container can determine. In varied configurations, proxies, generics, or `FactoryBean`s can affect type detection.
- The lookup can instantiate a lazy singleton not previously created. Only scan "all" when that impact is acceptable, or use non-eager name-listing APIs and filter by scope/bean definition.
- If prototypes must be excluded from the registry, inspect actual scope. Type lookup does not guarantee the result contains only singletons.
- If an exporter depends back on the registry and the registry calls the exporter during the callback, avoid cycles or premature invocations.
- When multiple exporters provide the same format, define an explicit conflict policy. Never assume the "first created" bean wins, because ordering is not an application contract.
- Some infrastructure beans may create proxies during post-processing; the end-of-pre-instantiation callback lets you access regular beans that have finished initialization, yet you should still use public APIs and avoid assuming the target type is a concrete implementation.

## 8. Callback Ordering Among Multiple SmartInitializingSingleton Beans

Suppose two independent beans both implement `SmartInitializingSingleton`:

```java
@Component
class RegistryA implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Populate A data.
    }
}

@Component
class RegistryB implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Use A data?
    }
}
```

The classes above require importing `Component` and `SmartInitializingSingleton`. Do not assume A's callback is guaranteed to run before B's callback based on class names, classpath scanning order, or merely adding `@Order`. This interface has no contract sequencing dependent callbacks. In a specific implementation they may be called in singleton registration order, yet that order can shift whenever configuration changes.

To satisfy the invariant "B needs A's completed result", you can:
1. Combine building A and B into **one** orchestration bean; call `prepareA()` then `prepareB()` in the same callback.
2. Put A's data into a prepared state during A's local init (`@PostConstruct`), so B's callback reads that data after pre-instantiation.
3. If this involves managing long-running processes or multiple phases, use `SmartLifecycle` with appropriate phases/depends-on.
4. Design an explicit API returning completed data, avoiding timing dependencies between two callbacks.

`@DependsOn("registryA")` ensures the dependency is **initialized** before the dependent bean, but does not mean `registryA`'s `afterSingletonsInstantiated()` callback runs before `B`'s callback: both callbacks belong to the final phase. This is an easily missed distinction between bean initialization order and smart callback order.

## 9. If the Callback Throws an Exception

`afterSingletonsInstantiated()` runs while Spring finishes bootstrap. If the method throws an unchecked exception, context refresh can fail; the application typically reports a startup error with the cause. For a registry needing consistency guarantees, this can be an appropriate **fail-fast** mechanism:

```java
@Override
public void afterSingletonsInstantiated() {
    if (requiredStrategies.isEmpty()) {
        throw new IllegalStateException(
                "No strategy bean registered for this application");
    }
}
```

This is a fragment belonging to a class already implementing the interface, needing a `requiredStrategies` field of the right type; it is not standalone runnable source. If the callback creates resources and then fails, do not expect every cleanup hook to run in all situations, especially if the process crashes or the context never finished refreshing. Manage local cleanup and only publish completed state after validation succeeds.

Distinguish:
- **Required configuration violation**: throw a clear exception and halt startup.
- **External service temporarily unavailable**: avoid infinite loops or blocking startup without timeouts; consider post-startup readiness/retries.
- **Long asynchronous tasks**: use an appropriate lifecycle component/runner, rather than spawning ad-hoc threads from the callback and ignoring shutdown.

A bean created inside a startup callback can trigger new side effects and make "regular singletons have finished creation" harder to reason about; keep the callback focused on **validation, registry synthesis, and preparing state** from existing dependencies.

## 10. Concurrency, Multiple Containers, and Application Scope

`SmartInitializingSingleton` normally runs synchronously during `preInstantiateSingletons()` of a standard BeanFactory. However, the callback **does not** grant a lock over all singletons or make every object thread-safe. If the callback publishes a mutable registry for subsequent concurrent requests, you still must ensure readers see only complete state and any runtime updates are properly synchronized.

For applications that do not expose beans to other threads before initialization finishes, storing an immutable snapshot in the callback can suffice for concurrent reads after startup. Yet if a bean leaks itself to another thread in its constructor/init or mutates state after publication, never rely on the bootstrap callback as a substitute for synchronization.

### Parent/child contexts

An application can have a root `ApplicationContext` and one or more child contexts (e.g., separately configured web components). Each BeanFactory bootstraps **its own** singletons. A callback in a child does not merge root/child into a JVM-wide singleton scope. When coordinating across contexts, clarify bean ownership and lifetimes rather than assuming a "once across all ApplicationContexts" callback.

### Multiple processes/pods

Multiple replicas running the same application each have their own BeanFactory and run their own bootstrap callbacks. Do not use `afterSingletonsInstantiated()` to perform migrations, send emails, reset data, or run jobs that must happen **exactly once system-wide**. For those, use migration tooling, DB constraints, distributed leaders/locks, or job services with matching semantics.

### When using Spring Boot

In Spring Boot, the `ApplicationContext` is refreshed before runners execute; `SmartInitializingSingleton` belongs to the bean factory bootstrap process, not a "server has started listening on its port" callback. If you need to ensure the system is ready to serve traffic, use Boot's appropriate lifecycle and readiness mechanisms, verifying each external dependency as needed, instead of equating this callback with Ready status.

## 11. Common Mistakes

| Error / symptom | Cause | How to fix |
| --- | --- | --- |
| `afterSingletonsInstantiated()` is not called | Object created with `new` or not registered as a Spring-managed singleton | Register `@Component`/`@Bean` properly and let BeanFactory create the instance |
| Lazy singleton created after startup does not run callback | Callback only runs at the end of pre-instantiation | Use `@PostConstruct`/`InitializingBean` for lazy bean initialization |
| Prototype implements the interface without receiving callback | Interface is not a per-prototype lifecycle | Use appropriate local initialization |
| Bean A fetches all beans by type inside `@PostConstruct` | Lookup may trigger eager initialization of other beans too early | Move whole-regular-singleton registry building to the smart callback |
| Calling `getBeansOfType()` unexpectedly creates lazy beans | The method may instantiate listed beans | Use controlled type/name discovery, filter by scope, and avoid unnecessary `getBean` calls |
| Registry is read before the callback runs | Another bean queries the registry during local init | Avoid lookups in local init; design readiness or create after bootstrap |
| Specifying `@Order`/`@DependsOn` expecting smart callbacks to be ordered | Initializing a bean earlier does not guarantee its smart callback runs earlier | Consolidate orchestration or choose a phased lifecycle |
| Starting a background consumer directly from the callback | Interface does not support stop/phase/readiness | Use `SmartLifecycle`, listener containers, or Spring-managed executors |
| Test calls `getBean` without seeing smart callback | Test uses a BeanFactory that never called `preInstantiateSingletons()` or object bypassed container | Use `AnnotationConfigApplicationContext.refresh()` or trigger bootstrap on the BeanFactory |
| Callback executes across multiple pods | Each context has its own lifecycle | Design distributed coordination when exactly-once is required |
| Callback runs before `ContextRefreshedEvent` | This is the standard order during context refresh | Choose `ContextRefreshedEvent` if a context-level event is needed |
| Callback error causes startup failure | Invariant violation or unchecked exception | Validate intentionally, state clear reasons, and handle cleanup |
| Building a mutable registry and updating it unsynchronized later | Bootstrap callback does not imply runtime synchronization | Use immutable snapshots/atomic publication or locks matching invariants |

## 12. Self-Check Exercises

1. How does `@PostConstruct` differ from `SmartInitializingSingleton.afterSingletonsInstantiated()`?
2. In a context with 5 eager singletons, an inspector implements the interface; when the inspector's callback begins, have those regular singletons finished standard initialization?
3. A `@Lazy` bean was not created at startup and is only created via `getBean` after context refresh. Does its smart callback run automatically?
4. A prototype bean implements `SmartInitializingSingleton`: is the smart callback called every time a new prototype is created?
5. If bean A's `@PostConstruct` calls `getBeansOfType(Handler.class)`, what can happen to beans whose turn to be created has not come yet?
6. Why is `afterSingletonsInstantiated()` well suited for building a registry of eager singleton strategies?
7. Does `@DependsOn("A")` on bean B guarantee A's smart callback runs before B's smart callback?
8. Which hook should you choose to manage start/stop of a long-running consumer?
9. A Spring Boot service has 4 pods. How many times in total is a singleton bean's smart callback called if each pod has a corresponding container and the callback is eligible?
10. If you need to read all singletons without prematurely creating `FactoryBean`s, which parameter of `getBeanNamesForType` should you consider?
11. Should you use the smart callback to determine whether the HTTP server is ready to accept traffic?
12. In the runnable example, why is `callback: alpha,beta initialized` printed before `main: checked=true`?

**Suggested answers:**

1. `@PostConstruct` runs per **individual bean** lifecycle; the smart callback runs after the regular singleton creation phase.
2. Yes, within the pre-instantiation guarantee.
3. No; lazy-on-demand beans created after bootstrap do not get that callback invoked again.
4. No; prototypes do not participate in the singleton bootstrap smart callback.
5. The lookup can initialize handlers that had not yet been created, causing side effects inside A's local initialization.
6. Regular singletons are already created and locally initialized, avoiding creating them prematurely just by scanning a registry.
7. No; initialization dependency does not establish ordering between two smart callbacks.
8. `Lifecycle`/`SmartLifecycle` or a listener/consumer container.
9. Potentially four times, once per container; not once across the entire cluster.
10. The `allowEagerInit` parameter and singleton/`FactoryBean` filtering rules; do not treat lookup results as side-effect-free if `getBean()` is called afterward.
11. No; this is a BeanFactory bootstrap milestone, not a health/readiness signal.
12. The `AnnotationConfigApplicationContext(AppConfig.class)` constructor calls refresh before returning, so the bootstrap callback finishes before `main` retrieves the bean.

## Official Documentation

- Spring Framework 6.2.18 — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Bean Lifecycle / Customizing Bean Nature: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Java-based Container Configuration, singleton startup, lazy and depends-on: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework — `ListableBeanFactory` and `getBeansOfType`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/SmartLifecycle.html
