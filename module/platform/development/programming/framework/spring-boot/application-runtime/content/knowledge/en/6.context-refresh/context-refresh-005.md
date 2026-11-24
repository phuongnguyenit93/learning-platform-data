# Eager Singleton Instantiation and Completing Refresh

## Objectives

This lesson belongs to **Spring Boot Application Runtime → Context and Refresh**, focusing on when Spring creates singleton beans, the meaning of the `finishBeanFactoryInitialization(...)` step, when `refresh()` truly completes, and which callbacks run before/after those milestones.

After this lesson, you will be able to:

1. Distinguish **singleton scope**, **eager initialization**, and **lazy initialization**.
2. Explain why Spring normally instantiates **non-lazy** singletons during `ApplicationContext.refresh()`, before the application is reported as ready.
3. Distinguish `@PostConstruct`, `InitializingBean`, `SmartInitializingSingleton`, `ContextRefreshedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent`.
4. Run a Spring Boot example observing singleton creation order, refresh completion, on-demand lazy bean creation, and cleanup on context close.
5. Diagnose startup failures, dependencies pulling lazy beans into early creation, startup latency, and understand the limits of calling `refresh()` again.

## 1. Singleton Is a Bean Management Scope, Not an Early-Creation Guarantee

In Spring Framework, the default `singleton` scope means **one managed bean instance per bean definition within a single Spring container**. If two different places receive the same singleton bean from the same context, they normally receive the same object. This does not mean a JVM-wide singleton or that a class may only have one object across all contexts.

Bean definition:

~~~java
@Component
public class PriceService {
}
~~~

The example above illustrates a default singleton **when the component is scanned**. If you create two separate `ApplicationContext` instances, each context can create its own `PriceService` singleton. On the other hand, Java code can still instantiate objects not managed by Spring; singleton scope does not forbid that.

**Eager and lazy are two strategies about instantiation timing**, and do not change how many singletons are held within one context:

| Characteristic | Default singleton, non-lazy | Singleton with `@Lazy` |
| --- | --- | --- |
| Scope | `singleton` | Still `singleton` |
| Typical creation time | During `refresh()`, in the non-lazy singleton initialization phase | When the bean is actually requested; exceptions exist due to dependencies or infrastructure |
| Number of instances Spring manages per bean definition | Normally one per context | Normally one per context |
| Constructor errors | Typically surface immediately at startup | May surface late, when the bean is requested |
| Performance impact | Startup may take longer; errors caught early | May shorten startup, but the first call incurs extra latency |

Note that `prototype` scope beans have a different contract: Spring creates a new instance per appropriate request; they do **not** belong to the set of singletons normally pre-created. Do not lump all scopes under a single instantiation rule.

## 2. Where Does Singleton Pre-Instantiation Sit Inside Refresh?

When `SpringApplication.run(...)` starts Spring Boot, the framework creates an appropriate `ApplicationContext` and then asks the context to execute `refresh()`. Inside `AbstractApplicationContext.refresh()` are these key milestones (internal details omitted for clarity of ordering):

~~~text
SpringApplication.run(...)
  |
  +-- Prepare Environment, create ApplicationContext
  |
  +-- ApplicationContext.refresh()
       |
       +-- prepareRefresh()
       +-- obtainFreshBeanFactory()
       +-- prepareBeanFactory(...)
       +-- postProcessBeanFactory(...)
       +-- invokeBeanFactoryPostProcessors(...)
       +-- registerBeanPostProcessors(...)
       +-- initMessageSource()
       +-- initApplicationEventMulticaster()
       +-- onRefresh()                 (context-specific infrastructure)
       +-- registerListeners()
       |
       +-- finishBeanFactoryInitialization(beanFactory)
       |    |
       |    +-- preInstantiateSingletons()
       |         +-- Create eligible, not-yet-existing singletons
       |         +-- Resolve dependencies / injection
       |         +-- Run bean lifecycle during initialization
       |         +-- Invoke SmartInitializingSingleton callbacks
       |
       +-- finishRefresh()
            +-- Complete context refresh tasks
            +-- Start lifecycle processor/SmartLifecycle
            +-- Publish ContextRefreshedEvent
  |
  +-- Spring Boot: ApplicationStartedEvent
  +-- Spring Boot: ApplicationRunner / CommandLineRunner
  +-- Spring Boot: ApplicationReadyEvent
  |
  +-- run(...) returns ConfigurableApplicationContext
~~~

This diagram reflects the **key milestones of Spring Framework 6.1 and Spring Boot 3.3**, not a verbatim copy of all source statements. Specific contexts or extensions may add their own work, and some beans may be created earlier due to infrastructure or bean definition processing.

Two items to distinguish:

- **`finishBeanFactoryInitialization(...)`**: the point where Spring completes initializing eligible non-lazy singletons of the BeanFactory, with the key step being `preInstantiateSingletons()`. The method name does **not** mean the entire refresh lifecycle and Spring Boot startup are finished.
- **`finishRefresh()`**: the milestone ending the `ApplicationContext` refresh phase. Here the lifecycle processor is invoked and `ContextRefreshedEvent` is published. Spring Boot still continues with its own post-refresh steps (started event, runners, ready event).

In a web application, preparing the embedded server can happen during refresh. **The server may start listening before `ApplicationReadyEvent`**; therefore, an open HTTP port is not proof that all startup runners have finished or that the instance is ready to receive traffic per operational policy.

## 3. What Does Spring Do Inside preInstantiateSingletons()?

When using `DefaultListableBeanFactory`, the `preInstantiateSingletons()` step works over registered bean definitions. Under the standard contract:

1. Inspects eligible bean definitions, targeting **singleton and non-lazy** beans not yet created.
2. Requests their creation through the container mechanism. This can trigger creating dependency beans **before** the dependent bean.
3. The bean goes through constructor/factory method, dependency injection, Aware and BeanPostProcessor callbacks, and lifecycle initialization.
4. After the regular singleton preparation phase, invokes `afterSingletonsInstantiated()` on managed beans implementing `SmartInitializingSingleton`.

Do not think of `preInstantiateSingletons()` as a loop calling `new` in exact source-code order. The container also handles bean definitions, dependencies, post-processors, factory methods, scopes, and proxies. Some infrastructure beans are created earlier to support bootstrapping itself.

### Rules to Remember

- A **non-lazy** singleton can be created during refresh even when no HTTP request has arrived and no class has invoked that service from business logic.
- A **lazy** bean can still be created during refresh when a non-lazy singleton directly requires it via constructor or factory method. `@Lazy` does **not** guarantee the bean is absent at the end of startup.
- Certain `FactoryBean` cases have specific rules; the factory and the object the factory produces do not always share the same instantiation time. Do not extrapolate all beans from simplified examples.
- `preInstantiateSingletons()` does not pre-instantiate **every** prototype or every unrequested lazy singleton.
- When a non-lazy bean has a failing constructor or unsatisfied dependency, startup normally fails right at refresh. This is a benefit of early checking, alongside startup cost.

## 4. Per-Bean Lifecycle Ordering

Consider a regular singleton bean with valid dependencies created under container management:

~~~text
Instantiate (constructor or @Bean factory method)
  |
  +-- Dependency injection / Aware callbacks
  +-- BeanPostProcessor before initialization
  |    +-- @PostConstruct is typically processed in this phase
  |
  +-- InitializingBean.afterPropertiesSet() (if present)
  +-- custom init method (if declared)
  +-- BeanPostProcessor after initialization
  |
  +-- Bean ready to be retrieved from context
~~~

If the bean implements `SmartInitializingSingleton`, `afterSingletonsInstantiated()` is called at a separate milestone **after** the regular singleton pre-instantiation step, rather than right when that bean's own constructor finishes.

| Hook | Timing, scope | Used for |
| --- | --- | --- |
| Constructor / factory method | When creating **one bean** | Establishing valid state, validating basic arguments |
| `@PostConstruct` | During initialization of **that bean** | Validating/assembling locally injected resources |
| `InitializingBean.afterPropertiesSet()` | After properties are set on **that bean** | Validation/finalizing initialization with Spring API dependency |
| Custom `initMethod` | Initialization phase of **that bean** | Init logic without coupling the class to a Spring interface |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | After pre-instantiating non-lazy singletons | Logic that must wait for the regular singleton instantiation phase to finish |
| `ContextRefreshedEvent` | When **ApplicationContext** completes refresh | Observing completion of a refresh pass |
| `ApplicationStartedEvent` | Spring Boot: after refresh, before runners | Observing startup reached at the Boot milestone |
| `ApplicationRunner`, `CommandLineRunner` | After `ApplicationStartedEvent`, before ready | Executing application startup tasks |
| `ApplicationReadyEvent` | After runners, when Boot reaches ready state | Observing the application-ready milestone |

**Note:** `@PostConstruct` on bean A **does not guarantee** all beans B, C, D in the context are already created. If A needs B, injection resolves B according to dependency rules; unrelated singletons might not be instantiated yet. Use `SmartInitializingSingleton` or the event at the appropriate milestone when the requirement is waiting for an overall phase.

`SmartInitializingSingleton` is a callback for *beans created during the pre-instantiation phase*; it does not mean all lazy singletons have already been created. A `SmartInitializingSingleton` that is itself lazy and never created before refresh will not automatically receive the callback on late creation as a way to "re-run all of pre-instantiate."

## 5. Complete Example: Observing Eager, Refresh, and Lazy

The example uses **Java 17+**, **Spring Boot 3.3.13**, and Gradle. It only uses `spring-boot-starter`, making it a **non-web** application; it opens no HTTP port and closes the context itself after the experiment.

### 5.1. Structure

~~~text
singleton-refresh-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/refresh/RefreshLifecycleApplication.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'singleton-refresh-demo'
~~~

File `build.gradle`:

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
    mainClass = 'com.example.refresh.RefreshLifecycleApplication'
}
~~~

File `src/main/java/com/example/refresh/RefreshLifecycleApplication.java`:

~~~java
package com.example.refresh;

import java.util.Locale;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class RefreshLifecycleApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(RefreshLifecycleApplication.class, args)) {

            System.out.println("MAIN: run returned");

            // At this point refresh and Boot startup callbacks have finished.
            // Requesting the lazy bean for the first time triggers its creation.
            LazyParser parser = context.getBean(LazyParser.class);
            System.out.println("MAIN: parsed=" + parser.parse("ab"));
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    EagerCatalog eagerCatalog() {
        return new EagerCatalog();
    }

    @Bean
    @Lazy
    LazyParser lazyParser() {
        return new LazyParser();
    }

    @Bean
    SmartInitializingSingleton allNonLazySingletonsReady(EagerCatalog catalog) {
        // Depending on EagerCatalog ensures that bean already exists.
        return () -> System.out.println(
                "CALLBACK: afterSingletonsInstantiated");
    }

    @EventListener(ContextRefreshedEvent.class)
    void afterContextRefresh() {
        System.out.println("EVENT: ContextRefreshedEvent");
    }

    @EventListener(ApplicationStartedEvent.class)
    void afterBootStarted() {
        System.out.println("EVENT: ApplicationStartedEvent");
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterBootReady() {
        System.out.println("EVENT: ApplicationReadyEvent");
    }

    static final class EagerCatalog {
        EagerCatalog() {
            System.out.println("BEAN: EagerCatalog created");
        }

        @PreDestroy
        public void destroy() {
            System.out.println("BEAN: EagerCatalog destroyed");
        }
    }

    static final class LazyParser {
        LazyParser() {
            System.out.println("BEAN: LazyParser created");
        }

        String parse(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

**Why is this a complete program?** It has a `@SpringBootApplication` class, a `main` method, Gradle dependencies, an eager bean, a lazy bean, a lifecycle callback, helper classes, and a real `getBean` call. Within the same source package, no extra Java files or web server are needed.

### 5.2. Running

From the `singleton-refresh-demo` directory:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows. The Gradle version used must be compatible with Spring Boot 3.3 and the installed Java version.

Ignoring Spring Boot's own logs, **the lines printed by the program itself** have the expected order:

~~~text
BEAN: EagerCatalog created
CALLBACK: afterSingletonsInstantiated
EVENT: ContextRefreshedEvent
EVENT: ApplicationStartedEvent
EVENT: ApplicationReadyEvent
MAIN: run returned
BEAN: LazyParser created
MAIN: parsed=AB
BEAN: EagerCatalog destroyed
MAIN: context closed
~~~

The order of lines above reflects the lifecycle contract for the demo configuration; other build/runtime logs and output lines may be interleaved. Creation order among **unrelated** beans in a large project does not necessarily follow a fixed declaration list order.

### 5.3. Analyzing Each Milestone

**Milestone 1 — `EagerCatalog` is created before `run` returns**

There is no HTTP request and `main` has not called `getBean(EagerCatalog.class)` yet. This singleton is still created because it is non-lazy by default; furthermore, the `allNonLazySingletonsReady` callback takes it as a dependency, so the container must resolve it first.

**Milestone 2 — `SmartInitializingSingleton` is invoked after the singleton instantiation phase**

The line `CALLBACK: afterSingletonsInstantiated` is emitted by the lambda bean implementing `SmartInitializingSingleton`. It runs after pre-instantiating non-lazy singletons, yet **does not** force `LazyParser` to be created. This is the rationale for choosing this callback when an operation depends on regular singletons having finished initialization.

**Milestone 3 — Context refreshed before Boot started/ready milestones**

`ContextRefreshedEvent` is published inside `finishRefresh()`. After `refresh` returns successfully, Spring Boot publishes `ApplicationStartedEvent`, executes startup runners (if any), and then publishes `ApplicationReadyEvent`. The demo has no runners; the distinction between the two events remains important when adding runners later.

**Milestone 4 — `SpringApplication.run` returns and the lazy bean still does not exist**

`MAIN: run returned` appears after the milestones above. Only when `context.getBean(LazyParser.class)` is called must Spring instantiate the missing lazy singleton; the constructor prints `BEAN: LazyParser created`, and `parse("ab")` returns `AB`.

**Milestone 5 — Closing the context is not the same as finishing a request**

`try-with-resources` calls `context.close()` after the main operations. The `EagerCatalog` bean has `@PreDestroy`, so it is cleaned up; then the program prints `MAIN: context closed`. This is a CLI example actively closing the context; in a long-running web application, do not close the context right after startup finishes.

### 5.4. Trying Variations

Do not modify the main example in multiple directions at once; test each variation separately and re-run the application:

1. **Remove `@Lazy` on `lazyParser`.** Expect `LazyParser` to be created during refresh, before the `MAIN: run returned` line.
2. **Keep `@Lazy` but call `context.getBean(LazyParser.class)` twice.** Two lookups in the same context for the same bean definition still return the same singleton; the constructor does not run twice.
3. **Add a non-lazy singleton bean with constructor injection of `LazyParser`.** Now the dependency can force `LazyParser` to be created during refresh, even though it carries `@Lazy`.
4. **Have `EagerCatalog`'s constructor throw an exception.** Startup is aborted before ready; inspect the log for bean creation failure. Do not keep this error in the working demo.
5. **Add an `ApplicationRunner` with a log line.** Confirm the runner runs **after** `ApplicationStartedEvent` and **before** `ApplicationReadyEvent`.
6. **Enable global lazy initialization and re-run.** Observe which beans are deferred and which infrastructure components are still created early. Do not predict that all callbacks still occur identically when changing global configuration.

## 6. @Lazy: Situations Easy to Misunderstand

### @Lazy on a Bean Definition

~~~java
@Bean
@Lazy
ReportEngine reportEngine() {
    return new ReportEngine();
}
~~~

The snippet above is **illustrative**, assuming a `ReportEngine` class and `@Bean`/`@Lazy` imports. Spring does not need to build `ReportEngine` during the non-lazy pre-instantiation phase if nothing requests it early.

### A Non-Lazy Dependency Causes a Lazy Bean to Be Created Early

~~~java
@Component
final class StartupService {

    private final ReportEngine reportEngine;

    StartupService(ReportEngine reportEngine) {
        this.reportEngine = reportEngine;
    }
}
~~~

If `StartupService` is a non-lazy singleton and Spring must inject `ReportEngine` directly when creating it, `ReportEngine` will be resolved even though its bean definition is marked lazy. Therefore, **merely putting `@Lazy` on a bean does not guarantee it stays deferred**.

This is an illustrative snippet with corresponding imports/types in a full project; **do not** add `StartupService` to the section 5 program if you want `LazyParser` to remain uncreated before `getBean`.

### Using ObjectProvider When You Truly Want On-Demand Retrieval

~~~java
@Component
final class ReportControllerSupport {

    private final ObjectProvider<ReportEngine> engine;

    ReportControllerSupport(ObjectProvider<ReportEngine> engine) {
        this.engine = engine;
    }

    String generateReport() {
        return engine.getObject().render();
    }
}
~~~

The snippet above is **partially illustrative**, requiring a `ReportEngine` class with `render()`, imports, and a corresponding project. `ObjectProvider` lets you defer *retrieving the instance* until `getObject()`; another bean can still request `ReportEngine` early, so the outcome is not an absolute guarantee that the bean was never created beforehand.

You can use `@Lazy` at an injection point to receive a proxy that defers dependency resolution in appropriate cases. Understand the effects of the proxy and which method actually triggers the target, rather than using it to mask circular dependency bugs.

### Global Lazy Initialization

Spring Boot supports:

~~~properties
spring.main.lazy-initialization=true
~~~

Or configuring it early in `SpringApplication` code accordingly. Global lazy can speed up startup, but causes certain configuration or connection errors to surface only on the first request/task. Infrastructure beans, listeners, or dependencies required during startup can still be initialized early. **Do not infer that every bean is strictly lazy**, nor enable it solely to hide startup errors.

## 7. Why Doesn't @PostConstruct Replace SmartInitializingSingleton?

Suppose a `CatalogIndex` bean has `@PostConstruct` and wants to look up all `ProductHandler` beans.

Inside `@PostConstruct`, **`CatalogIndex` itself** is finishing initialization, yet singletons **without a dependency relationship** might not have been created by Spring yet. If the task must run after the phase in which all non-lazy singletons have been pre-instantiated, `SmartInitializingSingleton` is the closer-fitting hook:

~~~java
@Component
final class CatalogIndex implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Suitable for verification/aggregation after the pre-instantiate phase.
        // Do not infer that lazy singletons have already been created.
    }
}
~~~

This is an **illustrative snippet**, not a class used directly with the section 5 example; it requires `Component` and `SmartInitializingSingleton` imports.

Keep three levels of milestones in mind:

- **Bean ready:** Initialization steps of a single bean are complete.
- **Non-lazy singleton pre-instantiation complete:** Spring has completed the regular singleton phase in `finishBeanFactoryInitialization` and invoked `SmartInitializingSingleton` callbacks.
- **Context refreshed / Boot ready:** The context has finished `refresh`; Spring Boot still has started, runners, and ready afterward.

If you want to run work requiring **the entire application** to have finished starting and after runners, `ApplicationReadyEvent` is the closer milestone. If you need to provide start/stop hooks for runtime components, look into `SmartLifecycle` and `LifecycleProcessor`: they govern starting/stopping lifecycle beans, not one-time singleton initialization callbacks.

## 8. Successful Refresh, Failure, and Rollback

### When a Non-Lazy Singleton Fails

Example:

~~~java
@Bean
InventoryClient inventoryClient() {
    throw new IllegalStateException(
            "Missing external inventory configuration");
}
~~~

This is an **intentionally failing** example; do not add it to a working project. During refresh, if Spring must create `inventoryClient` and the factory method throws an exception, a `BeanCreationException` or startup exception may be thrown outward. The context cannot be considered successfully refreshed; late callbacks such as `ContextRefreshedEvent` and `ApplicationReadyEvent` are normally not reached on this failed startup.

Spring performs cleanup when refresh fails within the framework's capabilities, including destroying managed singletons where appropriate. However, do not interpret that cleanup as a guarantee that every manually opened external resource is always closed cleanly in every case. Constructors or init methods that open files/sockets/connections and fail partway through must handle their own cleanup.

### A Failed Request Does Not Trigger Another Refresh

In a running web application, a controller may throw an exception during a request. That is normally handled only within the scope of the HTTP request. Do not call `SpringApplication.run(...)` again to "fix" a broken request; doing so can create a second context, duplicate beans, and cause port conflicts.

### Should You Call context.refresh() Again?

**Do not treat `refresh()` as a general hot-reload button for a Spring Boot application.** Not all `ApplicationContext` implementations support multiple refreshes; contexts based on `GenericApplicationContext` normally forbid a second refresh. Even with implementations that support it, changing bean definitions/config and managing all running resources requires explicit design.

To change startup/bean configuration in real applications, prefer deploying a new version, performing a controlled restart, or using a refresh mechanism with an explicit contract (if provided by the system). Editing `application.yml` on disk does not automatically cause an already-created singleton to "re-initialize."

## 9. Relationship to Startup Time, Readiness, and Operations

### What Are the Benefits of Eager Initialization?

- Helps detect missing dependencies, misconfigured beans, and constructor/initialization errors of non-lazy beans early.
- Required singletons are typically already created before reaching context refreshed, reducing unexpected instantiation on the first request.
- Suitable for components that must be ready to serve immediately once traffic is routed to the application.

### What Is the Cost of Eager Initialization?

- Creating many beans early increases startup time and sometimes consumes resources for features not needed right away.
- Constructors/`@PostConstruct` performing long network I/O or blocking operations can delay refresh and readiness.
- Container orchestration startup timeouts can trigger restart loops if startup work is too heavy.

### What Are the Benefits and Limits of Lazy Initialization?

- Defers initialization of a subset of beans until first use; can reduce initial startup cost.
- First use may be slower, and bean errors are discovered later.
- Creation timing can be hard to predict when many beans have complex dependencies; measure with real logs/metrics rather than assuming.

**Readiness ≠ finishRefresh.** `ContextRefreshedEvent` marks context refresh completion, whereas Spring Boot can still run `ApplicationRunner`/`CommandLineRunner` before `ApplicationReadyEvent`. An application may already have an open HTTP port before it is truly ready. Deployment systems should use proper readiness probes to route traffic, rather than just checking whether a port is listening.

To profile startup, you can use `ApplicationStartup`/`BufferingApplicationStartup`, Java Flight Recorder, or Micrometer Observation appropriate to your system version and configuration. Do not mistake the duration of a single bean's constructor for the entire refresh time.

## 10. Common Thinking Errors

**1. "Singletons are always created right at startup."** False. A singleton can be lazy; beans are created on demand after startup or early due to dependencies. Singleton describes scope, not necessarily timing.

**2. "@Lazy guarantees the bean is not created until the first request."** False. An eager bean with a direct dependency on a lazy bean can pull it into creation during refresh. In a CLI app, a lazy bean can be retrieved via `getBean` even without any requests.

**3. "@PostConstruct means all other singletons are already ready."** False. It is only the initialization phase of the current bean. If you need a broader milestone, use `SmartInitializingSingleton` or events as needed.

**4. "finishBeanFactoryInitialization and finishRefresh are the same thing."** False. Completing BeanFactory initialization happens **before** `finishRefresh`; Spring Boot still continues with post-context-refresh startup milestones.

**5. "ContextRefreshedEvent = ApplicationReadyEvent."** False. `ContextRefreshedEvent` belongs to the Spring context; `ApplicationReadyEvent` belongs to Spring Boot and arrives after startup runners when startup succeeds.

**6. "Calling preInstantiateSingletons creates every bean in the JVM."** False. It runs within the corresponding BeanFactory, focusing on eligible non-lazy singletons; other scopes and contexts have their own contracts.

**7. "Beans are initialized in file-name order or @Bean declaration order."** Do not rely on that. The dependency graph, post-processors, and bean infrastructure determine many constraints. Express ordering dependencies only when genuinely needed, and avoid business logic relying on incidental registration order.

**8. "When startup fails, everything external has been rolled back."** False. Container cleanup has limits; operations with external side effects (DB writes, API calls, sending messages) need idempotency and dedicated recovery.

**9. "Lazy initialization is definitely faster in every scenario."** There is no such guarantee. It shifts startup cost to usage time and can increase first-request latency or delay error detection.

**10. "Just call refresh() again to re-run @PostConstruct."** Incompatible with Spring Boot's general mechanism. Identify the actual lifecycle and context type; if beans/config must be recreated, design a supported solution.

## 11. Practice Exercises and Self-Check Questions

1. In the demo, record the order of `EagerCatalog created`, `afterSingletonsInstantiated`, `ContextRefreshedEvent`, and `ApplicationReadyEvent`. Why are they not the same milestone?
2. Remove `@Lazy` from `lazyParser`. Where does the `LazyParser` creation line move? Does this change turn the singleton into a prototype?
3. Keep `@Lazy`, call `context.getBean(LazyParser.class)` twice, and compare with `==`. What result do you predict?
4. Create a non-lazy singleton requiring `LazyParser` in its constructor. Observe whether `LazyParser` still stays deferred until after `run`. Explain why.
5. Add an `ApplicationRunner` with a log message to the example. Which Boot event precedes the runner and which follows it?
6. Intentionally throw an exception inside the `EagerCatalog` constructor. Do the post-refresh milestone log lines appear? Why does the application fail to reach ready?
7. Enable `spring.main.lazy-initialization=true`. Inspect bean creation logs and test the validity of the assumption "all beans are deferred."
8. A service needs to run logic after all non-lazy singletons are instantiated; should you pick `@PostConstruct` or `SmartInitializingSingleton`? If a startup job must finish before the system is reported ready, which runner or event should you consider?
9. If a singleton creates a connection pool during initialization, how do you ensure cleanup when startup fails or the context closes? Why should you avoid network I/O without timeouts inside constructors?
10. If a web application has finished refreshing yet a startup runner is still running, should you conclude the instance is ready for traffic just because a TCP port check succeeds?

## Takeaways

- **Singleton scope** is a rule for bean existence in a container; **eager/lazy** determines instantiation timing.
- During a successful `ApplicationContext.refresh()`, Spring normally **pre-instantiates non-lazy singletons** in `finishBeanFactoryInitialization(...)` and invokes eligible `SmartInitializingSingleton` beans.
- `finishRefresh()` runs afterward and publishes `ContextRefreshedEvent`; Spring Boot also has `ApplicationStartedEvent`, runners, and `ApplicationReadyEvent`.
- `@PostConstruct` only confirms the initialization phase of **one bean**; it does not prove all other singletons or the entire application are ready.
- `@Lazy` does not guarantee a bean stays deferred if a dependency requires it early. Deferred initialization can shift cost and errors to first use.
- Do not arbitrarily use `refresh()` to reload an entire application, and do not treat "port is open" as proof of readiness.

### References

- Spring Framework 6.1 — `AbstractApplicationContext.refresh()`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.1 — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework 6.1 — `SmartInitializingSingleton`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Bean Initialization and Destruction: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Boot 3.3 — SpringApplication and Application Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
