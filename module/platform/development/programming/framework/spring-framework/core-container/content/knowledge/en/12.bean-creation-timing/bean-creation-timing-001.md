# Eager Singleton Initialization and Pre-Instantiation in Spring Core Container

## 1. Lesson Objectives

One of the most important behaviors of the Spring IoC Container is **bean creation timing**. With `ApplicationContext`, Spring by default **creates and configures non-lazy singletons right during context startup** (*eager singleton initialization / singleton pre-instantiation*). Thanks to this, errors such as missing dependencies, constructor failures, misconfigurations, or faulty initialization callbacks are typically caught before the application begins processing work.

This concept is easily misunderstood in two directions:

- "A singleton is only created on the first `getBean()` call" — **not true by default with `ApplicationContext`**.
- "Having a bean definition means the object has already been created" — **not true**. A definition is metadata, whereas the instance appears at a later stage.
- "`@Lazy` guarantees a bean is never created at startup" — **not absolute**. An eager singleton with a required dependency on a lazy bean can force Spring to create the lazy bean to fulfill the dependency.
- "Pre-instantiation means creating all beans of every scope" — **not true**. It mainly applies to **non-lazy singletons**, with specific exceptions and details for `FactoryBean`, the dependency graph, and bootstrap mechanisms.

This lesson belongs to the **Bean Creation Timing** section of **Spring Framework – Core Container**, aiming to help you:

1. Distinguish `BeanDefinition`, bean instance, singleton scope, and the singleton cache.
2. Understand when `ApplicationContext.refresh()` performs pre-instantiation.
3. Understand the default **eager singleton** behavior and why Spring prioritizes failing fast.
4. Use `@Lazy`, XML `lazy-init`, `default-lazy-init`, and understand how dependencies cause a lazy bean to be created early.
5. Compare `ApplicationContext` with low-level `BeanFactory` usage.
6. Know the difference between *registered*, *currently in creation*, *fully initialized*, and *present in the singleton cache*.
7. Understand the relationship between constructors, dependency injection, `@PostConstruct`, `InitializingBean`, `initMethod`, and `BeanPostProcessor`.
8. Understand the `SmartInitializingSingleton.afterSingletonsInstantiated()` callback at the end of the pre-instantiation phase.
9. Know why `@DependsOn` expresses ordering rather than replacing constructor dependencies or job orchestration.
10. Diagnose slow startup, bean creation failures, circular dependencies, and startup side effects.
11. Write and run **Java 17 + Spring Framework 6.2** examples with deterministic output that does not rely on accidental bean creation order.
12. Check whether a bean has actually been created using the appropriate API and build lifecycle-based integration tests.

**Core principle:** **singleton** answers the question "how many instances are managed for a bean definition within a container?", while **eager/lazy** answers the question "when is the instance created?". These two axes are conceptually independent.

## 2. What Is a Singleton in Spring?

By default, a Spring bean definition has `singleton` scope:

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    AccountService accountService() {
        return new AccountService();
    }
}
```

This is an **illustrative snippet**, requiring a real `AccountService` class. When the BeanFactory manages the `accountService` bean in singleton scope, lookups for this bean within the same container normally receive the same reference:

```java
// Illustrative snippet using an already created context variable.
Object first = context.getBean("accountService");
Object second = context.getBean("accountService");
System.out.println(first == second); // true
```

Spring stores and returns the managed singleton instance; it does not invoke the factory method once per `getBean()`.

### Spring's Singleton Is Not the GoF Singleton Pattern

| Aspect | Spring singleton scope | GoF Singleton pattern |
| --- | --- | --- |
| Unit of management | Per **bean definition**, within one **container** | Usually controlled by class/classloader or a static field |
| Creation mechanism | BeanFactory based on bean metadata and lifecycle | In-class logic such as private constructor + static method |
| Flexibility | One class can have multiple bean definitions with different names | Usually targets one global instance |
| Testing | Each test ApplicationContext can have its own singletons | Global static instance easily causes shared state |
| AOP/proxy | Bean reference may be a managed proxy | Not a characteristic of the pattern |

If an ApplicationContext declares two bean names using the same `Client` class, the container can create **two independent singletons**. "Singleton" does not mean there is strictly one object per Java class across the entire JVM.

### Scope and Creation Timing Are Two Different Attributes

A `singleton` bean can be:

- **Eager:** created during context refresh, before application code calls `getBean()`.
- **Lazy:** created when the container first needs the instance.
- **Lazy but pulled in early by a dependency:** an eager singleton requires it as a constructor parameter.
- **Registered after the context is already active:** dynamic registration operations have their own lifecycle and should not by default be interpreted the same way as the initial refresh flow.

A `prototype` bean is normally created each time it is requested; it is not "bulk pre-instantiated" in a single refresh pass like a regular singleton.

## 3. A BeanDefinition Is Not a Bean Instance

Spring reads metadata from many sources: `@Configuration`/`@Bean`, component scanning, XML `<bean>`, or registration via `BeanDefinitionRegistry`. From those sources, it knows **which beans need to exist** before necessarily constructing objects.

Diagram:

```text
@Configuration / @Bean / @Component / XML
                     |
                     v
               BeanDefinition
        bean name, class/factory method,
        scope, lazy, dependencies, init...
                     |
                     v
       BeanFactory registers definition
                     |
                 On demand
        or singleton pre-instantiation
                     |
                     v
         Constructor / factory method
                     |
                     v
           Dependency injection
                     |
                     v
            Initialization phase
                     |
                     v
       Fully initialized managed bean
                     |
                     v
       Singleton cache / bean exposure
```

Some steps may nest, and Spring also handles `BeanPostProcessor`, AOP proxies, circular-reference protection, awareness callbacks, and related infrastructure. The diagram is a mental model, **not a complete description of every internal step** of every BeanFactory.

### Checking "Definition Exists" Differs from "Singleton Already Created"

With `ConfigurableApplicationContext`:

```java
// Illustrative snippet while the context is active.
boolean defined =
        context.getBeanFactory().containsBeanDefinition("client");
boolean instantiated =
        context.getBeanFactory().containsSingleton("client");
```

- `containsBeanDefinition("client")` asks whether the registry holds a **local definition** with that name; it does not mean it has been instantiated.
- `containsSingleton("client")` asks whether the singleton registry currently holds a **singleton object** for that name.
- `containsBean("client")` tells whether the bean name can be resolved (possibly considering parent/aliases per the API), **not** a test for "the object has already been built".
- `getBean("client")` **can itself cause the bean to be created**, so do not use it to inspect pre-instantiation state and then claim you did not affect what is being observed.

In addition, infrastructure can register singleton objects that do not originate from a regular BeanDefinition; that is why you should not assume the two APIs checking definitions and the singleton cache always agree.

## 4. Eager Singleton: The Default Behavior of ApplicationContext

In a standard `ApplicationContext`, Spring creates and configures **regular, non-lazy singleton beans** when the context is initialized/refreshed.

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // By the time the constructor returns, refresh has already
    // executed the default pre-instantiation phase.
}
```

This is an illustrative snippet; `AppConfig` needs to be declared and the `org.springframework.context.annotation.AnnotationConfigApplicationContext` API imported.

The key point is that **before entering the body of `try`**, the `AnnotationConfigApplicationContext(AppConfig.class)` constructor has already created and refreshed the context. Therefore an eager singleton may have already run its constructor/init callback even when user code has not looked up any bean yet.

### Why Does Spring Create Beans Early?

- **Fail fast:** Missing beans, converter errors, wrong properties, or constructor exceptions surface at startup.
- **Dependency graph:** Singletons are usually ready to serve the application's first call.
- **More predictable lifecycle:** Init callbacks of required beans execute before the context is considered done initializing.
- **Observability:** Configuration errors have a clear cause at startup instead of appearing randomly when the first user calls an API.
- **Container responsibilities:** `ApplicationContext` can proactively prepare a range of infrastructure beans such as listeners, lifecycle processors, and bean post-processors at the right stage.

In return, creating many singletons can make startup consume CPU, RAM, filesystem, I/O, and time connecting to external dependencies. You need to distinguish **legitimate bean construction cost** from **heavy business workflows stuffed into constructors/init callbacks**.

### What Exactly Does Spring Create?

A useful phrasing is: Spring pre-instantiates **regular, non-lazy singleton beans** in the BeanFactory. This is **not** a claim that every bean of every scope, lazy dependencies, or all external resources are ready.

A prototype bean is not created on its own just because a definition exists. However, if an eager singleton's constructor requires a prototype, Spring can **create a prototype instance** to inject into the singleton. That is **dependency-driven creation**, not "pre-instantiating all prototype beans".

## 5. Where Does the Pre-Instantiation Phase Sit in Refresh?

`ApplicationContext.refresh()` executes multiple steps to turn metadata into a ready-to-serve container. A conceptual flow:

```text
ApplicationContext.refresh()
   |
   +--> Prepare Environment and context
   |
   +--> Create / obtain BeanFactory, load bean definitions
   |
   +--> BeanFactoryPostProcessor / registry processing
   |
   +--> Register BeanPostProcessor
   |
   +--> Infrastructure: application events, message source, lifecycle...
   |
   +--> finishBeanFactoryInitialization(...)
   |       |
   |       +--> preInstantiateSingletons()
   |                |
   |                +--> Create regular non-lazy singletons
   |                +--> Resolve dependencies
   |                +--> Run bean-local initialization
   |                +--> SmartInitializingSingleton callbacks
   |
   +--> finishRefresh(...)
           |
           +--> Lifecycle startup via corresponding mechanism
           +--> ContextRefreshedEvent
```

This is a **simplified diagram** for a standard ApplicationContext, and does not commit to exact ordering details of every extension point, bean definition, event multicaster, or background task across all versions.

### What API Is preInstantiateSingletons()?

`org.springframework.beans.factory.config.ConfigurableListableBeanFactory` declares:

```java
void preInstantiateSingletons();
```

This method ensures pre-instantiation of **non-lazy singletons**, with special handling related to `FactoryBean`, and can throw `BeansException` if a bean cannot be created.

In an `ApplicationContext`, you normally **do not need to call this method manually**, because the `refresh()` lifecycle handles it. This API is useful for understanding the mechanism or when working with a `DefaultListableBeanFactory` at a low level.

### "Pre-Instantiated" Does Not Mean "Every Business Task Has Run"

Pre-instantiation completes the group of bean instances according to their lifecycle. It does not automatically:

- Seed a database or run business migrations unless code/infrastructure is registered to do so.
- Guarantee that a message broker, database cluster, or external APIs are healthy.
- Create all unused lazy singletons.
- Guarantee that scheduler/consumer lifecycles have finished starting before every other lifecycle milestone.
- Turn an init callback into an exactly-once mechanism across multiple replicas.

## 6. Distinguishing Plain BeanFactory and ApplicationContext

`BeanFactory` is the foundational IoC container interface. Some programs may use `DefaultListableBeanFactory` and register `BeanDefinition`s manually, then call `getBean` as needed.

If you only register a definition into a fresh `DefaultListableBeanFactory`, it **does not assume you want to populate all non-lazy singletons at registration time**. You can call `preInstantiateSingletons()` when needed or let them be created via `getBean()`.

By contrast, `AnnotationConfigApplicationContext`/`ClassPathXmlApplicationContext` typically orchestrate BeanFactory setup, BeanPostProcessors, and pre-instantiation inside `refresh()`.

### Illustrative Example

```java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "tool", new RootBeanDefinition(Tool.class));

// Definition exists, instance does not necessarily exist yet.
boolean before = factory.containsSingleton("tool");

// Manually trigger pre-instantiation:
factory.preInstantiateSingletons();
boolean after = factory.containsSingleton("tool");
```

This is an illustrative snippet; `Tool` must be a suitable class with a public constructor, and imports for `DefaultListableBeanFactory`/`RootBeanDefinition` are needed. A standalone runnable version of this idea is in Section 13.

**Do not use a raw BeanFactory demo to infer that all ApplicationContext features work automatically**: BeanPostProcessors, annotation-driven features, application events, and lifecycle orchestration have separate registration steps.

## 7. Lazy Singleton: Deferring Creation

`@Lazy` causes a bean definition to intentionally **not be pre-instantiated** like a regular eager singleton.

```java
@Configuration(proxyBeanMethods = false)
class Config {

    @Bean
    @Lazy
    HeavyCatalog heavyCatalog() {
        return new HeavyCatalog();
    }
}
```

This is an illustration requiring `HeavyCatalog`. If no eager bean has a required dependency on `HeavyCatalog`, the container can defer initialization until the first time it is requested.

In XML:

```xml
<bean id="heavyCatalog"
      class="example.HeavyCatalog"
      lazy-init="true"/>
```

### Default Eager and Explicit Lazy

| Bean definition | Scope | Lazy? | When is it typically created? |
| --- | --- | --- | --- |
| `@Bean CatalogRepository repository()` | default singleton | No | During `ApplicationContext.refresh()` |
| `@Bean @Lazy CacheClient cacheClient()` | singleton | Yes | On first request unless pulled in by an eager dependency |
| XML `<bean id="repo" .../>` | default singleton | No | When ApplicationContext refreshes |
| XML `<bean id="cache" ... lazy-init="true"/>` | singleton | Yes | On demand, unless needed by an eager bean |
| `@Scope("prototype")` | prototype | Not bound to eager singleton semantics | On demand, including when acting as a dependency |
| Lazy singleton dependency of an eager singleton | singleton | Yes | Can **be created at startup** |

Specifically: **lazy is not a new scope**. Once created, a lazy singleton still has normal singleton identity.

### @Lazy on a @Configuration Class

```java
@Configuration
@Lazy
class LazyConfiguration {
    @Bean
    ExpensiveClient client() {
        return new ExpensiveClient();
    }
}
```

According to the Spring reference, `@Lazy` on `@Configuration` can set default lazy initialization for bean definitions belonging to that configuration. However, singletons required by other eager beans can still be created, and infrastructure/configuration-processing mechanics have their own rules. Do not assume the entire context becomes "no beans initialized at all".

### XML default-lazy-init

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="client" class="example.Client"/>
    <bean id="service" class="example.Service"/>
</beans>
```

This is a namespace-simplified illustration; in a real application, declare the XML schema and full namespaces. `default-lazy-init="true"` sets default laziness for beans within that metadata scope. Beans with explicit `lazy-init="false"` can be marked eager, and the dependency graph can still cause lazy collaborators to be created early.

## 8. Trap: A Lazy Bean Is a Dependency of an Eager Singleton

This is an exception emphasized by the Spring docs.

Suppose:

```java
@Configuration(proxyBeanMethods = false)
class Config {

    @Bean
    @Lazy
    PriceRules priceRules() {
        return new PriceRules();
    }

    @Bean
    CheckoutService checkoutService(PriceRules priceRules) {
        return new CheckoutService(priceRules);
    }
}
```

The two types here are illustrative. `priceRules` has lazy metadata; however, `checkoutService` is a non-lazy singleton. When Spring needs to create `checkoutService` during refresh, it must pass a `PriceRules` instance into the constructor, so the `priceRules` bean is created **at startup**.

```text
checkoutService (eager singleton)
         |
         +--> constructor parameter: PriceRules
                            |
                            v
                   priceRules (lazy definition)
                            |
                            v
               Still instantiated during refresh
```

**Remember:** `@Lazy` on a **bean definition** does not automatically create a proxy for every dependency injection point. If an eager consumer needs the real instance to complete its constructor, the BeanFactory will resolve it.

### @Lazy at the Injection Point Differs from Lazy at the Definition

Spring also supports `@Lazy` at an injection point to create a **lazy-resolution proxy** in suitable situations:

```java
final class CheckoutService {
    private final PriceRules rules;

    CheckoutService(@Lazy PriceRules rules) {
        this.rules = rules;
    }
}
```

This snippet requires importing `org.springframework.context.annotation.Lazy`. At the injection point, Spring can inject a proxy that defers target resolution. However, using a proxy has type/proxy semantics limitations, and **does not fix circular dependencies or bad design** merely by deferring.

Moreover, if code invokes a method on the proxy inside a constructor or init callback, the target may still be created very early. Do not treat an `@Lazy` injection point as an absolute guarantee for all startup states.

## 9. How Does Prototype Differ from Pre-Instantiated Singleton?

`prototype` means the BeanFactory creates a new instance each time it is requested according to that scope's semantics.

```java
@Bean
@Scope("prototype")
Worker worker() {
    return new Worker();
}
```

This is an illustration requiring `Worker` and importing `Scope`. The `worker` bean will not be bulk pre-instantiated merely because it sits in the registry.

However:

```java
@Bean
JobRunner jobRunner(Worker worker) {
    return new JobRunner(worker);
}
```

If `jobRunner` is an eager singleton, Spring creates one `Worker` prototype to inject **when JobRunner is created**. `JobRunner` keeps that same worker unless its own logic replaces the reference; it does not automatically receive a fresh prototype on every `run()` call.

### Factory/Provider When a New Object Is Needed Each Time

```java
final class JobRunner {
    private final ObjectProvider<Worker> workers;

    JobRunner(ObjectProvider<Worker> workers) {
        this.workers = workers;
    }

    void runJob() {
        Worker fresh = workers.getObject();
        fresh.run();
    }
}
```

This is an illustration requiring importing `org.springframework.beans.factory.ObjectProvider` and a `Worker.run()` method. Each `getObject()` call for a prototype can create a new instance. However, do not use a provider merely to mask a constructor cycle or a missing required dependency.

### Prototype Destruction

The container performs initialization for the created prototype bean, but does not automatically manage destruction callbacks of every prototype like a singleton after handing the instance to the caller. If a worker owns files/sockets/resources, the application must design ownership and cleanup.

## 10. Lifecycle of an Eager Singleton

Pre-instantiation is not simply calling a constructor and storing the object. For a Spring-managed bean, there can be:

1. Registering the bean definition.
2. Selecting the constructor or `@Bean` factory method.
3. Resolving required bean dependencies.
4. Constructing the raw instance.
5. Dependency/property injection.
6. Applicable `Aware` callbacks.
7. `BeanPostProcessor` hooks and initialization annotations.
8. `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, and custom `initMethod` per Spring's mechanism.
9. Proxy wrapping and final post-processing.
10. Publishing the bean instance in the singleton registry per container semantics.

The steps may differ for infrastructure beans or extension points; especially with AOP/proxies, factory methods, `FactoryBean`, and early singleton references. The key point is that only once a bean has gone through the appropriate lifecycle should it be considered "ready".

### Constructor Runs Before @PostConstruct

```java
final class LocalIndex {
    private boolean ready;

    public LocalIndex() {
        ready = false;
    }

    void initialize() {
        ready = true;
    }
}
```

If declared with `@Bean(initMethod="initialize")`, Spring calls the init method after the factory creates the instance and prepares the corresponding injections. Inside a bean's init callback, do not assume every other bean across the entire context is ready.

### Do Not Run Heavy Business Logic in Constructors and @PostConstruct

The Spring 6.2 documentation notes that singleton initialization callbacks typically run under the management of the **singleton creation lock**. Heavy work, external I/O, or cross-accessing other beans from an init callback can prolong startup or cause deadlocks.

Appropriate:

- Validating local settings.
- Preparing a small internal lookup table.
- Asserting the bean's invariants.
- Initializing a resource that the bean genuinely owns under a designed lifecycle, with timeout/cleanup.

Consider a later mechanism for:

- Seeding business data.
- Calling multiple external APIs to prepare the system.
- Starting a long-running background worker.
- Coordinating transactions and readiness across multiple modules.

These tasks should have a dedicated startup coordinator or appropriate lifecycle extension point, rather than being attached arbitrarily to every constructor.

## 11. SmartInitializingSingleton: Hook at the End of the Pre-Instantiation Phase

`org.springframework.beans.factory.SmartInitializingSingleton` provides the callback:

```java
public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
```

A non-lazy singleton implementing this interface can be called **after the BeanFactory completes pre-instantiation of regular singletons**.

Benefits:

- A bean wishing to perform a post-initialization step can assume **regular non-lazy singleton beans** have been created.
- Reduces the risk of a `getBeansOfType(...)` call accidentally triggering early initialization right in the middle of the singleton creation phase.
- Suitable for multi-bean post-initialization work without requiring the ApplicationContext event model.
- Supported by an appropriate `ListableBeanFactory`, not only `ApplicationContext` listeners.

### Does the Callback Run for a Lazy Singleton Created After Startup?

**Not by default.** The Javadoc states this callback is not triggered for singletons that are lazy and only created on demand **after BeanFactory bootstrap**, nor is it triggered for other scopes.

If a coordinator needs to run at startup, ensure the coordinator itself is a managed **non-lazy singleton** created during the pre-instantiation phase.

### Is This Callback Spring Boot's ApplicationReadyEvent?

No. `SmartInitializingSingleton` lives in the Spring Framework beans module and runs at the end of **singleton pre-instantiation**; it does not mean the entire web server has published readiness or that all external systems are ready.

`ContextRefreshedEvent` is published after the appropriate refresh stages. `ApplicationReadyEvent` belongs to **Spring Boot**, typically occurring later in the Boot lifecycle. Do not conflate these milestones into a single concept of "the application has finished everything".

### When Should You Use SmartLifecycle Instead?

If a component has **phased start/stop** such as a consumer, poller, or long-running listener, Spring recommends `Lifecycle`/`SmartLifecycle` to manage start/stop, shutdown callbacks, and phase ordering. `SmartInitializingSingleton` is suitable for a short callback after pre-instantiation, not a place to put an infinite loop.

## 12. Runnable Example: Eager, Lazy, and Lazy Pulled In Early

The example uses **Java 17, Spring Framework 6.2.19, and Maven**. It does not require Spring Boot, a DB, network, or external files outside the project.

To avoid relying on Spring's **constructor output order**, we use a `Tracker` to record event milestones. The program only prints **states guaranteed by the dependency contract** after context refresh completes, so stdout is deterministic.

### 12.1. Project Structure

```text
spring-eager-singletons/
├── pom.xml
└── src/main/java/demo/
    └── EagerSingletonDemo.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-eager-singletons</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. Complete Java File

Create `src/main/java/demo/EagerSingletonDemo.java`:

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

public class EagerSingletonDemo {

    public static final class Tracker {
        private final Set<String> events = new HashSet<>();

        public void mark(String event) {
            events.add(event);
        }

        public boolean has(String event) {
            return events.contains(event);
        }
    }

    public static final class EagerCache {
        private final Tracker tracker;

        public EagerCache(Tracker tracker) {
            this.tracker = tracker;
            tracker.mark("eager.constructed");
        }

        public void initialize() {
            tracker.mark("eager.initialized");
        }

        public void shutdown() {
            tracker.mark("eager.destroyed");
        }
    }

    public static final class RequiredIndex {
        public RequiredIndex(Tracker tracker) {
            tracker.mark("required.created");
        }
    }

    public static final class OptionalGateway {
        public OptionalGateway(Tracker tracker) {
            tracker.mark("optional.created");
        }
    }

    public static final class EagerConsumer {
        private final RequiredIndex index;
        private final EagerCache cache;

        public EagerConsumer(RequiredIndex index, EagerCache cache) {
            this.index = index;
            this.cache = cache;
        }

        public boolean hasDependencies() {
            return index != null && cache != null;
        }
    }

    public static final class StartupCheck
            implements SmartInitializingSingleton {
        private final Tracker tracker;

        public StartupCheck(Tracker tracker) {
            this.tracker = tracker;
        }

        @Override
        public void afterSingletonsInstantiated() {
            tracker.mark("afterSingletons");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Tracker tracker() {
            return new Tracker();
        }

        @Bean(initMethod = "initialize", destroyMethod = "shutdown")
        public EagerCache eagerCache(Tracker tracker) {
            return new EagerCache(tracker);
        }

        @Bean
        @Lazy
        public RequiredIndex requiredIndex(Tracker tracker) {
            return new RequiredIndex(tracker);
        }

        @Bean
        @Lazy
        public OptionalGateway optionalGateway(Tracker tracker) {
            return new OptionalGateway(tracker);
        }

        @Bean
        public EagerConsumer eagerConsumer(
                RequiredIndex index, EagerCache cache) {
            return new EagerConsumer(index, cache);
        }

        @Bean
        public StartupCheck startupCheck(Tracker tracker) {
            return new StartupCheck(tracker);
        }
    }

    public static void main(String[] args) {
        Tracker tracker;

        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            tracker = context.getBean(Tracker.class);

            System.out.println("eager.constructed=" +
                    tracker.has("eager.constructed"));
            System.out.println("eager.initialized=" +
                    tracker.has("eager.initialized"));
            System.out.println("requiredLazy.created=" +
                    tracker.has("required.created"));
            System.out.println("optionalLazy.createdBefore=" +
                    tracker.has("optional.created"));
            System.out.println("afterSingletons.called=" +
                    tracker.has("afterSingletons"));
            System.out.println("consumer.dependencies=" +
                    context.getBean(EagerConsumer.class).hasDependencies());

            OptionalGateway first =
                    context.getBean(OptionalGateway.class);
            OptionalGateway second =
                    context.getBean(OptionalGateway.class);

            System.out.println("optionalLazy.createdAfter=" +
                    tracker.has("optional.created"));
            System.out.println("optionalLazy.sameSingleton=" +
                    (first == second));
        }

        System.out.println("eager.destroyedAfterClose=" +
                tracker.has("eager.destroyed"));
    }
}
```

### 12.4. Run Command

In the directory containing `pom.xml`:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.EagerSingletonDemo
```

### 12.5. Exact Expected Output

These are **the lines printed by the program**; logs from Maven and framework components (if any) are not counted in application stdout:

```text
eager.constructed=true
eager.initialized=true
requiredLazy.created=true
optionalLazy.createdBefore=false
afterSingletons.called=true
consumer.dependencies=true
optionalLazy.createdAfter=true
optionalLazy.sameSingleton=true
eager.destroyedAfterClose=true
```

### 12.6. Explanation of Each Group of Lines

**`eager.constructed=true`:** `eagerCache` is a non-lazy singleton. Spring creates it during refresh, so the constructor has already marked `eager.constructed` before the code in `main` checks it.

**`eager.initialized=true`:** `@Bean(initMethod = "initialize")` tells Spring to call `EagerCache.initialize()` after creating the bean and preparing dependencies. Thus by the time the ApplicationContext constructor returns, the bean has completed its local init callback.

**`requiredLazy.created=true`:** `requiredIndex` has `@Lazy`, but `eagerConsumer` is an eager singleton needing `RequiredIndex` via its constructor. The container is forced to create `requiredIndex` in order to complete `eagerConsumer`.

**`optionalLazy.createdBefore=false`:** `optionalGateway` also has `@Lazy`, but no eager bean requires it. Therefore immediately after refresh in the example, this object has not been created yet.

**`afterSingletons.called=true`:** `startupCheck` is an eager singleton implementing `SmartInitializingSingleton`. Spring calls the callback after completing pre-instantiation of regular non-lazy singleton beans, so the marker has been recorded.

**`consumer.dependencies=true`:** `EagerConsumer` receives both `RequiredIndex` and `EagerCache` via `@Bean` method parameters. Both references are non-null.

**`optionalLazy.createdAfter=true`:** When `main` calls `context.getBean(OptionalGateway.class)`, Spring creates the missing lazy bean. The constructor records the new mark in Tracker.

**`optionalLazy.sameSingleton=true`:** A lazy bean once created is still a singleton. Retrieving it twice in the same context returns the same reference.

**`eager.destroyedAfterClose=true`:** Exiting `try-with-resources` calls `ApplicationContext.close()`, triggering `@Bean(destroyMethod = "shutdown")` of `eagerCache`. The marker is read via the `tracker` Java reference still held in a local variable after the context closes, solely to prove the lifecycle callback; you should not continue using managed beans for business logic after the container has closed.

### 12.7. What Makes This Example Reliable

- All bean classes are `public static` nested classes; Spring can create them from Java `@Bean` methods without needing an outer object.
- There is no static mutable global counter; state belongs to the current context's `Tracker` bean.
- Does not rely on `HashSet` iteration order to print results, only membership checks. Therefore internal bean construction order does not affect stdout order.
- Does not call `getBean(OptionalGateway.class)` **before** printing `optionalLazy.createdBefore`.
- `@Configuration(proxyBeanMethods=false)` is safe because dependencies are passed via **factory method parameters**, without directly calling another `@Bean` method.
- Does not use Spring Boot, `@SpringBootApplication`, or a web server; `spring-context` is sufficient for this code.
- Uses `try-with-resources` to demonstrate cleanup of the managed singleton.

## 13. Standalone Experiment with Plain BeanFactory

To understand the difference between **registration** and **pre-instantiation**, here is a small project running with the Maven dependency from Section 12. Create a second Java file `src/main/java/demo/BeanFactoryPreInstantiationDemo.java`:

```java
package demo;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;

public class BeanFactoryPreInstantiationDemo {

    public static final class Tool {
        public Tool() {
        }
    }

    public static void main(String[] args) {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();

        factory.registerBeanDefinition(
                "tool", new RootBeanDefinition(Tool.class));

        System.out.println("definition=" +
                factory.containsBeanDefinition("tool"));
        System.out.println("before=" +
                factory.containsSingleton("tool"));

        factory.preInstantiateSingletons();

        System.out.println("after=" +
                factory.containsSingleton("tool"));

        factory.destroySingletons();

        System.out.println("afterDestroy=" +
                factory.containsSingleton("tool"));
    }
}
```

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanFactoryPreInstantiationDemo
```

Output:

```text
definition=true
before=false
after=true
afterDestroy=false
```

**Explanation:**

1. `registerBeanDefinition` registers metadata, so `definition=true`.
2. No instance has been requested and pre-instantiation has not run yet, so `before=false`.
3. `preInstantiateSingletons()` triggers creation of the non-lazy singleton `tool`, so `after=true`.
4. `destroySingletons()` releases singleton instances in the registry in this low-level BeanFactory example, so `afterDestroy=false`.

**Limitation:** This BeanFactory demo illustrates registration and the singleton cache, and does not reproduce the entire `ApplicationContext.refresh()` lifecycle. You should not replace ApplicationContext in normal applications just to manually control creation timing if you still need full annotations, events, and lifecycle infrastructure.

## 14. How to Configure in Spring XML

Although the main example uses Java configuration, eager/lazy mechanics also apply to bean definitions read from XML.

### 14.1. Default Eager Singleton

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalog" class="example.CatalogService"/>

</beans>
```

Assuming `example.CatalogService` has a valid constructor and complete classpath, this singleton bean will be pre-instantiated in `ClassPathXmlApplicationContext` by default.

### 14.2. Lazy on a Single Bean

```xml
<bean id="optionalClient"
      class="example.OptionalClient"
      lazy-init="true"/>
```

This bean is not pre-instantiated by default **if no other eager dependency needs it**.

### 14.3. Default Lazy for a Group of Beans

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="clientA" class="example.ClientA"/>
    <bean id="clientB" class="example.ClientB"/>
</beans>
```

The snippet omits the schema to focus on the attribute. An XML-reading BeanFactory can apply default laziness to definitions in that scope. Keep in mind that infrastructure beans and eager dependency requirements may still cause some objects to be created at startup.

### 14.4. Lazy Bean Referenced from an Eager Bean

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="lazyRules"
          class="example.PriceRules"
          lazy-init="true"/>

    <bean id="checkoutService"
          class="example.CheckoutService">
        <constructor-arg ref="lazyRules"/>
    </bean>
</beans>
```

Per dependency resolution rules, `checkoutService` is eager by default, so `lazyRules` is created early enough to be passed into the constructor. This is the **XML equivalent** of the `@Bean @Lazy` + eager consumer case in Java.

### 14.5. Prototype Scope in XML

```xml
<bean id="jobWorker"
      class="example.JobWorker"
      scope="prototype"/>
```

There is no concept of pre-instantiating all prototype beans in one pass because the number of instances depends on caller requests.

## 15. @DependsOn and Ordering Control

`@DependsOn`/XML `depends-on` can instruct the BeanFactory to **initialize one bean before another** when there is an ordering requirement outside constructor/property dependencies.

Java:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

XML:

```xml
<bean id="reportService"
      class="example.ReportService"
      depends-on="schemaValidator"/>
```

These are illustrative snippets requiring the definition of `schemaValidator` and the `ReportService` class. If `reportService` is created, Spring guarantees the `schemaValidator` bean is created beforehand according to the dependency ordering requested by metadata.

### Relationships Already Present via Constructor Do Not Need @DependsOn Again

```java
@Bean
ReportService reportService(ReportRepository repository) {
    return new ReportService(repository);
}
```

Here the BeanFactory must have `ReportRepository` to call the factory method creating `ReportService`. Therefore it is normally unnecessary to add `@DependsOn("reportRepository")` just to repeat an already explicit dependency.

### @DependsOn Does Not Guarantee Application Readiness

`@DependsOn` is not a job scheduler or business orchestration. It has no built-in transactions, retries, readiness, idempotency, or distributed coordination.

If `schemaValidator` exists only to run business logic when its constructor is called, check whether that is a task needing a dedicated startup coordinator/migration infrastructure. Do not attach heavy side effects to constructors just to force ordering.

### Circular Dependencies

If A has `@DependsOn("b")` and B has `@DependsOn("a")`, you have declared an unresolvable order. Spring cannot create both A before B and B before A. Similarly, constructor dependencies A→B→A must be fixed in the dependency graph and cannot be cured by reordering bean definitions.

## 16. Pre-Instantiation and BeanPostProcessor/AOP

In `ApplicationContext`, Spring registers various infrastructure beans **before** creating regular non-lazy singleton beans. A `BeanPostProcessor` can participate in the bean initialization phase and wrap the target with a proxy, for example to support certain AOP features.

This produces important rules:

- Do not call `getBean` arbitrarily inside a `BeanFactoryPostProcessor` to try to "warm up" business services; it can cause beans to be created **too early** before the required BeanPostProcessors are registered.
- `BeanFactoryPostProcessor`/`BeanPostProcessor` definitions may need to be created very early for the container to work, and do not simply follow all the same "regular eager singleton" rules as ordinary application services.
- A bean initialized early outside the post-processing cycle may not get AOP-proxied as expected, and Spring may emit diagnostics about eligibility.
- If a `@Configuration` defines a `BeanFactoryPostProcessor` via a non-static `@Bean`, the framework may have to instantiate the configuration class early. When appropriate, declare `static @Bean` for post-processors to avoid early config instance creation.
- When reading logs, distinguish target objects, proxy objects, and bean definitions; do not assume every constructor log proves callers will see that same raw reference.

### Can You Rely on Constructor Order Across Beans?

**You should not.** For independent beans, internal order can change depending on registration, dependencies, versions, and bootstrap options. Spring guarantees **necessary dependency ordering**, not business initialization ordering if you merely rely on log lines showing "bean A appeared before bean B".

To get meaningful ordering, express dependencies or use appropriate lifecycle orchestration. The main example deliberately checks **state at a stable milestone** instead of letting stdout depend on bean creation order.

## 17. FactoryBean During the Pre-Instantiation Phase

`FactoryBean<T>` is a Spring extension point that can create a **product bean**. It differs from a `@Bean` factory method and from an ordinary GoF factory class.

With BeanFactory, when a bean name corresponds to a `FactoryBean`:

- `getBean("name")` normally returns the **product** of the factory.
- `getBean("&name")` (the `&` prefix) returns the **FactoryBean object** itself.
- `FactoryBean.isSingleton()` determines whether the product supplied by the factory has singleton semantics.
- Pre-instantiation has special logic to create/check `FactoryBean` and, in cases marked eager-init, can initialize the product early per the `SmartFactoryBean`/container contract.

Do not conclude "every FactoryBean product is eager" or "every FactoryBean product is lazy". You must check:

1. Whether the factory's own definition is a non-lazy singleton.
2. Whether the product has singleton semantics.
3. Whether the factory supports eager product initialization.
4. Whether the dependency graph demands the product early.
5. Whether type inspection forces Spring to initialize the factory in order to determine the type.

### Be Careful with getBeansOfType and allowEagerInit

Some overloads of `getBeanNamesForType`/`getBeansOfType` take an `allowEagerInit` parameter. For a `FactoryBean`, type introspection sometimes requires initializing the factory to know `getObjectType()`. Therefore an operation "inspecting beans by type" is not always completely free of side effects.

If the goal is merely to check whether a singleton already exists at a given point, `containsSingleton(beanName)` is preferable to using `getBean` or iterating over all beans.

## 18. Pre-Instantiation and Circular Dependencies

Constructor cycle:

```java
final class Alpha {
    Alpha(Beta beta) {
    }
}

final class Beta {
    Beta(Alpha alpha) {
    }
}
```

If both are eager singletons with constructors requiring each other, the BeanFactory cannot complete initialization:

```text
alpha -> beta -> alpha (currently in creation)
```

Spring may throw `BeanCurrentlyInCreationException` or an exception chain of `UnsatisfiedDependencyException`/`BeanCreationException`, depending on the failing stage.

### Fail-Fast Is a Benefit, Not a Drawback

If the dependency graph is genuinely wrong, failing at startup helps you detect it before users interact with the app. Switching all beans to lazy may simply push the error to the first API call, making runtime failures harder to predict.

### Setter/Field Cycles Should Also Be Fixed by Design

Some setter/field injection cycles in Spring can be handled via early singleton references if the mechanism is enabled; however, code may observe incomplete state or unpredictable proxy semantics. Constructor cycles normally remain unresolvable.

**The sustainable solution** is to fix the dependency graph:

```text
Before:
OrderService <--> PaymentService

After:
CheckoutCoordinator --> OrderService
                   \-> PaymentService
```

Or extract a shared abstraction/policy so services do not have to inject each other. Do not enable circular-reference support just to bypass unclear design.

## 19. Is Faster Startup via Lazy Always Better?

No. Lazy defers the **instance creation cost**; it does not eliminate that cost.

If a bean is slow because it connects to a remote service or loads large datasets, turning the bean lazy can:

- Make startup faster.
- Make the **first request** slow or fail.
- Concentrate connection work during a moment under traffic pressure.
- Hide configuration errors until a rarely used feature is triggered.
- When multiple threads call concurrently, force concurrent callers to wait for initialization.

### When to Use Lazy

- Rarely used features.
- A bean with high construction cost that many application runs do not need.
- Optional integrations only called when users enable a feature.
- Tooling/admin beans not on the critical request-serving path.
- When you intentionally want deferred construction, with monitoring and timeouts.

### When to Keep Eager

- Core services used immediately after startup.
- Need to catch configuration errors before becoming ready to serve.
- Dependencies that must be validated early because they affect application safety.
- Need to complete resource initialization before accepting traffic.

**Pragmatic rule:** Prioritize fixing the root cause making construction heavy first. If a constructor loads millions of records, the issue may be business initialization placed in the wrong lifecycle; `@Lazy` merely shifts the workload to another request.

## 20. Startup Side Effects and Idempotency

Putting business commands inside an eager singleton's constructor:

```java
// Anti-pattern; application types would need to be defined separately.
final class WelcomeMailService {
    WelcomeMailService(MailGateway gateway) {
        gateway.sendWelcomeToAllUsers();
    }
}
```

accidentally causes every time an ApplicationContext pre-instantiates the bean to run the mail workflow. Multiple contexts in tests, application restarts, multiple replicas, or staging environments can cause business logic to run repeatedly.

Separate them:

- Constructor: store dependencies and validate invariants.
- Bean init callback: prepare small local resources/state, per the bean's contract.
- Startup coordinator: decide whether to run seeding/checks/migrations at the appropriate lifecycle stage.
- Service method: contain the business use case.
- Storage/transaction: ensure idempotency if the task may run repeatedly.

`SmartInitializingSingleton` can serve as a trigger point for a post-initialization step, but it does **not** automatically guarantee cluster-wide exactly-once execution. For DB seeding, use unique constraints/UPSERT or an appropriate coordination mechanism.

## 21. Common Errors and How to Diagnose Them

| Symptom | Likely explanation | How to check/fix |
| --- | --- | --- |
| Constructor runs even without `getBean()` | Eager singleton pre-instantiation in `ApplicationContext.refresh()` | Check scope and `@Lazy`/XML `lazy-init` |
| `@Lazy` bean is still created at startup | It is a dependency of an eager singleton | Draw the dependency graph; inspect injection points |
| `containsBeanDefinition` returns true, `containsSingleton` false | Metadata exists but instance has not been created yet | Expected for lazy or a BeanFactory not yet pre-instantiated |
| Prototype appears in startup logs | An eager singleton requested the prototype as a dependency | Check factory parameters/constructor injection |
| Bean is created twice despite singleton scope | Two contexts, two bean names, direct `new`, or factory method call outside the container | Check registry/identity/scope |
| Test passes in IDE, fails at prod startup | Different profiles/config/resource dependencies; eager validation exposes the mistake | Run integration tests with corresponding prod config |
| Startup is too slow | Many eager beans or init callbacks doing heavy I/O | Profile startup, check constructors and init methods |
| Lazy bean fails after first request | Dependency/config is only checked on demand | Test feature paths and readiness/fail-fast policy |
| `BeanCurrentlyInCreationException` | Circular dependency or early bean access | Draw the bean graph; remove constructor cycles |
| `@PostConstruct` hangs startup | Init callback performs heavy work/calls external beans | Move to an appropriate lifecycle coordinator |
| `SmartInitializingSingleton` callback does not run | Coordinator bean is lazy, prototype, or not registered in BeanFactory | Ensure it is an eager managed singleton |
| Callback runs but external system is not ready | Hook only guarantees regular singleton pre-instantiation | Design explicit dependency checks and readiness |
| `@Transactional` does not apply in init | Callback runs before proxy interception/self-invocation | Call the service through a managed proxy in the right phase |
| `@DependsOn` introduces a cycle | Ordering A→B and B→A | Remove the dependency cycle |
| BeanPostProcessor does not process a bean | Bean was created too early during a post-processor/bootstrap | Check for early getBean/configuration static @Bean |
| FactoryBean is initialized during type lookup | `allowEagerInit` or product type introspection | Use the inspection API appropriate for your need |
| `getBeanNamesForType` appears before bean creation | May read metadata types, not proof an instance exists | Use `containsSingleton`/constructor instrumentation when needed |
| Shutdown does not clean up resources | ApplicationContext not closed, missing destroy callback, or object outside container | Use try-with-resources and lifecycle cleanup |
| Spring Boot starts fast but first endpoint is slow | Global lazy / deferred resource startup | Evaluate startup vs first-use latency |

### Debugging in Sequence

1. Identify the bean name and scope.
2. Check whether the bean definition has the `lazyInit` flag.
3. Check whether the bean is required by another eager singleton.
4. Check the context type and when `refresh()` occurs.
5. Inspect what the constructor/factory method, `@PostConstruct`, and custom init callbacks are doing.
6. Determine whether the failure is in definition registration, bean instantiation, or a lifecycle callback.
7. Check whether the bean is already in the singleton cache without triggering creation.
8. Check whether factories/post-processors are unintentionally initializing beans early.
9. Check active profiles, properties, conditional beans, and the actual classpath.
10. Fix the root cause, then run a context startup test and a first-use test for lazy beans.

## 22. Testing: Proving Eager and Lazy Without Unintended Side Effects

### Test That Eager Was Initialized Before Client Code

In the Section 12 example, you can add assertions:

```java
if (!tracker.has("eager.constructed")) {
    throw new AssertionError("Eager singleton was not created");
}
if (!tracker.has("eager.initialized")) {
    throw new AssertionError("Eager init method did not run");
}
```

Place these in the `try` body after creating `context` and obtaining `tracker`; assertions print nothing extra when passing.

### Test That Lazy Was Not Created Before Being Requested

```java
if (tracker.has("optional.created")) {
    throw new AssertionError("Optional lazy bean created too early");
}
```

Do not call `context.getBean(OptionalGateway.class)` before this assertion; if you do, the test has altered the condition it is measuring.

### Test That Lazy Was Pulled In Early by an Eager Consumer

```java
if (!tracker.has("required.created")) {
    throw new AssertionError("Required lazy dependency was not resolved");
}
```

Because `EagerConsumer` is an eager singleton that requires `RequiredIndex`, that marker must be recorded after refresh.

### Test Singleton Identity After First Use

```java
OptionalGateway first = context.getBean(OptionalGateway.class);
OptionalGateway second = context.getBean(OptionalGateway.class);

if (first != second) {
    throw new AssertionError("Lazy singleton identity is broken");
}
```

This is an identity check **within the same context**, not across two independent contexts.

### Test Shutdown

After closing the context in the example, `tracker.has("eager.destroyed")` must be true. Do not continue invoking business methods on beans already destroyed by Spring, even though a Java object reference still exists.

### Avoid Tests Depending on Uncontracted Bean Creation Order

Do not write assertions like "constructor A is guaranteed to be called right before constructor B" unless A↔B has an explicit dependency/ordering contract. Checking milestones **before refresh / after refresh / after first use / after close** is more reliable and less flaky.

## 23. Comparison with Spring Boot

Spring Boot uses the Spring Framework Core Container underneath, so it still has eager/lazy, singleton scopes, and dependency-driven creation. In addition, Boot offers convenience settings such as:

```properties
spring.main.lazy-initialization=true
```

This is a **Spring Boot property**, not a Java annotation or a generic property that a plain `AnnotationConfigApplicationContext` reads automatically to enable global laziness.

Boot global lazy initialization can improve startup times in some applications but defers configuration errors until first use; notably, it does not guarantee that all infrastructure beans become lazy.

Distinguishing the lifecycle hooks:

| Milestone | Layer | Primary meaning |
| --- | --- | --- |
| `preInstantiateSingletons()` | Spring BeanFactory | Builds regular non-lazy singletons |
| `SmartInitializingSingleton` | Spring Beans | Callback at the end of the pre-instantiation phase |
| `ContextRefreshedEvent` | Spring Context | Context has been initialized/refreshed |
| `SmartLifecycle.start()` | Spring Context | Lifecycle-aware component started via the lifecycle processor |
| `ApplicationRunner`/`CommandLineRunner` | Spring Boot | Startup runners invoked by Boot |
| `ApplicationReadyEvent` | Spring Boot | Signal that Boot has finished the standard startup sequence |
| Readiness/liveness probes | Spring Boot/operations | Operational state observation, not a replacement for the dependency graph |

**Do not equate these milestones** with "all external services succeeded". Real readiness needs appropriate checks of business-critical dependencies; pre-instantiating a client object does not necessarily prove the network endpoint is healthy.

## 24. Frequently Asked Questions

### Is a singleton created only once for the entire JVM?

No. A Spring singleton by default is **per bean definition per container**. Two ApplicationContexts can have two instances for the same class/bean name.

### Does an eager singleton mean you must call getBean() once?

No. ApplicationContext typically pre-instantiates non-lazy singletons during refresh; callers do not have to manually fetch each bean.

### Does @Lazy mean prototype?

No. Lazy is about timing; prototype is about instance count. A lazy singleton after first use still returns the same reference.

### Why does a @Lazy bean still run its constructor at startup?

That bean may be a required dependency of an eager singleton, or requested by another startup mechanism. Inspect the full dependency graph and early lookups.

### Does context refresh create every bean?

No. Prototypes, unrequested lazy singletons, and certain scoped objects do not belong to bulk singleton pre-instantiation.

### Is pre-instantiation ordered by source-code constructor order?

Do not rely on source order or method names. Dependencies and infrastructure processing determine the required order; independent beans should not have order-dependent behavior.

### Can I disable eager to hide a missing dependency?

You should not. If the dependency is required, making the bean lazy may only push the failure to request-serving time, worsening reliability. Fix the configuration or define feature availability conditions.

### When does @PostConstruct run compared to SmartInitializingSingleton?

`@PostConstruct` is a **bean-local** callback while that bean is being initialized; `SmartInitializingSingleton` runs **after the pre-instantiation phase of regular non-lazy singleton beans**.

### Will a lazy singleton newly created after refresh have afterSingletonsInstantiated called?

By contract, **no**. That callback is for the end of singleton pre-instantiation, not every time Spring creates any new singleton later on.

### If getBeanNamesForType does not fetch instances, is it completely safe?

No. Some type introspection, especially with `FactoryBean` and `allowEagerInit`, can cause the factory to be created in order to know `getObjectType()`. Choose the right API if you want to observe without mutating state.

### Does Spring guarantee singletons are thread-safe?

Spring provides safe publication of managed singleton initialization state, but **does not make all mutable business state inside a singleton thread-safe**. If a bean holds counters, maps, or state that mutates after startup, you still need proper synchronization/concurrent data structures.

### Does a @Bean get initMethod called automatically if I call new directly in Java?

No. `new` invokes the Java constructor, whereas Spring-managed lifecycle callbacks are only invoked automatically when the object is created/managed by the BeanFactory according to a definition with appropriate metadata.

### Does @DependsOn replace constructor dependencies?

No. `@DependsOn` is about ordering, whereas constructor parameter injection provides the collaborator instance. When a dependency is already passed via parameter, `@DependsOn` is usually unnecessary.

## 25. Practice Exercises with Answers

### Exercise 1 — Definition and Instance

You register a bean definition named `mailClient` into a `DefaultListableBeanFactory` without calling `getBean` or `preInstantiateSingletons`. Is the instance guaranteed to exist yet?

**Answer:** No. Registration adds metadata; it does not force instantiation. Check `containsBeanDefinition` and `containsSingleton` to distinguish them.

### Exercise 2 — Default Eager Singleton

A `@Bean Repository repository()` has singleton scope and no `@Lazy`. After successfully creating `AnnotationConfigApplicationContext(AppConfig.class)`, you call `getBean(Repository.class)`. At which milestone did the Repository constructor normally run?

**Answer:** Inside ApplicationContext `refresh()`, before the context constructor returned. The subsequent `getBean` retrieves the already created managed singleton.

### Exercise 3 — Standalone @Lazy

Bean `mailGateway` has `@Lazy` and no eager bean needs it. After refresh, has the bean necessarily been created?

**Answer:** No. Normally it remains deferred until the first time it is requested.

### Exercise 4 — Lazy Pulled In by a Dependency

Eager singleton `A` has constructor `A(B b)`; `B` is a singleton but `@Lazy`. After refresh, could `B` have already been created?

**Answer:** Yes. Spring must supply `B` to create eager `A`, unless the injection is designed to defer via a proxy/provider under a separate contract.

### Exercise 5 — Prototype

Prototype `Worker` is a constructor dependency of eager singleton `Scheduler`. How many `Worker` instances are created for Scheduler in its constructor?

**Answer:** One instance is resolved to be injected at the time Scheduler is created, given the single-parameter constructor described. Spring does not pre-instantiate all prototypes on the classpath.

### Exercise 6 — SmartInitializingSingleton

Does the `afterSingletonsInstantiated` callback guarantee that no lazy singleton has ever been created?

**Answer:** No. A lazy definition may have already been required by an eager dependency. The hook guarantees that regular non-lazy singleton beans have gone through pre-instantiation, not that all lazy beans are absent.

### Exercise 7 — Lazy Coordinator

A bean implements `SmartInitializingSingleton` but is annotated with `@Lazy` and nobody needs it during refresh. Does the callback run automatically at bootstrap?

**Answer:** No. Per the Javadoc, the callback does not run for a lazy singleton that is only created after BeanFactory bootstrap finishes.

### Exercise 8 — Observing State

You want to know whether a bean already has an instance without causing it to be created. Choose `getBean("x")` or `containsSingleton("x")`?

**Answer:** `containsSingleton("x")` checks the cache without requesting creation. `getBean("x")` can trigger bean creation.

### Exercise 9 — Constructor Order

Two independent singletons A and B. Should you assert that A's constructor always runs before B's just because `@Bean a()` appears earlier in source than `@Bean b()`?

**Answer:** No. Only test order when there is an explicit dependency/lifecycle contract; avoid depending on implementation order.

### Exercise 10 — Slow Startup

An eager singleton constructor calls an API downloading 100 MB of data. Is enabling `@Lazy` a root-cause fix?

**Answer:** No. It shifts the cost/failure risk to first use. You need to check whether a business/bootstrap workflow was misplaced in the constructor and choose an appropriate startup/async/readiness mechanism.

### Exercise 11 — Plain BeanFactory

With `DefaultListableBeanFactory`, which API proactively initializes registered non-lazy singletons?

**Answer:** `preInstantiateSingletons()` on `ConfigurableListableBeanFactory`/the corresponding implementation.

### Exercise 12 — Scope and Context

Two different ApplicationContexts both declare a singleton bean named `reportService` of the same class. Must they be the same object reference?

**Answer:** No. Singleton scope is per bean definition within each container.

### Exercise 13 — BeanFactory vs ApplicationContext

Why does a BeanFactory program that registers a definition not yet have a singleton instance, whereas ApplicationContext creates the singleton before calling `getBean`?

**Answer:** ApplicationContext `refresh()` typically orchestrates pre-instantiation automatically; registration on a low-level BeanFactory is not equivalent to a full refresh.

### Exercise 14 — State After Close

After `try (ApplicationContext ...)` ends, a Java local reference to a singleton still exists. Should you use that reference as an active normal bean?

**Answer:** No. The container has closed and destroy callbacks may have run; runtime state and resource ownership are no longer guaranteed. Using the reference after close in the example is only for observing the academic marker.

### Exercise 15 — @DependsOn and Cycles

`@DependsOn("b")` on A, `@DependsOn("a")` on B. Can eager initialization satisfy both?

**Answer:** No. This is an ordering cycle. You must fix the dependency direction.

### Exercise 16 — FactoryBean

Does a pre-instantiated singleton `FactoryBean` necessarily mean its product is created early?

**Answer:** No. You must distinguish the factory object, the product singleton flag, the `SmartFactoryBean` eager-init contract, type introspection, and dependency demand.

### Exercise 17 — Spring Boot Global Lazy

Does the `spring.main.lazy-initialization=true` property work automatically in a plain Spring program `new AnnotationConfigApplicationContext(AppConfig.class)`?

**Answer:** No. That is a Spring Boot configuration, not a universal property automatically read by plain ApplicationContext to enable global laziness.

### Exercise 18 — Predicting Output

In the Section 12 example, why is `requiredLazy.created=true` while `optionalLazy.createdBefore=false`?

**Answer:** Both bean definitions are lazy, but eager `EagerConsumer` strictly requires `RequiredIndex`; no eager bean requires `OptionalGateway` before `main` requests it.

## 26. Project Application Checklist

- [ ] Distinguish between a **registered bean definition** and a **created bean instance**.
- [ ] Understand singleton is per-bean, per-container, not by default per-JVM.
- [ ] Know that `ApplicationContext.refresh()` pre-instantiates regular non-lazy singletons.
- [ ] Use `@Lazy` or XML `lazy-init` based on first-use requirements, not to hide errors.
- [ ] Check which eager singletons depend on lazy singletons.
- [ ] Do not expect prototypes to be bulk pre-instantiated.
- [ ] If a singleton needs a fresh prototype per job, use an appropriate provider/factory.
- [ ] Keep constructors and bean-local init callbacks lightweight, deterministic, and equipped with cleanup.
- [ ] Do not run non-idempotent business side effects simply because an eager bean is created.
- [ ] Understand the exact meaning of `SmartInitializingSingleton` and its limits regarding lazy beans.
- [ ] Separate startup readiness, refresh events, and Boot application readiness from singleton pre-instantiation.
- [ ] Do not initialize business beans prematurely from a BeanFactoryPostProcessor.
- [ ] Account for FactoryBean type queries/eager semantics if the application uses them.
- [ ] Do not rely on the order of independent constructors for business ordering.
- [ ] Do not automatically enable circular references to work around flawed dependency design.
- [ ] Have integration tests verify state **after refresh**, **after first use**, and **after close**.
- [ ] Do not use `getBean` to check whether a lazy bean has been created if the goal is not to alter state.
- [ ] Have startup metrics/logs to detect costs and root causes without logging secrets.
- [ ] If using Boot global lazy, evaluate startup speed traded against first-request latency.
- [ ] Ensure connection/thread resources have timeouts and proper destruction/lifecycle handling.

## Conclusion

**Eager singleton pre-instantiation** is an important default behavior of `ApplicationContext`: Spring creates and configures **regular non-lazy singletons** right during refresh, catching configuration errors before application code starts calling services. That differs from merely registering a `BeanDefinition` in `DefaultListableBeanFactory`.

Keep four rules in mind:

1. **Singleton is identity/scope**, **eager/lazy is timing**.
2. `@Lazy` does not prevent a bean from being created early if an **eager dependency** strictly needs it.
3. `preInstantiateSingletons()` completes the bulk singleton creation phase and relates to the `SmartInitializingSingleton` callback, but **does not** mean all prototypes/lazy beans/external services are ready.
4. Constructors/init callbacks should handle **bean-local** responsibilities, while business workflows and readiness must have their own triggers/policies.

Measure state at clear milestones, respect the dependency graph, write tests for startup and first-use, and only use lazy when deferring truly fits application requirements.

## Official Spring Documentation

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): `ApplicationContext` eager pre-instantiation, `@Lazy`/`lazy-init`, and lazy dependencies of eager singletons.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton per-container/per-bean, prototype semantics.
- [Spring Framework 6.2 — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle, init callbacks, `SmartInitializingSingleton`, and `SmartLifecycle`.
- [Spring Framework 6.2 — ConfigurableListableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html): `preInstantiateSingletons()`.
- [Spring Framework 6.2 — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback after regular singleton pre-instantiation and limitations for lazy beans.
- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): dependency ordering.
- [Spring Framework 6.2 — The IoC Container](https://docs.spring.io/spring-framework/reference/6.2/core/beans.html): BeanFactory, ApplicationContext, and bean definitions.
