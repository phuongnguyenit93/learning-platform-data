# ApplicationReadyEvent in Spring Boot Application Events

## 1. Concept and Purpose

`ApplicationReadyEvent` is a lifecycle event published by **Spring Boot** when the startup process via `SpringApplication` has reached the milestone of being ready to serve. This is a very late signal during startup: after the `ApplicationContext` is created and refreshed, after Boot publishes `ApplicationStartedEvent`, and **after `ApplicationRunner` / `CommandLineRunner` beans have been invoked and completed normally**.

Class name:

```java
org.springframework.boot.context.event.ApplicationReadyEvent
```

This class extends `SpringApplicationEvent`; it is not an event published by the application on every request. Spring Boot publishes it to signal the milestone of **completing startup successfully**, not for handling individual business operations.

For example, an order management system needs to initialize beans, read configuration, perform startup checks, and load essential data. Once mandatory startup steps are done, a listener wants to record startup duration metrics or schedule a non-critical post-startup task. `ApplicationReadyEvent` is the appropriate place to observe this milestone.

**Important limitation:** receiving the event does not automatically prove all external systems are healthy, no requests are failing, all background tasks have finished, or the application will stay ready forever. Those aspects must be evaluated with appropriate readiness/health checks and business mechanisms.

## 2. Where Does ApplicationReadyEvent Fit in the Startup Process?

Along a successful Spring Boot `SpringApplication.run(...)` sequence:

```text
SpringApplication.run(args)
          |
          +--> ApplicationStartingEvent
          |
          +--> ApplicationEnvironmentPreparedEvent
          |
          +--> ApplicationContextInitializedEvent
          |
          +--> ApplicationPreparedEvent
          |
          +--> Refresh ApplicationContext
          |      +--> ContextRefreshedEvent
          |      +--> WebServerInitializedEvent (if web server present)
          |
          +--> ApplicationStartedEvent
          |
          +--> AvailabilityChangeEvent(LivenessState.CORRECT)
          |
          +--> Run ApplicationRunner / CommandLineRunner
          |
          +--> ApplicationReadyEvent
          |
          +--> AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
          |
          +--> SpringApplication.run(...) completes
```

**Core order:** `ApplicationStartedEvent` → runners → `ApplicationReadyEvent` → readiness state `ACCEPTING_TRAFFIC`.

A few notes:

- `ApplicationStartedEvent` is published **after context refresh**, but **before** runners.
- `ApplicationRunner` and `CommandLineRunner` are invoked by Spring Boot after `ApplicationStartedEvent`. A runner can enforce mandatory startup conditions.
- `ApplicationReadyEvent` is published **after runners** on the successful startup path.
- Immediately afterward, Boot publishes `AvailabilityChangeEvent` with `ReadinessState.ACCEPTING_TRAFFIC` to announce readiness through the availability mechanism.
- If startup throws an exception before completing, Boot may publish `ApplicationFailedEvent`; do not expect a ready event for a failed run.
- For web applications, `WebServerInitializedEvent` concerns web server initialization and is **not identical** to all runners having completed.

The diagram shows the logical order of milestones; it does not guarantee every event type is received only once in systems with multiple contexts or listeners registered across multiple scopes.

### Comparing Easily Confused Events

| Event | Timing | Is It the Post-Runner Ready Milestone? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Spring Framework completes context refresh | No |
| `ApplicationStartedEvent` | Spring Boot refreshed context, before runners | No |
| `ApplicationReadyEvent` | Spring Boot finished running runners and is about to announce readiness | **Yes** |
| `AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)` | Boot announces the state allowing traffic, right after the ready event | This is a readiness state change |
| `ApplicationFailedEvent` | Error during startup | No, failure path |
| `ContextClosedEvent` | Context is closing | No, belongs to shutdown |

`ApplicationReadyEvent` is a **single startup milestone event**, whereas `ReadinessState` is a state that can continue changing multiple times while the application is running.

## 3. How to Register a Listener

### 3.1. `@EventListener` Method

```java
@Component
public class ReadyNotification {

    @EventListener
    public void afterStartup(ApplicationReadyEvent event) {
        System.out.println("Spring Boot reached ready milestone");
    }
}
```

This is an illustrative snippet meant for a Boot project with component scanning; imports for `@Component`, `@EventListener`, and `ApplicationReadyEvent` are needed. When the context manages the `ReadyNotification` bean, Spring discovers the event-receiving method by parameter type. You do not need to call this method manually from `main`.

If you do not use the event payload, you can declare `@EventListener(ApplicationReadyEvent.class)` on a no-parameter method:

```java
@EventListener(ApplicationReadyEvent.class)
public void announceReady() {
    // Record successful startup.
}
```

This is also an illustrative snippet, not a standalone program.

### 3.2. `ApplicationListener<ApplicationReadyEvent>` Interface

```java
@Component
public class ReadyObserver
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready: "
                + event.getApplicationContext().getId());
    }
}
```

Using the interface is valid if you want the event type visible in the class declaration. Register a listener through a single clear mechanism to avoid accidentally running twice.

### 3.3. Why Can a Spring Bean Listener Receive the Ready Event?

Very early Boot events, such as `ApplicationStartingEvent`, occur **before beans are created**, so you cannot rely solely on `@EventListener` on a bean to receive them. By contrast, `ApplicationReadyEvent` occurs after the context has been initialized. Therefore, a regular bean declared via `@Component` or `@Bean` is sufficient to receive the ready event.

When you need to listen to events **before context/beans exist**, register an early listener via `SpringApplication.addListeners(...)` or another Boot-supported mechanism; do not push that requirement into a ready listener unnecessarily.

## 4. ApplicationReadyEvent API

Commonly used methods:

| Method | Provided Value | Usage |
| --- | --- | --- |
| `getApplicationContext()` | `ConfigurableApplicationContext` associated with the event | Distinguishing the source context |
| `getSpringApplication()` | Source `SpringApplication` | Observing the Boot run milestone |
| `getArgs()` | Input arguments when running the application | Diagnostics under proper security policies |
| `getTimeTaken()` | `Duration`, or `null` if unknown | Tracking startup duration |

Example reading duration:

```java
@EventListener
public void onReady(ApplicationReadyEvent event) {
    Duration duration = event.getTimeTaken();
    if (duration != null) {
        System.out.println("Startup duration: "
                + duration.toMillis() + " ms");
    }
}
```

This snippet requires importing `Duration` and belongs inside a Spring bean. `getTimeTaken()` can be `null`, so do not call `toMillis()` before checking. Duration varies by machine and environment; **never hardcode a fixed millisecond stdout value** as an expected test result.

Do not log `getArgs()` verbatim in production if command-line arguments might contain sensitive information.

## 5. Complete Example with Java 17 and Spring Boot 3.5.0

A console example without a web server, clearly illustrating the exact order among:

1. `ApplicationStartedEvent`.
2. A completed `ApplicationRunner`.
3. `ApplicationReadyEvent`.

There is only **one runner** so printed output does not depend on ordering among multiple runners. The application closes the context after `SpringApplication.run(...)` returns.

### 5.1. Directory Structure

```text
ready-event-demo/
├── pom.xml
└── src/main/java/example/ReadyEventDemo.java
```

### 5.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>ready-event-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. File src/main/java/example/ReadyEventDemo.java

```java
package example;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class ReadyEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ReadyEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // SpringApplication.run has finished the runners
            // and published ApplicationReadyEvent before returning.
        }
    }

    @Bean
    public ApplicationRunner prepareDemoData() {
        return new ApplicationRunner() {
            @Override
            public void run(ApplicationArguments args) {
                System.out.println("02 ApplicationRunner completed");
            }
        };
    }

    @Bean
    public StartupObserver startupObserver() {
        return new StartupObserver();
    }

    public static class StartupObserver {
        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("01 ApplicationStartedEvent");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("03 ApplicationReadyEvent");
        }
    }
}
```

### 5.4. Running

Open a terminal in the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q spring-boot:run
```

**Lines printed by the example source code**, excluding Boot/Maven logs (if any):

```text
01 ApplicationStartedEvent
02 ApplicationRunner completed
03 ApplicationReadyEvent
```

Explanation:

- `@SpringBootApplication` and `SpringApplication.run` start the context.
- The `StartupObserver` bean is created by Spring via `@Bean`, and its `@EventListener` methods are registered before the final startup milestones.
- After refresh, Spring Boot publishes `ApplicationStartedEvent`; the first callback prints line 01.
- Spring Boot executes `ApplicationRunner.run`; line 02 appears once the runner has executed.
- Boot publishes `ApplicationReadyEvent` after the runner succeeds; the callback prints line 03.
- Following the standard startup sequence, Boot continues by publishing `ReadinessState.ACCEPTING_TRAFFIC`. The example does not print the availability event.
- `SpringApplication.run(...)` returns the context; `try-with-resources` calls `close()` so the console application exits.

Using `spring-boot-starter` (not `spring-boot-starter-web`) and setting `WebApplicationType.NONE` avoids starting an HTTP server. The example prints in deterministic order because there is only one runner and default listeners run synchronously. We do not use `Thread.sleep(...)` or assume random timing.

**Scope of evidence:** the example demonstrates the ordering of **Boot milestones**; it does not mean every background task triggered by a runner has also ended. If a runner dispatches an async task and returns immediately, Boot only knows the runner **returned**, not that the task completed.

## 6. ApplicationRunner and CommandLineRunner vs. the Ready Event

Both interfaces are invoked by Boot once the context has started, **before ApplicationReadyEvent**:

- `ApplicationRunner.run(ApplicationArguments args)` receives arguments parsed via `ApplicationArguments`.
- `CommandLineRunner.run(String... args)` receives arguments as a `String` array.

Example of two equivalent styles by purpose:

```java
@Bean
ApplicationRunner validateStartupConfig() {
    return args -> {
        // Validate required configuration.
    };
}

@Bean
CommandLineRunner verifyRequiredSchema() {
    return args -> {
        // Validate another required condition.
    };
}
```

This is integrated illustrative code; if placing both in an application, add the corresponding imports. When multiple runners exist and ordering is needed, Spring Boot supports `Ordered`/`@Order`. Do not assume execution order based on method names, declaration position in a file, or interface type.

**Choosing where to place logic:**

| Need | Where to Place | Reason |
| --- | --- | --- |
| Condition that must complete before serving | `ApplicationRunner` / `CommandLineRunner` | Boot waits for runners on the startup thread |
| Log/metrics on successful startup | `ApplicationReadyEvent` listener | Observes the exact ready milestone |
| Initializing a single bean | Constructor/DI/appropriate lifecycle | Responsibility belongs to the owning bean |
| Post-startup task allowed to fail without affecting readiness | Ready listener or managed background job | Does not block the startup path |
| Background work mandatory before traffic | Runner waits for task, or explicit readiness mechanism | Prevents announcing ready prematurely |

Spring Boot recommends running necessary startup tasks via runners rather than pushing lengthy work into `@PostConstruct`. `@PostConstruct` is for bean initialization, occurs during context construction, and easily creates hard-to-control bean ordering dependencies.

## 7. Distinguishing ApplicationReadyEvent and ReadinessState

The name `ApplicationReadyEvent` can make it seem like readiness only has two states ("not ready / ready") throughout the lifecycle. In reality:

- The **ready event** is a notification tied to a **startup run**.
- **Readiness state** reflects whether the application wants/is allowed to accept new traffic **at the current moment**.
- `ApplicationAvailability` is the API to retrieve the current availability state.
- `AvailabilityChangeEvent` is used to publish an availability state transition.

The two standard readiness states are:

| `ReadinessState` | Meaning |
| --- | --- |
| `ACCEPTING_TRAFFIC` | The application is ready to accept traffic |
| `REFUSING_TRAFFIC` | The application is not yet / does not want to accept traffic |

Per Spring Boot's mechanism, readiness is published as `ACCEPTING_TRAFFIC` **after** `ApplicationReadyEvent`. Therefore, **reading `ApplicationAvailability.getReadinessState()` inside a ready listener may still observe the previous state**; do not use the ready callback as an assertion that the `ACCEPTING_TRAFFIC` availability event has already been published.

A listener observing readiness changes:

```java
@EventListener
public void onReadiness(AvailabilityChangeEvent<ReadinessState> event) {
    if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
        // Ready to accept traffic.
    } else {
        // Not yet accepting traffic.
    }
}
```

This snippet needs imports for `AvailabilityChangeEvent`, `ReadinessState`, `@EventListener` and belongs in a Spring bean; it is not part of the runnable example in section 5.

`ApplicationReadyEvent` is a fixed milestone of a startup run; readiness state can transition to `REFUSING_TRAFFIC` when the service is overloaded and back to `ACCEPTING_TRAFFIC` without producing a new `ApplicationReadyEvent`.

### Actuator Readiness Probes and Kubernetes

When using Spring Boot Actuator with properly configured health probes, a readiness endpoint can be read by Kubernetes or a load balancer to decide when to route requests. The `ApplicationReadyEvent` event **is not an HTTP readiness endpoint**. Probing requires Actuator configuration and deployment environment policies; the event does not turn itself into an HTTP route.

You must also distinguish **liveness** from **readiness**. Liveness asks whether the process is still in a valid state to keep running; readiness asks whether new traffic should be sent to it. A temporarily failing external API dependency is normally a readiness concern, not a reason to force repeated restarts via liveness.

## 8. Using @Async on a Ready Listener

Some post-startup tasks, such as generating best-effort summary reports, can run in the background:

```java
@Component
public class ReadyBackgroundJob {
    @Async("maintenanceExecutor")
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Work not mandatory before serving.
    }
}
```

This is illustrative code requiring `@EnableAsync`, the `maintenanceExecutor` executor bean, and corresponding imports. With Spring `@Async`, the listener call can be handed off to a thread pool, letting Boot continue startup.

**Risk:** after the listener submits the task to the executor, Boot may still publish `ReadinessState.ACCEPTING_TRAFFIC` even though the task has not finished. If that task loads mandatory data or checks essential migrations, the application may receive requests in an incomplete state.

Design anti-pattern:

```java
@Async("maintenanceExecutor")
@EventListener
public void onReady(ApplicationReadyEvent event) {
    mandatoryCatalog.loadAll();
}
```

This snippet requires the `mandatoryCatalog` dependency; it is not a standalone program. If the catalog is an indispensable precondition before receiving traffic, execute/await it inside a runner, or coordinate readiness explicitly via an appropriate health/checkpoint system. Do not conclude startup is safe merely because `@Async` returns fast.

Other consequences of using async:

1. Exceptions in `@Async void` methods are not propagated automatically to the caller; an `AsyncUncaughtExceptionHandler` or proper error handling is required.
2. An overloaded pool can reject tasks; monitor `TaskRejectedException` and define retry/backpressure policies.
3. Worker threads do not automatically inherit transactions, security context, or MDC from the startup thread.
4. A process crash can lose in-memory tasks; use durable mechanisms if the work cannot be lost.
5. Never assume completion order among multiple async listeners matches registration order.

**Subtle note:** Boot publishes `ACCEPTING_TRAFFIC` **after the ready callback**. Thus, if a ready listener itself publishes `ReadinessState.REFUSING_TRAFFIC` inside the callback, that state may be overwritten by Boot's subsequent accepting publication. If you must control startup readiness, use a runner/health condition at the right point instead of relying on flipping state inside a ready callback.

## 9. Changing Readiness After Startup

While running, an application may become overloaded or lose a critical resource. You can publish state from a Spring bean injected with `ApplicationEventPublisher`:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.REFUSING_TRAFFIC);
```

When recovered and genuinely able to accept more requests:

```java
AvailabilityChangeEvent.publish(
        publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
```

These two snippets require importing `AvailabilityChangeEvent`, `ReadinessState`, and an injected `publisher` variable; they are not standalone examples. They control runtime **availability state**; they do not replace `ApplicationReadyEvent` and do not directly allocate or close resources.

Do not publish `ACCEPTING_TRAFFIC` merely because one dependency just became pingable if the system is not yet business-ready. Define a complete set of conditions for readiness and recovery.

## 10. Why Might ApplicationReadyEvent Not Be Published?

Typical causes:

| Symptom | Possible Explanation | How to Check |
| --- | --- | --- |
| Startup stops before ready | Bean/configuration or runner threw an exception | Check original error and `ApplicationFailedEvent` path |
| Listener does not receive it | Class is not a Spring bean, outside component scan, or wrong event type | Check `@Bean`/`@Component` and method signature |
| Running `AnnotationConfigApplicationContext.refresh()` directly | This is a Spring Framework context, not `SpringApplication.run` sequence | Use Boot `SpringApplication` to test Boot events |
| Ready log appears late | Async listener or startup process takes a long time | Inspect runners, executors, threads, and timestamps |
| Multi-context system | Event originates from another context, listener may be called multiple times | Inspect `event.getApplicationContext()` |
| Context stopped before ready | Startup failed or process terminated early | Inspect lifecycle and shutdown cause |

**If an `ApplicationRunner` throws an error**, Boot does not complete the successful startup path and does not publish the corresponding ready event. Catching and continuing in a runner just to "let Boot become ready" can mask an unmet mandatory requirement.

A synchronous ready listener throwing an unhandled exception can disrupt `SpringApplication.run(...)` completion. If used only for auxiliary logging, consider handling errors inside the callback so a minor observability failure does not become a startup failure.

## 11. Multiple ApplicationContexts and Receiving Events Multiple Times

Spring Boot may use a hierarchy of `SpringApplication`s or `ApplicationContext`s. Events published from a child context can propagate up to the parent context, causing listeners in the parent to receive the corresponding events. For logic meant to handle only "this exact context's ready", compare the source:

```java
@Component
public class LocalReadyOnly {
    private final ApplicationContext ownContext;

    public LocalReadyOnly(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        // Handle ready only for the matching context.
    }
}
```

This is an integration snippet requiring imports for `ApplicationContext`, `@Component`, `@EventListener`, and `ApplicationReadyEvent`. When an application has only one context, this filter may be unnecessary. With multiple contexts, do not equate a single child context being ready with the **entire process** being ready.

Additionally, restarting or redeploying an application triggers a new startup. A callback performing important side effects (e.g., sending an external notification) should be designed idempotently so valid restarts/retries do not create duplicates.

## 12. Testing the Event and Ready Milestone

The test suite should separate three concerns:

1. **Event presence:** `ApplicationReadyEvent` is actually published when Boot startup succeeds.
2. **Correct timing:** the event occurs after runners, but before accepting readiness is published.
3. **Correct conditions:** failed startup is not treated as ready; incomplete background tasks are not hidden.

Minimum test matrix:

| Scenario | Expected Result |
| --- | --- |
| One runner completes successfully | `ApplicationStartedEvent` → runner → `ApplicationReadyEvent` |
| Runner throws an exception | No successful ready event for that startup run |
| `getTimeTaken()` has a value | Verify `Duration` type and non-negative duration, without asserting a fixed number |
| `@Async` listener runs long work | Do not conclude work finished when Boot publishes ready |
| Pure context without running `SpringApplication` | Do not expect Boot ready event to be published automatically |
| Application with parent/child contexts | Verify which context the event belongs to |
| Instance became ready and later loses serving capability | Readiness state can change without a new ready event |

Test the section 5 example by running with Maven and comparing the three lines `01`, `02`, `03`. If replacing the runner with an error-throwing snippet to test startup failure, use a separate fixture or process and confirm the ready callback is not invoked. Do not test by calling `new ReadyEventDemo.StartupObserver().onReady(...)` directly and treating that as proof Boot published the event.

With `@SpringBootTest`, the Spring context may already be initialized **before the test method runs**. Therefore, a listener created late inside a test body will miss startup milestones. Register the listener properly within the startup lifecycle under test and await async results via a latch/future with a timeout, not just `Thread.sleep(...)`.

## 13. Common Mistakes

1. **Confusing `ApplicationStartedEvent` with `ApplicationReadyEvent`.** Started is after refresh but before runners; ready is after runners.
2. **Using `ContextRefreshedEvent` as proof of Boot startup completion.** Refresh does not include runners yet.
3. **Assuming ready is the absolute final event.** After ready comes `AvailabilityChangeEvent` with `ACCEPTING_TRAFFIC`, and the application continues publishing many other events while running.
4. **Assuming the ready event means all dependencies are healthy.** Separate health/readiness checks are required.
5. **Doing mandatory initialization in `@Async @EventListener(ApplicationReadyEvent)`.** Boot may accept traffic before the task ends.
6. **Letting a synchronous listener block too long.** The callback can prolong startup; prefer an appropriate runner or background task.
7. **Forgetting to make the listener a Spring bean.** Annotations on a Java object created externally with `new` are not auto-registered.
8. **Using plain Spring Framework and expecting Boot events.** You must run via `SpringApplication`.
9. **Asserting startup against a hardcoded duration.** `getTimeTaken()` varies and can be `null`.
10. **Ignoring the source context.** In a hierarchy, a listener may see events belonging to a child context.
11. **Using `@TransactionalEventListener` for the ready event.** Normally there is no business transaction; with `fallbackExecution = false` the callback will not run. Use `@EventListener`.
12. **Manually instantiating `ApplicationReadyEvent` to mark the app ready.** Publishing an event object does not execute Boot's full startup and does not replace availability state.
13. **Assuming a ready listener runs strictly once forever.** Every deploy/restart has a new lifecycle; idempotency is needed for critical side effects.
14. **Ignoring exceptions in callbacks.** An error in a synchronous listener can disrupt startup; an async error may only go to a handler/log.

## 14. Application Checklist

- [ ] Used `ApplicationReadyEvent` from package `org.springframework.boot.context.event`.
- [ ] Understood `ApplicationStartedEvent` runs before runners and `ApplicationReadyEvent` runs after them.
- [ ] Distinguished the ready event from `ReadinessState.ACCEPTING_TRAFFIC` published afterward.
- [ ] Listener is a Spring bean or registered at the proper time.
- [ ] Mandatory startup conditions are not hidden inside a fire-and-forget `@Async` task.
- [ ] Listener tasks have appropriate timeout, error handling, and observability policies.
- [ ] `getTimeTaken()` is checked for `null` before use.
- [ ] Tested both successful and failed startups, rather than merely invoking the listener method manually.
- [ ] With multi-context hierarchies, clearly identified which context the event comes from.
- [ ] Did not confuse the one-time ready event with runtime readiness health state changes.
- [ ] Critical side effects are protected by idempotency/retry or durable job/outbox mechanisms.

**Takeaway:** `ApplicationReadyEvent` is the milestone where Spring Boot has finished executing runners in a successful startup. To initialize mandatory data before accepting traffic, use runners and await completion; to observe startup completion, use a ready listener; to coordinate traffic according to changing runtime status, use readiness state and health probes.

## References

- [Spring Boot — SpringApplication / Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Application Availability and Readiness State](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability)
- [Spring Boot Javadoc — ApplicationReadyEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html)
- [Spring Boot Javadoc — ApplicationStartedEvent](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
- [Spring Boot Javadoc — ReadinessState](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ReadinessState.html)
