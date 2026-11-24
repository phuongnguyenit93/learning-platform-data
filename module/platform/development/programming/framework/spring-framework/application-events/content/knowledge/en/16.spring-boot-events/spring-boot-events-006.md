# ApplicationStartedEvent in Spring Boot

## 1. Lesson Objectives

`ApplicationStartedEvent` belongs to the **Spring Boot application events** group and represents a specific milestone during `SpringApplication.run(...)`: **the ApplicationContext has finished refreshing, but `ApplicationRunner` and `CommandLineRunner` beans have not been invoked yet**.

The full name of this type is `org.springframework.boot.context.event.ApplicationStartedEvent`. This is an event about the **Spring Boot application lifecycle**, not a domain event such as `OrderCreated` or `PaymentCompleted`.

After this lesson, you will understand:

- When Spring Boot publishes `ApplicationStartedEvent` and why this milestone differs from `ApplicationReadyEvent`.
- How to receive the event via `@EventListener` and `ApplicationListener<ApplicationStartedEvent>`.
- Event properties such as `getApplicationContext()`, `getArgs()`, and `getTimeTaken()`.
- The ordering relative to `ContextRefreshedEvent`, runners, and liveness/readiness states.
- Issues related to startup failure, synchronous/asynchronous listeners, multiple contexts, and testing.
- How to run a Java 17+ program that deterministically verifies the ordering.

## 2. Position of `ApplicationStartedEvent` in the Startup Cycle

A typical `SpringApplication.run` pass goes through these main milestones:

~~~text
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  |
  +-- refresh ApplicationContext
  |      |
  |      +-- bean definitions, BeanPostProcessors, singleton, lifecycle
  |      +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- AvailabilityChangeEvent(LivenessState.CORRECT)
  |
  +-- ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent
  +-- AvailabilityChangeEvent(ReadinessState.ACCEPTING_TRAFFIC)
  |
  +-- SpringApplication.run(...) returns ApplicationContext
~~~

This is a summary diagram of **relevant milestones**; internal steps such as environment preparation, web server configuration, and context callbacks involve more detail. For example, a `WebServerInitializedEvent` may be published during web server preparation, before the started milestone.

**Key invariants:**

1. `ApplicationStartedEvent` occurs **after context refresh succeeds**.
2. It occurs **before Boot invokes application/command-line runners**.
3. `ApplicationReadyEvent` occurs **after runners finish executing**.
4. Boot publishes `LivenessState.CORRECT` right after started, and `ReadinessState.ACCEPTING_TRAFFIC` after ready. **Live** and **ready** are two distinct states.

Per the `SpringApplicationRunListener` contract, the `started(context, timeTaken)` method describes the exact point when refresh has completed but runners have not yet been called; `ready(context, timeTaken)` is called after runners. Spring Boot publishes `ApplicationStartedEvent` through the application events mechanism so application listeners can react to that started milestone.

### Started Does Not Mean Ready to Serve Every Request

An application may have published `ApplicationStartedEvent` while still needing to run runners that load data, verify encryption keys, prepare integration systems, or perform other initialization steps. Therefore, **do not use started as the sole signal permitting traffic**. Spring Boot has dedicated readiness and health/availability concepts to coordinate this.

For web applications, the fact that the web server has bound a port does not by itself prove all business logic is ready. Context refresh, server initialized, started, ready, and application availability are distinct milestones and contracts.

## 3. Event Properties

`ApplicationStartedEvent` is a subclass of `SpringApplicationEvent` and provides useful APIs:

| API | Value and Meaning |
| --- | --- |
| `getApplicationContext()` | The `ConfigurableApplicationContext` that just started; used to identify the source context |
| `getSpringApplication()` | The `SpringApplication` instance associated with the run |
| `getArgs()` | The `String[]` arguments passed into `SpringApplication` |
| `getTimeTaken()` | `Duration` up to the started milestone, or `null` if unknown |

Illustrative example of reading them:

~~~java
// Method of a Spring-managed bean, not yet a standalone program.
@EventListener
public void started(ApplicationStartedEvent event) {
    ConfigurableApplicationContext context = event.getApplicationContext();
    Duration elapsed = event.getTimeTaken();

    System.out.println("Context ID = " + context.getId());
    if (elapsed != null) {
        System.out.println("Started after " + elapsed.toMillis() + " ms");
    }
}
~~~

Startup duration depends on machine and system load, with no fixed stdout milliseconds. `getTimeTaken()` is not a measurement of the entire startup phase through ready, because runners executing after started are not yet included. If you need duration until ready, use `ApplicationReadyEvent.getTimeTaken()` along with detailed profiling tools.

## 4. Registering a Listener with `@EventListener`

Because `ApplicationStartedEvent` is published **after** refresh, a Spring-managed bean can receive the event with `@EventListener`:

~~~java
@Component
public class StartedObserver {
    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Boot context started: "
                + event.getApplicationContext().getId());
    }
}
~~~

This is an illustrative snippet where the class needs imports for `@Component`, `@EventListener`, and `ApplicationStartedEvent`, and is component-scanned or declared as a bean in a real application.

The listener is selected by Spring based on event type. With the default synchronous multicaster, the method executes on the event-publishing thread, before the runner stage. You do not need to publish `ApplicationStartedEvent` yourself; Spring Boot publishes it during `SpringApplication.run`.

If the listener only records metrics/logs or checks a brief condition, this approach is straightforward. If the listener makes network calls or waits a long time, it can prolong startup or cause startup to fail if an exception goes unhandled.

## 5. Registering with `ApplicationListener`

You can also implement `ApplicationListener<ApplicationStartedEvent>`:

~~~java
public final class StartedListener
        implements ApplicationListener<ApplicationStartedEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartedEvent event) {
        System.out.println("Boot started: "
                + event.getApplicationContext().getId());
    }
}
~~~

The illustrative code above requires importing `org.springframework.context.ApplicationListener` and the Boot event type. Register `StartedListener` as a Spring bean, or instantiate it and register it directly via `SpringApplication.addListeners(listener)` **before** calling `run()`.

Example with direct registration:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new StartedListener());
app.run(args);
~~~

This is illustrative code inside `main`; `MyApplication` must be defined. Do not accidentally register the same listener twice, or it may process a single event multiple times.

### Note on Earlier Events

`ApplicationStartingEvent` is published very early, **before `ApplicationContext` is created**. A listener existing solely as a bean inside the context cannot receive events that already occurred earlier. To observe early startup events, use a listener registered with `SpringApplication` before `run()` or an early registration mechanism supported by Boot.

`ApplicationStartedEvent` differs in that the context is already ready, so beans with `@EventListener` can receive it.

## 6. Standalone Java 17+ Example: Verifying the Order of Five Milestones

The program below uses **Spring Boot 3.3.13**, Java 17+, and Maven. No web server is created, keeping observation focused on startup events.

We use an `AtomicInteger` counter to prove:

1. `ContextRefreshedEvent` runs first.
2. `ApplicationStartedEvent` runs after refresh.
3. `ApplicationRunner` is invoked after started.
4. `ApplicationReadyEvent` is invoked after the runner.
5. `SpringApplication.run()` returns to `main` once the steps above have completed.

No `Thread.sleep` is used to guess ordering; each callback verifies the exact prior state.

Structure:

~~~text
boot-started-event/
├── pom.xml
└── src/main/java/demo/ApplicationStartedDemo.java
~~~

### 6.1. `pom.xml`

~~~xml
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
    <artifactId>boot-started-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
~~~

### 6.2. `src/main/java/demo/ApplicationStartedDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication(proxyBeanMethods = false)
public class ApplicationStartedDemo {

    public static final class Progress {
        private final AtomicInteger step = new AtomicInteger();

        public void advance(int expected, int next, String label) {
            if (!step.compareAndSet(expected, next)) {
                throw new IllegalStateException(
                    "Expected " + expected + " but actual " + step.get());
            }
            System.out.println(label);
        }

        public int value() {
            return step.get();
        }
    }

    public static final class StartupEvents {
        private final Progress progress;

        public StartupEvents(Progress progress) {
            this.progress = progress;
        }

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            progress.advance(0, 1, "1 ContextRefreshedEvent");
        }

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            progress.advance(1, 2, "2 ApplicationStartedEvent");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            progress.advance(3, 4, "4 ApplicationReadyEvent");
        }
    }

    @Bean
    public Progress progress() {
        return new Progress();
    }

    @Bean
    public StartupEvents startupEvents(Progress progress) {
        return new StartupEvents(progress);
    }

    @Bean
    public ApplicationRunner runner(Progress progress) {
        return new ApplicationRunner() {
            @Override
            public void run(ApplicationArguments args) {
                progress.advance(2, 3, "3 ApplicationRunner");
            }
        };
    }

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ApplicationStartedDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            Progress progress = context.getBean(Progress.class);
            if (progress.value() != 4) {
                throw new AssertionError("Unexpected startup lifecycle");
            }
            System.out.println("5 SpringApplication.run returned");
        }
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q spring-boot:run
~~~

Five lines printed by the program itself (in exact order):

~~~text
1 ContextRefreshedEvent
2 ApplicationStartedEvent
3 ApplicationRunner
4 ApplicationReadyEvent
5 SpringApplication.run returned
~~~

The console may also contain additional logs from Maven/Spring, but the order of the **five lines printed by the example code** is enforced by `Progress.advance`.

### 6.3. Why Is the Output Reliable?

- The refresh portion of `SpringApplication.run` publishes `ContextRefreshedEvent`. The listener bean was registered during context initialization; the counter moves from 0 to 1.
- Spring Boot publishes `ApplicationStartedEvent` after refresh; the counter moves from 1 to 2.
- `ApplicationRunner` is invoked next by Boot and moves the counter from 2 to 3.
- `ApplicationReadyEvent` is published after the runner and moves the counter from 3 to 4.
- `SpringApplication.run` returns `ConfigurableApplicationContext`, and then `main` reads counter 4 and prints the final line.

Here `WebApplicationType.NONE` eliminates the web server. The example has only a single context without hierarchy, one runner, synchronous listeners, and no `@Async` enabled, so the milestones are relatively clear. In projects with multiple runners, context hierarchies, or async callbacks, you must further examine the scope and guarantees you need.

## 7. Comparing Easily Confused Events

| Event | When Published | Usage Suggestion |
| --- | --- | --- |
| `ApplicationStartingEvent` | Very early, before environment/context are ready | Register listener prior to `run()` |
| `ApplicationEnvironmentPreparedEvent` | Environment prepared, context not yet created | Hook for preparing environment configuration |
| `ApplicationPreparedEvent` | Context prepared and definitions loaded, not yet refreshed | Observe step right before refresh |
| `ContextRefreshedEvent` | A Spring `ApplicationContext` finishes refreshing | Listen to container context lifecycle |
| `ApplicationStartedEvent` | **After refresh, before runners** | Hook/metrics at the started milestone |
| `ApplicationReadyEvent` | After runners | Work requiring Boot to have completed startup |
| `ApplicationFailedEvent` | Startup raised an exception | Error-branch handling/recording |

**`ContextStartedEvent` is not `ApplicationStartedEvent`.** `ContextStartedEvent` is a Spring Framework event published in connection with `ConfigurableApplicationContext.start()`; `ApplicationStartedEvent` is a startup event published by Spring Boot inside `SpringApplication.run()`. Do not assume these two names mean the same thing.

## 8. Startup Failure: Started May Have Happened While Ready Has Not

There are two critical failure points:

**Failure before refresh succeeds:** Boot has not reached the started milestone, so `ApplicationStartedEvent` does not appear. `ApplicationFailedEvent` may be published to report the failure cause.

**Failure in `ApplicationRunner`/`CommandLineRunner`:** Boot already published `ApplicationStartedEvent` beforehand; the runner throwing an exception causes startup to fail. `ApplicationReadyEvent` does not appear along the normal startup flow.

Example:

~~~java
// Illustrative snippet of a failing runner; not a standalone class.
@Bean
ApplicationRunner failingRunner() {
    return args -> {
        throw new IllegalStateException("Required configuration unavailable");
    };
}
~~~

If adding this failing runner, determine runner invocation order when multiple runners exist. Do not use the started event as proof that "the application started successfully" when post-refresh steps can still fail.

For monitoring, it is generally better to distinguish **context created**, **started**, **ready**, and **failed** states rather than storing a single boolean flag `started=true`.

## 9. Synchronous, `@Async`, and Completion Timing

### Default Synchronous Listeners

With the default `SimpleApplicationEventMulticaster`, listener callbacks are invoked synchronously during event dispatch. A slow `ApplicationStartedEvent` listener can delay runners and readiness. An unhandled exception in a synchronous callback can cause `SpringApplication.run` to fail depending on error handler configuration.

Do not place un-timeouted network requests, large migrations, or tasks that could hang inside a synchronous startup listener without error management.

### Asynchronous Listeners

If a bean has `@Async`, the application enables `@EnableAsync`, and a suitable executor is configured, the listener body can execute on a background thread:

~~~java
// Illustration: requires @EnableAsync and an executor bean named startupExecutor.
@Async("startupExecutor")
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    warmupCache();
}
~~~

The event still carries the meaning of the started milestone, yet **Boot does not implicitly wait for this async task to finish before calling runners**. If a runner depends on a warmed cache, a race condition will occur. When dependencies exist, use a coordination step that explicitly awaits the result, or let the runner directly execute/await the required work.

Async threads do not automatically carry transactions, `ThreadLocal`s, security context, or MDC from the publishing thread. Decide how to propagate context, log errors, retry, and handle executor saturation.

### `getTimeTaken()` and Performance

`getTimeTaken()` measures up to the **started milestone**. It does not reflect runner duration because runners have not executed yet. To find bottlenecks, combine time-to-ready with observing startup steps using appropriate tools (e.g., `ApplicationStartup`, metrics/tracing).

## 10. Parent/Child Contexts and Receiving Multiple Events

Spring allows parent and child contexts. Events published in a child can propagate up to the parent, causing listeners in the parent to receive additional events. If processing is meant only for the context owning the bean, check identity:

~~~java
// Illustration inside a bean with ApplicationContext ownContext injected.
@EventListener
public void onStarted(ApplicationStartedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    initializeForOwnContext();
}
~~~

This illustrative snippet needs declarations for `ownContext` and `initializeForOwnContext`. With multiple `SpringApplication`s, integration tests, or context hierarchies, do not use a JVM-wide static variable to assert an event happens only once in the lifetime of the process.

When a startup action has side effects, design it to be safely repeatable without creating duplicate records, sending duplicate notifications, or claiming resources multiple times. This is especially valuable when tests run multiple contexts.

## 11. Choosing the Right Tool for the Requirement

| Practical Need | Appropriate Tool |
| --- | --- |
| Record the milestone where context refresh finished but runners have not run | `ApplicationStartedEvent` |
| Run a controlled initialization step after refresh | `ApplicationRunner` or `CommandLineRunner` |
| React after all runners and Boot's startup process | `ApplicationReadyEvent` |
| Track live/ready status for accepting traffic | `ApplicationAvailability`, health/readiness probes |
| Manage start/stop of a resource tied to the context | `SmartLifecycle` or appropriate lifecycle interface |
| Catch events before the context exists | `ApplicationListener` registered early with `SpringApplication` |
| Handle startup failures | `ApplicationFailedEvent`, logging, and error handling |

### Common Mistakes

- **Confusing started with ready:** `ApplicationStartedEvent` occurs **before** runners. Do not build request-serving readiness conditions solely on this event.
- **Confusing starting with started:** `ApplicationStartingEvent` occurs very early; ordinary bean listeners may not exist yet.
- **Confusing Boot with Framework:** `ContextStartedEvent` is not identical to `ApplicationStartedEvent`.
- **Blocking startup indefinitely:** synchronous listeners making slow network calls or waiting on Futures without timeouts.
- **Assuming an async listener finishes before runners:** when using `@Async`, Boot only knows the listener was scheduled; the work may not have finished yet.
- **Ignoring runner failures:** started was published, yet ready may never appear if a runner fails.
- **Not filtering context:** callbacks in a parent receive events from a child and unintentionally execute multiple times.
- **Misreading timing:** `getTimeTaken()` at started excludes runners; its value may be `null`.
- **Using `@TransactionalEventListener` without a transaction:** Boot lifecycle events are usually not bound to an active transaction, and default transaction-bound listeners may skip the event.

## 12. Self-Check Exercises

1. Run the Java example; explain why `ContextRefreshedEvent` appears before `ApplicationStartedEvent`.
2. Add a `CommandLineRunner`. If a specific order among multiple runners is needed, use `@Order`/`Ordered` and test it. Do not assume a deterministic order when unconfigured.
3. Create a runner that throws an exception; predict which events were published and which do not appear.
4. Print `getTimeTaken()` at started and ready. Why can measurements differ across runs and between the two events?
5. Change a started listener to `@Async` and add slow processing; check whether runners wait for the listener to finish.
6. In an application with parent/child contexts, use `getApplicationContext()` to ensure the listener handles only the intended source.

**Takeaway:** `ApplicationStartedEvent` marks that Spring Boot has finished refreshing the context and is about to invoke runners. To confirm that post-refresh startup tasks have completed, use the ready milestone and appropriate readiness conditions.

## Official Documentation

- Spring Boot — SpringApplication events and startup order: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot 3.3 — `ApplicationStartedEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html
- Spring Boot 3.3 — `SpringApplicationRunListener` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplicationRunListener.html
- Spring Boot 3.3 — `ApplicationReadyEvent` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/event/ApplicationReadyEvent.html
- Spring Framework — ApplicationContext events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
