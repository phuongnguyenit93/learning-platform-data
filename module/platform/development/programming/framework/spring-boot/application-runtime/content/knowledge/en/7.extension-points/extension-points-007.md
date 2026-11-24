# Distinguishing RunListener from ApplicationListener and Runners in Spring Boot 3.3

## 1. Goal

In Spring Boot, the terms "listener" and "runner" are easy to confuse because all of them relate to `SpringApplication.run(...)`. However, these three groups of extension points solve **three distinct kinds of needs**:

1. **`SpringApplicationRunListener`** tracks the `SpringApplication.run(...)` call chain itself, from the very first bootstrap steps through success or failure.
2. **`ApplicationListener<E>`** reacts to specific **Spring events**; depending on how it is registered, it can receive ultra-early events or events fired while the application is running.
3. **`ApplicationRunner` / `CommandLineRunner`** are **Spring beans invoked by Boot to perform work after the context has refreshed**, before the milestone where the application is marked ready.

This article uses **Spring Boot 3.3 and Java 21** to accurately distinguish APIs, timing, registration methods, received data, dependency injection (DI) capability, error handling, and selection scenarios. At the end is a complete runnable Maven example.

**Guiding question:** Do you need to observe **the entire `run()` process**, receive **a type of application event**, or **execute an initialization task needing Spring beans**? Answering this question helps pick the right extension point.

## 2. Overview comparison

| Criterion | `SpringApplicationRunListener` | `ApplicationListener<E>` | `ApplicationRunner` / `CommandLineRunner` |
| --- | --- | --- | --- |
| Nature | SPI observing phases of `SpringApplication.run()` | Listener in the Spring application events system | Bean with a `run(...)` callback to perform startup tasks |
| Key methods | `starting`, `environmentPrepared`, `contextPrepared`, `contextLoaded`, `started`, `ready`, `failed` | `onApplicationEvent(E event)` | `run(ApplicationArguments)` or `run(String... args)` |
| Timing | Multiple milestones from ultra-early through end of startup | When the matching event is published; depends on registration | After `ApplicationStartedEvent`, before `ApplicationReadyEvent` |
| Depends on bean container? | Must not assume the container is ready | Early-registered listeners need no beans; bean-based listeners exist only once the container creates beans | Yes; runners are Spring-managed beans |
| Common registration | `META-INF/spring.factories`, key `org.springframework.boot.SpringApplicationRunListener` | `SpringApplication.addListeners(...)`, `spring.factories`, or bean/`@EventListener` for late events | `@Component` or `@Bean` returning a runner |
| Receives CLI arguments? | Constructor `(SpringApplication, String[])` | Some `SpringApplicationEvent` types expose `getArgs()` | Structured `ApplicationArguments` or raw `String...` |
| When to use? | Framework/infrastructure-level bootstrap integration, timing startup phases | Observing events/lifecycle, handling application events | Controlled warm-up, data validation, post-refresh initialization |
| Thrown exceptions | Can cause bootstrap to fail | Can propagate and affect the event-publishing phase | Runner errors cause startup to fail, never reaching normal ready |

**Practical rule:** Business applications normally use **runners** for initialization tasks and **ApplicationListener** for events. Only use **SpringApplicationRunListener** when you genuinely need a deep hook into `SpringApplication.run()` or are writing an infrastructure integration library.

## 3. Shared timeline in Spring Boot 3.3

The following diagram combines all three mechanisms into a single successful startup:

```text
main(String[] args)
  |
  +-- new SpringApplication(App.class)
  +-- app.addListeners(...)                 [register early ApplicationListener]
  |
  +-- app.run(args)
       |
       +-- SpringApplicationRunListener.starting(...)
       |     +-- ApplicationStartingEvent
       |
       +-- Prepare Environment
       +-- RunListener.environmentPrepared(...)
       |     +-- ApplicationEnvironmentPreparedEvent
       |
       +-- Create ApplicationContext, run initializers
       +-- RunListener.contextPrepared(...)
       |     +-- ApplicationContextInitializedEvent
       |
       +-- Load initial bean definition sources
       +-- RunListener.contextLoaded(...)
       |     +-- ApplicationPreparedEvent
       |
       +-- refresh ApplicationContext
       |     +-- process configuration, DI, create non-lazy singletons
       |     +-- ContextRefreshedEvent (Spring Framework)
       |
       +-- RunListener.started(...)
       |     +-- ApplicationStartedEvent
       |     +-- LivenessState.CORRECT
       |
       +-- Invoke ApplicationRunner / CommandLineRunner
       |
       +-- RunListener.ready(...)
       |     +-- ApplicationReadyEvent
       |     +-- ReadinessState.ACCEPTING_TRAFFIC
       |
       +-- SpringApplication.run(...) returns ApplicationContext
```

At each milestone, **a run listener callback and a Boot-published event are two views of the same phase**. By default, Spring Boot has `EventPublishingRunListener` bridging them to publish application events. Do not infer that every custom `RunListener` always runs before or after every `ApplicationListener` at the same milestone: exact ordering across listeners depends on sorting and registration mechanisms.

If startup fails, Boot invokes `SpringApplicationRunListener.failed(context, exception)` and publishes `ApplicationFailedEvent` while running the failure-handling flow. `context` may be `null` if the failure occurs before context creation. A startup failing before runners will not produce a successful `ApplicationReadyEvent`.

Milestones to remember:

- **`ApplicationStartingEvent`**: before `Environment` and `ApplicationContext` are ready.
- **`ApplicationEnvironmentPreparedEvent`**: `Environment` prepared, context not created yet.
- **`ApplicationContextInitializedEvent`**: context has passed initializers, before loading primary bean definitions.
- **`ApplicationPreparedEvent`**: initial bean definition sources loaded, before refresh.
- **`ApplicationStartedEvent`**: after refresh, before calling runners.
- **`ApplicationReadyEvent`**: after runners have been called.
- Additionally, there are Spring Framework events such as `ContextRefreshedEvent`, and availability change events.

Therefore, you must never describe a runner as "running before context creation", or interpret `ApplicationStartedEvent` as meaning all runners have finished.

## 4. SpringApplicationRunListener: startup-sequence hook

### 4.1. Contract and meaning

`org.springframework.boot.SpringApplicationRunListener` is an interface discovered by Spring Boot via `SpringFactoriesLoader`. **Each `SpringApplication.run(...)` call receives a new instance** per Boot's instantiation mechanism. In Boot 3.3, implementations are loaded through `META-INF/spring.factories` and require a public constructor with **two parameters `(SpringApplication, String[])`**.

Callbacks (`default` methods, so you only need to override needed milestones):

| Callback | Timing |
| --- | --- |
| `starting(ConfigurableBootstrapContext)` | Right when `run()` begins; complete `Environment` does not exist yet |
| `environmentPrepared(ConfigurableBootstrapContext, ConfigurableEnvironment)` | `Environment` prepared, before creating context |
| `contextPrepared(ConfigurableApplicationContext)` | Context created, prepared, and initializers run; initial config sources not loaded yet |
| `contextLoaded(ConfigurableApplicationContext)` | Sources loaded into context, before refresh |
| `started(ConfigurableApplicationContext, Duration)` | Context refreshed, runners not called yet |
| `ready(ConfigurableApplicationContext, Duration)` | Runners have been called; `run()` is about to finish |
| `failed(ConfigurableApplicationContext, Throwable)` | `run()` failed; context may be `null` |

`Duration timeTaken` in `started` and `ready` may be `null` on certain call paths. If using it to record metrics, handle the absent case; do not assume every startup always provides a measured duration.

### 4.2. How to register

File **`src/main/resources/META-INF/spring.factories`**:

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
```

The key here is **`org.springframework.boot.SpringApplicationRunListener`**, not `org.springframework.context.ApplicationListener`. Merely adding `@Component` to `TraceRunListener` is not how this SPI is registered. `SpringApplication.addListeners(...)` also takes `ApplicationListener`, **not `SpringApplicationRunListener`**.

**Do not confuse `spring.factories` with `AutoConfiguration.imports`.** In Boot 3, auto-configuration class declarations use `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; that serves a different purpose from registering `SpringApplicationRunListener`.

### 4.3. Important characteristics

- RunListeners are instantiated **before normal service beans are ready**; their constructors are not constructor-injection points for Spring application beans.
- Very early callbacks must not call `context.getBean(...)`, because the context may not exist or may not have refreshed yet.
- The failure callback must work when `context == null`.
- Do not perform heavy I/O or long-running business work inside this SPI because it can block startup.
- When you need to track multiple bootstrap milestones uniformly inside a foundational library, RunListener fits better than scattered runners.

## 5. ApplicationListener: listening to events

### 5.1. Contract

A listener typically implements the generic interface:

```java
public final class StartingOnlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("ApplicationStartingEvent observed");
    }
}
```

**This is an illustrative snippet inside a Spring project**, requiring imports for `org.springframework.context.ApplicationListener` and `org.springframework.boot.context.event.ApplicationStartingEvent`. The generic parameter specifies the event the listener cares about.

If you need to listen to multiple Boot event types, you can implement `ApplicationListener<SpringApplicationEvent>` and use `instanceof` to branch. For custom business events, you can also use an `@EventListener` bean or an `ApplicationListener` for that event type.

### 5.2. Early registration vs. bean registration

**Approach 1 — register before `run()`:**

```java
SpringApplication app = new SpringApplication(App.class);
app.addListeners(new StartingOnlyListener());
app.run(args);
```

`App` is a hypothetical main class. This approach can receive `ApplicationStartingEvent` before the context is created.

**Approach 2 — auto-register via `spring.factories`:**

```properties
org.springframework.context.ApplicationListener=com.example.lifecycle.StartingOnlyListener
```

The listener is loaded through classpath configuration when `SpringApplication` starts, so it can catch early events when implemented appropriately. Classes instantiated during bootstrap must not depend on DI of application beans.

**Approach 3 — as a Spring bean:**

```java
@Component
class ReadyAudit {
    @EventListener
    void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready event received");
    }
}
```

The snippet above requires importing `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, and `org.springframework.boot.context.event.ApplicationReadyEvent`; this is a bean example inside a Spring application. It fits events **after beans have been created**, and can use constructor injection to receive services.

**Key limitation:** a listener existing solely as a `@Bean`, `@Component`, or `@EventListener` will not retroactively receive ultra-early events that fired before the bean was created. To receive `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`, register before `run` or via an appropriate bootstrap mechanism.

### 5.3. Ordering, errors, and multiple contexts

- When multiple listeners exist, `@Order` or `Ordered` can be used when processing order within the same event truly matters.
- Event listeners are usually invoked synchronously on the event-publishing thread by default; a listener doing heavy work or throwing exceptions can slow down or break startup.
- With an application context hierarchy, events in a child context may be propagated to the parent; a listener may observe multiple events of the same type. To distinguish them, compare the source context in the event with the context the listener belongs to.
- `ApplicationListener` has no mechanism to replay past events fired before it was registered.

## 6. ApplicationRunner and CommandLineRunner: running work after refresh

### 6.1. Contract

Both interfaces live in `org.springframework.boot` and each defines a single `run` method:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

The two signatures above show **the method contract**, not redefinitions of library interfaces in application source code.

The biggest difference is the input data type:

- `ApplicationRunner` receives `ApplicationArguments`: separates options like `--mode=demo` from non-option arguments, letting you call `containsOption("mode")`, `getOptionValues("mode")`, `getNonOptionArgs()`, and `getSourceArgs()`.
- `CommandLineRunner` receives the raw CLI string array (`String...`), so if you want option parsing you must parse it yourself or use another mechanism.

Runners are **Spring beans** (registered via `@Component` or `@Bean`). They run **after context refresh**. They can constructor-inject services/repositories for warm-up, health validation, or clearly bounded initialization tasks.

If multiple runners exist, use `@Order` or `Ordered`; Boot sorts `ApplicationRunner` and `CommandLineRunner` in order before invoking them. Do not rely on default classpath scanning order.

### 6.2. Do runners execute after ApplicationReadyEvent?

**No.** The normal sequence is:

```text
refresh context
  -> ApplicationStartedEvent
  -> ApplicationRunner / CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
```

Therefore, if a runner throws an exception, startup enters the failure branch and a successful `ApplicationReadyEvent` will not be published. This is why runners suit tasks that **must complete before the application is considered ready**.

Nor is a runner a scheduler: Boot invokes it during the startup lifecycle, not periodically or on every HTTP request. For scheduled jobs, use a proper scheduler/job framework.

## 7. Complete example: one application using all three types

The following application uses **Java 21**, **Spring Boot 3.3.13**, and Maven. It does not start an HTTP server, making it easy to focus on startup observation. The example demonstrates:

- A RunListener loaded from `spring.factories`.
- An ApplicationListener registered directly on `SpringApplication` before `run(args)`.
- `ApplicationRunner` and `CommandLineRunner` as two `@Component` beans with explicit ordering.
- Log lines showing runners executing **after started** and **before ready**.

### 7.1. Project structure

```text
lifecycle-hooks-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/lifecycle/
        │   ├── LifecycleDemoApplication.java
        │   ├── TraceRunListener.java
        │   ├── TraceApplicationEvents.java
        │   ├── StructuredArgsRunner.java
        │   └── RawArgsRunner.java
        └── resources/META-INF/
            └── spring.factories
```

### 7.2. Maven

**File `pom.xml`:**

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

    <groupId>com.example</groupId>
    <artifactId>lifecycle-hooks-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` provides the core startup components; `spring-boot-starter-web` is not needed. Using `java.version` 21 aligns with the runtime JDK.

### 7.3. RunListener implementing all callbacks

**File `src/main/java/com/example/lifecycle/TraceRunListener.java`:**

```java
package com.example.lifecycle;

import java.time.Duration;

import org.springframework.boot.ConfigurableBootstrapContext;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringApplicationRunListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

public final class TraceRunListener implements SpringApplicationRunListener {

    // SpringFactoriesLoader requires a public constructor with this exact signature.
    public TraceRunListener(SpringApplication application, String[] args) {
    }

    @Override
    public void starting(ConfigurableBootstrapContext bootstrapContext) {
        System.out.println("RUN starting");
    }

    @Override
    public void environmentPrepared(
            ConfigurableBootstrapContext bootstrapContext,
            ConfigurableEnvironment environment) {
        System.out.println("RUN environmentPrepared");
    }

    @Override
    public void contextPrepared(ConfigurableApplicationContext context) {
        System.out.println("RUN contextPrepared");
    }

    @Override
    public void contextLoaded(ConfigurableApplicationContext context) {
        System.out.println("RUN contextLoaded");
    }

    @Override
    public void started(ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN started");
    }

    @Override
    public void ready(ConfigurableApplicationContext context, Duration timeTaken) {
        System.out.println("RUN ready");
    }

    @Override
    public void failed(ConfigurableApplicationContext context, Throwable exception) {
        System.err.println("RUN failed: " + exception.getClass().getSimpleName());
    }
}
```

**File `src/main/resources/META-INF/spring.factories`:**

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
```

The constructor is required even though the demo does not use the two parameters. This is a Boot SPI, **not a Spring bean needing `@Component`**. Callbacks `starting` through `ready` run in their respective phases; `failed` is invoked only on the failure path.

### 7.4. ApplicationListener receiving bootstrap events

**File `src/main/java/com/example/lifecycle/TraceApplicationEvents.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.boot.context.event.SpringApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class TraceApplicationEvents
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        if (event instanceof ApplicationStartingEvent) {
            System.out.println("EVENT starting");
        }
        else if (event instanceof ApplicationEnvironmentPreparedEvent) {
            System.out.println("EVENT environmentPrepared");
        }
        else if (event instanceof ApplicationStartedEvent) {
            System.out.println("EVENT started");
        }
        else if (event instanceof ApplicationReadyEvent) {
            System.out.println("EVENT ready");
        }
        else if (event instanceof ApplicationFailedEvent) {
            System.err.println("EVENT failed");
        }
    }
}
```

This listener receives `SpringApplicationEvent` instances and selects a few types to print. It **does not print all events**; for example, `ApplicationContextInitializedEvent` or `ApplicationPreparedEvent` are still sent, yet the demo filters them out by condition. `AvailabilityChangeEvent` is a separate event type; do not assume not printing availability means no liveness/readiness change occurred.

### 7.5. Two runners to compare arguments

**File `src/main/java/com/example/lifecycle/StructuredArgsRunner.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public final class StructuredArgsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("APP RUNNER mode=" + args.getOptionValues("mode")
                + "; free=" + args.getNonOptionArgs());
    }
}
```

**File `src/main/java/com/example/lifecycle/RawArgsRunner.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public final class RawArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("CLI RUNNER args=" + String.join("|", args));
    }
}
```

`@Order(10)` and `@Order(20)` give the runners a predictable order: `StructuredArgsRunner` runs before `RawArgsRunner`. `@Order` **does not alter** when Boot fires `ApplicationStartedEvent` or `ApplicationReadyEvent`.

### 7.6. Main class registering ApplicationListener before running

**File `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // ApplicationListener registered before run to receive very early events.
        application.addListeners(new TraceApplicationEvents());

        // TraceRunListener is discovered by Boot via META-INF/spring.factories.
        application.run(args);
    }
}
```

When running `main`, there is no need to call `new TraceRunListener(...)` or add `@Component` to that class. Boot discovers the RunListener via `spring.factories`, while `TraceApplicationEvents` is added directly to `SpringApplication`. The two runners are discovered by component scanning and invoked after refresh.

### 7.7. Running and verifying output

Prerequisites: JDK 21, Maven, and accessible dependencies.

```bash
java -version
mvn -version
mvn package
java -jar target/lifecycle-hooks-demo-0.0.1-SNAPSHOT.jar --mode=demo alpha beta
```

`mvn package` creates an executable JAR packaged by Boot's plugin. `--mode=demo` is an **option**, while `alpha` and `beta` are **non-option arguments**.

The lines from the two runners must appear exactly as follows:

```text
APP RUNNER mode=[demo]; free=[alpha, beta]
CLI RUNNER args=--mode=demo|alpha|beta
```

For the RunListener, the following lines appear in relative order:

```text
RUN starting
RUN environmentPrepared
RUN contextPrepared
RUN contextLoaded
RUN started
RUN ready
```

For the selected ApplicationListener, the following lines appear in relative order:

```text
EVENT starting
EVENT environmentPrepared
EVENT started
EVENT ready
```

**Do not merge the three blocks above into a single stdout stream grouped by block.** Spring Boot logs may interleave; and `RUN` vs `EVENT` lines from the same phase may interleave. Two relationships that must be verified are:

- Both `RUN started` and `EVENT started` belong to the stage **before** the two runners.
- Both `RUN ready` and `EVENT ready` belong to the stage **after** the two runners.
- The two runners follow `APP RUNNER` then `CLI RUNNER` due to `@Order`.

If running the application **without `--mode`**, `getOptionValues("mode")` may return `null`; the example simply prints the value so it does not throw, yet production code must check the option before using it.

## 8. Variation experiment: using an @EventListener bean

To observe the difference with a Spring-managed listener, you can add the following bean in package `com.example.lifecycle`:

**Additional file `ReadyBeanListener.java`:**

```java
package com.example.lifecycle;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public final class ReadyBeanListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("BEAN EVENT ready");
    }
}
```

This bean can receive `ApplicationReadyEvent` because the container has refreshed and created the listener bean before the ready milestone. If you change the parameter to `ApplicationStartingEvent`, **you cannot expect** it to receive the initial event: the bean does not exist yet at that time.

A listener bean can use constructor injection and interact with available services, though long-running work should still be avoided in default callbacks. If a task must finish before ready, a runner usually expresses that intent more clearly.

## 9. Choosing by scenario

| Practical requirement | Should use | Explanation |
| --- | --- | --- |
| Record `run()` milestones from ultra-early through completion to measure framework startup | `SpringApplicationRunListener` | Invoked along bootstrap callbacks |
| Integration library needing to observe when `Environment` is ready before context | `SpringApplicationRunListener.environmentPrepared` or early `ApplicationListener` | Both can run before beans exist |
| Simply logging `ApplicationReadyEvent` | `@EventListener` bean or `ApplicationListener<ApplicationReadyEvent>` | No low-level SPI needed |
| Logging `ApplicationFailedEvent` even for very early errors | `ApplicationListener` registered before `run`, or RunListener `failed` | Context may not exist yet |
| Reading CLI option `--mode=sync` and injecting services | `ApplicationRunner` | Receives parsed `ApplicationArguments` |
| Receiving raw argument strings and injecting services | `CommandLineRunner` | Receives `String... args` |
| Seeding data before the app accepts traffic | Appropriate runner, controlled and idempotent | Runs before ready |
| Running scheduled recurring tasks | Scheduler/job framework | None of the three hooks above is a scheduler |
| Handling domain events after the app is running | `ApplicationListener` bean/`@EventListener` | Events can fire repeatedly at runtime |
| Changing `Environment` config very early | `EnvironmentPostProcessor` or appropriate bootstrap hook | This is early configuration, not a runner responsibility |

**Decision example:** if you need to call a service after DI, read a customer list, and warm up a cache before accepting requests, choose `ApplicationRunner`. If you want to report that the application is ready, choose `ApplicationReadyEvent`. If building a starter that must instrument `SpringApplication`'s `contextPrepared` and `contextLoaded` milestones across many projects, consider `SpringApplicationRunListener`.

## 10. Common mistakes and fixes

### 10.1. Registering RunListener with @Component

**Wrong approach:** adding `@Component` to a class implementing `SpringApplicationRunListener` and expecting Boot to call `starting(...)`.

**Why it fails:** Spring Boot discovers the RunListener SPI via `SpringFactoriesLoader`, before processing Spring beans.

**Right approach:** create a public `(SpringApplication, String[])` constructor, declare it in `META-INF/spring.factories` under key `org.springframework.boot.SpringApplicationRunListener`, and package the resource on the classpath.

### 10.2. Confusing spring.factories keys

The two lines below have **two different meanings**:

```properties
org.springframework.boot.SpringApplicationRunListener=com.example.lifecycle.TraceRunListener
org.springframework.context.ApplicationListener=com.example.lifecycle.TraceApplicationEvents
```

Use the second line if you want to **auto-register** `TraceApplicationEvents` early via metadata instead of `application.addListeners(...)`. Do not use both registration mechanisms **for the same listener** without reason, or you may observe duplicate callbacks. Never replace Boot's default `EventPublishingRunListener`.

### 10.3. ApplicationListener misses very early events

**Symptom:** `@EventListener(ApplicationStartingEvent.class)` on a bean does not run.

**Cause:** `ApplicationStartingEvent` fires before Spring creates the context and listener beans.

**Fix:** instantiate the listener and register it via `SpringApplication.addListeners(...)` before `run(args)`, or via `spring.factories`.

### 10.4. Runner is never called

Check whether the bean is actually registered via `@Component`/`@Bean`, whether its package is within component scan, and whether startup passed the refresh step. If refresh failed, it is normal for runners not to be called. If you manually call `new MyRunner()` without registering it as a bean, Boot will not discover that object automatically.

### 10.5. Ordering results differ from expectations

Do not assume `ApplicationRunner` always runs before `CommandLineRunner` **merely because of interface names**. Use `@Order`/`Ordered` when deterministic order is needed. Between callbacks of the same phase like RunListener and ApplicationListener, avoid relying on log sequence without an explicit ordering contract.

### 10.6. Runner error prevents the app from becoming ready

If a runner's `run(...)` throws an exception, Boot handles it as a startup failure: logging the error, calling failure callbacks, and not publishing a successful `ApplicationReadyEvent`. For critical initialization tasks, define clearly when startup is allowed to fail; for optional tasks, handle errors/timeouts properly instead of causing restart loops.

### 10.7. Early callback calls getBean

`starting(...)` or `environmentPrepared(...)` runs when there is no `ApplicationContext` yet; even `contextPrepared(...)` is still before refresh. Do not use these callbacks to look up regular services, repositories, or transaction managers. When injected beans are needed, choose a runner or late event.

### 10.8. Event handling takes too long

Application event listeners run synchronously by default in many scenarios. A callback performing slow I/O can delay startup or request processing. Do not execute heavy tasks inside startup listeners; use runners with timeouts, or appropriate background/job systems when blocking readiness is not required.

### 10.9. Duplicate events seen in parent-child contexts

With an `ApplicationContext` hierarchy, events from a child context can propagate up to the parent, so a parent listener may receive multiple events of the same type. Inspect the source context on the event and filter as needed; never assume each event type occurs only once across the entire hierarchy.

## 11. Questions and exercises

1. State the differences between `SpringApplicationRunListener`, `ApplicationListener<E>`, and `ApplicationRunner`: what invokes them, when, and what data do they receive?
2. Why does `TraceRunListener` need the `(SpringApplication, String[])` constructor even without using DI?
3. If you remove `META-INF/spring.factories`, do the `RUN ...` lines in the example still appear? Why?
4. Why can a listener added via `addListeners(...)` catch `ApplicationStartingEvent`, whereas a listener with only `@Component` usually cannot?
5. State the order of `ApplicationStartedEvent`, `StructuredArgsRunner`, `RawArgsRunner`, and `ApplicationReadyEvent`.
6. Run the application with `--mode=demo alpha beta`. Compare how `ApplicationRunner` and `CommandLineRunner` see the arguments.
7. Swap `@Order` between the two runners. Observe the order change; check whether `started` and `ready` events shift relative to the runners.
8. Add `ApplicationPreparedEvent` to `TraceApplicationEvents` and print the event name; determine whether it occurs before or after `refresh`.
9. Have `RawArgsRunner` throw `IllegalStateException("demo failure")`. Predict `RUN failed`, `EVENT failed`, and why there is no successful `ready`.
10. If you need to use a `DataSource` bean to validate initial data, should the logic go in RunListener `environmentPrepared`, `ApplicationListener<ApplicationStartingEvent>`, or `ApplicationRunner`? Explain.
11. If you need to observe application events published by business logic **after the application is ready**, does using RunListener make sense?
12. Explain why a runner's `@Order` cannot make `ApplicationReadyEvent` fire before `ApplicationStartedEvent`.

**Self-assessment criteria:** you meet expectations when you can run the example with Maven/JDK 21, recognize `RUN` as SPI callbacks, `EVENT` as event notifications, `APP RUNNER` and `CLI RUNNER` as bean-driven work, and explain the difference between **refreshed**, **runners invoked**, and **ready**.

## 12. Official documentation

- Spring Boot 3.3.13 — `SpringApplicationRunListener` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot 3.3.13 — `SpringApplication` and Application Events: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — `ApplicationRunner` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3.13 — `CommandLineRunner` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Framework 6.1 — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
