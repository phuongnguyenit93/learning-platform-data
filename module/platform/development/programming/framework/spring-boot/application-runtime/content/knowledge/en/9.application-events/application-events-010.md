# ApplicationReadyEvent After Runners Complete — Spring Boot 3.3

## 1. Lesson Objectives

`ApplicationReadyEvent` is a major milestone in the **Spring Boot application startup lifecycle**. Spring Boot emits this event **very late during `SpringApplication.run(...)`**, after the `ApplicationContext` has refreshed and **after Boot has finished calling all `ApplicationRunner` and `CommandLineRunner` beans** along the successful startup path.

After this lesson, you should be able to:

1. Accurately describe the position of `ApplicationReadyEvent` relative to `ApplicationStartedEvent`, `ApplicationRunner`, `CommandLineRunner`, and `ApplicationFailedEvent`.
2. Register listeners using `@EventListener` or `ApplicationListener<ApplicationReadyEvent>`.
3. Understand what "runners completed" means, especially when a runner only **kicks off asynchronous work** and returns.
4. Choose the right callback for mandatory startup tasks, post-startup notifications, and readiness/liveness.
5. Run a Java 21 + Spring Boot 3.3 example and explain its output, including the case where a runner throws an exception.

**Key message:** `ApplicationReadyEvent` occurs **after runner `run(...)` callbacks finish normally**, yet it does not automatically prove that all background tasks, external connections, message consumers, or dependent services are truly ready.

## 2. Position in the Startup Sequence

A **successful** Spring Boot 3.3 startup follows this conceptual flow:

```text
main(String[] args)
   |
   +-- SpringApplication.run(args)
         |
         +-- ApplicationStartingEvent
         +-- Prepare Environment
         +-- ApplicationEnvironmentPreparedEvent
         +-- Create ApplicationContext, run initializers
         +-- ApplicationContextInitializedEvent
         +-- Load primary sources/bean definitions
         +-- ApplicationPreparedEvent
         |
         +-- refresh ApplicationContext
         |     +-- Process configuration and bean definitions
         |     +-- Instantiate/inject standard non-lazy singletons
         |     +-- Start web server if present
         |
         +-- ApplicationStartedEvent
         +-- AvailabilityChangeEvent(LivenessState.CORRECT)
         |
         +-- ApplicationRunner.run(ApplicationArguments)
         +-- CommandLineRunner.run(String... args)
         |     +-- All runners sorted in appropriate order
         |     +-- Exit normally without throwing exceptions
         |
         +-- ApplicationReadyEvent                 <-- lesson focus
         +-- AvailabilityChangeEvent(
         |       ReadinessState.ACCEPTING_TRAFFIC)
         |
         +-- run(...) returns ApplicationContext
```

The diagram omits internal callbacks, context-specific behaviors, and secondary events. Points to distinguish:

- **`ContextRefreshedEvent`** is a Spring Framework event occurring when the context refreshes; it is **not** the milestone where runners complete.
- **`ApplicationStartedEvent`** is emitted by Boot **after refresh but before runners**. The word "Started" does not mean all startup tasks have finished.
- **`ApplicationReadyEvent`** is emitted by Boot **after runners have executed and returned**. It is the near-final milestone Boot uses to announce the application is ready.
- **`ReadinessState.ACCEPTING_TRAFFIC`** is published **after** `ApplicationReadyEvent` in the standard flow. Do not confuse `ApplicationReadyEvent` with the availability event; reading readiness **inside** a ready listener may still observe the state prior to Boot publishing accepting traffic.
- **`ApplicationFailedEvent`** belongs to the failed startup path. If a runner throws an exception, the success flow never reaches `ApplicationReadyEvent`.

### 2.1. Four Easily Confused Milestones

| Milestone | Context refreshed? | Runners completed? | Meaning |
| --- | --- | --- | --- |
| `ApplicationPreparedEvent` | No | No | Initial sources loaded, about to refresh |
| `ApplicationStartedEvent` | Yes | No | Refresh succeeded; about to invoke runners |
| `ApplicationReadyEvent` | Yes | Yes, meaning runner callbacks returned normally | Signals the startup phase is nearly complete |
| `ReadinessState.ACCEPTING_TRAFFIC` | Yes | Yes | Boot announces readiness state accepting traffic |

The most important distinction is **`Started` → `runners` → `Ready`**, not `Started` and `Ready` simultaneously.

## 3. Where Do ApplicationRunner and CommandLineRunner Run?

Spring Boot looks up beans implementing either of two interfaces:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

These are **illustrative contract signatures**; do not copy them as custom application-defined interfaces. Both are real interfaces in the `org.springframework.boot` package.

- **`ApplicationRunner`** receives `ApplicationArguments` for structured argument inspection: `containsOption`, `getOptionValues`, `getNonOptionArgs`, `getSourceArgs`.
- **`CommandLineRunner`** directly receives raw command-line strings as `String... args`.
- Both runner types are **Spring beans**: registered via `@Component`, `@Bean`, or any valid bean registration mechanism. They can inject services and repositories because the context has already refreshed.
- When multiple runners exist, Spring Boot uses ordering semantics (`@Order` or `Ordered`) to determine **`run(...)` invocation order**. `@Order` does not say every runner/bean's constructor runs in that same order.
- There is no rule that "all ApplicationRunners run before all CommandLineRunners"; execution order across mixed runners is determined by Boot's ordering mechanism.

**A runner is considered complete as soon as its `run(...)` method returns normally.** If it launches a thread, `CompletableFuture`, `@Async` method, or enqueues a message and returns, Boot does not automatically wait for that background work to finish. That directly affects how `ApplicationReadyEvent` should be interpreted.

## 4. What Is ApplicationReadyEvent?

`org.springframework.boot.context.event.ApplicationReadyEvent` is a `SpringApplicationEvent`. It is published near the end of startup to indicate the application has completed the steps managed by `SpringApplication` and is ready to process work under Boot's contract.

Commonly used APIs:

- **`getApplicationContext()`**: returns the `ConfigurableApplicationContext` of the startup run.
- **`getSpringApplication()`**: the `SpringApplication` instance that emitted the event, via the `SpringApplicationEvent` superclass.
- **`getArgs()`**: the source argument array used at startup, via the superclass.
- **`getTimeTaken()`**: duration measured for the startup process when available; may be `null`, so check before using.

**Do not use `getTimeTaken()` as an SLA for the entire external system.** It reflects the startup duration measured by Boot across the startup lifecycle, not necessarily background processes that continue running.

A listener receiving the ready event is a suitable place to:

- Log or publish a metric for startup completion time.
- Notify observability systems that a new instance reached the ready milestone.
- Trigger a task that **is not required to finish before readiness**, provided it is designed not to block startup and handles errors properly.

Conversely, if you must **validate configuration, migrate data, or populate mandatory caches** before the system is considered ready, place that work in a runner or a startup/lifecycle mechanism designed for that purpose, rather than starting it only after ready fires.

## 5. Registering a Listener for ApplicationReadyEvent

### 5.1. Using @EventListener in a Spring Bean

Example:

```java
@Component
public class ReadyObserver {

    @EventListener
    public void whenReady(ApplicationReadyEvent event) {
        System.out.println("ApplicationReadyEvent received");
    }
}
```

This snippet is **illustrative**, requiring imports for `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, and `org.springframework.boot.context.event.ApplicationReadyEvent`.

Once the context has refreshed, the `ReadyObserver` bean is managed by Spring and the `@EventListener` method can receive the event. For `ApplicationReadyEvent`, it is **not mandatory** to register the listener before context creation.

### 5.2. Implementing ApplicationListener

An alternative:

```java
@Component
public class ReadyApplicationListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready event from ApplicationListener");
    }
}
```

This snippet requires importing `org.springframework.context.ApplicationListener`, `org.springframework.stereotype.Component`, and `org.springframework.boot.context.event.ApplicationReadyEvent`.

This is also a **Spring bean listener**; in a standard app, it is registered when the container constructs beans. Constructor injection works just like any other bean.

**Choose only one style** for the same behavior to avoid duplicate logs or side effects. `@EventListener` and `ApplicationListener` both handle application events, differing only in how they are declared.

### 5.3. Is Direct Registration Before Run Needed?

You can call:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.addListeners(new ReadyApplicationListener());
application.run(args);
```

This is an **illustrative snippet**; an appropriate application class and listener are needed. This approach is necessary when catching ultra-early events like `ApplicationStartingEvent` or `ApplicationEnvironmentPreparedEvent`. For the ready event, registering **as a bean** is sufficient because the event occurs only after refresh.

Do not both annotate the same listener with `@Component` and add an instance of it via `addListeners(...)`: that creates two objects or registration paths, causing unintended duplicate callbacks.

### 5.4. @EventListener and @TransactionalEventListener

`ApplicationReadyEvent` does not inherently execute inside an active transaction. `@TransactionalEventListener` binds callbacks to transaction phases by default; using it merely to catch application ready may prevent the listener from running when no transaction is active.

If the goal is simply tracking startup, a regular **`@EventListener`** is appropriate. Transactional listeners should be reserved for business events genuinely tied to transaction commit/rollback lifecycles.

## 6. Complete Example — Java 21 and Spring Boot 3.3.13

The following program uses a **non-web application** so output focuses on the startup lifecycle without needing a database, controller, or HTTP port.

It includes:

1. A listener printing the `ApplicationStartedEvent` and `ApplicationReadyEvent` milestones.
2. An `ApplicationRunner` ordered first, which can intentionally fail to test the failure branch.
3. A `CommandLineRunner` ordered second.
4. A main class creating and running `SpringApplication`.

### 6.1. Directory Structure

```text
ready-event-demo/
├── pom.xml
└── src/main/java/com/example/ready/
    ├── ReadyEventApplication.java
    ├── FirstRunner.java
    ├── SecondRunner.java
    └── StartupEvents.java
```

### 6.2. pom.xml

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
    <artifactId>ready-event-demo</artifactId>
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

Spring Boot 3.3 supports Java 21; the parent POM manages dependency versions. The base starter suffices for a command-line example without `spring-boot-starter-web`.

### 6.3. Application Class

**File `src/main/java/com/example/ready/ReadyEventApplication.java`:**

```java
package com.example.ready;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReadyEventApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ReadyEventApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

`@SpringBootApplication` in `com.example.ready` enables component scanning to find runners and listeners in the same package. `WebApplicationType.NONE` keeps the app from opening an HTTP port.

### 6.4. ApplicationRunner Invoked First

**File `src/main/java/com/example/ready/FirstRunner.java`:**

```java
package com.example.ready;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class FirstRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RUNNER first");

        if (args.containsOption("fail-runner")) {
            throw new IllegalStateException("demo runner failed");
        }
    }
}
```

`ApplicationArguments.containsOption("fail-runner")` supports the `--fail-runner` flag. On the normal path, the method prints one line and returns. On the failure path, it throws `IllegalStateException`, preventing startup from **completing successfully**.

### 6.5. CommandLineRunner Invoked Second

**File `src/main/java/com/example/ready/SecondRunner.java`:**

```java
package com.example.ready;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class SecondRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("RUNNER second");
    }
}
```

`@Order(10)` and `@Order(20)` define the **invocation order of runners** in this example. Do not infer that those two annotations fix constructor execution order across all Spring beans.

### 6.6. Listener for Started and Ready

**File `src/main/java/com/example/ready/StartupEvents.java`:**

```java
package com.example.ready;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupEvents {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ready");
        System.out.println("CONTEXT active="
                + event.getApplicationContext().isActive());
    }
}
```

At `ApplicationStartedEvent`, Spring Boot has refreshed the context yet **has not called runners**. At `ApplicationReadyEvent`, both runners have returned normally. `event.getApplicationContext().isActive()` returns `true` on the example's normal startup path; this confirms the context is active, not that every external service is healthy.

### 6.7. Build and Run

Requires **JDK 21**, Maven, and dependencies downloadable from configured repositories.

```bash
java -version
mvn -version
mvn package
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar
```

The **lines explicitly printed by the program** in order are:

```text
EVENT started
RUNNER first
RUNNER second
EVENT ready
CONTEXT active=true
```

This is **not the entire stdout**: the console also shows the banner, Spring Boot logging, and environment-specific messages. Still, the order of the five lines printed by the program accurately reflects the lifecycle:

1. Once context refresh completes, `ApplicationStartedEvent` is emitted.
2. Boot calls the runner with `@Order(10)`.
3. Boot calls the runner with `@Order(20)`.
4. Once all runners return normally, Boot emits `ApplicationReadyEvent`.
5. The context remains active while the event is handled.

Non-web apps typically exit after startup if no non-daemon thread keeps the JVM alive; that **does not mean `ApplicationReadyEvent` was not emitted**.

### 6.8. Testing the Runner Failure Case

Run the same JAR with the flag:

```bash
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar --fail-runner
```

The lines printed by the program **before the error** include:

```text
EVENT started
RUNNER first
```

Then Boot's startup error stack trace/log appears; exact log details may vary. **None of** `RUNNER second`, `EVENT ready`, or `CONTEXT active=true` appear on this normal failure path, because the first runner throws an exception before Boot calls the next runner.

Spring Boot may publish `ApplicationFailedEvent` when handling the startup failure. Do not assume that simply refreshing the context guarantees the application reaches the ready milestone.

### 6.9. Measuring Startup Time from ApplicationReadyEvent

You can add the following logic inside `StartupEvents.onReady(...)`:

```java
java.time.Duration duration = event.getTimeTaken();
if (duration != null) {
    System.out.println("STARTUP durationMs=" + duration.toMillis());
}
```

This is an **additional snippet inside the listener method**, not a standalone program. The millisecond count depends on hardware, CPU load, classpath, and runtime environment, so no fixed stdout number is given for this line.

`getTimeTaken()` reflects Boot's measured startup duration; if a runner merely hands work off to a background worker and returns, this value does not cover the background worker's full completion time.

## 7. When Runners Have Async Work: Understanding "Completion" Properly

One of the most common architectural mistakes is assuming that returning from `run(...)` means all business initialization is complete.

**Error-illustrating** example:

```java
@Component
public class BadWarmup implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        CompletableFuture.runAsync(() -> {
            // Example: loading a large cache over the network.
            warmUpCache();
        });
    }

    private void warmUpCache() {
        // Illustration: logic to implement in a real application.
    }
}
```

The snippet above is **illustrative code**, requiring imports for `CompletableFuture`, `ApplicationRunner`, `ApplicationArguments`, and `@Component`. The `run` callback returns immediately after scheduling the `CompletableFuture`; it **does not wait** for `warmUpCache()` to finish. Thus Boot can publish `ApplicationReadyEvent` while the cache is still loading.

### 7.1. If Work Must Finish Before Ready

Execute synchronously or await the task with a timeout, explicit interruption handling, and exception propagation. Illustrative example:

```java
@Component
public class RequiredWarmup implements ApplicationRunner {

    private final CacheService cacheService;

    public RequiredWarmup(CacheService cacheService) {
        this.cacheService = cacheService;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        cacheService.warmUpBlocking();
    }
}
```

This is an **architectural pattern, not a standalone program**: `CacheService` and corresponding imports are required. `warmUpBlocking()` must genuinely wait for completion or throw an error; if it merely spawns a background task, the contract is violated. For external I/O, configure timeouts, bounded retries, cleanup, and startup-failure policies.

Some tasks should not be shoved arbitrarily into runners: database schema migrations belong in Flyway/Liquibase; coordinating start/stop for message consumers may fit `SmartLifecycle`; periodic jobs belong in a scheduler or job framework. What matters is ensuring **readiness reflects the application's actual serving conditions**, not merely that a bootstrap event fired.

### 7.2. If Work Is Not Mandatory Before Accepting Traffic

It can happen after ready, yet should not block a synchronous event listener for too long. Consider a managed executor or job queue with lifecycle management, logging, metrics, and shutdown behavior. When using `@Async` or `CompletableFuture`, handle errors and completion tracking explicitly: Boot does not wait for such tasks merely because they were started inside a listener.

Do not call an untimed `CompletableFuture.join()` on the startup thread against an unreliable network dependency. Indefinite blocking prevents the application from ever completing startup.

## 8. Ready Event and Availability/Readiness

Spring Boot defines availability states:

- **`LivenessState`**: whether the application is healthy enough to continue operating or is in a broken state requiring intervention.
- **`ReadinessState`**: whether the application is **ready to accept traffic** or temporarily refusing it to finish startup or adjust state.

On the normal path, Boot publishes `LivenessState.CORRECT` after `ApplicationStartedEvent` and `ReadinessState.ACCEPTING_TRAFFIC` after `ApplicationReadyEvent`.

**Subtle point:** `ApplicationReadyEvent` and `ReadinessState.ACCEPTING_TRAFFIC` are not the same event. While a ready listener is executing, Boot may **not yet have published** the accepting-traffic readiness state because that publication follows the ready event in the lifecycle callback.

If you need to react at the exact moment readiness state changes, listen for `AvailabilityChangeEvent` with `ReadinessState`, or use the availability API instead of equating the two events. For services needing HTTP/Kubernetes readiness, consider Spring Boot Actuator and readiness probes configured for your deployment environment.

### 8.1. ApplicationReadyEvent Does Not Verify External Systems

An application can emit the ready event while:

- A cache is still only being populated by a background task.
- A connection pool to an external API has just initialized without executing a real test request.
- A message consumer is still waiting on partition assignment or a broker.
- An external service changed state right after app startup.

Consequently, production readiness may require health indicators, checks, and dedicated lifecycle coordination. Do not take receiving a single event as proof that all external dependencies are permanently healthy.

### 8.2. Ready Event Is Not a Periodic Event

`ApplicationReadyEvent` is part of **each successful `SpringApplication` startup**. It does not re-fire on every HTTP request, health check, or network reconnect. If an application runs multiple application contexts or independent startups in tests, multiple corresponding events may be observed; do not assume strictly one event per JVM across every topology.

## 9. Synchronicity, Listener Errors, and @Order

### 9.1. Default Listeners Are Usually Synchronous

With the default multicaster, application event listeners usually execute **synchronously** on the event-publishing thread. Thus if `@EventListener(ApplicationReadyEvent.class)` performs slow I/O or throws an exception, it can delay or affect startup outcome. A ready listener is **not** the right place for an infinite loop or untimed API calls.

If the event multicaster is configured with an asynchronous executor, callbacks may not finish before Spring Boot proceeds through startup. Do not rely on the completion order of asynchronous listeners to determine readiness.

### 9.2. @Order Does Not Reverse Started and Ready

You can apply `@Order` to runners to control the invocation order of runner beans. For multiple listeners handling the ready event, ordering can affect callback order when supported by the event multicaster. However, `@Order` **never makes `ApplicationReadyEvent` fire before `ApplicationStartedEvent`**, nor does it run a runner before context refresh.

Event order is governed by the Spring Boot startup lifecycle; ordering among callbacks **for the same event type** is a separate concern.

### 9.3. Runner Errors vs. Ready Listener Errors

Distinguish:

- **Runner throws an exception**: Boot halts runner execution at the failure point; on the normal path, ready is not published.
- **Synchronous ready listener throws an exception**: the error can propagate out of event publishing, causing `run(...)` to be treated as a startup failure. Do not assume that once `ApplicationReadyEvent` is called, startup can no longer fail.
- **Async ready listener throws an exception**: outcome depends on the executor and async error handler. Errors must be observed, logged, and managed separately; do not assume they will fail startup.
- **Runner catches and swallows an exception**: Boot may proceed and emit ready even though initialization failed. For essential tasks, surface failures via explicit exceptions.

### 9.4. Need an Event Catching Ultra-Early Errors?

An `@EventListener(ApplicationFailedEvent.class)` bean may not even exist if startup fails **before context creation finishes**. To observe errors across early bootstrap phases too, register `ApplicationListener<ApplicationFailedEvent>` **before `SpringApplication.run(...)`** or through an appropriate bootstrap mechanism. This is an important difference from `ApplicationReadyEvent`, which occurs late enough for bean listeners to receive it.

## 10. Testing ApplicationReadyEvent Timing

### 10.1. Testing with a Real Executable Program

You can use these two commands to verify the success and failure branches:

```bash
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar
java -jar target/ready-event-demo-0.0.1-SNAPSHOT.jar --fail-runner
```

On the success flow, the line order must be `EVENT started` → `RUNNER first` → `RUNNER second` → `EVENT ready`. On the intentional failure branch, `EVENT ready` must not be printed.

When writing test automation, assert **the presence and relative order of specific markers** rather than matching entire Spring Boot logs (which vary by version, PID, timestamps, and log configuration).

### 10.2. Distinguishing Spring Context Tests from SpringApplication Startup Tests

`ApplicationReadyEvent` is tied to **the `SpringApplication.run(...)` sequence**. A test that merely creates an `AnnotationConfigApplicationContext` and calls `refresh()` does not automatically run `SpringApplication`'s sequence, runners, or emit Boot's ready event. To test real timing, boot through the corresponding Spring Boot test support or invoke a real `SpringApplication`.

When testing initialization tasks with side effects, design runners to be **idempotent** so test runs or restarts do not corrupt real data. Tasks can be disabled in a test profile via appropriate conditions, while ensuring timing tests keep at least one runner to observe the sequence.

### 10.3. Meaningful Assertions

- `ApplicationStartedEvent` appears **before** logs from runners.
- With explicitly ordered runners, the runner callback with the smaller order runs before the one with the larger order.
- `ApplicationReadyEvent` appears **after** all runners finish normally.
- If a runner throws, no `ApplicationReadyEvent` appears on the success path.
- If a runner starts an async task and returns, test the completion state **of the async task** separately rather than treating ready event emission as proof the task finished.

## 11. Common Errors and Resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Ready listener not called | Startup failed; runner threw; bean listener not scanned/registered | Check `ApplicationFailedEvent`, stack trace, component scan package, and registration |
| Saw `ApplicationStartedEvent` but no ready | Runner failed or post-refresh step blocked | Check runners, timeouts, exceptions, and startup logs |
| Ready event arrived while cache is still loading | Runner only scheduled async work and returned | If cache is critical, await completion in the runner with a timeout |
| `@EventListener` on class not invoked | Class is not a Spring bean or wrong method signature/import | Place class within component scan, register `@Bean`, or use `ApplicationListener` |
| `@Order` did not change ready milestone | It only orders callbacks/runners, not lifecycle phases | Rely on the started → runners → ready contract |
| Reading readiness inside ready listener shows not accepting yet | Boot publishes accepting readiness after the ready event | Listen to availability change events rather than assuming both milestones are one |
| Calling slow external API inside ready listener | Event handling may be synchronous and stall startup | Move mandatory work to a runner, or non-mandatory work to a managed async job |
| App reports ready even though a runner logged an error | Runner caught/swallowed the exception and returned | Clarify failure policy and throw exceptions when essential initialization fails |
| Testing `ApplicationReadyEvent` with plain context `refresh()` | Not using SpringApplication startup lifecycle | Boot with a Spring Boot integration test or `SpringApplication` |
| Ready event received multiple times | Multiple contexts/runs or duplicate listener registration | Inspect source context and registration paths |

**Investigation checklist:** (1) did `SpringApplication` run; (2) did the context finish refreshing; (3) which runner beans are registered; (4) runner order and exceptions; (5) is the listener a valid bean; (6) is the work synchronous or asynchronous; (7) does external dependency readiness have concrete health checks.

## 12. Practice Exercises

1. Redraw the timeline from `ApplicationPreparedEvent` to `ApplicationReadyEvent`. Mark where refresh completes and where runners sit.
2. Explain why `ApplicationStartedEvent` does **not** guarantee runners have executed.
3. In the example, why does `EVENT ready` appear after both `RUNNER first` and `RUNNER second`?
4. Change `@Order(10)` on `FirstRunner` to `@Order(30)` and predict the order of the two runner lines without altering started/ready order.
5. Run with `--fail-runner`. Why do `RUNNER second` and `EVENT ready` no longer appear?
6. Try adding a ready listener using `getTimeTaken()` with a `null` check, printing the measured duration without hardcoding a value.
7. If `FirstRunner` calls `CompletableFuture.runAsync(...)` and immediately returns, is data guaranteed to be ready at `ApplicationReadyEvent`? Propose two designs depending on how mandatory the task is.
8. Write an `@EventListener` accepting `ApplicationReadyEvent` and printing `getApplicationContext().isActive()`. What does this prove and what does it **not** prove?
9. Why is `@TransactionalEventListener` not the default choice for the ready event?
10. Compare the ready event with `ReadinessState.ACCEPTING_TRAFFIC`: which milestone is usually published later?
11. When do you need an `ApplicationListener<ApplicationFailedEvent>` registered before `run` instead of just an `@EventListener` on a bean?
12. Explain why missing the ready event in a plain `AnnotationConfigApplicationContext.refresh()` test does not mean a real Spring Boot application is broken.
13. Design a critical startup cache: if the cache server times out, should the app report ready? Where should the check and error handling live?
14. In a multi-context app or repeated `SpringApplication.run` calls, why should you not use a static variable assuming strictly one ready event across the JVM?

**Passing criteria:** run the Maven project, observe the exact order started → runner 1 → runner 2 → ready; understand that a throwing runner blocks ready on the success path, and do not confuse **runner callback returned** with **async task actually completed**.

## 13. Official Documentation

- Spring Boot 3.3 — SpringApplication, events, runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 API — ApplicationReadyEvent: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Boot 3.3 API — ApplicationRunner: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 API — CommandLineRunner: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot 3.3 — Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability
- Spring Framework — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
