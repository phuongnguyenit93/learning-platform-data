# ContextRefreshedEvent in the Spring Framework and Spring Boot Lifecycle

## 1. What Is ContextRefreshedEvent?

`ContextRefreshedEvent` belongs to `org.springframework.context.event` in **Spring Framework**. It is emitted when an `ApplicationContext` **completes initialization or refresh**. In a typical Spring Boot application, it occurs during `SpringApplication.run(...)`, after Spring Framework finishes building the core bean container, but **before** Spring Boot emits `ApplicationStartedEvent`, invokes `ApplicationRunner`/`CommandLineRunner`, and emits `ApplicationReadyEvent`.

In short:

- **Context created**: an `ApplicationContext` object exists, though beans may not exist yet.
- **Context initialized** via `ApplicationContextInitializer`: early customizations have been applied, while `refresh()` still lies ahead.
- **Context refreshed**: the core steps of `refresh()` finish; `ContextRefreshedEvent` is emitted.
- **Application ready**: Spring Boot has completed runners and its required startup steps; this milestone is **later** than `ContextRefreshedEvent`.

That is why this event is useful to know **the container refreshed successfully up to the event publication point**, yet **insufficient** to conclude the service is ready to accept traffic, all startup tasks have finished, or all external dependencies are healthy.

This lesson follows **Spring Framework 6.1.x, Spring Boot 3.3.x, Java 17+**. You will learn the API, emission timing, relationship with bean lifecycles and `SmartLifecycle`, two ways to write listeners, a runnable example, parent–child contexts, common errors, and how to pick the right event for your goal.

## 2. Where Does ContextRefreshedEvent Sit in the Refresh Sequence?

For a typical `AbstractApplicationContext`, visualize it as follows:

```text
SpringApplication.run(args)
    |
    +-- Prepare Environment
    +-- Create ConfigurableApplicationContext
    +-- Run ApplicationContextInitializer
    +-- ApplicationContextInitializedEvent       [Spring Boot]
    +-- Load configuration sources / bean definitions
    +-- ApplicationPreparedEvent                 [Spring Boot]
    |
    +-- context.refresh()                        [Spring Framework]
    |      |
    |      +-- prepareRefresh()
    |      +-- obtainFreshBeanFactory()
    |      +-- prepareBeanFactory(...)
    |      +-- BeanFactoryPostProcessor / BeanPostProcessor
    |      +-- Initialize MessageSource, event multicaster
    |      +-- onRefresh() / context-specific infrastructure
    |      +-- Register listeners
    |      +-- Instantiate non-lazy singletons
    |      +-- finishRefresh()
    |             |
    |             +-- LifecycleProcessor.onRefresh()
    |             |       +-- auto-start eligible SmartLifecycle beans
    |             |
    |             +-- publish ContextRefreshedEvent   <-- focus
    |
    +-- ApplicationStartedEvent                 [Spring Boot]
    +-- LivenessState.CORRECT                   [Boot availability]
    +-- ApplicationRunner / CommandLineRunner
    +-- ApplicationReadyEvent                   [Spring Boot]
    +-- ReadinessState.ACCEPTING_TRAFFIC        [Boot availability]
```

The order above shows **typical milestones**, not a single mandatory path of every method across all subclasses or custom tests. In particular, `onRefresh()` may prepare the web server and several other infrastructure events.

A point confirmed by the `AbstractApplicationContext.finishRefresh()` Javadoc: this method finishes refresh by invoking `LifecycleProcessor.onRefresh()` and then publishing `ContextRefreshedEvent`. Therefore, `SmartLifecycle` beans configured for auto-start may already have received `start()` **before ContextRefreshedEvent listeners are invoked**.

### 2.1. "Refresh Done" Does Not Mean "Everything Is Done"

Inside the event handler, normal **non-lazy** singletons have already been instantiated. However:

- `@Lazy` beans may **not have been created yet**.
- Spring Boot's `ApplicationRunner`/`CommandLineRunner` beans **have not been called yet**.
- A background worker may have just started and not yet finished its work.
- A `SmartLifecycle` bean may be configured to run only on an explicit start command rather than auto-start.
- Opening an HTTP server does not prove external dependencies are healthy or that the instance is allowed to accept traffic.
- An async listener may process after the event emission milestone rather than providing synchronous listener guarantees.

Therefore, treat this event as a **bean container lifecycle milestone**, not as a comprehensive readiness probe.

## 3. This Is a Spring Framework Event, Not Specific to Spring Boot

Fully qualified class name:

```java
org.springframework.context.event.ContextRefreshedEvent
```

`ContextRefreshedEvent` extends `ApplicationContextEvent`, is an `ApplicationEvent`, and is emitted by the framework when an `ApplicationContext` is initialized or refreshed. It appears in both plain Spring Framework applications and Spring Boot.

Two key APIs:

```java
ApplicationContext getApplicationContext();
long getTimestamp();
```

These are two API-explanatory signatures, **not a standalone Java program**:

- `getApplicationContext()`: retrieves the context **that emitted the event**. Use it to check instance identity, distinguish parent/child contexts, and look up beans when appropriate.
- `getTimestamp()`: the timestamp when the event object was created, **not** startup duration or a completion-time guarantee for all tasks.
- `getSource()` from the superclass also relates to the context, though `getApplicationContext()` is clearer in meaning and type.

Do not manually instantiate `new ContextRefreshedEvent(context)` and publish it to simulate a refresh. That is merely an event object: Spring will not run the full `refresh()` sequence simply because you published an event manually.

### 3.1. Does Active Context Equal Ready?

At the time of the event, a normal context reports `isActive() == true`. However, `AbstractApplicationContext` may set the active flag **early during `refresh()`**. Combining `isActive()` with `ContextRefreshedEvent` shows you observed a specific milestone, yet still does not prove:

- Spring Boot has executed its runners.
- `ReadinessState` is `ACCEPTING_TRAFFIC`.
- A Kubernetes probe returns 200.
- The database, cache, or queue is responsive.
- All asynchronous startup jobs have finished.

When deciding whether to accept traffic, use the availability/readiness mechanism designed for operations.

## 4. How Does ContextRefreshedEvent Differ from Other Startup Events?

| Event | Source | Emission milestone | Are regular application beans ready? |
| --- | --- | --- | --- |
| `ApplicationContextInitializedEvent` | Spring Boot | After `ApplicationContextInitializer` runs, before loading bean definitions | Not yet. |
| `ApplicationPreparedEvent` | Spring Boot | After loading bean definitions, before `refresh()` | Not yet. |
| **`ContextRefreshedEvent`** | **Spring Framework** | **End of `refresh()`, after instantiating regular singletons and auto-start lifecycle beans** | **Usually non-lazy singletons are available.** |
| `ApplicationStartedEvent` | Spring Boot | After refresh, before runners | Refreshed; runners have not run yet. |
| `ApplicationReadyEvent` | Spring Boot | After runners | Boot startup-completion milestone, about to announce accepting traffic. |
| `ContextStartedEvent` | Spring Framework | When `ConfigurableApplicationContext.start()` is called | Signals start of the lifecycle processor; not synonymous with refresh. |
| `ContextStoppedEvent` | Spring Framework | When `ConfigurableApplicationContext.stop()` is called | Bean container usually remains active. |
| `ContextClosedEvent` | Spring Framework | During context closing | Shutting down, not refreshing. |

**Two very easy points to confuse:**

1. `ApplicationContextInitializedEvent` contains "Initialized," yet it is an **early Boot milestone** before loading definitions/refresh. `ContextRefreshedEvent` is the **milestone after Spring Framework refreshes the context**.
2. `ContextStartedEvent` is emitted when `context.start()` is called; it is **not** emitted just because Boot emitted `ApplicationStartedEvent`. The two events have similar names but are driven by different mechanisms.

### 4.1. Order of ContextRefreshedEvent and ApplicationStartedEvent

In a standard successful startup:

```text
ApplicationPreparedEvent
      |
context.refresh()
      |
ContextRefreshedEvent
      |
ApplicationStartedEvent
      |
ApplicationRunner / CommandLineRunner
      |
ApplicationReadyEvent
```

When a `ContextRefreshedEvent` listener runs synchronously, `SpringApplication.run(...)` is still inside refresh and has not returned the context to `main` yet. If the handler throws an unhandled exception, startup can abort before reaching `ApplicationStartedEvent`.

## 5. Approach 1: Catching the Event with @EventListener in a Bean

For `ContextRefreshedEvent`, the common approach is `@EventListener` on a Spring-managed bean:

```java
package com.example.lifecycle;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshLogger {

    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed: "
                + event.getApplicationContext().getId());
    }
}
```

This is a **complete Java file** at `src/main/java/com/example/lifecycle/RefreshLogger.java` in a Spring Boot project whose component scan covers this package. Once the container finishes building non-lazy singletons and emits the event, the `@EventListener` processor is already wired to invoke the method.

Why does this work here, whereas `@EventListener(ApplicationContextInitializedEvent.class)` on a regular bean arrives too late? Because `ContextRefreshedEvent` is emitted **at the end of refresh**, after Spring has processed singletons and registered listener methods; by contrast, `ApplicationContextInitializedEvent` arrives **before refresh**, before listener beans exist.

### 5.1. Event Listener Technique in Spring Framework

An `@EventListener` method can take the event as a parameter. With a single `ContextRefreshedEvent` parameter, specifying the class in the annotation is optional:

```java
@EventListener
public void handle(ContextRefreshedEvent event) {
    // Use event.getApplicationContext().
}
```

This is an **illustrative method inside a Spring bean**, not a standalone class. Both `@EventListener(ContextRefreshedEvent.class)` and `@EventListener` with an event parameter are valid.

A default synchronous handler **should be brief and predictable**. If you need heavy work or must guarantee execution only after full Boot startup finishes, consider `ApplicationRunner` or a later event.

## 6. Approach 2: Implementing ApplicationListener<ContextRefreshedEvent>

If you want type safety with a dedicated listener class:

```java
package com.example.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.stereotype.Component;

@Component
public class RefreshListener
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("Framework context id: "
                + event.getApplicationContext().getId());
    }
}
```

This is also a **complete Java file** in a project with a Spring context. The listener is registered as a bean and invoked by Spring when the event is published.

You can manually register an `ApplicationListener<ContextRefreshedEvent>` **before `run`** using `SpringApplication.addListeners(...)`, or `ConfigurableApplicationContext.addApplicationListener(...)` before refresh inside an initializer. However, you do **not need** ultra-early registration for this event when a properly scanned listener bean already exists.

**Do not register both examples in the same project unless you want duplicate logs**: these are two alternatives, or they can coexist if two handlers are intentional.

### 6.1. Choosing @EventListener or ApplicationListener?

| Criterion | `@EventListener` | `ApplicationListener` |
| --- | --- | --- |
| Syntax | Method annotation inside a bean | Class/interface with generic type |
| Best suited for | Short event logic inside the app | Dedicated, easily reusable listener components |
| Registered via component scan | Yes | Yes |
| Can register early outside BeanFactory | Not its main purpose | Yes, via `SpringApplication.addListeners` |
| Type-safe | By parameter/event class | By generic type parameter |
| Needs parent-child filtering | Possibly yes | Possibly yes |

There is no "single right way"; choose based on testability, lifecycle placement, and project architecture.

## 7. Complete Example: Observing Refresh, SmartLifecycle, and Boot Readiness

We create a Spring Boot application **without an HTTP server** to demonstrate the exact sequence unaffected by a servlet container. The program has:

- An auto-starting `SmartLifecycle` bean that logs when starting and stopping.
- An observer bean catching `ContextRefreshedEvent`, `ApplicationStartedEvent`, and `ApplicationReadyEvent`.
- An `ApplicationRunner` that logs after `ApplicationStartedEvent`.
- `try-with-resources` to close the context cleanly when `run(...)` returns.

**File:** `src/main/java/com/example/lifecycle/ContextRefreshDemoApplication.java`

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ContextRefreshDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextRefreshDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("06 RUN_RETURNED active=" + context.isActive());
        }
    }

    @Bean
    SmartLifecycle sampleLifecycle() {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                running = true;
                System.out.println("01 LIFECYCLE_START");
            }

            @Override
            public void stop() {
                running = false;
                System.out.println("07 LIFECYCLE_STOP");
            }

            @Override
            public void stop(Runnable callback) {
                stop();
                callback.run();
            }

            @Override
            public boolean isRunning() {
                return running;
            }

            @Override
            public boolean isAutoStartup() {
                return true;
            }

            @Override
            public int getPhase() {
                return 0;
            }
        };
    }

    @Bean
    EventObserver eventObserver(ApplicationContext ownContext) {
        return new EventObserver(ownContext);
    }

    @Bean
    ApplicationRunner reportRunner() {
        return arguments -> System.out.println("04 RUNNER");
    }

    public static final class EventObserver {
        private final ApplicationContext ownContext;

        public EventObserver(ApplicationContext ownContext) {
            this.ownContext = ownContext;
        }

        @EventListener
        public void afterRefresh(ContextRefreshedEvent event) {
            if (event.getApplicationContext() != ownContext) {
                return; // Ignore events emitted from child contexts if any.
            }
            ConfigurableApplicationContext context =
                    (ConfigurableApplicationContext) ownContext;
            System.out.println("02 CONTEXT_REFRESHED active="
                    + context.isActive());
        }

        @EventListener
        public void afterStarted(ApplicationStartedEvent event) {
            if (event.getApplicationContext() == ownContext) {
                System.out.println("03 APPLICATION_STARTED");
            }
        }

        @EventListener
        public void afterReady(ApplicationReadyEvent event) {
            if (event.getApplicationContext() == ownContext) {
                System.out.println("05 APPLICATION_READY");
            }
        }
    }
}
```

### 7.1. Dependencies and Environment

In a Java 17+ project configured with Spring Boot Gradle plugin 3.3.x and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

If you want a minimal Gradle Groovy DSL build script, the main part can be:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Note: the build script above assumes you have Gradle and compatible plugins; this example illustrates Boot 3.3.x configuration and does not require the exact patch version shown if your project pins another compatible 3.3.x release. With `WebApplicationType.NONE`, the application needs no web starter, port 8080, or database.

### 7.2. Running the Program

In the project directory with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD:

```bat
gradlew.bat bootRun
```

If the project has multiple `main` classes, configure the right main class for `bootRun` or keep a single main class in the source set.

### 7.3. Logs in Exact Lifecycle Order

Ignoring the banner, Spring INFO/DEBUG lines, and Gradle logs, the lines **printed by the example itself** appear in the expected order:

```text
01 LIFECYCLE_START
02 CONTEXT_REFRESHED active=true
03 APPLICATION_STARTED
04 RUNNER
05 APPLICATION_READY
06 RUN_RETURNED active=true
07 LIFECYCLE_STOP
```

Explaining each milestone:

1. `01`: `DefaultLifecycleProcessor.onRefresh()` auto-starts the `SmartLifecycle` bean.
2. `02`: `ContextRefreshedEvent` is published after that step; the context is active.
3. `03`: Spring Boot emits `ApplicationStartedEvent` after `refresh()`.
4. `04`: `ApplicationRunner` is invoked by Boot after `ApplicationStartedEvent`.
5. `05`: Boot emits `ApplicationReadyEvent` once runners complete.
6. `06`: `SpringApplication.run(...)` returns the context to `main`.
7. `07`: exiting the `try-with-resources` block closes the context, and the lifecycle bean receives `stop()`.

With a standard single context and no interfering listeners/runners, the order of **lines printed by this code itself** is deterministic. Spring may interleave framework logs; adding asynchronous listeners or multiple contexts can make global log order more complex.

**Important:** `EventObserver` is registered as a `@Bean`, yet still catches `ContextRefreshedEvent` because listener beans and annotation processors are ready **before `finishRefresh()`**. That differs from ultra-early events like `ApplicationContextInitializedEvent`.

### 7.4. Is @EnableAsync Needed to Receive the Event?

No. The example handles events **synchronously**, which is the standard mechanism. If you add `@Async` to a listener and configure async support, the handler's completion order is no longer guaranteed to match the logs above. Do not switch a handler to async if its logic is a prerequisite before the application starts serving; instead, use a coordination mechanism with explicit completion rather than fire-and-forget.

## 8. @PostConstruct, Singletons, and @Lazy at Event Time

During `refresh()`, Spring typically:

1. Registers and runs `BeanFactoryPostProcessor` instances, and prepares `BeanPostProcessor` instances.
2. Instantiates **non-lazy** singletons and invokes their initialization callbacks.
3. Finishes refresh, starts lifecycle components, and emits `ContextRefreshedEvent`.

Example:

```java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class InventoryCache {

    @PostConstruct
    public void initialize() {
        System.out.println("InventoryCache initialized");
    }
}
```

If `InventoryCache` is component-scanned, this non-lazy singleton typically runs `@PostConstruct` **before** listeners receive `ContextRefreshedEvent`. This order holds within a normal application context and does not depend on an HTTP server.

However, if the bean is `@Lazy`:

```java
@Lazy
@Component
public class LazyExporter {
    // Constructor runs only when the bean is actually requested.
}
```

This is an illustrative class requiring `@Lazy` and `@Component` imports; it is not a standalone program with its own `main`. `ContextRefreshedEvent` **does not force every lazy bean to be instantiated**. A lazy bean may only be created when code requests it later.

### 8.1. Do Not Call getBean for Every Bean Type Upon Receiving the Event

Even though the BeanFactory is operational, calling `getBean(...)` in bulk inside a listener can:

- Defeat lazy initialization.
- Prolong startup.
- Trigger uncontrolled network I/O or data loading.
- Create circular dependencies or hard-to-trace errors.
- Accidentally turn an event handler into business work with side effects.

Retrieve only the dependencies the handler genuinely needs. When initial data loading is a mandatory startup step, `ApplicationRunner` usually has a clearer place in the Spring Boot sequence.

## 9. SmartLifecycle and ContextRefreshedEvent

`Lifecycle` and `SmartLifecycle` provide the `start()`/`stop()` contract for stateful running beans. Spring uses a `LifecycleProcessor` (typically `DefaultLifecycleProcessor`) to coordinate them.

`SmartLifecycle` adds:

- `isAutoStartup()`: whether the bean starts automatically on context refresh.
- `getPhase()`: phase for ordering start/stop.
- `stop(Runnable callback)`: signals asynchronous stop completion; must invoke the callback when done stopping.

Inside `AbstractApplicationContext.finishRefresh()`, the processor receives `onRefresh()` **before** `ContextRefreshedEvent` is emitted. Eligible auto-start `SmartLifecycle` beans can therefore be started before event listeners run.

### 9.1. Not Every Lifecycle Bean Is Already Running

A bean implementing only `Lifecycle` is generally not auto-started like `SmartLifecycle.isAutoStartup()`. A `SmartLifecycle` bean can also return `false` from `isAutoStartup()`. Therefore:

```text
ContextRefreshedEvent emitted
      !=
every Lifecycle bean is running
      !=
every background job has completed
```

If you need to know whether a specific worker has picked up tasks, inspect that worker's actual state or design a dedicated event/health indicator instead of inferring it from context refresh.

### 9.2. Is ContextRefreshedEvent Re-emitted When Calling start()?

**Not under the normal contract.** `context.start()` tells `LifecycleProcessor` to start eligible lifecycle beans and emits `ContextStartedEvent`. It **does not call `refresh()` again**, so it does not produce another `ContextRefreshedEvent` merely from starting after a stop.

Similarly, `context.stop()` emits `ContextStoppedEvent` and stops lifecycle beans; `context.close()` enters shutdown and emits `ContextClosedEvent`. The three operations should not be confused with "refresh."

## 10. Can ContextRefreshedEvent Be Emitted Multiple Times?

There is no "strictly once per JVM" guarantee. Scenarios to consider:

- **Multiple contexts:** applications with parent/child contexts, multiple `SpringApplication` instances, or multiple tests spinning up different contexts.
- **Some implementations support repeated refresh:** calling `refresh()` again validly emits a new event.
- **Event propagation:** an event emitted in a child context can be forwarded to listeners in a parent context.
- **Duplicate listener registration:** the same logic can receive two callbacks even when only one real context refresh occurred.

Conversely, many implementations based on `GenericApplicationContext` allow refreshing only once. `Spring Boot` typically does not design runtime flows around repeatedly invoking `refresh()`; do not treat this event as an application restart button.

### 10.1. Why Does a Listener in the Parent Receive Child Events?

Spring Framework allows events from a child context to propagate up to its parent context. If you have:

```text
Parent ApplicationContext
    |
    +-- Child ApplicationContext
            |
            +-- refresh() -> ContextRefreshedEvent(child)
                                   |
                              Child listeners
                                   |
                              Parent listeners
```

A listener in the parent may receive **child** events, not solely events emitted by the parent. If cache loading or resource registration runs on every received event without filtering, it may run twice or against the wrong context.

### 10.2. Filtering Events to the Right Context

Example of a Spring bean injected with its own context:

```java
@Component
public class OwnContextRefreshHandler {

    private final ApplicationContext ownContext;

    public OwnContextRefreshHandler(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("My own context refreshed");
    }
}
```

This is an **illustrative Java class** inside a project package; it requires importing `org.springframework.stereotype.Component`, `ApplicationContext`, `ContextRefreshedEvent`, and `EventListener`. Identity comparison with `!=` answers "is the context that emitted the event the exact context of this bean?" rather than comparing displayName values that could collide.

If you want a side effect to run **once per deployment**, context filtering only solves part of it. Idempotency and an appropriate strategy are still needed if tests or runtime recreate contexts multiple times.

## 11. Should ContextRefreshedEvent Be Used for Business Initialization?

It depends on what you need.

**Tasks that only need a refreshed container:** a listener can be suitable for logging configuration, registering a lightweight hook, or inspecting built bean metadata.

**Mandatory startup tasks needing beans/repositories:** typically use `ApplicationRunner`/`CommandLineRunner`, because Spring Boot's sequence is designed to execute runners **after context refresh and before ready**.

**Tasks that must finish before the instance accepts traffic:** coordinate with real readiness; do not just create an `@Async @EventListener(ContextRefreshedEvent.class)` and assume the app will wait for it to finish.

### 11.1. Scenario: Initializing a Cache from a Database

Suppose the application needs to populate a data cache. Placing heavy database queries in a `ContextRefreshedEvent` listener can block startup, increase wait times, and cause refresh to fail on database hiccups. A clearer alternative:

```java
@Bean
ApplicationRunner warmCache(CacheService service) {
    return args -> service.warmUp();
}
```

This is a snippet inside `@Configuration`/`@SpringBootApplication`; it assumes `CacheService` is a bean with a `warmUp()` method, and requires importing `ApplicationRunner` and `@Bean`. When the runner is called by Boot, singletons are ready. Configure timeouts, error handling, and health/readiness per business requirements. **Do not treat this snippet as standalone Java** without `CacheService`.

### 11.2. Scenario: Registering a Listener or Metric After Refresh

If you only need to log "context X refreshed" and read bean definition counts, a brief listener fits. Do not use the event as a "final hook to add any bean": by then singleton creation has already completed; late bean definition edits may not enter the ready state as intended.

When you want to modify BeanFactory configuration, consider `BeanDefinitionRegistryPostProcessor` or `BeanFactoryPostProcessor`, which run **before** singleton creation.

## 12. How Do Errors in a Listener Affect Startup?

Under normal synchronous event configuration, listeners are invoked directly on the `ContextRefreshedEvent` publishing path. If a listener throws an unhandled exception, it can propagate out of `publishEvent` and cause `refresh()` to fail. Spring performs appropriate cleanup and Boot may emit `ApplicationFailedEvent`.

That is why an audit/diagnostic-only handler should not alter startup outcome due to auxiliary I/O failures. Conversely, if it validates a **mandatory** condition for safe startup, intentional fail-fast behavior can be reasonable.

### 12.1. Comparing Synchronous and Asynchronous Listener Reactions

- **Synchronous (usually default):** handler code runs on the publishing path; timeouts/errors can affect startup.
- **Configured asynchronous:** the handler may run after `publishEvent` returns, with errors handled by the executor/async error mechanism; startup may proceed before business results are ready.
- **Transaction-bound listener:** `@TransactionalEventListener` has a contract tied to transactions. `ContextRefreshedEvent` is not normally emitted inside a business transaction, so do not use it as a drop-in replacement for `@EventListener`.

Do not call `Thread.sleep(...)` inside an event listener to "wait for the server to be ready." Use the proper Spring Boot event or readiness API.

### 12.2. Startup Failures Can Still Happen After Refresh

An application can emit `ContextRefreshedEvent` successfully and then have an `ApplicationRunner` throw an exception. In that case `ApplicationStartedEvent` may have occurred, while `ApplicationReadyEvent` will not. Therefore, "seeing ContextRefreshedEvent in the logs" is **not proof that overall startup PASSED**.

## 13. Does the Event Relate to Active, Running, and Closed States?

`ConfigurableApplicationContext` provides `isActive()` and `Lifecycle` operations such as `start()`, `stop()`, and `isRunning()`. Distinguish them:

- **`isActive()`:** whether the context is active per the refresh/close lifecycle. Inside `ContextRefreshedEvent`, this is normally `true`.
- **`isRunning()`:** running state per `LifecycleProcessor`; typically `true` after `finishRefresh()` with the default processor, though it does not mean every application/bean is healthy.
- **`close()`:** closes the context, stops lifecycle beans, and destroys singletons; `ContextClosedEvent` belongs to the shutdown path.
- **`start()/stop()`:** coordinates managed lifecycle beans; does not re-run a full `refresh()`.
- **"Closed"** has no universal `ConfigurableApplicationContext.isClosed()` in the commonly used contract; `isActive() == false` can mean either not yet refreshed or already closed.

Simple state example:

```text
Before refresh:
    active=false, running=false

After successful refresh:
    active=true, running=true (typically)

After context.stop():
    active=true, running=false

After context.start():
    active=true, running=true

After context.close():
    active=false, running=false
```

Not every custom context or lifecycle processor produces the exact same table. What is certain is that **`ContextRefreshedEvent` and `ContextClosedEvent` sit at opposite ends of the context lifecycle**.

## 14. Spring Boot Readiness, Liveness, and ContextRefreshedEvent

In Spring Boot 3.3, `ApplicationAvailability` separates two operational concepts:

- `LivenessState`: `CORRECT` or `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`.

Typical startup progression:

```text
ContextRefreshedEvent
    |
ApplicationStartedEvent
    |
LivenessState.CORRECT
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
```

Hence, at `ContextRefreshedEvent`, readiness is not yet guaranteed to allow traffic. If the application includes Spring Boot Actuator, `/actuator/health/liveness` and `/actuator/health/readiness` probes can be useful when enabled and configured appropriately. In Kubernetes, Boot can automatically enable availability probes, though actual endpoints depend on Actuator config, management port, and network routing.

**Do not replace readiness with a listener setting a custom "READY=true" boolean in `ContextRefreshedEvent`.** Doing so could open traffic while runners have not finished or a required dependency is still unready.

## 15. Distinguishing ContextRefreshedEvent from Test Lifecycles

In Spring Boot or Spring Framework tests:

- `@SpringBootTest` uses Spring TestContext, which can **cache** `ApplicationContext` across multiple tests.
- `ContextRefreshedEvent` fires when a context actually refreshes, **not necessarily before every test method**.
- If a single cached context serves the entire test suite, the listener may be invoked fewer times than the number of tests.
- Using `@DirtiesContext` forces the test framework to evict the cache and create/refresh a new context, triggering a new event; do not use it indiscriminately as it increases startup time.
- If the listener has side effects on a real database, queue, or external resource, tests may inadvertently trigger side effects on every refresh or context recreation.

To test a listener in isolation, it is often better to unit-test the event-handling method with a suitable mock/constructed context and keep integration tests for the real milestone to a minimum.

### 15.1. Parent-Child Events in Tests

A test with a context hierarchy can produce events from both parent and child; a parent listener may receive child events too. When counting listener invocations, record context id/identity and filter for the target context instead of assuming one callback = one application startup.

## 16. Diagnosing Common Misconceptions

| Symptom or statement | Cause / truth | Resolution |
| --- | --- | --- |
| "ContextRefreshedEvent means the app is completely ready." | Boot runners and readiness still come afterward. | Use `ApplicationReadyEvent` and readiness probes. |
| "Cannot catch ContextRefreshedEvent with @EventListener." | Listener bean not scanned, wrong annotation import, or different context. | Check component scan, bean registration, and context identity. |
| "Must call addListeners in main to catch this event." | That requirement applies to certain **early Boot events**. | For ContextRefreshedEvent, a listener bean or `@EventListener` is usually enough. |
| "ContextRefreshedEvent runs before @PostConstruct." | Eager singleton init and callbacks typically run before finishRefresh. | Check lazy/non-lazy settings and bean lifecycle. |
| "Seeing the event means all @Lazy beans are created." | Lazy beans may still be uninstantiated. | Do not assume; request the specific bean only when needed. |
| "SmartLifecycle always starts after ContextRefreshedEvent." | `LifecycleProcessor.onRefresh()` typically runs before publishing the event. | Check phase and `isAutoStartup()`. |
| "context.start() re-emits ContextRefreshedEvent." | `start()` relates to `ContextStartedEvent`. | Distinguish refresh from start. |
| "An event occurs only once across the JVM." | Multiple contexts/refreshes or propagation can trigger multiple callbacks. | Filter by context and design idempotently. |
| "A listener in the parent hears only the parent." | Child events can propagate to the parent. | Compare `event.getApplicationContext() == ownContext`. |
| "Seeing ContextRefreshedEvent guarantees startup succeeds." | Runners or late callbacks can still fail. | Watch `ApplicationReadyEvent` and post-event exceptions. |
| "ContextRefreshedEvent is used to restart the context." | The event is a notification, not a refresh command. | Let the framework own the lifecycle. |
| "Running infinite I/O on the event won't affect startup." | Synchronous listeners can block or break refresh. | Bound work, add timeouts, use runners, or redesign. |
| "@TransactionalEventListener is equivalent to @EventListener." | Transactional listeners require transaction conditions. | Use `@EventListener` for normal context events. |
| "Getting HTTP 404 means ContextRefreshedEvent hasn't happened." | The server may be running without a matching route. | Check logs, handler mappings, URLs, and probes. |

## 17. Production Implementation Checklist

1. Decide whether you need the **context refresh**, **Boot started**, **runners complete**, or **readiness** milestone before choosing an event.
2. For `ContextRefreshedEvent`, prefer a small, clear, idempotent listener bean.
3. If using parent/child contexts, always check `event.getApplicationContext()`.
4. Do not assume lazy beans are created; avoid fetching all beans just to inspect them.
5. If using `SmartLifecycle`, check `isAutoStartup()` and `getPhase()`.
6. Do not call `context.refresh()` or `context.close()` from a listener just to "control progress."
7. Do not perform blocking network I/O or infinite retries in a synchronous handler.
8. For mandatory pre-ready tasks, use runners + timeouts + failure policies; verify readiness.
9. Do not treat this event as a shutdown event; `ContextClosedEvent` belongs to context closing.
10. If your app uses test context caching, never assert "every test gets one ContextRefreshedEvent."
11. When startup fails, distinguish failures in refresh listeners from failures in post-refresh runners.
12. Inspect your app's own logs separately from framework logs; do not rely on the ordering of asynchronous loggers.
13. For production services, combine traces/metrics, Spring Boot Actuator, and dependency health rather than a custom boolean flag.
14. When separating operations by phase, use `BeanFactoryPostProcessor`, `@PostConstruct`, `SmartLifecycle`, `ApplicationRunner`, or `ApplicationReadyEvent` according to their contracts.

## 18. Self-Check Questions

**1. Does ContextRefreshedEvent occur before non-lazy singletons are created?**

No; in a standard `AbstractApplicationContext` it is emitted at the end of `refresh()`, after the container finishes instantiating non-lazy singletons.

**2. Can @EventListener on a normal bean catch ContextRefreshedEvent?**

Yes. Unlike ultra-early Boot events, this event arrives when Spring already has the bean listener processing infrastructure in place.

**3. At ContextRefreshedEvent, has ApplicationRunner run yet?**

Not in the standard `SpringApplication.run` sequence. Runners execute after `ApplicationStartedEvent`, while the refresh event occurs earlier.

**4. When calling context.stop() and then context.start(), which event reflects the start command?**

`ContextStartedEvent`, not `ContextRefreshedEvent`. Start does not automatically refresh the context.

**5. Can a listener in a parent context receive child events?**

Yes. Compare `event.getApplicationContext()` against the listener's actual context if you want to handle only its own events.

**6. Does ContextRefreshedEvent prove the HTTP server is ready and backend databases are always healthy?**

No. It is a container lifecycle milestone; readiness/health require separate checks.

**7. Is SmartLifecycle auto-started before or after the refresh event?**

In `AbstractApplicationContext.finishRefresh()` with the default processor, `onRefresh()` starts eligible `SmartLifecycle` beans **before** publishing `ContextRefreshedEvent`.

**8. What happens if a synchronous ContextRefreshedEvent listener throws an exception?**

It can cause `refresh()`/startup to fail, triggering cleanup and `ApplicationFailedEvent`. Therefore, choose an intentional error-handling strategy.

## 19. Summary

```text
ApplicationContextInitializedEvent  [Boot: before loading bean definitions]
               |
ApplicationPreparedEvent            [Boot: before refresh]
               |
           refresh()
               |
     instantiate non-lazy singletons
               |
     LifecycleProcessor.onRefresh()
               |
      ContextRefreshedEvent          [Framework: context refresh]
               |
      ApplicationStartedEvent        [Boot: after refresh]
               |
        ApplicationRunner
               |
       ApplicationReadyEvent         [Boot: after runners]
               |
      Readiness ACCEPTING_TRAFFIC
```

**Quick rule of thumb:** `ContextRefreshedEvent` says **the Spring bean container has refreshed**, not **Spring Boot's full startup process is finished**. It differs from `ApplicationContextInitializedEvent`, `ContextStartedEvent`, and `ContextClosedEvent`. Pick the right phase for bean-dependent work, rely on readiness before opening traffic, and filter events by actual context when multiple contexts exist.

## Official Documentation

- [Spring Framework 6.1 — ContextRefreshedEvent API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html)
- [Spring Framework 6.1 — AbstractApplicationContext API, finishRefresh()](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — Application events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Bean lifecycle, Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication events and listeners](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Application Availability, readiness/liveness](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability)
