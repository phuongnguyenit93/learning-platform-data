# What Is Lazy Initialization and How Does It Change Bean Creation Timing?

## Learning Objectives

In Spring Boot, **lazy initialization** is a mechanism that defers **creating and initializing a bean** until it is actually requested, instead of necessarily creating it up front during `ApplicationContext.refresh()`. This concept is easy to confuse with singleton scope, proxies, dependency injection, and JVM class loading.

This lesson belongs to **Spring Boot Application Runtime → Lazy Initialization**, illustrated with Java 17+ and Spring Boot 3.3.x. After this lesson, you will be able to:

1. Explain the difference between **eager initialization** and **lazy initialization** and know how they affect when constructors, dependency injection, `@PostConstruct`, and other callbacks run.
2. Distinguish **scope** (`singleton`, `prototype`, request scope, etc.) from **initialization timing strategy**.
3. Configure `@Lazy` on `@Component`, `@Bean`, `@Configuration`, and at injection points, and clearly understand the differences.
4. Enable application-wide lazy initialization using `spring.main.lazy-initialization=true` or `SpringApplication.setLazyInitialization(true)` and explicitly keep certain beans eager via `@Lazy(false)`.
5. Understand why an eager singleton depending directly on a lazy singleton can still cause the lazy bean **to be created at startup**.
6. Write, run, and observe a Spring Boot example with an eager bean, a lazy bean requested later, a bean that is never used, and a destruction callback when closing the context.
7. Evaluate the pros and cons of lazy initialization on startup time, first-request latency, readiness, late-discovered errors, memory, and resources.

**Guiding principle:** `@Lazy` is a hint about **when a bean is initialized**, not an absolute guarantee that the bean will only be created after `ApplicationReadyEvent`, nor is it a way to automatically make multithreaded code thread-safe.

## 1. Eager vs. Lazy: The Difference Is Timing, Not Class Name

By default, a Spring `ApplicationContext` typically creates and configures **non-lazy singleton** beans during context refresh. This is called **eager initialization**. This approach adds work during startup, but helps detect constructor, dependency, and configuration errors early.

**Lazy initialization** defers bean creation until an operation actually needs it: for example, another bean requires the dependency, `context.getBean(...)` is called, a proxy is used, or application logic retrieves the bean through `ObjectProvider`.

Example declarations in Java:

~~~java
@Component
public class LocalCatalog {
    public LocalCatalog() {
        System.out.println("LocalCatalog created");
    }
}
~~~

~~~java
@Component
@Lazy
public class HeavyReportEngine {
    public HeavyReportEngine() {
        System.out.println("HeavyReportEngine created");
    }
}
~~~

These are **two illustrative snippets** (requiring `Component`/`Lazy` imports and a project with component scanning), not files to be added to the complete example in Section 7.

If `LocalCatalog` is a normal singleton, the container may create it during refresh even if no application code directly calls `new LocalCatalog()`. For `HeavyReportEngine`, the container can defer initialization until a consumer requests the bean. **However**, if `LocalCatalog` requires `HeavyReportEngine` in its constructor, Spring still has reason to initialize `HeavyReportEngine` early to satisfy the dependency.

### Visualizing the Timeline

~~~text
Without lazy initialization:
SpringApplication.run()
    |
    +-- ApplicationContext.refresh()
    |      +-- create EagerA
    |      +-- create HeavyReportEngine
    |      +-- run @PostConstruct for both
    |
    +-- runners
    +-- ApplicationReadyEvent
    +-- first business call: uses already created bean

Using lazy for HeavyReportEngine, not pulled into early creation by any eager bean:
SpringApplication.run()
    |
    +-- ApplicationContext.refresh()
    |      +-- create EagerA
    |      +-- HeavyReportEngine not yet created
    |
    +-- runners
    +-- ApplicationReadyEvent
    |
    +-- first request for HeavyReportEngine
           +-- create instance, inject, initialize
           +-- run @PostConstruct
           +-- execute business logic
~~~

The diagram illustrates the typical case; at actual runtime, framework infrastructure, the dependency graph, and application configuration may cause exact timing to differ. Do not assume that every lazy bean is guaranteed to wait for the first HTTP request.

### Quick Comparison Table

| Characteristic | Default Eager Singleton | Lazy Singleton |
| --- | --- | --- |
| Scope | `singleton` | Still `singleton` |
| Expected creation timing | Refresh phase during pre-instantiation | When actually needed |
| Constructor | Typically runs during startup | May run after startup |
| Dependency injection, BeanPostProcessor, init callbacks | When the eager bean is created | When the lazy bean is actually created |
| Can fail at startup | Yes | Yes if requested early by a dependency; otherwise, errors may surface late |
| Available before first request? | Usually yes | Not guaranteed |
| Initial time cost | Higher if there are many heavy beans | Can be lower |
| First-use cost | Usually excludes creating that bean | May include constructor/init/dependencies |
| Number of instances held by Spring per singleton bean definition | Typically one per container | Typically one per container |

## 2. Singleton Scope Does Not Mean Eager Initialization

Spring's default `singleton` scope means **one managed instance per bean definition within a single Spring container**. It does not mean a single object for the entire JVM, all classloaders, or all `ApplicationContext` instances.

Example:

~~~java
@Bean
@Lazy
PriceCalculator priceCalculator() {
    return new PriceCalculator();
}
~~~

Even though the `priceCalculator` bean is lazy, its default scope is still `singleton`. The first request may create a `PriceCalculator`; subsequent requests from the **same container** typically receive the same cached instance.

This differs from:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
PriceCalculator priceCalculator() {
    return new PriceCalculator();
}
~~~

The snippet above illustrates a **prototype bean**, not a standalone runnable file; corresponding imports are required. With prototype scope, the container creates a new instance on each appropriate lookup. Using `@Lazy` does not turn a singleton into a prototype; using `@Scope("prototype")` likewise does not turn a prototype into a singleton.

If two different contexts both have the `priceCalculator` bean definition, each context can have its own singleton. For an object created directly via `new PriceCalculator()` outside Spring, the container does not automatically manage that object's lifecycle.

### Separating Two Axes of Thought

| Axis | Question Answered | Example |
| --- | --- | --- |
| **Scope** | How many times and within what boundary is the bean shared/created? | singleton, prototype, request |
| **Initialization strategy** | At what stage is the bean instance typically created? | eager or lazy |
| **Dependency resolution** | What makes the container need the bean? | constructor injection, `getBean`, provider |
| **Lifecycle** | Which callbacks run when the bean is created/destroyed? | `@PostConstruct`, `@PreDestroy` |
| **Runtime execution** | When do business methods run? | In a runner or on each HTTP request |

An eager singleton may be created up front yet **never execute its business methods** if nothing calls it. A lazy singleton may be created late and then reused across thousands of subsequent requests. Initialization and business execution are two separate things.

## 3. At Which Step Does Spring Create Default Singletons?

In Spring Framework, `AbstractApplicationContext.refresh()` handles multiple stages such as preparing the BeanFactory, invoking `BeanFactoryPostProcessor`, registering `BeanPostProcessor`, setting up event multicasting, and finally creating eligible non-lazy singletons.

Most relevant milestones:

~~~text
SpringApplication.run(...)
    |
    +-- prepare environment / create context
    |
    +-- ApplicationContext.refresh()
    |    |
    |    +-- process bean definitions and post-processors
    |    |
    |    +-- finishBeanFactoryInitialization(...)
    |    |    |
    |    |    +-- preInstantiateSingletons()
    |    |         +-- singleton, non-lazy beans
    |    |         +-- dependencies that must be created alongside them
    |    |
    |    +-- finishRefresh()
    |         +-- context lifecycle finishes refresh
    |         +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent
    +-- run(...) returns context
~~~

The diagram shows the **main milestones**, not a verbatim copy of every Spring Framework instruction. Some infrastructure beans may initialize earlier before the pre-instantiation phase; extensions and special bean factories have their own contracts.

Key point: when a lazy bean is created **after refresh**, its constructor and initialization callbacks also run **after refresh**. Spring does not run a lazy bean's `@PostConstruct` at startup and leave the constructor until first use.

### Initialization Sequence of a Bean

When the container actually needs to create a bean:

~~~text
Factory method / constructor
    |
Dependency resolution and injection
    |
BeanPostProcessor before initialization
    |-- processes @PostConstruct in suitable configurations
    |
InitializingBean.afterPropertiesSet()
Custom init method (if declared)
BeanPostProcessor after initialization
    |
Bean ready for use
~~~

This applies whenever the bean is initialized, whether at startup or later. Laziness **does not eliminate** lifecycle callbacks; it only pushes when they run to a later time.

For a lazy bean that is **never created**, there is no instance on which to invoke `@PreDestroy`. If the bean was created and is managed by the container under the appropriate contract, the proper destroy callback is invoked when the context closes.

## 4. Marking a Bean as Lazy with @Lazy

The annotation at `org.springframework.context.annotation.Lazy` has a default attribute `value() = true`. Most commonly, it is placed on a `@Component` class or a `@Bean` factory method.

### @Lazy on @Component

~~~java
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@Component
@Lazy
public class ReportExporter {

    public ReportExporter() {
        System.out.println("ReportExporter initialized");
    }
}
~~~

This is a syntactically complete Java class, but it needs to reside in a Spring application with component scanning. If nothing requests `ReportExporter` during startup, its creation can be deferred.

### @Lazy on @Bean

~~~java
@Configuration
public class ReportConfiguration {

    @Bean
    @Lazy
    ReportExporter reportExporter() {
        return new ReportExporter();
    }
}
~~~

Illustrative configuration snippet; add imports for `Configuration`, `Bean`, `Lazy`, and the `ReportExporter` class. Placing the annotation on `@Bean` changes the lazy flag of **the bean definition produced by the method**.

**Do not confuse:** merely writing `@Lazy` on a helper class not registered as a Spring bean will not cause every Java `new` call to be automatically deferred. The annotation takes effect when Spring processes an appropriate bean definition or injection point.

### @Lazy(false) to Request Eager Initialization

~~~java
@Bean
@Lazy(false)
EssentialValidator essentialValidator() {
    return new EssentialValidator();
}
~~~

If another configuration requests lazy by default, `@Lazy(false)` is the explicit way to specify that a bean should be created eagerly according to the container contract. In Spring Boot, global lazy configuration also allows protecting specific beans with `@Lazy(false)`. This option is useful for beans that must fail fast before ready.

This is an illustrative snippet requiring the `EssentialValidator` type definition and imports; it is not a standalone program.

### @Lazy on @Configuration

~~~java
@Configuration
@Lazy
public class OptionalIntegrationsConfiguration {

    @Bean
    OptionalSearchClient searchClient() {
        return new OptionalSearchClient();
    }

    @Bean
    @Lazy(false)
    RequiredHealthRule requiredHealthRule() {
        return new RequiredHealthRule();
    }
}
~~~

When `@Lazy` is placed on a `@Configuration` class, the `@Bean` methods declared inside are marked lazy by default; `@Lazy(false)` on a factory method can override that behavior. The `OptionalSearchClient`/`RequiredHealthRule` classes are illustrative types not defined in the snippet.

Do not infer that the entire `@Configuration` class is never created or read by Spring during startup. Spring still has to process metadata, configuration, and infrastructure beans; the lazy flag here mainly affects **bean definitions created by the `@Bean` methods**.

## 5. Why Can a @Lazy Bean Still Be Created at Startup?

This is the most important mechanism when diagnosing issues.

Suppose there is a lazy service:

~~~java
@Component
@Lazy
class HeavyIndexer {
    HeavyIndexer() {
        System.out.println("HeavyIndexer created");
    }

    void index() {
        System.out.println("Indexing");
    }
}
~~~

However, a non-lazy singleton requires that service in its constructor:

~~~java
@Component
class BootstrapCoordinator {

    private final HeavyIndexer indexer;

    BootstrapCoordinator(HeavyIndexer indexer) {
        this.indexer = indexer;
    }
}
~~~

The classes above are illustrative (requiring `Component` and `Lazy` imports). Because `BootstrapCoordinator` is created eagerly, Spring must resolve the `HeavyIndexer` dependency to pass into its constructor. Therefore `HeavyIndexer` may be created **right during refresh**, even though the class has `@Lazy`.

**Rule:** `@Lazy` on a **bean definition** says "do not proactively pre-instantiate this bean if not needed"; it does **not** mean "all dependencies are automatically deferred and nothing is allowed to retrieve this bean early".

### Four Cases to Compare

| Bean A | Bean B | Relationship | What Typically Happens |
| --- | --- | --- | --- |
| A eager | B lazy | A does not need B | A created at startup; B may not be created yet |
| A eager | B lazy | A needs B via direct constructor | Spring must obtain B when creating A, so B may be created early |
| A lazy | B lazy | Nothing requests them | Neither may be created yet |
| A eager | B lazy | A receives `ObjectProvider<B>`, has not called `getObject()` | A can be created while B still remains uncreated |

Situations can also be more complex due to `BeanPostProcessor`, factory beans, events, runners, startup checks, Actuator, and external libraries requesting beans. Measure and observe the actual container rather than concluding from a single annotation.

### @DependsOn Can Pull Dependencies into Early Creation

A bean with `@DependsOn("lazyBean")` can cause the depended-on bean to initialize early under dependency rules if the bean carrying `@DependsOn` is created eagerly. The purpose of `@DependsOn` is to enforce creation/destruction ordering, **not** a way to defer a bean.

### Beans Retrieved from ApplicationRunner

`ApplicationRunner`/`CommandLineRunner` runs after context refresh but before ready. If a runner calls `getBean(LazyService.class)` or `ObjectProvider.getObject()`, the lazy bean is created **during the startup runner phase**. Thus it can be created **before `ApplicationReadyEvent`**, even though it was not pre-instantiated during refresh.

### Event Listeners and Hooks Can Trigger Bean Creation

An `@EventListener` bean may be initialized by Spring to register an event handler according to the framework lifecycle; a listener or callback can subsequently trigger another bean. Be cautious if trying to make all listeners/handlers lazy and assuming they will still reliably operate on every event. Verify the contract of each specific integration.

## 6. Lazy Dependency and Lazy-Resolution Proxy Are Not the Same

`@Lazy` has **two common contexts**:

1. On `@Component`/`@Bean`: determines whether the bean definition is eagerly pre-instantiated.
2. On an **injection point** such as a constructor parameter or `@Autowired` field: tells Spring to provide a **lazy-resolution proxy** for the dependency at that point.

### @Lazy Directly at the Injection Point

~~~java
@Component
class DashboardService {

    private final ReportGenerator generator;

    DashboardService(@Lazy ReportGenerator generator) {
        this.generator = generator;
    }

    String openDashboard() {
        return generator.generate();
    }
}
~~~

This snippet is illustrative, requiring a `ReportGenerator` interface and a Spring bean implementation. Spring can inject a proxy into `DashboardService`'s constructor, and the proxy looks up the target when `generate()` is actually called. Thus an eager `DashboardService` can initialize without immediately creating the target *solely due to* constructor injection.

However, **there are two caveats**:

- If the `ReportGenerator` bean itself remains an independent **eager singleton**, Spring may still pre-instantiate the target during the refresh phase even though `DashboardService` holds a proxy. To defer the target, you need to configure the lazy flag on the **bean definition** or use an appropriate global lazy mechanism.
- A proxy does not guarantee the real target is always available. If the dependency does not exist or fails to create, the error may surface when **invoking a method through the proxy**, making diagnosis harder. For optional dependencies, a proxy can mask a missing bean until it is too late.

Do not use lazy proxies to "fix" circular dependencies without proper analysis. Spring Boot 3.x favors clean constructor injection design, and hiding a dependency cycle can shift an error from startup to runtime.

### ObjectProvider: An Explicit Choice When Retrieving On Demand

~~~java
@Component
class DashboardService {

    private final ObjectProvider<ReportGenerator> generators;

    DashboardService(ObjectProvider<ReportGenerator> generators) {
        this.generators = generators;
    }

    String openDashboard() {
        ReportGenerator generator = generators.getObject();
        return generator.generate();
    }
}
~~~

This is an illustrative example requiring imports for `org.springframework.beans.factory.ObjectProvider`, `Component`, and the `ReportGenerator` type. `ObjectProvider` separates **when the provider is injected** from **when the real bean is requested**. It offers better APIs for handling missing beans, such as `getIfAvailable()` for appropriate optional needs.

However, a provider **does not automatically turn an eager bean into a lazy one**. If the target is proactively pre-instantiated by the container, the provider simply returns the existing instance. To defer target creation, you must consider both the bean definition's lazy flag and other dependencies.

### When to Choose Which Approach?

| Need | Typically Suitable Option |
| --- | --- |
| An optional, rarely used service | `@Lazy` on the bean definition |
| An eager bean that only needs a dependency when a specific method is called | `ObjectProvider<T>` or `@Lazy` at the injection point plus lazy target configuration |
| A dependency that might not exist | `ObjectProvider.getIfAvailable()` and an intentional fallback |
| An essential bean that must fail fast at startup | Eager or `@Lazy(false)` |
| Every request needs the service immediately | Eager is usually simpler with more predictable latency |
| A server application needing overall startup optimization | Measure and consider selective global lazy initialization |

## 7. Runnable Example: Observing Exact Bean Creation Timing

The project below uses **Java 17**, **Spring Boot 3.3.13**, and **Gradle**. It is a non-web CLI application requiring neither a database nor network access. It creates an eager bean, registers two lazy beans, **does not access the lazy beans inside the startup runner**, and then requests one lazy bean after `SpringApplication.run(...)` returns.

We will observe:

- The eager bean is created during refresh.
- A lazy bean **does not yet have an instance** after ready.
- The first `getBean(...)` call creates the instance.
- The second lookup receives the exact same singleton already created.
- Another lazy bean that is never requested **is not created**.
- Closing the context destroys the lazy bean that was created.

### 7.1. Structure

~~~text
lazy-bean-timing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lazy/
    └── LazyBeanTimingApplication.java
~~~

**File `settings.gradle`:**

~~~groovy
rootProject.name = 'lazy-bean-timing-demo'
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.lazy.LazyBeanTimingApplication'
}
~~~

The project requires a Gradle version compatible with the Spring Boot 3.3 plugin and JDK 17+. You can use an installed `gradle` or add the Gradle Wrapper; the snippet does not generate the wrapper.

### 7.2. Complete Java Code

**File `src/main/java/com/example/lazy/LazyBeanTimingApplication.java`:**

~~~java
package com.example.lazy;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LazyBeanTimingApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyBeanTimingApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN: run returned");

            // Only ask whether SingletonBeanRegistry already holds the instance.
            // Do not call getBean on this line.
            System.out.println("MAIN: lazy exists before get="
                    + context.getBeanFactory().containsSingleton("lazyReport"));

            LazyReport first = context.getBean(LazyReport.class);
            System.out.println("MAIN: first result=" + first.render());

            LazyReport second = context.getBean(LazyReport.class);
            System.out.println("MAIN: same instance=" + (first == second));

            System.out.println("MAIN: lazy exists after get="
                    + context.getBeanFactory().containsSingleton("lazyReport"));

            System.out.println("MAIN: unused exists="
                    + context.getBeanFactory().containsSingleton("unusedEngine"));
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    EagerCatalog eagerCatalog() {
        return new EagerCatalog();
    }

    @Bean
    @Lazy
    LazyReport lazyReport() {
        return new LazyReport();
    }

    @Bean
    @Lazy
    UnusedEngine unusedEngine() {
        return new UnusedEngine();
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("RUNNER: executed");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        System.out.println("EVENT: ready");
    }

    public static final class EagerCatalog {
        public EagerCatalog() {
            System.out.println("BEAN: eager catalog created");
        }
    }

    public static final class LazyReport {
        public LazyReport() {
            System.out.println("BEAN: lazy report created");
        }

        public String render() {
            return "RPT-42";
        }

        @PreDestroy
        public void close() {
            System.out.println("BEAN: lazy report destroyed");
        }
    }

    public static final class UnusedEngine {
        public UnusedEngine() {
            System.out.println("BEAN: unused engine created");
        }
    }
}
~~~

**Why is this example runnable?** It defines the `@SpringBootApplication` class, a `main` method, three `@Bean` definitions with explicit names (`eagerCatalog`, `lazyReport`, `unusedEngine`), an `ApplicationRunner`, and a ready listener, along with the data/service classes as nested static classes. All necessary imports and dependencies for the program have been specified.

**Why not inject LazyReport into the Runner?** If the Runner directly received `LazyReport` via its constructor or factory method, the runner itself could cause the lazy bean to be created during startup, defeating the goal of observing "not yet created after ready". The demo intentionally keeps the lazy beans **free of eager dependencies**.

### 7.3. Running

In the `lazy-bean-timing-demo` directory:

~~~bash
gradle bootRun
~~~

If you have the Gradle Wrapper: use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows.

**The lines printed by the program itself**, ignoring Gradle messages and Spring Boot logs, have the expected order:

~~~text
BEAN: eager catalog created
RUNNER: executed
EVENT: ready
MAIN: run returned
MAIN: lazy exists before get=false
BEAN: lazy report created
MAIN: first result=RPT-42
MAIN: same instance=true
MAIN: lazy exists after get=true
MAIN: unused exists=false
BEAN: lazy report destroyed
MAIN: context closed
~~~

Timing breakdown:

1. `BEAN: eager catalog created` occurs during the pre-instantiation phase of non-lazy singletons.
2. `RUNNER: executed` appears after context refresh but before ready.
3. `EVENT: ready` arrives when Spring Boot publishes `ApplicationReadyEvent` after startup runners.
4. `MAIN: run returned` only appears once `SpringApplication.run` has returned successfully.
5. `containsSingleton("lazyReport")` is a **check for an already-cached singleton instance**, not a request to create the bean. Because `LazyReport` has not been requested yet, the result is `false`.
6. The first `getBean(LazyReport.class)` call makes Spring create the bean and run the `LazyReport()` constructor.
7. The second lookup returns the same singleton instance, so `first == second` is `true`. There is no second constructor line.
8. `containsSingleton("lazyReport")` after the lookup is `true`. This proves the bean definition already existed, while the instance only appeared upon first request.
9. `unusedEngine` was never looked up, so it has no singleton instance and does not print `BEAN: unused engine created`.
10. When `try-with-resources` calls `context.close()`, the created `LazyReport` bean is destroyed, so `@PreDestroy` prints `BEAN: lazy report destroyed`. Afterward, `MAIN: context closed` appears.

**Measurement limitations:** `containsSingleton(name)` reports whether the registry currently holds a singleton object registered under that name; `false` **does not** mean the bean definition does not exist. Nor does it replace startup profiling tools in real systems. With different bean names, different scopes, or proxies/factory beans, the interpretation must be adjusted.

### 7.4. Varying One Factor at a Time to Experiment

Keep the original version to know the expected output, then try **one change at a time**:

1. **Remove `@Lazy` from the `lazyReport` factory method:** The `LazyReport` bean becomes eager by default; the constructor line moves before Runner and ready, and `MAIN: lazy exists before get` becomes `true`.
2. **Keep `@Lazy`, but call `context.getBean(LazyReport.class)` inside `ApplicationRunner`:** The bean is created in the runner, **before** ready, because the runner itself requested it.
3. **Keep the bean lazy, and add an eager bean with a constructor dependency on `LazyReport`:** The lazy bean is created to satisfy the eager bean's dependency, typically during refresh.
4. **Call `context.getBean(UnusedEngine.class)` after the first check:** The `UnusedEngine` constructor will print when it is retrieved for the first time; `containsSingleton("unusedEngine")` afterward becomes `true`.
5. **Change `@Lazy` to `@Lazy(false)` on `lazyReport`:** The bean is requested eagerly just as if the annotation were absent.
6. **Make the `LazyReport` constructor throw an exception:** Because it is only requested in `main` after `run`, the error may appear **after `ApplicationReadyEvent`**; this demonstrates the risk of late error detection.
7. **Use `@Lazy(false)` on `eagerCatalog` and then enable global lazy:** This critical bean is requested eagerly even when most other beans are configured as lazy.

## 8. Enabling Lazy Initialization for the Entire Spring Boot Application

Beyond annotating individual beans with `@Lazy`, Spring Boot supports lazy mode on a broad scale.

### application.properties

**`src/main/resources/application.properties`:**

~~~properties
spring.main.lazy-initialization=true
~~~

### application.yml

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

These are two ways to express the same property; only **one** needs to be used in a real application, or you should clearly determine which configuration source takes precedence.

### Configuring Programmatically

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
~~~

This is **illustrative code**; replace `MyApplication` with the actual application class. Crucially, call `setLazyInitialization(true)` **before** `run`. With `SpringApplicationBuilder`, there is also the `lazyInitialization(true)` method.

When global lazy is enabled, many beans can be created on demand rather than during startup. This can reduce startup cost in some applications, especially when there are many web-related beans or rarely used features. However, **it does not guarantee every bean is deferred**: Spring infrastructure, dependencies needed during bootstrap, listeners, runners, and beans marked eager may still be created early.

### Keeping Essential Beans Eager Under Global Lazy

~~~java
@Bean
@Lazy(false)
StartupPolicyValidator startupPolicyValidator() {
    return new StartupPolicyValidator();
}
~~~

This is an illustrative snippet requiring the `StartupPolicyValidator` class and `Bean`/`Lazy` imports. If the policy validator must detect critical misconfigurations **before ready**, keep it eager or validate explicitly at an appropriate startup milestone.

### Caution When Enabling Global Lazy in the Section 7 Demo

If you run the project with:

~~~bash
gradle bootRun --args="--spring.main.lazy-initialization=true"
~~~

the number of eager beans and log order may **differ** from the output in Section 7. Because infrastructure, runners, and observers still need to function, do not simply assume that every bean without `@Lazy(false)` is guaranteed to remain uncreated at ready. Observe through logs, and avoid using the old output as a test assertion for a configuration with a different purpose.

**The default value in Spring Boot 3.3 is `false`** for `spring.main.lazy-initialization`. Enable it only after measuring benefits and accepting the trade-offs; do not enable it by default merely to see a faster startup.

## 9. @Lazy and @PostConstruct, @PreDestroy, Events, and Runners

Lazy initialization changes **when** lifecycle callbacks are invoked.

| Callback or Milestone | Default Eager Bean | Unrequested Lazy Bean |
| --- | --- | --- |
| Constructor / `@Bean` method | During startup when bean is created | Has not run yet |
| Dependency injection | When bean is created | Not yet performed for non-existent instance |
| `@PostConstruct` | During initialization | Has not run yet |
| `InitializingBean.afterPropertiesSet()` | During initialization | Has not run yet |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | May run for eligible beans after pre-instantiation phase | Do not expect the callback to be invoked automatically if the bean was never pre-instantiated |
| `ApplicationStartedEvent` | Boot event published at application milestone | Does not automatically make all lazy beans eager |
| `ApplicationRunner`/`CommandLineRunner` | Runs in startup phase, may look up beans | Can cause a lazy bean to be created when the runner uses it |
| `ApplicationReadyEvent` | Boot event signaling ready milestone | Does not require all lazy beans to be created |
| `@PreDestroy` | When singleton was created and context closes normally | No instance to destroy if never created |

A common mistake is expecting a lazy bean's `@PostConstruct` to run before all startup runners. It will not: if the bean has not been created yet, that bean's callbacks have not run. If a runner needs a bean validated, it must request the bean or the essential bean must be designed as eager.

Similarly, `ContextRefreshedEvent` means the context has refreshed, not that every lazy singleton has been initialized. `ApplicationReadyEvent` means Boot's startup process has reached the ready milestone after runners succeeded, not that optional features will avoid initialization on the first request.

## 10. Operational Trade-offs: Faster Startup Can Make the First Request Slower

Lazy initialization **shifts cost**. Instead of paying the cost at startup, the application may pay it when a feature is first invoked.

### Potential Benefits

- Reduces bean creation time at startup when there are many rarely used features.
- Reduces some memory usage right after startup when large objects have not yet been constructed.
- Defers non-essential resources such as specialized caches, certain parsers/formatters, or optional clients.
- Useful for CLI applications with many features where each run only uses one specific command.
- Can improve the cold-start path if the set of beans truly needed for the first request is smaller than all bean definitions.

### Costs and Risks

- **First-use latency:** The first request or job waits for the constructor, injection, `@PostConstruct`, and dependencies; p95/p99 latency can spike if a cold path is hit suddenly.
- **Late error detection:** A bean missing a property, missing a class, having a connection error, or throwing an init exception may only surface after the application has reported ready.
- **Memory spikes:** The application may run with a low heap right after startup, then jump sharply when many features are first invoked together; heap must be sized for the full workload.
- **Harder observability:** Normal startup logs will not show parts that only fail on the first request.
- **Can be an illusory improvement:** If critical endpoints all require the same set of services, they still must be created on first use, merely shifting the cost onto the user.
- **Callback complexity:** Code expecting all singletons to exist at refresh may need revision when global lazy is enabled.

### Thinking in "Startup Time" vs. "Time to Serve Readiness"

If we account for the costs:

~~~text
Eager:
startup = build context + create essential beans + create optional beans
first request ≈ business work (bean already exists)

Lazy:
startup = build context + create beans actually needed during bootstrap
first request = create lazy dependencies + business work
~~~

This is a **qualitative** model, not a real-time formula for every application. Laziness can change dependency paths, I/O ordering, class loading, and memory usage; only benchmarking an actual deployment shows whether it helps.

### Readiness Does Not Automatically Validate All Lazy Beans

A container orchestrator may consider an instance ready because Spring Boot has finished its startup runners. Yet a rarely used endpoint with a broken lazy dependency can return an error when called for the first time.

If a bean or downstream service is a **prerequisite for receiving traffic**, choose one of these explicit strategies:

1. Keep the bean eager using `@Lazy(false)`.
2. Validate/initialize essential beans inside a startup runner with clear timeouts and failure policies.
3. Use readiness/health indicators that reflect critical conditions without causing dangerous side effects.
4. Add a pre-warm step during deployment before shifting traffic, if pre-warming is useful and safe.

**Do not make a liveness probe depend on an external downstream service in a way that causes all pods to restart simultaneously when the external system has an outage.** Liveness and readiness serve different purposes.

## 11. Lazy Singletons and Concurrent Access

A web application may receive two requests that use a lazy singleton for the first time concurrently. The Spring container must coordinate normal singleton creation so it does not arbitrarily create multiple instances for the same bean definition, but that **does not make the bean's business state thread-safe**.

Risk example:

~~~java
@Component
@Lazy
class VisitCounter {

    private int visits;

    int next() {
        return ++visits;
    }
}
~~~

The code above illustrates **poor** thread safety and is not part of the sample project. Two requests calling `next()` concurrently can hit a race condition on `++`. `@Lazy` only affects bean creation timing; it does not make incrementing atomic.

If a shared counter must be maintained, consider `AtomicInteger`, appropriate synchronization, or a stateless design. Similarly, `@Lazy` does not solve deadlocks, blocking I/O, or visibility issues of application-managed state.

### A Single Creation Can Still Take a Long Time

If a lazy bean's constructor makes an external connection without a timeout, the first request may be blocked for a very long time. Make sure to:

- Limit I/O inside constructors when possible.
- Configure explicit timeouts for network clients.
- Move mandatory initialization into a controlled startup/health mechanism.
- Measure initialization time and how often the bean is actually used.
- Avoid holding overly broad application locks around operations that trigger lazy bean creation.

## 12. Design Scenarios and Appropriate Choices

### Scenario A: Rarely Used Optional Feature

A specialized report exporter called only a few times per week. `@Lazy` can make sense to defer the heavy engine until it is actually used. Use a dedicated endpoint or job to trigger it.

What to check: reasonable wait time on the first call, engine creation cost, peak memory usage, and retry capability if init fails.

### Scenario B: Mandatory Authentication/Security or Policy

If policy validation must complete before the server receives traffic, leaving the bean lazy without startup checks increases risk. Ensure authentication configuration beans and essential checks have an appropriate eager/fail-fast strategy; do not defer security failures just to reduce startup time.

### Scenario C: Multi-Subcommand CLI

A single JAR used for `import` or `export`, where each command has its own dependencies. Lazy bean definitions or conditional configuration help avoid initializing tools not needed for the subcommand being run.

In particular, if a dispatching `ApplicationRunner` invokes only the appropriate provider for each feature, the corresponding bean is created when the runner requests it. This is a different design from a web app that must serve many features concurrently.

### Scenario D: Web Application Requiring Consistent First-Request Latency

If every critical request uses the same heavy service, lazy initialization can make the first request slow and trigger timeouts. You may prefer eager initialization or pre-warming. Measure startup + first-request latency + p95/p99, rather than only looking at Spring Boot's "Started" log.

### Scenario E: External Service Occasionally Unavailable

Making a bean lazy can allow the application to still start up even when an external dependency is down, but **lazy must not be used as a substitute for a circuit breaker or retry mechanism**. You need a clear policy: can the feature degrade, what is the health status, how is a failed first call handled, and is the user notified appropriately?

## 13. Diagnostics: How to Know When a Bean Is Created?

### Logging in the Constructor or Factory Method

In the demo, the constructor prints `BEAN: lazy report created`. When the log appears is when the constructor runs. This is intuitive for learning, but in production you must not log sensitive information and should not add excessive logging to every bean.

### Using BeanFactory.containsSingleton to Check Instance State

~~~java
boolean instantiated =
        context.getBeanFactory().containsSingleton("lazyReport");
~~~

A `false` value means the singleton registry **does not yet hold an instance under that key**, not that the bean definition is missing. This works well for `@Bean` singletons with known names. With `FactoryBean`, custom scopes, proxies, or multiple contexts, the state may require deeper interpretation.

### Using Appropriate Startup Diagnostics

Spring Boot provides `ApplicationStartup`/`BufferingApplicationStartup` to capture startup steps, and can integrate with the Actuator startup endpoint when appropriately configured. Java Flight Recorder and profiling/metrics can show how much time bean initialization or class loading actually takes. Examine **both the startup phase** and **the first use** after ready.

### Do Not Use getBean to "Check Whether a Bean Already Exists"

~~~java
context.getBean(LazyReport.class);
~~~

If `LazyReport` has not yet been created, this call itself **triggers initialization**. Thus it is not a passive probe. Use `containsBeanDefinition(...)` to check for the definition, `containsSingleton(...)` to check for an instance in registry terms, or metrics tools when passive observation is needed.

### Inspecting the Dependency Graph

If `@Lazy` does not behave as expected, answer these questions in order:

1. Does an eager bean directly constructor-inject this bean?
2. Does `@DependsOn`, a `@Bean` factory method, or a `BeanPostProcessor` require it early?
3. Does a runner or startup event listener call `getBean` or a provider before ready?
4. Is there a `@Lazy(false)` configuration or a `BeanFactoryPostProcessor` altering the lazy flag?
5. Does an `AutoConfiguration` library force initialization of a bean of the same type?
6. Is there another context or a duplicate bean of the same type causing you to misread what you observe?
7. Are you measuring the constructor, proxy creation, bean method, or business method? Those four do not necessarily happen at the same time.

## 14. Testing Lazy Initialization Properly

### Unit Testing the Idea with a Context

A good test should prove:

- The bean definition exists right after refresh.
- The singleton bean has not been created when nothing requests it.
- The first lookup creates the instance.
- The second lookup in the same context returns the same instance.
- Closing the context runs the destroy callback if the instance was created.

The Section 7 demo is essentially a test by observing logs. In automated tests, replace `System.out.println` with carefully designed counters or test spies, avoiding reliance on the log ordering of the entire framework.

### Testing with ApplicationContextRunner

Spring Boot Test provides `ApplicationContextRunner` to create a small context in tests. A test can build a configuration containing an eager bean and a lazy bean, then check bean registry state before and after `getBean` inside the callback. This is a suitable tool when you want to test bean definition behavior without booting an entire web server.

An **illustrative** snippet for a test assuming `DemoConfig` and `MyLazyService` are already declared:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(DemoConfig.class)
        .run(context -> {
            assertFalse(context.getBeanFactory()
                    .containsSingleton("myLazyService"));

            MyLazyService service =
                    context.getBean(MyLazyService.class);

            assertNotNull(service);
            assertTrue(context.getBeanFactory()
                    .containsSingleton("myLazyService"));
        });
~~~

This is **not** standalone test code. It requires the `spring-boot-starter-test` dependency, imports for `ApplicationContextRunner`/JUnit assertions, exact bean names, and a `DemoConfig` class returning a `@Bean @Lazy MyLazyService`. Use the right test runner/JUnit version; do not treat this snippet as a complete file you can compile with `javac` on its own.

### Test the Failure Path as Well

Mark a bean as `@Lazy` and intentionally have its factory method throw an exception in a test; verify:

- The context can refresh while nothing has requested that bean.
- `context.getBean(...)` surfaces the bean creation error.
- When the mandatory bean is changed to eager, startup must not silently swallow that error.
- Production tests should classify the real error instead of merely asserting "any exception".

Successful startup **does not prove** that all lazy beans are valid.

## 15. Common Mistakes and Fixes

**1. "Singletons are eager by definition."** False. Singleton refers to instance scope; lazy/eager refers to creation timing. `@Bean @Lazy` is still singleton by default.

**2. "@Lazy always ensures a bean is only created on the first HTTP request."** False. The bean can be requested by an eager dependency, runner, listener, or other code before any request arrives.

**3. "@Lazy on a dependency alone guarantees deferring the target."** Not necessarily. `@Lazy` at an **injection point** usually creates a proxy; if the target bean itself is eager and pre-instantiated, the target can still exist from startup.

**4. "@Lazy removes @PostConstruct."** False. `@PostConstruct` still runs when the bean is actually created and initialized, just later.

**5. "@PreDestroy is guaranteed to run for an unused lazy bean."** No. If no instance was ever created by Spring, there is no instance to destroy.

**6. "ApplicationReadyEvent means all lazy beans are ready."** False. Ready is Boot's startup milestone after runners, not a loop forcing creation of all lazy bean definitions.

**7. "Enabling global lazy guarantees no bean is created at startup."** False. Some infrastructure beans and required dependencies may be requested early; `@Lazy(false)` also allows specifying eager beans.

**8. "Use getBean to check whether a bean has been created yet."** False. `getBean` can **itself be the trigger** that initializes the bean. If you need a passive check for the singleton registry, `containsSingleton` lets you observe within the appropriate scope.

**9. "@Lazy means prototype."** False. Laziness does not change scope. A singleton still has only one instance per bean definition in the container once created.

**10. "Shorter startup time automatically means better user experience."** Not always. Laziness can shift costs onto the first request, increasing tail latency and delaying error detection.

**11. "No need to configure timeouts because the bean is created on demand."** False. Network I/O in a lazy bean's constructor or init method can hang the first request or runner, causing timeouts.

**12. "@Lazy makes a bean thread-safe."** False. Spring manages singleton creation, but mutable fields and business methods require their own concurrency policy.

**13. "@Lazy can fix circular dependency errors without changing design."** Avoid doing this. Proxies/late resolution can mask symptoms; separate responsibilities and keep the dependency graph clean.

**14. "@Lazy(false) has no effect when global lazy is enabled."** Incorrect for Spring Boot 3.3: the annotation can be used to mark a bean for eager creation while the rest are lazy.

**15. "@Lazy on a class not managed by Spring still takes effect."** False. The annotation does not turn objects instantiated via `new` outside the container into lazy Spring beans.

**16. "No need to test lazy beans because startup PASSED."** False. Rarely used paths may hide configuration, classpath, or dependency errors.

**17. "Once created, a lazy singleton automatically closes right after its first use."** False. A singleton is retained in the container; its lifecycle ends when the context closes or another appropriate destruction mechanism triggers.

**18. "All other beans can be accessed inside a lazy bean's @PostConstruct."** Do not infer that from a single callback; you must consider initialization timing, the dependency graph, context state, and the contracts of the beans involved.

## 16. Exercises

1. Run the Section 7 project. Why does `BEAN: eager catalog created` appear before `EVENT: ready`?
2. Why is `MAIN: lazy exists before get=false` still true even though Spring already loaded the `lazyReport` `@Bean` definition?
3. After the first `context.getBean(LazyReport.class)` call, why does the constructor print only once even when `getBean` is called a second time?
4. `UnusedEngine` is never requested in the program. Why is its constructor log not shown?
5. Remove `@Lazy` from `lazyReport`, rerun, and note which output lines change. Does singleton behavior change?
6. Add an eager bean whose constructor accepts `LazyReport`. What happens to when `LazyReport` is created?
7. Have the runner accept `ObjectProvider<LazyReport>` and call `getObject()` inside `run`. Is the bean created before or after `ApplicationReadyEvent`?
8. Keep the provider, but **do not** call `getObject()` inside the runner. Does the result differ?
9. Enable `spring.main.lazy-initialization=true` and compare the number of beans created at startup with the default configuration. Can you conclude all beans are lazy?
10. Place `@Lazy(false)` on `eagerCatalog` while global lazy is enabled. Observe the result and explain the fail-fast purpose.
11. Add `@PostConstruct` to `LazyReport`. Does it appear before or after `MAIN: lazy exists before get=false`?
12. Keep `@PreDestroy` in `LazyReport`, but remove all code requesting `LazyReport`. When the context closes, does `LazyReport`'s callback run?
13. Add a `LazyReport` whose factory method intentionally throws an exception. If nothing requests the bean, can startup reach ready? What happens on lookup?
14. In a web application, measure first-request latency with lazy enabled and disabled. Why is the "Started" log time alone insufficient for evaluation?
15. An eager controller injects a target via a `@Lazy` injection point. Why can the proxy exist at startup while the target has not yet been created? In what cases is the target still created early?
16. A system has a database client required before receiving traffic. Would you keep the client lazy, or use startup validation/`@Lazy(false)`? State your reasoning.
17. Why does a lazy singleton with an `int count` field still suffer from a data race when multiple concurrent requests increment `count`?
18. Write a test using `ApplicationContextRunner`/`containsSingleton` to assert a lazy bean definition and its first lookup. Which bean name and scope checks matter?
19. Compare `@Lazy` on `@Bean` vs. `@Lazy` on a constructor parameter: how do they differ for the bean definition and the dependency reference?
20. If a rarely used feature has a constructor taking several seconds, how would you design pre-warming, timeouts, health checks, and user feedback?

## Key Takeaways

- **Lazy initialization** defers creating and initializing a bean **until needed**, though dependencies can still cause the bean to be created early.
- `@Lazy` on `@Bean`/`@Component` affects the **bean definition**; `@Lazy` at an injection point can create a **lazy-resolution proxy**.
- **Singleton scope** does not change: a lazy singleton after its first creation is still retained and reused within the same context.
- Spring Boot does not enable global lazy by default. It can be enabled with `spring.main.lazy-initialization=true` or `SpringApplication.setLazyInitialization(true)`; use `@Lazy(false)` for critical beans that must be eager.
- Constructors, injection, `@PostConstruct`, and init callbacks run **when the bean is actually created**, not at startup for an uninstantiated bean.
- `ApplicationReadyEvent` and readiness do not guarantee all lazy beans exist or are valid.
- Laziness can reduce startup time but **shifts costs and errors** to first use; always measure first-use latency, memory, late-discovered errors, and operational impact.
- `ObjectProvider`, dependency injection, lifecycle callbacks, and runtime readiness must be understood together; slapping `@Lazy` on beans is not a silver bullet for every performance issue.

### References

- Spring Boot 3.3 — Lazy Initialization, SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.lazy-initialization
- Spring Boot 3.3 — SpringApplication Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `@Lazy` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — Bean Scope: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Bean lifecycle callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — `ObjectProvider` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
